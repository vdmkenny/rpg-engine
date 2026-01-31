"""
Combat service for handling player and entity combat.

Implements RuneScape-style combat mechanics:
- Hit/miss calculations based on Attack vs Defence
- Damage calculations based on Strength and equipment bonuses
- XP rewards for combat skills
- Entity death handling

Following GSM architecture:
- Service contains ALL business logic
- GSM used ONLY for data operations
- No direct database/Valkey access
"""

import random
from dataclasses import dataclass
from typing import Optional, Literal, Dict, Any
from enum import Enum

from server.src.core.logging_config import get_logger
from server.src.core.skills import SkillType
from server.src.services.game_state_manager import get_game_state_manager
from server.src.services.skill_service import SkillService
from server.src.core.entities import EntityID

logger = get_logger(__name__)


class CombatStyle(str, Enum):
    """Combat attack styles"""
    MELEE = "melee"
    RANGED = "ranged"
    MAGIC = "magic"


@dataclass
class CombatStats:
    """Combat statistics for an attacker or defender"""
    # Offensive stats
    attack_level: int
    strength_level: int
    attack_bonus: int
    strength_bonus: int
    
    # Defensive stats
    defence_level: int
    defence_bonus: int
    
    # HP
    current_hp: int
    max_hp: int
    
    # Identity
    name: str  # Username or entity display name


@dataclass
class CombatResult:
    """Result of a combat action"""
    success: bool
    hit: bool  # Did the attack hit?
    damage: int  # Damage dealt (0 if miss)
    attacker_hp: int  # Attacker's HP after combat
    defender_hp: int  # Defender's HP after combat
    defender_died: bool  # Did defender die?
    xp_gained: Dict[SkillType, int]  # XP rewards by skill
    message: str  # Combat message for display
    error: Optional[str] = None  # Error message if success=False


class CombatService:
    """
    Combat service implementing RuneScape-style combat mechanics.
    
    All business logic is here. GSM is used ONLY for data operations.
    """
    
    # Combat constants
    MAX_HIT_ROLL = 64  # Maximum value for hit roll calculations
    MAX_DEFENCE_ROLL = 64  # Maximum value for defence roll calculations
    
    @staticmethod
    async def get_player_combat_stats(player_id: int) -> Optional[CombatStats]:
        """
        Get player's combat statistics.
        
        Args:
            player_id: Player's database ID
            
        Returns:
            CombatStats or None if player not found
        """
        gsm = get_game_state_manager()
        
        # Get skills
        skills = await gsm.get_all_skills(player_id)
        if not skills:
            return None
        
        attack_skill = skills.get("attack", {})
        strength_skill = skills.get("strength", {})
        defence_skill = skills.get("defence", {})
        hitpoints_skill = skills.get("hitpoints", {})
        
        attack_level = attack_skill.get("level", 1)
        strength_level = strength_skill.get("level", 1)
        defence_level = defence_skill.get("level", 1)
        
        # Get HP
        hp_data = await gsm.get_player_hp(player_id)
        if not hp_data:
            return None
        
        # Get equipment bonuses
        equipment = await gsm.get_equipment(player_id)
        attack_bonus = 0
        strength_bonus = 0
        defence_bonus = 0
        
        for slot, item_data in equipment.items():
            item_id = item_data.get("item_id")
            item_meta = gsm.get_cached_item_meta(item_id)
            if item_meta:
                attack_bonus += item_meta.get("attack_bonus", 0)
                strength_bonus += item_meta.get("strength_bonus", 0)
                defence_bonus += item_meta.get("physical_defence_bonus", 0)
        
        # Get username for display
        username = gsm._id_to_username.get(player_id, f"Player{player_id}")
        
        return CombatStats(
            attack_level=attack_level,
            strength_level=strength_level,
            attack_bonus=attack_bonus,
            strength_bonus=strength_bonus,
            defence_level=defence_level,
            defence_bonus=defence_bonus,
            current_hp=hp_data["current_hp"],
            max_hp=hp_data["max_hp"],
            name=username
        )
    
    @staticmethod
    async def get_entity_combat_stats(entity_id: int) -> Optional[CombatStats]:
        """
        Get entity's combat statistics from instance data.
        
        Args:
            entity_id: Entity instance ID
            
        Returns:
            CombatStats or None if entity not found
        """
        gsm = get_game_state_manager()
        
        # Get entity instance
        entity_data = await gsm.get_entity_instance(entity_id)
        if not entity_data:
            return None
        
        # Get entity definition
        entity_name = entity_data.get("entity_name", "")
        entity_enum = EntityID.from_name(entity_name)
        if not entity_enum:
            return None
        
        entity_def = entity_enum.value
        
        # Extract skills from definition
        attack_level = entity_def.skills.get(SkillType.ATTACK, 1)
        strength_level = entity_def.skills.get(SkillType.STRENGTH, 1)
        defence_level = entity_def.skills.get(SkillType.DEFENCE, 1)
        
        return CombatStats(
            attack_level=attack_level,
            strength_level=strength_level,
            attack_bonus=entity_def.attack_bonus,
            strength_bonus=entity_def.strength_bonus,
            defence_level=defence_level,
            defence_bonus=entity_def.physical_defence_bonus,
            current_hp=int(entity_data.get("current_hp", 0)),
            max_hp=int(entity_data.get("max_hp", 10)),
            name=entity_def.display_name
        )
    
    @staticmethod
    def calculate_hit_chance(attacker: CombatStats, defender: CombatStats) -> float:
        """
        Calculate hit chance using RuneScape-style formula.
        
        Hit chance = attack_roll / (attack_roll + defence_roll)
        
        Args:
            attacker: Attacker's combat stats
            defender: Defender's combat stats
            
        Returns:
            Hit chance as float between 0.0 and 1.0
        """
        # Attack roll = (attack_level + attack_bonus + 8) * (64 + attack_bonus) / 64
        attack_roll = (attacker.attack_level + attacker.attack_bonus + 8) * (
            CombatService.MAX_HIT_ROLL + attacker.attack_bonus
        ) / CombatService.MAX_HIT_ROLL
        
        # Defence roll = (defence_level + defence_bonus + 8) * (64 + defence_bonus) / 64
        defence_roll = (defender.defence_level + defender.defence_bonus + 8) * (
            CombatService.MAX_DEFENCE_ROLL + defender.defence_bonus
        ) / CombatService.MAX_DEFENCE_ROLL
        
        # Hit chance = attack_roll / (attack_roll + defence_roll)
        if attack_roll + defence_roll == 0:
            return 0.5  # Equal chance if both are 0
        
        hit_chance = attack_roll / (attack_roll + defence_roll)
        
        # Clamp between 0.05 and 0.95 (always 5% chance to hit/miss)
        return max(0.05, min(0.95, hit_chance))
    
    @staticmethod
    def calculate_max_hit(attacker: CombatStats) -> int:
        """
        Calculate maximum possible hit damage.
        
        Max hit = floor((strength_level * (strength_bonus + 64) + 320) / 640)
        
        Args:
            attacker: Attacker's combat stats
            
        Returns:
            Maximum hit damage
        """
        max_hit = (
            attacker.strength_level * (attacker.strength_bonus + 64) + 320
        ) // 640
        
        return max(1, max_hit)  # Minimum 1 damage
    
    @staticmethod
    def roll_damage(attacker: CombatStats, did_hit: bool) -> int:
        """
        Roll actual damage dealt.
        
        If hit: random damage between 0 and max_hit
        If miss: 0 damage
        
        Args:
            attacker: Attacker's combat stats
            did_hit: Whether the attack hit
            
        Returns:
            Damage dealt
        """
        if not did_hit:
            return 0
        
        max_hit = CombatService.calculate_max_hit(attacker)
        return random.randint(0, max_hit)
    
    @staticmethod
    def calculate_combat_xp(damage_dealt: int, defender_died: bool) -> Dict[SkillType, int]:
        """
        Calculate XP rewards for combat.
        
        - Attack XP: damage * 4
        - Strength XP: damage * 4
        - Hitpoints XP: damage * 4 / 3
        - Defence XP (on kill): defender max HP * 2
        
        Args:
            damage_dealt: Amount of damage dealt
            defender_died: Whether defender died from this attack
            
        Returns:
            Dict of {SkillType: xp_amount}
        """
        xp_rewards = {}
        
        if damage_dealt > 0:
            # Attack and Strength XP (4 XP per damage)
            xp_rewards[SkillType.ATTACK] = damage_dealt * 4
            xp_rewards[SkillType.STRENGTH] = damage_dealt * 4
            
            # Hitpoints XP (1.33 XP per damage)
            xp_rewards[SkillType.HITPOINTS] = int(damage_dealt * 4 / 3)
        
        return xp_rewards
    
    @staticmethod
    async def perform_attack(
        attacker_type: Literal["player", "entity"],
        attacker_id: int,
        defender_type: Literal["player", "entity"],
        defender_id: int,
    ) -> CombatResult:
        """
        Perform a combat attack.
        
        Args:
            attacker_type: "player" or "entity"
            attacker_id: Attacker's ID (player_id or entity instance_id)
            defender_type: "player" or "entity"
            defender_id: Defender's ID (player_id or entity instance_id)
            
        Returns:
            CombatResult with outcome
        """
        # Get combat stats
        if attacker_type == "player":
            attacker_stats = await CombatService.get_player_combat_stats(attacker_id)
        else:
            attacker_stats = await CombatService.get_entity_combat_stats(attacker_id)
        
        if not attacker_stats:
            return CombatResult(
                success=False,
                hit=False,
                damage=0,
                attacker_hp=0,
                defender_hp=0,
                defender_died=False,
                xp_gained={},
                message="",
                error="Attacker not found"
            )
        
        if defender_type == "player":
            defender_stats = await CombatService.get_player_combat_stats(defender_id)
        else:
            defender_stats = await CombatService.get_entity_combat_stats(defender_id)
        
        if not defender_stats:
            return CombatResult(
                success=False,
                hit=False,
                damage=0,
                attacker_hp=attacker_stats.current_hp,
                defender_hp=0,
                defender_died=False,
                xp_gained={},
                message="",
                error="Defender not found"
            )
        
        # Check if defender is already dead
        if defender_stats.current_hp <= 0:
            return CombatResult(
                success=False,
                hit=False,
                damage=0,
                attacker_hp=attacker_stats.current_hp,
                defender_hp=0,
                defender_died=True,
                xp_gained={},
                message="",
                error="Target is already dead"
            )
        
        # Calculate hit chance and roll
        hit_chance = CombatService.calculate_hit_chance(attacker_stats, defender_stats)
        did_hit = random.random() < hit_chance
        
        # Roll damage
        damage = CombatService.roll_damage(attacker_stats, did_hit)
        
        # Apply damage
        new_defender_hp = max(0, defender_stats.current_hp - damage)
        defender_died = new_defender_hp == 0
        
        # Update HP via GSM
        gsm = get_game_state_manager()
        if defender_type == "player":
            await gsm.set_player_hp(defender_id, new_defender_hp)
        else:
            await gsm.update_entity_hp(defender_id, new_defender_hp)
            
            # If entity died, trigger death animation
            if defender_died:
                from server.src.game.game_loop import _global_tick_counter
                death_tick = _global_tick_counter + 10  # 10 ticks for death animation
                await gsm.despawn_entity(defender_id, death_tick=death_tick, respawn_delay_seconds=30)
        
        # Calculate XP (only for player attackers)
        xp_gained = {}
        if attacker_type == "player":
            xp_gained = CombatService.calculate_combat_xp(damage, defender_died)
            
            # Award XP
            for skill_type, xp_amount in xp_gained.items():
                await SkillService.add_experience(attacker_id, skill_type.name.lower(), xp_amount)
        
        # Build combat message
        if did_hit:
            if damage > 0:
                message = f"{attacker_stats.name} hit {defender_stats.name} for {damage} damage"
            else:
                message = f"{attacker_stats.name} hit {defender_stats.name} but dealt no damage"
        else:
            message = f"{attacker_stats.name} attacked {defender_stats.name} but missed"
        
        if defender_died:
            message += f" - {defender_stats.name} died!"
        
        logger.info(
            "Combat action performed",
            extra={
                "attacker_type": attacker_type,
                "attacker_id": attacker_id,
                "defender_type": defender_type,
                "defender_id": defender_id,
                "hit": did_hit,
                "damage": damage,
                "defender_died": defender_died,
            }
        )
        
        # Auto-retaliation: If defender is a player and alive, check if they should auto-attack back
        if defender_type == "player" and not defender_died and new_defender_hp > 0:
            # Get defender's settings
            defender_settings = await gsm.get_player_settings(defender_id)
            auto_retaliate = defender_settings.get("auto_retaliate", True)
            
            # Check if defender is already in combat
            defender_combat_state = await gsm.get_player_combat_state(defender_id)
            
            # If auto-retaliate is on and not already in combat, set combat state to attack back
            if auto_retaliate and not defender_combat_state:
                from server.src.game.game_loop import _global_tick_counter
                from server.src.core.config import game_config
                
                # Get defender's weapon attack speed
                defender_equipment = await gsm.get_equipment(defender_id)
                defender_weapon = defender_equipment.get("weapon")
                if defender_weapon and defender_weapon.get("item_id"):
                    weapon_meta = gsm.get_cached_item_meta(defender_weapon["item_id"])
                    base_attack_speed = game_config.get("game", {}).get("combat", {}).get("base_attack_speed", 3.0)
                    defender_attack_speed = weapon_meta.get("attack_speed", base_attack_speed)
                else:
                    # Unarmed
                    defender_attack_speed = game_config.get("game", {}).get("combat", {}).get("base_attack_speed", 3.0)
                
                # Set combat state to retaliate
                await gsm.set_player_combat_state(
                    player_id=defender_id,
                    target_type=attacker_type,
                    target_id=attacker_id,
                    last_attack_tick=_global_tick_counter,
                    attack_speed=defender_attack_speed,
                )
                
                logger.info(
                    "Auto-retaliation triggered",
                    extra={
                        "defender_id": defender_id,
                        "attacker_type": attacker_type,
                        "attacker_id": attacker_id,
                    }
                )
        
        return CombatResult(
            success=True,
            hit=did_hit,
            damage=damage,
            attacker_hp=attacker_stats.current_hp,
            defender_hp=new_defender_hp,
            defender_died=defender_died,
            xp_gained=xp_gained,
            message=message
        )
