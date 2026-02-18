"""
Service for managing entity definitions and their database synchronization.
"""

from typing import Optional, Dict, Any, Union

from ..core.entities import EntityType
from ..core.humanoids import HumanoidID, HumanoidDefinition
from ..core.monsters import MonsterID, MonsterDefinition
from ..core.entity_utils import entity_def_to_dict
from ..core.logging_config import get_logger
from ..models.entity import Entity
from .game_state import get_reference_data_manager

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
        ref_mgr = get_reference_data_manager()
        await ref_mgr.sync_entities_to_database()

    @staticmethod
    def entity_def_to_dict(
        name: str,
        definition: Union[HumanoidDefinition, MonsterDefinition]
    ) -> Dict[str, Any]:
        """
        Convert an entity definition to a dictionary suitable for DB insertion.

        Handles both HumanoidDefinition and MonsterDefinition.
        Delegates to core utility functions to avoid code duplication.
        """
        return entity_def_to_dict(name, definition)
