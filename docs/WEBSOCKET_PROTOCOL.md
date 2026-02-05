# WebSocket Protocol Specification v2.0

> **Authoritative Reference**: This document is the definitive protocol specification for rpg-engine WebSocket communication. The implementation source of truth is `common/src/protocol.py`. For quick reference tables, see [WEBSOCKET_QUICK_REFERENCE.md](WEBSOCKET_QUICK_REFERENCE.md).

---

## Table of Contents

1. [Overview](#overview)
2. [Message Structure](#message-structure)
3. [Message Types Reference](#message-types-reference)
4. [Payload Schemas](#payload-schemas)
5. [Error Handling](#error-handling)
6. [Rate Limiting](#rate-limiting)
7. [Connection Lifecycle](#connection-lifecycle)
8. [Game Update System](#game-update-system)
9. [Client Implementation Guide](#client-implementation-guide)
10. [Appendix](#appendix)

---

## Overview

### Protocol Characteristics

| Property | Value | Description |
|----------|-------|-------------|
| **Version** | 2.0 | Current protocol version |
| **Transport** | WebSocket | Full-duplex communication over `/ws` endpoint |
| **Encoding** | MessagePack | Binary serialization for efficiency |
| **Authentication** | JWT Token | Passed in initial CMD_AUTHENTICATE |
| **Message Pattern** | Request-Response | Correlation IDs match requests to responses |
| **Updates** | Diff-based | Only changed entities sent per tick |

### Message Categories

| Category | Prefix | Direction | Response | Correlation ID |
|----------|--------|-----------|----------|----------------|
| **Commands** | `cmd_` | Client → Server | `resp_success` or `resp_error` | **Required** |
| **Queries** | `query_` | Client → Server | `resp_data` | **Required** |
| **Responses** | `resp_` | Server → Client | N/A | Matches request |
| **Events** | `event_` | Server → Client | N/A | None (null) |

### Design Principles

1. **Server-Authoritative**: All game state validation happens server-side
2. **Minimal Payloads**: Only necessary data is transmitted
3. **Structured Errors**: All errors use categorized error codes
4. **Visibility-Based**: Updates filtered by player view range
5. **Rate-Limited**: Operations have cooldowns to prevent abuse

---

## Message Structure

### Base Message Format (WSMessage)

All messages use this envelope structure:

```python
{
    "id": str | null,           # Correlation ID (UUID format)
    "type": str,                # MessageType enum value
    "payload": dict,            # Type-specific data
    "timestamp": int,           # UTC milliseconds (auto-generated)
    "version": "2.0"            # Protocol version
}
```

### Field Requirements

| Field | Commands | Queries | Responses | Events |
|-------|----------|---------|-----------|--------|
| `id` | **Required** (UUID) | **Required** (UUID) | Matches request | `null` |
| `type` | **Required** | **Required** | **Required** | **Required** |
| `payload` | **Required** | **Required** | **Required** | **Required** |
| `timestamp` | Auto-generated | Auto-generated | Auto-generated | Auto-generated |
| `version` | Defaults to "2.0" | Defaults to "2.0" | "2.0" | "2.0" |

### Correlation ID System

- **Client generates** UUID for every command and query
- **Server echoes** the same ID in the response
- **Client matches** responses to pending requests by ID
- **Events have no correlation ID** (id is `null`)

Example flow:
```python
# Client sends command
{
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "type": "cmd_move",
    "payload": {"direction": "DOWN"}
}

# Server responds with matching ID
{
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "type": "resp_success",
    "payload": {"new_position": {...}}
}
```

---

## Message Types Reference

### Commands (Client → Server)

Commands change game state and always receive a response.

#### CMD_AUTHENTICATE

**Purpose**: Initial authentication with JWT token

**Payload**:
```python
{
    "token": str  # JWT authentication token
}
```

**Success Response** (`resp_success`):
```python
{
    "player_id": int,
    "username": str,
    "x": int,
    "y": int,
    "map_id": str,
    "current_hp": int,
    "max_hp": int,
    "facing_direction": str  # "UP", "DOWN", "LEFT", "RIGHT"
}
```

**Rate Limit**: None (only sent once)

---

#### CMD_MOVE

**Purpose**: Move player in a cardinal direction

**Payload**:
```python
{
    "direction": str  # "UP", "DOWN", "LEFT", "RIGHT"
}
```

**Success Response**:
```python
{
    "new_position": {
        "x": int,
        "y": int,
        "map_id": str
    },
    "old_position": {
        "x": int,
        "y": int,
        "map_id": str
    }
}
```

**Error Codes**: `MOVE_INVALID_DIRECTION`, `MOVE_COLLISION_DETECTED`, `MOVE_RATE_LIMITED`, `MOVE_INVALID_POSITION`

**Rate Limit**: 0.5 seconds cooldown

**Side Effects**:
- Clears combat state
- May trigger chunk update if crossing chunk boundary
- Broadcasts position to nearby players

---

#### CMD_CHAT_SEND

**Purpose**: Send chat message

**Payload**:
```python
{
    "message": str,           # Max 500 characters (280 for local)
    "channel": str,           # "local", "global", "dm"
    "recipient": str | null   # Username (only for "dm" channel)
}
```

**Success Response**:
```python
{
    "channel": str,
    "message_id": str
}
```

**Error Codes**: `CHAT_MESSAGE_TOO_LONG`, `CHAT_PERMISSION_DENIED`, `CHAT_RATE_LIMITED`, `CHAT_RECIPIENT_NOT_FOUND`

**Rate Limit**: 1.0 seconds

---

#### CMD_INVENTORY_MOVE

**Purpose**: Move item between inventory slots

**Payload**:
```python
{
    "from_slot": int,  # 0-27
    "to_slot": int     # 0-27
}
```

**Success Response**: Empty payload (use `query_inventory` to get updated state)

**Error Codes**: `INV_INVALID_SLOT`, `INV_SLOT_EMPTY`, `INV_INVENTORY_FULL`, `INV_CANNOT_STACK`

**Rate Limit**: 0.5 seconds

---

#### CMD_INVENTORY_SORT

**Purpose**: Sort inventory by criteria

**Payload**:
```python
{
    "sort_by": str  # "category", "rarity", "value", "name"
}
```

**Success Response**: Empty payload

**Error Codes**: `INV_INVALID_SLOT`

**Rate Limit**: 0.5 seconds

---

#### CMD_ITEM_DROP

**Purpose**: Drop item from inventory to ground

**Payload**:
```python
{
    "inventory_slot": int,  # 0-27
    "quantity": int         # >= 1, defaults to 1
}
```

**Success Response**:
```python
{
    "ground_item_id": str,
    "item_name": str,
    "quantity": int
}
```

**Error Codes**: `INV_INVALID_SLOT`, `INV_SLOT_EMPTY`, `INV_INSUFFICIENT_QUANTITY`

**Rate Limit**: 0.2 seconds

---

#### CMD_ITEM_PICKUP

**Purpose**: Pick up item from ground

**Payload**:
```python
{
    "ground_item_id": str
}
```

**Success Response**:
```python
{
    "item": {
        "id": int,
        "name": str,
        "quantity": int
    },
    "inventory_slot": int
}
```

**Error Codes**: `GROUND_TOO_FAR`, `GROUND_PROTECTED_LOOT`, `GROUND_ITEM_NOT_FOUND`, `INV_INVENTORY_FULL`

**Rate Limit**: 0.2 seconds

---

#### CMD_ITEM_EQUIP

**Purpose**: Equip item from inventory

**Payload**:
```python
{
    "inventory_slot": int  # 0-27
}
```

**Success Response**:
```python
{
    "message": str,
    "item_name": str,
    "equipment_slot": str
}
```

**Error Codes**: `INV_INVALID_SLOT`, `INV_SLOT_EMPTY`, `EQ_ITEM_NOT_EQUIPABLE`, `EQ_REQUIREMENTS_NOT_MET`, `EQ_INVALID_SLOT`

**Rate Limit**: 0.5 seconds

---

#### CMD_ITEM_UNEQUIP

**Purpose**: Unequip item to inventory

**Payload**:
```python
{
    "equipment_slot": str  # See Equipment Slots in Appendix
}
```

**Success Response**:
```python
{
    "message": str,
    "item_name": str,
    "inventory_slot": int
}
```

**Error Codes**: `EQ_INVALID_SLOT`, `EQ_CANNOT_UNEQUIP_FULL_INV`, `INV_INVENTORY_FULL`

**Rate Limit**: 0.5 seconds

---

#### CMD_ATTACK

**Purpose**: Attack entity or player

**Payload**:
```python
{
    "target_type": str,   # "entity" or "player"
    "target_id": int | str  # Entity instance ID or player username
}
```

**Success Response**:
```python
{
    "message": str,
    "hit": bool,
    "damage": int,
    "defender_hp": int,
    "defender_died": bool,
    "xp_gained": {
        "attack": int,
        "strength": int,
        "hitpoints": int
    }
}
```

**Error Codes**: (Uses generic errors like `SYS_INTERNAL_ERROR` - needs improvement)

**Rate Limit**: 0.5 seconds

---

#### CMD_TOGGLE_AUTO_RETALIATE

**Purpose**: Toggle auto-retaliation setting

**Payload**:
```python
{
    "enabled": bool
}
```

**Success Response**: Empty payload

**Rate Limit**: 0.5 seconds

---

#### CMD_UPDATE_APPEARANCE

**Purpose**: Update player appearance (paperdoll customization)

**Payload**:
```python
{
    "body_type": int,            # 0-3 (slim, normal, athletic, heavy)
    "skin_tone": int,            # 0-9 (skin color palette index)
    "hair_style": int,           # 0-15 (hair style index, -1 for bald)
    "hair_color": int,           # 0-15 (hair color palette index)
    "eye_color": int,            # 0-7 (eye color palette index)
    "facial_hair_style": int,    # 0-7 (beard/mustache style, -1 for none)
    "facial_hair_color": int,    # 0-15 (facial hair color, -1 if no facial hair)
    "shirt_style": int,          # 0-9 (shirt style index)
    "shirt_color": int,          # 0-15 (shirt color palette index)
    "pants_style": int,          # 0-7 (pants style index)
    "pants_color": int,          # 0-15 (pants color palette index)
    "shoes_style": int,          # 0-5 (shoes style index)
    "shoes_color": int           # 0-15 (shoes color palette index)
}
```

**Success Response**:
```python
{
    "appearance": {
        "body_type": int,
        "skin_tone": int,
        "hair_style": int,
        "hair_color": int,
        "eye_color": int,
        "facial_hair_style": int,
        "facial_hair_color": int,
        "shirt_style": int,
        "shirt_color": int,
        "pants_style": int,
        "pants_color": int,
        "shoes_style": int,
        "shoes_color": int
    },
    "visual_hash": str  # Cache key for sprite lookup
}
```

**Error Codes**: `APPEARANCE_INVALID_VALUE`, `APPEARANCE_UPDATE_FAILED`

**Rate Limit**: 5.0 seconds

---

### Queries (Client → Server)

Queries request data and always receive a `resp_data` response.

#### QUERY_INVENTORY

**Payload**: Empty `{}`

**Response**:
```python
{
    "inventory": {
        "0": {
            "id": int,
            "name": str,
            "display_name": str,
            "quantity": int,
            "stackable": bool
        } | null,
        # ... slots 0-27
    }
}
```

---

#### QUERY_EQUIPMENT

**Payload**: Empty `{}`

**Response**:
```python
{
    "equipment": {
        "head": EquipmentSlot | null,    # Helmet/headgear
        "cape": EquipmentSlot | null,    # Cape/cloak
        "weapon": EquipmentSlot | null,  # Primary weapon
        "body": EquipmentSlot | null,    # Chest armor
        "shield": EquipmentSlot | null, # Off-hand shield
        "legs": EquipmentSlot | null,    # Leg armor
        "gloves": EquipmentSlot | null,  # Hand/glove armor
        "boots": EquipmentSlot | null,   # Footwear
        "ammo": EquipmentSlot | null     # Ammunition/quiver
    }
}
```

Where `EquipmentSlot` is:
```python
{
    "id": int,
    "name": str,
    "display_name": str,
    "stats": {
        "attack_stab": int,
        "attack_slash": int,
        "attack_crush": int,
        "defense_stab": int,
        "defense_slash": int,
        "defense_crush": int,
        "strength_bonus": int
    }
}
```

---

#### QUERY_STATS

**Payload**: Empty `{}`

**Response**:
```python
{
    "stats": {
        "attack_stab": int,
        "attack_slash": int,
        "attack_crush": int,
        "defense_stab": int,
        "defense_slash": int,
        "defense_crush": int,
        "strength_bonus": int
    },
    "skills": [
        {
            "skill_id": int,
            "name": str,
            "current_level": int,
            "current_xp": int,
            "target_xp": int
        }
    ],
    "total_level": int
}
```

---

#### QUERY_MAP_CHUNKS

**Payload**:
```python
{
    "map_id": str,
    "center_x": int,   # Tile coordinate
    "center_y": int,   # Tile coordinate
    "radius": int      # 1-5 (max 5 chunks in each direction)
}
```

**Response**:
```python
{
    "chunks": [
        {
            "chunk_x": int,
            "chunk_y": int,
            "tiles": [[int]],      # 16x16 grid of tile IDs
            "width": 16,
            "height": 16
        }
    ],
    "map_id": str,
    "center": {
        "x": int,
        "y": int
    },
    "radius": int
}
```

**Error Codes**: `MAP_INVALID_COORDS`, `MAP_CHUNK_LIMIT_EXCEEDED`, `MAP_NOT_FOUND`

---

### Responses (Server → Client)

#### RESP_SUCCESS

Sent when a command succeeds.

```python
{
    "id": str,           # Matches request correlation ID
    "type": "resp_success",
    "payload": {...},    # Command-specific data
    "timestamp": int,
    "version": "2.0"
}
```

---

#### RESP_ERROR

Sent when a command or query fails.

```python
{
    "id": str,                 # Matches request correlation ID
    "type": "resp_error",
    "payload": {
        "error_code": str,             # Structured error code
        "error_category": str,         # "validation", "permission", "system", "rate_limit"
        "message": str,                # Human-readable message
        "details": {...} | null,       # Additional context
        "retry_after": float | null,   # Seconds to wait (rate limiting)
        "suggested_action": str | null # Hint for client
    },
    "timestamp": int,
    "version": "2.0"
}
```

---

#### RESP_DATA

Sent in response to queries.

```python
{
    "id": str,           # Matches request correlation ID
    "type": "resp_data",
    "payload": {...},    # Query-specific data (see query docs)
    "timestamp": int,
    "version": "2.0"
}
```

---

### Events (Server → Client)

Events are broadcast by the server and have no correlation ID.

#### EVENT_WELCOME

Sent immediately after successful authentication.

```python
{
    "id": null,
    "type": "event_welcome",
    "payload": {
        "message": str,      # Welcome message
        "motd": str | null   # Message of the day
    },
    "timestamp": int,
    "version": "2.0"
}
```

**Note**: Detailed player data comes in `EVENT_STATE_UPDATE` after welcome.

---

#### EVENT_CHUNK_UPDATE

Sent when player crosses chunk boundary.

```python
{
    "id": null,
    "type": "event_chunk_update",
    "payload": {
        "map_id": str,
        "chunks": [ChunkData]  # See QUERY_MAP_CHUNKS response
    },
    "timestamp": int,
    "version": "2.0"
}
```

---

#### EVENT_STATE_UPDATE

Consolidated state changes for the player.

```python
{
    "id": null,
    "type": "event_state_update",
    "payload": {
        "update_type": str,   # "full" or "delta"
        "target": str,        # "personal", "nearby", "map", "global"
        "systems": {
            "player": {...} | null,     # Position, HP, basic info
            "inventory": {...} | null,  # Inventory state
            "equipment": {...} | null,  # Equipment slots
            "stats": {...} | null,      # Aggregated stats
            "entities": {...} | null    # Visible entities
        }
    },
    "timestamp": int,
    "version": "2.0"
}
```

---

#### EVENT_GAME_UPDATE

Real-time entity updates (sent every game tick, 20 TPS).

```python
{
    "id": null,
    "type": "event_game_update",
    "payload": {
        "entities": [EntityData],      # Added or updated entities
        "removed_entities": [str | int], # IDs of removed entities
        "map_id": str
    },
    "timestamp": int,
    "version": "2.0"
}
```

**EntityData for Players**:
```python
{
    "type": "player",
    "player_id": int,
    "username": str,
    "x": int,
    "y": int,
    "current_hp": int,
    "max_hp": int,
    "facing_direction": str,
    "visual_hash": str | null,  # For sprite caching
    "visual_state": {...} | null  # Appearance + equipment
}
```

**EntityData for NPCs**:
```python
{
    "type": "entity",
    "id": str,              # "entity_<instance_id>"
    "entity_type": str,     # "humanoid" or "monster"
    "entity_name": str,     # Internal name
    "display_name": str,    # Display name
    "behavior_type": str,   # "PASSIVE", "AGGRESSIVE", "DEFENSIVE"
    "x": int,
    "y": int,
    "current_hp": int,
    "max_hp": int,
    "state": str,           # "idle", "dying", "dead"
    "is_attackable": bool,
    "visual_hash": str | null,     # For humanoids
    "visual_state": {...} | null,  # For humanoids
    "sprite_sheet_id": str | null  # For monsters
}
```

**EntityData for Ground Items**:
```python
{
    "type": "ground_item",
    "id": str,              # "ground_item_<id>"
    "item_id": int,
    "item_name": str,
    "display_name": str,
    "rarity": str,          # "common", "uncommon", "rare", "epic", "legendary"
    "x": int,
    "y": int,
    "quantity": int,
    "is_protected": bool   # Can't be picked up by others
}
```

---

#### EVENT_CHAT_MESSAGE

Broadcast chat message.

```python
{
    "id": null,
    "type": "event_chat_message",
    "payload": {
        "sender": str,
        "message": str,
        "channel": str,  # "local", "global", "dm"
        "sender_position": {
            "x": int,
            "y": int,
            "map_id": str
        } | null
    },
    "timestamp": int,
    "version": "2.0"
}
```

---

#### EVENT_PLAYER_JOINED

Notification that a player joined the map.

```python
{
    "id": null,
    "type": "event_player_joined",
    "payload": {
        "player": {
            "player_id": int,
            "username": str,
            "x": int,
            "y": int,
            "current_hp": int,
            "max_hp": int,
            "facing_direction": str
        }
    },
    "timestamp": int,
    "version": "2.0"
}
```

---

#### EVENT_PLAYER_LEFT

Notification that a player left the map.

```python
{
    "id": null,
    "type": "event_player_left",
    "payload": {
        "username": str,
        "reason": str | null  # "disconnect", "timeout", etc.
    },
    "timestamp": int,
    "version": "2.0"
}
```

---

#### EVENT_PLAYER_DIED

Notification that a player died.

```python
{
    "id": null,
    "type": "event_player_died",
    "payload": {
        "player_id": int,
        "username": str,
        "death_position": {
            "x": int,
            "y": int,
            "map_id": str
        },
        "killer": {
            "id": str | int,
            "name": str,
            "type": str  # "entity" or "player"
        } | null
    },
    "timestamp": int,
    "version": "2.0"
}
```

---

#### EVENT_PLAYER_RESPAWN

Notification that a player respawned.

```python
{
    "id": null,
    "type": "event_player_respawn",
    "payload": {
        "player_id": int,
        "username": str,
        "spawn_position": {
            "x": int,
            "y": int,
            "map_id": str
        },
        "current_hp": int,
        "max_hp": int
    },
    "timestamp": int,
    "version": "2.0"
}
```

---

#### EVENT_SERVER_SHUTDOWN

Warning that server is shutting down.

```python
{
    "id": null,
    "type": "event_server_shutdown",
    "payload": {
        "message": str,
        "countdown_seconds": int | null
    },
    "timestamp": int,
    "version": "2.0"
}
```

---

#### EVENT_COMBAT_ACTION

Real-time combat event (damage dealt, hits, misses).

```python
{
    "id": null,
    "type": "event_combat_action",
    "payload": {
        "attacker_type": str,   # "entity" or "player"
        "attacker_id": int | str,
        "attacker_name": str,
        "defender_type": str,   # "entity" or "player"
        "defender_id": int | str,
        "defender_name": str,
        "hit": bool,
        "damage": int,
        "defender_hp": int,
        "defender_died": bool,
        "message": str
    },
    "timestamp": int,
    "version": "2.0"
}
```

---

#### EVENT_APPEARANCE_UPDATE

Broadcast when a player changes their appearance. Sent to nearby players only.

```python
{
    "id": null,
    "type": "event_appearance_update",
    "payload": {
        "player_id": int,
        "username": str,
        "appearance": {
            "body_type": int,
            "skin_tone": int,
            "hair_style": int,
            "hair_color": int,
            "eye_color": int,
            "facial_hair_style": int,
            "facial_hair_color": int,
            "shirt_style": int,
            "shirt_color": int,
            "pants_style": int,
            "pants_color": int,
            "shoes_style": int,
            "shoes_color": int
        },
        "visual_hash": str  # Cache key for sprite lookup
    },
    "timestamp": int,
    "version": "2.0"
}
```

---

## Error Handling

### Error Response Structure

All error responses follow this structure:

```python
{
    "error_code": str,           # Machine-readable code
    "error_category": str,       # Error classification
    "message": str,              # Human-readable description
    "details": {...} | null,     # Context-specific data
    "retry_after": float | null, # Seconds to wait (rate limiting)
    "suggested_action": str | null  # Client guidance
}
```

### Error Categories

| Category | Description | Example |
|----------|-------------|---------|
| `validation` | Input validation failure | Invalid direction |
| `permission` | Authorization failure | Global chat without permission |
| `system` | Server-side error | Database unavailable |
| `rate_limit` | Too many requests | Movement cooldown active |

### Complete Error Code Reference

#### Authentication Errors (`AUTH_*`)

| Code | Description |
|------|-------------|
| `AUTH_INVALID_TOKEN` | JWT token is invalid |
| `AUTH_EXPIRED_TOKEN` | JWT token has expired |
| `AUTH_PLAYER_NOT_FOUND` | Player account doesn't exist |
| `AUTH_PLAYER_BANNED` | Account is banned |
| `AUTH_PLAYER_TIMEOUT` | Account is temporarily suspended |

#### Movement Errors (`MOVE_*`)

| Code | Description |
|------|-------------|
| `MOVE_INVALID_DIRECTION` | Direction not in [UP, DOWN, LEFT, RIGHT] |
| `MOVE_COLLISION_DETECTED` | Tile is blocked by obstacle |
| `MOVE_RATE_LIMITED` | Movement cooldown hasn't elapsed |
| `MOVE_INVALID_POSITION` | Position validation failed |

#### Chat Errors (`CHAT_*`)

| Code | Description |
|------|-------------|
| `CHAT_MESSAGE_TOO_LONG` | Message exceeds max length |
| `CHAT_PERMISSION_DENIED` | No permission for channel |
| `CHAT_RATE_LIMITED` | Sending messages too fast |
| `CHAT_RECIPIENT_NOT_FOUND` | DM target not found or offline |

#### Inventory Errors (`INV_*`)

| Code | Description |
|------|-------------|
| `INV_INVALID_SLOT` | Slot number out of range (0-27) |
| `INV_SLOT_EMPTY` | No item in specified slot |
| `INV_INVENTORY_FULL` | No free inventory slots |
| `INV_CANNOT_STACK` | Items cannot be stacked |
| `INV_INSUFFICIENT_QUANTITY` | Not enough items for operation |

#### Equipment Errors (`EQ_*`)

| Code | Description |
|------|-------------|
| `EQ_ITEM_NOT_EQUIPABLE` | Item cannot be equipped |
| `EQ_REQUIREMENTS_NOT_MET` | Player doesn't meet skill requirements |
| `EQ_INVALID_SLOT` | Invalid equipment slot name |
| `EQ_CANNOT_UNEQUIP_FULL_INV` | Cannot unequip (inventory full) |

#### Appearance Errors (`APPEARANCE_*`)

| Code | Description |
|------|-------------|
| `APPEARANCE_INVALID_VALUE` | Appearance value out of valid range |
| `APPEARANCE_UPDATE_FAILED` | Server error during appearance update |

#### Ground Items Errors (`GROUND_*`)

| Code | Description |
|------|-------------|
| `GROUND_TOO_FAR` | Item is too far from player |
| `GROUND_PROTECTED_LOOT` | Item is protected for another player |
| `GROUND_ITEM_NOT_FOUND` | Ground item doesn't exist |

#### Map Errors (`MAP_*`)

| Code | Description |
|------|-------------|
| `MAP_INVALID_COORDS` | Invalid map coordinates |
| `MAP_CHUNK_LIMIT_EXCEEDED` | Requested too many chunks (>5 radius) |
| `MAP_NOT_FOUND` | Map ID doesn't exist |

#### System Errors (`SYS_*`)

| Code | Description |
|------|-------------|
| `SYS_DATABASE_ERROR` | Database operation failed |
| `SYS_SERVICE_UNAVAILABLE` | Service temporarily unavailable |
| `SYS_INTERNAL_ERROR` | Unexpected internal error |

---

## Rate Limiting

### Per-Operation Limits

| Operation | Max Requests | Window | Cooldown |
|-----------|-------------|--------|----------|
| `cmd_move` | 1 | 0.5s | 0.5s |
| `cmd_chat_send` | 1 | 1.0s | 1.0s |
| `cmd_inventory_move` | 1 | 0.5s | 0.5s |
| `cmd_inventory_sort` | 1 | 0.5s | 0.5s |
| `cmd_item_equip` | 1 | 0.5s | 0.5s |
| `cmd_item_unequip` | 1 | 0.5s | 0.5s |
| `cmd_item_drop` | 1 | 0.2s | 0.2s |
| `cmd_item_pickup` | 1 | 0.2s | 0.2s |
| `cmd_attack` | 1 | 0.5s | 0.5s |
| `cmd_toggle_auto_retaliate` | 1 | 0.5s | 0.5s |
| `cmd_update_appearance` | 1 | 5.0s | 5.0s |

### Rate Limit Error Response

When rate limited, the server responds with:

```python
{
    "type": "resp_error",
    "payload": {
        "error_code": "<OPERATION>_RATE_LIMITED",
        "error_category": "rate_limit",
        "message": "Operation rate limited",
        "retry_after": 0.35,  # Seconds remaining
        "suggested_action": "Wait before retrying"
    }
}
```

---

## Connection Lifecycle

### 1. Connection Establishment

```
Client                              Server
   |                                   |
   |--- HTTP Upgrade (GET /ws) ------>|
   |<-- 101 Switching Protocols -----|
   |                                   |
```

### 2. Authentication Handshake

```python
# 1. Client sends authentication
{
    "id": "auth-correlation-id",
    "type": "cmd_authenticate",
    "payload": {
        "token": "eyJhbGciOiJIUzI1NiIs..."
    }
}

# 2. Server responds with success
{
    "id": "auth-correlation-id",
    "type": "resp_success",
    "payload": {
        "player_id": 123,
        "username": "player1",
        "x": 10,
        "y": 10,
        "map_id": "samplemap",
        "current_hp": 10,
        "max_hp": 10,
        "facing_direction": "DOWN"
    }
}

# 3. Server sends welcome event
{
    "id": null,
    "type": "event_welcome",
    "payload": {
        "message": "Welcome to the game!",
        "motd": "Have fun and play fair!"
    }
}

# 4. Server sends initial state
{
    "id": null,
    "type": "event_state_update",
    "payload": {
        "update_type": "full",
        "target": "personal",
        "systems": {
            "player": {...},
            "inventory": {...},
            "equipment": {...},
            "stats": {...}
        }
    }
}
```

### 3. Normal Operation

After authentication, the client can:
- Send commands (move, chat, inventory ops, combat)
- Send queries (inventory, equipment, stats, chunks)
- Receive events (game updates, chat messages, state updates)

### 4. Disconnection

When connection closes:
- Server cleans up player state
- Other players receive `EVENT_GAME_UPDATE` with player removed
- Combat state is cleared
- Position and HP are persisted

---

## Game Update System

### Diff-Based Broadcasting

The server uses a diff-based system to minimize bandwidth:

1. **Full state** sent only on:
   - Initial connection
   - Explicit state refresh requests
   - Major state changes

2. **Delta updates** sent every tick (20 TPS):
   - Only changed entities
   - Added/updated/removed lists
   - Per-player visibility filtering

### Visibility Rules

- **Range**: 3x3 chunks around player (48x48 tiles)
- **Per-Player**: Each player receives personalized updates
- **No Redundancy**: Own player data included for position confirmation
- **Smooth Updates**: Removed entities fade out gracefully

### Update Frequency

| Update Type | Frequency | Trigger |
|-------------|-----------|---------|
| `EVENT_GAME_UPDATE` | 20 Hz (50ms) | Game tick |
| `EVENT_CHUNK_UPDATE` | On demand | Chunk boundary crossing |
| `EVENT_STATE_UPDATE` | On demand | State changes |
| `EVENT_CHAT_MESSAGE` | Real-time | Chat sent |
| `EVENT_COMBAT_ACTION` | Real-time | Combat event |

---

## Client Implementation Guide

### Connection Example

```python
import msgpack
import websockets
import uuid

async def connect_and_authenticate(server_url: str, jwt_token: str):
    websocket = await websockets.connect(f"{server_url}/ws")
    
    # Send authentication
    auth_id = str(uuid.uuid4())
    auth_msg = {
        "id": auth_id,
        "type": "cmd_authenticate",
        "payload": {"token": jwt_token}
    }
    await websocket.send(msgpack.packb(auth_msg))
    
    # Wait for response
    response_data = await websocket.recv()
    response = msgpack.unpackb(response_data, raw=False)
    
    if response["type"] == "resp_success":
        print(f"Authenticated as {response['payload']['username']}")
        return websocket
    else:
        raise AuthenticationError(response["payload"]["message"])
```

### Message Router Pattern

```python
class ProtocolHandler:
    def __init__(self):
        self.pending_requests = {}
        self.event_handlers = {}
    
    def register_event_handler(self, event_type: str, handler):
        self.event_handlers[event_type] = handler
    
    async def send_command(self, websocket, msg_type: str, payload: dict):
        correlation_id = str(uuid.uuid4())
        message = {
            "id": correlation_id,
            "type": msg_type,
            "payload": payload
        }
        
        # Create future to await response
        future = asyncio.Future()
        self.pending_requests[correlation_id] = future
        
        await websocket.send(msgpack.packb(message))
        
        # Wait for response with timeout
        try:
            response = await asyncio.wait_for(future, timeout=5.0)
            return response
        except asyncio.TimeoutError:
            del self.pending_requests[correlation_id]
            raise TimeoutError(f"Command {msg_type} timed out")
    
    async def handle_message(self, message: dict):
        msg_type = message["type"]
        correlation_id = message.get("id")
        
        # Match response to pending request
        if correlation_id and correlation_id in self.pending_requests:
            future = self.pending_requests.pop(correlation_id)
            future.set_result(message)
        elif msg_type in self.event_handlers:
            # Handle event
            await self.event_handlers[msg_type](message["payload"])
```

### Error Handling Pattern

```python
async def execute_command(handler, msg_type: str, payload: dict):
    try:
        response = await handler.send_command(websocket, msg_type, payload)
        
        if response["type"] == "resp_error":
            error = response["payload"]
            
            # Handle rate limiting
            if error["error_category"] == "rate_limit":
                retry_after = error.get("retry_after", 1.0)
                await asyncio.sleep(retry_after)
                return await execute_command(handler, msg_type, payload)
            
            # Handle specific error codes
            error_code = error["error_code"]
            if error_code == "MOVE_COLLISION_DETECTED":
                show_notification("Cannot move there - blocked!")
            elif error_code == "INV_SLOT_EMPTY":
                show_notification("That slot is empty")
            else:
                show_notification(f"Error: {error['message']}")
            
            return None
        
        return response["payload"]
        
    except TimeoutError:
        show_notification("Request timed out. Please retry.")
        return None
```

### Best Practices

1. **Always Include Correlation IDs**: Every command/query needs a unique ID
2. **Implement Timeout Logic**: Default 5-second timeout for commands
3. **Handle Rate Limits**: Respect `retry_after` field
4. **Process Events Async**: Don't block on event handling
5. **Cache Chunk Data**: Avoid re-requesting same chunks
6. **Track Cooldowns**: Client-side cooldown tracking prevents errors
7. **Validate Locally**: Pre-validate inputs when possible
8. **Handle Disconnects**: Implement reconnection with exponential backoff

---

## Appendix

### Enum Definitions

#### Direction
```python
UP = "UP"
DOWN = "DOWN"
LEFT = "LEFT"
RIGHT = "RIGHT"
```

#### ChatChannel
```python
LOCAL = "local"
GLOBAL = "global"
DM = "dm"
```

#### CombatTargetType
```python
ENTITY = "entity"
PLAYER = "player"
```

#### ErrorCategory
```python
VALIDATION = "validation"
PERMISSION = "permission"
SYSTEM = "system"
RATE_LIMIT = "rate_limit"
```

#### UpdateType
```python
FULL = "full"
DELTA = "delta"
```

#### UpdateScope
```python
PERSONAL = "personal"
NEARBY = "nearby"
MAP = "map"
GLOBAL = "global"
```

#### InventorySortCriteria
```python
CATEGORY = "category"
RARITY = "rarity"
VALUE = "value"
NAME = "name"
```

### Equipment Slots

Valid equipment slot names:
- `head` - Helmet/headgear
- `cape` - Cape/cloak
- `weapon` - Primary weapon
- `body` - Chest armor
- `shield` - Off-hand shield
- `legs` - Leg armor
- `gloves` - Hand/glove armor
- `boots` - Footwear
- `ammo` - Ammunition/quiver

### Complete Message Type List

| Message Type | Value | Category |
|--------------|-------|----------|
| CMD_AUTHENTICATE | `cmd_authenticate` | Command |
| CMD_MOVE | `cmd_move` | Command |
| CMD_CHAT_SEND | `cmd_chat_send` | Command |
| CMD_INVENTORY_MOVE | `cmd_inventory_move` | Command |
| CMD_INVENTORY_SORT | `cmd_inventory_sort` | Command |
| CMD_ITEM_DROP | `cmd_item_drop` | Command |
| CMD_ITEM_PICKUP | `cmd_item_pickup` | Command |
| CMD_ITEM_EQUIP | `cmd_item_equip` | Command |
| CMD_ITEM_UNEQUIP | `cmd_item_unequip` | Command |
| CMD_ATTACK | `cmd_attack` | Command |
| CMD_TOGGLE_AUTO_RETALIATE | `cmd_toggle_auto_retaliate` | Command |
| CMD_UPDATE_APPEARANCE | `cmd_update_appearance` | Command |
| QUERY_INVENTORY | `query_inventory` | Query |
| QUERY_EQUIPMENT | `query_equipment` | Query |
| QUERY_STATS | `query_stats` | Query |
| QUERY_MAP_CHUNKS | `query_map_chunks` | Query |
| RESP_SUCCESS | `resp_success` | Response |
| RESP_ERROR | `resp_error` | Response |
| RESP_DATA | `resp_data` | Response |
| EVENT_WELCOME | `event_welcome` | Event |
| EVENT_CHUNK_UPDATE | `event_chunk_update` | Event |
| EVENT_STATE_UPDATE | `event_state_update` | Event |
| EVENT_GAME_UPDATE | `event_game_update` | Event |
| EVENT_CHAT_MESSAGE | `event_chat_message` | Event |
| EVENT_PLAYER_JOINED | `event_player_joined` | Event |
| EVENT_PLAYER_LEFT | `event_player_left` | Event |
| EVENT_PLAYER_DIED | `event_player_died` | Event |
| EVENT_PLAYER_RESPAWN | `event_player_respawn` | Event |
| EVENT_SERVER_SHUTDOWN | `event_server_shutdown` | Event |
| EVENT_COMBAT_ACTION | `event_combat_action` | Event |
| EVENT_APPEARANCE_UPDATE | `event_appearance_update` | Event |

---

## Version History

### v2.0 (Current)
- Complete protocol redesign
- Correlation ID system for request-response matching
- Structured error codes with categories
- Diff-based game updates (20 TPS)
- Rate limiting on all operations
- Per-player visibility filtering
- Pydantic schema validation
- Binary MessagePack encoding

### v1.0 (Deprecated)
- Basic movement and chat
- Simple error responses (strings only)
- Full-state broadcasting (no diffs)
- No correlation IDs
- JSON encoding

---

**Document Version**: 2.0.1  
**Last Updated**: February 2026  
**Authoritative Source**: `common/src/protocol.py`
