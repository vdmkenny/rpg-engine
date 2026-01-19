# RPG Engine Architecture

This document describes the server-side architecture, focusing on the GameStateManager
and service hierarchy. It serves as a reference for both human developers and AI coding agents.

## Table of Contents

1. [Overview](#overview)
2. [Service Hierarchy](#service-hierarchy)
3. [GameStateManager](#gamestatemanager)
4. [Data Flow](#data-flow)
5. [Valkey Schema](#valkey-schema)
6. [Write Strategy](#write-strategy)
7. [API Reference](#api-reference)
8. [For AI Agents](#for-ai-agents)

---

## Overview

The server uses a layered architecture with clear separation of concerns:

```
+--------------------------------------------------------------------+
|                         ENTRY POINTS                                |
|  WebSocket API (websockets.py) | REST API | Game Loop              |
+---------------------------------+----------------------------------+
                                  |
                                  v
+--------------------------------------------------------------------+
|                    BUSINESS LOGIC SERVICES                          |
|  HpService | InventoryService | EquipmentService | SkillService    |
|                    GroundItemService                                |
|                                                                     |
|  These services contain game logic (damage calculation, XP         |
|  formulas, equip requirements) but delegate ALL state operations   |
|  to the GameStateManager.                                          |
+---------------------------------+----------------------------------+
                                  |
                                  v
+--------------------------------------------------------------------+
|                   GAME STATE MANAGER (Singleton)                    |
|                                                                     |
|  The ONLY component that interacts with Valkey and PostgreSQL.     |
|  All game state reads and writes go through this layer.            |
|                                                                     |
|  Responsibilities:                                                  |
|  - Player state: position, HP, inventory, equipment, skills        |
|  - World state: ground items                                       |
|  - Lifecycle: load on connect, sync on disconnect, batch sync      |
|  - Online player tracking                                          |
+---------------------------------+----------------------------------+
                                  |
                  +---------------+---------------+
                  v                               v
       +------------------+            +------------------+
       |  Valkey (Cache)  |            |    PostgreSQL    |
       |  Hot data only   |            |  Durable storage |
       +------------------+            +------------------+
```

### Key Principles

1. **Single Source of Truth**: GameStateManager (GSM) is the only component aware of storage backends
2. **Valkey-First**: Online player state lives in Valkey for performance; PostgreSQL is for durability
3. **Batch Persistence**: Writes accumulate in Valkey, sync to PostgreSQL periodically
4. **Services for Logic**: Business logic in services, state access through GSM
5. **Consistent Keys**: All Valkey keys use `player_id` (integer), not `username`

---

## Service Hierarchy

### Entry Points -> Services -> GSM

| Layer | Components | Responsibility |
|-------|------------|----------------|
| **Entry Points** | `websockets.py`, `api/*.py`, `game_loop.py` | Handle client requests, orchestrate services |
| **Business Logic** | `HpService`, `InventoryService`, `EquipmentService`, `SkillService`, `GroundItemService` | Game rules, calculations, validation |
| **State Management** | `GameStateManager` | All state read/write, storage abstraction |
| **Reference Data** | `ItemService` | Read-only item definitions (not through GSM) |

### Service Responsibilities

| Service | Purpose | Key Methods |
|---------|---------|-------------|
| **HpService** | Damage, healing, death/respawn | `deal_damage()`, `heal()`, `full_death_sequence()` |
| **InventoryService** | Add/remove/move items | `add_item()`, `remove_item()`, `move_item()` |
| **EquipmentService** | Equip/unequip, stat bonuses | `equip_from_inventory()`, `get_total_stats()`, `get_max_hp()` |
| **SkillService** | XP gain, level calculation | `add_experience()`, `get_player_skills()` |
| **GroundItemService** | Drop/pickup items | `drop_from_inventory()`, `pickup_ground_item()` |
| **ItemService** | Item definitions (read-only) | `get_item_by_id()`, `get_all_items()` |

### What Services Must NOT Do

- Do NOT import `GlideClient` or make Valkey calls
- Do NOT import `AsyncSession` or make direct database queries for mutable state
- Do NOT track whether players are online/offline
- Do NOT manage dirty tracking or sync logic

### What Services SHOULD Do

- Contain game logic (formulas, validation, business rules)
- Call `get_game_state_manager()` for all state operations
- Return domain objects or result types
- Log business events

---

## GameStateManager

### Singleton Pattern

```python
from server.src.services.game_state_manager import (
    init_game_state_manager,  # Called once at startup
    get_game_state_manager,   # Get the singleton instance
)

# At startup (main.py):
gsm = init_game_state_manager(valkey_client, AsyncSessionLocal)

# In services and handlers:
gsm = get_game_state_manager()
inventory = await gsm.get_inventory(player_id)
```

### Internal State

```python
class GameStateManager:
    _valkey: GlideClient              # Valkey connection
    _session_factory: sessionmaker    # PostgreSQL session factory
    _online_players: Set[int]         # Currently online player IDs
    _username_to_id: Dict[str, int]   # Cache for username lookups
```

### Method Categories

| Category | Methods | When Used |
|----------|---------|-----------|
| **Registry** | `register_online_player()`, `unregister_online_player()`, `is_online()` | Player connect/disconnect |
| **Position/HP** | `get_player_position()`, `set_player_position()`, `get_player_hp()`, `set_player_hp()` | Movement, combat |
| **Inventory** | `get_inventory()`, `set_inventory_slot()`, `delete_inventory_slot()`, `get_free_slot()` | Item operations |
| **Equipment** | `get_equipment()`, `set_equipment_slot()`, `delete_equipment_slot()` | Equip/unequip |
| **Skills** | `get_skill()`, `get_all_skills()`, `set_skill()` | XP/leveling |
| **Ground Items** | `add_ground_item()`, `remove_ground_item()`, `get_visible_ground_items()` | Drop/pickup |
| **Lifecycle** | `load_player_state()`, `sync_player_to_db()`, `cleanup_player_state()` | Connect/disconnect |
| **Batch Sync** | `sync_all()`, `sync_all_on_shutdown()` | Periodic, shutdown |

---

## Data Flow

### Player Connect

```
1. WebSocket authenticates player via JWT
2. Query PostgreSQL for player record
3. gsm.load_player_state(player_id, username):
   a. Query inventory, equipment, skills from PostgreSQL
   b. Write all state to Valkey (player:{id}, inventory:{id}, etc.)
   c. Register player as online
4. Send WELCOME message to client
```

### During Gameplay

```
1. Client sends action (MOVE, EQUIP, DROP, etc.)
2. Handler calls appropriate service
3. Service calls GSM for state read/write
4. GSM reads/writes Valkey, marks dirty for batch sync
5. Handler sends response to client

Note: NO database writes during normal gameplay
```

### Periodic Batch Sync (every N ticks)

```
1. Game loop calls gsm.sync_all()
2. For each dirty set (inventory, equipment, skills, position, ground_items):
   a. Read dirty IDs from Valkey
   b. Read current state from Valkey
   c. Bulk write to PostgreSQL
   d. Clear dirty set
```

### Player Disconnect

```
1. WebSocket connection closes
2. gsm.sync_player_to_db(player_id, username):
   a. Read all state from Valkey
   b. Write to PostgreSQL (immediate commit)
3. gsm.cleanup_player_state(player_id):
   a. Delete all Valkey keys for player
   b. Unregister from online set
```

---

## Valkey Schema

All player keys use `player_id` (integer) for consistency:

| Key Pattern | Type | Fields |
|-------------|------|--------|
| `player:{player_id}` | Hash | `username`, `x`, `y`, `map_id`, `current_hp`, `max_hp` |
| `inventory:{player_id}` | Hash | `{slot}` -> JSON `{"item_id": N, "quantity": N, "durability": N}` |
| `equipment:{player_id}` | Hash | `{slot_name}` -> JSON `{"item_id": N, "quantity": N, "durability": N}` |
| `skills:{player_id}` | Hash | `{skill_name}` -> JSON `{"skill_id": N, "level": N, "experience": N}` |
| `ground_item:{id}` | Hash | `id`, `item_id`, `map_id`, `x`, `y`, `quantity`, `dropped_by`, `despawn_at`, etc. |
| `ground_items:map:{map_id}` | Set | Ground item IDs on this map |
| `ground_items:next_id` | String | Counter for unique ground item IDs |

### Dirty Tracking Keys

| Key | Type | Contents |
|-----|------|----------|
| `dirty:position` | Set | Player IDs with unsaved position/HP |
| `dirty:inventory` | Set | Player IDs with unsaved inventory |
| `dirty:equipment` | Set | Player IDs with unsaved equipment |
| `dirty:skills` | Set | Player IDs with unsaved skills |
| `dirty:ground_items` | Set | Map IDs with unsaved ground items |

---

## Write Strategy

### Batch Writes (Default)

All gameplay state changes write to Valkey only, with periodic sync to PostgreSQL:

- Player position and HP
- Inventory changes (add, remove, move items)
- Equipment changes (equip, unequip)
- Skill XP and level changes
- Ground item creation/removal

### Immediate Writes (Exceptions)

Security-critical operations that must be durable immediately:

| Operation | Why Immediate |
|-----------|---------------|
| Player registration | New account must be durable |
| Password change | Security-critical |
| Account deletion/ban | Security-critical |

### Forced Sync Points

| Event | What Syncs |
|-------|------------|
| Player disconnect | All state for that player |
| Server shutdown | All state for all players |
| Periodic interval | All dirty state |

---

## API Reference

### Initialization

```python
# Called once during server startup (main.py lifespan)
init_game_state_manager(
    valkey: GlideClient,
    session_factory: sessionmaker[AsyncSession]
) -> GameStateManager

# Get singleton instance (use everywhere else)
get_game_state_manager() -> GameStateManager
```

### Player Registry

```python
register_online_player(player_id: int, username: str) -> None
unregister_online_player(player_id: int) -> None
is_online(player_id: int) -> bool
get_online_player_ids() -> Set[int]
get_player_id_by_username(username: str) -> Optional[int]
```

### Position & HP

```python
async get_player_position(player_id: int) -> Optional[Dict]
    # Returns: {"x": int, "y": int, "map_id": str}

async set_player_position(player_id: int, x: int, y: int, map_id: str) -> None

async get_player_hp(player_id: int) -> Optional[Dict]
    # Returns: {"current_hp": int, "max_hp": int}

async set_player_hp(player_id: int, current_hp: int, max_hp: int = None) -> None
```

### Inventory

```python
async get_inventory(player_id: int) -> Dict[int, Dict]
    # Returns: {slot: {"item_id": N, "quantity": N, "durability": N}}

async get_inventory_slot(player_id: int, slot: int) -> Optional[Dict]
async set_inventory_slot(player_id: int, slot: int, item_id: int,
                         quantity: int, durability: Optional[int]) -> None
async delete_inventory_slot(player_id: int, slot: int) -> None
async get_free_inventory_slot(player_id: int, max_slots: int = 28) -> Optional[int]
async get_inventory_count(player_id: int) -> int
async clear_inventory(player_id: int) -> None
```

### Equipment

```python
async get_equipment(player_id: int) -> Dict[str, Dict]
    # Returns: {slot_name: {"item_id": N, "quantity": N, "durability": N}}

async get_equipment_slot(player_id: int, slot: str) -> Optional[Dict]
async set_equipment_slot(player_id: int, slot: str, item_id: int,
                         quantity: int, durability: Optional[int]) -> None
async delete_equipment_slot(player_id: int, slot: str) -> None
async clear_equipment(player_id: int) -> None
```

### Skills

```python
async get_skill(player_id: int, skill_name: str) -> Optional[Dict]
    # Returns: {"skill_id": N, "level": N, "experience": N}

async get_all_skills(player_id: int) -> Dict[str, Dict]
async set_skill(player_id: int, skill_name: str, skill_id: int,
                level: int, experience: int) -> None
```

### Ground Items

```python
async add_ground_item(
    item_id: int, item_name: str, display_name: str, rarity: str,
    map_id: str, x: int, y: int, quantity: int,
    dropped_by_player_id: Optional[int] = None
) -> int  # Returns ground_item_id

async remove_ground_item(ground_item_id: int, map_id: str) -> bool
async get_ground_item(ground_item_id: int) -> Optional[Dict]
async get_visible_ground_items(
    map_id: str, x: int, y: int, player_id: Optional[int], tile_radius: int = 32
) -> List[Dict]
async cleanup_expired_ground_items(map_id: str) -> int
```

### Lifecycle

```python
async load_player_state(player_id: int, username: str) -> None
    # Load from PostgreSQL to Valkey on connect

async sync_player_to_db(player_id: int, username: str) -> None
    # Sync from Valkey to PostgreSQL on disconnect

async cleanup_player_state(player_id: int) -> None
    # Delete Valkey keys after sync
```

### Batch Sync

```python
async sync_all() -> Dict[str, int]
    # Periodic sync, returns count by type

async sync_all_on_shutdown(active_players: Dict[str, int]) -> int
    # Shutdown sync, returns player count
```

---

## For AI Agents

This section provides quick reference patterns for AI coding agents working on this codebase.

### Quick Reference

When modifying game state:

```python
# DO THIS:
from server.src.services.game_state_manager import get_game_state_manager

async def my_handler(...):
    gsm = get_game_state_manager()
    inventory = await gsm.get_inventory(player_id)
    await gsm.set_inventory_slot(player_id, slot, item_id, quantity, durability)

# DON'T DO THIS:
from glide import GlideClient  # Never import in services
await valkey.hset(...)          # Never direct Valkey access
await db.execute(...)           # Never direct DB access for mutable state
```

### Service Pattern

When creating or modifying a service:

```python
from server.src.services.game_state_manager import get_game_state_manager
from server.src.core.logging_config import get_logger

logger = get_logger(__name__)

class MyService:
    @staticmethod
    async def do_something(player_id: int, ...) -> Result:
        gsm = get_game_state_manager()

        # Read state
        current_state = await gsm.get_inventory(player_id)

        # Business logic here
        if not some_validation(current_state):
            return Result(success=False, message="Validation failed")

        # Write state
        await gsm.set_inventory_slot(player_id, slot, item_id, qty, dur)

        logger.info("Did something", extra={"player_id": player_id})
        return Result(success=True, ...)
```

### Files to Know

| File | Purpose |
|------|---------|
| `server/src/services/game_state_manager.py` | Single source of truth for all state |
| `server/src/api/websockets.py` | WebSocket handlers, uses GSM for lifecycle |
| `server/src/game/game_loop.py` | Calls `gsm.sync_all()` periodically |
| `server/src/main.py` | Initializes GSM at startup |
| `server/src/services/*.py` | Business logic services (call GSM) |

### Common Patterns

**Get player state:**
```python
gsm = get_game_state_manager()
pos = await gsm.get_player_position(player_id)  # {x, y, map_id}
hp = await gsm.get_player_hp(player_id)         # {current_hp, max_hp}
inv = await gsm.get_inventory(player_id)        # {slot: item_data}
eq = await gsm.get_equipment(player_id)         # {slot_name: item_data}
skills = await gsm.get_all_skills(player_id)    # {skill_name: skill_data}
```

**Check if player online:**
```python
gsm = get_game_state_manager()
if gsm.is_online(player_id):
    # Player state is in Valkey
else:
    # Player is offline, state only in PostgreSQL
```

**In tests:**
```python
@pytest_asyncio.fixture
async def game_state_manager(fake_valkey):
    from server.src.services.game_state_manager import init_game_state_manager
    return init_game_state_manager(fake_valkey, AsyncSessionLocal)
```

### Checklist for Service Changes

When modifying a service, verify:

- [ ] No direct imports of `GlideClient`, `AsyncSession` for state operations
- [ ] All state reads go through `get_game_state_manager()`
- [ ] All state writes go through `get_game_state_manager()`
- [ ] Business logic remains in the service (not moved to GSM)
- [ ] Logging uses `get_logger(__name__)`
- [ ] Tests use the `game_state_manager` fixture

### Checklist for WebSocket Handler Changes

When modifying websocket handlers, verify:

- [ ] Player lifecycle uses `gsm.load_player_state()` on connect
- [ ] Player lifecycle uses `gsm.sync_player_to_db()` on disconnect
- [ ] Player lifecycle uses `gsm.cleanup_player_state()` after sync
- [ ] State operations use GSM methods, not direct Valkey calls
- [ ] Position updates use `gsm.set_player_position()`
- [ ] HP updates use `gsm.set_player_hp()`
