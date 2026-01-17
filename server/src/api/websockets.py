"""
WebSocket router for real-time game communication.
"""

import json
import time
from typing import Optional, Dict
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, status
from jose import JWTError, jwt
import msgpack
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from glide import GlideClient

from server.src.api.connection_manager import ConnectionManager
from server.src.core.config import settings
from server.src.core.database import get_valkey, get_db
from server.src.core.logging_config import get_logger
from server.src.core.metrics import (
    metrics,
    websocket_connections_active,
    players_online,
)
from server.src.models.player import Player
from server.src.services.map_service import map_manager
from common.src.protocol import GameMessage, MessageType, Direction, MoveIntentPayload, PlayerDisconnectPayload
from server.src.game.game_loop import cleanup_disconnected_player

router = APIRouter()
manager = ConnectionManager()
logger = get_logger(__name__)


async def get_token_from_ws(websocket: WebSocket) -> str:
    """
    Receives and decodes the authentication message from the client.
    """
    auth_bytes = await websocket.receive_bytes()
    try:
        auth_message = msgpack.unpackb(auth_bytes, raw=False)
        if auth_message.get("type") != MessageType.AUTHENTICATE:
            raise ValueError("Authentication message expected.")
        token = auth_message.get("payload", {}).get("token")
        if not token:
            raise ValueError("Token not provided in authentication message.")
        return token
    except (msgpack.exceptions.UnpackException, ValueError) as e:
        raise WebSocketDisconnect(code=status.WS_1008_POLICY_VIOLATION, reason=str(e))


async def handle_chat_message(
    username: str, payload: dict, valkey: GlideClient, websocket: WebSocket
):
    """
    Processes a SEND_CHAT_MESSAGE from a client and routes it appropriately.
    """
    try:
        channel = payload.get("channel", "local").lower()
        message = payload.get("message", "").strip()
        
        if not message:
            return
            
        logger.info(
            "Processing chat message",
            extra={
                "username": username,
                "channel": channel,
                "chat_content": message
            }
        )
        
        # Get sender's position for local chat range checking
        player_key = f"player:{username}"
        sender_pos_raw = await valkey.hgetall(player_key)
        sender_pos = {k.decode(): v.decode() for k, v in sender_pos_raw.items()}
        sender_x = int(sender_pos.get("x", 0))
        sender_y = int(sender_pos.get("y", 0))
        sender_map = sender_pos.get("map_id", "large_test_map")
        
        # Create the chat message to broadcast
        chat_response = GameMessage(
            type=MessageType.NEW_CHAT_MESSAGE,
            payload={
                "username": username,
                "message": message,
                "channel": channel,
                "timestamp": time.time()
            }
        )
        
        if channel == "global":
            # Broadcast to all connected players
            packed_message = msgpack.packb(chat_response.model_dump(), use_bin_type=True)
            await manager.broadcast_to_all(packed_message)
            
        elif channel == "local":
            # Broadcast to players within 5 chunks on same map
            local_range = 5 * 16  # 5 chunks = 5 * 16 tiles
            
            # Get all players and filter by distance and map
            connections = manager.get_all_connections()
            local_recipients = []
            
            for connection in connections:
                recipient_username = connection.get("username")
                if not recipient_username:
                    continue
                    
                # Get recipient position
                recipient_key = f"player:{recipient_username}"
                recipient_pos_raw = await valkey.hgetall(recipient_key)
                recipient_pos = {k.decode(): v.decode() for k, v in recipient_pos_raw.items()}
                recipient_x = int(recipient_pos.get("x", 0))
                recipient_y = int(recipient_pos.get("y", 0))
                recipient_map = recipient_pos.get("map_id", "large_test_map")
                
                # Check if on same map and within range (include sender too)
                if recipient_map == sender_map:
                    if recipient_username == username:
                        # Always include sender
                        local_recipients.append(recipient_username)
                    else:
                        # Check distance for other players
                        distance = max(abs(recipient_x - sender_x), abs(recipient_y - sender_y))
                        if distance <= local_range:
                            local_recipients.append(recipient_username)
            
            # Broadcast to local recipients (now includes sender)
            packed_message = msgpack.packb(chat_response.model_dump(), use_bin_type=True)
            await manager.broadcast_to_users(local_recipients, packed_message)
            
        elif channel == "dm":
            # For DM, we'd need target username in the payload
            # For now, just echo back that DMs aren't implemented yet
            dm_response = GameMessage(
                type=MessageType.NEW_CHAT_MESSAGE,
                payload={
                    "username": "System",
                    "message": "Direct messages not yet implemented",
                    "channel": "dm",
                    "timestamp": time.time()
                }
            )
            packed_message = msgpack.packb(dm_response.model_dump(), use_bin_type=True)
            await manager.send_personal_message(username, packed_message)
            
    except Exception as e:
        logger.error(
            "Error handling chat message",
            extra={"username": username, "error": str(e)},
            exc_info=True
        )


async def handle_move_intent(
    username: str, payload: dict, valkey: GlideClient, websocket: WebSocket
):
    """
    Processes a MOVE_INTENT message from a client.
    """
    import time

    try:
        move_payload = MoveIntentPayload(**payload)
        player_key = f"player:{username}"

        # Get current position and movement state
        current_pos_raw = await valkey.hgetall(player_key)
        current_pos = {k.decode(): v.decode() for k, v in current_pos_raw.items()}

        current_x = int(current_pos.get("x", 0))
        current_y = int(current_pos.get("y", 0))
        map_id = current_pos.get(
            "map_id", "large_test_map"
        )  # Default to large_test_map
        last_move_time = float(current_pos.get("last_move_time", 0))

        # Check movement cooldown (server-side rate limiting)
        current_time = time.time()
        move_cooldown = settings.MOVE_COOLDOWN

        if current_time - last_move_time < move_cooldown:
            # Movement too fast, ignore (anti-spam protection)
            logger.debug(
                "Movement rejected: too fast",
                extra={
                    "username": username,
                    "time_since_last_move": current_time - last_move_time,
                    "required_cooldown": move_cooldown,
                },
            )
            return

        # Calculate new position based on direction
        new_x, new_y = current_x, current_y
        if move_payload.direction == Direction.UP:
            new_y -= 1
        elif move_payload.direction == Direction.DOWN:
            new_y += 1
        elif move_payload.direction == Direction.LEFT:
            new_x -= 1
        elif move_payload.direction == Direction.RIGHT:
            new_x += 1

        # Validate movement with collision detection
        if map_manager.is_valid_move(map_id, current_x, current_y, new_x, new_y):
            # Movement is valid, update position and movement state
            await valkey.hset(
                player_key,
                {
                    "x": str(new_x),
                    "y": str(new_y),
                    "facing_direction": str(move_payload.direction.value),
                    "is_moving": "true",
                    "last_move_time": str(current_time),
                },
            )
            logger.debug(
                "Player moved",
                extra={
                    "username": username,
                    "direction": move_payload.direction,
                    "from_position": {"x": current_x, "y": current_y},
                    "to_position": {"x": new_x, "y": new_y},
                    "map_id": map_id,
                },
            )

            # Track movement metrics
            metrics.track_player_movement(move_payload.direction.value)

            # Send position confirmation to the moving player only
            # Other players will receive updates via the game loop's diff-based broadcasting
            position_update = {
                "type": "GAME_STATE_UPDATE",
                "payload": {
                    "entities": [
                        {
                            "type": "player",
                            "username": username,
                            "x": new_x,
                            "y": new_y,
                            "map_id": map_id,
                        }
                    ]
                },
            }
            packed_update = msgpack.packb(position_update, use_bin_type=True)
            if packed_update:
                await websocket.send_bytes(packed_update)
        else:
            # Movement blocked by collision
            logger.debug(
                "Movement blocked",
                extra={
                    "username": username,
                    "direction": move_payload.direction,
                    "blocked_position": {"x": new_x, "y": new_y},
                    "current_position": {"x": current_x, "y": current_y},
                    "map_id": map_id,
                },
            )

            # Send position correction to client
            position_correction = {
                "type": "GAME_STATE_UPDATE",
                "payload": {
                    "entities": [
                        {
                            "type": "player",
                            "username": username,
                            "x": current_x,
                            "y": current_y,
                            "map_id": map_id,
                        }
                    ]
                },
            }
            packed_correction = msgpack.packb(position_correction, use_bin_type=True)
            await websocket.send_bytes(packed_correction)

    except Exception as e:
        logger.error(
            "Error processing move intent",
            extra={
                "username": username,
                "error": str(e),
                "error_type": type(e).__name__,
                "payload": payload,
            },
        )
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")


async def handle_chunk_request(
    username: str, payload: Dict, valkey: GlideClient, websocket: WebSocket
):
    """
    Handle chunk data requests from clients.

    Args:
        username: The player's username
        payload: Request payload containing map_id, center_x, center_y, radius
        valkey: Valkey client for player data
        websocket: WebSocket connection to send chunk data
    """
    try:
        # Get player's current position from cache if not provided
        player_key = f"player:{username}"
        player_data_raw = await valkey.hgetall(player_key)

        if not player_data_raw:
            logger.warning(
                "No player data for chunk request", extra={"username": username}
            )
            return

        player_data = {k.decode(): v.decode() for k, v in player_data_raw.items()}
        current_map = player_data.get("map_id", "test_map")
        current_x = int(player_data.get("x", 0))
        current_y = int(player_data.get("y", 0))

        # Use provided coordinates or fall back to current position
        center_x = payload.get("center_x", current_x)
        center_y = payload.get("center_y", current_y)
        map_id = payload.get("map_id", current_map)
        radius = payload.get("radius", 1)

        # Security: Only allow chunk requests for the player's current map
        if map_id != current_map:
            logger.warning(
                "Player requested chunks for different map",
                extra={
                    "username": username,
                    "requested_map": map_id,
                    "current_map": current_map,
                },
            )
            return

        # Security: Only allow chunk requests within reasonable distance from player
        # Maximum allowed distance: 5 chunks (80 tiles) in any direction
        max_distance = 5 * 16  # 5 chunks * 16 tiles per chunk
        distance_x = abs(center_x - current_x)
        distance_y = abs(center_y - current_y)

        if distance_x > max_distance or distance_y > max_distance:
            logger.warning(
                "Player requested chunks too far from position",
                extra={
                    "username": username,
                    "current_pos": (current_x, current_y),
                    "requested_pos": (center_x, center_y),
                    "distance": (distance_x, distance_y),
                    "max_allowed": max_distance,
                },
            )
            return

        # Limit radius to prevent abuse
        radius = min(radius, 2)  # Max 2 chunks radius (5x5 chunk grid)

        # Get chunk data from map manager
        chunks = map_manager.get_chunks_for_player(map_id, center_x, center_y, radius)

        if chunks is None:
            # Send error response
            error_message = GameMessage(
                type=MessageType.ERROR, payload={"message": f"Map '{map_id}' not found"}
            )
            await websocket.send_bytes(
                msgpack.packb(error_message.dict(), use_bin_type=True)
            )
            return

        # Convert chunks to protocol format
        from common.src.protocol import ChunkData, ChunkDataPayload, TileData

        chunk_data_list = []
        for chunk in chunks:
            # Convert tile data to protocol format
            protocol_tiles = []
            for row in chunk["tiles"]:
                protocol_row = []
                for tile in row:
                    protocol_row.append(
                        TileData(
                            gid=tile["gid"], 
                            properties=tile["properties"],
                            layers=tile.get("layers", [])  # Include multi-layer data
                        )
                    )
                protocol_tiles.append(protocol_row)

            chunk_data_list.append(
                ChunkData(
                    chunk_x=chunk["chunk_x"],
                    chunk_y=chunk["chunk_y"],
                    tiles=protocol_tiles,
                    width=chunk["width"],
                    height=chunk["height"],
                )
            )

        # Send chunk data response
        chunk_response = GameMessage(
            type=MessageType.CHUNK_DATA,
            payload=ChunkDataPayload(
                map_id=map_id,
                chunks=[chunk.dict() for chunk in chunk_data_list],
                player_x=center_x,
                player_y=center_y,
            ).dict(),
        )

        await websocket.send_bytes(
            msgpack.packb(chunk_response.dict(), use_bin_type=True)
        )
        metrics.track_websocket_message("CHUNK_DATA", "outbound")

        logger.debug(
            "Sent chunk data to client",
            extra={
                "username": username,
                "map_id": map_id,
                "center": f"({center_x}, {center_y})",
                "radius": radius,
                "chunk_count": len(chunk_data_list),
            },
        )

    except Exception as e:
        logger.error(
            "Error handling chunk request",
            extra={"username": username, "payload": payload, "error": str(e), "error_type": type(e).__name__},
            exc_info=True,
        )
        # Send error response
        error_message = GameMessage(
            type=MessageType.ERROR,
            payload={"message": "Failed to process chunk request"},
        )
        await websocket.send_bytes(
            msgpack.packb(error_message.dict(), use_bin_type=True)
        )


async def sync_player_to_db(username: str, valkey: GlideClient, db: AsyncSession):
    """
    Synchronizes a player's data from Valkey back to the PostgreSQL database.
    """
    player_key = f"player:{username}"
    player_data_raw = await valkey.hgetall(player_key)
    player_data = {k.decode(): v.decode() for k, v in player_data_raw.items()}

    if not player_data:
        logger.debug("No player data in cache to sync", extra={"username": username})
        return

    try:
        x_coord = int(player_data.get("x", 0))
        y_coord = int(player_data.get("y", 0))
        map_id = player_data.get("map_id", "test_map")  # Use string map ID directly

        query = select(Player).where(Player.username == username)
        result = await db.execute(query)
        player = result.scalar_one_or_none()

        if player:
            player.x_coord = x_coord
            player.y_coord = y_coord
            player.map_id = map_id
            await db.commit()
            logger.info(
                "Player data synced to database",
                extra={
                    "username": username,
                    "position": {"x": x_coord, "y": y_coord},
                    "map_id": map_id,
                },
            )
        else:
            logger.warning(
                "Player not found in database for syncing", extra={"username": username}
            )

    except (ValueError, TypeError) as e:
        logger.error(
            "Error processing player data from cache",
            extra={"username": username, "error": str(e), "player_data": player_data},
        )
    except Exception as e:
        logger.error(
            "Unexpected error during database sync",
            extra={"username": username, "error": str(e)},
        )


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    valkey: GlideClient = Depends(get_valkey),
    db: AsyncSession = Depends(get_db),
):
    """
    The main WebSocket endpoint for real-time communication.
    - Authenticates the user.
    - Loads player data from the database into Valkey.
    - Manages the WebSocket connection.
    - Handles incoming messages (e.g., move intents).
    """
    username: Optional[str] = None
    connection_start_time = None
    try:
        # Accept the WebSocket connection first
        await websocket.accept()
        metrics.track_websocket_connection("accepted")
        connection_start_time = time.time()

        token = await get_token_from_ws(websocket)
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.ALGORITHM]
        )

        sub = payload.get("sub")
        if sub is None:
            raise WebSocketDisconnect(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Invalid token: sub missing",
            )
        username = sub
        assert username is not None

        # Load player data from DB
        query = select(Player).where(Player.username == username)
        result = await db.execute(query)
        player = result.scalar_one_or_none()

        if not player:
            raise WebSocketDisconnect(
                code=status.WS_1008_POLICY_VIOLATION, reason="Player not found"
            )

        # Validate player position and use spawn if invalid
        validated_map, validated_x, validated_y = map_manager.validate_player_position(
            player.map_id, player.x_coord, player.y_coord
        )

        # Update database if position was corrected
        if (
            validated_map != player.map_id
            or validated_x != player.x_coord
            or validated_y != player.y_coord
        ):

            logger.info(
                "Player position corrected",
                extra={
                    "username": username,
                    "original_position": {
                        "map_id": player.map_id,
                        "x": player.x_coord,
                        "y": player.y_coord,
                    },
                    "corrected_position": {
                        "map_id": validated_map,
                        "x": validated_x,
                        "y": validated_y,
                    },
                },
            )

            player.map_id = validated_map
            player.x_coord = validated_x
            player.y_coord = validated_y
            await db.commit()

        player_key = f"player:{username}"
        await valkey.hset(
            player_key,
            {
                "x": str(validated_x),
                "y": str(validated_y),
                "map_id": validated_map,
                "facing_direction": "DOWN",  # Default facing direction
                "is_moving": "false",
                "last_move_time": "0",
            },
        )
        logger.info(
            "Player connected to WebSocket",
            extra={
                "username": username,
                "initial_position": {"x": validated_x, "y": validated_y},
                "map_id": validated_map,
            },
        )

        await manager.connect(websocket, username, validated_map)

        # Update metrics for active connections
        total_connections = sum(
            len(conns) for conns in manager.connections_by_map.values()
        )
        websocket_connections_active.set(total_connections)
        players_online.set(total_connections)

        # Track players by map
        map_player_count = len(manager.connections_by_map.get(validated_map, {}))
        metrics.set_players_by_map(validated_map, map_player_count)

        # Acknowledge successful authentication and send player position
        welcome_message = GameMessage(
            type=MessageType.WELCOME,
            payload={
                "message": f"Welcome {username}!",
                "player": {"username": username, "x": validated_x, "y": validated_y, "map_id": validated_map},
                "config": {
                    "move_cooldown": settings.MOVE_COOLDOWN,
                    "animation_duration": settings.ANIMATION_DURATION,
                },
            },
        )
        await websocket.send_bytes(
            msgpack.packb(welcome_message.model_dump(), use_bin_type=True)
        )
        metrics.track_websocket_message("WELCOME", "outbound")
        
        # Send a welcome chat message to the new player
        welcome_chat = GameMessage(
            type=MessageType.NEW_CHAT_MESSAGE,
            payload={
                "username": "Server",
                "message": f"Welcome to the game, {username}! You can chat by clicking in the chat window at the bottom.",
                "channel": "local",
                "timestamp": time.time()
            }
        )
        await websocket.send_bytes(
            msgpack.packb(welcome_chat.model_dump(), use_bin_type=True)
        )

        # Send existing players on this map to the new player
        existing_players = []
        for other_username in manager.connections_by_map.get(validated_map, {}):
            if other_username != username:  # Don't include self
                other_player_key = f"player:{other_username}"
                other_pos_raw = await valkey.hgetall(other_player_key)
                if other_pos_raw:
                    other_pos = {
                        k.decode(): v.decode() for k, v in other_pos_raw.items()
                    }
                    existing_players.append(
                        {
                            "type": "player",
                            "username": other_username,
                            "x": int(other_pos.get("x", 0)),
                            "y": int(other_pos.get("y", 0)),
                            "map_id": other_pos.get("map_id", validated_map),
                        }
                    )

        if existing_players:
            # Send existing players to new player
            existing_players_message = {
                "type": "GAME_STATE_UPDATE",
                "payload": {"entities": existing_players},
            }
            packed_existing = msgpack.packb(existing_players_message, use_bin_type=True)
            if packed_existing:
                await websocket.send_bytes(packed_existing)

        # Notify existing players about the new player
        new_player_message = {
            "type": "GAME_STATE_UPDATE",
            "payload": {
                "entities": [
                    {
                        "type": "player",
                        "username": username,
                        "x": validated_x,
                        "y": validated_y,
                        "map_id": validated_map,
                    }
                ]
            },
        }
        packed_new_player = msgpack.packb(new_player_message, use_bin_type=True)
        if packed_new_player:
            # Send to all other players on the same map (exclude the new player)
            for other_username, other_websocket in list(manager.connections_by_map.get(
                validated_map, {}
            ).items()):
                if other_username != username:
                    try:
                        await other_websocket.send_bytes(packed_new_player)
                    except Exception:
                        # Ignore errors sending to disconnected/broken connections
                        # They will be cleaned up by their own disconnect handler
                        pass

        # Main message loop
        while True:
            data = await websocket.receive_bytes()
            message = GameMessage(**msgpack.unpackb(data, raw=False))

            # Track incoming message
            metrics.track_websocket_message(message.type.value, "inbound")

            if message.type == MessageType.MOVE_INTENT:
                await handle_move_intent(username, message.payload, valkey, websocket)
            elif message.type == MessageType.REQUEST_CHUNKS:
                await handle_chunk_request(username, message.payload, valkey, websocket)
                # Don't broadcast chunk requests to other players
                continue
            elif message.type == MessageType.SEND_CHAT_MESSAGE:
                await handle_chat_message(username, message.payload, valkey, websocket)
                # Don't broadcast chat messages through the general system
                continue

            # For now, broadcast every message to all clients on the same map
            # This will be replaced by a proper game state update loop
            logger.debug(
                "Broadcasting message to map",
                extra={
                    "username": username,
                    "map_id": validated_map,
                    "message_type": message.type.value,
                },
            )
            packed_message = msgpack.packb(message.dict(), use_bin_type=True)
            if packed_message:
                await manager.broadcast_to_map(validated_map, packed_message)
                metrics.track_websocket_message(message.type.value, "broadcast")

    except WebSocketDisconnect as e:
        logger.info(
            "Client disconnected",
            extra={"username": username, "reason": e.reason or "Normal disconnect"},
        )
        metrics.track_websocket_connection("disconnected")
        # If we raised WebSocketDisconnect ourselves (e.g., auth failure), close the connection
        if e.code and e.code != 1000:
            try:
                await websocket.close(code=e.code, reason=e.reason or "")
            except Exception:
                pass  # Already closed
    except JWTError:
        logger.warning("JWT validation failed for WebSocket connection")
        metrics.track_websocket_connection("auth_failed")
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token"
        )
    except Exception as e:
        logger.error(
            "Unexpected error in WebSocket handler",
            extra={"username": username, "error": str(e), "error_type": type(e).__name__},
            exc_info=True,
        )
        metrics.track_websocket_connection("error")
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
    finally:
        # Track connection duration if we have the start time
        if connection_start_time:
            from server.src.core.metrics import websocket_connection_duration_seconds

            duration = time.time() - connection_start_time
            websocket_connection_duration_seconds.observe(duration)

        if username:
            # Get the player's map before disconnection
            player_map = manager.client_to_map.get(username)

            # Sync data to DB and purge from Valkey on disconnect
            await sync_player_to_db(username, valkey, db)
            await valkey.delete(f"player:{username}")
            logger.debug("Player cache purged", extra={"username": username})

            # Notify other players on the same map about player leaving
            if player_map:
                disconnect_message = GameMessage(
                    type=MessageType.PLAYER_DISCONNECT,
                    payload=PlayerDisconnectPayload(username=username).model_dump(),
                )
                packed_disconnect = msgpack.packb(disconnect_message.model_dump(), use_bin_type=True)
                if packed_disconnect:
                    for other_websocket in manager.connections_by_map.get(
                        player_map, {}
                    ).values():
                        try:
                            await other_websocket.send_bytes(packed_disconnect)
                        except Exception:
                            # Ignore errors sending to other disconnecting clients
                            pass

            manager.disconnect(username)
            cleanup_disconnected_player(username)
            logger.info("Client disconnected and removed", extra={"username": username})

            # Update metrics for active connections after disconnect
            total_connections = sum(
                len(conns) for conns in manager.connections_by_map.values()
            )
            websocket_connections_active.set(total_connections)
            players_online.set(total_connections)
