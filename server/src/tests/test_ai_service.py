"""
Unit tests for AIService.

Tests entity AI behavior including state machine transitions,
aggro detection, movement, and combat.
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any, List, Set, Tuple

from server.src.services.ai_service import AIService
from server.src.services.game_state_manager import GameStateManager
from server.src.core.entities import EntityBehavior, EntityState
from server.src.core.monsters import MonsterDefinition


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_gsm():
    """Create a mock GameStateManager for testing."""
    gsm = AsyncMock(spec=GameStateManager)
    return gsm


@pytest.fixture
def mock_entity_def():
    """Create a mock MonsterDefinition with default values."""
    entity_def = MagicMock(spec=MonsterDefinition)
    entity_def.behavior = EntityBehavior.AGGRESSIVE
    entity_def.aggro_radius = 10
    entity_def.disengage_radius = 20
    entity_def.base_damage = 5
    entity_def.attack_speed = 1.0
    return entity_def


@pytest.fixture
def basic_entity():
    """Create a basic entity dict for testing."""
    return {
        "id": 1,
        "entity_name": "GOBLIN",
        "x": 50,
        "y": 50,
        "spawn_x": 50,
        "spawn_y": 50,
        "state": "idle",
        "current_hp": 100,
        "max_hp": 100,
        "aggro_radius": 10,
        "disengage_radius": 20,
        "wander_radius": 5,
        "target_player_id": None,
        "los_lost_at_tick": None,
    }


@pytest.fixture
def simple_collision_grid():
    """Create a simple 100x100 collision grid with all tiles walkable."""
    return [[False for _ in range(100)] for _ in range(100)]


@pytest.fixture
def collision_grid_with_wall():
    """Create a collision grid with a wall blocking path."""
    grid = [[False for _ in range(100)] for _ in range(100)]
    # Create a horizontal wall at y=55 from x=45 to x=60
    for x in range(45, 61):
        grid[55][x] = True
    return grid


@pytest.fixture
def empty_blocked_positions():
    """Return empty set of blocked positions."""
    return set()


@pytest.fixture
def players_on_map():
    """Create a list of players for testing."""
    return [
        {"player_id": 100, "username": "player1", "x": 55, "y": 50},
        {"player_id": 101, "username": "player2", "x": 100, "y": 100},
    ]


@pytest.fixture(autouse=True)
def reset_ai_timers():
    """Reset AIService timers before and after each test."""
    AIService.reset_all_timers()
    yield
    AIService.reset_all_timers()


# =============================================================================
# Timer Management Tests
# =============================================================================

class TestTimerManagement:
    """Tests for AIService timer management."""

    def test_cleanup_entity_timers(self):
        """Test that cleanup_entity_timers removes timer state."""
        AIService._entity_timers[123] = {"idle_timer": 50}
        AIService._entity_timers[456] = {"idle_timer": 30}
        
        AIService.cleanup_entity_timers(123)
        
        assert 123 not in AIService._entity_timers
        assert 456 in AIService._entity_timers

    def test_cleanup_nonexistent_entity(self):
        """Test that cleanup of nonexistent entity doesn't raise."""
        AIService.cleanup_entity_timers(99999)  # Should not raise

    def test_reset_all_timers(self):
        """Test that reset_all_timers clears all state."""
        AIService._entity_timers[1] = {"idle_timer": 10}
        AIService._entity_timers[2] = {"idle_timer": 20}
        AIService._entity_timers[3] = {"idle_timer": 30}
        
        AIService.reset_all_timers()
        
        assert len(AIService._entity_timers) == 0


# =============================================================================
# Aggro Detection Tests
# =============================================================================

class TestAggroDetection:
    """Tests for AIService._check_aggro()."""

    @pytest.mark.asyncio
    async def test_aggro_detects_nearby_player(
        self, basic_entity, mock_entity_def, players_on_map, simple_collision_grid
    ):
        """Test that aggro is triggered for a nearby player within range and LOS."""
        # player1 is at (55, 50), entity at (50, 50) - distance 5, within aggro radius 10
        result = await AIService._check_aggro(
            entity=basic_entity,
            entity_def=mock_entity_def,
            players_on_map=players_on_map,
            collision_grid=simple_collision_grid,
        )
        
        assert result is not None
        assert result["player_id"] == 100  # player1 is closer

    @pytest.mark.asyncio
    async def test_aggro_ignores_distant_player(
        self, basic_entity, mock_entity_def, simple_collision_grid
    ):
        """Test that distant players don't trigger aggro."""
        distant_players = [
            {"player_id": 100, "username": "player1", "x": 100, "y": 100},  # Distance 71
        ]
        
        result = await AIService._check_aggro(
            entity=basic_entity,
            entity_def=mock_entity_def,
            players_on_map=distant_players,
            collision_grid=simple_collision_grid,
        )
        
        assert result is None

    @pytest.mark.asyncio
    async def test_aggro_requires_los(
        self, basic_entity, mock_entity_def, collision_grid_with_wall
    ):
        """Test that aggro requires line of sight."""
        # Player at (55, 60), entity at (50, 50), wall at y=55 blocks LOS
        players_behind_wall = [
            {"player_id": 100, "username": "player1", "x": 55, "y": 60},
        ]
        basic_entity["aggro_radius"] = 15  # Large enough to include player
        
        result = await AIService._check_aggro(
            entity=basic_entity,
            entity_def=mock_entity_def,
            players_on_map=players_behind_wall,
            collision_grid=collision_grid_with_wall,
        )
        
        assert result is None

    @pytest.mark.asyncio
    async def test_aggro_selects_closest_player(
        self, basic_entity, mock_entity_def, simple_collision_grid
    ):
        """Test that aggro selects the closest valid target."""
        multiple_players = [
            {"player_id": 101, "username": "far", "x": 58, "y": 50},    # Distance 8
            {"player_id": 100, "username": "close", "x": 52, "y": 50}, # Distance 2
            {"player_id": 102, "username": "medium", "x": 55, "y": 50}, # Distance 5
        ]
        
        result = await AIService._check_aggro(
            entity=basic_entity,
            entity_def=mock_entity_def,
            players_on_map=multiple_players,
            collision_grid=simple_collision_grid,
        )
        
        assert result is not None
        assert result["player_id"] == 100  # Closest player

    @pytest.mark.asyncio
    async def test_aggro_zero_radius(
        self, basic_entity, mock_entity_def, players_on_map, simple_collision_grid
    ):
        """Test that zero aggro radius never triggers aggro."""
        basic_entity["aggro_radius"] = 0
        mock_entity_def.aggro_radius = 0
        
        result = await AIService._check_aggro(
            entity=basic_entity,
            entity_def=mock_entity_def,
            players_on_map=players_on_map,
            collision_grid=simple_collision_grid,
        )
        
        assert result is None

    @pytest.mark.asyncio
    async def test_aggro_empty_player_list(
        self, basic_entity, mock_entity_def, simple_collision_grid
    ):
        """Test aggro with no players on map."""
        result = await AIService._check_aggro(
            entity=basic_entity,
            entity_def=mock_entity_def,
            players_on_map=[],
            collision_grid=simple_collision_grid,
        )
        
        assert result is None


# =============================================================================
# Idle State Tests
# =============================================================================

class TestIdleState:
    """Tests for AIService._handle_idle_state()."""

    @pytest.mark.asyncio
    async def test_idle_timer_decrements(self, mock_gsm, basic_entity, mock_entity_def):
        """Test that idle timer decrements each call."""
        timers = {"idle_timer": 50, "wander_target": None, "last_move_tick": 0}
        
        await AIService._handle_idle_state(
            gsm=mock_gsm,
            entity=basic_entity,
            entity_def=mock_entity_def,
            timers=timers,
            current_tick=100,
        )
        
        assert timers["idle_timer"] == 49
        mock_gsm.set_entity_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_idle_transitions_to_wander(self, mock_gsm, basic_entity, mock_entity_def):
        """Test that idle transitions to wander when timer expires."""
        timers = {"idle_timer": 1, "wander_target": None, "last_move_tick": 0}
        
        await AIService._handle_idle_state(
            gsm=mock_gsm,
            entity=basic_entity,
            entity_def=mock_entity_def,
            timers=timers,
            current_tick=100,
        )
        
        mock_gsm.set_entity_state.assert_called_once_with(1, EntityState.WANDER)
        assert timers["wander_target"] is not None
        assert timers["last_move_tick"] == 100

    @pytest.mark.asyncio
    async def test_idle_no_wander_radius_stays_idle(
        self, mock_gsm, basic_entity, mock_entity_def
    ):
        """Test that entity with no wander radius stays idle forever."""
        basic_entity["wander_radius"] = 0
        timers = {"idle_timer": 1, "wander_target": None, "last_move_tick": 0}
        
        await AIService._handle_idle_state(
            gsm=mock_gsm,
            entity=basic_entity,
            entity_def=mock_entity_def,
            timers=timers,
            current_tick=100,
        )
        
        mock_gsm.set_entity_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_idle_wander_target_within_radius(
        self, mock_gsm, basic_entity, mock_entity_def
    ):
        """Test that wander target is within wander radius of spawn."""
        basic_entity["wander_radius"] = 5
        basic_entity["spawn_x"] = 50
        basic_entity["spawn_y"] = 50
        timers = {"idle_timer": 1, "wander_target": None, "last_move_tick": 0}
        
        await AIService._handle_idle_state(
            gsm=mock_gsm,
            entity=basic_entity,
            entity_def=mock_entity_def,
            timers=timers,
            current_tick=100,
        )
        
        target = timers["wander_target"]
        assert target is not None
        # Check target is within wander radius
        dx = abs(target[0] - 50)
        dy = abs(target[1] - 50)
        assert dx <= 5
        assert dy <= 5


# =============================================================================
# Wander State Tests
# =============================================================================

class TestWanderState:
    """Tests for AIService._handle_wander_state()."""

    @pytest.mark.asyncio
    async def test_wander_respects_interval(
        self, mock_gsm, basic_entity, mock_entity_def, simple_collision_grid, empty_blocked_positions
    ):
        """Test that wander respects the move interval."""
        basic_entity["state"] = "wander"
        timers = {
            "idle_timer": 0,
            "wander_target": (55, 50),
            "last_move_tick": 95,  # Recent move
            "last_aggro_check_tick": 0,
            "last_attack_tick": 0,
        }
        
        with patch("server.src.services.ai_service.settings") as mock_settings:
            mock_settings.ENTITY_AI_WANDER_INTERVAL = 40
            mock_settings.ENTITY_AI_MAX_PATHFINDING_DISTANCE = 50
            
            await AIService._handle_wander_state(
                gsm=mock_gsm,
                entity=basic_entity,
                entity_def=mock_entity_def,
                timers=timers,
                collision_grid=simple_collision_grid,
                blocked_positions=empty_blocked_positions,
                current_tick=100,  # Only 5 ticks since last move
            )
        
        mock_gsm.update_entity_position.assert_not_called()

    @pytest.mark.asyncio
    async def test_wander_moves_toward_target(
        self, mock_gsm, basic_entity, mock_entity_def, simple_collision_grid, empty_blocked_positions
    ):
        """Test that entity moves toward wander target."""
        basic_entity["state"] = "wander"
        timers = {
            "idle_timer": 0,
            "wander_target": (55, 50),  # 5 tiles east
            "last_move_tick": 0,
            "last_aggro_check_tick": 0,
            "last_attack_tick": 0,
        }
        
        with patch("server.src.services.ai_service.settings") as mock_settings:
            mock_settings.ENTITY_AI_WANDER_INTERVAL = 40
            mock_settings.ENTITY_AI_MAX_PATHFINDING_DISTANCE = 50
            
            await AIService._handle_wander_state(
                gsm=mock_gsm,
                entity=basic_entity,
                entity_def=mock_entity_def,
                timers=timers,
                collision_grid=simple_collision_grid,
                blocked_positions=empty_blocked_positions,
                current_tick=100,
            )
        
        # Should move one step east toward target
        mock_gsm.update_entity_position.assert_called_once_with(1, 51, 50)
        assert timers["last_move_tick"] == 100

    @pytest.mark.asyncio
    async def test_wander_at_target_returns_to_idle(
        self, mock_gsm, basic_entity, mock_entity_def, simple_collision_grid, empty_blocked_positions
    ):
        """Test that reaching wander target returns to idle."""
        basic_entity["x"] = 55
        basic_entity["y"] = 50
        basic_entity["state"] = "wander"
        timers = {
            "idle_timer": 0,
            "wander_target": (55, 50),  # Already at target
            "last_move_tick": 0,
            "last_aggro_check_tick": 0,
            "last_attack_tick": 0,
        }
        
        with patch("server.src.services.ai_service.settings") as mock_settings:
            mock_settings.ENTITY_AI_WANDER_INTERVAL = 40
            mock_settings.ENTITY_AI_IDLE_MIN = 20
            mock_settings.ENTITY_AI_IDLE_MAX = 100
            
            await AIService._handle_wander_state(
                gsm=mock_gsm,
                entity=basic_entity,
                entity_def=mock_entity_def,
                timers=timers,
                collision_grid=simple_collision_grid,
                blocked_positions=empty_blocked_positions,
                current_tick=100,
            )
        
        mock_gsm.set_entity_state.assert_called_once_with(1, EntityState.IDLE)
        assert timers["wander_target"] is None
        assert 20 <= timers["idle_timer"] <= 100

    @pytest.mark.asyncio
    async def test_wander_no_target_returns_to_idle(
        self, mock_gsm, basic_entity, mock_entity_def, simple_collision_grid, empty_blocked_positions
    ):
        """Test that missing wander target returns to idle."""
        basic_entity["state"] = "wander"
        timers = {
            "idle_timer": 0,
            "wander_target": None,  # No target
            "last_move_tick": 0,
            "last_aggro_check_tick": 0,
            "last_attack_tick": 0,
        }
        
        with patch("server.src.services.ai_service.settings") as mock_settings:
            mock_settings.ENTITY_AI_WANDER_INTERVAL = 40
            mock_settings.ENTITY_AI_IDLE_MIN = 20
            mock_settings.ENTITY_AI_IDLE_MAX = 100
            
            await AIService._handle_wander_state(
                gsm=mock_gsm,
                entity=basic_entity,
                entity_def=mock_entity_def,
                timers=timers,
                collision_grid=simple_collision_grid,
                blocked_positions=empty_blocked_positions,
                current_tick=100,
            )
        
        mock_gsm.set_entity_state.assert_called_once_with(1, EntityState.IDLE)


# =============================================================================
# Combat State Tests
# =============================================================================

class TestCombatState:
    """Tests for AIService._handle_combat_state()."""

    @pytest.mark.asyncio
    async def test_combat_no_target_returns(
        self, mock_gsm, basic_entity, mock_entity_def, players_on_map,
        simple_collision_grid, empty_blocked_positions
    ):
        """Test that combat without target transitions to returning."""
        basic_entity["state"] = "combat"
        basic_entity["target_player_id"] = None  # No target
        timers = {
            "idle_timer": 0,
            "wander_target": None,
            "last_move_tick": 0,
            "last_aggro_check_tick": 0,
            "last_attack_tick": 0,
        }
        
        await AIService._handle_combat_state(
            gsm=mock_gsm,
            entity=basic_entity,
            entity_def=mock_entity_def,
            timers=timers,
            players_on_map=players_on_map,
            collision_grid=simple_collision_grid,
            blocked_positions=empty_blocked_positions,
            current_tick=100,
            map_id="test_map",
        )
        
        mock_gsm.set_entity_state.assert_called_once_with(1, EntityState.RETURNING)

    @pytest.mark.asyncio
    async def test_combat_target_left_map_returns(
        self, mock_gsm, basic_entity, mock_entity_def,
        simple_collision_grid, empty_blocked_positions
    ):
        """Test that target leaving map causes return to spawn."""
        basic_entity["state"] = "combat"
        basic_entity["target_player_id"] = 999  # Not in players list
        timers = {
            "idle_timer": 0,
            "wander_target": None,
            "last_move_tick": 0,
            "last_aggro_check_tick": 0,
            "last_attack_tick": 0,
        }
        
        await AIService._handle_combat_state(
            gsm=mock_gsm,
            entity=basic_entity,
            entity_def=mock_entity_def,
            timers=timers,
            players_on_map=[],  # Player left
            collision_grid=simple_collision_grid,
            blocked_positions=empty_blocked_positions,
            current_tick=100,
            map_id="test_map",
        )
        
        mock_gsm.set_entity_state.assert_called_once_with(1, EntityState.RETURNING)

    @pytest.mark.asyncio
    async def test_combat_disengage_when_target_too_far(
        self, mock_gsm, basic_entity, mock_entity_def,
        simple_collision_grid, empty_blocked_positions
    ):
        """Test that entity disengages when target is beyond disengage radius from spawn."""
        basic_entity["state"] = "combat"
        basic_entity["target_player_id"] = 100
        basic_entity["spawn_x"] = 50
        basic_entity["spawn_y"] = 50
        basic_entity["disengage_radius"] = 15
        mock_entity_def.disengage_radius = 15
        
        # Player is at distance 50 from spawn (too far)
        far_players = [
            {"player_id": 100, "username": "player1", "x": 100, "y": 50},
        ]
        
        timers = {
            "idle_timer": 0,
            "wander_target": None,
            "last_move_tick": 0,
            "last_aggro_check_tick": 0,
            "last_attack_tick": 0,
        }
        
        await AIService._handle_combat_state(
            gsm=mock_gsm,
            entity=basic_entity,
            entity_def=mock_entity_def,
            timers=timers,
            players_on_map=far_players,
            collision_grid=simple_collision_grid,
            blocked_positions=empty_blocked_positions,
            current_tick=100,
            map_id="test_map",
        )
        
        mock_gsm.set_entity_state.assert_called_once_with(1, EntityState.RETURNING)

    @pytest.mark.asyncio
    async def test_combat_chases_target(
        self, mock_gsm, basic_entity, mock_entity_def,
        simple_collision_grid, empty_blocked_positions
    ):
        """Test that entity chases target when not adjacent."""
        basic_entity["state"] = "combat"
        basic_entity["target_player_id"] = 100
        basic_entity["x"] = 50
        basic_entity["y"] = 50
        
        # Player at distance 5
        players = [{"player_id": 100, "username": "player1", "x": 55, "y": 50}]
        
        timers = {
            "idle_timer": 0,
            "wander_target": None,
            "last_move_tick": 0,
            "last_aggro_check_tick": 0,
            "last_attack_tick": 0,
        }
        
        with patch("server.src.services.ai_service.settings") as mock_settings:
            mock_settings.ENTITY_AI_CHASE_INTERVAL = 10
            mock_settings.ENTITY_AI_ATTACK_INTERVAL = 60
            mock_settings.ENTITY_AI_LOS_TIMEOUT = 100
            mock_settings.ENTITY_AI_MAX_PATHFINDING_DISTANCE = 50
            
            await AIService._handle_combat_state(
                gsm=mock_gsm,
                entity=basic_entity,
                entity_def=mock_entity_def,
                timers=timers,
                players_on_map=players,
                collision_grid=simple_collision_grid,
                blocked_positions=empty_blocked_positions,
                current_tick=100,
                map_id="test_map",
            )
        
        # Should move toward player
        mock_gsm.update_entity_position.assert_called_once_with(1, 51, 50)
        assert timers["last_move_tick"] == 100

    @pytest.mark.asyncio
    async def test_combat_attacks_when_adjacent(
        self, mock_gsm, basic_entity, mock_entity_def,
        simple_collision_grid, empty_blocked_positions
    ):
        """Test that entity attacks when adjacent to target."""
        basic_entity["state"] = "combat"
        basic_entity["target_player_id"] = 100
        basic_entity["x"] = 54
        basic_entity["y"] = 50
        
        # Player adjacent (distance 1)
        players = [{"player_id": 100, "username": "player1", "x": 55, "y": 50}]
        
        timers = {
            "idle_timer": 0,
            "wander_target": None,
            "last_move_tick": 0,
            "last_aggro_check_tick": 0,
            "last_attack_tick": 0,  # Ready to attack
        }
        
        mock_attack_result = MagicMock()
        mock_attack_result.success = True
        mock_attack_result.damage = 5
        mock_attack_result.hit = True
        mock_attack_result.defender_hp = 95
        mock_attack_result.defender_died = False
        mock_attack_result.message = "Test hit"
        
        with patch("server.src.services.ai_service.settings") as mock_settings:
            mock_settings.ENTITY_AI_CHASE_INTERVAL = 10
            mock_settings.ENTITY_AI_ATTACK_INTERVAL = 60
            mock_settings.ENTITY_AI_LOS_TIMEOUT = 100
            mock_settings.ENTITY_AI_MAX_PATHFINDING_DISTANCE = 50
            
            with patch("server.src.services.combat_service.CombatService.perform_attack", new_callable=AsyncMock) as mock_attack:
                mock_attack.return_value = mock_attack_result
                
                with patch("server.src.services.ai_service.PlayerService.get_username_by_player_id", new_callable=AsyncMock) as mock_get_username:
                    mock_get_username.return_value = "player1"
                    
                    combat_event = await AIService._handle_combat_state(
                        gsm=mock_gsm,
                        entity=basic_entity,
                        entity_def=mock_entity_def,
                        timers=timers,
                        players_on_map=players,
                        collision_grid=simple_collision_grid,
                        blocked_positions=empty_blocked_positions,
                        current_tick=100,
                        map_id="test_map",
                    )
        
        assert timers["last_attack_tick"] == 100
        # Verify combat event was returned
        assert combat_event is not None
        assert combat_event.attacker_id == 1
        assert combat_event.defender_id == 100
        assert combat_event.defender_name == "player1"
        assert combat_event.damage == 5
        assert combat_event.hit is True

    @pytest.mark.asyncio
    async def test_combat_los_timeout_triggers_return(
        self, mock_gsm, basic_entity, mock_entity_def,
        collision_grid_with_wall, empty_blocked_positions
    ):
        """Test that losing LOS for too long triggers return."""
        basic_entity["state"] = "combat"
        basic_entity["target_player_id"] = 100
        basic_entity["x"] = 50
        basic_entity["y"] = 50
        basic_entity["los_lost_at_tick"] = 1  # Lost LOS at tick 1
        
        # Player behind wall (no LOS)
        players = [{"player_id": 100, "username": "player1", "x": 55, "y": 60}]
        
        timers = {
            "idle_timer": 0,
            "wander_target": None,
            "last_move_tick": 0,
            "last_aggro_check_tick": 0,
            "last_attack_tick": 0,
        }
        
        with patch("server.src.services.ai_service.settings") as mock_settings:
            mock_settings.ENTITY_AI_CHASE_INTERVAL = 10
            mock_settings.ENTITY_AI_ATTACK_INTERVAL = 60
            mock_settings.ENTITY_AI_LOS_TIMEOUT = 100
            mock_settings.ENTITY_AI_MAX_PATHFINDING_DISTANCE = 50
            
            await AIService._handle_combat_state(
                gsm=mock_gsm,
                entity=basic_entity,
                entity_def=mock_entity_def,
                timers=timers,
                players_on_map=players,
                collision_grid=collision_grid_with_wall,
                blocked_positions=empty_blocked_positions,
                current_tick=200,  # Well past LOS timeout
                map_id="test_map",
            )
        
        mock_gsm.set_entity_state.assert_called_with(1, EntityState.RETURNING)


# =============================================================================
# Returning State Tests
# =============================================================================

class TestReturningState:
    """Tests for AIService._handle_returning_state()."""

    @pytest.mark.asyncio
    async def test_returning_at_spawn_transitions_to_idle(
        self, mock_gsm, basic_entity, mock_entity_def,
        simple_collision_grid, empty_blocked_positions
    ):
        """Test that reaching spawn heals and transitions to idle."""
        basic_entity["state"] = "returning"
        basic_entity["x"] = 50
        basic_entity["y"] = 50
        basic_entity["spawn_x"] = 50
        basic_entity["spawn_y"] = 50
        basic_entity["current_hp"] = 50
        basic_entity["max_hp"] = 100
        
        timers = {
            "idle_timer": 0,
            "wander_target": None,
            "last_move_tick": 0,
            "last_aggro_check_tick": 0,
            "last_attack_tick": 0,
        }
        
        with patch("server.src.services.ai_service.settings") as mock_settings:
            mock_settings.ENTITY_AI_WANDER_INTERVAL = 40
            mock_settings.ENTITY_AI_IDLE_MIN = 20
            mock_settings.ENTITY_AI_IDLE_MAX = 100
            
            await AIService._handle_returning_state(
                gsm=mock_gsm,
                entity=basic_entity,
                entity_def=mock_entity_def,
                timers=timers,
                collision_grid=simple_collision_grid,
                blocked_positions=empty_blocked_positions,
                current_tick=100,
            )
        
        mock_gsm.update_entity_hp.assert_called_once_with(1, 100)
        mock_gsm.set_entity_state.assert_called_once_with(1, EntityState.IDLE)

    @pytest.mark.asyncio
    async def test_returning_moves_toward_spawn(
        self, mock_gsm, basic_entity, mock_entity_def,
        simple_collision_grid, empty_blocked_positions
    ):
        """Test that entity moves toward spawn while returning."""
        basic_entity["state"] = "returning"
        basic_entity["x"] = 55
        basic_entity["y"] = 50
        basic_entity["spawn_x"] = 50
        basic_entity["spawn_y"] = 50
        
        timers = {
            "idle_timer": 0,
            "wander_target": None,
            "last_move_tick": 0,
            "last_aggro_check_tick": 0,
            "last_attack_tick": 0,
        }
        
        with patch("server.src.services.ai_service.settings") as mock_settings:
            mock_settings.ENTITY_AI_WANDER_INTERVAL = 40
            mock_settings.ENTITY_AI_MAX_PATHFINDING_DISTANCE = 50
            
            await AIService._handle_returning_state(
                gsm=mock_gsm,
                entity=basic_entity,
                entity_def=mock_entity_def,
                timers=timers,
                collision_grid=simple_collision_grid,
                blocked_positions=empty_blocked_positions,
                current_tick=100,
            )
        
        mock_gsm.update_entity_position.assert_called_once_with(1, 54, 50)

    @pytest.mark.asyncio
    async def test_returning_teleports_if_blocked(
        self, mock_gsm, basic_entity, mock_entity_def,
        empty_blocked_positions
    ):
        """Test that entity teleports to spawn if path is completely blocked."""
        basic_entity["state"] = "returning"
        basic_entity["x"] = 55
        basic_entity["y"] = 50
        basic_entity["spawn_x"] = 50
        basic_entity["spawn_y"] = 50
        basic_entity["max_hp"] = 100
        
        # Create a collision grid that blocks all paths
        blocked_grid = [[True for _ in range(100)] for _ in range(100)]
        blocked_grid[50][55] = False  # Only current position is walkable
        
        timers = {
            "idle_timer": 0,
            "wander_target": None,
            "last_move_tick": 0,
            "last_aggro_check_tick": 0,
            "last_attack_tick": 0,
        }
        
        with patch("server.src.services.ai_service.settings") as mock_settings:
            mock_settings.ENTITY_AI_WANDER_INTERVAL = 40
            mock_settings.ENTITY_AI_MAX_PATHFINDING_DISTANCE = 50
            mock_settings.ENTITY_AI_IDLE_MIN = 20
            mock_settings.ENTITY_AI_IDLE_MAX = 100
            
            await AIService._handle_returning_state(
                gsm=mock_gsm,
                entity=basic_entity,
                entity_def=mock_entity_def,
                timers=timers,
                collision_grid=blocked_grid,
                blocked_positions=empty_blocked_positions,
                current_tick=100,
            )
        
        # Should teleport to spawn
        mock_gsm.update_entity_position.assert_called_once_with(1, 50, 50)
        mock_gsm.update_entity_hp.assert_called_once_with(1, 100)


# =============================================================================
# Process Entities Integration Tests
# =============================================================================

class TestProcessEntities:
    """Tests for AIService.process_entities() - main entry point."""

    @pytest.mark.asyncio
    async def test_process_entities_disabled(self, mock_gsm):
        """Test that processing is skipped when AI is disabled."""
        with patch("server.src.services.ai_service.settings") as mock_settings:
            mock_settings.ENTITY_AI_ENABLED = False
            
            await AIService.process_entities(
                gsm=mock_gsm,
                map_id="test_map",
                current_tick=100,
            )
        
        mock_gsm.get_map_entities.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_entities_no_entities(self, mock_gsm):
        """Test processing when no entities on map."""
        mock_gsm.get_map_entities.return_value = []
        
        with patch("server.src.services.ai_service.settings") as mock_settings:
            mock_settings.ENTITY_AI_ENABLED = True
            
            await AIService.process_entities(
                gsm=mock_gsm,
                map_id="test_map",
                current_tick=100,
            )
        
        mock_gsm.get_map_entities.assert_called_once_with("test_map")

    @pytest.mark.asyncio
    async def test_process_entities_skips_dead(self, mock_gsm, simple_collision_grid):
        """Test that dead entities are skipped."""
        dead_entity = {
            "id": 1,
            "entity_name": "GOBLIN",
            "x": 50,
            "y": 50,
            "state": "dead",  # Dead entity
        }
        mock_gsm.get_map_entities.return_value = [dead_entity]
        
        with patch("server.src.services.ai_service.settings") as mock_settings:
            mock_settings.ENTITY_AI_ENABLED = True
            
            with patch("server.src.services.ai_service.get_map_manager") as mock_map_mgr:
                mock_tile_map = MagicMock()
                mock_tile_map.get_collision_grid.return_value = simple_collision_grid
                mock_map_mgr.return_value.get_map.return_value = mock_tile_map
                
                with patch("server.src.services.ai_service.EntitySpawnService.get_entity_positions", new_callable=AsyncMock) as mock_positions:
                    mock_positions.return_value = {}
                    
                    with patch("server.src.services.ai_service.PlayerService.get_players_on_map", new_callable=AsyncMock) as mock_players:
                        mock_players.return_value = []
                        
                        await AIService.process_entities(
                            gsm=mock_gsm,
                            map_id="test_map",
                            current_tick=100,
                        )
        
        # Should not have processed the dead entity (no state changes)
        mock_gsm.set_entity_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_entities_skips_merchant(self, mock_gsm, simple_collision_grid):
        """Test that merchant NPCs are skipped."""
        # This tests that MERCHANT behavior entities don't get AI processing
        merchant_entity = {
            "id": 1,
            "entity_name": "VILLAGE_MERCHANT",  # Assuming this is a merchant
            "x": 50,
            "y": 50,
            "state": "idle",
        }
        mock_gsm.get_map_entities.return_value = [merchant_entity]
        
        with patch("server.src.services.ai_service.settings") as mock_settings:
            mock_settings.ENTITY_AI_ENABLED = True
            
            with patch("server.src.services.ai_service.get_map_manager") as mock_map_mgr:
                mock_tile_map = MagicMock()
                mock_tile_map.get_collision_grid.return_value = simple_collision_grid
                mock_map_mgr.return_value.get_map.return_value = mock_tile_map
                
                with patch("server.src.services.ai_service.EntitySpawnService.get_entity_positions", new_callable=AsyncMock) as mock_positions:
                    mock_positions.return_value = {}
                    
                    with patch("server.src.services.ai_service.PlayerService.get_players_on_map", new_callable=AsyncMock) as mock_players:
                        mock_players.return_value = []
                        
                        with patch("server.src.services.ai_service.get_entity_by_name") as mock_get_entity:
                            # Mock as merchant
                            mock_enum = MagicMock()
                            mock_def = MagicMock()
                            mock_def.behavior = EntityBehavior.MERCHANT
                            mock_enum.value = mock_def
                            mock_get_entity.return_value = mock_enum
                            
                            await AIService.process_entities(
                                gsm=mock_gsm,
                                map_id="test_map",
                                current_tick=100,
                            )
        
        # Should not have processed the merchant (no movement or state changes)
        mock_gsm.update_entity_position.assert_not_called()


# =============================================================================
# State Transition Helper Tests  
# =============================================================================

class TestStateTransitions:
    """Tests for state transition helper methods."""

    @pytest.mark.asyncio
    async def test_transition_to_idle(self, mock_gsm):
        """Test _transition_to_idle sets state and resets timers."""
        timers = {
            "idle_timer": 0,
            "wander_target": (10, 20),
        }
        
        with patch("server.src.services.ai_service.settings") as mock_settings:
            mock_settings.ENTITY_AI_IDLE_MIN = 20
            mock_settings.ENTITY_AI_IDLE_MAX = 100
            
            await AIService._transition_to_idle(
                gsm=mock_gsm,
                instance_id=1,
                timers=timers,
            )
        
        mock_gsm.set_entity_state.assert_called_once_with(1, EntityState.IDLE)
        assert timers["wander_target"] is None
        assert 20 <= timers["idle_timer"] <= 100

    @pytest.mark.asyncio
    async def test_transition_to_returning(self, mock_gsm):
        """Test _transition_to_returning sets state and clears target."""
        timers = {
            "idle_timer": 50,
            "wander_target": (10, 20),
        }
        
        await AIService._transition_to_returning(
            gsm=mock_gsm,
            instance_id=1,
            timers=timers,
        )
        
        mock_gsm.set_entity_state.assert_called_once_with(1, EntityState.RETURNING)
        assert timers["wander_target"] is None


# =============================================================================
# Clear Entities Targeting Player Tests
# =============================================================================

class TestClearEntitiesTargetingPlayer:
    """Tests for AIService.clear_entities_targeting_player()."""

    @pytest.mark.asyncio
    async def test_clear_entities_targeting_player(self, mock_gsm):
        """Test that entities targeting a dead player are transitioned to RETURNING."""
        # Two entities targeting player 100, one targeting player 101
        entities = [
            {"id": 1, "entity_name": "GOBLIN", "target_player_id": 100},
            {"id": 2, "entity_name": "GOBLIN", "target_player_id": 100},
            {"id": 3, "entity_name": "GOBLIN", "target_player_id": 101},
        ]
        mock_gsm.get_map_entities.return_value = entities
        
        # Setup timer state for entities
        AIService._entity_timers[1] = {"wander_target": (10, 20)}
        AIService._entity_timers[2] = {"wander_target": (30, 40)}
        AIService._entity_timers[3] = {"wander_target": (50, 60)}
        
        result = await AIService.clear_entities_targeting_player(
            gsm=mock_gsm,
            map_id="test_map",
            player_id=100,
        )
        
        # Should have cleared 2 entities
        assert result == 2
        
        # Verify set_entity_state was called for entities 1 and 2
        calls = mock_gsm.set_entity_state.call_args_list
        assert len(calls) == 2
        
        # Check that both entities targeting player 100 got RETURNING state
        called_instance_ids = [call.kwargs.get("instance_id") for call in calls]
        assert 1 in called_instance_ids
        assert 2 in called_instance_ids
        
        # Entity 3 should not have been affected
        assert 3 not in called_instance_ids
        
        # Check timer wander_target was cleared for entities 1 and 2
        assert AIService._entity_timers[1]["wander_target"] is None
        assert AIService._entity_timers[2]["wander_target"] is None
        # Entity 3 timer should be unchanged
        assert AIService._entity_timers[3]["wander_target"] == (50, 60)

    @pytest.mark.asyncio
    async def test_clear_entities_no_entities_targeting(self, mock_gsm):
        """Test when no entities are targeting the player."""
        entities = [
            {"id": 1, "entity_name": "GOBLIN", "target_player_id": 101},
            {"id": 2, "entity_name": "GOBLIN", "target_player_id": None},
        ]
        mock_gsm.get_map_entities.return_value = entities
        
        result = await AIService.clear_entities_targeting_player(
            gsm=mock_gsm,
            map_id="test_map",
            player_id=100,  # No entities targeting this player
        )
        
        assert result == 0
        mock_gsm.set_entity_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_clear_entities_empty_map(self, mock_gsm):
        """Test when there are no entities on the map."""
        mock_gsm.get_map_entities.return_value = []
        
        result = await AIService.clear_entities_targeting_player(
            gsm=mock_gsm,
            map_id="test_map",
            player_id=100,
        )
        
        assert result == 0
        mock_gsm.set_entity_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_clear_entities_handles_missing_timer_state(self, mock_gsm):
        """Test that clearing entities works even if timer state doesn't exist."""
        entities = [
            {"id": 999, "entity_name": "GOBLIN", "target_player_id": 100},
        ]
        mock_gsm.get_map_entities.return_value = entities
        
        # Entity 999 has no timer state
        assert 999 not in AIService._entity_timers
        
        result = await AIService.clear_entities_targeting_player(
            gsm=mock_gsm,
            map_id="test_map",
            player_id=100,
        )
        
        # Should still clear the target (just won't clear timer state)
        assert result == 1
        mock_gsm.set_entity_state.assert_called_once()
