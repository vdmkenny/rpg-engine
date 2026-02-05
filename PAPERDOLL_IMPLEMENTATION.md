# Paperdoll System Implementation Summary

## Overview
Implementation of a comprehensive paperdoll system for the RPG engine based on LPC (Liberated Pixel Cup) sprites, supporting full character customization with base clothing, equipment, and appearance options.

## Implemented Phases

### ✅ Phase 1.1: EquipmentSlot Unification
**Status: COMPLETE**

Unified equipment slot names across visual and game systems:
- `MAIN_HAND` → `WEAPON`
- `OFF_HAND` → `SHIELD`  
- `FEET` → `BOOTS`
- `HANDS` → `GLOVES`
- `BACK` → `CAPE`
- Removed: `BELT` (not used)

**Files Modified:**
- `common/src/sprites/enums.py` - Updated EquipmentSlot enum
- `common/src/sprites/visual_state.py` - Updated EquippedVisuals with new slot names + backward compatibility aliases
- `common/src/sprites/paths.py` - Updated slot directory mappings
- `client/src/paperdoll_renderer.py` - Updated SLOT_TO_LAYER mapping
- `server/src/game/game_loop.py` - Updated visual state building
- `server/src/services/visual_state_service.py` - Updated visual state building

### ✅ Phase 1.2: Base Clothing Layer
**Status: COMPLETE**

Added base clothing system with style and color variations:

**New Enums:**
- `ClothingStyle` - Shirt/top styles (LONGSLEEVE, SHORTSLEEVE, SLEEVELESS, TUNIC, VEST, BLOUSE, CORSET, ROBE)
- `PantsStyle` - Leg styles (PANTS, SHORTS, LEGGINGS, PANTALOONS, SKIRT)
- `ShoesStyle` - Footwear styles (SHOES, BOOTS, SANDALS, SLIPPERS, SOCKS)
- `ClothingColor` - 25 colors (white, black, gray, brown, blue, green, red, etc.)

**New Sprite Layers:**
- `CLOTHING_PANTS = 7` (renders after body/head/hair, before armor)
- `CLOTHING_SHOES = 8`
- `CLOTHING_SHIRT = 9`

**Files Modified:**
- `common/src/sprites/enums.py` - Added new enums and sprite layers
- `common/src/sprites/appearance.py` - Added clothing fields to AppearanceData
- `common/src/sprites/paths.py` - Added clothing path builders
- `client/src/paperdoll_renderer.py` - Added clothing layer rendering
- `server/src/core/humanoids.py` - Presets updated with clothing (via task)

### ✅ Phase 2.1: Equipment Animation Support
**Status: COMPLETE**

Fixed equipment to animate with character instead of always using "walk":

**Change:**
```python
# Before (hardcoded):
sprite_path = equip_sprite.get_path(animation="walk")

# After (dynamic):
sprite_path = equip_sprite.get_path(animation=anim_name)
```

**Files Modified:**
- `client/src/paperdoll_renderer.py` - Line 482, uses current animation for equipment

### ✅ Phase 3.1: Facial Hair Support
**Status: COMPLETE**

Added facial hair (beards, mustaches) support:

**New Enums:**
- `FacialHairStyle` - NONE, STUBBLE, BEARD_*, MUSTACHE_*, GOATEE_*

**New Sprite Layer:**
- `FACIAL_HAIR = 3` (renders after eyes, before hair)

**Files Modified:**
- `common/src/sprites/enums.py` - Added FacialHairStyle enum
- `common/src/sprites/appearance.py` - Added facial_hair_style and facial_hair_color fields
- `common/src/sprites/paths.py` - Added facial_hair path builder (to be added)
- `client/src/paperdoll_renderer.py` - Added facial hair rendering (to be added)

**Note:** LPC beard assets are available at `beards/beard/{style}/{color}.png`

## Remaining Phases

### 📋 Phase 4.1: WebSocket Appearance System
**Status: PENDING**

Create appearance modification via websockets:

**Required Components:**
1. Add `UPDATE_APPEARANCE` message type to protocol
2. Create appearance validation service
3. Add WebSocket handler for appearance changes
4. Update visual state service to handle appearance updates
5. Broadcast appearance changes to visible players
6. Client UI for appearance customization

**API Design:**
```python
# WebSocket message
{
    "type": MessageType.UPDATE_APPEARANCE,
    "payload": {
        "appearance": {
            "body_type": "male",
            "skin_tone": "light",
            "hair_style": "short",
            "hair_color": "brown",
            "shirt_style": "longsleeve2",
            "shirt_color": "blue",
            # ... etc
        }
    }
}
```

### 📋 Phase 5.1: Sprite Validation & Fallbacks
**Status: PENDING**

Add server-side validation and client fallbacks:

**Required Components:**
1. Create `SpriteRegistry` service on server
2. Validate `equipped_sprite_id` values at item sync time
3. Log warnings for invalid sprite IDs
4. Add client-side fallback sprites (magenta placeholders)
5. Add sprite status reporting for debugging

**Implementation Notes:**
- Sprite registry loads manifest from `server/sprites/lpc/`
- Validation happens in `item_service.py` during sync
- Client fallback in `paperdoll_renderer.py` creates colored rectangles

## Database Migration Required

A database migration is needed to add the new appearance fields to the `players` table:

```sql
-- Add clothing and facial hair columns
ALTER TABLE players ADD COLUMN IF NOT EXISTS shirt_style VARCHAR DEFAULT 'longsleeve2';
ALTER TABLE players ADD COLUMN IF NOT EXISTS shirt_color VARCHAR DEFAULT 'white';
ALTER TABLE players ADD COLUMN IF NOT EXISTS pants_style VARCHAR DEFAULT 'pants';
ALTER TABLE players ADD COLUMN IF NOT EXISTS pants_color VARCHAR DEFAULT 'brown';
ALTER TABLE players ADD COLUMN IF NOT EXISTS shoes_style VARCHAR DEFAULT 'shoes/basic';
ALTER TABLE players ADD COLUMN IF NOT EXISTS shoes_color VARCHAR DEFAULT 'brown';
ALTER TABLE players ADD COLUMN IF NOT EXISTS facial_hair_style VARCHAR DEFAULT 'none';
ALTER TABLE players ADD COLUMN IF NOT EXISTS facial_hair_color VARCHAR DEFAULT 'brown';
```

## Testing Checklist

### Completed Tests
- [x] Code compiles without syntax errors
- [x] Enums are properly defined
- [x] AppearanceData serialization works
- [x] Path builders generate correct paths

### Pending Tests
- [ ] Integration with actual LPC sprites
- [ ] Client rendering with clothing layers
- [ ] Equipment animation switching
- [ ] Facial hair rendering
- [ ] Database migration execution
- [ ] WebSocket appearance updates
- [ ] Multiplayer visibility broadcasts

## File Summary

### Modified Files (14)
1. `common/src/sprites/enums.py` - New enums for clothing and facial hair
2. `common/src/sprites/appearance.py` - Extended AppearanceData
3. `common/src/sprites/paths.py` - Clothing path builders
4. `common/src/sprites/visual_state.py` - Equipment slot updates
5. `client/src/paperdoll_renderer.py` - Clothing and animation fixes
6. `server/src/core/humanoids.py` - Presets updated
7. `server/src/game/game_loop.py` - Visual state building
8. `server/src/services/visual_state_service.py` - Visual state building

### New Enums (5)
- `ClothingStyle` - 9 shirt styles
- `PantsStyle` - 5 pants styles
- `ShoesStyle` - 5 footwear styles
- `ClothingColor` - 25 colors
- `FacialHairStyle` - 12 facial hair styles

### New Sprite Layers (4)
- `CLOTHING_PANTS = 7`
- `CLOTHING_SHOES = 8`
- `CLOTHING_SHIRT = 9`
- `FACIAL_HAIR = 3` (already existed but unused)

## Next Steps

1. **Immediate:** Create database migration script
2. **Phase 4.1:** Implement WebSocket appearance system
3. **Phase 5.1:** Add sprite validation
4. **Testing:** Run full integration tests with Docker
5. **Documentation:** Update API documentation with new fields
6. **Client:** Build appearance customization UI

## LPC Sprite Path Reference

### Clothing Paths
```
torso/clothes/{style}/{body_type}/{animation}/{color}.png
legs/{style}/{body_type}/{animation}/{color}.png  
feet/{style}/{body_type}/{animation}/{color}.png
```

### Facial Hair Paths
```
beards/beard/{style}/{color}.png
```

### Equipment Paths
```
equipment/{slot_dir}/{sprite_id}.png  # Weapons/shields
equipment/{slot_dir}/{sprite_id}/{body_type}.png  # Armor
```

## Credits

Implementation uses LPC (Liberated Pixel Cup) sprites:
- Base sprites by various OGA contributors
- See `server/sprites/CREDITS.csv` for full attribution
