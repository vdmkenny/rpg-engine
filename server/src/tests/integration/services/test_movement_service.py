"""
Unit tests for MovementService.

Tests movement validation, cooldown management, position calculations,
collision detection, and movement execution.
"""

import pytest
import pytest_asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

from server.src.services.movement_service import MovementService
from server.src.services.game_state import get_player_state_manager, get_entity_manager
from common.src.protocol import CombatTargetType


class TestIsValidDirection:
    """Tests for MovementService.is_valid_direction()"""

    def test_valid_cardinal_directions(self):
        """Test that cardinal directions are valid."""
        assert MovementService.is_valid_direction("up") is True
        assert MovementService.is_valid_direction("down") is True
        assert MovementService.is_valid_direction("left") is True
        assert MovementService.is_valid_direction("right") is True

    def test_valid_compass_directions(self):
        """Test that compass directions are valid."""
        assert MovementService.is_valid_direction("north") is True
        assert MovementService.is_valid_direction("south") is True
        assert MovementService.is_valid_direction("east") is True
        assert MovementService.is_valid_direction("west") is True

    def test_case_insensitive(self):
        """Test that direction validation is case insensitive."""
        assert MovementService.is_valid_direction("UP") is True
        assert MovementService.is_valid_direction("Down") is True
        assert MovementService.is_valid_direction("LEFT") is True
        assert MovementService.is_valid_direction("NORTH") is True

    def test_invalid_directions(self):
        """Test that invalid directions are rejected."""
        assert MovementService.is_valid_direction("invalid") is False
        assert MovementService.is_valid_direction("diagonal") is False
        assert MovementService.is_valid_direction("northwest") is False
        assert MovementService.is_valid_direction("") is False
        assert MovementService.is_valid_direction("  ") is False
        assert MovementService.is_valid_direction("jump") is False


class TestCalculateNewPosition:
    """Tests for MovementService.calculate_new_position()"""

    def test_move_up(self):
        """Test movement in the up direction."""
        new_x, new_y = MovementService.calculate_new_position(10, 10, "up")
        assert new_x == 10
        assert new_y == 9

    def test_move_down(self):
        """Test movement in the down direction."""
        new_x, new_y = MovementService.calculate_new_position(10, 10, "down")
        assert new_x == 10
        assert new_y == 11

    def test_move_left(self):
        """Test movement in the left direction."""
        new_x, new_y = MovementService.calculate_new_position(10, 10, "left")
        assert new_x == 9
        assert new_y == 10

    def test_move_right(self):
        """Test movement in the right direction."""
        new_x, new_y = MovementService.calculate_new_position(10, 10, "right")
        assert new_x == 11
        assert new_y == 10

    def test_move_north(self):
        """Test movement in the north direction (alias for up)."""
        new_x, new_y = MovementService.calculate_new_position(10, 10, "north")
        assert new_x == 10
        assert new_y == 9

    def test_move_south(self):
        """Test movement in the south direction (alias for down)."""
        new_x, new_y = MovementService.calculate_new_position(10, 10, "south")
        assert new_x == 10
        assert new_y == 11

    def test_move_west(self):
        """Test movement in the west direction (alias for left)."""
        new_x, new_y = MovementService.calculate_new_position(10, 10, "west")
        assert new_x == 9
        assert new_y == 10

    def test_move_east(self):
        """Test movement in the east direction (alias for right)."""
        new_x, new_y = MovementService.calculate_new_position(10, 10, "east")
        assert new_x == 11
        assert new_y == 10

    def test_case_insensitive_directions(self):
        """Test that directions are case insensitive."""
        new_x, new_y = MovementService.calculate_new_position(10, 10, "UP")
        assert new_x == 10
        assert new_y == 9

        new_x, new_y = MovementService.calculate_new_position(10, 10, "Down")
        assert new_x == 10
        assert new_y == 11

    def test_invalid_direction_returns_same_position(self):
        """Test that invalid directions return the original position."""
        new_x, new_y = MovementService.calculate_new_position(10, 10, "invalid")
        assert new_x == 10
        assert new_y == 10

    def test_boundary_clamp_negative_x(self):
        """Test that X coordinate is clamped to 0 when moving left at boundary."""
        new_x, new_y = MovementService.calculate_new_position(0, 10, "left")
        assert new_x == 0
        assert new_y == 10

    def test_boundary_clamp_negative_y(self):
        """Test that Y coordinate is clamped to 0 when moving up at boundary."""
        new_x, new_y = MovementService.calculate_new_position(10, 0, "up")
        assert new_x == 10
        assert new_y == 0

    def test_from_origin(self):
        """Test movement from origin (0, 0)."""
        # Moving up or left from origin should stay at boundary
        new_x, new_y = MovementService.calculate_new_position(0, 0, "up")
        assert new_x == 0
        assert new_y == 0

        new_x, new_y = MovementService.calculate_new_position(0, 0, "left")
        assert new_x == 0
        assert new_y == 0

        # Moving down or right from origin should work
        new_x, new_y = MovementService.calculate_new_position(0, 0, "down")
        assert new_x == 0
        assert new_y == 1

        new_x, new_y = MovementService.calculate_new_position(0, 0, "right")
        assert new_x == 1
        assert new_y == 0


class TestValidateMovementCooldown:
    """Tests for MovementService.validate_movement_cooldown()"""

    @pytest.mark.asyncio
    async def test_can_move_when_not_in_cooldown(self, game_state_managers, create_test_player):
        """Test that player can move when cooldown has expired."""
        player_mgr = get_player_state_manager()
        player = await create_test_player("cooldown_test", "password123")
        
        # Set last movement time to well in the past (beyond cooldown)
        old_time = time.time() - 10  # 10 seconds ago
        # Use the correct key format "player:{player_id}" and field "last_move_time"
        await player_mgr._valkey.hset(
            f"player:{player.id}",
            {"last_move_time": str(old_time)}
        )
        
        result = await MovementService.validate_movement_cooldown(player.id)
        
        assert result["can_move"] is True
        assert result["reason"] is None
        assert result["cooldown_remaining"] == 0

    @pytest.mark.asyncio
    async def test_cannot_move_during_cooldown(self, game_state_managers, create_test_player):
        """Test that player cannot move during cooldown period."""
        player_mgr = get_player_state_manager()
        player = await create_test_player("cooldown_test2", "password123")
        
        # Set last movement time to very recent (within cooldown)
        recent_time = time.time() - 0.1  # 100ms ago (cooldown is 500ms)
        # Use the correct key format "player:{player_id}" and field "last_move_time"
        await player_mgr._valkey.hset(
            f"player:{player.id}",
            {"last_move_time": str(recent_time)}
        )
        
        result = await MovementService.validate_movement_cooldown(player.id)
        
        assert result["can_move"] is False
        assert result["reason"] == "Movement cooldown active"
        assert result["cooldown_remaining"] > 0
        assert result["cooldown_remaining"] < MovementService.MOVEMENT_COOLDOWN

    @pytest.mark.asyncio
    async def test_player_not_online(self, game_state_managers):
        """Test cooldown check for player not online."""
        result = await MovementService.validate_movement_cooldown(99999)  # Non-existent player
        
        assert result["can_move"] is False
        assert result["reason"] == "Player not online"


class TestValidateMovementCollision:
    """Tests for MovementService.validate_movement_collision()"""

    @pytest.mark.asyncio
    async def test_valid_move_no_collision(self, game_state_managers, map_manager_loaded):
        """Test that valid moves are allowed."""
        # Mock map manager to return valid move (coordinates may not be walkable in real map)
        with patch("server.src.services.movement_service.get_map_manager") as mock_get_mm:
            mock_mm = MagicMock()
            mock_mm.is_valid_move.return_value = True
            mock_get_mm.return_value = mock_mm
            
            result = await MovementService.validate_movement_collision(
                "samplemap", 5, 5, 5, 6
            )
            
            assert result["valid"] is True
            assert result["reason"] is None
            assert result["collision_detected"] is False

    @pytest.mark.asyncio
    async def test_collision_with_obstacle(self, game_state_managers, map_manager_loaded):
        """Test that collision with obstacles blocks movement."""
        # Mock the map manager to return invalid move
        with patch("server.src.services.movement_service.get_map_manager") as mock_get_mm:
            mock_mm = MagicMock()
            mock_mm.is_valid_move.return_value = False
            mock_get_mm.return_value = mock_mm
            
            result = await MovementService.validate_movement_collision(
                "samplemap", 5, 5, 5, 6
            )
            
            assert result["valid"] is False
            assert result["reason"] == "Movement blocked by obstacle"
            assert result["collision_detected"] is True


class TestValidatePosition:
    """Tests for MovementService.validate_position()"""

    @pytest.mark.asyncio
    async def test_negative_x_invalid(self, game_state_managers):
        """Test that negative X coordinates are invalid."""
        result = await MovementService.validate_position("samplemap", -1, 5)
        
        assert result["valid"] is False
        assert result["reason"] == "Coordinates cannot be negative"

    @pytest.mark.asyncio
    async def test_negative_y_invalid(self, game_state_managers):
        """Test that negative Y coordinates are invalid."""
        result = await MovementService.validate_position("samplemap", 5, -1)
        
        assert result["valid"] is False
        assert result["reason"] == "Coordinates cannot be negative"

    @pytest.mark.asyncio
    async def test_valid_position(self, game_state_managers, map_manager_loaded):
        """Test that valid positions are accepted."""
        # Mock map manager to return valid position (coordinates may not be walkable in real map)
        with patch("server.src.services.movement_service.get_map_manager") as mock_get_mm:
            mock_mm = MagicMock()
            mock_mm.is_valid_move.return_value = True
            mock_get_mm.return_value = mock_mm
            
            result = await MovementService.validate_position("samplemap", 5, 5)
            
            assert result["valid"] is True
            assert result["reason"] is None

    @pytest.mark.asyncio
    async def test_non_walkable_position(self, game_state_managers):
        """Test that non-walkable positions are rejected."""
        with patch("server.src.services.movement_service.get_map_manager") as mock_get_mm:
            mock_mm = MagicMock()
            mock_mm.is_valid_move.return_value = False
            mock_get_mm.return_value = mock_mm
            
            result = await MovementService.validate_position("samplemap", 100, 100)
            
            assert result["valid"] is False
            assert result["reason"] == "Position is not walkable"


class TestSetPlayerPosition:
    """Tests for MovementService.set_player_position()"""

    @pytest.mark.asyncio
    async def test_set_position_success(self, game_state_managers, create_test_player):
        """Test successful position update."""
        player_mgr = get_player_state_manager()
        player = await create_test_player("pos_test", "password123")
        
        result = await MovementService.set_player_position(
            player.id, 20, 30, "samplemap"
        )
        
        assert result is True
        
        # Verify position was updated
        position = await player_mgr.get_player_position(player.id)
        assert position["x"] == 20
        assert position["y"] == 30
        assert position["map_id"] == "samplemap"

    @pytest.mark.asyncio
    async def test_set_position_preserves_hp(self, game_state_managers, create_test_player):
        """Test that setting position preserves HP values."""
        player_mgr = get_player_state_manager()
        player = await create_test_player("hp_test", "password123", current_hp=50)
        
        # Set initial HP state
        await player_mgr.set_player_full_state(player.id, state={"x": 10, "y": 10, "map_id": "samplemap", "current_hp": 75, "max_hp": 100})
        
        # Update position
        result = await MovementService.set_player_position(
            player.id, 20, 30, "samplemap"
        )
        
        assert result is True
        
        # Verify HP was preserved
        state = await player_mgr.get_player_full_state(player.id)
        assert state["current_hp"] == 75
        assert state["max_hp"] == 100

    @pytest.mark.asyncio
    async def test_set_position_new_player_defaults(self, game_state_managers):
        """Test that new player gets default HP values."""
        player_mgr = get_player_state_manager()
        # Create a player ID that doesn't have state yet
        player_id = 99999
        
        # Register as online player
        await player_mgr.register_online_player(player_id, "test_user_99999")
        
        result = await MovementService.set_player_position(
            player_id, 5, 5, "samplemap", update_movement_time=False
        )
        
        assert result is True
        
        # Verify defaults were applied
        state = await player_mgr.get_player_full_state(player_id)
        assert state["current_hp"] == 100
        assert state["max_hp"] == 100


class TestInitializePlayerPosition:
    """Tests for MovementService.initialize_player_position()"""

    @pytest.mark.asyncio
    async def test_initialize_position(self, game_state_managers, create_test_player):
        """Test player position initialization."""
        player_mgr = get_player_state_manager()
        player = await create_test_player("init_test", "password123")
        
        result = await MovementService.initialize_player_position(
            player.id, 15, 25, "samplemap"
        )
        
        assert result is True
        
        position = await player_mgr.get_player_position(player.id)
        assert position["x"] == 15
        assert position["y"] == 25


class TestExecuteMovement:
    """Tests for MovementService.execute_movement()"""

    @pytest.mark.asyncio
    async def test_successful_movement(self, game_state_managers, create_test_player, map_manager_loaded):
        """Test successful movement execution."""
        player_mgr = get_player_state_manager()
        player = await create_test_player("move_test", "password123")
        
        # Set initial position with old movement time
        old_time = time.time() - 10  # Well past cooldown
        await player_mgr.set_player_full_state(player.id, {"x": 10, "y": 10, "map_id": "samplemap", "current_hp": 100, "max_hp": 100})
        await player_mgr._valkey.hset(
            f"player:{player.id}",
            {"last_move_time": str(old_time)}
        )
        
        result = await MovementService.execute_movement(player.id, "down")
        
        assert result["success"] is True
        assert result["reason"] is None
        assert result["new_position"]["x"] == 10
        assert result["new_position"]["y"] == 11
        assert result["old_position"]["x"] == 10
        assert result["old_position"]["y"] == 10
        assert result["collision"] is False

    @pytest.mark.asyncio
    async def test_movement_invalid_direction(self, game_state_managers, create_test_player):
        """Test movement with invalid direction."""
        player = await create_test_player("invalid_dir_test", "password123")
        
        result = await MovementService.execute_movement(player.id, "diagonal")
        
        assert result["success"] is False
        assert result["reason"] == "invalid_direction"

    @pytest.mark.asyncio
    async def test_movement_rate_limited(self, game_state_managers, create_test_player):
        """Test movement when rate limited."""
        player_mgr = get_player_state_manager()
        player = await create_test_player("rate_limit_test", "password123")
        
        # Set very recent movement time (within cooldown)
        recent_time = time.time() - 0.1  # 100ms ago
        await player_mgr.set_player_full_state(player.id, {"x": 10, "y": 10, "map_id": "samplemap", "current_hp": 100, "max_hp": 100})
        await player_mgr._valkey.hset(
            f"player:{player.id}",
            {"last_move_time": str(recent_time)}
        )
        
        result = await MovementService.execute_movement(player.id, "up")
        
        assert result["success"] is False
        assert result["reason"] == "rate_limited"
        assert result["cooldown_remaining"] > 0

    @pytest.mark.asyncio
    async def test_movement_player_not_online(self, game_state_managers):
        """Test movement for player not online."""
        result = await MovementService.execute_movement(99999, "up")
        
        assert result["success"] is False
        # Cooldown check may fail first for non-existent players, returning rate_limited
        assert result["reason"] in ["player_not_online", "rate_limited"]

    @pytest.mark.asyncio
    async def test_movement_blocked_by_collision(self, game_state_managers, create_test_player):
        """Test movement blocked by collision."""
        player_mgr = get_player_state_manager()
        player = await create_test_player("collision_test", "password123")
        
        # Set up position with old movement time
        old_time = time.time() - 10
        await player_mgr.set_player_full_state(player.id, {"x": 10, "y": 10, "map_id": "samplemap", "current_hp": 100, "max_hp": 100})
        await player_mgr._valkey.hset(
            f"player:{player.id}",
            {"last_move_time": str(old_time)}
        )
        
        # Mock collision detection to block movement
        with patch("server.src.services.movement_service.get_map_manager") as mock_get_mm:
            mock_mm = MagicMock()
            mock_mm.is_valid_move.return_value = False
            mock_get_mm.return_value = mock_mm
            
            result = await MovementService.execute_movement(player.id, "up")
            
            assert result["success"] is False
            assert result["reason"] == "blocked"
            assert result["collision"] is True

    @pytest.mark.asyncio
    async def test_movement_clears_combat_state(self, game_state_managers, create_test_player, map_manager_loaded):
        """Test that movement clears combat state."""
        player_mgr = get_player_state_manager()
        player = await create_test_player("combat_clear_test", "password123")
        
        # Set up player in combat
        old_time = time.time() - 10
        await player_mgr.set_player_full_state(player.id, {"x": 10, "y": 10, "map_id": "samplemap", "current_hp": 100, "max_hp": 100})
        await player_mgr._valkey.hset(
            f"player:{player.id}",
            {"last_move_time": str(old_time)}
        )
        
        # Set combat state with correct signature: player_id and combat_state dict
        await player_mgr.set_player_combat_state(
            player.id,
            {
                "target_type": CombatTargetType.ENTITY,
                "target_id": 999,
                "last_attack_tick": int(time.time()),
                "attack_speed": 1.0
            }
        )
        
        # Verify combat state is set
        combat_state = await player_mgr.get_player_combat_state(player.id)
        assert combat_state is not None
        
        # Execute movement
        result = await MovementService.execute_movement(player.id, "down")
        
        assert result["success"] is True
        
        # Verify combat state was cleared
        combat_state = await player_mgr.get_player_combat_state(player.id)
        assert combat_state is None


class TestTeleportPlayer:
    """Tests for MovementService.teleport_player()"""

    @pytest.mark.asyncio
    async def test_successful_teleport(self, game_state_managers, create_test_player, map_manager_loaded):
        """Test successful player teleport."""
        player = await create_test_player("teleport_test", "password123")
        
        # Mock map manager to return valid position (coordinates may not be walkable in real map)
        with patch("server.src.services.movement_service.get_map_manager") as mock_get_mm:
            mock_mm = MagicMock()
            mock_mm.is_valid_move.return_value = True
            mock_get_mm.return_value = mock_mm
            
            result = await MovementService.teleport_player(
                player.id, 50, 60, "samplemap"
            )
            
            assert result["success"] is True
            assert result["reason"] is None
            assert result["new_position"]["x"] == 50
            assert result["new_position"]["y"] == 60
            assert result["new_position"]["map_id"] == "samplemap"

    @pytest.mark.asyncio
    async def test_teleport_to_invalid_position(self, game_state_managers, create_test_player):
        """Test teleport to invalid position."""
        player = await create_test_player("teleport_invalid_test", "password123")
        
        # Teleport to negative coordinates
        result = await MovementService.teleport_player(
            player.id, -10, 50, "samplemap"
        )
        
        assert result["success"] is False
        assert result["reason"] == "Coordinates cannot be negative"

    @pytest.mark.asyncio
    async def test_teleport_skip_validation(self, game_state_managers, create_test_player):
        """Test teleport with validation disabled."""
        player = await create_test_player("teleport_no_validate", "password123")
        
        # Even invalid positions should work when validation is disabled
        # (negative coords are still clamped by set_player_position)
        result = await MovementService.teleport_player(
            player.id, 999, 888, "samplemap", validate_position=False
        )
        
        assert result["success"] is True
        assert result["new_position"]["x"] == 999
        assert result["new_position"]["y"] == 888

    @pytest.mark.asyncio
    async def test_teleport_to_non_walkable_position(self, game_state_managers, create_test_player):
        """Test teleport to non-walkable position is rejected."""
        player = await create_test_player("teleport_blocked", "password123")
        
        with patch("server.src.services.movement_service.get_map_manager") as mock_get_mm:
            mock_mm = MagicMock()
            mock_mm.is_valid_move.return_value = False
            mock_get_mm.return_value = mock_mm
            
            result = await MovementService.teleport_player(
                player.id, 50, 60, "samplemap"
            )
            
            assert result["success"] is False
            assert result["reason"] == "Position is not walkable"


class TestGetMovementState:
    """Tests for MovementService.get_movement_state()"""

    @pytest.mark.asyncio
    async def test_get_state_can_move(self, game_state_managers, create_test_player):
        """Test getting movement state when player can move."""
        player_mgr = get_player_state_manager()
        player = await create_test_player("state_test", "password123")
        
        # Set old movement time using correct key format
        old_time = time.time() - 10
        await player_mgr.set_player_full_state(player.id, {"x": 10, "y": 10, "map_id": "samplemap", "current_hp": 100, "max_hp": 100})
        await player_mgr._valkey.hset(
            f"player:{player.id}",
            {"last_move_time": str(old_time)}
        )
        
        state = await MovementService.get_movement_state(player.id)
        
        assert state["can_move"] is True
        assert state["cooldown_remaining"] == 0
        assert state["movement_cooldown"] == MovementService.MOVEMENT_COOLDOWN

    @pytest.mark.asyncio
    async def test_get_state_in_cooldown(self, game_state_managers, create_test_player):
        """Test getting movement state during cooldown."""
        player_mgr = get_player_state_manager()
        player = await create_test_player("cooldown_state_test", "password123")
        
        # Set recent movement time using correct key format
        recent_time = time.time() - 0.1
        await player_mgr.set_player_full_state(player.id, {"x": 10, "y": 10, "map_id": "samplemap", "current_hp": 100, "max_hp": 100})
        await player_mgr._valkey.hset(
            f"player:{player.id}",
            {"last_move_time": str(recent_time)}
        )
        
        state = await MovementService.get_movement_state(player.id)
        
        assert state["can_move"] is False
        assert state["cooldown_remaining"] > 0
        assert state["movement_cooldown"] == MovementService.MOVEMENT_COOLDOWN


class TestDirectionOffsets:
    """Tests for DIRECTION_OFFSETS constant."""

    def test_all_directions_have_offsets(self):
        """Verify all expected directions are defined."""
        expected = ["up", "down", "left", "right", "north", "south", "west", "east"]
        for direction in expected:
            assert direction in MovementService.DIRECTION_OFFSETS

    def test_opposite_directions_cancel(self):
        """Verify opposite directions have cancelling offsets."""
        # up/down
        up_offset = MovementService.DIRECTION_OFFSETS["up"]
        down_offset = MovementService.DIRECTION_OFFSETS["down"]
        assert up_offset[0] + down_offset[0] == 0
        assert up_offset[1] + down_offset[1] == 0

        # left/right
        left_offset = MovementService.DIRECTION_OFFSETS["left"]
        right_offset = MovementService.DIRECTION_OFFSETS["right"]
        assert left_offset[0] + right_offset[0] == 0
        assert left_offset[1] + right_offset[1] == 0

    def test_cardinal_compass_equivalence(self):
        """Verify cardinal and compass directions are equivalent."""
        assert MovementService.DIRECTION_OFFSETS["up"] == MovementService.DIRECTION_OFFSETS["north"]
        assert MovementService.DIRECTION_OFFSETS["down"] == MovementService.DIRECTION_OFFSETS["south"]
        assert MovementService.DIRECTION_OFFSETS["left"] == MovementService.DIRECTION_OFFSETS["west"]
        assert MovementService.DIRECTION_OFFSETS["right"] == MovementService.DIRECTION_OFFSETS["east"]


class TestMovementCooldownConstant:
    """Tests for MOVEMENT_COOLDOWN constant."""

    def test_cooldown_is_positive(self):
        """Verify cooldown is a positive value."""
        assert MovementService.MOVEMENT_COOLDOWN > 0

    def test_cooldown_is_reasonable(self):
        """Verify cooldown is within a reasonable range (100ms to 2s)."""
        assert 0.1 <= MovementService.MOVEMENT_COOLDOWN <= 2.0
