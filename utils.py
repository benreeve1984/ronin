# Shared Utilities for Ronin
# ==========================
# Common functions used across multiple modules

from typing import List, Tuple, Any

def parse_claude_response(response_content: List[Any]) -> Tuple[str, List[Any]]:
    """Parse Claude's response into text and tool use blocks.
    
    Args:
        response_content: List of content blocks from Claude's response
        
    Returns:
        Tuple of (text_content, tool_use_blocks)
    """
    text_parts = []
    tool_uses = []
    
    for block in response_content:
        if getattr(block, "type", None) == "text":
            text = block.text.strip()
            if text:
                text_parts.append(text)
        elif getattr(block, "type", None) == "tool_use":
            tool_uses.append(block)
    
    combined_text = "\n".join(text_parts)
    return combined_text, tool_uses