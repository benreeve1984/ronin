# Import necessary Python libraries
import argparse  # For parsing command-line arguments
import os  # For accessing environment variables
import sys  # For system operations like exit codes
import pathlib  # For path handling

# Import the main execution function from agent.py
from agent import run_once
# Import logging setup
from logging_config import setup_logging
# Import secrets management
from secrets_manager import set_api_key, remove_api_key, list_providers, get_api_key
# Import LangSmith tracing
from langsmith_tracer import configure_langsmith

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
    # OPTIONAL: Ask for confirmation before applying changes
    # action="store_true" means it's a flag (present = True, absent = False)
    # DEFAULT: Auto-approve is ON. Use --no-auto-yes to require confirmations
    p.add_argument("--no-auto-yes", action="store_true", help="Ask for confirmation before changes (default: auto-approve)")
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
    
    # SECRETS MANAGEMENT: Commands for managing API keys
    # These allow setting API keys that persist across all sessions
    p.add_argument("--set-key", nargs=2, metavar=("PROVIDER", "KEY"),
                   help="Store API key for a provider (e.g., --set-key anthropic sk-...)")
    p.add_argument("--remove-key", metavar="PROVIDER",
                   help="Remove stored API key for a provider")
    p.add_argument("--list-keys", action="store_true",
                   help="List providers with stored API keys")
    
    # TRACING: LangSmith observability options
    p.add_argument("--no-tracing", action="store_true",
                   help="Disable LangSmith tracing for this session (tracing is on by default if API key is set)")
    p.add_argument("--langsmith-project", metavar="PROJECT",
                   help="Set LangSmith project name for organizing traces")
    
    # Parse the command-line arguments into a namespace object
    args = p.parse_args()
    
    # Initialize logging (can be configured via env vars)
    # Only show warnings and errors in console by default
    log_level = os.getenv("RONIN_LOG_LEVEL", "WARNING")
    log_to_file = os.getenv("RONIN_LOG_TO_FILE", "true").lower() == "true"
    setup_logging(level=log_level, log_to_file=log_to_file)
    
    # Handle secrets management commands BEFORE initializing tracing
    if args.set_key:
        provider, key = args.set_key
        if set_api_key(provider, key):
            print(f"✅ API key stored for {provider}")
            print(f"You can now use Ronin without setting {provider.upper()}_API_KEY")
        else:
            print(f"❌ Failed to store API key for {provider}")
        sys.exit(0)
    
    if args.remove_key:
        if remove_api_key(args.remove_key):
            print(f"✅ API key removed for {args.remove_key}")
        else:
            print(f"❌ No API key found for {args.remove_key}")
        sys.exit(0)
    
    if args.list_keys:
        providers = list_providers()
        if providers:
            print("📔 Stored API keys:")
            for provider in providers:
                # Show provider and masked key for security
                key = get_api_key(provider)
                if key:
                    masked = key[:8] + "..." + key[-4:] if len(key) > 12 else "***"
                    print(f"  - {provider}: {masked}")
        else:
            print("No API keys stored. Use --set-key to add one.")
        sys.exit(0)
    
    # Configure LangSmith tracing AFTER handling secrets (on by default if API key exists)
    if args.no_tracing:
        os.environ["RONIN_ENABLE_TRACING"] = "false"
    
    if args.langsmith_project:
        os.environ["LANGSMITH_PROJECT"] = args.langsmith_project
    
    # Initialize LangSmith silently (will be enabled by default if API key exists)
    tracing_enabled = configure_langsmith(
        enabled=False if args.no_tracing else None
    )
    
    # Only show tracing status in debug mode
    if os.getenv("RONIN_LOG_LEVEL") == "DEBUG":
        if tracing_enabled:
            print("🔍 LangSmith tracing active")
        elif not args.no_tracing:
            print("🔍 LangSmith tracing not available")

    # Check for Claude API key (from environment or stored secrets)
    # This key authenticates your requests to Claude AI
    api_key = get_api_key("anthropic")
    if not api_key:
        print("Error: No API key found for Anthropic", file=sys.stderr)
        print("Please either:", file=sys.stderr)
        print("  1. Set ANTHROPIC_API_KEY environment variable", file=sys.stderr)
        print("  2. Run: Ronin --set-key anthropic <your-api-key>", file=sys.stderr)
        # Exit with code 2 (configuration error)
        sys.exit(2)
    
    # Set the API key in environment for this session
    # (The Anthropic client reads from environment)
    if not os.getenv("ANTHROPIC_API_KEY"):
        os.environ["ANTHROPIC_API_KEY"] = api_key

    # If no prompt provided, enter interactive mode
    if not args.prompt:
        from chat_mode import interactive_mode
        # Convert the root to Path and run interactive mode
        root = pathlib.Path(args.root).resolve()
        interactive_mode(
            model=args.model,
            root=root,
            auto_yes=not args.no_auto_yes,  # Default is True unless flag is set
            max_steps=args.max_steps
        )
        sys.exit(0)

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
        auto_yes=not args.no_auto_yes,  # Auto-approve changes by default
        dry_run=args.plan,  # Preview mode?
        max_steps=args.max_steps,  # Maximum tool operations
    )
    # Exit with appropriate code:
    # 0 = success (Unix convention)
    # 1 = general error
    sys.exit(0 if ok else 1)