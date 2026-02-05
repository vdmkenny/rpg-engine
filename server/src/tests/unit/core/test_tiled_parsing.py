"""
Unit tests for Tiled map object layer parsing.
"""

import pytest
from unittest.mock import Mock, MagicMock
from server.src.services.map_service import TileMap


class TestTiledObjectLayerParsing:
    """Test parsing of Tiled object layers for spawn points."""
    
    def test_parse_entity_spawn_basic(self):
        """Test parsing basic entity spawn point."""
        # Create mock Tiled object
        mock_obj = Mock()
        mock_obj.type = "entity_spawn"
        mock_obj.name = "Goblin Spawn 1"
        mock_obj.id = 10
        mock_obj.x = 320  # 10 tiles * 32 pixels
        mock_obj.y = 480  # 15 tiles * 32 pixels
        mock_obj.properties = {
            "entity_id": "GOBLIN",
            "wander_radius": 5
        }
        
        # Create TileMap mock with necessary attributes
        tile_map = Mock(spec=TileMap)
        tile_map.tile_width = 32
        tile_map.tile_height = 32
        tile_map.entity_spawn_points = []
        
        # Call the parsing method directly
        TileMap._parse_entity_spawn(tile_map, mock_obj)
        
        # Verify spawn point was added
        assert len(tile_map.entity_spawn_points) == 1
        spawn = tile_map.entity_spawn_points[0]
        
        assert spawn["id"] == 10
        assert spawn["name"] == "Goblin Spawn 1"
        assert spawn["entity_id"] == "GOBLIN"
        assert spawn["x"] == 10  # Converted from pixels to tiles
        assert spawn["y"] == 15
        assert spawn["wander_radius"] == 5
        assert spawn["aggro_override"] is None
        assert spawn["disengage_override"] is None
        assert spawn["patrol_route"] is None
    
    def test_parse_entity_spawn_with_overrides(self):
        """Test parsing entity spawn with custom aggro/disengage overrides."""
        mock_obj = Mock()
        mock_obj.type = "entity_spawn"
        mock_obj.name = "Boss Spawn"
        mock_obj.id = 20
        mock_obj.x = 800
        mock_obj.y = 800
        mock_obj.properties = {
            "entity_id": "FOREST_BEAR",
            "wander_radius": 0,
            "aggro_override": 10,
            "disengage_override": 30
        }
        
        tile_map = Mock(spec=TileMap)
        tile_map.tile_width = 32
        tile_map.tile_height = 32
        tile_map.entity_spawn_points = []
        
        TileMap._parse_entity_spawn(tile_map, mock_obj)
        
        assert len(tile_map.entity_spawn_points) == 1
        spawn = tile_map.entity_spawn_points[0]
        
        assert spawn["entity_id"] == "FOREST_BEAR"
        assert spawn["aggro_override"] == 10
        assert spawn["disengage_override"] == 30
    
    def test_parse_entity_spawn_missing_entity_id(self):
        """Test that spawn without entity_id is skipped with warning."""
        mock_obj = Mock()
        mock_obj.type = "entity_spawn"
        mock_obj.name = "Invalid Spawn"
        mock_obj.id = 30
        mock_obj.x = 320
        mock_obj.y = 320
        mock_obj.properties = {
            "wander_radius": 5
            # Missing entity_id
        }
        
        tile_map = Mock(spec=TileMap)
        tile_map.tile_width = 32
        tile_map.tile_height = 32
        tile_map.entity_spawn_points = []
        
        TileMap._parse_entity_spawn(tile_map, mock_obj)
        
        # Should not add invalid spawn
        assert len(tile_map.entity_spawn_points) == 0
    
    def test_parse_entity_spawn_with_patrol_route(self):
        """Test parsing entity spawn with patrol route."""
        mock_obj = Mock()
        mock_obj.type = "entity_spawn"
        mock_obj.name = "Guard Patrol"
        mock_obj.id = 40
        mock_obj.x = 1600
        mock_obj.y = 1600
        mock_obj.properties = {
            "entity_id": "VILLAGE_GUARD",
            "wander_radius": 0,
            "patrol_route": "route_1"
        }
        
        tile_map = Mock(spec=TileMap)
        tile_map.tile_width = 32
        tile_map.tile_height = 32
        tile_map.entity_spawn_points = []
        
        TileMap._parse_entity_spawn(tile_map, mock_obj)
        
        assert len(tile_map.entity_spawn_points) == 1
        spawn = tile_map.entity_spawn_points[0]
        
        assert spawn["patrol_route"] == "route_1"
    
    def test_parse_player_spawn_basic(self):
        """Test parsing basic player spawn point."""
        mock_obj = Mock()
        mock_obj.type = "player_spawn"
        mock_obj.name = "Main Spawn"
        mock_obj.id = 1
        mock_obj.x = 800  # 25 tiles
        mock_obj.y = 800  # 25 tiles
        
        tile_map = Mock(spec=TileMap)
        tile_map.tile_width = 32
        tile_map.tile_height = 32
        tile_map.player_spawn_point = None
        
        TileMap._parse_player_spawn(tile_map, mock_obj)
        
        # Verify player spawn was set
        assert tile_map.player_spawn_point is not None
        spawn = tile_map.player_spawn_point
        
        assert spawn["id"] == 1
        assert spawn["name"] == "Main Spawn"
        assert spawn["x"] == 25
        assert spawn["y"] == 25
    
    def test_parse_player_spawn_only_first(self):
        """Test that only first player spawn is used."""
        tile_map = Mock(spec=TileMap)
        tile_map.tile_width = 32
        tile_map.tile_height = 32
        tile_map.player_spawn_point = None
        
        # Parse first spawn
        mock_obj1 = Mock()
        mock_obj1.type = "player_spawn"
        mock_obj1.name = "First Spawn"
        mock_obj1.id = 1
        mock_obj1.x = 800
        mock_obj1.y = 800
        
        TileMap._parse_player_spawn(tile_map, mock_obj1)
        
        first_spawn = tile_map.player_spawn_point
        assert first_spawn["name"] == "First Spawn"
        
        # Try to parse second spawn
        mock_obj2 = Mock()
        mock_obj2.type = "player_spawn"
        mock_obj2.name = "Second Spawn"
        mock_obj2.id = 2
        mock_obj2.x = 1600
        mock_obj2.y = 1600
        
        TileMap._parse_player_spawn(tile_map, mock_obj2)
        
        # Should still have first spawn
        assert tile_map.player_spawn_point == first_spawn
        assert tile_map.player_spawn_point["name"] == "First Spawn"
    
    def test_parse_multiple_entity_spawns(self):
        """Test parsing multiple entity spawn points."""
        tile_map = Mock(spec=TileMap)
        tile_map.tile_width = 32
        tile_map.tile_height = 32
        tile_map.entity_spawn_points = []
        
        # Create multiple spawn objects
        spawns = [
            ("GOBLIN", 320, 320, 5),
            ("GIANT_RAT", 640, 640, 3),
            ("SHOPKEEPER_BOB", 960, 960, 0),
        ]
        
        for entity_id, x, y, wander in spawns:
            mock_obj = Mock()
            mock_obj.type = "entity_spawn"
            mock_obj.name = f"{entity_id} Spawn"
            mock_obj.id = len(tile_map.entity_spawn_points) + 10
            mock_obj.x = x
            mock_obj.y = y
            mock_obj.properties = {
                "entity_id": entity_id,
                "wander_radius": wander
            }
            
            TileMap._parse_entity_spawn(tile_map, mock_obj)
        
        # Verify all spawns were added
        assert len(tile_map.entity_spawn_points) == 3
        
        # Verify each spawn
        assert tile_map.entity_spawn_points[0]["entity_id"] == "GOBLIN"
        assert tile_map.entity_spawn_points[0]["wander_radius"] == 5
        
        assert tile_map.entity_spawn_points[1]["entity_id"] == "GIANT_RAT"
        assert tile_map.entity_spawn_points[1]["wander_radius"] == 3
        
        assert tile_map.entity_spawn_points[2]["entity_id"] == "SHOPKEEPER_BOB"
        assert tile_map.entity_spawn_points[2]["wander_radius"] == 0
    
    def test_pixel_to_tile_conversion(self):
        """Test correct conversion from pixel coordinates to tile coordinates."""
        tile_map = Mock(spec=TileMap)
        tile_map.tile_width = 32
        tile_map.tile_height = 32
        tile_map.entity_spawn_points = []
        
        # Test various pixel positions
        test_cases = [
            (0, 0, 0, 0),      # Origin
            (32, 32, 1, 1),    # One tile offset
            (320, 480, 10, 15), # Multi-tile offset
            (1600, 1600, 50, 50), # Large offset
            (31, 31, 0, 0),    # Just under one tile (should round down)
        ]
        
        for pixel_x, pixel_y, expected_tile_x, expected_tile_y in test_cases:
            tile_map.entity_spawn_points = []  # Reset
            
            mock_obj = Mock()
            mock_obj.type = "entity_spawn"
            mock_obj.name = f"Test {pixel_x},{pixel_y}"
            mock_obj.id = 1
            mock_obj.x = pixel_x
            mock_obj.y = pixel_y
            mock_obj.properties = {"entity_id": "GOBLIN", "wander_radius": 0}
            
            TileMap._parse_entity_spawn(tile_map, mock_obj)
            
            spawn = tile_map.entity_spawn_points[0]
            assert spawn["x"] == expected_tile_x, f"Failed for pixel_x={pixel_x}"
            assert spawn["y"] == expected_tile_y, f"Failed for pixel_y={pixel_y}"
    
    def test_parse_entity_spawn_default_wander_radius(self):
        """Test that wander_radius defaults to 0 if not specified."""
        mock_obj = Mock()
        mock_obj.type = "entity_spawn"
        mock_obj.name = "Static NPC"
        mock_obj.id = 50
        mock_obj.x = 800
        mock_obj.y = 800
        mock_obj.properties = {
            "entity_id": "VILLAGE_ELDER"
            # No wander_radius specified
        }
        
        tile_map = Mock(spec=TileMap)
        tile_map.tile_width = 32
        tile_map.tile_height = 32
        tile_map.entity_spawn_points = []
        
        TileMap._parse_entity_spawn(tile_map, mock_obj)
        
        spawn = tile_map.entity_spawn_points[0]
        assert spawn["wander_radius"] == 0  # Should default to 0
    
    def test_parse_object_layers_integration(self):
        """Test full object layer parsing integration."""
        # Create mock TMX data with objects
        mock_tmx = Mock()
        
        # Create entity spawn object
        entity_obj = Mock()
        entity_obj.type = "entity_spawn"
        entity_obj.name = "Goblin 1"
        entity_obj.id = 10
        entity_obj.x = 320
        entity_obj.y = 480
        entity_obj.properties = {
            "entity_id": "GOBLIN",
            "wander_radius": 8
        }
        
        # Create player spawn object
        player_obj = Mock()
        player_obj.type = "player_spawn"
        player_obj.name = "Main Spawn"
        player_obj.id = 1
        player_obj.x = 800
        player_obj.y = 800
        player_obj.properties = {}
        
        # Create unrelated object (should be ignored)
        other_obj = Mock()
        other_obj.type = "decoration"
        other_obj.name = "Tree"
        other_obj.id = 100
        
        mock_tmx.objects = [entity_obj, player_obj, other_obj]
        
        # Create a minimal TileMap instance manually (bypass constructor)
        tile_map = object.__new__(TileMap)
        tile_map.tmx_data = mock_tmx
        tile_map.tile_width = 32
        tile_map.tile_height = 32
        tile_map.entity_spawn_points = []
        tile_map.player_spawn_point = None
        
        # Call the parsing method directly
        tile_map._parse_object_layers()
        
        # Verify results
        assert len(tile_map.entity_spawn_points) == 1
        assert tile_map.entity_spawn_points[0]["entity_id"] == "GOBLIN"
        assert tile_map.entity_spawn_points[0]["wander_radius"] == 8
        
        assert tile_map.player_spawn_point is not None
        assert tile_map.player_spawn_point["name"] == "Main Spawn"
    
    def test_parse_no_objects(self):
        """Test parsing when no objects exist in map."""
        mock_tmx = Mock()
        mock_tmx.objects = []
        
        tile_map = Mock(spec=TileMap)
        tile_map.tmx_data = mock_tmx
        tile_map.tile_width = 32
        tile_map.tile_height = 32
        tile_map.entity_spawn_points = []
        tile_map.player_spawn_point = None
        
        TileMap._parse_object_layers(tile_map)
        
        # Should handle gracefully
        assert len(tile_map.entity_spawn_points) == 0
        assert tile_map.player_spawn_point is None
