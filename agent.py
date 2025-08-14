# Simplified Ronin agent using centralized tool system
# ======================================================
# This module orchestrates Claude AI and manages the conversation flow.
# Tool definitions and execution are now centralized in tool_registry and tool_executor.

import anthropic
from pathlib import Path
from tool_registry import get_tool_specs
from tool_executor import ToolExecutor
from prompts import get_system_prompt
from utils import parse_claude_response
from langsmith_tracer import get_tracer, trace_chain

@trace_chain(name="ronin_single_command")
def run_once(prompt: str, model: str, root: Path, auto_yes: bool, dry_run: bool, max_steps: int) -> bool:
    """
    Process a user request with Claude AI, allowing multiple operations until complete.
    
    This is the main entry point for single-shot Ronin usage (non-interactive mode).
    It manages the conversation with Claude, executes requested tools, and handles
    the back-and-forth until the task is complete or max_steps is reached.
    
    Args:
        prompt: The user's request in natural language
        model: Which Claude model to use (e.g., "claude-3-sonnet-20240229")
        root: The sandbox root directory (Ronin can't access files outside this)
        auto_yes: If True, auto-approve all changes without asking
        dry_run: If True, simulate changes without actually making them
        max_steps: Maximum number of tool operations before stopping
        
    Returns:
        True if successful, False if there was an error
        
    Flow:
        1. Send user prompt to Claude with available tools
        2. Claude responds with text and/or tool requests
        3. Execute requested tools through ToolExecutor
        4. Send results back to Claude
        5. Repeat until Claude stops requesting tools or max_steps reached
    """
    # Initialize Claude client with LangSmith tracing
    client = anthropic.Anthropic()
    client = get_tracer().get_wrapped_anthropic_client(client)
    
    # Start conversation with user's prompt
    messages = [{"role": "user", "content": prompt}]
    
    # Initialize tool executor with our settings
    executor = ToolExecutor(root, auto_yes, dry_run)
    
    # Track total operations to enforce max_steps limit
    total_operations = 0
    
    # Get system prompt and tool specifications
    system_prompt = get_system_prompt(interactive=False)
    tool_specs = get_tool_specs(root)
    
    # Main conversation loop
    while total_operations < max_steps:
        # Get Claude's response
        resp = client.messages.create(
            model=model,
            system=system_prompt,
            tools=tool_specs,
            messages=messages,
            max_tokens=2000,  # Enough for complex operations
        )

        # Parse Claude's response
        text, tool_uses = parse_claude_response(resp.content)
        if text:
            print(f"\n🤖 {text}")
        
        if not tool_uses:
            # No more tools requested - task is complete!
            return True

        # Process each tool request
        results = []
        for tool_use in tool_uses:
            tool_name = tool_use.name
            args = dict(tool_use.input or {})
            total_operations += 1
            
            # Execute the tool through our centralized executor
            output, success = executor.execute(tool_name, args)
            
            # Build result for Claude
            results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": output,
                "is_error": not success  # Tell Claude if it failed
            })

        # Continue conversation with tool results
        messages.append({"role": "assistant", "content": resp.content})
        messages.append({"role": "user", "content": results})

    # Reached max_steps limit
    print(f"\n⚠️  Reached maximum operations limit ({max_steps})")
    return True