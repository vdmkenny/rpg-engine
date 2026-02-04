"""
Test fixtures and configuration for the RPG server tests.
"""

import asyncio
import pytest
import pytest_asyncio
import msgpack
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator, Callable, Awaitable, Dict, Any, Optional, List, Generator
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select
from sqlalchemy import delete, create_engine, text
from sqlalchemy.pool import NullPool
from alembic import command
from alembic.config import Config

from server.src.main import app
from server.src.core.database import get_db, get_valkey
from server.src.models import Base
from server.src.models.player import Player
from server.src.models.item import Item, GroundItem, PlayerInventory, PlayerEquipment
from server.src.models.skill import Skill, PlayerSkill
from server.src.models.skill import PlayerSkill
from server.src.core.security import get_password_hash, create_access_token
from server.src.services.game_state import (
    get_player_state_manager,
    get_reference_data_manager,
    init_all_managers,
    reset_all_managers,
)

# Configure logger for test fixtures
logger = logging.getLogger(__name__)


class FakeValkeyTransaction:
    """
    Transaction wrapper for FakeValkey that queues operations for atomic execution.
    
    Mimics the behavior of real Valkey transactions by:
    - Queuing operations during the transaction
    - Executing all operations atomically when exec() is called
    - Supporting the main operations used by GSM atomic operations
    """
    
    def __init__(self, valkey_instance):
        self.valkey = valkey_instance
        self.queued_operations = []
    
    async def hset(self, key: str, mapping: Dict[str, str]) -> None:
        """Queue a hash set operation."""
        self.queued_operations.append(('hset', key, mapping))
    
    async def set(self, key: str, value: str) -> None:
        """Queue a string set operation."""
        self.queued_operations.append(('set', key, value))
    
    async def sadd(self, key: str, members: list) -> None:
        """Queue a set add operation."""
        self.queued_operations.append(('sadd', key, members))
    
    async def hdel(self, key: str, fields: list) -> None:
        """Queue a hash delete operation."""
        self.queued_operations.append(('hdel', key, fields))
    
    async def delete(self, keys: list | str) -> None:
        """Queue a key delete operation."""
        self.queued_operations.append(('delete', keys))
    
    async def incr(self, key: str) -> None:
        """Queue an increment operation."""
        self.queued_operations.append(('incr', key))
    
    async def srem(self, key: str, member: str) -> None:
        """Queue a set remove operation."""
        self.queued_operations.append(('srem', key, member))
    
    async def exec(self) -> list:
        """Execute all queued operations atomically and return results."""
        results = []
        for operation, *args in self.queued_operations:
            if operation == 'hset':
                result = await self.valkey.hset(args[0], args[1])
            elif operation == 'set':
                result = await self.valkey.set(args[0], args[1])
            elif operation == 'sadd':
                result = await self.valkey.sadd(args[0], args[1])
            elif operation == 'hdel':
                result = await self.valkey.hdel(args[0], args[1])
            elif operation == 'delete':
                result = await self.valkey.delete(args[0])
            elif operation == 'incr':
                result = await self.valkey.incr(args[0])
            elif operation == 'srem':
                result = await self.valkey.srem(args[0], [args[1]])
            results.append(result)
        return results


# Worker Detection and Database URL Generation
def get_worker_id() -> str:
    """
    Get pytest-xdist worker ID or 'main' for single-threaded execution.
    
    Returns:
        Worker ID like 'gw0', 'gw1', etc. or 'main' for non-parallel execution
    """
    return os.getenv("PYTEST_XDIST_WORKER", "main")


def get_worker_database_url(worker_id: str) -> str:
    """
    Generate worker-specific database URL for isolation.
    
    Args:
        worker_id: The worker identifier from get_worker_id()
        
    Returns:
        PostgreSQL URL for worker-specific database
    """
    # Detect if running inside Docker container
    if os.path.exists('/.dockerenv'):
        # Inside Docker: use service name and internal port
        base_url = "postgresql+asyncpg://rpg_test:rpg_test_password@test_db:5432"
    else:
        # Outside Docker: use localhost and mapped port
        base_url = "postgresql+asyncpg://rpg_test:rpg_test_password@localhost:5433"
        
    worker_db_name = f"rpg_test_worker_{worker_id}"
    return f"{base_url}/{worker_db_name}"


def get_sync_worker_database_url(worker_id: str) -> str:
    """
    Generate sync (non-asyncpg) worker database URL for Alembic operations.
    
    Note: Even though this says 'sync', it still uses asyncpg because our
    Alembic env.py is configured for async operations with AsyncEngine.
    
    Args:
        worker_id: The worker identifier from get_worker_id()
        
    Returns:
        AsyncPG PostgreSQL URL for worker-specific database (for Alembic)
    """
    # Detect if running inside Docker container
    if os.path.exists('/.dockerenv'):
        # Inside Docker: use service name and internal port
        base_url = "postgresql+asyncpg://rpg_test:rpg_test_password@test_db:5432"
    else:
        # Outside Docker: use localhost and mapped port  
        base_url = "postgresql+asyncpg://rpg_test:rpg_test_password@localhost:5433"
        
    worker_db_name = f"rpg_test_worker_{worker_id}"
    return f"{base_url}/{worker_db_name}"


def get_admin_database_url() -> str:
    """
    Generate admin database URL for creating/dropping worker databases.
    
    Returns:
        PostgreSQL URL for connecting to postgres admin database
    """
    # Detect if running inside Docker container
    if os.path.exists('/.dockerenv'):
        # Inside Docker: use service name and internal port
        return "postgresql://rpg_test:rpg_test_password@test_db:5432/postgres"
    else:
        # Outside Docker: use localhost and mapped port
        return "postgresql://rpg_test:rpg_test_password@localhost:5433/postgres"


# Use PostgreSQL for tests (production parity)
# Worker-specific database URL based on pytest-xdist worker ID
WORKER_ID = get_worker_id()
TEST_DATABASE_URL = get_worker_database_url(WORKER_ID)

# Global test engine and session maker
test_engine = None
TestingSessionLocal = None


class FakeValkeyPipeline:
    """
    Pipeline for batching Valkey operations.
    """
    
    def __init__(self, valkey_instance):
        self._valkey = valkey_instance
        self._commands = []
    
    def hset(self, key: str, field: str, value: str):
        """Queue hset command for batch execution."""
        self._commands.append(('hset', key, field, value))
        return self
    
    def hgetall(self, key: str):
        """Queue hgetall command for batch execution."""
        self._commands.append(('hgetall', key))
        return self
    
    def sadd(self, key: str, member: str):
        """Queue sadd command for batch execution.""" 
        self._commands.append(('sadd', key, member))
        return self
        
    async def execute(self):
        """Execute all queued commands."""
        results = []
        for cmd in self._commands:
            if cmd[0] == 'hset':
                _, key, field, value = cmd
                if key not in self._valkey._data:
                    self._valkey._data[key] = {}
                self._valkey._data[key][field] = str(value)
                results.append(1)
            elif cmd[0] == 'hgetall':
                _, key = cmd
                if key not in self._valkey._data:
                    results.append({})
                else:
                    # Return bytes like real Valkey does
                    results.append({k.encode(): v.encode() for k, v in self._valkey._data[key].items()})
            elif cmd[0] == 'sadd':
                _, key, member = cmd
                if key not in self._valkey._set_data:
                    self._valkey._set_data[key] = set()
                if str(member) not in self._valkey._set_data[key]:
                    self._valkey._set_data[key].add(str(member))
                    results.append(1)
                else:
                    results.append(0)
        self._commands.clear()
        return results


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
    
    async def scan(self, cursor: int, pattern: str, count: int = 10) -> tuple[int, list]:
        """
        Iterate over keys matching a pattern (simplified for testing).
        
        Returns:
            Tuple of (next_cursor, list_of_keys)
            next_cursor is 0 when iteration is complete
        """
        import fnmatch
        all_keys = list(self._data.keys()) + list(self._string_data.keys()) + list(self._set_data.keys())
        
        # Filter by pattern
        if pattern and pattern != "*":
            matching_keys = [k for k in all_keys if fnmatch.fnmatch(k, pattern)]
        else:
            matching_keys = all_keys
        
        # Return all matching keys at once (simplified, real Redis uses cursor pagination)
        # For testing, we just return cursor 0 to indicate we're done
        return (0, [k.encode() for k in matching_keys])
    
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
    
    async def expire(self, key: str, seconds: int) -> int:
        """Set a timeout on key (for testing, we just return success)."""
        # In a real implementation this would set TTL, but for tests we don't need to track it
        # Just return 1 to indicate the key exists and the expire was set
        if (key in self._data or key in self._string_data or key in self._set_data):
            return 1
        return 0
    
    def multi(self):
        """Start a transaction and return a transaction object."""
        return FakeValkeyTransaction(self)
    
    def pipeline(self):
        """Create a pipeline for batch operations (returns itself for simplicity)."""
        return FakeValkeyPipeline(self)
    
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


@pytest.fixture(scope="session", autouse=True) 
def setup_worker_database():
    """
    Set up worker-specific database for complete isolation between pytest-xdist workers.
    
    Each worker gets its own database to eliminate race conditions and enable true 
    parallel test execution. Databases are auto-cleaned up after session completion.
    """
    worker_id = get_worker_id()
    worker_db_name = f"rpg_test_worker_{worker_id}"
    
    logger.info(f"Setting up worker database: {worker_db_name} (worker: {worker_id})")
    
    # Set the DATABASE_URL environment variable for this worker
    worker_db_url = get_worker_database_url(worker_id)
    sync_worker_db_url = get_sync_worker_database_url(worker_id) 
    os.environ["DATABASE_URL"] = worker_db_url
    
    # Connect to main PostgreSQL instance to create worker database
    admin_db_url = get_admin_database_url()
    admin_engine = create_engine(admin_db_url, echo=False)
    
    try:
        # Create worker-specific database
        # Use autocommit for DDL operations like CREATE DATABASE
        admin_engine = create_engine(admin_db_url, echo=False, isolation_level="AUTOCOMMIT")
        
        with admin_engine.connect() as conn:
            # Check if database exists first
            result = conn.execute(text(
                "SELECT 1 FROM pg_database WHERE datname = :db_name"
            ), {"db_name": worker_db_name})
            
            if result.fetchone() is None:
                logger.info(f"Creating worker database: {worker_db_name}")
                conn.execute(text(f'CREATE DATABASE "{worker_db_name}"'))
                logger.info(f"Worker database created: {worker_db_name}")
            else:
                logger.info(f"Worker database already exists: {worker_db_name}")
                
        admin_engine.dispose()  # Clean up admin engine
        logger.info(f"Worker database ready: {worker_db_name}")
        
        # Run Alembic migrations on the worker database
        try:
            logger.info(f"Running Alembic migrations on {worker_db_name}")
            logger.info(f"Alembic URL: {sync_worker_db_url}")
            
            # Run Alembic in subprocess to avoid pytest context issues
            import subprocess
            import sys
            
            env = os.environ.copy()
            env["DATABASE_URL"] = sync_worker_db_url
            
            # Run alembic upgrade head in subprocess
            result = subprocess.run([
                sys.executable, "-m", "alembic", 
                "upgrade", "head"
            ], 
            env=env, 
            cwd="/app/server",  # Change to server directory where alembic.ini is located
            capture_output=True, 
            text=True
            )
            
            if result.returncode != 0:
                logger.error(f"Alembic subprocess failed: {result.stderr}")
                raise RuntimeError(f"Alembic migration failed: {result.stderr}")
            else:
                logger.info("Alembic subprocess completed successfully")
                logger.info(f"Alembic stdout: {result.stdout}")
            
            logger.info(f"Alembic migrations completed for {worker_db_name}")
            
            # Verify the migration worked by checking if tables exist
            verify_engine = create_engine(sync_worker_db_url.replace("+asyncpg", ""), echo=False)
            with verify_engine.connect() as conn:
                result = conn.execute(text("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'"))
                table_count = result.scalar()
                logger.info(f"Worker database {worker_db_name} has {table_count} tables")
                if table_count == 0:
                    raise RuntimeError(f"No tables found in {worker_db_name} after migration")
            verify_engine.dispose()
            
        except Exception as alembic_error:
            logger.error(f"Alembic migration failed for {worker_db_name}: {alembic_error}")
            # Try to get more details about the database state
            try:
                verify_engine = create_engine(sync_worker_db_url.replace("+asyncpg", ""), echo=False)
                with verify_engine.connect() as conn:
                    result = conn.execute(text("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'"))
                    table_count = result.scalar()
                    logger.error(f"Database {worker_db_name} has {table_count} tables after failed migration")
                verify_engine.dispose()
            except Exception as verify_error:
                logger.error(f"Could not verify database state: {verify_error}")
            
            raise alembic_error
        
    except Exception as e:
        logger.error(f"Worker database setup failed: {e}")
        raise
    finally:
        # Ensure admin engine is disposed
        try:
            admin_engine.dispose()
        except:
            pass

    yield
    
    # Auto-cleanup: Drop worker database after session completes
    try:
        logger.info(f"Cleaning up worker database: {worker_db_name}")
        cleanup_engine = create_engine(admin_db_url, echo=False, isolation_level="AUTOCOMMIT")
        
        with cleanup_engine.connect() as conn:
            # Force disconnect any remaining connections to the worker database
            conn.execute(text(
                "SELECT pg_terminate_backend(pid) "
                "FROM pg_stat_activity " 
                "WHERE datname = :db_name AND pid <> pg_backend_pid()"
            ), {"db_name": worker_db_name})
            
            # Drop the worker database
            conn.execute(text(f'DROP DATABASE IF EXISTS "{worker_db_name}"'))
            logger.info(f"Worker database cleaned up: {worker_db_name}")
            
    except Exception as e:
        logger.warning(f"Worker database cleanup failed: {e}")
    finally:
        try:
            cleanup_engine.dispose()
        except:
            pass


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_db():
    """Set up async database engine and session factory for worker database."""
    global test_engine, TestingSessionLocal

    test_engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        # Optimize for test isolation with connection pooling
        poolclass=NullPool,  # Each session gets its own connection
    )
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    yield

    # Clean up
    await test_engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def session() -> AsyncGenerator[AsyncSession, None]:
    """
    Creates a fresh database session for each test with isolated connection.
    Cleans up test data after the test completes.
    """
    if TestingSessionLocal is None:
        raise RuntimeError("TestingSessionLocal not initialized")

    # Create a completely isolated session with its own connection
    isolated_engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False, 
        poolclass=NullPool,  # No connection pooling for maximum isolation
    )
    
    IsolatedSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=isolated_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with IsolatedSessionLocal() as session_obj:
        try:
            yield session_obj
        except Exception:
            await session_obj.rollback()
            raise
        finally:
            # Clean up data created during the test
            # Order matters due to foreign key constraints
            try:
                # Check if session is still active before cleanup
                if not session_obj.is_active:
                    logger.warning("Session is not active during test cleanup")
                else:
                    await session_obj.rollback()  # Rollback any uncommitted changes first
                    await session_obj.execute(delete(GroundItem))
                    await session_obj.execute(delete(PlayerInventory))
                    await session_obj.execute(delete(PlayerEquipment))
                    await session_obj.execute(delete(PlayerSkill))
                    await session_obj.execute(delete(Player))
                    # Don't delete Item table - it's static data synced on startup
                    await session_obj.commit()
                
            except Exception as cleanup_error:
                logger.warning(
                    f"Error during test session cleanup: {cleanup_error}",
                    extra={"error_type": type(cleanup_error).__name__}
                )
                try:
                    await session_obj.rollback()
                except Exception:
                    pass  # Ignore rollback errors during cleanup
                    
            finally:
                try:
                    await session_obj.close()
                    # Dispose the isolated engine
                    await isolated_engine.dispose()
                except Exception as close_error:
                    logger.warning(
                        f"Error closing test session: {close_error}",
                        extra={"error_type": type(close_error).__name__}
                    )


@pytest_asyncio.fixture(scope="function")
async def fake_valkey() -> FakeValkey:
    """
    Create a fresh FakeValkey instance for each test.
    """
    valkey = FakeValkey()
    yield valkey
    valkey.clear()


@pytest_asyncio.fixture(scope="function")
async def game_state_managers(fake_valkey: FakeValkey) -> AsyncGenerator[None, None]:
    """
    Initialize all game state managers for testing.
    
    Managers manage their own sessions internally - no external session binding.
    This ensures tests use the same architecture as production code.
    """
    if TestingSessionLocal is None:
        raise RuntimeError("TestingSessionLocal not initialized")
    
    # Initialize all managers with test dependencies
    init_all_managers(fake_valkey, TestingSessionLocal)
    
    # Load item cache from database (ReferenceDataManager uses its own session management)
    ref_manager = get_reference_data_manager()
    await ref_manager.load_item_cache_from_db()
    
    yield
    
    # Clean up - reset all managers
    reset_all_managers()


@pytest_asyncio.fixture(scope="function")
async def gsm(fake_valkey: FakeValkey, game_state_managers) -> AsyncGenerator[None, None]:
    """
    Legacy alias for game_state_managers fixture.
    
    Maintained for backward compatibility with existing tests.
    Tests can call individual manager getters (get_player_state_manager, etc.)
    to access the initialized managers.
    """
    # Yield nothing - game_state_managers handles initialization
    # Tests should use get_player_state_manager(), get_inventory_manager(), etc.
    yield


@pytest_asyncio.fixture(scope="function")
async def items_synced(game_state_managers) -> None:
    """
    Global fixture to ensure items are synced to database using ReferenceDataManager.
    
    Depends on game_state_managers fixture to ensure managers are initialized first.
    Uses managers' own session management - no external sessions needed.
    """
    from server.src.services.item_service import ItemService
    await ItemService.sync_items_to_db()
    # Reload cache after syncing to pick up any new items
    ref_manager = get_reference_data_manager()
    await ref_manager.load_item_cache_from_db()


@pytest_asyncio.fixture(scope="function")  
async def map_manager_loaded() -> None:
    """
    Global fixture to ensure maps are loaded for tests that need spawn positions.
    
    Loads real map files from server/maps/ directory.
    """
    from server.src.services.map_service import get_map_manager
    
    map_manager = get_map_manager()
    
    # Load real maps if not already loaded
    if not map_manager.maps:
        await map_manager.load_maps()
        logger.info(f"Loaded {len(map_manager.maps)} real map(s) for testing")


@pytest_asyncio.fixture(scope="function")
async def skills_synced(game_state_managers) -> None:
    """
    Global fixture to ensure skills are synced to database.
    
    Depends on game_state_managers fixture to ensure managers are initialized first.
    Uses managers' own session management - no external sessions needed.
    """
    from server.src.services.skill_service import SkillService
    await SkillService.sync_skills_to_db()


@pytest_asyncio.fixture
async def client(
    session: AsyncSession, fake_valkey: FakeValkey, game_state_managers
) -> AsyncGenerator[AsyncClient, None]:
    """
    Create an HTTP client that uses the test database session, fake Valkey, and initialized GSM.
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
    session: AsyncSession,  # Use the same session as HTTP endpoints
    game_state_managers,
) -> Callable[..., Awaitable[Player]]:
    """
    Fixture factory to create a test player using the same database session as HTTP endpoints.
    
    This ensures that players created by tests are visible to HTTP endpoint calls in the same test.
    Uses the proper architecture: Tests → Services → Database (same session as HTTP endpoints)
    """
    async def _create_player(
        username: str, 
        password: str, 
        x: int = 10, 
        y: int = 10, 
        map_id: str = "samplemap",
        current_hp: int = 10,
        **extra_fields
    ) -> Player:
        from server.src.core.security import get_password_hash
        from server.src.models.player import Player
        from server.src.services.game_state import get_player_state_manager, get_skills_manager
        
        # Create player record using the same session as HTTP endpoints
        # This ensures test players are visible to HTTP endpoint calls
        hashed_password = get_password_hash(password)
        
        player = Player(
            username=username,
            hashed_password=hashed_password,
            x=x,
            y=y,
            map_id=map_id,
            current_hp=current_hp
        )
        
        # Use the SAME session that HTTP endpoints use (from session fixture)
        session.add(player)
        await session.flush()  # Get player ID
        
        # Initialize skills using SkillsManager
        try:
            skills_manager = get_skills_manager()
            await skills_manager.grant_all_skills(player.id)
        except Exception:
            # Skills may not be available in test environment, that's ok
            pass
        
        # IMPORTANT: Commit the transaction so the player is visible to other sessions
        # This is required for authentication tests that use separate database sessions
        await session.commit()
        
        # Get managers for state operations
        player_state_manager = get_player_state_manager()
        
        # Apply any extra fields to the created player state  
        if extra_fields:
            current_state = await player_state_manager.get_player_full_state(player.id)
            if current_state:
                updated_state = {**current_state, **extra_fields}
                # Update player state with extra fields
                await player_state_manager.set_player_full_state(
                    player_id=player.id,
                    state=updated_state
                )
        
        # Register player as online for operations in tests
        await player_state_manager.register_online_player(player.id, player.username)
        
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
def create_offline_player(session: AsyncSession) -> Callable[..., Awaitable[Player]]:
    """
    Create database-only players for offline testing scenarios.
    
    This fixture creates Player records in the database without GSM registration,
    perfect for testing auto-loading behavior and offline player scenarios.
    """
    async def _create_offline_player(
        player_id: int,
        username: str = None,
        x_coord: int = 50, 
        y_coord: int = 50,
        map_id: str = "test_map",
        current_hp: int = 10,
        **extra_fields
    ) -> Player:
        from server.src.core.security import get_password_hash
        from server.src.models.player import Player
        
        if username is None:
            username = f"test_player_{player_id}"
            
        player = Player(
            id=player_id,
            username=username,
            hashed_password=get_password_hash("test_password"),
            x_coord=x_coord,
            y_coord=y_coord, 
            map_id=map_id,
            current_hp=current_hp,
            **extra_fields
        )
        session.add(player)
        await session.flush()  # Get auto-generated fields if needed
        return player
    
    return _create_offline_player


@pytest_asyncio.fixture
def create_player_with_skills(
    create_offline_player, session: AsyncSession, skills_synced
) -> Callable[..., Awaitable[Player]]:
    """
    Create player with pre-configured PlayerSkill records.
    
    This eliminates the boilerplate of creating Player + PlayerSkill records
    manually while ensuring foreign key constraints are satisfied.
    """
    async def _create_with_skills(
        player_id: int,
        skills_data: Dict[str, Dict[str, Any]],
        **player_kwargs
    ) -> Player:
        from server.src.services.skill_service import SkillService
        from server.src.models.skill import PlayerSkill
        
        # Create base player first (satisfies foreign key constraint)
        player = await create_offline_player(player_id, **player_kwargs)
        
        # Get skill ID mapping
        skill_id_map = await SkillService.get_skill_id_map()
        
        # Create PlayerSkill records
        for skill_name, skill_props in skills_data.items():
            skill_record = PlayerSkill(
                player_id=player_id,
                skill_id=skill_id_map[skill_name],
                current_level=skill_props.get('level', 1),
                experience=skill_props.get('xp', 0)
            )
            session.add(skill_record)
            
        await session.flush()
        return player
    
    return _create_with_skills


@pytest_asyncio.fixture
def create_player_with_inventory(
    create_offline_player, session: AsyncSession, items_synced
) -> Callable[..., Awaitable[Player]]:
    """
    Create player with pre-configured PlayerInventory records.
    
    This eliminates the boilerplate of creating Player + PlayerInventory records
    manually while ensuring foreign key constraints are satisfied.
    """
    async def _create_with_inventory(
        player_id: int,
        inventory_data: List[Dict[str, Any]],
        **player_kwargs
    ) -> Player:
        from server.src.models.item import PlayerInventory
        
        # Create base player first (satisfies foreign key constraint)
        player = await create_offline_player(player_id, **player_kwargs)
        
        # Create PlayerInventory records
        for inv_item in inventory_data:
            inventory_record = PlayerInventory(
                player_id=player_id,
                item_id=inv_item['item_id'],
                slot=inv_item['slot'],
                quantity=inv_item['quantity'],
                current_durability=inv_item.get('durability', 1.0)
            )
            session.add(inventory_record)
            
        await session.flush()
        return player
    
    return _create_with_inventory


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


# Import modern WebSocket testing framework to register fixtures
from server.src.tests.websocket_test_utils import WebSocketTestClient


@pytest_asyncio.fixture
async def test_client(
    fake_valkey: FakeValkey, game_state_managers, map_manager_loaded: None
) -> AsyncGenerator[WebSocketTestClient, None]:
    """
    Create a WebSocket test client with per-test data cleanup.
    
    Provides a pre-authenticated WebSocket connection with unique usernames
    to prevent conflicts. Uses PlayerService for player creation following
    the service-first architecture pattern.
    
    Uses AsyncExitStack for proper resource cleanup and timeouts to prevent hanging.
    """
    import uuid
    from contextlib import AsyncExitStack
    from httpx import AsyncClient
    from httpx_ws import aconnect_ws
    from httpx_ws.transport import ASGIWebSocketTransport
    from server.src.services.player_service import PlayerService
    from server.src.schemas.player import PlayerCreate
    from common.src.protocol import WSMessage, MessageType, AuthenticatePayload
    from server.src.core.security import create_access_token
    
    # Create a session for this integration test
    if TestingSessionLocal is None:
        raise RuntimeError("TestingSessionLocal not initialized")
    
    # Use AsyncExitStack for guaranteed cleanup
    async with AsyncExitStack() as stack:
        # Track for final cleanup
        player_id = None
        
        try:
            # Create session
            session = await stack.enter_async_context(TestingSessionLocal())
            
            # Override dependencies for WebSocket endpoint
            async def override_get_db():
                yield session
            
            async def override_get_valkey():
                return fake_valkey
            
            app.dependency_overrides[get_db] = override_get_db
            app.dependency_overrides[get_valkey] = override_get_valkey
            
            # Create test player using PlayerService (service-first pattern)
            username = f"testuser_{uuid.uuid4().hex[:8]}"
            password = "testpass123"
            
            player_data = PlayerCreate(username=username, password=password)
            player_result = await PlayerService.create_player(
                player_data=player_data,
                x=10,
                y=10,
                map_id="samplemap"
            )
            player_id = player_result.id
            
            # Create JWT token
            token = create_access_token(data={"sub": username})
            
            # Create httpx-ws transport and client (manual management to avoid cancel scope issues)
            transport = ASGIWebSocketTransport(app)
            http_client = AsyncClient(transport=transport, base_url="http://test")
            await http_client.__aenter__()
            
            # Connect WebSocket with timeout
            ws_context = aconnect_ws("http://test/ws", http_client)
            websocket = await asyncio.wait_for(
                ws_context.__aenter__(),
                timeout=5.0
            )
            
            try:
                # Authenticate with timeout
                auth_message = WSMessage(
                    id=str(uuid.uuid4()),
                    type=MessageType.CMD_AUTHENTICATE,
                    payload=AuthenticatePayload(token=token).model_dump(),
                    version="2.0"
                )
                
                packed_auth = msgpack.packb(auth_message.model_dump(), use_bin_type=True)
                await websocket.send_bytes(packed_auth)
                
                # Wait for auth response with timeout
                auth_response_bytes = await asyncio.wait_for(
                    websocket.receive_bytes(),
                    timeout=5.0
                )
                auth_response_data = msgpack.unpackb(auth_response_bytes, raw=False)
                auth_response = WSMessage(**auth_response_data)
                
                if auth_response.type != MessageType.EVENT_WELCOME:
                    raise Exception(f"Authentication failed: expected WELCOME but got {auth_response.type}")
                
                # Consume welcome chat message with timeout
                chat_response_bytes = await asyncio.wait_for(
                    websocket.receive_bytes(),
                    timeout=5.0
                )
                chat_response_data = msgpack.unpackb(chat_response_bytes, raw=False)
                chat_response = WSMessage(**chat_response_data)
                
                if chat_response.type != MessageType.EVENT_CHAT_MESSAGE:
                    raise Exception(f"Expected welcome chat message but got {chat_response.type}")
                
                # Create WebSocket test client wrapper
                client = WebSocketTestClient(websocket)
                await client.__aenter__()
                
                yield client
                
            finally:
                # Clean up WebSocket client
                try:
                    await client.close()
                except Exception as e:
                    logger.warning(f"Error closing WebSocket client: {e}")
                
                # Close WebSocket connection
                try:
                    await ws_context.__aexit__(None, None, None)
                except Exception as e:
                    logger.warning(f"Error closing WebSocket connection: {e}")
                
                # Close HTTP client
                try:
                    await http_client.__aexit__(None, None, None)
                except Exception as e:
                    logger.warning(f"Error closing HTTP client: {e}")
            
        finally:
            # AsyncExitStack will clean up all contexts automatically
            # We only need to handle player deletion which is outside the stack
            if player_id is not None:
                try:
                    await PlayerService.delete_player(player_id)
                except Exception as e:
                    logger.warning(f"Error deleting test player: {e}")
            
            # Clear dependency overrides
            app.dependency_overrides.clear()


@pytest_asyncio.fixture
def create_test_token() -> Callable[[str], str]:
    """
    Fixture factory to create a JWT token for testing with the async client.
    """
    def _create_token(username: str) -> str:
        return create_access_token(data={"sub": username})
    
    return _create_token


@pytest_asyncio.fixture  
def test_disconnection_context(
    fake_valkey: FakeValkey, game_state_managers
) -> Dict[str, Any]:
    """
    Provides a context for testing WebSocket disconnection scenarios.
    Does NOT attempt actual connections - just provides the setup needed
    for disconnection tests that handle their own connection attempts.
    """
    # Create a session for this integration test
    if TestingSessionLocal is None:
        raise RuntimeError("TestingSessionLocal not initialized")
    
    return {
        'session_factory': TestingSessionLocal,
        'fake_valkey': fake_valkey,
        'app': app,
        'get_db': get_db,
        'get_valkey': get_valkey
    }


@pytest_asyncio.fixture
def test_item_id() -> str:
    """Provide a test item ID for equipment tests"""
    return "wooden_sword"  # Use an item that should exist in the test data
