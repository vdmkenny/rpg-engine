"""
Game constants and configuration values.
This file centralizes all magic numbers used throughout the game.
"""

# Animation and Timing Constants
MOVEMENT_ANIMATION_DURATION = 0.5  # Seconds for smooth movement animation
CLIENT_MOVE_COOLDOWN = 0.5  # Minimum time between client moves (seconds)
WEBSOCKET_TIMEOUT = 1.0  # WebSocket receive timeout (seconds) - only used for connection setup
ASYNC_SLEEP_SHORT = 0.3  # Short async sleep duration (seconds)
ASYNC_SLEEP_MEDIUM = 0.5  # Medium async sleep duration (seconds)

# Game World Constants
CHUNK_REQUEST_DISTANCE = 8  # Distance in tiles before requesting new chunks
MILLISECONDS_TO_SECONDS = 1000.0  # Conversion factor from milliseconds to seconds

# UI and Display Constants
SCREEN_WIDTH = 800  # Default screen width in pixels
SCREEN_HEIGHT = 600  # Default screen height in pixels
TILE_SIZE = 32  # Size of each tile in pixels

# Color Constants (RGB values)
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
GRAY = (128, 128, 128)  # UI background
DARK_GRAY = (64, 64, 64)  # UI border

# Server Constants
DEFAULT_CHUNK_SIZE = 64  # Default chunk size in tiles
SERVER_MOVE_COOLDOWN = 0.5  # Server-side movement cooldown (seconds) - matches client

# Progress and Animation Constants
ANIMATION_COMPLETE = 1.0  # Animation completion threshold
ANIMATION_START = 0.0  # Animation start value
