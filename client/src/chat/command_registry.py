"""
Command registry for chat slash commands.

Allows registering handlers for commands starting with '/'
that are intercepted before being sent to the chat server.
"""

from typing import Callable, Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class CommandInfo:
    """Information about a registered command."""
    name: str
    handler: Callable[[str], Optional[str]]
    description: str


class CommandRegistry:
    """Registry for chat slash commands.
    
    Commands are registered with a name (without the leading slash),
    a handler function, and a description. When a chat message starts
    with '/', the registry attempts to match and execute the command
    locally instead of sending it to the server.
    
    Example:
        registry = get_command_registry()
        registry.register("customize", handle_customize, "Open character customisation")
        
        # Later, when user types "/customize" in chat:
        result = registry.try_handle("/customize")
        if result is not None:
            # Command was handled locally, result is the response (or None)
            pass
        else:
            # Not a known command, send to server as regular chat
            pass
    """
    
    def __init__(self):
        self._commands: Dict[str, CommandInfo] = {}
    
    def register(
        self,
        name: str,
        handler: Callable[[str], Optional[str]],
        description: str = ""
    ) -> None:
        """Register a command handler.
        
        Args:
            name: Command name without leading slash (e.g., "customize")
            handler: Function called when command is invoked.
                    Receives the full command text (including args).
                    Should return a response string or None.
            description: Human-readable description for help text
        """
        self._commands[name.lower()] = CommandInfo(
            name=name.lower(),
            handler=handler,
            description=description
        )
    
    def try_handle(self, text: str) -> Optional[str]:
        """Attempt to handle a command.
        
        Args:
            text: The full command text (e.g., "/customize arg1 arg2")
            
        Returns:
            Handler result if command was found and executed, None otherwise.
            Returns None means the text should be sent to server as regular chat.
        """
        if not text.startswith("/"):
            return None
        
        # Extract command name (first word after /)
        parts = text[1:].split(maxsplit=1)
        if not parts:
            return None
        
        command_name = parts[0].lower()
        
        if command_name not in self._commands:
            return None
        
        cmd = self._commands[command_name]
        return cmd.handler(text)
    
    def get_commands(self) -> List[Tuple[str, str]]:
        """Get list of all registered commands with descriptions.
        
        Returns:
            List of (name, description) tuples
        """
        return [
            (cmd.name, cmd.description)
            for cmd in self._commands.values()
        ]
    
    def is_command(self, text: str) -> bool:
        """Check if text is a known command.
        
        Args:
            text: Text to check (e.g., "/customize")
            
        Returns:
            True if this is a registered command
        """
        if not text.startswith("/"):
            return False
        
        parts = text[1:].split(maxsplit=1)
        if not parts:
            return False
        
        return parts[0].lower() in self._commands


# Singleton instance
_command_registry: Optional[CommandRegistry] = None


def get_command_registry() -> CommandRegistry:
    """Get the global command registry singleton.
    
    Returns:
        The global CommandRegistry instance
    """
    global _command_registry
    if _command_registry is None:
        _command_registry = CommandRegistry()
    return _command_registry
