"""
Broadcast helper functions.

Handles welcome messages and player join/leave broadcasting.
"""

import traceback
from typing import Optional

import msgpack

from server.src.core.config import settings
from server.src.core.logging_config import get_logger
from server.src.services.player_service import PlayerService
from server.src.services.hp_service import HpService
from server.src.services.connection_service import ConnectionService
from server.src.services.visual_state_service import VisualStateService

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
        # Use services for data access
        position = await PlayerService.get_player_position(player_id)
        current_hp, max_hp = await HpService.get_hp(player_id)
        
        # Get visual state (appearance + equipment)
        visual_data = await VisualStateService.get_player_visual_state(player_id)
        
        # Build player payload
        player_payload = {
            "id": player_id,
            "username": username,
            "position": position,
            "hp": {
                "current_hp": current_hp,
                "max_hp": max_hp
            },
        }
        
        # Add visual state if available
        if visual_data:
            player_payload["visual_hash"] = visual_data["visual_hash"]
            player_payload["visual_state"] = visual_data["visual_state"]
        
        welcome_event = WSMessage(
            id=None,
            type=MessageType.EVENT_WELCOME,
            payload={
                "message": settings.WELCOME_MESSAGE.format(username=username),
                "motd": settings.WELCOME_MOTD,
                "player": player_payload,
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
        
        logger.debug(
            "Welcome messages sent",
            extra={"username": username, "player_id": player_id}
        )
        
    except Exception as e:
        logger.error(
            "Error sending welcome message",
            extra={
                "username": username,
                "error": str(e),
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc()
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
        position = await PlayerService.get_player_position(player_id)
        
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
                    "player_id": player_id,
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
        other_player_ids = [
            conn['player_id'] for conn in all_connections 
            if conn['map_id'] == map_id and conn['player_id'] != player_id
        ]
        
        if other_player_ids:
            await connection_manager.broadcast_to_players(other_player_ids, packed_join)
        
        logger.debug(
            "Player join broadcast completed",
            extra={
                "username": username,
                "player_id": player_id,
                "map_id": map_id,
                "existing_players": len(existing_players_data) if existing_players_data else 0
            }
        )
        
    except Exception as e:
        logger.error(
            "Error handling player join broadcast",
            extra={
                "username": username,
                "player_id": player_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc()
            }
        )


async def broadcast_player_left(
    username: str,
    player_id: int,
    player_map: str | None,
    connection_manager
) -> None:
    """
    Broadcast player left event to remaining players.
    
    Args:
        username: Player's username (for display)
        player_id: Player's database ID (for identification)
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
                "player_id": player_id,
                "username": username,
                "reason": "Disconnected"
            },
            version=PROTOCOL_VERSION
        )
        
        packed_left = msgpack.packb(player_left.model_dump(), use_bin_type=True)
        
        # Get all connections on this map and filter out the disconnecting player
        all_connections = await connection_manager.get_all_connections()
        other_player_ids = [
            conn['player_id'] for conn in all_connections 
            if conn['map_id'] == player_map and conn['player_id'] != player_id
        ]
        
        if other_player_ids:
            await connection_manager.broadcast_to_players(other_player_ids, packed_left)
            
    except Exception as e:
        logger.error(
            "Error broadcasting player left",
            extra={
                "username": username,
                "player_id": player_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc()
            }
        )
