"""
Message handlers for server-to-client events.

Each handler processes a specific message type and updates game state.
"""

from typing import Dict, Any, Optional, TYPE_CHECKING

from ..logging_config import get_logger
from ..core import get_event_bus, EventType

if TYPE_CHECKING:
    from ..game.client_state import ClientGameState

import sys
from pathlib import Path
common_path = Path(__file__).parent.parent.parent.parent / "common" / "src"
if str(common_path) not in sys.path:
    sys.path.insert(0, str(common_path))

from protocol import MessageType

logger = get_logger(__name__)


class MessageHandlers:
    """Container for all message handlers."""
    
    def __init__(self, game_state: "ClientGameState", connection=None):
        self.game_state = game_state
        self.event_bus = get_event_bus()
        self.connection = connection
    
    # =================================================================
    # EVENT HANDLERS
    # =================================================================
    
    async def handle_welcome(self, payload: Dict[str, Any], correlation_id: Optional[str] = None) -> None:
        """Handle welcome event with initial player data."""
        # Extract player data from nested structure
        player_data = payload.get("player", {})
        
        # Set player identity
        self.game_state.player_id = player_data.get("id")
        self.game_state.username = player_data.get("username")
        
        # Set position
        position = player_data.get("position", {})
        if position:
            self.game_state.position = position
            self.game_state.map_id = position.get("map_id")
        
        # Set HP
        hp_data = player_data.get("hp", {})
        self.game_state.current_hp = hp_data.get("current_hp", 100)
        self.game_state.max_hp = hp_data.get("max_hp", 100)
        
        # Set visual state if provided
        if "visual_hash" in player_data:
            self.game_state.visual_hash = player_data["visual_hash"]
        if "visual_state" in player_data:
            self.game_state.visual_state = player_data["visual_state"]

            # Preload player paperdoll sprites
            try:
                from ..rendering.sprite_manager import get_sprite_manager
                from ..rendering.paperdoll_renderer import PaperdollRenderer
                sprite_manager = get_sprite_manager()
                paperdoll = PaperdollRenderer(sprite_manager)
                # Preload in background - don't block welcome processing
                import asyncio
                asyncio.create_task(
                    paperdoll.preload_character(
                        player_data["visual_state"],
                        player_data.get("visual_hash", "default")
                    )
                )
                logger.debug("Started preloading character sprites")
            except Exception as e:
                logger.warning(f"Failed to start sprite preloading: {e}")

        logger.info(f"Welcome received: {self.game_state.username} at position ({self.game_state.position.get('x')}, {self.game_state.position.get('y')})")
        
        # IMPORTANT: Load tilesets for the map
        if self.game_state.map_id:
            from ..tileset_manager import get_tileset_manager
            tileset_manager = get_tileset_manager()
            try:
                logger.info(f"Loading tilesets for map: {self.game_state.map_id}")
                await tileset_manager.load_map_tilesets(self.game_state.map_id)
                logger.info(f"Tilesets loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load tilesets: {e}")
        
        # Request map chunks around current position (handles reconnects)
        if self.connection and self.game_state.position:
            from .message_sender import MessageSender
            sender = MessageSender()
            x = self.game_state.position.get("x", 0)
            y = self.game_state.position.get("y", 0)
            try:
                logger.info(f"Requesting map chunks at ({x}, {y})")
                await sender.query_map_chunks(x, y)
            except Exception as e:
                logger.error(f"Failed to request map chunks: {e}")
        
        self.event_bus.emit(EventType.GAME_STARTED, {"player_id": self.game_state.player_id})
    
    async def handle_chunk_update(self, payload: Dict[str, Any], correlation_id: Optional[str] = None) -> None:
        """Handle chunk update from server."""
        chunks = payload.get("chunks", [])
        map_id = payload.get("map_id", "unknown")

        logger.info(f"Received chunk update: {len(chunks)} chunks for map {map_id}")

        for chunk in chunks:
            chunk_x = chunk.get("chunk_x")
            chunk_y = chunk.get("chunk_y")
            tiles = chunk.get("tiles")

            logger.debug(f"Processing chunk ({chunk_x}, {chunk_y}) with {len(tiles) if tiles else 0} rows")

            if chunk_x is not None and chunk_y is not None and tiles:
                self.game_state.chunks[(chunk_x, chunk_y)] = tiles
                # Log first tile format for debugging
                if tiles and tiles[0]:
                    first_tile = tiles[0][0]
                    logger.debug(f"First tile format: {type(first_tile).__name__} - {first_tile if not isinstance(first_tile, dict) else list(first_tile.keys())}")
                logger.info(f"Stored chunk ({chunk_x}, {chunk_y}) with {len(tiles)} rows")
            else:
                logger.warning(f"Invalid chunk data: chunk_x={chunk_x}, chunk_y={chunk_y}, has_tiles={tiles is not None}")

        self.event_bus.emit(EventType.CHUNK_RECEIVED, {"count": len(chunks)})
    
    async def handle_state_update(self, payload: Dict[str, Any], correlation_id: Optional[str] = None) -> None:
        """Handle mid-frequency state updates (5 TPS)."""
        systems = payload.get("systems", {})
        
        # Update player stats
        if "player" in systems:
            player_data = systems["player"]
            if "current_hp" in player_data:
                self.game_state.current_hp = player_data["current_hp"]
            if "max_hp" in player_data:
                self.game_state.max_hp = player_data["max_hp"]
            if "visual_hash" in player_data:
                self.game_state.visual_hash = player_data["visual_hash"]
        
        # Update entities
        if "entities" in systems:
            for entity_data in systems["entities"]:
                entity_id = entity_data.get("id")
                if entity_id:
                    self.game_state.update_entity(entity_id, entity_data)
        
        self.event_bus.emit(EventType.STATE_CHANGED, {"systems": list(systems.keys())})
    
    async def handle_game_update(self, payload: Dict[str, Any], correlation_id: Optional[str] = None) -> None:
        """Handle high-frequency game updates (20 TPS)."""
        entities = payload.get("entities", [])
        removed_entities = payload.get("removed_entities", [])
        
        # Update existing entities
        for entity in entities:
            entity_id = entity.get("id")
            if entity_id:
                self.game_state.update_entity(entity_id, entity)
        
        # Remove despawned entities
        for entity_id in removed_entities:
            if entity_id in self.game_state.entities:
                del self.game_state.entities[entity_id]
                self.event_bus.emit(EventType.ENTITY_DESPAWNED, {"entity_id": entity_id})
        
        # Update ground items if present
        if "ground_items" in payload:
            self.game_state.ground_items.clear()
            for item in payload["ground_items"]:
                item_id = item.get("ground_item_id")
                if item_id:
                    self.game_state.ground_items[item_id] = item
    
    async def handle_chat_message(self, payload: Dict[str, Any], correlation_id: Optional[str] = None) -> None:
        """Handle incoming chat message."""
        channel = payload.get("channel", "local")
        sender = payload.get("sender", "Unknown")
        message = payload.get("message", "")
        timestamp = payload.get("timestamp", 0)
        
        chat_entry = {
            "channel": channel,
            "sender": sender,
            "message": message,
            "timestamp": timestamp
        }
        
        self.game_state.chat_history.append(chat_entry)
        
        # Keep chat history manageable
        if len(self.game_state.chat_history) > 100:
            self.game_state.chat_history.pop(0)
        
        self.event_bus.emit(EventType.CHAT_MESSAGE_RECEIVED, chat_entry)
    
    async def handle_player_joined(self, payload: Dict[str, Any], correlation_id: Optional[str] = None) -> None:
        """Handle player joined event."""
        player_id = payload.get("player_id")
        username = payload.get("username")
        position = payload.get("position", {})
        
        logger.info(f"Player joined: {username}")
        
        self.game_state.other_players[player_id] = {
            "username": username,
            "position": position,
            "current_hp": payload.get("current_hp", 100),
            "max_hp": payload.get("max_hp", 100)
        }
        
        self.event_bus.emit(EventType.ENTITY_SPAWNED, {"player_id": player_id, "username": username})
    
    async def handle_player_left(self, payload: Dict[str, Any], correlation_id: Optional[str] = None) -> None:
        """Handle player left event."""
        player_id = payload.get("player_id")
        username = payload.get("username")
        
        logger.info(f"Player left: {username}")
        
        if player_id in self.game_state.other_players:
            del self.game_state.other_players[player_id]
        
        self.event_bus.emit(EventType.ENTITY_DESPAWNED, {"player_id": player_id, "username": username})
    
    async def handle_player_died(self, payload: Dict[str, Any], correlation_id: Optional[str] = None) -> None:
        """Handle player died event."""
        player_id = payload.get("player_id")
        username = payload.get("username")
        killed_by = payload.get("killed_by", "Unknown")
        
        logger.info(f"Player {username} died (killed by {killed_by})")
        
        if player_id == self.game_state.player_id:
            self.game_state.is_dead = True
            self.event_bus.emit(EventType.PLAYER_DIED, {"killed_by": killed_by})
    
    async def handle_player_respawn(self, payload: Dict[str, Any], correlation_id: Optional[str] = None) -> None:
        """Handle player respawn event."""
        player_id = payload.get("player_id")
        username = payload.get("username")
        position = payload.get("position", {})
        
        logger.info(f"Player {username} respawned")
        
        if player_id == self.game_state.player_id:
            self.game_state.is_dead = False
            self.game_state.position = position
            self.game_state.current_hp = self.game_state.max_hp
            self.event_bus.emit(EventType.PLAYER_RESPAWNED, {"position": position})
    
    async def handle_combat_action(self, payload: Dict[str, Any], correlation_id: Optional[str] = None) -> None:
        """Handle combat action event."""
        action_type = payload.get("action_type")
        attacker = payload.get("attacker", {})
        target = payload.get("target", {})
        damage = payload.get("damage", 0)
        
        logger.debug(f"Combat action: {action_type} - {damage} damage")
        
        # Add hit splat if damage was dealt
        if damage > 0 or action_type == "miss":
            target_id = target.get("id")
            is_miss = action_type == "miss"
            
            hit_splat = {
                "target_id": target_id,
                "damage": damage,
                "is_miss": is_miss,
                "timestamp": payload.get("timestamp", 0)
            }
            self.game_state.hit_splats.append(hit_splat)
        
        # Track XP gains
        if "skill_xp" in payload:
            for skill, xp in payload["skill_xp"].items():
                self.game_state.add_skill_xp(skill, xp)
        
        self.event_bus.emit(EventType.COMBAT_ACTION_RECEIVED, {
            "action_type": action_type,
            "damage": damage,
            "attacker": attacker.get("id"),
            "target": target.get("id")
        })
    
    async def handle_appearance_update(self, payload: Dict[str, Any], correlation_id: Optional[str] = None) -> None:
        """Handle appearance update event."""
        player_id = payload.get("player_id")
        visual_hash = payload.get("visual_hash")
        
        if player_id == self.game_state.player_id:
            self.game_state.visual_hash = visual_hash
            if "appearance" in payload:
                self.game_state.appearance = payload["appearance"]
        elif player_id in self.game_state.other_players:
            self.game_state.other_players[player_id]["visual_hash"] = visual_hash
        
        self.event_bus.emit(EventType.APPEARANCE_UPDATED, {
            "player_id": player_id,
            "visual_hash": visual_hash
        })
    
    async def handle_server_shutdown(self, payload: Dict[str, Any], correlation_id: Optional[str] = None) -> None:
        """Handle server shutdown warning."""
        reason = payload.get("reason", "Server maintenance")
        countdown = payload.get("countdown_seconds", 60)
        
        logger.warning(f"Server shutdown in {countdown}s: {reason}")
        self.game_state.server_shutdown_warning = {
            "reason": reason,
            "countdown": countdown
        }
    
    # =================================================================
    # RESPONSE HANDLERS
    # =================================================================
    
    async def handle_success_response(self, payload: Dict[str, Any], correlation_id: Optional[str] = None) -> None:
        """Handle success response."""
        message = payload.get("message", "Success")
        data = payload.get("data", payload)
        logger.debug(f"Success: {message}")
        
        # Update game state based on response data
        if "new_position" in data:
            self.game_state.position = data["new_position"]
            self.event_bus.emit(EventType.PLAYER_MOVED, data["new_position"])
    
    async def handle_error_response(self, payload: Dict[str, Any], correlation_id: Optional[str] = None) -> None:
        """Handle error response."""
        error = payload.get("error", "Unknown error")
        code = payload.get("code", "UNKNOWN")
        category = payload.get("category", "system")
        
        logger.error(f"Server error [{code}]: {error}")
        
        # Emit error event for UI to display
        self.event_bus.emit(EventType.ERROR_RECEIVED, {
            "error": error,
            "code": code,
            "category": category
        })
    
    async def handle_data_response(self, payload: Dict[str, Any], correlation_id: Optional[str] = None) -> None:
        """Handle data response from queries."""
        data_type = payload.get("data_type")
        data = payload.get("data", {})
        
        logger.debug(f"Received data response: {data_type}")
        
        if data_type == "inventory":
            self.game_state.update_inventory(data)
            self.event_bus.emit(EventType.INVENTORY_UPDATED, data)
        elif data_type == "equipment":
            self.game_state.update_equipment(data)
            self.event_bus.emit(EventType.EQUIPMENT_UPDATED, data)
        elif data_type == "stats":
            self.game_state.update_stats(data)
            self.event_bus.emit(EventType.STATS_UPDATED, data)
        elif data_type == "map_chunks":
            self.game_state.update_map_chunks(data)
            self.event_bus.emit(EventType.CHUNK_RECEIVED, data)


def register_all_handlers(game_state: "ClientGameState") -> MessageHandlers:
    """Create and register all message handlers with the connection manager."""
    from .connection import get_connection_manager
    
    handlers = MessageHandlers(game_state)
    connection = get_connection_manager()
    
    # Register event handlers
    connection.register_handler(MessageType.EVENT_WELCOME, handlers.handle_welcome)
    connection.register_handler(MessageType.EVENT_CHUNK_UPDATE, handlers.handle_chunk_update)
    connection.register_handler(MessageType.EVENT_STATE_UPDATE, handlers.handle_state_update)
    connection.register_handler(MessageType.EVENT_GAME_UPDATE, handlers.handle_game_update)
    connection.register_handler(MessageType.EVENT_CHAT_MESSAGE, handlers.handle_chat_message)
    connection.register_handler(MessageType.EVENT_PLAYER_JOINED, handlers.handle_player_joined)
    connection.register_handler(MessageType.EVENT_PLAYER_LEFT, handlers.handle_player_left)
    connection.register_handler(MessageType.EVENT_PLAYER_DIED, handlers.handle_player_died)
    connection.register_handler(MessageType.EVENT_PLAYER_RESPAWN, handlers.handle_player_respawn)
    connection.register_handler(MessageType.EVENT_COMBAT_ACTION, handlers.handle_combat_action)
    connection.register_handler(MessageType.EVENT_APPEARANCE_UPDATE, handlers.handle_appearance_update)
    connection.register_handler(MessageType.EVENT_SERVER_SHUTDOWN, handlers.handle_server_shutdown)
    
    # Register response handlers
    connection.register_handler(MessageType.RESP_SUCCESS, handlers.handle_success_response)
    connection.register_handler(MessageType.RESP_ERROR, handlers.handle_error_response)
    connection.register_handler(MessageType.RESP_DATA, handlers.handle_data_response)
    
    logger.info("All message handlers registered")
    return handlers
