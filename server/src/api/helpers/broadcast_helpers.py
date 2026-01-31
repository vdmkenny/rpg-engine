"""
Broadcast helper functions.

Handles welcome messages and player join/leave broadcasting.
"""

import traceback

import msgpack

from server.src.core.config import settings
from server.src.core.logging_config import get_logger
from server.src.services.game_state_manager import get_game_state_manager
from server.src.services.connection_service import ConnectionService

from common.src.protocol import (
    WSMessage,
    MessageType,
    PROTOCOL_VERSION,
)

logger = get_logger(__name__)


async def send_welcome_message(websocket, username: str, player_id: int) -> None:
    """
    Send EVENT_WELCOME message to newly connected player.
    
    Args:
        websocket: The WebSocket connection
        username: Player's username
        player_id: Player's database ID
    """
    try:
        gsm = get_game_state_manager()
        position = await gsm.get_player_position(player_id)
        hp_data = await gsm.get_player_hp(player_id)
        
        welcome_event = WSMessage(
            id=None,
            type=MessageType.EVENT_WELCOME,
            payload={
                "message": f"Welcome to RPG Engine, {username}!",
                "motd": "WebSocket Protocol - Enhanced with correlation IDs and structured responses",
                "player": {
                    "id": player_id,
                    "username": username,
                    "position": position,
                    "hp": hp_data,
                },
                "config": {
                    "move_cooldown": settings.MOVE_COOLDOWN,
                    "animation_duration": settings.ANIMATION_DURATION,
                    "protocol_version": PROTOCOL_VERSION
                }
            },
            version=PROTOCOL_VERSION
        )
        
        packed_message = msgpack.packb(welcome_event.model_dump(), use_bin_type=True)
        await websocket.send_bytes(packed_message)
        
        # Send welcome chat message
        welcome_chat = WSMessage(
            id=None,
            type=MessageType.EVENT_CHAT_MESSAGE,
            payload={
                "sender": "Server",
                "message": f"Welcome, {username}! You can chat by typing in the chat window.",
                "channel": "system",
                "sender_position": None
            },
            version=PROTOCOL_VERSION
        )
        
        packed_chat = msgpack.packb(welcome_chat.model_dump(), use_bin_type=True)
        await websocket.send_bytes(packed_chat)
        
        logger.info(
            "Welcome messages sent",
            extra={"username": username, "player_id": player_id}
        )
        
    except Exception as e:
        logger.error(
            "Error sending welcome message",
            extra={
                "username": username,
                "error": str(e),
                "error_type": type(e).__name__
            }
        )


async def handle_player_join_broadcast(
    websocket, 
    username: str, 
    player_id: int,
    connection_manager
) -> None:
    """
    Handle player join broadcasting to existing players.
    
    Args:
        websocket: The WebSocket connection
        username: Player's username
        player_id: Player's database ID
        connection_manager: ConnectionManager instance
    """
    try:
        gsm = get_game_state_manager()
        position = await gsm.get_player_position(player_id)
        
        if not position:
            logger.error(
                "Could not get player position for join broadcast", 
                extra={"player_id": player_id}
            )
            return
            
        map_id = position["map_id"]
        
        # Get existing players on this map
        existing_players_data = await ConnectionService.get_existing_players_on_map(
            map_id, username
        )
        
        if existing_players_data:
            # Send existing players to new player
            game_update = WSMessage(
                id=None,
                type=MessageType.EVENT_STATE_UPDATE,
                payload={
                    "entities": existing_players_data,
                    "removed_entities": [],
                    "map_id": map_id
                },
                version=PROTOCOL_VERSION
            )
            
            packed_update = msgpack.packb(game_update.model_dump(), use_bin_type=True)
            await websocket.send_bytes(packed_update)
        
        # Broadcast new player join to existing players
        player_joined = WSMessage(
            id=None,
            type=MessageType.EVENT_PLAYER_JOINED,
            payload={
                "player": {
                    "username": username,
                    "position": position,
                    "type": "player"
                }
            },
            version=PROTOCOL_VERSION
        )
        
        packed_join = msgpack.packb(player_joined.model_dump(), use_bin_type=True)
        
        # Get all connections on this map and filter out the joining player
        all_connections = await connection_manager.get_all_connections()
        other_players = [
            conn['username'] for conn in all_connections 
            if conn['map_id'] == map_id and conn['username'] != username
        ]
        
        if other_players:
            await connection_manager.broadcast_to_users(other_players, packed_join)
        
        logger.info(
            "Player join broadcast completed",
            extra={
                "username": username,
                "map_id": map_id,
                "existing_players": len(existing_players_data) if existing_players_data else 0
            }
        )
        
    except Exception as e:
        logger.error(
            "Error handling player join broadcast",
            extra={
                "username": username,
                "error": str(e),
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc()
            }
        )


async def broadcast_player_left(
    username: str,
    player_map: str | None,
    connection_manager
) -> None:
    """
    Broadcast player left event to remaining players.
    
    Args:
        username: Player's username
        player_map: Map player was on (may be None)
        connection_manager: ConnectionManager instance
    """
    if not player_map:
        return
        
    try:
        player_left = WSMessage(
            id=None,
            type=MessageType.EVENT_PLAYER_LEFT,
            payload={
                "username": username,
                "reason": "Disconnected"
            },
            version=PROTOCOL_VERSION
        )
        
        packed_left = msgpack.packb(player_left.model_dump(), use_bin_type=True)
        
        # Get all connections on this map and filter out the disconnecting player
        all_connections = await connection_manager.get_all_connections()
        other_players = [
            conn['username'] for conn in all_connections 
            if conn['map_id'] == player_map and conn['username'] != username
        ]
        
        if other_players:
            await connection_manager.broadcast_to_users(other_players, packed_left)
            
    except Exception as e:
        logger.error(
            "Error broadcasting player left",
            extra={
                "username": username,
                "error": str(e),
                "error_type": type(e).__name__
            }
        )
