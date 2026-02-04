# WebSocket Protocol Documentation

**Document Version**: 2.0  
**Protocol Version**: 2.0  
**Created**: January 2026  
**Updated**: February 2026  
**Purpose**: Complete WebSocket message protocol for rpg-engine client-server communication

## Table of Contents
- [Overview](#overview)
- [Connection Flow](#connection-flow)
- [Message Structure](#message-structure)
- [Authentication](#authentication)
- [Movement](#movement)
- [Chat](#chat)
- [Inventory & Equipment](#inventory--equipment)
- [Combat](#combat)
- [Map & Chunks](#map--chunks)
- [Game Updates](#game-updates)
- [Error Handling](#error-handling)
- [Testing](#testing)

## Overview

### Protocol Features
- **Binary Protocol**: Uses MessagePack for efficient serialization
- **Correlation IDs**: Request-response matching for async operations
- **Version Negotiation**: Protocol version in every message
- **Structured Error Codes**: Consistent error handling across all operations
- **Event Broadcasting**: Server-initiated events for game state changes

### Message Categories
1. **Commands (CMD_*)**: Client → Server actions requiring confirmation
2. **Queries (QUERY_*)**: Client → Server requests for information
3. **Responses (RESP_*)**: Server → Client replies to commands/queries
4. **Events (EVENT_*)**: Server → Client broadcasts (no correlation ID)

### Transport
- **Encoding**: MessagePack binary format (`msgpack.packb()`)
- **WebSocket**: Full-duplex communication over `/ws` endpoint
- **Authentication**: JWT token in initial handshake

## Connection Flow

### 1. Connection Establishment

```
Client                                 Server
  |                                      |
  |--- HTTP Upgrade (GET /ws) --------->|
  |<-- 101 Switching Protocols ---------|
  |                                      |
```

### 2. Authentication

```python
# Client sends authentication command
{
    "id": "uuid-correlation-id",
    "type": "cmd_authenticate",
    "payload": {
        "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
    },
    "version": "2.0"
}

# Server validates and responds with welcome event
{
    "id": "uuid-correlation-id",
    "type": "event_welcome",
    "payload": {
        "player_id": 123,
        "username": "player1",
        "x": 10,
        "y": 10,
        "map_id": "samplemap",
        "current_hp": 10,
        "max_hp": 10
    },
    "version": "2.0"
}

# Server sends welcome chat message
{
    "id": null,  # Events have no correlation ID
    "type": "event_chat_message",
    "payload": {
        "username": "System",
        "message": "Welcome to the game!",
        "channel": "system",
        "timestamp": 1706832000.123
    },
    "version": "2.0"
}

# Server sends player's skills
{
    "id": null,
    "type": "event_skills",
    "payload": {
        "skills": [
            {
                "skill_id": 1,
                "name": "attack",
                "current_level": 1,
                "current_xp": 0,
                "target_xp": 83
            },
            # ... more skills
        ]
    },
    "version": "2.0"
}
```

### 3. Disconnection

Server automatically handles disconnection cleanup:
- Player removed from online registry
- Combat state cleared
- Position/HP saved to database
- Other players notified via `EVENT_GAME_UPDATE` (removed entity)

## Message Structure

### Base Message Format

```python
class WSMessage(BaseModel):
    id: Optional[str]  # Correlation ID (UUID) for commands/queries, null for events
    type: MessageType  # Message type enum
    payload: Dict[str, Any]  # Type-specific payload
    version: str = "2.0"  # Protocol version
```

### Message Type Enum

```python
class MessageType(str, Enum):
    # Commands (client → server, require response)
    CMD_AUTHENTICATE = "cmd_authenticate"
    CMD_MOVE = "cmd_move"
    CMD_CHAT_SEND = "cmd_chat_send"
    CMD_INVENTORY_USE = "cmd_inventory_use"
    CMD_INVENTORY_DROP = "cmd_inventory_drop"
    CMD_EQUIPMENT_EQUIP = "cmd_equipment_equip"
    CMD_EQUIPMENT_UNEQUIP = "cmd_equipment_unequip"
    CMD_ATTACK = "cmd_attack"
    CMD_PICKUP_ITEM = "cmd_pickup_item"
    
    # Queries (client → server, request data)
    QUERY_CHUNKS = "query_chunks"
    QUERY_INVENTORY = "query_inventory"
    QUERY_EQUIPMENT = "query_equipment"
    
    # Responses (server → client, reply to commands/queries)
    RESP_SUCCESS = "resp_success"
    RESP_ERROR = "resp_error"
    
    # Events (server → client, broadcasts)
    EVENT_WELCOME = "event_welcome"
    EVENT_CHAT_MESSAGE = "event_chat_message"
    EVENT_GAME_UPDATE = "event_game_update"
    EVENT_SKILLS = "event_skills"
    EVENT_PLAYER_DIED = "event_player_died"
    EVENT_PLAYER_RESPAWNED = "event_player_respawned"
    EVENT_INVENTORY_UPDATE = "event_inventory_update"
    EVENT_EQUIPMENT_UPDATE = "event_equipment_update"
    EVENT_GROUND_ITEMS_UPDATE = "event_ground_items_update"
    EVENT_SERVER_SHUTDOWN = "event_server_shutdown"
```

### Success Response

```python
{
    "id": "correlation-id",  # Matches request
    "type": "resp_success",
    "payload": {
        # Operation-specific data
        "new_position": {"x": 11, "y": 10, "map_id": "samplemap"},
        "old_position": {"x": 10, "y": 10, "map_id": "samplemap"}
    },
    "version": "2.0"
}
```

### Error Response

```python
{
    "id": "correlation-id",  # Matches request
    "type": "resp_error",
    "payload": {
        "error_code": "MOVEMENT_BLOCKED",
        "message": "Cannot move to that location",
        "details": {
            "reason": "collision",
            "tile_type": "wall"
        }
    },
    "version": "2.0"
}
```

## Authentication

### CMD_AUTHENTICATE

**Client Request**:
```python
{
    "id": "uuid",
    "type": "cmd_authenticate",
    "payload": {
        "token": "jwt_token_string"
    },
    "version": "2.0"
}
```

**Server Response** (Success - EVENT_WELCOME):
```python
{
    "id": "uuid",
    "type": "event_welcome",
    "payload": {
        "player_id": 123,
        "username": "player1",
        "x": 10,
        "y": 10,
        "map_id": "samplemap",
        "current_hp": 10,
        "max_hp": 10,
        "facing_direction": "south",
        "animation_state": "idle"
    },
    "version": "2.0"
}
```

**Server Response** (Error):
```python
{
    "id": "uuid",
    "type": "resp_error",
    "payload": {
        "error_code": "AUTHENTICATION_FAILED",
        "message": "Invalid or expired token",
        "details": {}
    },
    "version": "2.0"
}
```

**Error Codes**:
- `AUTHENTICATION_FAILED`: Invalid or expired JWT token
- `AUTHENTICATION_MISSING_TOKEN`: No token provided
- `AUTHENTICATION_INVALID_PAYLOAD`: Malformed authentication payload

## Movement

### CMD_MOVE

**Client Request**:
```python
{
    "id": "uuid",
    "type": "cmd_move",
    "payload": {
        "direction": "DOWN"  # UP, DOWN, LEFT, RIGHT (case-sensitive)
    },
    "version": "2.0"
}
```

**Server Response** (Success):
```python
{
    "id": "uuid",
    "type": "resp_success",
    "payload": {
        "new_position": {
            "x": 10,
            "y": 11,  # Moved down (y increased)
            "map_id": "samplemap",
            "player_id": 123,
            "timestamp": 1706832000.123
        },
        "old_position": {
            "x": 10,
            "y": 10,
            "map_id": "samplemap"
        },
        "collision": false
    },
    "version": "2.0"
}
```

**Server Response** (Error):
```python
{
    "id": "uuid",
    "type": "resp_error",
    "payload": {
        "error_code": "MOVEMENT_BLOCKED",
        "message": "Movement blocked by collision",
        "details": {
            "reason": "blocked",
            "current_position": {"x": 10, "y": 10, "map_id": "samplemap"},
            "collision": true
        }
    },
    "version": "2.0"
}
```

**Error Codes**:
- `MOVEMENT_RATE_LIMITED`: Moving too fast (cooldown not elapsed)
- `MOVEMENT_BLOCKED`: Collision with wall/obstacle
- `MOVEMENT_INVALID_DIRECTION`: Invalid direction value
- `MOVEMENT_OUT_OF_BOUNDS`: Attempting to move outside map boundaries

**Side Effects**:
- Clears combat state (moving breaks combat)
- Broadcasts `EVENT_GAME_UPDATE` to nearby players with updated position
- Auto-retaliation may re-engage combat

**Movement Mechanics**:
- **Cooldown**: 500ms between moves (configurable)
- **Grid-Based**: Moves exactly 1 tile in specified direction
- **Collision Detection**: Server-side validation against map tiles
- **Combat Break**: Moving clears `player_combat_state` in Valkey

## Chat

### CMD_CHAT_SEND

**Client Request**:
```python
{
    "id": "uuid",
    "type": "cmd_chat_send",
    "payload": {
        "message": "Hello, world!",
        "channel": "local",  # "local", "global", "dm"
        "recipient": "player2"  # Only for DM channel
    },
    "version": "2.0"
}
```

**Server Response** (Success):
```python
{
    "id": "uuid",
    "type": "resp_success",
    "payload": {
        "message_id": "123_1706832000",
        "channel": "local",
        "recipients": ["player1", "player2", "player3"]
    },
    "version": "2.0"
}
```

**Server Broadcast** (EVENT_CHAT_MESSAGE):
```python
{
    "id": null,  # Events have no correlation ID
    "type": "event_chat_message",
    "payload": {
        "username": "player1",
        "message": "Hello, world!",
        "channel": "local",
        "timestamp": 1706832000.123
    },
    "version": "2.0"
}
```

**Error Codes**:
- `CHAT_RATE_LIMITED`: Sending messages too fast (1 second cooldown)
- `CHAT_MESSAGE_TOO_LONG`: Message exceeds max length (256 chars)
- `CHAT_EMPTY_MESSAGE`: Empty or whitespace-only message
- `CHAT_DM_RECIPIENT_NOT_FOUND`: DM target player not found or offline
- `CHAT_INVALID_CHANNEL`: Invalid channel type

**Chat Channels**:
- **Local**: Players within `CHAT_LOCAL_CHUNK_RADIUS` (default: 3 chunks = 48 tiles)
- **Global**: All connected players (requires permission)
- **DM**: Direct message to specific player

**Chat Mechanics**:
- **Rate Limiting**: 1 second cooldown per message
- **Profanity Filter**: Basic filter applied (configurable)
- **Max Length**: 256 characters
- **System Messages**: Special "System" username for server messages

## Inventory & Equipment

### QUERY_INVENTORY

**Client Request**:
```python
{
    "id": "uuid",
    "type": "query_inventory",
    "payload": {},
    "version": "2.0"
}
```

**Server Response**:
```python
{
    "id": "uuid",
    "type": "resp_success",
    "payload": {
        "inventory": {
            "0": {
                "item_id": 1,
                "quantity": 10,
                "name": "Bronze arrow",
                "stackable": true
            },
            "1": {
                "item_id": 5,
                "quantity": 1,
                "name": "Bronze sword",
                "stackable": false
            }
            # ... up to slot 27 (28 slots total)
        }
    },
    "version": "2.0"
}
```

### CMD_INVENTORY_USE

**Client Request**:
```python
{
    "id": "uuid",
    "type": "cmd_inventory_use",
    "payload": {
        "slot": 3  # Inventory slot number (0-27)
    },
    "version": "2.0"
}
```

**Server Response**:
```python
{
    "id": "uuid",
    "type": "resp_success",
    "payload": {
        "result": "consumed",  # or "equipped", "activated"
        "effect": "restored_10_hp"
    },
    "version": "2.0"
}
```

**Error Codes**:
- `INVENTORY_SLOT_EMPTY`: No item in specified slot
- `INVENTORY_INVALID_SLOT`: Slot number out of range (0-27)
- `INVENTORY_FULL`: Cannot add item, all slots occupied
- `INVENTORY_ITEM_NOT_FOUND`: Item does not exist

### QUERY_EQUIPMENT

**Client Request**:
```python
{
    "id": "uuid",
    "type": "query_equipment",
    "payload": {},
    "version": "2.0"
}
```

**Server Response**:
```python
{
    "id": "uuid",
    "type": "resp_success",
    "payload": {
        "equipment": {
            "head": null,
            "cape": null,
            "neck": null,
            "weapon": {
                "item_id": 5,
                "name": "Bronze sword",
                "stats": {
                    "attack_bonus_stab": 4,
                    "attack_bonus_slash": 5,
                    "attack_bonus_crush": 3
                }
            },
            "body": null,
            "shield": null,
            "legs": null,
            "hands": null,
            "feet": null,
            "ring": null,
            "ammo": null
        }
    },
    "version": "2.0"
}
```

### CMD_EQUIPMENT_EQUIP

**Client Request**:
```python
{
    "id": "uuid",
    "type": "cmd_equipment_equip",
    "payload": {
        "inventory_slot": 1,  # Slot in inventory
        "equipment_slot": "weapon"  # Target equipment slot
    },
    "version": "2.0"
}
```

**Server Response**:
```python
{
    "id": "uuid",
    "type": "resp_success",
    "payload": {
        "equipped_item": {
            "item_id": 5,
            "name": "Bronze sword"
        },
        "unequipped_item": {
            "item_id": 3,
            "name": "Bronze dagger"
        },  # null if slot was empty
        "inventory_changes": {
            "1": null,  # Removed from inventory
            "2": {"item_id": 3, "quantity": 1}  # Old weapon moved here
        }
    },
    "version": "2.0"
}
```

**Error Codes**:
- `EQUIPMENT_SLOT_INVALID`: Invalid equipment slot name
- `EQUIPMENT_REQUIREMENTS_NOT_MET`: Player doesn't meet skill requirements
- `EQUIPMENT_WRONG_SLOT`: Item cannot be equipped in that slot
- `EQUIPMENT_INVENTORY_FULL`: Cannot unequip (no inventory space)

### CMD_EQUIPMENT_UNEQUIP

**Client Request**:
```python
{
    "id": "uuid",
    "type": "cmd_equipment_unequip",
    "payload": {
        "equipment_slot": "weapon"
    },
    "version": "2.0"
}
```

**Server Response**:
```python
{
    "id": "uuid",
    "type": "resp_success",
    "payload": {
        "unequipped_item": {
            "item_id": 5,
            "name": "Bronze sword"
        },
        "inventory_slot": 3  # Placed in this inventory slot
    },
    "version": "2.0"
}
```

**Equipment Slots**:
- `head`, `cape`, `neck`, `weapon`, `body`, `shield`, `legs`, `hands`, `feet`, `ring`, `ammo`

## Combat

### CMD_ATTACK

**Client Request**:
```python
{
    "id": "uuid",
    "type": "cmd_attack",
    "payload": {
        "target_id": "npc_456",  # or "player_123" for PvP
        "target_type": "npc"  # "npc" or "player"
    },
    "version": "2.0"
}
```

**Server Response**:
```python
{
    "id": "uuid",
    "type": "resp_success",
    "payload": {
        "combat_started": true,
        "target": {
            "id": "npc_456",
            "name": "Goblin",
            "current_hp": 10,
            "max_hp": 10
        }
    },
    "version": "2.0"
}
```

**Server Broadcast** (Combat Damage):
```python
{
    "id": null,
    "type": "event_game_update",
    "payload": {
        "entities": [
            {
                "id": "npc_456",
                "current_hp": 7,  # Damaged
                "combat_state": "in_combat"
            }
        ],
        "removed_entities": [],
        "map_id": "samplemap"
    },
    "version": "2.0"
}
```

**Error Codes**:
- `COMBAT_TARGET_NOT_FOUND`: Target does not exist
- `COMBAT_OUT_OF_RANGE`: Target too far away
- `COMBAT_ALREADY_IN_COMBAT`: Player already engaged with another target
- `COMBAT_INVALID_TARGET`: Cannot attack that target type

**Combat Mechanics**:
- **Attack Speed**: Determined by weapon type
- **Damage Calculation**: Based on attack/defense stats + equipment bonuses
- **Auto-Retaliation**: NPCs/players auto-attack back
- **Movement Breaks Combat**: Moving clears combat state
- **Death**: Entity removed at 0 HP, drops items

### EVENT_PLAYER_DIED

```python
{
    "id": null,
    "type": "event_player_died",
    "payload": {
        "player_id": 123,
        "username": "player1",
        "death_position": {"x": 15, "y": 20, "map_id": "samplemap"},
        "killer": {
            "id": "npc_456",
            "name": "Goblin",
            "type": "npc"
        }
    },
    "version": "2.0"
}
```

### EVENT_PLAYER_RESPAWNED

```python
{
    "id": null,
    "type": "event_player_respawned",
    "payload": {
        "player_id": 123,
        "username": "player1",
        "spawn_position": {"x": 10, "y": 10, "map_id": "spawn_area"},
        "current_hp": 10,
        "max_hp": 10
    },
    "version": "2.0"
}
```

## Map & Chunks

### QUERY_CHUNKS

**Client Request**:
```python
{
    "id": "uuid",
    "type": "query_chunks",
    "payload": {
        "map_id": "samplemap",
        "chunk_x": 0,
        "chunk_y": 0,
        "radius": 1  # Max: 5 (security limit)
    },
    "version": "2.0"
}
```

**Server Response**:
```python
{
    "id": "uuid",
    "type": "resp_success",
    "payload": {
        "chunks": [
            {
                "chunk_x": 0,
                "chunk_y": 0,
                "tiles": [
                    # 16x16 grid of tile IDs
                    [1, 1, 1, 1, ...],
                    [1, 2, 2, 1, ...],
                    # ... 16 rows
                ],
                "collision": [
                    # 16x16 grid of booleans
                    [false, false, false, ...],
                    [false, true, true, ...],
                    # ... 16 rows
                ]
            },
            # ... more chunks in 3x3 grid
        ]
    },
    "version": "2.0"
}
```

**Error Codes**:
- `CHUNKS_RADIUS_TOO_LARGE`: Radius exceeds max (5 chunks)
- `CHUNKS_MAP_NOT_FOUND`: Map ID does not exist
- `CHUNKS_INVALID_COORDINATES`: Invalid chunk coordinates

**Chunk System**:
- **Chunk Size**: 16x16 tiles
- **Max Radius**: 5 chunks (security limit to prevent abuse)
- **Coordinate System**: Tile (x, y) → Chunk (x // 16, y // 16)
- **Lazy Loading**: Chunks loaded on demand, cached client-side

### CMD_PICKUP_ITEM

**Client Request**:
```python
{
    "id": "uuid",
    "type": "cmd_pickup_item",
    "payload": {
        "ground_item_id": "ground_item_789"
    },
    "version": "2.0"
}
```

**Server Response**:
```python
{
    "id": "uuid",
    "type": "resp_success",
    "payload": {
        "item": {
            "item_id": 1,
            "quantity": 5,
            "name": "Bronze arrow"
        },
        "inventory_slot": 3
    },
    "version": "2.0"
}
```

**Server Broadcast** (Ground Item Removed):
```python
{
    "id": null,
    "type": "event_ground_items_update",
    "payload": {
        "added": [],
        "removed": ["ground_item_789"]
    },
    "version": "2.0"
}
```

## Game Updates

### EVENT_GAME_UPDATE

Server broadcasts game state changes to players within visibility range (typically 3x3 chunks around player).

**Diff-Based Broadcasting**:
```python
{
    "id": null,
    "type": "event_game_update",
    "payload": {
        "entities": [
            # Added or updated entities
            {
                "id": "player_456",
                "type": "player",
                "username": "player2",
                "x": 15,
                "y": 10,
                "facing_direction": "east",
                "animation_state": "walking",
                "current_hp": 10,
                "max_hp": 10,
                "visual_state": {
                    "equipment": {
                        "weapon": {"item_id": 5, "sprite_id": "bronze_sword"},
                        "body": null,
                        # ... other slots
                    }
                }
            },
            {
                "id": "npc_789",
                "type": "npc",
                "name": "Goblin",
                "x": 20,
                "y": 15,
                "current_hp": 7,
                "max_hp": 10,
                "combat_state": "in_combat"
            }
        ],
        "removed_entities": [
            123,  # player_id for players
            "npc_456"  # entity_id for NPCs
        ],
        "map_id": "samplemap"
    },
    "version": "2.0"
}
```

**Update Triggers**:
- Player movement
- Combat damage/death
- Equipment changes
- Animation state changes
- Entity spawn/despawn

**Visibility Rules**:
- **Range**: Chunk radius (default: 1 = 3x3 chunks = 48x48 tiles)
- **Diff-Based**: Only sends changes (added/updated/removed)
- **Per-Player**: Each player gets personalized updates
- **Rate**: Game tick rate (default: 20 TPS = 50ms per tick)

### EVENT_SKILLS

```python
{
    "id": null,
    "type": "event_skills",
    "payload": {
        "skills": [
            {
                "skill_id": 1,
                "name": "attack",
                "current_level": 5,
                "current_xp": 150,
                "target_xp": 388
            },
            {
                "skill_id": 2,
                "name": "defense",
                "current_level": 3,
                "current_xp": 80,
                "target_xp": 224
            },
            # ... all 9 skills
        ]
    },
    "version": "2.0"
}
```

**Skills**:
- `attack`, `strength`, `defense`, `hitpoints`, `ranged`, `magic`, `prayer`, `woodcutting`, `mining`

### EVENT_INVENTORY_UPDATE

```python
{
    "id": null,
    "type": "event_inventory_update",
    "payload": {
        "inventory": {
            "3": {
                "item_id": 1,
                "quantity": 15,  # Quantity increased
                "name": "Bronze arrow"
            },
            "5": null  # Item removed
        }
    },
    "version": "2.0"
}
```

### EVENT_EQUIPMENT_UPDATE

```python
{
    "id": null,
    "type": "event_equipment_update",
    "payload": {
        "equipment": {
            "weapon": {
                "item_id": 5,
                "name": "Bronze sword"
            },
            "body": null  # Unequipped
        }
    },
    "version": "2.0"
}
```

### EVENT_GROUND_ITEMS_UPDATE

```python
{
    "id": null,
    "type": "event_ground_items_update",
    "payload": {
        "added": [
            {
                "ground_item_id": "ground_item_123",
                "item_id": 5,
                "quantity": 1,
                "x": 15,
                "y": 20,
                "map_id": "samplemap",
                "owner_id": 456,  # null if public
                "despawn_time": 1706832060.0
            }
        ],
        "removed": ["ground_item_789"]
    },
    "version": "2.0"
}
```

## Error Handling

### Error Response Structure

```python
{
    "id": "correlation-id",
    "type": "resp_error",
    "payload": {
        "error_code": "ERROR_CODE_ENUM",
        "message": "Human-readable error message",
        "details": {
            # Optional context-specific details
        }
    },
    "version": "2.0"
}
```

### Error Code Categories

**Authentication Errors** (`AUTHENTICATION_*`):
- `AUTHENTICATION_FAILED`
- `AUTHENTICATION_MISSING_TOKEN`
- `AUTHENTICATION_INVALID_PAYLOAD`
- `AUTHENTICATION_EXPIRED_TOKEN`

**Movement Errors** (`MOVEMENT_*`):
- `MOVEMENT_RATE_LIMITED`
- `MOVEMENT_BLOCKED`
- `MOVEMENT_INVALID_DIRECTION`
- `MOVEMENT_OUT_OF_BOUNDS`

**Chat Errors** (`CHAT_*`):
- `CHAT_RATE_LIMITED`
- `CHAT_MESSAGE_TOO_LONG`
- `CHAT_EMPTY_MESSAGE`
- `CHAT_DM_RECIPIENT_NOT_FOUND`
- `CHAT_INVALID_CHANNEL`

**Inventory Errors** (`INVENTORY_*`):
- `INVENTORY_SLOT_EMPTY`
- `INVENTORY_INVALID_SLOT`
- `INVENTORY_FULL`
- `INVENTORY_ITEM_NOT_FOUND`

**Equipment Errors** (`EQUIPMENT_*`):
- `EQUIPMENT_SLOT_INVALID`
- `EQUIPMENT_REQUIREMENTS_NOT_MET`
- `EQUIPMENT_WRONG_SLOT`
- `EQUIPMENT_INVENTORY_FULL`

**Combat Errors** (`COMBAT_*`):
- `COMBAT_TARGET_NOT_FOUND`
- `COMBAT_OUT_OF_RANGE`
- `COMBAT_ALREADY_IN_COMBAT`
- `COMBAT_INVALID_TARGET`

**Chunk Errors** (`CHUNKS_*`):
- `CHUNKS_RADIUS_TOO_LARGE`
- `CHUNKS_MAP_NOT_FOUND`
- `CHUNKS_INVALID_COORDINATES`

**Generic Errors**:
- `INVALID_MESSAGE_FORMAT`: Malformed message
- `UNKNOWN_MESSAGE_TYPE`: Unrecognized message type
- `PROTOCOL_VERSION_MISMATCH`: Incompatible protocol version
- `INTERNAL_SERVER_ERROR`: Unexpected server error

### Client Error Handling Pattern

```python
async def send_command(message_type, payload):
    correlation_id = str(uuid.uuid4())
    message = {
        "id": correlation_id,
        "type": message_type,
        "payload": payload,
        "version": "2.0"
    }
    
    await websocket.send_bytes(msgpack.packb(message))
    
    # Wait for response with matching correlation ID
    response = await wait_for_response(correlation_id, timeout=5.0)
    
    if response["type"] == "resp_error":
        error = response["payload"]
        raise GameError(
            error["error_code"],
            error["message"],
            error.get("details", {})
        )
    
    return response["payload"]
```

## Testing

### Unit Testing WebSocket Protocol

**Test Utilities** (`server/src/tests/websocket_test_utils.py`):

```python
from server.src.tests.websocket_test_utils import WebSocketTestClient

async def test_movement(test_client: WebSocketTestClient):
    # test_client is already authenticated
    
    # Wait for movement cooldown
    await asyncio.sleep(0.6)
    
    # Send move command
    response = await test_client.send_command(
        MessageType.CMD_MOVE,
        {"direction": "DOWN"}
    )
    
    # Assertions
    assert response.type == MessageType.RESP_SUCCESS
    assert response.payload["new_position"]["y"] == 11
```

**WebSocketTestClient Features**:
- Automatic correlation ID tracking
- Response matching with timeouts
- Event capture with filtering
- Background message processing
- Proper async cleanup

### Integration Testing

**Test Setup**:
```python
@pytest_asyncio.fixture
async def test_client(fake_valkey, game_state_managers):
    # Fixture creates authenticated WebSocket connection
    # - Creates test player in database
    # - Generates JWT token
    # - Authenticates via WebSocket
    # - Returns WebSocketTestClient instance
    
    yield client
    
    # Automatic cleanup:
    # - Deletes test player
    # - Closes WebSocket connection
    # - Clears Valkey cache
```

**Running Integration Tests**:
```bash
# Start test containers
cd docker && docker-compose -f docker-compose.test.yml up -d --build

# Run database migrations
docker exec docker-server-1 bash -c "cd server && alembic upgrade head"

# Start server in background
docker exec -d docker-server-1 uvicorn server.src.main:app --host 0.0.0.0 --port 8000

# Run integration tests
docker exec docker-server-1 bash -c "RUN_INTEGRATION_TESTS=1 pytest -v"
```

### Test Coverage

**Current Integration Tests** (19 tests):
- ✅ Movement (valid, invalid, rate limiting)
- ✅ Chat (local, rate limiting, empty messages)
- ✅ Chunk requests (valid, excessive radius)
- ✅ Visibility system (range, filtering, diff calculation)
- ✅ FakeValkey (hset, hget, delete, exists, clear)

## Protocol Version History

### Version 2.0 (Current)
- Complete message type reorganization
- Structured error codes with categories
- Diff-based game updates
- Pydantic schema validation
- Combat state management
- Ground item system

### Version 1.0 (Deprecated)
- Basic movement and chat
- Simple error responses
- Full-state broadcasting
- No correlation IDs

## Security Considerations

### Rate Limiting
- **Movement**: 500ms cooldown per move
- **Chat**: 1 second cooldown per message
- **Combat**: Attack speed based on weapon
- **Chunk Queries**: Max radius 5, no cooldown (cached client-side)

### Validation
- All inputs validated server-side
- Client cannot bypass skill requirements
- Server authoritative for all game state
- No client-side prediction of critical actions

### Authentication
- JWT tokens expire after 24 hours (configurable)
- Tokens validated on every WebSocket connection
- No session persistence without re-authentication
- Tokens contain only username (no sensitive data)

### Anti-Cheat
- Movement speed enforced server-side
- Position updates validated against map collision
- Item/equipment operations require inventory checks
- Combat calculations server-authoritative

## Best Practices

### Client Implementation
1. **Always use correlation IDs** for commands/queries
2. **Handle all error codes** gracefully
3. **Implement timeout logic** (default: 5 seconds)
4. **Process events asynchronously** (don't block on event handling)
5. **Cache chunk data** (don't re-request same chunks)
6. **Respect rate limits** (track cooldowns client-side)

### Server Implementation
1. **Validate all inputs** before processing
2. **Use structured logging** with context
3. **Return explicit error codes** (never generic errors)
4. **Broadcast events efficiently** (diff-based updates)
5. **Clean up on disconnect** (remove from caches)
6. **Use GSM for all state** (no direct database access)

### Message Design
1. **Keep payloads minimal** (only necessary data)
2. **Use enums for types** (not magic strings)
3. **Version all messages** (for future compatibility)
4. **Document all fields** (with types and examples)
5. **Test error paths** (not just happy paths)

---

**This protocol is the authoritative specification for all client-server communication in rpg-engine. All implementations must adhere to this specification.**
