# Test Suite

Comprehensive test suite for the RPG game server.

## Structure

```
tests/
├── conftest.py                 # Root fixtures shared across all tests
├── websocket_test_utils.py   # WebSocket testing utilities
├── README.md                  # This file
│
├── unit/                      # Fast unit tests (<100ms each)
│   ├── models/               # ORM model tests
│   ├── schemas/              # Pydantic schema tests  
│   ├── core/                 # Core utilities (skills, items, security)
│   └── services/             # Service calculation tests
│
├── integration/              # Integration tests with DB/Valkey (<500ms)
│   ├── managers/             # Manager CRUD + auto-loading tests (NEW)
│   ├── services/             # Business logic tests
│   ├── api/                  # HTTP endpoint tests
│   ├── game/                 # Game mechanic tests
│   └── cross_domain/         # Service interaction tests (NEW)
│
├── e2e/                      # End-to-end WebSocket tests (<2s)
│   └── test_websocket_*.py   # Full gameplay flows
│
└── stress/                   # Load/concurrency tests (>1s)
    ├── test_concurrency.py
    ├── test_race_conditions.py
    └── test_atomic_operations.py
```

## Running Tests

```bash
# All tests
pytest

# Unit tests only (fast)
pytest server/src/tests/unit -v

# Integration tests
pytest server/src/tests/integration -v

# WebSocket E2E tests (requires running server)
pytest server/src/tests/e2e -v -m "websocket"

# Stress tests
pytest server/src/tests/stress -v

# Exclude slow tests
pytest -v -m "not stress"

# Parallel execution
pytest -n auto
```

## Test Architecture

### Unit Tests
- **Purpose:** Test logic in isolation
- **Speed:** <100ms per test
- **Database:** No
- **Coverage:** Core calculations, formulas, enums

### Integration Tests  
- **Purpose:** Test services with real DB/Valkey
- **Speed:** <500ms per test
- **Database:** Yes (PostgreSQL)
- **Coverage:** Business logic, data persistence

### E2E Tests
- **Purpose:** Test full gameplay flows
- **Speed:** <2s per test
- **Database:** Yes
- **Coverage:** WebSocket flows, multiplayer

### Stress Tests
- **Purpose:** Test concurrency and load
- **Speed:** >1s per test  
- **Database:** Yes
- **Coverage:** Race conditions, atomicity

## Fixtures

### Root Fixtures (conftest.py)
- `session` - Database session
- `fake_valkey` - In-memory Valkey
- `game_state_managers` - All initialized managers
- `create_test_player` - Factory for test players

### Category-Specific Fixtures
See `conftest.py` in each subdirectory for specialized fixtures.

## Writing Tests

### Unit Test Example
```python
def test_xp_calculation():
    """Pure unit test - no database."""
    result = xp_for_level(50)
    assert result == expected_value
```

### Integration Test Example
```python
@pytest.mark.asyncio
async def test_add_item_to_inventory(create_test_player):
    """Integration test - uses real managers."""
    player = await create_test_player("test", "pass")
    result = await InventoryService.add_item(player["id"], item_id=1, quantity=5)
    assert result.success is True
```

## Migration from Old Structure

The test suite was restructured from a flat directory to the current nested structure:

- Old `test_*.py` files → organized by type and domain
- GSM mocking removed → Real manager integration
- 48 files → 63 files (more focused, better coverage)

## Coverage Goals

- **Unit tests:** Core calculations, edge cases
- **Integration:** Business logic, data consistency  
- **E2E:** Critical user flows
- **Stress:** Concurrency, race conditions

## CI/CD Integration

```yaml
# Run on PR - fast unit tests only
pytest server/src/tests/unit -v

# Run on merge - full suite
pytest -v

# Run nightly - stress tests
pytest server/src/tests/stress -v --timeout=300
```
