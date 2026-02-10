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
                # Collect dirty items first
                dirty_positions = await self._player.get_dirty_positions()
                dirty_inventories = await self._inventory.get_dirty_inventories()
                dirty_equipment = await self._equipment.get_dirty_equipment()
                dirty_skills = await self._skills.get_dirty_skills()

                # Sync positions
                for player_id in dirty_positions:
                    await self._player.sync_player_position_to_db(player_id, db)
                    stats["positions"] += 1

                # Sync inventories
                for player_id in dirty_inventories:
                    await self._inventory.sync_inventory_to_db(player_id, db)
                    stats["inventories"] += 1

                # Sync equipment
                for player_id in dirty_equipment:
                    await self._equipment.sync_equipment_to_db(player_id, db)
                    stats["equipment"] += 1

                # Sync skills
                for player_id in dirty_skills:
                    await self._skills.sync_skills_to_db(player_id, db)
                    stats["skills"] += 1

                # Sync ground items
                await self._ground_items.sync_ground_items_to_db(db)

                # Commit first, then clear dirty flags
                await db.commit()

                # Only clear dirty flags after successful commit
                for player_id in dirty_positions:
                    await self._player.clear_dirty_position(player_id)
                for player_id in dirty_inventories:
                    await self._inventory.clear_dirty_inventory(player_id)
                for player_id in dirty_equipment:
                    await self._equipment.clear_dirty_equipment(player_id)
                for player_id in dirty_skills:
                    await self._skills.clear_dirty_skills(player_id)

                logger.debug("Batch sync completed", extra={"stats": stats})
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

                # Commit first, then clear dirty flags
                await db.commit()

                # Only clear dirty flags after successful commit
                for player_id in online_players:
                    await self._player.clear_dirty_position(player_id)
                    await self._inventory.clear_dirty_inventory(player_id)
                    await self._equipment.clear_dirty_equipment(player_id)
                    await self._skills.clear_dirty_skills(player_id)

                logger.info(
                    "Shutdown sync completed",
                    extra={"player_count": stats["players"]}
                )
                return stats

        except Exception as e:
            logger.error(
                "Shutdown sync failed",
                extra={"error": str(e), "traceback": traceback.format_exc()},
            )
            raise

    async def sync_single_player(self, player_id: int, db) -> Dict[str, Any]:
        """
        Sync all data for a single player to database immediately.
        
        Used for logout, periodic saves, or manual admin saves.
        This method does NOT commit the transaction - caller is responsible for that.
        
        Args:
            player_id: Player ID to sync
            db: Database session (provided by caller)
            
        Returns:
            Dict with sync results and any errors
        """
        results = {
            "success": True,
            "errors": [],
            "synced": {"position": False, "inventory": False, "equipment": False, "skills": False}
        }
        
        # Track if we need to clear dirty flags (only on success)
        synced_position = False
        synced_inventory = False
        synced_equipment = False
        synced_skills = False
        
        # Sync position
        try:
            await self._player.sync_player_position_to_db(player_id, db)
            results["synced"]["position"] = True
            synced_position = True
        except Exception as e:
            results["success"] = False
            results["errors"].append(f"Position sync failed: {str(e)}")
            logger.error("Position sync failed", extra={"player_id": player_id, "error": str(e)})
        
        # Sync inventory
        try:
            await self._inventory.sync_inventory_to_db(player_id, db)
            results["synced"]["inventory"] = True
            synced_inventory = True
        except Exception as e:
            results["success"] = False
            results["errors"].append(f"Inventory sync failed: {str(e)}")
            logger.error("Inventory sync failed", extra={"player_id": player_id, "error": str(e)})
        
        # Sync equipment
        try:
            await self._equipment.sync_equipment_to_db(player_id, db)
            results["synced"]["equipment"] = True
            synced_equipment = True
        except Exception as e:
            results["success"] = False
            results["errors"].append(f"Equipment sync failed: {str(e)}")
            logger.error("Equipment sync failed", extra={"player_id": player_id, "error": str(e)})
        
        # Sync skills
        try:
            await self._skills.sync_skills_to_db(player_id, db)
            results["synced"]["skills"] = True
            synced_skills = True
        except Exception as e:
            results["success"] = False
            results["errors"].append(f"Skills sync failed: {str(e)}")
            logger.error("Skills sync failed", extra={"player_id": player_id, "error": str(e)})
        
        # Only clear dirty flags if all syncs were successful
        if results["success"]:
            if synced_position:
                await self._player.clear_dirty_position(player_id)
            if synced_inventory:
                await self._inventory.clear_dirty_inventory(player_id)
            if synced_equipment:
                await self._equipment.clear_dirty_equipment(player_id)
            if synced_skills:
                await self._skills.clear_dirty_skills(player_id)
            logger.debug("Successfully synced all data for player", extra={"player_id": player_id})
        else:
            logger.warning(
                "Partial sync for player",
                extra={"player_id": player_id, "synced": results["synced"], "errors": results["errors"]}
            )
        
        return results

    async def sync_and_commit_player(self, player_id: int) -> Dict[str, Any]:
        """
        Sync all data for a single player to database with internal session management.
        
        This method manages its own database session, making it suitable for use
        from service layer without violating GSM architecture. Commits are handled
        internally.
        
        Args:
            player_id: Player ID to sync
            
        Returns:
            Dict with sync results and any errors
        """
        if not self._session_factory:
            logger.warning("No session factory available for sync")
            return {"success": False, "errors": ["No database connection"], "synced": {}}
        
        try:
            async with self._session_factory() as db:
                results = await self.sync_single_player(player_id, db)
                await db.commit()
                return results
        except Exception as e:
            logger.error(
                "Failed to sync and commit player",
                extra={"player_id": player_id, "error": str(e), "traceback": traceback.format_exc()}
            )
            return {"success": False, "errors": [f"Commit failed: {str(e)}"], "synced": {}}


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
