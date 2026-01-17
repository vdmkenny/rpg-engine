"""
Batch synchronization service for persisting Valkey state to PostgreSQL.

Syncs are organized by data type for efficient bulk SQL operations.
This service is called:
1. Periodically from the game loop (every DB_SYNC_INTERVAL_TICKS)
2. On player disconnect (for that player only)
3. On server shutdown (for all remaining data)
"""

from typing import Dict, Optional

from glide import GlideClient
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from server.src.core.logging_config import get_logger
from server.src.models.item import PlayerEquipment, PlayerInventory, GroundItem
from server.src.models.player import Player
from server.src.models.skill import PlayerSkill
from server.src.services.ground_item_valkey_service import GroundItemValkeyService
from server.src.services.player_state_valkey_service import (
    DIRTY_EQUIPMENT_KEY,
    DIRTY_GROUND_ITEMS_KEY,
    DIRTY_INVENTORY_KEY,
    DIRTY_SKILLS_KEY,
    PlayerStateValkeyService,
)

logger = get_logger(__name__)


class BatchSyncService:
    """Service for batch-syncing Valkey state to PostgreSQL."""

    @staticmethod
    async def sync_all(valkey: GlideClient, db: AsyncSession) -> Dict[str, int]:
        """
        Run all batch syncs sequentially by data type.

        This is the main entry point for periodic syncs from the game loop.

        Args:
            valkey: Valkey client
            db: Database session

        Returns:
            Dict with count of synced items per type
        """
        results = {}

        results["inventories"] = await BatchSyncService.sync_inventories(valkey, db)
        results["equipment"] = await BatchSyncService.sync_equipment(valkey, db)
        results["skills"] = await BatchSyncService.sync_skills(valkey, db)
        results["ground_items"] = await BatchSyncService.sync_ground_items(valkey, db)

        total = sum(results.values())
        if total > 0:
            logger.info(
                "Batch sync completed", extra={"results": results, "total": total}
            )

        return results

    @staticmethod
    async def sync_inventories(valkey: GlideClient, db: AsyncSession) -> int:
        """
        Sync all dirty inventories using bulk delete + insert.

        For each dirty player:
        1. Delete all existing inventory rows for that player
        2. Insert all current inventory rows from Valkey

        Args:
            valkey: Valkey client
            db: Database session

        Returns:
            Number of players synced
        """
        dirty_ids = await PlayerStateValkeyService.get_dirty_set(
            valkey, DIRTY_INVENTORY_KEY
        )

        if not dirty_ids:
            return 0

        all_inventory_rows = []

        for player_id_str in dirty_ids:
            player_id = int(player_id_str)
            inventory = await PlayerStateValkeyService.get_inventory(valkey, player_id)

            # Delete existing inventory for this player
            await db.execute(
                delete(PlayerInventory).where(PlayerInventory.player_id == player_id)
            )

            # Prepare rows for bulk insert
            for slot, data in inventory.items():
                all_inventory_rows.append(
                    {
                        "player_id": player_id,
                        "slot": slot,
                        "item_id": data["item_id"],
                        "quantity": data["quantity"],
                        "current_durability": data.get("durability"),
                    }
                )

        # Bulk insert all inventory rows
        if all_inventory_rows:
            await db.execute(pg_insert(PlayerInventory).values(all_inventory_rows))

        await db.commit()
        await PlayerStateValkeyService.clear_dirty_set(valkey, DIRTY_INVENTORY_KEY)

        logger.debug(
            "Synced inventories",
            extra={"players": len(dirty_ids), "rows": len(all_inventory_rows)},
        )
        return len(dirty_ids)

    @staticmethod
    async def sync_equipment(valkey: GlideClient, db: AsyncSession) -> int:
        """
        Sync all dirty equipment using bulk delete + insert.

        For each dirty player:
        1. Delete all existing equipment rows for that player
        2. Insert all current equipment rows from Valkey

        Args:
            valkey: Valkey client
            db: Database session

        Returns:
            Number of players synced
        """
        dirty_ids = await PlayerStateValkeyService.get_dirty_set(
            valkey, DIRTY_EQUIPMENT_KEY
        )

        if not dirty_ids:
            return 0

        all_equipment_rows = []

        for player_id_str in dirty_ids:
            player_id = int(player_id_str)
            equipment = await PlayerStateValkeyService.get_equipment(valkey, player_id)

            # Delete existing equipment for this player
            await db.execute(
                delete(PlayerEquipment).where(PlayerEquipment.player_id == player_id)
            )

            # Prepare rows for bulk insert
            for slot, data in equipment.items():
                all_equipment_rows.append(
                    {
                        "player_id": player_id,
                        "equipment_slot": slot,
                        "item_id": data["item_id"],
                        "quantity": data["quantity"],
                        "current_durability": data.get("durability"),
                    }
                )

        # Bulk insert all equipment rows
        if all_equipment_rows:
            await db.execute(pg_insert(PlayerEquipment).values(all_equipment_rows))

        await db.commit()
        await PlayerStateValkeyService.clear_dirty_set(valkey, DIRTY_EQUIPMENT_KEY)

        logger.debug(
            "Synced equipment",
            extra={"players": len(dirty_ids), "rows": len(all_equipment_rows)},
        )
        return len(dirty_ids)

    @staticmethod
    async def sync_skills(valkey: GlideClient, db: AsyncSession) -> int:
        """
        Sync all dirty skills using individual updates.

        Skills use update rather than delete+insert because:
        1. Skills are never added/removed during gameplay (only XP/level changes)
        2. Updates are more efficient for this pattern

        Args:
            valkey: Valkey client
            db: Database session

        Returns:
            Number of players synced
        """
        dirty_ids = await PlayerStateValkeyService.get_dirty_set(
            valkey, DIRTY_SKILLS_KEY
        )

        if not dirty_ids:
            return 0

        for player_id_str in dirty_ids:
            player_id = int(player_id_str)
            skills = await PlayerStateValkeyService.get_all_skills(valkey, player_id)

            for skill_name, data in skills.items():
                # Update using skill_id
                result = await db.execute(
                    select(PlayerSkill).where(
                        PlayerSkill.player_id == player_id,
                        PlayerSkill.skill_id == data["skill_id"],
                    )
                )
                player_skill = result.scalar_one_or_none()

                if player_skill:
                    player_skill.current_level = data["level"]
                    player_skill.experience = data["experience"]

        await db.commit()
        await PlayerStateValkeyService.clear_dirty_set(valkey, DIRTY_SKILLS_KEY)

        logger.debug("Synced skills", extra={"players": len(dirty_ids)})
        return len(dirty_ids)

    @staticmethod
    async def sync_ground_items(valkey: GlideClient, db: AsyncSession) -> int:
        """
        Sync all dirty maps' ground items.

        For each dirty map:
        1. Get all items from Valkey for that map
        2. Get all items from DB for that map
        3. Delete items from DB that are no longer in Valkey (picked up)
        4. Update quantities for items still in Valkey

        Note: New ground items are still created in DB immediately when dropped,
        so we don't need to insert here - only update and delete.

        Args:
            valkey: Valkey client
            db: Database session

        Returns:
            Number of maps synced
        """
        dirty_maps = await PlayerStateValkeyService.get_dirty_set(
            valkey, DIRTY_GROUND_ITEMS_KEY
        )

        if not dirty_maps:
            return 0

        synced_maps = 0

        for map_id in dirty_maps:
            # Get all items from Valkey for this map
            valkey_items = await GroundItemValkeyService.get_ground_items_on_map(
                valkey, map_id
            )
            valkey_ids = {item["id"] for item in valkey_items}

            # Get all items from DB for this map
            result = await db.execute(
                select(GroundItem).where(GroundItem.map_id == map_id)
            )
            db_items = list(result.scalars().all())

            # Remove items from DB that are no longer in Valkey (picked up)
            for db_item in db_items:
                if db_item.id not in valkey_ids:
                    await db.delete(db_item)

            # Update quantities for items still in Valkey
            valkey_by_id = {item["id"]: item for item in valkey_items}
            for db_item in db_items:
                if db_item.id in valkey_by_id:
                    v_item = valkey_by_id[db_item.id]
                    if db_item.quantity != v_item["quantity"]:
                        db_item.quantity = v_item["quantity"]

            synced_maps += 1

        await db.commit()
        await PlayerStateValkeyService.clear_dirty_set(valkey, DIRTY_GROUND_ITEMS_KEY)

        logger.debug("Synced ground items", extra={"maps": synced_maps})
        return synced_maps

    @staticmethod
    async def sync_single_player(
        valkey: GlideClient,
        db: AsyncSession,
        player_id: int,
        username: str,
    ) -> None:
        """
        Sync a single player's complete state on disconnect.

        This is called when a player disconnects to ensure their data is persisted
        immediately rather than waiting for the next batch sync.

        Args:
            valkey: Valkey client
            db: Database session
            player_id: Player's database ID
            username: Player's username (for position key lookup)
        """
        # Sync position/HP from the existing player:{username} key
        player_key = f"player:{username}"
        player_data_raw = await valkey.hgetall(player_key)

        if player_data_raw:
            player_data = {
                k.decode() if isinstance(k, bytes) else k: v.decode()
                if isinstance(v, bytes)
                else v
                for k, v in player_data_raw.items()
            }

            result = await db.execute(
                select(Player).where(Player.username == username)
            )
            player = result.scalar_one_or_none()

            if player:
                player.x_coord = int(player_data.get("x", 0))
                player.y_coord = int(player_data.get("y", 0))
                player.map_id = player_data.get("map_id", "samplemap")
                player.current_hp = int(player_data.get("current_hp", 10))

        # Sync inventory
        inventory = await PlayerStateValkeyService.get_inventory(valkey, player_id)
        await db.execute(
            delete(PlayerInventory).where(PlayerInventory.player_id == player_id)
        )

        for slot, data in inventory.items():
            inv = PlayerInventory(
                player_id=player_id,
                slot=slot,
                item_id=data["item_id"],
                quantity=data["quantity"],
                current_durability=data.get("durability"),
            )
            db.add(inv)

        # Sync equipment
        equipment = await PlayerStateValkeyService.get_equipment(valkey, player_id)
        await db.execute(
            delete(PlayerEquipment).where(PlayerEquipment.player_id == player_id)
        )

        for slot, data in equipment.items():
            eq = PlayerEquipment(
                player_id=player_id,
                equipment_slot=slot,
                item_id=data["item_id"],
                quantity=data["quantity"],
                current_durability=data.get("durability"),
            )
            db.add(eq)

        # Sync skills
        skills = await PlayerStateValkeyService.get_all_skills(valkey, player_id)
        for skill_name, data in skills.items():
            result = await db.execute(
                select(PlayerSkill).where(
                    PlayerSkill.player_id == player_id,
                    PlayerSkill.skill_id == data["skill_id"],
                )
            )
            player_skill = result.scalar_one_or_none()
            if player_skill:
                player_skill.current_level = data["level"]
                player_skill.experience = data["experience"]

        await db.commit()

        # Clean up player's Valkey state and remove from dirty sets
        await PlayerStateValkeyService.delete_player_state(valkey, player_id)

        logger.info(
            "Synced player on disconnect",
            extra={"player_id": player_id, "username": username},
        )

    @staticmethod
    async def sync_all_players_on_shutdown(
        valkey: GlideClient,
        db: AsyncSession,
        active_players: Dict[str, int],
    ) -> int:
        """
        Force sync all active players on server shutdown.

        This is called during server shutdown to ensure all player data is
        persisted before the server stops.

        Args:
            valkey: Valkey client
            db: Database session
            active_players: Dict mapping username to player_id for all online players

        Returns:
            Number of players synced
        """
        synced = 0

        for username, player_id in active_players.items():
            try:
                await BatchSyncService.sync_single_player(
                    valkey, db, player_id, username
                )
                synced += 1
            except Exception as e:
                logger.error(
                    "Failed to sync player on shutdown",
                    extra={
                        "player_id": player_id,
                        "username": username,
                        "error": str(e),
                    },
                )

        logger.info("Shutdown player sync completed", extra={"players_synced": synced})
        return synced
