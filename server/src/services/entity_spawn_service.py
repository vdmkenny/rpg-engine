"""
Entity spawn service for managing entity instance creation.

Handles spawning entities from Tiled map object layers and managing
entity respawn logic.
"""

import traceback
from typing import Dict, List, Optional

from server.src.core.entities import EntityID
from server.src.core.logging_config import get_logger
from server.src.services.game_state_manager import GameStateManager
from server.src.services.map_service import get_map_manager

logger = get_logger(__name__)


class EntitySpawnService:
    """
    Entity spawn service for creating entity instances from Tiled maps.
    
    Spawns entities on server startup and handles respawn logic.
    """
    
    @staticmethod
    async def spawn_map_entities(gsm: GameStateManager, map_id: str) -> int:
        """
        Spawn all entity instances for a map from Tiled spawn points.
        
        Args:
            gsm: GameStateManager instance
            map_id: Map identifier
            
        Returns:
            Number of entities spawned
        """
        map_manager = get_map_manager()
        tile_map = map_manager.get_map(map_id)
        
        if not tile_map:
            logger.warning("Map not found for entity spawning", extra={"map_id": map_id})
            return 0
        
        if not tile_map.entity_spawn_points:
            logger.debug("No entity spawn points on map", extra={"map_id": map_id})
            return 0
        
        spawned_count = 0
        for spawn_point in tile_map.entity_spawn_points:
            try:
                await EntitySpawnService._spawn_single_entity(gsm, map_id, spawn_point)
                spawned_count += 1
            except Exception as e:
                logger.error(
                    "Failed to spawn entity",
                    extra={
                        "map_id": map_id,
                        "spawn_point": spawn_point,
                        "error": str(e),
                        "traceback": traceback.format_exc(),
                    }
                )
        
        logger.info(
            "Entities spawned for map",
            extra={"map_id": map_id, "count": spawned_count}
        )
        
        return spawned_count
    
    @staticmethod
    async def _spawn_single_entity(
        gsm: GameStateManager, map_id: str, spawn_point: Dict
    ) -> int:
        """
        Spawn a single entity instance from a spawn point.
        
        Args:
            gsm: GameStateManager instance
            map_id: Map identifier
            spawn_point: Spawn point data from Tiled
            
        Returns:
            Entity instance ID
        """
        entity_id_str = spawn_point["entity_id"]
        
        # Get entity definition from EntityID enum
        try:
            entity_enum = EntityID[entity_id_str]
            entity_def = entity_enum.value
        except KeyError:
            logger.error(
                "Unknown entity ID in spawn point",
                extra={
                    "entity_id": entity_id_str,
                    "spawn_point": spawn_point,
                    "traceback": traceback.format_exc(),
                }
            )
            raise ValueError(f"Unknown entity ID: {entity_id_str}")
        
        # Extract spawn point data
        spawn_x = spawn_point["x"]
        spawn_y = spawn_point["y"]
        wander_radius = spawn_point.get("wander_radius", 0)
        spawn_point_id = spawn_point["id"]
        
        # Optional overrides from Tiled
        aggro_override = spawn_point.get("aggro_override")
        disengage_override = spawn_point.get("disengage_override")
        
        # Spawn entity instance
        instance_id = await gsm.spawn_entity_instance(
            entity_name=entity_id_str,
            map_id=map_id,
            x=spawn_x,
            y=spawn_y,
            spawn_x=spawn_x,
            spawn_y=spawn_y,
            max_hp=entity_def.max_hp,
            wander_radius=wander_radius,
            spawn_point_id=spawn_point_id,
            aggro_radius=aggro_override,
            disengage_radius=disengage_override,
        )
        
        logger.debug(
            "Entity spawned",
            extra={
                "instance_id": instance_id,
                "entity_type": entity_id_str,
                "map_id": map_id,
                "position": (spawn_x, spawn_y),
            }
        )
        
        return instance_id
    
    @staticmethod
    async def check_respawn_queue(gsm: GameStateManager) -> int:
        """
        Check respawn queue and respawn entities that are ready.
        
        This should be called periodically by the game loop.
        
        Args:
            gsm: GameStateManager instance
            
        Returns:
            Number of entities respawned
        """
        if not gsm.valkey:
            return 0
        
        from server.src.services.game_state_manager import (
            ENTITY_RESPAWN_QUEUE_KEY,
            _utc_timestamp,
        )
        
        # Get entities ready to respawn (score <= current time)
        current_time = _utc_timestamp()
        ready_to_respawn = await gsm.valkey.zrangebyscore(
            ENTITY_RESPAWN_QUEUE_KEY,
            min=0,
            max=current_time,
        )
        
        if not ready_to_respawn:
            return 0
        
        respawned_count = 0
        for instance_id_bytes in ready_to_respawn:
            instance_id = int(instance_id_bytes.decode() if isinstance(instance_id_bytes, bytes) else instance_id_bytes)
            
            # Get entity data to respawn
            entity_data = await gsm.get_entity_instance(instance_id)
            if not entity_data:
                logger.warning("Entity not found for respawn", extra={"instance_id": instance_id})
                await gsm.valkey.zrem(ENTITY_RESPAWN_QUEUE_KEY, [str(instance_id)])
                continue
            
            # Respawn entity at spawn position
            await gsm.update_entity_position(instance_id, entity_data["spawn_x"], entity_data["spawn_y"])
            await gsm.update_entity_hp(instance_id, entity_data["max_hp"])
            await gsm.set_entity_state(instance_id, "idle")
            
            # Remove from respawn queue
            await gsm.valkey.zrem(ENTITY_RESPAWN_QUEUE_KEY, [str(instance_id)])
            
            respawned_count += 1
            logger.debug(
                "Entity respawned",
                extra={
                    "instance_id": instance_id,
                    "entity_type": entity_data["entity_name"],
                    "map_id": entity_data["map_id"],
                }
            )
        
        if respawned_count > 0:
            logger.info("Entities respawned", extra={"count": respawned_count})
        
        return respawned_count
