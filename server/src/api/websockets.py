"""
WebSocket router for real-time game communication.
"""

import json
import time
from datetime import datetime, timezone
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
from server.src.core.items import InventorySortType, EquipmentSlot
from server.src.models.player import Player
from server.src.models.item import PlayerInventory, PlayerEquipment
from server.src.models.skill import PlayerSkill, Skill
from server.src.services.map_service import map_manager
from server.src.services.inventory_service import InventoryService
from server.src.services.equipment_service import EquipmentService
from server.src.services.skill_service import SkillService
from server.src.services.ground_item_service import GroundItemService
from server.src.services.game_state_manager import get_game_state_manager
from server.src.services.authentication_service import AuthenticationService
from server.src.services.connection_service import ConnectionService
from server.src.services.movement_service import MovementService
from server.src.services.chat_service import ChatService
from server.src.services.player_service import PlayerService
from sqlalchemy.orm import selectinload
from common.src.protocol import (
    GameMessage,
    MessageType,
    Direction,
    MoveIntentPayload,
    PlayerDisconnectPayload,
    MoveInventoryItemPayload,
    SortInventoryPayload,
    DropItemPayload,
    EquipItemPayload,
    UnequipItemPayload,
    PickupItemPayload,
    OperationResultPayload,
    PlayerDiedPayload,
    PlayerRespawnPayload,
    ErrorPayload,
)
from server.src.game.game_loop import cleanup_disconnected_player, register_player_login

router = APIRouter()
manager = ConnectionManager()
logger = get_logger(__name__)


class OperationRateLimiter:
    """
    Rate limiter for inventory and equipment operations.
    Tracks last operation time per player per operation type.
    """

    def __init__(self):
        # {username: {operation_type: last_operation_time}}
        self._last_operation_times: Dict[str, Dict[str, float]] = {}

    def check_rate_limit(
        self, username: str, operation_type: str, cooldown: float
    ) -> bool:
        """
        Check if an operation is allowed based on rate limiting.

        Args:
            username: The player's username
            operation_type: Type of operation (e.g., "inventory", "equipment")
            cooldown: Minimum time between operations in seconds

        Returns:
            True if the operation is allowed, False if rate limited
        """
        current_time = time.time()

        if username not in self._last_operation_times:
            self._last_operation_times[username] = {}

        last_time = self._last_operation_times[username].get(operation_type, 0)

        if current_time - last_time < cooldown:
            return False

        self._last_operation_times[username][operation_type] = current_time
        return True

    def cleanup_player(self, username: str):
        """Remove rate limit tracking for a disconnected player."""
        if username in self._last_operation_times:
            del self._last_operation_times[username]


# Global rate limiter instance
operation_rate_limiter = OperationRateLimiter()


def create_death_broadcast_callback(valkey: GlideClient):
    """
    Create a broadcast callback for PLAYER_DIED and PLAYER_RESPAWN messages.
    
    This callback is passed to HpService.full_death_sequence() when a player dies.
    It broadcasts death/respawn messages to nearby players on the same map.
    
    Usage (when combat is implemented):
        damage_result = await HpService.deal_damage(db, valkey, username, damage)
        if damage_result.player_died:
            broadcast_callback = create_death_broadcast_callback(valkey)
            await HpService.full_death_sequence(db, valkey, username, broadcast_callback)
    
    Args:
        valkey: Valkey client for looking up player positions
        
    Returns:
        Async callback function(message_type, payload, username)
    """
    async def broadcast_callback(message_type: str, payload: dict, username: str):
        """Broadcast death/respawn messages to players on the same map."""
        # Get the map from the payload (death location or respawn location)
        map_id = payload.get("map_id")
        if not map_id:
            logger.warning(
                "No map_id in death/respawn payload",
                extra={"username": username, "message_type": message_type},
            )
            return
        
        # Create the appropriate message
        if message_type == "PLAYER_DIED":
            message = GameMessage(
                type=MessageType.PLAYER_DIED,
                payload=PlayerDiedPayload(**payload).model_dump(),
            )
        elif message_type == "PLAYER_RESPAWN":
            message = GameMessage(
                type=MessageType.PLAYER_RESPAWN,
                payload=PlayerRespawnPayload(**payload).model_dump(),
            )
        else:
            logger.warning(
                "Unknown message type for death broadcast",
                extra={"message_type": message_type, "username": username},
            )
            return
        
        # Broadcast to all players on the map
        packed_message = msgpack.packb(message.model_dump(), use_bin_type=True)
        if packed_message:
            await manager.broadcast_to_map(map_id, packed_message)
            logger.info(
                "Broadcast death/respawn message",
                extra={
                    "message_type": message_type,
                    "username": username,
                    "map_id": map_id,
                },
            )
    
    return broadcast_callback


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
    username: str, payload: dict, valkey: GlideClient, websocket: WebSocket, db: AsyncSession = None
):
    """
    Processes a SEND_CHAT_MESSAGE from a client using ChatService.
    """
    try:
        # Get player ID for service calls
        from server.src.models.player import Player
        from sqlalchemy.future import select
        
        query = select(Player.id).where(Player.username == username)
        result = await db.execute(query)
        player_id = result.scalar_one_or_none()
        
        if not player_id:
            logger.error(
                "Player not found for chat message",
                extra={"username": username}
            )
            return
            
        # Use ChatService to handle the message
        chat_result = await ChatService.handle_chat_message(
            db, player_id, username, payload, manager
        )
        
        if chat_result["success"]:
            logger.info(
                "Chat message processed via service",
                extra={
                    "username": username,
                    "channel": chat_result["channel"],
                    "recipient_count": len(chat_result.get("recipients", [])),
                    "message_id": chat_result.get("message_id")
                }
            )
        else:
            logger.warning(
                "Chat message rejected by service",
                extra={
                    "username": username,
                    "reason": chat_result.get("reason"),
                    "payload": payload
                }
            )
        
    except Exception as e:
        logger.error(
            "Error handling chat message via service",
            extra={
                "username": username,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )


async def handle_move_intent(
    username: str, payload: dict, valkey: GlideClient, websocket: WebSocket
):
    """
    Processes a MOVE_INTENT message from a client using MovementService.
    """
    try:
        move_payload = MoveIntentPayload(**payload)
        
        # Get player ID for service calls
        from server.src.models.player import Player
        from sqlalchemy.future import select
        from server.src.core.database import get_db
        
        async with get_db() as db:
            query = select(Player.id).where(Player.username == username)
            result = await db.execute(query)
            player_id = result.scalar_one_or_none()
            
            if not player_id:
                logger.error(
                    "Player not found for movement",
                    extra={"username": username}
                )
                return
                
            # Use MovementService to handle the movement
            movement_result = await MovementService.execute_movement(
                db, player_id, move_payload.direction
            )
            
            if movement_result["success"]:
                # Movement succeeded - send confirmation to player
                new_x = movement_result["new_position"]["x"]
                new_y = movement_result["new_position"]["y"]
                map_id = movement_result["new_position"]["map_id"]
                
                logger.debug(
                    "Player moved via service",
                    extra={
                        "username": username,
                        "direction": move_payload.direction,
                        "from_position": movement_result["old_position"],
                        "to_position": movement_result["new_position"],
                        "map_id": map_id,
                    },
                )

                # Track movement metrics
                metrics.track_player_movement(move_payload.direction.value)

                # Send position confirmation to the moving player only
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
                # Movement blocked or rate limited
                reason = movement_result.get("reason", "unknown")
                logger.debug(
                    f"Movement {reason}",
                    extra={
                        "username": username,
                        "direction": move_payload.direction,
                        "reason": reason,
                        "current_position": movement_result.get("current_position"),
                    },
                )

                # Send position correction to client if blocked by collision
                if reason == "blocked":
                    current_pos = movement_result["current_position"]
                    position_correction = {
                        "type": "GAME_STATE_UPDATE",
                        "payload": {
                            "entities": [
                                {
                                    "type": "player",
                                    "username": username,
                                    "x": current_pos["x"],
                                    "y": current_pos["y"],
                                    "map_id": current_pos["map_id"],
                                }
                            ]
                        },
                    }
                    packed_correction = msgpack.packb(position_correction, use_bin_type=True)
                    await websocket.send_bytes(packed_correction)

    except Exception as e:
        logger.error(
            "Error processing move intent via service",
            extra={
                "username": username,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
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
    username: str, payload: Dict, valkey: GlideClient, websocket: WebSocket, db: AsyncSession = None
):
    """
    Handle chunk data requests from clients using MapService for validation.

    Args:
        username: The player's username
        payload: Request payload containing map_id, center_x, center_y, radius
        valkey: Valkey client (legacy param, not used)
        websocket: WebSocket connection to send chunk data
        db: Database session for player data
    """
    try:
        # Get player ID for service calls
        from server.src.models.player import Player
        from sqlalchemy.future import select
        
        query = select(Player.id).where(Player.username == username)
        result = await db.execute(query)
        player_id = result.scalar_one_or_none()
        
        if not player_id:
            logger.warning(
                "Player not found for chunk request", extra={"username": username}
            )
            return

        # Use MapService to validate chunk request
        validation_result = await MapService.validate_chunk_request_security(
            player_id, 
            payload.get("map_id"),
            payload.get("center_x"),
            payload.get("center_y"), 
            payload.get("radius", 1)
        )
        
        if not validation_result["valid"]:
            logger.warning(
                "Chunk request failed validation",
                extra={
                    "username": username,
                    "reason": validation_result["reason"],
                    "payload": payload
                }
            )
            return
            
        # Extract validated parameters
        map_id = validation_result["validated_map_id"]
        center_x = validation_result["validated_center_x"] 
        center_y = validation_result["validated_center_y"]
        radius = validation_result["validated_radius"]

        # Get chunk data from map manager
        chunks = map_manager.get_chunks_for_player(map_id, center_x, center_y, radius)

        if chunks is None:
            # Send error response
            error_message = GameMessage(
                type=MessageType.ERROR,
                payload=ErrorPayload(message=f"Map '{map_id}' not found").model_dump(),
            )
            await websocket.send_bytes(
                msgpack.packb(error_message.model_dump(), use_bin_type=True)
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
                chunks=[chunk.model_dump() for chunk in chunk_data_list],
                player_x=center_x,
                player_y=center_y,
                radius=radius,
            ).model_dump(),
        )

        await websocket.send_bytes(
            msgpack.packb(chunk_response.model_dump(), use_bin_type=True)
        )
        metrics.track_websocket_message("CHUNK_DATA", "outbound")

        logger.debug(
            "Chunk data sent via service",
            extra={
                "username": username,
                "map_id": map_id,
                "center": (center_x, center_y),
                "radius": radius,
                "chunk_count": len(chunk_data_list),
            },
        )

    except Exception as e:
        logger.error(
            "Error handling chunk request via service",
            extra={
                "username": username,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )

        # Send error response to client
        error_message = GameMessage(
            type=MessageType.ERROR,
            payload=ErrorPayload(message="Failed to process chunk request").model_dump(),
        )
        await websocket.send_bytes(
            msgpack.packb(error_message.model_dump(), use_bin_type=True)
        )
            return

        player_data = {k.decode(): v.decode() for k, v in player_data_raw.items()}
        current_map = player_data.get("map_id", settings.DEFAULT_MAP)
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
                type=MessageType.ERROR,
                payload=ErrorPayload(message=f"Map '{map_id}' not found").model_dump(),
            )
            await websocket.send_bytes(
                msgpack.packb(error_message.model_dump(), use_bin_type=True)
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
                chunks=[chunk.model_dump() for chunk in chunk_data_list],
                player_x=center_x,
                player_y=center_y,
            ).model_dump(),
        )

        await websocket.send_bytes(
            msgpack.packb(chunk_response.model_dump(), use_bin_type=True)
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
            payload=ErrorPayload(message="Failed to process chunk request").model_dump(),
        )
        await websocket.send_bytes(
            msgpack.packb(error_message.model_dump(), use_bin_type=True)
        )


async def send_operation_result(
    websocket: WebSocket,
    operation: str,
    success: bool,
    message: str,
    data: Optional[Dict] = None,
):
    """Send an operation result back to the client."""
    result = GameMessage(
        type=MessageType.OPERATION_RESULT,
        payload=OperationResultPayload(
            operation=operation,
            success=success,
            message=message,
            data=data,
        ).model_dump(),
    )
    await websocket.send_bytes(
        msgpack.packb(result.model_dump(), use_bin_type=True)
    )


async def send_inventory_update(
    websocket: WebSocket, db: AsyncSession, player_id: int
):
    """Send full inventory state to the client."""
    gsm = get_game_state_manager()
    inventory = await InventoryService.get_inventory_response(db, player_id, state_manager=gsm)
    update = GameMessage(
        type=MessageType.INVENTORY_UPDATE,
        payload=inventory.model_dump(),
    )
    await websocket.send_bytes(
        msgpack.packb(update.model_dump(), use_bin_type=True)
    )


async def send_equipment_update(
    websocket: WebSocket, db: AsyncSession, player_id: int
):
    """Send full equipment state to the client."""
    gsm = get_game_state_manager()
    equipment = await EquipmentService.get_equipment_response(db, player_id, state_manager=gsm)
    update = GameMessage(
        type=MessageType.EQUIPMENT_UPDATE,
        payload=equipment.model_dump(),
    )
    await websocket.send_bytes(
        msgpack.packb(update.model_dump(), use_bin_type=True)
    )


async def send_stats_update(
    websocket: WebSocket, db: AsyncSession, player_id: int
):
    """Send aggregated equipment stats to the client."""
    gsm = get_game_state_manager()
    stats = await EquipmentService.get_total_stats(db, player_id, state_manager=gsm)
    update = GameMessage(
        type=MessageType.STATS_UPDATE,
        payload=stats.model_dump(),
    )
    await websocket.send_bytes(
        msgpack.packb(update.model_dump(), use_bin_type=True)
    )


async def handle_request_inventory(
    player_id: int, db: AsyncSession, websocket: WebSocket
):
    """Handle REQUEST_INVENTORY message."""
    try:
        await send_inventory_update(websocket, db, player_id)
    except Exception as e:
        logger.error(
            "Error handling inventory request",
            extra={"player_id": player_id, "error": str(e)},
        )
        await send_operation_result(
            websocket, "request_inventory", False, "Failed to get inventory"
        )


async def handle_move_inventory_item(
    player_id: int, payload: dict, db: AsyncSession, websocket: WebSocket
):
    """Handle MOVE_INVENTORY_ITEM message."""
    try:
        move_payload = MoveInventoryItemPayload(**payload)
        gsm = get_game_state_manager()
        result = await InventoryService.move_item(
            db, player_id, move_payload.from_slot, move_payload.to_slot, state_manager=gsm
        )

        await send_operation_result(
            websocket, "move_item", result.success, result.message
        )

        if result.success:
            await send_inventory_update(websocket, db, player_id)

    except Exception as e:
        logger.error(
            "Error handling move inventory item",
            extra={"player_id": player_id, "error": str(e)},
        )
        await send_operation_result(
            websocket, "move_item", False, "Failed to move item"
        )


async def handle_sort_inventory(
    player_id: int, payload: dict, db: AsyncSession, websocket: WebSocket
):
    """Handle SORT_INVENTORY message."""
    try:
        sort_payload = SortInventoryPayload(**payload)

        # Validate sort type
        try:
            sort_type = InventorySortType(sort_payload.sort_type)
        except ValueError:
            await send_operation_result(
                websocket, "sort_inventory", False, f"Invalid sort type: {sort_payload.sort_type}"
            )
            return

        result = await InventoryService.sort_inventory(db, player_id, sort_type)

        await send_operation_result(
            websocket,
            "sort_inventory",
            result.success,
            result.message,
            {"items_moved": result.items_moved, "stacks_merged": result.stacks_merged},
        )

        if result.success:
            await send_inventory_update(websocket, db, player_id)

    except Exception as e:
        logger.error(
            "Error handling sort inventory",
            extra={"player_id": player_id, "error": str(e)},
        )
        await send_operation_result(
            websocket, "sort_inventory", False, "Failed to sort inventory"
        )


async def handle_drop_item(
    player_id: int,
    payload: dict,
    db: AsyncSession,
    valkey: GlideClient,
    username: str,
    websocket: WebSocket,
):
    """Handle DROP_ITEM message."""
    try:
        drop_payload = DropItemPayload(**payload)

        # Get player position from valkey
        player_key = f"player:{username}"
        player_data_raw = await valkey.hgetall(player_key)
        player_data = {k.decode(): v.decode() for k, v in player_data_raw.items()}

        map_id = player_data.get("map_id", settings.DEFAULT_MAP)
        x = int(player_data.get("x", 0))
        y = int(player_data.get("y", 0))

        result = await GroundItemService.drop_from_inventory(
            player_id=player_id,
            inventory_slot=drop_payload.inventory_slot,
            map_id=map_id,
            x=x,
            y=y,
            quantity=drop_payload.quantity,
        )

        await send_operation_result(
            websocket,
            "drop_item",
            result.success,
            result.message,
            {"ground_item_id": result.ground_item_id} if result.ground_item_id else None,
        )

        if result.success:
            await send_inventory_update(websocket, db, player_id)

    except Exception as e:
        logger.error(
            "Error handling drop item",
            extra={"player_id": player_id, "error": str(e)},
        )
        await send_operation_result(
            websocket, "drop_item", False, "Failed to drop item"
        )


async def handle_request_equipment(
    player_id: int, db: AsyncSession, websocket: WebSocket
):
    """Handle REQUEST_EQUIPMENT message."""
    try:
        await send_equipment_update(websocket, db, player_id)
    except Exception as e:
        logger.error(
            "Error handling equipment request",
            extra={"player_id": player_id, "error": str(e)},
        )
        await send_operation_result(
            websocket, "request_equipment", False, "Failed to get equipment"
        )


async def handle_equip_item(
    player_id: int, payload: dict, db: AsyncSession, websocket: WebSocket
):
    """Handle EQUIP_ITEM message."""
    try:
        equip_payload = EquipItemPayload(**payload)
        gsm = get_game_state_manager()
        result = await EquipmentService.equip_from_inventory(
            db, player_id, equip_payload.inventory_slot, state_manager=gsm
        )

        await send_operation_result(
            websocket, "equip_item", result.success, result.message
        )

        if result.success:
            await send_inventory_update(websocket, db, player_id)
            await send_equipment_update(websocket, db, player_id)
            await send_stats_update(websocket, db, player_id)

    except Exception as e:
        logger.error(
            "Error handling equip item",
            extra={"player_id": player_id, "error": str(e)},
        )
        await send_operation_result(
            websocket, "equip_item", False, "Failed to equip item"
        )


async def handle_unequip_item(
    player_id: int, payload: dict, db: AsyncSession, websocket: WebSocket
):
    """Handle UNEQUIP_ITEM message."""
    try:
        unequip_payload = UnequipItemPayload(**payload)

        # Validate equipment slot
        try:
            slot = EquipmentSlot(unequip_payload.equipment_slot)
        except ValueError:
            await send_operation_result(
                websocket, "unequip_item", False, f"Invalid equipment slot: {unequip_payload.equipment_slot}"
            )
            return

        gsm = get_game_state_manager()
        result = await EquipmentService.unequip_to_inventory(db, player_id, slot, state_manager=gsm)

        await send_operation_result(
            websocket, "unequip_item", result.success, result.message
        )

        if result.success:
            await send_inventory_update(websocket, db, player_id)
            await send_equipment_update(websocket, db, player_id)
            await send_stats_update(websocket, db, player_id)

    except Exception as e:
        logger.error(
            "Error handling unequip item",
            extra={"player_id": player_id, "error": str(e)},
        )
        await send_operation_result(
            websocket, "unequip_item", False, "Failed to unequip item"
        )


async def handle_request_stats(
    player_id: int, db: AsyncSession, websocket: WebSocket
):
    """Handle REQUEST_STATS message."""
    try:
        await send_stats_update(websocket, db, player_id)
    except Exception as e:
        logger.error(
            "Error handling stats request",
            extra={"player_id": player_id, "error": str(e)},
        )
        await send_operation_result(
            websocket, "request_stats", False, "Failed to get stats"
        )


async def handle_pickup_item(
    player_id: int,
    payload: dict,
    db: AsyncSession,
    valkey: GlideClient,
    username: str,
    websocket: WebSocket,
):
    """Handle PICKUP_ITEM message."""
    try:
        pickup_payload = PickupItemPayload(**payload)

        # Get player position from valkey
        player_key = f"player:{username}"
        player_data_raw = await valkey.hgetall(player_key)
        player_data = {k.decode(): v.decode() for k, v in player_data_raw.items()}

        x = int(player_data.get("x", 0))
        y = int(player_data.get("y", 0))
        map_id = player_data.get("map_id", settings.DEFAULT_MAP)

        result = await GroundItemService.pickup_item(
            player_id=player_id,
            ground_item_id=pickup_payload.ground_item_id,
            player_x=x,
            player_y=y,
            player_map_id=map_id,
        )

        await send_operation_result(
            websocket,
            "pickup_item",
            result.success,
            result.message,
            {"inventory_slot": result.inventory_slot} if result.inventory_slot is not None else None,
        )

        if result.success:
            await send_inventory_update(websocket, db, player_id)

    except Exception as e:
        logger.error(
            "Error handling pickup item",
            extra={"player_id": player_id, "error": str(e)},
        )
        await send_operation_result(
            websocket, "pickup_item", False, "Failed to pick up item"
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
        map_id = player_data.get("map_id", settings.DEFAULT_MAP)
        current_hp = int(player_data.get("current_hp", 10))

        query = select(Player).where(Player.username == username)
        result = await db.execute(query)
        player = result.scalar_one_or_none()

        if player:
            player.x_coord = x_coord
            player.y_coord = y_coord
            player.map_id = map_id
            player.current_hp = current_hp
            await db.commit()
            logger.info(
                "Player data synced to database",
                extra={
                    "username": username,
                    "position": {"x": x_coord, "y": y_coord},
                    "map_id": map_id,
                    "current_hp": current_hp,
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

        # Check if player is banned
        if player.is_banned:
            logger.warning(
                "Banned player attempted WebSocket connection",
                extra={"username": username},
            )
            raise WebSocketDisconnect(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Account is banned",
            )

        # Check if player is timed out
        if player.timeout_until:
            # Handle both timezone-aware and naive datetimes (SQLite vs PostgreSQL)
            timeout_until = player.timeout_until
            if timeout_until.tzinfo is None:
                timeout_until = timeout_until.replace(tzinfo=timezone.utc)
            if timeout_until > datetime.now(timezone.utc):
                logger.warning(
                    "Timed out player attempted WebSocket connection",
                    extra={"username": username, "timeout_until": str(player.timeout_until)},
                )
                raise WebSocketDisconnect(
                    code=status.WS_1008_POLICY_VIOLATION,
                    reason=f"Account is timed out until {player.timeout_until.isoformat()}",
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

        # Calculate max HP for this player
        max_hp = await EquipmentService.get_max_hp(player.id)
        current_hp = player.current_hp

        # Ensure current HP doesn't exceed max HP (equipment might have changed)
        if current_hp > max_hp:
            current_hp = max_hp
            player.current_hp = current_hp
            await db.commit()

        # Initialize player connection state using service layer
        await ConnectionService.initialize_player_connection(
            db, player.id, username, validated_x, validated_y, validated_map, current_hp, max_hp
        )

        logger.info(
            "Player connected to WebSocket",
            extra={
                "username": username,
                "initial_position": {"x": validated_x, "y": validated_y},
                "map_id": validated_map,
                "current_hp": current_hp,
                "max_hp": max_hp,
                "player_id": player.id,
            },
        )

        await manager.connect(websocket, username, validated_map)
        
        # Register player login tick for staggered HP regeneration
        register_player_login(username)

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
                "player": {
                    "id": player.id,
                    "username": username,
                    "x": validated_x,
                    "y": validated_y,
                    "map_id": validated_map,
                    "current_hp": current_hp,
                    "max_hp": max_hp,
                },
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

        # Send existing players on this map to the new player using service layer
        existing_players_data = await ConnectionService.get_existing_players_on_map(
            db, validated_map, username
        )
        
        if existing_players_data:
            # Send existing players to new player
            existing_players_message = {
                "type": "GAME_STATE_UPDATE",
                "payload": {"entities": existing_players_data},
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
                await handle_chunk_request(username, message.payload, valkey, websocket, db)
                # Don't broadcast chunk requests to other players
                continue
            elif message.type == MessageType.SEND_CHAT_MESSAGE:
                await handle_chat_message(username, message.payload, valkey, websocket, db)
                # Don't broadcast chat messages through the general system
                continue

            # Inventory operations (with rate limiting)
            elif message.type == MessageType.REQUEST_INVENTORY:
                await handle_request_inventory(player.id, db, websocket)
                continue
            elif message.type == MessageType.MOVE_INVENTORY_ITEM:
                if not operation_rate_limiter.check_rate_limit(
                    username, "inventory", settings.INVENTORY_OPERATION_COOLDOWN
                ):
                    await send_operation_result(
                        websocket, "move_item", False, "Operation too fast, please wait"
                    )
                    continue
                await handle_move_inventory_item(player.id, message.payload, db, websocket)
                continue
            elif message.type == MessageType.SORT_INVENTORY:
                if not operation_rate_limiter.check_rate_limit(
                    username, "inventory", settings.INVENTORY_OPERATION_COOLDOWN
                ):
                    await send_operation_result(
                        websocket, "sort_inventory", False, "Operation too fast, please wait"
                    )
                    continue
                await handle_sort_inventory(player.id, message.payload, db, websocket)
                continue
            elif message.type == MessageType.DROP_ITEM:
                if not operation_rate_limiter.check_rate_limit(
                    username, "inventory", settings.INVENTORY_OPERATION_COOLDOWN
                ):
                    await send_operation_result(
                        websocket, "drop_item", False, "Operation too fast, please wait"
                    )
                    continue
                await handle_drop_item(player.id, message.payload, db, valkey, username, websocket)
                continue

            # Equipment operations (with rate limiting)
            elif message.type == MessageType.REQUEST_EQUIPMENT:
                await handle_request_equipment(player.id, db, websocket)
                continue
            elif message.type == MessageType.EQUIP_ITEM:
                if not operation_rate_limiter.check_rate_limit(
                    username, "equipment", settings.EQUIPMENT_OPERATION_COOLDOWN
                ):
                    await send_operation_result(
                        websocket, "equip_item", False, "Operation too fast, please wait"
                    )
                    continue
                await handle_equip_item(player.id, message.payload, db, websocket)
                continue
            elif message.type == MessageType.UNEQUIP_ITEM:
                if not operation_rate_limiter.check_rate_limit(
                    username, "equipment", settings.EQUIPMENT_OPERATION_COOLDOWN
                ):
                    await send_operation_result(
                        websocket, "unequip_item", False, "Operation too fast, please wait"
                    )
                    continue
                await handle_unequip_item(player.id, message.payload, db, websocket)
                continue
            elif message.type == MessageType.REQUEST_STATS:
                await handle_request_stats(player.id, db, websocket)
                continue

            # Ground item operations (with rate limiting - uses inventory cooldown)
            elif message.type == MessageType.PICKUP_ITEM:
                if not operation_rate_limiter.check_rate_limit(
                    username, "inventory", settings.INVENTORY_OPERATION_COOLDOWN
                ):
                    await send_operation_result(
                        websocket, "pickup_item", False, "Operation too fast, please wait"
                    )
                    continue
                await handle_pickup_item(player.id, message.payload, db, valkey, username, websocket)
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
            packed_message = msgpack.packb(message.model_dump(), use_bin_type=True)
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

            # Handle player disconnection using service layer
            await ConnectionService.handle_player_disconnect(
                db, username, player_map, manager, operation_rate_limiter
            )

            # Update metrics for active connections after disconnect
            total_connections = sum(
                len(conns) for conns in manager.connections_by_map.values()
            )
            websocket_connections_active.set(total_connections)
            players_online.set(total_connections)
