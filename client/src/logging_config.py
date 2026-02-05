"""
Logging configuration for the client.

Provides structured logging with configurable levels and output formats.
"""

import logging
import sys
from pathlib import Path
from typing import Optional

from .config import get_config


def setup_logging(
    log_level: Optional[str] = None,
    log_file: Optional[Path] = None,
    log_to_console: bool = True
) -> logging.Logger:
    """
    Configure logging for the client.
    
    Args:
        log_level: Override log level (DEBUG, INFO, WARNING, ERROR). Uses config if not specified.
        log_file: Optional path to log file
        log_to_console: Whether to log to console
    
    Returns:
        The root logger for the client
    """
    # Get log level from config or parameter
    if log_level is None:
        config = get_config()
        log_level = config.debug.log_level
    
    # Convert string to level
    level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Create logger
    logger = logging.getLogger("rpg_client")
    logger.setLevel(level)
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Format
    formatter = logging.Formatter(
        "%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Console handler
    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    # File handler
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a child logger for a specific module."""
    return logging.getLogger(f"rpg_client.{name}")


class LogContext:
    """Context manager for adding context to log messages."""
    
    def __init__(self, logger: logging.Logger, **context):
        self.logger = logger
        self.context = context
        self.original_extra = {}
    
    def __enter__(self):
        # Store current extra if exists
        if hasattr(self.logger, "_context"):
            self.original_extra = self.logger._context.copy()
        
        # Add new context
        self.logger._context = {**self.original_extra, **self.context}
        return self.logger
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restore original context
        if hasattr(self.logger, "_context"):
            self.logger._context = self.original_extra


def log_with_context(logger: logging.Logger, level: int, msg: str, **context):
    """Log a message with additional context."""
    extra = getattr(logger, "_context", {})
    extra.update(context)
    
    # Build context string
    context_str = " | ".join(f"{k}={v}" for k, v in extra.items())
    if context_str:
        msg = f"{msg} [{context_str}]"
    
    logger.log(level, msg)
