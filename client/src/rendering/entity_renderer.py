"""
Entity renderer.

Renders players, NPCs, monsters, ground items, and effects using paperdoll sprites or fallback shapes.
"""

import pygame
from typing import Dict, Any, List, Tuple, Union, Optional
import logging
import time

from protocol import Direction
from sprites.enums import AnimationType, BodyType
from sprites.animation import AnimationState, ANIMATION_CONFIGS
from ..config import get_config
from ..ui.colors import Colors
from .camera import Camera
from .paperdoll_renderer import PaperdollRenderer
from .sprite_manager import get_sprite_manager, FRAME_SIZE
from .icon_manager import get_icon_manager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Layout constants (pixel values at native game-surface resolution, pre-zoom)
# ---------------------------------------------------------------------------

# Health bar
HEALTH_BAR_WIDTH = 30
HEALTH_BAR_HEIGHT = 4
HEALTH_BAR_Y_OFFSET = 6       # Gap between health bar bottom and label top

# Name labels
LABEL_Y_OFFSET = 37            # Pixels above tile top for entity/player name labels
LABEL_MAX_CHARS_ENTITY = 20    # Max characters shown in NPC/monster name
LABEL_MAX_CHARS_PLAYER = 15    # Max characters shown in player username

# Fallback entity ellipse (used when paperdoll sprites are unavailable)
FALLBACK_INSET = 3             # Inset from tile edges for fallback ellipse
FALLBACK_LABEL_Y_OFFSET = 5   # Pixels above tile top for fallback label
FALLBACK_HEALTH_BAR_Y = 10    # Pixels above tile top for fallback health bar

# Ground item fallback marker
GROUND_ITEM_RADIUS = 4        # Circle radius for items without an icon
GROUND_ITEM_OUTLINE_WIDTH = 1  # Outline stroke width

# Hit splat styling
HIT_SPLAT_Y_OFFSET = 20       # Pixels above entity center for hit splat
HIT_SPLAT_PADDING = 4         # Padding around hit splat text
HIT_SPLAT_BORDER_RADIUS = 4   # Rounded corner radius
HIT_SPLAT_BORDER_WIDTH = 1    # Outline stroke width

# Floating combat messages
FLOAT_MSG_INITIAL_Y = 40      # Starting Y offset above screen center
FLOAT_MSG_RISE_SPEED = 20     # Pixels per second the message floats upward
FLOAT_MSG_STAGGER = 14        # Vertical spacing between stacked messages

# Font sizes
FONT_SIZE_LABEL = 9
FONT_SIZE_HIT_SPLAT = 14
FONT_SIZE_FLOAT = 12
FONT_SIZE_LOADING = 10

# Movement interpolation
MOVE_PROGRESS_COMPLETE = 1.0


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
        self.player_color = Colors.ENTITY_PLAYER
        self.other_player_color = Colors.ENTITY_OTHER_PLAYER
        self.npc_color = Colors.ENTITY_NPC
        self.monster_color = Colors.ENTITY_MONSTER
        self.item_color = Colors.ENTITY_ITEM
        
        # Paperdoll rendering
        sprite_manager = get_sprite_manager()
        self.paperdoll_renderer = PaperdollRenderer(sprite_manager)
        
        # Cached fonts (created once, reused for performance)
        self.label_font = pygame.font.SysFont("sans-serif", FONT_SIZE_LABEL)
        self.hit_splat_font = pygame.font.SysFont("sans-serif", FONT_SIZE_HIT_SPLAT, bold=True)
        self.float_font = pygame.font.SysFont("sans-serif", FONT_SIZE_FLOAT)
        self.loading_font = pygame.font.SysFont("monospace", FONT_SIZE_LOADING)
    
    def update(self, delta_time: float) -> None:
        """Update entity movement interpolation and animation states."""
        from ..game.client_state import get_game_state
        game_state = get_game_state()
        
        # Default body type for animation updates (used by AnimationState)
        default_body = BodyType.MALE
        
        # Update other player movement interpolation and animation
        for player_id, player in game_state.other_players.items():
            if player.get("is_moving"):
                player["move_progress"] = player.get("move_progress", 0.0) + delta_time / self.move_animation_duration
                if player["move_progress"] >= MOVE_PROGRESS_COMPLETE:
                    player["move_progress"] = MOVE_PROGRESS_COMPLETE
                    player["is_moving"] = False
            
            # Drive animation state for other players
            entity_id = f"player_{player_id}"
            anim = game_state.get_anim_state(entity_id)
            self._update_animation_state(
                anim, default_body, delta_time,
                is_moving=player.get("is_moving", False),
                in_combat=game_state.is_in_combat(entity_id),
            )
        
        # Update entity movement interpolation and animation
        for entity_id, entity in game_state.entities.items():
            if entity.is_moving:
                entity.move_progress += delta_time / self.move_animation_duration
                if entity.move_progress >= MOVE_PROGRESS_COMPLETE:
                    entity.move_progress = MOVE_PROGRESS_COMPLETE
                    entity.is_moving = False
            
            # Drive animation state for entities
            body = self._get_body_type(entity.visual_state) if entity.visual_state else default_body
            self._update_animation_state(
                entity.anim_state, body, delta_time,
                is_moving=entity.is_moving,
                in_combat=entity.state == "combat" or game_state.is_in_combat(entity.entity_id),
            )
        
        # Drive local player animation state
        local_anim = game_state.local_anim_state
        local_entity_id = f"player_{game_state.player_id}" if game_state.player_id else None
        local_in_combat = False
        if local_entity_id:
            local_in_combat = game_state.is_in_combat(local_entity_id)
        self._update_animation_state(
            local_anim, default_body, delta_time,
            is_moving=game_state.is_moving,
            in_combat=local_in_combat,
        )
    
    @staticmethod
    def _get_body_type(visual_state: Optional[Dict[str, Any]]) -> BodyType:
        """Extract BodyType from visual state dict."""
        if visual_state:
            body_str = visual_state.get("body_type", "male")
            try:
                return BodyType(body_str)
            except ValueError:
                pass
        return BodyType.MALE
    
    @staticmethod
    def _update_animation_state(
        anim: AnimationState,
        body_type: BodyType,
        dt: float,
        is_moving: bool,
        in_combat: bool,
    ) -> None:
        """
        Drive animation state transitions.
        
        State machine:
          - Moving -> WALK (always overrides)
          - One-shot finished (SLASH) -> transition to COMBAT_IDLE or IDLE
          - One-shot playing (SLASH) -> let it finish
          - In combat, not moving -> COMBAT_IDLE
          - Not in combat, not moving -> IDLE (transitions from WALK on stop)
        """
        current = anim.animation
        
        if is_moving:
            # Movement always takes priority
            if current != AnimationType.WALK:
                anim.play(AnimationType.WALK, reset=True)
        elif anim.finished:
            # One-shot animation finished, transition to appropriate idle
            if in_combat:
                anim.play(AnimationType.COMBAT_IDLE, reset=True)
            else:
                anim.play(AnimationType.IDLE, reset=True)
        elif current == AnimationType.SLASH:
            # One-shot in progress, let it play out
            pass
        elif in_combat:
            if current != AnimationType.COMBAT_IDLE:
                anim.play(AnimationType.COMBAT_IDLE, reset=False)
        else:
            if current != AnimationType.IDLE:
                anim.play(AnimationType.IDLE, reset=False)
        
        # Advance the animation timer
        anim.update(dt, body_type)
    
    # =========================================================================
    # SPRITE POSITIONING
    # =========================================================================

    def _sprite_blit_pos(
        self, sprite: pygame.Surface, anchor_x: float, anchor_y: float
    ) -> Tuple[int, int]:
        """
        Calculate blit position so a sprite's feet align with the tile bottom.

        The anchor point (anchor_x, anchor_y) is the top-left of the tile the
        entity occupies.

        Standard sprites (FRAME_SIZE x FRAME_SIZE, typically 64x64) are
        horizontally centered on the tile with feet bottom-aligned to the tile
        bottom.  The head extends above the tile.

        Oversize sprites (e.g. 128x128 attack_slash) have the body in the
        center FRAME_SIZE region.  The blit position is calculated so that the
        body portion lands in the same place as a standard sprite, with the
        weapon art extending beyond.
        """
        sw, sh = sprite.get_width(), sprite.get_height()

        # Standard body position: centered on tile, feet at tile bottom
        body_x = anchor_x + (self.tile_size - FRAME_SIZE) / 2
        body_y = anchor_y + self.tile_size - FRAME_SIZE

        # Offset from frame origin to the body region within the sprite
        body_offset_x = (sw - FRAME_SIZE) // 2 if sw > FRAME_SIZE else 0
        body_offset_y = (sh - FRAME_SIZE) // 2 if sh > FRAME_SIZE else 0

        sprite_x = body_x - body_offset_x
        sprite_y = body_y - body_offset_y

        return int(sprite_x), int(sprite_y)
    
    # =========================================================================
    # Y-SORTED RENDER ENTRY POINT
    # =========================================================================

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
    
    # =========================================================================
    # INDIVIDUAL ENTITY RENDERING
    # =========================================================================

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
            
            # Render with paperdoll sprite using animation state
            sprite = None
            try:
                direction = Direction[entity.facing_direction.upper()]
                anim = entity.anim_state
                if entity.is_moving:
                    sprite = self.paperdoll_renderer.get_walk_frame(
                        visual_state, visual_hash, direction,
                        progress=entity.move_progress, render_size=FRAME_SIZE
                    )
                else:
                    sprite = self.paperdoll_renderer.get_frame(
                        visual_state, visual_hash,
                        anim.animation, direction,
                        frame=anim.sprite_frame, render_size=FRAME_SIZE
                    )
            except Exception as e:
                logger.warning(
                    "Error rendering entity sprite",
                    extra={"entity_id": entity_id, "error": str(e)},
                )
            
            if sprite:
                blit_x, blit_y = self._sprite_blit_pos(sprite, screen_x, screen_y)
                self.screen.blit(sprite, (blit_x, blit_y))
            else:
                # Fallback to colored shape
                self._render_entity_at(x, y, self.npc_color, entity.name)
            
            # Draw entity name label
            tile_center_x = screen_x + self.tile_size / 2
            text = self.label_font.render(entity.name[:LABEL_MAX_CHARS_ENTITY], True, Colors.TEXT_WHITE)
            text_rect = text.get_rect(center=(tile_center_x, screen_y - LABEL_Y_OFFSET))
            self.screen.blit(text, text_rect)
            
            # Draw health bar above name when entity is in combat
            from ..game.client_state import get_game_state
            gs = get_game_state()
            if gs.is_in_combat(entity.entity_id):
                self._render_health_bar(
                    int(tile_center_x),
                    text_rect.top,
                    entity.current_hp,
                    entity.max_hp
                )
        else:
            # Legacy rendering for monsters without paperdoll data
            if entity_type.value == "monster":
                color = self.monster_color
            else:
                color = self.npc_color
            
            self._render_entity_at(x, y, color, entity.name)
            
            # Draw health bar for fallback entities in combat
            from ..game.client_state import get_game_state
            gs = get_game_state()
            if gs.is_in_combat(entity.entity_id):
                screen_x, screen_y = self.camera.tile_to_screen(x, y)
                self._render_health_bar(
                    int(screen_x + self.tile_size / 2),
                    int(screen_y - FALLBACK_HEALTH_BAR_Y),
                    entity.current_hp,
                    entity.max_hp
                )
    
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
        
        # Render with paperdoll sprite using animation state
        sprite = None
        if visual_state and visual_hash:
            try:
                direction = Direction[player.get("facing_direction", "DOWN").upper()]
                entity_id_str = f"player_{player_id}"
                from ..game.client_state import get_game_state
                anim = get_game_state().get_anim_state(entity_id_str)
                if player.get("is_moving"):
                    progress = player.get("move_progress", 0.0)
                    sprite = self.paperdoll_renderer.get_walk_frame(
                        visual_state, visual_hash, direction,
                        progress=progress, render_size=FRAME_SIZE
                    )
                else:
                    sprite = self.paperdoll_renderer.get_frame(
                        visual_state, visual_hash,
                        anim.animation, direction,
                        frame=anim.sprite_frame, render_size=FRAME_SIZE
                    )
            except Exception as e:
                logger.warning(
                    "Error rendering other player sprite",
                    extra={"username": username, "error": str(e)},
                )
        
        if sprite:
            blit_x, blit_y = self._sprite_blit_pos(sprite, screen_x, screen_y)
            self.screen.blit(sprite, (blit_x, blit_y))
        
        # Draw username label
        tile_center_x = screen_x + self.tile_size / 2
        text = self.label_font.render(username[:LABEL_MAX_CHARS_PLAYER], True, Colors.TEXT_WHITE)
        text_rect = text.get_rect(center=(tile_center_x, screen_y - LABEL_Y_OFFSET))
        self.screen.blit(text, text_rect)
        
        # Draw health bar above name when player is in combat
        from ..game.client_state import get_game_state
        gs = get_game_state()
        player_entity_id = f"player_{player_id}"
        if gs.is_in_combat(player_entity_id):
            current_hp = player.get("current_hp", 0)
            max_hp = player.get("max_hp", 1)
            self._render_health_bar(
                int(tile_center_x),
                text_rect.top,
                current_hp,
                max_hp
            )
    
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
        
        # Render with paperdoll sprite using animation state
        sprite = None
        if visual_state and visual_hash:
            try:
                direction = Direction[facing_direction.upper()]
                from ..game.client_state import get_game_state
                anim = get_game_state().local_anim_state
                if is_moving:
                    sprite = self.paperdoll_renderer.get_walk_frame(
                        visual_state, visual_hash, direction,
                        progress=move_progress, render_size=FRAME_SIZE
                    )
                else:
                    sprite = self.paperdoll_renderer.get_frame(
                        visual_state, visual_hash,
                        anim.animation, direction,
                        frame=anim.sprite_frame, render_size=FRAME_SIZE
                    )
            except Exception as e:
                logger.error(
                    "Error rendering player sprite",
                    extra={"error": str(e)},
                )
        
        if sprite:
            blit_x, blit_y = self._sprite_blit_pos(sprite, center_x, center_y)
            self.screen.blit(sprite, (blit_x, blit_y))
        else:
            # Sprite unavailable - draw placeholder
            text = self.loading_font.render("(Loading...)", True, Colors.TEXT_GRAY)
            self.screen.blit(text, (center_x - text.get_width() // 2, center_y - text.get_height() // 2))
        
        # Draw health bar above local player when in combat
        from ..game.client_state import get_game_state
        gs = get_game_state()
        if gs.player_id is not None:
            local_entity_id = f"player_{gs.player_id}"
            if gs.is_in_combat(local_entity_id):
                tile_center_x = int(center_x + self.tile_size / 2)
                label_top_y = int(center_y - LABEL_Y_OFFSET)
                self._render_health_bar(
                    tile_center_x,
                    label_top_y - HEALTH_BAR_Y_OFFSET,
                    gs.current_hp,
                    gs.max_hp
                )
    
    # =========================================================================
    # GROUND ITEMS
    # =========================================================================

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
            pygame.draw.circle(self.screen, self.item_color, (center_x, center_y), GROUND_ITEM_RADIUS)
            pygame.draw.circle(self.screen, Colors.WHITE, (center_x, center_y), GROUND_ITEM_RADIUS, GROUND_ITEM_OUTLINE_WIDTH)
    
    # =========================================================================
    # VISUAL EFFECTS
    # =========================================================================

    def render_effects(self, hit_splats: List[Any], floating_messages: List[Dict[str, Any]]) -> None:
        """Render visual effects like hit splats and floating text."""
        from ..game.client_state import get_game_state
        game_state = get_game_state()
        current_time = time.time()
        
        # Render hit splats
        for splat in hit_splats:
            if hasattr(splat, 'is_expired') and splat.is_expired(current_time):
                continue
            
            target_id = getattr(splat, 'target_id', None)
            damage = getattr(splat, 'damage', 0)
            is_miss = getattr(splat, 'is_miss', False)
            is_heal = getattr(splat, 'is_heal', False)
            
            screen_x, screen_y = self._get_entity_screen_position(target_id, game_state)
            if screen_x is None:
                continue
            
            self._render_hit_splat(screen_x, screen_y - HIT_SPLAT_Y_OFFSET, damage, is_miss, is_heal)
        
        # Render floating messages (rise from player and fade)
        for idx, msg in enumerate(floating_messages):
            message = msg.get("message", "")
            timestamp = msg.get("timestamp", 0)
            duration = msg.get("duration", 3.0)
            
            age = current_time - timestamp
            if age > duration:
                continue
            
            # Stagger vertically so multiple messages don't overlap
            x = self.screen.get_width() // 2
            y = self.screen.get_height() // 2 - FLOAT_MSG_INITIAL_Y - int(age * FLOAT_MSG_RISE_SPEED) - (idx * FLOAT_MSG_STAGGER)
            
            # Fade out
            alpha = max(0, 255 - int((age / duration) * 255))
            
            self._render_floating_text(x, y, message, alpha)
    
    # =========================================================================
    # HELPERS
    # =========================================================================

    def _get_entity_screen_position(self, entity_id, game_state) -> tuple:
        """Get screen position for an entity by its ID. Returns (screen_x, screen_y) or (None, None)."""
        if entity_id is None:
            return (None, None)
        
        # Check if this is the local player
        local_player_id = game_state.player_id
        if local_player_id is not None:
            local_entity_id = f"player_{local_player_id}"
            if entity_id == local_entity_id or entity_id == "self":
                return (self.screen.get_width() // 2, self.screen.get_height() // 2)
        
        # Check entities (NPCs/monsters)
        if entity_id in game_state.entities:
            entity = game_state.entities[entity_id]
            if entity.is_moving:
                t = entity.move_progress
                x = entity.start_x + (entity.target_x - entity.start_x) * t
                y = entity.start_y + (entity.target_y - entity.start_y) * t
            else:
                x = entity.x
                y = entity.y
            screen_x, screen_y = self.camera.tile_to_screen(x, y)
            return (int(screen_x + self.tile_size / 2), int(screen_y))
        
        # Check other players (entity_id format: "player_{id}")
        if isinstance(entity_id, str) and entity_id.startswith("player_"):
            try:
                pid = int(entity_id.split("_", 1)[1])
            except (ValueError, IndexError):
                return (None, None)
            if pid in game_state.other_players:
                player = game_state.other_players[pid]
                if player.get("is_moving"):
                    t = player.get("move_progress", 0.0)
                    sx = player.get("move_start_x", 0)
                    sy = player.get("move_start_y", 0)
                    tx = player.get("position", {}).get("x", 0)
                    ty = player.get("position", {}).get("y", 0)
                    x = sx + (tx - sx) * t
                    y = sy + (ty - sy) * t
                else:
                    x = player.get("position", {}).get("x", 0)
                    y = player.get("position", {}).get("y", 0)
                screen_x, screen_y = self.camera.tile_to_screen(x, y)
                return (int(screen_x + self.tile_size / 2), int(screen_y))
        
        return (None, None)
    
    def _render_health_bar(self, center_x: int, top_y: int, current_hp: int, max_hp: int) -> None:
        """Render a health bar above an entity in combat."""
        if max_hp <= 0:
            return
        
        hp_ratio = max(0.0, min(1.0, current_hp / max_hp))
        bar_x = int(center_x - HEALTH_BAR_WIDTH / 2)
        bar_y = int(top_y - HEALTH_BAR_Y_OFFSET)
        
        # Background (black)
        pygame.draw.rect(self.screen, Colors.HP_BG, (bar_x, bar_y, HEALTH_BAR_WIDTH, HEALTH_BAR_HEIGHT))
        
        # HP fill (green to red gradient based on HP%)
        fill_width = int(HEALTH_BAR_WIDTH * hp_ratio)
        if fill_width > 0:
            r = int(255 * (1 - hp_ratio))
            g = int(255 * hp_ratio)
            hp_color = (r, g, 0)
            pygame.draw.rect(self.screen, hp_color, (bar_x, bar_y, fill_width, HEALTH_BAR_HEIGHT))
        
        # Border (dark outline)
        pygame.draw.rect(self.screen, Colors.HP_BORDER, (bar_x, bar_y, HEALTH_BAR_WIDTH, HEALTH_BAR_HEIGHT), 1)
    
    def _render_entity_at(self, tile_x: int, tile_y: int, color: Tuple[int, int, int], label: str) -> None:
        """Render a single entity at tile coordinates using fallback ellipse."""
        screen_x, screen_y = self.camera.tile_to_screen(tile_x, tile_y)
        
        # Check if on screen
        if not self.camera.is_on_screen(tile_x * self.tile_size, tile_y * self.tile_size, margin=self.tile_size):
            return
        
        # Draw entity body
        size = self.tile_size - FALLBACK_INSET * 2
        rect = pygame.Rect(
            int(screen_x + FALLBACK_INSET),
            int(screen_y + FALLBACK_INSET),
            size,
            size
        )
        
        pygame.draw.ellipse(self.screen, color, rect)
        pygame.draw.ellipse(self.screen, Colors.ENTITY_FALLBACK_BORDER, rect, 1)
        
        # Draw label
        text = self.label_font.render(label[:LABEL_MAX_CHARS_ENTITY], True, Colors.TEXT_WHITE)
        text_rect = text.get_rect(center=(screen_x + self.tile_size / 2, screen_y - FALLBACK_LABEL_Y_OFFSET))
        self.screen.blit(text, text_rect)
    
    def _render_hit_splat(self, x: int, y: int, damage: int, is_miss: bool, is_heal: bool) -> None:
        """Render a hit splat."""
        if is_miss:
            text = "MISS"
            color = Colors.HIT_SPLAT_MISS_TEXT
            bg_color = Colors.HIT_SPLAT_MISS_BG
        elif is_heal:
            text = f"+{damage}"
            color = Colors.HIT_SPLAT_HEAL_TEXT
            bg_color = Colors.HIT_SPLAT_HEAL_BG
        elif damage == 0:
            text = "0"
            color = Colors.HIT_SPLAT_ZERO_TEXT
            bg_color = Colors.HIT_SPLAT_ZERO_BG
        else:
            text = str(damage)
            color = Colors.HIT_SPLAT_DAMAGE_TEXT
            bg_color = Colors.HIT_SPLAT_DAMAGE_BG
        
        # Draw background
        text_surface = self.hit_splat_font.render(text, True, color)
        text_rect = text_surface.get_rect(center=(x, y))
        
        bg_rect = text_rect.inflate(HIT_SPLAT_PADDING * 2, HIT_SPLAT_PADDING * 2)
        pygame.draw.rect(self.screen, bg_color, bg_rect, border_radius=HIT_SPLAT_BORDER_RADIUS)
        pygame.draw.rect(self.screen, Colors.HIT_SPLAT_BORDER, bg_rect, HIT_SPLAT_BORDER_WIDTH, border_radius=HIT_SPLAT_BORDER_RADIUS)
        
        # Draw text
        self.screen.blit(text_surface, text_rect)
    
    def _render_floating_text(self, x: int, y: int, text: str, alpha: int) -> None:
        """Render floating text with transparency."""
        text_surface = self.float_font.render(text, True, Colors.FLOATING_TEXT)
        
        # Set alpha
        text_surface.set_alpha(alpha)
        
        text_rect = text_surface.get_rect(center=(x, y))
        self.screen.blit(text_surface, text_rect)
