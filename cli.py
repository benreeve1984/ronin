# Import necessary Python libraries
import argparse  # For parsing command-line arguments
import os  # For accessing environment variables
import sys  # For system operations like exit codes
import pathlib  # For path handling

# Import the main execution function from agent.py
from .agent import run_once

def main():
    """Main entry point for the Ronin CLI application.
    
    This function:
    1. Parses command-line arguments
    2. Validates environment setup (API key)
    3. Calls the agent to process the user's request
    4. Returns appropriate exit codes
    """
    # Create the argument parser for command-line options
    # prog="Ronin" sets the program name shown in help text
    p = argparse.ArgumentParser(prog="Ronin", description="Minimal CLI LLM agent")
    # POSITIONAL ARGUMENT: The user's request/prompt
    # nargs="*" means it accepts multiple words (space-separated)
    # Example: Ronin "Add a TODO section" or Ronin Add a TODO section
    p.add_argument("prompt", nargs="*", help="User prompt (quote for multi-word)")
    # OPTIONAL: Specify which directory to work in
    # This creates the sandbox boundary - Ronin can't access files outside this
    # Default "." means current working directory
    p.add_argument("--root", default=".", help="Project root (sandbox). Default: cwd")
    # OPTIONAL: Auto-approve all file changes without asking
    # action="store_true" means it's a flag (present = True, absent = False)
    # Useful for automation but risky - changes happen immediately!
    p.add_argument("--yes", action="store_true", help="Apply writes without confirmation")
    # OPTIONAL: Preview mode - shows what would happen without doing it
    # Great for testing or understanding what Ronin will do
    p.add_argument("--plan", action="store_true", help="Dry-run mode (no writes)")
    # OPTIONAL: Limit how many tool operations Claude can perform
    # Prevents runaway operations or excessive API usage
    # Each "step" is one round of tool use (read, write, etc.)
    p.add_argument("--max-steps", type=int, default=10, help="Max tool rounds before stop")
    # OPTIONAL: Choose which Claude model to use
    # First checks RONIN_MODEL environment variable, then uses default
    # Different models have different capabilities and costs
    p.add_argument("--model", default=os.getenv("RONIN_MODEL", "claude-sonnet-4-20250514"),
                   help="Model name (or set RONIN_MODEL env var)")
    # Parse the command-line arguments into a namespace object
    args = p.parse_args()

    # Validate that user provided a prompt
    if not args.prompt:
        # Print usage help to stderr (error output stream)
        print('Usage: Ronin "your prompt here"', file=sys.stderr)
        # Exit with code 2 (conventional for command-line usage errors)
        sys.exit(2)

    # Check for Claude API key in environment variables
    # This key authenticates your requests to Claude AI
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY is not set", file=sys.stderr)
        # Exit with code 2 (configuration error)
        sys.exit(2)

    # Combine multiple prompt words into a single string
    # Example: ["Add", "a", "TODO"] becomes "Add a TODO"
    prompt = " ".join(args.prompt).strip()
    # Convert the root directory to an absolute Path object
    # .resolve() expands relative paths and follows symlinks
    root = pathlib.Path(args.root).resolve()

    # Call the main agent execution function with all parameters
    # Returns True if successful, False if there was an error
    ok = run_once(
        prompt=prompt,  # User's request
        model=args.model,  # Which Claude model to use
        root=root,  # Directory to work in (sandbox)
        auto_yes=args.yes,  # Auto-approve changes?
        dry_run=args.plan,  # Preview mode?
        max_steps=args.max_steps,  # Maximum tool operations
    )
    # Exit with appropriate code:
    # 0 = success (Unix convention)
    # 1 = general error
    sys.exit(0 if ok else 1)