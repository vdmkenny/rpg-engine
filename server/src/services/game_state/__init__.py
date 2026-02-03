"""
Game state management package.

Provides focused managers for different aspects of game state:
- PlayerStateManager: Online registry, position, HP, settings, combat state
- InventoryManager: Inventory CRUD with auto-loading
- EquipmentManager: Equipment CRUD with auto-loading
- SkillsManager: Skills CRUD with auto-loading
- GroundItemManager: Ground items (dropped items)
- EntityManager: Entity instances (ephemeral combat entities)
- ReferenceDataManager: Item/skill/entity definitions (permanent cache)
"""

from glide import GlideClient
from sqlalchemy.orm import sessionmaker
from typing import Optional

from .base_manager import BaseManager
from .player_state_manager import (
    PlayerStateManager,
    get_player_state_manager,
    init_player_state_manager,
    reset_player_state_manager,
)
from .inventory_manager import (
    InventoryManager,
    get_inventory_manager,
    init_inventory_manager,
    reset_inventory_manager,
)
from .equipment_manager import (
    EquipmentManager,
    get_equipment_manager,
    init_equipment_manager,
    reset_equipment_manager,
)
from .skills_manager import (
    SkillsManager,
    get_skills_manager,
    init_skills_manager,
    reset_skills_manager,
)
from .ground_item_manager import (
    GroundItemManager,
    get_ground_item_manager,
    init_ground_item_manager,
    reset_ground_item_manager,
)
from .entity_manager import (
    EntityManager,
    get_entity_manager,
    init_entity_manager,
    reset_entity_manager,
    ENTITY_RESPAWN_QUEUE_KEY,
)
from .reference_data_manager import (
    ReferenceDataManager,
    get_reference_data_manager,
    init_reference_data_manager,
    reset_reference_data_manager,
)

# Batch sync coordinator
from .batch_sync import BatchSyncCoordinator, get_batch_sync_coordinator

__all__ = [
    "BaseManager",
    "PlayerStateManager",
    "get_player_state_manager",
    "InventoryManager",
    "get_inventory_manager",
    "EquipmentManager",
    "get_equipment_manager",
    "SkillsManager",
    "get_skills_manager",
    "GroundItemManager",
    "get_ground_item_manager",
    "EntityManager",
    "get_entity_manager",
    "ReferenceDataManager",
    "get_reference_data_manager",
    "BatchSyncCoordinator",
    "get_batch_sync_coordinator",
    "init_all_managers",
    "reset_all_managers",
]


# Global references to all managers
_player_state_manager: Optional[PlayerStateManager] = None
_inventory_manager: Optional[InventoryManager] = None
_equipment_manager: Optional[EquipmentManager] = None
_skills_manager: Optional[SkillsManager] = None
_ground_item_manager: Optional[GroundItemManager] = None
_entity_manager: Optional[EntityManager] = None
_reference_data_manager: Optional[ReferenceDataManager] = None
_batch_sync_coordinator: Optional[BatchSyncCoordinator] = None


def init_all_managers(
    valkey_client: Optional[GlideClient] = None,
    session_factory: Optional[sessionmaker] = None,
) -> None:
    """Initialize all game state managers with shared connections."""
    global _player_state_manager, _inventory_manager, _equipment_manager
    global _skills_manager, _ground_item_manager, _entity_manager
    global _reference_data_manager, _batch_sync_coordinator

    _player_state_manager = init_player_state_manager(valkey_client, session_factory)
    _inventory_manager = init_inventory_manager(valkey_client, session_factory)
    _equipment_manager = init_equipment_manager(valkey_client, session_factory)
    _skills_manager = init_skills_manager(valkey_client, session_factory)
    _ground_item_manager = init_ground_item_manager(valkey_client, session_factory)
    _entity_manager = init_entity_manager(valkey_client, session_factory)
    _reference_data_manager = init_reference_data_manager(valkey_client, session_factory)
    
    # Initialize batch sync coordinator with all managers
    _batch_sync_coordinator = BatchSyncCoordinator(
        _player_state_manager,
        _inventory_manager,
        _equipment_manager,
        _skills_manager,
        _ground_item_manager,
        session_factory,
    )


def reset_all_managers() -> None:
    """Reset all game state managers."""
    global _player_state_manager, _inventory_manager, _equipment_manager
    global _skills_manager, _ground_item_manager, _entity_manager
    global _reference_data_manager, _batch_sync_coordinator

    reset_player_state_manager()
    reset_inventory_manager()
    reset_equipment_manager()
    reset_skills_manager()
    reset_ground_item_manager()
    reset_entity_manager()
    reset_reference_data_manager()
    _batch_sync_coordinator = None


# Convenience exports
player = get_player_state_manager
inventory = get_inventory_manager
equipment = get_equipment_manager
skills = get_skills_manager
ground_items = get_ground_item_manager
entities = get_entity_manager
reference_data = get_reference_data_manager
sync = get_batch_sync_coordinator
