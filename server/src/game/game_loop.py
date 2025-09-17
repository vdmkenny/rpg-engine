"""
Game loop module for server tick updates.
"""

import asyncio
import time
import msgpack
from typing import Tuple
from glide import GlideClient

from server.src.api.connection_manager import ConnectionManager
from server.src.core.config import settings
from server.src.core.logging_config import get_logger
from server.src.core.metrics import (
    game_loop_iterations_total,
    game_loop_duration_seconds,
    game_state_broadcasts_total,
)
from server.src.services.map_service import get_map_manager
from common.src.protocol import (
    GameMessage,
    MessageType,
    GameStateUpdatePayload,
    ChunkDataPayload,
    ChunkData,
    TileData,
)

logger = get_logger(__name__)

# Track player chunk positions to detect when they need updates
player_chunk_positions = {}  # {username: (chunk_x, chunk_y)}


def get_chunk_coordinates(x: int, y: int, chunk_size: int = 16) -> Tuple[int, int]:
    """Convert tile coordinates to chunk coordinates."""
    return (x // chunk_size, y // chunk_size)


async def send_chunk_update_if_needed(
    username: str, map_id: str, x: int, y: int, websocket, chunk_size: int = 16
):
    """
    Send chunk data if player moved to a new chunk.

    Args:
        username: Player's username
        map_id: Current map ID
        x, y: Player's current tile position
        websocket: Player's WebSocket connection
        chunk_size: Size of chunks in tiles
    """
    try:
        current_chunk = get_chunk_coordinates(x, y, chunk_size)
        last_chunk = player_chunk_positions.get(username)

        # Send chunks if player is new or moved to different chunk
        if last_chunk != current_chunk:
            map_manager = get_map_manager()
            chunks = map_manager.get_chunks_for_player(map_id, x, y, radius=1)

            if chunks:
                # Convert to protocol format
                chunk_data_list = []
                for chunk in chunks:
                    protocol_tiles = []
                    for row in chunk["tiles"]:
                        protocol_row = []
                        for tile in row:
                            protocol_row.append(
                                TileData(gid=tile["gid"], properties=tile["properties"])
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

                # Send chunk data
                chunk_message = GameMessage(
                    type=MessageType.CHUNK_DATA,
                    payload=ChunkDataPayload(
                        map_id=map_id, chunks=chunk_data_list, player_x=x, player_y=y
                    ).dict(),
                )

                await websocket.send_bytes(
                    msgpack.packb(chunk_message.dict(), use_bin_type=True)
                )

                # Update tracked position
                player_chunk_positions[username] = current_chunk

                logger.debug(
                    "Sent automatic chunk update",
                    extra={
                        "username": username,
                        "old_chunk": last_chunk,
                        "new_chunk": current_chunk,
                        "chunk_count": len(chunk_data_list),
                    },
                )

    except Exception as e:
        logger.error(
            "Error sending chunk update", extra={"username": username, "error": str(e)}
        )


async def game_loop(manager: ConnectionManager, valkey: GlideClient):
    """
    The main game loop.

    Args:
        manager: The connection manager.
        valkey: The Valkey client.
    """
    tick_interval = 1 / settings.GAME_TICK_RATE

    while True:
        loop_start_time = time.time()
        try:
            # Track game loop iteration
            game_loop_iterations_total.inc()

            # --- Game State Broadcasting ---
            active_maps = list(manager.connections_by_map.keys())
            for map_id in active_maps:
                player_keys = [
                    f"player:{username}"
                    for username in manager.connections_by_map[map_id].keys()
                ]
                if not player_keys:
                    continue

                # Get all player data for the current map and check for chunk updates
                all_player_data = []
                for player_key in player_keys:
                    data = await valkey.hgetall(player_key)
                    if data:
                        # Extract username from key
                        username = player_key.split(":")[1]
                        x = int(data.get(b"x", b"0"))
                        y = int(data.get(b"y", b"0"))

                        all_player_data.append(
                            {
                                "id": username,
                                "x": x,
                                "y": y,
                            }
                        )

                        # Check if this player needs chunk updates
                        if username in manager.connections_by_map[map_id]:
                            websocket = manager.connections_by_map[map_id][username]
                            await send_chunk_update_if_needed(
                                username, map_id, x, y, websocket
                            )

                # Create and broadcast game state update
                game_state_update = GameMessage(
                    type=MessageType.GAME_STATE_UPDATE,
                    payload=GameStateUpdatePayload(entities=all_player_data),
                )
                packed_message = msgpack.packb(
                    game_state_update.dict(), use_bin_type=True
                )
                if packed_message:
                    await manager.broadcast_to_map(map_id, packed_message)
                    game_state_broadcasts_total.labels(map_id=map_id).inc()

            # Track loop duration
            loop_duration = time.time() - loop_start_time
            game_loop_duration_seconds.observe(loop_duration)

            await asyncio.sleep(tick_interval)

        except Exception as e:
            logger.error(
                "Error in game loop",
                extra={"error": str(e), "tick_interval": tick_interval},
            )
            # Avoid rapid-fire loops on persistent errors
            await asyncio.sleep(1)
