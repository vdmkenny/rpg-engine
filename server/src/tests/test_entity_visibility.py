"""
Tests for entity visibility in game loop.
"""

import pytest
from server.src.game.game_loop import (
    get_visible_npc_entities,
    get_visible_entities,
    is_in_visible_range,
    _build_equipped_items_map,
)


class TestEntityVisibility:
    """Test entity visibility calculations in game loop."""
    
    def test_get_visible_npc_entities_empty_list(self):
        """Test with no entities."""
        visible = get_visible_npc_entities(25, 25, [])
        assert visible == {}
    
    def test_get_visible_npc_entities_in_range(self):
        """Test entity within visible range."""
        entities = [
            {
                "id": 1,
                "entity_name": "GOBLIN",
                "x": 30,
                "y": 30,
                "current_hp": 10,
                "max_hp": 10,
                "state": "idle",
            }
        ]
        
        visible = get_visible_npc_entities(25, 25, entities)
        
        assert len(visible) == 1
        assert "entity_1" in visible
        entity_data = visible["entity_1"]
        assert entity_data["type"] == "entity"
        assert entity_data["id"] == 1
        assert entity_data["entity_name"] == "GOBLIN"
        assert entity_data["display_name"] == "Goblin"
        assert entity_data["behavior_type"] == "AGGRESSIVE"
        assert entity_data["x"] == 30
        assert entity_data["y"] == 30
        assert entity_data["current_hp"] == 10
        assert entity_data["max_hp"] == 10
        assert entity_data["state"] == "idle"
        assert entity_data["is_attackable"] is True
        # Monsters include sprite_sheet_id for rendering
        assert "sprite_sheet_id" in entity_data
        assert entity_data["entity_type"] == "monster"
    
    def test_get_visible_npc_entities_out_of_range(self):
        """Test entity outside visible range."""
        entities = [
            {
                "id": 1,
                "entity_name": "GOBLIN",
                "x": 100,  # Far away
                "y": 100,
                "current_hp": 10,
                "max_hp": 10,
                "state": "idle",
            }
        ]
        
        visible = get_visible_npc_entities(25, 25, entities)
        
        assert len(visible) == 0
    
    def test_get_visible_npc_entities_skip_dead(self):
        """Test that dead entities are not visible."""
        entities = [
            {
                "id": 1,
                "entity_name": "GOBLIN",
                "x": 30,
                "y": 30,
                "current_hp": 0,
                "max_hp": 10,
                "state": "dead",  # Dead entities are hidden
            }
        ]
        
        visible = get_visible_npc_entities(25, 25, entities)
        
        assert len(visible) == 0
    
    def test_get_visible_npc_entities_show_dying(self):
        """Test that dying entities are visible (death animation)."""
        entities = [
            {
                "id": 1,
                "entity_name": "GOBLIN",
                "x": 30,
                "y": 30,
                "current_hp": 0,
                "max_hp": 10,
                "state": "dying",  # Dying entities are visible
                "death_tick": 1000,
            }
        ]
        
        visible = get_visible_npc_entities(25, 25, entities)
        
        assert len(visible) == 1
        assert "entity_1" in visible
        entity_data = visible["entity_1"]
        assert entity_data["state"] == "dying"
        assert entity_data["current_hp"] == 0
        assert entity_data["is_attackable"] is False  # Can't attack dying entities
    
    def test_get_visible_npc_entities_multiple(self):
        """Test multiple entities with mixed visibility."""
        entities = [
            {
                "id": 1,
                "entity_name": "GOBLIN",
                "x": 30,
                "y": 30,
                "current_hp": 10,
                "max_hp": 10,
                "state": "idle",
            },
            {
                "id": 2,
                "entity_name": "GIANT_RAT",
                "x": 32,
                "y": 28,
                "current_hp": 8,
                "max_hp": 8,
                "state": "wandering",
            },
            {
                "id": 3,
                "entity_name": "FOREST_BEAR",
                "x": 200,  # Out of range
                "y": 200,
                "current_hp": 60,
                "max_hp": 60,
                "state": "idle",
            },
            {
                "id": 4,
                "entity_name": "GOBLIN",
                "x": 28,
                "y": 27,
                "current_hp": 0,
                "max_hp": 10,
                "state": "dead",  # Dead, should be hidden
            }
        ]
        
        visible = get_visible_npc_entities(25, 25, entities)
        
        assert len(visible) == 2
        assert "entity_1" in visible
        assert "entity_2" in visible
        assert "entity_3" not in visible  # Out of range
        assert "entity_4" not in visible  # Dead
        
        # Check GIANT_RAT data
        rat_data = visible["entity_2"]
        assert rat_data["display_name"] == "Giant Rat"
        assert rat_data["behavior_type"] == "AGGRESSIVE"
    
    def test_get_visible_npc_entities_npc_types(self):
        """Test different NPC types (guards, merchants, quest givers)."""
        entities = [
            {
                "id": 1,
                "entity_name": "VILLAGE_GUARD",
                "entity_type": "humanoid_npc",
                "x": 30,
                "y": 30,
                "current_hp": 100,
                "max_hp": 100,
                "state": "idle",
            },
            {
                "id": 2,
                "entity_name": "SHOPKEEPER_BOB",
                "entity_type": "humanoid_npc",
                "x": 32,
                "y": 28,
                "current_hp": 10,
                "max_hp": 10,
                "state": "idle",
            },
            {
                "id": 3,
                "entity_name": "VILLAGE_ELDER",
                "entity_type": "humanoid_npc",
                "x": 28,
                "y": 27,
                "current_hp": 20,
                "max_hp": 20,
                "state": "idle",
            }
        ]
        
        visible = get_visible_npc_entities(25, 25, entities)
        
        assert len(visible) == 3
        
        # Check guard - humanoid with appearance and equipment
        guard_data = visible["entity_1"]
        assert guard_data["display_name"] == "Village Guard"
        assert guard_data["behavior_type"] == "GUARD"
        assert guard_data["is_attackable"] is True
        assert guard_data["entity_type"] == "humanoid_npc"
        assert "appearance" in guard_data
        assert "equipped_items" in guard_data
        
        # Check merchant
        merchant_data = visible["entity_2"]
        assert merchant_data["display_name"] == "Bob"
        assert merchant_data["behavior_type"] == "MERCHANT"
        assert merchant_data["is_attackable"] is False
        assert merchant_data["entity_type"] == "humanoid_npc"
        
        # Check quest giver
        elder_data = visible["entity_3"]
        assert elder_data["display_name"] == "Village Elder"
        assert elder_data["behavior_type"] == "QUEST_GIVER"
        assert elder_data["is_attackable"] is False
        assert elder_data["entity_type"] == "humanoid_npc"
    
    def test_get_visible_npc_entities_unknown_entity_type(self):
        """Test entity with unknown entity_name."""
        entities = [
            {
                "id": 1,
                "entity_name": "UNKNOWN_MONSTER",
                "x": 30,
                "y": 30,
                "current_hp": 10,
                "max_hp": 10,
                "state": "idle",
            }
        ]
        
        visible = get_visible_npc_entities(25, 25, entities)
        
        assert len(visible) == 1
        entity_data = visible["entity_1"]
        assert entity_data["entity_name"] == "UNKNOWN_MONSTER"
        assert entity_data["display_name"] == "UNKNOWN_MONSTER"  # Falls back to entity_name
        assert entity_data["behavior_type"] == "PASSIVE"  # Default behavior
        assert entity_data["is_attackable"] is True  # Default attackable
    
    def test_is_in_visible_range(self):
        """Test visibility range calculation."""
        # Default radius = 1, chunk_size = 16
        # Visible range = (1 + 1) * 16 = 32 tiles
        
        # Within range (exactly 32 tiles away)
        assert is_in_visible_range(0, 0, 32, 0) is True
        assert is_in_visible_range(0, 0, 0, 32) is True
        assert is_in_visible_range(0, 0, 32, 32) is True
        
        # Within range (closer)
        assert is_in_visible_range(0, 0, 10, 10) is True
        assert is_in_visible_range(0, 0, 0, 0) is True
        
        # Outside range (33 tiles away)
        assert is_in_visible_range(0, 0, 33, 0) is False
        assert is_in_visible_range(0, 0, 0, 33) is False
        assert is_in_visible_range(0, 0, 33, 33) is False
        
        # Outside range (far away)
        assert is_in_visible_range(0, 0, 100, 100) is False


class TestPlayerVisibility:
    """Test player visibility with paperdoll data."""
    
    def test_get_visible_players_includes_appearance(self):
        """Test that visible players include appearance data."""
        players = [
            {
                "id": "player1",
                "username": "player1",
                "x": 30,
                "y": 30,
                "current_hp": 50,
                "max_hp": 100,
                "appearance": {"skin_tone": 1, "hair_style": "short", "hair_color": "#4A3728"},
                "equipped_items": {"weapon": "BRONZE_SWORD"},
            },
            {
                "id": "viewer",
                "username": "viewer",
                "x": 25,
                "y": 25,
                "current_hp": 100,
                "max_hp": 100,
                "appearance": None,
                "equipped_items": None,
            }
        ]
        
        visible = get_visible_entities(25, 25, players, "viewer")
        
        assert len(visible) == 1
        assert "player1" in visible
        player_data = visible["player1"]
        assert player_data["type"] == "player"
        assert player_data["appearance"] == {"skin_tone": 1, "hair_style": "short", "hair_color": "#4A3728"}
        assert player_data["equipped_items"] == {"weapon": "BRONZE_SWORD"}
    
    def test_get_visible_players_excludes_self(self):
        """Test that viewing player is excluded from visibility."""
        players = [
            {
                "id": "viewer",
                "username": "viewer",
                "x": 25,
                "y": 25,
                "current_hp": 100,
                "max_hp": 100,
                "appearance": None,
                "equipped_items": None,
            }
        ]
        
        visible = get_visible_entities(25, 25, players, "viewer")
        
        assert len(visible) == 0
    
    def test_get_visible_players_out_of_range(self):
        """Test that distant players are not visible."""
        players = [
            {
                "id": "distant_player",
                "username": "distant_player",
                "x": 200,
                "y": 200,
                "current_hp": 100,
                "max_hp": 100,
                "appearance": None,
                "equipped_items": None,
            }
        ]
        
        visible = get_visible_entities(25, 25, players, "viewer")
        
        assert len(visible) == 0
    
    def test_get_visible_players_null_appearance(self):
        """Test players with null appearance are still visible."""
        players = [
            {
                "id": "player1",
                "username": "player1",
                "x": 30,
                "y": 30,
                "current_hp": 50,
                "max_hp": 100,
                "appearance": None,
                "equipped_items": None,
            }
        ]
        
        visible = get_visible_entities(25, 25, players, "viewer")
        
        assert len(visible) == 1
        player_data = visible["player1"]
        assert player_data["appearance"] is None
        assert player_data["equipped_items"] is None


class TestBuildEquippedItemsMap:
    """Test the equipment to item name mapping helper."""
    
    def test_empty_equipment(self):
        """Test with no equipment."""
        result = _build_equipped_items_map({}, None)
        assert result is None
    
    def test_none_equipment(self):
        """Test with None equipment."""
        result = _build_equipped_items_map(None, None)
        assert result is None
    
    def test_equipment_with_missing_item_id(self):
        """Test equipment entries without item_id are skipped."""
        equipment = {"weapon": {"quantity": 1}}
        
        class MockGSM:
            def get_cached_item_meta(self, item_id):
                return {"name": "test_item"}
        
        result = _build_equipped_items_map(equipment, MockGSM())
        assert result is None  # No valid items
    
    def test_equipment_with_valid_items(self):
        """Test equipment with valid item IDs."""
        equipment = {
            "weapon": {"item_id": 1, "quantity": 1},
            "shield": {"item_id": 2, "quantity": 1},
        }
        
        class MockGSM:
            def get_cached_item_meta(self, item_id):
                items = {1: {"name": "BRONZE_SWORD"}, 2: {"name": "WOODEN_SHIELD"}}
                return items.get(item_id)
        
        result = _build_equipped_items_map(equipment, MockGSM())
        assert result == {"weapon": "BRONZE_SWORD", "shield": "WOODEN_SHIELD"}
    
    def test_equipment_with_uncached_item(self):
        """Test equipment with item not in cache is skipped."""
        equipment = {
            "weapon": {"item_id": 1, "quantity": 1},
            "shield": {"item_id": 999, "quantity": 1},  # Not in cache
        }
        
        class MockGSM:
            def get_cached_item_meta(self, item_id):
                items = {1: {"name": "BRONZE_SWORD"}}
                return items.get(item_id)
        
        result = _build_equipped_items_map(equipment, MockGSM())
        assert result == {"weapon": "BRONZE_SWORD"}
