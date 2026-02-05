"""
Integration tests for Entity AI behavior.

Tests the full AI state machine in action including:
- Entity wandering behavior
- Aggro detection and combat engagement
- Combat chasing and attacking
- Disengage and return to spawn
- LOS timeout handling

These tests use a controlled environment with mocked time/ticks
to exercise the AI without waiting for real-time intervals.
"""

import pytest
import pytest_asyncio
import asyncio
from typing import Dict, Any, List, Set, Tuple
from unittest.mock import patch, MagicMock, AsyncMock

from server.src.services.ai_service import AIService
from server.src.services.entity_spawn_service import EntitySpawnService
from server.src.core.entities import EntityState, EntityBehavior, EntityType
from server.src.services.game_state import get_entity_manager, get_reference_data_manager


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest_asyncio.fixture
async def ai_test_map(game_state_managers):
    """
    Create a test map with a simple collision grid for AI testing.
    
    Returns map_id and collision grid.
    """
    from server.src.services.map_service import get_map_manager
    
    map_id = "ai_test_map"
    
    # Create a mock tile map with open area and one wall
    class MockAITestMap:
        def __init__(self):
            self.width = 100
            self.height = 100
            self.tile_width = 32
            self.tile_height = 32
            self._collision_grid = [[False for _ in range(100)] for _ in range(100)]
            # Add a wall at y=60 from x=40 to x=60
            for x in range(40, 61):
                self._collision_grid[60][x] = True
            self.entity_spawn_points = []
            self.player_spawn_point = {"x": 10, "y": 10}
        
        def get_collision_grid(self):
            return self._collision_grid
        
        def get_spawn_position(self):
            return (10, 10)
        
        def is_walkable(self, x, y):
            if 0 <= x < 100 and 0 <= y < 100:
                return not self._collision_grid[y][x]
            return False
        
        def get_chunks_around_position(self, x, y, radius):
            return []
    
    map_manager = get_map_manager()
    mock_map = MockAITestMap()
    map_manager.maps[map_id] = mock_map
    
    yield {
        "map_id": map_id,
        "collision_grid": mock_map._collision_grid,
        "map": mock_map,
    }
    
    # Cleanup
    if map_id in map_manager.maps:
        del map_manager.maps[map_id]


@pytest_asyncio.fixture
async def spawned_goblin(game_state_managers, ai_test_map):
    """Spawn a goblin entity for testing."""
    map_id = ai_test_map["map_id"]
    entity_mgr = get_entity_manager()
    ref_mgr = get_reference_data_manager()
    
    goblin_entity_id = await ref_mgr.get_entity_id_by_name("GOBLIN")
    assert goblin_entity_id is not None, "GOBLIN entity not found in reference data"
    
    instance_id = await entity_mgr.spawn_entity_instance(
        entity_id=goblin_entity_id,
        map_id=map_id,
        x=50,
        y=50,
        current_hp=100,
        max_hp=100,
    )
    
    yield {
        "instance_id": instance_id,
        "map_id": map_id,
        "spawn_x": 50,
        "spawn_y": 50,
    }
    
    # Cleanup - despawn entity
    try:
        await entity_mgr.despawn_entity(instance_id, death_tick=0, respawn_delay_seconds=0)
    except Exception:
        pass  # May already be gone


@pytest.fixture(autouse=True)
def reset_ai_state():
    """Reset AI state before each test."""
    AIService.reset_all_timers()
    yield
    AIService.reset_all_timers()


# =============================================================================
# Idle State Integration Tests
# =============================================================================

class TestIdleStateIntegration:
    """Integration tests for entity idle behavior."""

    @pytest.mark.asyncio
    async def test_entity_starts_in_idle_state(
        self, game_state_managers, spawned_goblin, ai_test_map
    ):
        """Test that a newly spawned entity starts in idle state."""
        instance_id = spawned_goblin["instance_id"]
        entity_mgr = get_entity_manager()
        
        entity = await entity_mgr.get_entity_instance(instance_id)
        
        assert entity is not None
        assert entity["state"] == "idle"

    @pytest.mark.asyncio
    async def test_idle_entity_transitions_to_wander(
        self, game_state_managers, spawned_goblin, ai_test_map
    ):
        """Test that idle entity transitions to wander after timer expires."""
        instance_id = spawned_goblin["instance_id"]
        map_id = spawned_goblin["map_id"]
        entity_mgr = get_entity_manager()
        
        # Initialize timer to almost expired
        AIService._entity_timers[instance_id] = {
            "idle_timer": 1,  # Will expire on first process
            "wander_target": None,
            "last_move_tick": 0,
            "last_aggro_check_tick": 0,
            "last_attack_tick": 0,
        }
        
        # Process entities
        with patch("server.src.services.ai_service.settings") as mock_settings:
            mock_settings.ENTITY_AI_ENABLED = True
            mock_settings.ENTITY_AI_IDLE_MIN = 20
            mock_settings.ENTITY_AI_IDLE_MAX = 100
            mock_settings.ENTITY_AI_WANDER_INTERVAL = 40
            mock_settings.ENTITY_AI_CHASE_INTERVAL = 10
            mock_settings.ENTITY_AI_ATTACK_INTERVAL = 60
            mock_settings.ENTITY_AI_AGGRO_CHECK_INTERVAL = 5
            mock_settings.ENTITY_AI_LOS_TIMEOUT = 100
            mock_settings.ENTITY_AI_MAX_PATHFINDING_DISTANCE = 50
            
            with patch("server.src.services.ai_service.PlayerService.get_players_on_map", new_callable=AsyncMock) as mock_players:
                mock_players.return_value = []  # No players
                
                await AIService.process_entities(entity_mgr, map_id, current_tick=100)
        
        # Check entity transitioned to wander
        entity = await entity_mgr.get_entity_instance(instance_id)
        assert entity["state"] == "wander"
        
        # Check wander target was set
        assert AIService._entity_timers[instance_id]["wander_target"] is not None


# =============================================================================
# Wander State Integration Tests
# =============================================================================

class TestWanderStateIntegration:
    """Integration tests for entity wandering behavior."""

    @pytest.mark.asyncio
    async def test_wandering_entity_moves(
        self, game_state_managers, spawned_goblin, ai_test_map
    ):
        """Test that wandering entity moves toward target."""
        instance_id = spawned_goblin["instance_id"]
        map_id = spawned_goblin["map_id"]
        entity_mgr = get_entity_manager()
        
        # Set entity to wander state with target east
        await entity_mgr.set_entity_state(instance_id, EntityState.WANDER)
        
        AIService._entity_timers[instance_id] = {
            "idle_timer": 0,
            "wander_target": (55, 50),  # 5 tiles east
            "last_move_tick": 0,
            "last_aggro_check_tick": 0,
            "last_attack_tick": 0,
        }
        
        original_entity = await entity_mgr.get_entity_instance(instance_id)
        original_x = original_entity["x"]
        
        # Process entities with enough ticks for movement
        with patch("server.src.services.ai_service.settings") as mock_settings:
            mock_settings.ENTITY_AI_ENABLED = True
            mock_settings.ENTITY_AI_IDLE_MIN = 20
            mock_settings.ENTITY_AI_IDLE_MAX = 100
            mock_settings.ENTITY_AI_WANDER_INTERVAL = 40
            mock_settings.ENTITY_AI_CHASE_INTERVAL = 10
            mock_settings.ENTITY_AI_ATTACK_INTERVAL = 60
            mock_settings.ENTITY_AI_AGGRO_CHECK_INTERVAL = 5
            mock_settings.ENTITY_AI_LOS_TIMEOUT = 100
            mock_settings.ENTITY_AI_MAX_PATHFINDING_DISTANCE = 50
            
            with patch("server.src.services.ai_service.PlayerService.get_players_on_map", new_callable=AsyncMock) as mock_players:
                mock_players.return_value = []
                
                await AIService.process_entities(entity_mgr, map_id, current_tick=100)
        
        # Check entity moved
        entity = await entity_mgr.get_entity_instance(instance_id)
        assert entity["x"] == original_x + 1  # Moved one tile east

    @pytest.mark.asyncio
    async def test_wandering_entity_returns_to_idle_at_target(
        self, game_state_managers, spawned_goblin, ai_test_map
    ):
        """Test that entity returns to idle when reaching wander target."""
        instance_id = spawned_goblin["instance_id"]
        map_id = spawned_goblin["map_id"]
        entity_mgr = get_entity_manager()
        
        # Set entity at its target location
        await entity_mgr.set_entity_state(instance_id, EntityState.WANDER)
        
        AIService._entity_timers[instance_id] = {
            "idle_timer": 0,
            "wander_target": (50, 50),  # Already at target
            "last_move_tick": 0,
            "last_aggro_check_tick": 0,
            "last_attack_tick": 0,
        }
        
        with patch("server.src.services.ai_service.settings") as mock_settings:
            mock_settings.ENTITY_AI_ENABLED = True
            mock_settings.ENTITY_AI_IDLE_MIN = 20
            mock_settings.ENTITY_AI_IDLE_MAX = 100
            mock_settings.ENTITY_AI_WANDER_INTERVAL = 40
            mock_settings.ENTITY_AI_CHASE_INTERVAL = 10
            mock_settings.ENTITY_AI_ATTACK_INTERVAL = 60
            mock_settings.ENTITY_AI_AGGRO_CHECK_INTERVAL = 5
            mock_settings.ENTITY_AI_LOS_TIMEOUT = 100
            mock_settings.ENTITY_AI_MAX_PATHFINDING_DISTANCE = 50
            
            with patch("server.src.services.ai_service.PlayerService.get_players_on_map", new_callable=AsyncMock) as mock_players:
                mock_players.return_value = []
                
                await AIService.process_entities(entity_mgr, map_id, current_tick=100)
        
        # Check entity returned to idle
        entity = await entity_mgr.get_entity_instance(instance_id)
        assert entity["state"] == "idle"


# =============================================================================
# Aggro Detection Integration Tests
# =============================================================================

class TestAggroIntegration:
    """Integration tests for aggro detection and combat engagement."""

    @pytest.mark.asyncio
    async def test_aggressive_entity_aggros_nearby_player(
        self, game_state_managers, spawned_goblin, ai_test_map
    ):
        """Test that aggressive entity enters combat when player is nearby."""
        instance_id = spawned_goblin["instance_id"]
        map_id = spawned_goblin["map_id"]
        
        # Entity at
        entity_mgr = get_entity_manager()
        
        # Entity at (50, 50), player nearby at (55, 50) - distance 5, within aggro 10
        nearby_player = [
            {"player_id": 100, "username": "test_player", "x": 55, "y": 50}
        ]
        
        AIService._entity_timers[instance_id] = {
            "idle_timer": 50,
            "wander_target": None,
            "last_move_tick": 0,
            "last_aggro_check_tick": 0,  # Will trigger aggro check
            "last_attack_tick": 0,
        }
        
        with patch("server.src.services.ai_service.settings") as mock_settings:
            mock_settings.ENTITY_AI_ENABLED = True
            mock_settings.ENTITY_AI_IDLE_MIN = 20
            mock_settings.ENTITY_AI_IDLE_MAX = 100
            mock_settings.ENTITY_AI_WANDER_INTERVAL = 40
            mock_settings.ENTITY_AI_CHASE_INTERVAL = 10
            mock_settings.ENTITY_AI_ATTACK_INTERVAL = 60
            mock_settings.ENTITY_AI_AGGRO_CHECK_INTERVAL = 5
            mock_settings.ENTITY_AI_LOS_TIMEOUT = 100
            mock_settings.ENTITY_AI_MAX_PATHFINDING_DISTANCE = 50
            
            with patch("server.src.services.ai_service.PlayerService.get_players_on_map", new_callable=AsyncMock) as mock_players:
                mock_players.return_value = nearby_player
                
                await AIService.process_entities(entity_mgr, map_id, current_tick=100)
        
        # Check entity entered combat
        entity = await entity_mgr.get_entity_instance(instance_id)
        assert entity["state"] == "combat"
        assert entity["target_player_id"] == 100

    @pytest.mark.asyncio
    async def test_entity_does_not_aggro_distant_player(
        self, game_state_managers, spawned_goblin, ai_test_map
    ):
        """Test that entity ignores players outside aggro radius."""
        instance_id = spawned_goblin["instance_id"]
        map_id = spawned_goblin["map_id"]
        
        # Entity at
        entity_mgr = get_entity_manager()
        
        # Entity at (50, 50), player far at (70, 50) - distance 20, outside aggro 10
        distant_player = [
            {"player_id": 100, "username": "test_player", "x": 70, "y": 50}
        ]
        
        AIService._entity_timers[instance_id] = {
            "idle_timer": 50,
            "wander_target": None,
            "last_move_tick": 0,
            "last_aggro_check_tick": 0,
            "last_attack_tick": 0,
        }
        
        with patch("server.src.services.ai_service.settings") as mock_settings:
            mock_settings.ENTITY_AI_ENABLED = True
            mock_settings.ENTITY_AI_IDLE_MIN = 20
            mock_settings.ENTITY_AI_IDLE_MAX = 100
            mock_settings.ENTITY_AI_WANDER_INTERVAL = 40
            mock_settings.ENTITY_AI_CHASE_INTERVAL = 10
            mock_settings.ENTITY_AI_ATTACK_INTERVAL = 60
            mock_settings.ENTITY_AI_AGGRO_CHECK_INTERVAL = 5
            mock_settings.ENTITY_AI_LOS_TIMEOUT = 100
            mock_settings.ENTITY_AI_MAX_PATHFINDING_DISTANCE = 50
            
            with patch("server.src.services.ai_service.PlayerService.get_players_on_map", new_callable=AsyncMock) as mock_players:
                mock_players.return_value = distant_player
                
                await AIService.process_entities(entity_mgr, map_id, current_tick=100)
        
        # Check entity stayed in idle
        entity = await entity_mgr.get_entity_instance(instance_id)
        assert entity["state"] == "idle"


# =============================================================================
# Combat State Integration Tests
# =============================================================================

class TestCombatIntegration:
    """Integration tests for entity combat behavior."""

    @pytest.mark.asyncio
    async def test_combat_entity_chases_target(
        self, game_state_managers, spawned_goblin, ai_test_map
    ):
        """Test that entity in combat chases its target."""
        instance_id = spawned_goblin["instance_id"]
        map_id = spawned_goblin["map_id"]
        entity_mgr = get_entity_manager()
        
        # Set entity to combat state targeting player at (55, 50)
        await entity_mgr.set_entity_state(
            instance_id, 
            EntityState.COMBAT,
            target_player_id=100
        )
        
        player = [
            {"player_id": 100, "username": "test_player", "x": 55, "y": 50}
        ]
        
        AIService._entity_timers[instance_id] = {
            "idle_timer": 0,
            "wander_target": None,
            "last_move_tick": 0,  # Ready to move
            "last_aggro_check_tick": 100,
            "last_attack_tick": 0,
        }
        
        original_entity = await entity_mgr.get_entity_instance(instance_id)
        original_x = original_entity["x"]
        
        with patch("server.src.services.ai_service.settings") as mock_settings:
            mock_settings.ENTITY_AI_ENABLED = True
            mock_settings.ENTITY_AI_IDLE_MIN = 20
            mock_settings.ENTITY_AI_IDLE_MAX = 100
            mock_settings.ENTITY_AI_WANDER_INTERVAL = 40
            mock_settings.ENTITY_AI_CHASE_INTERVAL = 10
            mock_settings.ENTITY_AI_ATTACK_INTERVAL = 60
            mock_settings.ENTITY_AI_AGGRO_CHECK_INTERVAL = 5
            mock_settings.ENTITY_AI_LOS_TIMEOUT = 100
            mock_settings.ENTITY_AI_MAX_PATHFINDING_DISTANCE = 50
            
            with patch("server.src.services.ai_service.PlayerService.get_players_on_map", new_callable=AsyncMock) as mock_players:
                mock_players.return_value = player
                
                await AIService.process_entities(entity_mgr, map_id, current_tick=100)
        
        # Check entity moved toward player
        entity = await entity_mgr.get_entity_instance(instance_id)
        assert entity["x"] == original_x + 1  # Moved east toward player
        assert entity["state"] == "combat"  # Still in combat

    @pytest.mark.asyncio
    async def test_combat_entity_returns_when_target_leaves(
        self, game_state_managers, spawned_goblin, ai_test_map
    ):
        """Test that entity returns to spawn when target leaves map."""
        instance_id = spawned_goblin["instance_id"]
        map_id = spawned_goblin["map_id"]
        entity_mgr = get_entity_manager()
        
        # Set entity to combat state
        await entity_mgr.set_entity_state(
            instance_id, 
            EntityState.COMBAT,
            target_player_id=100
        )
        
        AIService._entity_timers[instance_id] = {
            "idle_timer": 0,
            "wander_target": None,
            "last_move_tick": 0,
            "last_aggro_check_tick": 100,
            "last_attack_tick": 0,
        }
        
        with patch("server.src.services.ai_service.settings") as mock_settings:
            mock_settings.ENTITY_AI_ENABLED = True
            mock_settings.ENTITY_AI_IDLE_MIN = 20
            mock_settings.ENTITY_AI_IDLE_MAX = 100
            mock_settings.ENTITY_AI_WANDER_INTERVAL = 40
            mock_settings.ENTITY_AI_CHASE_INTERVAL = 10
            mock_settings.ENTITY_AI_ATTACK_INTERVAL = 60
            mock_settings.ENTITY_AI_AGGRO_CHECK_INTERVAL = 5
            mock_settings.ENTITY_AI_LOS_TIMEOUT = 100
            mock_settings.ENTITY_AI_MAX_PATHFINDING_DISTANCE = 50
            
            with patch("server.src.services.ai_service.PlayerService.get_players_on_map", new_callable=AsyncMock) as mock_players:
                mock_players.return_value = []  # Player left
                
                await AIService.process_entities(entity_mgr, map_id, current_tick=100)
        
        # Check entity is returning
        entity = await entity_mgr.get_entity_instance(instance_id)
        assert entity["state"] == "returning"

    @pytest.mark.asyncio
    async def test_combat_entity_disengages_beyond_radius(
        self, game_state_managers, spawned_goblin, ai_test_map
    ):
        """Test entity disengages when target moves beyond disengage radius from spawn."""
        instance_id = spawned_goblin["instance_id"]
        map_id = spawned_goblin["map_id"]
        entity_mgr = get_entity_manager()
        
        # Set entity to combat state
        await entity_mgr.set_entity_state(
            instance_id, 
            EntityState.COMBAT,
            target_player_id=100
        )
        
        # Player is 30 tiles from spawn (50, 50) - beyond disengage_radius of 20
        far_player = [
            {"player_id": 100, "username": "test_player", "x": 80, "y": 50}
        ]
        
        AIService._entity_timers[instance_id] = {
            "idle_timer": 0,
            "wander_target": None,
            "last_move_tick": 0,
            "last_aggro_check_tick": 100,
            "last_attack_tick": 0,
        }
        
        with patch("server.src.services.ai_service.settings") as mock_settings:
            mock_settings.ENTITY_AI_ENABLED = True
            mock_settings.ENTITY_AI_IDLE_MIN = 20
            mock_settings.ENTITY_AI_IDLE_MAX = 100
            mock_settings.ENTITY_AI_WANDER_INTERVAL = 40
            mock_settings.ENTITY_AI_CHASE_INTERVAL = 10
            mock_settings.ENTITY_AI_ATTACK_INTERVAL = 60
            mock_settings.ENTITY_AI_AGGRO_CHECK_INTERVAL = 5
            mock_settings.ENTITY_AI_LOS_TIMEOUT = 100
            mock_settings.ENTITY_AI_MAX_PATHFINDING_DISTANCE = 50
            
            with patch("server.src.services.ai_service.PlayerService.get_players_on_map", new_callable=AsyncMock) as mock_players:
                mock_players.return_value = far_player
                
                await AIService.process_entities(entity_mgr, map_id, current_tick=100)
        
        # Check entity is returning (disengaged)
        entity = await entity_mgr.get_entity_instance(instance_id)
        assert entity["state"] == "returning"


# =============================================================================
# Returning State Integration Tests
# =============================================================================

class TestReturningIntegration:
    """Integration tests for entity returning to spawn behavior."""

    @pytest.mark.asyncio
    async def test_returning_entity_moves_to_spawn(
        self, game_state_managers, spawned_goblin, ai_test_map
    ):
        """Test that returning entity moves toward spawn."""
        instance_id = spawned_goblin["instance_id"]
        map_id = spawned_goblin["map_id"]
        
        # Move entity
        entity_mgr = get_entity_manager()
        
        # Move entity away from spawn
        await entity_mgr.update_entity_position(instance_id, 55, 50)
        await entity_mgr.set_entity_state(instance_id, EntityState.RETURNING)
        
        AIService._entity_timers[instance_id] = {
            "idle_timer": 0,
            "wander_target": None,
            "last_move_tick": 0,
            "last_aggro_check_tick": 100,
            "last_attack_tick": 0,
        }
        
        with patch("server.src.services.ai_service.settings") as mock_settings:
            mock_settings.ENTITY_AI_ENABLED = True
            mock_settings.ENTITY_AI_IDLE_MIN = 20
            mock_settings.ENTITY_AI_IDLE_MAX = 100
            mock_settings.ENTITY_AI_WANDER_INTERVAL = 40
            mock_settings.ENTITY_AI_CHASE_INTERVAL = 10
            mock_settings.ENTITY_AI_ATTACK_INTERVAL = 60
            mock_settings.ENTITY_AI_AGGRO_CHECK_INTERVAL = 5
            mock_settings.ENTITY_AI_LOS_TIMEOUT = 100
            mock_settings.ENTITY_AI_MAX_PATHFINDING_DISTANCE = 50
            
            with patch("server.src.services.ai_service.PlayerService.get_players_on_map", new_callable=AsyncMock) as mock_players:
                mock_players.return_value = []
                
                await AIService.process_entities(entity_mgr, map_id, current_tick=100)
        
        # Check entity moved toward spawn
        entity = await entity_mgr.get_entity_instance(instance_id)
        assert entity["x"] == 54  # Moved west toward spawn at 50

    @pytest.mark.asyncio
    async def test_returning_entity_heals_at_spawn(
        self, game_state_managers, spawned_goblin, ai_test_map
    ):
        """Test that entity heals to full when returning to spawn."""
        instance_id = spawned_goblin["instance_id"]
        map_id = spawned_goblin["map_id"]
        
        # Entity at
        entity_mgr = get_entity_manager()
        
        # Entity at spawn but with reduced HP
        await entity_mgr.update_entity_hp(instance_id, 50)
        await entity_mgr.set_entity_state(instance_id, EntityState.RETURNING)
        
        AIService._entity_timers[instance_id] = {
            "idle_timer": 0,
            "wander_target": None,
            "last_move_tick": 0,
            "last_aggro_check_tick": 100,
            "last_attack_tick": 0,
        }
        
        with patch("server.src.services.ai_service.settings") as mock_settings:
            mock_settings.ENTITY_AI_ENABLED = True
            mock_settings.ENTITY_AI_IDLE_MIN = 20
            mock_settings.ENTITY_AI_IDLE_MAX = 100
            mock_settings.ENTITY_AI_WANDER_INTERVAL = 40
            mock_settings.ENTITY_AI_CHASE_INTERVAL = 10
            mock_settings.ENTITY_AI_ATTACK_INTERVAL = 60
            mock_settings.ENTITY_AI_AGGRO_CHECK_INTERVAL = 5
            mock_settings.ENTITY_AI_LOS_TIMEOUT = 100
            mock_settings.ENTITY_AI_MAX_PATHFINDING_DISTANCE = 50
            
            with patch("server.src.services.ai_service.PlayerService.get_players_on_map", new_callable=AsyncMock) as mock_players:
                mock_players.return_value = []
                
                await AIService.process_entities(entity_mgr, map_id, current_tick=100)
        
        # Check entity healed and returned to idle
        entity = await entity_mgr.get_entity_instance(instance_id)
        assert entity["current_hp"] == 100
        assert entity["state"] == "idle"


# =============================================================================
# Full State Machine Cycle Tests
# =============================================================================

class TestFullStateMachineCycle:
    """Tests for complete state machine cycles."""

    @pytest.mark.asyncio
    async def test_full_combat_cycle(
        self, game_state_managers, spawned_goblin, ai_test_map
    ):
        """
        Test complete combat cycle:
        IDLE -> COMBAT (aggro) -> RETURNING (target leaves) -> IDLE (at spawn)
        """
        instance_id = spawned_goblin["instance_id"]
        map_id = spawned_goblin["map_id"]
        
        # Start with entity idle
        entity_mgr = get_entity_manager()
        
        # Start with entity idle, player nearby
        AIService._entity_timers[instance_id] = {
            "idle_timer": 50,
            "wander_target": None,
            "last_move_tick": 0,
            "last_aggro_check_tick": 0,
            "last_attack_tick": 0,
        }
        
        nearby_player = [
            {"player_id": 100, "username": "test_player", "x": 55, "y": 50}
        ]
        
        with patch("server.src.services.ai_service.settings") as mock_settings:
            mock_settings.ENTITY_AI_ENABLED = True
            mock_settings.ENTITY_AI_IDLE_MIN = 20
            mock_settings.ENTITY_AI_IDLE_MAX = 100
            mock_settings.ENTITY_AI_WANDER_INTERVAL = 40
            mock_settings.ENTITY_AI_CHASE_INTERVAL = 10
            mock_settings.ENTITY_AI_ATTACK_INTERVAL = 60
            mock_settings.ENTITY_AI_AGGRO_CHECK_INTERVAL = 5
            mock_settings.ENTITY_AI_LOS_TIMEOUT = 100
            mock_settings.ENTITY_AI_MAX_PATHFINDING_DISTANCE = 50
            
            # Step 1: Process with player nearby -> should enter combat
            with patch("server.src.services.ai_service.PlayerService.get_players_on_map", new_callable=AsyncMock) as mock_players:
                mock_players.return_value = nearby_player
                await AIService.process_entities(entity_mgr, map_id, current_tick=100)
            
            entity = await entity_mgr.get_entity_instance(instance_id)
            assert entity["state"] == "combat", "Should enter combat when player nearby"
            
            # Step 2: Player leaves -> should transition to returning
            with patch("server.src.services.ai_service.PlayerService.get_players_on_map", new_callable=AsyncMock) as mock_players:
                mock_players.return_value = []  # Player left
                await AIService.process_entities(entity_mgr, map_id, current_tick=110)
            
            entity = await entity_mgr.get_entity_instance(instance_id)
            assert entity["state"] == "returning", "Should return when target leaves"
            
            # Step 3: Entity is at spawn -> should heal and return to idle
            # (Entity was never moved from spawn in this test)
            await AIService.process_entities(entity_mgr, map_id, current_tick=200)
            
            entity = await entity_mgr.get_entity_instance(instance_id)
            assert entity["state"] == "idle", "Should return to idle at spawn"

    @pytest.mark.asyncio
    async def test_wander_cycle(
        self, game_state_managers, spawned_goblin, ai_test_map
    ):
        """
        Test wander cycle:
        IDLE (timer expires) -> WANDER (reach target) -> IDLE
        """
        instance_id = spawned_goblin["instance_id"]
        map_id = spawned_goblin["map_id"]
        
        # Start with timer
        entity_mgr = get_entity_manager()
        
        # Start with timer about to expire
        AIService._entity_timers[instance_id] = {
            "idle_timer": 1,
            "wander_target": None,
            "last_move_tick": 0,
            "last_aggro_check_tick": 0,
            "last_attack_tick": 0,
        }
        
        with patch("server.src.services.ai_service.settings") as mock_settings:
            mock_settings.ENTITY_AI_ENABLED = True
            mock_settings.ENTITY_AI_IDLE_MIN = 20
            mock_settings.ENTITY_AI_IDLE_MAX = 100
            mock_settings.ENTITY_AI_WANDER_INTERVAL = 40
            mock_settings.ENTITY_AI_CHASE_INTERVAL = 10
            mock_settings.ENTITY_AI_ATTACK_INTERVAL = 60
            mock_settings.ENTITY_AI_AGGRO_CHECK_INTERVAL = 5
            mock_settings.ENTITY_AI_LOS_TIMEOUT = 100
            mock_settings.ENTITY_AI_MAX_PATHFINDING_DISTANCE = 50
            
            with patch("server.src.services.ai_service.PlayerService.get_players_on_map", new_callable=AsyncMock) as mock_players:
                mock_players.return_value = []
                
                # Step 1: Idle -> Wander
                await AIService.process_entities(entity_mgr, map_id, current_tick=100)
                
                entity = await entity_mgr.get_entity_instance(instance_id)
                assert entity["state"] == "wander", "Should transition to wander"
                wander_target = AIService._entity_timers[instance_id]["wander_target"]
                assert wander_target is not None
                
                # Step 2: Set entity position to target to simulate reaching it
                await entity_mgr.update_entity_position(instance_id, wander_target[0], wander_target[1])
                await AIService.process_entities(entity_mgr, map_id, current_tick=200)
                
                entity = await entity_mgr.get_entity_instance(instance_id)
                assert entity["state"] == "idle", "Should return to idle at target"


# =============================================================================
# Edge Case Tests
# =============================================================================

class TestAIEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_process_entities_handles_missing_entity_def(
        self, game_state_managers, ai_test_map
    ):
        """Test that unknown entity types are handled gracefully."""
        map_id = ai_test_map["map_id"]
        entity_mgr = get_entity_manager()
        ref_mgr = get_reference_data_manager()
        
        # Use a non-existent entity ID that won't be found in reference data
        # This simulates an entity instance with invalid entity_id
        non_existent_entity_id = 999999
        
        instance_id = await entity_mgr.spawn_entity_instance(
            entity_id=non_existent_entity_id,
            map_id=map_id,
            x=50,
            y=50,
            current_hp=100,
            max_hp=100,
        )
        
        with patch("server.src.services.ai_service.settings") as mock_settings:
            mock_settings.ENTITY_AI_ENABLED = True
            mock_settings.ENTITY_AI_IDLE_MIN = 20
            mock_settings.ENTITY_AI_IDLE_MAX = 100
            mock_settings.ENTITY_AI_WANDER_INTERVAL = 40
            mock_settings.ENTITY_AI_AGGRO_CHECK_INTERVAL = 5
            
            with patch("server.src.services.ai_service.PlayerService.get_players_on_map", new_callable=AsyncMock) as mock_players:
                mock_players.return_value = []
                
                # Should not raise even with unknown entity type
                await AIService.process_entities(entity_mgr, map_id, current_tick=100)

    @pytest.mark.asyncio
    async def test_dead_entities_skipped(
        self, game_state_managers, spawned_goblin, ai_test_map
    ):
        """Test that dead entities are not processed."""
        instance_id = spawned_goblin["instance_id"]
        map_id = spawned_goblin["map_id"]
        entity_mgr = get_entity_manager()
        
        # Kill the entity
        await entity_mgr.update_entity_hp(instance_id, 0)
        await entity_mgr.set_entity_state(instance_id, EntityState.DEAD)
        
        AIService._entity_timers[instance_id] = {
            "idle_timer": 1,
            "wander_target": None,
            "last_move_tick": 0,
            "last_aggro_check_tick": 0,
            "last_attack_tick": 0,
        }
        
        with patch("server.src.services.ai_service.settings") as mock_settings:
            mock_settings.ENTITY_AI_ENABLED = True
            mock_settings.ENTITY_AI_IDLE_MIN = 20
            mock_settings.ENTITY_AI_IDLE_MAX = 100
            mock_settings.ENTITY_AI_WANDER_INTERVAL = 40
            mock_settings.ENTITY_AI_AGGRO_CHECK_INTERVAL = 5
            
            with patch("server.src.services.ai_service.PlayerService.get_players_on_map", new_callable=AsyncMock) as mock_players:
                mock_players.return_value = []
                
                await AIService.process_entities(entity_mgr, map_id, current_tick=100)
        
        # Entity should still be dead, not have transitioned
        entity = await entity_mgr.get_entity_instance(instance_id)
        assert entity["state"] == "dead"
