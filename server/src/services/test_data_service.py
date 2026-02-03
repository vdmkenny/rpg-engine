"""
Test Data Service - Centralized test data management for WebSocket integration tests.

This service handles all test data setup, synchronization, and cleanup operations
using the service layer architecture. It eliminates the need for direct database
or GSM access in tests and provides standardized test scenarios.
"""

from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass

from ..core.logging_config import get_logger
from ..core.security import get_password_hash
from ..models.player import Player
from ..schemas.service_results import (
    TestDataServiceResult,
    ServiceErrorCodes
)
from .item_service import ItemService
from .player_service import PlayerService
from .inventory_service import InventoryService
from .equipment_service import EquipmentService
from .ground_item_service import GroundItemService
from .game_state import get_player_state_manager, get_inventory_manager, get_equipment_manager, get_reference_data_manager

logger = get_logger(__name__)


@dataclass
class PlayerConfig:
    """Configuration for creating a test player."""
    username_prefix: str = "player"
    password: str = "testpassword123"
    x: int = 0
    y: int = 0
    map_id: str = "samplemap"
    skills: Optional[Dict[str, int]] = None  # {skill_name: level}
    items: Optional[List[Tuple[str, int]]] = None  # [(item_name, quantity)]
    equipment: Optional[Dict[str, str]] = None  # {slot: item_name}


@dataclass
class GroundItemConfig:
    """Configuration for creating test ground items."""
    item_name: str
    x: int
    y: int
    map_id: str = "samplemap"
    quantity: int = 1
    dropped_by_player_id: Optional[int] = None


@dataclass
class MultiplayerScenario:
    """Complete multiplayer test scenario."""
    players: List[Player]
    ground_items: List[Dict[str, Any]]
    scenario_data: Dict[str, Any]


class TestDataService:
    """Service for managing test data through proper service layer."""

    @staticmethod
    async def ensure_game_data_synced() -> TestDataServiceResult[int]:
        """
        Ensure all game data (items, skills, maps) is synchronized to database.
        
        This replaces all pytest.skip("item not found") patterns by ensuring
        test data is available before tests run.
        
        Returns:
            TestDataServiceResult with count of items synced
        """
        try:
            # Sync items to database - this is the main cause of test skips
            await ItemService.sync_items_to_db()
            
            # Get item count from GSM cache
            ref_mgr = get_reference_data_manager()
            cached_items = ref_mgr.get_all_cached_items()
            item_count = len(cached_items) if cached_items else 0
            
            logger.info(
                "Game data synchronized for tests",
                extra={"items_synced": item_count}
            )
            
            return TestDataServiceResult(
                success=True,
                data=item_count,
                message=f"Synchronized {item_count} items to database"
            )
            
        except Exception as e:
            logger.error(
                "Failed to sync game data",
                extra={"error": str(e)}
            )
            return TestDataServiceResult(
                success=False,
                data=None,
                message=f"Failed to sync game data: {str(e)}",
                error_code=ServiceErrorCodes.VALIDATION_ERROR
            )

    @staticmethod
    async def create_test_player_with_items(
        config: PlayerConfig
    ) -> TestDataServiceResult[Player]:
        """
        Create a test player with full setup including items and equipment.
        
        This replaces direct database/GSM manipulation in tests with proper
        service layer calls.
        
        Args:
            config: Player configuration
            
        Returns:
            TestDataServiceResult with created player
        """
        try:
            # Generate unique username
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            username = f"{config.username_prefix}_{timestamp}"
            
            # Create player through service layer
            from ..schemas.player import PlayerCreate
            
            player_data = PlayerCreate(
                username=username,
                password=config.password
            )
            
            player = await PlayerService.create_player(
                player_data=player_data
            )
            
            if not player:
                return TestDataServiceResult(
                    success=False,
                    data=None,
                    message="Failed to create player: PlayerService returned None",
                    error_code=ServiceErrorCodes.PLAYER_ALREADY_EXISTS
                )
            
            # Update player position if specified
            if config.x != 0 or config.y != 0 or config.map_id != "samplemap":
                # Set position through player state manager
                player_mgr = get_player_state_manager()
                player_mgr.register_online_player(player_id=player.id, username=username)
                await player_mgr.set_player_full_state(
                    player_id=player.id,
                    x=config.x,
                    y=config.y,
                    map_id=config.map_id,
                    current_hp=10,
                    max_hp=10
                )
            
            # Add items to inventory if specified
            if config.items:
                for item_name, quantity in config.items:
                    item = await ItemService.get_item_by_name(item_name)
                    if item:
                        await InventoryService.add_item(
                            player_id=player.id,
                            item_id=item.id,
                            quantity=quantity
                        )
                    else:
                        logger.warning(
                            "Test item not found - skipping",
                            extra={"item_name": item_name, "player": username}
                        )
            
            # Equip items if specified
            if config.equipment:
                for slot, item_name in config.equipment.items():
                    item = await ItemService.get_item_by_name(item_name)
                    if item:
                        # First add to inventory, then equip
                        await InventoryService.add_item(
                            player_id=player.id,
                            item_id=item.id,
                            quantity=1
                        )
                        # Find the inventory slot and equip
                        inventory = await InventoryService.get_inventory(player.id)
                        for inv_item in inventory:
                            if inv_item.item_id == item.id:
                                await EquipmentService.equip_from_inventory(
                                    player_id=player.id,
                                    inventory_slot=inv_item.slot
                                )
                                break
            
            logger.info(
                "Test player created",
                extra={
                    "username": username,
                    "player_id": player.id,
                    "items_count": len(config.items) if config.items else 0,
                    "equipment_count": len(config.equipment) if config.equipment else 0
                }
            )
            
            return TestDataServiceResult.success_with_players(
                data=player,
                player_ids=[player.id],
                message=f"Test player {username} created successfully"
            )
            
        except Exception as e:
            logger.error(
                "Failed to create test player",
                extra={"config": config, "error": str(e)}
            )
            return TestDataServiceResult.failure(
                message=f"Failed to create test player: {str(e)}",
                error_code=ServiceErrorCodes.VALIDATION_ERROR
            )

    @staticmethod
    async def create_multiplayer_scenario(
        player_configs: List[PlayerConfig],
        ground_items: Optional[List[GroundItemConfig]] = None
    ) -> TestDataServiceResult[MultiplayerScenario]:
        """
        Create a complete multiplayer test scenario.
        
        Args:
            player_configs: List of player configurations
            ground_items: Optional ground items to create
            
        Returns:
            TestDataServiceResult with complete scenario
        """
        try:
            created_players = []
            created_player_ids = []
            
            # Create all players
            for config in player_configs:
                player_result = await TestDataService.create_test_player_with_items(
                    config=config
                )
                if player_result.success:
                    created_players.append(player_result.data)
                    created_player_ids.append(player_result.data.id)
                else:
                    # If any player creation fails, clean up and return error
                    await TestDataService.cleanup_test_players(created_player_ids)
                    return TestDataServiceResult.failure(
                        message=f"Failed to create player: {player_result.message}",
                        error_code=ServiceErrorCodes.VALIDATION_ERROR
                    )
            
            # Create ground items if specified
            created_ground_items = []
            if ground_items:
                for gi_config in ground_items:
                    item = await ItemService.get_item_by_name(gi_config.item_name)
                    if item:
                        ground_item_id = await GroundItemService.create_ground_item(
                            item_id=item.id,
                            map_id=gi_config.map_id,
                            x=gi_config.x,
                            y=gi_config.y,
                            quantity=gi_config.quantity,
                            dropped_by=gi_config.dropped_by_player_id
                        )
                        if ground_item_id:
                            created_ground_items.append({
                                "id": ground_item_id,
                                "item_name": gi_config.item_name,
                                "x": gi_config.x,
                                "y": gi_config.y,
                                "quantity": gi_config.quantity
                            })
            
            scenario = MultiplayerScenario(
                players=created_players,
                ground_items=created_ground_items,
                scenario_data={
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "player_count": len(created_players),
                    "ground_item_count": len(created_ground_items)
                }
            )
            
            logger.info(
                "Multiplayer scenario created",
                extra={
                    "player_count": len(created_players),
                    "ground_item_count": len(created_ground_items)
                }
            )
            
            return TestDataServiceResult.success_with_players(
                data=scenario,
                player_ids=created_player_ids,
                message=f"Multiplayer scenario with {len(created_players)} players created"
            )
            
        except Exception as e:
            logger.error(
                "Failed to create multiplayer scenario",
                extra={"error": str(e)}
            )
            return TestDataServiceResult.failure(
                message=f"Failed to create multiplayer scenario: {str(e)}",
                error_code=ServiceErrorCodes.VALIDATION_ERROR
            )

    @staticmethod
    async def cleanup_test_players(
        player_ids: List[int],
        cleanup_gsm: bool = True
    ) -> TestDataServiceResult[None]:
        """
        Clean up test players and their associated data.
        
        Args:
            player_ids: List of player IDs to clean up
            cleanup_gsm: Whether to clean up GSM state as well
            
        Returns:
            TestDataServiceResult indicating cleanup success
        """
        try:
            if cleanup_gsm:
                inv_mgr = get_inventory_manager()
                equip_mgr = get_equipment_manager()
                for player_id in player_ids:
                    # Clear player state from managers
                    await inv_mgr.clear_inventory(player_id)
                    await equip_mgr.clear_equipment(player_id)
            
            # Database cleanup would typically involve deleting the player records,
            # but for tests we might want to keep them for debugging
            # This can be implemented based on testing needs
            
            logger.info(
                "Test players cleaned up",
                extra={"player_ids": player_ids, "cleanup_gsm": cleanup_gsm}
            )
            
            return TestDataServiceResult.success_no_data(
                message=f"Cleaned up {len(player_ids)} test players"
            )
            
        except Exception as e:
            logger.error(
                "Failed to clean up test players",
                extra={"player_ids": player_ids, "error": str(e)}
            )
            return TestDataServiceResult.failure(
                message=f"Failed to clean up test players: {str(e)}",
                error_code=ServiceErrorCodes.VALIDATION_ERROR
            )