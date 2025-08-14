# Simplified Ronin agent using ChatSession for unified implementation
# =====================================================================
# This module now acts as a simple wrapper around ChatSession to prevent
# code divergence between single command and interactive modes.

from pathlib import Path
from chat_mode import ChatSession
from langsmith_tracer import trace_chain

@trace_chain(name="ronin_single_command")
def run_once(prompt: str, model: str, root: Path, auto_yes: bool, dry_run: bool, max_steps: int) -> bool:
    """
    Process a single user request using ChatSession.
    
    This is now a thin wrapper around ChatSession that processes exactly one
    user input and then exits. This ensures single command mode and chat mode
    use the exact same code paths, preventing divergence and bugs.
    
    Args:
        prompt: The user's request in natural language
        model: Which Claude model to use
        root: The sandbox root directory
        auto_yes: If True, auto-approve all changes without asking
        dry_run: If True, simulate changes without actually making them
        max_steps: Maximum number of tool operations before stopping
        
    Returns:
        True if successful, False if there was an error
    """
    # Create a chat session with the same parameters
    session = ChatSession(
        model=model,
        root=root,
        auto_yes=auto_yes,
        max_steps=max_steps,
        dry_run=dry_run
    )
    
    # Process the single input and return the result
    # process_input returns False on error or exit commands
    # For single command mode, we want to invert this:
    # - True from process_input means "continue chatting" -> return True (success)
    # - False from process_input means "exit chat" -> check if it was an error
    result = session.process_input(prompt)
    
    # In single command mode, if process_input returns True, that means
    # the command succeeded and chat would continue (but we exit)
    # If it returns False, that could mean error or intentional exit
    # Since we're not using exit commands in single mode, False = error
    return result or prompt.lower() in ('exit', 'quit', 'bye')