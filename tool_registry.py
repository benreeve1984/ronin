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

def format_git_status(result: Dict) -> str:
    """Format git status output in an AI-friendly way."""
    if "error" in result:
        return f"Git Error: {result['error']}\nImplication: Not in a git repository or git is not available."
    
    output = []
    
    # Current branch context
    if result.get("branch"):
        output.append(f"Current branch: {result['branch']}")
        if result['branch'] == "main" or result['branch'] == "master":
            output.append("  → You are on the main branch (primary codebase)")
        else:
            output.append(f"  → You are on a feature/experimental branch")
    
    if result.get("ahead_behind"):
        output.append(f"Branch sync status: {result['ahead_behind']}")
        if "ahead" in result['ahead_behind']:
            output.append("  → Local commits not yet pushed to remote")
        if "behind" in result['ahead_behind']:
            output.append("  → Remote has commits you don't have locally")
    
    # File status with clear explanations
    has_changes = False
    
    if result.get("staged"):
        has_changes = True
        output.append("\n📦 STAGED (ready to commit):")
        for file in result["staged"]:
            output.append(f"  ✓ {file}")
        output.append(f"  → These {len(result['staged'])} file(s) will be included in the next commit")
    
    if result.get("modified"):
        has_changes = True
        output.append("\n✏️ MODIFIED (not staged):")
        for file in result["modified"]:
            output.append(f"  M {file}")
        output.append(f"  → These {len(result['modified'])} file(s) have changes but won't be committed unless staged")
        output.append("  → Use git_commit with add_all=True to include them")
    
    if result.get("untracked"):
        has_changes = True
        output.append("\n🆕 UNTRACKED (not in git):")
        for file in result["untracked"]:
            output.append(f"  ? {file}")
        output.append(f"  → These {len(result['untracked'])} file(s) are new and not tracked by git")
        output.append("  → They will be ignored unless explicitly added")
    
    if not has_changes:
        output.append("\n✅ Working tree is clean")
        output.append("  → No uncommitted changes")
        output.append("  → Safe to switch branches or pull updates")
    else:
        output.append("\n💡 Summary: You have uncommitted changes")
        output.append("  → Consider committing to save current state")
        output.append("  → Users may want to revert these changes later")
    
    return "\n".join(output)

def format_git_diff(result: Dict) -> str:
    """Format git diff output in an AI-friendly way."""
    if "error" in result:
        return f"Git Error: {result['error']}\nImplication: Could not generate diff. Check if files exist and repository is valid."
    
    if not result.get("diff"):
        return "No changes detected\n  → Files are identical to comparison point\n  → Nothing to commit or review"
    
    diff_text = result["diff"]
    
    # Parse diff to provide summary
    lines = diff_text.split('\n')
    files_changed = []
    additions = 0
    deletions = 0
    
    for line in lines:
        if line.startswith('+++') or line.startswith('---'):
            if '/' in line:
                filename = line.split('/')[-1]
                if filename not in files_changed and not filename.startswith('+++') and not filename.startswith('---'):
                    files_changed.append(filename)
        elif line.startswith('+') and not line.startswith('+++'):
            additions += 1
        elif line.startswith('-') and not line.startswith('---'):
            deletions += 1
    
    output = []
    output.append("📊 DIFF ANALYSIS:")
    
    if files_changed:
        output.append(f"Files with changes: {', '.join(set(files_changed))}")
    
    if additions or deletions:
        output.append(f"Lines added: +{additions}, Lines removed: -{deletions}")
        net = additions - deletions
        if net > 0:
            output.append(f"  → Net change: +{net} lines (code expanded)")
        elif net < 0:
            output.append(f"  → Net change: {net} lines (code reduced)")
        else:
            output.append(f"  → Net change: 0 lines (code refactored)")
    
    output.append("\n📝 DETAILED CHANGES:")
    output.append(diff_text)
    
    output.append("\n💡 INTERPRETATION:")
    output.append("  → Review changes above before committing")
    output.append("  → '+' lines are additions, '-' lines are deletions")
    output.append("  → Use git_commit to save these changes permanently")
    
    return "\n".join(output)

def format_git_commit(result: Dict) -> str:
    """Format git commit result in an AI-friendly way."""
    if "error" in result:
        error_msg = result['error']
        if "nothing to commit" in error_msg.lower():
            return "❌ No changes to commit\n  → Working directory is clean\n  → Make some modifications first"
        elif "nothing staged" in error_msg.lower():
            return "❌ No staged changes\n  → Files are modified but not staged\n  → Use git_commit with add_all=True to include all changes"
        else:
            return f"Git Error: {error_msg}\n  → Check repository status with git_status"
    
    output = ["✅ COMMIT SUCCESSFUL!"]
    
    if result.get("commit_hash"):
        output.append(f"\n📌 Commit ID: {result['commit_hash'][:8]}")
        output.append(f"  → This is your restoration point")
        output.append(f"  → Use this ID to revert if needed: git_revert(target='{result['commit_hash'][:8]}', type='commit')")
    
    if result.get("message"):
        output.append(f"\n💬 Message: {result['message']}")
    
    stats = []
    if result.get("files_changed"):
        stats.append(f"{result['files_changed']} file(s)")
    if result.get("insertions"):
        stats.append(f"+{result['insertions']} additions")
    if result.get("deletions"):
        stats.append(f"-{result['deletions']} deletions")
    
    if stats:
        output.append(f"\n📈 Changes saved: {', '.join(stats)}")
    
    output.append("\n💡 WHAT THIS MEANS:")
    output.append("  → Your changes are now saved in git history")
    output.append("  → Users can revert to this point if needed")
    output.append("  → Continue working - you have a safety checkpoint")
    
    return "\n".join(output)

def format_git_log(result: Dict) -> str:
    """Format git log output in an AI-friendly way."""
    if "error" in result:
        return f"Git Error: {result['error']}\n  → Repository may not have any commits yet"
    
    if not result.get("commits"):
        return "📭 No commits found\n  → This might be a new repository\n  → Start by making your first commit"
    
    output = ["📜 COMMIT HISTORY (most recent first):"]
    output.append(f"  Showing {len(result['commits'])} most recent commits\n")
    
    for i, commit in enumerate(result["commits"]):
        # Mark the most recent commit specially
        if i == 0:
            output.append(f"🔵 LATEST: {commit['hash'][:8]} - {commit['message']}")
            output.append("  ↑ Current state of the repository")
        else:
            output.append(f"⚪ {commit['hash'][:8]} - {commit['message']}")
        
        output.append(f"   Author: {commit['author']}")
        output.append(f"   Date: {commit['date']}")
        
        if commit.get("files"):
            files_str = ', '.join(commit['files'][:3])
            if len(commit['files']) > 3:
                files_str += f" + {len(commit['files']) - 3} more"
            output.append(f"   Files: {files_str}")
        output.append("")
    
    output.append("💡 UNDERSTANDING THE HISTORY:")
    output.append("  → Each commit is a saved checkpoint")
    output.append("  → You can revert to any commit using its ID")
    output.append("  → Most recent work is at the top")
    
    # Analyze commit patterns
    if len(result['commits']) > 1:
        messages = [c['message'].lower() for c in result['commits'][:5]]
        if any('fix' in m for m in messages):
            output.append("  → Recent fixes suggest active debugging")
        if any('add' in m or 'feature' in m for m in messages):
            output.append("  → Recent feature additions detected")
    
    return "\n".join(output)

def format_git_branch(result: Dict) -> str:
    """Format git branch operations in an AI-friendly way."""
    if "error" in result:
        error_msg = result['error']
        if "not found" in error_msg.lower():
            return f"❌ Branch not found: {error_msg}\n  → Check available branches with git_branch(action='list')"
        elif "not fully merged" in error_msg.lower():
            return f"❌ Branch has unmerged changes\n  → Use force=True to delete anyway (data loss risk!)"
        else:
            return f"Git Error: {error_msg}"
    
    if result.get("action") == "list":
        output = ["🌳 AVAILABLE BRANCHES:"]
        
        current_branch = None
        other_branches = []
        
        for branch in result.get("branches", []):
            if branch.get("current"):
                current_branch = branch['name']
            else:
                other_branches.append(branch['name'])
        
        if current_branch:
            output.append(f"\n🔵 Current: {current_branch}")
            output.append("  ↑ You are here")
        
        if other_branches:
            output.append("\n⚪ Other branches:")
            for branch in other_branches:
                output.append(f"  - {branch}")
                if "main" in branch or "master" in branch:
                    output.append("    → Main branch (stable code)")
                elif "dev" in branch:
                    output.append("    → Development branch")
                elif "feature" in branch:
                    output.append("    → Feature branch")
        
        output.append("\n💡 BRANCH MANAGEMENT:")
        output.append("  → Switch branches to work on different features")
        output.append("  → Create branches for experimental changes")
        output.append("  → Main/master branch should stay stable")
        
        return "\n".join(output)
        
    elif result.get("action") == "create":
        return f"✅ Created branch: {result['branch']}\n  → New branch created from current position\n  → Use git_branch(action='switch', name='{result['branch']}') to switch to it"
        
    elif result.get("action") == "switch":
        return f"✅ Switched to branch: {result['branch']}\n  → Now working on {result['branch']}\n  → Changes will be isolated to this branch\n  → Previous branch state is preserved"
        
    elif result.get("action") == "delete":
        return f"✅ Deleted branch: {result['branch']}\n  → Branch removed permanently\n  → Cannot be recovered unless pushed to remote"
    
    return str(result)

def format_git_revert(result: Dict) -> str:
    """Format git revert operations in an AI-friendly way."""
    if "error" in result:
        error_msg = result['error']
        if "does not exist" in error_msg.lower():
            return f"❌ Target not found: {error_msg}\n  → Check file paths or commit IDs\n  → Use git_log to see available commits"
        else:
            return f"Git Error: {error_msg}\n  → Operation failed - no changes made"
    
    if result.get("action") == "file":
        return (f"✅ REVERTED FILE: {result['file']}\n"
                f"  → File restored to last committed state\n"
                f"  → All uncommitted changes in this file are gone\n"
                f"  → Use git_diff to see what was reverted")
                
    elif result.get("action") == "commit":
        output = [f"✅ REVERTED COMMIT: {result['commit'][:8]}"]
        if result.get('new_commit'):
            output.append(f"\n📌 New revert commit: {result['new_commit'][:8]}")
            output.append("  → Created a new commit that undoes the target commit")
            output.append("  → Original commit still exists in history")
            output.append("  → You can revert this revert if needed")
        
        output.append("\n💡 WHAT HAPPENED:")
        output.append("  → Changes from the target commit were undone")
        output.append("  → This is recorded as a new commit")
        output.append("  → History shows both original and revert")
        
        return "\n".join(output)
    
    return str(result)

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
    ),
    
    # ============================================================================
    # GIT TOOLS - Version control integration
    # ============================================================================
    
    "git_status": ToolDefinition(
        name="git_status",
        description="Check git repository status. Shows branch, staged/modified/untracked files.",
        category="git",
        parameters={},
        handler=tools.git_status,
        formatter=format_git_status,
        needs_confirmation=False
    ),
    
    "git_diff": ToolDefinition(
        name="git_diff",
        description="Show changes in files. Can show staged changes, unstaged changes, or changes between commits.",
        category="git",
        parameters={
            "staged": {
                "type": "boolean",
                "default": False,
                "description": "Show staged changes (--cached). Default: show unstaged"
            },
            "file": {
                "type": "string",
                "description": "Specific file to diff. Default: all files"
            },
            "commit": {
                "type": "string",
                "description": "Compare with specific commit. Default: working tree"
            }
        },
        handler=tools.git_diff,
        formatter=format_git_diff,
        needs_confirmation=False
    ),
    
    "git_commit": ToolDefinition(
        name="git_commit",
        description="Create a git commit with staged changes. Automatically stages modified files if needed.",
        category="git",
        parameters={
            "message": {
                "type": "string",
                "description": "Commit message",
                "required": True
            },
            "add_all": {
                "type": "boolean",
                "default": False,
                "description": "Stage all modified files before commit (-a). Default: False"
            }
        },
        handler=tools.git_commit,
        formatter=format_git_commit,
        needs_confirmation=True  # Ask before committing
    ),
    
    "git_log": ToolDefinition(
        name="git_log",
        description="View commit history. Shows recent commits with messages, authors, and files changed.",
        category="git",
        parameters={
            "limit": {
                "type": "number",
                "default": 10,
                "description": "Number of commits to show. Default: 10"
            },
            "oneline": {
                "type": "boolean",
                "default": False,
                "description": "Compact one-line format. Default: False"
            },
            "file": {
                "type": "string",
                "description": "Show commits affecting specific file. Default: all files"
            }
        },
        handler=tools.git_log,
        formatter=format_git_log,
        needs_confirmation=False
    ),
    
    "git_branch": ToolDefinition(
        name="git_branch",
        description="Manage git branches. List, create, switch, or delete branches.",
        category="git",
        parameters={
            "action": {
                "type": "string",
                "enum": ["list", "create", "switch", "delete"],
                "default": "list",
                "description": "Branch operation: list, create, switch, or delete"
            },
            "name": {
                "type": "string",
                "description": "Branch name (required for create/switch/delete)"
            },
            "force": {
                "type": "boolean",
                "default": False,
                "description": "Force delete even if not merged (for delete action)"
            }
        },
        handler=tools.git_branch,
        formatter=format_git_branch,
        needs_confirmation=True  # Confirm for create/switch/delete, but handler can skip for list
    ),
    
    "git_revert": ToolDefinition(
        name="git_revert",
        description="Revert changes. Can revert uncommitted changes in a file or revert an entire commit.",
        category="git",
        parameters={
            "target": {
                "type": "string",
                "description": "File path to revert, or commit hash to revert",
                "required": True
            },
            "type": {
                "type": "string",
                "enum": ["file", "commit"],
                "default": "file",
                "description": "Revert type: 'file' for uncommitted changes, 'commit' for entire commit"
            }
        },
        handler=tools.git_revert,
        formatter=format_git_revert,
        needs_confirmation=True  # Always confirm reverts
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