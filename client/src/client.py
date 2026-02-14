"""
RPG Client v2.0 - Proper screen-based architecture.

Screen flow: Server Select -> Login/Register -> Game
"""

import asyncio
import time
from typing import Optional

import aiohttp
import pygame

from client.src.config import get_config
from client.src.logging_config import setup_logging, get_logger
from client.src.game.client_state import get_game_state, ClientGameState
from client.src.network.connection import get_connection_manager
from client.src.network.handlers import register_all_handlers
from client.src.network.message_sender import get_message_sender
from client.src.rendering.renderer import Renderer
from client.src.rendering.ui_panels import RARITY_COLOR_MAP
from client.src.ui.screens import ServerSelectScreen, LoginScreen, GameScreen
from client.src.ui.colors import Colors
from client.src.game_states import GameState
from client.src.core import get_event_bus, EventType, Event
from client.src.chat import get_command_registry

from protocol import Direction

logger = get_logger(__name__)


class Client:
    """Main RPG client with proper screen flow."""
    
    # Server list - configurable
    SERVERS = [
        {
            "name": "Local Server",
            "host": "localhost",
            "port": 8000,
            "description": "Development server",
        },
    ]
    
    def __init__(self):
        self.config = get_config()
        self.game_state = get_game_state()
        self.connection = get_connection_manager()
        self.message_sender = get_message_sender()
        
        # Pygame setup
        pygame.init()
        self.screen = pygame.display.set_mode((
            self.config.display.width,
            self.config.display.height
        ))
        pygame.display.set_caption(self.config.display.title)
        self.clock = pygame.time.Clock()
        
        # Network
        self.http_session: Optional[aiohttp.ClientSession] = None
        self.jwt_token: Optional[str] = None
        self.selected_server_index = 0
        
        # Movement tracking
        self.keys_pressed: set = set()
        self.last_move_time: float = 0.0
        self.move_cooldown: float = self.config.game.move_cooldown  # 0.15s
        
        # State
        self.state = GameState.SERVER_SELECT
        self._running = False
        
        # UI callbacks
        self._setup_ui_callbacks()
        
        # Screens
        self.server_select_screen: Optional[ServerSelectScreen] = None
        self.login_screen: Optional[LoginScreen] = None
        self.game_screen: Optional[GameScreen] = None
        self.renderer: Optional[Renderer] = None
        
        # Status checking
        self.server_status = {}
        self.last_status_check = 0
        
        # Cached fonts for performance
        self.debug_font = pygame.font.SysFont("monospace", 12)
        
        # Subscribe to GAME_STARTED event to handle reconnections
        self._setup_event_handlers()
    
    def _setup_event_handlers(self):
        """Subscribe to events for handling game state changes."""
        event_bus = get_event_bus()
        event_bus.subscribe(EventType.GAME_STARTED, self._on_game_started)
        event_bus.subscribe(EventType.CHAT_MESSAGE_RECEIVED, self._on_chat_message_received)
        event_bus.subscribe(EventType.ERROR_RECEIVED, self._on_error_received)
        logger.debug("Subscribed to GAME_STARTED, CHAT_MESSAGE_RECEIVED, and ERROR_RECEIVED events")
    
    async def _on_game_started(self, event: Event):
        """Handle game start - ensures renderer exists for reconnects."""
        logger.info(f"Game started event received for player {event.data.get('player_id')}")
        
        # If no renderer (reconnect after logout), recreate it
        if not self.renderer:
            logger.info("Recreating renderer after reconnect")
            self.renderer = Renderer(self.screen)
            self.game_screen = GameScreen(self.screen, self.renderer)
            # Reset callback setup flag since we have a new renderer instance
            self._ui_callbacks_setup = False
            self._connect_ui_callbacks()
            
            # Transition to PLAYING state if we're in LOGIN
            if self.state == GameState.LOGIN:
                self.state = GameState.PLAYING
                logger.info("Transitioned to PLAYING state after reconnect")

    def _on_chat_message_received(self, event: Event):
        """Handle incoming chat message - route to chat window."""
        chat_data = event.data
        sender = chat_data.get("sender", "Unknown")
        message = chat_data.get("message", "")
        channel = chat_data.get("channel", "local")

        # Skip messages from self (already added locally with "You" prefix)
        if sender == self.game_state.username:
            return

        # Add message to chat window (Fix D)
        if self.renderer and self.renderer.ui_renderer:
            chat_window = self.renderer.ui_renderer.chat_window
            chat_window.add_message(channel, sender, message)

    def _on_error_received(self, event: Event):
        """Handle error responses from server - display in local chat."""
        error_message = event.data.get("error", "Unknown error")
        if self.renderer and self.renderer.ui_renderer:
            chat_window = self.renderer.ui_renderer.chat_window
            # Pass empty username for system messages so they don't show "System: " prefix
            chat_window.add_message("local", "", error_message)

    async def run(self):
        """Main client loop."""
        self._running = True
        
        setup_logging()
        logger.info("RPG Client v2.0 starting...")
        
        # Initialize HTTP session
        self.http_session = aiohttp.ClientSession()
        
        # Initialize screens
        self.server_select_screen = ServerSelectScreen(self.screen, self.SERVERS)
        self.login_screen = LoginScreen(self.screen, is_register=False)
        
        # Fetch initial server status
        await self._refresh_server_status()
        
        try:
            while self._running:
                delta_time = self.clock.tick(self.config.display.fps) / 1000.0
                
                # Process events
                should_quit = False
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        should_quit = True
                        break
                    
                    # Track key state for continuous movement
                    if event.type == pygame.KEYDOWN:
                        self.keys_pressed.add(event.key)
                    elif event.type == pygame.KEYUP:
                        self.keys_pressed.discard(event.key)
                    
                    action = self._handle_event(event)
                    if action == "quit":
                        should_quit = True
                        break
                    elif action:
                        await self._process_action(action)
                
                if should_quit:
                    break
                
                # Update
                self._update(delta_time)
                
                # Render
                self._draw()
                
                pygame.display.flip()
                await asyncio.sleep(0)
                
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        except Exception as e:
            logger.error(f"Error in main loop: {e}", exc_info=True)
        finally:
            await self.shutdown()
    
    def _handle_event(self, event: pygame.event.Event) -> Optional[str]:
        """Route events to appropriate screen handler."""
        # For PLAYING state, capture chat focus BEFORE routing to UI (Fix 1: prevents ESC race condition)
        chat_focused = False
        if self.state == GameState.PLAYING and self.renderer and self.renderer.ui_renderer:
            chat_focused = self.renderer.ui_renderer.is_chat_input_active()

        # Route to screen handlers first (so UI gets priority over global shortcuts)
        if self.state == GameState.SERVER_SELECT and self.server_select_screen:
            return self.server_select_screen.handle_event(event)
        elif self.state in (GameState.LOGIN, GameState.REGISTER) and self.login_screen:
            return self.login_screen.handle_event(event)
        elif self.state == GameState.PLAYING and self.game_screen:
            action = self.game_screen.handle_event(event, self.game_state)
            if action:
                return action

        # Global shortcuts for panel toggling in PLAYING state (only if not consumed by UI)
        if self.state == GameState.PLAYING:
            if event.type == pygame.KEYDOWN:
                # ESCAPE: defocus chat if active
                if event.key == pygame.K_ESCAPE:
                    if chat_focused:
                        # Just defocus chat input, don't hide the window
                        self.renderer.ui_renderer.set_chat_input_active(False)
                        return None
                    # No panel hiding on Escape - modals are handled upstream in UIRenderer
                    return None

                # If chat is focused, don't process other shortcuts (let UI handle typing)
                if chat_focused:
                    return None

                # Process global shortcuts only when chat is NOT focused
                if event.key == pygame.K_i:
                    return "toggle_inventory"
                elif event.key == pygame.K_e:
                    return "toggle_equipment"
                elif event.key == pygame.K_s:
                    return "toggle_stats"
                elif event.key == pygame.K_c:
                    return "toggle_chat"
                elif event.key == pygame.K_m:
                    return "toggle_minimap"
                elif event.key == pygame.K_t:
                    return "start_chat"

            # Handle world mouse interactions
            if event.type == pygame.MOUSEBUTTONDOWN and self.renderer:
                # Get mouse position in display coordinates
                mouse_pos = pygame.mouse.get_pos()
                
                # Convert display coordinates to game surface coordinates (account for zoom)
                game_x, game_y = self.renderer.screen_to_game_coords(mouse_pos[0], mouse_pos[1])
                
                # Get world coordinates from game surface coordinates
                camera = self.renderer.camera
                world_x, world_y = camera.screen_to_world(game_x, game_y)
                tile_x = int(world_x // self.config.game.tile_size)
                tile_y = int(world_y // self.config.game.tile_size)

                # Check if click was on UI (don't handle world clicks if clicking UI)
                if self.renderer.ui_renderer:
                    ui_rects = [
                        self.renderer.ui_renderer.side_panel.rect,
                        self.renderer.ui_renderer.chat_window.rect,
                    ]
                    # Convert minimap center/radius to rect for hit testing (M7 fix)
                    if hasattr(self.renderer.ui_renderer.minimap, 'x'):
                        mm = self.renderer.ui_renderer.minimap
                        mm_rect = pygame.Rect(
                            mm.x - mm.radius,
                            mm.y - mm.radius,
                            mm.radius * 2,
                            mm.radius * 2
                        )
                        ui_rects.append(mm_rect)

                    # Check if click is on any UI element
                    click_on_ui = any(rect.collidepoint(mouse_pos) for rect in ui_rects if hasattr(rect, 'collidepoint'))
                    if click_on_ui:
                        pass  # Let UI handle it
                    else:
                        # Handle world click
                        if event.button == 1:  # Left click - attack or pickup
                            action = self._handle_world_left_click(tile_x, tile_y)
                            if action:
                                return action
                        elif event.button == 3:  # Right click - context menu
                            action = self._handle_world_right_click(tile_x, tile_y)
                            if action:
                                return action

        return None
    
    def _handle_world_left_click(self, tile_x: int, tile_y: int) -> Optional[str]:
        """Handle left click on the game world."""
        # Check for entities at this tile
        for entity_id, entity in self.game_state.entities.items():
            if entity.x == tile_x and entity.y == tile_y:
                # Attack the entity
                entity_type = entity.entity_type.value if hasattr(entity.entity_type, 'value') else str(entity.entity_type)
                asyncio.create_task(self.message_sender.attack(entity_type, entity_id))
                return None
        
        # Check for other players at this tile
        for player_id, player in self.game_state.other_players.items():
            pos = player.get("position", {})
            if pos.get("x") == tile_x and pos.get("y") == tile_y:
                # Attack the player
                asyncio.create_task(self.message_sender.attack("player", player_id))
                return None
        
        # Check for ground items at this tile
        for item_id, item in self.game_state.ground_items.items():
            if item.get("x") == tile_x and item.get("y") == tile_y:
                # Pick up the item
                asyncio.create_task(self.message_sender.item_pickup(item_id))
                return None
        
        return None
    
    def _handle_world_right_click(self, tile_x: int, tile_y: int) -> Optional[str]:
        """Handle right click on the game world - show context menu."""
        from client.src.rendering.ui_panels import ContextMenuItem
        
        menu_items = []
        menu_x, menu_y = pygame.mouse.get_pos()
        
        # Check for entities at this tile
        for entity_id, entity in self.game_state.entities.items():
            if entity.x == tile_x and entity.y == tile_y:
                entity_name = entity.name
                entity_type = entity.entity_type.value if hasattr(entity.entity_type, 'value') else str(entity.entity_type)
                menu_items.append(ContextMenuItem(
                    f"Attack {entity_name}",
                    "attack_entity",
                    (255, 100, 100),  # Red
                    (entity_type, entity_id)
                ))
                menu_items.append(ContextMenuItem(
                    f"Examine {entity_name}",
                    "examine_entity",
                    (100, 200, 255),  # Cyan
                    entity
                ))
        
        # Check for other players at this tile
        for player_id, player in self.game_state.other_players.items():
            pos = player.get("position", {})
            if pos.get("x") == tile_x and pos.get("y") == tile_y:
                username = player.get("username", "Unknown")
                menu_items.append(ContextMenuItem(
                    f"Attack {username}",
                    "attack_player",
                    (255, 100, 100),  # Red
                    ("player", player_id)
                ))
                menu_items.append(ContextMenuItem(
                    f"Examine {username}",
                    "examine_player",
                    (100, 200, 255),  # Cyan
                    player
                ))
        
        # Check for ground items at this tile
        for item_id, item in self.game_state.ground_items.items():
            if item.get("x") == tile_x and item.get("y") == tile_y:
                item_name = item.get("display_name", item.get("item_name", "Unknown Item"))
                rarity = item.get("rarity", "common")
                item_color = RARITY_COLOR_MAP.get(rarity, Colors.RARITY_COMMON)
                menu_items.append(ContextMenuItem(
                    f"Take {item_name}",
                    "pickup",
                    item_color,
                    item_id
                ))
                menu_items.append(ContextMenuItem(
                    f"Examine {item_name}",
                    "examine_item",
                    (100, 200, 255),  # Cyan
                    item
                ))
        
        # Show context menu if we have items
        if menu_items and self.renderer:
            def on_menu_select(item):
                if item.action.startswith("attack"):
                    target_type, target_id = item.data
                    asyncio.create_task(self.message_sender.attack(target_type, target_id))
                elif item.action == "pickup":
                    asyncio.create_task(self.message_sender.item_pickup(item.data))
            
            self.renderer.ui_renderer.context_menu.show(
                menu_x, menu_y, menu_items, on_menu_select
            )
        
        return None
    
    async def _process_action(self, action: str):
        """Process actions from screen handlers."""
        if action.startswith("select_server:"):
            idx = int(action.split(":")[1])
            self.selected_server_index = idx
            await self._select_server()
        
        elif action == "refresh_status":
            await self._refresh_server_status()
            
        elif action == "submit":
            if self.state == GameState.LOGIN:
                await self._attempt_login()
            elif self.state == GameState.REGISTER:
                await self._attempt_register()
                
        elif action == "switch_mode":
            if self.state == GameState.LOGIN:
                self.state = GameState.REGISTER
                self.login_screen.is_register = True
            else:
                self.state = GameState.LOGIN
                self.login_screen.is_register = False
            self.login_screen.status_message = ""
        
        elif action == "toggle_inventory":
            if self.renderer:
                self.renderer.ui_renderer.toggle_panel("inventory")
        
        elif action == "toggle_equipment":
            if self.renderer:
                self.renderer.ui_renderer.toggle_panel("equipment")
        
        elif action == "toggle_stats":
            if self.renderer:
                self.renderer.ui_renderer.toggle_panel("stats")
        
        elif action == "toggle_chat":
            if self.renderer:
                self.renderer.ui_renderer.toggle_panel("chat")
        
        elif action == "toggle_minimap":
            if self.renderer:
                self.renderer.ui_renderer.toggle_panel("minimap")
        
        elif action == "start_chat":
            if self.renderer:
                self.renderer.ui_renderer.set_chat_input_active(True)
        
        elif action == "chat_send":
            # Chat message was sent from UI (Fix C: read pending_message, not input_text)
            if self.renderer and self.renderer.ui_renderer.is_chat_input_active():
                # Get the message from chat window and send it
                chat_window = self.renderer.ui_renderer.chat_window
                if chat_window.pending_message and chat_window.pending_message.strip():
                    message = chat_window.pending_message
                    
                    # Check if this is a slash command
                    if message.startswith("/"):
                        registry = get_command_registry()
                        if registry.is_command(message):
                            # Known command - handle it locally
                            registry.try_handle(message)
                        else:
                            # Unknown command - show error in chat, don't send to server
                            chat_window.add_message(chat_window.active_channel, "System", f"Unknown command: {message}")
                        chat_window.pending_message = None
                        return
                    
                    # Not a command - send as regular chat
                    asyncio.create_task(self.message_sender.chat_send(message))
                    chat_window.pending_message = None  # Clear after sending

        elif action == "logout":
            # Logout requested from UI
            await self._handle_logout()

    def _setup_ui_callbacks(self):
        """Setup UI interaction callbacks."""
        # These will be connected once the renderer is initialized
        self._ui_callbacks_setup = False
    
    def _safe_create_task(self, coro):
        """Create an async task with error logging callback."""
        task = asyncio.create_task(coro)
        task.add_done_callback(self._on_task_done)
        return task
    
    def _on_task_done(self, task):
        """Log any exceptions from fire-and-forget tasks."""
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            logger.error(f"Async task failed: {exc}", exc_info=exc)
    
    def _connect_ui_callbacks(self):
        """Connect UI callbacks to message sender."""
        if self._ui_callbacks_setup or not self.renderer:
            return
        
        ui_renderer = self.renderer.ui_renderer
        
        # Inventory actions
        def on_inventory_action(action: str, slot: int):
            if action == "equip":
                self._safe_create_task(self.message_sender.item_equip(slot))
            elif action == "drop":
                self._safe_create_task(self.message_sender.item_drop(slot))
            elif action == "use":
                # Use item - could be implemented based on item type
                pass
            elif action == "examine":
                item = self.game_state.inventory.get(slot)
                if item and self.renderer and self.renderer.ui_renderer:
                    desc = item.description or "Nothing interesting."
                    self.renderer.ui_renderer.chat_window.add_message("local", "", f"{item.name} {desc}")
        
        # Equipment actions  
        def on_equipment_action(action: str, slot: str):
            if action == "unequip":
                self._safe_create_task(self.message_sender.item_unequip(slot))
            elif action == "examine":
                item = self.game_state.equipment.get(slot)
                if item and self.renderer and self.renderer.ui_renderer:
                    desc = item.description or "Nothing interesting."
                    self.renderer.ui_renderer.chat_window.add_message("local", "", f"{item.name} {desc}")
        
        # World actions
        def on_world_action(action: str, data: any):
            if action == "attack":
                target_type, target_id = data
                self._safe_create_task(self.message_sender.attack(target_type, target_id))
            elif action == "pickup":
                ground_item_id = data
                self._safe_create_task(self.message_sender.item_pickup(ground_item_id))
        
        logger.debug(f"_connect_ui_callbacks: Setting callbacks on ui_renderer")
        ui_renderer.on_inventory_action = on_inventory_action
        ui_renderer.on_equipment_action = on_equipment_action
        ui_renderer.on_world_action = on_world_action

        # Setup logout callback
        def on_logout():
            asyncio.create_task(self._handle_logout())

        ui_renderer.set_logout_callback(on_logout)

        # Setup inventory sort callback
        def on_inventory_sort(criteria: str):
            asyncio.create_task(self.message_sender.inventory_sort(criteria))

        ui_renderer.set_inventory_sort_callback(on_inventory_sort)

        self._ui_callbacks_setup = True
    
    def _init_customisation_panel(self) -> None:
        """Initialize the character customisation panel and register commands."""
        from client.src.rendering.customisation_panel import CustomisationPanel
        from client.src.chat import get_command_registry
        
        # Get paperdoll renderer from entity_renderer (it's already instantiated there)
        paperdoll_renderer = self.renderer.entity_renderer.paperdoll_renderer
        
        # Create the customisation panel
        customisation_panel = CustomisationPanel(
            screen_width=self.screen.get_width(),
            screen_height=self.screen.get_height(),
            paperdoll_renderer=paperdoll_renderer,
            on_apply=self._on_customisation_apply,
            on_cancel=self._on_customisation_cancel,
        )
        
        # Attach to UI renderer
        self.renderer.ui_renderer.customisation_panel = customisation_panel
        
        # Register slash commands
        registry = get_command_registry()
        
        # /customize - Open character customisation
        def handle_customize(command_text: str) -> None:
            asyncio.create_task(self._open_customisation_panel())
            return None
        
        registry.register(
            "customize",
            handle_customize,
            "Open character customisation panel"
        )
        
        # /help - Show help modal
        def handle_help(command_text: str) -> None:
            if self.renderer and self.renderer.ui_renderer:
                self.renderer.ui_renderer.show_help_modal()
            return None
        
        registry.register(
            "help",
            handle_help,
            "Show help modal with controls and commands"
        )
        
        # /logout - Log out of the game
        def handle_logout(command_text: str) -> None:
            asyncio.create_task(self._handle_logout())
            return None
        
        registry.register(
            "logout",
            handle_logout,
            "Log out and return to login screen"
        )
        
        # /give <player> <item> [amount] - Give item to a player (admin only)
        def handle_give(command_text: str) -> None:
            parts = command_text[1:].split(maxsplit=3)  # /give player item [amount]
            if len(parts) < 3:
                return "Usage: /give <player> <item> [amount]"
            
            target_player = parts[1]
            item_name = parts[2].lower()
            quantity = 1
            
            if len(parts) > 3:
                try:
                    quantity = int(parts[3])
                except ValueError:
                    return "Invalid quantity - must be a number"
            
            if quantity < 1:
                return "Quantity must be at least 1"
            
            asyncio.create_task(
                self.message_sender.admin_give(target_player, item_name, quantity)
            )
            return f"Sending give command for {quantity}x {item_name} to {target_player}..."
        
        registry.register(
            "give",
            handle_give,
            "Give item to a player (admin only)"
        )
        
        # /giveme <item> [amount] - Give item to yourself (admin only)
        def handle_giveme(command_text: str) -> None:
            parts = command_text[1:].split(maxsplit=2)  # /giveme item [amount]
            if len(parts) < 2:
                return "Usage: /giveme <item> [amount]"
            
            item_name = parts[1].lower()
            quantity = 1
            
            if len(parts) > 2:
                try:
                    quantity = int(parts[2])
                except ValueError:
                    return "Invalid quantity - must be a number"
            
            if quantity < 1:
                return "Quantity must be at least 1"
            
            # Use the current player's username
            if not hasattr(self.game_state, 'username') or not self.game_state.username:
                return "Error: Could not determine current player"
            
            asyncio.create_task(
                self.message_sender.admin_give(self.game_state.username, item_name, quantity)
            )
            return f"Sending give command for {quantity}x {item_name} to yourself..."
        
        registry.register(
            "giveme",
            handle_giveme,
            "Give item to yourself (admin only)"
        )
        
        logger.info("Customisation panel initialized and commands registered")
    
    async def _open_customisation_panel(self) -> None:
        """Open the customisation panel by fetching options from server."""
        if not self.renderer or not self.renderer.ui_renderer.customisation_panel:
            logger.error("Customisation panel not initialized")
            return
        
        panel = self.renderer.ui_renderer.customisation_panel
        
        # Fetch appearance options from server
        try:
            url = f"{self.config.server.base_url}/api/appearance/options"
            headers = {"Authorization": f"Bearer {self.jwt_token}"}
            
            async with self.http_session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    panel.set_categories(data.get("categories", []))
                else:
                    logger.error(f"Failed to fetch appearance options: HTTP {resp.status}")
                    # Still open panel with empty categories - will show loading state
                    panel.set_categories([])
        except Exception as e:
            logger.error(f"Error fetching appearance options: {e}")
            panel.set_categories([])
        
        # Set current appearance
        appearance = self.game_state.appearance or {}
        panel.set_current_appearance(appearance)
        
        # Show the panel
        panel.show()
    
    def _on_customisation_apply(self, changes: dict) -> None:
        """Handle customisation apply - send changes to server."""
        if changes:
            asyncio.create_task(self.message_sender.update_appearance(changes))
            logger.info(f"Applying appearance changes: {list(changes.keys())}")
    
    def _on_customisation_cancel(self) -> None:
        """Handle customisation cancel - discard changes."""
        logger.debug("Customisation cancelled - changes discarded")
    
    async def _refresh_server_status(self):
        """Fetch server status for all servers."""
        for i, server in enumerate(self.SERVERS):
            try:
                url = f"http://{server['host']}:{server['port']}/status"
                async with self.http_session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                    if resp.status == 200:
                        self.server_status[i] = await resp.json()
                    else:
                        self.server_status[i] = {"status": "error", "error": f"HTTP {resp.status}"}
            except Exception as e:
                self.server_status[i] = {"status": "error", "error": str(e)}
        
        # Update screen with status
        if self.server_select_screen:
            self.server_select_screen.server_status = self.server_status
    
    async def _select_server(self):
        """Select a server and proceed to login."""
        server = self.SERVERS[self.selected_server_index]
        logger.info(f"Selected server: {server['name']}")
        
        # Update config with selected server
        self.config.server.host = server['host']
        self.config.server.port = server['port']
        
        self.state = GameState.LOGIN
        self.login_screen.status_message = ""
    
    async def _attempt_login(self):
        """Attempt login with credentials."""
        username, password, _ = self.login_screen.get_credentials()
        
        if not username or not password:
            self.login_screen.set_status("Please enter username and password", Colors.TEXT_RED)
            return
        
        self.login_screen.set_status("Logging in...", Colors.TEXT_WHITE)
        
        try:
            url = f"{self.config.server.base_url}/auth/login"
            async with self.http_session.post(url, data={"username": username, "password": password}) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    self.login_screen.set_status(f"Login failed: {error}", Colors.TEXT_RED)
                    return
                
                data = await resp.json()
                self.jwt_token = data.get("access_token")
            
            if not self.jwt_token:
                self.login_screen.set_status("No access token received", Colors.TEXT_RED)
                return
            
            # IMPORTANT: Register handlers BEFORE connecting so welcome event can be processed
            register_all_handlers(self.game_state)
            
            # IMPORTANT: Set auth token for tileset manager BEFORE connecting
            from client.src.tileset_manager import get_tileset_manager
            tileset_manager = get_tileset_manager()
            tileset_manager.set_auth_token(self.jwt_token)

            # Set auth token for sprite manager for paperdoll sprites
            from client.src.rendering.sprite_manager import get_sprite_manager
            sprite_manager = get_sprite_manager()
            sprite_manager.set_auth_token(self.jwt_token)
            
            # Initialize icon manager for inventory and ground item icons
            from client.src.rendering.icon_manager import IconManager, set_icon_manager
            icon_manager = IconManager(self.config.server.base_url, self.jwt_token)
            set_icon_manager(icon_manager)
            
            # Connect WebSocket
            self.login_screen.set_status("Connecting...", Colors.TEXT_WHITE)
            success = await self.connection.connect(self.jwt_token)
            
            if success:
                self.game_state.username = username
                self.game_state.is_authenticated = True
                
                # Initialize game screen
                self.renderer = Renderer(self.screen)
                self.game_screen = GameScreen(self.screen, self.renderer)
                # Reset callback setup flag since we have a new renderer instance
                self._ui_callbacks_setup = False

                # Set username in chat window for prefix display (Fix B)
                self.renderer.ui_renderer.chat_window.username = username
                
                # Initialize customisation panel
                self._init_customisation_panel()

                # Connect UI callbacks for interactions
                self._connect_ui_callbacks()
                
                # Request initial data from server
                self.login_screen.set_status("Loading game data...", Colors.TEXT_WHITE)
                await self.message_sender.query_inventory()
                await self.message_sender.query_equipment()
                await self.message_sender.query_stats()
                
                # Request map chunks around current position
                x = self.game_state.position.get("x", 0)
                y = self.game_state.position.get("y", 0)
                await self.message_sender.query_map_chunks(x, y)
                
                self.state = GameState.PLAYING
                logger.info("Login successful, entering game")
                
                # Auto-open customisation panel for first-time players
                if not self.game_state.appearance:
                    asyncio.create_task(self._open_customisation_panel())
                    logger.info("Auto-opening customisation panel for first-time player")
            else:
                self.login_screen.set_status("WebSocket connection failed", Colors.TEXT_RED)
                
        except Exception as e:
            logger.error(f"Login error: {e}")
            self.login_screen.set_status(f"Connection error: {e}", Colors.TEXT_RED)
    
    async def _attempt_register(self):
        """Attempt registration."""
        username, password, email = self.login_screen.get_credentials()
        
        if not username or not password:
            self.login_screen.set_status("Please fill all fields", Colors.TEXT_RED)
            return
        
        self.login_screen.set_status("Registering...", Colors.TEXT_WHITE)
        
        try:
            url = f"{self.config.server.base_url}/auth/register"
            payload = {"username": username, "password": password, "email": email or ""}
            
            async with self.http_session.post(url, json=payload) as resp:
                if resp.status == 201:
                    self.login_screen.set_status("Registration successful! Please login.", Colors.TEXT_GREEN)
                    self.state = GameState.LOGIN
                    self.login_screen.is_register = False
                else:
                    error = await resp.text()
                    self.login_screen.set_status(f"Registration failed: {error}", Colors.TEXT_RED)
                    
        except Exception as e:
            logger.error(f"Registration error: {e}")
            self.login_screen.set_status(f"Connection error: {e}", Colors.TEXT_RED)
    
    def _update(self, delta_time: float):
        """Update game state."""
        if self.state == GameState.PLAYING and self.game_state.is_authenticated:
            # Process continuous movement
            self._process_movement()
            
            # Clean up expired effects
            self.game_state.cleanup_hit_splats()
            
            # Update movement interpolation
            if self.game_state.is_moving:
                self.game_state.move_progress += delta_time / self.config.game.move_duration
                if self.game_state.move_progress >= 1.0:
                    self.game_state.move_progress = 1.0
                    self.game_state.is_moving = False
                    # Snap position to target when animation completes
                    self.game_state.position["x"] = self.game_state.move_target_x
                    self.game_state.position["y"] = self.game_state.move_target_y
            
            # Update camera
            if self.renderer:
                self.renderer.update(delta_time)
            
            # Update customisation panel animation
            if (self.renderer and 
                self.renderer.ui_renderer.customisation_panel and 
                self.renderer.ui_renderer.customisation_panel.is_visible()):
                self.renderer.ui_renderer.customisation_panel.update(delta_time)
    
    def _process_movement(self):
        """Process held keys and send movement commands."""
        # Skip movement if chat input is focused (Fix E)
        if self.renderer and self.renderer.ui_renderer.is_chat_input_active():
            return

        current_time = time.time()
        if current_time - self.last_move_time < self.move_cooldown:
            return

        # Determine direction from held keys (priority: UP > DOWN > LEFT > RIGHT)
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
            # Update facing direction immediately for responsive rendering
            self.game_state.facing_direction = direction.value
            # Schedule async move command
            asyncio.create_task(self.message_sender.move(direction))
            self.last_move_time = current_time
    
    def _draw(self):
        """Render current screen."""
        if self.state == GameState.SERVER_SELECT:
            self.server_select_screen.draw()
        elif self.state in (GameState.LOGIN, GameState.REGISTER):
            self.login_screen.draw()
        elif self.state == GameState.PLAYING:
            if self.game_screen and self.renderer:
                self.game_screen.draw(self.game_state)
        
        # Debug: Show current state
        state_text = f"State: {self.state.value}"
        text_surface = self.debug_font.render(state_text, True, (255, 255, 0))
        self.screen.blit(text_surface, (10, 10))

    async def _handle_logout(self):
        """Handle logout - disconnect and return to login screen."""
        logger.info("Logging out...")

        # Disconnect WebSocket
        await self.connection.disconnect()

        # Clean up game state
        from .game.client_state import reset_game_state
        reset_game_state()
        self.game_state = get_game_state()
        
        # Reset all singletons for clean logout state (M8 fix)
        from .tileset_manager import get_tileset_manager
        from .rendering.sprite_manager import get_sprite_manager
        from .core import get_event_bus
        from .network.connection import get_connection_manager
        
        # Close and reset tileset manager session
        tileset_mgr = get_tileset_manager()
        if tileset_mgr:
            await tileset_mgr.close()
        
        # Clear other singletons
        get_sprite_manager().clear_memory_cache()
        # Note: EventBus handlers are not cleared - they persist across sessions
        
        # Clean up renderer resources (but don't quit pygame - we need display for login)
        if self.renderer:
            # Just clear references, don't call cleanup() which quits pygame
            self.renderer = None
            self.game_screen = None

        # Reset auth
        self.jwt_token = None
        self._ui_callbacks_setup = False

        # Return to login screen
        self.state = GameState.LOGIN
        if self.login_screen:
            self.login_screen.set_status("Logged out successfully", Colors.TEXT_GREEN)
            self.login_screen.username = ""
            self.login_screen.password = ""
            self.login_screen.email = ""
            self.login_screen.active_field = "username"

        logger.info("Logout complete")

    async def shutdown(self):
        """Clean shutdown."""
        logger.info("Shutting down client...")
        self._running = False
        
        await self.connection.disconnect()
        
        if self.renderer:
            self.renderer.cleanup()
        
        if self.http_session:
            await self.http_session.close()
        
        pygame.quit()
        logger.info("Client shutdown complete")


async def main():
    """Entry point."""
    client = Client()
    await client.run()


if __name__ == "__main__":
    asyncio.run(main())
