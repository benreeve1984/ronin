# Interactive Chat Mode for Ronin
# =================================
# This module provides interactive conversation capabilities with Ronin.
# Users can have multi-turn conversations with file context persistence.

import os
import sys
from pathlib import Path
from typing import List, Dict
import anthropic
from datetime import datetime

from tool_registry import get_tool_specs
from tool_executor import ToolExecutor
from prompts import get_system_prompt, FILE_CONTEXT_TEMPLATE, format_prompt
from utils import parse_claude_response
from langsmith_tracer import get_tracer, trace_chain

# Token limits (approximate - using character count as proxy)
MAX_CONTEXT_TOKENS = 140_000
CHARS_PER_TOKEN = 4  # Rough estimate: 1 token ≈ 4 characters

class FileMemory:
    """
    Track files read during the session for context awareness.
    
    This class maintains an LRU (Least Recently Used) cache of files
    that have been read during the conversation. Files are kept in
    context to help Claude understand what's been discussed.
    
    Attributes:
        files: Dictionary mapping file paths to their contents
        access_order: List tracking access order for LRU eviction
        content_hash: Track content hashes to detect changes
        max_files: Maximum number of files to keep in memory
    """
    
    def __init__(self, max_files: int = 10):
        """Initialize empty file memory."""
        self.files: Dict[str, str] = {}  # path -> content mapping
        self.access_order: List[str] = []  # LRU tracking
        self.content_hash: Dict[str, int] = {}  # path -> hash for change detection
        self.max_files = max_files
        
    def add_file(self, path: str, content: str):
        """
        Add or update a file in memory with deduplication.
        
        Args:
            path: File path as string
            content: File contents
            
        Note:
            - Only updates if content has changed
            - Enforces max_files limit with LRU eviction
        """
        content_hash = hash(content)
        
        # Skip if content hasn't changed
        if path in self.files and self.content_hash.get(path) == content_hash:
            # Just update access order
            self.access_order.remove(path)
            self.access_order.append(path)
            return
        
        # Remove from access order if it exists
        if path in self.files:
            self.access_order.remove(path)
        
        # Enforce max files limit (LRU eviction)
        while len(self.files) >= self.max_files and self.access_order:
            oldest = self.access_order.pop(0)
            del self.files[oldest]
            del self.content_hash[oldest]
        
        # Add/update the file
        self.files[path] = content
        self.content_hash[path] = content_hash
        self.access_order.append(path)
        
    def get_context(self, max_chars: int) -> str:
        """
        Get file context within size limit.
        
        Args:
            max_chars: Maximum characters to include
            
        Returns:
            Formatted string with file contents, most recent first
        """
        if not self.files:
            return ""
            
        context_parts = []
        total_chars = 0
        
        # Add files in reverse access order (most recent first)
        for path in reversed(self.access_order):
            content = self.files[path]
            file_section = f"\n--- {path} ---\n{content}\n"
            
            if total_chars + len(file_section) > max_chars:
                break
                
            context_parts.append(file_section)
            total_chars += len(file_section)
            
        if context_parts:
            file_context = "".join(context_parts)
            return format_prompt(FILE_CONTEXT_TEMPLATE, file_context=file_context)
        return ""

class ChatSession:
    """
    Manages an interactive chat session with Ronin.
    
    This class handles:
    - Multi-turn conversations with Claude
    - File memory management
    - Special commands (/, help, etc.)
    - Context size management
    - Tool execution through ToolExecutor
    
    Attributes:
        client: Anthropic API client
        model: Claude model to use
        root: Sandbox root directory
        auto_yes: Whether to auto-approve changes
        max_steps: Max tool operations per turn
        messages: Conversation history
        file_memory: Files read during session
        executor: Tool executor instance
        total_operations: Total tool uses in session
    """
    
    def __init__(self, model: str, root: Path, auto_yes: bool, max_steps: int, dry_run: bool = False):
        """
        Initialize a new chat session.
        
        Args:
            model: Claude model name
            root: Sandbox root directory
            auto_yes: Auto-approve changes if True
            max_steps: Max operations per turn
            dry_run: If True, simulate changes without making them
        """
        self.client = anthropic.Anthropic()
        # Wrap with LangSmith tracer if available
        self.client = get_tracer().get_wrapped_anthropic_client(self.client)
        self.model = model
        self.root = root
        self.auto_yes = auto_yes
        self.max_steps = max_steps
        self.dry_run = dry_run
        self.messages = []
        self.file_memory = FileMemory()
        self.executor = ToolExecutor(root, auto_yes, dry_run=dry_run, file_memory=self.file_memory)
        self.total_operations = 0
        
    def get_system_prompt(self) -> str:
        """
        Build system prompt with file context.
        
        Returns:
            Complete system prompt including any files in memory
        """
        # Reserve 1/3 of context for files
        max_file_context = MAX_CONTEXT_TOKENS * CHARS_PER_TOKEN // 3
        file_context = self.file_memory.get_context(max_file_context)
        
        return get_system_prompt(interactive=True, file_context=file_context)
        
    @trace_chain(name="chat_conversation_turn")
    def process_input(self, user_input: str) -> bool:
        """
        Process one user input.
        
        Args:
            user_input: User's message
            
        Returns:
            False to exit, True to continue
        """
        # Check for exit commands
        if user_input.lower() in ('exit', 'quit', 'bye', '/exit', '/quit'):
            return False
            
        # Check for special slash commands
        if user_input.startswith('/'):
            return self.handle_command(user_input)
            
        # Add user message to conversation
        self.messages.append({"role": "user", "content": user_input})
        
        # Compress context if needed before calling Claude
        self.compress_context()
        
        # Process with Claude
        operations_this_turn = 0
        
        # Build system prompt ONCE per user turn (not per tool iteration!)
        system_prompt = self.get_system_prompt()
        tool_specs = get_tool_specs(self.root)
        
        while operations_this_turn < self.max_steps:
            try:
                # Get Claude's response with prompt caching
                # Cache system prompt and tools for 5 minutes (they don't change within a turn)
                resp = self.client.messages.create(
                    model=self.model,
                    system=[
                        {
                            "type": "text",
                            "text": system_prompt,
                            "cache_control": {"type": "ephemeral"}  # Cache for 5 minutes
                        }
                    ],
                    tools=tool_specs,  # Tools are automatically cached when >1024 tokens
                    messages=self.messages,
                    max_tokens=2000,
                )
                
                # Parse and print Claude's response
                text, tool_uses = parse_claude_response(resp.content)
                if text:
                    print(f"\n🤖 {text}")
                
                # Add assistant message to history
                self.messages.append({"role": "assistant", "content": resp.content})
                
                if not tool_uses:
                    # No more tools requested - turn complete
                    break
                    
                # Process tool requests
                results = self.process_tools(tool_uses)
                operations_this_turn += len(tool_uses)
                self.total_operations += len(tool_uses)
                
                # Add results to conversation
                self.messages.append({"role": "user", "content": results})
                
            except Exception as e:
                print(f"\n❌ Error: {e}")
                break
                
        if operations_this_turn >= self.max_steps:
            print(f"\n⚠️  Reached maximum operations for this turn ({self.max_steps})")
            
        # Trim message history if getting too long
        # Context compression now happens at the start of process_input
        
        return True
        
    def process_tools(self, tool_uses) -> List[Dict]:
        """
        Process tool requests from Claude.
        
        Args:
            tool_uses: List of tool use requests from Claude
            
        Returns:
            List of tool results to send back to Claude
        """
        results = []
        
        for tool_use in tool_uses:
            tool_name = tool_use.name
            args = dict(tool_use.input or {})
            
            # Execute through our centralized executor
            output, success = self.executor.execute(tool_name, args)
            
            results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": output,
                "is_error": not success
            })
                
        return results
        
    def handle_command(self, command: str) -> bool:
        """
        Handle special slash commands.
        
        Args:
            command: The slash command (e.g., "/help")
            
        Returns:
            True to continue, False to exit
        """
        cmd = command.lower().strip()
        
        if cmd in ('/help', '/h', '/?'):
            print("""
📚 Available commands:
  /help, /h     - Show this help
  /files, /f    - List files in memory
  /clear        - Clear conversation history
  /root         - Show current root directory
  /stats        - Show session statistics
  /exit, /quit  - Exit Ronin
  
Just type normally to interact with Ronin!
""")
        elif cmd in ('/files', '/f'):
            if self.file_memory.files:
                print("\n📁 Files in memory:")
                for path in self.file_memory.access_order:
                    size = len(self.file_memory.files[path])
                    print(f"  - {path} ({size} bytes)")
            else:
                print("\n📁 No files in memory yet")
                
        elif cmd == '/clear':
            self.messages = []
            print("\n🧹 Conversation history cleared")
            
        elif cmd == '/root':
            print(f"\n📂 Root directory: {self.root}")
            
        elif cmd == '/stats':
            # Check tracing status
            from langsmith_tracer import get_tracer
            tracer = get_tracer()
            tracing_status = "✅ Active" if tracer.enabled else "❌ Disabled (no API key)"
            
            # Calculate context usage
            estimated_tokens = self.estimate_context_size()
            usage_percent = (estimated_tokens / MAX_CONTEXT_TOKENS) * 100
            
            # Create usage bar
            bar_width = 20
            filled = int(bar_width * usage_percent / 100)
            bar = "█" * filled + "░" * (bar_width - filled)
            
            print(f"""
📊 Session Statistics:
  Messages: {len(self.messages)}
  Operations: {self.total_operations}
  Files in memory: {len(self.file_memory.files)} (max: {self.file_memory.max_files})
  Root: {self.root}
  LangSmith Tracing: {tracing_status}
  
  Context Usage: [{bar}] {usage_percent:.1f}%
  Tokens: ~{estimated_tokens:,} / {MAX_CONTEXT_TOKENS:,}
  
  Compression triggers at 80% ({int(MAX_CONTEXT_TOKENS * 0.8):,} tokens)
""")
        else:
            print(f"\n❓ Unknown command: {command}")
            print("Type /help for available commands")
            
        return True
        
    def estimate_context_size(self) -> int:
        """Estimate current context size in tokens."""
        # Count message history
        message_chars = sum(len(str(msg)) for msg in self.messages)
        
        # Count file context
        file_chars = len(self.file_memory.get_context(MAX_CONTEXT_TOKENS * CHARS_PER_TOKEN))
        
        # Count system prompt (rough estimate)
        system_chars = 2000  # Approximate system prompt size
        
        total_chars = message_chars + file_chars + system_chars
        return total_chars // CHARS_PER_TOKEN
    
    def compress_context(self):
        """
        Intelligently compress context when approaching limits.
        
        Strategy:
        1. First, reduce file context (keep only most recent/relevant)
        2. Then, summarize older conversation turns
        3. Finally, hard trim if necessary
        """
        estimated_tokens = self.estimate_context_size()
        
        # Start compression at 80% of limit
        if estimated_tokens < MAX_CONTEXT_TOKENS * 0.8:
            return
        
        print("\n🗜️ Compressing context to stay within limits...")
        
        # Step 1: Reduce file memory (keep only 5 most recent)
        if len(self.file_memory.files) > 5:
            # Keep only the 5 most recently accessed files
            to_remove = self.file_memory.access_order[:-5]
            for path in to_remove:
                del self.file_memory.files[path]
                del self.file_memory.content_hash[path]
            self.file_memory.access_order = self.file_memory.access_order[-5:]
            print("  • Reduced file context to 5 most recent files")
        
        # Step 2: Compress old messages (keep first 2 and last 10)
        if len(self.messages) > 15:
            first_messages = self.messages[:2]  # Keep initial context
            recent_messages = self.messages[-10:]  # Keep recent context
            
            # Create a summary of the middle messages
            middle_count = len(self.messages) - 12
            summary_msg = {
                "role": "assistant",
                "content": f"[Previous {middle_count} messages compressed - continuing conversation]"
            }
            
            self.messages = first_messages + [summary_msg] + recent_messages
            print(f"  • Compressed {middle_count} older messages")
        
        # Check if we're still over limit
        estimated_tokens = self.estimate_context_size()
        if estimated_tokens > MAX_CONTEXT_TOKENS * 0.95:
            # Emergency trim - keep only last 5 messages
            self.messages = self.messages[-5:]
            self.file_memory.files.clear()
            self.file_memory.access_order.clear()
            self.file_memory.content_hash.clear()
            print("  • Emergency trim: kept only last 5 messages, cleared file context")

def interactive_mode(model: str, root: Path, auto_yes: bool, max_steps: int):
    """
    Run Ronin in interactive chat mode.
    
    This is the main entry point for interactive mode. It displays
    a welcome message and starts the conversation loop.
    
    Args:
        model: Claude model to use
        root: Sandbox root directory
        auto_yes: Auto-approve changes if True
        max_steps: Max operations per turn
    """
    
    print("""
    ██████╗  ██████╗ ███╗   ██╗██╗███╗   ██╗
    ██╔══██╗██╔═══██╗████╗  ██║██║████╗  ██║
    ██████╔╝██║   ██║██╔██╗ ██║██║██╔██╗ ██║
    ██╔══██╗██║   ██║██║╚██╗██║██║██║╚██╗██║
    ██║  ██║╚██████╔╝██║ ╚████║██║██║ ╚████║
    ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝╚═╝╚═╝  ╚═══╝
    
    🥷 Your CLI Agent
    
    Commands: /help  /clear  /exit
    Just type to start chatting!
""")
    
    session = ChatSession(model, root, auto_yes, max_steps)
    
    while True:
        try:
            # Get user input
            user_input = input("\n💬 You: ").strip()
            
            if not user_input:
                continue
                
            # Process input
            if not session.process_input(user_input):
                print("\n👋 Goodbye!")
                break
                
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except EOFError:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Unexpected error: {e}")
            print("You can continue or type 'exit' to quit.")