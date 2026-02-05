"""
Unit tests for entity spawn service.
"""

import pytest
import pytest_asyncio
from unittest.mock import Mock, AsyncMock, patch
from server.src.services.entity_spawn_service import EntitySpawnService
from server.src.core.entities import get_entity_by_name
from server.src.core.monsters import MonsterID
from server.src.core.humanoids import HumanoidID
from server.src.services.game_state.entity_manager import (
    EntityManager,
    ENTITY_INSTANCE_KEY,
    ENTITY_RESPAWN_QUEUE_KEY,
)


class FakeValkey:
    """Fake Valkey client for testing."""
    
    def __init__(self):
        self.data = {}
        self.sets = {}
        self.counters = {}
        self.sorted_sets = {}
    
    async def incr(self, key):
        """Increment counter."""
        if key not in self.counters:
            self.counters[key] = 0
        self.counters[key] += 1
        return self.counters[key]
    
    async def hset(self, key, mapping):
        """Set hash fields."""
        if key not in self.data:
            self.data[key] = {}
        self.data[key].update(mapping)
    
    async def hgetall(self, key):
        """Get all hash fields."""
        return self.data.get(key, {})
    
    async def sadd(self, key, members):
        """Add to set."""
        if key not in self.sets:
            self.sets[key] = set()
        self.sets[key].update(members)
    
    async def smembers(self, key):
        """Get set members."""
        return list(self.sets.get(key, set()))
    
    async def srem(self, key, members):
        """Remove from set."""
        if key in self.sets:
            for member in members:
                self.sets[key].discard(member)
    
    async def hdel(self, key, fields):
        """Delete hash fields."""
        if key in self.data:
            for field in fields:
                self.data[key].pop(field, None)
    
    async def zadd(self, key, mapping):
        """Add to sorted set."""
        if key not in self.sorted_sets:
            self.sorted_sets[key] = {}
        self.sorted_sets[key].update(mapping)
    
    async def zrangebyscore(self, key, min, max):
        """Get sorted set members by score range."""
        if key not in self.sorted_sets:
            return []
        return [
            member.encode() if isinstance(member, str) else member
            for member, score in self.sorted_sets[key].items()
            if min <= score <= max
        ]
    
    async def zrange(self, key, score_query):
        """Get sorted set members by score range using RangeByScore."""
        if key not in self.sorted_sets:
            return []
        # Extract min/max from RangeByScore query
        # In Glide, query.start and query.end are already converted to strings
        min_score = float(score_query.start)
        max_score = float(score_query.end)
        return [
            member.encode() if isinstance(member, str) else member
            for member, score in self.sorted_sets[key].items()
            if min_score <= score <= max_score
        ]
    
    async def zrem(self, key, members):
        """Remove from sorted set."""
        if key in self.sorted_sets:
            for member in members:
                self.sorted_sets[key].pop(member, None)
    
    async def set(self, key, value):
        """Set value."""
        self.data[key] = value
    
    async def delete(self, keys):
        """Delete keys."""
        for key in keys:
            self.data.pop(key, None)
            self.sets.pop(key, None)
            self.sorted_sets.pop(key, None)
    
    async def expire(self, key, ttl):
        """Set expiration (no-op for fake)."""
        pass
    
    async def exists(self, keys):
        """Check if keys exist."""
        if not keys:
            return 0
        return sum(1 for k in keys if k in self.data or k in self.sets or k in self.sorted_sets)


class FakeEntityManager(EntityManager):
    """Fake EntityManager for testing that uses FakeValkey."""
    
    def __init__(self):
        # Don't call super().__init__ to avoid needing real GlideClient
        self._valkey = FakeValkey()
        self._session_factory = None
    
    async def spawn_entity_instance(
        self,
        entity_id: int,
        map_id: str,
        x: int,
        y: int,
        current_hp: int,
        max_hp: int,
        state: str = "idle",
        target_player_id: int = None,
        respawn_delay_seconds: int = 30,
    ) -> int:
        """Spawn a new entity instance with additional spawn metadata."""
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
            # Additional spawn metadata added by EntitySpawnService
            "entity_name": None,
            "entity_type": None,
            "spawn_x": x,
            "spawn_y": y,
            "wander_radius": 0,
            "spawn_point_id": None,
            "aggro_radius": None,
            "disengage_radius": None,
        }
        
        # Always store in FakeValkey regardless of USE_VALKEY setting
        if self._valkey:
            # Store instance data
            key = ENTITY_INSTANCE_KEY.format(instance_id=instance_id)
            await self._cache_in_valkey(key, instance_data, 1800)
            
            # Add to map index
            from server.src.services.game_state.entity_manager import MAP_ENTITIES_KEY
            map_key = MAP_ENTITIES_KEY.format(map_id=map_id)
            await self._valkey.sadd(map_key, [str(instance_id)])
        
        return instance_id
    
    async def get_entity_instance(self, instance_id: int):
        """Get entity instance by ID (override to bypass USE_VALKEY check)."""
        if not self._valkey:
            return None
        
        key = ENTITY_INSTANCE_KEY.format(instance_id=instance_id)
        data = await self._get_from_valkey(key)
        
        if data:
            # Decode values from Valkey storage
            decoded_data = {}
            for k, v in data.items():
                if isinstance(v, bytes):
                    v = v.decode()
                # Try to convert numeric strings back to numbers
                if k in ["instance_id", "entity_id", "x", "y", "current_hp", "max_hp", 
                        "target_player_id", "spawned_at", "respawn_delay_seconds",
                        "spawn_x", "spawn_y", "wander_radius", "spawn_point_id"]:
                    try:
                        v = int(v)
                    except (ValueError, TypeError):
                        pass
                decoded_data[k] = v
            return decoded_data
        
        return None
    
    async def _cache_in_valkey(self, key, data, ttl):
        """Store data in fake Valkey."""
        await self._valkey.hset(key, data)
    
    async def _get_from_valkey(self, key):
        """Get data from fake Valkey."""
        return await self._valkey.hgetall(key)
    
    async def _delete_from_valkey(self, key):
        """Delete data from fake Valkey."""
        await self._valkey.delete([key])
    
    def _decode_bytes(self, value):
        """Decode bytes to string."""
        if isinstance(value, bytes):
            return value.decode()
        return value
    
    def _decode_from_valkey(self, value, type_func=None):
        """Decode value from Valkey."""
        if value is None:
            return None
        decoded = self._decode_bytes(value)
        if type_func:
            return type_func(decoded)
        return decoded
    
    def _utc_timestamp(self):
        """Get UTC timestamp."""
        import time
        return time.time()


@pytest.mark.asyncio
class TestEntitySpawnService:
    """Test entity spawning functionality."""
    
    async def test_spawn_single_entity_basic(self, game_state_managers):
        """Test spawning a single basic entity."""
        entity_mgr = FakeEntityManager()
        map_id = "test_map"
        
        spawn_point = {
            "id": 10,
            "name": "Goblin Spawn 1",
            "entity_id": "GOBLIN",
            "x": 10,
            "y": 15,
            "wander_radius": 5,
            "aggro_override": None,
            "disengage_override": None,
            "patrol_route": None,
        }
        
        instance_id = await EntitySpawnService._spawn_single_entity(
            entity_mgr, map_id, spawn_point
        )
        
        # Verify entity was spawned
        assert instance_id == 1
        entity = await entity_mgr.get_entity_instance(instance_id)
        
        assert entity is not None
        assert entity["entity_name"] == "GOBLIN"
        assert entity["map_id"] == map_id
        assert entity["x"] == 10
        assert entity["y"] == 15
        assert entity["spawn_x"] == 10
        assert entity["spawn_y"] == 15
        assert entity["wander_radius"] == 5
        assert entity["state"] == "idle"
        assert entity["max_hp"] == MonsterID.GOBLIN.value.max_hp
    
    async def test_spawn_single_entity_with_overrides(self, game_state_managers):
        """Test spawning entity with aggro/disengage overrides."""
        entity_mgr = FakeEntityManager()
        map_id = "test_map"
        
        spawn_point = {
            "id": 20,
            "name": "Custom Bear",
            "entity_id": "FOREST_BEAR",
            "x": 50,
            "y": 50,
            "wander_radius": 0,
            "aggro_override": 15,
            "disengage_override": 45,
            "patrol_route": None,
        }
        
        instance_id = await EntitySpawnService._spawn_single_entity(
            entity_mgr, map_id, spawn_point
        )
        
        entity = await entity_mgr.get_entity_instance(instance_id)
        
        assert entity["aggro_radius"] == 15
        assert entity["disengage_radius"] == 45
    
    async def test_spawn_single_entity_unknown_entity_id(self, game_state_managers):
        """Test spawning with invalid entity ID raises error."""
        entity_mgr = FakeEntityManager()
        map_id = "test_map"
        
        spawn_point = {
            "id": 30,
            "name": "Invalid Spawn",
            "entity_id": "INVALID_ENTITY",
            "x": 10,
            "y": 10,
            "wander_radius": 0,
            "aggro_override": None,
            "disengage_override": None,
            "patrol_route": None,
        }
        
        # Should raise ValueError for unknown entity
        with pytest.raises(ValueError, match="Unknown entity ID"):
            await EntitySpawnService._spawn_single_entity(entity_mgr, map_id, spawn_point)
    
    async def test_spawn_map_entities_multiple(self, game_state_managers):
        """Test spawning multiple entities from a map."""
        entity_mgr = FakeEntityManager()
        
        # Create mock map manager
        mock_tile_map = Mock()
        mock_tile_map.entity_spawn_points = [
            {
                "id": 10,
                "name": "Goblin 1",
                "entity_id": "GOBLIN",
                "x": 10,
                "y": 10,
                "wander_radius": 5,
                "aggro_override": None,
                "disengage_override": None,
                "patrol_route": None,
            },
            {
                "id": 20,
                "name": "Rat 1",
                "entity_id": "GIANT_RAT",
                "x": 20,
                "y": 20,
                "wander_radius": 3,
                "aggro_override": None,
                "disengage_override": None,
                "patrol_route": None,
            },
            {
                "id": 30,
                "name": "Shopkeeper",
                "entity_id": "SHOPKEEPER_BOB",
                "x": 30,
                "y": 30,
                "wander_radius": 0,
                "aggro_override": None,
                "disengage_override": None,
                "patrol_route": None,
            },
        ]
        
        with patch("server.src.services.entity_spawn_service.get_map_manager") as mock_get_mm:
            mock_map_manager = Mock()
            mock_map_manager.get_map.return_value = mock_tile_map
            mock_get_mm.return_value = mock_map_manager
            
            spawned_count = await EntitySpawnService.spawn_map_entities(None, entity_mgr, "test_map")
        
        # Verify correct count
        assert spawned_count == 3
        
        # Verify all entities were spawned by checking map entities
        from server.src.services.game_state.entity_manager import MAP_ENTITIES_KEY
        map_key = MAP_ENTITIES_KEY.format(map_id="test_map")
        instance_ids = await entity_mgr._valkey.smembers(map_key)
        assert len(instance_ids) == 3
        
        # Verify each entity was created correctly
        for i, instance_id_bytes in enumerate(instance_ids, 1):
            instance_id = int(instance_id_bytes.decode() if isinstance(instance_id_bytes, bytes) else instance_id_bytes)
            entity = await entity_mgr.get_entity_instance(instance_id)
            assert entity is not None
    
    async def test_spawn_map_entities_no_spawn_points(self, game_state_managers):
        """Test spawning when map has no spawn points."""
        entity_mgr = FakeEntityManager()
        
        mock_tile_map = Mock()
        mock_tile_map.entity_spawn_points = []
        
        with patch("server.src.services.entity_spawn_service.get_map_manager") as mock_get_mm:
            mock_map_manager = Mock()
            mock_map_manager.get_map.return_value = mock_tile_map
            mock_get_mm.return_value = mock_map_manager
            
            spawned_count = await EntitySpawnService.spawn_map_entities(None, entity_mgr, "test_map")
        
        assert spawned_count == 0
        
        # Verify no entities on map
        from server.src.services.game_state.entity_manager import MAP_ENTITIES_KEY
        map_key = MAP_ENTITIES_KEY.format(map_id="test_map")
        instance_ids = await entity_mgr._valkey.smembers(map_key)
        assert len(instance_ids) == 0
    
    async def test_spawn_map_entities_map_not_found(self, game_state_managers):
        """Test spawning when map doesn't exist."""
        entity_mgr = FakeEntityManager()
        
        with patch("server.src.services.entity_spawn_service.get_map_manager") as mock_get_mm:
            mock_map_manager = Mock()
            mock_map_manager.get_map.return_value = None  # Map not found
            mock_get_mm.return_value = mock_map_manager
            
            spawned_count = await EntitySpawnService.spawn_map_entities(None, entity_mgr, "invalid_map")
        
        assert spawned_count == 0
    
    async def test_spawn_map_entities_partial_failure(self, game_state_managers):
        """Test that spawning continues after individual spawn failure."""
        entity_mgr = FakeEntityManager()
        
        mock_tile_map = Mock()
        mock_tile_map.entity_spawn_points = [
            {
                "id": 10,
                "name": "Valid",
                "entity_id": "GOBLIN",
                "x": 10,
                "y": 10,
                "wander_radius": 5,
                "aggro_override": None,
                "disengage_override": None,
                "patrol_route": None,
            },
            {
                "id": 20,
                "name": "Invalid",
                "entity_id": "INVALID_ENTITY",  # Will fail
                "x": 20,
                "y": 20,
                "wander_radius": 0,
                "aggro_override": None,
                "disengage_override": None,
                "patrol_route": None,
            },
            {
                "id": 30,
                "name": "Valid 2",
                "entity_id": "GIANT_RAT",
                "x": 30,
                "y": 30,
                "wander_radius": 3,
                "aggro_override": None,
                "disengage_override": None,
                "patrol_route": None,
            },
        ]
        
        with patch("server.src.services.entity_spawn_service.get_map_manager") as mock_get_mm:
            mock_map_manager = Mock()
            mock_map_manager.get_map.return_value = mock_tile_map
            mock_get_mm.return_value = mock_map_manager
            
            spawned_count = await EntitySpawnService.spawn_map_entities(None, entity_mgr, "test_map")
        
        # Should spawn 2 out of 3 (skipping the invalid one)
        assert spawned_count == 2
        
        # Verify only 2 entities were spawned
        from server.src.services.game_state.entity_manager import MAP_ENTITIES_KEY
        map_key = MAP_ENTITIES_KEY.format(map_id="test_map")
        instance_ids = await entity_mgr._valkey.smembers(map_key)
        assert len(instance_ids) == 2
    
    async def test_check_respawn_queue_empty(self, game_state_managers):
        """Test respawn queue check with no entities ready."""
        entity_mgr = FakeEntityManager()
        
        respawned_count = await EntitySpawnService.check_respawn_queue(entity_mgr)
        
        assert respawned_count == 0
    
    async def test_check_respawn_queue_entity_ready(self, game_state_managers, frozen_time):
        """Test respawning entity from queue."""
        entity_mgr = FakeEntityManager()
        
        # Spawn entity first
        spawn_point = {
            "id": 10,
            "name": "Goblin",
            "entity_id": "GOBLIN",
            "x": 10,
            "y": 15,
            "wander_radius": 5,
            "aggro_override": None,
            "disengage_override": None,
            "patrol_route": None,
        }
        
        instance_id = await EntitySpawnService._spawn_single_entity(
            entity_mgr, "test_map", spawn_point
        )
        
        # Simulate entity death - update to dead state and moved position
        key = ENTITY_INSTANCE_KEY.format(instance_id=instance_id)
        entity_data = await entity_mgr._get_from_valkey(key)
        entity_data["state"] = "dead"
        entity_data["current_hp"] = 0
        entity_data["x"] = 5  # Moved from spawn
        entity_data["y"] = 5
        await entity_mgr._cache_in_valkey(key, entity_data, 1800)
        
        # Add to respawn queue with past timestamp (ready to respawn)
        await entity_mgr._valkey.zadd(ENTITY_RESPAWN_QUEUE_KEY, {str(instance_id): 0})
        
        # Set frozen time and check respawn queue
        frozen_time.set_time(1000)
        respawned_count = await EntitySpawnService.check_respawn_queue(entity_mgr)
        
        assert respawned_count == 1
        
        # Verify entity was respawned at spawn position
        entity = await entity_mgr.get_entity_instance(instance_id)
        assert entity["x"] == 10  # Back at spawn_x
        assert entity["y"] == 15  # Back at spawn_y
        assert entity["current_hp"] == entity["max_hp"]  # Full HP
        assert entity["state"] == "idle"
    
    async def test_check_respawn_queue_not_ready_yet(self, game_state_managers, frozen_time):
        """Test that entities not ready to respawn are skipped."""
        entity_mgr = FakeEntityManager()
        
        # Spawn entity
        spawn_point = {
            "id": 10,
            "name": "Goblin",
            "entity_id": "GOBLIN",
            "x": 10,
            "y": 15,
            "wander_radius": 5,
            "aggro_override": None,
            "disengage_override": None,
            "patrol_route": None,
        }
        
        instance_id = await EntitySpawnService._spawn_single_entity(
            entity_mgr, "test_map", spawn_point
        )
        
        # Set frozen time and add to respawn queue with future timestamp (not ready)
        frozen_time.set_time(1000)
        future_time = 2000
        await entity_mgr._valkey.zadd(ENTITY_RESPAWN_QUEUE_KEY, {str(instance_id): future_time})
        
        # Check respawn queue - should not respawn since future_time > current_time
        respawned_count = await EntitySpawnService.check_respawn_queue(entity_mgr)
        
        # Should not respawn anything
        assert respawned_count == 0
    
    async def test_spawn_different_entity_types(self, game_state_managers):
        """Test spawning various entity types."""
        entity_mgr = FakeEntityManager()
        
        entity_types = [
            ("GOBLIN", 10, 10),
            ("GIANT_RAT", 20, 20),
            ("FOREST_BEAR", 30, 30),
            ("VILLAGE_GUARD", 40, 40),
            ("SHOPKEEPER_BOB", 50, 50),
            ("VILLAGE_ELDER", 60, 60),
        ]
        
        for entity_id, x, y in entity_types:
            spawn_point = {
                "id": x,
                "name": f"{entity_id} Spawn",
                "entity_id": entity_id,
                "x": x,
                "y": y,
                "wander_radius": 0,
                "aggro_override": None,
                "disengage_override": None,
                "patrol_route": None,
            }
            
            instance_id = await EntitySpawnService._spawn_single_entity(
                entity_mgr, "test_map", spawn_point
            )
            
            entity = await entity_mgr.get_entity_instance(instance_id)
            assert entity["entity_name"] == entity_id
            assert entity["x"] == x
            assert entity["y"] == y
        
        # Verify all entities spawned
        from server.src.services.game_state.entity_manager import MAP_ENTITIES_KEY
        map_key = MAP_ENTITIES_KEY.format(map_id="test_map")
        instance_ids = await entity_mgr._valkey.smembers(map_key)
        assert len(instance_ids) == 6
