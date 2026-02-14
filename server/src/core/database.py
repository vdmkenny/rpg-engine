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

import logging
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from glide import GlideClient, GlideClientConfiguration, NodeAddress, BackoffStrategy

from server.src.core.config import settings

logger = logging.getLogger(__name__)

# --- PostgreSQL Database Setup ---
engine = create_async_engine(
    settings.DATABASE_URL, 
    echo=settings.DATABASE_ECHO, 
    future=True,
    pool_size=settings.DB_POOL_SIZE,           # Persistent connections (default 20)
    max_overflow=settings.DB_MAX_OVERFLOW,     # Additional connections (default 30, total 50)
    pool_timeout=settings.DB_POOL_TIMEOUT,     # Wait timeout in seconds (default 30)
    pool_recycle=settings.DB_POOL_RECYCLE,     # Recycle connections after seconds (default 3600 = 1 hour)
    pool_pre_ping=settings.DB_POOL_PRE_PING,  # Validate connections before use (default True)
    connect_args={
        "server_settings": {
            "jit": "off",                       # Disable JIT for consistent performance
            "application_name": "rpg_engine"    # Application name for PostgreSQL logging
        }
    }
)

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
    # Create a fresh engine with production pool settings
    engine = create_async_engine(
        settings.DATABASE_URL, 
        echo=settings.DATABASE_ECHO, 
        future=True,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
        pool_recycle=settings.DB_POOL_RECYCLE,
        pool_pre_ping=settings.DB_POOL_PRE_PING,
        connect_args={
            "server_settings": {
                "jit": "off",
                "application_name": "rpg_engine"
            }
        }
    )
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

valkey_config = GlideClientConfiguration(
    [NodeAddress(host, port)],
    request_timeout=500,
    reconnect_strategy=BackoffStrategy(
        num_of_retries=5,
        factor=100,
        exponent_base=2,
    ),
)

class ResilientValkeyClient:
    """
    Wrapper around GlideClient that automatically reconnects on connection failures.
    
    When a method call fails due to a closed connection, this wrapper recreates the
    GlideClient and retries the operation. This ensures that Valkey idle disconnections
    (after ~27 minutes) don't permanently break the server.
    """

    def __init__(self, config: GlideClientConfiguration):
        self._config = config
        self._client: GlideClient | None = None
        self._lock_created = False

    async def _ensure_connected(self) -> GlideClient:
        """Ensure the client is connected, creating/recreating if necessary."""
        if self._client is None:
            self._client = await GlideClient.create(self._config)
            logger.info("ResilientValkeyClient: Created new GlideClient connection")
        return self._client

    async def _call_with_reconnect(self, method_name: str, *args, **kwargs):
        """
        Execute a method on the Valkey client with automatic reconnection on failure.
        """
        try:
            client = await self._ensure_connected()
            method = getattr(client, method_name)
            return await method(*args, **kwargs)
        except Exception as e:
            # Connection error — try to reconnect and retry once
            logger.warning(
                f"ResilientValkeyClient: Call to {method_name} failed with {type(e).__name__}, attempting reconnection",
                extra={"error": str(e)}
            )
            self._client = None  # Force reconnection
            try:
                client = await self._ensure_connected()
                method = getattr(client, method_name)
                result = await method(*args, **kwargs)
                logger.info(f"ResilientValkeyClient: Reconnection successful, {method_name} succeeded")
                return result
            except Exception as retry_error:
                # Reconnection/retry failed — log and re-raise
                logger.error(
                    f"ResilientValkeyClient: Reconnection/retry of {method_name} failed",
                    extra={"error": str(retry_error)}
                )
                raise

    def __getattr__(self, name: str):
        """Proxy all method calls through _call_with_reconnect."""
        async def method_wrapper(*args, **kwargs):
            return await self._call_with_reconnect(name, *args, **kwargs)
        return method_wrapper


valkey_client: ResilientValkeyClient | None = None


async def get_valkey() -> ResilientValkeyClient:
    """
    Dependency to get a Valkey client wrapped with automatic reconnection.
    """
    global valkey_client
    if valkey_client is None:
        valkey_client = ResilientValkeyClient(valkey_config)
    return valkey_client


def reset_valkey():
    """
    Reset the Valkey client singleton.
    
    This is needed for test isolation when using Starlette's TestClient,
    which creates a new event loop for each test. The Valkey client from
    the previous event loop becomes invalid and must be discarded.
    
    Note: This function must be called synchronously before TestClient starts.
    The old client will be recreated on next get_valkey() call.
    """
    global valkey_client
    if valkey_client is not None:
        valkey_client._client = None  # Force reconnection on next use
    valkey_client = None
