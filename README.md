# 🥷 Ronin

A minimal, powerful CLI agent that brings LLM capabilities directly to your codebase. Built with Claude's API, Ronin helps you read, write, search, and modify files with natural language commands.

> **Current Status**: Ronin currently focuses on text files (markdown, code, config files, etc.) with a robust foundation for file operations. We're actively expanding to support more file formats, external tools, and integrations. The architecture is designed to make adding new capabilities straightforward.

## ✨ Features

### What Ronin Does Today
- **Natural Language File Operations** - Just describe what you want: "Add error handling to the login function" or "Find all TODO comments"
- **Smart Context Management** - 140k token context window with intelligent file memory
- **Interactive Chat Mode** - Have conversations about your code with persistent context
- **Safe by Default** - Sandboxed execution, confirmation prompts, and dry-run mode
- **Powerful Search** - Fast, grep-like search across your entire codebase
- **Anchor-Based Editing** - Precise text modifications using surrounding context
- **Secure API Key Storage** - Store keys once, use everywhere

### Why Ronin?
- **Extensible Architecture** - Built from the ground up to easily add new tools and capabilities
- **Clean Abstractions** - Single source of truth for tools, standardized execution, unified error handling
- **Production Ready Foundation** - Structured logging, proper error recovery, secure secrets management
- **Rapid Development** - New tools can be added in minutes, not hours

## 🚀 Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/ronin.git
cd ronin

# Install in development mode
pip install -e .
```

### Setup

Store your Anthropic API key (one-time setup):

```bash
python cli.py --set-key anthropic YOUR_API_KEY
```

Or set it as an environment variable:

```bash
export ANTHROPIC_API_KEY=your_api_key_here
```

### Basic Usage

```bash
# Single command mode
python cli.py "list all markdown files"
python cli.py "create a README with installation instructions"
python cli.py "find all functions that handle authentication"

# Interactive chat mode (just run without arguments)
python cli.py

# Work in a specific directory
python cli.py "update the config file" --root ./my-project

# Dry run to preview changes
python cli.py "refactor the database module" --plan

# Manual confirmation mode
python cli.py "delete all test files" --no-auto-yes
```

## 💬 Interactive Mode

Launch an interactive session to have a conversation about your code:

```bash
python cli.py
```

In interactive mode:
- Chat naturally about your codebase
- Files remain in context across messages
- Use `/help` for available commands
- Use `/clear` to reset context
- Use `/exit` to quit

## 🛠️ Available Tools

Ronin can:
- **List Files** - Find files by pattern or extension
- **Read Files** - Load file contents with optional line ranges
- **Create Files** - Generate new files with content
- **Delete Files** - Remove files safely
- **Modify Files** - Edit files using anchor text or line positions
- **Search Files** - Find text across your codebase with context

## 🔧 Configuration

### Command Line Options

- `--root PATH` - Set the working directory (sandbox boundary)
- `--no-auto-yes` - Require confirmation for each change
- `--plan` - Dry-run mode to preview without making changes
- `--max-steps N` - Limit the number of operations (default: 10)
- `--model MODEL` - Choose Claude model (default: claude-3-5-sonnet)

### Environment Variables

- `ANTHROPIC_API_KEY` - Your Anthropic API key
- `RONIN_MODEL` - Default model to use
- `RONIN_LOG_LEVEL` - Logging verbosity (DEBUG, INFO, WARNING, ERROR)
- `RONIN_LOG_TO_FILE` - Enable file logging (true/false)

### Secrets Management

```bash
# Store a key
python cli.py --set-key anthropic sk-ant-...

# List stored keys
python cli.py --list-keys

# Remove a key
python cli.py --remove-key anthropic
```

Keys are stored securely in `~/.ronin/secrets.enc` with machine-specific encryption.

## 📁 Project Structure

```
ronin/
├── cli.py              # CLI entry point and argument parsing
├── agent.py            # Core agent logic for single commands
├── chat_mode.py        # Interactive chat session handler
├── tools.py            # File operation implementations
├── tool_registry.py    # Tool definitions and specifications
├── tool_executor.py    # Unified tool execution handler
├── prompts.py          # System prompts and templates
├── exceptions.py       # Custom errors with recovery hints
├── logging_config.py   # Structured logging setup
└── secrets_manager.py  # Secure API key storage
```

## 🎯 Design Philosophy

Ronin follows these principles:

1. **Minimal** - Simple, focused tools that do one thing well
2. **Composable** - Tools can be combined for complex operations
3. **Safe** - Sandboxed execution with confirmation prompts
4. **Transparent** - Clear feedback about what's happening
5. **Extensible** - Easy to add new tools and capabilities

## 🔐 Security

- **Sandboxed Execution** - Operations are restricted to the specified root directory
- **Confirmation Prompts** - Destructive operations require confirmation (unless using auto-yes)
- **Secure Key Storage** - API keys are encrypted with machine-specific keys
- **No Phone Home** - All operations are local, no telemetry

## 📊 Logging

Ronin provides structured logging for debugging and monitoring:

- Logs are stored in `~/.ronin/logs/`
- JSON format for easy parsing
- Configurable verbosity levels
- Trace IDs for tracking operations

## 🚦 Roadmap

### Currently Supported
- ✅ Text files (`.md`, `.txt`, `.py`, `.js`, `.json`, `.yaml`, etc.)
- ✅ Natural language file operations
- ✅ Interactive chat mode
- ✅ Secure API key management
- ✅ Structured logging

### Coming Soon
- 🔄 Binary file support (images, PDFs, spreadsheets)
- 🔄 Git operations (commit, branch, merge)
- 🔄 Shell command execution
- 🔄 Web browsing and API calls
- 🔄 Database connections
- 🔄 Cloud service integrations

### Future Vision
- 📋 Project-wide refactoring
- 📋 Test generation and execution
- 📋 Documentation generation
- 📋 Multi-file transactions
- 📋 Plugin system for custom tools

## 🔌 Extending Ronin

Adding new tools is straightforward thanks to our modular architecture:

1. Define your tool in `tool_registry.py`
2. Implement the handler in `tools.py`
3. Tools automatically get standardized execution, logging, and error handling

Example:
```python
# In tool_registry.py
TOOLS["my_tool"] = ToolDefinition(
    name="my_tool",
    description="What this tool does",
    handler=my_tool_handler,
    parameters={...}
)
```

## 🤝 Contributing

Contributions are welcome! We're especially looking for:

- **New file format support** - Help us handle more file types
- **Tool integrations** - Connect Ronin to your favorite services
- **Bug fixes and improvements** - Make Ronin better for everyone

How to contribute:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📝 License

MIT License - see LICENSE file for details

## 🙏 Acknowledgments

Built with:
- [Anthropic's Claude API](https://www.anthropic.com/)
- Python's pathlib for robust file operations
- Rich logging and error handling

## 💡 Tips

- Use `CLAUDE.md` files in your projects to give Ronin context about your codebase
- The `--plan` flag is great for understanding what changes will be made
- In chat mode, Ronin remembers files you've discussed for better context
- Search supports regex patterns for advanced queries

## 🐛 Troubleshooting

### API Key Issues
- Ensure your API key is set correctly with `--set-key` or environment variable
- Check key validity with `--list-keys`

### Permission Errors
- Ronin respects file system permissions
- Ensure you have read/write access to the target directory

### Context Limits
- Large files may exceed context limits
- Use line ranges when reading large files: `"read lines 100-200 of big_file.py"`

## 📧 Support

For issues, questions, or suggestions:
- Open an issue on GitHub
- Check existing issues for solutions
- Include error messages and steps to reproduce

---

*Ronin: Your silent, efficient coding companion* 🥷