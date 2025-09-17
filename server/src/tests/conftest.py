import pytest
import pytest_asyncio
from typing import AsyncGenerator, Callable, Awaitable, Dict
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from unittest.mock import AsyncMock

from server.src.main import app
from server.src.core.database import get_db
from server.src.models.base import Base
from server.src.models.player import Player
from server.src.core.security import get_password_hash, create_access_token

# Use SQLite in memory for tests to avoid async connection issues
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# Global test engine and session maker
test_engine = None
TestingSessionLocal = None


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
            await session_obj.close()


@pytest_asyncio.fixture
async def client(session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    Create an HTTP client that uses the test database session.
    """
    app.dependency_overrides[get_db] = lambda: session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

    # Clean up
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
def mock_valkey():
    """Mock Valkey client for testing."""
    return AsyncMock()


@pytest_asyncio.fixture
def create_test_player_and_token(
    session: AsyncSession,
) -> Callable[..., Awaitable[tuple[str, Player]]]:
    """
    Fixture factory to create a test player and a valid JWT for them.
    This avoids hitting the login endpoint for every test.
    """

    async def _create_player_and_token(
        username: str, password: str, initial_data: Dict | None = None
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
