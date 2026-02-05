"""
Integration tests for CombatService.

Tests real combat interactions using game state managers:
- Player combat stats retrieval
- Equipment bonus calculations
- Full attack flows
- Entity combat
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import patch

from server.src.services.combat_service import CombatService, CombatStats, CombatResult
from server.src.services.game_state import (
    get_player_state_manager,
    get_skills_manager,
    get_equipment_manager,
    get_entity_manager,
    get_reference_data_manager,
)
from server.src.core.skills import SkillType, xp_to_next_level, get_skill_xp_multiplier
from common.src.protocol import CombatTargetType


@pytest.mark.asyncio
class TestCombatServiceIntegration:
    """Test combat flow with real managers"""

    async def test_get_player_combat_stats(self, game_state_managers, create_test_player):
        """Test fetching player combat stats from managers"""
        player = await create_test_player("combat_stats_test", "password123")
        skills_mgr = get_skills_manager()

        await skills_mgr.set_skill(player.id, SkillType.ATTACK, 20, xp_to_next_level(20, get_skill_xp_multiplier(SkillType.ATTACK)))
        await skills_mgr.set_skill(player.id, SkillType.STRENGTH, 25, xp_to_next_level(25, get_skill_xp_multiplier(SkillType.STRENGTH)))
        await skills_mgr.set_skill(player.id, SkillType.DEFENCE, 15, xp_to_next_level(15, get_skill_xp_multiplier(SkillType.DEFENCE)))

        player_state_mgr = get_player_state_manager()
        await player_state_mgr.set_player_hp(player.id, current_hp=30, max_hp=30)

        stats = await CombatService.get_player_combat_stats(player.id)

        assert stats is not None
        assert stats.attack_level == 20
        assert stats.strength_level == 25
        assert stats.defence_level == 15
        assert stats.current_hp == 30
        assert stats.max_hp == 30
        assert stats.attack_bonus == 0
        assert stats.strength_bonus == 0
        assert stats.defence_bonus == 0
        assert stats.name == "combat_stats_test"

    async def test_get_player_combat_stats_with_equipment(
        self, game_state_managers, create_test_player
    ):
        """Test fetching player combat stats with equipment bonuses"""
        player = await create_test_player("equip_stats_test", "password123", current_hp=30)
        skills_mgr = get_skills_manager()
        await skills_mgr.set_skill(player.id, SkillType.ATTACK, 20, xp_to_next_level(20, get_skill_xp_multiplier(SkillType.ATTACK)))
        await skills_mgr.set_skill(player.id, SkillType.STRENGTH, 25, xp_to_next_level(25, get_skill_xp_multiplier(SkillType.STRENGTH)))
        await skills_mgr.set_skill(player.id, SkillType.DEFENCE, 15, xp_to_next_level(15, get_skill_xp_multiplier(SkillType.DEFENCE)))
        
        # Set player HP via state manager (required for combat stats)
        player_state_mgr = get_player_state_manager()
        await player_state_mgr.set_player_hp(player.id, current_hp=30, max_hp=30)

        equip_mgr = get_equipment_manager()
        ref_mgr = get_reference_data_manager()
        wooden_sword = ref_mgr.get_cached_item_by_name("WOODEN_SWORD")
        bronze_chestplate = ref_mgr.get_cached_item_by_name("BRONZE_CHESTPLATE")
        wooden_sword_id = wooden_sword["id"] if wooden_sword else 1
        bronze_chestplate_id = bronze_chestplate["id"] if bronze_chestplate else 2
        await equip_mgr.set_equipment_slot(player.id, "weapon", wooden_sword_id, 1, 1.0)
        await equip_mgr.set_equipment_slot(player.id, "chest", bronze_chestplate_id, 1, 1.0)

        stats = await CombatService.get_player_combat_stats(player.id)

        assert stats is not None
        assert stats.attack_bonus > 0
        assert stats.strength_bonus > 0
        assert stats.defence_bonus == 0  # Bronze chestplate has no defence bonus in current data

    async def test_get_player_combat_stats_not_found(self, game_state_managers):
        """Test fetching stats for non-existent player returns None"""
        stats = await CombatService.get_player_combat_stats(99999)
        assert stats is None

    async def test_perform_attack_player_vs_entity_success(
        self, game_state_managers, create_test_player
    ):
        """Test successful player attack on entity"""
        player = await create_test_player("attack_test", "password123", current_hp=50)
        skills_mgr = get_skills_manager()
        await skills_mgr.set_skill(player.id, SkillType.ATTACK, 50, xp_to_next_level(50, get_skill_xp_multiplier(SkillType.ATTACK)))
        await skills_mgr.set_skill(player.id, SkillType.STRENGTH, 50, xp_to_next_level(50, get_skill_xp_multiplier(SkillType.STRENGTH)))
        await skills_mgr.set_skill(player.id, SkillType.DEFENCE, 40, xp_to_next_level(40, get_skill_xp_multiplier(SkillType.DEFENCE)))
        
        # Set player HP via state manager (required for combat stats)
        player_state_mgr = get_player_state_manager()
        await player_state_mgr.set_player_hp(player.id, current_hp=50, max_hp=50)

        entity_mgr = get_entity_manager()
        ref_mgr = get_reference_data_manager()
        goblin_entity_id = await ref_mgr.get_entity_id_by_name("GOBLIN")
        assert goblin_entity_id is not None, "GOBLIN entity not found in reference data"
        entity_id = await entity_mgr.spawn_entity_instance(
            entity_id=goblin_entity_id,
            map_id="samplemap",
            x=10,
            y=10,
            current_hp=10,
            max_hp=10,
        )

        with patch("server.src.services.combat_service.random.random", return_value=0.1):
            with patch("server.src.services.combat_service.random.randint", return_value=5):
                result = await CombatService.perform_attack(
                    attacker_type=CombatTargetType.PLAYER,
                    attacker_id=player.id,
                    defender_type=CombatTargetType.ENTITY,
                    defender_id=entity_id,
                )

                assert result.success
                assert result.hit
                assert result.damage == 5
                assert result.defender_hp == 5
                assert not result.defender_died

                entity_data = await entity_mgr.get_entity_instance(entity_id)
                assert entity_data["current_hp"] == 5

    async def test_perform_attack_entity_dies(
        self, game_state_managers, create_test_player
    ):
        """Test entity death from player attack"""
        player = await create_test_player("kill_test", "password123", current_hp=50)
        skills_mgr = get_skills_manager()
        await skills_mgr.set_skill(player.id, SkillType.ATTACK, 50, xp_to_next_level(50, get_skill_xp_multiplier(SkillType.ATTACK)))
        await skills_mgr.set_skill(player.id, SkillType.STRENGTH, 50, xp_to_next_level(50, get_skill_xp_multiplier(SkillType.STRENGTH)))
        
        # Set player HP via state manager (required for combat stats)
        player_state_mgr = get_player_state_manager()
        await player_state_mgr.set_player_hp(player.id, current_hp=50, max_hp=50)

        entity_mgr = get_entity_manager()
        ref_mgr = get_reference_data_manager()
        goblin_entity_id = await ref_mgr.get_entity_id_by_name("GOBLIN")
        assert goblin_entity_id is not None, "GOBLIN entity not found in reference data"
        entity_id = await entity_mgr.spawn_entity_instance(
            entity_id=goblin_entity_id,
            map_id="samplemap",
            x=10,
            y=10,
            current_hp=3,
            max_hp=10,
        )

        with patch("server.src.services.combat_service.random.random", return_value=0.1):
            with patch("server.src.services.combat_service.random.randint", return_value=5):
                result = await CombatService.perform_attack(
                    attacker_type=CombatTargetType.PLAYER,
                    attacker_id=player.id,
                    defender_type=CombatTargetType.ENTITY,
                    defender_id=entity_id,
                )

                assert result.success
                assert result.hit
                assert result.damage == 5
                assert result.defender_hp == 0
                assert result.defender_died
                assert "died" in result.message.lower()

    async def test_perform_attack_target_already_dead(
        self, game_state_managers, create_test_player
    ):
        """Test attack on already dead target fails"""
        player = await create_test_player("dead_target_test", "password123", current_hp=50)
        skills_mgr = get_skills_manager()
        await skills_mgr.set_skill(player.id, SkillType.ATTACK, 50, xp_to_next_level(50, get_skill_xp_multiplier(SkillType.ATTACK)))
        await skills_mgr.set_skill(player.id, SkillType.STRENGTH, 50, xp_to_next_level(50, get_skill_xp_multiplier(SkillType.STRENGTH)))
        
        # Set player HP via state manager (required for combat stats)
        player_state_mgr = get_player_state_manager()
        await player_state_mgr.set_player_hp(player.id, current_hp=50, max_hp=50)

        entity_mgr = get_entity_manager()
        ref_mgr = get_reference_data_manager()
        goblin_entity_id = await ref_mgr.get_entity_id_by_name("GOBLIN")
        assert goblin_entity_id is not None, "GOBLIN entity not found in reference data"
        entity_id = await entity_mgr.spawn_entity_instance(
            entity_id=goblin_entity_id,
            map_id="samplemap",
            x=10,
            y=10,
            current_hp=0,
            max_hp=10,
        )

        result = await CombatService.perform_attack(
            attacker_type=CombatTargetType.PLAYER,
            attacker_id=player.id,
            defender_type=CombatTargetType.ENTITY,
            defender_id=entity_id,
        )

        assert not result.success
        assert result.error == "Target is already dead"
        assert not result.hit
        assert result.damage == 0

    async def test_perform_attack_invalid_attacker(self, game_state_managers):
        """Test attack with invalid attacker fails"""
        entity_mgr = get_entity_manager()
        ref_mgr = get_reference_data_manager()
        goblin_entity_id = await ref_mgr.get_entity_id_by_name("GOBLIN")
        assert goblin_entity_id is not None, "GOBLIN entity not found in reference data"
        entity_id = await entity_mgr.spawn_entity_instance(
            entity_id=goblin_entity_id,
            map_id="samplemap",
            x=10,
            y=10,
            current_hp=10,
            max_hp=10,
        )

        result = await CombatService.perform_attack(
            attacker_type=CombatTargetType.PLAYER,
            attacker_id=99999,
            defender_type=CombatTargetType.ENTITY,
            defender_id=entity_id,
        )

        assert not result.success
        assert result.error == "Attacker not found"

    async def test_perform_attack_invalid_defender(
        self, game_state_managers, create_test_player
    ):
        """Test attack with invalid defender fails"""
        player = await create_test_player("invalid_defender_test", "password123", current_hp=50)
        skills_mgr = get_skills_manager()
        await skills_mgr.set_skill(player.id, SkillType.ATTACK, 50, xp_to_next_level(50, get_skill_xp_multiplier(SkillType.ATTACK)))
        await skills_mgr.set_skill(player.id, SkillType.STRENGTH, 50, xp_to_next_level(50, get_skill_xp_multiplier(SkillType.STRENGTH)))
        
        # Set player HP via state manager (required for combat stats)
        player_state_mgr = get_player_state_manager()
        await player_state_mgr.set_player_hp(player.id, current_hp=50, max_hp=50)

        result = await CombatService.perform_attack(
            attacker_type=CombatTargetType.PLAYER,
            attacker_id=player.id,
            defender_type=CombatTargetType.ENTITY,
            defender_id=99999,
        )

        assert not result.success
        assert result.error == "Defender not found"

    async def test_combat_xp_rewards(self, game_state_managers, create_test_player):
        """Test XP rewards after successful combat"""
        player = await create_test_player("xp_test", "password123", current_hp=50)
        skills_mgr = get_skills_manager()
        await skills_mgr.set_skill(player.id, SkillType.ATTACK, 50, xp_to_next_level(50, get_skill_xp_multiplier(SkillType.ATTACK)))
        await skills_mgr.set_skill(player.id, SkillType.STRENGTH, 50, xp_to_next_level(50, get_skill_xp_multiplier(SkillType.STRENGTH)))
        await skills_mgr.set_skill(player.id, SkillType.HITPOINTS, 50, xp_to_next_level(50, get_skill_xp_multiplier(SkillType.HITPOINTS)))
        
        # Set player HP via state manager (required for combat stats)
        player_state_mgr = get_player_state_manager()
        await player_state_mgr.set_player_hp(player.id, current_hp=50, max_hp=50)

        initial_attack_skill = await skills_mgr.get_skill(player.id, "attack")
        initial_strength_skill = await skills_mgr.get_skill(player.id, "strength")
        initial_hp_skill = await skills_mgr.get_skill(player.id, "hitpoints")
        initial_attack_xp = initial_attack_skill.get("experience", 0) if initial_attack_skill else 0
        initial_strength_xp = initial_strength_skill.get("experience", 0) if initial_strength_skill else 0
        initial_hp_xp = initial_hp_skill.get("experience", 0) if initial_hp_skill else 0

        entity_mgr = get_entity_manager()
        ref_mgr = get_reference_data_manager()
        goblin_entity_id = await ref_mgr.get_entity_id_by_name("GOBLIN")
        assert goblin_entity_id is not None, "GOBLIN entity not found in reference data"
        entity_id = await entity_mgr.spawn_entity_instance(
            entity_id=goblin_entity_id,
            map_id="samplemap",
            x=10,
            y=10,
            current_hp=10,
            max_hp=10,
        )

        with patch("server.src.services.combat_service.random.random", return_value=0.1):
            with patch("server.src.services.combat_service.random.randint", return_value=5):
                result = await CombatService.perform_attack(
                    attacker_type=CombatTargetType.PLAYER,
                    attacker_id=player.id,
                    defender_type=CombatTargetType.ENTITY,
                    defender_id=entity_id,
                )

                assert result.success
                assert len(result.xp_gained) > 0

                final_attack_skill = await skills_mgr.get_skill(player.id, "attack")
                final_strength_skill = await skills_mgr.get_skill(player.id, "strength")
                final_hp_skill = await skills_mgr.get_skill(player.id, "hitpoints")
                final_attack_xp = final_attack_skill.get("experience", 0) if final_attack_skill else 0
                final_strength_xp = final_strength_skill.get("experience", 0) if final_strength_skill else 0
                final_hp_xp = final_hp_skill.get("experience", 0) if final_hp_skill else 0

                assert final_attack_xp > initial_attack_xp
                assert final_strength_xp > initial_strength_xp
                assert final_hp_xp > initial_hp_xp

    async def test_perform_attack_miss_no_damage(
        self, game_state_managers, create_test_player
    ):
        """Test that missed attacks deal no damage"""
        player = await create_test_player("miss_test", "password123", current_hp=50)
        skills_mgr = get_skills_manager()
        await skills_mgr.set_skill(player.id, SkillType.ATTACK, 50, xp_to_next_level(50, get_skill_xp_multiplier(SkillType.ATTACK)))
        await skills_mgr.set_skill(player.id, SkillType.STRENGTH, 50, xp_to_next_level(50, get_skill_xp_multiplier(SkillType.STRENGTH)))
        
        # Set player HP via state manager (required for combat stats)
        player_state_mgr = get_player_state_manager()
        await player_state_mgr.set_player_hp(player.id, current_hp=50, max_hp=50)

        entity_mgr = get_entity_manager()
        ref_mgr = get_reference_data_manager()
        goblin_entity_id = await ref_mgr.get_entity_id_by_name("GOBLIN")
        assert goblin_entity_id is not None, "GOBLIN entity not found in reference data"
        entity_id = await entity_mgr.spawn_entity_instance(
            entity_id=goblin_entity_id,
            map_id="samplemap",
            x=10,
            y=10,
            current_hp=10,
            max_hp=10,
        )

        with patch("server.src.services.combat_service.random.random", return_value=0.99):
            result = await CombatService.perform_attack(
                attacker_type=CombatTargetType.PLAYER,
                attacker_id=player.id,
                defender_type=CombatTargetType.ENTITY,
                defender_id=entity_id,
            )

            assert result.success
            assert not result.hit
            assert result.damage == 0
            assert result.defender_hp == 10

            entity_data = await entity_mgr.get_entity_instance(entity_id)
            assert entity_data["current_hp"] == 10
