"""
Map renderer.

Renders map chunks and tiles using tileset sprites.
"""

import pygame
from typing import Dict, Tuple, List, Optional, Any

from ..config import get_config
from ..ui.colors import Colors
from .camera import Camera
from ..tileset_manager import get_tileset_manager


class MapRenderer:
    """Renders map chunks and tiles."""
    
    def __init__(self, screen: pygame.Surface, camera: Camera, tile_size: int):
        self.screen = screen
        self.camera = camera
        self.tile_size = tile_size
        
        # Chunk size in tiles
        self.chunk_size = 16
        
        # Get tileset manager for sprites
        self.tileset_manager = get_tileset_manager()
        
        # Tile colors (fallback if no tileset loaded)
        self.tile_colors = {
            0: Colors.TILE_GRASS,
            1: Colors.TILE_DIRT,
            2: Colors.TILE_STONE,
            3: Colors.TILE_WATER,
            4: Colors.TILE_SAND,
            5: Colors.TILE_FOREST,
            6: Colors.TILE_WALL,
        }
        
        # Default color for unknown tiles
        self.default_color = Colors.TILE_DEFAULT
        
        # Current map ID for sprite lookups
        self.current_map_id: Optional[str] = None
        
        # Cached fonts for performance
        self._missing_chunk_font = pygame.font.SysFont("monospace", 20)
    
    def render(self, chunks: Dict[Tuple[int, int], Any], map_id: Optional[str] = None) -> None:
        """Render all visible map chunks."""
        # Update current map ID
        if map_id:
            self.current_map_id = map_id

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
            for x, tile_data in enumerate(row):
                # Calculate world position
                world_x = chunk_pixel_x + x * self.tile_size
                world_y = chunk_pixel_y + y * self.tile_size
                
                # Check if on screen
                if not self.camera.is_on_screen(world_x, world_y, margin=self.tile_size):
                    continue
                
                # Convert to screen coordinates
                screen_x, screen_y = self.camera.world_to_screen(world_x, world_y)
                
                # Handle both raw GID (int) and structured tile data (dict with layers)
                layers = []
                if isinstance(tile_data, dict):
                    # Structured format: {"layers": [{"gid": int, ...}], "properties": {...}}
                    layers = tile_data.get("layers", [])
                elif isinstance(tile_data, int):
                    # Raw GID format: just an integer
                    if tile_data > 0:
                        layers = [{"gid": tile_data}]
                elif isinstance(tile_data, list):
                    # List of GIDs format
                    for gid in tile_data:
                        if isinstance(gid, int) and gid > 0:
                            layers.append({"gid": gid})

                # Render each layer in order (bottom to top)
                for layer in layers:
                    if isinstance(layer, dict):
                        gid = layer.get("gid", 0)
                    elif isinstance(layer, int):
                        gid = layer
                    else:
                        continue

                    if gid > 0 and self.current_map_id:
                        sprite = self.tileset_manager.get_tile_sprite(gid, self.current_map_id)
                        if sprite:
                            self.screen.blit(sprite, (int(screen_x), int(screen_y)))
    
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
        pygame.draw.rect(self.screen, Colors.CHUNK_MISSING_BORDER, rect, 2)
        
        # Draw question mark
        text = self._missing_chunk_font.render("?", True, Colors.CHUNK_MISSING_TEXT)
        text_rect = text.get_rect(center=rect.center)
        self.screen.blit(text, text_rect)
