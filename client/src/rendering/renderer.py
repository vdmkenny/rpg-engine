"""
Main renderer orchestrator.

Coordinates all rendering systems and manages the render loop.
"""

import pygame
from typing import Optional, Dict, Any, List, Tuple
import time

from ..config import get_config
from ..logging_config import get_logger
from ..game.client_state import get_game_state

from .camera import Camera
from .map_renderer import MapRenderer
from .entity_renderer import EntityRenderer
from .ui_renderer import UIRenderer

logger = get_logger(__name__)


class Renderer:
    """
    Main rendering orchestrator.
    
    Manages pygame window, camera, and coordinates all render subsystems.
    Implements a zoomed game world with crisp UI overlay.
    """
    
    def __init__(self, screen: pygame.Surface):
        self.config = get_config()
        self.game_state = get_game_state()
        self.screen = screen
        
        # Zoom configuration
        self.zoom_level = self.config.game.zoom_level  # e.g., 2.0 for 2x zoom
        
        # Calculate game surface size (smaller buffer that gets scaled up)
        self.game_width = int(self.config.display.width / self.zoom_level)
        self.game_height = int(self.config.display.height / self.zoom_level)
        
        # Create game surface (render buffer at lower resolution)
        # All game world content (map, entities, players) renders here
        self.game_surface = pygame.Surface((self.game_width, self.game_height))
        
        # Pre-allocate scaled surface to avoid creating new surface every frame (H6 fix)
        self._scaled_surface = pygame.Surface((self.config.display.width, self.config.display.height))
        
        # FPS tracking (display flip/tick handled by main loop in client.py)
        self.fps = self.config.display.fps
        self.current_fps = 0.0
        
        # Sub-renderers
        # Camera works in game surface coordinates (not display coordinates)
        self.camera = Camera(
            self.game_width,
            self.game_height,
            self.config.game.tile_size
        )
        # Game renderers draw to game_surface
        self.map_renderer = MapRenderer(self.game_surface, self.camera, self.config.game.tile_size)
        self.entity_renderer = EntityRenderer(self.game_surface, self.camera, self.config.game.tile_size)
        # UI renderer draws directly to screen (stays crisp)
        self.ui_renderer = UIRenderer(self.screen)
        
        # Font for debug info
        self.debug_font = pygame.font.SysFont("monospace", 14)
        
        logger.info(f"Renderer initialized: {self.config.display.width}x{self.config.display.height} "
                   f"(game surface: {self.game_width}x{self.game_height}, zoom: {self.zoom_level}x)")
    
    def update(self, delta_time: float) -> None:
        """Update render state."""
        # Update camera to follow player
        if self.game_state.is_moving:
            # Interpolate between start and target positions during movement
            t = self.game_state.move_progress
            player_x = self.game_state.move_start_x + (self.game_state.move_target_x - self.game_state.move_start_x) * t
            player_y = self.game_state.move_start_y + (self.game_state.move_target_y - self.game_state.move_start_y) * t
        else:
            player_x = self.game_state.position.get("x", 0)
            player_y = self.game_state.position.get("y", 0)
        self.camera.update_target(player_x, player_y)
        self.camera.update(delta_time)
        
        # Update entity animations
        self.entity_renderer.update(delta_time)
    
    def render(self) -> None:
        """Render one frame."""
        # 1. Clear game surface (for game world content)
        self.game_surface.fill((0, 0, 0))
        
        # 2. Render game world to game_surface
        # Map/chunks
        self.map_renderer.render(self.game_state.chunks, self.game_state.map_id)
        
        # Ground items (rendered before all entities)
        self.entity_renderer.render_ground_items(self.game_state.ground_items)
        
        # Render all entities (NPCs, other players, local player) in Y-sorted order
        # Entities with higher Y (lower on screen) are rendered last (in front)
        player_x = self.game_state.position.get("x", 0)
        player_y = self.game_state.position.get("y", 0)
        self.entity_renderer.render_all_sorted(
            entities=self.game_state.entities,
            other_players=self.game_state.other_players,
            local_player={
                "x": player_x,
                "y": player_y,
                "visual_hash": self.game_state.visual_hash,
                "visual_state": self.game_state.visual_state,
                "facing_direction": self.game_state.facing_direction,
                "is_moving": getattr(self.game_state, 'is_moving', False),
                "move_progress": getattr(self.game_state, 'move_progress', 0.0),
            }
        )
        
        # Effects (hit splats, floating text)
        self.entity_renderer.render_effects(self.game_state.hit_splats, self.game_state.floating_messages)
        
        # 3. Scale game surface to display and blit to screen
        if self.zoom_level != 1.0:
            pygame.transform.scale(self.game_surface, 
                                  (self.config.display.width, self.config.display.height),
                                  self._scaled_surface)
            self.screen.blit(self._scaled_surface, (0, 0))
        else:
            self.screen.blit(self.game_surface, (0, 0))
        
        # 4. Render UI overlay directly to screen (stays crisp, not zoomed)
        self.ui_renderer.render(self.game_state)
        
        # 5. Debug info (rendered to screen for crisp text)
        if self.config.debug.show_fps:
            self._render_debug_info()
        
        # Note: display flip and FPS capping handled by main loop in client.py
    
    def _render_debug_info(self) -> None:
        """Render debug information overlay."""
        fps_text = f"FPS: {self.current_fps:.1f}"
        text_surface = self.debug_font.render(fps_text, True, (255, 255, 0))
        self.screen.blit(text_surface, (10, 10))
        
        pos_text = f"Pos: ({self.game_state.position.get('x', 0)}, {self.game_state.position.get('y', 0)})"
        text_surface = self.debug_font.render(pos_text, True, (255, 255, 0))
        self.screen.blit(text_surface, (10, 30))
    
    def handle_resize(self, screen: pygame.Surface, width: int, height: int) -> None:
        """Handle window resize."""
        # Update display surface reference (display managed by client.py)
        self.screen = screen
        
        # Recalculate game surface size
        self.game_width = int(width / self.zoom_level)
        self.game_height = int(height / self.zoom_level)
        self.game_surface = pygame.Surface((self.game_width, self.game_height))
        
        # Update camera with new dimensions
        self.camera.handle_resize(self.game_width, self.game_height)
        
        # Update UI renderer with new screen
        self.ui_renderer = UIRenderer(self.screen)
        
        logger.info(f"Window resized to {width}x{height} "
                   f"(game surface: {self.game_width}x{self.game_height})")
    
    def get_display_to_game_ratio(self) -> float:
        """Get the ratio of display coordinates to game surface coordinates."""
        return self.zoom_level
    
    def screen_to_game_coords(self, screen_x: float, screen_y: float) -> Tuple[float, float]:
        """Convert display screen coordinates to game surface coordinates."""
        return (screen_x / self.zoom_level, screen_y / self.zoom_level)
    
    def cleanup(self) -> None:
        """Cleanup pygame resources."""
        pygame.quit()
        logger.info("Renderer cleaned up")
