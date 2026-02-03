"""
Tests for EntityService.

Tests entity definition management and database synchronization.
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from server.src.services.entity_service import EntityService
from server.src.core.entities import EntityBehavior
from server.src.core.humanoids import HumanoidID, HumanoidDefinition
from server.src.core.monsters import MonsterID, MonsterDefinition
from common.src.sprites import AppearanceData, BodyType, SkinTone, HairStyle, HairColor
from server.src.core.skills import SkillType
from server.src.core.items import EquipmentSlot, ItemType


class TestMonsterDefToDict:
    """Tests for EntityService.entity_def_to_dict() with MonsterDefinition"""

    def test_converts_basic_monster_definition(self):
        """Test that basic monster fields are converted correctly."""
        monster_def = MonsterDefinition(
            display_name="Test Monster",
            description="A test monster for unit testing",
            behavior=EntityBehavior.AGGRESSIVE,
        )
        
        result = EntityService.entity_def_to_dict("TEST_MONSTER", monster_def)
        
        assert result["name"] == "TEST_MONSTER"
        assert result["entity_type"] == "monster"
        assert result["display_name"] == "Test Monster"
        assert result["description"] == "A test monster for unit testing"
        assert result["behavior"] == "aggressive"
        assert result["is_attackable"] is True

    def test_converts_behavior_enum_to_value(self):
        """Test that EntityBehavior enum is serialized to its string value."""
        for behavior in [EntityBehavior.AGGRESSIVE, EntityBehavior.PASSIVE, EntityBehavior.NEUTRAL]:
            monster_def = MonsterDefinition(
                display_name="Test",
                description="Test",
                behavior=behavior,
            )
            
            result = EntityService.entity_def_to_dict("TEST", monster_def)
            
            assert result["behavior"] == behavior.value

    def test_serializes_skills_dict(self):
        """Test that skills dict is properly serialized with lowercase keys."""
        monster_def = MonsterDefinition(
            display_name="Skilled Monster",
            description="Has skills",
            behavior=EntityBehavior.AGGRESSIVE,
            skills={
                SkillType.ATTACK: 10,
                SkillType.HITPOINTS: 50,
                SkillType.DEFENCE: 5,
            },
        )
        
        result = EntityService.entity_def_to_dict("SKILLED_MONSTER", monster_def)
        
        assert "skills" in result
        assert result["skills"]["attack"] == 10
        assert result["skills"]["hitpoints"] == 50
        assert result["skills"]["defence"] == 5

    def test_serializes_all_stat_bonuses(self):
        """Test that all combat stat bonuses are included in output."""
        monster_def = MonsterDefinition(
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
        
        result = EntityService.entity_def_to_dict("STRONG_MONSTER", monster_def)
        
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
        monster_def = MonsterDefinition(
            display_name="Big Monster",
            description="A large monster",
            behavior=EntityBehavior.NEUTRAL,
            sprite_sheet_id="big_monster",
            width=2,
            height=3,
            scale=1.5,
        )
        
        result = EntityService.entity_def_to_dict("BIG_MONSTER", monster_def)
        
        assert result["sprite_sheet_id"] == "big_monster"
        assert result["width"] == 2
        assert result["height"] == 3
        assert result["scale"] == 1.5

    def test_handles_combat_and_respawn_properties(self):
        """Test level, XP reward, aggro radius, and respawn time."""
        monster_def = MonsterDefinition(
            display_name="Boss Monster",
            description="A powerful boss",
            behavior=EntityBehavior.AGGRESSIVE,
            level=50,
            xp_reward=1000,
            aggro_radius=10,
            disengage_radius=20,
            respawn_time=300,
        )
        
        result = EntityService.entity_def_to_dict("BOSS_MONSTER", monster_def)
        
        assert result["level"] == 50
        assert result["xp_reward"] == 1000
        assert result["aggro_radius"] == 10
        assert result["disengage_radius"] == 20
        assert result["respawn_time"] == 300

    def test_max_hp_from_hitpoints_skill(self):
        """Test that max_hp is calculated from hitpoints skill."""
        monster_def = MonsterDefinition(
            display_name="HP Monster",
            description="Has HP",
            behavior=EntityBehavior.PASSIVE,
            skills={SkillType.HITPOINTS: 75},
        )
        
        result = EntityService.entity_def_to_dict("HP_MONSTER", monster_def)
        
        assert result["max_hp"] == 75

    def test_default_max_hp_when_no_hitpoints_skill(self):
        """Test default max_hp when hitpoints skill is not defined."""
        monster_def = MonsterDefinition(
            display_name="Default HP Monster",
            description="No HP skill",
            behavior=EntityBehavior.PASSIVE,
            skills={},
        )
        
        result = EntityService.entity_def_to_dict("DEFAULT_HP_MONSTER", monster_def)
        
        assert result["max_hp"] == 10


class TestHumanoidDefToDict:
    """Tests for EntityService.entity_def_to_dict() with HumanoidDefinition"""

    def test_converts_basic_humanoid_definition(self):
        """Test that basic humanoid fields are converted correctly."""
        humanoid_def = HumanoidDefinition(
            display_name="Test NPC",
            description="A test NPC for unit testing",
            behavior=EntityBehavior.MERCHANT,
            is_attackable=False,
        )
        
        result = EntityService.entity_def_to_dict("TEST_NPC", humanoid_def)
        
        assert result["name"] == "TEST_NPC"
        assert result["entity_type"] == "humanoid_npc"
        assert result["display_name"] == "Test NPC"
        assert result["description"] == "A test NPC for unit testing"
        assert result["behavior"] == "merchant"
        assert result["is_attackable"] is False

    def test_humanoid_with_appearance(self):
        """Test that appearance data is serialized."""
        appearance = AppearanceData(
            body_type=BodyType.MALE,
            skin_tone=SkinTone.OLIVE,
            hair_style=HairStyle.LONG,
            hair_color=HairColor.RED,
        )
        humanoid_def = HumanoidDefinition(
            display_name="Styled NPC",
            description="Has custom appearance",
            behavior=EntityBehavior.QUEST_GIVER,
            appearance=appearance,
        )
        
        result = EntityService.entity_def_to_dict("STYLED_NPC", humanoid_def)
        
        # Verify appearance is serialized with enum values
        assert result["appearance"]["body_type"] == "male"
        assert result["appearance"]["skin_tone"] == "olive"
        assert result["appearance"]["hair_style"] == "long"
        assert result["appearance"]["hair_color"] == "red"

    def test_humanoid_with_equipment(self):
        """Test that equipped items are serialized."""
        humanoid_def = HumanoidDefinition(
            display_name="Armed Guard",
            description="Has equipment",
            behavior=EntityBehavior.GUARD,
            equipped_items={
                EquipmentSlot.WEAPON: ItemType.IRON_SHORTSWORD,
                EquipmentSlot.BODY: ItemType.BRONZE_PLATEBODY,
            },
        )
        
        result = EntityService.entity_def_to_dict("ARMED_GUARD", humanoid_def)
        
        assert result["equipped_items"]["weapon"] == "IRON_SHORTSWORD"
        assert result["equipped_items"]["body"] == "BRONZE_PLATEBODY"

    def test_humanoid_with_dialogue(self):
        """Test that dialogue is serialized."""
        humanoid_def = HumanoidDefinition(
            display_name="Talkative NPC",
            description="Has dialogue",
            behavior=EntityBehavior.QUEST_GIVER,
            dialogue=["Hello, traveler!", "I have a quest for you."],
        )
        
        result = EntityService.entity_def_to_dict("TALKATIVE_NPC", humanoid_def)
        
        assert result["dialogue"] == ["Hello, traveler!", "I have a quest for you."]

    def test_humanoid_with_shop(self):
        """Test that shop_id is serialized."""
        humanoid_def = HumanoidDefinition(
            display_name="Shopkeeper",
            description="Runs a shop",
            behavior=EntityBehavior.MERCHANT,
            shop_id="weapon_shop",
        )
        
        result = EntityService.entity_def_to_dict("SHOPKEEPER", humanoid_def)
        
        assert result["shop_id"] == "weapon_shop"


class TestSyncEntitiesToDb:
    """Tests for EntityService.sync_entities_to_db()"""

    @pytest.mark.asyncio
    async def test_sync_entities_calls_gsm(self, game_state_managers):
        """Test that sync_entities_to_db calls GSM's sync method."""
        with patch.object(gsm, 'sync_entities_to_database', new_callable=AsyncMock) as mock_sync:
            with patch('server.src.services.entity_service.get_game_state_manager', return_value=gsm):
                await EntityService.sync_entities_to_db()
                
                mock_sync.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_entities_to_db_integration(self, game_state_managers, session):
        """Test full sync of entities to database."""
        with patch('server.src.services.entity_service.get_game_state_manager', return_value=gsm):
            await EntityService.sync_entities_to_db()
        
        # Verify at least one entity was synced by checking the database
        from server.src.models.entity import Entity
        from sqlalchemy import select
        
        result = await session.execute(select(Entity).limit(5))
        entities = result.scalars().all()
        
        # Should have synced entities from HumanoidID and MonsterID enums
        assert len(entities) > 0


class TestEntityServiceWithRealEntities:
    """Tests using real HumanoidID and MonsterID definitions."""

    def test_goblin_monster_conversion(self):
        """Test converting the GOBLIN monster definition."""
        goblin_def = MonsterID.GOBLIN.value
        
        result = EntityService.entity_def_to_dict("GOBLIN", goblin_def)
        
        assert result["name"] == "GOBLIN"
        assert result["entity_type"] == "monster"
        assert result["display_name"] == "Goblin"
        assert result["behavior"] == "aggressive"
        assert "skills" in result

    def test_village_guard_humanoid_conversion(self):
        """Test converting the VILLAGE_GUARD humanoid definition."""
        guard_def = HumanoidID.VILLAGE_GUARD.value
        
        result = EntityService.entity_def_to_dict("VILLAGE_GUARD", guard_def)
        
        assert result["name"] == "VILLAGE_GUARD"
        assert result["entity_type"] == "humanoid_npc"
        assert result["display_name"] == "Village Guard"
        assert result["behavior"] == "guard"
        assert result["appearance"] is not None
        assert result["equipped_items"] is not None

    def test_all_monster_ids_can_be_converted(self):
        """Test that all MonsterID enums can be converted to dict."""
        for monster_id in MonsterID:
            monster_def = monster_id.value
            
            result = EntityService.entity_def_to_dict(monster_id.name, monster_def)
            
            assert result["name"] == monster_id.name
            assert result["entity_type"] == "monster"
            assert "display_name" in result
            assert "behavior" in result
            assert "skills" in result

    def test_all_humanoid_ids_can_be_converted(self):
        """Test that all HumanoidID enums can be converted to dict."""
        for humanoid_id in HumanoidID:
            humanoid_def = humanoid_id.value
            
            result = EntityService.entity_def_to_dict(humanoid_id.name, humanoid_def)
            
            assert result["name"] == humanoid_id.name
            assert result["entity_type"] == "humanoid_npc"
            assert "display_name" in result
            assert "behavior" in result
            assert "skills" in result
