"""
Equipment management - Tier 2 data with auto-loading.

Pure persistence layer: CRUD operations only, no business logic.
Equipment validation and requirements checking handled by EquipmentService.
"""

import traceback
from typing import Any, Dict, Optional

from glide import GlideClient
from sqlalchemy import select, delete
from sqlalchemy.orm import sessionmaker

from server.src.core.config import settings
from server.src.core.logging_config import get_logger

from .base_manager import BaseManager, TIER2_TTL

logger = get_logger(__name__)

EQUIPMENT_KEY = "equipment:{player_id}"
DIRTY_EQUIPMENT_KEY = "dirty:equipment"


class EquipmentManager(BaseManager):
    """Manages player equipment persistence with transparent auto-loading."""

    def __init__(
        self,
        valkey_client: Optional[GlideClient] = None,
        session_factory: Optional[sessionmaker] = None,
    ):
        super().__init__(valkey_client, session_factory)

    # =========================================================================
    # Equipment CRUD
    # =========================================================================

    async def get_equipment(self, player_id: int) -> Dict[str, Dict[str, Any]]:
        """Get entire equipment with transparent auto-loading from DB."""
        if not settings.USE_VALKEY or not self._valkey:
            return await self._load_equipment_from_db(player_id)

        key = EQUIPMENT_KEY.format(player_id=player_id)

        async def load_from_db():
            return await self._load_equipment_from_db(player_id)

        equipment = await self.auto_load_with_ttl(key, load_from_db, TIER2_TTL)
        return equipment or {}

    async def _load_equipment_from_db(self, player_id: int) -> Dict[str, Dict[str, Any]]:
        if not self._session_factory:
            return {}

        from server.src.models.item import PlayerEquipment

        async with self._db_session() as db:
            result = await db.execute(
                select(PlayerEquipment).where(PlayerEquipment.player_id == player_id)
            )
            equipments = result.scalars().all()

            equipment_data = {}
            for eq in equipments:
                equipment_data[eq.equipment_slot] = {
                    "item_id": eq.item_id,
                    "quantity": eq.quantity,
                    "current_durability": eq.current_durability or 1.0,
                }

            return equipment_data

    async def get_equipment_slot(
        self, player_id: int, slot: str
    ) -> Optional[Dict[str, Any]]:
        """Get specific equipment slot contents."""
        equipment = await self.get_equipment(player_id)
        return equipment.get(slot)

    async def set_equipment_slot(
        self,
        player_id: int,
        slot: str,
        item_id: int,
        quantity: int = 1,
        durability: float = 1.0,
    ) -> None:
        """Set item in specific equipment slot."""
        if not settings.USE_VALKEY or not self._valkey:
            await self._update_equipment_slot_in_db(
                player_id, slot, item_id, quantity, durability
            )
            return

        key = EQUIPMENT_KEY.format(player_id=player_id)

        # Get current equipment
        equipment = await self._get_from_valkey(key) or {}

        # Update slot
        equipment[slot] = {
            "item_id": item_id,
            "quantity": quantity,
            "current_durability": durability,
        }

        await self._cache_in_valkey(key, equipment, TIER2_TTL)
        await self._valkey.sadd(DIRTY_EQUIPMENT_KEY, [str(player_id)])

    async def _update_equipment_slot_in_db(
        self, player_id: int, slot: str, item_id: int, quantity: int, durability: float
    ) -> None:
        if not self._session_factory:
            return

        from server.src.models.item import PlayerEquipment
        from sqlalchemy.dialects.postgresql import insert

        async with self._db_session() as db:
            # Upsert equipment slot
            stmt = insert(PlayerEquipment).values(
                player_id=player_id,
                equipment_slot=slot,
                item_id=item_id,
                quantity=quantity,
                current_durability=durability,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["player_id", "equipment_slot"],
                set_={
                    "item_id": item_id,
                    "quantity": quantity,
                    "current_durability": durability,
                },
            )
            await db.execute(stmt)
            await self._commit_if_not_test_session(db)

    async def delete_equipment_slot(self, player_id: int, slot: str) -> None:
        """Remove item from specific equipment slot."""
        if not settings.USE_VALKEY or not self._valkey:
            await self._delete_equipment_slot_from_db(player_id, slot)
            return

        key = EQUIPMENT_KEY.format(player_id=player_id)

        # Delete the field from the hash
        await self._valkey.hdel(key, [slot])
        await self._valkey.sadd(DIRTY_EQUIPMENT_KEY, [str(player_id)])

    async def _delete_equipment_slot_from_db(self, player_id: int, slot: str) -> None:
        if not self._session_factory:
            return

        from server.src.models.item import PlayerEquipment

        async with self._db_session() as db:
            await db.execute(
                delete(PlayerEquipment).where(
                    PlayerEquipment.player_id == player_id,
                    PlayerEquipment.equipment_slot == slot,
                )
            )
            await self._commit_if_not_test_session(db)

    async def clear_equipment(self, player_id: int) -> None:
        """Remove all equipped items."""
        if not settings.USE_VALKEY or not self._valkey:
            await self._clear_equipment_from_db(player_id)
            return

        key = EQUIPMENT_KEY.format(player_id=player_id)
        await self._delete_from_valkey(key)
        await self._valkey.sadd(DIRTY_EQUIPMENT_KEY, [str(player_id)])

    async def _clear_equipment_from_db(self, player_id: int) -> None:
        if not self._session_factory:
            return

        from server.src.models.item import PlayerEquipment

        async with self._db_session() as db:
            await db.execute(
                delete(PlayerEquipment).where(PlayerEquipment.player_id == player_id)
            )
            await self._commit_if_not_test_session(db)

    # =========================================================================
    # Batch Sync Support
    # =========================================================================

    async def get_dirty_equipment(self) -> list[int]:
        if not self._valkey:
            return []

        dirty = await self._valkey.smembers(DIRTY_EQUIPMENT_KEY)
        return [int(self._decode_bytes(d)) for d in dirty]

    async def clear_dirty_equipment(self, player_id: int) -> None:
        if self._valkey:
            await self._valkey.srem(DIRTY_EQUIPMENT_KEY, [str(player_id)])

    async def sync_equipment_to_db(self, player_id: int, db) -> None:
        if not self._valkey:
            return

        from server.src.models.item import PlayerEquipment
        from sqlalchemy.dialects.postgresql import insert

        key = EQUIPMENT_KEY.format(player_id=player_id)
        equipment = await self._get_from_valkey(key)

        if equipment is None:
            return

        # Delete existing equipment
        await db.execute(
            delete(PlayerEquipment).where(PlayerEquipment.player_id == player_id)
        )

        # Insert current state
        for slot, item_data in equipment.items():
            item_id = self._decode_from_valkey(item_data.get("item_id"), int)
            quantity = self._decode_from_valkey(item_data.get("quantity"), int)
            durability = self._decode_from_valkey(
                item_data.get("current_durability"), float
            )

            if item_id and slot:
                stmt = insert(PlayerEquipment).values(
                    player_id=player_id,
                    equipment_slot=slot,
                    item_id=item_id,
                    quantity=quantity or 1,
                    current_durability=durability or 1.0,
                )
                await db.execute(stmt)


# Singleton instance
_equipment_manager: Optional[EquipmentManager] = None


def init_equipment_manager(
    valkey_client: Optional[GlideClient] = None,
    session_factory: Optional[sessionmaker] = None,
) -> EquipmentManager:
    global _equipment_manager
    _equipment_manager = EquipmentManager(valkey_client, session_factory)
    return _equipment_manager


def get_equipment_manager() -> EquipmentManager:
    if _equipment_manager is None:
        raise RuntimeError("EquipmentManager not initialized")
    return _equipment_manager


def reset_equipment_manager() -> None:
    global _equipment_manager
    _equipment_manager = None
