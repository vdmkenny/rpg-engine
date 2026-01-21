# RPG Engine WebSocket Protocol Documentation

## Overview

The RPG Engine uses a binary WebSocket protocol with msgpack serialization for real-time communication between client and server. The protocol implements correlation IDs for request/response pairing, structured error handling, and comprehensive message validation.

**Protocol Version**: 2.0  
**Serialization**: MessagePack (msgpack)  
**Transport**: WebSocket over HTTP/HTTPS  
**Authentication**: JWT tokens

## Message Structure

All WebSocket messages follow the universal `WSMessage` envelope:

```json
{
    "id": "optional-correlation-id",
    "type": "message_type",
    "payload": { /* type-specific data */ },
    "timestamp": 1642781234567,
    "version": "2.0"
}
```

### Field Descriptions

- **id** (optional): Correlation ID for commands and queries. Used to match requests with responses.
- **type**: Message type from the MessageType enum
- **payload**: Type-specific payload data
- **timestamp**: UTC timestamp in milliseconds (auto-generated)
- **version**: Protocol version (always "2.0")

## Connection Flow

### 1. WebSocket Connection
```
Client -> Server: WebSocket connection to /ws
Server -> Client: Connection accepted
```

### 2. Authentication
```
Client -> Server: CMD_AUTHENTICATE with JWT token
Server -> Client: RESP_SUCCESS or RESP_ERROR
Server -> Client: EVENT_WELCOME (if successful)
```

### 3. Ongoing Communication
- Commands: Client sends commands, server responds with RESP_SUCCESS/RESP_ERROR
- Queries: Client sends queries, server responds with RESP_DATA
- Events: Server sends events (broadcasts, notifications)

## Message Types

### Client → Server: Commands (State-Changing Operations)

Commands modify game state and expect success/error responses.

#### CMD_AUTHENTICATE
Authenticate the WebSocket connection using JWT token.

**Payload**:
```json
{
    "token": "eyJhbGciOiJIUzI1NiIs..."
}
```

**Response**: RESP_SUCCESS or RESP_ERROR

**Example**:
```json
{
    "id": "auth-001",
    "type": "cmd_authenticate",
    "payload": {
        "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
    },
    "timestamp": 1642781234567,
    "version": "2.0"
}
```

#### CMD_MOVE
Move the player in a specified direction.

**Payload**:
```json
{
    "direction": "UP" | "DOWN" | "LEFT" | "RIGHT"
}
```

**Response**: RESP_SUCCESS with position data, or RESP_ERROR

**Example**:
```json
{
    "id": "move-001",
    "type": "cmd_move",
    "payload": {
        "direction": "UP"
    },
    "timestamp": 1642781234567,
    "version": "2.0"
}
```

#### CMD_CHAT_SEND
Send a chat message to a specific channel.

**Payload**:
```json
{
    "message": "Hello world!",
    "channel": "local" | "global" | "dm",
    "recipient": "username" // Required for DM channel
}
```

**Channel Limits**:
- **local**: 280 characters
- **global**: 200 characters (admin only)
- **dm**: 500 characters

**Response**: RESP_SUCCESS or RESP_ERROR

**Example**:
```json
{
    "id": "chat-001",
    "type": "cmd_chat_send",
    "payload": {
        "message": "Hello everyone!",
        "channel": "local"
    },
    "timestamp": 1642781234567,
    "version": "2.0"
}
```

#### CMD_INVENTORY_MOVE
Move items within the inventory.

**Payload**:
```json
{
    "from_slot": 0,
    "to_slot": 5
}
```

**Response**: RESP_SUCCESS or RESP_ERROR

#### CMD_INVENTORY_SORT
Sort inventory by specified criteria.

**Payload**:
```json
{
    "sort_by": "category" | "rarity" | "value" | "name"
}
```

**Response**: RESP_SUCCESS or RESP_ERROR

#### CMD_ITEM_DROP
Drop items from inventory to the ground.

**Payload**:
```json
{
    "inventory_slot": 0,
    "quantity": 1
}
```

**Response**: RESP_SUCCESS or RESP_ERROR

#### CMD_ITEM_PICKUP
Pickup items from the ground.

**Payload**:
```json
{
    "ground_item_id": "item-uuid-12345"
}
```

**Response**: RESP_SUCCESS or RESP_ERROR

#### CMD_ITEM_EQUIP
Equip items from inventory.

**Payload**:
```json
{
    "inventory_slot": 0
}
```

**Response**: RESP_SUCCESS or RESP_ERROR

#### CMD_ITEM_UNEQUIP
Unequip items to inventory.

**Payload**:
```json
{
    "equipment_slot": "weapon" | "armor" | "helmet" | "boots" | "gloves" | "ring" | "amulet"
}
```

**Response**: RESP_SUCCESS or RESP_ERROR

### Client → Server: Queries (Data Retrieval)

Queries retrieve data and expect RESP_DATA responses.

#### QUERY_INVENTORY
Request current inventory state.

**Payload**: `{}`

**Response**: RESP_DATA with inventory data

#### QUERY_EQUIPMENT
Request current equipment state.

**Payload**: `{}`

**Response**: RESP_DATA with equipment data

#### QUERY_STATS
Request player statistics.

**Payload**: `{}`

**Response**: RESP_DATA with stats data

#### QUERY_MAP_CHUNKS
Request map chunk data around player position.

**Payload**:
```json
{
    "map_id": "samplemap",
    "center_x": 10,
    "center_y": 15,
    "radius": 2
}
```

**Response**: RESP_DATA with chunk data

## Server → Client: Responses

### RESP_SUCCESS
Indicates successful command execution.

**Payload**: Variable success data
```json
{
    "id": "auth-001",
    "type": "resp_success",
    "payload": {
        "message": "Authentication successful"
    },
    "timestamp": 1642781234567,
    "version": "2.0"
}
```

### RESP_ERROR
Indicates command/query failure with structured error information.

**Payload**:
```json
{
    "error_code": "CHAT_MESSAGE_TOO_LONG",
    "error_category": "validation" | "permission" | "system" | "rate_limit",
    "message": "Human-readable error message",
    "details": { /* additional context */ },
    "retry_after": 1.5, // seconds (for rate limiting)
    "suggested_action": "Wait before trying again"
}
```

**Example**:
```json
{
    "id": "chat-001",
    "type": "resp_error",
    "payload": {
        "error_code": "CHAT_MESSAGE_TOO_LONG",
        "error_category": "validation",
        "message": "Message exceeds maximum length for local chat",
        "details": {
            "max_length": 280,
            "actual_length": 350
        },
        "suggested_action": "Shorten your message and try again"
    },
    "timestamp": 1642781234567,
    "version": "2.0"
}
```

### RESP_DATA
Returns query results.

**Payload**: Variable query response data

**Example**:
```json
{
    "id": "inv-query-001",
    "type": "resp_data",
    "payload": {
        "inventory": {
            "slots": {
                "0": {"item_id": 1, "quantity": 10},
                "1": {"item_id": 2, "quantity": 1}
            },
            "capacity": 30
        },
        "query_type": "inventory"
    },
    "timestamp": 1642781234567,
    "version": "2.0"
}
```

## Server → Client: Events

Events are server-initiated messages (no correlation ID required).

### EVENT_WELCOME
Sent after successful authentication.

**Payload**:
```json
{
    "message": "Welcome to RPG Engine, username!",
    "motd": "Message of the day",
    "player": {
        "id": 123,
        "username": "player1",
        "position": {"map_id": "samplemap", "x": 10, "y": 15},
        "hp": {"current": 100, "max": 100}
    },
    "config": {
        "move_cooldown": 0.5,
        "animation_duration": 0.3,
        "protocol_version": "2.0"
    }
}
```

### EVENT_STATE_UPDATE
Consolidated state changes for the player.

**Payload**:
```json
{
    "update_type": "full" | "delta",
    "target": "personal" | "nearby" | "map" | "global",
    "systems": {
        "player": { /* position, HP, basic info */ },
        "inventory": { /* items, capacity */ },
        "equipment": { /* equipped items */ },
        "stats": { /* aggregated stats */ },
        "entities": { /* visible game entities */ }
    }
}
```

### EVENT_GAME_UPDATE
Real-time game entity updates (movement, spawns, etc).

**Payload**:
```json
{
    "entities": [
        {
            "id": "player-123",
            "type": "player",
            "username": "player1",
            "position": {"x": 10, "y": 15},
            "sprite": "player_sprite.png"
        }
    ],
    "removed_entities": ["entity-456"],
    "map_id": "samplemap"
}
```

### EVENT_CHAT_MESSAGE
Chat message broadcast.

**Payload**:
```json
{
    "sender": "player1",
    "message": "Hello everyone!",
    "channel": "local",
    "sender_position": {"x": 10, "y": 15, "map_id": "samplemap"}
}
```

### EVENT_PLAYER_JOINED
Another player joined the game.

**Payload**:
```json
{
    "player": {
        "username": "newPlayer",
        "position": {"x": 10, "y": 15, "map_id": "samplemap"},
        "type": "player"
    }
}
```

### EVENT_PLAYER_LEFT
Another player left the game.

**Payload**:
```json
{
    "username": "departingPlayer",
    "reason": "Disconnected"
}
```

### EVENT_SERVER_SHUTDOWN
Server is shutting down.

**Payload**:
```json
{
    "message": "Server maintenance in progress",
    "countdown_seconds": 30
}
```

## Error Codes

The protocol uses semantic error codes for clear error identification:

### Authentication Errors
- `AUTH_INVALID_TOKEN`: JWT token is invalid or malformed
- `AUTH_EXPIRED_TOKEN`: JWT token has expired
- `AUTH_PLAYER_NOT_FOUND`: Player doesn't exist in database
- `AUTH_PLAYER_BANNED`: Player account is banned
- `AUTH_PLAYER_TIMEOUT`: Player account is temporarily suspended

### Movement Errors
- `MOVE_INVALID_DIRECTION`: Invalid movement direction
- `MOVE_COLLISION_DETECTED`: Movement blocked by obstacle
- `MOVE_RATE_LIMITED`: Moving too frequently
- `MOVE_INVALID_POSITION`: Invalid target position

### Chat Errors
- `CHAT_MESSAGE_TOO_LONG`: Message exceeds channel limit
- `CHAT_PERMISSION_DENIED`: No permission for channel
- `CHAT_RATE_LIMITED`: Sending messages too frequently
- `CHAT_RECIPIENT_NOT_FOUND`: DM recipient doesn't exist

### Inventory Errors
- `INV_INVALID_SLOT`: Invalid inventory slot number
- `INV_SLOT_EMPTY`: No item in specified slot
- `INV_INVENTORY_FULL`: Inventory has no free slots
- `INV_CANNOT_STACK`: Items cannot be stacked together
- `INV_INSUFFICIENT_QUANTITY`: Not enough items to complete operation

### Equipment Errors
- `EQ_ITEM_NOT_EQUIPABLE`: Item cannot be equipped
- `EQ_REQUIREMENTS_NOT_MET`: Player doesn't meet item requirements
- `EQ_INVALID_SLOT`: Invalid equipment slot
- `EQ_CANNOT_UNEQUIP_FULL_INV`: Cannot unequip with full inventory

### Ground Item Errors
- `GROUND_TOO_FAR`: Item too far from player
- `GROUND_PROTECTED_LOOT`: Item protected for another player
- `GROUND_ITEM_NOT_FOUND`: Ground item doesn't exist

### Map Errors
- `MAP_INVALID_COORDS`: Invalid map coordinates
- `MAP_CHUNK_LIMIT_EXCEEDED`: Requested too many chunks
- `MAP_NOT_FOUND`: Map doesn't exist

### System Errors
- `SYS_DATABASE_ERROR`: Database operation failed
- `SYS_SERVICE_UNAVAILABLE`: Service temporarily unavailable
- `SYS_INTERNAL_ERROR`: Internal server error

## Rate Limiting

The protocol implements per-operation rate limiting:

- **Movement**: 0.5 seconds between moves
- **Chat**: 1.0 seconds between local messages, 3.0 seconds for global
- **Inventory Operations**: 0.1 seconds between operations
- **Equipment Operations**: 0.1 seconds between operations

Rate limit violations return `RESP_ERROR` with `retry_after` field indicating wait time.

## Implementation Notes

### Message Serialization
All messages are serialized using MessagePack with `use_bin_type=True`:

```python
import msgpack
packed_data = msgpack.packb(message.model_dump(), use_bin_type=True)
await websocket.send_bytes(packed_data)
```

### Message Validation
All incoming messages are validated using Pydantic models. Invalid messages result in connection termination.

### Correlation IDs
- Commands and queries **must** include correlation IDs
- Events and responses to events **do not** use correlation IDs
- Correlation IDs should be unique per client session

### Error Handling
- Protocol errors (malformed messages) result in connection termination
- Business logic errors return structured error responses
- All errors include human-readable messages and actionable error codes

### Security
- Authentication required before any game operations
- JWT tokens validated on every WebSocket connection
- Rate limiting prevents abuse
- Input validation prevents injection attacks

## Client Implementation Example

```python
import asyncio
import msgpack
import websockets
from typing import Dict, Any

class RPGWebSocketClient:
    def __init__(self, token: str):
        self.token = token
        self.correlation_counter = 0
        
    async def connect(self, uri: str):
        self.websocket = await websockets.connect(uri)
        await self.authenticate()
        
    async def authenticate(self):
        auth_msg = {
            "id": self.next_correlation_id(),
            "type": "cmd_authenticate",
            "payload": {"token": self.token},
            "timestamp": int(time.time() * 1000),
            "version": "2.0"
        }
        await self.send_message(auth_msg)
        
    async def send_message(self, message: Dict[str, Any]):
        packed = msgpack.packb(message, use_bin_type=True)
        await self.websocket.send(packed)
        
    async def receive_message(self) -> Dict[str, Any]:
        data = await self.websocket.recv()
        return msgpack.unpackb(data, raw=False)
        
    def next_correlation_id(self) -> str:
        self.correlation_counter += 1
        return f"client-{self.correlation_counter}"
```

## Testing

The protocol includes comprehensive integration tests covering:
- Authentication flows
- All command and query types
- Error handling scenarios
- Rate limiting behavior
- Message validation
- Chat system functionality

Tests achieve 100% pass rate and verify protocol compliance.