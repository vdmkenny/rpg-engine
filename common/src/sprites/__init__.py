"""
LPC Sprite System - Type-safe sprite handling for Liberated Pixel Cup assets.

This module provides enums, dataclasses, and utilities for working with LPC
character spritesheets in a type-safe manner.

## Components

- **enums**: Type-safe enumerations for all sprite attributes
- **appearance**: AppearanceData for character visual attributes
- **visual_state**: VisualState combining appearance with equipment
- **animation**: Animation configurations and state management
- **paths**: Sprite path construction utilities

## Quick Start

```python
from common.src.sprites import (
    AppearanceData,
    BodyType,
    SkinTone,
    HairStyle,
    HairColor,
    EyeColor,
)

# Create a character appearance
appearance = AppearanceData(
    body_type=BodyType.FEMALE,
    skin_tone=SkinTone.OLIVE,
    hair_style=HairStyle.LONG,
    hair_color=HairColor.BRUNETTE,
    eye_color=EyeColor.GREEN,
)

# Get hash for efficient network transmission
hash_id = appearance.compute_hash()

# Serialize for storage/network
data = appearance.to_dict()

# Deserialize from storage/network
restored = AppearanceData.from_dict(data)
```

## License

The sprite assets these types reference are from the Liberated Pixel Cup project.
They are licensed under CC-BY-SA 3.0, OGA-BY 3.0, and GPL 3.0.

See server/sprites/CREDITS.csv for full attribution of all artists.
You MUST credit the original artists when using these sprites.
"""

# =============================================================================
# Enums - Type-safe sprite attribute values
# =============================================================================

from .enums import (
    # Body and appearance
    BodyType,
    SkinTone,
    HeadType,
    HairStyle,
    HairColor,
    EyeColor,
    EyeAgeGroup,
    
    # Animation
    AnimationType,
    
    # Rendering
    SpriteLayer,
    EquipmentSlot,
    
    # Compatibility mappings
    BODY_ANIMATIONS,
    
    # Helper functions
    supports_animation,
    get_fallback_animation,
    get_eye_age_group,
)

# =============================================================================
# Dataclasses - Structured sprite data
# =============================================================================

from .appearance import (
    AppearanceData,
    AppearancePresets,
)

from .visual_state import (
    EquippedVisuals,
    VisualState,
)

# =============================================================================
# Animation - Frame configuration and state
# =============================================================================

from .animation import (
    AnimationConfig,
    AnimationState,
    ANIMATION_CONFIGS,
    DIRECTION_ROW_OFFSET,
    get_animation_config,
    get_animation_config_for_body,
    get_animation_row,
)

# =============================================================================
# Paths - Sprite file path construction
# =============================================================================

from .paths import (
    SpritePaths,
    get_sprite_paths_for_appearance,
    get_body_sprite_path,
    get_head_sprite_path,
    get_eyes_sprite_path,
    get_hair_sprite_path,
    get_equipment_sprite_path,
    resolve_equipment_sprite,
)

# =============================================================================
# Equipment Mapping - Item sprite ID to LPC path resolution
# =============================================================================

from .equipment_mapping import (
    MetalTier,
    EquipmentSprite,
    METAL_TINT_COLORS,
    EQUIPMENT_SPRITES,
    get_equipment_sprite,
    resolve_equipment,
    get_all_sprite_ids,
    validate_sprite_id,
)

# =============================================================================
# Public API
# =============================================================================

__all__ = [
    # Enums
    "BodyType",
    "SkinTone",
    "HeadType",
    "HairStyle",
    "HairColor",
    "EyeColor",
    "EyeAgeGroup",
    "AnimationType",
    "SpriteLayer",
    "EquipmentSlot",
    "MetalTier",
    
    # Dataclasses
    "AppearanceData",
    "AppearancePresets",
    "EquippedVisuals",
    "VisualState",
    "AnimationConfig",
    "AnimationState",
    "EquipmentSprite",
    
    # Constants
    "BODY_ANIMATIONS",
    "ANIMATION_CONFIGS",
    "DIRECTION_ROW_OFFSET",
    "METAL_TINT_COLORS",
    "EQUIPMENT_SPRITES",
    
    # Functions
    "supports_animation",
    "get_fallback_animation",
    "get_eye_age_group",
    "get_animation_config",
    "get_animation_config_for_body",
    "get_animation_row",
    
    # Path utilities
    "SpritePaths",
    "get_sprite_paths_for_appearance",
    "get_body_sprite_path",
    "get_head_sprite_path",
    "get_eyes_sprite_path",
    "get_hair_sprite_path",
    "get_equipment_sprite_path",
    "resolve_equipment_sprite",
    
    # Equipment mapping utilities
    "get_equipment_sprite",
    "resolve_equipment",
    "get_all_sprite_ids",
    "validate_sprite_id",
]
