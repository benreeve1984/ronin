# Simplified Ronin agent using minimal, powerful tools
import json, difflib, anthropic
from pathlib import Path
from .tools import (
    ALLOWED_EXTS, validate_path, list_files,
    read_file, create_file, delete_file, modify_file,
    # Legacy compatibility imports
    validate_and_resolve, list_dir_entries, read_text_file, write_text_file
)

SYSTEM_PROMPT = """You are Ronin, a text-editing agent.
Work ONLY with .md and .txt files within the project root.
Always read files before modifying. Keep changes minimal and precise.

Guidelines:
- Prefer structured Markdown with proper headings
- Read before editing to avoid duplication
- Use precise anchors for modifications
- Stay within the project root sandbox
"""

def tool_specs(root: Path):
    """Define available tools for Claude AI."""
    base = f"Root: {root}"
    return [
        {
            "name": "list_files",
            "description": f"List .md/.txt files. {base}",
            "input_schema": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "default": "*"},
                },
            }
        },
        {
            "name": "read_file",
            "description": f"Read a text file. {base}",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"}
                },
                "required": ["path"]
            }
        },
        {
            "name": "create_file",
            "description": f"Create new .md/.txt file. {base}",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"}
                },
                "required": ["path", "content"]
            }
        },
        {
            "name": "delete_file",
            "description": f"Delete a file (with confirmation). {base}",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"}
                },
                "required": ["path"]
            }
        },
        {
            "name": "modify_file",
            "description": (
                "Modify file using anchor-based operations. "
                "anchor: text to find (empty=file boundaries), "
                "action: 'before'/'after'/'replace', "
                "content: new text (empty=delete), "
                "occurrence: which match (1=first, -1=last, 0=all)"
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "anchor": {"type": "string", "default": ""},
                    "action": {"type": "string", "enum": ["before", "after", "replace"]},
                    "content": {"type": "string", "default": ""},
                    "occurrence": {"type": "number", "default": 1}
                },
                "required": ["path", "action"]
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
    """Process a single user request with Claude AI."""
    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": prompt}]
    steps = 0

    while True:
        # Get Claude's response
        resp = client.messages.create(
            model=model,
            system=SYSTEM_PROMPT,
            tools=tool_specs(root),
            messages=messages,
            max_tokens=1200,
        )

        # Print any explanatory text
        for block in resp.content:
            if getattr(block, "type", None) == "text":
                print(block.text.strip())

        # Extract tool requests
        tool_uses = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]
        if not tool_uses:
            return True  # Done

        # Process each tool request
        results = []
        for tu in tool_uses:
            name = tu.name
            args = dict(tu.input or {})
            
            try:
                if name == "list_files":
                    pattern = args.get("pattern", "*")
                    result = list_files(root, pattern)
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": json.dumps(result)
                    })

                elif name == "read_file":
                    p = validate_path(root, args["path"])
                    content = read_file(p)
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": content
                    })

                elif name == "create_file":
                    p = validate_path(root, args["path"])
                    content = args["content"]
                    
                    if dry_run:
                        print(f"\n[DRY RUN] Would create: {p}")
                        print(f"Content preview: {content[:200]}...")
                        results.append({
                            "type": "tool_result",
                            "tool_use_id": tu.id,
                            "content": f"[DRY RUN] Would create {p}"
                        })
                    else:
                        if not auto_yes:
                            print(f"\nCreate new file: {p}")
                            print(f"Content preview: {content[:200]}...")
                            if input("Create? [y/N]: ").lower() not in ("y", "yes"):
                                results.append({
                                    "type": "tool_result",
                                    "tool_use_id": tu.id,
                                    "content": "User declined",
                                    "is_error": True
                                })
                                continue
                        
                        create_file(p, content)
                        results.append({
                            "type": "tool_result",
                            "tool_use_id": tu.id,
                            "content": f"Created {p}"
                        })

                elif name == "delete_file":
                    p = validate_path(root, args["path"])
                    
                    if dry_run:
                        results.append({
                            "type": "tool_result",
                            "tool_use_id": tu.id,
                            "content": f"[DRY RUN] Would delete {p}"
                        })
                    else:
                        # Always confirm deletions unless auto_yes
                        if not auto_yes:
                            if input(f"DELETE {p}? [y/N]: ").lower() not in ("y", "yes"):
                                results.append({
                                    "type": "tool_result",
                                    "tool_use_id": tu.id,
                                    "content": "User declined deletion",
                                    "is_error": True
                                })
                                continue
                        
                        delete_file(p)
                        results.append({
                            "type": "tool_result",
                            "tool_use_id": tu.id,
                            "content": f"Deleted {p}"
                        })

                elif name == "modify_file":
                    p = validate_path(root, args["path"])
                    anchor = args.get("anchor", "")
                    action = args["action"]
                    content = args.get("content", "")
                    occurrence = int(args.get("occurrence", 1))
                    
                    # Get the changes
                    old, new = modify_file(p, anchor, action, content, occurrence)
                    
                    # Show diff
                    diff = show_diff(old, new, p)
                    print(f"\n--- Proposed changes to: {p} ---")
                    print(diff if diff.strip() else "[No changes]")
                    
                    if dry_run:
                        results.append({
                            "type": "tool_result",
                            "tool_use_id": tu.id,
                            "content": f"[DRY RUN] Would modify {p}"
                        })
                    else:
                        if not auto_yes:
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
                        
                        results.append({
                            "type": "tool_result",
                            "tool_use_id": tu.id,
                            "content": f"Modified {p}"
                        })

                # Legacy tool support for backwards compatibility
                elif name == "list_dir":
                    path = args.get("path", ".")
                    glob = args.get("glob")
                    pattern = glob if glob else "*"
                    result = list_files(root, pattern)
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": json.dumps(result)
                    })

                elif name == "write_file":
                    p = validate_and_resolve(root, args["path"])
                    content = str(args["content"])
                    overwrite = bool(args.get("overwrite", False))
                    
                    if p.exists() and not overwrite:
                        results.append({
                            "type": "tool_result",
                            "tool_use_id": tu.id,
                            "content": f"File exists: {p}. Set overwrite=true to replace.",
                            "is_error": True
                        })
                    else:
                        if p.exists():
                            old, new = modify_file(p, "", "replace", content)
                            diff = show_diff(old, new, p)
                            print(f"\n--- Proposed overwrite: {p} ---")
                            print(diff if diff.strip() else "[no changes]")
                        else:
                            print(f"\n--- Creating new file: {p} ---")
                            print(f"Content preview: {content[:200]}...")
                        
                        if dry_run:
                            results.append({
                                "type": "tool_result",
                                "tool_use_id": tu.id,
                                "content": f"[DRY RUN] Would write {p}"
                            })
                        else:
                            if not auto_yes:
                                if input(f"Apply? [y/N]: ").lower() not in ("y", "yes"):
                                    results.append({
                                        "type": "tool_result",
                                        "tool_use_id": tu.id,
                                        "content": "User declined",
                                        "is_error": True
                                    })
                                    continue
                            
                            if not p.exists():
                                create_file(p, content)
                            else:
                                modify_file(p, "", "replace", content)
                            
                            results.append({
                                "type": "tool_result",
                                "tool_use_id": tu.id,
                                "content": f"Wrote {p}"
                            })

                elif name == "insert_text":
                    p = validate_and_resolve(root, args["path"])
                    content = str(args.get("content", ""))
                    
                    # Map old insert_text parameters to modify_file
                    line = args.get("line")
                    after = args.get("after")
                    before = args.get("before")
                    after_heading = args.get("after_heading")
                    before_heading = args.get("before_heading")
                    
                    # Determine anchor and action from old parameters
                    if line is not None:
                        # Line-based insertion not directly supported, append instead
                        anchor = ""
                        action = "after" if line > 1 else "before"
                    elif after is not None:
                        anchor = after
                        action = "after"
                    elif before is not None:
                        anchor = before
                        action = "before"
                    elif after_heading is not None:
                        anchor = f"# {after_heading}"  # Approximate heading
                        action = "after"
                    elif before_heading is not None:
                        anchor = f"# {before_heading}"  # Approximate heading
                        action = "before"
                    else:
                        anchor = ""
                        action = "after"
                    
                    old, new = modify_file(p, anchor, action, content)
                    diff = show_diff(old, new, p)
                    print(f"\n--- Proposed insert into: {p} ---")
                    print(diff if diff.strip() else "[no changes]")
                    
                    if dry_run:
                        results.append({
                            "type": "tool_result",
                            "tool_use_id": tu.id,
                            "content": f"[DRY RUN] Would insert into {p}"
                        })
                    else:
                        if not auto_yes:
                            if input(f"Apply? [y/N]: ").lower() not in ("y", "yes"):
                                p.write_text(old, encoding="utf-8")
                                results.append({
                                    "type": "tool_result",
                                    "tool_use_id": tu.id,
                                    "content": "User declined",
                                    "is_error": True
                                })
                                continue
                        
                        results.append({
                            "type": "tool_result",
                            "tool_use_id": tu.id,
                            "content": f"Inserted into {p}"
                        })

                else:
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": f"Unknown tool: {name}",
                        "is_error": True
                    })

            except Exception as e:
                results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": f"Error: {e}",
                    "is_error": True
                })

        # Continue conversation
        messages.append({"role": "assistant", "content": resp.content})
        messages.append({"role": "user", "content": results})

        steps += 1
        if steps >= max_steps:
            print("[Max steps reached]")
            return True