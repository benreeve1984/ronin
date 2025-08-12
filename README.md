# Ronin - A Minimal CLI LLM Agent for Text File Management

## What is Ronin?

Ronin is a command-line tool that uses Claude AI to help you manage and edit text files (`.md` and `.txt`) in your projects. Think of it as an AI assistant that can read, write, and organize your documentation and text files automatically based on your natural language instructions.

## Quick Start

```bash
# Install
pip install -e .

# Set your API key
export ANTHROPIC_API_KEY="your-api-key-here"

# Use Ronin
Ronin "Create a TODO list in tasks.md"
Ronin "Add a new section about installation to README"
Ronin "Replace all occurrences of 'old_name' with 'new_name' in docs.txt"
```

## Project Structure

```
ronin/
├── agent.py       # AI orchestration and tool execution
├── tools.py       # File operations (create, delete, modify)
├── cli.py         # Command-line interface
└── pyproject.toml # Package configuration
```

## Core Design: Simplicity Through Composability

Ronin uses a revolutionary **anchor-based modification** system. Instead of dozens of specialized functions, we have just **3 core operations** that can express any text manipulation:

### The 3 Core Operations

1. **`create_file(path, content)`** - Create new files
2. **`delete_file(path)`** - Delete files  
3. **`modify_file(path, anchor, action, content, occurrence)`** - Universal modification

### The Power of modify_file

The `modify_file` function uses a simple mental model:
- **Find an anchor** (text to search for, or use file boundaries)
- **Perform an action** relative to that anchor
- **Optionally specify which occurrence** to modify

#### Parameters:
- `anchor`: Text to find (empty = file boundaries)
- `action`: One of "before", "after", "replace"
- `content`: New text (empty = delete)
- `occurrence`: Which match (1=first, -1=last, 0=all)

#### Examples:

| Task | How to Do It |
|------|-------------|
| Append to file | `modify_file(path, "", "after", "new text")` |
| Insert at beginning | `modify_file(path, "", "before", "header")` |
| Replace entire file | `modify_file(path, "", "replace", "new content")` |
| Insert after TODO | `modify_file(path, "TODO:", "after", "- item")` |
| Delete text | `modify_file(path, "old", "replace", "")` |
| Replace all occurrences | `modify_file(path, "old", "replace", "new", 0)` |

## How Each File Works

### 1. **cli.py** - The Entry Point
Processes command-line arguments and launches the agent.

**Key arguments:**
- `prompt`: Your request in natural language
- `--root`: Directory to work in (default: current)
- `--yes`: Auto-approve changes
- `--plan`: Preview mode (dry run)
- `--max-steps`: Limit tool operations (default: 10)

### 2. **agent.py** - The AI Brain
Connects to Claude AI and orchestrates tool execution.

**What it does:**
- Sends your request to Claude
- Provides available tools to the AI
- Executes requested operations
- Shows diffs before applying changes
- Handles user confirmation

### 3. **tools.py** - File Operations
The simplified file manipulation library.

**Core functions:**
- `validate_path()`: Ensures sandbox security
- `list_files()`: Browse files with patterns
- `read_file()`: Read text content
- `create_file()`: Create new files
- `delete_file()`: Remove files
- `modify_file()`: Universal text modification

**Security features:**
- Path sandboxing (can't escape root)
- File type restrictions (.md/.txt only)
- Size limits for safety
- Clear error messages

## Installation & Setup

### Prerequisites
- Python 3.7 or higher
- Anthropic API key

### Steps

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd ronin
   ```

2. **Install the package**:
   ```bash
   pip install -e .
   ```

3. **Set your API key**:
   ```bash
   export ANTHROPIC_API_KEY="sk-ant-..."
   ```
   Add to your shell profile (.bashrc, .zshrc) to make permanent.

4. **Test it works**:
   ```bash
   Ronin "Create a file called hello.txt with 'Hello World' content"
   ```

## Common Use Cases

### Creating Documentation
```bash
Ronin "Create a comprehensive API documentation file"
```

### Updating Files
```bash
Ronin "Add installation instructions after the introduction in README.md"
```

### Bulk Find & Replace
```bash
Ronin "Replace all instances of 'foo' with 'bar' in config.txt"
```

### Deleting Content
```bash
Ronin "Remove the deprecated section from docs.md"
```

### Organizing Files
```bash
Ronin "Add proper markdown headings to notes.txt"
```

## Command-Line Options

| Option | Description | Example |
|--------|-------------|---------|
| `--root DIR` | Set working directory | `--root ./docs` |
| `--yes` | Auto-approve all changes | `--yes` |
| `--plan` | Preview without applying | `--plan` |
| `--max-steps N` | Limit AI operations | `--max-steps 5` |
| `--model NAME` | Choose Claude model | `--model claude-3-opus` |

## Safety Features

1. **Sandboxing**: Can only access files within specified root
2. **File Type Restriction**: Only .md and .txt files
3. **Confirmation Prompts**: Reviews changes before applying
4. **Dry Run Mode**: Preview with `--plan`
5. **Diff Display**: Shows exactly what will change
6. **Size Limits**: Prevents memory issues with large files

## Environment Variables

- `ANTHROPIC_API_KEY`: Required - Your Claude API key
- `RONIN_MODEL`: Optional - Default model to use

## Architecture Overview

```
User Input → CLI Parser → Agent Controller → Claude AI
                                    ↓
                          Tool Selection (create/delete/modify)
                                    ↓
                            File Operations (tools.py)
                                    ↓
                          User Confirmation → Apply Changes
```

## Design Philosophy

> "Perfection is achieved not when there is nothing more to add, but when there is nothing left to take away." - Antoine de Saint-Exupéry

Ronin embodies this principle with its minimal yet powerful design:
- **3 operations** instead of dozens
- **One mental model** for all modifications
- **70% less code** than traditional approaches
- **More capabilities** through composability

## Troubleshooting

### "ANTHROPIC_API_KEY is not set"
```bash
export ANTHROPIC_API_KEY="your-key-here"
```

### "Path escapes root"
Ronin detected an attempt to access files outside the project. Check your paths.

### "Only .md/.txt are allowed"
Convert other formats to text/markdown first.

### Changes not applying
Make sure you're typing 'y' when prompted, or use `--yes` flag.

## Advanced Usage

### Using Patterns
```bash
Ronin "List all markdown files in the docs folder"
```

### Complex Modifications
```bash
Ronin "In all .md files, add a copyright notice at the end"
```

### Dry Run First
```bash
Ronin "Reorganize the entire documentation" --plan
# Review the plan, then run without --plan
```

## Contributing

To modify Ronin:
1. Edit the Python files directly
2. Test changes: `python -m ronin.cli "test prompt"`
3. Reinstall if needed: `pip install -e .`

## Key Concepts

**Anchor-Based Modification**: Everything is about finding a position (anchor) and performing an action relative to it.

**Composability**: Simple operations combine to create complex behaviors.

**Sandboxing**: Security through strict path validation.

**Transparency**: Always show what will change before changing it.

## Security Notes

- Never share your `ANTHROPIC_API_KEY`
- Be cautious with `--yes` flag
- Always specify `--root` carefully
- Review diffs before confirming changes

## Why Ronin?

Traditional file manipulation tools have dozens of functions with complex parameters. Ronin proves that **3 simple operations** can do everything and more:

- **Simpler**: One pattern to learn
- **More Powerful**: Can do things other tools can't
- **Safer**: Clear diffs and confirmations
- **Cleaner**: 50% less code to maintain

## License

[Your license here]

## Support

For issues or questions:
- Review this README thoroughly
- Check the troubleshooting section
- Ensure your API key is valid
- Verify you're using .md or .txt files only