# Protocol Changes Documentation

## Overview
This document details all WebSocket protocol changes made during the paperdoll system implementation.

## New Message Types

### CMD_UPDATE_APPEARANCE
**Direction:** Client → Server  
**Purpose:** Update player appearance (paperdoll customization)  
**Rate Limit:** 1 per 5 seconds  

**Payload Schema:**
```json
{
  "body_type": "string (optional) - male/female/child/teen/skeleton/zombie",
  "skin_tone": "string (optional) - light/dark/olive/brown/green/etc",
  "head_type": "string (optional) - human/male, human/female, orc, etc",
  "hair_style": "string (optional) - short/long/bald/etc",
  "hair_color": "string (optional) - brown/blonde/black/etc",
  "eye_color": "string (optional) - brown/blue/green/etc",
  "facial_hair_style": "string (optional) - none/beard_black/mustache_brown/etc",
  "facial_hair_color": "string (optional) - brown/blonde/etc",
  "shirt_style": "string (optional) - longsleeve2/shortsleeve/tunic/etc",
  "shirt_color": "string (optional) - white/black/blue/etc",
  "pants_style": "string (optional) - pants/shorts/leggings/etc",
  "pants_color": "string (optional) - brown/black/etc",
  "shoes_style": "string (optional) - shoes/basic/boots/etc",
  "shoes_color": "string (optional) - brown/black/etc"
}
```

**Response:**
- Success: `RESP_SUCCESS` with updated appearance and visual hash
- Error: `RESP_ERROR` with code `APPEARANCE_INVALID_VALUE` or `APPEARANCE_UPDATE_FAILED`

**Behavior:**
- Only fields provided in the payload are updated
- Other appearance fields remain unchanged
- Validates all enum values before updating
- Broadcasts `EVENT_APPEARANCE_UPDATE` to nearby players
- Invalidates visual cache to force re-render

---

### EVENT_APPEARANCE_UPDATE
**Direction:** Server → Client (Broadcast)  
**Purpose:** Notify nearby players of appearance change  
**Scope:** NEARBY (players within visible range)  

**Payload Schema:**
```json
{
  "player_id": "integer",
  "username": "string",
  "appearance": {
    "body_type": "string",
    "skin_tone": "string",
    "head_type": "string",
    "hair_style": "string",
    "hair_color": "string",
    "eye_color": "string",
    "facial_hair_style": "string",
    "facial_hair_color": "string",
    "shirt_style": "string",
    "shirt_color": "string",
    "pants_style": "string",
    "pants_color": "string",
    "shoes_style": "string",
    "shoes_color": "string"
  },
  "visual_hash": "string (12-char hex)"
}
```

**Client Behavior:**
- Update local cache of player's appearance
- Trigger re-render if player is visible
- Use visual_hash to detect changes efficiently

---

## Renamed Classes (Clean Break - No Backward Compatibility)

### Response Payloads
- `SuccessPayload` → `SuccessResponsePayload`
- `ErrorPayload` → `ErrorResponsePayload`
- `DataPayload` → `DataResponsePayload`

### Event Payloads
- New: `AppearanceUpdatePayload` (for CMD_UPDATE_APPEARANCE)
- New: `AppearanceUpdateEventPayload` (for EVENT_APPEARANCE_UPDATE)

### Enums
- New: `ErrorCodes` - All error codes as enum values
  - `SYS_INTERNAL_ERROR`
  - `SYS_SERVICE_UNAVAILABLE`
  - `SYS_INVALID_MESSAGE`
  - `AUTH_TOKEN_INVALID`
  - `AUTH_TOKEN_EXPIRED`
  - `AUTH_PLAYER_NOT_FOUND`
  - `MOVE_RATE_LIMITED`
  - `MOVE_COLLISION_DETECTED`
  - `MOVE_INVALID_DIRECTION`
  - `MOVE_OUT_OF_BOUNDS`
  - `INV_SLOT_EMPTY`
  - `INV_SLOT_OCCUPIED`
  - `INV_INVALID_SLOT`
  - `INV_INVENTORY_FULL`
  - `INV_INSUFFICIENT_QUANTITY`
  - `INV_CANNOT_STACK`
  - `EQ_ITEM_NOT_EQUIPABLE`
  - `EQ_REQUIREMENTS_NOT_MET`
  - `EQ_INVALID_SLOT`
  - `EQ_CANNOT_UNEQUIP_FULL_INV`
  - `GROUND_ITEM_NOT_FOUND`
  - `GROUND_ITEM_TOO_FAR`
  - `MAP_INVALID_COORDS`
  - `MAP_NOT_FOUND`
  - `CHAT_MESSAGE_TOO_LONG`
  - `CHAT_PERMISSION_DENIED`
  - `APPEARANCE_INVALID_VALUE`
  - `APPEARANCE_UPDATE_FAILED`

---

## Updated ErrorResponsePayload Schema

**Old:**
```json
{
  "error_code": "string",
  "error_category": "string",
  "message": "string",
  "details": "object (optional)",
  "retry_after": "number (optional)",
  "suggested_action": "string (optional)"
}
```

**New:**
```json
{
  "error": "string",
  "category": "string",
  "details": "object (optional)"
}
```

**Changes:**
- Simplified structure
- Removed `error_code` field (use error message directly)
- Removed `retry_after` (use rate limit headers)
- Removed `suggested_action` (include in error message)

---

## Updated Event Payloads

### Event payloads now include appearance data:

**PlayerJoinedEventPayload:**
```json
{
  "player_id": "integer",
  "username": "string",
  "position": {"x": "integer", "y": "integer"},
  "appearance": "object (optional)"  // NEW: Full appearance data
}
```

**StateUpdateEventPayload:**
```json
{
  "timestamp": "integer",
  "sequence": "integer",
  "entities": [
    {
      "id": "integer|string",
      "type": "string",
      "x": "integer",
      "y": "integer",
      "direction": "string (optional)",
      "animation": "string (optional)",
      "visual_hash": "string (optional)",  // NEW
      "hp_percent": "number (optional)"
    }
  ],
  "player": {
    "position": {"x": "integer", "y": "integer"},
    "current_hp": "integer",
    "max_hp": "integer",
    "visual_hash": "string (optional)",  // NEW
    "equipment_hash": "string (optional)"  // NEW
  }
}
```

---

## Migration Guide

### Server-Side Changes Required

1. **Update all imports:**
   ```python
   # Old
   from common.src.protocol import ErrorPayload, SuccessPayload, DataPayload
   
   # New
   from common.src.protocol import ErrorResponsePayload, SuccessResponsePayload, DataResponsePayload
   ```

2. **Update error response creation:**
   ```python
   # Old
   error_payload = ErrorPayload(
       error_code="MOVE_RATE_LIMITED",
       error_category=ErrorCategory.RATE_LIMIT,
       message="Rate limit exceeded",
       details={},
       retry_after=5.0
   )
   
   # New
   error_payload = ErrorResponsePayload(
       error="Rate limit exceeded - retry after 5 seconds",
       category=ErrorCategory.RATE_LIMIT,
       details={"retry_after": 5.0}
   )
   ```

3. **Update success response creation:**
   ```python
   # Old
   success_payload = SuccessPayload(message="Success", data={"key": "value"})
   
   # New
   response_data = {"key": "value"}  # Pass directly to WSMessage payload
   ```

4. **Add appearance handler to WebSocket router:**
   ```python
   self.router.register_handler(
       MessageType.CMD_UPDATE_APPEARANCE, 
       self._handle_cmd_update_appearance
   )
   ```

### Client-Side Changes Required

1. **Update message type handling:**
   - Handle new `EVENT_APPEARANCE_UPDATE` message type
   - Parse appearance data from `PlayerJoinedEventPayload`
   - Use `visual_hash` from `StateUpdateEventPayload` for caching

2. **Update appearance UI:**
   - Send `CMD_UPDATE_APPEARANCE` with partial appearance updates
   - Only include changed fields in payload
   - Handle validation errors gracefully

3. **Update error handling:**
   - Parse new simplified `ErrorResponsePayload` format
   - Check `category` field for error type
   - Extract additional details from `details` object

---

## Database Schema

**No migration required** - appearance is stored as JSON in existing `appearance` column:

```sql
-- Players table already has:
appearance: JSON (nullable)

-- New fields are automatically included when AppearanceData.to_dict() is called:
{
  "body_type": "male",
  "skin_tone": "light",
  "head_type": "human/male",
  "hair_style": "short",
  "hair_color": "brown",
  "eye_color": "brown",
  "facial_hair_style": "none",
  "facial_hair_color": "brown",
  "shirt_style": "longsleeve2",
  "shirt_color": "white",
  "pants_style": "pants",
  "pants_color": "brown",
  "shoes_style": "shoes/basic",
  "shoes_color": "brown"
}
```

**Default values:**
- New players automatically get `AppearanceData()` defaults
- Existing players with `NULL` appearance will use defaults on next appearance fetch
- Individual appearance fields can be updated independently

---

## Implementation Status

### ✅ Completed
- [x] EquipmentSlot name unification
- [x] Base clothing layer (shirts, pants, shoes)
- [x] Clothing style and color enums
- [x] Facial hair support
- [x] Equipment animation fix (equipment follows character animation)
- [x] Protocol message types (CMD_UPDATE_APPEARANCE, EVENT_APPEARANCE_UPDATE)
- [x] Protocol payload schemas
- [x] Appearance handler mixin
- [x] Server-side sprite validation registry
- [x] Error codes enum
- [x] Clean break from old payload names

### 📋 Pending/Optional
- [ ] Client-side appearance customization UI
- [ ] Client-side sprite validation fallbacks
- [ ] Integration tests with Docker
- [ ] Performance benchmarks for appearance updates

---

## Testing Checklist

- [ ] CMD_UPDATE_APPEARANCE updates appearance correctly
- [ ] EVENT_APPEARANCE_UPDATE broadcasts to nearby players
- [ ] Visual hash changes trigger re-render
- [ ] Invalid appearance values return proper error
- [ ] Partial updates (only some fields) work correctly
- [ ] Appearance persists after logout/login
- [ ] Equipment overlays correctly on clothing
- [ ] Animation changes update equipment sprites
- [ ] Facial hair renders at correct layer
- [ ] Clothing renders under armor correctly

---

## Example Usage

### Update Appearance
```javascript
// Client sends
{
  "id": "update-123",
  "type": "cmd_update_appearance",
  "payload": {
    "shirt_color": "blue",
    "pants_color": "black"
  },
  "timestamp": 1709999999999,
  "version": "2.0"
}

// Server responds
{
  "id": "update-123",
  "type": "resp_success",
  "payload": {
    "appearance": {
      "body_type": "male",
      "skin_tone": "light",
      ...
      "shirt_color": "blue",
      "pants_color": "black"
    },
    "visual_hash": "a1b2c3d4e5f6"
  },
  "timestamp": 1709999999999,
  "version": "2.0"
}

// Server broadcasts to nearby
{
  "id": null,
  "type": "event_appearance_update",
  "payload": {
    "player_id": 42,
    "username": "player1",
    "appearance": {...},
    "visual_hash": "a1b2c3d4e5f6"
  },
  "timestamp": 1709999999999,
  "version": "2.0"
}
```

---

## Security Considerations

1. **Rate limiting:** Appearance updates limited to 1 per 5 seconds
2. **Validation:** All appearance values validated against enums
3. **Broadcast scope:** Only nearby players receive updates (not global)
4. **Persistence:** Appearance stored in database, survives logout
5. **No admin override:** Players can only change their own appearance

---

## Credits & Attribution

- LPC sprites from Liberated Pixel Cup
- See `server/sprites/CREDITS.csv` for full attribution
