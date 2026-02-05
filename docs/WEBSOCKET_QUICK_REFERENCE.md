# WebSocket Protocol Quick Reference

> **For full specification, see [WEBSOCKET_PROTOCOL.md](WEBSOCKET_PROTOCOL.md)**

---

## Message Types Summary

| Type | Direction | Description | Correlation ID |
|------|-----------|-------------|----------------|
| `cmd_authenticate` | Client → Server | Authenticate with JWT token | Required |
| `cmd_move` | Client → Server | Move player | Required |
| `cmd_chat_send` | Client → Server | Send chat message | Required |
| `cmd_inventory_move` | Client → Server | Move inventory items | Required |
| `cmd_inventory_sort` | Client → Server | Sort inventory | Required |
| `cmd_item_drop` | Client → Server | Drop item to ground | Required |
| `cmd_item_pickup` | Client → Server | Pickup ground item | Required |
| `cmd_item_equip` | Client → Server | Equip item | Required |
| `cmd_item_unequip` | Client → Server | Unequip item | Required |
| `cmd_attack` | Client → Server | Attack target | Required |
| `cmd_toggle_auto_retaliate` | Client → Server | Toggle auto-retaliation | Required |
| `cmd_update_appearance` | Client → Server | Update appearance | Required |
| `query_inventory` | Client → Server | Get inventory data | Required |
| `query_equipment` | Client → Server | Get equipment data | Required |
| `query_stats` | Client → Server | Get player stats | Required |
| `query_map_chunks` | Client → Server | Get map chunks | Required |
| `resp_success` | Server → Client | Command success | Matches request |
| `resp_error` | Server → Client | Command/query error | Matches request |
| `resp_data` | Server → Client | Query response | Matches request |
| `event_welcome` | Server → Client | Welcome message | None |
| `event_chunk_update` | Server → Client | Map chunk data | None |
| `event_state_update` | Server → Client | State changes | None |
| `event_game_update` | Server → Client | Game entity updates | None |
| `event_chat_message` | Server → Client | Chat broadcast | None |
| `event_player_joined` | Server → Client | Player joined | None |
| `event_player_left` | Server → Client | Player left | None |
| `event_player_died` | Server → Client | Player died | None |
| `event_player_respawn` | Server → Client | Player respawned | None |
| `event_server_shutdown` | Server → Client | Server shutdown | None |
| `event_combat_action` | Server → Client | Combat event | None |
| `event_appearance_update` | Server → Client | Appearance updated | None |

---

## Chat Channel Limits

| Channel | Max Length | Permission |
|---------|------------|------------|
| `local` | 280 chars | All players |
| `global` | 200 chars | Admin only |
| `dm` | 500 chars | All players |

---

## Error Codes Reference

### Authentication
- `AUTH_INVALID_TOKEN` - Invalid JWT token
- `AUTH_EXPIRED_TOKEN` - JWT token expired
- `AUTH_PLAYER_NOT_FOUND` - Player doesn't exist
- `AUTH_PLAYER_BANNED` - Account banned
- `AUTH_PLAYER_TIMEOUT` - Account temporarily suspended

### Movement
- `MOVE_INVALID_DIRECTION` - Invalid direction
- `MOVE_COLLISION_DETECTED` - Blocked by obstacle
- `MOVE_RATE_LIMITED` - Moving too fast
- `MOVE_INVALID_POSITION` - Invalid position

### Chat
- `CHAT_MESSAGE_TOO_LONG` - Message too long
- `CHAT_PERMISSION_DENIED` - No permission
- `CHAT_RATE_LIMITED` - Sending too fast
- `CHAT_RECIPIENT_NOT_FOUND` - DM target not found

### Inventory
- `INV_INVALID_SLOT` - Invalid slot number (0-27)
- `INV_SLOT_EMPTY` - Slot is empty
- `INV_INVENTORY_FULL` - No free slots
- `INV_CANNOT_STACK` - Items can't stack
- `INV_INSUFFICIENT_QUANTITY` - Not enough items

### Equipment
- `EQ_ITEM_NOT_EQUIPABLE` - Can't equip item
- `EQ_REQUIREMENTS_NOT_MET` - Requirements not met
- `EQ_INVALID_SLOT` - Invalid equipment slot
- `EQ_CANNOT_UNEQUIP_FULL_INV` - Inventory full

### Ground Items
- `GROUND_TOO_FAR` - Item too far away
- `GROUND_PROTECTED_LOOT` - Protected for other player
- `GROUND_ITEM_NOT_FOUND` - Item doesn't exist

### Map
- `MAP_INVALID_COORDS` - Invalid coordinates
- `MAP_CHUNK_LIMIT_EXCEEDED` - Too many chunks requested (>5 radius)
- `MAP_NOT_FOUND` - Map doesn't exist

### Appearance
- `APPEARANCE_INVALID_VALUE` - Invalid appearance field value
- `APPEARANCE_UPDATE_FAILED` - Failed to update appearance

### System
- `SYS_DATABASE_ERROR` - Database error
- `SYS_SERVICE_UNAVAILABLE` - Service unavailable
- `SYS_INTERNAL_ERROR` - Internal server error

---

## Rate Limits

| Operation | Cooldown |
|-----------|----------|
| Movement | 0.5 seconds |
| Chat (local) | 1.0 seconds |
| Chat (global) | 3.0 seconds |
| Inventory ops | 0.5 seconds |
| Equipment ops | 0.5 seconds |
| Item drop/pickup | 0.2 seconds |
| Attack | 0.5 seconds |
| Auto-retaliate toggle | 0.5 seconds |
| Appearance update | 5.0 seconds |

---

## Appearance Fields

Valid appearance customization fields:

### Core
- `body_type` - Player body type (e.g., `TYPE_A`, `TYPE_B`, `TYPE_C`)
- `skin_tone` - Skin color (e.g., `TONE_1` through `TONE_8`)
- `head_type` - Head shape (e.g., `HEAD_1` through `HEAD_6`)
- `hair_style` - Hair style (e.g., `STYLE_BALD`, `STYLE_SHORT`, `STYLE_LONG`, `STYLE_PONYTAIL`)
- `hair_color` - Hair color (e.g., `BLACK`, `BROWN`, `BLONDE`, `RED`, `WHITE`)
- `eye_color` - Eye color (e.g., `BROWN`, `BLUE`, `GREEN`, `GRAY`)

### Facial Hair
- `facial_hair_style` - Beard/mustache style (e.g., `NONE`, `GOATEE`, `BEARD_SHORT`, `BEARD_LONG`)
- `facial_hair_color` - Facial hair color (e.g., `BLACK`, `BROWN`, `GRAY`)

### Clothing
- `shirt_style` - Shirt type (e.g., `PLAIN`, `STRIPED`, `VEST`)
- `shirt_color` - Shirt color (e.g., `WHITE`, `BLUE`, `RED`, `GREEN`, `GRAY`)
- `pants_style` - Pants type (e.g., `PLAIN`, `JEANS`)
- `pants_color` - Pants color (e.g., `BLUE`, `BLACK`, `BROWN`, `GRAY`)
- `shoes_style` - Shoe type (e.g., `BOOTS`, `SHOES`)
- `shoes_color` - Shoe color (e.g., `BLACK`, `BROWN`)

---

## Equipment Slots

Valid equipment slot names:
- `head` - Helmet/headgear
- `body` - Chest armor
- `legs` - Leg armor
- `feet` - Boots
- `hands` - Gloves
- `main_hand` - Primary weapon
- `off_hand` - Shield or secondary weapon
- `back` - Cape/cloak
- `belt` - Belt/accessories

---

## Movement Directions

Valid movement directions:
- `UP`
- `DOWN`
- `LEFT`
- `RIGHT`

---

## Protocol Implementation

### Client Connection
```python
import msgpack
import websockets

# Connect and authenticate
websocket = await websockets.connect("ws://localhost:8000/ws")
auth_msg = {
    "id": "auth-1",
    "type": "cmd_authenticate",
    "payload": {"token": "your-jwt-token"},
    "timestamp": int(time.time() * 1000),
    "version": "2.0"
}
await websocket.send(msgpack.packb(auth_msg, use_bin_type=True))
```

### Message Handling
```python
# Receive and decode message
data = await websocket.recv()
message = msgpack.unpackb(data, raw=False)

# Send command with correlation ID
cmd_msg = {
    "id": "unique-id",
    "type": "cmd_move", 
    "payload": {"direction": "UP"},
    "timestamp": int(time.time() * 1000),
    "version": "2.0"
}
await websocket.send(msgpack.packb(cmd_msg, use_bin_type=True))
```

### Response Matching
```python
# Match responses by correlation ID
pending_requests = {}
correlation_id = "move-123"
pending_requests[correlation_id] = asyncio.Future()

# When response received
if message.get("id") == correlation_id:
    future = pending_requests.pop(correlation_id)
    future.set_result(message)
```

---

## Common Patterns

### Request-Response
1. Client sends command/query with correlation ID
2. Server responds with matching correlation ID
3. Client matches response to original request

### Events
1. Server sends event (no correlation ID)
2. Client processes event immediately
3. No response expected

### Error Handling
1. Check response type (`resp_error`)
2. Extract `error_code` for programmatic handling
3. Show `message` to user
4. Follow `suggested_action` if provided
5. Wait `retry_after` seconds if rate limited

### State Updates
1. Server sends `event_state_update`
2. Client updates local game state
3. UI reflects new state immediately

---

## Testing

Run WebSocket protocol tests:
```bash
cd docker && docker-compose -f docker-compose.test.yml up -d
docker exec docker-server-1 bash -c "RUN_INTEGRATION_TESTS=1 pytest server/src/tests/test_websocket_chat.py -v"
```

---

**Document Version**: 2.0.1  
**Last Updated**: February 2026
