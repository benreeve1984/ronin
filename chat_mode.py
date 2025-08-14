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
    """
    
    def __init__(self):
        """Initialize empty file memory."""
        self.files: Dict[str, str] = {}  # path -> content mapping
        self.access_order: List[str] = []  # LRU tracking
        
    def add_file(self, path: str, content: str):
        """
        Add or update a file in memory.
        
        Args:
            path: File path as string
            content: File contents
            
        Note:
            If file already exists, it's moved to end of access order (most recent)
        """
        if path in self.files:
            self.access_order.remove(path)
        self.files[path] = content
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
    
    def __init__(self, model: str, root: Path, auto_yes: bool, max_steps: int):
        """
        Initialize a new chat session.
        
        Args:
            model: Claude model name
            root: Sandbox root directory
            auto_yes: Auto-approve changes if True
            max_steps: Max operations per turn
        """
        self.client = anthropic.Anthropic()
        self.model = model
        self.root = root
        self.auto_yes = auto_yes
        self.max_steps = max_steps
        self.messages = []
        self.file_memory = FileMemory()
        self.executor = ToolExecutor(root, auto_yes, dry_run=False, file_memory=self.file_memory)
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
        
        # Process with Claude
        operations_this_turn = 0
        
        while operations_this_turn < self.max_steps:
            try:
                # Get Claude's response
                resp = self.client.messages.create(
                    model=self.model,
                    system=self.get_system_prompt(),
                    tools=get_tool_specs(self.root),
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
        self.trim_history()
        
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
            print(f"""
📊 Session Statistics:
  Messages: {len(self.messages)}
  Operations: {self.total_operations}
  Files in memory: {len(self.file_memory.files)}
  Root: {self.root}
""")
        else:
            print(f"\n❓ Unknown command: {command}")
            print("Type /help for available commands")
            
        return True
        
    def trim_history(self):
        """
        Trim conversation history if it gets too long.
        
        This prevents the conversation from exceeding Claude's context window.
        Keeps the most recent messages and discards older ones.
        """
        # Estimate total size
        total_chars = sum(len(str(msg)) for msg in self.messages)
        
        # If over 2/3 of limit, trim older messages
        if total_chars > MAX_CONTEXT_TOKENS * CHARS_PER_TOKEN * 2 / 3:
            # Keep system messages and recent messages
            keep_recent = 10
            if len(self.messages) > keep_recent:
                self.messages = self.messages[-keep_recent:]
                print("\n📋 (Trimmed older conversation history to stay within limits)")

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
╭─────────────────────────────────────────╮
│  🤖 Ronin - Interactive Mode             │
│                                         │
│  Type /help for commands                │
│  Type exit or /exit to quit             │
│                                         │
│  Ready to help with your text files!   │
╰─────────────────────────────────────────╯
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