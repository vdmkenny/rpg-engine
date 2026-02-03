"""
Shared infrastructure for all game state managers.

Provides database session management, Valkey operations, TTL handling,
and serialization utilities used across all managers.
"""

import json
import traceback
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Callable, Awaitable

from glide import GlideClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from server.src.core.config import settings
from server.src.core.logging_config import get_logger

logger = get_logger(__name__)

# TTL Configuration (in seconds)
TIER1_TTL = settings.GAME_STATE_CACHE.get("essential_data_ttl", 3600)
TIER2_TTL = settings.GAME_STATE_CACHE.get("inventory_ttl", 1800)
SKILLS_TTL = settings.GAME_STATE_CACHE.get("skills_ttl", 900)


class BaseManager:
    """Base class providing shared infrastructure for all game state managers."""

    def __init__(
        self,
        valkey_client: Optional[GlideClient] = None,
        session_factory: Optional[sessionmaker] = None,
    ):
        self._valkey = valkey_client
        self._session_factory = session_factory
        self._bound_test_session: Optional[AsyncSession] = None

    @property
    def valkey(self) -> Optional[GlideClient]:
        return self._valkey

    def bind_test_session(self, session: AsyncSession) -> None:
        self._bound_test_session = session
        logger.debug("Test session bound")

    def unbind_test_session(self) -> None:
        self._bound_test_session = None
        logger.debug("Test session unbound")

    @asynccontextmanager
    async def _db_session(self):
        if self._bound_test_session is not None:
            logger.debug(f"Using bound test session: {id(self._bound_test_session)}")
            yield self._bound_test_session
            return

        if not self._session_factory:
            raise RuntimeError("Database session factory not initialized")

        async with self._session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    async def _commit_if_not_test_session(self, db: AsyncSession) -> None:
        await db.commit()

    def _utc_timestamp(self) -> float:
        return datetime.now(timezone.utc).timestamp()

    def _decode_bytes(self, value: bytes | str) -> str:
        return value.decode() if isinstance(value, bytes) else value

    def _encode_for_valkey(self, value: Any) -> str:
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        return str(value)

    def _decode_from_valkey(self, value: Any, target_type: type = str) -> Any:
        if value is None:
            return None

        if isinstance(value, bytes):
            value = value.decode()

        if target_type == int:
            return int(value)
        elif target_type == float:
            return float(value)
        elif target_type == bool:
            return value.lower() == "true" if isinstance(value, str) else bool(value)
        elif target_type in (dict, list):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return {} if target_type == dict else []

        return value

    async def _refresh_ttl(self, key: str, ttl: int) -> None:
        if self._valkey:
            await self._valkey.expire(key, ttl)

    async def _cache_in_valkey(
        self, key: str, data: Dict[str, Any], ttl: int
    ) -> None:
        if not self._valkey:
            return

        encoded_data = {k: self._encode_for_valkey(v) for k, v in data.items()}
        await self._valkey.hset(key, encoded_data)
        await self._valkey.expire(key, ttl)

    async def _get_from_valkey(self, key: str) -> Optional[Dict[str, Any]]:
        if not self._valkey:
            return None

        raw = await self._valkey.hgetall(key)
        if not raw:
            return None

        return {self._decode_bytes(k): self._decode_bytes(v) for k, v in raw.items()}

    async def _delete_from_valkey(self, key: str) -> None:
        if self._valkey:
            await self._valkey.delete([key])

    async def auto_load_with_ttl(
        self,
        key: str,
        load_fn: Callable[[], Awaitable[Optional[Dict[str, Any]]]],
        ttl: int,
        decoder: Optional[Dict[str, type]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Generic auto-loader: check Valkey first, load from DB if missing.

        Args:
            key: Valkey key to check
            load_fn: Async function to load data from database
            ttl: TTL to set on cached data
            decoder: Optional dict mapping field names to types for decoding

        Returns:
            Data dict or None if not found anywhere
        """
        # 1. Try Valkey first
        if self._valkey and settings.USE_VALKEY:
            cached = await self._get_from_valkey(key)
            if cached:
                await self._refresh_ttl(key, ttl)

                if decoder:
                    return {
                        k: self._decode_from_valkey(v, decoder.get(k, str))
                        for k, v in cached.items()
                    }
                return cached

        # 2. Load from database
        try:
            db_data = await load_fn()
            if db_data and self._valkey and settings.USE_VALKEY:
                await self._cache_in_valkey(key, db_data, ttl)
            return db_data
        except Exception as e:
            logger.error(
                "Failed to auto-load data",
                extra={"key": key, "error": str(e), "traceback": traceback.format_exc()},
            )
            return None
