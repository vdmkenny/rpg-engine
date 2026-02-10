"""
Main renderer orchestrator.

Coordinates all rendering systems and manages the render loop.
"""

import pygame
from typing import Optional, Dict, Any, List
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
    """
    
    def __init__(self):
        self.config = get_config()
        self.game_state = get_game_state()
        
        # Pygame initialization
        pygame.init()
        pygame.display.set_caption(self.config.display.title)
        
        # Create window
        if self.config.display.fullscreen:
            self.screen = pygame.display.set_mode(
                (self.config.display.width, self.config.display.height),
                pygame.FULLSCREEN
            )
        else:
            self.screen = pygame.display.set_mode(
                (self.config.display.width, self.config.display.height)
            )
        
        # Create clock for FPS control
        self.clock = pygame.time.Clock()
        self.fps = self.config.display.fps
        self.current_fps = 0.0
        
        # Sub-renderers
        self.camera = Camera(
            self.config.display.width,
            self.config.display.height,
            self.config.game.tile_size
        )
        self.map_renderer = MapRenderer(self.screen, self.camera, self.config.game.tile_size)
        self.entity_renderer = EntityRenderer(self.screen, self.camera, self.config.game.tile_size)
        self.ui_renderer = UIRenderer(self.screen)
        
        # Font for debug info
        self.debug_font = pygame.font.SysFont("monospace", 14)
        
        logger.info(f"Renderer initialized: {self.config.display.width}x{self.config.display.height}")
    
    def update(self, delta_time: float) -> None:
        """Update render state."""
        # Update camera to follow player
        player_x = self.game_state.position.get("x", 0)
        player_y = self.game_state.position.get("y", 0)
        self.camera.update_target(player_x, player_y)
        self.camera.update(delta_time)
        
        # Update entity animations
        self.entity_renderer.update(delta_time)
    
    def render(self) -> None:
        """Render one frame."""
        # Clear screen (black background)
        self.screen.fill((0, 0, 0))
        
        # Render layers
        # 1. Map/chunks
        self.map_renderer.render(self.game_state.chunks, self.game_state.map_id)
        
        # 2. Ground items
        self.entity_renderer.render_ground_items(self.game_state.ground_items)
        
        # 3. Entities (NPCs, monsters)
        self.entity_renderer.render_entities(self.game_state.entities)
        
        # 4. Other players
        self.entity_renderer.render_other_players(self.game_state.other_players)
        
        # 5. Own player (centered on screen)
        player_x = self.game_state.position.get("x", 0)
        player_y = self.game_state.position.get("y", 0)
        self.entity_renderer.render_player(
            player_x, 
            player_y, 
            visual_hash=self.game_state.visual_hash,
            visual_state=self.game_state.visual_state,
            facing_direction=self.game_state.facing_direction,
            is_moving=getattr(self.game_state, 'is_moving', False),
            move_progress=getattr(self.game_state, 'move_progress', 0.0)
        )
        
        # 6. Effects (hit splats, floating text)
        self.entity_renderer.render_effects(self.game_state.hit_splats, self.game_state.floating_messages)
        
        # 7. UI overlay
        self.ui_renderer.render(self.game_state)
        
        # 8. Debug info
        if self.config.debug.show_fps:
            self._render_debug_info()
        
        # Flip display
        pygame.display.flip()
        
        # Cap FPS
        self.clock.tick(self.fps)
        self.current_fps = self.clock.get_fps()
    
    def _render_debug_info(self) -> None:
        """Render debug information overlay."""
        fps_text = f"FPS: {self.current_fps:.1f}"
        text_surface = self.debug_font.render(fps_text, True, (255, 255, 0))
        self.screen.blit(text_surface, (10, 10))
        
        pos_text = f"Pos: ({self.game_state.position.get('x', 0)}, {self.game_state.position.get('y', 0)})"
        text_surface = self.debug_font.render(pos_text, True, (255, 255, 0))
        self.screen.blit(text_surface, (10, 30))
    
    def handle_resize(self, width: int, height: int) -> None:
        """Handle window resize."""
        self.screen = pygame.display.set_mode((width, height))
        self.camera.handle_resize(width, height)
        logger.info(f"Window resized to {width}x{height}")
    
    def cleanup(self) -> None:
        """Cleanup pygame resources."""
        pygame.quit()
        logger.info("Renderer cleaned up")
