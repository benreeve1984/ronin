# Simplified, elegant file operations for Ronin
# Design philosophy: Minimal API, maximum power through composability

from pathlib import Path
from typing import Dict, Tuple, List
from exceptions import (
    SandboxViolationError, InvalidFileTypeError, 
    FileNotFoundError as RoninFileNotFoundError,
    FileAlreadyExistsError, AnchorNotFoundError
)

# Security: Only allow text file modifications
ALLOWED_EXTS = {".md", ".txt"}

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
    
    # Remove duplicates and sort
    files = sorted(set(files))
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