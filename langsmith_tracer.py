# LangSmith Tracing Integration for Ronin
# ========================================
# Provides observability and debugging capabilities through LangSmith

import os
import json
from typing import Optional, Dict, Any, List
from datetime import datetime
from pathlib import Path
import functools

try:
    from langsmith import Client, traceable
    from langsmith.wrappers import wrap_anthropic
    LANGSMITH_AVAILABLE = True
except ImportError:
    LANGSMITH_AVAILABLE = False
    # Create dummy decorators when LangSmith not available
    def traceable(*args, **kwargs):
        def decorator(func):
            return func
        return decorator
    
    class Client:
        def __init__(self):
            pass

from logging_config import get_logger
from secrets_manager import get_api_key

logger = get_logger("langsmith_tracer")

class LangSmithTracer:
    """
    Manages LangSmith tracing for Ronin operations.
    
    This provides:
    - Automatic tracing of all tool executions
    - Claude API call tracing
    - Performance metrics and debugging
    - Error tracking with recovery hints
    """
    
    def __init__(self, enabled: Optional[bool] = None):
        """
        Initialize LangSmith tracer.
        
        Args:
            enabled: Force enable/disable. If None, checks env vars and availability.
        """
        self.client = None
        self.enabled = False
        
        if enabled is False:
            return
        
        if not LANGSMITH_AVAILABLE:
            logger.debug("LangSmith not installed. Install with: pip install langsmith")
            return
        
        # Check for API key in secrets or environment
        api_key = get_api_key("langsmith") or os.getenv("LANGSMITH_API_KEY")
        
        if not api_key:
            logger.debug("No LangSmith API key found. Tracing disabled.")
            return
        
        # Set environment variables for LangSmith
        os.environ["LANGSMITH_API_KEY"] = api_key
        os.environ["LANGSMITH_TRACING"] = "true"
        
        # Check if user wants tracing enabled (default: true)
        if enabled is None:
            # Default to enabled unless explicitly disabled
            enabled = os.getenv("RONIN_ENABLE_TRACING", "true").lower() != "false"
        
        if enabled:
            try:
                self.client = Client()
                self.enabled = True
                
                # Set project name if specified
                project = os.getenv("LANGSMITH_PROJECT", "ronin-agent")
                os.environ["LANGSMITH_PROJECT"] = project
                
                logger.debug(f"LangSmith tracing enabled for project: {project}")
            except Exception as e:
                logger.debug(f"Failed to initialize LangSmith client: {e}")
                self.enabled = False
    
    def is_enabled(self) -> bool:
        """Check if tracing is enabled."""
        return self.enabled
    
    def get_wrapped_anthropic_client(self, client):
        """Wrap Anthropic client for automatic tracing."""
        if self.enabled and LANGSMITH_AVAILABLE:
            try:
                from langsmith.wrappers import wrap_anthropic
                return wrap_anthropic(client)
            except Exception as e:
                logger.debug(f"Failed to wrap Anthropic client: {e}")
        return client

# Global tracer instance
_tracer = None

def get_tracer() -> LangSmithTracer:
    """Get or create the global LangSmith tracer."""
    global _tracer
    if _tracer is None:
        _tracer = LangSmithTracer()
    return _tracer

def trace_tool(name: str = None, metadata: Dict[str, Any] = None):
    """
    Decorator for tracing tool executions.
    
    Args:
        name: Optional name for the trace
        metadata: Additional metadata to include
    
    Usage:
        @trace_tool(name="list_files", metadata={"category": "read"})
        def list_files(root, pattern):
            ...
    """
    def decorator(func):
        # Don't check if enabled at decoration time - check at execution time
        # This prevents initialization during import
        if not LANGSMITH_AVAILABLE:
            return func
        
        trace_name = name or func.__name__
        trace_metadata = metadata or {}
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Check if tracing is enabled at execution time, not decoration time
            if get_tracer().is_enabled():
                # Apply the traceable decorator dynamically
                traced_func = traceable(
                    run_type="tool",
                    name=trace_name,
                    metadata=trace_metadata
                )(func)
                return traced_func(*args, **kwargs)
            else:
                return func(*args, **kwargs)
        
        return wrapper
    return decorator

def trace_chain(name: str = None):
    """
    Decorator for tracing multi-step operations.
    
    Usage:
        @trace_chain(name="modify_file_chain")
        def complex_operation():
            ...
    """
    def decorator(func):
        # Don't check if enabled at decoration time
        if not LANGSMITH_AVAILABLE:
            return func
        
        trace_name = name or func.__name__
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Check if tracing is enabled at execution time
            if get_tracer().is_enabled():
                traced_func = traceable(
                    run_type="chain",
                    name=trace_name
                )(func)
                return traced_func(*args, **kwargs)
            else:
                return func(*args, **kwargs)
        
        return wrapper
    return decorator

def trace_llm(name: str = "Claude"):
    """
    Decorator for tracing LLM calls.
    
    Usage:
        @trace_llm(name="Claude-3.5-Sonnet")
        def call_claude(prompt):
            ...
    """
    def decorator(func):
        # Don't check if enabled at decoration time
        if not LANGSMITH_AVAILABLE:
            return func
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Check if tracing is enabled at execution time
            if get_tracer().is_enabled():
                traced_func = traceable(
                    run_type="llm",
                    name=name
                )(func)
                return traced_func(*args, **kwargs)
            else:
                return func(*args, **kwargs)
        
        return wrapper
    return decorator

def log_to_langsmith(
    run_type: str,
    name: str,
    inputs: Dict[str, Any],
    outputs: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
):
    """
    Manually log an event to LangSmith.
    
    Args:
        run_type: Type of run (tool, chain, llm, etc.)
        name: Name of the operation
        inputs: Input parameters
        outputs: Output results
        error: Error message if failed
        metadata: Additional metadata
    """
    if not get_tracer().is_enabled():
        return
    
    try:
        # This would use the LangSmith client to log
        # For now, we'll use the traceable decorator approach
        logger.debug(f"Logged to LangSmith: {name} ({run_type})")
    except Exception as e:
        logger.debug(f"Failed to log to LangSmith: {e}")

# Configuration helper
def configure_langsmith(
    api_key: Optional[str] = None,
    project: Optional[str] = None,
    enabled: bool = True
):
    """
    Configure LangSmith settings.
    
    Args:
        api_key: LangSmith API key (if not in secrets/env)
        project: Project name for organizing traces
        enabled: Whether to enable tracing
    """
    global _tracer
    
    if api_key:
        os.environ["LANGSMITH_API_KEY"] = api_key
    
    if project:
        os.environ["LANGSMITH_PROJECT"] = project
    
    os.environ["RONIN_ENABLE_TRACING"] = str(enabled).lower()
    
    # Reinitialize tracer with new settings
    _tracer = LangSmithTracer(enabled=enabled)
    
    return _tracer.is_enabled()