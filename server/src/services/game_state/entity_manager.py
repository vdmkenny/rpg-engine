"""
Entity instance management - ephemeral combat entities.

Handles monster and NPC instances spawned in the world. Valkey-only (no DB persistence).
Entity definitions are reference data; instances are runtime-only.
"""

import traceback
from typing import Any, Dict, List, Optional, Set

from glide import GlideClient
from sqlalchemy.orm import sessionmaker

from server.src.core.config import settings
from server.src.core.logging_config import get_logger

from .base_manager import BaseManager

logger = get_logger(__name__)

# Entity instance keys (ephemeral, Valkey-only)
ENTITY_INSTANCE_KEY = "entity_instance:{instance_id}"
MAP_ENTITIES_KEY = "map_entities:{map_id}"
ENTITY_INSTANCE_COUNTER_KEY = "entity_instance_counter"
ENTITY_RESPAWN_QUEUE_KEY = "entity_respawn_queue"

# Entity instance TTL (30 minutes for active entities)
ENTITY_TTL = 1800


class EntityManager(BaseManager):
    """Manages entity instances spawned in the world."""

    def __init__(
        self,
        valkey_client: Optional[GlideClient] = None,
        session_factory: Optional[sessionmaker] = None,
    ):
        super().__init__(valkey_client, session_factory)

    # =========================================================================
    # Entity Instance Lifecycle
    # =========================================================================

    async def spawn_entity_instance(
        self,
        entity_id: int,
        map_id: str,
        x: int,
        y: int,
        current_hp: int,
        max_hp: int,
        state: str = "idle",
        target_player_id: Optional[int] = None,
        respawn_delay_seconds: int = 30,
    ) -> int:
        """Spawn a new entity instance. Returns instance ID."""
        instance_id = await self._get_next_instance_id()

        instance_data = {
            "instance_id": instance_id,
            "entity_id": entity_id,
            "map_id": map_id,
            "x": x,
            "y": y,
            "current_hp": current_hp,
            "max_hp": max_hp,
            "state": state,
            "target_player_id": target_player_id,
            "spawned_at": self._utc_timestamp(),
            "respawn_delay_seconds": respawn_delay_seconds,
        }

        if self._valkey and settings.USE_VALKEY:
            # Store instance data
            key = ENTITY_INSTANCE_KEY.format(instance_id=instance_id)
            await self._cache_in_valkey(key, instance_data, ENTITY_TTL)

            # Add to map index
            map_key = MAP_ENTITIES_KEY.format(map_id=map_id)
            await self._valkey.sadd(map_key, [str(instance_id)])
            await self._valkey.expire(map_key, ENTITY_TTL)

        return instance_id

    async def _get_next_instance_id(self) -> int:
        """Get next unique entity instance ID."""
        if not self._valkey or not settings.USE_VALKEY:
            return int(self._utc_timestamp() * 1000)

        next_id = await self._valkey.incr(ENTITY_INSTANCE_COUNTER_KEY)
        return next_id

    async def get_entity_instance(self, instance_id: int) -> Optional[Dict[str, Any]]:
        """Get entity instance by ID."""
        if not self._valkey or not settings.USE_VALKEY:
            return None

        key = ENTITY_INSTANCE_KEY.format(instance_id=instance_id)
        data = await self._get_from_valkey(key)

        if data:
            await self._refresh_ttl(key, ENTITY_TTL)
            return self._decode_entity_instance(data)

        return None

    def _decode_entity_instance(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Decode entity instance data from Valkey."""
        return {
            "instance_id": self._decode_from_valkey(data.get("instance_id"), int),
            "entity_id": self._decode_from_valkey(data.get("entity_id"), int),
            "map_id": data.get("map_id", ""),
            "x": self._decode_from_valkey(data.get("x"), int),
            "y": self._decode_from_valkey(data.get("y"), int),
            "current_hp": self._decode_from_valkey(data.get("current_hp"), int),
            "max_hp": self._decode_from_valkey(data.get("max_hp"), int),
            "state": data.get("state", "idle"),
            "target_player_id": self._decode_from_valkey(
                data.get("target_player_id"), int
            ),
            "spawned_at": self._decode_from_valkey(data.get("spawned_at"), float),
            "respawn_delay_seconds": self._decode_from_valkey(
                data.get("respawn_delay_seconds"), int
            ),
        }

    async def get_map_entities(self, map_id: str) -> List[Dict[str, Any]]:
        """Get all entity instances on a specific map."""
        if not self._valkey or not settings.USE_VALKEY:
            return []

        map_key = MAP_ENTITIES_KEY.format(map_id=map_id)
        instance_ids = await self._valkey.smembers(map_key)

        entities = []
        for instance_id_bytes in instance_ids:
            instance_id = int(self._decode_bytes(instance_id_bytes))
            entity = await self.get_entity_instance(instance_id)
            if entity:
                entities.append(entity)

        return entities

    async def update_entity_position(self, instance_id: int, x: int, y: int) -> None:
        """Update entity position."""
        if not self._valkey or not settings.USE_VALKEY:
            return

        key = ENTITY_INSTANCE_KEY.format(instance_id=instance_id)
        data = await self._get_from_valkey(key)

        if data:
            data["x"] = x
            data["y"] = y
            await self._cache_in_valkey(key, data, ENTITY_TTL)

    async def update_entity_hp(self, instance_id: int, current_hp: int) -> None:
        """Update entity HP."""
        if not self._valkey or not settings.USE_VALKEY:
            return

        key = ENTITY_INSTANCE_KEY.format(instance_id=instance_id)
        data = await self._get_from_valkey(key)

        if data:
            data["current_hp"] = current_hp
            await self._cache_in_valkey(key, data, ENTITY_TTL)

    async def set_entity_state(
        self,
        instance_id: int,
        state: str,
        target_player_id: Optional[int] = None,
    ) -> None:
        """Set entity state and target."""
        if not self._valkey or not settings.USE_VALKEY:
            return

        key = ENTITY_INSTANCE_KEY.format(instance_id=instance_id)
        data = await self._get_from_valkey(key)

        if data:
            data["state"] = state
            if target_player_id is not None:
                data["target_player_id"] = target_player_id
            await self._cache_in_valkey(key, data, ENTITY_TTL)

    async def despawn_entity(
        self, instance_id: int, death_tick: int, respawn_delay_seconds: int = 30
    ) -> None:
        """Mark entity as dead and queue for respawn."""
        if not self._valkey or not settings.USE_VALKEY:
            return

        key = ENTITY_INSTANCE_KEY.format(instance_id=instance_id)
        data = await self._get_from_valkey(key)

        if not data:
            return

        map_id = data.get("map_id")
        entity_id = self._decode_from_valkey(data.get("entity_id"), int)

        # Remove from active entities
        await self._delete_from_valkey(key)

        if map_id:
            map_key = MAP_ENTITIES_KEY.format(map_id=map_id)
            await self._valkey.srem(map_key, [str(instance_id)])

        # Queue for respawn
        respawn_at = death_tick + respawn_delay_seconds
        await self._valkey.zadd(
            ENTITY_RESPAWN_QUEUE_KEY, {str(instance_id): float(respawn_at)}
        )

        # Store respawn data
        respawn_key = f"entity_respawn:{instance_id}"
        respawn_data = {
            "entity_id": entity_id,
            "map_id": map_id,
            "death_tick": death_tick,
            "respawn_at": respawn_at,
        }
        await self._cache_in_valkey(respawn_key, respawn_data, respawn_delay_seconds + 60)

    async def finalize_entity_death(self, instance_id: int) -> None:
        """Finalize entity death (remove from respawn queue)."""
        if not self._valkey or not settings.USE_VALKEY:
            return

        # Remove from respawn queue
        await self._valkey.zrem(ENTITY_RESPAWN_QUEUE_KEY, [str(instance_id)])

        # Clean up respawn data
        respawn_key = f"entity_respawn:{instance_id}"
        await self._delete_from_valkey(respawn_key)

    async def clear_all_entity_instances(self) -> None:
        """Clear all entity instances (server shutdown)."""
        if not self._valkey or not settings.USE_VALKEY:
            return

        # Get all map keys
        map_keys = await self._valkey.keys("map_entities:*")

        # Get all instance IDs from all maps
        all_instance_ids: Set[str] = set()
        for map_key in map_keys:
            instance_ids = await self._valkey.smembers(map_key)
            all_instance_ids.update(self._decode_bytes(i) for i in instance_ids)

        # Delete all instance data
        for instance_id in all_instance_ids:
            key = ENTITY_INSTANCE_KEY.format(instance_id=instance_id)
            await self._delete_from_valkey(key)

        # Delete all map indices
        for map_key in map_keys:
            await self._delete_from_valkey(map_key)

        # Clear respawn queue
        await self._delete_from_valkey(ENTITY_RESPAWN_QUEUE_KEY)

        logger.info(f"Cleared {len(all_instance_ids)} entity instances")

    async def clear_player_as_entity_target(self, player_id: int) -> None:
        """Clear all entities targeting a specific player."""
        if not self._valkey or not settings.USE_VALKEY:
            return

        # Get all map keys
        map_keys = await self._valkey.keys("map_entities:*")

        for map_key in map_keys:
            instance_ids = await self._valkey.smembers(map_key)

            for instance_id_bytes in instance_ids:
                instance_id = int(self._decode_bytes(instance_id_bytes))
                entity = await self.get_entity_instance(instance_id)

                if entity and entity.get("target_player_id") == player_id:
                    await self.set_entity_state(instance_id, "idle", None)

    async def get_entities_targeting_player(self, player_id: int) -> List[int]:
        """Get all entity instance IDs targeting a specific player."""
        if not self._valkey or not settings.USE_VALKEY:
            return []

        targeting: List[int] = []
        map_keys = await self._valkey.keys("map_entities:*")

        for map_key in map_keys:
            instance_ids = await self._valkey.smembers(map_key)

            for instance_id_bytes in instance_ids:
                instance_id = int(self._decode_bytes(instance_id_bytes))
                entity = await self.get_entity_instance(instance_id)

                if entity and entity.get("target_player_id") == player_id:
                    targeting.append(instance_id)

        return targeting

    async def get_respawn_queue(self, current_tick: int) -> List[Dict[str, Any]]:
        """Get entities ready to respawn (respawn_at <= current_tick)."""
        if not self._valkey or not settings.USE_VALKEY:
            return []

        # Get entities with respawn_at <= current_tick
        entities_to_respawn = await self._valkey.zrangebyscore(
            ENTITY_RESPAWN_QUEUE_KEY, min_value=0, max_value=float(current_tick)
        )

        respawn_list = []
        for instance_id_bytes in entities_to_respawn:
            instance_id = int(self._decode_bytes(instance_id_bytes))

            # Get respawn data
            respawn_key = f"entity_respawn:{instance_id}"
            respawn_data = await self._get_from_valkey(respawn_key)

            if respawn_data:
                respawn_list.append(
                    {
                        "instance_id": instance_id,
                        "entity_id": self._decode_from_valkey(
                            respawn_data.get("entity_id"), int
                        ),
                        "map_id": respawn_data.get("map_id"),
                    }
                )

        return respawn_list


# Singleton instance
_entity_manager: Optional[EntityManager] = None


def init_entity_manager(
    valkey_client: Optional[GlideClient] = None,
    session_factory: Optional[sessionmaker] = None,
) -> EntityManager:
    global _entity_manager
    _entity_manager = EntityManager(valkey_client, session_factory)
    return _entity_manager


def get_entity_manager() -> EntityManager:
    if _entity_manager is None:
        raise RuntimeError("EntityManager not initialized")
    return _entity_manager


def reset_entity_manager() -> None:
    global _entity_manager
    _entity_manager = None
