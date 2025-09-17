"""
Game entities - Player, FloatingMessage, and related classes.
"""

import os
import sys
from dataclasses import dataclass
from typing import List

# Import common constants
workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.append(workspace_root)
from common.src.constants import (
    MOVEMENT_ANIMATION_DURATION,
    ANIMATION_START,
)


class FloatingMessage:
    """Represents a floating chat message above a player."""
    def __init__(self, message: str, timestamp: float, duration: float = 3.0):
        self.message = message
        self.timestamp = timestamp
        self.duration = duration  # How long to show the message
        
    def is_expired(self, current_time: float) -> bool:
        """Check if message should be removed."""
        return current_time - self.timestamp > self.duration
        
    def get_alpha(self, current_time: float) -> int:
        """Get alpha value for fade out effect."""
        age = current_time - self.timestamp
        if age > self.duration * 0.7:  # Start fading at 70% of duration
            fade_progress = (age - self.duration * 0.7) / (self.duration * 0.3)
            return max(0, int(255 * (1 - fade_progress)))
        return 255


@dataclass
class Player:
    """
    Represents a player character with position, movement state, and animations.
    """

    def __init__(self):
        # Logical position (server-authoritative)
        self.x = 0
        self.y = 0
        self.map_id = "test_map"
        self.username = ""
        # Track last position where chunks were requested
        self.last_chunk_request_x = 0
        self.last_chunk_request_y = 0
        # Animation and movement state for smooth client-side rendering
        self.display_x = ANIMATION_START  # Smooth visual position
        self.display_y = ANIMATION_START
        self.is_moving = False
        self.facing_direction = "DOWN"  # UP, DOWN, LEFT, RIGHT
        self.move_start_time = ANIMATION_START
        self.move_duration = MOVEMENT_ANIMATION_DURATION
        # Floating chat messages
        self.floating_messages = []
        # Animation start positions (set dynamically)
        self._start_x = 0.0
        self._start_y = 0.0