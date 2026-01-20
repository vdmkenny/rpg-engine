"""
GameStateManager - Single source of truth for all game state.

This module provides a modular GameStateManager with helper classes to keep
file sizes manageable while maintaining clear separation of concerns.
"""

import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from glide import GlideClient
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, sessionmaker

from server.src.core.config import settings
from server.src.core.logging_config import get_logger

from .state_access import GSMStateAccess
from .batch_operations import GSMBatchOps  
from .migration_helpers import GSMMigrationHelpers

logger = get_logger(__name__)


# =============================================================================
# VALKEY KEY PATTERNS
# =============================================================================

# Player state keys (all use player_id for consistency)
PLAYER_KEY = "player:{player_id}"
INVENTORY_KEY = "inventory:{player_id}"
EQUIPMENT_KEY = "equipment:{player_id}"
SKILLS_KEY = "skills:{player_id}"

# Ground item keys
GROUND_ITEM_KEY = "ground_item:{ground_item_id}"
GROUND_ITEMS_MAP_KEY = "ground_items:map:{map_id}"
GROUND_ITEMS_NEXT_ID_KEY = "ground_items:next_id"

# Dirty tracking keys (for batch sync)
DIRTY_POSITION_KEY = "dirty:position"
DIRTY_INVENTORY_KEY = "dirty:inventory"
DIRTY_EQUIPMENT_KEY = "dirty:equipment"
DIRTY_SKILLS_KEY = "dirty:skills"
DIRTY_GROUND_ITEMS_KEY = "dirty:ground_items"


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def _utc_timestamp() -> float:
    """Get current UTC timestamp."""
    return datetime.now(timezone.utc).timestamp()


def _decode_bytes(value: bytes | str) -> str:
    """Safely decode bytes to string."""
    return value.decode() if isinstance(value, bytes) else value


# =============================================================================
# GAMESTATE MANAGER
# =============================================================================

class GameStateManager:
    """
    Single source of truth for all mutable game state.
    
    Manages Valkey (hot cache) and PostgreSQL (durable storage) for all
    player state, inventory, equipment, skills, and ground items.
    
    Design principles:
    - Valkey-first for online players
    - Batch persistence for performance  
    - Consistent player_id-based keys
    - Modular design with helper classes
    """
    
    def __init__(
        self,
        valkey_client: Optional[GlideClient] = None,
        session_factory: Optional[sessionmaker] = None,
    ):
        """
        Initialize GameStateManager.
        
        Args:
            valkey_client: Valkey client for hot cache
            session_factory: SQLAlchemy session factory for database
        """
        self._valkey = valkey_client
        self._session_factory = session_factory
        
        # Online player registry (in-memory)
        self._online_players: Set[int] = set()
        self._username_to_id: Dict[str, int] = {}
        self._id_to_username: Dict[int, str] = {}
        
        # Item metadata cache (loaded from database on startup)
        self._item_cache: Dict[int, Dict[str, Any]] = {}
        
        # Test session binding (for test isolation)
        self._bound_test_session: Optional[AsyncSession] = None
        
        # Initialize helper classes
        self.state_access = GSMStateAccess(self)
        self.batch_ops = GSMBatchOps(self)
        self.migration = GSMMigrationHelpers(self)
        
        logger.info("GameStateManager initialized")
    
    @property
    def valkey(self) -> Optional[GlideClient]:
        """Get Valkey client."""
        return self._valkey
    
    def bind_test_session(self, session: AsyncSession) -> None:
        """
        Bind external session for testing.
        
        When bound, GSM will use this session instead of creating new sessions.
        This ensures test operations share the same transaction boundary.
        
        Args:
            session: SQLAlchemy AsyncSession to use for database operations
        """
        self._bound_test_session = session
        logger.debug("Test session bound to GSM")
    
    def unbind_test_session(self) -> None:
        """
        Remove bound test session.
        
        Resume normal session creation behavior.
        """
        self._bound_test_session = None
        logger.debug("Test session unbound from GSM")
    
    async def _commit_if_not_test_session(self, db: AsyncSession) -> None:
        """
        Commit the session only if not using a bound test session.
        
        Test sessions handle their own transaction boundaries and should not be committed
        by GSM operations to maintain proper test isolation.
        
        UPDATE: Always commit for now - we need visibility between operations.
        """
        # Always commit for now - preventing commits breaks operation visibility
        await db.commit()
    
    @asynccontextmanager
    async def _db_session(self):
        """Create database session context manager."""
        # If we have a bound test session, use it directly
        if self._bound_test_session is not None:
            logger.debug(f"Using bound test session: {id(self._bound_test_session)}")
            yield self._bound_test_session
            return
            
        # Otherwise, use normal session factory
        if not self._session_factory:
            raise RuntimeError("Database session factory not initialized")
        
        logger.debug("Creating new session from factory")
        async with self._session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
    
    # =========================================================================
    # ITEM CACHE MANAGEMENT
    # =========================================================================
    
    async def load_item_cache_from_db(self) -> int:
        """
        Load item metadata cache from database.
        Called once during server startup.
        
        Returns:
            Number of items loaded
        """
        if not self._session_factory:
            logger.warning("Cannot load item cache - no database connection")
            return 0
        
        try:
            async with self._db_session() as db:
                from server.src.models.item import Item
                
                result = await db.execute(select(Item))
                items = result.scalars().all()
                
                self._item_cache = {}
                for item in items:
                    self._item_cache[item.id] = {
                        "id": item.id,
                        "name": item.name,
                        "display_name": item.display_name,
                        "description": item.description,
                        "category": item.category,
                        "rarity": item.rarity,
                        "value": item.value,
                        "max_durability": item.max_durability,
                        "max_stack_size": item.max_stack_size,
                        "equipable": item.equipment_slot is not None,  # equipable if has equipment slot
                        "equipment_slot": item.equipment_slot,
                        "attack_bonus": item.attack_bonus,
                        "strength_bonus": item.strength_bonus,
                        "physical_defence_bonus": item.physical_defence_bonus,
                        "ranged_attack_bonus": item.ranged_attack_bonus,
                        "ranged_strength_bonus": item.ranged_strength_bonus,
                        "magic_attack_bonus": item.magic_attack_bonus,
                        "magic_defence_bonus": item.magic_defence_bonus,
                        "health_bonus": item.health_bonus,
                        "speed_bonus": item.speed_bonus,
                        "required_skill": item.required_skill,
                        "required_level": item.required_level,
                        "is_two_handed": item.is_two_handed,
                        "ammo_type": item.ammo_type,
                        "is_indestructible": item.is_indestructible,
                        "is_tradeable": item.is_tradeable,
                    }
                
                logger.info(
                    "Item cache loaded",
                    extra={"item_count": len(self._item_cache)}
                )
                
                return len(self._item_cache)
                
        except Exception as e:
            logger.error("Failed to load item cache", extra={"error": str(e)})
            raise
    
    def get_cached_item_meta(self, item_id: int) -> Optional[Dict[str, Any]]:
        """
        Get item metadata from cache (synchronous).
        
        Args:
            item_id: Item ID
            
        Returns:
            Item metadata dict or None if not found
        """
        return self._item_cache.get(item_id)
    
    # =========================================================================
    # ONLINE PLAYER REGISTRY
    # =========================================================================
    
    def register_online_player(self, player_id: int, username: str) -> None:
        """
        Register a player as online.
        
        Args:
            player_id: Player's ID
            username: Player's username
        """
        self._online_players.add(player_id)
        self._username_to_id[username] = player_id
        self._id_to_username[player_id] = username
        
        logger.debug(
            "Player registered as online",
            extra={"player_id": player_id, "username": username}
        )
    
    def unregister_online_player(self, player_id: int) -> None:
        """
        Unregister a player from online status.
        
        Args:
            player_id: Player's ID
        """
        self._online_players.discard(player_id)
        
        username = self._id_to_username.pop(player_id, None)
        if username:
            self._username_to_id.pop(username, None)
        
        logger.debug(
            "Player unregistered from online",
            extra={"player_id": player_id, "username": username}
        )
    
    def is_online(self, player_id: int) -> bool:
        """Check if a player is online."""
        return player_id in self._online_players
    
    def get_online_player_ids(self) -> Set[int]:
        """Get set of all online player IDs."""
        return self._online_players.copy()
    
    def get_online_player_id_by_username(self, username: str) -> Optional[int]:
        """Get player ID by username (online players only)."""
        return self._username_to_id.get(username)
    
    def get_username_by_player_id(self, player_id: int) -> Optional[str]:
        """Get username by player ID."""
        return self._id_to_username.get(player_id)
    
    # =========================================================================
    # PLAYER POSITION & HP
    # =========================================================================
    
    async def get_player_position(self, player_id: int) -> Optional[Dict[str, Any]]:
        """
        Get player's position from Valkey.
        
        Args:
            player_id: Player's database ID
            
        Returns:
            Dict with x, y, map_id or None if not found
        """
        if not self._valkey or not self.is_online(player_id):
            return None
        
        key = PLAYER_KEY.format(player_id=player_id)
        raw = await self._valkey.hgetall(key)
        
        if not raw:
            return None
        
        try:
            return {
                "x": int(_decode_bytes(raw.get(b"x", b"0"))),
                "y": int(_decode_bytes(raw.get(b"y", b"0"))), 
                "map_id": _decode_bytes(raw.get(b"map_id", b""))
            }
        except (ValueError, TypeError):
            return None
    
    async def get_player_hp(self, player_id: int) -> Optional[Dict[str, int]]:
        """
        Get player's HP from Valkey.
        
        Args:
            player_id: Player's database ID
            
        Returns:
            Dict with current_hp, max_hp or None if not found
        """
        if not self._valkey or not self.is_online(player_id):
            return None
        
        key = PLAYER_KEY.format(player_id=player_id)
        raw = await self._valkey.hgetall(key)
        
        if not raw:
            return None
        
        return {
            "current_hp": int(_decode_bytes(raw.get(b"current_hp", b"10"))),
            "max_hp": int(_decode_bytes(raw.get(b"max_hp", b"10"))),
        }
    
    async def set_player_hp(
        self, player_id: int, current_hp: int, max_hp: Optional[int] = None
    ) -> None:
        """
        Set player's HP in Valkey and mark dirty.
        
        Args:
            player_id: Player's database ID
            current_hp: Current HP value
            max_hp: Max HP value (optional, only updates if provided)
        """
        if not self._valkey or not self.is_online(player_id):
            return
        
        key = PLAYER_KEY.format(player_id=player_id)
        update_data = {"current_hp": str(current_hp)}
        if max_hp is not None:
            update_data["max_hp"] = str(max_hp)
        
        await self._valkey.hset(key, update_data)
        await self._valkey.sadd(DIRTY_POSITION_KEY, [str(player_id)])
    
    async def get_player_full_state(self, player_id: int) -> Optional[Dict[str, Any]]:
        """
        Get complete player state from Valkey.
        
        Args:
            player_id: Player's database ID
            
        Returns:
            Dict with all player state or None if not found
        """
        if not self._valkey or not self.is_online(player_id):
            return None
        
        key = PLAYER_KEY.format(player_id=player_id)
        raw = await self._valkey.hgetall(key)
        
        if not raw:
            return None
        
        # Convert bytes to appropriate types
        state = {}
        for field, value in raw.items():
            field_str = _decode_bytes(field)
            value_str = _decode_bytes(value)
            
            # Convert numeric fields
            if field_str in ["x", "y", "current_hp", "max_hp", "player_id"]:
                state[field_str] = int(value_str) if value_str.isdigit() else 0
            else:
                state[field_str] = value_str
        
        # Add username if available
        username = self.get_username_by_player_id(player_id)
        if username:
            state["username"] = username
        
        return state
    
    async def set_player_full_state(
        self,
        player_id: int,
        x: int,
        y: int,
        map_id: str,
        current_hp: int,
        max_hp: int,
    ) -> None:
        """
        Set complete player state in Valkey.
        
        Args:
            player_id: Player's database ID
            x: Tile X coordinate
            y: Tile Y coordinate
            map_id: Map identifier
            current_hp: Current HP
            max_hp: Maximum HP
        """
        if not self._valkey or not self.is_online(player_id):
            return
        
        key = PLAYER_KEY.format(player_id=player_id)
        state_data = {
            "x": str(x),
            "y": str(y),
            "map_id": map_id,
            "current_hp": str(current_hp),
            "max_hp": str(max_hp),
            "player_id": str(player_id),
            "facing_direction": "DOWN",
            "is_moving": "false",
            "last_move_time": "0",
        }
        
        await self._valkey.hset(key, state_data)
        await self._valkey.sadd(DIRTY_POSITION_KEY, [str(player_id)])
    
    # =========================================================================
    # INVENTORY OPERATIONS
    # =========================================================================
    
    async def get_inventory(self, player_id: int) -> Dict[int, Dict]:
        """
        Get player's inventory from Valkey. Auto-loads from database if not in Valkey.
        Falls back to database if Valkey is unavailable or disabled.
        
        Args:
            player_id: Player's database ID
            
        Returns:
            Dict mapping slot number to item data
        """
        from server.src.core.config import settings
        
        # If Valkey disabled or unavailable, use database fallback
        if not settings.USE_VALKEY or not self._valkey:
            if not settings.USE_VALKEY:
                logger.debug("Valkey disabled, using database fallback", extra={"player_id": player_id})
            else:
                logger.warning("Valkey unavailable, using database fallback", extra={"player_id": player_id})
            return await self.get_inventory_offline(player_id)
        
        key = INVENTORY_KEY.format(player_id=player_id)
        raw = await self._valkey.hgetall(key)
        
        # If no data in Valkey, auto-load from database
        if not raw:
            logger.debug("Auto-loading player inventory from database", extra={"player_id": player_id})
            inventory_data = await self.get_inventory_offline(player_id)
            
            # Store in Valkey for future access with normal TTL
            if inventory_data:
                await self._load_inventory_to_valkey(player_id, inventory_data)
            
            return inventory_data
        
        # Parse Valkey data
        inventory = {}
        for slot_str, item_json in raw.items():
            slot = int(_decode_bytes(slot_str))
            item_data = json.loads(_decode_bytes(item_json))
            inventory[slot] = item_data
        
        return inventory

    async def _load_inventory_to_valkey(self, player_id: int, inventory_data: Dict[int, Dict]) -> None:
        """Load inventory data into Valkey with configured TTL."""
        from server.src.core.config import settings
        
        if not settings.USE_VALKEY or not self._valkey or not inventory_data:
            return
        
        key = INVENTORY_KEY.format(player_id=player_id)
        valkey_data = {}
        
        for slot, item_data in inventory_data.items():
            valkey_data[str(slot)] = json.dumps(item_data)
        
        await self._valkey.hset(key, valkey_data)
        
        # Set standard TTL (same for all player data regardless of online/offline status)
        # TODO: Make TTL configurable via settings
        await self._valkey.expire(key, 3600)  # 1 hour default, should be configurable
    
    async def get_inventory_slot(
        self, player_id: int, slot: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get item in specific inventory slot. Auto-loads from database if not in Valkey.
        Falls back to database if Valkey is unavailable or disabled.
        
        Args:
            player_id: Player's database ID
            slot: Inventory slot number
            
        Returns:
            Item data dict or None if empty
        """
        from server.src.core.config import settings
        
        # If Valkey disabled or unavailable, use database fallback
        if not settings.USE_VALKEY or not self._valkey:
            if not settings.USE_VALKEY:
                logger.debug("Valkey disabled, using database fallback for slot", extra={"player_id": player_id, "slot": slot})
            else:
                logger.warning("Valkey unavailable, using database fallback for slot", extra={"player_id": player_id, "slot": slot})
            inventory_data = await self.get_inventory_offline(player_id)
            return inventory_data.get(slot)
        
        key = INVENTORY_KEY.format(player_id=player_id)
        raw = await self._valkey.hget(key, str(slot))
        
        # If slot data not in Valkey, try auto-loading full inventory
        if not raw:
            logger.debug("Auto-loading player inventory for slot access", extra={"player_id": player_id, "slot": slot})
            inventory_data = await self.get_inventory(player_id)  # This will auto-load if needed
            return inventory_data.get(slot)
        
        try:
            return json.loads(_decode_bytes(raw))
        except ValueError as e:
            logger.error(
                "Failed to parse inventory slot data", 
                extra={"player_id": player_id, "slot": slot, "error": str(e)}
            )
            return None
        except json.JSONDecodeError as e:
            logger.warning(
                "Invalid inventory slot data",
                extra={"player_id": player_id, "slot": slot, "error": str(e)}
            )
            return None
    
    async def set_inventory_slot(
        self,
        player_id: int,
        slot: int,
        item_id: int,
        quantity: int,
        durability: float,
    ) -> None:
        """
        Set item in inventory slot. Auto-loads player data if needed.
        Falls back to database if Valkey is unavailable or disabled.
        
        Args:
            player_id: Player's database ID  
            slot: Inventory slot number
            item_id: Item ID
            quantity: Item quantity
            durability: Item durability (0.0 to 1.0)
        """
        from server.src.core.config import settings
        
        # If Valkey disabled or unavailable, use database fallback
        if not settings.USE_VALKEY or not self._valkey:
            if not settings.USE_VALKEY:
                logger.debug("Valkey disabled, using database for set_inventory_slot", extra={"player_id": player_id, "slot": slot})
            else:
                logger.warning("Valkey unavailable, using database for set_inventory_slot", extra={"player_id": player_id, "slot": slot})
            await self.set_inventory_slot_offline(player_id, slot, item_id, quantity, durability)
            return
        
        # Ensure player data is loaded (this will auto-load from DB if needed)
        await self.get_inventory(player_id)
        
        key = INVENTORY_KEY.format(player_id=player_id)
        item_data = {
            "item_id": item_id,
            "quantity": quantity,
            "current_durability": durability,
        }
        
        await self._valkey.hset(key, {str(slot): json.dumps(item_data)})
        await self._valkey.sadd(DIRTY_INVENTORY_KEY, [str(player_id)])
    
    async def delete_inventory_slot(self, player_id: int, slot: int) -> None:
        """
        Delete item from inventory slot.
        
        Args:
            player_id: Player's database ID
            slot: Inventory slot number
        """
        if not self._valkey or not self.is_online(player_id):
            return
        
        key = INVENTORY_KEY.format(player_id=player_id)
        await self._valkey.hdel(key, [str(slot)])
        await self._valkey.sadd(DIRTY_INVENTORY_KEY, [str(player_id)])
    
    async def get_free_inventory_slot(
        self, player_id: int, max_slots: int = 28
    ) -> Optional[int]:
        """
        Get first free inventory slot.
        
        Args:
            player_id: Player's database ID
            max_slots: Maximum inventory slots
            
        Returns:
            Free slot number or None if inventory full
        """
        inventory = await self.get_inventory(player_id)
        
        for slot in range(max_slots):
            if slot not in inventory:
                return slot
        
        return None
    
    async def get_inventory_count(self, player_id: int) -> int:
        """
        Get total number of items in inventory.
        
        Args:
            player_id: Player's database ID
            
        Returns:
            Total item count
        """
        inventory = await self.get_inventory(player_id)
        return sum(item["quantity"] for item in inventory.values())
    
    async def clear_inventory(self, player_id: int) -> None:
        """
        Clear all items from inventory.
        
        Args:
            player_id: Player's database ID
        """
        if not self._valkey or not self.is_online(player_id):
            return
        
        key = INVENTORY_KEY.format(player_id=player_id)
        await self._valkey.delete([key])
        await self._valkey.sadd(DIRTY_INVENTORY_KEY, [str(player_id)])
    
    # =========================================================================
    # PLAYER LIFECYCLE
    # =========================================================================
    
    async def load_player_state(self, player_id: int) -> None:
        """
        Load complete player state from database to Valkey.
        Called when player connects.
        
        Args:
            player_id: Player's database ID
        """
        if not self._valkey or not self._session_factory:
            return
        
        try:
            async with self._db_session() as db:
                from server.src.models.player import Player
                from server.src.models.item import PlayerInventory, PlayerEquipment
                from server.src.models.skill import PlayerSkill, Skill
                
                # Load player data
                stmt = select(Player).where(Player.id == player_id)
                result = await db.execute(stmt)
                player = result.scalar_one_or_none()
                
                if not player:
                    logger.warning("Player not found for state loading", extra={"player_id": player_id})
                    return
                
                # Set player state in Valkey
                await self.set_player_full_state(
                    player_id, player.x_coord, player.y_coord, player.map_id,
                    player.current_hp, player.current_hp  # TODO: Calculate max_hp from equipment
                )
                
                # Load inventory
                inv_stmt = select(PlayerInventory).where(PlayerInventory.player_id == player_id)
                inv_result = await db.execute(inv_stmt)
                inventory_items = inv_result.scalars().all()
                
                for item in inventory_items:
                    await self.set_inventory_slot(
                        player_id, item.slot, item.item_id, item.quantity, item.current_durability
                    )
                
                # Load equipment
                eq_stmt = select(PlayerEquipment).where(PlayerEquipment.player_id == player_id)
                eq_result = await db.execute(eq_stmt)
                equipment_items = eq_result.scalars().all()
                
                for item in equipment_items:
                    await self.set_equipment_slot(
                        player_id, item.equipment_slot, item.item_id, item.quantity, item.current_durability
                    )
                
                # Load skills
                skill_stmt = (
                    select(PlayerSkill, Skill)
                    .join(Skill)
                    .where(PlayerSkill.player_id == player_id)
                )
                skill_result = await db.execute(skill_stmt)
                skills = skill_result.all()
                
                for player_skill, skill in skills:
                    await self.set_skill(
                        player_id, skill.name.lower(), player_skill.skill_id,
                        player_skill.current_level, player_skill.experience
                    )
                
                logger.info(
                    "Player state loaded to Valkey",
                    extra={
                        "player_id": player_id,
                        "inventory_items": len(inventory_items),
                        "equipment_items": len(equipment_items),
                        "skills": len(skills)
                    }
                )
                
        except Exception as e:
            logger.error(
                "Failed to load player state",
                extra={"player_id": player_id, "error": str(e)}
            )
            raise
    
    async def sync_player_to_db(self, player_id: int, username: str) -> None:
        """
        Sync single player's complete state to database.
        Called when player disconnects.
        
        Args:
            player_id: Player's database ID
            username: Player's username
        """
        if not self._session_factory:
            logger.warning("No database session factory for player sync")
            return
        
        try:
            async with self._db_session() as db:
                await self.batch_ops._sync_single_player_to_db(db, player_id)
                await self._commit_if_not_test_session(db)
                
            logger.info("Player synced to database", extra={"player_id": player_id, "username": username})
            
        except Exception as e:
            logger.error(
                "Failed to sync player to database",
                extra={"player_id": player_id, "username": username, "error": str(e)}
            )
            raise
    
    async def cleanup_player_state(self, player_id: int) -> None:
        """
        Clean up player state from Valkey after sync.
        
        Args:
            player_id: Player's database ID
        """
        if not self._valkey:
            return
        
        try:
            # Delete all player keys
            keys_to_delete = [
                PLAYER_KEY.format(player_id=player_id),
                INVENTORY_KEY.format(player_id=player_id),
                EQUIPMENT_KEY.format(player_id=player_id),
                SKILLS_KEY.format(player_id=player_id)
            ]
            
            await self._valkey.delete(keys_to_delete)
            
            logger.debug("Player state cleaned up", extra={"player_id": player_id})
            
        except Exception as e:
            logger.error(
                "Failed to cleanup player state",
                extra={"player_id": player_id, "error": str(e)}
            )
    
    # =========================================================================
    # EQUIPMENT OPERATIONS
    # =========================================================================
    
    async def get_equipment(self, player_id: int) -> Dict[str, Dict]:
        """Get player's equipment from Valkey (online) or database (offline)."""
        if not self._valkey or not self.is_online(player_id):
            # Use offline database method for offline players
            return await self.get_equipment_offline(player_id)
        
        key = EQUIPMENT_KEY.format(player_id=player_id)
        raw = await self._valkey.hgetall(key)
        
        equipment = {}
        for slot_bytes, item_data_bytes in raw.items():
            try:
                slot = _decode_bytes(slot_bytes)
                item_data = json.loads(_decode_bytes(item_data_bytes))
                equipment[slot] = item_data
            except json.JSONDecodeError as e:
                logger.warning("Invalid equipment data", extra={"player_id": player_id, "error": str(e)})
        
        return equipment
    
    async def get_equipment_slot(self, player_id: int, slot: str) -> Optional[Dict[str, Any]]:
        """Get item in specific equipment slot."""
        if not self._valkey or not self.is_online(player_id):
            return None
        
        key = EQUIPMENT_KEY.format(player_id=player_id)
        raw = await self._valkey.hget(key, slot)
        
        if not raw:
            return None
        
        try:
            return json.loads(_decode_bytes(raw))
        except json.JSONDecodeError:
            return None
    
    async def set_equipment_slot(self, player_id: int, slot: str, item_id: int, quantity: int, durability: float) -> None:
        """Set item in equipment slot."""
        if not self._valkey or not self.is_online(player_id):
            return
        
        key = EQUIPMENT_KEY.format(player_id=player_id)
        item_data = {"item_id": item_id, "quantity": quantity, "current_durability": durability}
        
        await self._valkey.hset(key, {slot: json.dumps(item_data)})
        await self._valkey.sadd(DIRTY_EQUIPMENT_KEY, [str(player_id)])
    
    async def delete_equipment_slot(self, player_id: int, slot: str) -> None:
        """Delete item from equipment slot."""
        if not self._valkey or not self.is_online(player_id):
            return
        
        key = EQUIPMENT_KEY.format(player_id=player_id)
        await self._valkey.hdel(key, [slot])
        await self._valkey.sadd(DIRTY_EQUIPMENT_KEY, [str(player_id)])
    
    async def clear_equipment(self, player_id: int) -> None:
        """Clear all equipment."""
        if not self._valkey or not self.is_online(player_id):
            return
        
        key = EQUIPMENT_KEY.format(player_id=player_id)
        await self._valkey.delete([key])
        await self._valkey.sadd(DIRTY_EQUIPMENT_KEY, [str(player_id)])
    
    # =========================================================================
    # SKILL OPERATIONS
    # =========================================================================
    
    async def get_skill(self, player_id: int, skill_name: str) -> Optional[Dict[str, Any]]:
        """Get specific skill data from Valkey (online) or database (offline)."""
        if not self._valkey or not self.is_online(player_id):
            # Use offline database method for offline players
            skills_data = await self.get_skills_offline(player_id)
            return skills_data.get(skill_name.lower())
        
        key = SKILLS_KEY.format(player_id=player_id)
        raw = await self._valkey.hget(key, skill_name.lower())
        
        if not raw:
            return None
        
        try:
            return json.loads(_decode_bytes(raw))
        except json.JSONDecodeError:
            return None
    
    async def get_all_skills(self, player_id: int) -> Dict[str, Dict]:
        """Get all skills for a player from Valkey (online) or database (offline)."""
        if not self._valkey or not self.is_online(player_id):
            # Use offline database method for offline players
            return await self.get_skills_offline(player_id)
        
        key = SKILLS_KEY.format(player_id=player_id)
        raw = await self._valkey.hgetall(key)
        
        skills = {}
        for skill_name_bytes, skill_data_bytes in raw.items():
            try:
                skill_name = _decode_bytes(skill_name_bytes)
                skill_data = json.loads(_decode_bytes(skill_data_bytes))
                skills[skill_name] = skill_data
            except json.JSONDecodeError as e:
                logger.warning("Invalid skill data", extra={"player_id": player_id, "error": str(e)})
        
        return skills
    
    async def set_skill(self, player_id: int, skill_name: str, skill_id: int, level: int, experience: int) -> None:
        """Set skill data."""
        if not self._valkey or not self.is_online(player_id):
            return
        
        key = SKILLS_KEY.format(player_id=player_id)
        skill_data = {"skill_id": skill_id, "level": level, "experience": experience}
        
        await self._valkey.hset(key, {skill_name.lower(): json.dumps(skill_data)})
        await self._valkey.sadd(DIRTY_SKILLS_KEY, [str(player_id)])
    
    # =========================================================================
    # GROUND ITEM OPERATIONS  
    # =========================================================================
    
    async def get_next_ground_item_id(self) -> int:
        """Get next available ground item ID."""
        if not self._valkey:
            return 1
        return await self._valkey.incr(GROUND_ITEMS_NEXT_ID_KEY)
    
    async def set_next_ground_item_id(self, next_id: int) -> None:
        """Set next ground item ID."""
        if self._valkey:
            await self._valkey.set(GROUND_ITEMS_NEXT_ID_KEY, str(next_id))
    
    async def add_ground_item(self, map_id: str, x: int, y: int, item_id: int, quantity: int, durability: float, dropped_by_player_id: Optional[int] = None, loot_protection_expires_at: Optional[float] = None, despawn_at: Optional[float] = None) -> int:
        """Add ground item to Valkey."""
        if not self._valkey:
            return 0
        
        ground_item_id = await self.get_next_ground_item_id()
        current_time = _utc_timestamp()
        
        if despawn_at is None:
            despawn_at = current_time + 300  # 5 minutes default
        
        ground_item_data = {
            "id": str(ground_item_id), "map_id": map_id, "x": str(x), "y": str(y),
            "item_id": str(item_id), "quantity": str(quantity), "current_durability": str(durability),
            "created_at": str(current_time), "despawn_at": str(despawn_at)
        }
        
        if dropped_by_player_id:
            ground_item_data["dropped_by_player_id"] = str(dropped_by_player_id)
        if loot_protection_expires_at:
            ground_item_data["loot_protection_expires_at"] = str(loot_protection_expires_at)
        
        ground_item_key = GROUND_ITEM_KEY.format(ground_item_id=ground_item_id)
        await self._valkey.hset(ground_item_key, ground_item_data)
        
        map_key = GROUND_ITEMS_MAP_KEY.format(map_id=map_id)
        await self._valkey.sadd(map_key, [str(ground_item_id)])
        await self._valkey.sadd(DIRTY_GROUND_ITEMS_KEY, [map_id])
        
        return ground_item_id
    
    async def remove_ground_item(self, ground_item_id: int, map_id: str) -> bool:
        """Remove ground item from Valkey."""
        if not self._valkey:
            return False
        
        ground_item_key = GROUND_ITEM_KEY.format(ground_item_id=ground_item_id)
        deleted = await self._valkey.delete([ground_item_key])
        
        if deleted > 0:
            map_key = GROUND_ITEMS_MAP_KEY.format(map_id=map_id)
            await self._valkey.srem(map_key, [str(ground_item_id)])
            await self._valkey.sadd(DIRTY_GROUND_ITEMS_KEY, [map_id])
            return True
        
        return False
    
    async def get_ground_item(self, ground_item_id: int) -> Optional[Dict[str, Any]]:
        """Get ground item data."""
        if not self._valkey:
            return None
        
        ground_item_key = GROUND_ITEM_KEY.format(ground_item_id=ground_item_id)
        raw = await self._valkey.hgetall(ground_item_key)
        
        if not raw:
            return None
        
        item_data = {}
        for field, value in raw.items():
            field_str = _decode_bytes(field)
            value_str = _decode_bytes(value)
            
            if field_str in ["id", "item_id", "quantity", "x", "y", "dropped_by_player_id"]:
                item_data[field_str] = int(value_str) if value_str.isdigit() else 0
            elif field_str in ["current_durability", "created_at", "despawn_at", "loot_protection_expires_at"]:
                try:
                    item_data[field_str] = float(value_str)
                except ValueError:
                    item_data[field_str] = 0.0
            else:
                item_data[field_str] = value_str
        
        return item_data
    
    async def get_ground_items_on_map(self, map_id: str) -> List[Dict[str, Any]]:
        """Get all ground items on a map."""
        if not self._valkey:
            return []
        
        map_key = GROUND_ITEMS_MAP_KEY.format(map_id=map_id)
        ground_item_ids_raw = await self._valkey.smembers(map_key)
        
        if not ground_item_ids_raw:
            return []
        
        ground_items = []
        for ground_item_id_raw in ground_item_ids_raw:
            ground_item_id = int(_decode_bytes(ground_item_id_raw))
            item_data = await self.get_ground_item(ground_item_id)
            if item_data:
                ground_items.append(item_data)
        
        return ground_items
    
    async def load_ground_items_from_db(self) -> int:
        """Load ground items from database to Valkey on startup."""
        if not self._session_factory:
            return 0
        
        try:
            async with self._db_session() as db:
                from server.src.models.item import GroundItem
                
                result = await db.execute(select(GroundItem))
                ground_items = result.scalars().all()
                
                items_loaded = 0
                for item in ground_items:
                    await self.add_ground_item(
                        item.map_id, item.x, item.y, item.item_id, item.quantity,
                        item.current_durability, item.dropped_by_player_id,
                        item.loot_protection_expires_at.timestamp() if item.loot_protection_expires_at else None,
                        item.despawn_at.timestamp() if item.despawn_at else None
                    )
                    items_loaded += 1
                
                if ground_items:
                    max_id = max(item.id for item in ground_items)
                    await self.set_next_ground_item_id(max_id + 1)
                
                logger.info("Ground items loaded", extra={"count": items_loaded})
                return items_loaded
                
        except Exception as e:
            logger.error("Failed to load ground items", extra={"error": str(e)})
            raise
    
    # =========================================================================
    # BATCH SYNC OPERATIONS (Delegate to helper)
    # =========================================================================
    
    async def sync_all(self) -> None:
        """Sync all dirty data to database."""
        await self.batch_ops.sync_all()
    
    async def sync_all_on_shutdown(self) -> None:
        """Sync all online player data before shutdown."""
        await self.batch_ops.sync_all_on_shutdown()
    
    async def sync_ground_items_to_db(self) -> None:
        """Sync ground items to database."""
        await self.batch_ops._sync_ground_items()

    # =============================================================================
    # OFFLINE PLAYER METHODS (Direct Database Access)
    # =============================================================================
    
    async def get_inventory_offline(self, player_id: int) -> Dict[int, Dict]:
        """
        Get player inventory directly from database (for offline players).
        
        Args:
            player_id: Player ID
            
        Returns:
            Dictionary mapping slot numbers to item data
        """
        if not self._session_factory:
            return {}
            
        async with self._db_session() as db:
            from server.src.models.item import PlayerInventory
            
            result = await db.execute(
                select(PlayerInventory).where(PlayerInventory.player_id == player_id)
            )
            inventories = result.scalars().all()
            
            inventory_data = {}
            for inv in inventories:
                inventory_data[inv.slot] = {
                    "item_id": inv.item_id,
                    "quantity": inv.quantity,
                    "current_durability": inv.current_durability or 1.0
                }
            
            return inventory_data
    
    async def add_item_to_inventory_offline(
        self, player_id: int, item_id: int, quantity: int, durability: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Add item to player inventory directly in database (for offline players).
        
        Returns dictionary with success status and slot information.
        """
        if not self._session_factory:
            return {"success": False, "message": "No database connection"}
            
        async with self._db_session() as db:
            from server.src.models.item import PlayerInventory, Item
            from sqlalchemy import func
            
            # Get item data
            item_result = await db.execute(select(Item).where(Item.id == item_id))
            item = item_result.scalar_one_or_none()
            if not item:
                return {"success": False, "message": "Item not found"}
            
            # Set default durability
            if durability is None and item.max_durability is not None:
                durability = float(item.max_durability)
            elif durability is None:
                durability = 1.0
            
            # Try to stack with existing items first
            if item.max_stack_size > 1:
                existing_result = await db.execute(
                    select(PlayerInventory)
                    .where(PlayerInventory.player_id == player_id)
                    .where(PlayerInventory.item_id == item_id)
                    .where(PlayerInventory.quantity < item.max_stack_size)
                    .order_by(PlayerInventory.slot)
                )
                existing = existing_result.scalars().first()
                
                if existing:
                    space_available = item.max_stack_size - existing.quantity
                    add_amount = min(quantity, space_available)
                    existing.quantity += add_amount
                    await self._commit_if_not_test_session(db)
                    
                    remaining = quantity - add_amount
                    if remaining == 0:
                        return {
                            "success": True, 
                            "slot": existing.slot,
                            "message": f"Added {quantity} items to existing stack"
                        }
                    else:
                        quantity = remaining  # Continue with remaining
            
            # Find free slot
            max_slots = settings.INVENTORY_MAX_SLOTS
            used_slots_result = await db.execute(
                select(PlayerInventory.slot).where(PlayerInventory.player_id == player_id)
            )
            used_slots = {row[0] for row in used_slots_result}
            
            free_slot = None
            for slot in range(max_slots):
                if slot not in used_slots:
                    free_slot = slot
                    break
            
            if free_slot is None:
                return {"success": False, "message": "Inventory is full", "overflow_quantity": quantity}
            
            # Add new item
            new_inv = PlayerInventory(
                player_id=player_id,
                item_id=item_id,
                slot=free_slot,
                quantity=quantity,
                current_durability=durability
            )
            db.add(new_inv)
            await self._commit_if_not_test_session(db)
            
            return {
                "success": True, 
                "slot": free_slot,
                "message": f"Added {quantity} {item.display_name}"
            }
    
    async def remove_item_from_inventory_offline(
        self, player_id: int, slot: int, quantity: int = 1
    ) -> Dict[str, Any]:
        """
        Remove item from player inventory directly in database (for offline players).
        
        Returns dictionary with success status and removed quantity.
        """
        if not self._session_factory:
            return {"success": False, "message": "No database connection", "removed_quantity": 0}
            
        async with self._db_session() as db:
            from server.src.models.item import PlayerInventory
            
            result = await db.execute(
                select(PlayerInventory).where(
                    PlayerInventory.player_id == player_id,
                    PlayerInventory.slot == slot
                )
            )
            inv = result.scalar_one_or_none()
            
            if not inv:
                return {"success": False, "message": "Slot is empty", "removed_quantity": 0}
            
            if inv.quantity < quantity:
                return {
                    "success": False, 
                    "message": f"Not enough items (have {inv.quantity}, need {quantity})",
                    "removed_quantity": 0
                }
            
            inv.quantity -= quantity
            if inv.quantity == 0:
                await db.delete(inv)
            
            await self._commit_if_not_test_session(db)
            return {
                "success": True,
                "message": f"Removed {quantity} items",
                "removed_quantity": quantity
            }
    
    async def set_inventory_slot_offline(
        self, player_id: int, slot: int, item_id: int, quantity: int, durability: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Set item in specific inventory slot directly in database (for offline players).
        
        Args:
            player_id: Player's database ID
            slot: Inventory slot number
            item_id: Item ID to set
            quantity: Item quantity
            durability: Item durability
            
        Returns:
            Dictionary with success status
        """
        if not self._session_factory:
            return {"success": False, "message": "No database connection"}
            
        async with self._db_session() as db:
            from server.src.models.item import PlayerInventory, Item
            
            # Get item data for default durability
            if durability is None:
                item_result = await db.execute(select(Item).where(Item.id == item_id))
                item = item_result.scalar_one_or_none()
                if item and item.max_durability is not None:
                    durability = float(item.max_durability)
                else:
                    durability = 1.0
            
            # Check if slot already has an item
            existing_result = await db.execute(
                select(PlayerInventory).where(
                    PlayerInventory.player_id == player_id,
                    PlayerInventory.slot == slot
                )
            )
            existing_item = existing_result.scalar_one_or_none()
            
            if existing_item:
                # Update existing item in slot
                existing_item.item_id = item_id
                existing_item.quantity = quantity
                existing_item.current_durability = int(durability) if durability is not None else None
            else:
                # Create new inventory entry
                new_item = PlayerInventory(
                    player_id=player_id,
                    slot=slot,
                    item_id=item_id,
                    quantity=quantity,
                    current_durability=int(durability) if durability is not None else None
                )
                db.add(new_item)
            
            await self._commit_if_not_test_session(db)
            return {"success": True, "message": f"Set item in slot {slot}"}
    
    async def get_equipment_offline(self, player_id: int) -> Dict[str, Dict]:
        """
        Get player equipment directly from database (for offline players).
        
        Returns dictionary mapping equipment slot to item data.
        """
        if not self._session_factory:
            return {}
            
        async with self._db_session() as db:
            from server.src.models.item import PlayerEquipment
            
            result = await db.execute(
                select(PlayerEquipment).where(PlayerEquipment.player_id == player_id)
            )
            equipment = result.scalars().all()
            
            equipment_data = {}
            for eq in equipment:
                equipment_data[eq.equipment_slot] = {
                    "item_id": eq.item_id,
                    "quantity": eq.quantity,
                    "current_durability": eq.current_durability or 1.0
                }
            
            return equipment_data
    
    async def get_skills_offline(self, player_id: int) -> Dict[str, Dict]:
        """
        Get player skills directly from database (for offline players).
        
        Returns dictionary mapping skill name to skill data.
        """
        if not self._session_factory:
            return {}
            
        async with self._db_session() as db:
            from server.src.models.skill import PlayerSkill, Skill
            
            result = await db.execute(
                select(PlayerSkill, Skill.name)
                .join(Skill)
                .where(PlayerSkill.player_id == player_id)
            )
            skills = result.all()
            
            skill_data = {}
            for player_skill, skill_name in skills:
                skill_data[skill_name] = {
                    "level": player_skill.current_level,
                    "experience": player_skill.experience
                }
            
            return skill_data

    async def sync_skills_to_db_offline(self) -> list:
        """
        Ensure all SkillType entries exist in the skills table.
        
        Returns:
            List of all Skill records in the database
        """
        if not self._session_factory:
            return []
            
        async with self._db_session() as db:
            from server.src.models.skill import Skill
            from server.src.core.skills import SkillType
            
            skill_names = SkillType.all_skill_names()
            
            # Get existing skills
            result = await db.execute(select(Skill))
            existing_skills = {s.name: s for s in result.scalars().all()}
            
            # Insert missing skills
            for skill_name in skill_names:
                if skill_name not in existing_skills:
                    new_skill = Skill(name=skill_name)
                    db.add(new_skill)
            
            await self._commit_if_not_test_session(db)
            
            # Return all skills
            result = await db.execute(select(Skill))
            return list(result.scalars().all())
    
    async def get_skill_id_map_offline(self) -> Dict[str, int]:
        """
        Get a mapping of skill names to their database IDs.
        
        Returns:
            Dict mapping lowercase skill name to skill ID
        """
        if not self._session_factory:
            return {}
            
        async with self._db_session() as db:
            from server.src.models.skill import Skill
            
            result = await db.execute(select(Skill))
            return {s.name: s.id for s in result.scalars().all()}
    
    async def grant_all_skills_to_player_offline(self, player_id: int) -> list:
        """
        Create PlayerSkill rows for all skills for offline players.
        
        Args:
            player_id: The players database ID
            
        Returns:
            List of all PlayerSkill records for the player
        """
        if not self._session_factory:
            return []
            
        async with self._db_session() as db:
            from server.src.models.skill import PlayerSkill, Skill
            from server.src.core.skills import (
                SkillType, get_skill_xp_multiplier, xp_for_level, HITPOINTS_START_LEVEL
            )
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            
            skill_id_map = await self.get_skill_id_map_offline()
            
            if not skill_id_map:
                # No skills in database yet, sync them first
                await self.sync_skills_to_db_offline()
                skill_id_map = await self.get_skill_id_map_offline()
            
            if not skill_id_map:
                # Still no skills, return empty list
                return []
            
            # Calculate XP needed for Hitpoints starting level
            hitpoints_xp_multiplier = get_skill_xp_multiplier(SkillType.HITPOINTS)
            hitpoints_start_xp = xp_for_level(HITPOINTS_START_LEVEL, hitpoints_xp_multiplier)
            
            # Build values for all skills in a single INSERT
            values = []
            for skill_name, skill_id in skill_id_map.items():
                if skill_name == "hitpoints":
                    # Hitpoints starts at level 10
                    values.append({
                        "player_id": player_id,
                        "skill_id": skill_id,
                        "current_level": HITPOINTS_START_LEVEL,
                        "experience": hitpoints_start_xp,
                    })
                else:
                    # All other skills start at level 1 with 0 XP
                    values.append({
                        "player_id": player_id,
                        "skill_id": skill_id,
                        "current_level": 1,
                        "experience": 0,
                    })
            
            # Use INSERT ON CONFLICT DO NOTHING for idempotency
            stmt = pg_insert(PlayerSkill).values(values)
            stmt = stmt.on_conflict_do_nothing(constraint="_player_skill_uc")
            await db.execute(stmt)
            await self._commit_if_not_test_session(db)
            
            # Fetch and return all player skills
            result = await db.execute(
                select(PlayerSkill).where(PlayerSkill.player_id == player_id)
            )
            player_skills = list(result.scalars().all())
            
            logger.info(
                "Granted skills to player via GSM",
                extra={"player_id": player_id, "total_skills": len(player_skills)},
            )
            
            return player_skills
    
    async def add_experience_offline(self, player_id: int, skill_name: str, xp_amount: int) -> Optional[Dict[str, Any]]:
        """
        Add experience to a players skill (offline).
        
        Args:
            player_id: Player ID
            skill_name: Skill name (lowercase)
            xp_amount: Amount of XP to add
            
        Returns:
            Dict with level up result or None if skill not found
        """
        if not self._session_factory or xp_amount <= 0:
            return None
            
        async with self._db_session() as db:
            from server.src.models.skill import PlayerSkill, Skill
            from server.src.core.skills import (
                SkillType, get_skill_xp_multiplier, level_for_xp, xp_to_next_level, MAX_LEVEL
            )
            
            # Get the skill ID
            skill_result = await db.execute(select(Skill).where(Skill.name == skill_name))
            skill_record = skill_result.scalar_one_or_none()
            
            if skill_record is None:
                return None
            
            # Get player's current progress
            result = await db.execute(
                select(PlayerSkill).where(
                    PlayerSkill.player_id == player_id,
                    PlayerSkill.skill_id == skill_record.id,
                )
            )
            player_skill = result.scalar_one_or_none()
            
            if player_skill is None:
                return None
            
            # Get skill type and multiplier
            skill_type = SkillType.from_name(skill_name)
            if skill_type is None:
                return None
                
            xp_multiplier = get_skill_xp_multiplier(skill_type)
            
            previous_level = player_skill.current_level
            previous_xp = player_skill.experience
            
            # Calculate new XP and level
            new_xp = previous_xp + xp_amount
            new_level = level_for_xp(new_xp, xp_multiplier)
            
            # Cap at max level
            if new_level > MAX_LEVEL:
                new_level = MAX_LEVEL
            
            # Update the record
            player_skill.experience = new_xp
            player_skill.current_level = new_level
            
            await self._commit_if_not_test_session(db)
            
            leveled_up = new_level > previous_level
            if leveled_up:
                logger.info(
                    "Player leveled up via GSM offline",
                    extra={
                        "player_id": player_id,
                        "skill": skill_name,
                        "previous_level": previous_level,
                        "new_level": new_level,
                        "xp_gained": xp_amount,
                    },
                )
            
            return {
                "skill_name": skill_type.value.name,
                "previous_level": previous_level,
                "new_level": new_level,
                "current_xp": new_xp,
                "xp_to_next": xp_to_next_level(new_xp, xp_multiplier),
                "leveled_up": leveled_up,
                "levels_gained": new_level - previous_level,
            }
    
    async def get_player_skills_offline(self, player_id: int) -> list:
        """
        Fetch all skills for a player with computed metadata (offline).
        
        Args:
            player_id: Player ID
            
        Returns:
            List of skill info dicts with name, category, level, xp, etc.
        """
        if not self._session_factory:
            return []
            
        async with self._db_session() as db:
            from server.src.models.skill import PlayerSkill, Skill
            from server.src.core.skills import (
                SkillType, get_skill_xp_multiplier, xp_for_level, xp_to_next_level,
                progress_to_next_level, MAX_LEVEL
            )
            
            result = await db.execute(
                select(PlayerSkill, Skill)
                .join(Skill, PlayerSkill.skill_id == Skill.id)
                .where(PlayerSkill.player_id == player_id)
            )
            
            skills_data = []
            for player_skill, skill in result.all():
                skill_type = SkillType.from_name(skill.name)
                if skill_type is None:
                    continue
                
                xp_multiplier = get_skill_xp_multiplier(skill_type)
                current_xp = player_skill.experience
                current_level = player_skill.current_level
                
                skills_data.append({
                    "name": skill_type.value.name,
                    "category": skill_type.value.category.value,
                    "description": skill_type.value.description,
                    "current_level": current_level,
                    "experience": current_xp,
                    "xp_for_current_level": xp_for_level(current_level, xp_multiplier),
                    "xp_for_next_level": xp_for_level(current_level + 1, xp_multiplier) if current_level < MAX_LEVEL else 0,
                    "xp_to_next_level": xp_to_next_level(current_xp, xp_multiplier),
                    "xp_multiplier": xp_multiplier,
                    "progress_percent": progress_to_next_level(current_xp, xp_multiplier),
                    "max_level": MAX_LEVEL,
                })
            
            return skills_data
    
    async def get_total_level_offline(self, player_id: int) -> int:
        """
        Calculate the sum of all skill levels for a player (offline).
        
        Args:
            player_id: Player ID
            
        Returns:
            Total level across all skills
        """
        if not self._session_factory:
            return 0
            
        async with self._db_session() as db:
            from server.src.models.skill import PlayerSkill
            
            result = await db.execute(
                select(PlayerSkill).where(PlayerSkill.player_id == player_id)
            )
            player_skills = result.scalars().all()
            return sum(ps.current_level for ps in player_skills)
    
    async def get_hitpoints_level_offline(self, player_id: int) -> int:
        """
        Get the players Hitpoints skill level (offline).
        
        Args:
            player_id: Player ID
            
        Returns:
            Hitpoints level
        """
        if not self._session_factory:
            from server.src.core.skills import HITPOINTS_START_LEVEL
            return HITPOINTS_START_LEVEL
            
        async with self._db_session() as db:
            from server.src.models.skill import PlayerSkill, Skill
            from server.src.core.skills import HITPOINTS_START_LEVEL
            
            # Get the hitpoints skill ID
            skill_result = await db.execute(
                select(Skill).where(Skill.name == "hitpoints")
            )
            skill_record = skill_result.scalar_one_or_none()
            
            if skill_record is None:
                return HITPOINTS_START_LEVEL
            
            # Get player's hitpoints level
            result = await db.execute(
                select(PlayerSkill).where(
                    PlayerSkill.player_id == player_id,
                    PlayerSkill.skill_id == skill_record.id,
                )
            )
            player_skill = result.scalar_one_or_none()
            
            if player_skill is None:
                return HITPOINTS_START_LEVEL
            
            return player_skill.current_level

    # =========================================================================
    # CORE DATA ACCESS METHODS (for GSM-centric architecture)
    # =========================================================================
    
    async def get_player_id_by_username(self, username: str) -> Optional[int]:
        """
        Get player ID by username from online registry or database.
        
        Args:
            username: Player's username
            
        Returns:
            Player ID if found, None otherwise
        """
        # First check online players registry
        if self._valkey:
            for player_id in self._online_players:
                try:
                    # Get cached player state if available
                    player_state = await self.get_player_full_state(player_id)
                    if player_state and player_state.get("username") == username:
                        return player_id
                except Exception:
                    continue
        
        # Fall back to database lookup
        if not self._session_factory:
            return None
            
        async with self._db_session() as db:
            from server.src.models.player import Player
            
            result = await db.execute(
                select(Player.id).where(Player.username == username)
            )
            return result.scalar_one_or_none()
    
    async def get_player_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Get complete player data by username.
        
        Args:
            username: Player's username
            
        Returns:
            Player data dictionary or None if not found
        """
        if not self._session_factory:
            return None
            
        async with self._db_session() as db:
            from server.src.models.player import Player
            
            result = await db.execute(
                select(Player).where(Player.username == username)
            )
            player = result.scalar_one_or_none()
            
            if not player:
                return None
                
            return {
                "id": player.id,
                "username": player.username,
                "x": player.x,
                "y": player.y,
                "map_id": player.map_id,
                "current_hp": player.current_hp,
                "is_admin": player.is_admin,
            }
    
    async def update_player_hp(self, player_id: int, hp: int) -> None:
        """
        Update player's current HP in database and cache.
        
        Args:
            player_id: Player's database ID
            hp: New HP value
        """
        # Update online cache if player is online
        if self.is_online(player_id):
            # Get current state and update HP
            current_state = await self.get_player_full_state(player_id)
            if current_state:
                await self.set_player_state(
                    player_id,
                    current_state.get("x", 0),
                    current_state.get("y", 0),
                    current_state.get("map_id", ""),
                    hp,
                    current_state.get("max_hp", hp)
                )
        
        # Always update database
        if not self._session_factory:
            return
            
        async with self._db_session() as db:
            from server.src.models.player import Player
            
            result = await db.execute(
                select(Player).where(Player.id == player_id)
            )
            player = result.scalar_one_or_none()
            
            if player:
                player.current_hp = hp
                await self._commit_if_not_test_session(db)

    # =========================================================================
    # ITEM METADATA ACCESS (Simple caching)
    # =========================================================================
    
    async def get_item_meta(self, item_id: int) -> Optional[Dict[str, Any]]:
        """
        Get item metadata with caching.
        
        Args:
            item_id: Item's database ID
            
        Returns:
            Item metadata dictionary or None if not found
        """
        # Check cache first
        if hasattr(self, '_item_cache') and item_id in self._item_cache:
            return self._item_cache[item_id]
        
        # Load from database
        if not self._session_factory:
            return None
            
        async with self._db_session() as db:
            from server.src.models.item import Item
            
            result = await db.execute(
                select(Item).where(Item.id == item_id)
            )
            item = result.scalar_one_or_none()
            
            if not item:
                return None
                
            item_data = {
                "id": item.id,
                "name": item.name,
                "description": item.description,
                "equippable": item.equippable,
                "equipment_slot": item.equipment_slot,
                "health_bonus": item.health_bonus or 0,
                "attack_bonus": item.attack_bonus or 0,
                "defense_bonus": item.defense_bonus or 0,
                "stackable": item.stackable,
                "max_durability": item.max_durability,
            }
            
            # Cache for future use
            if not hasattr(self, '_item_cache'):
                self._item_cache = {}
            self._item_cache[item_id] = item_data
            
            return item_data
    
    async def get_items_meta(self, item_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        """
        Get metadata for multiple items efficiently.
        
        Args:
            item_ids: List of item database IDs
            
        Returns:
            Dictionary mapping item_id to item metadata
        """
        if not item_ids:
            return {}
            
        result = {}
        missing_ids = []
        
        # Check cache first
        if hasattr(self, '_item_cache'):
            for item_id in item_ids:
                if item_id in self._item_cache:
                    result[item_id] = self._item_cache[item_id]
                else:
                    missing_ids.append(item_id)
        else:
            missing_ids = list(item_ids)
            self._item_cache = {}
        
        # Load missing items from database
        if missing_ids and self._session_factory:
            async with self._db_session() as db:
                from server.src.models.item import Item
                
                db_result = await db.execute(
                    select(Item).where(Item.id.in_(missing_ids))
                )
                items = db_result.scalars().all()
                
                for item in items:
                    item_data = {
                        "id": item.id,
                        "name": item.name,
                        "description": item.description,
                        "equippable": item.equippable,
                        "equipment_slot": item.equipment_slot,
                        "health_bonus": item.health_bonus or 0,
                        "attack_bonus": item.attack_bonus or 0,
                        "defense_bonus": item.defense_bonus or 0,
                        "stackable": item.stackable,
                        "max_durability": item.max_durability,
                    }
                    
                    # Cache and add to result
                    self._item_cache[item.id] = item_data
                    result[item.id] = item_data
        
        return result
    
    async def preload_item_cache(self) -> None:
        """
        Preload all item metadata into cache for performance.
        """
        if not self._session_factory:
            return
            
        async with self._db_session() as db:
            from server.src.models.item import Item
            
            result = await db.execute(select(Item))
            items = result.scalars().all()
            
            self._item_cache = {}
            for item in items:
                item_data = {
                    "id": item.id,
                    "name": item.name,
                    "description": item.description,
                    "equippable": item.equippable,
                    "equipment_slot": item.equipment_slot,
                    "health_bonus": item.health_bonus or 0,
                    "attack_bonus": item.attack_bonus or 0,
                    "defense_bonus": item.defense_bonus or 0,
                    "stackable": item.stackable,
                    "max_durability": item.max_durability,
                }
                self._item_cache[item.id] = item_data
        
        logger.info(
            "Preloaded item cache",
            extra={"item_count": len(getattr(self, '_item_cache', {}))}
        )


# =============================================================================
# SINGLETON MANAGEMENT
# =============================================================================

_game_state_manager: Optional[GameStateManager] = None


def init_game_state_manager(
    valkey_client: GlideClient, 
    session_factory: sessionmaker
) -> GameStateManager:
    """
    Initialize the global GameStateManager singleton.
    
    Args:
        valkey_client: Valkey client for hot cache
        session_factory: SQLAlchemy session factory
        
    Returns:
        Initialized GameStateManager instance
    """
    global _game_state_manager
    _game_state_manager = GameStateManager(valkey_client, session_factory)
    return _game_state_manager


def get_game_state_manager() -> GameStateManager:
    """
    Get the global GameStateManager singleton.
    
    Returns:
        GameStateManager instance
        
    Raises:
        RuntimeError: If GSM not initialized
    """
    if _game_state_manager is None:
        raise RuntimeError("GameStateManager not initialized")
    return _game_state_manager


def reset_game_state_manager() -> None:
    """Reset the global GameStateManager singleton (for testing)."""
    global _game_state_manager
    _game_state_manager = None