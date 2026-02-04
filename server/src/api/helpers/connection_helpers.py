"""
WebSocket connection initialization helpers.
"""

from server.src.core.logging_config import get_logger
from server.src.services.connection_service import ConnectionService
from server.src.services.player_service import PlayerService
from server.src.services.equipment_service import EquipmentService
from server.src.services.map_service import get_map_manager
from server.src.services.game_state import get_player_state_manager

logger = get_logger(__name__)


async def handle_player_disconnect(player_id: int, username: str) -> None:
    """
    Handle player disconnection cleanup.
    
    Args:
        player_id: Player's database ID
        username: Player's username
    """
    try:
        await PlayerService.logout_player(player_id)
        logger.info(
            "Player disconnected",
            extra={"player_id": player_id, "username": username}
        )
    except Exception as e:
        logger.error(
            "Error during player disconnect",
            extra={
                "player_id": player_id,
                "username": username,
                "error": str(e)
            }
        )


async def initialize_player_connection(username: str, player_id: int, valkey) -> None:
    """
    Initialize player connection with validation and state setup.
    
    Args:
        username: Player's username
        player_id: Player's database ID
        valkey: Valkey client for state management
    """
    try:
        # Load player data from database via service
        player = await PlayerService.get_player_by_id(player_id)
        if not player:
            raise Exception(f"Player {player_id} not found")
        
        # Get map manager for position validation
        map_manager = get_map_manager()
        
        # Validate and correct player position if needed
        validated_map, validated_x, validated_y = map_manager.validate_player_position(
            player.map_id, player.x, player.y
        )
        
        # Calculate max HP and validate current HP
        max_hp = await EquipmentService.get_max_hp(player.id)
        current_hp = min(player.current_hp, max_hp)
        
        # Initialize player in service layer and GSM
        await PlayerService.login_player(player.id)
        await ConnectionService.initialize_player_connection(
            player.id, username, validated_x, validated_y, validated_map, current_hp, max_hp
        )
        
        logger.debug(
            "Player connection initialized",
            extra={
                "username": username,
                "player_id": player_id,
                "position": {"x": validated_x, "y": validated_y, "map_id": validated_map},
            }
        )
        
    except Exception as e:
        logger.error(
            "Failed to initialize player connection",
            extra={
                "username": username,
                "player_id": player_id,
                "error": str(e)
            }
        )
        raise