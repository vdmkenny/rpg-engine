"""
Test fixtures and configuration for the RPG server tests.
"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator, Callable, Awaitable, Dict, Any, Optional
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select
from sqlalchemy import delete

from server.src.main import app
from server.src.core.database import get_db, get_valkey
from server.src.models.base import Base
from server.src.models.player import Player
from server.src.models.item import GroundItem, PlayerInventory, PlayerEquipment
from server.src.models.skill import PlayerSkill
from server.src.core.security import get_password_hash, create_access_token
from server.src.services.game_state_manager import (
    GameStateManager,
    init_game_state_manager,
    reset_game_state_manager,
)

# Use SQLite in memory for tests to avoid async connection issues
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# Global test engine and session maker
test_engine = None
TestingSessionLocal = None


class FakeValkey:
    """
    In-memory Valkey/Redis implementation for testing.
    
    Mimics the behavior of a real Valkey client including:
    - Returning bytes for keys and values (like real Valkey)
    - Maintaining state across operations
    - Supporting hash operations (hset, hgetall, hget, hdel)
    - Supporting key operations (delete, exists, keys)
    - Supporting set operations (sadd, srem, smembers)
    - Supporting string operations (set, get, incr)
    """
    
    def __init__(self):
        self._data: Dict[str, Dict[str, str]] = {}
        self._string_data: Dict[str, str] = {}
        self._set_data: Dict[str, set] = {}
    
    async def hset(self, key: str, mapping: Dict[str, str]) -> int:
        """Set multiple hash fields."""
        if key not in self._data:
            self._data[key] = {}
        # Convert all values to strings
        for k, v in mapping.items():
            self._data[key][str(k)] = str(v)
        return len(mapping)
    
    async def hget(self, key: str, field: str) -> Optional[bytes]:
        """Get a single hash field value."""
        if key in self._data and field in self._data[key]:
            return self._data[key][field].encode()
        return None
    
    async def hgetall(self, key: str) -> Dict[bytes, bytes]:
        """Get all fields and values in a hash."""
        if key not in self._data:
            return {}
        # Return bytes like real Valkey does
        return {k.encode(): v.encode() for k, v in self._data[key].items()}
    
    async def hdel(self, key: str, fields: list) -> int:
        """Delete one or more hash fields."""
        if key not in self._data:
            return 0
        deleted = 0
        for field in fields:
            field_str = str(field)
            if field_str in self._data[key]:
                del self._data[key][field_str]
                deleted += 1
        return deleted
    
    async def delete(self, keys: list | str) -> int:
        """Delete one or more keys."""
        deleted = 0
        # Handle both single key (str) and list of keys
        if isinstance(keys, str):
            keys = [keys]
        for key in keys:
            if key in self._data:
                del self._data[key]
                deleted += 1
            if key in self._string_data:
                del self._string_data[key]
                deleted += 1
            if key in self._set_data:
                del self._set_data[key]
                deleted += 1
        return deleted
    
    async def exists(self, keys: list | str) -> int:
        """Check if keys exist. Returns count of existing keys."""
        if isinstance(keys, str):
            keys = [keys]
        count = 0
        for key in keys:
            if key in self._data or key in self._string_data or key in self._set_data:
                count += 1
        return count
    
    async def set(self, key: str, value: str) -> str:
        """Set a string value."""
        self._string_data[key] = str(value)
        return "OK"
    
    async def get(self, key: str) -> Optional[bytes]:
        """Get a string value."""
        if key in self._string_data:
            return self._string_data[key].encode()
        return None
    
    async def incr(self, key: str) -> int:
        """Increment the integer value of a key by one."""
        if key in self._string_data:
            value = int(self._string_data[key])
        else:
            value = 0
        value += 1
        self._string_data[key] = str(value)
        return value
    
    async def keys(self, pattern: str = "*") -> list:
        """Get keys matching a pattern."""
        import fnmatch
        all_keys = list(self._data.keys()) + list(self._string_data.keys()) + list(self._set_data.keys())
        if pattern == "*":
            return [k.encode() for k in all_keys]
        return [k.encode() for k in all_keys if fnmatch.fnmatch(k, pattern)]
    
    # Set operations
    async def sadd(self, key: str, members: list) -> int:
        """Add one or more members to a set."""
        if key not in self._set_data:
            self._set_data[key] = set()
        added = 0
        for member in members:
            member_str = str(member)
            if member_str not in self._set_data[key]:
                self._set_data[key].add(member_str)
                added += 1
        return added
    
    async def srem(self, key: str, members: list) -> int:
        """Remove one or more members from a set."""
        if key not in self._set_data:
            return 0
        removed = 0
        for member in members:
            member_str = str(member)
            if member_str in self._set_data[key]:
                self._set_data[key].remove(member_str)
                removed += 1
        return removed
    
    async def smembers(self, key: str) -> set:
        """Get all members of a set."""
        if key not in self._set_data:
            return set()
        # Return bytes like real Valkey does
        return {m.encode() for m in self._set_data[key]}
    
    async def sismember(self, key: str, member: str) -> int:
        """Check if a member exists in a set."""
        if key not in self._set_data:
            return 0
        return 1 if str(member) in self._set_data[key] else 0
    
    def clear(self):
        """Clear all data (useful between tests)."""
        self._data.clear()
        self._string_data.clear()
        self._set_data.clear()
    
    def get_hash_data(self, key: str) -> Dict[str, str]:
        """Direct access to hash data for test assertions."""
        return self._data.get(key, {})
    
    def get_set_data(self, key: str) -> set:
        """Direct access to set data for test assertions."""
        return self._set_data.get(key, set())


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_db():
    """Set up test database once per session."""
    global test_engine, TestingSessionLocal

    test_engine = create_async_engine(
        TEST_DATABASE_URL, echo=False, connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Create all tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    # Clean up
    await test_engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def session() -> AsyncGenerator[AsyncSession, None]:
    """
    Creates a fresh database session for each test.
    Cleans up test data after the test completes.
    """
    if TestingSessionLocal is None:
        raise RuntimeError("TestingSessionLocal not initialized")

    async with TestingSessionLocal() as session_obj:
        try:
            yield session_obj
        except Exception:
            await session_obj.rollback()
            raise
        finally:
            # Clean up data created during the test
            # Order matters due to foreign key constraints
            await session_obj.rollback()  # Rollback any uncommitted changes first
            await session_obj.execute(delete(GroundItem))
            await session_obj.execute(delete(PlayerInventory))
            await session_obj.execute(delete(PlayerEquipment))
            await session_obj.execute(delete(PlayerSkill))
            await session_obj.execute(delete(Player))
            # Don't delete Item table - it's static data synced on startup
            await session_obj.commit()
            await session_obj.close()


@pytest_asyncio.fixture(scope="function")
async def fake_valkey() -> FakeValkey:
    """
    Create a fresh FakeValkey instance for each test.
    """
    valkey = FakeValkey()
    yield valkey
    valkey.clear()


@pytest_asyncio.fixture(scope="function")
async def gsm(fake_valkey: FakeValkey) -> AsyncGenerator[GameStateManager, None]:
    """
    Create a GameStateManager for tests that need GSM functionality.
    
    Initializes the global GSM with a FakeValkey and test session factory.
    Tests using this fixture can call get_game_state_manager() and it will
    return this initialized GSM instance.
    """
    if TestingSessionLocal is None:
        raise RuntimeError("TestingSessionLocal not initialized")
    
    # Initialize the global GSM
    gsm_instance = init_game_state_manager(fake_valkey, TestingSessionLocal)

    # Load item cache from database for metadata lookups
    try:
        await gsm_instance.load_item_cache_from_db()
    except Exception:
        # Tests may not have items synced; caller tests should call ItemService.sync_items_to_db(session)
        pass
    
    yield gsm_instance
    
    # Clean up - reset the global GSM
    reset_game_state_manager()


@pytest_asyncio.fixture
async def client(
    session: AsyncSession, fake_valkey: FakeValkey
) -> AsyncGenerator[AsyncClient, None]:
    """
    Create an HTTP client that uses the test database session and fake Valkey.
    """
    # Override database dependency
    async def override_get_db():
        yield session
    
    # Override Valkey dependency
    async def override_get_valkey():
        return fake_valkey
    
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_valkey] = override_get_valkey

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

    # Clean up
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
def create_test_player(
    session: AsyncSession,
) -> Callable[..., Awaitable[Player]]:
    """
    Fixture factory to create a test player with proper initialization.
    Uses PlayerService for consistent player creation with skills.
    """
    async def _create_player(
        username: str, 
        password: str, 
        x: int = 10, 
        y: int = 10, 
        map_id: str = "samplemap",
        **extra_fields
    ) -> Player:
        from server.src.services.player_service import PlayerService
        from server.src.schemas.player import PlayerCreate
        
        # Create player data using Pydantic model
        player_data = PlayerCreate(
            username=username,
            password=password
        )
        
        # Use PlayerService for proper player creation with skills initialization
        player = await PlayerService.create_player(session, player_data)
        
        # Update position and map if different from defaults
        if x != 10 or y != 10 or map_id != "samplemap" or extra_fields:
            player.x_coord = x
            player.y_coord = y
            player.map_id = map_id
            
            # Apply any extra fields
            for key, value in extra_fields.items():
                if hasattr(player, key):
                    setattr(player, key, value)
            
            session.add(player)
            await session.commit()
            await session.refresh(player)
        
        return player

    return _create_player


@pytest_asyncio.fixture
def create_test_player_and_token(
    session: AsyncSession,
) -> Callable[..., Awaitable[tuple[str, Player]]]:
    """
    Fixture factory to create a test player and a valid JWT for them.
    This avoids hitting the login endpoint for every test.
    """

    async def _create_player_and_token(
        username: str, 
        password: str, 
        initial_data: Dict[str, Any] | None = None
    ) -> tuple[str, Player]:
        hashed_password = get_password_hash(password)

        player_data = {"username": username, "hashed_password": hashed_password}
        if initial_data:
            player_data.update(initial_data)

        player = Player(**player_data)
        session.add(player)
        await session.commit()
        await session.refresh(player)

        token = create_access_token(data={"sub": username})
        return token, player

    return _create_player_and_token


@pytest_asyncio.fixture
def create_expired_token() -> Callable[[str], str]:
    """
    Fixture factory to create an expired JWT token for testing.
    """
    from datetime import timedelta
    
    def _create_expired_token(username: str) -> str:
        # Create a token that expired 1 hour ago
        return create_access_token(
            data={"sub": username}, 
            expires_delta=timedelta(hours=-1)
        )
    
    return _create_expired_token


@pytest_asyncio.fixture
def set_player_banned(
    session: AsyncSession,
) -> Callable[[str], Awaitable[None]]:
    """
    Fixture factory to ban a player by username.
    """
    async def _set_player_banned(username: str) -> None:
        result = await session.execute(
            select(Player).where(Player.username == username)
        )
        player = result.scalar_one()
        player.is_banned = True
        await session.commit()

    return _set_player_banned


@pytest_asyncio.fixture
def set_player_timeout(
    session: AsyncSession,
) -> Callable[[str, timedelta], Awaitable[None]]:
    """
    Fixture factory to set a timeout on a player.
    
    Args:
        username: Player to timeout
        duration: How long the timeout should last from now
    """
    async def _set_player_timeout(username: str, duration: timedelta) -> None:
        result = await session.execute(
            select(Player).where(Player.username == username)
        )
        player = result.scalar_one()
        player.timeout_until = datetime.now(timezone.utc) + duration
        await session.commit()

    return _set_player_timeout
