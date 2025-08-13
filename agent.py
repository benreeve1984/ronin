# Simplified Ronin agent using minimal, powerful tools
import difflib, anthropic
from pathlib import Path
from tools import (
    ALLOWED_EXTS, validate_path, list_files,
    read_file, create_file, delete_file, modify_file, search_files
)

SYSTEM_PROMPT = """You are Ronin, a text-editing agent specializing in .md and .txt files.

IMPORTANT: You can make multiple tool calls to complete complex tasks. Keep working until the user's request is fully satisfied. You don't need to ask for permission to continue - just keep going until done.

Your tools use an ANCHOR-BASED MODIFICATION system:
- To append: modify_file with empty anchor and action="after"
- To prepend: modify_file with empty anchor and action="before"  
- To replace entire file: modify_file with empty anchor and action="replace"
- To insert after text: modify_file with anchor="text" and action="after"
- To delete text: modify_file with anchor="text" and action="replace" and empty content
- To replace all: modify_file with occurrence=0

Guidelines:
1. Always read files before modifying to understand current state
2. Use precise anchors - match exact text including punctuation
3. For multiple changes to the same file, do them in sequence
4. Verify your changes by reading the file again if needed
5. Complete the entire task - don't stop halfway
"""

def tool_specs(root: Path):
    """Define available tools for Claude AI with detailed usage instructions."""
    base = f"Root: {root}"
    return [
        {
            "name": "list_files",
            "description": (
                f"List .md/.txt files with sizes and line counts. Shows how big files are "
                f"so you can decide how much to read. Use patterns like '*.md' or 'docs/*.txt'. {base}"
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string", 
                        "default": "*",
                        "description": "Glob pattern (e.g. '*.md', 'docs/*', '**/*.txt')"
                    },
                },
            }
        },
        {
            "name": "read_file",
            "description": (
                f"Read a text file's contents or specific lines. Can read entire file or "
                f"just lines X to Y. Always check file size with list_files first for large files. {base}"
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to file (e.g. 'README.md', 'docs/guide.txt')"
                    },
                    "start_line": {
                        "type": "number",
                        "default": 1,
                        "description": "Line to start from (1-indexed). Default: 1 (beginning)"
                    },
                    "end_line": {
                        "type": "number",
                        "description": "Line to end at (inclusive). Default: end of file"
                    }
                },
                "required": ["path"]
            }
        },
        {
            "name": "create_file",
            "description": (
                f"Create a new .md/.txt file. Fails if file already exists. "
                f"Creates parent directories automatically. Returns size and line count. {base}"
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path for new file (e.g. 'notes.md', 'docs/new.txt')"
                    },
                    "content": {
                        "type": "string",
                        "description": "Initial content for the file"
                    }
                },
                "required": ["path", "content"]
            }
        },
        {
            "name": "delete_file",
            "description": (
                f"Delete a file permanently. User will be asked to confirm. "
                f"Returns deleted file info. {base}"
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to file to delete"
                    }
                },
                "required": ["path"]
            }
        },
        {
            "name": "modify_file",
            "description": (
                f"Modify file using anchor-based operations. This is the main editing tool. "
                f"Find an anchor text (or use empty for file boundaries) and perform an action. "
                f"Examples: append (empty anchor, after), prepend (empty anchor, before), "
                f"replace all (empty anchor, replace), insert after text (anchor='text', after), "
                f"delete text (anchor='text', replace with empty), replace all occurrences (occurrence=0). "
                f"Returns detailed change info. {base}"
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to file to modify"
                    },
                    "anchor": {
                        "type": "string", 
                        "default": "",
                        "description": "Text to find. Empty means file boundaries (start/end)"
                    },
                    "action": {
                        "type": "string", 
                        "enum": ["before", "after", "replace"],
                        "description": "What to do at anchor: before (insert before), after (insert after), replace"
                    },
                    "content": {
                        "type": "string", 
                        "default": "",
                        "description": "New content to insert/replace. Empty for deletion"
                    },
                    "occurrence": {
                        "type": "number", 
                        "default": 1,
                        "description": "Which match: 1=first, -1=last, 0=all occurrences"
                    }
                },
                "required": ["path", "action"]
            }
        },
        {
            "name": "search_files",
            "description": (
                f"Search for text across all files, like Ctrl+F but for multiple files. "
                f"Case-insensitive by default for human-friendly searching. "
                f"Shows context around matches to understand usage. "
                f"Returns line numbers and file paths. {base}"
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Text to search for (required)"
                    },
                    "pattern": {
                        "type": "string",
                        "default": "*",
                        "description": "Which files to search (e.g. '*.md', 'docs/*'). Default: all files"
                    },
                    "case_sensitive": {
                        "type": "boolean",
                        "default": False,
                        "description": "Make search case-sensitive. Default: False (case-insensitive)"
                    },
                    "context_lines": {
                        "type": "number",
                        "default": 2,
                        "description": "Lines to show before/after each match (0=just the match). Default: 2"
                    }
                },
                "required": ["text"]
            }
        }
    ]

def show_diff(old: str, new: str, path: Path) -> str:
    """Generate unified diff for file changes."""
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    diff = difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"{path} (before)",
        tofile=f"{path} (after)",
        lineterm=""
    )
    return "".join(diff)

def run_once(prompt: str, model: str, root: Path, auto_yes: bool, dry_run: bool, max_steps: int) -> bool:
    """Process a user request with Claude AI, allowing multiple operations until complete."""
    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": prompt}]
    total_operations = 0
    
    while total_operations < max_steps:
        # Get Claude's response
        resp = client.messages.create(
            model=model,
            system=SYSTEM_PROMPT,
            tools=tool_specs(root),
            messages=messages,
            max_tokens=2000,  # Increased for complex operations
        )

        # Print any explanatory text
        for block in resp.content:
            if getattr(block, "type", None) == "text":
                text = block.text.strip()
                if text:  # Only print non-empty text
                    print(f"\n🤖 {text}")

        # Extract tool requests
        tool_uses = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]
        if not tool_uses:
            # No more tools requested - task complete
            return True

        # Process each tool request
        results = []
        for tu in tool_uses:
            name = tu.name
            args = dict(tu.input or {})
            total_operations += 1
            
            print(f"\n🔧 Executing: {name}", end="")
            if name == "search_files":
                text = args.get("text", "?")
                print(f" (searching for: '{text[:30]}...')" if len(text) > 30 else f" (searching for: '{text}')")
            elif name == "modify_file":
                action = args.get("action", "?")
                anchor = args.get("anchor", "")
                if anchor:
                    print(f" ({action} anchor: '{anchor[:30]}...')" if len(anchor) > 30 else f" ({action} anchor: '{anchor}')")
                else:
                    print(f" ({action} file boundaries)")
            elif name in ("read_file", "create_file", "delete_file"):
                print(f" ({args.get('path', '?')})")
            else:
                print()
            
            try:
                if name == "list_files":
                    pattern = args.get("pattern", "*")
                    result = list_files(root, pattern)
                    
                    # Format result for clarity
                    if "error" in result:
                        output = f"Error: {result['error']}"
                    elif result.get("files"):
                        output = f"Found {result['count']} files matching '{pattern}':\n"
                        for f in result['files'][:20]:
                            output += f"  - {f['path']} ({f['lines']} lines, {f['size_display']})\n"
                        if result['count'] > 20:
                            output += f"  ... and {result['count'] - 20} more"
                    else:
                        output = f"No files found matching '{pattern}'"
                    
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": output
                    })

                elif name == "read_file":
                    p = validate_path(root, args["path"])
                    start_line = int(args.get("start_line", 1))
                    end_line = int(args.get("end_line")) if args.get("end_line") else None
                    
                    content = read_file(p, start_line, end_line)
                    
                    # Add helpful context for full reads
                    if start_line == 1 and end_line is None:
                        lines = content.count('\n') + 1
                        output = f"File: {p} ({lines} lines, {len(content)} bytes)\n\n{content}"
                    else:
                        output = f"File: {p}\n{content}"
                    
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": output
                    })

                elif name == "create_file":
                    p = validate_path(root, args["path"])
                    content = args["content"]
                    
                    if dry_run:
                        print(f"  → [DRY RUN] Would create: {p}")
                        results.append({
                            "type": "tool_result",
                            "tool_use_id": tu.id,
                            "content": f"[DRY RUN] Would create {p} with {len(content)} bytes"
                        })
                    else:
                        if not auto_yes:
                            print(f"\n📝 Create new file: {p}")
                            print(f"   Content preview: {content[:100]}..." if len(content) > 100 else f"   Content: {content}")
                            if input("   Create? [y/N]: ").lower() not in ("y", "yes"):
                                results.append({
                                    "type": "tool_result",
                                    "tool_use_id": tu.id,
                                    "content": "User declined file creation",
                                    "is_error": True
                                })
                                continue
                        
                        info = create_file(p, content)
                        print(f"  ✓ Created: {info['created']} ({info['lines']} lines)")
                        results.append({
                            "type": "tool_result",
                            "tool_use_id": tu.id,
                            "content": f"Created {info['created']} ({info['lines']} lines, {info['size']} bytes)"
                        })

                elif name == "delete_file":
                    p = validate_path(root, args["path"])
                    
                    if dry_run:
                        print(f"  → [DRY RUN] Would delete: {p}")
                        results.append({
                            "type": "tool_result",
                            "tool_use_id": tu.id,
                            "content": f"[DRY RUN] Would delete {p}"
                        })
                    else:
                        if not auto_yes:
                            if input(f"\n🗑️  DELETE {p}? [y/N]: ").lower() not in ("y", "yes"):
                                results.append({
                                    "type": "tool_result",
                                    "tool_use_id": tu.id,
                                    "content": "User declined deletion",
                                    "is_error": True
                                })
                                continue
                        
                        info = delete_file(p)
                        print(f"  ✓ Deleted: {info['deleted']}")
                        results.append({
                            "type": "tool_result",
                            "tool_use_id": tu.id,
                            "content": f"Deleted {info['deleted']} ({info['size']} bytes)"
                        })

                elif name == "search_files":
                    text = args["text"]
                    pattern = args.get("pattern", "*")
                    case_sensitive = args.get("case_sensitive", False)
                    context_lines = int(args.get("context_lines", 2))
                    
                    result = search_files(root, text, pattern, case_sensitive, context_lines)
                    
                    # Format human-readable output
                    if result["total_matches"] == 0:
                        output = f"No matches found for '{text}'"
                    else:
                        output = f"Found '{text}' {result['total_matches']} times in {result['files_with_matches']} files:\n\n"
                        
                        for file_result in result["matches"]:
                            output += f"{file_result['file']}:\n"
                            for match in file_result["matches"]:
                                # Show context
                                if context_lines > 0 and "before" in match:
                                    for i, line in enumerate(match["before"], match["line_number"] - len(match["before"])):
                                        output += f"  {i:4}: {line}\n"
                                
                                # Highlight the matching line
                                output += f"→ {match['line_number']:4}: {match['line']}\n"
                                
                                if context_lines > 0 and "after" in match:
                                    for i, line in enumerate(match["after"], match["line_number"] + 1):
                                        output += f"  {i:4}: {line}\n"
                                
                                if match.get("truncated"):
                                    output += "  ... (more matches truncated)\n"
                                output += "\n"
                    
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": output
                    })

                elif name == "modify_file":
                    p = validate_path(root, args["path"])
                    anchor = args.get("anchor", "")
                    action = args["action"]
                    content = args.get("content", "")
                    occurrence = int(args.get("occurrence", 1))
                    
                    # Get the changes
                    old, new, info = modify_file(p, anchor, action, content, occurrence)
                    
                    # Show diff
                    diff = show_diff(old, new, p)
                    if diff.strip():
                        print(f"\n--- Changes to: {p} ---")
                        # Limit diff display for very large changes
                        diff_lines = diff.split('\n')
                        if len(diff_lines) > 50:
                            print('\n'.join(diff_lines[:25]))
                            print(f"\n... [{len(diff_lines) - 50} lines omitted] ...\n")
                            print('\n'.join(diff_lines[-25:]))
                        else:
                            print(diff)
                    
                    if dry_run:
                        print(f"  → [DRY RUN] Would modify {p}")
                        results.append({
                            "type": "tool_result",
                            "tool_use_id": tu.id,
                            "content": f"[DRY RUN] Would modify {p}: {info}"
                        })
                    else:
                        if not auto_yes and diff.strip():
                            if input(f"Apply changes? [y/N]: ").lower() not in ("y", "yes"):
                                # Revert the change
                                p.write_text(old, encoding="utf-8")
                                results.append({
                                    "type": "tool_result",
                                    "tool_use_id": tu.id,
                                    "content": "User declined changes",
                                    "is_error": True
                                })
                                continue
                        
                        # Format detailed feedback
                        feedback = (
                            f"Modified {p}:\n"
                            f"  - Action: {info['action']} {info['anchor']}\n"
                            f"  - Changes: {info.get('modified_occurrences', info.get('position', 'unknown'))}\n"
                            f"  - Size: {info['old_size']} → {info['new_size']} bytes ({info['size_change']:+d})\n"
                            f"  - Lines: {info['old_lines']} → {info['new_lines']} ({info['line_change']:+d})"
                        )
                        
                        print(f"  ✓ Modified: {p} ({info['size_change']:+d} bytes, {info['line_change']:+d} lines)")
                        results.append({
                            "type": "tool_result",
                            "tool_use_id": tu.id,
                            "content": feedback
                        })

                else:
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": f"Unknown tool: {name}",
                        "is_error": True
                    })

            except Exception as e:
                print(f"  ❌ Error: {e}")
                results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": f"Error: {e}",
                    "is_error": True
                })

        # Continue conversation
        messages.append({"role": "assistant", "content": resp.content})
        messages.append({"role": "user", "content": results})

    print(f"\n⚠️  Reached maximum operations limit ({max_steps})")
    return True