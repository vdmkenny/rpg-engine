"""
Chat command system for the RPG client.

Provides an extensible command registry for slash commands typed in chat.
Commands starting with '/' are intercepted before being sent to the server.
"""

from client.src.chat.command_registry import CommandRegistry, get_command_registry

__all__ = ["CommandRegistry", "get_command_registry"]
