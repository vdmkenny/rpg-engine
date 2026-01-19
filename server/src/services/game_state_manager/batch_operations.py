"""
GameStateManager Batch Operations Helper

Handles batch sync operations, multi-player operations, and cleanup tasks.
Keeps batch logic separate from core state management.
"""

from typing import Any, Dict, List, Optional, Set
from contextlib import asynccontextmanager
from glide import GlideClient
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from server.src.core.logging_config import get_logger

logger = get_logger(__name__)


class GSMBatchOps:
    """Helper class for batch operations and cleanup tasks."""
    
    def __init__(self, gsm):
        """Initialize with reference to main GameStateManager."""
        self._gsm = gsm
    
    @property
    def valkey(self) -> Optional[GlideClient]:
        """Get Valkey client from main GSM."""
        return self._gsm.valkey
    
    async def sync_all(self) -> None:
        """
        Sync all dirty player data to PostgreSQL.
        Called periodically by the game loop.
        """
        if not self._gsm._session_factory:
            logger.warning("GSM not fully initialized, skipping batch sync")
            return
            
        try:
            # Sync each data type independently
            await self._sync_player_positions()
            await self._sync_inventories()
            await self._sync_equipment()
            await self._sync_skills()
            await self._sync_ground_items()
            
            logger.debug("Batch sync completed successfully")
            
        except Exception as e:
            logger.error("Batch sync failed", extra={"error": str(e)})
            raise
    
    async def sync_all_on_shutdown(self) -> None:
        """
        Sync all online player data before server shutdown.
        Ensures no data loss during graceful shutdown.
        """
        if not self.valkey or not self._gsm._session_factory:
            return
            
        logger.info("Starting shutdown sync for all online players")
        
        try:
            online_players = self._gsm.get_online_player_ids()
            
            async with self._gsm._db_session() as db:
                for player_id in online_players:
                    await self._sync_single_player_to_db(db, player_id)
                await db.commit()
            
            logger.info(
                "Shutdown sync completed",
                extra={"synced_players": len(online_players)}
            )
            
        except Exception as e:
            logger.error("Shutdown sync failed", extra={"error": str(e)})
            raise
    
    async def _sync_player_positions(self) -> None:
        """Sync dirty player positions to database."""
        if not self.valkey:
            return
            
        try:
            # Get all dirty player positions
            dirty_players_raw = await self.valkey.smembers("dirty:position")
            if not dirty_players_raw:
                return
                
            dirty_players = [int(p.decode() if isinstance(p, bytes) else p) for p in dirty_players_raw]
            
            async with self._gsm._db_session() as db:
                # Import here to avoid circular imports
                from server.src.models.player import Player
                
                for player_id in dirty_players:
                    position_data = await self._gsm.get_player_position(player_id)
                    hp_data = await self._gsm.get_player_hp(player_id)
                    
                    if position_data and hp_data:
                        # Update player position and HP in database
                        await db.execute(
                            select(Player).where(Player.id == player_id)
                        )
                        
                        stmt = (
                            select(Player)
                            .where(Player.id == player_id)
                        )
                        result = await db.execute(stmt)
                        player = result.scalar_one_or_none()
                        
                        if player:
                            player.x_coord = position_data["x"]
                            player.y_coord = position_data["y"] 
                            player.map_id = position_data["map_id"]
                            player.current_hp = hp_data["current_hp"]
                
                await db.commit()
                
                # Clear dirty tracking
                await self.valkey.delete(["dirty:position"])
                
            logger.debug(
                "Synced player positions",
                extra={"count": len(dirty_players)}
            )
            
        except Exception as e:
            logger.error("Failed to sync player positions", extra={"error": str(e)})
            raise
    
    async def _sync_inventories(self) -> None:
        """Sync dirty inventories to database."""
        if not self.valkey:
            return
            
        try:
            dirty_players_raw = await self.valkey.smembers("dirty:inventory")
            if not dirty_players_raw:
                return
                
            dirty_players = [int(p.decode() if isinstance(p, bytes) else p) for p in dirty_players_raw]
            
            async with self._gsm._db_session() as db:
                from server.src.models.item import PlayerInventory
                
                # Delete existing inventory data for dirty players
                await db.execute(
                    delete(PlayerInventory).where(PlayerInventory.player_id.in_(dirty_players))
                )
                
                # Insert fresh inventory data
                inventory_records = []
                for player_id in dirty_players:
                    inventory = await self._gsm.get_inventory(player_id)
                    for slot, item_data in inventory.items():
                        inventory_records.append({
                            "player_id": player_id,
                            "slot": slot,
                            "item_id": item_data["item_id"],
                            "quantity": item_data["quantity"], 
                            "current_durability": item_data["durability"]
                        })
                
                if inventory_records:
                    await db.execute(
                        pg_insert(PlayerInventory).values(inventory_records)
                    )
                
                await db.commit()
                await self.valkey.delete(["dirty:inventory"])
                
            logger.debug(
                "Synced inventories",
                extra={"players": len(dirty_players), "items": len(inventory_records)}
            )
            
        except Exception as e:
            logger.error("Failed to sync inventories", extra={"error": str(e)})
            raise
    
    async def _sync_equipment(self) -> None:
        """Sync dirty equipment to database."""
        if not self.valkey:
            return
            
        try:
            dirty_players_raw = await self.valkey.smembers("dirty:equipment")
            if not dirty_players_raw:
                return
                
            dirty_players = [int(p.decode() if isinstance(p, bytes) else p) for p in dirty_players_raw]
            
            async with self._gsm._db_session() as db:
                from server.src.models.item import PlayerEquipment
                
                # Delete existing equipment data
                await db.execute(
                    delete(PlayerEquipment).where(PlayerEquipment.player_id.in_(dirty_players))
                )
                
                # Insert fresh equipment data
                equipment_records = []
                for player_id in dirty_players:
                    equipment = await self._gsm.get_equipment(player_id)
                    for slot, item_data in equipment.items():
                        equipment_records.append({
                            "player_id": player_id,
                            "equipment_slot": slot,
                            "item_id": item_data["item_id"],
                            "quantity": item_data["quantity"],
                            "current_durability": item_data["durability"]
                        })
                
                if equipment_records:
                    await db.execute(
                        pg_insert(PlayerEquipment).values(equipment_records)
                    )
                
                await db.commit()
                await self.valkey.delete(["dirty:equipment"])
                
            logger.debug(
                "Synced equipment", 
                extra={"players": len(dirty_players), "items": len(equipment_records)}
            )
            
        except Exception as e:
            logger.error("Failed to sync equipment", extra={"error": str(e)})
            raise
    
    async def _sync_skills(self) -> None:
        """Sync dirty skills to database."""
        if not self.valkey:
            return
            
        try:
            dirty_players_raw = await self.valkey.smembers("dirty:skills")
            if not dirty_players_raw:
                return
                
            dirty_players = [int(p.decode() if isinstance(p, bytes) else p) for p in dirty_players_raw]
            
            async with self._gsm._db_session() as db:
                from server.src.models.skill import PlayerSkill
                
                for player_id in dirty_players:
                    skills = await self._gsm.get_all_skills(player_id)
                    
                    for skill_name, skill_data in skills.items():
                        # Update existing skill record
                        stmt = (
                            select(PlayerSkill)
                            .where(PlayerSkill.player_id == player_id)
                            .where(PlayerSkill.skill_id == skill_data["skill_id"])
                        )
                        result = await db.execute(stmt)
                        player_skill = result.scalar_one_or_none()
                        
                        if player_skill:
                            player_skill.current_level = skill_data["level"]
                            player_skill.experience = skill_data["experience"]
                
                await db.commit()
                await self.valkey.delete(["dirty:skills"])
                
            logger.debug(
                "Synced skills",
                extra={"players": len(dirty_players)}
            )
            
        except Exception as e:
            logger.error("Failed to sync skills", extra={"error": str(e)})
            raise
    
    async def _sync_ground_items(self) -> None:
        """Sync dirty ground items to database."""
        if not self.valkey:
            return
            
        try:
            dirty_maps_raw = await self.valkey.smembers("dirty:ground_items")
            if not dirty_maps_raw:
                return
                
            dirty_maps = [m.decode() if isinstance(m, bytes) else m for m in dirty_maps_raw]
            
            async with self._gsm._db_session() as db:
                from server.src.models.item import GroundItem
                
                for map_id in dirty_maps:
                    # Delete existing ground items for this map
                    await db.execute(
                        delete(GroundItem).where(GroundItem.map_id == map_id)
                    )
                    
                    # Insert current ground items
                    ground_items = await self._gsm.get_ground_items_on_map(map_id)
                    
                    ground_item_records = []
                    for item in ground_items:
                        ground_item_records.append({
                            "id": item["id"],
                            "map_id": map_id,
                            "x": item["x"],
                            "y": item["y"],
                            "item_id": item["item_id"],
                            "quantity": item["quantity"],
                            "current_durability": item["durability"],
                            "dropped_by_player_id": item.get("dropped_by_player_id"),
                            "loot_protection_expires_at": item.get("loot_protection_expires_at"),
                            "despawn_at": item["despawn_at"],
                            "created_at": item["created_at"]
                        })
                    
                    if ground_item_records:
                        await db.execute(
                            pg_insert(GroundItem).values(ground_item_records)
                        )
                
                await db.commit()
                await self.valkey.delete(["dirty:ground_items"])
                
            logger.debug(
                "Synced ground items",
                extra={"maps": len(dirty_maps)}
            )
            
        except Exception as e:
            logger.error("Failed to sync ground items", extra={"error": str(e)})
            raise
    
    async def _sync_single_player_to_db(self, db: AsyncSession, player_id: int) -> None:
        """Sync a single player's complete state to database."""
        try:
            # Import models here to avoid circular imports
            from server.src.models.player import Player
            from server.src.models.item import PlayerInventory, PlayerEquipment
            from server.src.models.skill import PlayerSkill
            
            # Get player from database
            stmt = select(Player).where(Player.id == player_id)
            result = await db.execute(stmt)
            player = result.scalar_one_or_none()
            
            if not player:
                logger.warning("Player not found for sync", extra={"player_id": player_id})
                return
            
            # Update position and HP
            position_data = await self._gsm.get_player_position(player_id)
            hp_data = await self._gsm.get_player_hp(player_id)
            
            if position_data:
                player.x_coord = position_data["x"]
                player.y_coord = position_data["y"]
                player.map_id = position_data["map_id"]
            
            if hp_data:
                player.current_hp = hp_data["current_hp"]
            
            # Sync inventory
            await db.execute(delete(PlayerInventory).where(PlayerInventory.player_id == player_id))
            inventory = await self._gsm.get_inventory(player_id)
            
            inventory_records = []
            for slot, item_data in inventory.items():
                inventory_records.append({
                    "player_id": player_id,
                    "slot": slot,
                    "item_id": item_data["item_id"],
                    "quantity": item_data["quantity"],
                    "current_durability": item_data["durability"]
                })
            
            if inventory_records:
                await db.execute(pg_insert(PlayerInventory).values(inventory_records))
            
            # Sync equipment
            await db.execute(delete(PlayerEquipment).where(PlayerEquipment.player_id == player_id))
            equipment = await self._gsm.get_equipment(player_id)
            
            equipment_records = []
            for slot, item_data in equipment.items():
                equipment_records.append({
                    "player_id": player_id,
                    "equipment_slot": slot,
                    "item_id": item_data["item_id"],
                    "quantity": item_data["quantity"],
                    "current_durability": item_data["durability"]
                })
            
            if equipment_records:
                await db.execute(pg_insert(PlayerEquipment).values(equipment_records))
            
            # Sync skills
            skills = await self._gsm.get_all_skills(player_id)
            for skill_name, skill_data in skills.items():
                stmt = (
                    select(PlayerSkill)
                    .where(PlayerSkill.player_id == player_id)
                    .where(PlayerSkill.skill_id == skill_data["skill_id"])
                )
                result = await db.execute(stmt)
                player_skill = result.scalar_one_or_none()
                
                if player_skill:
                    player_skill.current_level = skill_data["level"]
                    player_skill.experience = skill_data["experience"]
            
            logger.debug("Single player sync completed", extra={"player_id": player_id})
            
        except Exception as e:
            logger.error(
                "Failed to sync single player",
                extra={"player_id": player_id, "error": str(e)}
            )
            raise