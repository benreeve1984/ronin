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
        "entries": sorted(entries)[:200]  # Limit results
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
    return data.decode("utf-8", errors="replace")

def create_file(path: Path, content: str) -> None:
    """Create a new file (fails if exists).
    
    Args:
        path: Absolute path for new file
        content: Initial file content
        
    Raises:
        FileExistsError: If file already exists
    """
    if path.exists():
        raise FileExistsError(f"File already exists: {path}")
    
    # Create parent directories if needed
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write the file
    path.write_text(content, encoding="utf-8")

def delete_file(path: Path) -> None:
    """Delete a file.
    
    Args:
        path: Absolute path to file to delete
        
    Raises:
        FileNotFoundError: If file doesn't exist
    """
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    
    path.unlink()

def modify_file(path: Path, anchor: str = "", action: str = "after", 
                content: str = "", occurrence: int = 1) -> Tuple[str, str]:
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
        Tuple of (old_content, new_content) for diff generation
        
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
    
    # Handle empty anchor (beginning/end of file)
    if not anchor:
        if action == "before":
            new_content = content + old_content
        elif action == "after":
            new_content = old_content + content
        else:  # replace
            new_content = content
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
        
        # Select which occurrence(s) to modify
        if occurrence == 0:  # All occurrences
            targets = indices
        elif occurrence == -1:  # Last occurrence
            targets = [indices[-1]]
        elif 0 < occurrence <= len(indices):  # Specific occurrence
            targets = [indices[occurrence - 1]]
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
    
    return (old_content, new_content)

# Legacy compatibility functions (can be removed once migration complete)
def validate_and_resolve(root: Path, rel_path: str) -> Path:
    """Legacy name for validate_path."""
    return validate_path(root, rel_path)

def list_dir_entries(root: Path, rel_dir: str = ".", glob: str = None, max_entries: int = 200) -> Dict:
    """Legacy name for list_files."""
    pattern = glob if glob else "*"
    return list_files(root, pattern)

def read_text_file(path: Path, max_bytes: int = MAX_READ_BYTES) -> str:
    """Legacy name for read_file."""
    return read_file(path)

def write_text_file(path: Path, content: str, overwrite: bool = False) -> None:
    """Legacy function - use create_file or modify_file instead."""
    if path.exists() and not overwrite:
        raise FileExistsError(f"File exists: {path}")
    if not path.exists():
        create_file(path, content)
    else:
        modify_file(path, "", "replace", content)