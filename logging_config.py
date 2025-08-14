# Logging Configuration for Ronin
# ================================
# Structured logging that's both human-readable and machine-parseable.
# Ready for export to observability tools like LangSmith/Langfuse.

import logging
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional
import uuid

# Create logs directory if it doesn't exist
LOGS_DIR = Path.home() / ".ronin" / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

class StructuredFormatter(logging.Formatter):
    """
    Custom formatter that outputs structured JSON logs.
    
    Each log entry includes:
    - Timestamp
    - Level (DEBUG, INFO, WARNING, ERROR)
    - Module and function name
    - Message
    - Additional context
    - Trace ID for tracking related operations
    """
    
    def format(self, record):
        # Build structured log entry
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
        }
        
        # Add any extra fields
        if hasattr(record, 'trace_id'):
            log_entry['trace_id'] = record.trace_id
        if hasattr(record, 'tool_name'):
            log_entry['tool_name'] = record.tool_name
        if hasattr(record, 'context'):
            log_entry['context'] = record.context
        if hasattr(record, 'error_type'):
            log_entry['error_type'] = record.error_type
        if hasattr(record, 'recovery_hints'):
            log_entry['recovery_hints'] = record.recovery_hints
            
        return json.dumps(log_entry)

class HumanReadableFormatter(logging.Formatter):
    """
    Formatter for console output that's easy for humans to read.
    Uses colors and emojis for different log levels.
    """
    
    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[35m', # Magenta
        'RESET': '\033[0m'      # Reset
    }
    
    EMOJIS = {
        'DEBUG': '🔍',
        'INFO': '✅',
        'WARNING': '⚠️',
        'ERROR': '❌',
        'CRITICAL': '🚨'
    }
    
    def format(self, record):
        # Get color and emoji for level
        color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        emoji = self.EMOJIS.get(record.levelname, '')
        reset = self.COLORS['RESET']
        
        # Format the message
        if hasattr(record, 'tool_name'):
            prefix = f"{emoji} [{record.tool_name}]"
        else:
            prefix = f"{emoji} [{record.module}.{record.funcName}]"
        
        message = f"{color}{prefix} {record.getMessage()}{reset}"
        
        # Add context if present
        if hasattr(record, 'context') and record.context:
            message += f"\n    Context: {record.context}"
        
        # Add recovery hints for errors
        if hasattr(record, 'recovery_hints') and record.recovery_hints:
            message += f"\n    💡 Hint: {record.recovery_hints}"
        
        return message

class ToolExecutionLogger:
    """
    Context manager for logging tool execution with timing and tracing.
    
    Usage:
        with ToolExecutionLogger(tool_name="read_file") as logger:
            logger.info("Reading file", context={"path": "/foo/bar.txt"})
            # ... do work ...
            logger.success("File read successfully")
    """
    
    def __init__(self, tool_name: str, trace_id: Optional[str] = None):
        self.tool_name = tool_name
        self.trace_id = trace_id or str(uuid.uuid4())[:8]
        self.start_time = None
        self.logger = logging.getLogger(f"ronin.tools.{tool_name}")
        
    def __enter__(self):
        self.start_time = datetime.utcnow()
        # Only log to file, not console
        self.debug(f"Starting {self.tool_name}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = (datetime.utcnow() - self.start_time).total_seconds()
        
        if exc_type:
            self.error(f"{self.tool_name} failed after {duration:.2f}s", 
                      error=str(exc_val))
        else:
            # Log completion to file only
            self.debug(f"{self.tool_name} completed in {duration:.2f}s")
        
        return False  # Don't suppress exceptions
    
    def _add_extras(self, record, context=None, **kwargs):
        """Add extra fields to log record."""
        record.trace_id = self.trace_id
        record.tool_name = self.tool_name
        if context:
            record.context = context
        for key, value in kwargs.items():
            setattr(record, key, value)
    
    def debug(self, message: str, context: Optional[Dict] = None, **kwargs):
        """Log debug message with context."""
        extra = {}
        if hasattr(self, 'trace_id'):
            extra['trace_id'] = self.trace_id
        if hasattr(self, 'tool_name'):
            extra['tool_name'] = self.tool_name
        if context:
            extra['context'] = context
        extra.update(kwargs)
        self.logger.debug(message, extra=extra if extra else None)
    
    def info(self, message: str, context: Optional[Dict] = None, **kwargs):
        """Log info message with context."""
        extra = {}
        if hasattr(self, 'trace_id'):
            extra['trace_id'] = self.trace_id
        if hasattr(self, 'tool_name'):
            extra['tool_name'] = self.tool_name
        if context:
            extra['context'] = context
        extra.update(kwargs)
        self.logger.info(message, extra=extra if extra else None)
    
    def warning(self, message: str, context: Optional[Dict] = None, **kwargs):
        """Log warning message with context."""
        extra = {}
        if hasattr(self, 'trace_id'):
            extra['trace_id'] = self.trace_id
        if hasattr(self, 'tool_name'):
            extra['tool_name'] = self.tool_name
        if context:
            extra['context'] = context
        extra.update(kwargs)
        self.logger.warning(message, extra=extra if extra else None)
    
    def error(self, message: str, error: Optional[str] = None, 
              recovery_hints: Optional[str] = None, context: Optional[Dict] = None):
        """Log error with recovery hints."""
        extra = {}
        if hasattr(self, 'trace_id'):
            extra['trace_id'] = self.trace_id
        if hasattr(self, 'tool_name'):
            extra['tool_name'] = self.tool_name
        if error:
            extra['error_type'] = error
        if recovery_hints:
            extra['recovery_hints'] = recovery_hints
        if context:
            extra['context'] = context
        self.logger.error(message, extra=extra if extra else None)
    
    def success(self, message: str, context: Optional[Dict] = None):
        """Log successful completion (to file only)."""
        self.debug(f"✅ {message}", context)

def setup_logging(level: str = "INFO", log_to_file: bool = True, 
                 console_format: str = "human"):
    """
    Configure logging for Ronin.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_to_file: Whether to write logs to file
        console_format: "human" for readable, "json" for structured
    """
    # Create root logger for Ronin
    logger = logging.getLogger("ronin")
    logger.setLevel(getattr(logging, level.upper()))
    
    # Remove existing handlers
    logger.handlers.clear()
    
    # Console handler with human-readable format
    console_handler = logging.StreamHandler(sys.stdout)
    if console_format == "human":
        console_handler.setFormatter(HumanReadableFormatter())
    else:
        console_handler.setFormatter(StructuredFormatter())
    # Set console level to match requested level (WARNING by default from CLI)
    console_handler.setLevel(getattr(logging, level.upper()))
    logger.addHandler(console_handler)
    
    # File handler with JSON format
    if log_to_file:
        log_file = LOGS_DIR / f"ronin_{datetime.now().strftime('%Y%m%d')}.jsonl"
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(StructuredFormatter())
        file_handler.setLevel(logging.DEBUG)  # Log everything to file
        logger.addHandler(file_handler)
    
    # Log startup (only to file, not console)
    logger.debug("Ronin logging initialized", extra={
        "context": {
            "level": level,
            "log_file": str(log_file) if log_to_file else None,
            "console_format": console_format
        }
    })
    
    return logger

def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for a module."""
    return logging.getLogger(f"ronin.{name}")

# Export for observability tools
def export_trace(trace_id: str) -> Dict[str, Any]:
    """
    Export all logs for a specific trace ID.
    
    This can be sent to LangSmith, Langfuse, etc.
    
    Args:
        trace_id: The trace ID to export
        
    Returns:
        Dictionary with all logs for that trace
    """
    logs = []
    
    # Read today's log file
    log_file = LOGS_DIR / f"ronin_{datetime.now().strftime('%Y%m%d')}.jsonl"
    if log_file.exists():
        with open(log_file) as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if entry.get('trace_id') == trace_id:
                        logs.append(entry)
                except json.JSONDecodeError:
                    continue
    
    return {
        "trace_id": trace_id,
        "logs": logs,
        "tool_sequence": [log['tool_name'] for log in logs if 'tool_name' in log],
        "errors": [log for log in logs if log.get('level') == 'ERROR'],
        "duration": _calculate_duration(logs) if logs else 0
    }

def _calculate_duration(logs: list) -> float:
    """Calculate duration from first to last log."""
    if not logs:
        return 0
    
    start = datetime.fromisoformat(logs[0]['timestamp'])
    end = datetime.fromisoformat(logs[-1]['timestamp'])
    return (end - start).total_seconds()