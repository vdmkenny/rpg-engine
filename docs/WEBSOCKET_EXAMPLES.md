# WebSocket Protocol Message Examples

This document provides detailed examples of message flows for the RPG Engine WebSocket protocol.

## Authentication Flow

### 1. Successful Authentication

**Client Request:**
```json
{
    "id": "auth-12345",
    "type": "cmd_authenticate",
    "payload": {
        "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0dXNlciIsImV4cCI6MTY0Mjg2NzYzNCwiaWF0IjoxNjQyNzgxMjM0fQ.abc123"
    },
    "timestamp": 1642781234567,
    "version": "2.0"
}
```

**Server Response (Success):**
```json
{
    "id": "auth-12345",
    "type": "resp_success",
    "payload": {
        "message": "Authentication successful",
        "player_id": 123
    },
    "timestamp": 1642781234570,
    "version": "2.0"
}
```

**Server Event (Welcome):**
```json
{
    "type": "event_welcome",
    "payload": {
        "message": "Welcome to RPG Engine, testuser!",
        "motd": "WebSocket Protocol unified - Enhanced with correlation IDs and structured responses",
        "player": {
            "id": 123,
            "username": "testuser",
            "position": {
                "map_id": "samplemap",
                "x": 10,
                "y": 15
            },
            "hp": {
                "current": 100,
                "max": 100
            }
        },
        "config": {
            "move_cooldown": 0.5,
            "animation_duration": 0.3,
            "protocol_version": "2.0"
        }
    },
    "timestamp": 1642781234575,
    "version": "2.0"
}
```

### 2. Authentication Failure

**Client Request:**
```json
{
    "id": "auth-12346",
    "type": "cmd_authenticate",
    "payload": {
        "token": "invalid-token"
    },
    "timestamp": 1642781234567,
    "version": "2.0"
}
```

**Server Response (Error):**
```json
{
    "id": "auth-12346",
    "type": "resp_error",
    "payload": {
        "error_code": "AUTH_INVALID_TOKEN",
        "error_category": "permission",
        "message": "Invalid authentication token provided",
        "suggested_action": "Please log in again to get a fresh token"
    },
    "timestamp": 1642781234570,
    "version": "2.0"
}
```

## Movement Flow

### 1. Successful Movement

**Client Request:**
```json
{
    "id": "move-001",
    "type": "cmd_move",
    "payload": {
        "direction": "UP"
    },
    "timestamp": 1642781235000,
    "version": "2.0"
}
```

**Server Response:**
```json
{
    "id": "move-001",
    "type": "resp_success",
    "payload": {
        "new_position": {"x": 10, "y": 14},
        "old_position": {"x": 10, "y": 15}
    },
    "timestamp": 1642781235010,
    "version": "2.0"
}
```

**Server Event (Game Update - broadcasted to nearby players):**
```json
{
    "type": "event_game_update",
    "payload": {
        "entities": [
            {
                "id": "player-123",
                "type": "player",
                "username": "testuser",
                "position": {"x": 10, "y": 14},
                "sprite": "player_sprite.png",
                "direction": "UP"
            }
        ],
        "removed_entities": [],
        "map_id": "samplemap"
    },
    "timestamp": 1642781235020,
    "version": "2.0"
}
```

### 2. Movement Blocked (Collision)

**Client Request:**
```json
{
    "id": "move-002",
    "type": "cmd_move",
    "payload": {
        "direction": "UP"
    },
    "timestamp": 1642781235500,
    "version": "2.0"
}
```

**Server Response:**
```json
{
    "id": "move-002",
    "type": "resp_error",
    "payload": {
        "error_code": "MOVE_COLLISION_DETECTED",
        "error_category": "validation",
        "message": "Movement blocked by obstacle",
        "details": {
            "current_position": {"x": 10, "y": 14}
        }
    },
    "timestamp": 1642781235510,
    "version": "2.0"
}
```

### 3. Movement Rate Limited

**Client Request:**
```json
{
    "id": "move-003",
    "type": "cmd_move",
    "payload": {
        "direction": "RIGHT"
    },
    "timestamp": 1642781235100,
    "version": "2.0"
}
```

**Server Response:**
```json
{
    "id": "move-003",
    "type": "resp_error",
    "payload": {
        "error_code": "MOVE_RATE_LIMITED",
        "error_category": "rate_limit",
        "message": "Moving too quickly",
        "retry_after": 0.3,
        "suggested_action": "Wait before moving again"
    },
    "timestamp": 1642781235110,
    "version": "2.0"
}
```

## Chat Flow

### 1. Local Chat Message

**Client Request:**
```json
{
    "id": "chat-001",
    "type": "cmd_chat_send",
    "payload": {
        "message": "Hello everyone nearby!",
        "channel": "local"
    },
    "timestamp": 1642781236000,
    "version": "2.0"
}
```

**Server Response:**
```json
{
    "id": "chat-001",
    "type": "resp_success",
    "payload": {
        "channel": "local",
        "message": "Hello everyone nearby!"
    },
    "timestamp": 1642781236010,
    "version": "2.0"
}
```

**Server Event (Chat Message - broadcasted to nearby players):**
```json
{
    "type": "event_chat_message",
    "payload": {
        "sender": "testuser",
        "message": "Hello everyone nearby!",
        "channel": "local",
        "sender_position": {
            "x": 10,
            "y": 14,
            "map_id": "samplemap"
        }
    },
    "timestamp": 1642781236020,
    "version": "2.0"
}
```

### 2. Global Chat (Admin Only)

**Client Request:**
```json
{
    "id": "chat-002",
    "type": "cmd_chat_send",
    "payload": {
        "message": "Server restart in 5 minutes",
        "channel": "global"
    },
    "timestamp": 1642781237000,
    "version": "2.0"
}
```

**Server Response (Admin User):**
```json
{
    "id": "chat-002",
    "type": "resp_success",
    "payload": {
        "channel": "global",
        "message": "Server restart in 5 minutes"
    },
    "timestamp": 1642781237010,
    "version": "2.0"
}
```

**Server Event (Global Chat - broadcasted to all players):**
```json
{
    "type": "event_chat_message",
    "payload": {
        "sender": "AdminUser",
        "message": "Server restart in 5 minutes",
        "channel": "global",
        "sender_position": null
    },
    "timestamp": 1642781237020,
    "version": "2.0"
}
```

### 3. Global Chat Permission Denied

**Client Request:**
```json
{
    "id": "chat-003",
    "type": "cmd_chat_send",
    "payload": {
        "message": "I want to send global message",
        "channel": "global"
    },
    "timestamp": 1642781238000,
    "version": "2.0"
}
```

**Server Response (Regular User):**
```json
{
    "id": "chat-003",
    "type": "resp_error",
    "payload": {
        "error_code": "CHAT_PERMISSION_DENIED",
        "error_category": "permission",
        "message": "Global chat is restricted to administrators",
        "suggested_action": "Use local chat instead"
    },
    "timestamp": 1642781238010,
    "version": "2.0"
}
```

### 4. Direct Message

**Client Request:**
```json
{
    "id": "chat-004",
    "type": "cmd_chat_send",
    "payload": {
        "message": "Hey, want to team up?",
        "channel": "dm",
        "recipient": "frienduser"
    },
    "timestamp": 1642781239000,
    "version": "2.0"
}
```

**Server Response:**
```json
{
    "id": "chat-004",
    "type": "resp_success",
    "payload": {
        "channel": "dm",
        "message": "Hey, want to team up?"
    },
    "timestamp": 1642781239010,
    "version": "2.0"
}
```

**Server Event (Sent to recipient only):**
```json
{
    "type": "event_chat_message",
    "payload": {
        "sender": "testuser",
        "message": "Hey, want to team up?",
        "channel": "dm",
        "sender_position": {
            "x": 10,
            "y": 14,
            "map_id": "samplemap"
        }
    },
    "timestamp": 1642781239020,
    "version": "2.0"
}
```

### 5. Message Too Long

**Client Request:**
```json
{
    "id": "chat-005",
    "type": "cmd_chat_send",
    "payload": {
        "message": "This is a very long message that exceeds the 280 character limit for local chat messages. Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.",
        "channel": "local"
    },
    "timestamp": 1642781240000,
    "version": "2.0"
}
```

**Server Response:**
```json
{
    "id": "chat-005",
    "type": "resp_error",
    "payload": {
        "error_code": "CHAT_MESSAGE_TOO_LONG",
        "error_category": "validation",
        "message": "Message exceeds maximum length for local chat",
        "details": {
            "max_length": 280,
            "actual_length": 350,
            "channel": "local"
        },
        "suggested_action": "Shorten your message and try again"
    },
    "timestamp": 1642781240010,
    "version": "2.0"
}
```

## Inventory Operations

### 1. Query Inventory

**Client Request:**
```json
{
    "id": "inv-query-001",
    "type": "query_inventory",
    "payload": {},
    "timestamp": 1642781241000,
    "version": "2.0"
}
```

**Server Response:**
```json
{
    "id": "inv-query-001",
    "type": "resp_data",
    "payload": {
        "inventory": {
            "slots": {
                "0": {
                    "item_id": 1,
                    "quantity": 10,
                    "durability": 100.0,
                    "item_name": "Health Potion",
                    "item_type": "consumable"
                },
                "1": {
                    "item_id": 2,
                    "quantity": 1,
                    "durability": 85.5,
                    "item_name": "Iron Sword",
                    "item_type": "weapon"
                }
            },
            "capacity": 30,
            "used_slots": 2
        },
        "query_type": "inventory"
    },
    "timestamp": 1642781241010,
    "version": "2.0"
}
```

### 2. Move Inventory Item

**Client Request:**
```json
{
    "id": "inv-move-001",
    "type": "cmd_inventory_move",
    "payload": {
        "from_slot": 0,
        "to_slot": 5
    },
    "timestamp": 1642781242000,
    "version": "2.0"
}
```

**Server Response:**
```json
{
    "id": "inv-move-001",
    "type": "resp_success",
    "payload": {
        "message": "Item moved successfully"
    },
    "timestamp": 1642781242010,
    "version": "2.0"
}
```

**Server Event (State Update):**
```json
{
    "type": "event_state_update",
    "payload": {
        "update_type": "full",
        "target": "personal",
        "systems": {
            "inventory": {
                "slots": {
                    "5": {
                        "item_id": 1,
                        "quantity": 10,
                        "durability": 100.0,
                        "item_name": "Health Potion",
                        "item_type": "consumable"
                    },
                    "1": {
                        "item_id": 2,
                        "quantity": 1,
                        "durability": 85.5,
                        "item_name": "Iron Sword",
                        "item_type": "weapon"
                    }
                },
                "capacity": 30,
                "used_slots": 2
            }
        }
    },
    "timestamp": 1642781242020,
    "version": "2.0"
}
```

### 3. Drop Item

**Client Request:**
```json
{
    "id": "drop-001",
    "type": "cmd_item_drop",
    "payload": {
        "inventory_slot": 0,
        "quantity": 5
    },
    "timestamp": 1642781243000,
    "version": "2.0"
}
```

**Server Response:**
```json
{
    "id": "drop-001",
    "type": "resp_success",
    "payload": {
        "message": "Item dropped successfully",
        "ground_item_id": "ground-item-uuid-12345"
    },
    "timestamp": 1642781243010,
    "version": "2.0"
}
```

## Equipment Operations

### 1. Query Equipment

**Client Request:**
```json
{
    "id": "eq-query-001",
    "type": "query_equipment",
    "payload": {},
    "timestamp": 1642781244000,
    "version": "2.0"
}
```

**Server Response:**
```json
{
    "id": "eq-query-001",
    "type": "resp_data",
    "payload": {
        "equipment": {
            "slots": {
                "weapon": {
                    "item_id": 2,
                    "durability": 85.5,
                    "item_name": "Iron Sword",
                    "stats": {
                        "attack": 15,
                        "durability": 100
                    }
                },
                "armor": null,
                "helmet": null,
                "boots": null,
                "gloves": null,
                "ring": null,
                "amulet": null
            }
        },
        "query_type": "equipment"
    },
    "timestamp": 1642781244010,
    "version": "2.0"
}
```

### 2. Equip Item

**Client Request:**
```json
{
    "id": "equip-001",
    "type": "cmd_item_equip",
    "payload": {
        "inventory_slot": 1
    },
    "timestamp": 1642781245000,
    "version": "2.0"
}
```

**Server Response:**
```json
{
    "id": "equip-001",
    "type": "resp_success",
    "payload": {
        "message": "Item equipped successfully"
    },
    "timestamp": 1642781245010,
    "version": "2.0"
}
```

**Server Event (State Update with inventory, equipment, and stats):**
```json
{
    "type": "event_state_update",
    "payload": {
        "update_type": "full",
        "target": "personal",
        "systems": {
            "inventory": {
                "slots": {
                    "0": {
                        "item_id": 1,
                        "quantity": 5,
                        "durability": 100.0,
                        "item_name": "Health Potion",
                        "item_type": "consumable"
                    }
                },
                "capacity": 30,
                "used_slots": 1
            },
            "equipment": {
                "slots": {
                    "weapon": {
                        "item_id": 2,
                        "durability": 85.5,
                        "item_name": "Iron Sword"
                    }
                }
            },
            "stats": {
                "attack": 25,
                "defense": 10,
                "max_hp": 100,
                "current_hp": 100
            }
        }
    },
    "timestamp": 1642781245020,
    "version": "2.0"
}
```

## Error Scenarios

### 1. Invalid Message Format

**Client Request (Malformed):**
```json
{
    "type": "cmd_move",
    "payload": "invalid"
}
```

**Server Action:** Connection terminated immediately with close code 1008 (Policy Violation)

### 2. Missing Correlation ID

**Client Request:**
```json
{
    "type": "cmd_move",
    "payload": {
        "direction": "UP"
    },
    "timestamp": 1642781246000,
    "version": "2.0"
}
```

**Server Action:** Connection terminated immediately (commands require correlation IDs)

### 3. Invalid Equipment Slot

**Client Request:**
```json
{
    "id": "unequip-001",
    "type": "cmd_item_unequip",
    "payload": {
        "equipment_slot": "invalid_slot"
    },
    "timestamp": 1642781247000,
    "version": "2.0"
}
```

**Server Response:**
```json
{
    "id": "unequip-001",
    "type": "resp_error",
    "payload": {
        "error_code": "EQ_INVALID_SLOT",
        "error_category": "validation",
        "message": "Invalid equipment slot: invalid_slot",
        "details": {
            "valid_slots": ["weapon", "armor", "helmet", "boots", "gloves", "ring", "amulet"]
        }
    },
    "timestamp": 1642781247010,
    "version": "2.0"
}
```

## Player Connection Events

### 1. Player Joins

**Server Event (Broadcasted to existing players):**
```json
{
    "type": "event_player_joined",
    "payload": {
        "player": {
            "username": "newplayer",
            "position": {
                "x": 5,
                "y": 10,
                "map_id": "samplemap"
            },
            "type": "player"
        }
    },
    "timestamp": 1642781248000,
    "version": "2.0"
}
```

### 2. Player Leaves

**Server Event (Broadcasted to remaining players):**
```json
{
    "type": "event_player_left",
    "payload": {
        "username": "departingplayer",
        "reason": "Disconnected"
    },
    "timestamp": 1642781249000,
    "version": "2.0"
}
```

## Map Query

### 1. Request Map Chunks

**Client Request:**
```json
{
    "id": "map-001",
    "type": "query_map_chunks",
    "payload": {
        "map_id": "samplemap",
        "center_x": 10,
        "center_y": 15,
        "radius": 2
    },
    "timestamp": 1642781250000,
    "version": "2.0"
}
```

**Server Response:**
```json
{
    "id": "map-001",
    "type": "resp_data",
    "payload": {
        "chunks": [
            {
                "x": 0,
                "y": 0,
                "tiles": [
                    [1, 1, 2, 3],
                    [1, 0, 0, 3],
                    [1, 0, 0, 3],
                    [2, 2, 2, 3]
                ],
                "entities": []
            }
        ],
        "map_id": "samplemap",
        "center": {"x": 10, "y": 15},
        "radius": 2,
        "query_type": "map_chunks"
    },
    "timestamp": 1642781250010,
    "version": "2.0"
}
```

### 2. Invalid Chunk Request

**Client Request:**
```json
{
    "id": "map-002",
    "type": "query_map_chunks",
    "payload": {
        "map_id": "samplemap",
        "center_x": 10,
        "center_y": 15,
        "radius": 10
    },
    "timestamp": 1642781251000,
    "version": "2.0"
}
```

**Server Response:**
```json
{
    "id": "map-002",
    "type": "resp_error",
    "payload": {
        "error_code": "MAP_CHUNK_LIMIT_EXCEEDED",
        "error_category": "validation",
        "message": "Requested radius exceeds maximum allowed",
        "details": {
            "max_radius": 5,
            "requested_radius": 10
        },
        "suggested_action": "Request fewer chunks at once"
    },
    "timestamp": 1642781251010,
    "version": "2.0"
}
```

## Server Shutdown

**Server Event (Broadcasted to all connected players):**
```json
{
    "type": "event_server_shutdown",
    "payload": {
        "message": "Server maintenance starting soon",
        "countdown_seconds": 30
    },
    "timestamp": 1642781252000,
    "version": "2.0"
}
```

## Message Validation Patterns

All messages must follow these validation rules:

1. **Required Fields**: `type`, `payload`, `timestamp`, `version`
2. **Correlation IDs**: Required for all commands and queries
3. **Payload Validation**: Each message type has specific payload requirements
4. **Rate Limiting**: Commands subject to cooldown periods
5. **Authentication**: All operations (except authentication) require valid session

Invalid messages result in either structured error responses or connection termination, depending on the severity of the violation.