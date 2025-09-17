"""
Logging configuration for the RPG server.

Provides structured logging with different levels for development, testing, and production.
Configures formatters, handlers, and loggers for various components.
"""

import logging
import logging.config
import os
import sys
from typing import Dict, Any


def get_log_level() -> str:
    """Get the log level from environment variables."""
    return os.getenv("LOG_LEVEL", "INFO").upper()


def get_logging_config() -> Dict[str, Any]:
    """
    Get the logging configuration dictionary.

    Returns a logging configuration that can be used with logging.config.dictConfig().
    Supports different environments (development, testing, production) and provides
    structured output with proper formatting.
    """
    log_level = get_log_level()
    environment = os.getenv("ENVIRONMENT", "development").lower()

    # Choose formatter based on environment and availability
    if environment == "production":
        # Try to use JSON formatting for production, fall back to standard
        try:
            import pythonjsonlogger.jsonlogger

            formatter_class = "pythonjsonlogger.jsonlogger.JsonFormatter"
            formatter_format = "%(asctime)s %(name)s %(levelname)s %(message)s"
        except ImportError:
            formatter_class = "logging.Formatter"
            formatter_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s [JSON logger not available]"
    else:
        # Human-readable formatting for development/testing
        formatter_class = "logging.Formatter"
        formatter_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "class": formatter_class,
                "format": formatter_format,
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "detailed": {
                "class": formatter_class,
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": log_level,
                "formatter": "default",
                "stream": sys.stdout,
            },
            "error_console": {
                "class": "logging.StreamHandler",
                "level": "ERROR",
                "formatter": "detailed",
                "stream": sys.stderr,
            },
        },
        "loggers": {
            # Application loggers
            "rpg": {
                "level": log_level,
                "handlers": ["console", "error_console"],
                "propagate": False,
            },
            "rpg.websocket": {
                "level": log_level,
                "handlers": ["console", "error_console"],
                "propagate": False,
            },
            "rpg.auth": {
                "level": log_level,
                "handlers": ["console", "error_console"],
                "propagate": False,
            },
            "rpg.database": {
                "level": log_level,
                "handlers": ["console", "error_console"],
                "propagate": False,
            },
            "rpg.game": {
                "level": log_level,
                "handlers": ["console", "error_console"],
                "propagate": False,
            },
            # Third-party loggers
            "sqlalchemy.engine": {
                "level": "WARNING",  # Reduce SQLAlchemy verbosity
                "handlers": ["console"],
                "propagate": False,
            },
            "uvicorn": {
                "level": "INFO",
                "handlers": ["console"],
                "propagate": False,
            },
            "uvicorn.access": {
                "level": "INFO",
                "handlers": ["console"],
                "propagate": False,
            },
            "fastapi": {
                "level": "INFO",
                "handlers": ["console"],
                "propagate": False,
            },
        },
        "root": {
            "level": log_level,
            "handlers": ["console", "error_console"],
        },
    }

    return config


def setup_logging() -> None:
    """
    Configure logging for the application.

    This should be called once at application startup, before any other
    logging occurs. It sets up all loggers, handlers, and formatters
    according to the current environment.
    """
    config = get_logging_config()
    logging.config.dictConfig(config)

    # Log the configuration that was applied
    logger = logging.getLogger("rpg.logging")
    logger.info(
        "Logging configured",
        extra={
            "log_level": get_log_level(),
            "environment": os.getenv("ENVIRONMENT", "development"),
        },
    )


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for the given name.

    Args:
        name: The logger name, typically __name__ from the calling module

    Returns:
        A configured logger instance
    """
    # Ensure the logger name starts with 'rpg.' for proper hierarchy
    if not name.startswith("rpg."):
        if name.startswith("server.src."):
            # Convert server.src.api.websockets -> rpg.websocket
            parts = name.split(".")
            if len(parts) >= 3:
                component = parts[2]  # api, core, models, etc.
                if component == "api":
                    name = f"rpg.{parts[3]}" if len(parts) > 3 else "rpg.api"
                else:
                    name = f"rpg.{component}"
            else:
                name = "rpg"
        else:
            name = f"rpg.{name}"

    return logging.getLogger(name)
