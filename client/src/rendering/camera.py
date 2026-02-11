"""
Camera management.

Handles viewport positioning, smooth following, and coordinate transformations.
"""

from typing import Tuple, Optional
import math
import random

from ..config import get_config


class Camera:
    """
    Game camera that follows the player.
    
    Supports smooth interpolation and handles coordinate transformations.
    """
    
    def __init__(self, screen_width: int, screen_height: int, tile_size: int):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.tile_size = tile_size
        
        # Camera position (center of screen in world coordinates)
        self.x: float = 0.0
        self.y: float = 0.0
        
        # Target position (where we want to be)
        self.target_x: float = 0.0
        self.target_y: float = 0.0
        
        # Smooth follow speed (higher = snappier)
        self.follow_speed: float = 10.0
        
        # Shake effect
        self.shake_amount: float = 0.0
        self.shake_decay: float = 5.0
    
    def update_target(self, player_x: int, player_y: int) -> None:
        """Update the target position to follow the player."""
        # Target is player position in world coordinates
        self.target_x = player_x * self.tile_size
        self.target_y = player_y * self.tile_size
    
    def update(self, delta_time: float) -> None:
        """Update camera position with smooth interpolation."""
        # Smoothly interpolate towards target
        dx = self.target_x - self.x
        dy = self.target_y - self.y
        
        self.x += dx * self.follow_speed * delta_time
        self.y += dy * self.follow_speed * delta_time
        
        # Apply screen shake if active
        if self.shake_amount > 0:
            shake_x = (random.random() - 0.5) * 2 * self.shake_amount
            shake_y = (random.random() - 0.5) * 2 * self.shake_amount
            self.x += shake_x
            self.y += shake_y
            self.shake_amount *= (1.0 - self.shake_decay * delta_time)
            if self.shake_amount < 0.1:
                self.shake_amount = 0.0
    
    def world_to_screen(self, world_x: float, world_y: float) -> Tuple[float, float]:
        """
        Convert world coordinates to screen coordinates.
        
        Args:
            world_x: X position in world (tile coordinates * tile_size)
            world_y: Y position in world (tile coordinates * tile_size)
            
        Returns:
            (screen_x, screen_y) tuple
        """
        screen_x = world_x - self.x + self.screen_width / 2
        screen_y = world_y - self.y + self.screen_height / 2
        return (screen_x, screen_y)
    
    def screen_to_world(self, screen_x: float, screen_y: float) -> Tuple[float, float]:
        """
        Convert screen coordinates to world coordinates.
        
        Args:
            screen_x: X position on screen
            screen_y: Y position on screen
            
        Returns:
            (world_x, world_y) tuple in world coordinates
        """
        world_x = screen_x + self.x - self.screen_width / 2
        world_y = screen_y + self.y - self.screen_height / 2
        return (world_x, world_y)
    
    def tile_to_screen(self, tile_x: int, tile_y: int) -> Tuple[float, float]:
        """Convert tile coordinates directly to screen coordinates."""
        world_x = tile_x * self.tile_size
        world_y = tile_y * self.tile_size
        return self.world_to_screen(world_x, world_y)
    
    def screen_to_tile(self, screen_x: float, screen_y: float) -> Tuple[int, int]:
        """Convert screen coordinates to tile coordinates."""
        world_x, world_y = self.screen_to_world(screen_x, screen_y)
        tile_x = int(world_x // self.tile_size)
        tile_y = int(world_y // self.tile_size)
        return (tile_x, tile_y)
    
    def get_visible_tile_range(self) -> Tuple[int, int, int, int]:
        """
        Get the range of tiles visible on screen.
        
        Returns:
            (min_x, min_y, max_x, max_y) in tile coordinates
        """
        # Top-left corner of screen in world coords
        world_x = self.x - self.screen_width / 2
        world_y = self.y - self.screen_height / 2
        
        min_x = int(world_x // self.tile_size) - 1
        min_y = int(world_y // self.tile_size) - 1
        max_x = int((world_x + self.screen_width) // self.tile_size) + 1
        max_y = int((world_y + self.screen_height) // self.tile_size) + 1
        
        return (min_x, min_y, max_x, max_y)
    
    def is_on_screen(self, world_x: float, world_y: float, margin: int = 0) -> bool:
        """Check if a world position is visible on screen."""
        screen_x, screen_y = self.world_to_screen(world_x, world_y)
        return (-margin <= screen_x <= self.screen_width + margin and
                -margin <= screen_y <= self.screen_height + margin)
    
    def shake(self, amount: float) -> None:
        """Apply screen shake effect."""
        self.shake_amount = max(self.shake_amount, amount)
    
    def handle_resize(self, width: int, height: int) -> None:
        """Handle window resize."""
        self.screen_width = width
        self.screen_height = height
