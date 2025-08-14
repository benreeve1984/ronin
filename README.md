# 🥷 Ronin

A minimal, powerful CLI agent that brings LLM capabilities directly to your command line. Built with Claude's API, Ronin executes file operations, automates system tasks, and manages your workflows through natural language commands.

> **What Ronin Does**: Ronin is your intelligent CLI agent that directly executes tasks in your terminal. It specializes in file management, text processing, search operations, and system automation. Currently focused on text files with plans to expand to more formats, tools, and integrations.

## ✨ Features

### What Ronin Does Today
- **Natural Language CLI** - Execute terminal tasks by describing them in plain English
- **Smart Context Management** - 140k token context window with intelligent file memory
- **Interactive Chat Mode** - Work through multi-step operations with persistent context
- **Safe Execution** - Sandboxed operations, confirmation prompts, and dry-run mode
- **Powerful File Search** - Fast, grep-like search across your entire filesystem
- **Precision File Editing** - Modify files using anchor text or line-based operations
- **Secure API Key Storage** - Store keys once, use everywhere

### Why Ronin?
- **Direct Execution** - Ronin performs operations directly in your terminal, no intermediate code generation
- **Extensible Architecture** - Built to easily add new CLI tools and system capabilities
- **Clean Abstractions** - Single source of truth for operations, standardized execution, unified error handling
- **Production Ready** - Structured logging, proper error recovery, secure secrets management
- **Rapid Integration** - New CLI tools can be added in minutes, not hours

## 🚀 Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/ronin.git
cd ronin

# Install in development mode
pip install -e .

# Now you can use the 'Ronin' command from anywhere!
```

### Setup

Store your Anthropic API key (one-time setup):

```bash
Ronin --set-key anthropic YOUR_API_KEY
```

Or set it as an environment variable:

```bash
export ANTHROPIC_API_KEY=your_api_key_here
```

### Basic Usage

```bash
# Execute file operations
Ronin "list all markdown files in docs/"
Ronin "find and show all TODO comments in my project"
Ronin "search for API endpoints in the config files"

# Automate multi-step tasks
Ronin "organize these log files by date"
Ronin "extract all email addresses from these documents"

# Interactive chat mode for complex workflows
Ronin

# Work in a specific directory
Ronin "update all version numbers to 2.0.0" --root ./my-project

# Preview operations before execution
Ronin "clean up duplicate files" --plan

# Require confirmation for destructive operations
Ronin "remove all .tmp files" --no-auto-yes
```

## 💬 Interactive Mode

Launch an interactive session for multi-step tasks and conversations:

```bash
Ronin
```

In interactive mode:
- Work through complex tasks step by step
- Files remain in context across messages
- Use `/help` for available commands
- Use `/clear` to reset context
- Use `/exit` to quit

## 🛠️ Available Operations

Ronin executes these CLI operations:
- **List Files** - Find and enumerate files by pattern or extension
- **Read Files** - Display file contents with optional line ranges
- **Create Files** - Generate new files with specified content
- **Delete Files** - Remove files with safety checks
- **Modify Files** - Edit files using anchor text or line positions
- **Search Files** - Grep-like search across your filesystem with context

*Note: Ronin automatically ignores common directories like `.venv`, `node_modules`, `__pycache__`, `.git`, etc. when listing or searching files.*

## 🔧 Configuration

### Command Line Options

- `--root PATH` - Set the working directory (sandbox boundary)
- `--no-auto-yes` - Require confirmation for each change
- `--plan` - Dry-run mode to preview without making changes
- `--max-steps N` - Limit the number of operations (default: 10)
- `--model MODEL` - Choose Claude model (default: claude-3-5-sonnet)
- `--no-tracing` - Disable LangSmith tracing for this session
- `--langsmith-project NAME` - Set project name for organizing traces

### Environment Variables

- `ANTHROPIC_API_KEY` - Your Anthropic API key
- `RONIN_MODEL` - Default model to use
- `RONIN_LOG_LEVEL` - Logging verbosity (DEBUG, INFO, WARNING, ERROR)
- `RONIN_LOG_TO_FILE` - Enable file logging (true/false)
- `LANGSMITH_API_KEY` - LangSmith API key for tracing
- `LANGSMITH_PROJECT` - Default project name for traces
- `RONIN_ENABLE_TRACING` - Set to "false" to disable tracing (default: true when API key exists)

### Secrets Management

```bash
# Store a key
Ronin --set-key anthropic sk-ant-...

# List stored keys
Ronin --list-keys

# Remove a key
Ronin --remove-key anthropic
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

1. **Direct Action** - Execute operations immediately in your terminal
2. **Minimal** - Simple, focused operations that do one thing well
3. **Composable** - Operations can be chained for complex workflows
4. **Safe** - Sandboxed execution with confirmation prompts
5. **Transparent** - Clear feedback about what's being executed
6. **Extensible** - Easy to add new CLI tools and system capabilities

## 🔐 Security

- **Sandboxed Execution** - Operations are restricted to the specified root directory
- **Confirmation Prompts** - Destructive operations require confirmation (unless using auto-yes)
- **Secure Key Storage** - API keys are encrypted with machine-specific keys
- **No Phone Home** - All operations are local, no telemetry

## 📊 Logging & Observability

### Local Logging
Ronin provides structured logging for debugging:

- Logs are stored in `~/.ronin/logs/`
- JSON format for easy parsing
- Configurable verbosity levels
- Trace IDs for tracking operations

### LangSmith Tracing
Ronin automatically enables LangSmith tracing when an API key is available. No configuration needed - it just works!

```bash
# Optional: Install LangSmith for enhanced tracing
pip install langsmith

# Store your LangSmith API key (one-time setup)
Ronin --set-key langsmith <your-api-key>

# That's it! Tracing is automatic and silent
Ronin "organize my project files"

# Organize traces by project
Ronin "fix the bug" --langsmith-project "bug-fixes"

# Disable tracing for a specific session if needed
Ronin "private task" --no-tracing
```

**No API key? No problem!** Ronin works perfectly without LangSmith - tracing is completely optional.

When a LangSmith API key is configured:
- Complete traces of all tool executions
- Claude API call monitoring
- Performance metrics and latency tracking
- Error tracking with recovery hints
- Visual debugging in the LangSmith UI

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
- 📋 Project-wide transformations
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

- Use `CLAUDE.md` files in your projects to give Ronin context about your work
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

*Ronin: Your intelligent CLI agent—executing tasks, not generating code* 🥷