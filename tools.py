# Simplified, elegant file operations for Ronin
# Design philosophy: Minimal API, maximum power through composability

from pathlib import Path
from typing import Dict, Tuple

# Security: Only allow text file modifications
ALLOWED_EXTS = {".md", ".txt"}
MAX_READ_BYTES = 120_000

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
        raise ValueError(f"Path escapes root: {rel_path}")
    
    # Check file extension
    if p.suffix.lower() not in ALLOWED_EXTS:
        raise ValueError(f"Only {ALLOWED_EXTS} files are allowed")
    
    return p

def list_files(root: Path, pattern: str = "*") -> Dict:
    """List files matching pattern within root.
    
    Args:
        root: Project root directory
        pattern: Glob pattern (default: all files)
        
    Returns:
        Dict with path info and file list
    """
    try:
        root.relative_to(root)  # Validate it's a valid path
    except:
        return {"error": "Invalid root path"}
    
    if not root.exists() or not root.is_dir():
        return {"exists": False, "entries": []}
    
    # Find all matching files
    entries = []
    for p in root.rglob(pattern):
        if p.is_file() and p.suffix.lower() in ALLOWED_EXTS:
            entries.append(str(p.relative_to(root)))
    
    return {
        "root": str(root),
        "pattern": pattern,
        "entries": sorted(entries)[:200],  # Limit results
        "count": len(entries)
    }

def read_file(path: Path) -> str:
    """Read a text file.
    
    Args:
        path: Absolute path to file
        
    Returns:
        File contents as string
        
    Raises:
        FileNotFoundError: If file doesn't exist
    """
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    
    # Read with size limit for safety
    data = path.read_bytes()[:MAX_READ_BYTES]
    text = data.decode("utf-8", errors="replace")
    
    # Add line count info if truncated
    if len(data) == MAX_READ_BYTES:
        text += f"\n\n[TRUNCATED - file exceeds {MAX_READ_BYTES} bytes]"
    
    return text

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
        raise FileExistsError(f"File already exists: {path}")
    
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
        raise FileNotFoundError(f"File not found: {path}")
    
    # Get info before deletion
    size = path.stat().st_size
    
    path.unlink()
    
    return {
        "deleted": str(path),
        "size": size
    }

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
        raise FileNotFoundError(f"File not found: {path}")
    
    if action not in ("before", "after", "replace"):
        raise ValueError(f"Invalid action: {action}. Use 'before', 'after', or 'replace'")
    
    # Read current content
    old_content = read_file(path)
    
    # Remove truncation marker if present
    if "[TRUNCATED" in old_content:
        old_content = old_content.split("[TRUNCATED")[0]
    
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
        indices = []
        start = 0
        while True:
            idx = old_content.find(anchor, start)
            if idx == -1:
                break
            indices.append(idx)
            start = idx + 1
        
        if not indices:
            raise ValueError(f"Anchor not found: {anchor!r}")
        
        change_info["found_occurrences"] = len(indices)
        
        # Select which occurrence(s) to modify
        if occurrence == 0:  # All occurrences
            targets = indices
            change_info["modified_occurrences"] = "all"
        elif occurrence == -1:  # Last occurrence
            targets = [indices[-1]]
            change_info["modified_occurrences"] = "last"
        elif 0 < occurrence <= len(indices):  # Specific occurrence
            targets = [indices[occurrence - 1]]
            change_info["modified_occurrences"] = f"#{occurrence}"
        else:
            raise ValueError(f"Invalid occurrence {occurrence} (found {len(indices)} matches)")
        
        # Build new content by processing each target
        new_content = old_content
        offset = 0  # Track position changes from modifications
        
        for idx in targets:
            actual_idx = idx + offset
            anchor_end = actual_idx + len(anchor)
            
            if action == "before":
                new_content = new_content[:actual_idx] + content + new_content[actual_idx:]
                offset += len(content)
            elif action == "after":
                new_content = new_content[:anchor_end] + content + new_content[anchor_end:]
                offset += len(content)
            else:  # replace
                new_content = new_content[:actual_idx] + content + new_content[anchor_end:]
                offset += len(content) - len(anchor)
    
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