"""
Paperdoll Renderer - Composites LPC sprite layers into character sprites.

Handles:
- Loading and caching base body/head/eyes/hair sprites
- Loading and caching equipment sprites
- Compositing layers in correct order for rendering
- Extracting animation frames from spritesheets
- Applying tint colors to equipment
"""

import pygame
import asyncio
from typing import Dict, Optional, Tuple, List, Any
from dataclasses import dataclass

import sys
import os
workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, workspace_root)

from common.src.protocol import Direction
from common.src.sprites.enums import (
    BodyType,
    SkinTone,
    HeadType,
    HairStyle,
    HairColor,
    EyeColor,
    EyeAgeGroup,
    SpriteLayer,
    AnimationType,
    get_eye_age_group,
    get_fallback_animation,
)
from common.src.sprites.animation import (
    ANIMATION_CONFIGS,
    DIRECTION_ROW_OFFSET,
    get_animation_row,
    get_animation_config,
)
from common.src.sprites.paths import SpritePaths
from common.src.sprites.equipment_mapping import get_equipment_sprite

from sprite_manager import SpriteManager, FRAME_SIZE


# =============================================================================
# CONSTANTS
# =============================================================================

# Default render size (matches TILE_SIZE in client)
DEFAULT_RENDER_SIZE = 32

# Equipment slot to sprite layer mapping
SLOT_TO_LAYER: Dict[str, SpriteLayer] = {
    "head": SpriteLayer.ARMOR_HEAD,
    "body": SpriteLayer.ARMOR_BODY,
    "legs": SpriteLayer.ARMOR_LEGS,
    "feet": SpriteLayer.ARMOR_FEET,
    "hands": SpriteLayer.ARMOR_HANDS,
    "main_hand": SpriteLayer.WEAPON_FRONT,
    "off_hand": SpriteLayer.SHIELD,
    "back": SpriteLayer.BACK,
    "belt": SpriteLayer.ARMOR_BODY,  # Belt renders with body
}


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class RenderLayer:
    """A single sprite layer to be rendered."""
    layer: SpriteLayer
    sprite_path: str
    tint: Optional[str] = None
    
    def __lt__(self, other: "RenderLayer") -> bool:
        """Sort by layer order."""
        return self.layer.value < other.layer.value


@dataclass 
class CachedFrame:
    """A cached composited frame."""
    surface: pygame.Surface
    visual_hash: str


# =============================================================================
# PAPERDOLL RENDERER
# =============================================================================

class PaperdollRenderer:
    """
    Renders paperdoll characters by compositing LPC sprite layers.
    
    Handles appearance (body, head, eyes, hair) and equipment sprites,
    extracts animation frames, and caches composited results.
    """
    
    def __init__(self, sprite_manager: SpriteManager):
        self.sprite_manager = sprite_manager
        
        # Cache for composited frames: (visual_hash, animation, direction, frame) -> Surface
        self._frame_cache: Dict[Tuple[str, str, str, int], pygame.Surface] = {}
        
        # Cache for full composited spritesheets: visual_hash -> Surface
        self._sheet_cache: Dict[str, pygame.Surface] = {}
        
        # Track which visual hashes are being loaded
        self._loading: set = set()
        
        # Max cache size
        self._max_cache_size = 100
    
    def get_frame(
        self,
        visual_state: Dict[str, Any],
        visual_hash: str,
        animation: AnimationType,
        direction: Direction,
        frame: int = 0,
        render_size: int = DEFAULT_RENDER_SIZE,
    ) -> Optional[pygame.Surface]:
        """
        Get a single rendered frame for a character.
        
        Args:
            visual_state: The character's visual state data
            visual_hash: Hash of the visual state for caching
            animation: Animation type (WALK, IDLE, SLASH, etc.)
            direction: Facing direction
            frame: Frame index within animation
            render_size: Output size (will scale from 64x64)
            
        Returns:
            pygame.Surface or None if sprites not loaded
        """
        # Check frame cache
        cache_key = (visual_hash, animation.value, direction.value, frame)
        if cache_key in self._frame_cache:
            cached = self._frame_cache[cache_key]
            if render_size != FRAME_SIZE:
                return pygame.transform.scale(cached, (render_size, render_size))
            return cached
        
        # Get the layers to render
        layers = self._get_render_layers(visual_state)
        if not layers:
            return None
        
        # Get animation config
        config = get_animation_config(animation)
        if config is None:
            config = ANIMATION_CONFIGS[AnimationType.WALK]
        
        # Calculate row and column
        row = get_animation_row(animation, direction)
        col = frame % config.frame_count
        
        # Composite the frame
        composited = self._composite_frame(layers, row, col)
        if composited is None:
            return None
        
        # Cache the result
        self._cache_frame(cache_key, composited)
        
        if render_size != FRAME_SIZE:
            return pygame.transform.scale(composited, (render_size, render_size))
        return composited
    
    def get_idle_frame(
        self,
        visual_state: Dict[str, Any],
        visual_hash: str,
        direction: Direction,
        render_size: int = DEFAULT_RENDER_SIZE,
    ) -> Optional[pygame.Surface]:
        """
        Get an idle/standing frame for a character.
        
        Convenience method that uses IDLE animation frame 0.
        """
        return self.get_frame(
            visual_state,
            visual_hash,
            AnimationType.IDLE,
            direction,
            frame=0,
            render_size=render_size,
        )
    
    def get_walk_frame(
        self,
        visual_state: Dict[str, Any],
        visual_hash: str,
        direction: Direction,
        progress: float,
        render_size: int = DEFAULT_RENDER_SIZE,
    ) -> Optional[pygame.Surface]:
        """
        Get a walk animation frame based on movement progress.
        
        Args:
            visual_state: The character's visual state data
            visual_hash: Hash of the visual state for caching
            direction: Facing direction
            progress: Movement progress (0.0 to 1.0)
            render_size: Output size
            
        Returns:
            pygame.Surface or None
        """
        config = ANIMATION_CONFIGS[AnimationType.WALK]
        # Map progress to frame (skip first frame which is idle stance)
        frame = int(progress * (config.frame_count - 1)) + 1
        frame = min(frame, config.frame_count - 1)
        
        return self.get_frame(
            visual_state,
            visual_hash,
            AnimationType.WALK,
            direction,
            frame=frame,
            render_size=render_size,
        )
    
    async def preload_character(
        self,
        visual_state: Dict[str, Any],
        visual_hash: str,
    ) -> bool:
        """
        Preload all sprites needed for a character.
        
        Downloads any missing sprites and loads them into memory.
        
        Args:
            visual_state: The character's visual state data
            visual_hash: Hash for deduplication
            
        Returns:
            True if all sprites loaded successfully
        """
        if visual_hash in self._loading:
            return False
        
        self._loading.add(visual_hash)
        
        try:
            layers = self._get_render_layers(visual_state)
            paths = [layer.sprite_path for layer in layers]
            
            # Download all sprites in parallel
            tasks = [self.sprite_manager.download_sprite(path) for path in paths]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            success = all(r is True for r in results)
            return success
            
        finally:
            self._loading.discard(visual_hash)
    
    def is_loaded(self, visual_state: Dict[str, Any]) -> bool:
        """
        Check if all sprites for a visual state are loaded.
        
        Returns True if all needed sprites are cached locally.
        """
        layers = self._get_render_layers(visual_state)
        for layer in layers:
            if self.sprite_manager.get_surface(layer.sprite_path) is None:
                return False
        return True
    
    def clear_cache(self) -> None:
        """Clear the frame and sheet caches."""
        self._frame_cache.clear()
        self._sheet_cache.clear()
    
    def invalidate_visual(self, visual_hash: str) -> None:
        """Remove all cached frames for a specific visual hash."""
        keys_to_remove = [
            key for key in self._frame_cache.keys()
            if key[0] == visual_hash
        ]
        for key in keys_to_remove:
            del self._frame_cache[key]
        
        self._sheet_cache.pop(visual_hash, None)
    
    # =========================================================================
    # INTERNAL METHODS
    # =========================================================================
    
    def _get_render_layers(self, visual_state: Dict[str, Any]) -> List[RenderLayer]:
        """
        Build the list of sprite layers to render for a visual state.
        
        Returns layers sorted by render order (back to front).
        """
        layers: List[RenderLayer] = []
        
        appearance = visual_state.get("appearance", {})
        equipment = visual_state.get("equipment", {})
        
        # Parse appearance data
        body_type_str = appearance.get("body_type", "male")
        skin_tone_str = appearance.get("skin_tone", "light")
        head_type_str = appearance.get("head_type", "human/male")
        hair_style_str = appearance.get("hair_style", "short")
        hair_color_str = appearance.get("hair_color", "brown")
        eye_color_str = appearance.get("eye_color", "brown")
        
        # Convert to enums with fallbacks
        try:
            body_type = BodyType(body_type_str)
        except ValueError:
            body_type = BodyType.MALE
        
        try:
            skin_tone = SkinTone(skin_tone_str)
        except ValueError:
            skin_tone = SkinTone.LIGHT
        
        try:
            head_type = HeadType(head_type_str)
        except ValueError:
            head_type = HeadType.HUMAN_MALE
        
        try:
            hair_style = HairStyle(hair_style_str)
        except ValueError:
            hair_style = HairStyle.SHORT
        
        try:
            hair_color = HairColor(hair_color_str)
        except ValueError:
            hair_color = HairColor.BROWN
        
        try:
            eye_color = EyeColor(eye_color_str)
        except ValueError:
            eye_color = EyeColor.BROWN
        
        # Body layer
        body_path = SpritePaths.body(body_type, skin_tone)
        layers.append(RenderLayer(SpriteLayer.BODY, body_path))
        
        # Head layer
        head_path = SpritePaths.head(head_type, skin_tone)
        layers.append(RenderLayer(SpriteLayer.HEAD, head_path))
        
        # Eyes layer
        eye_age = get_eye_age_group(body_type, head_type)
        eyes_path = SpritePaths.eyes(eye_color, eye_age)
        layers.append(RenderLayer(SpriteLayer.EYES, eyes_path))
        
        # Hair layer (skip if bald)
        if hair_style != HairStyle.BALD:
            hair_path = SpritePaths.hair(hair_style, hair_color)
            if hair_path:
                layers.append(RenderLayer(SpriteLayer.HAIR, hair_path))
        
        # Equipment layers
        for slot, equip_data in equipment.items():
            if equip_data is None:
                continue
            
            sprite_id = equip_data.get("sprite_id")
            tint = equip_data.get("tint")
            
            if not sprite_id:
                continue
            
            # Look up the equipment sprite
            equip_sprite = get_equipment_sprite(sprite_id)
            if equip_sprite is None:
                continue
            
            # Get the sprite path (use walk animation as default)
            sprite_path = equip_sprite.get_path(animation="walk")
            
            # Use tint from visual state, or from equipment mapping
            final_tint = tint or equip_sprite.tint
            
            # Get the layer for this slot
            layer = SLOT_TO_LAYER.get(slot, SpriteLayer.ARMOR_BODY)
            
            layers.append(RenderLayer(layer, sprite_path, final_tint))
        
        # Sort by layer order
        layers.sort()
        
        return layers
    
    def _composite_frame(
        self,
        layers: List[RenderLayer],
        row: int,
        col: int,
    ) -> Optional[pygame.Surface]:
        """
        Composite multiple sprite layers into a single frame.
        
        Args:
            layers: List of layers to composite (in render order)
            row: Spritesheet row
            col: Spritesheet column (frame index)
            
        Returns:
            Composited pygame.Surface or None if any layer missing
        """
        # Create output surface
        result = pygame.Surface((FRAME_SIZE, FRAME_SIZE), pygame.SRCALPHA)
        
        for layer in layers:
            # Get the spritesheet surface
            sheet = self.sprite_manager.get_surface(layer.sprite_path)
            if sheet is None:
                # Sprite not loaded yet, return None to trigger fallback
                continue
            
            # Check if row/col are valid for this sheet
            sheet_cols = sheet.get_width() // FRAME_SIZE
            sheet_rows = sheet.get_height() // FRAME_SIZE
            
            if row >= sheet_rows or col >= sheet_cols:
                # This sheet doesn't have this animation/frame
                # Use row 10 (walk down) frame 0 as fallback
                row = min(10, sheet_rows - 1)
                col = 0
            
            # Extract the frame
            frame = self.sprite_manager.extract_frame(sheet, row, col)
            
            # Apply tint if needed
            if layer.tint:
                frame = self.sprite_manager.apply_tint(frame, layer.tint)
            
            # Composite onto result
            result.blit(frame, (0, 0))
        
        return result
    
    def _cache_frame(
        self,
        key: Tuple[str, str, str, int],
        surface: pygame.Surface,
    ) -> None:
        """Cache a composited frame, evicting old entries if needed."""
        if len(self._frame_cache) >= self._max_cache_size:
            # Simple eviction: remove oldest entries
            keys_to_remove = list(self._frame_cache.keys())[:self._max_cache_size // 4]
            for k in keys_to_remove:
                del self._frame_cache[k]
        
        self._frame_cache[key] = surface


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def create_fallback_sprite(
    color: Tuple[int, int, int],
    size: int = DEFAULT_RENDER_SIZE,
    with_border: bool = True,
) -> pygame.Surface:
    """
    Create a simple colored rectangle as a fallback sprite.
    
    Used when paperdoll sprites aren't loaded yet.
    
    Args:
        color: RGB color tuple
        size: Sprite size
        with_border: Whether to draw a border
        
    Returns:
        pygame.Surface
    """
    surface = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.rect(surface, color, (0, 0, size, size))
    
    if with_border:
        pygame.draw.rect(surface, (0, 0, 0), (0, 0, size, size), 1)
    
    return surface


def get_animation_frame_count(animation: AnimationType) -> int:
    """Get the number of frames in an animation."""
    config = get_animation_config(animation)
    if config is None:
        return 1
    return config.frame_count
