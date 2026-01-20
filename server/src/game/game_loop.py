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
from server.src.services.game_state_manager import get_game_state_manager
from server.src.core.database import AsyncSessionLocal
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
# Contains both players and ground items in a nested structure:
# {username: {"players": {other_username: {...}}, "ground_items": {ground_item_id: {...}}}}
player_visible_state: Dict[str, Dict[str, Dict]] = {}

# Global tick counter (incremented every game tick)
_global_tick_counter: int = 0

# Track when each player connected (in tick count) for staggered HP regen
# {username: tick_count_at_login}
player_login_ticks: Dict[str, int] = {}


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
    Get player entities visible to a player based on chunk range.
    
    Args:
        player_x, player_y: Player's tile position
        all_entities: All player entities on the map
        player_username: The player's username (to exclude self)
        
    Returns:
        Dict of {username: entity_data} for visible player entities
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
                "type": "player",
                "username": entity_username,
                "x": entity_x,
                "y": entity_y,
                "current_hp": entity.get("current_hp", 0),
                "max_hp": entity.get("max_hp", 0),
            }
    
    return visible


def compute_entity_diff(
    current_visible: Dict[str, Dict[str, Any]], 
    last_visible: Dict[str, Dict[str, Any]]
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Compute the difference between current and last visible player state.
    
    Args:
        current_visible: Currently visible player entities
        last_visible: Previously visible player entities
        
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
        removed.append({"type": "player", "username": username})
    
    # Entities that may have moved or changed HP
    for username in current_keys & last_keys:
        current = current_visible[username]
        last = last_visible[username]
        if (
            current["x"] != last["x"] 
            or current["y"] != last["y"]
            or current.get("current_hp") != last.get("current_hp")
            or current.get("max_hp") != last.get("max_hp")
        ):
            updated.append(current)
    
    return {"added": added, "updated": updated, "removed": removed}


def compute_ground_item_diff(
    current_visible: Dict[int, Dict[str, Any]], 
    last_visible: Dict[int, Dict[str, Any]]
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Compute the difference between current and last visible ground item state.
    
    Args:
        current_visible: Currently visible ground items {id: entity_data}
        last_visible: Previously visible ground items {id: entity_data}
        
    Returns:
        Dict with "added", "updated", and "removed" entity lists
    """
    added = []
    updated = []
    removed = []
    
    current_keys = set(current_visible.keys())
    last_keys = set(last_visible.keys())
    
    # Ground items that appeared
    for item_id in current_keys - last_keys:
        added.append(current_visible[item_id])
    
    # Ground items that disappeared (picked up or despawned)
    for item_id in last_keys - current_keys:
        removed.append({"type": "ground_item", "id": item_id})
    
    # Ground items that changed (quantity changed due to partial pickup)
    for item_id in current_keys & last_keys:
        current = current_visible[item_id]
        last = last_visible[item_id]
        if current.get("quantity") != last.get("quantity"):
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
    player_login_ticks.pop(username, None)
    
    # Also remove this player from other players' visible player state
    for other_state in player_visible_state.values():
        players_dict = other_state.get("players", {})
        players_dict.pop(username, None)


def register_player_login(username: str) -> None:
    """Register a player's login tick for staggered HP regen."""
    player_login_ticks[username] = _global_tick_counter


async def game_loop(manager: ConnectionManager, valkey: GlideClient) -> None:
    """
    The main game loop with diff-based visibility broadcasting.
    
    Each player only receives updates about entities within their visible
    chunk range, and only when those entities have changed since the last tick.

    Args:
        manager: The connection manager.
        valkey: The Valkey client.
    """
    global _global_tick_counter
    tick_interval = 1 / settings.GAME_TICK_RATE
    hp_regen_interval = settings.HP_REGEN_INTERVAL_TICKS
    db_sync_interval = settings.DB_SYNC_INTERVAL_TICKS

    while True:
        loop_start_time = time.time()
        try:
            # Track game loop iteration
            game_loop_iterations_total.inc()
            
            # Increment global tick counter
            _global_tick_counter += 1

            # Periodic batch sync of dirty data to database
            if _global_tick_counter % db_sync_interval == 0:
                try:
                    gsm = get_game_state_manager()
                    await gsm.batch_ops.sync_all()
                except Exception as sync_error:
                    logger.error(
                        "Batch sync failed",
                        extra={
                            "error": str(sync_error),
                            "tick": _global_tick_counter,
                        },
                    )

            # Process each active map
            active_maps = list(manager.connections_by_map.keys())
            for map_id in active_maps:
                map_connections = manager.connections_by_map.get(map_id, {})
                if not map_connections:
                    continue
                    
                player_usernames = list(map_connections.keys())
                
                gsm = get_game_state_manager()
                
                # Fetch all player states for this map in a single batch operation
                all_players_data = await gsm.state_access.get_multiple_players_by_usernames(player_usernames)
                
                # Process player data and handle HP regeneration
                all_player_data: List[Dict[str, Any]] = []
                player_positions: Dict[str, Tuple[int, int]] = {}
                
                for username, data in all_players_data.items():
                    if data:
                        x = int(data.get("x", 0))
                        y = int(data.get("y", 0))
                        current_hp = int(data.get("current_hp", 10))
                        max_hp = int(data.get("max_hp", 10))
                        
                        # Calculate HP regeneration based on player login time
                        login_tick = player_login_ticks.get(username, _global_tick_counter)
                        ticks_since_login = _global_tick_counter - login_tick
                        should_regen = (
                            ticks_since_login > 0 
                            and ticks_since_login % hp_regen_interval == 0
                            and current_hp < max_hp
                        )
                        
                        if should_regen:
                            current_hp = min(current_hp + 1, max_hp)
                            await gsm.state_access.set_player_hp_by_username(username, current_hp)
                            logger.debug(
                                "HP regenerated",
                                extra={
                                    "username": username,
                                    "new_hp": current_hp,
                                    "max_hp": max_hp,
                                    "ticks_since_login": ticks_since_login,
                                },
                            )
                        
                        all_player_data.append({
                            "id": username,
                            "username": username,
                            "x": x,
                            "y": y,
                            "current_hp": current_hp,
                            "max_hp": max_hp,
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
                    
                    # Get player entities currently visible to this player
                    current_visible_players = get_visible_entities(
                        player_x, player_y, all_player_data, username
                    )
                    
                    # Get ground items visible to this player
                    # We need the player_id for loot protection check
                    player_key = f"player:{username}"
                    player_data = await valkey.hgetall(player_key)
                    player_id = int(player_data.get(b"player_id", b"0")) if player_data else None
                    
                    # Use GroundItemService for ground item visibility (proper architecture)
                    from ..services.ground_item_service import GroundItemService
                    visible_ground_items = await GroundItemService.get_visible_ground_items_raw(
                        player_id=player_id,
                        map_id=map_id,
                        center_x=player_x,
                        center_y=player_y,
                        tile_radius=32,  # Same as visibility range
                    )
                    
                    # Convert to dict keyed by ground item ID
                    current_visible_ground_items = {}
                    for item in visible_ground_items:
                        current_visible_ground_items[item["id"]] = {
                            "type": "ground_item",
                            "id": item["id"],
                            "item_id": item["item_id"],
                            "item_name": item["item_name"],
                            "display_name": item["display_name"],
                            "rarity": item["rarity"],
                            "x": item["x"],
                            "y": item["y"],
                            "quantity": item["quantity"],
                            "is_protected": item.get("is_protected", False),
                        }
                    
                    # Get last known visible state for this player
                    last_state = player_visible_state.get(username, {"players": {}, "ground_items": {}})
                    last_visible_players = last_state.get("players", {})
                    last_visible_ground_items = last_state.get("ground_items", {})
                    
                    # Compute diffs for players and ground items
                    player_diff = compute_entity_diff(current_visible_players, last_visible_players)
                    ground_item_diff = compute_ground_item_diff(current_visible_ground_items, last_visible_ground_items)
                    
                    # Combine diffs
                    combined_diff = {
                        "added": player_diff["added"] + ground_item_diff["added"],
                        "updated": player_diff["updated"] + ground_item_diff["updated"],
                        "removed": player_diff["removed"] + ground_item_diff["removed"],
                    }
                    
                    # Send diff update if there are changes
                    await send_diff_update(username, websocket, combined_diff)
                    
                    # Update stored visible state
                    player_visible_state[username] = {
                        "players": current_visible_players,
                        "ground_items": current_visible_ground_items,
                    }
                    
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
