"""
GameStateManager - Single source of truth for all game state.

This module provides a modular GameStateManager with helper classes to keep
file sizes manageable while maintaining clear separation of concerns.
"""

import asyncio
import json
import traceback
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

from glide import GlideClient
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, sessionmaker

from server.src.core.config import settings
from server.src.core.logging_config import get_logger
from common.src.protocol import Direction

from .state_access import GSMStateAccess
from .batch_operations import GSMBatchOps  
from .atomic_operations import GSMAtomicOperations  

if TYPE_CHECKING:
    from server.src.core.skills import SkillType
    from server.src.core.items import EquipmentSlot  
    from server.src.core.entities import EntityState, EntityType
    from common.src.protocol import CombatTargetType, PlayerSettingKey  


logger = get_logger(__name__)


# =============================================================================
# PLAYER DATA STORAGE PATTERNS
# =============================================================================

# Player state keys (all use player_id for consistency)
PLAYER_KEY = "player:{player_id}"
INVENTORY_KEY = "inventory:{player_id}"
EQUIPMENT_KEY = "equipment:{player_id}"
SKILLS_KEY = "skills:{player_id}"
PLAYER_SETTINGS_KEY = "player_settings:{player_id}"
PLAYER_COMBAT_STATE_KEY = "player_combat_state:{player_id}"

# Ground item keys
GROUND_ITEM_KEY = "ground_item:{ground_item_id}"
GROUND_ITEMS_MAP_KEY = "ground_items:map:{map_id}"
GROUND_ITEMS_NEXT_ID_KEY = "ground_items:next_id"

# Entity instance keys (ephemeral, Valkey-only)
ENTITY_INSTANCE_KEY = "entity_instance:{instance_id}"
MAP_ENTITIES_KEY = "map_entities:{map_id}"
ENTITY_INSTANCE_COUNTER_KEY = "entity_instance_counter"
ENTITY_RESPAWN_QUEUE_KEY = "entity_respawn_queue"

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
    
    Manages player position, inventory, equipment, skills, and ground items
    for real-time multiplayer gameplay.
    
    Design principles:
    - Online players get real-time state updates
    - Efficient persistence for game progression  
    - Consistent player identification across sessions
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
            valkey_client: Cache client for real-time data
            session_factory: Database session factory for persistence
        """
        self._valkey = valkey_client
        self._session_factory = session_factory
        
        # Online player registry (in-memory)
        self._online_players: Set[int] = set()
        self._username_to_id: Dict[str, int] = {}
        self._id_to_username: Dict[int, str] = {}
        
        # Reference data cache (loaded at startup for game consistency)
        self._item_cache: Dict[int, Dict[str, Any]] = {}
        
        # Test session binding (for test isolation)
        self._bound_test_session: Optional[AsyncSession] = None
        
        # Initialize helper classes
        self.state_access = GSMStateAccess(self)
        self.batch_ops = GSMBatchOps(self)
        self.atomic_ops = GSMAtomicOperations(self)
        
        logger.info("GameStateManager initialized")
    
    @property
    def valkey(self) -> Optional[GlideClient]:
        """Get cache client."""
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
    # ENTITY DEFINITION OPERATIONS
    # =========================================================================
    
    async def sync_entities_to_database(self) -> None:
        """
        Sync HumanoidID and MonsterID enum definitions to the 'entities' database table.
        Mirroring the pattern used for Items.
        """
        from server.src.core.humanoids import HumanoidID
        from server.src.core.monsters import MonsterID
        from server.src.services.entity_service import EntityService

        logger.info("Syncing entities to database...")
        
        if not self._session_factory:
            logger.warning("Cannot sync entities - no database connection")
            return

        async with self._db_session() as db:
            from server.src.models.entity import Entity
            from sqlalchemy.dialects.postgresql import insert
            
            count = 0
            
            # Sync humanoid NPCs
            for humanoid_enum in HumanoidID:
                humanoid_def = humanoid_enum.value
                humanoid_name = humanoid_enum.name
                
                # Convert definition to dict
                entity_data = EntityService.entity_def_to_dict(humanoid_name, humanoid_def)
                
                # Upsert
                stmt = insert(Entity).values(**entity_data)
                stmt = stmt.on_conflict_do_update(
                    index_elements=['name'],
                    set_=entity_data
                )
                
                await db.execute(stmt)
                count += 1
            
            # Sync monsters
            for monster_enum in MonsterID:
                monster_def = monster_enum.value
                monster_name = monster_enum.name
                
                # Convert definition to dict
                entity_data = EntityService.entity_def_to_dict(monster_name, monster_def)
                
                # Upsert
                stmt = insert(Entity).values(**entity_data)
                stmt = stmt.on_conflict_do_update(
                    index_elements=['name'],
                    set_=entity_data
                )
                
                await db.execute(stmt)
                count += 1
            
            await self._commit_if_not_test_session(db)
        logger.info(f"Synced {count} entities to database.")

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
            logger.error(
                "Failed to load item cache",
                extra={
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }
            )
            raise
    
    def get_cached_item_meta(self, item_id: int) -> Optional[Dict[str, Any]]:
        """
        Get cached item metadata by ID.
        
        Args:
            item_id: Item ID
            
        Returns:
            Item metadata dict or None if not found
        """
        return self._item_cache.get(item_id)
    
    def get_all_cached_items(self) -> Dict[int, Dict[str, Any]]:
        """
        Get all cached item metadata.
        
        Returns:
            Dictionary mapping item IDs to their metadata
        """
        return dict(self._item_cache)  # Return a copy to prevent external modification
    
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
    
    async def unregister_online_player(self, player_id: int) -> None:
        """
        Unregister a player from online status.
        Immediately syncs player data to database and removes from cache.
        
        Args:
            player_id: Player's ID
        """
        # Get username before removing from registry
        username = self._id_to_username.get(player_id, f"player_{player_id}")
        
        # Remove from online status first
        self._online_players.discard(player_id)
        
        # Remove from username mappings
        if username and username != f"player_{player_id}":
            self._username_to_id.pop(username, None)
        self._id_to_username.pop(player_id, None)
        
        # Immediately sync all player data to database
        try:
            await self.sync_player_to_db(player_id, username)
            logger.debug(
                "Player data synced to database on logout",
                extra={"player_id": player_id, "username": username}
            )
        except Exception as e:
            logger.error(
                "Failed to sync player data on logout", 
                extra={
                    "player_id": player_id,
                    "username": username,
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }
            )
            # Continue with cleanup even if sync fails
        
        # Remove all player data from cache immediately
        try:
            await self.cleanup_player_state(player_id)
            logger.debug(
                "Player cache cleaned up on logout",
                extra={"player_id": player_id, "username": username}
            )
        except Exception as e:
            logger.error(
                "Failed to cleanup player cache on logout",
                extra={
                    "player_id": player_id,
                    "username": username,
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }
            )
        
        logger.debug(
            "Player unregistered from online with immediate sync and cleanup",
            extra={"player_id": player_id, "username": username}
        )
    
    def is_online(self, player_id: int) -> bool:
        """Check if a player is online."""
        return player_id in self._online_players
    
    def get_active_player_count(self) -> int:
        """
        Get count of currently active online players.
        Used for server capacity management and monitoring.
        
        Returns:
            Number of players currently registered as online
        """
        return len(self._online_players)
    
    # =========================================================================
    # PLAYER POSITION & HP
    # =========================================================================
    
    async def get_player_position(self, player_id: int) -> Optional[Dict[str, Any]]:
        """
        Get player position from game session cache.
        
        Args:
            player_id: Player's database ID
            
        Returns:
            Dict with x, y, map_id, last_movement_time or None if not found
        """
        # Configuration-based mode selection
        if not settings.USE_VALKEY:
            logger.debug("Position access not available in database-only mode", extra={"player_id": player_id})
            return None
        
        # Valkey mode - fail fast if unavailable
        if not self._valkey:
            logger.error("Valkey client required but unavailable for position access", 
                        extra={"player_id": player_id})
            raise RuntimeError("Cache infrastructure unavailable - check Valkey connection")
        
        # Check if player is online
        if not self.is_online(player_id):
            return None
        
        key = PLAYER_KEY.format(player_id=player_id)
        raw = await self._valkey.hgetall(key)
        
        if not raw:
            return None
        
        try:
            return {
                "x": int(_decode_bytes(raw.get(b"x", b"0"))),
                "y": int(_decode_bytes(raw.get(b"y", b"0"))), 
                "map_id": _decode_bytes(raw.get(b"map_id", b"")),
                "last_movement_time": float(_decode_bytes(raw.get(b"last_move_time", b"0")))
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
        # Configuration-based mode selection
        if not settings.USE_VALKEY:
            logger.debug("HP access not available in database-only mode", extra={"player_id": player_id})
            return None
        
        # Valkey mode - fail fast if unavailable
        if not self._valkey:
            logger.error("Valkey client required but unavailable for HP access", 
                        extra={"player_id": player_id})
            raise RuntimeError("Cache infrastructure unavailable - check Valkey connection")
        
        # Check if player is online
        if not self.is_online(player_id):
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
        # Configuration-based mode selection
        if not settings.USE_VALKEY:
            logger.debug("HP updates not available in database-only mode", extra={"player_id": player_id})
            return
        
        # Valkey mode - fail fast if unavailable
        if not self._valkey:
            logger.error("Valkey client required but unavailable for HP update", 
                        extra={"player_id": player_id})
            raise RuntimeError("Cache infrastructure unavailable - check Valkey connection")
        
        # Check if player is online
        if not self.is_online(player_id):
            return
        
        key = PLAYER_KEY.format(player_id=player_id)
        update_data = {"current_hp": str(current_hp)}
        if max_hp is not None:
            update_data["max_hp"] = str(max_hp)
        
        await self._valkey.hset(key, update_data)
        await self._valkey.sadd(DIRTY_POSITION_KEY, [str(player_id)])
    
    async def get_player_settings(self, player_id: int) -> Dict[str, Any]:
        """
        Get player's game settings (auto-retaliate, etc).
        
        Args:
            player_id: Player's database ID
            
        Returns:
            Dict with settings, defaults if not found
        """
        if not settings.USE_VALKEY or not self._valkey:
            return {"auto_retaliate": True}
        
        key = PLAYER_SETTINGS_KEY.format(player_id=player_id)
        raw = await self._valkey.hgetall(key)
        
        if not raw:
            return {"auto_retaliate": True}
        
        player_settings = {}
        for field, value in raw.items():
            field_str = _decode_bytes(field)
            value_str = _decode_bytes(value)
            
            if field_str == "auto_retaliate":
                player_settings[field_str] = value_str.lower() == "true"
            else:
                player_settings[field_str] = value_str
        
        return player_settings
    
    async def set_player_setting(
        self, player_id: int, setting_key: "PlayerSettingKey", value: Any
    ) -> None:
        """
        Update a specific player setting.
        
        Args:
            player_id: Player's database ID
            setting_key: PlayerSettingKey enum value (e.g., PlayerSettingKey.AUTO_RETALIATE)
            value: New value
        """
        if not settings.USE_VALKEY or not self._valkey:
            return
        
        key = PLAYER_SETTINGS_KEY.format(player_id=player_id)
        
        if isinstance(value, bool):
            str_value = "true" if value else "false"
        else:
            str_value = str(value)
        
        await self._valkey.hset(key, {setting_key.value: str_value})
    
    async def set_player_combat_state(
        self,
        player_id: int,
        target_type: "CombatTargetType",
        target_id: int,
        last_attack_tick: int,
        attack_speed: float,
    ) -> None:
        """
        Set player's active combat target.
        
        Args:
            player_id: Player's database ID
            target_type: CombatTargetType.ENTITY or CombatTargetType.PLAYER
            target_id: Target's ID
            last_attack_tick: Tick when last attack occurred
            attack_speed: Weapon attack speed in seconds
        """
        if not settings.USE_VALKEY or not self._valkey:
            return
        
        key = PLAYER_COMBAT_STATE_KEY.format(player_id=player_id)
        combat_state = {
            "target_type": target_type.value,
            "target_id": str(target_id),
            "last_attack_tick": str(last_attack_tick),
            "attack_speed": str(attack_speed),
            "started_at_tick": str(last_attack_tick),
        }
        
        await self._valkey.hset(key, combat_state)
    
    async def get_player_combat_state(self, player_id: int) -> Optional[Dict[str, Any]]:
        """
        Get player's combat state or None if not in combat.
        
        Args:
            player_id: Player's database ID
            
        Returns:
            Combat state dict or None
        """
        if not settings.USE_VALKEY or not self._valkey:
            return None
        
        key = PLAYER_COMBAT_STATE_KEY.format(player_id=player_id)
        raw = await self._valkey.hgetall(key)
        
        if not raw:
            return None
        
        combat_state = {}
        for field, value in raw.items():
            field_str = _decode_bytes(field)
            value_str = _decode_bytes(value)
            
            if field_str in ["target_id", "last_attack_tick", "started_at_tick"]:
                combat_state[field_str] = int(value_str)
            elif field_str == "attack_speed":
                combat_state[field_str] = float(value_str)
            else:
                combat_state[field_str] = value_str
        
        return combat_state
    
    async def clear_player_combat_state(self, player_id: int) -> None:
        """
        Stop player's auto-attack (clear combat state).
        
        Args:
            player_id: Player's database ID
        """
        if not settings.USE_VALKEY or not self._valkey:
            return
        
        key = PLAYER_COMBAT_STATE_KEY.format(player_id=player_id)
        await self._valkey.delete([key])
    
    async def get_all_players_in_combat(self) -> List[Dict[str, Any]]:
        """
        Get all online players currently in combat.
        
        Used by game loop to process auto-attacks.
        
        Returns:
            List of {player_id, combat_state} dicts
        """
        if not settings.USE_VALKEY or not self._valkey:
            return []
        
        players_in_combat = []
        
        for player_id in self._online_players:
            combat_state = await self.get_player_combat_state(player_id)
            if combat_state:
                players_in_combat.append({
                    "player_id": player_id,
                    "combat_state": combat_state,
                })
        
        return players_in_combat
    
    async def get_player_full_state(self, player_id: int) -> Optional[Dict[str, Any]]:
        """
        Get complete player state from Valkey.
        
        Args:
            player_id: Player's database ID
            
        Returns:
            Dict with all player state or None if not found
        """
        # Configuration-based mode selection
        if not settings.USE_VALKEY:
            logger.debug("Full state access not available in database-only mode", extra={"player_id": player_id})
            return None
        
        # Valkey mode - fail fast if unavailable
        if not self._valkey:
            logger.error("Valkey client required but unavailable for state access", 
                        extra={"player_id": player_id})
            raise RuntimeError("Cache infrastructure unavailable - check Valkey connection")
        
        # Check if player is online
        if not self.is_online(player_id):
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
            
            # Convert numeric fields (excluding player_id which should remain as string for consistency)
            if field_str in ["x", "y", "current_hp", "max_hp"]:
                state[field_str] = int(value_str) if value_str.isdigit() else 0
            elif field_str == "appearance":
                # Parse appearance JSON
                try:
                    state[field_str] = json.loads(value_str)
                except json.JSONDecodeError:
                    state[field_str] = None
            else:
                state[field_str] = value_str
        
        # Add username if available
        username = self._id_to_username.get(player_id)
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
        update_movement_time: bool = True,
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
            update_movement_time: Whether to update last_move_time (default True)
        """
        # Configuration-based mode selection
        if not settings.USE_VALKEY:
            logger.debug("State updates not available in database-only mode", extra={"player_id": player_id})
            return
        
        # Valkey mode - fail fast if unavailable
        if not self._valkey:
            logger.error("Valkey client required but unavailable for state update", 
                        extra={"player_id": player_id})
            raise RuntimeError("Cache infrastructure unavailable - check Valkey connection")
        
        # Check if player is online
        if not self.is_online(player_id):
            return
        
        import time
        key = PLAYER_KEY.format(player_id=player_id)
        state_data = {
            "x": str(x),
            "y": str(y),
            "map_id": map_id,
            "current_hp": str(current_hp),
            "max_hp": str(max_hp),
            "player_id": str(player_id),
            "facing_direction": Direction.DOWN.value,
            "is_moving": "false",
        }
        
        # Update movement time if requested (for actual movement, not initialization)
        if update_movement_time:
            state_data["last_move_time"] = str(time.time())
        else:
            # Preserve existing last_move_time or set to 0 if new player
            existing_data = await self._valkey.hgetall(key)
            if existing_data and b"last_move_time" in existing_data:
                state_data["last_move_time"] = _decode_bytes(existing_data[b"last_move_time"])
            else:
                state_data["last_move_time"] = "0"
        
        await self._valkey.hset(key, state_data)
        await self._valkey.sadd(DIRTY_POSITION_KEY, [str(player_id)])
    
    # =========================================================================
    # INVENTORY OPERATIONS
    # =========================================================================
    
    async def get_inventory(self, player_id: int) -> Dict[int, Dict]:
        """
        Get player's inventory data for game session.
        
        Args:
            player_id: Player's database ID
            
        Returns:
            Dict mapping slot number to item data
        """
        from server.src.core.config import settings
        
        # Configuration-based mode selection
        if not settings.USE_VALKEY:
            logger.debug("Using database-only mode for inventory access", extra={"player_id": player_id})
            return await self.get_inventory_offline(player_id)
        
        # Valkey mode - fail fast if unavailable  
        if not self._valkey:
            logger.error("Valkey client required but unavailable for inventory access", 
                        extra={"player_id": player_id})
            raise RuntimeError("Cache infrastructure unavailable - check Valkey connection")
        
        # Valkey operations (no fallback)
        key = INVENTORY_KEY.format(player_id=player_id)
        raw = await self._valkey.hgetall(key)
        
        # Load player inventory data if not currently available
        if not raw:
            logger.debug("Loading player inventory data", extra={"player_id": player_id})
            inventory_data = await self.get_inventory_offline(player_id)
            
            # Cache for session performance
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
        """Cache inventory data for session performance."""
        from server.src.core.config import settings
        
        if not settings.USE_VALKEY or not self._valkey or not inventory_data:
            return
        
        key = INVENTORY_KEY.format(player_id=player_id)
        valkey_data = {}
        
        for slot, item_data in inventory_data.items():
            valkey_data[str(slot)] = json.dumps(item_data)
        
        await self._valkey.hset(key, valkey_data)
        
        # Manage session cache lifetime for offline players
        if not self.is_online(player_id):
            await self._valkey.expire(key, settings.OFFLINE_PLAYER_CACHE_TTL)

    async def _cache_skills_in_valkey(self, player_id: int, skills_data: Dict[str, Dict]) -> None:
        """Cache skills data for session performance."""
        from server.src.core.config import settings
        
        if not settings.USE_VALKEY or not self._valkey or not skills_data:
            return
        
        key = SKILLS_KEY.format(player_id=player_id)
        valkey_data = {}
        
        for skill_name, skill_data in skills_data.items():
            valkey_data[skill_name.lower()] = json.dumps(skill_data)
        
        await self._valkey.hset(key, valkey_data)
        
        # Manage session cache lifetime for offline players
        if not self.is_online(player_id):
            await self._valkey.expire(key, settings.OFFLINE_PLAYER_CACHE_TTL)
    
    async def get_inventory_slot(
        self, player_id: int, slot: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get item in specific inventory slot for player session.
        
        Args:
            player_id: Player's database ID
            slot: Inventory slot number
            
        Returns:
            Item data dict or None if empty
        """
        from server.src.core.config import settings
        
        # Configuration-based mode selection
        if not settings.USE_VALKEY:
            logger.debug("Using database-only mode for inventory slot access", extra={"player_id": player_id, "slot": slot})
            inventory_data = await self.get_inventory_offline(player_id)
            return inventory_data.get(slot)
        
        # Valkey mode - fail fast if unavailable
        if not self._valkey:
            logger.error("Valkey client required but unavailable for inventory slot access", 
                        extra={"player_id": player_id, "slot": slot})
            raise RuntimeError("Cache infrastructure unavailable - check Valkey connection")
        
        # Valkey operations (no fallback)
        key = INVENTORY_KEY.format(player_id=player_id)
        raw = await self._valkey.hget(key, str(slot))
        
        # Load inventory data if slot not currently available
        if not raw:
            logger.debug("Loading inventory data for slot access", extra={"player_id": player_id, "slot": slot})
            inventory_data = await self.get_inventory(player_id)  # This will load if needed
            return inventory_data.get(slot)
        
        try:
            return json.loads(_decode_bytes(raw))
        except ValueError as e:
            logger.error(
                "Failed to parse inventory slot data", 
                extra={
                    "player_id": player_id,
                    "slot": slot,
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }
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
        Update item in inventory slot for player session.
        
        Args:
            player_id: Player's database ID  
            slot: Inventory slot number
            item_id: Item ID
            quantity: Item quantity
            durability: Item durability (0.0 to 1.0)
        """
        from server.src.core.config import settings
        
        # Configuration-based mode selection
        if not settings.USE_VALKEY:
            logger.debug("Using database-only mode for inventory update", extra={"player_id": player_id, "slot": slot})
            await self.set_inventory_slot_offline(player_id, slot, item_id, quantity, durability)
            return
        
        # Valkey mode - fail fast if unavailable
        if not self._valkey:
            logger.error("Valkey client required but unavailable for inventory update", 
                        extra={"player_id": player_id, "slot": slot})
            raise RuntimeError("Cache infrastructure unavailable - check Valkey connection")
        
        # Valkey operations (no fallback)
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
        # Configuration-based mode selection
        if not settings.USE_VALKEY:
            logger.debug("Inventory operations not available in database-only mode", extra={"player_id": player_id})
            return
        
        # Valkey mode - fail fast if unavailable
        if not self._valkey:
            logger.error("Valkey client required but unavailable for inventory operation", 
                        extra={"player_id": player_id})
            raise RuntimeError("Cache infrastructure unavailable - check Valkey connection")
        
        # Check if player is online
        if not self.is_online(player_id):
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
        # Configuration-based mode selection
        if not settings.USE_VALKEY:
            logger.debug("Inventory operations not available in database-only mode", extra={"player_id": player_id})
            return
        
        # Valkey mode - fail fast if unavailable
        if not self._valkey:
            logger.error("Valkey client required but unavailable for inventory operation", 
                        extra={"player_id": player_id})
            raise RuntimeError("Cache infrastructure unavailable - check Valkey connection")
        
        # Check if player is online
        if not self.is_online(player_id):
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
                from server.src.core.skills import SkillType
                
                # Load player data
                stmt = select(Player).where(Player.id == player_id)
                result = await db.execute(stmt)
                player = result.scalar_one_or_none()
                
                if not player:
                    logger.warning("Player not found for state loading", extra={"player_id": player_id})
                    return
                
                # Set player state in cache
                await self.set_player_full_state(
                    player_id, player.x_coord, player.y_coord, player.map_id,
                    player.current_hp, player.current_hp  # Using current HP for max HP calculation
                )
                
                # Store appearance in Valkey for visibility system
                if player.appearance:
                    key = PLAYER_KEY.format(player_id=player_id)
                    await self._valkey.hset(key, {"appearance": json.dumps(player.appearance)})
                
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
                    from server.src.core.items import EquipmentSlot
                    try:
                        equipment_slot = EquipmentSlot(item.equipment_slot)
                        await self.set_equipment_slot(
                            player_id, equipment_slot, item.item_id, item.quantity, item.current_durability or 1.0
                        )
                    except ValueError:
                        logger.warning(
                            "Unknown equipment slot in database",
                            extra={"player_id": player_id, "slot": item.equipment_slot}
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
                    skill_type = SkillType.from_name(skill.name)
                    if skill_type:
                        await self.set_skill(
                            player_id, skill_type,
                            player_skill.current_level, player_skill.experience
                        )
                
                logger.info(
                    "Player state loaded for game session",
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
                extra={
                    "player_id": player_id,
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }
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
                extra={
                    "player_id": player_id,
                    "username": username,
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }
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
                SKILLS_KEY.format(player_id=player_id),
                PLAYER_COMBAT_STATE_KEY.format(player_id=player_id),
            ]
            
            await self._valkey.delete(keys_to_delete)
            
            logger.debug("Player state cleaned up", extra={"player_id": player_id})
            
        except Exception as e:
            logger.error(
                "Failed to cleanup player state",
                extra={
                    "player_id": player_id,
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }
            )
    
    # =========================================================================
    # EQUIPMENT OPERATIONS
    # =========================================================================
    
    async def get_equipment(self, player_id: int) -> Dict[str, Dict]:
        """Get player's equipment for game session."""
        # Configuration-based mode selection
        if not settings.USE_VALKEY:
            logger.debug("Using database-only mode for equipment access", extra={"player_id": player_id})
            return await self.get_equipment_offline(player_id)
        
        # Valkey mode - fail fast if unavailable
        if not self._valkey:
            logger.error("Valkey client required but unavailable for equipment access", 
                        extra={"player_id": player_id})
            raise RuntimeError("Cache infrastructure unavailable - check Valkey connection")
        
        # Check if player is online
        if not self.is_online(player_id):
            # For offline players in Valkey mode, load from database
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
    
    async def get_equipment_slot(self, player_id: int, slot: "EquipmentSlot") -> Optional[Dict[str, Any]]:
        """Get item in specific equipment slot.
        
        Args:
            player_id: The player's database ID
            slot: The EquipmentSlot enum value
            
        Returns:
            Dict with item_id, quantity, current_durability or None if not found
        """
        slot_name = slot.value
        
        # Configuration-based mode selection
        if not settings.USE_VALKEY:
            logger.debug("Equipment slot access not available in database-only mode", extra={"player_id": player_id})
            return None
        
        # Valkey mode - fail fast if unavailable
        if not self._valkey:
            logger.error("Valkey client required but unavailable for equipment slot access", 
                        extra={"player_id": player_id})
            raise RuntimeError("Cache infrastructure unavailable - check Valkey connection")
        
        # Check if player is online
        if not self.is_online(player_id):
            return None
        
        key = EQUIPMENT_KEY.format(player_id=player_id)
        raw = await self._valkey.hget(key, slot_name)
        
        if not raw:
            return None
        
        try:
            return json.loads(_decode_bytes(raw))
        except json.JSONDecodeError:
            return None
    
    async def set_equipment_slot(self, player_id: int, slot: "EquipmentSlot", item_id: int, quantity: int, durability: float) -> None:
        """Set item in equipment slot.
        
        Args:
            player_id: The player's database ID
            slot: The EquipmentSlot enum value
            item_id: The item ID to equip
            quantity: The quantity (for stackable items like ammo)
            durability: The current durability (0.0-1.0)
        """
        slot_name = slot.value
        
        # Configuration-based mode selection
        if not settings.USE_VALKEY:
            logger.debug("Equipment operations not available in database-only mode", extra={"player_id": player_id})
            return
        
        # Valkey mode - fail fast if unavailable
        if not self._valkey:
            logger.error("Valkey client required but unavailable for equipment operation", 
                        extra={"player_id": player_id})
            raise RuntimeError("Cache infrastructure unavailable - check Valkey connection")
        
        # Check if player is online
        if not self.is_online(player_id):
            return
        
        key = EQUIPMENT_KEY.format(player_id=player_id)
        item_data = {"item_id": item_id, "quantity": quantity, "current_durability": durability}
        
        await self._valkey.hset(key, {slot_name: json.dumps(item_data)})
        await self._valkey.sadd(DIRTY_EQUIPMENT_KEY, [str(player_id)])
    
    async def delete_equipment_slot(self, player_id: int, slot: "EquipmentSlot") -> None:
        """Delete item from equipment slot.
        
        Args:
            player_id: The player's database ID
            slot: The EquipmentSlot enum value
        """
        slot_name = slot.value
        
        # Configuration-based mode selection
        if not settings.USE_VALKEY:
            logger.debug("Equipment operations not available in database-only mode", extra={"player_id": player_id})
            return
        
        # Valkey mode - fail fast if unavailable
        if not self._valkey:
            logger.error("Valkey client required but unavailable for equipment operation", 
                        extra={"player_id": player_id})
            raise RuntimeError("Cache infrastructure unavailable - check Valkey connection")
        
        # Check if player is online
        if not self.is_online(player_id):
            return
        
        key = EQUIPMENT_KEY.format(player_id=player_id)
        await self._valkey.hdel(key, [slot_name])
        await self._valkey.sadd(DIRTY_EQUIPMENT_KEY, [str(player_id)])
    
    async def clear_equipment(self, player_id: int) -> None:
        """Clear all equipment."""
        # Configuration-based mode selection
        if not settings.USE_VALKEY:
            logger.debug("Equipment operations not available in database-only mode", extra={"player_id": player_id})
            return
        
        # Valkey mode - fail fast if unavailable
        if not self._valkey:
            logger.error("Valkey client required but unavailable for equipment operation", 
                        extra={"player_id": player_id})
            raise RuntimeError("Cache infrastructure unavailable - check Valkey connection")
        
        # Check if player is online
        if not self.is_online(player_id):
            return
        
        key = EQUIPMENT_KEY.format(player_id=player_id)
        await self._valkey.delete([key])
        await self._valkey.sadd(DIRTY_EQUIPMENT_KEY, [str(player_id)])
    
    # =========================================================================
    # SKILL OPERATIONS
    # =========================================================================
    
    async def get_skill(self, player_id: int, skill: "SkillType") -> Optional[Dict[str, Any]]:
        """
        Get specific skill data for player session.
        
        Args:
            player_id: The player's database ID
            skill: The SkillType enum value
            
        Returns:
            Dict with skill_id, level, experience or None if not found
        """
        from server.src.core.skills import SkillType
        
        skill_name = skill.name.lower()
        
        # Configuration-based mode selection
        if not settings.USE_VALKEY:
            logger.debug("Using database-only mode for skill access", extra={"player_id": player_id, "skill": skill_name})
            skills_data = await self.get_skills_offline(player_id)
            return skills_data.get(skill_name)
        
        # Valkey mode - fail fast if unavailable
        if not self._valkey:
            logger.error("Valkey client required but unavailable for skill access", 
                        extra={"player_id": player_id, "skill": skill_name})
            raise RuntimeError("Cache infrastructure unavailable - check Valkey connection")
        
        # Valkey operations (no fallback)
        key = SKILLS_KEY.format(player_id=player_id)
        raw = await self._valkey.hget(key, skill_name)
        
        if raw is not None:
            try:
                return json.loads(_decode_bytes(raw))
            except json.JSONDecodeError as e:
                logger.warning("Invalid skill data in session cache", extra={"player_id": player_id, "skill": skill_name, "error": str(e)})
                # Continue to load from persistent storage
        
        # Load all skills and cache them for session
        skills_data = await self.get_skills_offline(player_id)
        if skills_data:
            # Cache all skills for session performance
            await self._cache_skills_in_valkey(player_id, skills_data)
            return skills_data.get(skill_name)
        
        return None
    
    async def get_all_skills(self, player_id: int) -> Dict[str, Dict]:
        """Get all skills for a player with session data loading."""
        # Configuration-based mode selection
        if not settings.USE_VALKEY:
            logger.debug("Using database-only mode for skills access", extra={"player_id": player_id})
            return await self.get_skills_offline(player_id)
        
        # Valkey mode - fail fast if unavailable
        if not self._valkey:
            logger.error("Valkey client required but unavailable for skills access", 
                        extra={"player_id": player_id})
            raise RuntimeError("Cache infrastructure unavailable - check Valkey connection")
        
        # Valkey operations (no fallback)
        key = SKILLS_KEY.format(player_id=player_id)
        raw = await self._valkey.hgetall(key)
        
        if raw:
            # Parse existing session data
            skills = {}
            for skill_name_bytes, skill_data_bytes in raw.items():
                try:
                    skill_name = _decode_bytes(skill_name_bytes)
                    skill_data = json.loads(_decode_bytes(skill_data_bytes))
                    skills[skill_name] = skill_data
                except json.JSONDecodeError as e:
                    logger.warning("Invalid skill data in session cache", extra={"player_id": player_id, "error": str(e)})
            return skills
        
        # Load skills from persistent storage and cache
        skills_data = await self.get_skills_offline(player_id)
        
        # Cache for session performance
        if skills_data:
            await self._cache_skills_in_valkey(player_id, skills_data)
        
        return skills_data
    
    async def set_skill(self, player_id: int, skill: "SkillType", level: int, experience: int) -> None:
        """
        Update skill data for player session.
        
        Args:
            player_id: The player's database ID
            skill: The SkillType enum value
            level: The skill level
            experience: Total experience points
        """
        from server.src.core.config import settings
        from server.src.core.skills import SkillType
        
        # Derive skill_name from enum
        skill_name = skill.name.lower()
        
        # Get skill_id from cached mapping
        skill_id_map = await self.get_skill_id_map()
        skill_id = skill_id_map.get(skill_name)
        if skill_id is None:
            logger.error("Skill not found in database", extra={"skill_name": skill_name})
            raise ValueError(f"Skill '{skill_name}' not found in database")
        
        # Configuration-based mode selection
        if not settings.USE_VALKEY:
            logger.debug("Using database-only mode for skill update", extra={"player_id": player_id, "skill": skill_name})
            await self._update_skill_in_database(player_id, skill_name, skill_id, level, experience)
            return
        
        # Valkey mode - fail fast if unavailable
        if not self._valkey:
            logger.error("Valkey client required but unavailable for skill update", 
                        extra={"player_id": player_id, "skill": skill_name})
            raise RuntimeError("Cache infrastructure unavailable - check Valkey connection")
        
        # Valkey operations (no fallback)
        key = SKILLS_KEY.format(player_id=player_id)
        skill_data = {"skill_id": skill_id, "level": level, "experience": experience}
        
        await self._valkey.hset(key, {skill_name: json.dumps(skill_data)})
        
        # Manage session cache lifetime for offline players
        if not self.is_online(player_id):
            await self._valkey.expire(key, settings.OFFLINE_PLAYER_CACHE_TTL)
        
        # Mark for persistent storage sync if player is online
        if self.is_online(player_id):
            await self._valkey.sadd(DIRTY_SKILLS_KEY, [str(player_id)])
        else:
            # For offline players, also update persistent storage immediately
            await self._update_skill_in_database(player_id, skill_name, skill_id, level, experience)

    async def _update_skill_in_database(self, player_id: int, skill_name: str, skill_id: int, level: int, experience: int) -> None:
        """Update skill data in persistent storage."""
        if not self._session_factory:
            return
            
        async with self._db_session() as db:
            from server.src.models.skill import PlayerSkill
            from sqlalchemy import update
            
            # Update the PlayerSkill record
            await db.execute(
                update(PlayerSkill)
                .where(
                    PlayerSkill.player_id == player_id,
                    PlayerSkill.skill_id == skill_id,
                )
                .values(current_level=level, experience=experience)
            )
            
            await self._commit_if_not_test_session(db)
    
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
        
        # Parse all IDs first
        ground_item_ids = [int(_decode_bytes(id_raw)) for id_raw in ground_item_ids_raw]
        
        # Fetch all items in parallel using asyncio.gather
        item_futures = [self.get_ground_item(item_id) for item_id in ground_item_ids]
        items = await asyncio.gather(*item_futures)
        
        # Filter out None results
        return [item for item in items if item is not None]
    
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
            logger.error(
                "Failed to load ground items",
                extra={
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }
            )
            raise
    
    # =========================================================================
    # ENTITY INSTANCE OPERATIONS (Valkey-only, ephemeral)
    # =========================================================================
    
    async def spawn_entity_instance(
        self,
        entity_name: str,
        entity_type: "EntityType",
        map_id: str,
        x: int,
        y: int,
        spawn_x: int,
        spawn_y: int,
        max_hp: int,
        wander_radius: int,
        spawn_point_id: int,
        aggro_radius: Optional[int] = None,
        disengage_radius: Optional[int] = None,
    ) -> int:
        """
        Spawn a new entity instance.
        
        Args:
            entity_name: Entity type name (e.g., "GOBLIN", "VILLAGE_GUARD")
            entity_type: EntityType enum (HUMANOID_NPC or MONSTER)
            map_id: Map identifier
            x, y: Current tile position
            spawn_x, spawn_y: Original spawn position
            max_hp: Maximum HP
            wander_radius: Wander distance from spawn
            spawn_point_id: ID of spawn point in Tiled map
            aggro_radius: Override aggro radius (optional)
            disengage_radius: Override disengage radius (optional)
            
        Returns:
            Entity instance ID
        """
        if not self._valkey:
            raise RuntimeError("Valkey required for entity instances")
        
        # Get next entity instance ID
        instance_id = await self._valkey.incr(ENTITY_INSTANCE_COUNTER_KEY)
        
        # Create entity instance data
        entity_data = {
            "id": str(instance_id),
            "entity_name": entity_name,
            "entity_type": entity_type.value,
            "map_id": map_id,
            "x": str(x),
            "y": str(y),
            "spawn_x": str(spawn_x),
            "spawn_y": str(spawn_y),
            "current_hp": str(max_hp),
            "max_hp": str(max_hp),
            "state": "idle",
            "wander_radius": str(wander_radius),
            "spawn_point_id": str(spawn_point_id),
            "last_move_tick": "0",
        }
        
        # Add optional overrides
        if aggro_radius is not None:
            entity_data["aggro_radius"] = str(aggro_radius)
        if disengage_radius is not None:
            entity_data["disengage_radius"] = str(disengage_radius)
        
        # Store entity instance
        instance_key = ENTITY_INSTANCE_KEY.format(instance_id=instance_id)
        await self._valkey.hset(instance_key, entity_data)
        
        # Add to map entity list
        map_key = MAP_ENTITIES_KEY.format(map_id=map_id)
        await self._valkey.sadd(map_key, [str(instance_id)])
        
        logger.debug(
            "Entity instance spawned",
            extra={
                "instance_id": instance_id,
                "entity_name": entity_name,
                "map_id": map_id,
                "position": (x, y),
            }
        )
        
        return instance_id
    
    async def get_entity_instance(self, instance_id: int) -> Optional[Dict[str, Any]]:
        """
        Get entity instance data.
        
        Args:
            instance_id: Entity instance ID
            
        Returns:
            Entity instance data or None if not found
        """
        if not self._valkey:
            return None
        
        instance_key = ENTITY_INSTANCE_KEY.format(instance_id=instance_id)
        raw = await self._valkey.hgetall(instance_key)
        
        if not raw:
            return None
        
        # Parse entity data
        entity_data = {}
        for field, value in raw.items():
            field_str = _decode_bytes(field)
            value_str = _decode_bytes(value)
            
            # Convert numeric fields
            if field_str in ["id", "x", "y", "spawn_x", "spawn_y", "current_hp", "max_hp", 
                             "wander_radius", "spawn_point_id", "target_player_id", 
                             "last_move_tick", "los_lost_at_tick", "los_lost_position_x", 
                             "los_lost_position_y", "aggro_radius", "disengage_radius"]:
                try:
                    entity_data[field_str] = int(value_str)
                except ValueError:
                    entity_data[field_str] = 0
            else:
                entity_data[field_str] = value_str
        
        return entity_data
    
    async def get_map_entities(self, map_id: str) -> List[Dict[str, Any]]:
        """
        Get all entity instances on a map.
        
        Args:
            map_id: Map identifier
            
        Returns:
            List of entity instance data
        """
        if not self._valkey:
            return []
        
        map_key = MAP_ENTITIES_KEY.format(map_id=map_id)
        instance_ids_raw = await self._valkey.smembers(map_key)
        
        if not instance_ids_raw:
            return []
        
        # Parse all IDs first
        instance_ids = [int(_decode_bytes(id_raw)) for id_raw in instance_ids_raw]
        
        # Fetch all entities in parallel using asyncio.gather
        entity_futures = [self.get_entity_instance(instance_id) for instance_id in instance_ids]
        entities = await asyncio.gather(*entity_futures)
        
        # Filter out None results
        return [entity for entity in entities if entity is not None]
    
    async def update_entity_position(self, instance_id: int, x: int, y: int) -> None:
        """
        Update entity position.
        
        Args:
            instance_id: Entity instance ID
            x, y: New tile position
        """
        if not self._valkey:
            return
        
        instance_key = ENTITY_INSTANCE_KEY.format(instance_id=instance_id)
        await self._valkey.hset(instance_key, {"x": str(x), "y": str(y)})
    
    async def update_entity_hp(self, instance_id: int, current_hp: int) -> None:
        """
        Update entity HP.
        
        Args:
            instance_id: Entity instance ID
            current_hp: New current HP
        """
        if not self._valkey:
            return
        
        instance_key = ENTITY_INSTANCE_KEY.format(instance_id=instance_id)
        await self._valkey.hset(instance_key, {"current_hp": str(current_hp)})
    
    async def set_entity_state(
        self,
        instance_id: int,
        state: "EntityState",
        target_player_id: Optional[int] = None,
        los_lost_at_tick: Optional[int] = None,
        los_lost_position_x: Optional[int] = None,
        los_lost_position_y: Optional[int] = None,
    ) -> None:
        """
        Update entity state and target.
        
        Args:
            instance_id: Entity instance ID
            state: New EntityState (IDLE, WANDER, COMBAT, RETURNING, DYING, DEAD)
            target_player_id: Target player ID (None to clear)
            los_lost_at_tick: Tick when LOS was lost (optional)
            los_lost_position_x, los_lost_position_y: Last known position (optional)
        """
        if not self._valkey:
            return
        
        instance_key = ENTITY_INSTANCE_KEY.format(instance_id=instance_id)
        update_data = {"state": state.value}
        
        if target_player_id is not None:
            update_data["target_player_id"] = str(target_player_id)
        else:
            # Clear target if None
            await self._valkey.hdel(instance_key, ["target_player_id"])
        
        if los_lost_at_tick is not None:
            update_data["los_lost_at_tick"] = str(los_lost_at_tick)
            if los_lost_position_x is not None and los_lost_position_y is not None:
                update_data["los_lost_position_x"] = str(los_lost_position_x)
                update_data["los_lost_position_y"] = str(los_lost_position_y)
        else:
            # Clear LOS data if None
            await self._valkey.hdel(instance_key, [
                "los_lost_at_tick", "los_lost_position_x", "los_lost_position_y"
            ])
        
        await self._valkey.hset(instance_key, update_data)
    
    async def despawn_entity(self, instance_id: int, death_tick: int, respawn_delay_seconds: int = 30) -> None:
        """
        Mark entity as dying (for animation) then transition to dead state.
        
        The entity goes through two phases:
        1. "dying" state - visible until death_tick is reached
        2. "dead" state - invisible, added to respawn queue
        
        Args:
            instance_id: Entity instance ID
            death_tick: Global tick when entity should transition to "dead" state
            respawn_delay_seconds: Seconds until respawn (default 30)
        """
        if not self._valkey:
            return
        
        instance_key = ENTITY_INSTANCE_KEY.format(instance_id=instance_id)
        
        # Set entity to "dying" state with death tick timestamp
        await self._valkey.hset(instance_key, {
            "state": "dying",
            "death_tick": str(death_tick),
            "respawn_delay": str(respawn_delay_seconds),
            "current_hp": "0"  # Ensure HP is 0 during dying state
        })
        
        # Clear combat target
        await self._valkey.hdel(instance_key, ["target_player_id", "los_lost_at_tick", 
                                                "los_lost_position_x", "los_lost_position_y"])
        
        logger.debug(
            "Entity entering dying state",
            extra={"instance_id": instance_id, "death_tick": death_tick}
        )
    
    async def finalize_entity_death(self, instance_id: int) -> None:
        """
        Transition entity from "dying" to "dead" and queue for respawn.
        Called by game loop when death_tick is reached.
        
        Args:
            instance_id: Entity instance ID
        """
        if not self._valkey:
            return
        
        instance_key = ENTITY_INSTANCE_KEY.format(instance_id=instance_id)
        
        # Get respawn delay from entity data
        entity_data = await self.get_entity_instance(instance_id)
        if not entity_data:
            return
        
        respawn_delay_seconds = int(entity_data.get("respawn_delay", 30))
        
        # Mark entity as dead (invisible)
        await self._valkey.hset(instance_key, {"state": "dead"})
        
        # Add to respawn queue
        respawn_at = _utc_timestamp() + respawn_delay_seconds
        await self._valkey.zadd(
            ENTITY_RESPAWN_QUEUE_KEY,
            {str(instance_id): respawn_at}
        )
        
        logger.debug(
            "Entity death finalized, queued for respawn",
            extra={"instance_id": instance_id, "respawn_in": respawn_delay_seconds}
        )
    
    async def clear_all_entity_instances(self) -> None:
        """Clear all entity instances from Valkey (server startup)."""
        if not self._valkey:
            return
        
        # Reset counter
        await self._valkey.set(ENTITY_INSTANCE_COUNTER_KEY, "0")
        
        # Clear respawn queue
        await self._valkey.delete([ENTITY_RESPAWN_QUEUE_KEY])
        
        logger.info("All entity instances cleared from Valkey")
    
    async def clear_player_as_entity_target(self, player_id: int) -> None:
        """
        Clear player as target from all entities (player death/logout).
        
        Args:
            player_id: Player ID to clear from entity targets
        """
        if not self._valkey:
            return
        
        # This would require scanning all entity instances
        # For now, we'll implement this in the entity AI service
        # when it processes entities - it should check if target player is still online
        logger.debug(
            "Player target clear requested (handled by AI service)",
            extra={"player_id": player_id}
        )
    
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
                    "skill_id": player_skill.skill_id,  # Include skill_id for compatibility
                    "level": player_skill.current_level,
                    "experience": player_skill.experience
                }
            
            return skill_data

    async def sync_skills_to_db(self) -> list:
        """
        Ensure all SkillType entries exist in the skills table with transparent handling.
        
        Returns:
            List of all Skill records in the database
        """
        # Skill syncing is a one-time operation that doesn't need online/offline distinction
        return await self._sync_skills_to_db_offline()

    async def _sync_skills_to_db_offline(self) -> list:
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
    
    async def get_skill_id_map(self) -> Dict[str, int]:
        """
        Get a mapping of skill names to their database IDs with transparent handling.
        
        Returns:
            Dict mapping lowercase skill name to skill ID
        """
        # Skill ID mapping is reference data that doesn't need online/offline distinction
        return await self._get_skill_id_map_offline()
    
    async def _get_skill_id_map_offline(self) -> Dict[str, int]:
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
    
    async def grant_all_skills_to_player(self, player_id: int) -> list:
        """
        Grant all skills to a player with transparent online/offline handling.
        
        Most skills start at level 1 with 0 XP.
        Hitpoints starts at level 10 with the XP required for level 10.
        
        Args:
            player_id: The player's database ID
            
        Returns:
            List of all PlayerSkill records for the player
        """
        from server.src.core.config import settings
        
        # For skill granting, always use offline method for consistency
        # Skills are reference data that doesn't benefit from online/offline distinction
        return await self._grant_all_skills_to_player_offline(player_id)
    
    async def _grant_all_skills_to_player_offline(self, player_id: int, db_session: Optional[AsyncSession] = None) -> list:
        """
        Create PlayerSkill rows for all skills for offline players.
        
        Args:
            player_id: The players database ID
            db_session: Optional database session to use (for transaction sharing)
            
        Returns:
            List of all PlayerSkill records for the player
        """
        if not self._session_factory:
            return []
        
        # Use provided session or create new one
        async def _execute_with_session():
            from server.src.models.skill import PlayerSkill, Skill
            from server.src.core.skills import (
                SkillType, get_skill_xp_multiplier, xp_for_level, HITPOINTS_START_LEVEL
            )
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            
            skill_id_map = await self._get_skill_id_map_offline()
            
            if not skill_id_map:
                # No skills in database yet, sync them first
                await self._sync_skills_to_db_offline()
                skill_id_map = await self._get_skill_id_map_offline()
            
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
            
            # Only commit if we created our own session
            if not db_session:
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
        
        if db_session:
            # Use provided session (transaction sharing)
            db = db_session
            return await _execute_with_session()
        else:
            # Create our own session
            async with self._db_session() as db:
                return await _execute_with_session()
    
    async def get_player_skills(self, player_id: int) -> list:
        """
        Fetch all skills for a player with computed metadata.
        Handles both online and offline players transparently.
        
        Args:
            player_id: Player ID
            
        Returns:
            List of skill info dicts with name, category, level, xp, etc.
        """
        from server.src.core.config import settings
        
        # For skill metadata computation, always use offline method for now
        # TODO: Add Valkey support for skill metadata computations  
        return await self._get_player_skills_offline(player_id)
    
    async def _get_player_skills_offline(self, player_id: int) -> list:
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
    
    async def get_hitpoints_level(self, player_id: int) -> int:
        """
        Get the player's Hitpoints skill level with transparent handling.
        
        Args:
            player_id: Player ID
            
        Returns:
            Hitpoints level
        """
        from server.src.core.skills import SkillType
        
        # Try the unified get_skill method first
        hitpoints_skill = await self.get_skill(player_id, SkillType.HITPOINTS)
        if hitpoints_skill:
            return hitpoints_skill["level"]
        
        # Fallback to offline method for safety
        return await self._get_hitpoints_level_offline(player_id)
    
    async def _get_hitpoints_level_offline(self, player_id: int) -> int:
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
                "x_coord": player.x_coord,
                "y_coord": player.y_coord,
                "map_id": player.map_id,
                "current_hp": player.current_hp,
                "hashed_password": player.hashed_password,
                "is_banned": player.is_banned,
                "timeout_until": player.timeout_until,
                "role": player.role,
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
                await self.set_player_full_state(
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

    async def sync_items_to_database(self) -> int:
        """
        Sync items from ItemType enum to database.
        
        Creates or updates item records based on the ItemType definitions.
        This ensures the database has all items defined in code.
        
        Returns:
            Number of items synced
        """
        if not self._session_factory:
            logger.warning("Cannot sync items - no database connection")
            return 0
            
        from server.src.core.items import ItemType
        from server.src.models.item import Item
        
        items_synced = 0
        
        async with self._db_session() as db:
            for item_type in ItemType:
                item_def = item_type.value
                
                # Check if item exists in database (using lowercase enum name)
                item_name = item_type.name.lower()
                result = await db.execute(
                    select(Item).where(Item.name == item_name)
                )
                existing_item = result.scalar_one_or_none()
                
                if existing_item:
                    # Update existing item
                    existing_item.display_name = item_def.display_name
                    existing_item.description = item_def.description
                    existing_item.category = item_def.category.value
                    existing_item.rarity = item_def.rarity.value if item_def.rarity else "common"
                    existing_item.value = item_def.value
                    existing_item.equipment_slot = item_def.equipment_slot.value if item_def.equipment_slot else None
                    existing_item.max_durability = item_def.max_durability
                    existing_item.max_stack_size = item_def.max_stack_size
                    existing_item.attack_bonus = item_def.attack_bonus
                    existing_item.strength_bonus = item_def.strength_bonus
                    existing_item.ranged_attack_bonus = item_def.ranged_attack_bonus
                    existing_item.ranged_strength_bonus = item_def.ranged_strength_bonus
                    existing_item.magic_attack_bonus = item_def.magic_attack_bonus
                    existing_item.magic_damage_bonus = item_def.magic_damage_bonus
                    existing_item.physical_defence_bonus = item_def.physical_defence_bonus
                    existing_item.magic_defence_bonus = item_def.magic_defence_bonus
                    existing_item.health_bonus = item_def.health_bonus
                    existing_item.speed_bonus = item_def.speed_bonus
                    existing_item.mining_bonus = item_def.mining_bonus
                    existing_item.woodcutting_bonus = item_def.woodcutting_bonus
                    existing_item.fishing_bonus = item_def.fishing_bonus
                    existing_item.is_two_handed = item_def.is_two_handed
                    existing_item.is_indestructible = item_def.is_indestructible
                    existing_item.is_tradeable = item_def.is_tradeable
                    existing_item.required_skill = item_def.required_skill.value if item_def.required_skill else None
                    existing_item.required_level = item_def.required_level
                    existing_item.ammo_type = item_def.ammo_type.value if item_def.ammo_type else None
                else:
                    # Create new item
                    new_item = Item(
                        name=item_name,  # Use lowercase name
                        display_name=item_def.display_name,
                        description=item_def.description,
                        category=item_def.category.value,
                        rarity=item_def.rarity.value if item_def.rarity else "common",
                        value=item_def.value,
                        equipment_slot=item_def.equipment_slot.value if item_def.equipment_slot else None,
                        max_durability=item_def.max_durability,
                        max_stack_size=item_def.max_stack_size,
                        attack_bonus=item_def.attack_bonus,
                        strength_bonus=item_def.strength_bonus,
                        ranged_attack_bonus=item_def.ranged_attack_bonus,
                        ranged_strength_bonus=item_def.ranged_strength_bonus,
                        magic_attack_bonus=item_def.magic_attack_bonus,
                        magic_damage_bonus=item_def.magic_damage_bonus,
                        physical_defence_bonus=item_def.physical_defence_bonus,
                        magic_defence_bonus=item_def.magic_defence_bonus,
                        health_bonus=item_def.health_bonus,
                        speed_bonus=item_def.speed_bonus,
                        mining_bonus=item_def.mining_bonus,
                        woodcutting_bonus=item_def.woodcutting_bonus,
                        fishing_bonus=item_def.fishing_bonus,
                        is_two_handed=item_def.is_two_handed,
                        is_indestructible=item_def.is_indestructible,
                        is_tradeable=item_def.is_tradeable,
                        required_skill=item_def.required_skill.value if item_def.required_skill else None,
                        required_level=item_def.required_level,
                        ammo_type=item_def.ammo_type.value if item_def.ammo_type else None,
                    )
                    db.add(new_item)
                
                items_synced += 1
                
            await db.commit()
            
        logger.info(f"Synced {items_synced} items to database")
        return items_synced

    # =========================================================================
    # COMPLETE PLAYER DATA MANAGEMENT
    # =========================================================================
    
    async def create_player_complete(
        self, username: str, hashed_password: str, 
        x: int = 10, y: int = 10, map_id: str = "samplemap"
    ) -> Dict[str, Any]:
        """
        Create player in database and immediately load into cache.
        
        Creates player record, initializes skills, and loads complete state.
        
        Args:
            username: Player username
            hashed_password: Pre-hashed password
            x: Initial X coordinate
            y: Initial Y coordinate  
            map_id: Initial map ID
            
        Returns:
            Complete player data dict
            
        Raises:
            IntegrityError: If username already exists
        """
        if not self._session_factory:
            raise RuntimeError("Database session factory not available")
            
        async with self._db_session() as db:
            from server.src.models.player import Player
            
            # Default appearance for new players (required for paperdoll rendering)
            default_appearance = {
                "body_type": "male",
                "skin_tone": "light",
                "head_type": "human/male",
                "hair_style": "plain",
                "hair_color": "brown",
                "eye_color": "brown",
            }
            
            # Create player record
            player = Player(
                username=username,
                hashed_password=hashed_password,
                x_coord=x,
                y_coord=y,
                map_id=map_id,
                appearance=default_appearance,
            )
            
            db.add(player)
            await db.flush()  # Get player ID
            
            # Initialize player skills with default values (using same session)
            await self._grant_all_skills_to_player_offline(player.id, db)
            
            await db.commit()
            await db.refresh(player)
            
            # Load player into cache immediately
            await self.load_player_state(player.id)
            
            # Return complete player data
            player_data = await self.get_player_complete(player.id)
            if not player_data:
                raise RuntimeError(f"Failed to load player data after creation: {player.id}")
            return player_data
    
    async def get_player_complete(self, player_id: int) -> Optional[Dict[str, Any]]:
        """
        Get complete player data by ID with auto-cache for offline players.
        
        Includes all player attributes plus derived/computed values.
        
        Args:
            player_id: Player ID
            
        Returns:
            Complete player data dict or None if not found
        """
        # Try to get from hot cache first
        player_state = await self.get_player_full_state(player_id)
        if player_state:
            return player_state
            
        # Auto-load from database if not in cache
        if not self._session_factory:
            return None
            
        async with self._db_session() as db:
            from server.src.models.player import Player
            
            result = await db.execute(
                select(Player).where(Player.id == player_id)
            )
            player = result.scalar_one_or_none()
            if not player:
                return None
            
            # Load into cache with TTL (offline player)
            await self.load_player_state(player_id)
            
            # For offline players, build the data manually since cache requires online status
            player_data = {
                "id": player.id,
                "username": player.username,
                "hashed_password": player.hashed_password,
                "x_coord": player.x_coord,
                "y_coord": player.y_coord,
                "map_id": player.map_id,
                "role": getattr(player, 'role', 'player'),
                "is_banned": getattr(player, 'is_banned', False),
                "timeout_until": getattr(player, 'timeout_until', None),
                "current_hp": player.current_hp,
                "x": player.x_coord,  # Legacy compatibility 
                "y": player.y_coord,  # Legacy compatibility
                "max_hp": player.current_hp,  # Will be calculated properly by services
            }
            
            return player_data
    
    async def get_player_by_username_complete(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Get complete player data by username with auto-cache for offline players.
        
        Args:
            username: Player username
            
        Returns:
            Complete player data dict or None if not found
        """
        # First try the username cache
        player_id = self._username_to_id.get(username)
        if player_id:
            return await self.get_player_complete(player_id)
            
        # Auto-load from database if not cached
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
            
            # Load into cache with TTL (offline player)
            await self.load_player_state(player.id)
            
            # Return the cached data
            return await self.get_player_full_state(player.id)
    
    async def get_player_permissions(self, player_id: int) -> Optional[Dict[str, Any]]:
        """
        Get player permissions including role, admin status, ban status, timeout info.
        
        Args:
            player_id: Player ID
            
        Returns:
            Dict with permission data or None if player not found
        """
        player_data = await self.get_player_complete(player_id)
        if not player_data:
            return None
            
        return {
            "role": player_data.get("role"),
            "is_admin": player_data.get("role") == "admin",
            "is_banned": player_data.get("is_banned", False),
            "timeout_until": player_data.get("timeout_until"),
        }
    
    async def get_player_id_by_username_autoload(self, username: str) -> Optional[int]:
        """
        Username to ID lookup with offline player auto-loading.
        
        Args:
            username: Player username to look up
            
        Returns:
            Player ID if found, None otherwise
        """
        # Check online players first for performance
        player_id = self._username_to_id.get(username)
        if player_id:
            return player_id
            
        # Use complete player lookup which handles auto-loading
        player_data = await self.get_player_by_username_complete(username)
        return player_data.get("id") if player_data else None

    # =========================================================================
    # PLAYER DELETION (Complete removal from cache and database)
    # =========================================================================
    
    async def delete_player_complete(self, player_id: int) -> bool:
        """
        Completely delete a player from both cache and database.
        
        Removes:
        - Player from online registry (if online)
        - All Valkey keys (position, inventory, equipment, skills, combat state, settings)
        - All database records (PlayerSkill, PlayerInventory, PlayerEquipment, GroundItem, Player)
        
        Args:
            player_id: Player ID to delete
            
        Returns:
            True if player was deleted, False if player didn't exist
        """
        logger.info("Deleting player completely", extra={"player_id": player_id})
        
        # 1. Remove from online registry if present
        username = self._id_to_username.get(player_id)
        if self.is_online(player_id):
            self._online_players.discard(player_id)
            if username:
                self._username_to_id.pop(username, None)
            self._id_to_username.pop(player_id, None)
            logger.debug("Removed player from online registry", extra={"player_id": player_id})
        
        # 2. Clean up all Valkey keys for this player
        await self.cleanup_player_state(player_id)
        
        # Also clean up settings key which cleanup_player_state doesn't handle
        if self._valkey:
            settings_key = PLAYER_SETTINGS_KEY.format(player_id=player_id)
            await self._valkey.delete([settings_key])
        
        # 3. Delete all database records
        if not self._session_factory:
            logger.warning("No database session factory for player deletion")
            return False
            
        try:
            async with self._db_session() as db:
                from server.src.models.player import Player
                from server.src.models.skill import PlayerSkill
                from server.src.models.item import PlayerInventory, PlayerEquipment, GroundItem
                
                # Check if player exists first
                result = await db.execute(
                    select(Player).where(Player.id == player_id)
                )
                player = result.scalar_one_or_none()
                
                if not player:
                    logger.debug("Player not found in database", extra={"player_id": player_id})
                    return False
                
                # Delete related records first (foreign key constraints)
                await db.execute(delete(PlayerSkill).where(PlayerSkill.player_id == player_id))
                await db.execute(delete(PlayerInventory).where(PlayerInventory.player_id == player_id))
                await db.execute(delete(PlayerEquipment).where(PlayerEquipment.player_id == player_id))
                await db.execute(delete(GroundItem).where(GroundItem.dropped_by == player_id))
                
                # Delete the player record
                await db.execute(delete(Player).where(Player.id == player_id))
                
                await self._commit_if_not_test_session(db)
                
                logger.info(
                    "Player deleted completely",
                    extra={"player_id": player_id, "username": username}
                )
                return True
                
        except Exception as e:
            logger.error(
                "Failed to delete player from database",
                extra={
                    "player_id": player_id,
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }
            )
            raise
    
    # =========================================================================
    # STATE RESET (For testing and server maintenance)
    # =========================================================================
    
    async def reset_all_state(self, clear_database: bool = False) -> None:
        """
        Reset all game state. Primarily used for testing.
        
        Clears:
        - All online player registries (in-memory)
        - All player-related Valkey keys
        - All entity instance keys
        - All ground item keys
        - Optionally: All player-related database tables
        
        Args:
            clear_database: If True, also clears database tables (destructive!)
        """
        logger.warning(
            "Resetting all game state",
            extra={"clear_database": clear_database}
        )
        
        # 1. Clear in-memory registries
        self._online_players.clear()
        self._username_to_id.clear()
        self._id_to_username.clear()
        
        # 2. Clear all Valkey state
        if self._valkey:
            try:
                # Clear entity instances and respawn queue
                await self.clear_all_entity_instances()
                
                # Clear dirty tracking sets
                dirty_keys = [
                    DIRTY_POSITION_KEY,
                    DIRTY_INVENTORY_KEY,
                    DIRTY_EQUIPMENT_KEY,
                    DIRTY_SKILLS_KEY,
                    DIRTY_GROUND_ITEMS_KEY,
                ]
                await self._valkey.delete(dirty_keys)
                
                # Clear ground items next ID counter
                await self._valkey.delete([GROUND_ITEMS_NEXT_ID_KEY])
                
                logger.debug("Cleared all Valkey state")
                
            except Exception as e:
                logger.error(
                    "Failed to clear Valkey state",
                    extra={
                        "error": str(e),
                        "traceback": traceback.format_exc(),
                    }
                )
        
        # 3. Optionally clear database tables
        if clear_database and self._session_factory:
            try:
                async with self._db_session() as db:
                    from server.src.models.player import Player
                    from server.src.models.skill import PlayerSkill
                    from server.src.models.item import PlayerInventory, PlayerEquipment, GroundItem
                    
                    # Delete in order to respect foreign key constraints
                    await db.execute(delete(PlayerSkill))
                    await db.execute(delete(PlayerInventory))
                    await db.execute(delete(PlayerEquipment))
                    await db.execute(delete(GroundItem))
                    await db.execute(delete(Player))
                    
                    await self._commit_if_not_test_session(db)
                    
                    logger.warning("Cleared all player data from database")
                    
            except Exception as e:
                logger.error(
                    "Failed to clear database state",
                    extra={
                        "error": str(e),
                        "traceback": traceback.format_exc(),
                    }
                )
                raise
        
        logger.info("Game state reset complete")


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