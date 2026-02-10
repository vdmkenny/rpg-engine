"""
Entity renderer.

Renders players, NPCs, monsters, ground items, and effects using paperdoll sprites or fallback shapes.
"""

import pygame
from typing import Dict, Any, List, Tuple, Union, Optional
import time
import sys
from pathlib import Path

# Setup paths for protocol imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "common" / "src"))

from protocol import Direction
from ..config import get_config
from ..ui.colors import Colors
from .camera import Camera
from .paperdoll_renderer import PaperdollRenderer
from .sprite_manager import get_sprite_manager


class EntityRenderer:
    """Renders all game entities."""
    
    def __init__(self, screen: pygame.Surface, camera: Camera, tile_size: int):
        self.screen = screen
        self.camera = camera
        self.tile_size = tile_size
        
        # Animation timing
        self.move_animation_duration = 0.2  # seconds
        
        # Colors (fallback when sprites not loaded)
        self.player_color = (0, 150, 255)  # Blue
        self.other_player_color = (255, 200, 0)  # Yellow
        self.npc_color = (0, 200, 100)  # Green
        self.monster_color = (200, 50, 50)  # Red
        self.item_color = (255, 215, 0)  # Gold
        
        # Paperdoll rendering
        sprite_manager = get_sprite_manager()
        self.paperdoll_renderer = PaperdollRenderer(sprite_manager)
    
    def update(self, delta_time: float) -> None:
        """Update entity animations."""
        # Update movement animations, etc.
        pass
    
    def render_entities(self, entities: Dict[Union[int, str], Any]) -> None:
        """Render NPCs and monsters."""
        for entity_id, entity in entities.items():
            x = entity.get("x", 0)
            y = entity.get("y", 0)
            entity_type = entity.get("entity_type", "npc")
            
            # Get color based on type
            if entity_type == "monster":
                color = self.monster_color
            else:
                color = self.npc_color
            
            self._render_entity_at(x, y, color, entity.get("name", "?"))
    
    def render_other_players(self, other_players: Dict[int, Dict[str, Any]]) -> None:
        """Render other players with paperdoll sprites."""
        for player_id, player in other_players.items():
            x = player.get("position", {}).get("x", 0)
            y = player.get("position", {}).get("y", 0)
            username = player.get("username", "?")
            visual_hash = player.get("visual_hash")
            visual_state = player.get("visual_state")
            
            screen_x, screen_y = self.camera.tile_to_screen(x, y)
            if not self.camera.is_on_screen(x * self.tile_size, y * self.tile_size, margin=self.tile_size):
                continue
            
            # Render with paperdoll sprite
            sprite = None
            if visual_state and visual_hash:
                try:
                    direction = Direction[player.get("facing_direction", "DOWN").upper()]
                    sprite = self.paperdoll_renderer.get_idle_frame(
                        visual_state,
                        visual_hash,
                        direction,
                        render_size=48  # Larger sprite size (48px)
                    )
                except Exception as e:
                    import logging
                    logging.warning(f"Error rendering other player {username} sprite: {e}")
            
            # Blit sprite (required - no fallback)
            # Position sprite so character's feet are at the bottom-center of the tile
            # LPC sprites have the character at the bottom of the frame
            if sprite:
                # Center horizontally, align bottom with tile bottom
                sprite_x = int(screen_x + (self.tile_size - sprite.get_width()) // 2)
                sprite_y = int(screen_y + self.tile_size - sprite.get_height())
                self.screen.blit(sprite, (sprite_x, sprite_y))
            
            # Draw username label above entity
            font = pygame.font.SysFont("sans-serif", 9)
            text = font.render(username[:15], True, (255, 255, 255))
            text_rect = text.get_rect(center=(screen_x + self.tile_size / 2, screen_y - 5))
            self.screen.blit(text, text_rect)
    
    def render_player(self, x: int, y: int, visual_hash: Optional[str] = None, visual_state: Optional[Dict[str, Any]] = None, facing_direction: str = "DOWN", is_moving: bool = False, move_progress: float = 0.0) -> None:
        """Render the local player at the center of the screen using paperdoll sprites."""
        # Player is always at the center of the camera view
        center_x = self.screen.get_width() // 2
        center_y = self.screen.get_height() // 2
        
        # Render with paperdoll sprites
        sprite = None
        if visual_state and visual_hash:
            try:
                # Determine which animation to use
                if is_moving:
                    # Use walk animation with progress
                    direction = Direction[facing_direction.upper()]
                    sprite = self.paperdoll_renderer.get_walk_frame(
                        visual_state,
                        visual_hash,
                        direction,
                        progress=move_progress,
                        render_size=48  # Larger sprite size (48px)
                    )
                else:
                    # Use idle animation
                    direction = Direction[facing_direction.upper()]
                    sprite = self.paperdoll_renderer.get_idle_frame(
                        visual_state,
                        visual_hash,
                        direction,
                        render_size=48  # Larger sprite size (48px)
                    )
            except Exception as e:
                # Log error but continue rendering
                import logging
                logging.error(f"Error rendering player sprite: {e}")
        
        # Render sprite (required - no fallback to circles)
        # Position sprite so character's feet are at the bottom-center of the tile
        if sprite:
            # Center horizontally, align bottom with tile bottom
            sprite_x = int(center_x + (self.tile_size - sprite.get_width()) // 2)
            sprite_y = int(center_y + self.tile_size - sprite.get_height())
            self.screen.blit(sprite, (sprite_x, sprite_y))
        else:
            # Sprite unavailable - draw placeholder text instead of circle
            font = pygame.font.SysFont("monospace", 10)
            text = font.render("(Loading...)", True, Colors.TEXT_GRAY)
            self.screen.blit(text, (center_x - text.get_width() // 2, center_y - text.get_height() // 2))
    
    def render_ground_items(self, ground_items: Dict[str, Dict[str, Any]]) -> None:
        """Render items on the ground."""
        for item_id, item in ground_items.items():
            x = item.get("x", 0)
            y = item.get("y", 0)
            
            screen_x, screen_y = self.camera.tile_to_screen(x, y)
            center_x = int(screen_x + self.tile_size / 2)
            center_y = int(screen_y + self.tile_size / 2)
            
            # Draw item marker (small circle)
            radius = 4
            pygame.draw.circle(self.screen, self.item_color, (center_x, center_y), radius)
            pygame.draw.circle(self.screen, (255, 255, 255), (center_x, center_y), radius, 1)
    
    def render_effects(self, hit_splats: List[Any], floating_messages: List[Dict[str, Any]]) -> None:
        """Render visual effects like hit splats and floating text."""
        current_time = time.time()
        
        # Render hit splats
        for splat in hit_splats:
            if hasattr(splat, 'is_expired') and splat.is_expired(current_time):
                continue
            
            target_id = getattr(splat, 'target_id', None)
            damage = getattr(splat, 'damage', 0)
            is_miss = getattr(splat, 'is_miss', False)
            is_heal = getattr(splat, 'is_heal', False)
            
            # Get position (for now, use player position for own splats)
            if target_id is None or target_id == "self":
                screen_x = self.screen.get_width() // 2
                screen_y = self.screen.get_height() // 2 - 20
            else:
                # For other targets, would need to look up their position
                continue
            
            self._render_hit_splat(screen_x, screen_y, damage, is_miss, is_heal)
        
        # Render floating messages
        for msg in floating_messages:
            message = msg.get("message", "")
            timestamp = msg.get("timestamp", 0)
            duration = msg.get("duration", 3.0)
            
            age = current_time - timestamp
            if age > duration:
                continue
            
            # Calculate position with float-up effect
            x = self.screen.get_width() // 2
            y = self.screen.get_height() // 2 - 40 - int(age * 20)
            
            # Fade out
            alpha = max(0, 255 - int((age / duration) * 255))
            
            self._render_floating_text(x, y, message, alpha)
    
    def _render_entity_at(self, tile_x: int, tile_y: int, color: Tuple[int, int, int], label: str) -> None:
        """Render a single entity at tile coordinates."""
        screen_x, screen_y = self.camera.tile_to_screen(tile_x, tile_y)
        
        # Check if on screen
        if not self.camera.is_on_screen(tile_x * self.tile_size, tile_y * self.tile_size, margin=self.tile_size):
            return
        
        # Draw entity body
        size = self.tile_size - 6
        rect = pygame.Rect(
            int(screen_x + 3),
            int(screen_y + 3),
            size,
            size
        )
        
        pygame.draw.ellipse(self.screen, color, rect)
        pygame.draw.ellipse(self.screen, (50, 50, 50), rect, 1)
        
        # Draw label
        font = pygame.font.SysFont("sans-serif", 9)
        text = font.render(label[:10], True, (255, 255, 255))
        text_rect = text.get_rect(center=(screen_x + self.tile_size / 2, screen_y - 5))
        self.screen.blit(text, text_rect)
    
    def _render_hit_splat(self, x: int, y: int, damage: int, is_miss: bool, is_heal: bool) -> None:
        """Render a hit splat."""
        if is_miss:
            text = "MISS"
            color = (200, 200, 200)
            bg_color = (100, 100, 100)
        elif is_heal:
            text = f"+{damage}"
            color = (255, 255, 255)
            bg_color = (0, 200, 0)
        else:
            text = str(damage)
            color = (255, 255, 255)
            bg_color = (200, 0, 0)
        
        # Draw background
        font = pygame.font.SysFont("sans-serif", 14, bold=True)
        text_surface = font.render(text, True, color)
        text_rect = text_surface.get_rect(center=(x, y))
        
        padding = 4
        bg_rect = text_rect.inflate(padding * 2, padding * 2)
        pygame.draw.rect(self.screen, bg_color, bg_rect, border_radius=4)
        pygame.draw.rect(self.screen, (50, 50, 50), bg_rect, 1, border_radius=4)
        
        # Draw text
        self.screen.blit(text_surface, text_rect)
    
    def _render_floating_text(self, x: int, y: int, text: str, alpha: int) -> None:
        """Render floating text with transparency."""
        font = pygame.font.SysFont("sans-serif", 12)
        text_surface = font.render(text, True, (255, 255, 200))
        
        # Set alpha
        text_surface.set_alpha(alpha)
        
        text_rect = text_surface.get_rect(center=(x, y))
        self.screen.blit(text_surface, text_rect)
