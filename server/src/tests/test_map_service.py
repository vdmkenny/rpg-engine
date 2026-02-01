"""
Unit tests for MapService (MapManager and TileMap classes).

Tests map management, collision detection, chunk data retrieval,
spawn point handling, and distance calculations.
"""

import pytest
import pytest_asyncio
from unittest.mock import MagicMock, Mock, patch, AsyncMock
from typing import Dict, List, Optional

from server.src.services.map_service import (
    MapManager,
    TileMap,
    get_map_manager,
    _map_manager_instance,
)
from server.src.services.game_state_manager import GameStateManager


class TestMapManagerSingleton:
    """Tests for MapManager singleton pattern."""

    def test_get_map_manager_returns_same_instance(self):
        """Test that get_map_manager returns the same instance."""
        # Reset the singleton for this test
        import server.src.services.map_service as map_service_module
        
        original = map_service_module._map_manager_instance
        map_service_module._map_manager_instance = None
        
        try:
            manager1 = get_map_manager()
            manager2 = get_map_manager()
            assert manager1 is manager2
        finally:
            # Restore original instance
            map_service_module._map_manager_instance = original

    def test_map_manager_initializes_empty_maps(self):
        """Test that MapManager initializes with empty maps dict."""
        manager = MapManager()
        assert manager.maps == {}


class TestMapManagerGetMap:
    """Tests for MapManager.get_map()"""

    def test_get_map_returns_none_for_missing_map(self):
        """Test that get_map returns None for non-existent maps."""
        manager = MapManager()
        result = manager.get_map("nonexistent_map")
        assert result is None

    def test_get_map_returns_map_when_exists(self):
        """Test that get_map returns the map when it exists."""
        manager = MapManager()
        mock_map = MagicMock(spec=TileMap)
        manager.maps["test_map"] = mock_map
        
        result = manager.get_map("test_map")
        assert result is mock_map


class TestMapManagerIsValidMove:
    """Tests for MapManager.is_valid_move()"""

    def test_valid_move_returns_true(self):
        """Test that valid moves return True."""
        manager = MapManager()
        mock_map = MagicMock(spec=TileMap)
        mock_map.is_walkable.return_value = True
        manager.maps["test_map"] = mock_map
        
        result = manager.is_valid_move("test_map", 5, 5, 5, 6)
        
        assert result is True
        mock_map.is_walkable.assert_called_once_with(5, 6)

    def test_invalid_move_returns_false(self):
        """Test that invalid moves return False."""
        manager = MapManager()
        mock_map = MagicMock(spec=TileMap)
        mock_map.is_walkable.return_value = False
        mock_map.get_tile_info.return_value = {"walkable": False}
        manager.maps["test_map"] = mock_map
        
        result = manager.is_valid_move("test_map", 5, 5, 5, 6)
        
        assert result is False

    def test_move_on_nonexistent_map_returns_false(self):
        """Test that moves on non-existent maps return False."""
        manager = MapManager()
        
        result = manager.is_valid_move("nonexistent", 5, 5, 5, 6)
        
        assert result is False


class TestMapManagerGetSpawnPosition:
    """Tests for MapManager.get_spawn_position()"""

    def test_get_spawn_position_from_map(self):
        """Test getting spawn position from a map."""
        manager = MapManager()
        mock_map = MagicMock(spec=TileMap)
        mock_map.get_spawn_position.return_value = (10, 20)
        manager.maps["test_map"] = mock_map
        
        result = manager.get_spawn_position("test_map")
        
        assert result == (10, 20)

    def test_get_spawn_position_fallback_for_missing_map(self):
        """Test fallback spawn position for missing maps."""
        manager = MapManager()
        
        result = manager.get_spawn_position("nonexistent")
        
        assert result == (0, 0)


class TestMapManagerGetDefaultSpawnPosition:
    """Tests for MapManager.get_default_spawn_position()"""

    def test_default_spawn_from_tiled_player_spawn(self):
        """Test that Tiled player spawn is used when available."""
        manager = MapManager()
        mock_map = MagicMock(spec=TileMap)
        mock_map.player_spawn_point = {"x": 15, "y": 25}
        manager.maps["samplemap"] = mock_map
        
        with patch("server.src.services.map_service.settings") as mock_settings:
            mock_settings.DEFAULT_MAP = "samplemap"
            mock_settings.DEFAULT_SPAWN_X = 5
            mock_settings.DEFAULT_SPAWN_Y = 5
            
            result = manager.get_default_spawn_position()
            
            assert result == ("samplemap", 15, 25)

    def test_default_spawn_fallback_to_config(self):
        """Test that config spawn is used when no Tiled spawn exists."""
        manager = MapManager()
        mock_map = MagicMock(spec=TileMap)
        mock_map.player_spawn_point = None
        manager.maps["samplemap"] = mock_map
        
        with patch("server.src.services.map_service.settings") as mock_settings:
            mock_settings.DEFAULT_MAP = "samplemap"
            mock_settings.DEFAULT_SPAWN_X = 30
            mock_settings.DEFAULT_SPAWN_Y = 40
            
            result = manager.get_default_spawn_position()
            
            assert result == ("samplemap", 30, 40)

    def test_default_spawn_fallback_to_first_map(self):
        """Test fallback to first loaded map when default map missing."""
        manager = MapManager()
        mock_map = MagicMock(spec=TileMap)
        mock_map.player_spawn_point = {"x": 5, "y": 5}
        manager.maps["other_map"] = mock_map
        
        with patch("server.src.services.map_service.settings") as mock_settings:
            mock_settings.DEFAULT_MAP = "nonexistent"
            
            result = manager.get_default_spawn_position()
            
            assert result[0] == "other_map"

    def test_default_spawn_with_no_maps_loaded(self):
        """Test fallback when no maps are loaded."""
        manager = MapManager()
        
        with patch("server.src.services.map_service.settings") as mock_settings:
            mock_settings.DEFAULT_MAP = "samplemap"
            
            result = manager.get_default_spawn_position()
            
            assert result == ("fallback_map", 0, 0)


class TestMapManagerValidatePlayerPosition:
    """Tests for MapManager.validate_player_position()"""

    def test_valid_position_returned_unchanged(self):
        """Test that valid positions are returned unchanged."""
        manager = MapManager()
        mock_map = MagicMock(spec=TileMap)
        mock_map.is_walkable.return_value = True
        manager.maps["test_map"] = mock_map
        
        result = manager.validate_player_position("test_map", 10, 20)
        
        assert result == ("test_map", 10, 20)

    def test_invalid_position_returns_map_spawn(self):
        """Test that invalid positions redirect to map spawn."""
        manager = MapManager()
        mock_map = MagicMock(spec=TileMap)
        mock_map.is_walkable.return_value = False
        mock_map.get_spawn_position.return_value = (5, 5)
        manager.maps["test_map"] = mock_map
        
        result = manager.validate_player_position("test_map", 100, 100)
        
        assert result == ("test_map", 5, 5)

    def test_invalid_map_returns_default_spawn(self):
        """Test that invalid map IDs redirect to default spawn."""
        manager = MapManager()
        mock_map = MagicMock(spec=TileMap)
        mock_map.player_spawn_point = {"x": 1, "y": 1}
        manager.maps["default_map"] = mock_map
        
        with patch("server.src.services.map_service.settings") as mock_settings:
            mock_settings.DEFAULT_MAP = "default_map"
            
            result = manager.validate_player_position("nonexistent", 10, 20)
            
            assert result[0] == "default_map"


class TestMapManagerGetChunksForPlayer:
    """Tests for MapManager.get_chunks_for_player()"""

    def test_get_chunks_returns_chunk_data(self):
        """Test that chunks are returned for valid positions."""
        manager = MapManager()
        mock_map = MagicMock(spec=TileMap)
        mock_chunks = [{"chunk_x": 0, "chunk_y": 0, "tiles": []}]
        mock_map.get_chunks_around_position.return_value = mock_chunks
        manager.maps["test_map"] = mock_map
        
        result = manager.get_chunks_for_player("test_map", 50, 50, radius=1)
        
        assert result == mock_chunks
        mock_map.get_chunks_around_position.assert_called_once_with(50, 50, 1)

    def test_get_chunks_returns_none_for_missing_map(self):
        """Test that None is returned for non-existent maps."""
        manager = MapManager()
        
        result = manager.get_chunks_for_player("nonexistent", 50, 50)
        
        assert result is None


class TestMapManagerGetChunkData:
    """Tests for MapManager.get_chunk_data()"""

    def test_get_chunk_data_returns_data(self):
        """Test getting specific chunk data."""
        manager = MapManager()
        mock_map = MagicMock(spec=TileMap)
        mock_chunk = {"chunk_x": 2, "chunk_y": 3, "tiles": []}
        mock_map.get_chunk_data.return_value = mock_chunk
        manager.maps["test_map"] = mock_map
        
        result = manager.get_chunk_data("test_map", 2, 3)
        
        assert result == mock_chunk

    def test_get_chunk_data_returns_none_for_missing_map(self):
        """Test that None is returned for non-existent maps."""
        manager = MapManager()
        
        result = manager.get_chunk_data("nonexistent", 2, 3)
        
        assert result is None


class TestMapManagerGetMapInfo:
    """Tests for MapManager.get_map_info()"""

    def test_get_map_info_returns_info(self):
        """Test getting map information."""
        manager = MapManager()
        mock_map = MagicMock(spec=TileMap)
        mock_map.width = 100
        mock_map.height = 80
        mock_map.tile_width = 32
        mock_map.tile_height = 32
        mock_map.walkable_tiles = {1, 2, 3, 4, 5}
        manager.maps["test_map"] = mock_map
        
        result = manager.get_map_info("test_map")
        
        assert result["exists"] is True
        assert result["id"] == "test_map"
        assert result["width"] == 100
        assert result["height"] == 80
        assert result["tile_size"] == {"width": 32, "height": 32}
        assert result["walkable_tiles"] == 5

    def test_get_map_info_returns_not_exists_for_missing(self):
        """Test that info for missing maps shows exists=False."""
        manager = MapManager()
        
        result = manager.get_map_info("nonexistent")
        
        assert result == {"exists": False}


class TestMapManagerGetDistanceBetweenPositions:
    """Tests for MapManager.get_distance_between_positions()"""

    def test_distance_same_position(self):
        """Test distance between same position is 0."""
        manager = MapManager()
        
        result = manager.get_distance_between_positions((5, 5), (5, 5))
        
        assert result == 0.0

    def test_distance_horizontal(self):
        """Test horizontal distance calculation."""
        manager = MapManager()
        
        result = manager.get_distance_between_positions((0, 0), (3, 0))
        
        assert result == 3.0

    def test_distance_vertical(self):
        """Test vertical distance calculation."""
        manager = MapManager()
        
        result = manager.get_distance_between_positions((0, 0), (0, 4))
        
        assert result == 4.0

    def test_distance_diagonal(self):
        """Test diagonal distance calculation (3-4-5 triangle)."""
        manager = MapManager()
        
        result = manager.get_distance_between_positions((0, 0), (3, 4))
        
        assert result == 5.0


class TestMapManagerValidateChunkRequestSecurity:
    """Tests for MapManager.validate_chunk_request_security()"""

    @pytest.mark.asyncio
    async def test_valid_chunk_request(self, gsm: GameStateManager):
        """Test that valid chunk requests are accepted."""
        manager = MapManager()
        
        with patch("server.src.services.player_service.PlayerService") as mock_player_service:
            mock_player_service.validate_player_position_access = AsyncMock(return_value=True)
            
            result = await manager.validate_chunk_request_security(
                player_id=1,
                map_id="test_map",
                chunk_x=0,
                chunk_y=0,
                radius=1
            )
            
            assert result is True

    @pytest.mark.asyncio
    async def test_invalid_position_access_denied(self, gsm: GameStateManager):
        """Test that invalid position access is denied."""
        manager = MapManager()
        
        with patch("server.src.services.player_service.PlayerService") as mock_player_service:
            mock_player_service.validate_player_position_access = AsyncMock(return_value=False)
            
            result = await manager.validate_chunk_request_security(
                player_id=1,
                map_id="test_map",
                chunk_x=100,
                chunk_y=100,
                radius=1
            )
            
            assert result is False

    @pytest.mark.asyncio
    async def test_excessive_radius_denied(self, gsm: GameStateManager):
        """Test that excessive radius requests are denied."""
        manager = MapManager()
        
        with patch("server.src.services.player_service.PlayerService") as mock_player_service:
            mock_player_service.validate_player_position_access = AsyncMock(return_value=True)
            
            result = await manager.validate_chunk_request_security(
                player_id=1,
                map_id="test_map",
                chunk_x=0,
                chunk_y=0,
                radius=10  # Too large (max is 2)
            )
            
            assert result is False


class TestMapManagerLoadMaps:
    """Tests for MapManager.load_maps()"""

    @pytest.mark.asyncio
    async def test_load_maps_handles_no_maps(self, gsm: GameStateManager):
        """Test that load_maps handles empty maps directory gracefully."""
        manager = MapManager()
        
        # Patch at the pathlib module level instead of on the instance
        with patch("pathlib.Path.glob", return_value=iter([])):
            await manager.load_maps()
            
            # Maps should be empty when no files found
            assert len(manager.maps) == 0 or manager.maps == {}


class TestTileMapIsWalkable:
    """Tests for TileMap.is_walkable()"""

    def test_out_of_bounds_negative_x(self):
        """Test that negative X is not walkable."""
        tile_map = Mock(spec=TileMap)
        tile_map.width = 10
        tile_map.height = 10
        tile_map.tmx_data = None
        tile_map.collision_layers = []
        
        # Call the actual method
        result = TileMap.is_walkable(tile_map, -1, 5)
        
        assert result is False

    def test_out_of_bounds_negative_y(self):
        """Test that negative Y is not walkable."""
        tile_map = Mock(spec=TileMap)
        tile_map.width = 10
        tile_map.height = 10
        tile_map.tmx_data = None
        tile_map.collision_layers = []
        
        result = TileMap.is_walkable(tile_map, 5, -1)
        
        assert result is False

    def test_out_of_bounds_exceeds_width(self):
        """Test that X >= width is not walkable."""
        tile_map = Mock(spec=TileMap)
        tile_map.width = 10
        tile_map.height = 10
        tile_map.tmx_data = None
        tile_map.collision_layers = []
        
        result = TileMap.is_walkable(tile_map, 10, 5)
        
        assert result is False

    def test_out_of_bounds_exceeds_height(self):
        """Test that Y >= height is not walkable."""
        tile_map = Mock(spec=TileMap)
        tile_map.width = 10
        tile_map.height = 10
        tile_map.tmx_data = None
        tile_map.collision_layers = []
        
        result = TileMap.is_walkable(tile_map, 5, 10)
        
        assert result is False


class TestTileMapGetSpawnPosition:
    """Tests for TileMap.get_spawn_position()"""

    def test_get_spawn_position_finds_walkable_tile(self):
        """Test that spawn position finds a walkable tile."""
        tile_map = Mock(spec=TileMap)
        tile_map.width = 10
        tile_map.height = 10
        
        # Make center tile walkable
        def mock_is_walkable(x, y):
            return x == 5 and y == 5
        
        tile_map.is_walkable = mock_is_walkable
        
        result = TileMap.get_spawn_position(tile_map)
        
        assert result == (5, 5)

    def test_get_spawn_position_fallback(self):
        """Test that spawn position falls back to (1, 1) if no walkable tile."""
        tile_map = Mock(spec=TileMap)
        tile_map.width = 4
        tile_map.height = 4
        tile_map.is_walkable = Mock(return_value=False)  # Nothing is walkable
        
        result = TileMap.get_spawn_position(tile_map)
        
        assert result == (1, 1)


class TestTileMapGetTileInfo:
    """Tests for TileMap.get_tile_info()"""

    def test_get_tile_info_out_of_bounds(self):
        """Test that out of bounds returns invalid tile info."""
        tile_map = Mock(spec=TileMap)
        tile_map.width = 10
        tile_map.height = 10
        
        result = TileMap.get_tile_info(tile_map, -1, 5)
        
        assert result == {"valid": False, "walkable": False}

    def test_get_tile_info_valid_tile(self):
        """Test that valid tile returns proper info."""
        tile_map = Mock(spec=TileMap)
        tile_map.width = 10
        tile_map.height = 10
        tile_map.is_walkable = Mock(return_value=True)
        tile_map.tmx_data = None
        
        result = TileMap.get_tile_info(tile_map, 5, 5)
        
        assert result["valid"] is True
        assert result["walkable"] is True


class TestTileMapGetCollisionGrid:
    """Tests for TileMap.get_collision_grid()"""

    def test_collision_grid_cached(self):
        """Test that collision grid is cached."""
        tile_map = Mock(spec=TileMap)
        tile_map._collision_grid = [[True, False], [False, True]]
        
        result = TileMap.get_collision_grid(tile_map)
        
        assert result == [[True, False], [False, True]]

    def test_collision_grid_built_when_not_cached(self):
        """Test that collision grid is built when not cached."""
        tile_map = Mock(spec=TileMap)
        tile_map._collision_grid = None
        tile_map.width = 2
        tile_map.height = 2
        
        # Checker pattern of walkable tiles
        def mock_is_walkable(x, y):
            return (x + y) % 2 == 0
        
        tile_map.is_walkable = mock_is_walkable
        
        result = TileMap.get_collision_grid(tile_map)
        
        # True = blocked, False = walkable
        # (0,0) walkable -> False, (1,0) blocked -> True
        # (0,1) blocked -> True, (1,1) walkable -> False
        expected = [[False, True], [True, False]]
        assert result == expected


class TestTileMapGetChunkData:
    """Tests for TileMap.get_chunk_data()"""

    def test_chunk_out_of_bounds_returns_none(self):
        """Test that completely out of bounds chunks return None."""
        tile_map = Mock(spec=TileMap)
        tile_map.width = 32
        tile_map.height = 32
        
        # Chunk at (10, 10) with size 16 = tiles 160-176, which is > 32
        result = TileMap.get_chunk_data(tile_map, 10, 10, 16)
        
        assert result is None


class TestTileMapGetChunksAroundPosition:
    """Tests for TileMap.get_chunks_around_position()"""

    def test_chunks_around_center_position(self):
        """Test getting chunks around a center position."""
        tile_map = Mock(spec=TileMap)
        tile_map.get_chunk_data = Mock(side_effect=lambda x, y, size: {
            "chunk_x": x,
            "chunk_y": y
        } if x >= 0 and y >= 0 else None)
        
        result = TileMap.get_chunks_around_position(tile_map, 24, 24, radius=1, chunk_size=16)
        
        # Position 24 is in chunk 1 (24 // 16 = 1)
        # With radius 1, we get chunks 0, 1, 2 in each direction
        assert len(result) == 9  # 3x3 grid


class TestTileMapGetTilesetMetadata:
    """Tests for TileMap.get_tileset_metadata()"""

    def test_get_tileset_metadata_no_tmx_data(self):
        """Test that empty list returned when no tmx data."""
        tile_map = Mock(spec=TileMap)
        tile_map.tmx_data = None
        
        result = TileMap.get_tileset_metadata(tile_map)
        
        assert result == []


class TestTileMapGetCorrectTileData:
    """Tests for TileMap.get_correct_tile_data()"""

    def test_get_correct_tile_data_no_tmx(self):
        """Test that None returned when no tmx data."""
        tile_map = Mock(spec=TileMap)
        tile_map.tmx_data = None
        
        result = TileMap.get_correct_tile_data(tile_map, 5)
        
        assert result is None

    def test_get_correct_tile_data_zero_gid(self):
        """Test that None returned for GID 0."""
        tile_map = Mock(spec=TileMap)
        tile_map.tmx_data = MagicMock()
        
        result = TileMap.get_correct_tile_data(tile_map, 0)
        
        assert result is None

    def test_get_correct_tile_data_negative_gid(self):
        """Test that None returned for negative GID."""
        tile_map = Mock(spec=TileMap)
        tile_map.tmx_data = MagicMock()
        
        result = TileMap.get_correct_tile_data(tile_map, -1)
        
        assert result is None
