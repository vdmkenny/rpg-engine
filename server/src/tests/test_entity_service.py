"""
Tests for EntityService.

Tests entity definition management and database synchronization.
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from server.src.services.entity_service import EntityService
from server.src.services.game_state_manager import GameStateManager
from server.src.core.entities import EntityID, EntityDefinition, EntityBehavior
from server.src.core.skills import SkillType


class TestEntityDefToDict:
    """Tests for EntityService._entity_def_to_dict()"""

    def test_converts_basic_entity_definition(self):
        """Test that basic entity fields are converted correctly."""
        entity_def = EntityDefinition(
            display_name="Test Monster",
            description="A test monster for unit testing",
            behavior=EntityBehavior.AGGRESSIVE,
        )
        
        result = EntityService._entity_def_to_dict("TEST_MONSTER", entity_def)
        
        assert result["name"] == "TEST_MONSTER"
        assert result["display_name"] == "Test Monster"
        assert result["description"] == "A test monster for unit testing"
        assert result["behavior"] == "aggressive"
        assert result["is_attackable"] is True

    def test_converts_behavior_enum_to_value(self):
        """Test that EntityBehavior enum is serialized to its string value."""
        for behavior in EntityBehavior:
            entity_def = EntityDefinition(
                display_name="Test",
                description="Test",
                behavior=behavior,
            )
            
            result = EntityService._entity_def_to_dict("TEST", entity_def)
            
            assert result["behavior"] == behavior.value

    def test_serializes_skills_dict(self):
        """Test that skills dict is properly serialized with lowercase keys."""
        entity_def = EntityDefinition(
            display_name="Skilled Monster",
            description="Has skills",
            behavior=EntityBehavior.AGGRESSIVE,
            skills={
                SkillType.ATTACK: 10,
                SkillType.HITPOINTS: 50,
                SkillType.DEFENCE: 5,
            },
        )
        
        result = EntityService._entity_def_to_dict("SKILLED_MONSTER", entity_def)
        
        assert "skills" in result
        assert result["skills"]["attack"] == 10
        assert result["skills"]["hitpoints"] == 50
        assert result["skills"]["defence"] == 5

    def test_serializes_all_stat_bonuses(self):
        """Test that all combat stat bonuses are included in output."""
        entity_def = EntityDefinition(
            display_name="Strong Monster",
            description="Has stat bonuses",
            behavior=EntityBehavior.AGGRESSIVE,
            attack_bonus=10,
            strength_bonus=15,
            ranged_attack_bonus=5,
            ranged_strength_bonus=8,
            magic_attack_bonus=3,
            magic_damage_bonus=7,
            physical_defence_bonus=20,
            magic_defence_bonus=12,
            speed_bonus=2,
        )
        
        result = EntityService._entity_def_to_dict("STRONG_MONSTER", entity_def)
        
        assert result["attack_bonus"] == 10
        assert result["strength_bonus"] == 15
        assert result["ranged_attack_bonus"] == 5
        assert result["ranged_strength_bonus"] == 8
        assert result["magic_attack_bonus"] == 3
        assert result["magic_damage_bonus"] == 7
        assert result["physical_defence_bonus"] == 20
        assert result["magic_defence_bonus"] == 12
        assert result["speed_bonus"] == 2

    def test_handles_visual_properties(self):
        """Test that visual properties are included."""
        entity_def = EntityDefinition(
            display_name="Big Monster",
            description="A large monster",
            behavior=EntityBehavior.NEUTRAL,
            sprite_name="big_monster",
            width=2,
            height=3,
            scale=1.5,
        )
        
        result = EntityService._entity_def_to_dict("BIG_MONSTER", entity_def)
        
        assert result["sprite_name"] == "big_monster"
        assert result["width"] == 2
        assert result["height"] == 3
        assert result["scale"] == 1.5

    def test_handles_optional_fields(self):
        """Test that optional fields (dialogue, shop_id) are included."""
        entity_def = EntityDefinition(
            display_name="Merchant NPC",
            description="Sells items",
            behavior=EntityBehavior.MERCHANT,
            is_attackable=False,
            dialogue=["Hello, traveler!", "Would you like to trade?"],
            shop_id="general_store",
        )
        
        result = EntityService._entity_def_to_dict("MERCHANT_NPC", entity_def)
        
        assert result["is_attackable"] is False
        assert result["dialogue"] == ["Hello, traveler!", "Would you like to trade?"]
        assert result["shop_id"] == "general_store"

    def test_handles_combat_and_respawn_properties(self):
        """Test level, XP reward, aggro radius, and respawn time."""
        entity_def = EntityDefinition(
            display_name="Boss Monster",
            description="A powerful boss",
            behavior=EntityBehavior.AGGRESSIVE,
            level=50,
            xp_reward=1000,
            aggro_radius=10,
            disengage_radius=20,
            respawn_time=300,
        )
        
        result = EntityService._entity_def_to_dict("BOSS_MONSTER", entity_def)
        
        assert result["level"] == 50
        assert result["xp_reward"] == 1000
        assert result["aggro_radius"] == 10
        assert result["disengage_radius"] == 20
        assert result["respawn_time"] == 300

    def test_max_hp_from_hitpoints_skill(self):
        """Test that max_hp is calculated from hitpoints skill."""
        entity_def = EntityDefinition(
            display_name="HP Monster",
            description="Has HP",
            behavior=EntityBehavior.PASSIVE,
            skills={SkillType.HITPOINTS: 75},
        )
        
        result = EntityService._entity_def_to_dict("HP_MONSTER", entity_def)
        
        # max_hp is a property, so it should be included
        assert result["max_hp"] == 75

    def test_default_max_hp_when_no_hitpoints_skill(self):
        """Test default max_hp when hitpoints skill is not defined."""
        entity_def = EntityDefinition(
            display_name="Default HP Monster",
            description="No HP skill",
            behavior=EntityBehavior.PASSIVE,
            skills={},
        )
        
        result = EntityService._entity_def_to_dict("DEFAULT_HP_MONSTER", entity_def)
        
        # Default is 10 when hitpoints skill not defined
        assert result["max_hp"] == 10


class TestSyncEntitiesToDb:
    """Tests for EntityService.sync_entities_to_db()"""

    @pytest.mark.asyncio
    async def test_sync_entities_calls_gsm(self, gsm: GameStateManager):
        """Test that sync_entities_to_db calls GSM's sync method."""
        with patch.object(gsm, 'sync_entities_to_database', new_callable=AsyncMock) as mock_sync:
            # Patch get_game_state_manager to return our test GSM
            with patch('server.src.services.entity_service.get_game_state_manager', return_value=gsm):
                await EntityService.sync_entities_to_db()
                
                mock_sync.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_entities_to_db_integration(self, gsm: GameStateManager, session):
        """Test full sync of entities to database."""
        # This is an integration test that verifies entities are synced
        with patch('server.src.services.entity_service.get_game_state_manager', return_value=gsm):
            await EntityService.sync_entities_to_db()
        
        # Verify at least one entity was synced by checking the database
        from server.src.models.entity import Entity
        from sqlalchemy import select
        
        result = await session.execute(select(Entity).limit(5))
        entities = result.scalars().all()
        
        # Should have synced entities from EntityID enum
        assert len(entities) > 0


class TestEntityServiceWithRealEntities:
    """Tests using real EntityID definitions."""

    def test_goblin_entity_conversion(self):
        """Test converting the GOBLIN entity definition."""
        goblin_def = EntityID.GOBLIN.value
        
        result = EntityService._entity_def_to_dict("GOBLIN", goblin_def)
        
        assert result["name"] == "GOBLIN"
        assert result["display_name"] == "Goblin"
        assert result["behavior"] == "aggressive"
        assert "skills" in result

    def test_all_entity_ids_can_be_converted(self):
        """Test that all EntityID enums can be converted to dict."""
        for entity_id in EntityID:
            entity_def = entity_id.value
            
            # Should not raise any exceptions
            result = EntityService._entity_def_to_dict(entity_id.name, entity_def)
            
            assert result["name"] == entity_id.name
            assert "display_name" in result
            assert "behavior" in result
            assert "skills" in result
