"""
Map renderer.

Renders map chunks and tiles.
"""

import pygame
from typing import Dict, Tuple, List, Optional

from ..config import get_config
from .camera import Camera


class MapRenderer:
    """Renders map chunks and tiles."""
    
    def __init__(self, screen: pygame.Surface, camera: Camera, tile_size: int):
        self.screen = screen
        self.camera = camera
        self.tile_size = tile_size
        
        # Chunk size in tiles
        self.chunk_size = 16
        
        # Tile colors (fallback if no tileset)
        self.tile_colors = {
            0: (34, 139, 34),    # Grass - green
            1: (139, 69, 19),    # Dirt - brown
            2: (100, 100, 100),  # Stone - gray
            3: (0, 105, 148),    # Water - blue
            4: (210, 180, 140),  # Sand - tan
            5: (34, 100, 34),    # Forest - dark green
            6: (80, 80, 80),     # Wall - dark gray
        }
        
        # Default color for unknown tiles
        self.default_color = (128, 128, 128)
    
    def render(self, chunks: Dict[Tuple[int, int], List[List[int]]]) -> None:
        """Render all visible map chunks."""
        # Get visible tile range
        min_x, min_y, max_x, max_y = self.camera.get_visible_tile_range()
        
        # Convert to chunk coordinates
        min_chunk_x = min_x // self.chunk_size
        min_chunk_y = min_y // self.chunk_size
        max_chunk_x = max_x // self.chunk_size
        max_chunk_y = max_y // self.chunk_size
        
        # Render each visible chunk
        for chunk_x in range(min_chunk_x, max_chunk_x + 1):
            for chunk_y in range(min_chunk_y, max_chunk_y + 1):
                chunk = chunks.get((chunk_x, chunk_y))
                if chunk:
                    self._render_chunk(chunk_x, chunk_y, chunk)
                else:
                    # Render placeholder for missing chunk
                    self._render_missing_chunk(chunk_x, chunk_y)
    
    def _render_chunk(self, chunk_x: int, chunk_y: int, chunk: List[List[int]]) -> None:
        """Render a single chunk."""
        chunk_pixel_x = chunk_x * self.chunk_size * self.tile_size
        chunk_pixel_y = chunk_y * self.chunk_size * self.tile_size
        
        for y, row in enumerate(chunk):
            for x, tile_id in enumerate(row):
                # Calculate world position
                world_x = chunk_pixel_x + x * self.tile_size
                world_y = chunk_pixel_y + y * self.tile_size
                
                # Check if on screen
                if not self.camera.is_on_screen(world_x, world_y, margin=self.tile_size):
                    continue
                
                # Convert to screen coordinates
                screen_x, screen_y = self.camera.world_to_screen(world_x, world_y)
                
                # Get tile color
                color = self.tile_colors.get(tile_id, self.default_color)
                
                # Draw tile
                rect = pygame.Rect(int(screen_x), int(screen_y), self.tile_size, self.tile_size)
                pygame.draw.rect(self.screen, color, rect)
                
                # Draw tile border (subtle grid)
                pygame.draw.rect(self.screen, (0, 0, 0), rect, 1)
    
    def _render_missing_chunk(self, chunk_x: int, chunk_y: int) -> None:
        """Render placeholder for missing chunk."""
        chunk_pixel_x = chunk_x * self.chunk_size * self.tile_size
        chunk_pixel_y = chunk_y * self.chunk_size * self.tile_size
        
        # Check if chunk is on screen
        if not self.camera.is_on_screen(chunk_pixel_x, chunk_pixel_y, margin=self.chunk_size * self.tile_size):
            return
        
        # Convert to screen coordinates
        screen_x, screen_y = self.camera.world_to_screen(chunk_pixel_x, chunk_pixel_y)
        
        # Draw missing chunk indicator
        size = self.chunk_size * self.tile_size
        rect = pygame.Rect(int(screen_x), int(screen_y), size, size)
        pygame.draw.rect(self.screen, (50, 50, 50), rect, 2)
        
        # Draw question mark
        font = pygame.font.SysFont("monospace", 20)
        text = font.render("?", True, (100, 100, 100))
        text_rect = text.get_rect(center=rect.center)
        self.screen.blit(text, text_rect)
