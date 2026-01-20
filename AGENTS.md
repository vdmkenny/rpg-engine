# AGENTS.md - Coding Agent Guidelines

This document provides guidelines for AI coding agents working in the rpg-engine codebase.

## Project Overview

A 2D multiplayer RPG game with:
- **Server**: FastAPI + SQLAlchemy + PostgreSQL + Valkey (Redis) - async Python
- **Client**: Pygame thin client - async Python
- **Common**: Shared Pydantic protocol definitions

Python version: **3.14**

## Project Structure

```
rpg-engine/
├── server/src/           # FastAPI server
│   ├── api/              # REST endpoints, WebSocket handlers
│   ├── core/             # Config, database, logging, security
│   ├── models/           # SQLAlchemy ORM models
│   ├── schemas/          # Pydantic request/response schemas
│   ├── services/         # Business logic (map service)
│   ├── game/             # Game loop logic
│   └── tests/            # Pytest test files
├── client/src/           # Pygame client
├── common/src/           # Shared protocol definitions
└── docker/               # Docker Compose files
```

## Build/Lint/Test Commands

### Install Dependencies

```bash
# Full development setup (server + client + dev tools)
poetry install --with server,client,dev

# Server only
poetry install --with server

# Client only
poetry install --with client
```

### Running Tests

```bash
# Run all tests
pytest

# Run all tests with verbose output
pytest -v

# Run tests in parallel
pytest -n auto

# Run a single test file
pytest server/src/tests/test_example.py -v

# Run a specific test function
pytest server/src/tests/test_example.py::test_function_name -v

# Run tests matching a pattern
pytest -k "test_login" -v
```

Test configuration is in `pytest.ini`. Tests are located in `server/src/tests/`.

### Docker Commands

```bash
# Build and run all services
cd docker && docker-compose up --build

# Run specific test suites
cd docker && docker-compose --profile test run test-collision
```

### Running Tests in Docker (Recommended)

The preferred way to run tests is using Docker, which provides a consistent environment with PostgreSQL and Valkey:

```bash
# 1. Start the test containers (builds if needed)
cd docker && docker-compose -f docker-compose.test.yml up -d --build

# 2. Run unit tests only
docker exec docker-server-1 pytest -v

# 3. Run tests in parallel
docker exec docker-server-1 pytest -v -n auto

# 4. Run a specific test file
docker exec docker-server-1 pytest server/src/tests/test_hitpoints.py -v

# 5. Run tests matching a pattern
docker exec docker-server-1 pytest -k "test_login" -v

# 6. Stop test containers when done
cd docker && docker-compose -f docker-compose.test.yml down
```

The Docker test environment provides:
- **PostgreSQL** database on port 5433 (mapped from container's 5432)
- **Valkey** (Redis-compatible) on port 6380 (mapped from container's 6379)
- All Python dependencies pre-installed
- Volume mount of the source code for live changes

### Running Integration Tests

Integration tests (WebSocket tests) require the server to be running and database migrations to be applied. These tests are skipped by default unless `RUN_INTEGRATION_TESTS=1` is set.

```bash
# 1. Start the test containers (if not already running)
cd docker && docker-compose -f docker-compose.test.yml up -d --build

# 2. Run database migrations (required before first run or after schema changes)
docker exec docker-server-1 bash -c "cd server && alembic upgrade head"

# 3. Start the server in the background inside the container
docker exec -d docker-server-1 uvicorn server.src.main:app --host 0.0.0.0 --port 8000

# 4. Wait a moment for server to start, then run all tests including integration tests
docker exec docker-server-1 bash -c "sleep 2 && RUN_INTEGRATION_TESTS=1 pytest -v"

# 5. Or run only integration tests (WebSocket tests)
docker exec docker-server-1 bash -c "RUN_INTEGRATION_TESTS=1 pytest -v -k 'websocket'"

# 6. Stop test containers when done
cd docker && docker-compose -f docker-compose.test.yml down
```

**Note**: Integration tests connect to the running server via WebSocket and test real authentication, movement, chat, inventory, and equipment operations.

**IMPORTANT FOR AI AGENTS**: When running tests, ALWAYS run integration tests as well. Use the full integration test workflow above to ensure both unit tests and WebSocket integration tests pass. Never skip integration tests when verifying changes.

### Running the Application

```bash
# Server (with Docker)
cd docker && docker-compose up

# Client (local development)
./run_client.sh
```

## Code Style Guidelines

### Naming Conventions

| Element | Convention | Example |
|---------|------------|---------|
| Files | snake_case | `map_service.py`, `game_states.py` |
| Functions | snake_case | `get_password_hash()`, `handle_move_intent()` |
| Classes | PascalCase | `Player`, `MapManager`, `GameMessage` |
| Variables | snake_case | `player_key`, `current_pos` |
| Constants | SCREAMING_SNAKE_CASE | `TILE_SIZE`, `FPS`, `BLACK` |
| Enums | PascalCase class, SCREAMING_SNAKE_CASE values | `MessageType.AUTHENTICATE` |
| Pydantic Models | PascalCase with suffix | `PlayerCreate`, `PlayerPublic`, `TokenData` |
| SQLAlchemy Models | PascalCase singular | `Player`, `Skill` (table: `players`) |

### Import Organization

Organize imports in this order, with blank lines between groups:

```python
# 1. Standard library
from datetime import timedelta
from typing import Dict, List, Optional, Any

# 2. Third-party packages
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

# 3. Local imports (absolute paths from project root)
from server.src.core.config import settings
from server.src.core.database import get_db
from server.src.models.player import Player
```

- Use **absolute imports** from project root: `from server.src.core.config import settings`
- Use **relative imports** within a package: `from .base import Base`
- Group multi-line imports with parentheses

### Comments and Documentation

**Business-Focused Comments Only**:
- Document **WHAT** the code does for business purposes, not **HOW** it's implemented
- Avoid technical implementation details in comments
- Never comment on code changes, refactoring decisions, or fallback strategies

**Examples of BAD comments**:
```python
# Always use GSM - no database fallbacks
# Fixed to avoid direct DB access
# Changed from old approach to new approach
# TODO: Refactor this later
```

**Examples of GOOD comments**:
```python
# Calculate player's maximum health including equipment bonuses
# Validate player meets skill requirements for equipment
# Handle ammunition stacking for ranged weapons
```

**Service Layer Comments**:
- Focus on business logic and user-facing functionality
- Avoid mentioning technical details like "GSM", "Valkey", "database operations"
- Describe the business purpose, not the implementation mechanism

### Data Access Patterns

**Single Source of Truth**: 
- Services should NEVER access database directly
- Always use GameStateManager (GSM) for all game state operations
- Tests should use services/GSM, not direct database manipulation
- No "fallback to database" patterns - use GSM exclusively

**GSM Singleton Pattern**:
- GSM should be accessed as a singleton using `get_game_state_manager()`
- Do NOT pass GSM as parameters between functions/services
- Services should import and call the singleton directly when needed
- This reduces coupling and makes the architecture cleaner

```python
# Good - Use singleton
from .game_state_manager import get_game_state_manager

def some_service_method():
    gsm = get_game_state_manager()
    return gsm.get_player_data(player_id)

# Bad - Parameter passing
def some_service_method(state_manager: GameStateManager):
    return state_manager.get_player_data(player_id)
```

### Type Hints

Always use type hints for function parameters and return values:

```python
from typing import Dict, List, Optional, Tuple, Any

def get_chunks_for_player(
    self, map_id: str, player_x: int, player_y: int, radius: int = 1
) -> Optional[List[Dict]]:
    ...
```

### Docstrings

Use Google-style docstrings:

```python
def get_chunks_for_player(
    self, map_id: str, player_x: int, player_y: int, radius: int = 1
) -> Optional[List[Dict]]:
    """
    Get chunk data around a player's position.

    Args:
        map_id: The map identifier
        player_x: Player's tile X position
        player_y: Player's tile Y position
        radius: Number of chunks in each direction from player

    Returns:
        List of chunk data or None if map doesn't exist
    """
```

### Error Handling

**API errors** - Use HTTPException with appropriate status codes:
```python
raise HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail="A player with this username already exists.",
)
```

**Structured logging** - Always include context in `extra` dict:
```python
logger.error(
    "Error processing move intent",
    extra={
        "username": username,
        "error": str(e),
        "error_type": type(e).__name__,
    },
)
```

**Database errors** - Rollback on IntegrityError:
```python
except IntegrityError:
    await db.rollback()
    logger.warning("Registration failed", extra={"username": username})
    raise HTTPException(status_code=400, detail="Username exists")
```

### Async Patterns

This codebase is heavily async. Use:
- `async def` for all I/O-bound operations
- `await` for async calls
- `asynccontextmanager` for resource lifecycle
- `pytest-asyncio` for async tests with `@pytest_asyncio.fixture`

### Pydantic Models

- Use `BaseModel` for data transfer objects
- Use `BaseSettings` with `SettingsConfigDict` for configuration
- Suffix conventions: `Create`, `Update`, `InDB`, `Public`

```python
class PlayerBase(BaseModel):
    username: str

class PlayerCreate(PlayerBase):
    password: str

class PlayerPublic(PlayerBase):
    id: int
```

### SQLAlchemy Models

- Inherit from `Base` (declarative base)
- Use singular PascalCase for class, plural lowercase for table name
- Define relationships explicitly

```python
class Player(Base):
    __tablename__ = "players"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
```

### WebSocket Protocol

- All messages use msgpack binary encoding
- Message structure: `{"type": MessageType, "payload": {...}}`
- Message types defined in `common/src/protocol.py`

## Testing Patterns

- Use `pytest` with `pytest-asyncio` for async tests
- Use `httpx.AsyncClient` for API testing
- Use `starlette.testclient.TestClient` for WebSocket testing
- Override dependencies with `app.dependency_overrides`
- Use SQLite in-memory database for tests
- Use `FakeValkey` class for in-memory Valkey testing

```python
@pytest_asyncio.fixture
async def async_client():
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
```

### FakeValkey for Testing

Use the `FakeValkey` class in `conftest.py` for testing Valkey operations:

```python
@pytest_asyncio.fixture
async def fake_valkey() -> FakeValkey:
    valkey = FakeValkey()
    yield valkey
    valkey.clear()
```

## Game Loop Architecture

The game loop (`server/src/game/game_loop.py`) implements diff-based visibility broadcasting:

- **Tick-based updates**: Runs at configurable tick rate (default 20 TPS)
- **Per-player visibility**: Each player only receives updates about entities in their chunk range
- **Diff broadcasting**: Only sends changes (added/updated/removed entities), not full state
- **Movement confirmation**: Moving player gets instant feedback, others see updates on next tick

Key functions:
- `is_in_visible_range()` - Check if entity is visible to player
- `get_visible_entities()` - Get all entities visible to a player
- `compute_entity_diff()` - Calculate changes since last tick
- `cleanup_disconnected_player()` - Clean up state when player disconnects

## Key Files

- `server/src/main.py` - FastAPI app entry point, game loop integration
- `server/src/core/config.py` - Settings via pydantic-settings (with JWT validation)
- `server/src/game/game_loop.py` - Tick-based game loop with visibility system
- `common/src/protocol.py` - Shared message types and payloads
- `server/config.yml` - Game configuration (tick rate, movement, maps)
- `GSM_ARCHITECTURE_PATTERNS.md` - **MANDATORY** GameStateManager architecture patterns and guidelines

## GameStateManager (GSM) Architecture

**CRITICAL**: All AI agents and developers MUST follow the patterns defined in `GSM_ARCHITECTURE_PATTERNS.md`. This document contains mandatory architecture guidelines for:

- Data layer separation (GSM vs Services)
- Hot/cold data lifecycle management  
- Service implementation patterns
- Error handling and testing approaches
- Cross-service communication patterns

**Key Principles**:
- GSM handles ONLY data persistence (Valkey + PostgreSQL)
- Services contain ALL business logic and validation
- NO direct database/Valkey access outside GSM
- NO database fallback patterns - fail fast approach
- Reference data (items, skills) permanently cached at startup
- Player data follows hot/cold TTL-based lifecycle

**Violation of these patterns requires architectural review and approval.**

## Security Notes

- JWT_SECRET_KEY must be changed from default in non-development environments
- Movement is rate-limited server-side to prevent speed hacking
- Chunk requests are limited to radius <= 5
- All message types should use the `MessageType` enum from `protocol.py`
