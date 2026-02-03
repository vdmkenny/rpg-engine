"""
Player state management - Tier 1 essential data.

Handles online registry, position, HP, settings, and combat state.
All data follows hot/cold TTL lifecycle with transparent auto-loading.
"""

import traceback
from typing import Any, Dict, List, Optional, Set

from glide import GlideClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import sessionmaker

from server.src.core.config import settings
from server.src.core.logging_config import get_logger

from .base_manager import BaseManager, TIER1_TTL

logger = get_logger(__name__)

PLAYER_KEY = "player:{player_id}"
PLAYER_SETTINGS_KEY = "player_settings:{player_id}"
PLAYER_COMBAT_STATE_KEY = "player_combat_state:{player_id}"

# Dirty tracking keys
DIRTY_POSITION_KEY = "dirty:position"
DIRTY_PLAYER_STATE_KEY = "dirty:player_state"


class PlayerStateManager(BaseManager):
    """Manages player online status, position, HP, settings, and combat state."""

    def __init__(
        self,
        valkey_client: Optional[GlideClient] = None,
        session_factory: Optional[sessionmaker] = None,
    ):
        super().__init__(valkey_client, session_factory)
        self._online_players: Set[int] = set()
        self._username_to_id: Dict[str, int] = {}
        self._id_to_username: Dict[int, str] = {}

    # =========================================================================
    # Online Player Registry
    # =========================================================================

    def register_online_player(self, player_id: int, username: str) -> None:
        self._online_players.add(player_id)
        self._username_to_id[username] = player_id
        self._id_to_username[player_id] = username
        logger.debug(
            "Player registered as online",
            extra={"player_id": player_id, "username": username},
        )

    async def unregister_online_player(self, player_id: int) -> None:
        username = self._id_to_username.get(player_id, f"player_{player_id}")

        self._online_players.discard(player_id)

        if username and username != f"player_{player_id}":
            self._username_to_id.pop(username, None)
        self._id_to_username.pop(player_id, None)

        # Remove all player data from cache
        try:
            await self._cleanup_player_cache(player_id)
            logger.debug(
                "Player cache cleaned up on logout",
                extra={"player_id": player_id, "username": username},
            )
        except Exception as e:
            logger.error(
                "Failed to cleanup player cache",
                extra={
                    "player_id": player_id,
                    "username": username,
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                },
            )

    def is_online(self, player_id: int) -> bool:
        return player_id in self._online_players

    def get_active_player_count(self) -> int:
        return len(self._online_players)

    def get_username_for_player(self, player_id: int) -> Optional[str]:
        return self._id_to_username.get(player_id)

    def get_player_id_for_username(self, username: str) -> Optional[int]:
        return self._username_to_id.get(username)

    def get_all_online_player_ids(self) -> List[int]:
        return list(self._online_players)

    # =========================================================================
    # Player Position
    # =========================================================================

    async def get_player_position(self, player_id: int) -> Optional[Dict[str, Any]]:
        if not settings.USE_VALKEY or not self._valkey:
            # Database-only mode - load directly
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

    async def _load_position_from_db(self, player_id: int) -> Optional[Dict[str, Any]]:
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
                    "last_move_time": (
                        row.last_move_time.timestamp() if row.last_move_time else 0
                    ),
                }
            return None

    async def set_player_position(
        self, player_id: int, x: int, y: int, map_id: str
    ) -> None:
        if not self._valkey or not settings.USE_VALKEY:
            # Database-only mode - update directly
            await self._update_position_in_db(player_id, x, y, map_id)
            return

        key = PLAYER_KEY.format(player_id=player_id)
        position_data = {
            "x": x,
            "y": y,
            "map_id": map_id,
            "last_move_time": self._utc_timestamp(),
        }
        await self._cache_in_valkey(key, position_data, TIER1_TTL)

        # Mark for batch sync
        if self._valkey:
            await self._valkey.sadd(DIRTY_POSITION_KEY, [str(player_id)])

    async def _update_position_in_db(
        self, player_id: int, x: int, y: int, map_id: str
    ) -> None:
        if not self._session_factory:
            return

        from server.src.models.player import Player
        from datetime import datetime, timezone

        async with self._db_session() as db:
            result = await db.execute(select(Player).where(Player.id == player_id))
            player = result.scalar_one_or_none()
            if player:
                player.x = x
                player.y = y
                player.map_id = map_id
                player.last_move_time = datetime.now(timezone.utc)
                await self._commit_if_not_test_session(db)

    # =========================================================================
    # Player HP
    # =========================================================================

    async def get_player_hp(self, player_id: int) -> Optional[Dict[str, int]]:
        if not settings.USE_VALKEY or not self._valkey:
            return await self._load_hp_from_db(player_id)

        key = PLAYER_KEY.format(player_id=player_id)
        data = await self._get_from_valkey(key)

        if data:
            await self._refresh_ttl(key, TIER1_TTL)
            current_hp = self._decode_from_valkey(data.get("current_hp"), int)
            max_hp = self._decode_from_valkey(data.get("max_hp"), int)
            if current_hp is not None and max_hp is not None:
                return {"current_hp": current_hp, "max_hp": max_hp}

        # Auto-load from DB
        return await self._load_hp_from_db(player_id)

    async def _load_hp_from_db(self, player_id: int) -> Optional[Dict[str, int]]:
        if not self._session_factory:
            return None

        from server.src.models.player import Player

        async with self._db_session() as db:
            result = await db.execute(
                select(Player.current_hp, Player.max_hp).where(Player.id == player_id)
            )
            row = result.first()

            if row:
                return {"current_hp": row.current_hp or 1, "max_hp": row.max_hp or 1}
            return None

    async def set_player_hp(
        self, player_id: int, current_hp: int, max_hp: Optional[int] = None
    ) -> None:
        if not self._valkey or not settings.USE_VALKEY:
            await self._update_hp_in_db(player_id, current_hp, max_hp)
            return

        key = PLAYER_KEY.format(player_id=player_id)

        # Get existing data first
        existing = await self._get_from_valkey(key) or {}
        existing["current_hp"] = current_hp
        if max_hp is not None:
            existing["max_hp"] = max_hp

        await self._cache_in_valkey(key, existing, TIER1_TTL)
        await self._valkey.sadd(DIRTY_PLAYER_STATE_KEY, [str(player_id)])

    async def _update_hp_in_db(
        self, player_id: int, current_hp: int, max_hp: Optional[int]
    ) -> None:
        if not self._session_factory:
            return

        from server.src.models.player import Player

        async with self._db_session() as db:
            result = await db.execute(select(Player).where(Player.id == player_id))
            player = result.scalar_one_or_none()
            if player:
                player.current_hp = current_hp
                if max_hp is not None:
                    player.max_hp = max_hp
                await self._commit_if_not_test_session(db)

    # =========================================================================
    # Player Settings
    # =========================================================================

    async def get_player_settings(self, player_id: int) -> Dict[str, Any]:
        if not settings.USE_VALKEY or not self._valkey:
            return await self._load_settings_from_db(player_id)

        key = PLAYER_SETTINGS_KEY.format(player_id=player_id)
        data = await self._get_from_valkey(key)

        if data:
            await self._refresh_ttl(key, TIER1_TTL)
            return {
                k: self._decode_from_valkey(v, bool if "auto" in k else str)
                for k, v in data.items()
            }

        return await self._load_settings_from_db(player_id)

    async def _load_settings_from_db(self, player_id: int) -> Dict[str, Any]:
        if not self._session_factory:
            return {}

        from server.src.models.player import PlayerSettings

        async with self._db_session() as db:
            result = await db.execute(
                select(PlayerSettings).where(PlayerSettings.player_id == player_id)
            )
            settings_list = result.scalars().all()

            return {s.setting_key: s.setting_value for s in settings_list}

    async def set_player_setting(self, player_id: int, key: str, value: Any) -> None:
        if not self._valkey or not settings.USE_VALKEY:
            await self._update_setting_in_db(player_id, key, value)
            return

        settings_key = PLAYER_SETTINGS_KEY.format(player_id=player_id)

        # Get existing settings
        existing = await self._get_from_valkey(settings_key) or {}
        existing[key] = value

        await self._cache_in_valkey(settings_key, existing, TIER1_TTL)

    async def _update_setting_in_db(
        self, player_id: int, key: str, value: Any
    ) -> None:
        if not self._session_factory:
            return

        from server.src.models.player import PlayerSettings
        from sqlalchemy.dialects.postgresql import insert

        async with self._db_session() as db:
            stmt = insert(PlayerSettings).values(
                player_id=player_id, setting_key=key, setting_value=str(value)
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["player_id", "setting_key"],
                set_={"setting_value": str(value)},
            )
            await db.execute(stmt)
            await self._commit_if_not_test_session(db)

    # =========================================================================
    # Combat State
    # =========================================================================

    async def get_player_combat_state(self, player_id: int) -> Optional[Dict[str, Any]]:
        if not settings.USE_VALKEY or not self._valkey:
            return None

        key = PLAYER_COMBAT_STATE_KEY.format(player_id=player_id)
        data = await self._get_from_valkey(key)

        if data:
            await self._refresh_ttl(key, TIER1_TTL)
            return {
                "in_combat": self._decode_from_valkey(data.get("in_combat"), bool),
                "target_type": data.get("target_type"),
                "target_id": self._decode_from_valkey(data.get("target_id"), int),
                "auto_retaliate": self._decode_from_valkey(
                    data.get("auto_retaliate"), bool
                ),
            }
        return None

    async def set_player_combat_state(
        self, player_id: int, target_type: str, target_id: int
    ) -> None:
        if not self._valkey or not settings.USE_VALKEY:
            return

        key = PLAYER_COMBAT_STATE_KEY.format(player_id=player_id)
        combat_data = {
            "in_combat": True,
            "target_type": target_type,
            "target_id": target_id,
            "auto_retaliate": True,  # Default, can be overridden by settings
        }
        await self._cache_in_valkey(key, combat_data, TIER1_TTL)

    async def clear_player_combat_state(self, player_id: int) -> None:
        if not self._valkey or not settings.USE_VALKEY:
            return

        key = PLAYER_COMBAT_STATE_KEY.format(player_id=player_id)
        await self._delete_from_valkey(key)

    # =========================================================================
    # Full State Operations
    # =========================================================================

    async def get_player_full_state(self, player_id: int) -> Optional[Dict[str, Any]]:
        position = await self.get_player_position(player_id)
        if not position:
            return None

        hp = await self.get_player_hp(player_id)
        settings = await self.get_player_settings(player_id)
        combat_state = await self.get_player_combat_state(player_id)

        return {
            "player_id": player_id,
            "username": self._id_to_username.get(player_id, ""),
            "x": position.get("x", 0),
            "y": position.get("y", 0),
            "map_id": position.get("map_id", ""),
            "current_hp": hp.get("current_hp", 1) if hp else 1,
            "max_hp": hp.get("max_hp", 1) if hp else 1,
            "settings": settings,
            "combat_state": combat_state,
        }

    async def set_player_full_state(
        self, player_id: int, state: Dict[str, Any]
    ) -> None:
        if not self._valkey or not settings.USE_VALKEY:
            return

        key = PLAYER_KEY.format(player_id=player_id)
        await self._cache_in_valkey(key, state, TIER1_TTL)

    # =========================================================================
    # Cleanup
    # =========================================================================

    async def _cleanup_player_cache(self, player_id: int) -> None:
        if not self._valkey:
            return

        keys = [
            PLAYER_KEY.format(player_id=player_id),
            PLAYER_SETTINGS_KEY.format(player_id=player_id),
            PLAYER_COMBAT_STATE_KEY.format(player_id=player_id),
        ]

        for key in keys:
            await self._delete_from_valkey(key)

    async def cleanup_player_state(self, player_id: int) -> None:
        await self._cleanup_player_cache(player_id)

    # =========================================================================
    # Batch Sync Support
    # =========================================================================

    async def get_dirty_positions(self) -> List[int]:
        if not self._valkey:
            return []

        dirty = await self._valkey.smembers(DIRTY_POSITION_KEY)
        return [int(self._decode_bytes(p)) for p in dirty]

    async def clear_dirty_position(self, player_id: int) -> None:
        if self._valkey:
            await self._valkey.srem(DIRTY_POSITION_KEY, [str(player_id)])

    async def sync_player_position_to_db(self, player_id: int, db) -> None:
        if not self._valkey:
            return

        from server.src.models.player import Player
        from datetime import datetime, timezone

        key = PLAYER_KEY.format(player_id=player_id)
        data = await self._get_from_valkey(key)

        if not data:
            return

        x = self._decode_from_valkey(data.get("x"), int)
        y = self._decode_from_valkey(data.get("y"), int)
        map_id = data.get("map_id", "")
        last_move_time = self._decode_from_valkey(data.get("last_move_time"), float)

        result = await db.execute(select(Player).where(Player.id == player_id))
        player = result.scalar_one_or_none()

        if player:
            player.x = x
            player.y = y
            player.map_id = map_id
            if last_move_time:
                player.last_move_time = datetime.fromtimestamp(
                    last_move_time, tz=timezone.utc
                )

    # =========================================================================
    # Player Record CRUD
    # =========================================================================

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
        """Create a new player record in the database."""
        if not self._session_factory:
            raise RuntimeError("Database session factory not initialized")

        from server.src.models.player import Player

        async with self._db_session() as db:
            player = Player(
                username=username,
                hashed_password=hashed_password,
                x=x,
                y=y,
                map_id=map_id,
                current_hp=current_hp,
                max_hp=max_hp,
            )
            db.add(player)
            await self._commit_if_not_test_session(db)
            await db.refresh(player)
            return player.id

    async def get_player_record_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Get player record by username."""
        if not self._session_factory:
            return None

        from server.src.models.player import Player

        async with self._db_session() as db:
            result = await db.execute(select(Player).where(Player.username == username))
            player = result.scalar_one_or_none()

            if player:
                return {
                    "id": player.id,
                    "username": player.username,
                    "hashed_password": player.hashed_password,
                    "x": player.x,
                    "y": player.y,
                    "map_id": player.map_id,
                    "current_hp": player.current_hp,
                    "max_hp": player.max_hp,
                    "role": player.role,
                    "is_banned": player.is_banned,
                }
            return None

    async def get_player_record_by_id(self, player_id: int) -> Optional[Dict[str, Any]]:
        """Get player record by ID."""
        if not self._session_factory:
            return None

        from server.src.models.player import Player

        async with self._db_session() as db:
            result = await db.execute(select(Player).where(Player.id == player_id))
            player = result.scalar_one_or_none()

            if player:
                return {
                    "id": player.id,
                    "username": player.username,
                    "hashed_password": player.hashed_password,
                    "x": player.x,
                    "y": player.y,
                    "map_id": player.map_id,
                    "current_hp": player.current_hp,
                    "max_hp": player.max_hp,
                    "role": player.role,
                    "is_banned": player.is_banned,
                }
            return None

    async def username_exists(self, username: str) -> bool:
        """Check if a username already exists."""
        if not self._session_factory:
            return False

        from server.src.models.player import Player

        async with self._db_session() as db:
            result = await db.execute(
                select(Player.id).where(Player.username == username)
            )
            return result.scalar_one_or_none() is not None

    async def update_player_record_field(
        self, player_id: int, field: str, value: Any
    ) -> bool:
        """Update a specific field in the player record."""
        if not self._session_factory:
            return False

        from server.src.models.player import Player

        async with self._db_session() as db:
            result = await db.execute(select(Player).where(Player.id == player_id))
            player = result.scalar_one_or_none()

            if player and hasattr(player, field):
                setattr(player, field, value)
                await self._commit_if_not_test_session(db)
                return True
            return False

    async def delete_player_record(self, player_id: int) -> bool:
        """Delete a player record from the database."""
        if not self._session_factory:
            return False

        from server.src.models.player import Player

        async with self._db_session() as db:
            result = await db.execute(select(Player).where(Player.id == player_id))
            player = result.scalar_one_or_none()

            if player:
                await db.delete(player)
                await self._commit_if_not_test_session(db)
                return True
            return False


# Singleton instance
_player_state_manager: Optional[PlayerStateManager] = None


def init_player_state_manager(
    valkey_client: Optional[GlideClient] = None,
    session_factory: Optional[sessionmaker] = None,
) -> PlayerStateManager:
    global _player_state_manager
    _player_state_manager = PlayerStateManager(valkey_client, session_factory)
    return _player_state_manager


def get_player_state_manager() -> PlayerStateManager:
    if _player_state_manager is None:
        raise RuntimeError("PlayerStateManager not initialized")
    return _player_state_manager


def reset_player_state_manager() -> None:
    global _player_state_manager
    _player_state_manager = None
