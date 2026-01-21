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
            from ..connection_service import ConnectionService
            online_players = ConnectionService.get_online_player_ids()
            
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
                            "current_durability": item_data["current_durability"]
                        })
                
                if inventory_records:
                    await db.execute(pg_insert(PlayerInventory).values(inventory_records))
                
                await db.commit()
                
                # Clear dirty flags for processed players
                for player_id in dirty_players:
                    await self.valkey.srem("dirty:inventory", str(player_id))
                
                logger.debug("Inventory sync completed", extra={"player_count": len(dirty_players)})
            
        except Exception as e:
            logger.error(
                "Failed to sync inventories",
                extra={"error": str(e)}
            )
            raise

    async def _sync_equipment(self) -> None:
        """Sync dirty equipment data to database."""
        if not self.valkey:
            return
            
        try:
            dirty_players_raw = await self.valkey.smembers("dirty:equipment")
            if not dirty_players_raw:
                return
                
            dirty_players = [int(p.decode() if isinstance(p, bytes) else p) for p in dirty_players_raw]
            
            async with self._gsm._db_session() as db:
                from server.src.models.item import PlayerEquipment
                
                # Delete existing equipment data for dirty players
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
                            "slot": slot,
                            "item_id": item_data["item_id"],
                            "current_durability": item_data.get("current_durability", None)
                        })
                
                if equipment_records:
                    await db.execute(pg_insert(PlayerEquipment).values(equipment_records))
                
                await db.commit()
                
                # Clear dirty flags for processed players
                for player_id in dirty_players:
                    await self.valkey.srem("dirty:equipment", str(player_id))
                
                logger.debug("Equipment sync completed", extra={"player_count": len(dirty_players)})
            
        except Exception as e:
            logger.error(
                "Failed to sync equipment",
                extra={"error": str(e)}
            )
            raise

    async def _sync_skills(self) -> None:
        """Sync dirty skills data to database."""
        if not self.valkey:
            return
            
        try:
            dirty_players_raw = await self.valkey.smembers("dirty:skills")
            if not dirty_players_raw:
                return
                
            dirty_players = [int(p.decode() if isinstance(p, bytes) else p) for p in dirty_players_raw]
            
            async with self._gsm._db_session() as db:
                from server.src.models.skill import PlayerSkill
                
                # Delete existing skills data for dirty players
                await db.execute(
                    delete(PlayerSkill).where(PlayerSkill.player_id.in_(dirty_players))
                )
                
                # Insert fresh skills data
                skills_records = []
                for player_id in dirty_players:
                    skills = await self._gsm.get_skills_offline(player_id)  # Use offline method for consistency
                    for skill_name, skill_data in skills.items():
                        skills_records.append({
                            "player_id": player_id,
                            "skill_id": skill_data["skill_id"],
                            "current_level": skill_data["level"],
                            "experience": skill_data["experience"]
                        })
                
                if skills_records:
                    await db.execute(pg_insert(PlayerSkill).values(skills_records))
                
                await db.commit()
                
                # Clear dirty flags for processed players
                for player_id in dirty_players:
                    await self.valkey.srem("dirty:skills", str(player_id))
                
                logger.debug("Skills sync completed", extra={"player_count": len(dirty_players)})
            
        except Exception as e:
            logger.error(
                "Failed to sync skills",
                extra={"error": str(e)}
            )
            raise

    async def _sync_ground_items(self) -> None:
        """Sync dirty ground items data to database."""
        if not self.valkey:
            return
            
        try:
            # Ground items are synced by map, not by player
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
                    
                    # Insert fresh ground items data
                    ground_items = await self._gsm.get_ground_items_on_map(map_id)
                    if ground_items:
                        ground_item_records = []
                        for item_data in ground_items:
                            ground_item_records.append({
                                "id": item_data["id"],
                                "item_id": item_data["item_id"],
                                "x": item_data["x"],
                                "y": item_data["y"],
                                "map_id": item_data["map_id"],
                                "quantity": item_data["quantity"],
                                "current_durability": item_data.get("current_durability", None),
                                "dropped_by": item_data.get("dropped_by", None),
                                "dropped_at": item_data.get("dropped_at", None),
                                "protected_until": item_data.get("protected_until", None)
                            })
                        
                        if ground_item_records:
                            await db.execute(pg_insert(GroundItem).values(ground_item_records))
                
                await db.commit()
                
                # Clear dirty flags for processed maps
                for map_id in dirty_maps:
                    await self.valkey.srem("dirty:ground_items", map_id)
                
                logger.debug("Ground items sync completed", extra={"map_count": len(dirty_maps)})
            
        except Exception as e:
            logger.error(
                "Failed to sync ground items",
                extra={"error": str(e)}
            )
            raise

    async def _sync_single_player_to_db(self, db: AsyncSession, player_id: int) -> None:
        """
        Sync all data for a single player to the database.
        Used during shutdown to ensure data integrity.
        
        Args:
            db: Database session to use
            player_id: Player ID to sync
        """
        try:
            from server.src.models.player import Player
            from server.src.models.item import PlayerInventory, PlayerEquipment, GroundItem
            from server.src.models.skill import PlayerSkill
            
            # Update player position and HP
            position_data = await self._gsm.get_player_position(player_id)
            hp_data = await self._gsm.get_player_hp(player_id)
            
            if position_data and hp_data:
                stmt = select(Player).where(Player.id == player_id)
                result = await db.execute(stmt)
                player = result.scalar_one_or_none()
                
                if player:
                    player.x_coord = position_data["x"]
                    player.y_coord = position_data["y"] 
                    player.map_id = position_data["map_id"]
                    player.current_hp = hp_data["current_hp"]
            
            # Sync inventory
            await db.execute(delete(PlayerInventory).where(PlayerInventory.player_id == player_id))
            inventory = await self._gsm.get_inventory(player_id)
            if inventory:
                inventory_records = []
                for slot, item_data in inventory.items():
                    inventory_records.append({
                        "player_id": player_id,
                        "slot": slot,
                        "item_id": item_data["item_id"],
                        "quantity": item_data["quantity"],
                        "current_durability": item_data["current_durability"]
                    })
                
                if inventory_records:
                    await db.execute(pg_insert(PlayerInventory).values(inventory_records))
            
            # Sync equipment  
            await db.execute(delete(PlayerEquipment).where(PlayerEquipment.player_id == player_id))
            equipment = await self._gsm.get_equipment(player_id)
            if equipment:
                equipment_records = []
                for slot, item_data in equipment.items():
                    equipment_records.append({
                        "player_id": player_id,
                        "slot": slot,
                        "item_id": item_data["item_id"],
                        "current_durability": item_data.get("current_durability", None)
                    })
                
                if equipment_records:
                    await db.execute(pg_insert(PlayerEquipment).values(equipment_records))
            
            # Sync skills
            await db.execute(delete(PlayerSkill).where(PlayerSkill.player_id == player_id))
            skills = await self._gsm.get_skills_offline(player_id)
            if skills:
                skills_records = []
                for skill_name, skill_data in skills.items():
                    skills_records.append({
                        "player_id": player_id,
                        "skill_id": skill_data["skill_id"],
                        "current_level": skill_data["level"],
                        "experience": skill_data["experience"]
                    })
                
                if skills_records:
                    await db.execute(pg_insert(PlayerSkill).values(skills_records))
            
            logger.debug("Single player sync completed", extra={"player_id": player_id})
            
        except Exception as e:
            logger.error(
                "Failed to sync single player",
                extra={"player_id": player_id, "error": str(e)}
            )
            raise