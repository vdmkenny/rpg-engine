# GSM Architecture Patterns & Guidelines

**Document Version**: 2.0  
**Created**: January 2026  
**Updated**: February 2026  
**Purpose**: Standard patterns for AI agents and developers working with the rpg-engine GameStateManager

## Core Architecture Principles

### 1. Data Layer Separation

**GameStateManager (GSM) Responsibilities:**
- **ONLY** manage data persistence (Valkey + PostgreSQL)
- Handle online/offline player state transitions
- Provide CRUD operations for game entities
- Maintain hot/cold data lifecycle
- **NEVER** contain business logic or game rules

**Service Layer Responsibilities:**
- **ALL** business logic and validation
- Cross-domain coordination between services
- Game rule enforcement
- **NEVER** access database or Valkey directly

### 2. Data Access Patterns

**Mandatory Data Flow:**
```
API Layer → Service Layer → GSM → Valkey/PostgreSQL
```

**Forbidden Patterns:**
```
Service → Direct Database ❌
Service → Direct Valkey ❌
API → Direct GSM ❌
GSM → Business Logic ❌
```

### 3. GSM Data Architecture

**Permanent Cache (Never Expires):**
- Item definitions/metadata
- Skill definitions/metadata  
- Map data
- Any static reference data

**Hot/Cold Player Data (TTL-Based):**
- **Tier 1** (Essential): Player position, HP, online status
- **Tier 2** (On-Demand): Inventory, equipment, player skills/XP

## Implementation Patterns

### GSM Method Design

**✅ Correct GSM Methods (Pure Data Operations):**
```python
async def get_player_inventory(self, player_id: int) -> Dict[int, Dict]
async def set_player_position(self, player_id: int, x: int, y: int) -> bool
async def update_inventory_slot(self, player_id: int, slot: int, data: Dict) -> bool
def get_item_metadata(self, item_id: int) -> Optional[Dict]  # Sync for cached data
```

**❌ Forbidden GSM Methods (Business Logic):**
```python
async def add_item_to_inventory(self, player_id: int, item_id: int) -> AddResult  ❌
async def can_equip_item(self, player_id: int, item_id: int) -> bool  ❌
async def deal_damage(self, player_id: int, damage: int) -> DamageResult  ❌
```

### Service Implementation Pattern

**✅ Correct Service Structure:**
```python
class InventoryService:
    @staticmethod
    async def add_item(player_id: int, item_id: int, quantity: int) -> AddItemResult:
        gsm = get_game_state_manager()
        
        # 1. Get metadata from permanent cache (synchronous)
        item_meta = gsm.get_item_metadata(item_id)
        if not item_meta:
            return AddItemResult(success=False, error="Item not found")
        
        # 2. Get current state (auto-loads if needed)
        inventory = await gsm.get_player_inventory(player_id)
        
        # 3. Apply business logic
        target_slot = self._find_best_slot(inventory, item_meta, quantity)
        if target_slot is None:
            return AddItemResult(success=False, error="Inventory full")
        
        # 4. Update via GSM
        success = await gsm.update_inventory_slot(player_id, target_slot, new_data)
        return AddItemResult(success=success, slot=target_slot)
```

**❌ Anti-Patterns to Avoid:**
```python
# Direct database access
async with get_db_session() as db:  ❌
    result = await db.execute(select(Item)...)

# Calling other GSM business logic  
return await gsm.add_item_with_validation(...)  ❌

# Online/offline logic in services
if gsm.is_online(player_id):  ❌
    # Different logic paths
```

### Service Method Signatures

**✅ Correct Signatures (No Database Sessions):**
```python
async def add_item(player_id: int, item_id: int, quantity: int) -> AddItemResult
async def equip_item(player_id: int, slot: int, equipment_slot: str) -> EquipResult
async def move_player(player_id: int, x: int, y: int) -> MoveResult
```

**❌ Old Patterns (Removed):**
```python
async def add_item(db: AsyncSession, player_id: int, ...) -> AddItemResult  ❌
```

## Hot/Cold Data Lifecycle

### Data Loading Strategy

**Startup (Server):**
- Load ALL reference data (items, skills) into permanent Valkey cache
- **FAIL STARTUP** if reference data loading fails (no fallbacks)

**Player Connect:**
- Load Tier 1 data (position, HP) immediately  
- Load Tier 2 data (inventory, equipment, skills) on first access

**Player Disconnect:**
- Set TTL on all player data (don't delete immediately)
- Allow graceful reconnection within TTL window

**Memory Pressure:**
- Evict Tier 2 data for oldest offline players
- Never evict data for online players
- Respect configurable player limits

### Auto-Loading Pattern

**Services should see NO difference between online and offline players.** GSM handles data loading transparently:

```python
# ✅ Service code - same for online/offline players
inventory = await gsm.get_inventory(player_id)  # Auto-loads from DB if needed

# ❌ Old anti-pattern - online/offline branching
if gsm.is_online(player_id):
    inventory = await gsm.get_inventory(player_id)
else:
    inventory = await gsm.get_inventory_offline(player_id)  # REMOVED
```

**GSM Auto-Loading Behavior:**
1. **Check Valkey first**: Try to get data from Valkey cache
2. **Auto-load if missing**: If not in Valkey, load from database
3. **Cache with TTL**: Store in Valkey with configured TTL using `EXPIRE`
4. **Transparent to services**: Services always call the same methods

**Valkey Unavailable Fallback:**
- **USE_VALKEY=false**: Always use database (for development/testing)
- **Valkey unavailable**: Log warning, use database fallback
- **Never fail**: System remains functional without Valkey

### TTL Management

Uses built-in Valkey TTL commands:
- **`EXPIRE key seconds`**: Set TTL when loading data
- **`TTL key`**: Check remaining time (future: memory pressure management)
- **Automatic expiry**: Valkey handles expiration, no manual cleanup needed

### TTL Configuration
```yaml
game_state_cache:
  max_cached_players: 1000
  essential_data_ttl: 3600    # 1 hour
  inventory_ttl: 1800         # 30 minutes  
  equipment_ttl: 1800         # 30 minutes
  skills_ttl: 900             # 15 minutes
  sync_interval: 60           # Batch sync frequency
  dirty_player_threshold: 50  # Early sync trigger
```

## Cross-Service Communication

**✅ Correct Pattern:**
```python
class EquipmentService:
    @staticmethod
    async def equip_item(player_id: int, inv_slot: int, eq_slot: str) -> EquipResult:
        # 1. Validate via other services
        can_equip = await SkillService.meets_requirements(player_id, item_id)
        if not can_equip:
            return EquipResult(success=False, error="Requirements not met")
            
        # 2. Coordinate with other services  
        inv_result = await InventoryService.remove_item(player_id, inv_slot)
        
        # 3. Update state via GSM
        gsm = get_game_state_manager()
        await gsm.update_equipment_slot(player_id, eq_slot, item_data)
        
        # 4. Notify dependent services
        await HpService.recalculate_max_hp(player_id)
        
        return EquipResult(success=True)
```

## Error Handling Patterns

### GSM Error Handling
- **Valkey Unavailable**: Fail fast, don't start server
- **Data Loading Failure**: Log error, fail operation 
- **Partial Load Failure**: Rollback, return error result

### Service Error Handling
- Return structured result objects with success/failure
- Log business events with structured context
- Never silently fail or return inconsistent state

### Startup Error Handling
- Reference data loading failure → Exit with error code 1
- Database connection failure → Exit with error code 1  
- Valkey connection failure → Exit with error code 1

## Testing Patterns

### GSM Testing
- Test data persistence and retrieval correctness
- Test TTL and cleanup behavior
- Mock Valkey/database for unit tests
- **Don't test business logic in GSM tests**

### Service Testing  
- Mock GSM responses using fixtures
- Test all business logic and validation
- Test error conditions and edge cases
- **Don't test data persistence in service tests**

### Integration Testing
- Test complete player lifecycle
- Test cross-service interactions
- Test memory management under load
- Test reference data loading at startup

## Configuration Management

### Required Settings
- All TTL values configurable
- Memory limits configurable  
- Batch sync timing configurable
- Feature flags for gradual rollouts

### Environment Handling
- Development: Shorter TTLs, smaller limits
- Production: Longer TTLs, higher limits
- Testing: In-memory backends, fast cleanup

## Monitoring & Observability

### Key Metrics (Prometheus)
- Memory usage (Valkey memory, cached players)
- Data loading times (database → Valkey)
- Cache hit/miss rates per data type
- Service response times
- Player lifecycle events

### Critical Logs
- Reference data loading success/failure
- Player data loading/eviction events  
- Memory pressure and cleanup activities
- Cross-service operation failures

## Migration Guidelines

### Adding New Services
1. Define clear domain boundaries
2. Implement pure business logic (no data access)
3. Use GSM singleton for all state operations
4. Return structured result objects
5. Write comprehensive tests with mocked GSM

### Modifying Existing Services  
1. **No backwards compatibility** - clean break approach
2. Remove database session parameters completely
3. Rewrite complete test suite per service
4. Update all callers simultaneously

### Schema Changes
1. Reference data changes require new server version
2. Player data schema changes need migration scripts
3. Always maintain data consistency during transitions

### Common Anti-Patterns

### ❌ Things to Never Do
1. **"God Service" GSM** - Don't put business logic in GSM
2. **Database Shortcuts** - Don't bypass GSM for any data access
3. **Mixed Responsibilities** - Don't mix validation and persistence  
4. **Leaky Abstractions** - Don't expose GSM internals to services
5. **Silent Failures** - Always return explicit success/failure results
6. **Fallback Patterns** - No database fallbacks, fail fast instead
7. **Dictionary Access on Pydantic Models** - Use attribute access (`model.field`), not dict access (`model["field"]`)
8. **Legacy Compatibility** - Never create backward compatibility layers, update all references

### Code Review Red Flags
- Services importing database models for data access
- GSM methods containing validation or business rules
- Online/offline branching logic in services
- Direct Valkey/database operations outside GSM
- Database session parameters in service methods
- Accessing Pydantic models with dictionary syntax
- Creating legacy compatibility wrappers

## Player State Management Patterns

### Player Data Structure

**PlayerData Schema (Pydantic)**:
```python
class PlayerData(BaseModel):
    id: int
    username: str
    x: int
    y: int
    map_id: str
    is_online: bool
    facing_direction: Direction  # Runtime state
    animation_state: AnimationState  # Runtime state
    current_hp: int
    max_hp: int  # Computed from hitpoints skill level
    total_level: int  # Computed from all skill levels
```

**Key Fields**:
- **Database Fields**: `id`, `username`, `x`, `y`, `map_id`
- **Runtime Fields**: `is_online`, `facing_direction`, `animation_state` (not persisted)
- **Computed Fields**: `max_hp`, `total_level` (calculated from other data)

### PlayerStateManager Methods

**Position Management**:
```python
async def get_player_position(player_id: int) -> Optional[Dict[str, Any]]
async def set_player_position(player_id: int, x: int, y: int, map_id: str) -> bool
```

**HP Management**:
```python
async def get_player_hp(player_id: int) -> Optional[Dict[str, int]]
async def set_player_hp(player_id: int, current_hp: int, max_hp: int) -> bool
```

**Online Registry**:
```python
async def register_online_player(player_id: int, username: str) -> None
async def unregister_online_player(player_id: int) -> None
async def is_online(player_id: int) -> bool
async def get_all_online_player_ids() -> List[int]
async def get_username_for_player(player_id: int) -> Optional[str]
```

**Combat State**:
```python
async def get_player_combat_state(player_id: int) -> Optional[Dict[str, Any]]
async def set_player_combat_state(player_id: int, combat_state: Dict[str, Any]) -> None
async def clear_player_combat_state(player_id: int) -> None
```

**Player Settings**:
```python
async def get_player_settings(player_id: int) -> Optional[Dict[str, Any]]
async def set_player_settings(player_id: int, settings: Dict[str, Any]) -> bool
```

**Player Data Loading**:
```python
async def get_player_data(player_id: int) -> Optional[PlayerData]
async def get_player_data_by_username(username: str) -> Optional[PlayerData]
```

### Pydantic Model Access Patterns

**✅ Correct - Attribute Access**:
```python
# PlayerData is a Pydantic model
player_data = await PlayerService.get_player_by_username(username)
if player_data:
    player_id = player_data.id  # ✅ Correct
    username = player_data.username  # ✅ Correct
    
# NearbyPlayer is a Pydantic model
nearby = await PlayerService.get_nearby_players(player_id, radius=10)
for player in nearby:
    x = player.x  # ✅ Correct
    username = player.username  # ✅ Correct

# PlayerPosition is a Pydantic model  
position = await PlayerService.get_player_position(player_id)
if position:
    map_id = position.map_id  # ✅ Correct
    x = position.x  # ✅ Correct
```

**❌ Incorrect - Dictionary Access**:
```python
player_data = await PlayerService.get_player_by_username(username)
if player_data:
    player_id = player_data["id"]  # ❌ AttributeError!
    username = player_data["username"]  # ❌ AttributeError!

nearby = await PlayerService.get_nearby_players(player_id, radius=10)
for player in nearby:
    x = player["x"]  # ❌ TypeError: 'NearbyPlayer' object is not subscriptable
```

**Converting to Dictionary** (when needed):
```python
player_data = await PlayerService.get_player_by_username(username)
if player_data:
    # Convert Pydantic model to dict if needed
    player_dict = player_data.model_dump()  # ✅ Correct
    player_id = player_dict["id"]  # ✅ Now works
```

### Combat Mechanics

**Combat State Lifecycle**:
1. **Initiate Combat**: When player attacks or is attacked
   - Set combat state via `set_player_combat_state()`
   - Track target, last action time, etc.

2. **Movement Breaks Combat**: Moving clears combat state
   - Call `clear_player_combat_state()` on movement
   - Auto-retaliation will re-engage combat

3. **Auto-Retaliation**: NPC/player can re-initiate combat
   - Check if target moved away
   - Re-engage if within range

**Example - Movement Service**:
```python
async def execute_movement(player_id: int, direction: str) -> Dict:
    # ... validate and move ...
    
    # Break combat on movement
    player_mgr = get_player_state_manager()
    await player_mgr.clear_player_combat_state(player_id)
    
    return {"success": True, "new_position": new_pos}
```

### HP Calculation Patterns

**Max HP Computation**:
```python
# Max HP is calculated from hitpoints skill level
async def calculate_max_hp(player_id: int) -> int:
    # Query hitpoints skill level from database
    hitpoints_result = await db.execute(
        select(PlayerSkill.current_level)
        .join(Skill)
        .where(
            PlayerSkill.player_id == player_id,
            Skill.name == SkillType.HITPOINTS.value.name  # Note: .value.name
        )
    )
    max_hp = hitpoints_result.scalar_one_or_none() or HITPOINTS_START_LEVEL
    return max_hp
```

**Critical**: Use `SkillType.HITPOINTS.value.name` to get the string name, not just `.value` which returns a `SkillDefinition` object.

### Missing Await Patterns

**Common Missing Await Errors**:
```python
# ❌ Incorrect - Missing await
online_players = player_mgr.get_all_online_player_ids()  # Returns coroutine!
username = player_mgr.get_username_for_player(other_id)  # Returns coroutine!

# ✅ Correct - With await
online_players = await player_mgr.get_all_online_player_ids()
username = await player_mgr.get_username_for_player(other_id)

# ❌ Incorrect - Missing await in condition
if not player_mgr.is_online(self.player_id):  # Always truthy (coroutine object)!

# ✅ Correct - With await
if not await player_mgr.is_online(self.player_id):
```

**Rule**: All `PlayerStateManager` async methods MUST be awaited.

### Authentication Patterns

**Password Verification Requires Database Access**:
```python
# ❌ Incorrect - PlayerData doesn't include hashed_password
async def authenticate_with_password(username: str, password: str):
    player = await PlayerService.get_player_by_username(username)  # Returns PlayerData
    if not verify_password(password, player["hashed_password"]):  # Field doesn't exist!
        return None
    return player

# ✅ Correct - Query database directly for password verification
async def authenticate_with_password(username: str, password: str) -> Optional[PlayerData]:
    from sqlalchemy import select
    
    player_mgr = get_player_state_manager()
    
    # Use PlayerStateManager's session factory for test isolation
    async with player_mgr._db_session() as db:
        result = await db.execute(
            select(Player).where(Player.username == username)
        )
        player_record = result.scalar_one_or_none()
        
        if not player_record:
            return None
        
        # Verify password against database record
        if not verify_password(password, player_record.hashed_password):
            return None
        
        # Check ban/timeout status
        if player_record.is_banned:
            raise PermissionError("Player is banned")
    
    # Return PlayerData via service for consistency
    return await PlayerService.get_player_by_username(username)
```

**Why PlayerData Excludes hashed_password**:
- **Security**: Never expose password hashes outside authentication layer
- **Separation**: Authentication requires database, normal operations use GSM
- **Test Isolation**: Using `player_mgr._db_session()` ensures test database is used

**Key Principles**:
1. `PlayerData` is for normal game operations - excludes sensitive fields
2. Authentication is the ONLY operation requiring direct database access for passwords
3. Use `player_mgr._db_session()` for test isolation, NOT `AsyncSessionLocal()`
4. Always return Pydantic models (`PlayerData`) to calling code, not SQLAlchemy models

## Decision Log

### Architecture Decisions Made
- **Data Storage**: Single hash per reference data type in Valkey
- **Updates**: Reference data updates require server restart (new versions)
- **Startup**: Always reload reference data from database (no cache validation)
- **Service Signatures**: Remove all database session parameters
- **TTL Refresh**: Refresh on any data access (read or write)
- **Memory Management**: Player count limits (configurable)
- **Loading**: First-come-first-served for on-demand loading
- **Batch Sync**: 60 seconds OR 50 dirty players (both configurable)
- **Pydantic Models**: Always use attribute access, never dictionary access
- **Legacy Compatibility**: No backward compatibility layers - clean break approach
- **Combat Mechanics**: Movement breaks combat, auto-retaliation re-engages
- **HP Calculation**: Max HP computed from hitpoints skill level, not stored separately
- **Authentication**: Password verification is the only operation requiring direct database access
- **Test Isolation**: Services must use `player_mgr._db_session()` for database access to maintain test isolation

### Rationale
- Simplicity over complexity in data access patterns
- Fail-fast approach for better reliability  
- Clear separation of concerns between layers
- Performance optimization through permanent reference caching
- Memory efficiency through intelligent TTL management
- Security through separation of concerns (password hashes never in game state)

---

**These patterns are mandatory for all future development. Any deviation requires architectural review and approval.**