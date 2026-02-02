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


class FakeGSM:
    """Fake GameStateManager for testing."""
    
    def __init__(self):
        self.valkey = FakeValkey()
        self.entity_instances = {}
        self.next_instance_id = 1
    
    async def spawn_entity_instance(
        self,
        entity_name,
        entity_type,
        map_id,
        x,
        y,
        spawn_x,
        spawn_y,
        max_hp,
        wander_radius,
        spawn_point_id,
        aggro_radius=None,
        disengage_radius=None,
    ):
        """Spawn entity instance."""
        instance_id = self.next_instance_id
        self.next_instance_id += 1
        
        self.entity_instances[instance_id] = {
            "id": instance_id,
            "entity_name": entity_name,
            "entity_type": entity_type.value if hasattr(entity_type, 'value') else entity_type,
            "map_id": map_id,
            "x": x,
            "y": y,
            "spawn_x": spawn_x,
            "spawn_y": spawn_y,
            "current_hp": max_hp,
            "max_hp": max_hp,
            "state": "idle",
            "wander_radius": wander_radius,
            "spawn_point_id": spawn_point_id,
            "aggro_radius": aggro_radius,
            "disengage_radius": disengage_radius,
        }
        
        return instance_id
    
    async def get_entity_instance(self, instance_id):
        """Get entity instance."""
        return self.entity_instances.get(instance_id)
    
    async def update_entity_position(self, instance_id, x, y):
        """Update entity position."""
        if instance_id in self.entity_instances:
            self.entity_instances[instance_id]["x"] = x
            self.entity_instances[instance_id]["y"] = y
    
    async def update_entity_hp(self, instance_id, current_hp):
        """Update entity HP."""
        if instance_id in self.entity_instances:
            self.entity_instances[instance_id]["current_hp"] = current_hp
    
    async def set_entity_state(self, instance_id, state, **kwargs):
        """Set entity state."""
        if instance_id in self.entity_instances:
            self.entity_instances[instance_id]["state"] = state


@pytest.mark.asyncio
class TestEntitySpawnService:
    """Test entity spawning functionality."""
    
    async def test_spawn_single_entity_basic(self):
        """Test spawning a single basic entity."""
        gsm = FakeGSM()
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
            gsm, map_id, spawn_point
        )
        
        # Verify entity was spawned
        assert instance_id == 1
        entity = await gsm.get_entity_instance(instance_id)
        
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
    
    async def test_spawn_single_entity_with_overrides(self):
        """Test spawning entity with aggro/disengage overrides."""
        gsm = FakeGSM()
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
            gsm, map_id, spawn_point
        )
        
        entity = await gsm.get_entity_instance(instance_id)
        
        assert entity["aggro_radius"] == 15
        assert entity["disengage_radius"] == 45
    
    async def test_spawn_single_entity_unknown_entity_id(self):
        """Test spawning with invalid entity ID raises error."""
        gsm = FakeGSM()
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
            await EntitySpawnService._spawn_single_entity(gsm, map_id, spawn_point)
    
    async def test_spawn_map_entities_multiple(self):
        """Test spawning multiple entities from a map."""
        gsm = FakeGSM()
        
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
            
            spawned_count = await EntitySpawnService.spawn_map_entities(gsm, "test_map")
        
        # Verify correct count
        assert spawned_count == 3
        
        # Verify all entities were spawned
        assert len(gsm.entity_instances) == 3
        assert gsm.entity_instances[1]["entity_name"] == "GOBLIN"
        assert gsm.entity_instances[2]["entity_name"] == "GIANT_RAT"
        assert gsm.entity_instances[3]["entity_name"] == "SHOPKEEPER_BOB"
    
    async def test_spawn_map_entities_no_spawn_points(self):
        """Test spawning when map has no spawn points."""
        gsm = FakeGSM()
        
        mock_tile_map = Mock()
        mock_tile_map.entity_spawn_points = []
        
        with patch("server.src.services.entity_spawn_service.get_map_manager") as mock_get_mm:
            mock_map_manager = Mock()
            mock_map_manager.get_map.return_value = mock_tile_map
            mock_get_mm.return_value = mock_map_manager
            
            spawned_count = await EntitySpawnService.spawn_map_entities(gsm, "test_map")
        
        assert spawned_count == 0
        assert len(gsm.entity_instances) == 0
    
    async def test_spawn_map_entities_map_not_found(self):
        """Test spawning when map doesn't exist."""
        gsm = FakeGSM()
        
        with patch("server.src.services.entity_spawn_service.get_map_manager") as mock_get_mm:
            mock_map_manager = Mock()
            mock_map_manager.get_map.return_value = None  # Map not found
            mock_get_mm.return_value = mock_map_manager
            
            spawned_count = await EntitySpawnService.spawn_map_entities(gsm, "invalid_map")
        
        assert spawned_count == 0
    
    async def test_spawn_map_entities_partial_failure(self):
        """Test that spawning continues after individual spawn failure."""
        gsm = FakeGSM()
        
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
            
            spawned_count = await EntitySpawnService.spawn_map_entities(gsm, "test_map")
        
        # Should spawn 2 out of 3 (skipping the invalid one)
        assert spawned_count == 2
        assert len(gsm.entity_instances) == 2
    
    async def test_check_respawn_queue_empty(self):
        """Test respawn queue check with no entities ready."""
        gsm = FakeGSM()
        
        respawned_count = await EntitySpawnService.check_respawn_queue(gsm)
        
        assert respawned_count == 0
    
    async def test_check_respawn_queue_entity_ready(self):
        """Test respawning entity from queue."""
        gsm = FakeGSM()
        
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
            gsm, "test_map", spawn_point
        )
        
        # Simulate entity death - update to dead state and moved position
        gsm.entity_instances[instance_id]["state"] = "dead"
        gsm.entity_instances[instance_id]["current_hp"] = 0
        gsm.entity_instances[instance_id]["x"] = 5  # Moved from spawn
        gsm.entity_instances[instance_id]["y"] = 5
        
        # Add to respawn queue with past timestamp (ready to respawn)
        await gsm.valkey.zadd("entity_respawn_queue", {str(instance_id): 0})
        
        # Check respawn queue (patch _utc_timestamp from GSM module)
        with patch("server.src.services.game_state_manager._utc_timestamp", return_value=1000):
            respawned_count = await EntitySpawnService.check_respawn_queue(gsm)
        
        assert respawned_count == 1
        
        # Verify entity was respawned at spawn position
        entity = await gsm.get_entity_instance(instance_id)
        assert entity["x"] == 10  # Back at spawn_x
        assert entity["y"] == 15  # Back at spawn_y
        assert entity["current_hp"] == entity["max_hp"]  # Full HP
        assert entity["state"] == "idle"
    
    async def test_check_respawn_queue_not_ready_yet(self):
        """Test that entities not ready to respawn are skipped."""
        gsm = FakeGSM()
        
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
            gsm, "test_map", spawn_point
        )
        
        # Add to respawn queue with future timestamp (not ready)
        current_time = 1000
        future_time = 2000
        await gsm.valkey.zadd("entity_respawn_queue", {str(instance_id): future_time})
        
        # Check respawn queue (patch _utc_timestamp from GSM module)
        with patch("server.src.services.game_state_manager._utc_timestamp", return_value=current_time):
            respawned_count = await EntitySpawnService.check_respawn_queue(gsm)
        
        # Should not respawn anything
        assert respawned_count == 0
    
    async def test_spawn_different_entity_types(self):
        """Test spawning various entity types."""
        gsm = FakeGSM()
        
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
                gsm, "test_map", spawn_point
            )
            
            entity = await gsm.get_entity_instance(instance_id)
            assert entity["entity_name"] == entity_id
            assert entity["x"] == x
            assert entity["y"] == y
        
        # Verify all entities spawned
        assert len(gsm.entity_instances) == 6
