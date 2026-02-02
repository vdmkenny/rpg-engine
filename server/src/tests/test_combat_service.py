"""
Unit tests for CombatService.

Tests RuneScape-style combat mechanics including:
- Hit chance calculations
- Max hit calculations
- Damage rolls
- XP calculations
- Full combat flow
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from server.src.services.combat_service import CombatService, CombatStats, CombatResult
from server.src.core.skills import SkillType
from common.src.protocol import CombatTargetType


class TestCombatCalculations:
    """Test combat calculation formulas"""
    
    def test_calculate_hit_chance_equal_stats(self):
        """Test hit chance with equal stats (should be ~50%)"""
        attacker = CombatStats(
            attack_level=10,
            strength_level=10,
            attack_bonus=0,
            strength_bonus=0,
            defence_level=10,
            defence_bonus=0,
            current_hp=10,
            max_hp=10,
            name="Attacker"
        )
        defender = CombatStats(
            attack_level=10,
            strength_level=10,
            attack_bonus=0,
            strength_bonus=0,
            defence_level=10,
            defence_bonus=0,
            current_hp=10,
            max_hp=10,
            name="Defender"
        )
        
        hit_chance = CombatService.calculate_hit_chance(attacker, defender)
        assert 0.45 <= hit_chance <= 0.55, f"Expected ~50% hit chance, got {hit_chance}"
    
    def test_calculate_hit_chance_high_attack(self):
        """Test hit chance with high attack vs low defence (should be high)"""
        attacker = CombatStats(
            attack_level=50,
            strength_level=50,
            attack_bonus=50,
            strength_bonus=50,
            defence_level=10,
            defence_bonus=0,
            current_hp=10,
            max_hp=10,
            name="Attacker"
        )
        defender = CombatStats(
            attack_level=10,
            strength_level=10,
            attack_bonus=0,
            strength_bonus=0,
            defence_level=1,
            defence_bonus=0,
            current_hp=10,
            max_hp=10,
            name="Defender"
        )
        
        hit_chance = CombatService.calculate_hit_chance(attacker, defender)
        assert hit_chance == 0.95, f"Expected max hit chance (0.95), got {hit_chance}"
    
    def test_calculate_hit_chance_high_defence(self):
        """Test hit chance with low attack vs high defence (should be low)"""
        attacker = CombatStats(
            attack_level=1,
            strength_level=1,
            attack_bonus=0,
            strength_bonus=0,
            defence_level=1,
            defence_bonus=0,
            current_hp=10,
            max_hp=10,
            name="Attacker"
        )
        defender = CombatStats(
            attack_level=10,
            strength_level=10,
            attack_bonus=0,
            strength_bonus=0,
            defence_level=50,
            defence_bonus=50,
            current_hp=10,
            max_hp=10,
            name="Defender"
        )
        
        hit_chance = CombatService.calculate_hit_chance(attacker, defender)
        assert hit_chance == 0.05, f"Expected min hit chance (0.05), got {hit_chance}"
    
    def test_calculate_max_hit_no_bonuses(self):
        """Test max hit calculation with no bonuses"""
        attacker = CombatStats(
            attack_level=10,
            strength_level=10,
            attack_bonus=0,
            strength_bonus=0,
            defence_level=10,
            defence_bonus=0,
            current_hp=10,
            max_hp=10,
            name="Attacker"
        )
        
        max_hit = CombatService.calculate_max_hit(attacker)
        # Formula: (10 * (0 + 64) + 320) / 640 = (640 + 320) / 640 = 1.5 = floor(1.5) = 1
        assert max_hit == 1, f"Expected max hit of 1, got {max_hit}"
    
    def test_calculate_max_hit_with_bonuses(self):
        """Test max hit calculation with strength bonuses"""
        attacker = CombatStats(
            attack_level=50,
            strength_level=50,
            attack_bonus=50,
            strength_bonus=50,
            defence_level=10,
            defence_bonus=0,
            current_hp=10,
            max_hp=10,
            name="Attacker"
        )
        
        max_hit = CombatService.calculate_max_hit(attacker)
        # Formula: (50 * (50 + 64) + 320) / 640 = (50 * 114 + 320) / 640 = (5700 + 320) / 640 = 9.40 = floor(9.40) = 9
        assert max_hit == 9, f"Expected max hit of 9, got {max_hit}"
    
    def test_calculate_max_hit_minimum(self):
        """Test max hit has minimum of 1"""
        attacker = CombatStats(
            attack_level=1,
            strength_level=1,
            attack_bonus=0,
            strength_bonus=0,
            defence_level=1,
            defence_bonus=0,
            current_hp=10,
            max_hp=10,
            name="Attacker"
        )
        
        max_hit = CombatService.calculate_max_hit(attacker)
        # Even with level 1, should always be at least 1 damage
        assert max_hit >= 1, f"Expected minimum max hit of 1, got {max_hit}"
    
    def test_roll_damage_on_miss(self):
        """Test damage is 0 on miss"""
        attacker = CombatStats(
            attack_level=10,
            strength_level=10,
            attack_bonus=0,
            strength_bonus=0,
            defence_level=10,
            defence_bonus=0,
            current_hp=10,
            max_hp=10,
            name="Attacker"
        )
        
        damage = CombatService.roll_damage(attacker, did_hit=False)
        assert damage == 0, f"Expected 0 damage on miss, got {damage}"
    
    def test_roll_damage_on_hit(self):
        """Test damage is between 0 and max_hit on hit"""
        attacker = CombatStats(
            attack_level=50,
            strength_level=50,
            attack_bonus=50,
            strength_bonus=50,
            defence_level=10,
            defence_bonus=0,
            current_hp=10,
            max_hp=10,
            name="Attacker"
        )
        
        max_hit = CombatService.calculate_max_hit(attacker)
        
        # Roll damage 100 times and ensure it's always in range
        for _ in range(100):
            damage = CombatService.roll_damage(attacker, did_hit=True)
            assert 0 <= damage <= max_hit, f"Damage {damage} outside range [0, {max_hit}]"
    
    def test_calculate_combat_xp_no_damage(self):
        """Test XP calculation with no damage"""
        xp_rewards = CombatService.calculate_combat_xp(damage_dealt=0, defender_died=False)
        assert len(xp_rewards) == 0, "Expected no XP for 0 damage"
    
    def test_calculate_combat_xp_with_damage(self):
        """Test XP calculation with damage dealt"""
        damage = 5
        xp_rewards = CombatService.calculate_combat_xp(damage_dealt=damage, defender_died=False)
        
        assert SkillType.ATTACK in xp_rewards
        assert SkillType.STRENGTH in xp_rewards
        assert SkillType.HITPOINTS in xp_rewards
        
        # Attack and Strength get 4 XP per damage
        assert xp_rewards[SkillType.ATTACK] == damage * 4
        assert xp_rewards[SkillType.STRENGTH] == damage * 4
        
        # Hitpoints gets 4/3 XP per damage
        assert xp_rewards[SkillType.HITPOINTS] == int(damage * 4 / 3)
    
    def test_calculate_defensive_xp_on_miss(self):
        """Test defensive XP when attack misses (player dodges)"""
        xp_rewards = CombatService.calculate_defensive_xp(did_hit=False, damage_taken=0)
        
        assert SkillType.DEFENCE in xp_rewards
        assert xp_rewards[SkillType.DEFENCE] == 2
        # Should not get hitpoints XP on a miss
        assert SkillType.HITPOINTS not in xp_rewards
    
    def test_calculate_defensive_xp_on_hit(self):
        """Test defensive XP when attack hits (player takes damage)"""
        damage = 6
        xp_rewards = CombatService.calculate_defensive_xp(did_hit=True, damage_taken=damage)
        
        # Should get hitpoints XP for enduring damage
        assert SkillType.HITPOINTS in xp_rewards
        assert xp_rewards[SkillType.HITPOINTS] == damage // 3  # 6 // 3 = 2
        # Should not get defence XP when hit
        assert SkillType.DEFENCE not in xp_rewards
    
    def test_calculate_defensive_xp_minimum_hp_xp(self):
        """Test defensive XP has minimum of 1 HP XP on hit"""
        damage = 1  # Low damage
        xp_rewards = CombatService.calculate_defensive_xp(did_hit=True, damage_taken=damage)
        
        # 1 // 3 = 0, but should be at least 1
        assert SkillType.HITPOINTS in xp_rewards
        assert xp_rewards[SkillType.HITPOINTS] == 1
    
    def test_calculate_defensive_xp_zero_damage_hit(self):
        """Test defensive XP when hit but zero damage (e.g., 0 hit)"""
        xp_rewards = CombatService.calculate_defensive_xp(did_hit=True, damage_taken=0)
        
        # No XP for zero damage hits
        assert len(xp_rewards) == 0


@pytest.mark.asyncio
class TestCombatService:
    """Test full combat flow with mocked GSM"""
    
    async def test_get_player_combat_stats(self):
        """Test fetching player combat stats from GSM"""
        player_id = 1
        
        # Mock GSM methods
        with patch('server.src.services.combat_service.get_game_state_manager') as mock_gsm_getter:
            mock_gsm = MagicMock()
            mock_gsm_getter.return_value = mock_gsm
            
            # Mock skill data (async method)
            mock_gsm.get_all_skills = AsyncMock(return_value={
                "attack": {"level": 20},
                "strength": {"level": 25},
                "defence": {"level": 15},
                "hitpoints": {"level": 30}
            })
            
            # Mock HP data (async method)
            mock_gsm.get_player_hp = AsyncMock(return_value={
                "current_hp": 30,
                "max_hp": 30
            })
            
            # Mock equipment (async method)
            mock_gsm.get_equipment = AsyncMock(return_value={})
            
            # Mock username lookup
            mock_gsm._id_to_username = {1: "TestPlayer"}
            
            # Mock item meta (not called with no equipment)
            mock_gsm.get_cached_item_meta.return_value = None
            
            stats = await CombatService.get_player_combat_stats(player_id)
            
            assert stats is not None
            assert stats.attack_level == 20
            assert stats.strength_level == 25
            assert stats.defence_level == 15
            assert stats.current_hp == 30
            assert stats.max_hp == 30
            assert stats.attack_bonus == 0
            assert stats.strength_bonus == 0
            assert stats.defence_bonus == 0
            assert stats.name == "TestPlayer"
    
    async def test_get_player_combat_stats_with_equipment(self):
        """Test fetching player combat stats with equipment bonuses"""
        player_id = 1
        
        with patch('server.src.services.combat_service.get_game_state_manager') as mock_gsm_getter:
            mock_gsm = MagicMock()
            mock_gsm_getter.return_value = mock_gsm
            
            # Mock skill data (async method)
            mock_gsm.get_all_skills = AsyncMock(return_value={
                "attack": {"level": 20},
                "strength": {"level": 25},
                "defence": {"level": 15},
                "hitpoints": {"level": 30}
            })
            
            # Mock HP data (async method)
            mock_gsm.get_player_hp = AsyncMock(return_value={
                "current_hp": 30,
                "max_hp": 30
            })
            
            # Mock equipment with bonuses (async method)
            mock_gsm.get_equipment = AsyncMock(return_value={
                "weapon": {"item_id": "BRONZE_SWORD"},
                "chest": {"item_id": "BRONZE_CHESTPLATE"}
            })
            
            # Mock username lookup
            mock_gsm._id_to_username = {1: "TestPlayer"}
            
            # Mock item metadata with bonuses
            def get_item_meta(item_id):
                if item_id == "BRONZE_SWORD":
                    return {"attack_bonus": 10, "strength_bonus": 8, "physical_defence_bonus": 0}
                elif item_id == "BRONZE_CHESTPLATE":
                    return {"attack_bonus": 0, "strength_bonus": 0, "physical_defence_bonus": 15}
                return {}
            
            mock_gsm.get_cached_item_meta.side_effect = get_item_meta
            
            stats = await CombatService.get_player_combat_stats(player_id)
            
            assert stats is not None
            assert stats.attack_bonus == 10
            assert stats.strength_bonus == 8
            assert stats.defence_bonus == 15
    
    async def test_get_entity_combat_stats(self):
        """Test fetching entity combat stats"""
        entity_id = 1
        
        with patch('server.src.services.combat_service.get_game_state_manager') as mock_gsm_getter:
            mock_gsm = MagicMock()
            mock_gsm_getter.return_value = mock_gsm
            
            # Mock entity instance (async method)
            mock_gsm.get_entity_instance = AsyncMock(return_value={
                "entity_name": "GOBLIN",
                "current_hp": 5,
                "max_hp": 10,
                "x": 30,
                "y": 30,
                "map_id": "samplemap"
            })
            
            # Mock entity definition via get_entity_by_name
            with patch('server.src.services.combat_service.get_entity_by_name') as mock_get_entity:
                from server.src.core.monsters import MonsterID
                # Return the actual MonsterID enum member
                mock_get_entity.return_value = MonsterID.GOBLIN
                
                stats = await CombatService.get_entity_combat_stats(entity_id)
                
                assert stats is not None
                assert stats.attack_level == 5
                assert stats.strength_level == 5
                assert stats.defence_level == 5
                assert stats.current_hp == 5
                assert stats.max_hp == 10
                assert stats.name == "Goblin"
    
    async def test_perform_attack_player_vs_entity_success(self):
        """Test successful player attack on entity"""
        player_id = 1
        entity_id = 1
        
        with patch('server.src.services.combat_service.get_game_state_manager') as mock_gsm_getter:
            mock_gsm = MagicMock()
            mock_gsm_getter.return_value = mock_gsm
            
            # Mock player stats
            with patch.object(CombatService, 'get_player_combat_stats') as mock_player_stats:
                mock_player_stats.return_value = CombatStats(
                    attack_level=50,
                    strength_level=50,
                    attack_bonus=50,
                    strength_bonus=50,
                    defence_level=40,
                    defence_bonus=30,
                    current_hp=50,
                    max_hp=50,
                    name="TestPlayer"
                )
                
                # Mock entity stats
                with patch.object(CombatService, 'get_entity_combat_stats') as mock_entity_stats:
                    mock_entity_stats.return_value = CombatStats(
                        attack_level=5,
                        strength_level=5,
                        attack_bonus=0,
                        strength_bonus=0,
                        defence_level=1,
                        defence_bonus=0,
                        current_hp=10,
                        max_hp=10,
                        name="Goblin"
                    )
                    
                    # Mock GSM update methods
                    mock_gsm.update_entity_hp = AsyncMock()
                    mock_gsm.despawn_entity = AsyncMock()
                    
                    # Mock SkillService
                    with patch('server.src.services.combat_service.SkillService.add_experience') as mock_add_xp:
                        mock_add_xp.return_value = AsyncMock()
                        
                        # Mock global tick counter from game_loop module
                        with patch('server.src.game.game_loop._global_tick_counter', 100):
                            # Force a hit for testing
                            with patch('server.src.services.combat_service.random.random', return_value=0.1):
                                # Force specific damage
                                with patch('server.src.services.combat_service.random.randint', return_value=5):
                                    result = await CombatService.perform_attack(
                                        attacker_type=CombatTargetType.PLAYER,
                                        attacker_id=player_id,
                                        defender_type=CombatTargetType.ENTITY,
                                        defender_id=entity_id
                                    )
                                    
                                    assert result.success
                                    assert result.hit
                                    assert result.damage == 5
                                    assert result.defender_hp == 5
                                    assert not result.defender_died
                                    assert len(result.xp_gained) > 0
                                    
                                    # Verify GSM calls
                                    mock_gsm.update_entity_hp.assert_called_once_with(entity_id, 5)
    
    async def test_perform_attack_entity_dies(self):
        """Test entity death from player attack"""
        player_id = 1
        entity_id = 1
        
        with patch('server.src.services.combat_service.get_game_state_manager') as mock_gsm_getter:
            mock_gsm = MagicMock()
            mock_gsm_getter.return_value = mock_gsm
            
            # Mock player stats (strong)
            with patch.object(CombatService, 'get_player_combat_stats') as mock_player_stats:
                mock_player_stats.return_value = CombatStats(
                    attack_level=50,
                    strength_level=50,
                    attack_bonus=50,
                    strength_bonus=50,
                    defence_level=40,
                    defence_bonus=30,
                    current_hp=50,
                    max_hp=50,
                    name="TestPlayer"
                )
                
                # Mock entity stats (low HP)
                with patch.object(CombatService, 'get_entity_combat_stats') as mock_entity_stats:
                    mock_entity_stats.return_value = CombatStats(
                        attack_level=5,
                        strength_level=5,
                        attack_bonus=0,
                        strength_bonus=0,
                        defence_level=1,
                        defence_bonus=0,
                        current_hp=3,  # Low HP
                        max_hp=10,
                        name="Goblin"
                    )
                    
                    # Mock GSM update methods
                    mock_gsm.update_entity_hp = AsyncMock()
                    mock_gsm.despawn_entity = AsyncMock()
                    
                    # Mock SkillService
                    with patch('server.src.services.combat_service.SkillService.add_experience') as mock_add_xp:
                        mock_add_xp.return_value = AsyncMock()
                        
                        # Mock global tick counter from game_loop module
                        with patch('server.src.game.game_loop._global_tick_counter', 100):
                            # Force a hit with 5 damage (kills entity)
                            with patch('server.src.services.combat_service.random.random', return_value=0.1):
                                with patch('server.src.services.combat_service.random.randint', return_value=5):
                                    result = await CombatService.perform_attack(
                                        attacker_type=CombatTargetType.PLAYER,
                                        attacker_id=player_id,
                                        defender_type=CombatTargetType.ENTITY,
                                        defender_id=entity_id
                                    )
                                    
                                    assert result.success
                                    assert result.hit
                                    assert result.damage == 5
                                    assert result.defender_hp == 0
                                    assert result.defender_died
                                    assert "died" in result.message.lower()
                                    
                                    # Verify despawn called with death animation
                                    mock_gsm.despawn_entity.assert_called_once()
                                    call_args = mock_gsm.despawn_entity.call_args
                                    assert call_args[0][0] == entity_id  # entity_id
                                    assert call_args[1]["death_tick"] == 110  # 100 + 10
                                    assert call_args[1]["respawn_delay_seconds"] == 30
    
    async def test_perform_attack_target_already_dead(self):
        """Test attack on already dead target fails"""
        player_id = 1
        entity_id = 1
        
        # Mock player stats
        with patch.object(CombatService, 'get_player_combat_stats') as mock_player_stats:
            mock_player_stats.return_value = CombatStats(
                attack_level=50,
                strength_level=50,
                attack_bonus=50,
                strength_bonus=50,
                defence_level=40,
                defence_bonus=30,
                current_hp=50,
                max_hp=50,
                name="TestPlayer"
            )
            
            # Mock entity stats (dead)
            with patch.object(CombatService, 'get_entity_combat_stats') as mock_entity_stats:
                mock_entity_stats.return_value = CombatStats(
                    attack_level=5,
                    strength_level=5,
                    attack_bonus=0,
                    strength_bonus=0,
                    defence_level=1,
                    defence_bonus=0,
                    current_hp=0,  # Already dead
                    max_hp=10,
                    name="Goblin"
                )
                
                result = await CombatService.perform_attack(
                    attacker_type=CombatTargetType.PLAYER,
                    attacker_id=player_id,
                    defender_type=CombatTargetType.ENTITY,
                    defender_id=entity_id
                )
                
                assert not result.success
                assert result.error == "Target is already dead"
                assert not result.hit
                assert result.damage == 0
    
    async def test_perform_attack_invalid_attacker(self):
        """Test attack with invalid attacker fails"""
        player_id = 999  # Non-existent
        entity_id = 1
        
        # Mock player stats (return None for not found)
        with patch.object(CombatService, 'get_player_combat_stats') as mock_player_stats:
            mock_player_stats.return_value = None
            
            result = await CombatService.perform_attack(
                attacker_type=CombatTargetType.PLAYER,
                attacker_id=player_id,
                defender_type=CombatTargetType.ENTITY,
                defender_id=entity_id
            )
            
            assert not result.success
            assert result.error == "Attacker not found"
    
    async def test_perform_attack_invalid_defender(self):
        """Test attack with invalid defender fails"""
        player_id = 1
        entity_id = 999  # Non-existent
        
        # Mock player stats
        with patch.object(CombatService, 'get_player_combat_stats') as mock_player_stats:
            mock_player_stats.return_value = CombatStats(
                attack_level=50,
                strength_level=50,
                attack_bonus=50,
                strength_bonus=50,
                defence_level=40,
                defence_bonus=30,
                current_hp=50,
                max_hp=50,
                name="TestPlayer"
            )
            
            # Mock entity stats (return None for not found)
            with patch.object(CombatService, 'get_entity_combat_stats') as mock_entity_stats:
                mock_entity_stats.return_value = None
                
                result = await CombatService.perform_attack(
                    attacker_type=CombatTargetType.PLAYER,
                    attacker_id=player_id,
                    defender_type=CombatTargetType.ENTITY,
                    defender_id=entity_id
                )
                
                assert not result.success
                assert result.error == "Defender not found"
