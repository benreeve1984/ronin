# Tool Registry System for Ronin
# ================================
# This is the SINGLE SOURCE OF TRUTH for all tools in Ronin.
# Each tool is defined once here with its specification, handler, and formatter.
# 
# Adding a new tool? Just add it to TOOLS below!

from pathlib import Path
from typing import Dict, Any, Callable, Optional
from dataclasses import dataclass
import tools  # Our existing tools module

@dataclass
class ToolDefinition:
    """
    Defines everything about a tool in one place.
    
    Attributes:
        name: Tool identifier (e.g., "list_files")
        description: Human-readable description for the AI
        parameters: Parameter definitions for the tool
        handler: Function that executes the tool
        formatter: Function that formats the output (optional)
        needs_confirmation: Whether to ask user before executing
        category: Tool category for organization (read/write/search)
    """
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Callable
    formatter: Optional[Callable] = None
    needs_confirmation: bool = False
    category: str = "general"

def format_file_list(result: Dict) -> str:
    """Format file listing results in a human-readable way."""
    if "error" in result:
        return f"Error: {result['error']}"
    elif result.get("files"):
        output = f"Found {result['count']} files matching '{result.get('pattern', '*')}':\n"
        for f in result['files'][:20]:
            output += f"  - {f['path']} ({f['lines']} lines, {f['size_display']})\n"
        if result['count'] > 20:
            output += f"  ... and {result['count'] - 20} more"
        return output
    else:
        return f"No files found matching '{result.get('pattern', '*')}'"

def format_read_file(path: Path, content: str, start_line: int, end_line: Optional[int]) -> str:
    """Format file reading results."""
    if start_line == 1 and end_line is None:
        lines = content.count('\n') + 1
        return f"File: {path} ({lines} lines, {len(content)} bytes)\n\n{content}"
    else:
        return f"File: {path}\n{content}"

def format_search_results(result: Dict) -> str:
    """Format search results with context."""
    if result["total_matches"] == 0:
        return f"No matches found for '{result['query']}'"
    
    output = f"Found '{result['query']}' {result['total_matches']} times in {result['files_with_matches']} files:\n\n"
    
    for file_result in result["matches"]:
        output += f"{file_result['file']}:\n"
        for match in file_result["matches"]:
            # Show context lines before
            if "before" in match:
                for i, line in enumerate(match["before"], 
                                       match["line_number"] - len(match["before"])):
                    output += f"  {i:4}: {line}\n"
            
            # Highlight the matching line
            output += f"→ {match['line_number']:4}: {match['line']}\n"
            
            # Show context lines after
            if "after" in match:
                for i, line in enumerate(match["after"], match["line_number"] + 1):
                    output += f"  {i:4}: {line}\n"
            
            if match.get("truncated"):
                output += "  ... (more matches truncated)\n"
            output += "\n"
    
    return output

def format_file_creation(info: Dict) -> str:
    """Format file creation results."""
    return f"Created {info['created']} ({info['lines']} lines, {info['size']} bytes)"

def format_file_deletion(info: Dict) -> str:
    """Format file deletion results."""
    return f"Deleted {info['deleted']} ({info['size']} bytes)"

def format_file_modification(info: Dict) -> str:
    """Format file modification results."""
    return (
        f"Modified {info['file']}:\n"
        f"  - Action: {info['action']} {info['anchor']}\n"
        f"  - Changes: {info.get('modified_occurrences', info.get('position', 'unknown'))}\n"
        f"  - Size: {info['old_size']} → {info['new_size']} bytes ({info['size_change']:+d})\n"
        f"  - Lines: {info['old_lines']} → {info['new_lines']} ({info['line_change']:+d})"
    )

# ============================================================================
# TOOL DEFINITIONS - Add new tools here!
# ============================================================================

TOOLS = {
    "list_files": ToolDefinition(
        name="list_files",
        description="List .md/.txt files with sizes and line counts. Shows how big files are so you can decide how much to read.",
        category="read",
        parameters={
            "pattern": {
                "type": "string",
                "default": "*",
                "description": "Glob pattern (e.g. '*.md', 'docs/*', '**/*.txt')"
            }
        },
        handler=tools.list_files,
        formatter=format_file_list,
        needs_confirmation=False
    ),
    
    "read_file": ToolDefinition(
        name="read_file",
        description="Read a text file's contents or specific lines. Can read entire file or just lines X to Y. Always check file size with list_files first for large files.",
        category="read",
        parameters={
            "path": {
                "type": "string",
                "description": "Relative path to file (e.g. 'README.md', 'docs/guide.txt')",
                "required": True
            },
            "start_line": {
                "type": "number",
                "default": 1,
                "description": "Line to start from (1-indexed). Default: 1 (beginning)"
            },
            "end_line": {
                "type": "number",
                "description": "Line to end at (inclusive). Default: end of file"
            }
        },
        handler=tools.read_file,
        formatter=format_read_file,
        needs_confirmation=False
    ),
    
    "search_files": ToolDefinition(
        name="search_files",
        description="Search for text across all files, like Ctrl+F but for multiple files. Case-insensitive by default for human-friendly searching. Shows context around matches to understand usage.",
        category="search",
        parameters={
            "text": {
                "type": "string",
                "description": "Text to search for",
                "required": True
            },
            "pattern": {
                "type": "string",
                "default": "*",
                "description": "Which files to search (e.g. '*.md', 'docs/*'). Default: all files"
            },
            "case_sensitive": {
                "type": "boolean",
                "default": False,
                "description": "Make search case-sensitive. Default: False"
            },
            "context_lines": {
                "type": "number",
                "default": 2,
                "description": "Lines to show before/after each match (0=just the match). Default: 2"
            }
        },
        handler=tools.search_files,
        formatter=format_search_results,
        needs_confirmation=False
    ),
    
    "create_file": ToolDefinition(
        name="create_file",
        description="Create a new .md/.txt file. Fails if file already exists. Creates parent directories automatically.",
        category="write",
        parameters={
            "path": {
                "type": "string",
                "description": "Path for new file (e.g. 'notes.md', 'docs/new.txt')",
                "required": True
            },
            "content": {
                "type": "string",
                "description": "Initial content for the file",
                "required": True
            }
        },
        handler=tools.create_file,
        formatter=format_file_creation,
        needs_confirmation=True  # Ask before creating
    ),
    
    "delete_file": ToolDefinition(
        name="delete_file",
        description="Delete a file permanently. User will be asked to confirm.",
        category="write",
        parameters={
            "path": {
                "type": "string",
                "description": "Path to file to delete",
                "required": True
            }
        },
        handler=tools.delete_file,
        formatter=format_file_deletion,
        needs_confirmation=True  # Always ask before deleting!
    ),
    
    "modify_file": ToolDefinition(
        name="modify_file",
        description=(
            "Modify file using anchor-based operations. This is the main editing tool. "
            "Find an anchor text (or use empty for file boundaries) and perform an action. "
            "Examples: append (empty anchor, after), prepend (empty anchor, before), "
            "replace all (empty anchor, replace), insert after text (anchor='text', after), "
            "delete text (anchor='text', replace with empty), replace all occurrences (occurrence=0)."
        ),
        category="write",
        parameters={
            "path": {
                "type": "string",
                "description": "Path to file to modify",
                "required": True
            },
            "anchor": {
                "type": "string",
                "default": "",
                "description": "Text to find. Empty means file boundaries (start/end)"
            },
            "action": {
                "type": "string",
                "enum": ["before", "after", "replace"],
                "description": "What to do at anchor: before (insert before), after (insert after), replace",
                "required": True
            },
            "content": {
                "type": "string",
                "default": "",
                "description": "New content to insert/replace. Empty for deletion"
            },
            "occurrence": {
                "type": "number",
                "default": 1,
                "description": "Which match: 1=first, -1=last, 0=all occurrences"
            }
        },
        handler=tools.modify_file,
        formatter=format_file_modification,
        needs_confirmation=True  # Ask before modifying
    )
}

def get_tool_specs(root: Path) -> list:
    """
    Generate tool specifications for Claude AI.
    
    This converts our tool definitions into the format Claude expects.
    Called by agent.py to tell Claude what tools are available.
    """
    specs = []
    base = f"Root: {root}"
    
    for tool_def in TOOLS.values():
        # Build the input schema from our parameter definitions
        properties = {}
        required = []
        
        for param_name, param_info in tool_def.parameters.items():
            # Extract the parameter info
            param_spec = {
                "type": param_info["type"],
                "description": param_info.get("description", "")
            }
            
            # Add default if present
            if "default" in param_info:
                param_spec["default"] = param_info["default"]
            
            # Add enum if present
            if "enum" in param_info:
                param_spec["enum"] = param_info["enum"]
            
            properties[param_name] = param_spec
            
            # Track required parameters
            if param_info.get("required", False):
                required.append(param_name)
        
        # Build the tool specification
        spec = {
            "name": tool_def.name,
            "description": f"{tool_def.description} {base}",
            "input_schema": {
                "type": "object",
                "properties": properties
            }
        }
        
        # Only add required field if there are required parameters
        if required:
            spec["input_schema"]["required"] = required
        
        specs.append(spec)
    
    return specs

def get_tool(name: str) -> Optional[ToolDefinition]:
    """Get a tool definition by name."""
    return TOOLS.get(name)

def list_tools_by_category() -> Dict[str, list]:
    """Group tools by category for documentation."""
    by_category = {}
    for tool in TOOLS.values():
        if tool.category not in by_category:
            by_category[tool.category] = []
        by_category[tool.category].append(tool)
    return by_category