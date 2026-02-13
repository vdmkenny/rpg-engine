"""
Entity renderer.

Renders players, NPCs, monsters, ground items, and effects using paperdoll sprites or fallback shapes.
"""

import pygame
from typing import Dict, Any, List, Tuple, Union, Optional
import time

from protocol import Direction
from ..config import get_config
from ..ui.colors import Colors
from .camera import Camera
from .paperdoll_renderer import PaperdollRenderer
from .sprite_manager import get_sprite_manager
from .icon_manager import get_icon_manager


class EntityRenderer:
    """Renders all game entities."""
    
    def __init__(self, screen: pygame.Surface, camera: Camera, tile_size: int):
        self.screen = screen
        self.camera = camera
        self.tile_size = tile_size
        
        # Animation timing
        config = get_config()
        self.move_animation_duration = config.game.move_duration
        
        # Colors (fallback when sprites not loaded)
        self.player_color = (0, 150, 255)  # Blue
        self.other_player_color = (255, 200, 0)  # Yellow
        self.npc_color = (0, 200, 100)  # Green
        self.monster_color = (200, 50, 50)  # Red
        self.item_color = (255, 215, 0)  # Gold
        
        # Paperdoll rendering
        sprite_manager = get_sprite_manager()
        self.paperdoll_renderer = PaperdollRenderer(sprite_manager)
        
        # Cached fonts (created once, reused for performance)
        self.label_font = pygame.font.SysFont("sans-serif", 9)
        self.hit_splat_font = pygame.font.SysFont("sans-serif", 14, bold=True)
        self.float_font = pygame.font.SysFont("sans-serif", 12)
        self.loading_font = pygame.font.SysFont("monospace", 10)
    
    def update(self, delta_time: float) -> None:
        """Update entity animations."""
        from ..game.client_state import get_game_state
        game_state = get_game_state()
        
        # Update other player movement interpolation
        for player_id, player in game_state.other_players.items():
            if player.get("is_moving"):
                player["move_progress"] = player.get("move_progress", 0.0) + delta_time / self.move_animation_duration
                if player["move_progress"] >= 1.0:
                    player["move_progress"] = 1.0
                    player["is_moving"] = False
        
        # Update entity movement interpolation
        for entity_id, entity in game_state.entities.items():
            if entity.is_moving:
                entity.move_progress += delta_time / self.move_animation_duration
                if entity.move_progress >= 1.0:
                    entity.move_progress = 1.0
                    entity.is_moving = False
    
    def render_all_sorted(
        self,
        entities: Dict[Union[int, str], Any],
        other_players: Dict[int, Dict[str, Any]],
        local_player: Dict[str, Any]
    ) -> None:
        """
        Render all entities (NPCs, other players, local player) sorted by Y position.
        
        Entities with lower Y (higher on screen) are rendered first (behind).
        Entities with higher Y (lower on screen) are rendered last (in front).
        """
        # Build list of all renderable objects with their Y positions
        render_list: List[Tuple[float, str, Any, Any]] = []  # (y, type, id/data, extra)
        
        # 1. NPCs and monsters
        for entity_id, entity in entities.items():
            # Get interpolated Y position if moving
            if entity.is_moving:
                t = entity.move_progress
                start_y = entity.start_y
                target_y = entity.target_y
                y = start_y + (target_y - start_y) * t
            else:
                y = entity.y
            render_list.append((y, "entity", entity_id, entity))
        
        # 2. Other players
        for player_id, player in other_players.items():
            # Get interpolated Y position
            if player.get("is_moving"):
                t = player.get("move_progress", 0.0)
                start_y = player.get("move_start_y", 0)
                target_y = player.get("position", {}).get("y", 0)
                y = start_y + (target_y - start_y) * t
            else:
                y = player.get("position", {}).get("y", 0)
            render_list.append((y, "other_player", player_id, player))
        
        # 3. Local player
        local_y = local_player.get("y", 0)
        render_list.append((local_y, "local_player", None, local_player))
        
        # Sort by Y position ascending (top to bottom)
        render_list.sort(key=lambda item: item[0])
        
        # Render in sorted order
        for y, entity_type, entity_id, data in render_list:
            if entity_type == "entity":
                self._render_single_entity(entity_id, data)
            elif entity_type == "other_player":
                self._render_single_other_player(entity_id, data)
            elif entity_type == "local_player":
                self._render_single_local_player(data)
    
    def _render_single_entity(self, entity_id: Union[int, str], entity) -> None:
        """Render a single NPC/monster entity with paperdoll if available."""
        # Use interpolated position if moving
        if entity.is_moving:
            t = entity.move_progress
            x = entity.start_x + (entity.target_x - entity.start_x) * t
            y = entity.start_y + (entity.target_y - entity.start_y) * t
        else:
            x = entity.x
            y = entity.y
        entity_type = entity.entity_type
        
        # Check if entity has paperdoll data (humanoid NPCs)
        visual_hash = entity.visual_hash
        visual_state = entity.visual_state
        
        if visual_state and visual_hash:
            # Render humanoid NPC with paperdoll sprite
            screen_x, screen_y = self.camera.tile_to_screen(x, y)
            if not self.camera.is_on_screen(x * self.tile_size, y * self.tile_size, margin=self.tile_size):
                return
            
            # Render with paperdoll sprite
            sprite = None
            try:
                direction = Direction[entity.facing_direction.upper()]
                if entity.is_moving:
                    sprite = self.paperdoll_renderer.get_walk_frame(
                        visual_state, visual_hash, direction,
                        progress=entity.move_progress, render_size=64
                    )
                else:
                    sprite = self.paperdoll_renderer.get_idle_frame(
                        visual_state, visual_hash, direction, render_size=64
                    )
            except Exception as e:
                import logging
                logging.warning(f"Error rendering entity {entity_id} sprite: {e}")
            
            # Blit sprite
            if sprite:
                sprite_x = int(screen_x + (self.tile_size - sprite.get_width()) // 2)
                sprite_y = int(screen_y + self.tile_size - sprite.get_height())
                self.screen.blit(sprite, (sprite_x, sprite_y))
            else:
                # Fallback to colored shape
                self._render_entity_at(x, y, self.npc_color, entity.name)
            
            # Draw entity name label
            text = self.label_font.render(entity.name[:20], True, (255, 255, 255))
            text_rect = text.get_rect(center=(screen_x + self.tile_size / 2, screen_y - 37))
            self.screen.blit(text, text_rect)
        else:
            # Legacy rendering for monsters without paperdoll data
            if entity_type.value == "monster":
                color = self.monster_color
            else:
                color = self.npc_color
            
            self._render_entity_at(x, y, color, entity.name)
    
    def _render_single_other_player(self, player_id: int, player: Dict[str, Any]) -> None:
        """Render a single other player with paperdoll sprite."""
        # Get position with interpolation
        if player.get("is_moving"):
            t = player.get("move_progress", 0.0)
            start_x = player.get("move_start_x", 0)
            start_y = player.get("move_start_y", 0)
            target_x = player.get("position", {}).get("x", 0)
            target_y = player.get("position", {}).get("y", 0)
            x = start_x + (target_x - start_x) * t
            y = start_y + (target_y - start_y) * t
        else:
            x = player.get("position", {}).get("x", 0)
            y = player.get("position", {}).get("y", 0)
        
        username = player.get("username", "?")
        visual_hash = player.get("visual_hash")
        visual_state = player.get("visual_state")
        
        screen_x, screen_y = self.camera.tile_to_screen(x, y)
        if not self.camera.is_on_screen(x * self.tile_size, y * self.tile_size, margin=self.tile_size):
            return
        
        # Render with paperdoll sprite
        sprite = None
        if visual_state and visual_hash:
            try:
                direction = Direction[player.get("facing_direction", "DOWN").upper()]
                if player.get("is_moving"):
                    progress = player.get("move_progress", 0.0)
                    sprite = self.paperdoll_renderer.get_walk_frame(
                        visual_state, visual_hash, direction,
                        progress=progress, render_size=64
                    )
                else:
                    sprite = self.paperdoll_renderer.get_idle_frame(
                        visual_state, visual_hash, direction, render_size=64
                    )
            except Exception as e:
                import logging
                logging.warning(f"Error rendering other player {username} sprite: {e}")
        
        # Blit sprite
        if sprite:
            sprite_x = int(screen_x + (self.tile_size - sprite.get_width()) // 2)
            sprite_y = int(screen_y + self.tile_size - sprite.get_height())
            self.screen.blit(sprite, (sprite_x, sprite_y))
        
        # Draw username label
        text = self.label_font.render(username[:15], True, (255, 255, 255))
        text_rect = text.get_rect(center=(screen_x + self.tile_size / 2, screen_y - 37))
        self.screen.blit(text, text_rect)
    
    def _render_single_local_player(self, player: Dict[str, Any]) -> None:
        """Render the local player at the center of the screen."""
        # Player is always at the center of the camera view
        center_x = self.screen.get_width() // 2
        center_y = self.screen.get_height() // 2
        
        visual_hash = player.get("visual_hash")
        visual_state = player.get("visual_state")
        facing_direction = player.get("facing_direction", "DOWN")
        is_moving = player.get("is_moving", False)
        move_progress = player.get("move_progress", 0.0)
        
        # Render with paperdoll sprite
        sprite = None
        if visual_state and visual_hash:
            try:
                direction = Direction[facing_direction.upper()]
                if is_moving:
                    sprite = self.paperdoll_renderer.get_walk_frame(
                        visual_state, visual_hash, direction,
                        progress=move_progress, render_size=64
                    )
                else:
                    sprite = self.paperdoll_renderer.get_idle_frame(
                        visual_state, visual_hash, direction, render_size=64
                    )
            except Exception as e:
                import logging
                logging.error(f"Error rendering player sprite: {e}")
        
        # Blit sprite
        if sprite:
            sprite_x = int(center_x + (self.tile_size - sprite.get_width()) // 2)
            sprite_y = int(center_y + self.tile_size - sprite.get_height())
            self.screen.blit(sprite, (sprite_x, sprite_y))
        else:
            # Sprite unavailable - draw placeholder
            text = self.loading_font.render("(Loading...)", True, Colors.TEXT_GRAY)
            self.screen.blit(text, (center_x - text.get_width() // 2, center_y - text.get_height() // 2))
    
    def render_ground_items(self, ground_items: Dict[str, Dict[str, Any]]) -> None:
        """Render items on the ground using icons."""
        icon_manager = get_icon_manager()
        
        for item_id, item in ground_items.items():
            x = item.get("x", 0)
            y = item.get("y", 0)
            
            screen_x, screen_y = self.camera.tile_to_screen(x, y)
            center_x = int(screen_x + self.tile_size / 2)
            center_y = int(screen_y + self.tile_size / 2)
            
            # Try to render icon if available
            icon_sprite_id = item.get("icon_sprite_id")
            if icon_manager and icon_sprite_id:
                # Synchronously check cache (non-blocking)
                icon_surface = icon_manager.get_icon_surface_sync(icon_sprite_id)
                if icon_surface:
                    # Center the icon on the tile
                    icon_x = center_x - icon_surface.get_width() // 2
                    icon_y = center_y - icon_surface.get_height() // 2
                    self.screen.blit(icon_surface, (icon_x, icon_y))
                    continue
                else:
                    # Not cached - schedule background download
                    icon_manager.schedule_download(icon_sprite_id)
            
            # Fallback: draw item marker (small circle)
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
        text = self.label_font.render(label[:10], True, (255, 255, 255))
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
        text_surface = self.hit_splat_font.render(text, True, color)
        text_rect = text_surface.get_rect(center=(x, y))
        
        padding = 4
        bg_rect = text_rect.inflate(padding * 2, padding * 2)
        pygame.draw.rect(self.screen, bg_color, bg_rect, border_radius=4)
        pygame.draw.rect(self.screen, (50, 50, 50), bg_rect, 1, border_radius=4)
        
        # Draw text
        self.screen.blit(text_surface, text_rect)
    
    def _render_floating_text(self, x: int, y: int, text: str, alpha: int) -> None:
        """Render floating text with transparency."""
        text_surface = self.float_font.render(text, True, (255, 255, 200))
        
        # Set alpha
        text_surface.set_alpha(alpha)
        
        text_rect = text_surface.get_rect(center=(x, y))
        self.screen.blit(text_surface, text_rect)
