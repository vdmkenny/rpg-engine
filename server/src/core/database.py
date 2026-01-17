"""
Database and cache connection setup.

This module initializes the connections to the primary database (PostgreSQL)
and the in-memory cache (Valkey/Redis). It provides dependency injection
functions (`get_db` and `get_valkey`) for use in other parts of the application.

Notes for the next agent:
- The Valkey client is created as a singleton instance. This is generally
  fine for most applications, but for very high-concurrency scenarios,
  you might consider a connection pool if the client library supports it.
- The database engine is configured with `echo=True`, which logs all SQL
  statements. This is useful for development but should be disabled in
  production for performance and security reasons.
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from glide import GlideClient, GlideClientConfiguration, NodeAddress

from server.src.core.config import settings

# --- PostgreSQL Database Setup ---
engine = create_async_engine(settings.DATABASE_URL, echo=settings.DATABASE_ECHO, future=True)

AsyncSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine, class_=AsyncSession
)


def reset_engine():
    """
    Reset the database engine and session factory.
    
    This is needed for test isolation when using Starlette's TestClient,
    which creates a new event loop for each test. Connections from the
    previous event loop become invalid and must be discarded.
    
    Note: This function must be called synchronously before TestClient starts.
    The old engine's connections will be garbage collected.
    """
    global engine, AsyncSessionLocal
    # Create a fresh engine (old connections will be garbage collected)
    engine = create_async_engine(settings.DATABASE_URL, echo=settings.DATABASE_ECHO, future=True)
    AsyncSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=engine, class_=AsyncSession
    )


async def get_db() -> AsyncSession:
    """
    Dependency to get a database session.
    Uses the current AsyncSessionLocal which may be reset between tests.
    """
    async with AsyncSessionLocal() as session:
        yield session


# --- Valkey (Redis) Cache Setup ---
# Parse Valkey URL and create configuration
import urllib.parse

parsed_url = urllib.parse.urlparse(settings.VALKEY_URL)
host = parsed_url.hostname or "localhost"
port = parsed_url.port or 6379

valkey_config = GlideClientConfiguration([NodeAddress(host, port)])

valkey_client: GlideClient | None = None


async def get_valkey() -> GlideClient:
    """
    Dependency to get a Valkey client.
    """
    global valkey_client
    if valkey_client is None:
        valkey_client = await GlideClient.create(valkey_config)
    return valkey_client
