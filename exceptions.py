# Custom Exceptions for Ronin
# ============================
# These exceptions provide clear error messages and recovery hints
# for both humans and Claude AI to understand what went wrong.

from typing import Optional, Dict, Any
from pathlib import Path

class RoninError(Exception):
    """
    Base exception for all Ronin errors.
    
    Attributes:
        message: Human-readable error message
        recovery_hints: Suggestions for fixing the error (for Claude)
        context: Additional context about the error
    """
    
    def __init__(self, message: str, recovery_hints: Optional[str] = None, 
                 context: Optional[Dict[str, Any]] = None):
        self.message = message
        self.recovery_hints = recovery_hints or "Please check the error message and try again."
        self.context = context or {}
        super().__init__(self.message)
    
    def to_claude_message(self) -> str:
        """Format error for Claude to understand and recover from."""
        msg = f"❌ Error: {self.message}\n"
        msg += f"💡 How to fix: {self.recovery_hints}"
        if self.context:
            msg += f"\n📋 Context: {self.context}"
        return msg

class ToolNotFoundError(RoninError):
    """Raised when a requested tool doesn't exist."""
    
    def __init__(self, tool_name: str, available_tools: list):
        super().__init__(
            message=f"Tool '{tool_name}' not found",
            recovery_hints=f"Use one of these tools instead: {', '.join(available_tools)}",
            context={"requested": tool_name, "available": available_tools}
        )

class FileNotFoundError(RoninError):
    """Raised when a file doesn't exist."""
    
    def __init__(self, path: Path, suggestion: Optional[str] = None):
        hints = f"Try: 1) Check if the path '{path}' is correct, 2) Use list_files to see available files"
        if suggestion:
            hints += f", 3) Did you mean '{suggestion}'?"
        
        super().__init__(
            message=f"File not found: {path}",
            recovery_hints=hints,
            context={"path": str(path), "suggestion": suggestion}
        )

class FileAlreadyExistsError(RoninError):
    """Raised when trying to create a file that already exists."""
    
    def __init__(self, path: Path):
        super().__init__(
            message=f"File already exists: {path}",
            recovery_hints=(
                f"Try: 1) Use modify_file to edit the existing file, "
                f"2) Use delete_file first if you want to recreate it, "
                f"3) Choose a different filename"
            ),
            context={"path": str(path)}
        )

class SandboxViolationError(RoninError):
    """Raised when trying to access files outside the sandbox."""
    
    def __init__(self, path: Path, root: Path):
        super().__init__(
            message=f"Path '{path}' is outside the sandbox root '{root}'",
            recovery_hints=(
                f"Only access files within '{root}'. "
                f"Use relative paths or paths starting with the root directory."
            ),
            context={"attempted_path": str(path), "sandbox_root": str(root)}
        )

class InvalidFileTypeError(RoninError):
    """Raised when trying to work with non-text files."""
    
    def __init__(self, path: Path, allowed_types: set):
        super().__init__(
            message=f"File type not allowed: {path.suffix}",
            recovery_hints=f"Only these file types are allowed: {', '.join(allowed_types)}",
            context={"file": str(path), "extension": path.suffix, "allowed": list(allowed_types)}
        )

class AnchorNotFoundError(RoninError):
    """Raised when modify_file can't find the anchor text."""
    
    def __init__(self, anchor: str, file_path: Path, suggestions: Optional[list] = None):
        hints = (
            f"The text '{anchor[:50]}...' was not found in {file_path}. "
            f"Try: 1) Check for typos, 2) Use read_file to see the actual content, "
            f"3) Make sure you're matching exact text including spaces and punctuation"
        )
        if suggestions:
            hints += f", 4) Similar text found: {suggestions[:3]}"
        
        super().__init__(
            message=f"Anchor text not found in {file_path}",
            recovery_hints=hints,
            context={"anchor": anchor, "file": str(file_path), "suggestions": suggestions}
        )

class InvalidParameterError(RoninError):
    """Raised when tool receives invalid parameters."""
    
    def __init__(self, param_name: str, expected: str, got: Any):
        super().__init__(
            message=f"Invalid parameter '{param_name}': expected {expected}, got {type(got).__name__}",
            recovery_hints=f"Check the parameter type. {param_name} should be {expected}.",
            context={"parameter": param_name, "expected": expected, "received": str(got)}
        )

class ToolExecutionError(RoninError):
    """Raised when a tool fails during execution."""
    
    def __init__(self, tool_name: str, original_error: Exception):
        super().__init__(
            message=f"Tool '{tool_name}' failed: {str(original_error)}",
            recovery_hints=(
                "Check the error details. Common fixes: "
                "1) Verify file paths are correct, "
                "2) Ensure files exist before modifying, "
                "3) Check parameter types match tool requirements"
            ),
            context={"tool": tool_name, "error_type": type(original_error).__name__}
        )

class ContextLimitError(RoninError):
    """Raised when approaching Claude's context limit."""
    
    def __init__(self, current_tokens: int, max_tokens: int):
        super().__init__(
            message=f"Approaching context limit: {current_tokens}/{max_tokens} tokens",
            recovery_hints=(
                "Try: 1) Read specific line ranges instead of full files, "
                "2) Clear conversation history with /clear, "
                "3) Focus on fewer files at once"
            ),
            context={"current": current_tokens, "max": max_tokens, "percentage": current_tokens/max_tokens*100}
        )

class UserDeclinedError(RoninError):
    """Raised when user declines a confirmation prompt."""
    
    def __init__(self, action: str):
        super().__init__(
            message=f"User declined: {action}",
            recovery_hints="The user chose not to proceed. Ask them what they'd like to do instead.",
            context={"declined_action": action}
        )

def find_similar_paths(path: str, available_paths: list, threshold: float = 0.6) -> list:
    """
    Find similar file paths (for typo suggestions).
    
    Uses simple character overlap ratio for speed.
    Returns top 3 most similar paths.
    """
    from difflib import SequenceMatcher
    
    similarities = []
    for available in available_paths:
        ratio = SequenceMatcher(None, path.lower(), available.lower()).ratio()
        if ratio > threshold:
            similarities.append((available, ratio))
    
    similarities.sort(key=lambda x: x[1], reverse=True)
    return [path for path, _ in similarities[:3]]

def find_similar_text(anchor: str, content: str, max_distance: int = 3) -> list:
    """
    Find text similar to the anchor in content.
    
    Returns lines that might be what the user meant.
    """
    # Simple approach: find lines with high word overlap
    anchor_words = set(anchor.lower().split())
    suggestions = []
    
    for line in content.splitlines():
        line_words = set(line.lower().split())
        overlap = len(anchor_words & line_words)
        if overlap >= len(anchor_words) * 0.5:  # At least 50% word overlap
            suggestions.append(line.strip()[:100])  # First 100 chars
    
    return suggestions[:3]  # Top 3 suggestions