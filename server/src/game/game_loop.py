"""
Game loop module for server tick updates.

Implements diff-based visibility broadcasting where each player only receives
updates about entities within their visible chunk range.
"""

import asyncio
import time
import traceback
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
from server.src.services.visibility_service import get_visibility_service
from server.src.core.database import AsyncSessionLocal
from common.src.protocol import (
    WSMessage,
    MessageType,
    GameUpdateEventPayload,
)

logger = get_logger(__name__)

# Default chunk size in tiles
CHUNK_SIZE = 16

# Visibility radius in chunks (1 = 3x3 grid of chunks around player)
VISIBILITY_RADIUS = 1

# Track player chunk positions for chunk updates
player_chunk_positions: Dict[str, Tuple[int, int]] = {}

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


def get_visible_npc_entities(
    player_x: int, player_y: int,
    all_entity_instances: List[Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    """
    Get NPC/monster entities visible to a player based on chunk range.
    
    Args:
        player_x, player_y: Player's tile position
        all_entity_instances: All entity instances on the map
        
    Returns:
        Dict of {entity_key: entity_data} for visible entities
    """
    from server.src.core.entities import EntityID
    
    visible = {}
    for entity in all_entity_instances:
        entity_state = entity.get("state", "idle")
        
        # Show entities in "dying" state (10-tick death animation)
        # Skip entities fully despawned (state == "dead")
        if entity_state == "dead":
            continue
            
        entity_x = int(entity.get("x", 0))
        entity_y = int(entity.get("y", 0))
        
        if is_in_visible_range(player_x, player_y, entity_x, entity_y):
            entity_id = entity.get("id")
            entity_name = entity.get("entity_name", "")
            
            # Get entity definition for display name and behavior
            entity_enum = EntityID.from_name(entity_name)
            display_name = entity_name
            behavior_type = "PASSIVE"
            sprite_info = ""
            is_attackable = True
            
            if entity_enum:
                entity_def = entity_enum.value
                display_name = entity_def.display_name
                behavior_type = entity_def.behavior.name
                sprite_info = ""  # Empty for now, will be populated later
                is_attackable = entity_def.is_attackable and entity_state != "dying"  # Can't attack dying entities
            else:
                is_attackable = entity_state != "dying"  # Can't attack dying entities
            
            visible[f"entity_{entity_id}"] = {
                "type": "entity",
                "id": entity_id,
                "entity_name": entity_name,
                "display_name": display_name,
                "behavior_type": behavior_type,
                "sprite_info": sprite_info,
                "x": entity_x,
                "y": entity_y,
                "current_hp": int(entity.get("current_hp", 0)),
                "max_hp": int(entity.get("max_hp", 0)),
                "state": entity_state,
                "is_attackable": is_attackable,
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


async def _process_auto_attacks(
    gsm,
    manager: ConnectionManager,
    tick_counter: int
) -> None:
    """
    Process all players in combat and execute auto-attacks.
    
    Called every game tick (20 TPS = 50ms per tick).
    
    For each player in combat:
    1. Check if enough ticks passed (attack_speed * 20 ticks/second)
    2. Validate target still exists and in range
    3. Execute CombatService.perform_attack()
    4. Update last_attack_tick
    5. Broadcast EVENT_COMBAT_ACTION
    6. Clear combat state if target died or out of range
    
    Args:
        gsm: GameStateManager instance
        manager: ConnectionManager for broadcasting
        tick_counter: Current tick number
    """
    from ..services.combat_service import CombatService
    from ..services.connection_service import ConnectionService
    from common.src.protocol import WSMessage, MessageType, PROTOCOL_VERSION
    
    players_in_combat = await gsm.get_all_players_in_combat()
    
    for combat_entry in players_in_combat:
        player_id = combat_entry["player_id"]
        combat_state = combat_entry["combat_state"]
        
        try:
            # Calculate ticks since last attack
            last_attack_tick = combat_state["last_attack_tick"]
            attack_speed = combat_state["attack_speed"]
            ticks_required = int(attack_speed * 20)  # Convert seconds to ticks
            
            ticks_since_last_attack = tick_counter - last_attack_tick
            
            if ticks_since_last_attack < ticks_required:
                continue  # Not ready to attack yet
            
            # Get player position
            player_pos = await gsm.get_player_position(player_id)
            if not player_pos:
                await gsm.clear_player_combat_state(player_id)
                continue
            
            # Check if player is still alive
            player_hp = await gsm.get_player_hp(player_id)
            if not player_hp or player_hp["current_hp"] <= 0:
                await gsm.clear_player_combat_state(player_id)
                continue
            
            # Get target position and validate
            target_type = combat_state["target_type"]
            target_id = combat_state["target_id"]
            
            if target_type == "entity":
                target_data = await gsm.get_entity_instance(target_id)
                if not target_data:
                    await gsm.clear_player_combat_state(player_id)
                    continue
                
                target_x = target_data["x"]
                target_y = target_data["y"]
                target_map_id = target_data["map_id"]
                
                # Check if target is on same map
                if target_map_id != player_pos["map_id"]:
                    await gsm.clear_player_combat_state(player_id)
                    continue
                
                # Check range (melee = 1 tile)
                distance = max(
                    abs(target_x - player_pos["x"]),
                    abs(target_y - player_pos["y"])
                )
                
                if distance > 1:  # Melee range
                    await gsm.clear_player_combat_state(player_id)
                    continue
                
                # Execute attack
                result = await CombatService.perform_attack(
                    attacker_type="player",
                    attacker_id=player_id,
                    defender_type="entity",
                    defender_id=target_id,
                )
                
                if result.success:
                    # Update last attack tick
                    await gsm.set_player_combat_state(
                        player_id=player_id,
                        target_type=target_type,
                        target_id=target_id,
                        last_attack_tick=tick_counter,
                        attack_speed=attack_speed,
                    )
                    
                    # Broadcast combat event
                    username = ConnectionService.get_online_username_by_player_id(player_id)
                    if username:
                        combat_event = WSMessage(
                            id=None,
                            type=MessageType.EVENT_COMBAT_ACTION,
                            payload={
                                "attacker_type": "player",
                                "attacker_id": player_id,
                                "attacker_name": username,
                                "defender_type": "entity",
                                "defender_id": target_id,
                                "defender_name": target_data.get("display_name", "Unknown"),
                                "hit": result.hit,
                                "damage": result.damage,
                                "defender_hp": result.defender_hp,
                                "defender_died": result.defender_died,
                                "message": result.message
                            },
                            version=PROTOCOL_VERSION
                        )
                        
                        packed_event = msgpack.packb(combat_event.model_dump(), use_bin_type=True)
                        await manager.broadcast_to_map(player_pos["map_id"], packed_event)
                    
                    # Clear combat if target died
                    if result.defender_died:
                        await gsm.clear_player_combat_state(player_id)
                else:
                    # Attack failed, clear combat state
                    await gsm.clear_player_combat_state(player_id)
            
            # TODO: Handle player vs player combat when implemented
            
        except Exception as e:
            logger.error(
                "Error processing auto-attack",
                extra={
                    "player_id": player_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "traceback": traceback.format_exc(),
                }
            )
            # Clear combat state on error
            await gsm.clear_player_combat_state(player_id)


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
                # Convert to simple chunk format for EVENT_STATE_UPDATE
                chunk_data_list = []
                for chunk in chunks:
                    chunk_data_list.append({
                        "chunk_x": chunk["chunk_x"],
                        "chunk_y": chunk["chunk_y"], 
                        "tiles": chunk["tiles"],  # Keep raw tile data
                        "width": chunk["width"],
                        "height": chunk["height"],
                    })

                # Send chunk data as state update event
                chunk_message = WSMessage(
                    id=None,  # No correlation ID for events
                    type=MessageType.EVENT_STATE_UPDATE,
                    payload={
                        "update_type": "full",
                        "target": "personal", 
                        "systems": {
                            "map": {
                                "map_id": map_id,
                                "chunks": chunk_data_list,
                                "player_x": x,
                                "player_y": y
                            }
                        }
                    },
                    version="2.0"
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
            "Error sending chunk update",
            extra={
                "username": username,
                "error": str(e),
                "traceback": traceback.format_exc(),
            }
        )


async def send_diff_update(
    username: str, 
    websocket, 
    diff: Dict[str, List[Dict[str, Any]]],
    map_id: str
) -> None:
    """
    Send a diff-based game state update to a specific player.
    
    Args:
        username: Player's username
        websocket: Player's WebSocket connection
        diff: The entity diff (added/updated/removed)
        map_id: The map identifier
    """
    # Only send if there are actual changes
    if not diff["added"] and not diff["updated"] and not diff["removed"]:
        return
        
    try:
        # Combine added and updated into entities list
        entities = diff["added"] + diff["updated"]
        
        update_message = WSMessage(
            id=None,  # No correlation ID for events
            type=MessageType.EVENT_STATE_UPDATE,
            payload={
                "entities": entities,
                "removed_entities": [e.get("username") or str(e.get("id", "")) for e in diff["removed"]],
                "map_id": map_id,
            },
            version="2.0"
        )
        
        packed = msgpack.packb(update_message.model_dump(), use_bin_type=True)
        if packed:
            await websocket.send_bytes(packed)
            
    except Exception as e:
        logger.error(
            "Error sending diff update", 
            extra={
                "username": username,
                "error": str(e),
                "traceback": traceback.format_exc(),
            }
        )


async def cleanup_disconnected_player(username: str) -> None:
    """Clean up state tracking for a disconnected player."""
    player_chunk_positions.pop(username, None)
    player_login_ticks.pop(username, None)
    
    # Remove player from VisibilityService
    visibility_service = get_visibility_service()
    await visibility_service.remove_player(username)


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
                            "traceback": traceback.format_exc(),
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
                visibility_service = get_visibility_service()
                
                # Process player data and collect HP regeneration updates
                all_player_data: List[Dict[str, Any]] = []
                player_positions: Dict[str, Tuple[int, int]] = {}
                hp_updates: List[tuple[str, int]] = []  # Batch HP updates
                
                # Fetch player states individually (avoiding broken batch methods)
                for username in player_usernames:
                    # Get player state using existing individual method
                    data = await gsm.state_access.get_player_state_by_username(username)
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
                            new_hp = min(current_hp + 1, max_hp)
                            hp_updates.append((username, new_hp))
                            current_hp = new_hp  # Use updated HP for this tick
                        
                        all_player_data.append({
                            "id": username,
                            "username": username,
                            "x": x,
                            "y": y,
                            "current_hp": current_hp,
                            "max_hp": max_hp,
                        })
                        player_positions[username] = (x, y)

                # Execute batch HP regeneration updates
                if hp_updates:
                    await gsm.state_access.batch_update_player_hp(hp_updates)

                # Process dying entities (death animation completion)
                entity_instances = await gsm.get_map_entities(map_id)
                for entity in entity_instances:
                    if entity.get("state") == "dying":
                        death_tick = int(entity.get("death_tick", 0))
                        if _global_tick_counter >= death_tick:
                            # Death animation complete, finalize death
                            await gsm.finalize_entity_death(entity["id"])

                # Process auto-attacks for all players in combat
                await _process_auto_attacks(gsm, manager, _global_tick_counter)

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
                    
                    # Get entity instances visible to this player
                    entity_instances = await gsm.get_map_entities(map_id)
                    current_visible_entities = get_visible_npc_entities(
                        player_x, player_y, entity_instances
                    )
                    
                    # Get ground items visible to this player
                    from ..services.connection_service import ConnectionService
                    player_id = ConnectionService.get_online_player_id_by_username(username)
                    
                    # Skip ground item processing if player_id is invalid
                    if not player_id:
                        current_visible_ground_items = {}
                    else:
                        # Use GroundItemService for ground item visibility
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
                    
                    # Combine players and ground items into single visibility state
                    combined_visible_entities = {}
                    
                    # Add players with 'player_' prefix to avoid ID conflicts with ground items
                    for player_username, player_data in current_visible_players.items():
                        combined_visible_entities[f"player_{player_username}"] = player_data
                    
                    # Add ground items directly (they already have unique IDs)
                    for ground_item_id, ground_item_data in current_visible_ground_items.items():
                        combined_visible_entities[f"ground_item_{ground_item_id}"] = ground_item_data
                    
                    # Add entity instances (already has entity_ prefix from helper function)
                    for entity_key, entity_data in current_visible_entities.items():
                        combined_visible_entities[entity_key] = entity_data
                    
                    # Use VisibilityService to compute diff and update state
                    diff = await visibility_service.update_player_visible_entities(username, combined_visible_entities)
                    
                    # Send diff update if there are changes
                    await send_diff_update(username, websocket, diff, map_id)
                    
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
                extra={
                    "error": str(e), 
                    "error_type": type(e).__name__,
                    "traceback": traceback.format_exc(),
                    "tick_interval": tick_interval
                },
            )
            # Avoid rapid-fire loops on persistent errors
            await asyncio.sleep(1)
