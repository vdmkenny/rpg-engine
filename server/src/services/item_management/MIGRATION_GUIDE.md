# Item Management Service Migration Guide

This document outlines the strategy for migrating from the current fragmented inventory services to the unified ItemManager service.

## Migration Strategy Overview

The migration follows a **phased approach** to maintain backwards compatibility and minimize risk:

### Phase 1: Interface Introduction (Completed)
- ✅ Create `ItemManager` interface with unified operations
- ✅ Implement delegation to existing services for compatibility
- ✅ Add atomic transaction infrastructure (foundation for future phases)
- ✅ Maintain 100% backward compatibility

### Phase 2: API Layer Migration (Next Step)
- Update WebSocket handlers to use `ItemManager` instead of individual services
- Replace direct service calls with unified interface calls
- Maintain existing functionality while using new interface

### Phase 3: Service Consolidation
- Inline inventory operations into `ItemManager`
- Inline equipment operations into `ItemManager` 
- Inline ground item operations into `ItemManager`
- Remove delegated service calls

### Phase 4: Atomic Transaction Implementation
- Replace multi-step operations with atomic transactions
- Implement proper rollback mechanisms
- Add transaction logging and monitoring

## Current Service Interaction Patterns

### Equipment Operations
```python
# Current: Multiple service calls
inventory_item = await InventoryService.get_item_at_slot(db, player_id, slot)
equip_result = await EquipmentService.equip_from_inventory(db, player_id, slot)
if health_bonus:
    await HpService.adjust_hp_for_equip(player_id, health_bonus)

# New: Single atomic operation
equip_result = await item_manager.equip_item(db, player_id, slot)
```

### Death Handling
```python
# Current: Multiple service interactions  
await InventoryService.clear_inventory(db, player_id)
await EquipmentService.clear_equipment(db, player_id)
await GroundItemService.drop_player_items_on_death(player_id, map_id, x, y)

# New: Single atomic transaction
items_dropped = await item_manager.handle_player_death(player_id, map_id, x, y)
```

## Migration Steps

### Step 1: Update Import Statements

Replace individual service imports:
```python
# Old imports
from server.src.services.inventory_service import InventoryService
from server.src.services.equipment_service import EquipmentService  
from server.src.services.ground_item_service import GroundItemService

# New import
from server.src.services.item_management import get_item_manager
```

### Step 2: Update WebSocket Handlers

Replace service calls in `server/src/api/websockets.py`:

```python
# Old pattern
async def handle_equip_item(username, payload, valkey, websocket, db):
    result = await EquipmentService.equip_from_inventory(db, player_id, slot)
    
# New pattern  
async def handle_equip_item(username, payload, valkey, websocket, db):
    item_manager = get_item_manager()
    result = await item_manager.equip_item(db, player_id, slot)
```

### Step 3: Update Test Files

Update test imports and service calls:
```python
# Old test pattern
from server.src.services.inventory_service import InventoryService
result = await InventoryService.add_item(db, player_id, item_id)

# New test pattern
from server.src.services.item_management import get_item_manager
item_manager = get_item_manager()
result = await item_manager.add_item_to_inventory(db, player_id, item_id)
```

### Step 4: Validate Functionality

After each migration step:
1. Run all existing tests to ensure no regressions
2. Run integration tests for WebSocket operations
3. Test complex scenarios (death drops, equipment swapping)

## Benefits After Migration

### Immediate Benefits (Phase 1-2)
- **Unified Interface**: Single point of entry for all item operations
- **Better Testing**: Mock single service instead of multiple services
- **Cleaner Dependencies**: Reduced coupling between services

### Future Benefits (Phase 3-4)  
- **Atomic Transactions**: No partial state updates or item duplication
- **Better Error Handling**: Consistent error responses across all operations
- **Improved Performance**: Reduced GSM round-trips for multi-step operations
- **Enhanced Debugging**: Transaction logging for complex operations

## Risk Mitigation

### Backward Compatibility
- Phase 1 maintains 100% compatibility via delegation
- Existing tests pass without modification
- No changes to external APIs or database schema

### Gradual Rollout
- Each phase can be deployed and tested independently
- Rollback capability at each phase boundary
- Feature flags can control which code paths are used

### Testing Strategy
- Comprehensive unit tests for new ItemManager interface
- Integration tests for WebSocket handlers using new service
- Performance tests to ensure no regression in response times
- Load tests for atomic transaction overhead

## Implementation Priority

1. **High Priority**: API layer migration (Phase 2)
   - Immediate benefits with minimal risk
   - Enables better testing of complex operations

2. **Medium Priority**: Service consolidation (Phase 3)  
   - Reduces code duplication and maintenance burden
   - Improves code organization and readability

3. **Low Priority**: Atomic transactions (Phase 4)
   - Advanced feature for edge case handling
   - Requires careful design and testing

## Success Metrics

- **No Regressions**: All existing tests pass after each phase
- **Code Reduction**: 30%+ reduction in item-related service code
- **Bug Reduction**: Fewer item duplication/loss incidents
- **Developer Velocity**: Faster implementation of new item features

This phased approach ensures a safe migration while providing immediate benefits and setting the foundation for advanced features.
