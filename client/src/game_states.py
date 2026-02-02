"""
Game state definitions and enums.
"""

from enum import Enum


class GameState(Enum):
    """Game states for the RPG client."""
    SERVER_SELECT = "server_select"
    LOGIN = "login"
    REGISTER = "register"
    PLAYING = "playing"
    CONNECTING = "connecting"