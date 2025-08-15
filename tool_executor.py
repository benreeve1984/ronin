# Unified Tool Executor for Ronin
# =================================
# This module handles all tool execution in one place, eliminating duplication
# between agent.py and chat_mode.py. It manages confirmations, dry runs, and formatting.

from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import difflib
import json
from datetime import datetime
from tool_registry import get_tool, ToolDefinition, TOOLS
from prompts import get_confirmation_prompt
import tools
from exceptions import (
    RoninError, ToolNotFoundError, FileNotFoundError, FileAlreadyExistsError,
    SandboxViolationError, InvalidFileTypeError, AnchorNotFoundError,
    InvalidParameterError, ToolExecutionError, UserDeclinedError,
    find_similar_paths, find_similar_text
)
from logging_config import ToolExecutionLogger, get_logger

# Module logger
logger = get_logger("tool_executor")

class ToolExecutor:
    """
    Centralized tool execution handler.
    
    This class is responsible for:
    1. Validating tool inputs
    2. Handling user confirmations
    3. Executing tools (or simulating in dry-run mode)
    4. Formatting outputs
    5. Managing file memory in chat mode
    
    Attributes:
        root: The sandbox root directory
        auto_yes: Whether to auto-approve confirmations
        dry_run: Whether to simulate without actual changes
        file_memory: Optional file memory for chat mode
    """
    
    def __init__(self, root: Path, auto_yes: bool = False, dry_run: bool = False, file_memory=None):
        """
        Initialize the tool executor.
        
        Args:
            root: Project root directory (sandbox boundary)
            auto_yes: Skip confirmation prompts if True
            dry_run: Simulate execution without making changes
            file_memory: Optional FileMemory instance for chat mode
        """
        self.root = root
        self.auto_yes = auto_yes
        self.dry_run = dry_run
        self.file_memory = file_memory  # For chat mode context tracking
        
        # Dispatch table for tool execution
        self._tool_executors = {
            "list_files": self._execute_list_files,
            "read_file": self._execute_read_file,
            "search_files": self._execute_search_files,
            "create_file": self._execute_create_file,
            "delete_file": self._execute_delete_file,
            "modify_file": self._execute_modify_file,
            # Git tools
            "git_status": self._execute_generic,
            "git_diff": self._execute_generic,
            "git_commit": self._execute_git_commit,
            "git_log": self._execute_generic,
            "git_branch": self._execute_git_branch,
            "git_revert": self._execute_git_revert,
        }
        
        # Initialize operation history
        self._init_history()
    
    def execute(self, tool_name: str, args: Dict[str, Any]) -> Tuple[str, bool]:
        """
        Execute a tool and return formatted output.
        
        Args:
            tool_name: Name of the tool to execute
            args: Arguments for the tool
            
        Returns:
            Tuple of (output_string, success_boolean)
        """
        # Use structured logging to track execution
        with ToolExecutionLogger(tool_name) as log:
            try:
                # Get the tool definition
                tool_def = get_tool(tool_name)
                if not tool_def:
                    available = list(TOOLS.keys())
                    error = ToolNotFoundError(tool_name, available)
                    log.error("Tool not found", error=str(error), 
                             recovery_hints=error.recovery_hints)
                    return error.to_claude_message(), False
                
                # Log the execution start (to file only)
                log.debug(f"Executing {tool_name}", context={"args": args})
                
                # Print simple execution header for user
                self._print_execution_header(tool_name, args)
                
                # Validate parameters
                self._validate_parameters(tool_def, args)
                
                # Execute using dispatch table or generic handler
                executor = self._tool_executors.get(tool_name, self._execute_generic)
                result = executor(tool_def, args)
                
                # Standardized success message
                output, success = result
                if success:
                    # Make tool name human-readable
                    display_name = tool_name.replace('_', ' ').title()
                    print(f"  ✅ {display_name} completed successfully")
                
                # Log to history for important operations
                if tool_name in ["create_file", "delete_file", "modify_file", 
                                 "git_commit", "git_branch", "git_revert"]:
                    self._log_operation(tool_name, args, success, output)
                
                log.debug(f"{tool_name} completed")
                return result
                    
            except RoninError as e:
                # Our custom errors with recovery hints
                log.error(f"{tool_name} failed", error=type(e).__name__,
                         recovery_hints=e.recovery_hints, context=e.context)
                print(f"  ❌ {e.message}")
                return e.to_claude_message(), False
                
            except Exception as e:
                # Unexpected errors - wrap them
                error = ToolExecutionError(tool_name, e)
                log.error(f"{tool_name} crashed", error=str(e),
                         recovery_hints=error.recovery_hints)
                print(f"  ❌ Unexpected error: {e}")
                return error.to_claude_message(), False
    
    def _validate_parameters(self, tool_def: ToolDefinition, args: Dict):
        """Validate tool parameters before execution."""
        for param_name, param_spec in tool_def.parameters.items():
            # Check required parameters
            if param_spec.get("required") and param_name not in args:
                raise InvalidParameterError(
                    param_name, 
                    f"required {param_spec.get('type', 'parameter')}", 
                    "missing"
                )
            
            # Check parameter types if present
            if param_name in args:
                value = args[param_name]
                expected_type = param_spec.get("type")
                
                if expected_type == "string" and not isinstance(value, str):
                    raise InvalidParameterError(param_name, "string", value)
                elif expected_type == "number" and not isinstance(value, (int, float)):
                    raise InvalidParameterError(param_name, "number", value)
                elif expected_type == "boolean" and not isinstance(value, bool):
                    raise InvalidParameterError(param_name, "boolean", value)
    
    def _print_execution_header(self, tool_name: str, args: Dict):
        """Print execution header based on tool type."""
        display_name = tool_name.replace('_', ' ').title()
        print(f"\n🔧 Executing: {display_name}", end="")
        
        if tool_name == "search_files":
            text = args.get("text", "?")
            print(f" (searching for: '{text[:30]}...')" if len(text) > 30 else f" (searching for: '{text}')")
        elif tool_name == "modify_file":
            action = args.get("action", "?")
            anchor = args.get("anchor", "")
            if anchor:
                print(f" ({action} anchor: '{anchor[:30]}...')" if len(anchor) > 30 else f" ({action} anchor: '{anchor}')")
            else:
                print(f" ({action} file boundaries)")
        elif tool_name in ("read_file", "create_file", "delete_file"):
            print(f" ({args.get('path', '?')})")
        else:
            print()
    
    def _execute_list_files(self, tool_def: ToolDefinition, args: Dict) -> Tuple[str, bool]:
        """Execute list_files tool."""
        pattern = args.get("pattern", "*")
        result = tool_def.handler(self.root, pattern)
        output = tool_def.formatter(result) if tool_def.formatter else str(result)
        return output, True
    
    def _execute_read_file(self, tool_def: ToolDefinition, args: Dict) -> Tuple[str, bool]:
        """Execute read_file tool with path validation."""
        path = tools.validate_path(self.root, args["path"])
        start_line = int(args.get("start_line", 1))
        end_line = int(args.get("end_line")) if args.get("end_line") else None
        
        content = tool_def.handler(path, start_line, end_line)
        
        # Track in file memory if available (chat mode)
        if self.file_memory and start_line == 1 and end_line is None:
            self.file_memory.add_file(str(path), content)
        
        # Format output
        if tool_def.formatter:
            output = tool_def.formatter(path, content, start_line, end_line)
        else:
            output = content
        
        return output, True
    
    def _execute_search_files(self, tool_def: ToolDefinition, args: Dict) -> Tuple[str, bool]:
        """Execute search_files tool."""
        text = args["text"]
        pattern = args.get("pattern", "*")
        case_sensitive = args.get("case_sensitive", False)
        context_lines = int(args.get("context_lines", 2))
        
        result = tool_def.handler(self.root, text, pattern, case_sensitive, context_lines)
        output = tool_def.formatter(result) if tool_def.formatter else str(result)
        return output, True
    
    def _execute_create_file(self, tool_def: ToolDefinition, args: Dict) -> Tuple[str, bool]:
        """Execute create_file with confirmation."""
        path = tools.validate_path(self.root, args["path"])
        content = args["content"]
        
        if self.dry_run:
            print(f"  → [DRY RUN] Would create: {path}")
            return f"[DRY RUN] Would create {path} with {len(content)} bytes", True
        
        # Ask for confirmation if needed
        if not self.auto_yes and tool_def.needs_confirmation:
            preview = content[:100] + "..." if len(content) > 100 else content
            prompt = get_confirmation_prompt("create", path=path, preview=preview)
            if input(prompt).lower() not in ("y", "yes"):
                return "User declined file creation", False
        
        # Create the file
        info = tool_def.handler(path, content)
        
        # Track in file memory if available
        if self.file_memory:
            self.file_memory.add_file(str(path), content)
        
        # Don't include file content in output
        output = f"Created {path} ({info['lines']} lines, {info['size']} bytes)"
        return output, True
    
    def _execute_delete_file(self, tool_def: ToolDefinition, args: Dict) -> Tuple[str, bool]:
        """Execute delete_file with confirmation."""
        path = tools.validate_path(self.root, args["path"])
        
        if self.dry_run:
            print(f"  → [DRY RUN] Would delete: {path}")
            return f"[DRY RUN] Would delete {path}", True
        
        # Ask for confirmation if needed
        if not self.auto_yes and tool_def.needs_confirmation:
            prompt = get_confirmation_prompt("delete", path=path)
            if input(prompt).lower() not in ("y", "yes"):
                return "User declined deletion", False
        
        # Delete the file
        info = tool_def.handler(path)
        
        # Remove from file memory if available
        if self.file_memory and str(path) in self.file_memory.files:
            del self.file_memory.files[str(path)]
            if str(path) in self.file_memory.access_order:
                self.file_memory.access_order.remove(str(path))
        
        output = tool_def.formatter(info) if tool_def.formatter else str(info)
        return output, True
    
    def _execute_modify_file(self, tool_def: ToolDefinition, args: Dict) -> Tuple[str, bool]:
        """Execute modify_file with diff display and confirmation."""
        path = tools.validate_path(self.root, args["path"])
        anchor = args.get("anchor", "")
        action = args["action"]
        content = args.get("content", "")
        occurrence = int(args.get("occurrence", 1))
        
        # Get the changes
        old, new, info = tool_def.handler(path, anchor, action, content, occurrence)
        
        # Show diff
        diff = self._generate_diff(old, new, path)
        if diff.strip():
            print(f"\n--- Changes to: {path} ---")
            self._print_truncated_diff(diff)
        
        if self.dry_run:
            print(f"  → [DRY RUN] Would modify {path}")
            return f"[DRY RUN] Would modify {path}: {info}", True
        
        # Ask for confirmation if needed
        if not self.auto_yes and tool_def.needs_confirmation and diff.strip():
            prompt = get_confirmation_prompt("modify", path=path)
            if input(prompt).lower() not in ("y", "yes"):
                # Revert the change
                path.write_text(old, encoding="utf-8")
                return "User declined changes", False
        
        # Update file memory if available
        if self.file_memory:
            self.file_memory.add_file(str(path), new)
        
        output = tool_def.formatter(info) if tool_def.formatter else str(info)
        return output, True
    
    def _execute_generic(self, tool_def: ToolDefinition, args: Dict) -> Tuple[str, bool]:
        """Generic execution for future tools."""
        # Basic execution for tools without special handling
        result = tool_def.handler(self.root, **args)
        output = tool_def.formatter(result) if tool_def.formatter else str(result)
        return output, True
    
    def _generate_diff(self, old: str, new: str, path: Path) -> str:
        """Generate a unified diff for file changes."""
        old_lines = old.splitlines(keepends=True)
        new_lines = new.splitlines(keepends=True)
        diff = difflib.unified_diff(
            old_lines, new_lines,
            fromfile=f"{path} (before)",
            tofile=f"{path} (after)",
            lineterm=""
        )
        return "".join(diff)
    
    def _print_truncated_diff(self, diff: str, max_lines: int = 50):
        """Print a diff with color coding, truncating if too long."""
        # ANSI color codes
        RED = '\033[91m'
        GREEN = '\033[92m'
        RESET = '\033[0m'
        
        diff_lines = diff.split('\n')
        
        def colorize_line(line):
            """Add color to diff lines."""
            if line.startswith('-') and not line.startswith('---'):
                return f"{RED}{line}{RESET}"
            elif line.startswith('+') and not line.startswith('+++'):
                return f"{GREEN}{line}{RESET}"
            else:
                return line
        
        # Apply colors to all lines
        colored_lines = [colorize_line(line) for line in diff_lines]
        
        # Ensure proper spacing between removals and additions
        output_lines = []
        prev_was_removal = False
        
        for i, line in enumerate(colored_lines):
            # Check if we're transitioning from removals to additions
            if prev_was_removal and line.startswith(f"{GREEN}+"):
                # Add a blank line if there isn't one already
                if i > 0 and output_lines[-1].strip():
                    output_lines.append("")
            
            output_lines.append(line)
            prev_was_removal = line.startswith(f"{RED}-")
        
        # Print with truncation if needed
        if len(output_lines) > max_lines:
            print('\n'.join(output_lines[:max_lines//2]))
            print(f"\n... [{len(output_lines) - max_lines} lines omitted] ...\n")
            print('\n'.join(output_lines[-max_lines//2:]))
        else:
            print('\n'.join(output_lines))
    
    def _execute_git_commit(self, tool_def: ToolDefinition, args: Dict) -> Tuple[str, bool]:
        """Execute git_commit with confirmation."""
        message = args["message"]
        add_all = args.get("add_all", False)
        
        if self.dry_run:
            print(f"  → [DRY RUN] Would commit with message: {message}")
            return f"[DRY RUN] Would create commit", True
        
        # Ask for confirmation if needed
        if not self.auto_yes and tool_def.needs_confirmation:
            prompt = get_confirmation_prompt("git_commit", message=message, add_all=add_all)
            if input(prompt).lower() not in ("y", "yes"):
                return "User declined commit", False
        
        # Execute commit
        result = tool_def.handler(self.root, message, add_all)
        output = tool_def.formatter(result) if tool_def.formatter else str(result)
        return output, "error" not in result
    
    def _execute_git_branch(self, tool_def: ToolDefinition, args: Dict) -> Tuple[str, bool]:
        """Execute git_branch with conditional confirmation."""
        action = args.get("action", "list")
        name = args.get("name")
        force = args.get("force", False)
        
        # Only confirm for destructive actions
        needs_confirm = action in ["delete", "switch"]
        
        if self.dry_run and needs_confirm:
            print(f"  → [DRY RUN] Would {action} branch: {name}")
            return f"[DRY RUN] Would {action} branch", True
        
        # Ask for confirmation if needed
        if not self.auto_yes and needs_confirm and tool_def.needs_confirmation:
            prompt = get_confirmation_prompt("git_branch", action=action, name=name)
            if input(prompt).lower() not in ("y", "yes"):
                return f"User declined branch {action}", False
        
        # Execute branch operation
        result = tool_def.handler(self.root, action, name, force)
        output = tool_def.formatter(result) if tool_def.formatter else str(result)
        return output, "error" not in result
    
    def _execute_git_revert(self, tool_def: ToolDefinition, args: Dict) -> Tuple[str, bool]:
        """Execute git_revert with confirmation."""
        target = args["target"]
        revert_type = args.get("type", "file")
        
        if self.dry_run:
            print(f"  → [DRY RUN] Would revert {revert_type}: {target}")
            return f"[DRY RUN] Would revert {revert_type}", True
        
        # Ask for confirmation
        if not self.auto_yes and tool_def.needs_confirmation:
            prompt = get_confirmation_prompt("git_revert", target=target, type=revert_type)
            if input(prompt).lower() not in ("y", "yes"):
                return "User declined revert", False
        
        # Execute revert
        result = tool_def.handler(self.root, target, revert_type)
        output = tool_def.formatter(result) if tool_def.formatter else str(result)
        return output, "error" not in result
    
    def _init_history(self):
        """Initialize the .ronin_history file if it doesn't exist."""
        self.history_file = self.root / ".ronin_history"
        if not self.history_file.exists():
            try:
                self.history_file.write_text(json.dumps({
                    "created": datetime.now().isoformat(),
                    "operations": []
                }, indent=2))
            except Exception as e:
                logger.warning(f"Failed to create .ronin_history: {e}")
    
    def _log_operation(self, tool_name: str, args: Dict, success: bool, result: str):
        """Log an operation to .ronin_history."""
        try:
            # Read existing history
            history = json.loads(self.history_file.read_text())
            
            # Add new operation
            operation = {
                "timestamp": datetime.now().isoformat(),
                "tool": tool_name,
                "args": args,
                "success": success,
                "result_summary": result[:200] if len(result) > 200 else result
            }
            
            # Append operation to history
            history["operations"].append(operation)
            
            # Write back
            self.history_file.write_text(json.dumps(history, indent=2))
        except Exception as e:
            logger.warning(f"Failed to log operation to history: {e}")