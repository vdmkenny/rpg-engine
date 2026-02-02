"""
Refactored RPG Client - Thin client architecture.

All game logic is server-side. This client:
- Receives state from server via WebSocket
- Renders visuals based on server state
- Sends user input commands to server
- Downloads sprites/assets from server via HTTP
"""

import pygame
import asyncio
import websockets
from websockets.protocol import State as WebSocketState
import msgpack
import aiohttp
import sys
import os
import time
from typing import Optional, Dict, Any, List, Tuple

# Import common protocol
workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.append(workspace_root)

from common.src.protocol import (
    MessageType, WSMessage, Direction, ChatChannel,
    COMMAND_TYPES, QUERY_TYPES, EVENT_TYPES, RESPONSE_TYPES,
    PROTOCOL_VERSION
)

# Import client components
from game_states import GameState
from client_state import ClientGameState, EntityType, Entity, GroundItem, HitSplat
from protocol_handler import ProtocolHandler
from chunk_manager import ChunkManager
from tileset_manager import TilesetManager
from sprite_manager import SpriteManager
from paperdoll_renderer import PaperdollRenderer, create_fallback_sprite
from ui_panels import (
    Colors, UIPanel, InventoryPanel, EquipmentPanel, StatsPanel,
    StatusOrb, Minimap, ChatWindow, ContextMenu, ContextMenuItem, Tooltip,
    HelpPanel, HelpButton, LogoutButton, TabbedSidePanel
)
from common.src.sprites.enums import AnimationType

# =============================================================================
# CONSTANTS
# =============================================================================

WINDOW_WIDTH = 1024
WINDOW_HEIGHT = 768
FPS = 60
TILE_SIZE = 32
CHUNK_SIZE = 16

# Movement timing
MOVE_COOLDOWN = 0.15  # seconds between moves (matches server rate limit)
MOVE_DURATION = 0.2  # animation duration

# Network
CHUNK_REQUEST_DISTANCE = 8  # tiles before requesting new chunks

# Server
SERVER_BASE_URL = "http://localhost:8000"
WEBSOCKET_URL = "ws://localhost:8000/ws"

# Client protocol support
CLIENT_SUPPORTED_PROTOCOL = "2.0"  # Minimum protocol version this client supports


# =============================================================================
# MAIN CLIENT CLASS
# =============================================================================

class RPGClient:
    """
    Thin RPG client - renders server state and sends user input.
    
    All game logic is handled server-side. The client:
    1. Authenticates via HTTP
    2. Connects WebSocket for real-time updates
    3. Renders game state received from server
    4. Sends user commands (move, attack, use item, etc.)
    5. Downloads sprites/assets from server HTTP endpoints
    """
    
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("RPG Client")
        self.clock = pygame.time.Clock()
        
        # Fonts
        self.font = pygame.font.Font(None, 36)
        self.small_font = pygame.font.Font(None, 24)
        self.tiny_font = pygame.font.Font(None, 18)
        
        # Game state (received from server)
        self.game_state = ClientGameState()
        self.state = GameState.LOGIN
        
        # Protocol handler for WebSocket communication
        self.protocol = ProtocolHandler()
        self._register_event_handlers()
        
        # Network
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.jwt_token: Optional[str] = None
        self.http_session: Optional[aiohttp.ClientSession] = None
        self._ws_receive_task: Optional[asyncio.Task] = None  # Background WebSocket receiver
        
        # Map and rendering
        self.chunk_manager = ChunkManager()
        self.tileset_manager = TilesetManager()
        self.sprite_manager = SpriteManager(SERVER_BASE_URL)
        self.paperdoll_renderer = PaperdollRenderer(self.sprite_manager)
        self.current_map_id: Optional[str] = None
        
        # Camera
        self.camera_x = 0.0
        self.camera_y = 0.0
        self.target_camera_x = 0.0
        self.target_camera_y = 0.0
        
        # Input state
        self.keys_pressed: set = set()
        self.last_move_time = 0.0
        
        # UI Components
        self._init_ui()
        
        # Login form fields
        self.username_text = ""
        self.password_text = ""
        self.email_text = ""
        self.active_field = "username"
        self.status_message = ""
        self.status_color = Colors.TEXT_WHITE
    
    def _init_ui(self) -> None:
        """Initialize UI components."""
        # Status orbs (top-left area)
        self.hp_orb = StatusOrb(70, 70, 25, Colors.HP_GREEN, "HP")
        self.prayer_orb = StatusOrb(40, 110, 20, Colors.TEXT_CYAN, "Pray")
        self.run_orb = StatusOrb(100, 110, 20, Colors.TEXT_YELLOW, "Run")
        
        # Minimap (top-right)
        self.minimap = Minimap(WINDOW_WIDTH - 85, 75, 60)
        
        # OSRS-style tabbed side panel (bottom-right, mirroring chat position)
        self.side_panel = TabbedSidePanel(
            WINDOW_WIDTH - 214, WINDOW_HEIGHT - 322,  # Same height as chat (312 panel + 10 margin)
            on_inventory_click=self._on_inventory_click,
            on_equipment_click=self._on_equipment_click,
            on_logout=self._on_logout_click
        )
        
        # Keep old panels for compatibility but hide them
        panel_x = WINDOW_WIDTH - 170
        self.inventory_panel = InventoryPanel(
            panel_x, 300,
            on_slot_click=self._on_inventory_click
        )
        self.inventory_panel.visible = False
        
        self.equipment_panel = EquipmentPanel(
            panel_x, 50,
            on_slot_click=self._on_equipment_click
        )
        self.equipment_panel.visible = False
        
        self.stats_panel = StatsPanel(panel_x - 210, 50)
        self.stats_panel.visible = False
        
        # Chat window (bottom-left, wider for readability)
        self.chat_window = ChatWindow(
            10, WINDOW_HEIGHT - 220,
            550, 210,
            self.small_font,
            on_send=self._on_chat_send
        )
        
        # Context menu and tooltip
        self.context_menu = ContextMenu()
        self.tooltip = Tooltip()
        
        # Help panel and button
        self.help_panel = HelpPanel(WINDOW_WIDTH // 2 - 140, WINDOW_HEIGHT // 2 - 170)
        self.help_button = HelpButton(WINDOW_WIDTH - 40, 10)
        
        # Protocol version warning
        self.protocol_warning: Optional[str] = None
        self.protocol_warning_time: float = 0.0
        
        # Tab buttons for panel switching (legacy)
        self.active_panel = "inventory"
    
    def _register_event_handlers(self) -> None:
        """Register handlers for server events."""
        self.protocol.register_event_handler(
            MessageType.EVENT_WELCOME, self._handle_welcome
        )
        self.protocol.register_event_handler(
            MessageType.EVENT_GAME_STATE_UPDATE, self._handle_game_state_update
        )
        self.protocol.register_event_handler(
            MessageType.EVENT_STATE_UPDATE, self._handle_state_update
        )
        self.protocol.register_event_handler(
            MessageType.EVENT_GAME_UPDATE, self._handle_game_update
        )
        self.protocol.register_event_handler(
            MessageType.EVENT_CHAT_MESSAGE, self._handle_chat_message
        )
        self.protocol.register_event_handler(
            MessageType.EVENT_PLAYER_JOINED, self._handle_player_joined
        )
        self.protocol.register_event_handler(
            MessageType.EVENT_PLAYER_LEFT, self._handle_player_left
        )
        self.protocol.register_event_handler(
            MessageType.EVENT_COMBAT_ACTION, self._handle_combat_action
        )
        self.protocol.register_event_handler(
            MessageType.EVENT_PLAYER_DIED, self._handle_player_died
        )
        self.protocol.register_event_handler(
            MessageType.EVENT_PLAYER_RESPAWN, self._handle_player_respawn
        )
        self.protocol.register_event_handler(
            MessageType.RESP_DATA, self._handle_data_response
        )
        self.protocol.register_event_handler(
            MessageType.RESP_ERROR, self._handle_error_response
        )
        self.protocol.register_event_handler(
            MessageType.EVENT_SERVER_SHUTDOWN, self._handle_server_shutdown
        )
    
    # =========================================================================
    # NETWORK - HTTP Authentication
    # =========================================================================
    
    async def _get_http_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self.http_session is None:
            self.http_session = aiohttp.ClientSession()
        return self.http_session
    
    async def attempt_login(self) -> None:
        """Attempt login via HTTP, then connect WebSocket."""
        if not self.username_text or not self.password_text:
            self.status_message = "Please enter username and password"
            self.status_color = Colors.TEXT_RED
            return
        
        self.status_message = "Logging in..."
        self.status_color = Colors.TEXT_WHITE
        
        try:
            session = await self._get_http_session()
            
            async with session.post(
                f"{SERVER_BASE_URL}/auth/login",
                data={"username": self.username_text, "password": self.password_text}
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    self.status_message = f"Login failed: {error_text}"
                    self.status_color = Colors.TEXT_RED
                    return
                
                data = await resp.json()
                self.jwt_token = data.get("access_token")
            
            if not self.jwt_token:
                self.status_message = "No access token received"
                self.status_color = Colors.TEXT_RED
                return
            
            # Set up tileset manager with auth
            self.tileset_manager.set_auth_token(self.jwt_token)
            
            # Set up sprite manager with auth for paperdoll sprites
            self.sprite_manager.set_auth_token(self.jwt_token)
            
            # Connect WebSocket
            await self._connect_websocket()
            
        except Exception as e:
            self.status_message = f"Connection error: {e}"
            self.status_color = Colors.TEXT_RED
    
    async def attempt_register(self) -> None:
        """Attempt registration via HTTP."""
        if not self.username_text or not self.password_text or not self.email_text:
            self.status_message = "Please fill all fields"
            self.status_color = Colors.TEXT_RED
            return
        
        self.status_message = "Registering..."
        self.status_color = Colors.TEXT_WHITE
        
        try:
            session = await self._get_http_session()
            
            async with session.post(
                f"{SERVER_BASE_URL}/auth/register",
                json={
                    "username": self.username_text,
                    "password": self.password_text,
                    "email": self.email_text
                }
            ) as resp:
                if resp.status == 201:
                    self.status_message = "Registration successful! You can now login."
                    self.status_color = Colors.TEXT_GREEN
                    self.state = GameState.LOGIN
                else:
                    error_text = await resp.text()
                    self.status_message = f"Registration failed: {error_text}"
                    self.status_color = Colors.TEXT_RED
                    
        except Exception as e:
            self.status_message = f"Connection error: {e}"
            self.status_color = Colors.TEXT_RED
    
    # =========================================================================
    # NETWORK - WebSocket
    # =========================================================================
    
    async def _connect_websocket(self) -> None:
        """Connect to WebSocket and authenticate."""
        try:
            self.websocket = await websockets.connect(
                WEBSOCKET_URL,
                additional_headers={"Authorization": f"Bearer {self.jwt_token}"}
            )
            
            # Send authentication command
            auth_msg = self.protocol.create_command(
                MessageType.CMD_AUTHENTICATE,
                {"token": self.jwt_token}
            )
            await self._send_message(auth_msg)
            
            self.game_state.username = self.username_text
            self.state = GameState.PLAYING
            self.status_message = "Connected!"
            self.status_color = Colors.TEXT_GREEN
            
            # Clear any stale sprite caches and start preloading common sprites
            self.sprite_manager.clear_memory_cache()
            self.sprite_manager.clear_failed()
            self.paperdoll_renderer.clear_cache()
            
            # Start background WebSocket receiver task (event-driven)
            self._start_websocket_receiver()
            
        except Exception as e:
            self.status_message = f"WebSocket failed: {e}"
            self.status_color = Colors.TEXT_RED
    
    async def _send_message(self, message: WSMessage) -> None:
        """Send a message via WebSocket."""
        if self.websocket:
            packed = msgpack.packb(message.model_dump())
            await self.websocket.send(packed)
    
    async def _websocket_receiver_task(self) -> None:
        """Background task that continuously receives WebSocket messages (event-driven)."""
        try:
            while self.websocket and self.websocket.state == WebSocketState.OPEN:
                try:
                    data = await self.websocket.recv()
                    message = msgpack.unpackb(data, raw=False)
                    
                    # DEBUG: Log all incoming message types
                    msg_type = message.get("type", "UNKNOWN")
                    if msg_type not in ("EVENT_GAME_STATE_UPDATE",):  # Skip noisy ones
                        print(f"[DEBUG] Received message type: {msg_type}")
                    
                    await self.protocol.handle_message(message)
                    
                except websockets.exceptions.ConnectionClosed:
                    print("WebSocket connection closed")
                    break
                except Exception as e:
                    print(f"WebSocket receiver error: {e}")
                    break
        finally:
            print("WebSocket receiver task stopped")
    
    def _start_websocket_receiver(self) -> None:
        """Start the background WebSocket receiver task."""
        if self._ws_receive_task is None or self._ws_receive_task.done():
            self._ws_receive_task = asyncio.create_task(self._websocket_receiver_task())
    
    async def _stop_websocket_receiver(self) -> None:
        """Stop the background WebSocket receiver task."""
        if self._ws_receive_task and not self._ws_receive_task.done():
            self._ws_receive_task.cancel()
            try:
                await self._ws_receive_task
            except asyncio.CancelledError:
                pass
            self._ws_receive_task = None
    
    # =========================================================================
    # EVENT HANDLERS - Server Events
    # =========================================================================
    
    async def _handle_welcome(self, payload: Dict[str, Any]) -> None:
        """Handle welcome event with initial player data."""
        player_data = payload.get("player", {})
        config_data = payload.get("config", {})
        
        # Display welcome message and motd in chat
        welcome_message = payload.get("message", "")
        motd = payload.get("motd", "")
        if welcome_message:
            self.chat_window.add_message("Server", welcome_message, ChatChannel.LOCAL.value)
        if motd:
            self.chat_window.add_message("MOTD", motd, ChatChannel.LOCAL.value)
        
        # Check protocol version from server (inside config object)
        server_version = config_data.get("protocol_version", "1.0")
        self._check_protocol_version(server_version)
        
        if player_data:
            # Server sends nested position and hp objects
            position = player_data.get("position", {})
            hp_data = player_data.get("hp", {})
            
            self.game_state.x = position.get("x", 0) if position else 0
            self.game_state.y = position.get("y", 0) if position else 0
            self.game_state.map_id = position.get("map_id", "samplemap") if position else "samplemap"
            self.game_state.current_hp = hp_data.get("current_hp", 10) if hp_data else 10
            self.game_state.max_hp = hp_data.get("max_hp", 10) if hp_data else 10
            
            # Initialize display position
            self.game_state.display_x = float(self.game_state.x)
            self.game_state.display_y = float(self.game_state.y)
            
            # Update camera immediately
            self._update_camera(instant=True)
            
            # Load tilesets for map
            if self.game_state.map_id:
                self.current_map_id = self.game_state.map_id
                try:
                    await self.tileset_manager.load_map_tilesets(self.current_map_id)
                except Exception as e:
                    print(f"Failed to load tilesets: {e}")
            
            # Request initial chunks
            await self._request_chunks()
            
            # Request initial inventory/equipment/stats
            await self._query_inventory()
            await self._query_equipment()
            await self._query_stats()
        
        # Update timing from config
        if config_data:
            self.game_state.move_duration = config_data.get("animation_duration", MOVE_DURATION)
    
    async def _handle_game_state_update(self, payload: Dict[str, Any]) -> None:
        """Handle game state update (entity positions, etc.)."""
        entities = payload.get("entities", [])
        
        for entity_data in entities:
            entity_type = entity_data.get("type", "")
            
            if entity_type == "player":
                username = entity_data.get("username", "")
                
                if username == self.game_state.username:
                    # Update own player position
                    new_x = entity_data.get("x", self.game_state.x)
                    new_y = entity_data.get("y", self.game_state.y)
                    self.game_state.update_player_position(new_x, new_y)
                    
                    # Update HP if provided
                    if "current_hp" in entity_data:
                        self.game_state.update_player_hp(
                            entity_data.get("current_hp", self.game_state.current_hp),
                            entity_data.get("max_hp", self.game_state.max_hp)
                        )
                    
                    # Update visual state for paperdoll rendering
                    if "visual_state" in entity_data:
                        self.game_state.update_visual_state(
                            entity_data.get("visual_state"),
                            entity_data.get("visual_hash", "")
                        )
                        # Start preloading sprites in background
                        asyncio.create_task(self._preload_player_sprites())
                    
                    # Check if we need new chunks
                    await self._check_chunk_request()
                else:
                    # Update other player
                    self.game_state._update_other_player(username, entity_data)
                    # Preload other player sprites if we have visual state
                    other_player = self.game_state.other_players.get(username)
                    if other_player and other_player.visual_state:
                        asyncio.create_task(self._preload_entity_sprites(other_player))
            
            elif entity_type in ["npc", "monster", "humanoid"]:
                instance_id = entity_data.get("instance_id", 0)
                self.game_state._update_entity(instance_id, entity_data)
            
            elif entity_type == "ground_item":
                ground_item_id = entity_data.get("ground_item_id", "")
                self.game_state._update_ground_item(ground_item_id, entity_data)
        
        # Handle removed entities
        removed = payload.get("removed_entities", [])
        for entity_id in removed:
            try:
                int_id = int(entity_id)
                self.game_state.entities.pop(int_id, None)
            except ValueError:
                self.game_state.ground_items.pop(entity_id, None)
    
    async def _handle_state_update(self, payload: Dict[str, Any]) -> None:
        """Handle state update (inventory, equipment, skills changes)."""
        systems = payload.get("systems", {})
        
        if "inventory" in systems:
            self.game_state.set_inventory(systems["inventory"])
            self._update_inventory_ui()
        
        if "equipment" in systems:
            self.game_state.set_equipment(systems["equipment"])
            self._update_equipment_ui()
        
        if "stats" in systems:
            self.game_state.set_stats(systems["stats"])
        
        if "skills" in systems:
            self.game_state.set_skills(systems["skills"])
            self._update_stats_ui()
        
        if "player" in systems:
            player = systems["player"]
            if "current_hp" in player:
                self.game_state.update_player_hp(
                    player.get("current_hp"),
                    player.get("max_hp", self.game_state.max_hp)
                )
    
    async def _handle_game_update(self, payload: Dict[str, Any]) -> None:
        """Handle game update (entities visibility changes)."""
        entities = payload.get("entities", [])
        removed = payload.get("removed_entities", [])
        
        print(f"[DEBUG] _handle_game_update: received {len(entities)} entities, {len(removed)} removed")
        for e in entities:
            print(f"[DEBUG]   Entity: type={e.get('type')}, username={e.get('username')}, x={e.get('x')}, y={e.get('y')}")
        
        self.game_state.update_entities(entities, removed)
    
    async def _handle_chat_message(self, payload: Dict[str, Any]) -> None:
        """Handle incoming chat message."""
        sender = payload.get("sender", payload.get("username", "Unknown"))
        message = payload.get("message", "")
        channel = payload.get("channel", ChatChannel.LOCAL.value)
        
        self.chat_window.add_message(sender, message, channel)
        
        # Add floating message for local chat
        if channel == ChatChannel.LOCAL.value:
            if sender == self.game_state.username:
                self.game_state.add_floating_message(message)
            elif sender in self.game_state.other_players:
                # Add to other player's floating messages
                pass  # TODO: track floating messages per player
    
    async def _handle_player_joined(self, payload: Dict[str, Any]) -> None:
        """Handle player joined event."""
        player_data = payload.get("player", {})
        username = player_data.get("username", "")
        
        if username and username != self.game_state.username:
            self.chat_window.add_message("System", f"{username} has joined.", ChatChannel.LOCAL.value)
    
    async def _handle_player_left(self, payload: Dict[str, Any]) -> None:
        """Handle player left event."""
        player_id = payload.get("player_id")
        username = payload.get("username", "")
        
        if player_id:
            self.game_state.remove_player(player_id)
        if username:
            self.chat_window.add_message("System", f"{username} has left.", ChatChannel.LOCAL.value)
    
    async def _handle_combat_action(self, payload: Dict[str, Any]) -> None:
        """Handle combat action event (hit splats, etc.)."""
        attacker = payload.get("attacker", "")
        target = payload.get("target", "")
        damage = payload.get("damage", 0)
        is_miss = payload.get("is_miss", False)
        target_type = payload.get("target_type", "")
        target_id = payload.get("target_id")
        
        # Create hit splat on target
        if target == self.game_state.username:
            # Hit on our player
            self.game_state.hit_splats.append(HitSplat(
                damage=damage,
                is_miss=is_miss,
                timestamp=time.time()
            ))
        # TODO: Add hit splats to other entities
    
    async def _handle_player_died(self, payload: Dict[str, Any]) -> None:
        """Handle player death event."""
        username = payload.get("username", "")
        
        if username == self.game_state.username:
            self.chat_window.add_message("System", "Oh dear, you are dead!", ChatChannel.LOCAL.value)
    
    async def _handle_player_respawn(self, payload: Dict[str, Any]) -> None:
        """Handle player respawn event."""
        if "x" in payload and "y" in payload:
            self.game_state.update_player_position(
                payload["x"], payload["y"], animate=False
            )
            self.game_state.current_hp = payload.get("current_hp", self.game_state.max_hp)
            self._update_camera(instant=True)
    
    async def _handle_data_response(self, payload: Dict[str, Any]) -> None:
        """Handle query data response."""
        query_type = payload.get("query_type", "")
        
        if query_type == "inventory":
            self.game_state.set_inventory(payload.get("inventory", {}))
            self._update_inventory_ui()
        
        elif query_type == "equipment":
            self.game_state.set_equipment(payload.get("equipment", {}))
            self._update_equipment_ui()
        
        elif query_type == "stats":
            self.game_state.set_stats(payload.get("stats", {}))
            # Also handle skills data if present
            if "skills" in payload:
                self.game_state.set_skills(payload.get("skills", {}))
                self._update_stats_ui()
        
        elif query_type == "map_chunks":
            chunks = payload.get("chunks", [])
            for chunk in chunks:
                self.chunk_manager.add_chunk(chunk)
    
    async def _handle_error_response(self, payload: Dict[str, Any]) -> None:
        """Handle error response."""
        error_code = payload.get("error_code", "UNKNOWN")
        message = payload.get("message", "An error occurred")
        
        self.chat_window.add_message("Error", f"{error_code}: {message}", ChatChannel.LOCAL.value)
    
    async def _handle_server_shutdown(self, payload: Dict[str, Any]) -> None:
        """Handle server shutdown notification."""
        message = payload.get("message", "Server is shutting down")
        countdown = payload.get("countdown_seconds")
        
        if countdown:
            self.chat_window.add_message("Server", f"{message} (in {countdown}s)", ChatChannel.LOCAL.value)
        else:
            self.chat_window.add_message("Server", message, ChatChannel.LOCAL.value)
        
        # Disconnect and return to login screen
        await self._handle_logout()
    
    def _check_protocol_version(self, server_version: str) -> None:
        """Check if server protocol version is compatible with client."""
        try:
            # Parse versions as tuples for comparison (e.g., "2.0" -> (2, 0))
            client_parts = tuple(int(x) for x in CLIENT_SUPPORTED_PROTOCOL.split("."))
            server_parts = tuple(int(x) for x in server_version.split("."))
            
            if server_parts > client_parts:
                # Server has newer protocol, warn user
                self.protocol_warning = (
                    f"Server uses protocol v{server_version}, "
                    f"client supports v{CLIENT_SUPPORTED_PROTOCOL}. "
                    "Some features may not work correctly. Consider updating your client."
                )
                self.protocol_warning_time = time.time()
                
                # Also add to chat
                self.chat_window.add_message(
                    "System",
                    f"Warning: Protocol mismatch - server v{server_version}, client v{CLIENT_SUPPORTED_PROTOCOL}",
                    ChatChannel.LOCAL.value
                )
                print(f"Protocol Warning: {self.protocol_warning}")
            elif server_parts < client_parts:
                # Client is newer than server (less critical)
                self.chat_window.add_message(
                    "System",
                    f"Note: Server uses older protocol v{server_version}",
                    ChatChannel.LOCAL.value
                )
        except (ValueError, AttributeError) as e:
            print(f"Could not parse protocol version: {e}")
    
    # =========================================================================
    # COMMANDS - Send to Server
    # =========================================================================
    
    async def _send_move(self, direction: Direction) -> None:
        """Send move command to server."""
        msg = self.protocol.create_command(
            MessageType.CMD_MOVE,
            {"direction": direction.value}
        )
        await self._send_message(msg)
        self.last_move_time = time.time()
    
    async def _send_chat(self, channel: str, message: str) -> None:
        """Send chat message to server."""
        msg = self.protocol.create_command(
            MessageType.CMD_CHAT_SEND,
            {"channel": channel, "message": message}
        )
        await self._send_message(msg)
    
    async def _send_attack(self, target_type: str, target_id: int) -> None:
        """Send attack command to server."""
        msg = self.protocol.create_command(
            MessageType.CMD_ATTACK,
            {"target_type": target_type, "target_id": target_id}
        )
        await self._send_message(msg)
    
    async def _send_pickup(self, ground_item_id: str) -> None:
        """Send pickup command to server."""
        msg = self.protocol.create_command(
            MessageType.CMD_ITEM_PICKUP,
            {"ground_item_id": ground_item_id}
        )
        await self._send_message(msg)
    
    async def _send_drop(self, slot: int, quantity: int = 1) -> None:
        """Send drop command to server."""
        msg = self.protocol.create_command(
            MessageType.CMD_ITEM_DROP,
            {"inventory_slot": slot, "quantity": quantity}
        )
        await self._send_message(msg)
    
    async def _send_equip(self, slot: int) -> None:
        """Send equip command to server."""
        msg = self.protocol.create_command(
            MessageType.CMD_ITEM_EQUIP,
            {"inventory_slot": slot}
        )
        await self._send_message(msg)
    
    async def _send_unequip(self, equipment_slot: str) -> None:
        """Send unequip command to server."""
        msg = self.protocol.create_command(
            MessageType.CMD_ITEM_UNEQUIP,
            {"equipment_slot": equipment_slot}
        )
        await self._send_message(msg)
    
    async def _request_chunks(self) -> None:
        """Request map chunks around player."""
        msg = self.protocol.create_query(
            MessageType.QUERY_MAP_CHUNKS,
            {
                "map_id": self.game_state.map_id,
                "center_x": self.game_state.x,
                "center_y": self.game_state.y,
                "radius": 2
            }
        )
        await self._send_message(msg)
        self.game_state.last_chunk_request_x = self.game_state.x
        self.game_state.last_chunk_request_y = self.game_state.y
    
    async def _query_inventory(self) -> None:
        """Query inventory from server."""
        msg = self.protocol.create_query(MessageType.QUERY_INVENTORY, {})
        await self._send_message(msg)
    
    async def _query_equipment(self) -> None:
        """Query equipment from server."""
        msg = self.protocol.create_query(MessageType.QUERY_EQUIPMENT, {})
        await self._send_message(msg)
    
    async def _query_stats(self) -> None:
        """Query stats from server."""
        msg = self.protocol.create_query(MessageType.QUERY_STATS, {})
        await self._send_message(msg)
    
    async def _check_chunk_request(self) -> None:
        """Check if we need to request new chunks."""
        dx = abs(self.game_state.x - self.game_state.last_chunk_request_x)
        dy = abs(self.game_state.y - self.game_state.last_chunk_request_y)
        
        if dx + dy >= CHUNK_REQUEST_DISTANCE:
            await self._request_chunks()
    
    async def _preload_player_sprites(self) -> None:
        """Preload sprites for the player's paperdoll."""
        if not self.game_state.visual_state or not self.game_state.visual_hash:
            return
        
        try:
            await self.paperdoll_renderer.preload_character(
                self.game_state.visual_state,
                self.game_state.visual_hash
            )
        except Exception as e:
            print(f"Error preloading player sprites: {e}")
    
    async def _preload_entity_sprites(self, entity: Entity) -> None:
        """Preload sprites for an entity's paperdoll."""
        if not entity.visual_state or not entity.visual_hash:
            return
        
        try:
            await self.paperdoll_renderer.preload_character(
                entity.visual_state,
                entity.visual_hash
            )
        except Exception as e:
            print(f"Error preloading entity sprites: {e}")
    
    # =========================================================================
    # UI CALLBACKS
    # =========================================================================
    
    def _on_inventory_click(self, slot: int, button: int) -> None:
        """Handle inventory slot click."""
        if slot not in self.game_state.inventory:
            return
        
        item = self.game_state.inventory[slot]
        
        if button == 1:  # Left click - use/equip
            if item.equipable:
                asyncio.create_task(self._send_equip(slot))
        elif button == 3:  # Right click - context menu
            self._show_inventory_context_menu(slot, item)
    
    def _on_equipment_click(self, slot: str, button: int) -> None:
        """Handle equipment slot click."""
        if slot not in self.game_state.equipment:
            return
        
        if button == 1:  # Left click - unequip
            asyncio.create_task(self._send_unequip(slot))
        elif button == 3:  # Right click - context menu
            self._show_equipment_context_menu(slot)
    
    def _on_chat_send(self, channel: str, message: str) -> None:
        """Handle chat send from UI."""
        asyncio.create_task(self._send_chat(channel, message))
    
    def _on_logout_click(self) -> None:
        """Handle logout button click from tabbed panel."""
        asyncio.create_task(self._handle_logout())
    
    def _show_inventory_context_menu(self, slot: int, item) -> None:
        """Show context menu for inventory item."""
        mouse_pos = pygame.mouse.get_pos()
        
        items = [
            ContextMenuItem("Use", lambda: None, Colors.TEXT_WHITE),
        ]
        
        if item.equipable:
            items.append(ContextMenuItem(
                "Equip",
                lambda s=slot: asyncio.create_task(self._send_equip(s)),
                Colors.TEXT_WHITE
            ))
        
        items.append(ContextMenuItem(
            "Drop",
            lambda s=slot: asyncio.create_task(self._send_drop(s)),
            Colors.TEXT_RED
        ))
        
        items.append(ContextMenuItem("Examine", lambda: None, Colors.TEXT_CYAN))
        
        self.context_menu.show(mouse_pos[0], mouse_pos[1], items)
    
    def _show_equipment_context_menu(self, slot: str) -> None:
        """Show context menu for equipment slot."""
        mouse_pos = pygame.mouse.get_pos()
        
        items = [
            ContextMenuItem(
                "Unequip",
                lambda s=slot: asyncio.create_task(self._send_unequip(s)),
                Colors.TEXT_WHITE
            ),
            ContextMenuItem("Examine", lambda: None, Colors.TEXT_CYAN),
        ]
        
        self.context_menu.show(mouse_pos[0], mouse_pos[1], items)
    
    def _update_inventory_ui(self) -> None:
        """Update inventory panel with current state."""
        items = {}
        for slot, item in self.game_state.inventory.items():
            items[slot] = {
                "item_id": item.item_id,
                "name": item.name,
                "quantity": item.quantity,
                "rarity": item.rarity,
            }
        self.inventory_panel.set_items(items)
        self.side_panel.set_items(items)
    
    def _update_equipment_ui(self) -> None:
        """Update equipment panel with current state."""
        equipment = {}
        for slot, item in self.game_state.equipment.items():
            equipment[slot] = {
                "item_id": item.item_id,
                "name": item.name,
                "rarity": item.rarity,
            }
        self.equipment_panel.set_equipment(equipment)
        self.side_panel.set_equipment(equipment)
    
    def _update_stats_ui(self) -> None:
        """Update stats panel with current skills."""
        skills = {}
        for name, skill in self.game_state.skills.items():
            skills[name] = {
                "level": skill.level,
                "experience": skill.experience,
            }
        self.stats_panel.set_skills(skills)
        self.side_panel.set_skills(skills)
    
    # =========================================================================
    # INPUT HANDLING
    # =========================================================================
    
    async def _handle_login_event(self, event: pygame.event.Event) -> None:
        """Handle events in login/register state."""
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_TAB:
                # Cycle through fields
                if self.state == GameState.LOGIN:
                    fields = ["username", "password"]
                else:
                    fields = ["username", "password", "email"]
                idx = fields.index(self.active_field) if self.active_field in fields else 0
                self.active_field = fields[(idx + 1) % len(fields)]
            
            elif event.key == pygame.K_RETURN:
                if self.state == GameState.LOGIN:
                    await self.attempt_login()
                else:
                    await self.attempt_register()
            
            elif event.key == pygame.K_BACKSPACE:
                if self.active_field == "username":
                    self.username_text = self.username_text[:-1]
                elif self.active_field == "password":
                    self.password_text = self.password_text[:-1]
                elif self.active_field == "email":
                    self.email_text = self.email_text[:-1]
            
            elif event.unicode and event.unicode.isprintable():
                if self.active_field == "username":
                    self.username_text += event.unicode
                elif self.active_field == "password":
                    self.password_text += event.unicode
                elif self.active_field == "email":
                    self.email_text += event.unicode
        
        elif event.type == pygame.MOUSEBUTTONDOWN:
            # Check for button clicks
            mouse_pos = event.pos
            
            # Simple button areas
            center_x = WINDOW_WIDTH // 2
            
            # Input field click detection
            username_rect = pygame.Rect(center_x - 150, 300, 300, 40)
            password_rect = pygame.Rect(center_x - 150, 360, 300, 40)
            email_rect = pygame.Rect(center_x - 150, 420, 300, 40)
            
            if username_rect.collidepoint(mouse_pos):
                self.active_field = "username"
            elif password_rect.collidepoint(mouse_pos):
                self.active_field = "password"
            elif email_rect.collidepoint(mouse_pos) and self.state == GameState.REGISTER:
                self.active_field = "email"
            
            # Login/Register button
            btn_rect = pygame.Rect(center_x - 80, 480, 160, 40)
            if btn_rect.collidepoint(mouse_pos):
                if self.state == GameState.LOGIN:
                    await self.attempt_login()
                else:
                    await self.attempt_register()
            
            # Switch mode button
            switch_rect = pygame.Rect(center_x - 80, 530, 160, 40)
            if switch_rect.collidepoint(mouse_pos):
                if self.state == GameState.LOGIN:
                    self.state = GameState.REGISTER
                else:
                    self.state = GameState.LOGIN
                # Reset active field to username when switching modes
                self.active_field = "username"
    
    async def _handle_game_event(self, event: pygame.event.Event) -> None:
        """Handle events in playing state."""
        # Help panel takes high priority when visible
        if self.help_panel.handle_event(event):
            return
        
        # Help button
        if self.help_button.handle_event(event):
            self.help_panel.visible = not self.help_panel.visible
            return
        
        # Context menu takes priority
        if self.context_menu.handle_event(event):
            return
        
        # Tabbed side panel (OSRS-style)
        side_panel_action = self.side_panel.handle_event(event)
        if side_panel_action:
            if side_panel_action == "logout":
                await self._handle_logout()
            return
        
        # Chat window
        if self.chat_window.handle_event(event):
            # Process pending chat message
            if self.chat_window.pending_message:
                channel, message = self.chat_window.pending_message
                self.chat_window.pending_message = None
                await self._send_chat(channel, message)
            return
        
        # Track key state for movement
        if event.type == pygame.KEYDOWN:
            self.keys_pressed.add(event.key)
            
            # Toggle help with ? key (shift+/)
            if event.unicode == "?":
                self.help_panel.visible = not self.help_panel.visible
                return
            
            # ESC closes help panel (and other panels)
            if event.key == pygame.K_ESCAPE:
                if self.help_panel.visible:
                    self.help_panel.visible = False
                    return
            
            # Toggle tabs with I/E/S keys
            if event.key == pygame.K_i:
                self.side_panel.active_tab = "inventory"
            elif event.key == pygame.K_e:
                self.side_panel.active_tab = "equipment"
            elif event.key == pygame.K_s and not (pygame.key.get_mods() & pygame.KMOD_CTRL):
                self.side_panel.active_tab = "stats"
            elif event.key == pygame.K_t:
                if not self.chat_window.input_focused:
                    self.chat_window.input_focused = True
            elif event.key == pygame.K_c:
                # Toggle chat visibility (only when not typing)
                if not self.chat_window.input_focused:
                    self.chat_window.toggle_visibility()
        
        elif event.type == pygame.KEYUP:
            self.keys_pressed.discard(event.key)
        
        elif event.type == pygame.MOUSEBUTTONDOWN:
            # Handle game world clicks
            if event.button == 1:  # Left click
                await self._handle_world_click(event.pos)
            elif event.button == 3:  # Right click
                await self._handle_world_right_click(event.pos)
    
    async def _handle_logout(self) -> None:
        """Handle logout - disconnect and return to login screen."""
        # Stop WebSocket receiver task
        await self._stop_websocket_receiver()
        
        # Close websocket connection gracefully
        if self.websocket and self.websocket.state == WebSocketState.OPEN:
            try:
                await self.websocket.close(code=1000, reason="User logout")
            except Exception:
                pass
            self.websocket = None
        
        # Reset game state
        self.game_state.reset()
        
        # Reset authentication
        self.jwt_token = None
        
        # Clear paperdoll cache
        self.paperdoll_renderer.clear_cache()
        
        # Clear chunk manager
        self.chunk_manager.chunks.clear()
        
        # Reset to login state
        self.state = GameState.LOGIN
        self.username_text = ""
        self.password_text = ""
        self.status_message = "Logged out"
        self.status_color = Colors.TEXT_WHITE
        self.email_input = ""
        self.active_field = "username"
        
        # Add system message
        print("Logged out successfully")
    
    async def _handle_world_click(self, pos: Tuple[int, int]) -> None:
        """Handle left click in game world."""
        world_x, world_y = self._screen_to_world(pos)
        tile_x = int(world_x // TILE_SIZE)
        tile_y = int(world_y // TILE_SIZE)
        
        # Check for entity at position
        for instance_id, entity in self.game_state.entities.items():
            if entity.x == tile_x and entity.y == tile_y:
                if entity.is_attackable:
                    await self._send_attack("entity", instance_id)
                return
        
        # Check for ground item at position
        for ground_item_id, item in self.game_state.ground_items.items():
            if item.x == tile_x and item.y == tile_y:
                await self._send_pickup(ground_item_id)
                return
    
    async def _handle_world_right_click(self, pos: Tuple[int, int]) -> None:
        """Handle right click in game world."""
        world_x, world_y = self._screen_to_world(pos)
        tile_x = int(world_x // TILE_SIZE)
        tile_y = int(world_y // TILE_SIZE)
        
        # Check for entity at position
        for instance_id, entity in self.game_state.entities.items():
            if entity.x == tile_x and entity.y == tile_y:
                self._show_entity_context_menu(pos, entity)
                return
        
        # Check for ground item
        for ground_item_id, item in self.game_state.ground_items.items():
            if item.x == tile_x and item.y == tile_y:
                self._show_ground_item_context_menu(pos, item)
                return
    
    def _show_entity_context_menu(self, pos: Tuple[int, int], entity: Entity) -> None:
        """Show context menu for entity."""
        items = []
        
        if entity.is_attackable:
            items.append(ContextMenuItem(
                f"Attack {entity.display_name}",
                lambda e=entity: asyncio.create_task(self._send_attack("entity", e.instance_id)),
                Colors.TEXT_RED
            ))
        
        items.append(ContextMenuItem(f"Examine {entity.display_name}", lambda: None, Colors.TEXT_CYAN))
        
        self.context_menu.show(pos[0], pos[1], items)
    
    def _show_ground_item_context_menu(self, pos: Tuple[int, int], item: GroundItem) -> None:
        """Show context menu for ground item."""
        items = [
            ContextMenuItem(
                f"Take {item.display_name}",
                lambda i=item: asyncio.create_task(self._send_pickup(i.ground_item_id)),
                Colors.TEXT_WHITE
            ),
            ContextMenuItem(f"Examine {item.display_name}", lambda: None, Colors.TEXT_CYAN),
        ]
        
        self.context_menu.show(pos[0], pos[1], items)
    
    async def _process_movement(self) -> None:
        """Process continuous movement from held keys."""
        if self.chat_window.input_focused:
            return
        
        current_time = time.time()
        if current_time - self.last_move_time < MOVE_COOLDOWN:
            return
        
        # Check if still animating
        if self.game_state.is_moving:
            progress = (current_time - self.game_state.move_start_time) / self.game_state.move_duration
            if progress < 0.5:  # Allow next move at 50% animation completion
                return
        
        # Determine direction
        direction = None
        if pygame.K_w in self.keys_pressed or pygame.K_UP in self.keys_pressed:
            direction = Direction.UP
        elif pygame.K_s in self.keys_pressed or pygame.K_DOWN in self.keys_pressed:
            direction = Direction.DOWN
        elif pygame.K_a in self.keys_pressed or pygame.K_LEFT in self.keys_pressed:
            direction = Direction.LEFT
        elif pygame.K_d in self.keys_pressed or pygame.K_RIGHT in self.keys_pressed:
            direction = Direction.RIGHT
        
        if direction:
            await self._send_move(direction)
    
    # =========================================================================
    # RENDERING
    # =========================================================================
    
    def _update_camera(self, instant: bool = False) -> None:
        """Update camera to follow player."""
        self.target_camera_x = self.game_state.display_x * TILE_SIZE - WINDOW_WIDTH // 2
        self.target_camera_y = self.game_state.display_y * TILE_SIZE - WINDOW_HEIGHT // 2
        
        if instant:
            self.camera_x = self.target_camera_x
            self.camera_y = self.target_camera_y
        else:
            lerp = 0.15
            self.camera_x += (self.target_camera_x - self.camera_x) * lerp
            self.camera_y += (self.target_camera_y - self.camera_y) * lerp
    
    def _world_to_screen(self, world_x: float, world_y: float) -> Tuple[float, float]:
        """Convert world coordinates to screen coordinates."""
        return world_x - self.camera_x, world_y - self.camera_y
    
    def _screen_to_world(self, screen_pos: Tuple[int, int]) -> Tuple[float, float]:
        """Convert screen coordinates to world coordinates."""
        return screen_pos[0] + self.camera_x, screen_pos[1] + self.camera_y
    
    def _draw_login_form(self) -> None:
        """Draw login/register form."""
        self.screen.fill(Colors.PANEL_BG)
        
        center_x = WINDOW_WIDTH // 2
        
        # Title
        title = "Login" if self.state == GameState.LOGIN else "Register"
        title_surface = self.font.render(title, True, Colors.TEXT_ORANGE)
        self.screen.blit(title_surface, (center_x - title_surface.get_width() // 2, 150))
        
        # Fields
        fields = [
            ("Username", self.username_text, "username", 300),
            ("Password", "*" * len(self.password_text), "password", 360),
        ]
        
        if self.state == GameState.REGISTER:
            fields.append(("Email", self.email_text, "email", 420))
        
        for label, value, field_name, y_pos in fields:
            # Label
            label_surface = self.small_font.render(label, True, Colors.TEXT_WHITE)
            self.screen.blit(label_surface, (center_x - 150, y_pos - 20))
            
            # Field background
            field_rect = pygame.Rect(center_x - 150, y_pos, 300, 40)
            pygame.draw.rect(self.screen, Colors.SLOT_BG, field_rect)
            
            border_color = Colors.TEXT_ORANGE if self.active_field == field_name else Colors.SLOT_BORDER
            pygame.draw.rect(self.screen, border_color, field_rect, 2)
            
            # Field text
            text_surface = self.font.render(value, True, Colors.TEXT_WHITE)
            self.screen.blit(text_surface, (field_rect.x + 10, field_rect.y + 8))
        
        # Buttons
        btn_y = 480 if self.state == GameState.LOGIN else 500
        
        # Login/Register button
        btn_rect = pygame.Rect(center_x - 80, btn_y, 160, 40)
        pygame.draw.rect(self.screen, Colors.STONE_MEDIUM, btn_rect)
        pygame.draw.rect(self.screen, Colors.STONE_HIGHLIGHT, btn_rect, 2)
        
        btn_text = "Login" if self.state == GameState.LOGIN else "Register"
        btn_surface = self.font.render(btn_text, True, Colors.TEXT_WHITE)
        self.screen.blit(btn_surface, (center_x - btn_surface.get_width() // 2, btn_y + 8))
        
        # Switch mode button
        switch_rect = pygame.Rect(center_x - 80, btn_y + 50, 160, 40)
        pygame.draw.rect(self.screen, Colors.STONE_DARK, switch_rect)
        pygame.draw.rect(self.screen, Colors.SLOT_BORDER, switch_rect, 2)
        
        switch_text = "Register" if self.state == GameState.LOGIN else "Login"
        switch_surface = self.small_font.render(f"Go to {switch_text}", True, Colors.TEXT_GRAY)
        self.screen.blit(switch_surface, (center_x - switch_surface.get_width() // 2, btn_y + 60))
        
        # Status message
        if self.status_message:
            status_surface = self.small_font.render(self.status_message, True, self.status_color)
            self.screen.blit(status_surface, (center_x - status_surface.get_width() // 2, 650))
    
    def _draw_game(self) -> None:
        """Draw the game world and UI."""
        self.screen.fill((0, 0, 0))
        
        # Draw map chunks
        self._draw_chunks()
        
        # Draw ground items
        self._draw_ground_items()
        
        # Draw entities (NPCs, monsters)
        self._draw_entities()
        
        # Draw other players
        self._draw_other_players()
        
        # Draw own player
        self._draw_player()
        
        # Draw floating messages
        self._draw_floating_messages()
        
        # Draw hit splats
        self._draw_hit_splats()
        
        # Draw UI
        self._draw_ui()
    
    def _draw_chunks(self) -> None:
        """Draw visible map chunks."""
        for (chunk_x, chunk_y), chunk_data in self.chunk_manager.chunks.items():
            self._draw_chunk(chunk_x, chunk_y, chunk_data)
    
    def _draw_chunk(self, chunk_x: int, chunk_y: int, chunk_data: Dict) -> None:
        """Draw a single chunk."""
        chunk_world_x = chunk_x * CHUNK_SIZE * TILE_SIZE
        chunk_world_y = chunk_y * CHUNK_SIZE * TILE_SIZE
        
        screen_x, screen_y = self._world_to_screen(chunk_world_x, chunk_world_y)
        
        # Culling
        if (screen_x > WINDOW_WIDTH or screen_y > WINDOW_HEIGHT or
            screen_x + CHUNK_SIZE * TILE_SIZE < 0 or screen_y + CHUNK_SIZE * TILE_SIZE < 0):
            return
        
        tiles = chunk_data.get("tiles", [])
        if not tiles:
            return
        
        # Handle 2D and flat array formats
        if tiles and isinstance(tiles[0], list):
            for ty in range(min(CHUNK_SIZE, len(tiles))):
                for tx in range(min(CHUNK_SIZE, len(tiles[ty]))):
                    tile_data = tiles[ty][tx]
                    self._draw_tile(screen_x + tx * TILE_SIZE, screen_y + ty * TILE_SIZE, tile_data)
        else:
            for ty in range(CHUNK_SIZE):
                for tx in range(CHUNK_SIZE):
                    idx = ty * CHUNK_SIZE + tx
                    if idx < len(tiles):
                        self._draw_tile(screen_x + tx * TILE_SIZE, screen_y + ty * TILE_SIZE, tiles[idx])
    
    def _draw_tile(self, screen_x: float, screen_y: float, tile_data: Any) -> None:
        """Draw a single tile."""
        if isinstance(tile_data, dict):
            # Multi-layer tile format
            layers = tile_data.get("layers", [])
            for layer in layers:
                gid = layer.get("gid", 0)
                if gid > 0 and self.current_map_id:
                    sprite = self.tileset_manager.get_tile_sprite(gid, self.current_map_id)
                    if sprite:
                        self.screen.blit(sprite, (int(screen_x), int(screen_y)))
        elif isinstance(tile_data, int) and tile_data > 0:
            if self.current_map_id:
                sprite = self.tileset_manager.get_tile_sprite(tile_data, self.current_map_id)
                if sprite:
                    self.screen.blit(sprite, (int(screen_x), int(screen_y)))
    
    def _draw_ground_items(self) -> None:
        """Draw ground items."""
        for item in self.game_state.ground_items.values():
            screen_x, screen_y = self._world_to_screen(item.x * TILE_SIZE, item.y * TILE_SIZE)
            
            if -TILE_SIZE < screen_x < WINDOW_WIDTH and -TILE_SIZE < screen_y < WINDOW_HEIGHT:
                # Draw simple item indicator
                pygame.draw.rect(
                    self.screen, Colors.TEXT_YELLOW,
                    (int(screen_x) + 8, int(screen_y) + 8, 16, 16)
                )
                pygame.draw.rect(
                    self.screen, Colors.PANEL_BORDER,
                    (int(screen_x) + 8, int(screen_y) + 8, 16, 16), 1
                )
    
    def _draw_entities(self) -> None:
        """Draw NPCs and monsters."""
        for entity in self.game_state.entities.values():
            self._draw_entity(entity)
    
    def _draw_entity(self, entity: Entity) -> None:
        """Draw a single entity."""
        screen_x, screen_y = self._world_to_screen(
            entity.display_x * TILE_SIZE,
            entity.display_y * TILE_SIZE
        )
        
        if not (-TILE_SIZE < screen_x < WINDOW_WIDTH and -TILE_SIZE < screen_y < WINDOW_HEIGHT):
            return
        
        # Try to render paperdoll sprite for humanoid entities
        sprite = None
        if entity.visual_state and entity.visual_hash:
            if entity.is_moving:
                # Calculate walk progress
                current_time = time.time()
                elapsed = current_time - entity.move_start_time
                progress = min(elapsed / self.game_state.move_duration, 1.0)
                sprite = self.paperdoll_renderer.get_walk_frame(
                    entity.visual_state,
                    entity.visual_hash,
                    entity.facing_direction,
                    progress,
                    render_size=TILE_SIZE,
                )
            else:
                sprite = self.paperdoll_renderer.get_idle_frame(
                    entity.visual_state,
                    entity.visual_hash,
                    entity.facing_direction,
                    render_size=TILE_SIZE,
                )
        
        if sprite:
            self.screen.blit(sprite, (int(screen_x), int(screen_y)))
        else:
            # Fallback to colored rectangle
            if entity.entity_type == EntityType.MONSTER:
                color = Colors.TEXT_RED
            else:
                color = Colors.TEXT_YELLOW
            
            pygame.draw.rect(self.screen, color, (int(screen_x), int(screen_y), TILE_SIZE, TILE_SIZE))
            pygame.draw.rect(self.screen, Colors.PANEL_BORDER, (int(screen_x), int(screen_y), TILE_SIZE, TILE_SIZE), 1)
        
        # Draw health bar if damaged
        if entity.current_hp < entity.max_hp:
            self._draw_health_bar(screen_x, screen_y - 8, TILE_SIZE, 4, entity.current_hp, entity.max_hp)
        
        # Draw name
        name_surface = self.tiny_font.render(entity.display_name, True, Colors.TEXT_WHITE)
        name_x = int(screen_x + TILE_SIZE // 2 - name_surface.get_width() // 2)
        self.screen.blit(name_surface, (name_x, int(screen_y) - 20))
    
    def _draw_other_players(self) -> None:
        """Draw other players."""
        for player_id, player in self.game_state.other_players.items():
            self._draw_other_player(player)
    
    def _draw_other_player(self, player: Entity) -> None:
        """Draw another player."""
        username = player.name  # Username is stored in the Entity for display
        screen_x, screen_y = self._world_to_screen(
            player.display_x * TILE_SIZE,
            player.display_y * TILE_SIZE
        )
        
        if not (-TILE_SIZE < screen_x < WINDOW_WIDTH and -TILE_SIZE < screen_y < WINDOW_HEIGHT):
            return
        
        # Try to render paperdoll sprite
        sprite = None
        if player.visual_state and player.visual_hash:
            if player.is_moving:
                # Calculate walk progress
                current_time = time.time()
                elapsed = current_time - player.move_start_time
                progress = min(elapsed / self.game_state.move_duration, 1.0)
                sprite = self.paperdoll_renderer.get_walk_frame(
                    player.visual_state,
                    player.visual_hash,
                    player.facing_direction,
                    progress,
                    render_size=TILE_SIZE,
                )
            else:
                sprite = self.paperdoll_renderer.get_idle_frame(
                    player.visual_state,
                    player.visual_hash,
                    player.facing_direction,
                    render_size=TILE_SIZE,
                )
        
        if sprite:
            self.screen.blit(sprite, (int(screen_x), int(screen_y)))
        else:
            # Fallback to colored rectangle based on username hash
            color = self._get_player_color(username)
            pygame.draw.rect(self.screen, color, (int(screen_x), int(screen_y), TILE_SIZE, TILE_SIZE))
            pygame.draw.rect(self.screen, Colors.PANEL_BORDER, (int(screen_x), int(screen_y), TILE_SIZE, TILE_SIZE), 1)
        
        # Draw name
        name_surface = self.tiny_font.render(username, True, Colors.TEXT_WHITE)
        name_x = int(screen_x + TILE_SIZE // 2 - name_surface.get_width() // 2)
        self.screen.blit(name_surface, (name_x, int(screen_y) - 20))
    
    def _draw_player(self) -> None:
        """Draw the player character."""
        screen_x, screen_y = self._world_to_screen(
            self.game_state.display_x * TILE_SIZE,
            self.game_state.display_y * TILE_SIZE
        )
        
        # Try to render paperdoll sprite
        sprite = None
        if self.game_state.visual_state and self.game_state.visual_hash:
            if self.game_state.is_moving:
                # Calculate walk progress
                current_time = time.time()
                elapsed = current_time - self.game_state.move_start_time
                progress = min(elapsed / self.game_state.move_duration, 1.0)
                sprite = self.paperdoll_renderer.get_walk_frame(
                    self.game_state.visual_state,
                    self.game_state.visual_hash,
                    self.game_state.facing_direction,
                    progress,
                    render_size=TILE_SIZE,
                )
            else:
                sprite = self.paperdoll_renderer.get_idle_frame(
                    self.game_state.visual_state,
                    self.game_state.visual_hash,
                    self.game_state.facing_direction,
                    render_size=TILE_SIZE,
                )
        
        if sprite:
            self.screen.blit(sprite, (int(screen_x), int(screen_y)))
            # Draw white border to indicate own player
            pygame.draw.rect(self.screen, Colors.TEXT_WHITE, (int(screen_x), int(screen_y), TILE_SIZE, TILE_SIZE), 2)
        else:
            # Fallback to colored rectangle
            color = self._get_player_color(self.game_state.username)
            pygame.draw.rect(self.screen, color, (int(screen_x), int(screen_y), TILE_SIZE, TILE_SIZE))
            pygame.draw.rect(self.screen, Colors.TEXT_WHITE, (int(screen_x), int(screen_y), TILE_SIZE, TILE_SIZE), 2)
        
        # Draw name
        name_surface = self.tiny_font.render(self.game_state.username, True, Colors.TEXT_GREEN)
        name_x = int(screen_x + TILE_SIZE // 2 - name_surface.get_width() // 2)
        self.screen.blit(name_surface, (name_x, int(screen_y) - 20))
        
        # Draw health bar
        self._draw_health_bar(
            screen_x, screen_y - 8, TILE_SIZE, 4,
            self.game_state.current_hp, self.game_state.max_hp
        )
    
    def _draw_health_bar(
        self, x: float, y: float, width: int, height: int,
        current: int, maximum: int
    ) -> None:
        """Draw a health bar."""
        # Background
        pygame.draw.rect(self.screen, Colors.HP_BG, (int(x), int(y), width, height))
        
        # Fill
        if maximum > 0:
            fill_width = int(width * current / maximum)
            pygame.draw.rect(self.screen, Colors.HP_GREEN, (int(x), int(y), fill_width, height))
        
        # Border
        pygame.draw.rect(self.screen, Colors.HP_BORDER, (int(x), int(y), width, height), 1)
    
    def _draw_floating_messages(self) -> None:
        """Draw floating chat messages."""
        current_time = time.time()
        
        screen_x, screen_y = self._world_to_screen(
            self.game_state.display_x * TILE_SIZE,
            self.game_state.display_y * TILE_SIZE
        )
        
        y_offset = 0
        for msg in self.game_state.floating_messages:
            alpha = msg.get_alpha(current_time)
            
            # Create message surface
            text_surface = self.small_font.render(msg.message, True, Colors.TEXT_WHITE)
            
            # Apply alpha
            if alpha < 255:
                text_surface.set_alpha(alpha)
            
            # Position
            msg_x = int(screen_x + TILE_SIZE // 2 - text_surface.get_width() // 2)
            msg_y = int(screen_y - 40 - y_offset)
            
            # Background bubble
            bubble_rect = pygame.Rect(
                msg_x - 4, msg_y - 2,
                text_surface.get_width() + 8, text_surface.get_height() + 4
            )
            bubble_surface = pygame.Surface((bubble_rect.width, bubble_rect.height), pygame.SRCALPHA)
            pygame.draw.rect(bubble_surface, (0, 0, 0, min(180, alpha)), bubble_surface.get_rect(), border_radius=4)
            self.screen.blit(bubble_surface, bubble_rect.topleft)
            
            self.screen.blit(text_surface, (msg_x, msg_y))
            y_offset += 25
    
    def _draw_hit_splats(self) -> None:
        """Draw hit splat damage indicators."""
        current_time = time.time()
        
        screen_x, screen_y = self._world_to_screen(
            self.game_state.display_x * TILE_SIZE,
            self.game_state.display_y * TILE_SIZE
        )
        
        for splat in self.game_state.hit_splats:
            y_offset = splat.get_y_offset(current_time)
            
            # Splat color
            if splat.is_heal:
                color = Colors.HIT_SPLAT_HEAL
            elif splat.is_miss:
                color = Colors.HIT_SPLAT_MISS
            else:
                color = Colors.HIT_SPLAT_DAMAGE
            
            # Draw splat circle
            splat_x = int(screen_x + TILE_SIZE // 2)
            splat_y = int(screen_y + TILE_SIZE // 2 + y_offset)
            
            pygame.draw.circle(self.screen, color, (splat_x, splat_y), 12)
            pygame.draw.circle(self.screen, Colors.PANEL_BORDER, (splat_x, splat_y), 12, 1)
            
            # Draw damage number
            text = str(splat.damage) if not splat.is_miss else "0"
            text_surface = self.tiny_font.render(text, True, Colors.TEXT_WHITE)
            self.screen.blit(text_surface, (splat_x - text_surface.get_width() // 2, splat_y - text_surface.get_height() // 2))
    
    def _draw_ui(self) -> None:
        """Draw all UI elements."""
        # HP orb
        self.hp_orb.set_value(self.game_state.current_hp, self.game_state.max_hp)
        self.hp_orb.draw(self.screen, self.small_font)
        
        # Minimap
        other_players = [(p.x, p.y) for p in self.game_state.other_players.values()]
        npcs = [(e.x, e.y) for e in self.game_state.entities.values() if e.entity_type == EntityType.NPC]
        monsters = [(e.x, e.y) for e in self.game_state.entities.values() if e.entity_type == EntityType.MONSTER]
        
        self.minimap.update(
            self.game_state.x, self.game_state.y,
            other_players, npcs, monsters
        )
        self.minimap.draw(self.screen, self.small_font)
        
        # Help button (top-right, before minimap)
        self.help_button.draw(self.screen, self.small_font)
        
        # OSRS-style tabbed side panel (bottom-right)
        self.side_panel.draw(self.screen, self.small_font)
        
        # Chat window
        self.chat_window.draw(self.screen, self.small_font)
        
        # Context menu (on top of everything)
        self.context_menu.draw(self.screen, self.small_font)
        
        # Tooltip
        self.tooltip.draw(self.screen, self.small_font)
        
        # Help panel (on top of everything except context menu)
        self.help_panel.draw(self.screen, self.small_font)
        
        # Protocol version warning (fades out after 10 seconds)
        if self.protocol_warning and time.time() - self.protocol_warning_time < 10.0:
            self._draw_protocol_warning()
        
        # FPS counter
        fps = int(self.clock.get_fps())
        fps_text = self.tiny_font.render(f"FPS: {fps}", True, Colors.TEXT_WHITE)
        self.screen.blit(fps_text, (10, 10))
    
    def _draw_protocol_warning(self) -> None:
        """Draw protocol version warning banner."""
        if not self.protocol_warning:
            return
        
        # Calculate fade (fade out over last 3 seconds of 10-second display)
        elapsed = time.time() - self.protocol_warning_time
        alpha = 255
        if elapsed > 7.0:
            alpha = int(255 * (1.0 - (elapsed - 7.0) / 3.0))
        
        # Create warning banner
        padding = 10
        warning_font = pygame.font.Font(None, 20)
        text_surface = warning_font.render(self.protocol_warning, True, Colors.TEXT_YELLOW)
        
        banner_width = text_surface.get_width() + padding * 2
        banner_height = text_surface.get_height() + padding * 2
        banner_x = (WINDOW_WIDTH - banner_width) // 2
        banner_y = 50
        
        # Semi-transparent background
        banner_surface = pygame.Surface((banner_width, banner_height), pygame.SRCALPHA)
        pygame.draw.rect(banner_surface, (80, 60, 0, min(200, alpha)), banner_surface.get_rect(), border_radius=5)
        pygame.draw.rect(banner_surface, (255, 200, 0, alpha), banner_surface.get_rect(), 2, border_radius=5)
        
        self.screen.blit(banner_surface, (banner_x, banner_y))
        
        # Text with alpha
        text_surface.set_alpha(alpha)
        self.screen.blit(text_surface, (banner_x + padding, banner_y + padding))
    
    def _get_player_color(self, username: str) -> Tuple[int, int, int]:
        """Get color for a player based on username hash."""
        h = hash(username)
        r = max(100, (h & 0xFF0000) >> 16)
        g = max(100, (h & 0x00FF00) >> 8)
        b = max(100, h & 0x0000FF)
        return (r, g, b)
    
    # =========================================================================
    # MAIN LOOP
    # =========================================================================
    
    async def run(self) -> None:
        """Main game loop."""
        running = True
        
        while running:
            # Handle events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                
                if self.state in [GameState.LOGIN, GameState.REGISTER]:
                    await self._handle_login_event(event)
                elif self.state == GameState.PLAYING:
                    await self._handle_game_event(event)
            
            # Game logic (playing state)
            if self.state == GameState.PLAYING:
                # WebSocket messages are now received in background task (event-driven)
                # No polling needed here!
                
                # Process movement
                await self._process_movement()
                
                # Update animations
                self.game_state.update_animations(time.time(), self.game_state.move_duration)
                
                # Update camera
                self._update_camera()
                
                # Clean up protocol
                self.protocol.cleanup_expired_requests()
            
            # Render
            if self.state in [GameState.LOGIN, GameState.REGISTER]:
                self._draw_login_form()
            elif self.state == GameState.PLAYING:
                self._draw_game()
            
            pygame.display.flip()
            self.clock.tick(FPS)
            
            # Yield to other async tasks
            await asyncio.sleep(0)
        
        # Cleanup
        print("Shutting down client...")
        
        # Stop WebSocket receiver task first
        await self._stop_websocket_receiver()
        
        # Close WebSocket connection gracefully (sends close frame to server)
        if self.websocket and self.websocket.state == WebSocketState.OPEN:
            try:
                print("Closing WebSocket connection...")
                await self.websocket.close(code=1000, reason="Client shutdown")
                print("WebSocket closed")
            except Exception as e:
                print(f"Error closing WebSocket: {e}")
        
        # Close HTTP session
        if self.http_session:
            await self.http_session.close()
        
        # Close resource managers
        await self.tileset_manager.close()
        await self.sprite_manager.close()
        
        # Clear paperdoll renderer cache
        self.paperdoll_renderer.clear_cache()
        
        print("Client shutdown complete")
        pygame.quit()


# =============================================================================
# ENTRY POINT
# =============================================================================

async def main():
    """Main entry point."""
    client = RPGClient()
    await client.run()


if __name__ == "__main__":
    asyncio.run(main())
