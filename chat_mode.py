# Interactive chat mode for Ronin
import os
import sys
import json
from pathlib import Path
from typing import List, Dict, Tuple
import anthropic
from datetime import datetime

from agent import run_once, SYSTEM_PROMPT, tool_specs, show_diff
from tools import (
    ALLOWED_EXTS, validate_path, list_files,
    read_file, create_file, delete_file, modify_file, search_files
)

# Token limits (approximate - we'll use character count as proxy)
MAX_CONTEXT_TOKENS = 140_000
CHARS_PER_TOKEN = 4  # Rough estimate

class FileMemory:
    """Track files read during the session."""
    
    def __init__(self):
        self.files: Dict[str, str] = {}  # path -> content
        self.access_order: List[str] = []  # LRU tracking
        
    def add_file(self, path: str, content: str):
        """Add or update a file in memory."""
        if path in self.files:
            self.access_order.remove(path)
        self.files[path] = content
        self.access_order.append(path)
        
    def get_context(self, max_chars: int) -> str:
        """Get file context within size limit."""
        if not self.files:
            return ""
            
        context = "\n=== FILES IN CONTEXT ===\n"
        total_chars = len(context)
        
        # Add files in reverse access order (most recent first)
        for path in reversed(self.access_order):
            content = self.files[path]
            file_section = f"\n--- {path} ---\n{content}\n"
            
            if total_chars + len(file_section) > max_chars:
                break
                
            context += file_section
            total_chars += len(file_section)
            
        return context if len(self.files) > 0 else ""

class ChatSession:
    """Interactive chat session with Ronin."""
    
    def __init__(self, model: str, root: Path, auto_yes: bool, max_steps: int):
        self.client = anthropic.Anthropic()
        self.model = model
        self.root = root
        self.auto_yes = auto_yes
        self.max_steps = max_steps
        self.messages = []
        self.file_memory = FileMemory()
        self.total_operations = 0
        
    def get_system_prompt(self) -> str:
        """Build system prompt with file context."""
        base_prompt = SYSTEM_PROMPT + """

You are in INTERACTIVE MODE. The user can have multiple exchanges with you.
Remember what was discussed and what files were created/modified earlier in the conversation.
"""
        
        # Add file context (reserve space for conversation)
        max_file_context = MAX_CONTEXT_TOKENS * CHARS_PER_TOKEN // 3  # Use 1/3 for files
        file_context = self.file_memory.get_context(max_file_context)
        
        if file_context:
            return base_prompt + "\n" + file_context
        return base_prompt
        
    def process_input(self, user_input: str) -> bool:
        """Process one user input. Returns False to exit."""
        
        # Check for exit commands
        if user_input.lower() in ('exit', 'quit', 'bye', '/exit', '/quit'):
            return False
            
        # Check for special commands
        if user_input.startswith('/'):
            return self.handle_command(user_input)
            
        # Add user message
        self.messages.append({"role": "user", "content": user_input})
        
        # Process with Claude
        operations_this_turn = 0
        
        while operations_this_turn < self.max_steps:
            try:
                # Get Claude's response
                resp = self.client.messages.create(
                    model=self.model,
                    system=self.get_system_prompt(),
                    tools=tool_specs(self.root),
                    messages=self.messages,
                    max_tokens=2000,
                )
                
                # Print any explanatory text
                for block in resp.content:
                    if getattr(block, "type", None) == "text":
                        text = block.text.strip()
                        if text:
                            print(f"\n🤖 {text}")
                
                # Extract tool requests
                tool_uses = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]
                
                # Add assistant message to history
                self.messages.append({"role": "assistant", "content": resp.content})
                
                if not tool_uses:
                    # No more tools requested - turn complete
                    break
                    
                # Process tool requests
                results = self.process_tools(tool_uses)
                operations_this_turn += len(tool_uses)
                self.total_operations += len(tool_uses)
                
                # Add results to conversation
                self.messages.append({"role": "user", "content": results})
                
            except Exception as e:
                print(f"\n❌ Error: {e}")
                break
                
        if operations_this_turn >= self.max_steps:
            print(f"\n⚠️  Reached maximum operations for this turn ({self.max_steps})")
            
        # Trim message history if getting too long
        self.trim_history()
        
        return True
        
    def process_tools(self, tool_uses) -> List[Dict]:
        """Process tool requests and track file access."""
        results = []
        
        for tu in tool_uses:
            name = tu.name
            args = dict(tu.input or {})
            
            print(f"\n🔧 Executing: {name}", end="")
            if name == "search_files":
                text = args.get("text", "?")
                print(f" (searching for: '{text[:30]}...')" if len(text) > 30 else f" (searching for: '{text}')")
            elif name == "modify_file":
                action = args.get("action", "?")
                anchor = args.get("anchor", "")
                if anchor:
                    print(f" ({action} anchor: '{anchor[:30]}...')" if len(anchor) > 30 else f" ({action} anchor: '{anchor}')")
                else:
                    print(f" ({action} file boundaries)")
            elif name in ("read_file", "create_file", "delete_file"):
                print(f" ({args.get('path', '?')})")
            else:
                print()
            
            try:
                if name == "list_files":
                    pattern = args.get("pattern", "*")
                    result = list_files(self.root, pattern)
                    
                    # Format result
                    if "error" in result:
                        output = f"Error: {result['error']}"
                    elif result.get("files"):
                        output = f"Found {result['count']} files matching '{pattern}':\n"
                        for f in result['files'][:20]:
                            output += f"  - {f['path']} ({f['lines']} lines, {f['size_display']})\n"
                        if result['count'] > 20:
                            output += f"  ... and {result['count'] - 20} more"
                    else:
                        output = f"No files found matching '{pattern}'"
                    
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": output
                    })
                    
                elif name == "read_file":
                    p = validate_path(self.root, args["path"])
                    start_line = int(args.get("start_line", 1))
                    end_line = int(args.get("end_line")) if args.get("end_line") else None
                    
                    content = read_file(p, start_line, end_line)
                    
                    # Track file in memory (only for full reads)
                    if start_line == 1 and end_line is None:
                        self.file_memory.add_file(str(p), content)
                    
                    # Add helpful context for full reads
                    if start_line == 1 and end_line is None:
                        lines = content.count('\n') + 1
                        output = f"File: {p} ({lines} lines, {len(content)} bytes)\n\n{content}"
                    else:
                        output = f"File: {p}\n{content}"
                    
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": output
                    })
                    
                elif name == "create_file":
                    p = validate_path(self.root, args["path"])
                    content = args["content"]
                    
                    if not self.auto_yes:
                        print(f"\n📝 Create new file: {p}")
                        print(f"   Content preview: {content[:100]}..." if len(content) > 100 else f"   Content: {content}")
                        if input("   Create? [y/N]: ").lower() not in ("y", "yes"):
                            results.append({
                                "type": "tool_result",
                                "tool_use_id": tu.id,
                                "content": "User declined file creation",
                                "is_error": True
                            })
                            continue
                    
                    info = create_file(p, content)
                    
                    # Track new file
                    self.file_memory.add_file(str(p), content)
                    
                    print(f"  ✓ Created: {info['created']} ({info['lines']} lines)")
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": f"Created {info['created']} ({info['lines']} lines, {info['size']} bytes)"
                    })
                    
                elif name == "delete_file":
                    p = validate_path(self.root, args["path"])
                    
                    if not self.auto_yes:
                        if input(f"\n🗑️  DELETE {p}? [y/N]: ").lower() not in ("y", "yes"):
                            results.append({
                                "type": "tool_result",
                                "tool_use_id": tu.id,
                                "content": "User declined deletion",
                                "is_error": True
                            })
                            continue
                    
                    info = delete_file(p)
                    
                    # Remove from memory
                    if str(p) in self.file_memory.files:
                        del self.file_memory.files[str(p)]
                        self.file_memory.access_order.remove(str(p))
                    
                    print(f"  ✓ Deleted: {info['deleted']}")
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": f"Deleted {info['deleted']} ({info['size']} bytes)"
                    })
                    
                elif name == "search_files":
                    text = args["text"]
                    pattern = args.get("pattern", "*")
                    case_sensitive = args.get("case_sensitive", False)
                    context_lines = int(args.get("context_lines", 2))
                    
                    result = search_files(self.root, text, pattern, case_sensitive, context_lines)
                    
                    # Format human-readable output
                    if result["total_matches"] == 0:
                        output = f"No matches found for '{text}'"
                    else:
                        output = f"Found '{text}' {result['total_matches']} times in {result['files_with_matches']} files:\n\n"
                        
                        for file_result in result["matches"]:
                            output += f"{file_result['file']}:\n"
                            for match in file_result["matches"]:
                                # Show context
                                if context_lines > 0 and "before" in match:
                                    for i, line in enumerate(match["before"], match["line_number"] - len(match["before"])):
                                        output += f"  {i:4}: {line}\n"
                                
                                # Highlight the matching line
                                output += f"→ {match['line_number']:4}: {match['line']}\n"
                                
                                if context_lines > 0 and "after" in match:
                                    for i, line in enumerate(match["after"], match["line_number"] + 1):
                                        output += f"  {i:4}: {line}\n"
                                
                                if match.get("truncated"):
                                    output += "  ... (more matches truncated)\n"
                                output += "\n"
                    
                    print(f"  ✓ Search complete: {result['total_matches']} matches in {result['files_with_matches']} files")
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": output
                    })
                    
                elif name == "modify_file":
                    p = validate_path(self.root, args["path"])
                    anchor = args.get("anchor", "")
                    action = args["action"]
                    content = args.get("content", "")
                    occurrence = int(args.get("occurrence", 1))
                    
                    # Get the changes
                    old, new, info = modify_file(p, anchor, action, content, occurrence)
                    
                    # Update file in memory
                    self.file_memory.add_file(str(p), new)
                    
                    # Show diff
                    diff = show_diff(old, new, p)
                    if diff.strip():
                        print(f"\n--- Changes to: {p} ---")
                        diff_lines = diff.split('\n')
                        if len(diff_lines) > 50:
                            print('\n'.join(diff_lines[:25]))
                            print(f"\n... [{len(diff_lines) - 50} lines omitted] ...\n")
                            print('\n'.join(diff_lines[-25:]))
                        else:
                            print(diff)
                    
                    if not self.auto_yes and diff.strip():
                        if input(f"Apply changes? [y/N]: ").lower() not in ("y", "yes"):
                            # Revert the change
                            p.write_text(old, encoding="utf-8")
                            results.append({
                                "type": "tool_result",
                                "tool_use_id": tu.id,
                                "content": "User declined changes",
                                "is_error": True
                            })
                            continue
                    
                    # Format detailed feedback
                    feedback = (
                        f"Modified {p}:\n"
                        f"  - Action: {info['action']} {info['anchor']}\n"
                        f"  - Changes: {info.get('modified_occurrences', info.get('position', 'unknown'))}\n"
                        f"  - Size: {info['old_size']} → {info['new_size']} bytes ({info['size_change']:+d})\n"
                        f"  - Lines: {info['old_lines']} → {info['new_lines']} ({info['line_change']:+d})"
                    )
                    
                    print(f"  ✓ Modified: {p} ({info['size_change']:+d} bytes, {info['line_change']:+d} lines)")
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": feedback
                    })
                    
                else:
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": f"Unknown tool: {name}",
                        "is_error": True
                    })
                    
            except Exception as e:
                print(f"  ❌ Error: {e}")
                results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": f"Error: {e}",
                    "is_error": True
                })
                
        return results
        
    def handle_command(self, command: str) -> bool:
        """Handle special slash commands."""
        cmd = command.lower().strip()
        
        if cmd in ('/help', '/h', '/?'):
            print("""
📚 Available commands:
  /help, /h     - Show this help
  /files, /f    - List files in memory
  /clear        - Clear conversation history
  /root         - Show current root directory
  /stats        - Show session statistics
  /exit, /quit  - Exit Ronin
  
Just type normally to interact with Ronin!
""")
        elif cmd in ('/files', '/f'):
            if self.file_memory.files:
                print("\n📁 Files in memory:")
                for path in self.file_memory.access_order:
                    size = len(self.file_memory.files[path])
                    print(f"  - {path} ({size} bytes)")
            else:
                print("\n📁 No files in memory yet")
                
        elif cmd == '/clear':
            self.messages = []
            print("\n🧹 Conversation history cleared")
            
        elif cmd == '/root':
            print(f"\n📂 Root directory: {self.root}")
            
        elif cmd == '/stats':
            print(f"""
📊 Session Statistics:
  Messages: {len(self.messages)}
  Operations: {self.total_operations}
  Files in memory: {len(self.file_memory.files)}
  Root: {self.root}
""")
        else:
            print(f"\n❓ Unknown command: {command}")
            print("Type /help for available commands")
            
        return True
        
    def trim_history(self):
        """Trim conversation history if it gets too long."""
        # Estimate total size
        total_chars = sum(len(str(msg)) for msg in self.messages)
        
        # If over 2/3 of limit, trim older messages
        if total_chars > MAX_CONTEXT_TOKENS * CHARS_PER_TOKEN * 2 / 3:
            # Keep system messages and recent messages
            keep_recent = 10
            if len(self.messages) > keep_recent:
                self.messages = self.messages[-keep_recent:]
                print("\n📋 (Trimmed older conversation history to stay within limits)")

def interactive_mode(model: str, root: Path, auto_yes: bool, max_steps: int):
    """Run Ronin in interactive chat mode."""
    
    print("""
╭─────────────────────────────────────────╮
│  🤖 Ronin - Interactive Mode             │
│                                         │
│  Type /help for commands                │
│  Type exit or /exit to quit             │
│                                         │
│  Ready to help with your text files!   │
╰─────────────────────────────────────────╯
""")
    
    session = ChatSession(model, root, auto_yes, max_steps)
    
    while True:
        try:
            # Get user input
            user_input = input("\n💬 You: ").strip()
            
            if not user_input:
                continue
                
            # Process input
            if not session.process_input(user_input):
                print("\n👋 Goodbye!")
                break
                
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except EOFError:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Unexpected error: {e}")
            print("You can continue or type 'exit' to quit.")