# Simplified, elegant file operations for Ronin
# Design philosophy: Minimal API, maximum power through composability

from pathlib import Path
from typing import Dict, Tuple, List, Optional
from langsmith_tracer import trace_tool
from exceptions import (
    SandboxViolationError, InvalidFileTypeError, 
    FileNotFoundError as RoninFileNotFoundError,
    FileAlreadyExistsError, AnchorNotFoundError
)

# Security: Only allow text file modifications
ALLOWED_EXTS = {".md", ".txt"}

# Common directories to ignore during search
IGNORE_DIRS = {
    ".venv", "venv", "env",  # Python virtual environments
    "__pycache__", ".pytest_cache",  # Python cache
    "node_modules",  # Node.js
    ".git", ".svn", ".hg",  # Version control
    "dist", "build", "target",  # Build outputs
    ".idea", ".vscode",  # IDE directories
    "*.egg-info",  # Python package info
}

def should_ignore_path(path: Path) -> bool:
    """Check if a path should be ignored based on common patterns.
    
    Args:
        path: Path to check
        
    Returns:
        True if path should be ignored, False otherwise
    """
    for parent in path.parents:
        if parent.name in IGNORE_DIRS or any(parent.match(ignore) for ignore in IGNORE_DIRS):
            return True
    return False

def validate_path(root: Path, rel_path: str) -> Path:
    """Validate path stays within sandbox and has allowed extension.
    
    Args:
        root: Project root (sandbox boundary)
        rel_path: Path relative to root
        
    Returns:
        Resolved absolute Path
        
    Raises:
        ValueError: If path escapes root or has invalid extension
    """
    if not rel_path or rel_path.strip() == "":
        raise ValueError("Path must be non-empty")
    
    # Resolve to absolute path
    p = (root / rel_path).resolve()
    
    # Security: Ensure path stays within root
    try:
        p.relative_to(root)
    except ValueError:
        raise SandboxViolationError(p, root)
    
    # Check file extension
    if p.suffix.lower() not in ALLOWED_EXTS:
        raise InvalidFileTypeError(p, ALLOWED_EXTS)
    
    return p

@trace_tool(name="list_files", metadata={"category": "read"})
def list_files(root: Path, pattern: str = "*") -> Dict:
    """List files matching pattern within root, with size and line info.
    
    Args:
        root: Project root directory
        pattern: Glob pattern (default: all files)
        
    Returns:
        Dict with file details including paths, sizes, and line counts
    """
    try:
        root.relative_to(root)  # Validate it's a valid path
    except:
        return {"error": "Invalid root path"}
    
    if not root.exists() or not root.is_dir():
        return {"exists": False, "files": []}
    
    # Find all matching files
    file_details = []
    files = []
    for p in root.rglob(pattern):
        if p.is_file() and p.suffix.lower() in ALLOWED_EXTS:
            # Skip files in ignored directories
            if not should_ignore_path(p):
                files.append(p)
    
    # Get details for each file (limit to 200)
    for file_path in sorted(files)[:200]:
        try:
            rel_path = str(file_path.relative_to(root))
            size = file_path.stat().st_size
            
            # Count lines efficiently
            with file_path.open('r', encoding='utf-8', errors='ignore') as f:
                line_count = sum(1 for _ in f)
            
            file_details.append({
                "path": rel_path,
                "size": size,
                "lines": line_count,
                "size_display": f"{size:,} bytes" if size < 1024 else f"{size/1024:.1f} KB"
            })
        except Exception:
            # Skip files that can't be read
            continue
    
    return {
        "root": str(root),
        "pattern": pattern,
        "files": file_details,
        "count": len(file_details)
    }

@trace_tool(name="read_file", metadata={"category": "read"})
def read_file(path: Path, start_line: int = 1, end_line: int = None) -> str:
    """Read a text file or specific lines from it.
    
    Args:
        path: Absolute path to file
        start_line: Line to start from (1-indexed, default: 1)
        end_line: Line to end at (inclusive, default: None = end of file)
        
    Returns:
        File contents as string (with line numbers if partial read)
        
    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If line numbers are invalid
    """
    if not path.exists():
        raise RoninFileNotFoundError(path)
    
    # Read entire file (no size limit - trust the model)
    text = path.read_text(encoding="utf-8", errors="replace")
    
    # If reading entire file, return as-is
    if start_line == 1 and end_line is None:
        return text
    
    # Split into lines for partial reading
    lines = text.splitlines()
    total_lines = len(lines)
    
    # Validate line numbers
    if start_line < 1:
        raise ValueError(f"start_line must be >= 1, got {start_line}")
    if end_line and end_line < start_line:
        raise ValueError(f"end_line must be >= start_line")
    
    # Adjust to 0-based indexing
    start_idx = start_line - 1
    end_idx = end_line if end_line else total_lines
    
    # Get the requested lines
    selected_lines = lines[start_idx:end_idx]
    
    # Format with line numbers for partial reads
    result = []
    for i, line in enumerate(selected_lines, start_line):
        result.append(f"{i:6}: {line}")
    
    # Add context about what was read
    header = f"[Lines {start_line}-{min(end_idx, total_lines)} of {total_lines}]\n"
    return header + "\n".join(result)

@trace_tool(name="create_file", metadata={"category": "write"})
def create_file(path: Path, content: str) -> Dict:
    """Create a new file (fails if exists).
    
    Args:
        path: Absolute path for new file
        content: Initial file content
        
    Returns:
        Dict with creation details
        
    Raises:
        FileExistsError: If file already exists
    """
    if path.exists():
        raise FileAlreadyExistsError(path)
    
    # Create parent directories if needed
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write the file
    path.write_text(content, encoding="utf-8")
    
    return {
        "created": str(path),
        "size": len(content),
        "lines": content.count('\n') + 1
    }

@trace_tool(name="delete_file", metadata={"category": "write"})
def delete_file(path: Path) -> Dict:
    """Delete a file.
    
    Args:
        path: Absolute path to file to delete
        
    Returns:
        Dict with deletion details
        
    Raises:
        FileNotFoundError: If file doesn't exist
    """
    if not path.exists():
        raise RoninFileNotFoundError(path)
    
    # Get info before deletion
    size = path.stat().st_size
    
    path.unlink()
    
    return {
        "deleted": str(path),
        "size": size
    }

def _find_anchor_indices(text: str, anchor: str) -> List[int]:
    """Find all indices where anchor appears in text."""
    indices = []
    start = 0
    while True:
        idx = text.find(anchor, start)
        if idx == -1:
            break
        indices.append(idx)
        start = idx + 1
    return indices

def _select_target_indices(indices: List[int], occurrence: int) -> Tuple[List[int], str]:
    """Select which occurrence(s) to modify based on occurrence parameter."""
    if occurrence == 0:  # All occurrences
        return indices, "all"
    elif occurrence == -1:  # Last occurrence
        return [indices[-1]], "last"
    elif 0 < occurrence <= len(indices):  # Specific occurrence
        return [indices[occurrence - 1]], f"#{occurrence}"
    else:
        raise ValueError(f"Invalid occurrence {occurrence} (found {len(indices)} matches)")

def _apply_modification(content: str, targets: List[int], anchor: str, 
                       action: str, new_text: str) -> str:
    """Apply the modification action at target indices."""
    result = content
    offset = 0  # Track position changes from modifications
    
    for idx in targets:
        actual_idx = idx + offset
        anchor_end = actual_idx + len(anchor)
        
        if action == "before":
            result = result[:actual_idx] + new_text + result[actual_idx:]
            offset += len(new_text)
        elif action == "after":
            result = result[:anchor_end] + new_text + result[anchor_end:]
            offset += len(new_text)
        else:  # replace
            result = result[:actual_idx] + new_text + result[anchor_end:]
            offset += len(new_text) - len(anchor)
    
    return result

@trace_tool(name="modify_file", metadata={"category": "write"})
def modify_file(path: Path, anchor: str = "", action: str = "after", 
                content: str = "", occurrence: int = 1) -> Tuple[str, str, Dict]:
    """Modify a file using anchor-based operations.
    
    This is the universal modification function that handles all edit operations
    through a simple anchor + action model.
    
    Args:
        path: Absolute path to file
        anchor: Text to find (empty string = beginning/end of file)
        action: One of "before", "after", "replace"
        content: New content to insert/replace with
        occurrence: Which occurrence to modify (1=first, -1=last, 0=all)
        
    Returns:
        Tuple of (old_content, new_content, change_info)
        
    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If anchor not found or invalid action
        
    Examples:
        # Append to file
        modify_file(path, anchor="", action="after", content="new text")
        
        # Insert at beginning
        modify_file(path, anchor="", action="before", content="header")
        
        # Replace entire file
        modify_file(path, anchor="", action="replace", content="new content")
        
        # Insert after marker
        modify_file(path, anchor="TODO:", action="after", content="- item")
        
        # Delete text
        modify_file(path, anchor="old text", action="replace", content="")
        
        # Replace all occurrences
        modify_file(path, anchor="foo", action="replace", content="bar", occurrence=0)
    """
    if not path.exists():
        raise RoninFileNotFoundError(path)
    
    if action not in ("before", "after", "replace"):
        raise ValueError(f"Invalid action: {action}. Use 'before', 'after', or 'replace'")
    
    # Read current content
    old_content = read_file(path)
    
    
    change_info = {
        "file": str(path),
        "action": action,
        "anchor": anchor if anchor else "[file boundaries]",
        "occurrence": occurrence
    }
    
    # Handle empty anchor (beginning/end of file)
    if not anchor:
        if action == "before":
            new_content = content + old_content
            change_info["position"] = "beginning"
        elif action == "after":
            new_content = old_content + content
            change_info["position"] = "end"
        else:  # replace
            new_content = content
            change_info["position"] = "entire file"
    else:
        # Find anchor occurrences
        indices = _find_anchor_indices(old_content, anchor)
        
        if not indices:
            # Try to find similar text for suggestions
            from exceptions import find_similar_text
            suggestions = find_similar_text(anchor, old_content)
            raise AnchorNotFoundError(anchor, path, suggestions)
        
        change_info["found_occurrences"] = len(indices)
        
        # Select which occurrence(s) to modify
        targets, occurrence_desc = _select_target_indices(indices, occurrence)
        change_info["modified_occurrences"] = occurrence_desc
        
        # Apply the modifications
        new_content = _apply_modification(old_content, targets, anchor, action, content)
    
    # Write the modified content
    path.write_text(new_content, encoding="utf-8")
    
    # Add size/line change info
    change_info["old_size"] = len(old_content)
    change_info["new_size"] = len(new_content)
    change_info["old_lines"] = old_content.count('\n') + 1
    change_info["new_lines"] = new_content.count('\n') + 1
    change_info["size_change"] = len(new_content) - len(old_content)
    change_info["line_change"] = change_info["new_lines"] - change_info["old_lines"]
    
    return (old_content, new_content, change_info)

@trace_tool(name="search_files", metadata={"category": "read"})
def search_files(root: Path, text: str, pattern: str = "*", 
                 case_sensitive: bool = False, context_lines: int = 2) -> Dict:
    """Search for text across files, like Ctrl+F but for multiple files.
    
    Args:
        root: Project root directory
        text: Text to search for
        pattern: Glob pattern for files to search (default: all files)
        case_sensitive: Whether search is case-sensitive (default: False)
        context_lines: Number of lines to show before/after each match (0 = just the match)
        
    Returns:
        Dict with search results including file paths, line numbers, and context
    """
    if not text:
        raise ValueError("Search text cannot be empty")
    
    results = {
        "query": text,
        "case_sensitive": case_sensitive,
        "matches": [],
        "total_matches": 0,
        "files_searched": 0,
        "files_with_matches": 0
    }
    
    # Prepare search text
    search_text = text if case_sensitive else text.lower()
    
    # Find all matching files
    files = []
    for ext in ALLOWED_EXTS:
        if pattern == "*":
            files.extend(root.rglob(f"*{ext}"))
        else:
            # Handle patterns like "*.md" or "docs/*.txt"
            if not pattern.endswith(ext) and "*" not in pattern:
                # If pattern doesn't include extension, add it
                files.extend(root.glob(f"{pattern}{ext}"))
            else:
                files.extend(root.glob(pattern))
    
    # Filter out files in ignored directories
    filtered_files = [f for f in files if not should_ignore_path(f)]
    
    # Remove duplicates and sort
    files = sorted(set(filtered_files))
    results["files_searched"] = len(files)
    
    for file_path in files:
        try:
            content = file_path.read_text(encoding="utf-8")
            lines = content.splitlines()
            file_matches = []
            
            for line_num, line in enumerate(lines, 1):
                check_line = line if case_sensitive else line.lower()
                if search_text in check_line:
                    # Build context
                    context = {}
                    
                    # Get before context
                    if context_lines > 0:
                        start = max(0, line_num - context_lines - 1)
                        context["before"] = lines[start:line_num - 1]
                    
                    # The matching line
                    context["line"] = line
                    context["line_number"] = line_num
                    
                    # Get after context
                    if context_lines > 0:
                        end = min(len(lines), line_num + context_lines)
                        context["after"] = lines[line_num:end]
                    
                    file_matches.append(context)
                    
                    # Limit matches per file to avoid spam
                    if len(file_matches) >= 10:
                        context["truncated"] = True
                        break
            
            if file_matches:
                results["matches"].append({
                    "file": str(file_path.relative_to(root)),
                    "matches": file_matches
                })
                results["files_with_matches"] += 1
                results["total_matches"] += len(file_matches)
                
        except Exception as e:
            # Skip files that can't be read
            continue
    
    return results

# ============================================================================
# GIT INTEGRATION - Version control operations
# ============================================================================

import subprocess
import json
from datetime import datetime

def run_git_command(root: Path, command: List[str]) -> Tuple[bool, str, str]:
    """Run a git command and return success, stdout, stderr.
    
    Args:
        root: Project root directory  
        command: Git command as list (e.g., ["status", "--porcelain"])
        
    Returns:
        Tuple of (success, stdout, stderr)
    """
    try:
        result = subprocess.run(
            ["git"] + command,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Git command timed out"
    except FileNotFoundError:
        return False, "", "Git is not installed or not in PATH"
    except Exception as e:
        return False, "", str(e)

@trace_tool(name="git_status", metadata={"category": "git"})
def git_status(root: Path) -> Dict:
    """Check git repository status.
    
    Args:
        root: Project root directory
        
    Returns:
        Dict with branch, staged, modified, and untracked files
    """
    # Check if we're in a git repo
    success, _, _ = run_git_command(root, ["rev-parse", "--git-dir"])
    if not success:
        return {"error": "Not in a git repository"}
    
    result = {}
    
    # Get current branch
    success, branch, _ = run_git_command(root, ["branch", "--show-current"])
    if success:
        result["branch"] = branch.strip()
    
    # Get ahead/behind status
    success, tracking, _ = run_git_command(root, ["status", "-sb"])
    if success and ("ahead" in tracking or "behind" in tracking):
        # Extract ahead/behind from first line
        first_line = tracking.split('\n')[0]
        if '[' in first_line and ']' in first_line:
            result["ahead_behind"] = first_line[first_line.index('['):first_line.index(']')+1]
    
    # Get file statuses
    success, status, _ = run_git_command(root, ["status", "--porcelain"])
    if success:
        staged = []
        modified = []
        untracked = []
        
        for line in status.splitlines():
            if not line:
                continue
            status_code = line[:2]
            filename = line[3:]
            
            if status_code[0] in "MADRC":  # Staged
                staged.append(filename)
            if status_code[1] == "M":  # Modified
                modified.append(filename)
            elif status_code == "??":  # Untracked
                untracked.append(filename)
        
        if staged:
            result["staged"] = staged
        if modified:
            result["modified"] = modified
        if untracked:
            result["untracked"] = untracked
    
    return result

@trace_tool(name="git_diff", metadata={"category": "git"})
def git_diff(root: Path, staged: bool = False, file: Optional[str] = None, 
             commit: Optional[str] = None) -> Dict:
    """Show git diff output.
    
    Args:
        root: Project root directory
        staged: Show staged changes instead of unstaged
        file: Specific file to diff
        commit: Compare with specific commit
        
    Returns:
        Dict with diff output
    """
    cmd = ["diff"]
    
    if staged:
        cmd.append("--cached")
    
    if commit:
        cmd.append(commit)
    
    if file:
        # Validate file path stays in sandbox
        try:
            file_path = (root / file).resolve()
            file_path.relative_to(root)
            cmd.append(str(file))
        except ValueError:
            return {"error": f"File path '{file}' is outside project root"}
    
    success, diff, error = run_git_command(root, cmd)
    
    if not success:
        return {"error": error or "Failed to get diff"}
    
    return {"diff": diff if diff else "No changes"}

@trace_tool(name="git_commit", metadata={"category": "git"})
def git_commit(root: Path, message: str, add_all: bool = False) -> Dict:
    """Create a git commit.
    
    Args:
        root: Project root directory
        message: Commit message
        add_all: Stage all modified files before commit
        
    Returns:
        Dict with commit result
    """
    if not message:
        return {"error": "Commit message is required"}
    
    # Add files if requested
    if add_all:
        success, _, error = run_git_command(root, ["add", "-A"])
        if not success:
            return {"error": f"Failed to stage files: {error}"}
    
    # Check if there's anything to commit
    success, status, _ = run_git_command(root, ["status", "--porcelain"])
    if success and not status:
        return {"error": "Nothing to commit, working tree clean"}
    
    # Create commit
    success, output, error = run_git_command(root, ["commit", "-m", message])
    
    if not success:
        if "nothing to commit" in error or "nothing to commit" in output:
            return {"error": "Nothing staged for commit"}
        return {"error": error or "Failed to create commit"}
    
    # Get commit details
    result = {"message": message}
    
    # Get commit hash
    success, hash_out, _ = run_git_command(root, ["rev-parse", "HEAD"])
    if success:
        result["commit_hash"] = hash_out.strip()
    
    # Parse commit output for stats
    for line in output.splitlines():
        if "file" in line and "changed" in line:
            parts = line.split(",")
            for part in parts:
                part = part.strip()
                if "file" in part:
                    result["files_changed"] = int(part.split()[0])
                elif "insertion" in part:
                    result["insertions"] = int(part.split()[0])
                elif "deletion" in part:
                    result["deletions"] = int(part.split()[0])
    
    return result

@trace_tool(name="git_log", metadata={"category": "git"})
def git_log(root: Path, limit: int = 10, oneline: bool = False, 
            file: Optional[str] = None) -> Dict:
    """View git commit history.
    
    Args:
        root: Project root directory
        limit: Number of commits to show
        oneline: Use compact format
        file: Show commits for specific file
        
    Returns:
        Dict with commit history
    """
    cmd = ["log", f"-{limit}"]
    
    if oneline:
        cmd.append("--oneline")
    else:
        # Use a format that's easy to parse
        cmd.extend(["--pretty=format:%H|%an|%ae|%ad|%s", "--date=short"])
    
    if file:
        # Validate file path
        try:
            file_path = (root / file).resolve()
            file_path.relative_to(root)
            cmd.extend(["--", str(file)])
        except ValueError:
            return {"error": f"File path '{file}' is outside project root"}
    
    success, log_output, error = run_git_command(root, cmd)
    
    if not success:
        return {"error": error or "Failed to get log"}
    
    if not log_output:
        return {"commits": []}
    
    commits = []
    
    if oneline:
        for line in log_output.splitlines():
            if line:
                parts = line.split(" ", 1)
                commits.append({
                    "hash": parts[0],
                    "message": parts[1] if len(parts) > 1 else ""
                })
    else:
        for line in log_output.splitlines():
            if line:
                parts = line.split("|")
                if len(parts) >= 5:
                    commit = {
                        "hash": parts[0],
                        "author": parts[1],
                        "email": parts[2],
                        "date": parts[3],
                        "message": parts[4]
                    }
                    
                    # Get files changed for this commit
                    success, files, _ = run_git_command(
                        root, 
                        ["diff-tree", "--no-commit-id", "--name-only", "-r", parts[0]]
                    )
                    if success and files:
                        commit["files"] = files.strip().splitlines()
                    
                    commits.append(commit)
    
    return {"commits": commits}

@trace_tool(name="git_branch", metadata={"category": "git"})
def git_branch(root: Path, action: str = "list", name: Optional[str] = None, 
               force: bool = False) -> Dict:
    """Manage git branches.
    
    Args:
        root: Project root directory
        action: Operation - list, create, switch, delete
        name: Branch name (for create/switch/delete)
        force: Force delete even if not merged
        
    Returns:
        Dict with branch operation result
    """
    if action == "list":
        success, branches, error = run_git_command(root, ["branch", "-a"])
        if not success:
            return {"error": error or "Failed to list branches"}
        
        branch_list = []
        for line in branches.splitlines():
            if line:
                is_current = line.startswith("*")
                branch_name = line[2:].strip() if is_current else line.strip()
                branch_list.append({
                    "name": branch_name,
                    "current": is_current
                })
        
        return {"action": "list", "branches": branch_list}
    
    elif action in ["create", "switch", "delete"]:
        if not name:
            return {"error": f"Branch name required for {action}"}
        
        if action == "create":
            success, _, error = run_git_command(root, ["branch", name])
            if not success:
                return {"error": error or f"Failed to create branch '{name}'"}
            return {"action": "create", "branch": name}
        
        elif action == "switch":
            # Try checkout first (works on older git)
            success, _, error = run_git_command(root, ["checkout", name])
            if not success:
                # Try switch (newer git command)
                success, _, error = run_git_command(root, ["switch", name])
            
            if not success:
                return {"error": error or f"Failed to switch to branch '{name}'"}
            return {"action": "switch", "branch": name}
        
        elif action == "delete":
            cmd = ["branch"]
            cmd.append("-D" if force else "-d")
            cmd.append(name)
            
            success, _, error = run_git_command(root, cmd)
            if not success:
                return {"error": error or f"Failed to delete branch '{name}'"}
            return {"action": "delete", "branch": name}
    
    else:
        return {"error": f"Unknown action: {action}"}

@trace_tool(name="git_revert", metadata={"category": "git"})
def git_revert(root: Path, target: str, type: str = "file") -> Dict:
    """Revert changes in git.
    
    Args:
        root: Project root directory
        target: File path or commit hash
        type: 'file' to revert file changes, 'commit' to revert a commit
        
    Returns:
        Dict with revert result
    """
    if type == "file":
        # Validate file path
        try:
            file_path = (root / target).resolve()
            file_path.relative_to(root)
        except ValueError:
            return {"error": f"File path '{target}' is outside project root"}
        
        # Check if file exists
        if not file_path.exists():
            return {"error": f"File '{target}' does not exist"}
        
        # Revert file to last committed state
        success, _, error = run_git_command(root, ["checkout", "HEAD", "--", target])
        
        if not success:
            return {"error": error or f"Failed to revert '{target}'"}
        
        return {"action": "file", "file": target}
    
    elif type == "commit":
        # Revert a commit
        success, _, error = run_git_command(root, ["revert", target, "--no-edit"])
        
        if not success:
            return {"error": error or f"Failed to revert commit '{target}'"}
        
        # Get new commit hash
        success, new_hash, _ = run_git_command(root, ["rev-parse", "HEAD"])
        
        result = {"action": "commit", "commit": target}
        if success:
            result["new_commit"] = new_hash.strip()
        
        return result
    
    else:
        return {"error": f"Unknown revert type: {type}"}