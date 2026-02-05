"""
Player state management.

Handles player positions, HP, settings, and combat state.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from sqlalchemy import select
from time import time

from server.src.core.config import settings
from server.src.core.logging_config import get_logger
from server.src.schemas.player import PlayerData, Direction, AnimationState

logger = get_logger(__name__)

# Valkey key patterns
PLAYER_KEY = "player:{player_id}"
PLAYER_SETTINGS_KEY = "player_settings:{player_id}"
PLAYER_COMBAT_STATE_KEY = "player_combat:{player_id}"

# TTL tiers
TIER1_TTL = 300  # 5 minutes - frequently accessed
TIER2_TTL = 600  # 10 minutes


class PlayerStateManager:
    """Manages player state with Valkey caching."""

    def __init__(self, session_factory=None, valkey=None):
        self._session_factory = session_factory
        self._valkey = valkey

    def _db_session(self):
        """Create a database session."""
        return self._session_factory()

    async def _commit_if_not_test_session(self, db):
        """Commit if this is not a test session."""
        await db.commit()

    def _utc_timestamp(self) -> float:
        """Get current UTC timestamp."""
        return time()

    def _decode_bytes(self, value: Any) -> Any:
        """Decode bytes to string."""
        if isinstance(value, bytes):
            return value.decode('utf-8')
        return value

    def _decode_from_valkey(self, value: Any, type_func=None) -> Any:
        """Decode value from Valkey."""
        if value is None:
            return None
        decoded = self._decode_bytes(value)
        if type_func and decoded is not None:
            try:
                return type_func(decoded)
            except (ValueError, TypeError):
                return decoded
        return decoded

    async def _cache_in_valkey(
        self, key: str, data: Dict[str, Any], ttl: int
    ) -> None:
        """Cache data in Valkey."""
        if not self._valkey or not settings.USE_VALKEY:
            return

        import json
        encoded_data = {k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in data.items()}
        await self._valkey.hset(key, encoded_data)
        await self._valkey.expire(key, ttl)

    async def _get_from_valkey(self, key: str) -> Optional[Dict[str, Any]]:
        """Get data from Valkey."""
        if not self._valkey or not settings.USE_VALKEY:
            return None

        raw = await self._valkey.hgetall(key)
        if not raw:
            return None

        import json
        result = {}
        for k, v in raw.items():
            decoded_key = self._decode_bytes(k)
            decoded_value = self._decode_bytes(v)
            # Try to parse JSON strings back into dicts/lists
            if isinstance(decoded_value, str):
                try:
                    decoded_value = json.loads(decoded_value)
                except json.JSONDecodeError:
                    pass  # Keep as string if not valid JSON
            result[decoded_key] = decoded_value
        return result

    async def _refresh_ttl(self, key: str, ttl: int) -> None:
        """Refresh TTL for a key."""
        if self._valkey and settings.USE_VALKEY:
            await self._valkey.expire(key, ttl)

    # =========================================================================
    # Online Player Registry
    # =========================================================================

    async def register_online_player(self, player_id: int, username: Optional[str] = None) -> None:
        """
        Register player as online.
        
        Args:
            player_id: Player database ID
            username: Optional username. If not provided, will be looked up from database.
        """
        # Look up username if not provided
        if username is None:
            username = await self.get_username_for_player(player_id)
            if not username:
                logger.error(
                    "Cannot register online player - username lookup failed",
                    extra={"player_id": player_id}
                )
                return
        
        key = PLAYER_KEY.format(player_id=player_id)
        data = {
            "player_id": player_id,
            "username": username,
            "online_since": self._utc_timestamp(),
        }
        await self._cache_in_valkey(key, data, TIER1_TTL)

    async def unregister_online_player(self, player_id: int) -> None:
        """Unregister player from online registry."""
        key = PLAYER_KEY.format(player_id=player_id)
        if self._valkey and settings.USE_VALKEY:
            await self._valkey.delete([key])

    async def is_online(self, player_id: int) -> bool:
        """Check if player is online."""
        if not self._valkey or not settings.USE_VALKEY:
            return False
        key = PLAYER_KEY.format(player_id=player_id)
        exists = await self._valkey.exists(key)
        return bool(exists)

    async def get_all_online_player_ids(self) -> List[int]:
        """Get all online player IDs."""
        if not self._valkey or not settings.USE_VALKEY:
            return []

        player_ids = []
        cursor = 0
        pattern = PLAYER_KEY.format(player_id="*")

        while True:
            cursor, keys = await self._valkey.scan(cursor, pattern, count=100)
            for key in keys:
                key_str = self._decode_bytes(key)
                # Extract player_id from key pattern "player:{player_id}"
                if key_str.startswith("player:"):
                    try:
                        player_id = int(key_str.split(":")[1])
                        player_ids.append(player_id)
                    except (ValueError, IndexError):
                        continue
            if cursor == 0:
                break

        return player_ids

    async def get_active_player_count(self) -> int:
        """Get count of currently active (online) players."""
        online_players = await self.get_all_online_player_ids()
        return len(online_players)

    async def get_username_for_player(self, player_id: int) -> Optional[str]:
        """Get username for a player from cache or database."""
        if self._valkey and settings.USE_VALKEY:
            key = PLAYER_KEY.format(player_id=player_id)
            data = await self._get_from_valkey(key)
            if data and "username" in data:
                return data["username"]

        if not self._session_factory:
            return None

        from server.src.models.player import Player

        async with self._db_session() as db:
            result = await db.execute(
                select(Player.username).where(Player.id == player_id)
            )
            row = result.first()
            return row.username if row else None

    # =========================================================================
    # HP Management
    # =========================================================================

    async def get_player_hp(self, player_id: int) -> Optional[Dict[str, int]]:
        """
        Get player's current and max HP from Valkey cache.
        
        Args:
            player_id: Player's database ID
            
        Returns:
            Dict with 'current_hp' and 'max_hp' or None if not cached
        """
        if not self._valkey or not settings.USE_VALKEY:
            return None
            
        key = PLAYER_KEY.format(player_id=player_id)
        data = await self._get_from_valkey(key)
        
        if not data or "current_hp" not in data or "max_hp" not in data:
            return None
            
        return {
            "current_hp": int(data["current_hp"]),
            "max_hp": int(data["max_hp"])
        }

    async def set_player_hp(
        self, player_id: int, current_hp: int, max_hp: Optional[int] = None
    ) -> None:
        """
        Set player's HP in Valkey cache.
        
        Args:
            player_id: Player's database ID
            current_hp: New current HP value
            max_hp: Optional new max HP value (if not provided, existing max_hp is preserved)
        """
        if not self._valkey or not settings.USE_VALKEY:
            return
            
        key = PLAYER_KEY.format(player_id=player_id)
        
        # Get existing data to preserve other fields and max_hp if not provided
        existing_data = await self._get_from_valkey(key)
        
        if existing_data:
            # Update existing cache entry
            existing_data["current_hp"] = current_hp
            if max_hp is not None:
                existing_data["max_hp"] = max_hp
            await self._cache_in_valkey(key, existing_data, TIER1_TTL)
        else:
            # Create new cache entry (requires max_hp)
            if max_hp is None:
                logger.warning(
                    "Attempting to set HP without max_hp for non-cached player",
                    extra={"player_id": player_id}
                )
                return
                
            data = {
                "player_id": player_id,
                "current_hp": current_hp,
                "max_hp": max_hp,
            }
            await self._cache_in_valkey(key, data, TIER1_TTL)

    # =========================================================================
    # Player Record Management
    # =========================================================================

    async def username_exists(self, username: str) -> bool:
        """Check if username exists in database."""
        if not self._session_factory:
            return False

        from server.src.models.player import Player

        async with self._db_session() as db:
            result = await db.execute(
                select(Player).where(Player.username == username)
            )
            return result.first() is not None

    async def create_player_record(
        self,
        username: str,
        hashed_password: str,
        x: int,
        y: int,
        map_id: str,
        current_hp: int,
        max_hp: int,
    ) -> int:
        """Create new Player record in database and return the player_id."""
        if not self._session_factory:
            raise RuntimeError("Session factory not available")

        from server.src.models.player import Player

        async with self._db_session() as db:
            player = Player(
                username=username,
                hashed_password=hashed_password,
                x=x,
                y=y,
                map_id=map_id,
                current_hp=current_hp,
            )
            db.add(player)
            await db.flush()
            await db.refresh(player)
            await db.commit()
            return player.id

    async def get_player_record_by_username(self, username: str) -> Optional[PlayerData]:
        """Get player record by username from database."""
        if not self._session_factory:
            return None

        from server.src.models.player import Player
        from server.src.models.skill import PlayerSkill, Skill
        from server.src.core.skills import SkillType, HITPOINTS_START_LEVEL

        async with self._db_session() as db:
            result = await db.execute(
                select(Player).where(Player.username == username)
            )
            player = result.scalar_one_or_none()

            if not player:
                return None

            # Get hitpoints skill level for max_hp calculation
            hitpoints_result = await db.execute(
                select(PlayerSkill.current_level)
                .join(Skill)
                .where(
                    PlayerSkill.player_id == player.id,
                    Skill.name == SkillType.HITPOINTS.value.name
                )
            )
            max_hp = hitpoints_result.scalar_one_or_none() or HITPOINTS_START_LEVEL
            
            return PlayerData(
                id=player.id,
                username=player.username,
                x=player.x,
                y=player.y,
                map_id=player.map_id,
                current_hp=player.current_hp,
                max_hp=max_hp,
                role=player.role,
                is_banned=player.is_banned,
                timeout_until=player.timeout_until,
                is_online=False,  # Runtime state, set by connection service
                facing_direction=Direction.SOUTH,  # Default, overridden by hot data
                animation_state=AnimationState.IDLE,  # Default, overridden by hot data
                total_level=0  # TODO: Calculate from skills when needed
            )

    async def get_player_record_by_id(self, player_id: int) -> Optional[PlayerData]:
        """Get player record by ID from database."""
        if not self._session_factory:
            return None

        from server.src.models.player import Player
        from server.src.models.skill import PlayerSkill, Skill
        from server.src.core.skills import SkillType, HITPOINTS_START_LEVEL

        async with self._db_session() as db:
            result = await db.execute(
                select(Player).where(Player.id == player_id)
            )
            player = result.scalar_one_or_none()

            if not player:
                return None

            # Get hitpoints skill level for max_hp calculation
            hitpoints_result = await db.execute(
                select(PlayerSkill.current_level)
                .join(Skill)
                .where(
                    PlayerSkill.player_id == player.id,
                    Skill.name == SkillType.HITPOINTS.value.name
                )
            )
            max_hp = hitpoints_result.scalar_one_or_none() or HITPOINTS_START_LEVEL
            
            return PlayerData(
                id=player.id,
                username=player.username,
                x=player.x,
                y=player.y,
                map_id=player.map_id,
                current_hp=player.current_hp,
                max_hp=max_hp,
                role=player.role,
                is_banned=player.is_banned,
                timeout_until=player.timeout_until,
                is_online=False,  # Runtime state, set by connection service
                facing_direction=Direction.SOUTH,  # Default, overridden by hot data
                animation_state=AnimationState.IDLE,  # Default, overridden by hot data
                total_level=0,  # TODO: Calculate from skills when needed
                appearance=player.appearance
            )

    async def delete_player_record(self, player_id: int) -> bool:
        """Delete player from database."""
        if not self._session_factory:
            return False

        from server.src.models.player import Player

        async with self._db_session() as db:
            result = await db.execute(
                select(Player).where(Player.id == player_id)
            )
            player = result.scalar_one_or_none()

            if not player:
                return False

            await db.delete(player)
            await db.commit()
            return True

    # =========================================================================
    # Position Management
    # =========================================================================

    async def get_player_position(self, player_id: int) -> Optional[Dict[str, Any]]:
        """Get player position from cache or database."""
        try:
            if not settings.USE_VALKEY or not self._valkey:
                return await self._load_position_from_db(player_id)

            key = PLAYER_KEY.format(player_id=player_id)

            async def load_from_db():
                return await self._load_position_from_db(player_id)

            position = await self.auto_load_with_ttl(
                key, load_from_db, TIER1_TTL, decoder={"x": int, "y": int}
            )

            if position:
                return {
                    "x": position.get("x", 0),
                    "y": position.get("y", 0),
                    "map_id": position.get("map_id", ""),
                    "last_movement_time": float(position.get("last_move_time", 0)),
                }
            return None
        except Exception as e:
            logger.error(
                "Error getting player position",
                extra={"player_id": player_id, "error": str(e)}
            )
            return None

    async def _load_position_from_db(self, player_id: int) -> Optional[Dict[str, Any]]:
        """Load player position from database."""
        if not self._session_factory:
            return None

        from server.src.models.player import Player

        async with self._db_session() as db:
            result = await db.execute(
                select(Player.x, Player.y, Player.map_id, Player.last_move_time).where(
                    Player.id == player_id
                )
            )
            row = result.first()

            if row:
                return {
                    "x": row.x or 0,
                    "y": row.y or 0,
                    "map_id": row.map_id or "",
                    "last_move_time": (row.last_move_time or datetime.now(timezone.utc)).timestamp(),
                }
            return None

    async def set_player_position(
        self, player_id: int, x: int, y: int, map_id: str
    ) -> None:
        """Set player position in cache."""
        key = PLAYER_KEY.format(player_id=player_id)
        data = await self._get_from_valkey(key) or {}
        data["x"] = x
        data["y"] = y
        data["map_id"] = map_id
        await self._cache_in_valkey(key, data, TIER1_TTL)

    # =========================================================================
    # Full State Management
    # =========================================================================

    async def get_player_full_state(self, player_id: int) -> Optional[Dict[str, Any]]:
        """Get full player state from cache."""
        key = PLAYER_KEY.format(player_id=player_id)
        return await self._get_from_valkey(key)

    async def set_player_full_state(
        self, player_id: int, state: Dict[str, Any]
    ) -> None:
        """Set full player state in cache."""
        if not self._valkey or not settings.USE_VALKEY:
            return

        key = PLAYER_KEY.format(player_id=player_id)
        await self._cache_in_valkey(key, state, TIER1_TTL)

    # =========================================================================
    # Settings
    # =========================================================================

    async def get_player_settings(self, player_id: int) -> Dict[str, Any]:
        """Get player settings from Valkey (database fallback not implemented)."""
        if not settings.USE_VALKEY or not self._valkey:
            # Database fallback not implemented - PlayerSettings model doesn't exist
            return {}

        key = PLAYER_SETTINGS_KEY.format(player_id=player_id)
        data = await self._get_from_valkey(key)

        if data:
            await self._refresh_ttl(key, TIER1_TTL)
            return {
                k: self._decode_from_valkey(v, bool if "auto" in k else str)
                for k, v in data.items()
            }

        return {}

    async def set_player_setting(self, player_id: int, key: str, value: Any) -> None:
        """Set a player setting in Valkey (database fallback not implemented)."""
        if not self._valkey or not settings.USE_VALKEY:
            # Database fallback not implemented - PlayerSettings model doesn't exist
            return

        settings_key = PLAYER_SETTINGS_KEY.format(player_id=player_id)

        # Get existing settings
        existing = await self._get_from_valkey(settings_key) or {}
        existing[key] = value

        await self._cache_in_valkey(settings_key, existing, TIER1_TTL)

    # =========================================================================
    # Combat State
    # =========================================================================

    async def get_player_combat_state(self, player_id: int) -> Optional[Dict[str, Any]]:
        """Get player combat state."""
        if not settings.USE_VALKEY or not self._valkey:
            return None

        key = PLAYER_COMBAT_STATE_KEY.format(player_id=player_id)
        return await self._get_from_valkey(key)

    async def set_player_combat_state(
        self, player_id: int, combat_state: Dict[str, Any]
    ) -> None:
        """Set player combat state."""
        if not self._valkey or not settings.USE_VALKEY:
            return

        key = PLAYER_COMBAT_STATE_KEY.format(player_id=player_id)
        await self._cache_in_valkey(key, combat_state, TIER1_TTL)

    async def clear_player_combat_state(self, player_id: int) -> None:
        """Clear player combat state (e.g., on movement)."""
        if not self._valkey or not settings.USE_VALKEY:
            return

        key = PLAYER_COMBAT_STATE_KEY.format(player_id=player_id)
        await self._valkey.delete(key)

    # =========================================================================
    # Appearance
    # =========================================================================

    async def get_player_appearance(self, player_id: int) -> Optional[Dict[str, Any]]:
        """
        Get player appearance from database.
        
        Args:
            player_id: Player ID
            
        Returns:
            Appearance dict if found, None otherwise
        """
        if not self._session_factory:
            return None

        from server.src.models.player import Player

        async with self._db_session() as db:
            result = await db.execute(
                select(Player.appearance).where(Player.id == player_id)
            )
            return result.scalar_one_or_none()

    async def update_player_appearance(
        self, player_id: int, appearance_dict: Dict[str, Any]
    ) -> bool:
        """
        Update player appearance in database.
        
        Args:
            player_id: Player ID
            appearance_dict: Appearance data to save
            
        Returns:
            True if updated successfully, False otherwise
        """
        if not self._session_factory:
            return False

        from server.src.models.player import Player

        async with self._db_session() as db:
            result = await db.execute(
                select(Player).where(Player.id == player_id)
            )
            player = result.scalar_one_or_none()

            if player is None:
                logger.warning(
                    "Cannot update appearance - player not found",
                    extra={"player_id": player_id}
                )
                return False

            player.appearance = appearance_dict
            await self._commit_if_not_test_session(db)

            logger.info(
                "Player appearance updated",
                extra={"player_id": player_id}
            )
            return True

    # =========================================================================
    # Cleanup
    # =========================================================================

    async def cleanup_player(self, player_id: int) -> None:
        """Clean up all player data from cache."""
        if not self._valkey or not settings.USE_VALKEY:
            return

        keys = [
            PLAYER_KEY.format(player_id=player_id),
            PLAYER_SETTINGS_KEY.format(player_id=player_id),
            PLAYER_COMBAT_STATE_KEY.format(player_id=player_id),
        ]
        await self._valkey.delete(keys)

    # =========================================================================
    # Auto-load helper
    # =========================================================================

    async def auto_load_with_ttl(
        self,
        key: str,
        load_fn: callable,
        ttl: int,
        decoder: Optional[Dict[str, type]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Auto-load data from loader function with TTL."""
        data = await self._get_from_valkey(key)

        if data is None:
            data = await load_fn()
            if data:
                await self._cache_in_valkey(key, data, ttl)

        if data and decoder:
            for k, type_func in decoder.items():
                if k in data:
                    data[k] = self._decode_from_valkey(data[k], type_func)

        return data


# Singleton instance
_player_state_manager: Optional[PlayerStateManager] = None


def init_player_state_manager(session_factory=None, valkey=None) -> PlayerStateManager:
    """Initialize the player state manager."""
    global _player_state_manager
    _player_state_manager = PlayerStateManager(session_factory, valkey)
    return _player_state_manager


def get_player_state_manager() -> PlayerStateManager:
    """Get the player state manager singleton."""
    if _player_state_manager is None:
        raise RuntimeError("PlayerStateManager not initialized")
    return _player_state_manager


def reset_player_state_manager() -> None:
    """Reset the player state manager singleton."""
    global _player_state_manager
    _player_state_manager = None
