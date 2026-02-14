"""
Game loop module for server tick updates.

Implements diff-based visibility broadcasting where each player only receives
updates about entities within their visible chunk range.

KEY DESIGN PRINCIPLE:
- player_id (int) is the ONLY internal identifier for players
- username is for display/authentication only, never for internal lookups
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
from server.src.services.game_state import (
    get_player_state_manager,
    get_entity_manager,
    get_batch_sync_coordinator,
    get_reference_data_manager,
)
from server.src.services.visibility_service import get_visibility_service
from server.src.services.visual_registry import get_visual_registry
from server.src.services.visual_state_service import VisualStateService
from server.src.services.ai_service import AIService
from server.src.services.entity_spawn_service import EntitySpawnService
from server.src.core.entities import EntityState
from common.src.protocol import (
    WSMessage,
    MessageType,
    CombatTargetType,
    PROTOCOL_VERSION,
)
from common.src.sprites import (
    VisualState,
    AppearanceData,
    EquippedVisuals,
)
from server.src.schemas.item import EquipmentData

logger = get_logger(__name__)

# Default chunk size in tiles
CHUNK_SIZE = 16

# Visibility radius in chunks (1 = 3x3 grid of chunks around player)
VISIBILITY_RADIUS = 1


class GameLoopState:
    """
    Thread-safe container for game loop state.
    
    Encapsulates module-level mutable state with async locks to prevent
    race conditions between the game loop and WebSocket handlers.
    
    All player identification uses player_id (int), never username.
    """
    
    def __init__(self):
        self._lock = asyncio.Lock()
        self._player_chunk_positions: Dict[int, Tuple[int, int]] = {}  # player_id -> chunk
        self._global_tick_counter: int = 0
        self._player_login_ticks: Dict[int, int] = {}  # player_id -> tick
        self._players_dying: Set[int] = set()
        self._active_tasks: Set[asyncio.Task] = set()
    
    @property
    def tick_counter(self) -> int:
        """Get current tick counter (read-only, no lock needed for atomic int read)."""
        return self._global_tick_counter
    
    def increment_tick(self) -> int:
        """Increment and return new tick counter. Called only from game loop."""
        self._global_tick_counter += 1
        return self._global_tick_counter
    
    async def get_player_chunk_position(self, player_id: int) -> Optional[Tuple[int, int]]:
        """Get a player's last known chunk position."""
        async with self._lock:
            return self._player_chunk_positions.get(player_id)
    
    async def set_player_chunk_position(self, player_id: int, chunk: Tuple[int, int]) -> None:
        """Set a player's chunk position."""
        async with self._lock:
            self._player_chunk_positions[player_id] = chunk
    
    async def get_player_login_tick(self, player_id: int) -> Optional[int]:
        """Get the tick when a player logged in, or None if not found."""
        async with self._lock:
            return self._player_login_ticks.get(player_id)
    
    async def register_player_login(self, player_id: int) -> None:
        """Register a player's login tick for staggered HP regen."""
        async with self._lock:
            self._player_login_ticks[player_id] = self._global_tick_counter
    
    async def is_player_dying(self, player_id: int) -> bool:
        """Check if a player is currently in death sequence."""
        async with self._lock:
            return player_id in self._players_dying
    
    async def add_dying_player(self, player_id: int) -> bool:
        """
        Add a player to the dying set.
        
        Returns True if player was added, False if already dying.
        """
        async with self._lock:
            if player_id in self._players_dying:
                return False
            self._players_dying.add(player_id)
            return True
    
    async def remove_dying_player(self, player_id: int) -> None:
        """Remove a player from the dying set."""
        async with self._lock:
            self._players_dying.discard(player_id)
    
    async def cleanup_player(self, player_id: int) -> None:
        """Clean up all state for a disconnected player."""
        async with self._lock:
            self._player_chunk_positions.pop(player_id, None)
            self._player_login_ticks.pop(player_id, None)
    
    def track_task(self, task: asyncio.Task) -> None:
        """
        Track an async task for proper cleanup and exception handling.
        
        Adds a done callback to log exceptions and remove from tracking set.
        """
        self._active_tasks.add(task)
        
        def _on_task_done(t: asyncio.Task) -> None:
            self._active_tasks.discard(t)
            if t.cancelled():
                return
            exc = t.exception()
            if exc:
                logger.error(
                    "Background task failed",
                    extra={
                        "task_name": t.get_name(),
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                        "traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
                    },
                )
        
        task.add_done_callback(_on_task_done)
    
    async def cancel_all_tasks(self) -> None:
        """Cancel all tracked tasks (for shutdown)."""
        for task in list(self._active_tasks):
            if not task.done():
                task.cancel()
        
        if self._active_tasks:
            await asyncio.gather(*self._active_tasks, return_exceptions=True)
            self._active_tasks.clear()


# Singleton instance of game loop state
_game_loop_state: Optional[GameLoopState] = None


def get_game_loop_state() -> GameLoopState:
    """Get or create the singleton GameLoopState instance."""
    global _game_loop_state
    if _game_loop_state is None:
        _game_loop_state = GameLoopState()
    return _game_loop_state


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


def _build_equipped_items_map(equipment_data: Optional[EquipmentData], reference_mgr) -> Optional[Dict[str, str]]:
    """
    Convert equipment data to slot->sprite_id mapping for paperdoll rendering.
    
    Delegates to VisualStateService._build_equipped_items_map for single source of truth.
    
    Args:
        equipment_data: EquipmentData Pydantic model with slots list
        reference_mgr: ReferenceDataManager for item cache lookup
        
    Returns:
        Dict of {slot: equipped_sprite_id} or None if no equipment
    """
    if not equipment_data or not equipment_data.slots:
        return None
    
    # Convert EquipmentData to the format expected by VisualStateService
    equipment_list = []
    for slot_data in equipment_data.slots:
        if slot_data.item:
            equipment_list.append({
                "slot": slot_data.slot.value,
                "item_id": slot_data.item.id
            })
    
    return VisualStateService._build_equipped_items_map(equipment_list, reference_mgr)


def _build_visual_state(
    appearance: Optional[Dict],
    equipped_items: Optional[Dict[str, str]],
) -> VisualState:
    """
    Build a VisualState from appearance dict and equipped items map.
    
    Delegates to VisualStateService._build_visual_state for single source of truth.

    Args:
        appearance: Appearance dictionary from player state
        equipped_items: Dict mapping slot names to equipped_sprite_ids

    Returns:
        VisualState instance for hash computation and serialization
    """
    return VisualStateService._build_visual_state(appearance, equipped_items)


def get_visible_players(
    player_x: int, player_y: int, 
    all_players: List[Dict[str, Any]], 
    own_player_id: int
) -> Dict[int, Dict[str, Any]]:
    """
    Get player entities visible to a player based on chunk range.
    
    Args:
        player_x, player_y: Player's tile position
        all_players: All player entities on the map
        own_player_id: The player's ID (to exclude self)
        
    Returns:
        Dict of {player_id: entity_data} for visible player entities
    """
    visible = {}
    for entity in all_players:
        entity_player_id = entity.get("player_id")
        if entity_player_id == own_player_id:
            continue
            
        entity_x = entity.get("x", 0)
        entity_y = entity.get("y", 0)
        
        if is_in_visible_range(player_x, player_y, entity_x, entity_y):
            entity_data = {
                "id": f"player_{entity_player_id}",  # Entity ID for client tracking
                "type": "player",
                "player_id": entity_player_id,
                "username": entity.get("username", ""),  # For display
                "x": entity_x,
                "y": entity_y,
                "current_hp": entity.get("current_hp", 0),
                "max_hp": entity.get("max_hp", 0),
                "facing_direction": entity.get("facing_direction", "DOWN"),
            }
            
            # Include visual hash and state for sprite rendering
            if "visual_hash" in entity:
                entity_data["visual_hash"] = entity["visual_hash"]
            if "visual_state" in entity:
                entity_data["visual_state"] = entity["visual_state"]
            
            visible[entity_player_id] = entity_data
    
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
    from server.src.core.entities import EntityState, get_entity_by_name, EntityType
    from server.src.core.humanoids import HumanoidDefinition
    from server.src.core.monsters import MonsterDefinition
    
    visible = {}
    for entity in all_entity_instances:
        entity_state = entity.get("state", EntityState.IDLE.value)
        
        # Show entities in "dying" state (10-tick death animation)
        # Skip entities fully despawned (state == "dead")
        if entity_state == EntityState.DEAD.value:
            continue
            
        entity_x = int(entity.get("x", 0))
        entity_y = int(entity.get("y", 0))
        
        if is_in_visible_range(player_x, player_y, entity_x, entity_y):
            entity_id = entity.get("instance_id")
            entity_name = entity.get("entity_name", "")
            entity_type = entity.get("entity_type", EntityType.MONSTER.value)
            
            # Get entity definition for display name and behavior
            entity_enum = get_entity_by_name(entity_name)
            display_name = entity_name
            behavior_type = "PASSIVE"
            is_attackable = True
            
            # Entity-type specific rendering data
            sprite_sheet_id = None  # For monsters
            visual_state = None  # For humanoids
            
            if entity_enum:
                entity_def = entity_enum.value
                display_name = entity_def.display_name
                behavior_type = entity_def.behavior.name
                is_attackable = entity_def.is_attackable and entity_state != EntityState.DYING.value
                
                # Extract type-specific rendering data
                if isinstance(entity_def, HumanoidDefinition):
                    # Build visual state from humanoid appearance and equipment
                    appearance = entity_def.appearance.to_dict() if entity_def.appearance else None
                    equipped_items = None
                    if entity_def.equipped_items:
                        equipped_items = {
                            slot.value: item.value.equipped_sprite_id 
                            for slot, item in entity_def.equipped_items.items()
                            if item.value.equipped_sprite_id
                        }
                    visual_state = _build_visual_state(appearance, equipped_items)
                elif isinstance(entity_def, MonsterDefinition):
                    sprite_sheet_id = entity_def.sprite_sheet_id
            else:
                is_attackable = entity_state != EntityState.DYING.value
            
            entity_data = {
                "type": "entity",
                "id": entity_id,
                "entity_type": entity_type,
                "entity_name": entity_name,
                "display_name": display_name,
                "behavior_type": behavior_type,
                "x": entity_x,
                "y": entity_y,
                "facing_direction": entity.get("facing_direction", "DOWN"),
                "current_hp": int(entity.get("current_hp", 0)),
                "max_hp": int(entity.get("max_hp", 0)),
                "state": entity_state,
                "is_attackable": is_attackable,
            }
            
            # Add type-specific fields
            if entity_type == EntityType.HUMANOID_NPC.value and visual_state:
                entity_data["visual_hash"] = visual_state.compute_hash()
                entity_data["visual_state"] = visual_state.to_dict()
            elif entity_type == EntityType.MONSTER.value:
                entity_data["sprite_sheet_id"] = sprite_sheet_id
            
            visible[f"entity_{entity_id}"] = entity_data
    
    return visible


async def _process_auto_attacks(
    player_mgr,
    entity_mgr,
    manager: ConnectionManager,
    tick_counter: int
) -> None:
    """
    Process all players in combat and execute auto-attacks.
    
    Called every game tick (20 TPS = 50ms per tick).
    
    Args:
        player_mgr: PlayerStateManager instance
        entity_mgr: EntityManager instance
        manager: ConnectionManager for broadcasting
        tick_counter: Current tick number
    """
    from ..services.combat_service import CombatService
    from ..services.player_service import PlayerService
    
    players_in_combat = await player_mgr.get_all_players_in_combat()
    
    for combat_entry in players_in_combat:
        player_id = combat_entry["player_id"]
        combat_state = combat_entry["combat_state"]
        
        try:
            # Calculate ticks since last attack
            last_attack_tick = combat_state["last_attack_tick"]
            attack_speed = combat_state["attack_speed"]
            ticks_required = int(attack_speed * settings.GAME_TICK_RATE)  # Convert seconds to ticks
            
            ticks_since_last_attack = tick_counter - last_attack_tick
            
            if ticks_since_last_attack < ticks_required:
                continue  # Not ready to attack yet
            
            # Get player position
            player_pos = await player_mgr.get_player_position(player_id)
            if not player_pos:
                await player_mgr.clear_player_combat_state(player_id)
                continue
            
            # Check if player is still alive
            player_hp = await player_mgr.get_player_hp(player_id)
            if not player_hp or player_hp["current_hp"] <= 0:
                await player_mgr.clear_player_combat_state(player_id)
                continue
            
            # Get target position and validate
            target_type_str = combat_state["target_type"]
            target_type = CombatTargetType(target_type_str)
            target_id = combat_state["target_id"]
            
            if target_type == CombatTargetType.ENTITY:
                target_data = await entity_mgr.get_entity_instance(target_id)
                if not target_data:
                    await player_mgr.clear_player_combat_state(player_id)
                    continue
                
                target_x = target_data["x"]
                target_y = target_data["y"]
                target_map_id = target_data["map_id"]
                
                # Check if target is on same map
                if target_map_id != player_pos["map_id"]:
                    await player_mgr.clear_player_combat_state(player_id)
                    continue
                
                # Check range (melee = 1 tile)
                distance = max(
                    abs(target_x - player_pos["x"]),
                    abs(target_y - player_pos["y"])
                )
                
                if distance > 1:  # Melee range
                    await player_mgr.clear_player_combat_state(player_id)
                    continue
                
                # Execute attack
                result = await CombatService.perform_attack(
                    attacker_type=CombatTargetType.PLAYER,
                    attacker_id=player_id,
                    defender_type=CombatTargetType.ENTITY,
                    defender_id=target_id,
                )
                
                if result.success:
                    # Update last attack tick
                    await player_mgr.set_player_combat_state(
                        player_id,
                        target_type.value,
                        target_id
                    )
                    
                    # Get username for display in combat event
                    username = await PlayerService.get_username_by_player_id(player_id)
                    if username:
                        combat_event = WSMessage(
                            id=None,
                            type=MessageType.EVENT_COMBAT_ACTION,
                            payload={
                                "attacker_type": CombatTargetType.PLAYER.value,
                                "attacker_id": player_id,
                                "attacker_name": username,
                                "defender_type": CombatTargetType.ENTITY.value,
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
                        if packed_event:
                            await manager.broadcast_to_map(player_pos["map_id"], packed_event)
                    
                    # Clear combat if target died
                    if result.defender_died:
                        await player_mgr.clear_player_combat_state(player_id)
                else:
                    # Attack failed, clear combat state
                    await player_mgr.clear_player_combat_state(player_id)
            
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
            await player_mgr.clear_player_combat_state(player_id)


async def send_chunk_update_if_needed(
    player_id: int, map_id: str, x: int, y: int, websocket, chunk_size: int = CHUNK_SIZE
) -> None:
    """
    Send chunk data if player moved to a new chunk.

    Args:
        player_id: Player's unique database ID
        map_id: Current map ID
        x, y: Player's current tile position
        websocket: Player's WebSocket connection
        chunk_size: Size of chunks in tiles
    """
    try:
        state = get_game_loop_state()
        current_chunk = get_chunk_coordinates(x, y, chunk_size)
        last_chunk = await state.get_player_chunk_position(player_id)

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

                # Send chunk data as chunk update event
                chunk_message = WSMessage(
                    id=None,  # No correlation ID for events
                    type=MessageType.EVENT_CHUNK_UPDATE,
                    payload={
                        "map_id": map_id,
                        "chunks": chunk_data_list
                    },
                    version=PROTOCOL_VERSION
                )

                await websocket.send_bytes(
                    msgpack.packb(chunk_message.model_dump(), use_bin_type=True)
                )

                # Update tracked position
                await state.set_player_chunk_position(player_id, current_chunk)

                logger.debug(
                    "Sent automatic chunk update",
                    extra={
                        "player_id": player_id,
                        "old_chunk": last_chunk,
                        "new_chunk": current_chunk,
                        "chunk_count": len(chunk_data_list),
                    },
                )

    except Exception as e:
        logger.error(
            "Error sending chunk update",
            extra={
                "player_id": player_id,
                "error": str(e),
                "traceback": traceback.format_exc(),
            }
        )


async def send_diff_update(
    player_id: int, 
    websocket, 
    diff: Dict[str, List[Dict[str, Any]]],
    map_id: str
) -> None:
    """
    Send a diff-based game state update to a specific player.
    
    Args:
        player_id: Player's unique database ID
        websocket: Player's WebSocket connection
        diff: The entity diff (added/updated/removed)
        map_id: The map identifier
    """
    # Only send if there are actual changes
    if not diff["added"] and not diff["updated"] and not diff["removed"]:
        return
        
    try:
        # Combine added and updated into entities list
        all_entities = diff["added"] + diff["updated"]
        
        # Separate ground items from other entities
        entities = []
        ground_items = []
        for entity in all_entities:
            if entity.get("type") == "ground_item":
                ground_items.append(entity)
            else:
                entities.append(entity)
        
        # Build removed_entities list - use player_id for players, id for others
        removed_entities = []
        removed_ground_item_ids = []
        for e in diff["removed"]:
            entity_id = e.get("id", "")
            # Check if this is a ground item
            if isinstance(entity_id, str) and entity_id.startswith("ground_item_"):
                try:
                    ground_item_id = int(entity_id.replace("ground_item_", ""))
                    removed_ground_item_ids.append(ground_item_id)
                except ValueError:
                    removed_ground_item_ids.append(entity_id)
            # Entity keys are like "player_123" or "entity_456"
            elif isinstance(entity_id, str) and entity_id.startswith("player_"):
                # Extract player_id from key
                try:
                    removed_entities.append(int(entity_id.replace("player_", "")))
                except ValueError:
                    removed_entities.append(entity_id)
            else:
                removed_entities.append(str(entity_id))
        
        update_message = WSMessage(
            id=None,  # No correlation ID for events
            type=MessageType.EVENT_GAME_UPDATE,
            payload={
                "entities": entities,
                "removed_entities": removed_entities,
                "ground_items": ground_items,
                "removed_ground_item_ids": removed_ground_item_ids,
                "map_id": map_id,
            },
            version=PROTOCOL_VERSION
        )
        
        packed = msgpack.packb(update_message.model_dump(), use_bin_type=True)
        if packed:
            await websocket.send_bytes(packed)
            
    except Exception as e:
        logger.error(
            "Error sending diff update", 
            extra={
                "player_id": player_id,
                "error": str(e),
                "traceback": traceback.format_exc(),
            }
        )


async def cleanup_disconnected_player(player_id: int) -> None:
    """Clean up state tracking for a disconnected player."""
    state = get_game_loop_state()
    await state.cleanup_player(player_id)
    
    # Remove player from VisibilityService
    visibility_service = get_visibility_service()
    await visibility_service.remove_player(player_id)


async def _handle_player_death(
    player_id: int,
    map_id: str,
    manager: ConnectionManager,
) -> None:
    """
    Handle the full death sequence for a player who reached 0 HP.
    
    This function runs asynchronously and handles:
    1. Calling HpService.full_death_sequence() (drops items, waits, respawns)
    2. Broadcasting EVENT_PLAYER_DIED and EVENT_PLAYER_RESPAWN
    3. Clearing the player's combat state
    4. Clearing all entities targeting this player
    5. Removing player from players_dying set when complete
    
    Args:
        player_id: Player's database ID
        map_id: Map where the player died
        manager: ConnectionManager for broadcasting
    """
    from server.src.services.hp_service import HpService
    
    try:
        player_mgr = get_player_state_manager()
        entity_mgr = get_entity_manager()
        
        # Clear player's combat state immediately
        await player_mgr.clear_player_combat_state(player_id)
        
        # Clear all entities targeting this player
        await AIService.clear_entities_targeting_player(entity_mgr, map_id, player_id)
        
        # Create broadcast callback for death/respawn events
        async def broadcast_callback(message_type: str, payload: dict, username: str):
            """Broadcast death/respawn events to the map."""
            event_map_id = payload.get("map_id", map_id)
            
            # Map message_type string to MessageType enum
            if message_type == "EVENT_PLAYER_DIED":
                msg_type = MessageType.EVENT_PLAYER_DIED
            elif message_type == "EVENT_PLAYER_RESPAWN":
                msg_type = MessageType.EVENT_PLAYER_RESPAWN
            else:
                logger.warning("Unknown death broadcast message type", extra={"message_type": message_type})
                return
            
            event_message = WSMessage(
                id=None,
                type=msg_type,
                payload=payload,
                version=PROTOCOL_VERSION,
            )
            packed_event = msgpack.packb(event_message.model_dump(), use_bin_type=True)
            if packed_event:
                await manager.broadcast_to_map(event_map_id, packed_event)
        
        # Execute full death sequence
        result = await HpService.full_death_sequence(
            player_id=player_id,
            broadcast_callback=broadcast_callback,
        )
        
        if result.success:
            logger.info(
                "Player death sequence completed",
                extra={
                    "player_id": player_id,
                    "respawn_location": {
                        "map_id": result.map_id,
                        "x": result.x,
                        "y": result.y,
                    },
                    "new_hp": result.new_hp,
                },
            )
        else:
            logger.error(
                "Player death sequence failed",
                extra={
                    "player_id": player_id,
                    "message": result.message,
                },
            )
    
    except Exception as e:
        logger.error(
            "Error in player death handler",
            extra={
                "player_id": player_id,
                "map_id": map_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc(),
            },
        )
    finally:
        # Always remove player from dying set when done
        state = get_game_loop_state()
        await state.remove_dying_player(player_id)


async def register_player_login(player_id: int) -> None:
    """Register a player's login tick for staggered HP regen."""
    state = get_game_loop_state()
    await state.register_player_login(player_id)


async def game_loop(manager: ConnectionManager, valkey: GlideClient) -> None:
    """
    The main game loop with diff-based visibility broadcasting.
    
    Each player only receives updates about entities within their visible
    chunk range, and only when those entities have changed since the last tick.

    Args:
        manager: The connection manager.
        valkey: The Valkey client.
    """
    from ..services.hp_service import HpService
    from ..services.equipment_service import EquipmentService
    
    state = get_game_loop_state()
    tick_interval = 1 / settings.GAME_TICK_RATE
    hp_regen_interval = settings.HP_REGEN_INTERVAL_TICKS
    db_sync_interval = settings.DB_SYNC_INTERVAL_TICKS

    while True:
        loop_start_time = time.time()
        try:
            # Track game loop iteration
            game_loop_iterations_total.inc()
            
            # Increment global tick counter
            current_tick = state.increment_tick()

            # Periodic batch sync of dirty data to database
            if current_tick % db_sync_interval == 0:
                try:
                    sync_coordinator = get_batch_sync_coordinator()
                    await sync_coordinator.sync_all()
                except Exception as sync_error:
                    logger.error(
                        "Batch sync failed",
                        extra={
                            "error": str(sync_error),
                            "tick": current_tick,
                            "traceback": traceback.format_exc(),
                        },
                    )

            # Process entity respawn queue (every 10 ticks = 2x/sec)
            if current_tick % 10 == 0:
                try:
                    entity_mgr = get_entity_manager()
                    await EntitySpawnService.check_respawn_queue(entity_mgr)
                except TimeoutError as timeout_error:
                    # Transient timeout on non-critical operation - just warn
                    logger.warning(
                        "Entity respawn queue check timed out (retrying next cycle)",
                        extra={
                            "error": str(timeout_error),
                            "tick": current_tick,
                        },
                    )
                except Exception as respawn_error:
                    logger.error(
                        "Entity respawn processing failed",
                        extra={
                            "error": str(respawn_error),
                            "tick": current_tick,
                            "traceback": traceback.format_exc(),
                        },
                    )

            # Process each active map
            active_maps = list(manager.connections_by_map.keys())
            for map_id in active_maps:
                map_connections = manager.connections_by_map.get(map_id, {})
                if not map_connections:
                    continue
                
                # map_connections is now {player_id: websocket}
                player_ids = list(map_connections.keys())
                
                player_mgr = get_player_state_manager()
                entity_mgr = get_entity_manager()
                reference_mgr = get_reference_data_manager()
                visibility_service = get_visibility_service()
                visual_registry = get_visual_registry()
                
                # Process player data and collect HP regeneration updates
                all_player_data: List[Dict[str, Any]] = []
                player_positions: Dict[int, Tuple[int, int]] = {}  # player_id -> (x, y)
                hp_updates: List[Tuple[int, int]] = []  # (player_id, new_hp)
                
                # Fetch player states directly by player_id
                for player_id in player_ids:
                    # Get player state directly using player_id
                    data = await player_mgr.get_player_full_state(player_id)
                    if data:
                        x = int(data.get("x", 0))
                        y = int(data.get("y", 0))
                        current_hp = int(data.get("current_hp", 10))
                        max_hp = int(data.get("max_hp", 10))
                        appearance = data.get("appearance")  # Dict or None
                        facing_direction = data.get("facing_direction", "DOWN")
                        username = data.get("username", "")
                        
                        # Calculate HP regeneration based on player login time
                        login_tick = await state.get_player_login_tick(player_id) or current_tick
                        ticks_since_login = current_tick - login_tick
                        should_regen = (
                            ticks_since_login > 0 
                            and ticks_since_login % hp_regen_interval == 0
                            and current_hp < max_hp
                        )
                        
                        if should_regen:
                            new_hp = min(current_hp + 1, max_hp)
                            hp_updates.append((player_id, new_hp))
                            current_hp = new_hp  # Use updated HP for this tick
                        
                        # Get equipped items for paperdoll rendering
                        equipment_data = await EquipmentService.get_equipment(player_id)
                        equipped_items = _build_equipped_items_map(equipment_data, reference_mgr)
                        
                        # Build visual state and register with visual registry
                        # Wrapped in try/except to prevent one bad player from crashing all players
                        try:
                            visual_state = _build_visual_state(appearance, equipped_items)
                            visual_hash = await visual_registry.register_visual_state(
                                f"player_{player_id}", visual_state
                            )
                        except Exception as visual_error:
                            logger.error(
                                "Failed to build visual state for player",
                                extra={
                                    "player_id": player_id,
                                    "username": username,
                                    "error": str(visual_error),
                                    "appearance": str(appearance)[:200] if appearance else None,
                                },
                            )
                            # Skip this player for this tick - they'll be retried next tick
                            continue
                        
                        all_player_data.append({
                            "player_id": player_id,
                            "username": username,  # For display
                            "x": x,
                            "y": y,
                            "current_hp": current_hp,
                            "max_hp": max_hp,
                            "facing_direction": facing_direction,
                            "visual_hash": visual_hash,
                            "visual_state": visual_state.to_dict(),
                        })
                        player_positions[player_id] = (x, y)

                # Execute batch HP regeneration updates via HpService
                # Filter out dying players - they should not regenerate HP
                if hp_updates:
                    valid_hp_updates = [
                        (player_id, new_hp) 
                        for player_id, new_hp in hp_updates 
                        if not await state.is_player_dying(player_id)
                    ]
                    if valid_hp_updates:
                        await HpService.batch_regenerate_hp(valid_hp_updates)

                # Fetch all entity instances once for this map (reused for visibility)
                all_map_entity_instances = await entity_mgr.get_map_entities(map_id)
                
                # Process dying entities (death animation completion)
                for entity in all_map_entity_instances:
                    if entity.get("state") == EntityState.DYING.value:
                        death_tick = int(entity.get("death_tick", 0))
                        if current_tick >= death_tick:
                            # Death animation complete, finalize death
                            await entity_mgr.finalize_entity_death(entity["instance_id"])
                            # Clean up AI timer state for dead entity
                            AIService.cleanup_entity_timers(entity["instance_id"])

                # Process entity AI for this map
                entity_combat_events = await AIService.process_entities(
                    entity_mgr=entity_mgr,
                    map_id=map_id,
                    current_tick=current_tick,
                )
                
                # Broadcast any entity combat events
                if entity_combat_events:
                    for combat_event in entity_combat_events:
                        event_message = WSMessage(
                            id=None,
                            type=MessageType.EVENT_COMBAT_ACTION,
                            payload={
                                "attacker_type": CombatTargetType.ENTITY.value,
                                "attacker_id": combat_event.attacker_id,
                                "attacker_name": combat_event.attacker_name,
                                "defender_type": CombatTargetType.PLAYER.value,
                                "defender_id": combat_event.defender_id,
                                "defender_name": combat_event.defender_name,
                                "hit": combat_event.hit,
                                "damage": combat_event.damage,
                                "defender_hp": combat_event.defender_hp,
                                "defender_died": combat_event.defender_died,
                                "message": combat_event.message,
                            },
                            version=PROTOCOL_VERSION,
                        )
                        packed_event = msgpack.packb(event_message.model_dump(), use_bin_type=True)
                        if packed_event:
                            await manager.broadcast_to_map(combat_event.map_id, packed_event)
                
                # Check for player deaths and spawn death handlers
                for player_id in player_ids:
                    # Skip players already in death sequence
                    if await state.is_player_dying(player_id):
                        continue
                    
                    # Check player HP via HpService
                    current_hp, max_hp = await HpService.get_hp(player_id)
                    if current_hp <= 0:
                        # Player died - add to dying set and spawn death handler
                        if await state.add_dying_player(player_id):
                            task = asyncio.create_task(
                                _handle_player_death(player_id, map_id, manager),
                                name=f"death_handler_{player_id}"
                            )
                            state.track_task(task)

                # Process auto-attacks for all players in combat
                await _process_auto_attacks(player_mgr, entity_mgr, manager, current_tick)

                # For each connected player, compute and send their personalized diff
                for player_id in player_ids:
                    if player_id not in player_positions:
                        continue
                        
                    websocket = map_connections.get(player_id)
                    if not websocket:
                        continue
                    
                    player_x, player_y = player_positions[player_id]
                    
                    # Get player entities currently visible to this player
                    current_visible_players = get_visible_players(
                        player_x, player_y, all_player_data, player_id
                    )
                    
                    # Get entity instances visible to this player (reuse already fetched data)
                    current_visible_entities = get_visible_npc_entities(
                        player_x, player_y, all_map_entity_instances
                    )
                    
                    # Get ground items visible to this player
                    from ..services.ground_item_service import GroundItemService
                    visible_ground_items = await GroundItemService.get_visible_ground_items(
                        player_id=player_id,
                        map_id=map_id,
                        center_x=player_x,
                        center_y=player_y,
                        tile_radius=32,  # Same as visibility range
                    )
                    
                    # Convert GroundItem Pydantic models to dicts for visibility tracking
                    current_visible_ground_items = {}
                    for ground_item in visible_ground_items:
                        current_visible_ground_items[ground_item.id] = {
                            "type": "ground_item",
                            "id": ground_item.id,
                            "item_id": ground_item.item.id,
                            "item_name": ground_item.item.name,
                            "display_name": ground_item.item.display_name,
                            "rarity": ground_item.item.rarity.value,
                            "x": ground_item.x,
                            "y": ground_item.y,
                            "quantity": ground_item.quantity,
                            "is_protected": not ground_item.is_yours and ground_item.is_protected,
                            "icon_sprite_id": ground_item.item.icon_sprite_id,
                        }
                    
                    # Combine players and ground items into single visibility state
                    combined_visible_entities: Dict[str, Dict[str, Any]] = {}
                    
                    # Add the player's own data (so client can track its own position)
                    own_player_data = None
                    for entity in all_player_data:
                        if entity.get("player_id") == player_id:
                            own_player_data = {
                                "id": f"player_{player_id}",  # Entity ID for client tracking
                                "type": "player",
                                "player_id": player_id,
                                "username": entity.get("username", ""),  # For display
                                "x": entity.get("x", player_x),
                                "y": entity.get("y", player_y),
                                "current_hp": entity.get("current_hp", 0),
                                "max_hp": entity.get("max_hp", 0),
                                "facing_direction": entity.get("facing_direction", "DOWN"),
                            }
                            if "visual_hash" in entity:
                                own_player_data["visual_hash"] = entity["visual_hash"]
                            if "visual_state" in entity:
                                own_player_data["visual_state"] = entity["visual_state"]
                            break
                    
                    if own_player_data:
                        combined_visible_entities[f"player_{player_id}"] = own_player_data
                    else:
                        logger.warning("own_player_data is None for player", extra={"player_id": player_id})
                    
                    # Add other players with 'player_' prefix to avoid ID conflicts with ground items
                    for other_player_id, player_data in current_visible_players.items():
                        combined_visible_entities[f"player_{other_player_id}"] = player_data
                    
                    # Add ground items directly (they already have unique IDs)
                    for ground_item_id, ground_item_data in current_visible_ground_items.items():
                        combined_visible_entities[f"ground_item_{ground_item_id}"] = ground_item_data
                    
                    # Add entity instances (already has entity_ prefix from helper function)
                    for entity_key, entity_data in current_visible_entities.items():
                        combined_visible_entities[entity_key] = entity_data
                    
                    # Use VisibilityService to compute diff and update state
                    diff = await visibility_service.update_player_visible_entities(player_id, combined_visible_entities)
                    
                    # Send diff update if there are changes
                    await send_diff_update(player_id, websocket, diff, map_id)
                    
                    # Check if player needs chunk updates
                    await send_chunk_update_if_needed(
                        player_id, map_id, player_x, player_y, websocket
                    )
                    
                # Track broadcast for metrics
                game_state_broadcasts_total.labels(map_id=map_id).inc()

            # Track loop duration and calculate precise sleep time
            loop_duration = time.time() - loop_start_time
            game_loop_duration_seconds.observe(loop_duration)

            # Sleep for remaining tick time to maintain consistent tick rate
            sleep_time = max(0, tick_interval - loop_duration)
            await asyncio.sleep(sleep_time)

        except Exception as e:
            logger.error(
                f"Error in game loop: {e}\n{traceback.format_exc()}",
                extra={
                    "error": str(e), 
                    "error_type": type(e).__name__,
                    "tick_interval": tick_interval
                },
            )
            # Avoid rapid-fire loops on persistent errors
            await asyncio.sleep(1)
