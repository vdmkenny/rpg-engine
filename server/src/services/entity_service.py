"""
Service for managing entity definitions and their database synchronization.
"""

from typing import Optional, Dict, Any, List, Union

from ..core.entities import EntityType
from ..core.humanoids import HumanoidID, HumanoidDefinition
from ..core.monsters import MonsterID, MonsterDefinition
from ..core.logging_config import get_logger
from ..models.entity import Entity
from .game_state_manager import get_game_state_manager

logger = get_logger(__name__)


class EntityService:
    """
    Service for managing Entity templates.
    
    Responsibilities:
    1. Syncing HumanoidID and MonsterID enums to the 'entities' database table.
    2. Providing access to entity metadata.
    """
    
    @staticmethod
    async def sync_entities_to_db() -> None:
        """
        Sync entities from HumanoidID and MonsterID enums to the database.
        
        This is called on server startup to ensure the database 'entities' table
        mirrors the code definitions.
        """
        gsm = get_game_state_manager()
        await gsm.sync_entities_to_database()

    @staticmethod
    def _humanoid_def_to_dict(name: str, definition: HumanoidDefinition) -> Dict[str, Any]:
        """Convert a HumanoidDefinition to a dictionary suitable for DB insertion."""
        return {
            "name": name,
            "entity_type": EntityType.HUMANOID_NPC.value,
            "display_name": definition.display_name,
            "description": definition.description,
            "behavior": definition.behavior.value,
            "is_attackable": definition.is_attackable,
            "level": definition.level,
            "max_hp": definition.max_hp,
            "respawn_time": definition.respawn_time,
            
            # Serialize complex types
            "skills": {k.name.lower(): v for k, v in definition.skills.items()},
            "dialogue": definition.dialogue,
            "shop_id": definition.shop_id,
            
            # Humanoid-specific: appearance and equipment
            "appearance": definition.appearance.to_dict() if definition.appearance else None,
            "equipped_items": {
                slot.value: item.name for slot, item in definition.equipped_items.items()
            } if definition.equipped_items else {},
            
            # Humanoids derive stats from equipment, so these are 0
            "attack_bonus": 0,
            "strength_bonus": 0,
            "ranged_attack_bonus": 0,
            "ranged_strength_bonus": 0,
            "magic_attack_bonus": 0,
            "magic_damage_bonus": 0,
            "physical_defence_bonus": 0,
            "magic_defence_bonus": 0,
            "speed_bonus": 0,
            
            # Monsters-only fields (not applicable)
            "sprite_sheet_id": None,
            "width": 1,
            "height": 1,
            "scale": 1.0,
            "xp_reward": 0,
            "aggro_radius": 0,
            "disengage_radius": 0,
        }
    
    @staticmethod
    def _monster_def_to_dict(name: str, definition: MonsterDefinition) -> Dict[str, Any]:
        """Convert a MonsterDefinition to a dictionary suitable for DB insertion."""
        return {
            "name": name,
            "entity_type": EntityType.MONSTER.value,
            "display_name": definition.display_name,
            "description": definition.description,
            "behavior": definition.behavior.value,
            "is_attackable": True,  # Monsters are always attackable
            "level": definition.level,
            "max_hp": definition.max_hp,
            "respawn_time": definition.respawn_time,
            
            # Serialize complex types
            "skills": {k.name.lower(): v for k, v in definition.skills.items()},
            "dialogue": None,  # Monsters don't have dialogue
            "shop_id": None,  # Monsters don't have shops
            
            # Humanoid-specific fields (not applicable)
            "appearance": None,
            "equipped_items": {},
            
            # Monster combat stats (innate)
            "attack_bonus": definition.attack_bonus,
            "strength_bonus": definition.strength_bonus,
            "ranged_attack_bonus": definition.ranged_attack_bonus,
            "ranged_strength_bonus": definition.ranged_strength_bonus,
            "magic_attack_bonus": definition.magic_attack_bonus,
            "magic_damage_bonus": definition.magic_damage_bonus,
            "physical_defence_bonus": definition.physical_defence_bonus,
            "magic_defence_bonus": definition.magic_defence_bonus,
            "speed_bonus": definition.speed_bonus,
            
            # Monster visual/combat fields
            "sprite_sheet_id": definition.sprite_sheet_id,
            "width": definition.width,
            "height": definition.height,
            "scale": definition.scale,
            "xp_reward": definition.xp_reward,
            "aggro_radius": definition.aggro_radius,
            "disengage_radius": definition.disengage_radius,
        }
    
    @staticmethod
    def entity_def_to_dict(
        name: str,
        definition: Union[HumanoidDefinition, MonsterDefinition]
    ) -> Dict[str, Any]:
        """
        Convert an entity definition to a dictionary suitable for DB insertion.
        
        Handles both HumanoidDefinition and MonsterDefinition.
        """
        if isinstance(definition, HumanoidDefinition):
            return EntityService._humanoid_def_to_dict(name, definition)
        elif isinstance(definition, MonsterDefinition):
            return EntityService._monster_def_to_dict(name, definition)
        else:
            raise ValueError(f"Unknown definition type: {type(definition)}")
