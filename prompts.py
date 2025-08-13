# Prompts for Ronin AI Agent
# ===========================
# All prompts used by Ronin are defined here with variables.
# This makes it easy to:
# 1. Modify prompts without digging through code
# 2. Test different prompt strategies
# 3. Migrate to prompt management tools like Langfuse
# 4. Keep prompts consistent across the codebase

# System prompt for the main agent
# Variables: None (static prompt)
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

# Additional prompt for interactive mode
# Variables: None (appended to SYSTEM_PROMPT)
INTERACTIVE_MODE_SUFFIX = """

You are in INTERACTIVE MODE. The user can have multiple exchanges with you.
Remember what was discussed and what files were created/modified earlier in the conversation.
"""

# Prompt template for file context
# Variables: {file_context} - the actual file contents
FILE_CONTEXT_TEMPLATE = """
=== FILES IN CONTEXT ===
{file_context}
"""

# Prompt for when approaching context limits
# Variables: {used_tokens}, {max_tokens}, {percentage}
CONTEXT_WARNING_TEMPLATE = """
⚠️ Context Usage: {used_tokens}/{max_tokens} tokens ({percentage}% full)
Consider being more selective about what files to read fully.
"""

# Prompt for tool execution feedback
# Variables: {tool_name}, {result}
TOOL_SUCCESS_TEMPLATE = """
✓ {tool_name} completed successfully:
{result}
"""

# Prompt for tool execution errors
# Variables: {tool_name}, {error}
TOOL_ERROR_TEMPLATE = """
❌ {tool_name} failed:
{error}

Please try a different approach or ask the user for clarification.
"""

# Prompt for requesting user confirmation
# Variables: {action}, {details}
CONFIRMATION_PROMPT_TEMPLATE = """
{action}
{details}

Proceed? [y/N]: """

# Specific confirmation prompts for different actions
CREATE_FILE_CONFIRMATION = """
📝 Create new file: {path}
   Content preview: {preview}"""

DELETE_FILE_CONFIRMATION = """
🗑️  DELETE {path}?"""

MODIFY_FILE_CONFIRMATION = """
Apply changes to {path}?"""

# Prompt for suggesting next actions
# Variables: {completed_action}, {suggestions}
NEXT_ACTION_TEMPLATE = """
{completed_action}

Suggested next steps:
{suggestions}
"""

# Prompt for handling ambiguous requests
# Variables: {request}, {options}
CLARIFICATION_TEMPLATE = """
Your request "{request}" could mean several things:

{options}

Which would you like me to do?
"""

# Prompt for summarizing changes made
# Variables: {changes_list}
CHANGES_SUMMARY_TEMPLATE = """
📋 Summary of changes made:
{changes_list}
"""

# Error recovery prompts
RETRY_PROMPT = """
The previous attempt failed. Let me try a different approach...
"""

PERMISSION_DENIED_PROMPT = """
I don't have permission to access that file/directory. 
Please check the path and permissions.
"""

FILE_NOT_FOUND_PROMPT = """
I couldn't find the file: {path}
Would you like me to:
1. Create it as a new file
2. Search for similar filenames
3. List available files
"""

# Learning/Help prompts
HELP_PROMPT = """
I can help you with:
- Creating new text files (.md, .txt)
- Reading and searching through files
- Modifying existing files (insert, delete, replace text)
- Organizing and listing your files

Just tell me what you'd like to do in plain English!
"""

def format_prompt(template: str, **kwargs) -> str:
    """
    Format a prompt template with variables.
    
    Args:
        template: The prompt template string
        **kwargs: Variables to substitute into the template
        
    Returns:
        Formatted prompt string
        
    Example:
        >>> format_prompt(TOOL_SUCCESS_TEMPLATE, tool_name="read_file", result="Contents...")
        "✓ read_file completed successfully:\nContents..."
    """
    return template.format(**kwargs)

def get_system_prompt(interactive: bool = False, file_context: str = "") -> str:
    """
    Build the complete system prompt with optional additions.
    
    Args:
        interactive: Whether to add interactive mode instructions
        file_context: File contents to include in context
        
    Returns:
        Complete system prompt
    """
    prompt = SYSTEM_PROMPT
    
    if interactive:
        prompt += INTERACTIVE_MODE_SUFFIX
    
    if file_context:
        prompt += format_prompt(FILE_CONTEXT_TEMPLATE, file_context=file_context)
    
    return prompt

def get_confirmation_prompt(action_type: str, **details) -> str:
    """
    Get the appropriate confirmation prompt for an action.
    
    Args:
        action_type: Type of action ("create", "delete", "modify")
        **details: Action-specific details
        
    Returns:
        Formatted confirmation prompt
    """
    if action_type == "create":
        action = format_prompt(CREATE_FILE_CONFIRMATION, **details)
    elif action_type == "delete":
        action = format_prompt(DELETE_FILE_CONFIRMATION, **details)
    elif action_type == "modify":
        action = format_prompt(MODIFY_FILE_CONFIRMATION, **details)
    else:
        action = f"Perform {action_type}"
    
    return format_prompt(CONFIRMATION_PROMPT_TEMPLATE, 
                        action=action, 
                        details=details.get("extra_details", ""))