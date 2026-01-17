"""
Game loop module for server tick updates.

Implements diff-based visibility broadcasting where each player only receives
updates about entities within their visible chunk range.
"""

import asyncio
import time
import msgpack
from typing import Dict, List, Optional, Set, Tuple, Any
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

# Default chunk size in tiles
CHUNK_SIZE = 16

# Visibility radius in chunks (1 = 3x3 grid of chunks around player)
VISIBILITY_RADIUS = 1

# Track player chunk positions for chunk updates
player_chunk_positions: Dict[str, Tuple[int, int]] = {}

# Track last known visible state per player for diff calculation
# {username: {other_username: {"x": int, "y": int}}}
player_visible_state: Dict[str, Dict[str, Dict[str, Any]]] = {}


def get_chunk_coordinates(x: int, y: int, chunk_size: int = CHUNK_SIZE) -> Tuple[int, int]:
    """Convert tile coordinates to chunk coordinates."""
    return (x // chunk_size, y // chunk_size)


def is_in_visible_range(
    player_x: int, player_y: int, target_x: int, target_y: int, 
    chunk_radius: int = VISIBILITY_RADIUS, chunk_size: int = CHUNK_SIZE
) -> bool:
    """
    Check if a target position is within the visible chunk range of a player.
    
    Args:
        player_x, player_y: Player's tile position
        target_x, target_y: Target entity's tile position
        chunk_radius: Number of chunks visible in each direction
        chunk_size: Size of chunks in tiles
        
    Returns:
        True if target is within visible range
    """
    visible_range = (chunk_radius + 1) * chunk_size
    return (abs(target_x - player_x) <= visible_range and 
            abs(target_y - player_y) <= visible_range)


def get_visible_entities(
    player_x: int, player_y: int, 
    all_entities: List[Dict[str, Any]], 
    player_username: str
) -> Dict[str, Dict[str, Any]]:
    """
    Get entities visible to a player based on chunk range.
    
    Args:
        player_x, player_y: Player's tile position
        all_entities: All entities on the map
        player_username: The player's username (to exclude self)
        
    Returns:
        Dict of {username: entity_data} for visible entities
    """
    visible = {}
    for entity in all_entities:
        entity_username = entity.get("id") or entity.get("username")
        if entity_username == player_username:
            continue
            
        entity_x = entity.get("x", 0)
        entity_y = entity.get("y", 0)
        
        if is_in_visible_range(player_x, player_y, entity_x, entity_y):
            visible[entity_username] = {
                "username": entity_username,
                "x": entity_x,
                "y": entity_y,
            }
    
    return visible


def compute_entity_diff(
    current_visible: Dict[str, Dict[str, Any]], 
    last_visible: Dict[str, Dict[str, Any]]
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Compute the difference between current and last visible state.
    
    Args:
        current_visible: Currently visible entities
        last_visible: Previously visible entities
        
    Returns:
        Dict with "added", "updated", and "removed" entity lists
    """
    added = []
    updated = []
    removed = []
    
    current_keys = set(current_visible.keys())
    last_keys = set(last_visible.keys())
    
    # Entities that entered visible range
    for username in current_keys - last_keys:
        added.append(current_visible[username])
    
    # Entities that left visible range
    for username in last_keys - current_keys:
        removed.append({"username": username})
    
    # Entities that may have moved
    for username in current_keys & last_keys:
        current = current_visible[username]
        last = last_visible[username]
        if current["x"] != last["x"] or current["y"] != last["y"]:
            updated.append(current)
    
    return {"added": added, "updated": updated, "removed": removed}


async def send_chunk_update_if_needed(
    username: str, map_id: str, x: int, y: int, websocket, chunk_size: int = CHUNK_SIZE
) -> None:
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
            chunks = map_manager.get_chunks_for_player(map_id, x, y, radius=VISIBILITY_RADIUS)

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
                    ).model_dump(),
                )

                await websocket.send_bytes(
                    msgpack.packb(chunk_message.model_dump(), use_bin_type=True)
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


async def send_diff_update(
    username: str, 
    websocket, 
    diff: Dict[str, List[Dict[str, Any]]]
) -> None:
    """
    Send a diff-based game state update to a specific player.
    
    Args:
        username: Player's username
        websocket: Player's WebSocket connection
        diff: The entity diff (added/updated/removed)
    """
    # Only send if there are actual changes
    if not diff["added"] and not diff["updated"] and not diff["removed"]:
        return
        
    try:
        # Combine added and updated into entities list, include removed separately
        entities = diff["added"] + diff["updated"]
        
        payload = {"entities": entities}
        if diff["removed"]:
            payload["removed"] = diff["removed"]
        
        update_message = GameMessage(
            type=MessageType.GAME_STATE_UPDATE,
            payload=payload,
        )
        
        packed = msgpack.packb(update_message.model_dump(), use_bin_type=True)
        if packed:
            await websocket.send_bytes(packed)
            
    except Exception as e:
        logger.error(
            "Error sending diff update", 
            extra={"username": username, "error": str(e)}
        )


def cleanup_disconnected_player(username: str) -> None:
    """Clean up state tracking for a disconnected player."""
    player_chunk_positions.pop(username, None)
    player_visible_state.pop(username, None)
    
    # Also remove this player from other players' visible state
    for other_state in player_visible_state.values():
        other_state.pop(username, None)


async def game_loop(manager: ConnectionManager, valkey: GlideClient) -> None:
    """
    The main game loop with diff-based visibility broadcasting.
    
    Each player only receives updates about entities within their visible
    chunk range, and only when those entities have changed since the last tick.

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

            # Process each active map
            active_maps = list(manager.connections_by_map.keys())
            for map_id in active_maps:
                map_connections = manager.connections_by_map.get(map_id, {})
                if not map_connections:
                    continue
                    
                player_usernames = list(map_connections.keys())
                
                # Fetch all player data for this map from Valkey
                all_player_data: List[Dict[str, Any]] = []
                player_positions: Dict[str, Tuple[int, int]] = {}
                
                for username in player_usernames:
                    player_key = f"player:{username}"
                    data = await valkey.hgetall(player_key)
                    if data:
                        x = int(data.get(b"x", b"0"))
                        y = int(data.get(b"y", b"0"))
                        
                        all_player_data.append({
                            "id": username,
                            "username": username,
                            "x": x,
                            "y": y,
                        })
                        player_positions[username] = (x, y)

                # For each connected player, compute and send their personalized diff
                for username in player_usernames:
                    if username not in player_positions:
                        continue
                        
                    websocket = map_connections.get(username)
                    if not websocket:
                        continue
                    
                    player_x, player_y = player_positions[username]
                    
                    # Get entities currently visible to this player
                    current_visible = get_visible_entities(
                        player_x, player_y, all_player_data, username
                    )
                    
                    # Get last known visible state for this player
                    last_visible = player_visible_state.get(username, {})
                    
                    # Compute diff
                    diff = compute_entity_diff(current_visible, last_visible)
                    
                    # Send diff update if there are changes
                    await send_diff_update(username, websocket, diff)
                    
                    # Update stored visible state
                    player_visible_state[username] = current_visible
                    
                    # Check if player needs chunk updates
                    await send_chunk_update_if_needed(
                        username, map_id, player_x, player_y, websocket
                    )
                    
                # Track broadcast for metrics
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
