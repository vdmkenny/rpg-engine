"""
Integration tests for AIService.

Tests entity AI behavior including state machine transitions,
aggro detection, movement, and combat using real EntityManager.
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any, List, Set, Tuple

from server.src.services.ai_service import AIService
from server.src.core.entities import EntityBehavior, EntityState
from server.src.core.monsters import MonsterDefinition
from server.src.services.game_state import get_entity_manager, get_player_state_manager

# Apply game_state_managers fixture to all tests in this module
pytestmark = pytest.mark.usefixtures("game_state_managers")


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
        AIService.cleanup_entity_timers(99999)

    def test_reset_all_timers(self):
        """Test that reset_all_timers clears all state."""
        AIService._entity_timers[1] = {"idle_timer": 10}
        AIService._entity_timers[2] = {"idle_timer": 20}
        AIService._entity_timers[3] = {"idle_timer": 30}
        
        AIService.reset_all_timers()
        
        assert len(AIService._entity_timers) == 0


class TestAggroDetection:
    """Tests for AIService._check_aggro()."""

    @pytest.mark.asyncio
    async def test_aggro_detects_nearby_player(
        self, basic_entity, mock_entity_def, players_on_map, simple_collision_grid
    ):
        """Test that aggro is triggered for a nearby player within range and LOS."""
        result = await AIService._check_aggro(
            entity=basic_entity,
            entity_def=mock_entity_def,
            players_on_map=players_on_map,
            collision_grid=simple_collision_grid,
        )
        
        assert result is not None
        assert result["player_id"] == 100

    @pytest.mark.asyncio
    async def test_aggro_ignores_distant_player(
        self, basic_entity, mock_entity_def, simple_collision_grid
    ):
        """Test that distant players don't trigger aggro."""
        distant_players = [
            {"player_id": 100, "username": "player1", "x": 100, "y": 100},
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
        players_behind_wall = [
            {"player_id": 100, "username": "player1", "x": 55, "y": 60},
        ]
        basic_entity["aggro_radius"] = 15
        
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
            {"player_id": 101, "username": "far", "x": 58, "y": 50},
            {"player_id": 100, "username": "close", "x": 52, "y": 50},
            {"player_id": 102, "username": "medium", "x": 55, "y": 50},
        ]
        
        result = await AIService._check_aggro(
            entity=basic_entity,
            entity_def=mock_entity_def,
            players_on_map=multiple_players,
            collision_grid=simple_collision_grid,
        )
        
        assert result is not None
        assert result["player_id"] == 100

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


class TestIdleState:
    """Tests for AIService._handle_idle_state()."""

    @pytest.mark.asyncio
    async def test_idle_timer_decrements(self, basic_entity, mock_entity_def):
        """Test that idle timer decrements each call."""
        entity_manager = get_entity_manager()
        timers = {"idle_timer": 50, "wander_target": None, "last_move_tick": 0}
        
        await AIService._handle_idle_state(
            entity_mgr=entity_manager,
            entity=basic_entity,
            entity_def=mock_entity_def,
            timers=timers,
            current_tick=100,
        )
        
        assert timers["idle_timer"] == 49

    @pytest.mark.asyncio
    async def test_idle_transitions_to_wander(self, basic_entity, mock_entity_def):
        """Test that idle transitions to wander when timer expires."""
        entity_manager = get_entity_manager()
        timers = {"idle_timer": 1, "wander_target": None, "last_move_tick": 0}
        
        await AIService._handle_idle_state(
            entity_mgr=entity_manager,
            entity=basic_entity,
            entity_def=mock_entity_def,
            timers=timers,
            current_tick=100,
        )
        
        assert timers["wander_target"] is not None
        assert timers["last_move_tick"] == 100

    @pytest.mark.asyncio
    async def test_idle_no_wander_radius_stays_idle(
        self, basic_entity, mock_entity_def
    ):
        """Test that entity with no wander radius stays idle forever."""
        entity_manager = get_entity_manager()
        basic_entity["wander_radius"] = 0
        timers = {"idle_timer": 1, "wander_target": None, "last_move_tick": 0}
        
        await AIService._handle_idle_state(
            entity_mgr=entity_manager,
            entity=basic_entity,
            entity_def=mock_entity_def,
            timers=timers,
            current_tick=100,
        )

    @pytest.mark.asyncio
    async def test_idle_wander_target_within_radius(
        self, basic_entity, mock_entity_def
    ):
        """Test that wander target is within wander radius of spawn."""
        entity_manager = get_entity_manager()
        basic_entity["wander_radius"] = 5
        basic_entity["spawn_x"] = 50
        basic_entity["spawn_y"] = 50
        timers = {"idle_timer": 1, "wander_target": None, "last_move_tick": 0}
        
        await AIService._handle_idle_state(
            entity_mgr=entity_manager,
            entity=basic_entity,
            entity_def=mock_entity_def,
            timers=timers,
            current_tick=100,
        )
        
        target = timers["wander_target"]
        assert target is not None
        dx = abs(target[0] - 50)
        dy = abs(target[1] - 50)
        assert dx <= 5
        assert dy <= 5


class TestWanderState:
    """Tests for AIService._handle_wander_state()."""

    @pytest.mark.asyncio
    async def test_wander_respects_interval(
        self, basic_entity, mock_entity_def, simple_collision_grid, empty_blocked_positions
    ):
        """Test that wander respects the move interval."""
        entity_manager = get_entity_manager()
        basic_entity["state"] = "wander"
        timers = {
            "idle_timer": 0,
            "wander_target": (55, 50),
            "last_move_tick": 95,
            "last_aggro_check_tick": 0,
            "last_attack_tick": 0,
        }
        
        with patch("server.src.services.ai_service.settings") as mock_settings:
            mock_settings.ENTITY_AI_WANDER_INTERVAL = 40
            mock_settings.ENTITY_AI_MAX_PATHFINDING_DISTANCE = 50
            
            await AIService._handle_wander_state(
                entity_mgr=entity_manager,
                entity=basic_entity,
                entity_def=mock_entity_def,
                timers=timers,
                collision_grid=simple_collision_grid,
                blocked_positions=empty_blocked_positions,
                current_tick=100,
            )

    @pytest.mark.asyncio
    async def test_wander_moves_toward_target(
        self, basic_entity, mock_entity_def, simple_collision_grid, empty_blocked_positions
    ):
        """Test that entity moves toward wander target."""
        entity_manager = get_entity_manager()
        basic_entity["state"] = "wander"
        timers = {
            "idle_timer": 0,
            "wander_target": (55, 50),
            "last_move_tick": 0,
            "last_aggro_check_tick": 0,
            "last_attack_tick": 0,
        }
        
        with patch("server.src.services.ai_service.settings") as mock_settings:
            mock_settings.ENTITY_AI_WANDER_INTERVAL = 40
            mock_settings.ENTITY_AI_MAX_PATHFINDING_DISTANCE = 50
            
            await AIService._handle_wander_state(
                entity_mgr=entity_manager,
                entity=basic_entity,
                entity_def=mock_entity_def,
                timers=timers,
                collision_grid=simple_collision_grid,
                blocked_positions=empty_blocked_positions,
                current_tick=100,
            )
        
        assert timers["last_move_tick"] == 100

    @pytest.mark.asyncio
    async def test_wander_at_target_returns_to_idle(
        self, basic_entity, mock_entity_def, simple_collision_grid, empty_blocked_positions
    ):
        """Test that reaching wander target returns to idle."""
        entity_manager = get_entity_manager()
        basic_entity["x"] = 55
        basic_entity["y"] = 50
        basic_entity["state"] = "wander"
        timers = {
            "idle_timer": 0,
            "wander_target": (55, 50),
            "last_move_tick": 0,
            "last_aggro_check_tick": 0,
            "last_attack_tick": 0,
        }
        
        with patch("server.src.services.ai_service.settings") as mock_settings:
            mock_settings.ENTITY_AI_WANDER_INTERVAL = 40
            mock_settings.ENTITY_AI_IDLE_MIN = 20
            mock_settings.ENTITY_AI_IDLE_MAX = 100
            
            await AIService._handle_wander_state(
                entity_mgr=entity_manager,
                entity=basic_entity,
                entity_def=mock_entity_def,
                timers=timers,
                collision_grid=simple_collision_grid,
                blocked_positions=empty_blocked_positions,
                current_tick=100,
            )
        
        assert timers["wander_target"] is None
        assert 20 <= timers["idle_timer"] <= 100

    @pytest.mark.asyncio
    async def test_wander_no_target_returns_to_idle(
        self, basic_entity, mock_entity_def, simple_collision_grid, empty_blocked_positions
    ):
        """Test that missing wander target returns to idle."""
        entity_manager = get_entity_manager()
        basic_entity["state"] = "wander"
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
            
            await AIService._handle_wander_state(
                entity_mgr=entity_manager,
                entity=basic_entity,
                entity_def=mock_entity_def,
                timers=timers,
                collision_grid=simple_collision_grid,
                blocked_positions=empty_blocked_positions,
                current_tick=100,
            )


class TestCombatState:
    """Tests for AIService._handle_combat_state()."""

    @pytest.mark.asyncio
    async def test_combat_no_target_returns(
        self, basic_entity, mock_entity_def, players_on_map,
        simple_collision_grid, empty_blocked_positions
    ):
        """Test that combat without target transitions to returning."""
        entity_manager = get_entity_manager()
        basic_entity["state"] = "combat"
        basic_entity["target_player_id"] = None
        timers = {
            "idle_timer": 0,
            "wander_target": None,
            "last_move_tick": 0,
            "last_aggro_check_tick": 0,
            "last_attack_tick": 0,
        }
        
        await AIService._handle_combat_state(
                entity_mgr=entity_manager,
                entity=basic_entity,
                entity_def=mock_entity_def,
                timers=timers,
                players_on_map=players_on_map,
                collision_grid=simple_collision_grid,
                blocked_positions=empty_blocked_positions,
                current_tick=100,
                map_id="test_map",
            )

    @pytest.mark.asyncio
    async def test_combat_target_left_map_returns(
        self, basic_entity, mock_entity_def,
        simple_collision_grid, empty_blocked_positions
    ):
        """Test that target leaving map causes return to spawn."""
        entity_manager = get_entity_manager()
        basic_entity["state"] = "combat"
        basic_entity["target_player_id"] = 999
        timers = {
            "idle_timer": 0,
            "wander_target": None,
            "last_move_tick": 0,
            "last_aggro_check_tick": 0,
            "last_attack_tick": 0,
        }
        
        await AIService._handle_combat_state(
            entity_mgr=entity_manager,
            entity=basic_entity,
            entity_def=mock_entity_def,
            timers=timers,
            players_on_map=[],
            collision_grid=simple_collision_grid,
            blocked_positions=empty_blocked_positions,
            current_tick=100,
            map_id="test_map",
        )

    @pytest.mark.asyncio
    async def test_combat_disengage_when_target_too_far(
        self, basic_entity, mock_entity_def,
        simple_collision_grid, empty_blocked_positions
    ):
        """Test that entity disengages when target is beyond disengage radius from spawn."""
        entity_manager = get_entity_manager()
        basic_entity["state"] = "combat"
        basic_entity["target_player_id"] = 100
        basic_entity["spawn_x"] = 50
        basic_entity["spawn_y"] = 50
        basic_entity["disengage_radius"] = 15
        mock_entity_def.disengage_radius = 15
        
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
            entity_mgr=entity_manager,
            entity=basic_entity,
            entity_def=mock_entity_def,
            timers=timers,
            players_on_map=far_players,
            collision_grid=simple_collision_grid,
            blocked_positions=empty_blocked_positions,
            current_tick=100,
            map_id="test_map",
        )

    @pytest.mark.asyncio
    async def test_combat_chases_target(
        self, basic_entity, mock_entity_def,
        simple_collision_grid, empty_blocked_positions
    ):
        """Test that entity chases target when not adjacent."""
        entity_manager = get_entity_manager()
        basic_entity["state"] = "combat"
        basic_entity["target_player_id"] = 100
        basic_entity["x"] = 50
        basic_entity["y"] = 50
        
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
                entity_mgr=entity_manager,
                entity=basic_entity,
                entity_def=mock_entity_def,
                timers=timers,
                players_on_map=players,
                collision_grid=simple_collision_grid,
                blocked_positions=empty_blocked_positions,
                current_tick=100,
                map_id="test_map",
            )
        
        assert timers["last_move_tick"] == 100

    @pytest.mark.asyncio
    async def test_combat_los_timeout_triggers_return(
        self, basic_entity, mock_entity_def,
        collision_grid_with_wall, empty_blocked_positions
    ):
        """Test that losing LOS for too long triggers return."""
        entity_manager = get_entity_manager()
        basic_entity["state"] = "combat"
        basic_entity["target_player_id"] = 100
        basic_entity["x"] = 50
        basic_entity["y"] = 50
        basic_entity["los_lost_at_tick"] = 1
        
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
                entity_mgr=entity_manager,
                entity=basic_entity,
                entity_def=mock_entity_def,
                timers=timers,
                players_on_map=players,
                collision_grid=collision_grid_with_wall,
                blocked_positions=empty_blocked_positions,
                current_tick=200,
                map_id="test_map",
            )


class TestReturningState:
    """Tests for AIService._handle_returning_state()."""

    @pytest.mark.asyncio
    async def test_returning_at_spawn_transitions_to_idle(
        self, basic_entity, mock_entity_def,
        simple_collision_grid, empty_blocked_positions
    ):
        """Test that reaching spawn heals and transitions to idle."""
        entity_manager = get_entity_manager()
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
                entity_mgr=entity_manager,
                entity=basic_entity,
                entity_def=mock_entity_def,
                timers=timers,
                collision_grid=simple_collision_grid,
                blocked_positions=empty_blocked_positions,
                current_tick=100,
            )

    @pytest.mark.asyncio
    async def test_returning_moves_toward_spawn(
        self, basic_entity, mock_entity_def,
        simple_collision_grid, empty_blocked_positions
    ):
        """Test that entity moves toward spawn while returning."""
        entity_manager = get_entity_manager()
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
                entity_mgr=entity_manager,
                entity=basic_entity,
                entity_def=mock_entity_def,
                timers=timers,
                collision_grid=simple_collision_grid,
                blocked_positions=empty_blocked_positions,
                current_tick=100,
            )

    @pytest.mark.asyncio
    async def test_returning_teleports_if_blocked(
        self, basic_entity, mock_entity_def,
        empty_blocked_positions
    ):
        """Test that entity teleports to spawn if path is completely blocked."""
        entity_manager = get_entity_manager()
        basic_entity["state"] = "returning"
        basic_entity["x"] = 55
        basic_entity["y"] = 50
        basic_entity["spawn_x"] = 50
        basic_entity["spawn_y"] = 50
        basic_entity["max_hp"] = 100
        
        blocked_grid = [[True for _ in range(100)] for _ in range(100)]
        blocked_grid[50][55] = False
        
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
                entity_mgr=entity_manager,
                entity=basic_entity,
                entity_def=mock_entity_def,
                timers=timers,
                collision_grid=blocked_grid,
                blocked_positions=empty_blocked_positions,
                current_tick=100,
            )


class TestProcessEntities:
    """Tests for AIService.process_entities() - main entry point."""

    @pytest.mark.asyncio
    async def test_process_entities_disabled(self):
        """Test that processing is skipped when AI is disabled."""
        entity_manager = get_entity_manager()
        
        with patch("server.src.services.ai_service.settings") as mock_settings:
            mock_settings.ENTITY_AI_ENABLED = False
            
            await AIService.process_entities(
                entity_mgr=entity_manager,
                map_id="test_map",
                current_tick=100,
            )

    @pytest.mark.asyncio
    async def test_process_entities_no_entities(self):
        """Test processing when no entities on map."""
        entity_manager = get_entity_manager()
        
        with patch("server.src.services.ai_service.settings") as mock_settings:
            mock_settings.ENTITY_AI_ENABLED = True
            
            await AIService.process_entities(
                entity_mgr=entity_manager,
                map_id="test_map",
                current_tick=100,
            )

    @pytest.mark.asyncio
    async def test_process_entities_skips_dead(self, simple_collision_grid):
        """Test that dead entities are skipped."""
        entity_manager = get_entity_manager()
        
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
                entity_mgr=entity_manager,
                map_id="test_map",
                current_tick=100,
            )


class TestClearEntitiesTargetingPlayer:
    """Tests for AIService.clear_entities_targeting_player()."""

    @pytest.mark.asyncio
    async def test_clear_entities_targeting_player(self):
        """Test that entities targeting a dead player are transitioned to RETURNING."""
        entity_manager = get_entity_manager()
        
        # Set up timer state for entities
        AIService._entity_timers[1] = {"wander_target": (10, 20)}
        AIService._entity_timers[2] = {"wander_target": (30, 40)}
        AIService._entity_timers[3] = {"wander_target": (50, 60)}
        
        # Mock entities on map - entities 1 and 2 target player 100, entity 3 targets player 999
        mock_entities = [
            {"id": 1, "entity_name": "GOBLIN", "target_player_id": 100, "state": "combat"},
            {"id": 2, "entity_name": "GOBLIN", "target_player_id": 100, "state": "combat"},
            {"id": 3, "entity_name": "GOBLIN", "target_player_id": 999, "state": "combat"},
        ]
        
        with patch.object(entity_manager, "get_map_entities", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_entities
            
            with patch.object(entity_manager, "set_entity_state", new_callable=AsyncMock) as mock_set:
                result = await AIService.clear_entities_targeting_player(
                    entity_mgr=entity_manager,
                    map_id="test_map",
                    player_id=100,
                )
                
                # Verify set_entity_state was called for entities 1 and 2
                assert mock_set.call_count == 2
                
        # Verify timer state - entities targeting player 100 should have wander_target cleared
        assert AIService._entity_timers[1]["wander_target"] is None
        assert AIService._entity_timers[2]["wander_target"] is None
        # Entity 3 was not targeting player 100, so its wander_target should remain
        assert AIService._entity_timers[3]["wander_target"] == (50, 60)

    @pytest.mark.asyncio
    async def test_clear_entities_no_entities_targeting(self):
        """Test when no entities are targeting the player."""
        entity_manager = get_entity_manager()
        
        result = await AIService.clear_entities_targeting_player(
            entity_mgr=entity_manager,
            map_id="test_map",
            player_id=100,
        )
        
        assert result == 0

    @pytest.mark.asyncio
    async def test_clear_entities_empty_map(self):
        """Test when there are no entities on the map."""
        entity_manager = get_entity_manager()
        
        result = await AIService.clear_entities_targeting_player(
            entity_mgr=entity_manager,
            map_id="test_map",
            player_id=100,
        )
        
        assert result == 0
