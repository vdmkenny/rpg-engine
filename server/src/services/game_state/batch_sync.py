"""
Batch synchronization coordinator.

Handles periodic syncing of dirty player data from Valkey to PostgreSQL.
Coordinates between all managers for efficient batch operations.
"""

import traceback
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from server.src.core.config import settings
from server.src.core.logging_config import get_logger

from .player_state_manager import PlayerStateManager
from .inventory_manager import InventoryManager
from .equipment_manager import EquipmentManager
from .skills_manager import SkillsManager
from .ground_item_manager import GroundItemManager

logger = get_logger(__name__)


class BatchSyncCoordinator:
    """Coordinates batch sync operations across all managers."""

    def __init__(
        self,
        player_manager: PlayerStateManager,
        inventory_manager: InventoryManager,
        equipment_manager: EquipmentManager,
        skills_manager: SkillsManager,
        ground_item_manager: GroundItemManager,
        session_factory: Optional[sessionmaker] = None,
    ):
        self._player = player_manager
        self._inventory = inventory_manager
        self._equipment = equipment_manager
        self._skills = skills_manager
        self._ground_items = ground_item_manager
        self._session_factory = session_factory

    async def sync_all(self) -> Dict[str, int]:
        """Sync all dirty data to database. Returns counts of synced items."""
        if not self._session_factory:
            return {}

        stats = {"positions": 0, "inventories": 0, "equipment": 0, "skills": 0}

        try:
            from sqlalchemy.ext.asyncio import AsyncSession

            async with self._session_factory() as db:
                # Sync positions
                dirty_positions = await self._player.get_dirty_positions()
                for player_id in dirty_positions:
                    await self._player.sync_player_position_to_db(player_id, db)
                    await self._player.clear_dirty_position(player_id)
                    stats["positions"] += 1

                # Sync inventories
                dirty_inventories = await self._inventory.get_dirty_inventories()
                for player_id in dirty_inventories:
                    await self._inventory.sync_inventory_to_db(player_id, db)
                    await self._inventory.clear_dirty_inventory(player_id)
                    stats["inventories"] += 1

                # Sync equipment
                dirty_equipment = await self._equipment.get_dirty_equipment()
                for player_id in dirty_equipment:
                    await self._equipment.sync_equipment_to_db(player_id, db)
                    await self._equipment.clear_dirty_equipment(player_id)
                    stats["equipment"] += 1

                # Sync skills
                dirty_skills = await self._skills.get_dirty_skills()
                for player_id in dirty_skills:
                    await self._skills.sync_skills_to_db(player_id, db)
                    await self._skills.clear_dirty_skills(player_id)
                    stats["skills"] += 1

                # Sync ground items
                await self._ground_items.sync_ground_items_to_db(db)

                await db.commit()

                logger.debug(f"Batch sync completed: {stats}")
                return stats

        except Exception as e:
            logger.error(
                "Batch sync failed",
                extra={"error": str(e), "traceback": traceback.format_exc()},
            )
            raise

    async def sync_all_on_shutdown(self) -> Dict[str, int]:
        """Sync all online player data before server shutdown."""
        if not self._session_factory:
            return {}

        stats = {"players": 0}

        try:
            online_players = await self._player.get_all_online_player_ids()

            async with self._session_factory() as db:
                for player_id in online_players:
                    # Sync all data types for each player
                    await self._player.sync_player_position_to_db(player_id, db)
                    await self._inventory.sync_inventory_to_db(player_id, db)
                    await self._equipment.sync_equipment_to_db(player_id, db)
                    await self._skills.sync_skills_to_db(player_id, db)
                    stats["players"] += 1

                # Sync ground items
                await self._ground_items.sync_ground_items_to_db(db)

                await db.commit()

                logger.info(f"Shutdown sync completed for {stats['players']} players")
                return stats

        except Exception as e:
            logger.error(
                "Shutdown sync failed",
                extra={"error": str(e), "traceback": traceback.format_exc()},
            )
            raise


# Singleton instance
def get_batch_sync_coordinator() -> BatchSyncCoordinator:
    """Get the batch sync coordinator instance.
    
    The coordinator is initialized by init_all_managers() in the parent module.
    This function imports from the parent module to get the actual instance.
    """
    # Import here to avoid circular imports
    from server.src.services.game_state import _batch_sync_coordinator
    if _batch_sync_coordinator is None:
        raise RuntimeError("BatchSyncCoordinator not initialized - call init_all_managers() first")
    return _batch_sync_coordinator
