"""
Connection lifecycle helper functions.

Handles player connection initialization and disconnection cleanup.
"""

import traceback

from fastapi import WebSocketDisconnect, status

from server.src.core.logging_config import get_logger
from server.src.services.map_service import map_manager
from server.src.services.player_service import PlayerService
from server.src.services.equipment_service import EquipmentService
from server.src.services.connection_service import ConnectionService

logger = get_logger(__name__)


async def initialize_player_connection(
    username: str, 
    player_id: int, 
    valkey
) -> None:
    """
    Initialize player connection state in GSM and services.
    
    Args:
        username: Player's username
        player_id: Player's database ID
        valkey: Valkey client instance
        
    Raises:
        WebSocketDisconnect: If initialization fails
    """
    try:
        player_service = PlayerService()
        player = await player_service.get_player_by_id(player_id)
        
        if not player:
            raise WebSocketDisconnect(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Player not found during initialization"
            )
        
        # Validate and correct player position if needed
        validated_map, validated_x, validated_y = map_manager.validate_player_position(
            player["map_id"], player["x_coord"], player["y_coord"]
        )
        
        # Calculate max HP and validate current HP
        max_hp = await EquipmentService.get_max_hp(player["id"])
        current_hp = min(player["current_hp"], max_hp)
        
        # Initialize player in service layer and GSM
        from server.src.models.player import Player
        player_model = Player()
        player_model.id = player["id"]
        player_model.username = username
        await PlayerService.login_player(player_model)
        await ConnectionService.initialize_player_connection(
            player["id"], username, validated_x, validated_y, validated_map, current_hp, max_hp
        )
        
        logger.debug(
            "Player connection initialized",
            extra={
                "username": username,
                "player_id": player_id,
                "position": {"x": validated_x, "y": validated_y, "map_id": validated_map},
                "hp": {"current": current_hp, "max": max_hp}
            }
        )
        
    except WebSocketDisconnect:
        raise
    except Exception as e:
        logger.error(
            "Error initializing player connection",
            extra={
                "username": username,
                "player_id": player_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc()
            }
        )
        raise WebSocketDisconnect(
            code=status.WS_1011_INTERNAL_ERROR,
            reason="Failed to initialize player connection"
        )


async def handle_player_disconnect(
    username: str,
    player_id: int | None,
    player_map: str | None,
    connection_manager,
    rate_limiter
) -> None:
    """
    Handle player disconnection cleanup.
    
    Args:
        username: Player's username
        player_id: Player's database ID (may be None if auth failed)
        player_map: Map player was on (may be None)
        connection_manager: ConnectionManager instance
        rate_limiter: RateLimiter instance
    """
    try:
        await ConnectionService.handle_player_disconnect(
            username, player_map, connection_manager, rate_limiter
        )
        
        logger.debug(
            "Player disconnection handled",
            extra={"username": username, "player_map": player_map}
        )
        
    except Exception as e:
        logger.error(
            "Error handling player disconnect",
            extra={
                "username": username,
                "error": str(e),
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc()
            }
        )
