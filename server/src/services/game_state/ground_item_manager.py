"""
Ground item management - ephemeral world items.

Handles items dropped on the ground with despawn timers and loot protection.
Pure persistence layer; business logic (loot rules, distance checks) in GroundItemService.
"""

import traceback
from typing import Any, Dict, List, Optional

from glide import GlideClient
from sqlalchemy import select, delete
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.postgresql import insert as pg_insert

from server.src.core.config import settings
from server.src.core.logging_config import get_logger

from .base_manager import BaseManager

logger = get_logger(__name__)

GROUND_ITEM_KEY = "ground_item:{ground_item_id}"
GROUND_ITEMS_MAP_KEY = "ground_items:map:{map_id}"
GROUND_ITEMS_NEXT_ID_KEY = "ground_items:next_id"
DIRTY_GROUND_ITEMS_KEY = "dirty:ground_items"
GROUND_ITEMS_DELETE_KEY = "ground_items:to_delete"

# Ground items use longer TTL since they persist until picked up/despawn
GROUND_ITEM_TTL = 3600  # 1 hour


class GroundItemManager(BaseManager):
    """Manages ground items (dropped items in the world)."""

    def __init__(
        self,
        valkey_client: Optional[GlideClient] = None,
        session_factory: Optional[sessionmaker] = None,
    ):
        super().__init__(valkey_client, session_factory)

    # =========================================================================
    # Ground Item CRUD
    # =========================================================================

    async def get_next_ground_item_id(self) -> int:
        """Get next unique ground item ID."""
        if not self._valkey or not settings.USE_VALKEY:
            # Fallback to DB sequence or timestamp
            return int(self._utc_timestamp() * 1000)

        next_id = await self._valkey.incr(GROUND_ITEMS_NEXT_ID_KEY)
        return next_id

    async def add_ground_item(
        self,
        map_id: str,
        x: int,
        y: int,
        item_id: int,
        quantity: int,
        durability: float,
        dropped_by_player_id: Optional[int] = None,
        loot_protection_expires_at: Optional[float] = None,
        despawn_at: Optional[float] = None,
    ) -> int:
        """Add a new ground item. Returns the ground item ID."""
        ground_item_id = await self.get_next_ground_item_id()

        item_data = {
            "ground_item_id": ground_item_id,
            "map_id": map_id,
            "x": x,
            "y": y,
            "item_id": item_id,
            "quantity": quantity,
            "durability": durability,
            "dropped_by_player_id": dropped_by_player_id,
            "loot_protection_expires_at": loot_protection_expires_at,
            "despawn_at": despawn_at,
            "created_at": self._utc_timestamp(),
        }

        if self._valkey and settings.USE_VALKEY:
            # Store item data
            key = GROUND_ITEM_KEY.format(ground_item_id=ground_item_id)
            await self._cache_in_valkey(key, item_data, GROUND_ITEM_TTL)

            # Add to map index
            map_key = GROUND_ITEMS_MAP_KEY.format(map_id=map_id)
            await self._valkey.sadd(map_key, [str(ground_item_id)])
            await self._valkey.expire(map_key, GROUND_ITEM_TTL)

            # Mark for DB sync
            await self._valkey.sadd(DIRTY_GROUND_ITEMS_KEY, [str(ground_item_id)])

        return ground_item_id

    async def remove_ground_item(self, ground_item_id: int, map_id: str) -> bool:
        """Remove a ground item (picked up or despawned)."""
        if not self._valkey or not settings.USE_VALKEY:
            # Direct DB removal
            await self._remove_from_db(ground_item_id)
            return True

        key = GROUND_ITEM_KEY.format(ground_item_id=ground_item_id)

        # Check if item exists
        exists = await self._valkey.exists([key])
        if not exists:
            return False

        # Remove from Valkey
        await self._delete_from_valkey(key)

        # Remove from map index
        map_key = GROUND_ITEMS_MAP_KEY.format(map_id=map_id)
        await self._valkey.srem(map_key, [str(ground_item_id)])

        # Mark for DB deletion
        await self._valkey.sadd(GROUND_ITEMS_DELETE_KEY, [str(ground_item_id)])

        return True

    async def _remove_from_db(self, ground_item_id: int) -> None:
        if not self._session_factory:
            return

        from server.src.models.item import GroundItem

        async with self._db_session() as db:
            await db.execute(
                delete(GroundItem).where(GroundItem.id == ground_item_id)
            )
            await self._commit_if_not_test_session(db)

    async def get_ground_item(self, ground_item_id: int) -> Optional[Dict[str, Any]]:
        """Get ground item by ID."""
        if not self._valkey or not settings.USE_VALKEY:
            return await self._load_ground_item_from_db(ground_item_id)

        key = GROUND_ITEM_KEY.format(ground_item_id=ground_item_id)
        data = await self._get_from_valkey(key)

        if data:
            await self._refresh_ttl(key, GROUND_ITEM_TTL)
            return self._decode_ground_item(data)

        return None

    async def _load_ground_item_from_db(
        self, ground_item_id: int
    ) -> Optional[Dict[str, Any]]:
        if not self._session_factory:
            return None

        from server.src.models.item import GroundItem

        async with self._db_session() as db:
            result = await db.execute(
                select(GroundItem).where(GroundItem.id == ground_item_id)
            )
            item = result.scalar_one_or_none()

            if item:
                return {
                    "ground_item_id": item.id,
                    "map_id": item.map_id,
                    "x": item.x,
                    "y": item.y,
                    "item_id": item.item_id,
                    "quantity": item.quantity,
                    "durability": item.durability or 1.0,
                    "dropped_by_player_id": item.dropped_by_player_id,
                    "loot_protection_expires_at": (
                        item.loot_protection_expires_at.timestamp()
                        if item.loot_protection_expires_at
                        else None
                    ),
                    "despawn_at": (
                        item.despawn_at.timestamp() if item.despawn_at else None
                    ),
                }
            return None

    def _decode_ground_item(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Decode ground item data from Valkey."""
        return {
            "ground_item_id": self._decode_from_valkey(
                data.get("ground_item_id"), int
            ),
            "map_id": data.get("map_id", ""),
            "x": self._decode_from_valkey(data.get("x"), int),
            "y": self._decode_from_valkey(data.get("y"), int),
            "item_id": self._decode_from_valkey(data.get("item_id"), int),
            "quantity": self._decode_from_valkey(data.get("quantity"), int),
            "durability": self._decode_from_valkey(data.get("durability"), float),
            "dropped_by_player_id": self._decode_from_valkey(
                data.get("dropped_by_player_id"), int
            ),
            "loot_protection_expires_at": self._decode_from_valkey(
                data.get("loot_protection_expires_at"), float
            ),
            "despawn_at": self._decode_from_valkey(data.get("despawn_at"), float),
            "created_at": self._decode_from_valkey(data.get("created_at"), float),
        }

    async def get_ground_items_on_map(self, map_id: str) -> List[Dict[str, Any]]:
        """Get all ground items on a specific map."""
        if not self._valkey or not settings.USE_VALKEY:
            return await self._load_ground_items_for_map_from_db(map_id)

        map_key = GROUND_ITEMS_MAP_KEY.format(map_id=map_id)
        item_ids = await self._valkey.smembers(map_key)

        items = []
        for item_id_bytes in item_ids:
            item_id = int(self._decode_bytes(item_id_bytes))
            item = await self.get_ground_item(item_id)
            if item:
                items.append(item)

        return items

    async def _load_ground_items_for_map_from_db(self, map_id: str) -> List[Dict[str, Any]]:
        if not self._session_factory:
            return []

        from server.src.models.item import GroundItem

        async with self._db_session() as db:
            result = await db.execute(
                select(GroundItem).where(GroundItem.map_id == map_id)
            )
            items = result.scalars().all()

            return [
                {
                    "ground_item_id": item.id,
                    "map_id": item.map_id,
                    "x": item.x,
                    "y": item.y,
                    "item_id": item.item_id,
                    "quantity": item.quantity,
                    "durability": item.durability or 1.0,
                    "dropped_by_player_id": item.dropped_by_player_id,
                    "loot_protection_expires_at": (
                        item.loot_protection_expires_at.timestamp()
                        if item.loot_protection_expires_at
                        else None
                    ),
                    "despawn_at": (
                        item.despawn_at.timestamp() if item.despawn_at else None
                    ),
                }
                for item in items
            ]

    async def load_ground_items_from_db(self) -> int:
        """Load all ground items from database into Valkey (server startup)."""
        if not self._session_factory:
            return 0

        if not self._valkey or not settings.USE_VALKEY:
            return 0

        from server.src.models.item import GroundItem

        async with self._db_session() as db:
            result = await db.execute(select(GroundItem))
            items = result.scalars().all()

            count = 0
            for item in items:
                item_data = {
                    "ground_item_id": item.id,
                    "map_id": item.map_id,
                    "x": item.x,
                    "y": item.y,
                    "item_id": item.item_id,
                    "quantity": item.quantity,
                    "durability": item.durability or 1.0,
                    "dropped_by_player_id": item.dropped_by_player_id,
                    "loot_protection_expires_at": (
                        item.loot_protection_expires_at.timestamp()
                        if item.loot_protection_expires_at
                        else None
                    ),
                    "despawn_at": (
                        item.despawn_at.timestamp() if item.despawn_at else None
                    ),
                    "created_at": item.created_at.timestamp() if item.created_at else self._utc_timestamp(),
                }

                key = GROUND_ITEM_KEY.format(ground_item_id=item.id)
                await self._cache_in_valkey(key, item_data, GROUND_ITEM_TTL)

                # Add to map index
                map_key = GROUND_ITEMS_MAP_KEY.format(map_id=item.map_id)
                await self._valkey.sadd(map_key, [str(item.id)])
                await self._valkey.expire(map_key, GROUND_ITEM_TTL)

                count += 1

            # Set next ID
            if items:
                max_id = max(item.id for item in items)
                await self._valkey.set(GROUND_ITEMS_NEXT_ID_KEY, str(max_id + 1))

            logger.info(f"Loaded {count} ground items from database")
            return count

    # =========================================================================
    # Batch Sync Support
    # =========================================================================

    async def sync_ground_items_to_db(self, db) -> None:
        """Sync ground items to database (periodic cleanup)."""
        if not self._valkey:
            return

        from server.src.models.item import GroundItem
        from datetime import datetime, timezone

        # Get dirty items
        dirty_items = await self._valkey.smembers(DIRTY_GROUND_ITEMS_KEY)

        for item_id_bytes in dirty_items:
            item_id = int(self._decode_bytes(item_id_bytes))
            key = GROUND_ITEM_KEY.format(ground_item_id=item_id)
            data = await self._get_from_valkey(key)

            if not data:
                continue

            # Upsert to DB
            stmt = pg_insert(GroundItem).values(
                id=item_id,
                map_id=data.get("map_id"),
                x=self._decode_from_valkey(data.get("x"), int),
                y=self._decode_from_valkey(data.get("y"), int),
                item_id=self._decode_from_valkey(data.get("item_id"), int),
                quantity=self._decode_from_valkey(data.get("quantity"), int),
                durability=self._decode_from_valkey(data.get("durability"), float),
                dropped_by_player_id=self._decode_from_valkey(
                    data.get("dropped_by_player_id"), int
                ),
                loot_protection_expires_at=datetime.fromtimestamp(
                    self._decode_from_valkey(data.get("loot_protection_expires_at"), float),
                    tz=timezone.utc,
                )
                if data.get("loot_protection_expires_at")
                else None,
                despawn_at=datetime.fromtimestamp(
                    self._decode_from_valkey(data.get("despawn_at"), float),
                    tz=timezone.utc,
                )
                if data.get("despawn_at")
                else None,
                created_at=datetime.fromtimestamp(
                    self._decode_from_valkey(data.get("created_at"), float),
                    tz=timezone.utc,
                )
                if data.get("created_at")
                else datetime.now(timezone.utc),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "map_id": data.get("map_id"),
                    "x": self._decode_from_valkey(data.get("x"), int),
                    "y": self._decode_from_valkey(data.get("y"), int),
                    "quantity": self._decode_from_valkey(data.get("quantity"), int),
                    "durability": self._decode_from_valkey(data.get("durability"), float),
                },
            )
            await db.execute(stmt)

        # Process deletions
        items_to_delete = await self._valkey.smembers(GROUND_ITEMS_DELETE_KEY)
        for item_id_bytes in items_to_delete:
            item_id = int(self._decode_bytes(item_id_bytes))
            # Delete from database
            await db.execute(
                delete(GroundItem).where(GroundItem.id == item_id)
            )
            logger.debug("Deleted ground item from DB", extra={"item_id": item_id})

        # Clear dirty sets
        await self._valkey.delete([DIRTY_GROUND_ITEMS_KEY, GROUND_ITEMS_DELETE_KEY])


# Singleton instance
_ground_item_manager: Optional[GroundItemManager] = None


def init_ground_item_manager(
    valkey_client: Optional[GlideClient] = None,
    session_factory: Optional[sessionmaker] = None,
) -> GroundItemManager:
    global _ground_item_manager
    _ground_item_manager = GroundItemManager(valkey_client, session_factory)
    return _ground_item_manager


def get_ground_item_manager() -> GroundItemManager:
    if _ground_item_manager is None:
        raise RuntimeError("GroundItemManager not initialized")
    return _ground_item_manager


def reset_ground_item_manager() -> None:
    global _ground_item_manager
    _ground_item_manager = None
