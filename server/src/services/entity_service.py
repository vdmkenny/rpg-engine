"""
Service for managing entity definitions and their database synchronization.
"""

from typing import Optional, Dict, Any, List

from ..core.entities import EntityID, EntityDefinition
from ..core.logging_config import get_logger
from ..models.entity import Entity
from .game_state_manager import get_game_state_manager

logger = get_logger(__name__)

class EntityService:
    """
    Service for managing Entity templates.
    
    Responsibilities:
    1. Syncing EntityID enums to the 'entities' database table.
    2. Providing access to entity metadata.
    """
    
    @staticmethod
    async def sync_entities_to_db() -> None:
        """
        Sync entities from EntityID enum to the database.
        
        This is called on server startup to ensure the database 'entities' table
        mirrors the code definitions in 'EntityID'.
        """
        gsm = get_game_state_manager()
        
        # We need a session to write to the DB.
        # GSM manages sessions, but for this bulk sync operation we might want to 
        # use the session directly or add a method to GSM.
        # Since GSM architecture discourages direct DB access from services, 
        # we should ideally add this to GSM.
        # However, for this specific "Code -> DB Mirror" pattern which happens 
        # exactly once at startup, accessing the DB via GSM's session factory 
        # (if exposed) or passing a session is common.
        #
        # Looking at ItemService.sync_items_to_db(), it calls gsm.sync_items_to_database().
        # We should follow that pattern.
        
        await gsm.sync_entities_to_database()

    @staticmethod
    def _entity_def_to_dict(name: str, definition: EntityDefinition) -> Dict[str, Any]:
        """Convert an EntityDefinition to a dictionary suitable for DB insertion."""
        return {
            "name": name,
            "display_name": definition.display_name,
            "description": definition.description,
            "behavior": definition.behavior.value,
            "is_attackable": definition.is_attackable,
            "sprite_name": definition.sprite_name,
            "width": definition.width,
            "height": definition.height,
            "scale": definition.scale,
            "level": definition.level,
            "max_hp": definition.max_hp,
            "xp_reward": definition.xp_reward,
            "aggro_radius": definition.aggro_radius,
            "disengage_radius": definition.disengage_radius,
            "respawn_time": definition.respawn_time,
            
            # Serialize complex types
            "skills": {k.name.lower(): v for k, v in definition.skills.items()},
            "dialogue": definition.dialogue,
            "shop_id": definition.shop_id,
            
            # Stats
            "attack_bonus": definition.attack_bonus,
            "strength_bonus": definition.strength_bonus,
            "ranged_attack_bonus": definition.ranged_attack_bonus,
            "ranged_strength_bonus": definition.ranged_strength_bonus,
            "magic_attack_bonus": definition.magic_attack_bonus,
            "magic_damage_bonus": definition.magic_damage_bonus,
            "physical_defence_bonus": definition.physical_defence_bonus,
            "magic_defence_bonus": definition.magic_defence_bonus,
            "speed_bonus": definition.speed_bonus,
        }
