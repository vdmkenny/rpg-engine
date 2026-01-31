"""
Tests for entity visibility in game loop.
"""

import pytest
from server.src.game.game_loop import get_visible_npc_entities, is_in_visible_range


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
        assert entity_data["sprite_info"] == ""
    
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
                "x": 30,
                "y": 30,
                "current_hp": 100,
                "max_hp": 100,
                "state": "idle",
            },
            {
                "id": 2,
                "entity_name": "SHOPKEEPER_BOB",
                "x": 32,
                "y": 28,
                "current_hp": 10,
                "max_hp": 10,
                "state": "idle",
            },
            {
                "id": 3,
                "entity_name": "VILLAGE_ELDER",
                "x": 28,
                "y": 27,
                "current_hp": 20,
                "max_hp": 20,
                "state": "idle",
            }
        ]
        
        visible = get_visible_npc_entities(25, 25, entities)
        
        assert len(visible) == 3
        
        # Check guard
        guard_data = visible["entity_1"]
        assert guard_data["display_name"] == "Village Guard"
        assert guard_data["behavior_type"] == "GUARD"
        assert guard_data["is_attackable"] is True
        
        # Check merchant
        merchant_data = visible["entity_2"]
        assert merchant_data["display_name"] == "Bob"
        assert merchant_data["behavior_type"] == "MERCHANT"
        assert merchant_data["is_attackable"] is False
        
        # Check quest giver
        elder_data = visible["entity_3"]
        assert elder_data["display_name"] == "Village Elder"
        assert elder_data["behavior_type"] == "QUEST_GIVER"
        assert elder_data["is_attackable"] is False
    
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
