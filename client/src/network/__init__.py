"""Network layer for WebSocket communication."""

from .connection import ConnectionManager, ConnectionState

__all__ = [
    "ConnectionManager",
    "ConnectionState",
]
