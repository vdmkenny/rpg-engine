"""
Entity spawn service for managing entity instance creation.

Handles spawning entities from Tiled map object layers and managing
entity respawn logic.
"""

import traceback
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple, Union

from glide import RangeByScore, ScoreBoundary

from server.src.core.entities import (
    EntityState,
    EntityType,
    get_entity_by_name,
    is_humanoid,
)
from server.src.core.humanoids import HumanoidID, HumanoidDefinition
from server.src.core.monsters import MonsterID, MonsterDefinition
from server.src.core.logging_config import get_logger
from server.src.services.game_state import (
    EntityManager,
    PlayerStateManager,
    ENTITY_RESPAWN_QUEUE_KEY,
)
from server.src.services.map_service import get_map_manager
from server.src.services.pathfinding_service import PathfindingService

logger = get_logger(__name__)


class EntitySpawnService:
    """
    Entity spawn service for creating entity instances from Tiled maps.
    
    Spawns entities on server startup and handles respawn logic.
    """
    
    @staticmethod
    async def spawn_map_entities(player_mgr: PlayerStateManager, entity_mgr: EntityManager, map_id: str) -> int:
        """
        Spawn all entity instances for a map from Tiled spawn points.
        
        Args:
            player_mgr: PlayerStateManager instance
            entity_mgr: EntityManager instance
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
                await EntitySpawnService._spawn_single_entity(entity_mgr, map_id, spawn_point)
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
        entity_mgr: EntityManager, map_id: str, spawn_point: Dict
    ) -> int:
        """
        Spawn a single entity instance from a spawn point.
        
        Args:
            entity_mgr: EntityManager instance
            map_id: Map identifier
            spawn_point: Spawn point data from Tiled
            
        Returns:
            Entity instance ID
        """
        entity_id_str = spawn_point["entity_id"]
        
        # Get entity definition from HumanoidID or MonsterID enum
        entity_enum = get_entity_by_name(entity_id_str)
        if entity_enum is None:
            logger.error(
                "Unknown entity ID in spawn point",
                extra={
                    "entity_id": entity_id_str,
                    "spawn_point": spawn_point,
                    "traceback": traceback.format_exc(),
                }
            )
            raise ValueError(f"Unknown entity ID: {entity_id_str}")
        
        entity_def: Union[HumanoidDefinition, MonsterDefinition] = entity_enum.value
        entity_type = EntityType.HUMANOID_NPC if is_humanoid(entity_id_str) else EntityType.MONSTER
        
        # Extract spawn point data
        spawn_x = spawn_point["x"]
        spawn_y = spawn_point["y"]
        wander_radius = spawn_point.get("wander_radius", 0)
        spawn_point_id = spawn_point["id"]
        
        # Optional overrides from Tiled (only applicable to monsters)
        aggro_override = spawn_point.get("aggro_override")
        disengage_override = spawn_point.get("disengage_override")
        
        # Get the numeric entity_id from the enum
        entity_id = entity_enum.value.id if hasattr(entity_enum.value, 'id') else entity_enum.value.value
        
        # Spawn entity instance with simplified API
        instance_id = await entity_mgr.spawn_entity_instance(
            entity_id=entity_id,
            map_id=map_id,
            x=spawn_x,
            y=spawn_y,
            current_hp=entity_def.max_hp,
            max_hp=entity_def.max_hp,
            state="idle",
            target_player_id=None,
        )
        
        # Store additional spawn metadata in entity state
        key = f"entity_instance:{instance_id}"
        if entity_mgr._valkey:
            # Get current data and update with spawn metadata
            current_data = await entity_mgr._get_from_valkey(key)
            if current_data:
                current_data["entity_name"] = entity_id_str
                current_data["entity_type"] = entity_type.value
                current_data["spawn_x"] = spawn_x
                current_data["spawn_y"] = spawn_y
                current_data["wander_radius"] = wander_radius
                current_data["spawn_point_id"] = spawn_point_id
                current_data["aggro_radius"] = aggro_override
                current_data["disengage_radius"] = disengage_override
                await entity_mgr._cache_in_valkey(key, current_data, 1800)
        
        logger.debug(
            "Entity spawned",
            extra={
                "instance_id": instance_id,
                "entity_type": entity_type.value,
                "entity_name": entity_id_str,
                "map_id": map_id,
                "position": (spawn_x, spawn_y),
            }
        )
        
        return instance_id
    
    @staticmethod
    async def check_respawn_queue(entity_mgr: EntityManager) -> int:
        """
        Check respawn queue and respawn entities that are ready.
        
        This should be called periodically by the game loop.
        
        Args:
            entity_mgr: EntityManager instance
            
        Returns:
            Number of entities respawned
        """
        if not entity_mgr._valkey:
            return 0
        
        # Get entities ready to respawn (score <= current time)
        current_time = datetime.now(timezone.utc).timestamp()
        score_query = RangeByScore(
            start=ScoreBoundary(0, is_inclusive=True),
            end=ScoreBoundary(current_time, is_inclusive=True),
        )
        ready_to_respawn = await entity_mgr._valkey.zrange(
            ENTITY_RESPAWN_QUEUE_KEY,
            score_query,
        )
        
        if not ready_to_respawn:
            return 0
        
        respawned_count = 0
        for instance_id_bytes in ready_to_respawn:
            instance_id = int(instance_id_bytes.decode() if isinstance(instance_id_bytes, bytes) else instance_id_bytes)
            
            # Get entity data to respawn
            entity_data = await entity_mgr.get_entity_instance(instance_id)
            if not entity_data:
                logger.warning("Entity not found for respawn", extra={"instance_id": instance_id})
                await entity_mgr._valkey.zrem(ENTITY_RESPAWN_QUEUE_KEY, [str(instance_id)])
                continue
            
            # Get spawn coordinates from entity data or fall back to current position
            spawn_x = entity_data.get("spawn_x", entity_data.get("x"))
            spawn_y = entity_data.get("spawn_y", entity_data.get("y"))
            
            # Find valid respawn position (avoid entity collision)
            respawn_x, respawn_y = await EntitySpawnService.find_respawn_position(
                entity_mgr,
                entity_data["map_id"],
                spawn_x,
                spawn_y,
            )
            
            # Respawn entity at valid position
            await entity_mgr.update_entity_position(instance_id, respawn_x, respawn_y)
            await entity_mgr.update_entity_hp(instance_id, entity_data["max_hp"])
            await entity_mgr.set_entity_state(instance_id, "idle")
            
            # Remove from respawn queue
            await entity_mgr._valkey.zrem(ENTITY_RESPAWN_QUEUE_KEY, [str(instance_id)])
            
            respawned_count += 1
            logger.debug(
                "Entity respawned",
                extra={
                    "instance_id": instance_id,
                    "entity_type": entity_data.get("entity_type", "unknown"),
                    "entity_name": entity_data.get("entity_name", "unknown"),
                    "map_id": entity_data["map_id"],
                }
            )
        
        if respawned_count > 0:
            logger.info("Entities respawned", extra={"count": respawned_count})
        
        return respawned_count
    
    @staticmethod
    async def get_entity_positions(entity_mgr: EntityManager, map_id: str) -> Dict[int, Tuple[int, int]]:
        """
        Get all non-dead entity positions on a map.
        
        Used for entity collision avoidance during pathfinding and respawn.
        
        Args:
            entity_mgr: EntityManager instance
            map_id: Map identifier
            
        Returns:
            Dict mapping instance_id -> (x, y) position for all non-dead entities
        """
        entities = await entity_mgr.get_map_entities(map_id)
        
        positions: Dict[int, Tuple[int, int]] = {}
        for entity in entities:
            # Skip dead entities
            state = entity.get("state", "idle")
            if state in ("dead", "dying"):
                continue
            
            instance_id = entity.get("instance_id")
            x = entity.get("x")
            y = entity.get("y")
            
            if instance_id is not None and x is not None and y is not None:
                positions[instance_id] = (x, y)
        
        return positions
    
    @staticmethod
    async def find_respawn_position(
        entity_mgr: EntityManager,
        map_id: str,
        spawn_x: int,
        spawn_y: int,
    ) -> Tuple[int, int]:
        """
        Find a valid respawn position, avoiding other entities.
        
        Uses PathfindingService.find_nearest_open_tile() to find the nearest
        walkable position if the spawn point is occupied.
        
        Args:
            entity_mgr: EntityManager instance
            map_id: Map identifier
            spawn_x: Preferred spawn X coordinate
            spawn_y: Preferred spawn Y coordinate
            
        Returns:
            (x, y) position for respawn (may be spawn point or nearby open tile)
        """
        # Get map collision grid
        map_manager = get_map_manager()
        tile_map = map_manager.get_map(map_id)
        
        if not tile_map:
            logger.warning(
                "Map not found for respawn position check",
                extra={"map_id": map_id}
            )
            return (spawn_x, spawn_y)
        
        collision_grid = tile_map.get_collision_grid()
        
        # Get current entity positions on this map
        entity_positions = await EntitySpawnService.get_entity_positions(entity_mgr, map_id)
        blocked_positions: Set[Tuple[int, int]] = set(entity_positions.values())
        
        # Check if spawn position is available
        spawn_pos = (spawn_x, spawn_y)
        if spawn_pos not in blocked_positions:
            return spawn_pos
        
        # Spawn position is occupied, find nearest open tile
        open_tile = PathfindingService.find_nearest_open_tile(
            center=spawn_pos,
            collision_grid=collision_grid,
            blocked_positions=blocked_positions,
            max_radius=10,
        )
        
        if open_tile:
            logger.debug(
                "Respawn position adjusted due to collision",
                extra={
                    "original": spawn_pos,
                    "adjusted": open_tile,
                    "map_id": map_id,
                }
            )
            return open_tile
        
        # Fallback to original spawn position if no open tile found
        logger.warning(
            "Could not find open respawn position, using original spawn",
            extra={"spawn": spawn_pos, "map_id": map_id}
        )
        return spawn_pos
