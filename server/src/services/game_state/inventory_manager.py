"""
Inventory management - Tier 2 data with auto-loading.

Pure persistence layer: CRUD operations only, no business logic.
Stacking, slot allocation, and validation handled by InventoryService.
"""

import traceback
from typing import Any, Dict, List, Optional

from glide import GlideClient
from sqlalchemy import select, delete
from sqlalchemy.orm import sessionmaker

from server.src.core.config import settings
from server.src.core.logging_config import get_logger

from .base_manager import BaseManager, TIER2_TTL

logger = get_logger(__name__)

INVENTORY_KEY = "inventory:{player_id}"
DIRTY_INVENTORY_KEY = "dirty:inventory"


class InventoryManager(BaseManager):
    """Manages player inventory persistence with transparent auto-loading."""

    def __init__(
        self,
        valkey_client: Optional[GlideClient] = None,
        session_factory: Optional[sessionmaker] = None,
    ):
        super().__init__(valkey_client, session_factory)

    # =========================================================================
    # Inventory CRUD
    # =========================================================================

    async def get_inventory(self, player_id: int) -> Dict[int, Dict[str, Any]]:
        """Get entire inventory with transparent auto-loading from DB."""
        if not settings.USE_VALKEY or not self._valkey:
            return await self._load_inventory_from_db(player_id)

        key = INVENTORY_KEY.format(player_id=player_id)

        async def load_from_db():
            return await self._load_inventory_from_db(player_id)

        inventory = await self.auto_load_with_ttl(key, load_from_db, TIER2_TTL)
        return inventory or {}

    async def _load_inventory_from_db(self, player_id: int) -> Dict[int, Dict[str, Any]]:
        if not self._session_factory:
            return {}

        from server.src.models.item import PlayerInventory

        async with self._db_session() as db:
            result = await db.execute(
                select(PlayerInventory).where(PlayerInventory.player_id == player_id)
            )
            inventories = result.scalars().all()

            inventory_data = {}
            for inv in inventories:
                inventory_data[inv.slot] = {
                    "item_id": inv.item_id,
                    "quantity": inv.quantity,
                    "current_durability": inv.current_durability or 1.0,
                }

            return inventory_data

    async def get_inventory_slot(self, player_id: int, slot: int) -> Optional[Dict[str, Any]]:
        """Get specific slot contents."""
        inventory = await self.get_inventory(player_id)
        return inventory.get(str(slot))

    async def set_inventory_slot(
        self, player_id: int, slot: int, item_id: int, quantity: int, durability: float = 1.0
    ) -> None:
        """Set item in specific slot."""
        if not settings.USE_VALKEY or not self._valkey:
            await self._update_slot_in_db(player_id, slot, item_id, quantity, durability)
            return

        key = INVENTORY_KEY.format(player_id=player_id)

        # Get current inventory
        inventory = await self._get_from_valkey(key) or {}

        # Update slot
        slot_str = str(slot)
        inventory[slot_str] = {
            "item_id": item_id,
            "quantity": quantity,
            "current_durability": durability,
        }

        await self._cache_in_valkey(key, inventory, TIER2_TTL)
        await self._valkey.sadd(DIRTY_INVENTORY_KEY, [str(player_id)])

    async def _update_slot_in_db(
        self, player_id: int, slot: int, item_id: int, quantity: int, durability: float
    ) -> None:
        if not self._session_factory:
            return

        from server.src.models.item import PlayerInventory
        from sqlalchemy.dialects.postgresql import insert

        async with self._db_session() as db:
            # Delete existing item in slot
            await db.execute(
                delete(PlayerInventory).where(
                    PlayerInventory.player_id == player_id,
                    PlayerInventory.slot == slot,
                )
            )

            # Insert new item
            new_inv = PlayerInventory(
                player_id=player_id,
                item_id=item_id,
                slot=slot,
                quantity=quantity,
                current_durability=durability,
            )
            db.add(new_inv)
            await self._commit_if_not_test_session(db)

    async def delete_inventory_slot(self, player_id: int, slot: int) -> None:
        """Remove item from specific slot."""
        if not settings.USE_VALKEY or not self._valkey:
            await self._delete_slot_from_db(player_id, slot)
            return

        key = INVENTORY_KEY.format(player_id=player_id)
        slot_str = str(slot)

        # Delete the field from the hash
        await self._valkey.hdel(key, [slot_str])
        await self._valkey.sadd(DIRTY_INVENTORY_KEY, [str(player_id)])

    async def _delete_slot_from_db(self, player_id: int, slot: int) -> None:
        if not self._session_factory:
            return

        from server.src.models.item import PlayerInventory

        async with self._db_session() as db:
            await db.execute(
                delete(PlayerInventory).where(
                    PlayerInventory.player_id == player_id,
                    PlayerInventory.slot == slot,
                )
            )
            await self._commit_if_not_test_session(db)

    async def clear_inventory(self, player_id: int) -> None:
        """Remove all items from inventory."""
        if not settings.USE_VALKEY or not self._valkey:
            await self._clear_inventory_from_db(player_id)
            return

        key = INVENTORY_KEY.format(player_id=player_id)
        await self._delete_from_valkey(key)
        await self._valkey.sadd(DIRTY_INVENTORY_KEY, [str(player_id)])

    async def _clear_inventory_from_db(self, player_id: int) -> None:
        if not self._session_factory:
            return

        from server.src.models.item import PlayerInventory

        async with self._db_session() as db:
            await db.execute(
                delete(PlayerInventory).where(PlayerInventory.player_id == player_id)
            )
            await self._commit_if_not_test_session(db)

    # =========================================================================
    # Batch Sync Support
    # =========================================================================

    async def get_dirty_inventories(self) -> List[int]:
        if not self._valkey:
            return []

        dirty = await self._valkey.smembers(DIRTY_INVENTORY_KEY)
        return [int(self._decode_bytes(d)) for d in dirty]

    async def clear_dirty_inventory(self, player_id: int) -> None:
        if self._valkey:
            await self._valkey.srem(DIRTY_INVENTORY_KEY, [str(player_id)])

    async def sync_inventory_to_db(self, player_id: int, db) -> None:
        if not self._valkey:
            return

        from server.src.models.item import PlayerInventory
        from sqlalchemy.dialects.postgresql import insert

        key = INVENTORY_KEY.format(player_id=player_id)
        inventory = await self._get_from_valkey(key)

        if inventory is None:
            return

        # Delete existing inventory
        await db.execute(
            delete(PlayerInventory).where(PlayerInventory.player_id == player_id)
        )

        # Get reference data manager for item validation
        from .reference_data_manager import get_reference_data_manager
        ref_mgr = get_reference_data_manager()

        # Insert current state, skipping items with stale item_ids
        for slot_str, item_data in inventory.items():
            slot = int(slot_str)
            item_id = self._decode_from_valkey(item_data.get("item_id"), int)
            quantity = self._decode_from_valkey(item_data.get("quantity"), int)
            durability = self._decode_from_valkey(
                item_data.get("current_durability"), float
            )

            if item_id and quantity:
                # Validate item_id exists in reference data to prevent FK violations
                if not ref_mgr.get_item_by_id(item_id):
                    logger.warning(
                        "Skipping stale inventory item",
                        extra={
                            "player_id": player_id,
                            "item_id": item_id,
                            "slot": slot,
                        },
                    )
                    continue

                new_inv = PlayerInventory(
                    player_id=player_id,
                    item_id=item_id,
                    slot=slot,
                    quantity=quantity,
                    current_durability=durability or 1.0,
                )
                db.add(new_inv)


# Singleton instance
_inventory_manager: Optional[InventoryManager] = None


def init_inventory_manager(
    valkey_client: Optional[GlideClient] = None,
    session_factory: Optional[sessionmaker] = None,
) -> InventoryManager:
    global _inventory_manager
    _inventory_manager = InventoryManager(valkey_client, session_factory)
    return _inventory_manager


def get_inventory_manager() -> InventoryManager:
    if _inventory_manager is None:
        raise RuntimeError("InventoryManager not initialized")
    return _inventory_manager


def reset_inventory_manager() -> None:
    global _inventory_manager
    _inventory_manager = None
