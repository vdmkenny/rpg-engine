"""
Main client orchestrator.

Coordinates all systems: rendering, input, network, and game state.
This replaces the monolithic rpg_client.py with a clean architecture.
"""

import asyncio
import sys
from pathlib import Path
from typing import Optional

# Add common module to path
common_path = Path(__file__).parent.parent / "common" / "src"
if str(common_path) not in sys.path:
    sys.path.insert(0, str(common_path))

try:
    import aiohttp
    import pygame
except ImportError:
    pass  # Will be imported when running

from client.src.config import get_config
from client.src.logging_config import setup_logging, get_logger
from client.src.core import get_state_machine, GameState, get_event_bus, EventType
from client.src.game.client_state import get_game_state
from client.src.network.connection import get_connection_manager
from client.src.network.handlers import register_all_handlers
from client.src.network.message_sender import get_message_sender
from client.src.input.input_manager import InputManager, InputAction
from client.src.rendering.renderer import Renderer

import sys
from pathlib import Path
common_path = Path(__file__).parent.parent / "common" / "src"
if str(common_path) not in sys.path:
    sys.path.insert(0, str(common_path))

from protocol import Direction

logger = get_logger(__name__)


class Client:
    """Main client orchestrator."""
    
    def __init__(self):
        self.config = get_config()
        self.state_machine = get_state_machine()
        self.event_bus = get_event_bus()
        self.game_state = get_game_state()
        self.connection = get_connection_manager()
        self.message_sender = get_message_sender()
        
        self._running = False
        self.renderer: Optional[Renderer] = None
        self.input_manager: Optional[InputManager] = None
        self.http_session: Optional[aiohttp.ClientSession] = None
        
        self._jwt_token: Optional[str] = None
        
        self._setup_event_listeners()
        self._setup_input_handlers()
    
    def _setup_event_listeners(self):
        """Setup internal event listeners."""
        self.event_bus.subscribe(EventType.CONNECTING, self._on_connecting)
        self.event_bus.subscribe(EventType.CONNECTED, self._on_connected)
        self.event_bus.subscribe(EventType.DISCONNECTED, self._on_disconnected)
        self.event_bus.subscribe(EventType.AUTHENTICATED, self._on_authenticated)
        self.event_bus.subscribe(EventType.AUTH_FAILED, self._on_auth_failed)
        self.event_bus.subscribe(EventType.CONNECTION_ERROR, self._on_connection_error)
    
    def _setup_input_handlers(self):
        """Setup input action handlers."""
        # Will be set up after input_manager is created
        pass
    
    async def run(self):
        """Run the main client loop."""
        self._running = True
        
        # Setup logging
        setup_logging()
        logger.info("RPG Client starting...")
        
        # Initialize systems
        self.http_session = aiohttp.ClientSession()
        self.renderer = Renderer()
        self.input_manager = InputManager()
        self._setup_input_actions()
        
        # Register network handlers
        register_all_handlers(self.game_state)
        
        # Start in server select state
        self.state_machine.transition_to(GameState.SERVER_SELECT)
        
        # Main loop
        clock = pygame.time.Clock()
        
        try:
            while self._running:
                delta_time = clock.tick(self.config.display.fps) / 1000.0
                
                # Process input
                if not self.input_manager.process_events():
                    break
                
                # Update game state
                self._update(delta_time)
                
                # Render
                if self.renderer:
                    self.renderer.update(delta_time)
                    self.renderer.render()
                
                # Small yield to prevent blocking
                await asyncio.sleep(0)
                
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        except Exception as e:
            logger.error(f"Error in main loop: {e}", exc_info=True)
        finally:
            await self.shutdown()
    
    def _setup_input_actions(self):
        """Setup input action handlers."""
        self.input_manager.register_action_handler(InputAction.MOVE_UP, self._on_move_up)
        self.input_manager.register_action_handler(InputAction.MOVE_DOWN, self._on_move_down)
        self.input_manager.register_action_handler(InputAction.MOVE_LEFT, self._on_move_left)
        self.input_manager.register_action_handler(InputAction.MOVE_RIGHT, self._on_move_right)
        self.input_manager.register_action_handler(InputAction.OPEN_INVENTORY, self._on_open_inventory)
        self.input_manager.register_action_handler(InputAction.OPEN_EQUIPMENT, self._on_open_equipment)
        self.input_manager.register_action_handler(InputAction.OPEN_STATS, self._on_open_stats)
        self.input_manager.register_action_handler(InputAction.TOGGLE_CHAT, self._on_toggle_chat)
        self.input_manager.register_action_handler(InputAction.HIDE_CHAT, self._on_hide_chat)
        self.input_manager.register_action_handler(InputAction.CLOSE_PANELS, self._on_close_panels)
    
    def _update(self, delta_time: float):
        """Update game state."""
        # Update current state
        current_state = self.state_machine.current_state
        
        # State-specific updates
        if current_state == GameState.PLAYING:
            # Clean up expired hit splats
            self.game_state.cleanup_hit_splats()
    
    # =========================================================================
    # Input Action Handlers
    # =========================================================================
    
    def _on_move_up(self):
        if self.state_machine.is_in_game:
            asyncio.create_task(self.message_sender.move(Direction.UP))
    
    def _on_move_down(self):
        if self.state_machine.is_in_game:
            asyncio.create_task(self.message_sender.move(Direction.DOWN))
    
    def _on_move_left(self):
        if self.state_machine.is_in_game:
            asyncio.create_task(self.message_sender.move(Direction.LEFT))
    
    def _on_move_right(self):
        if self.state_machine.is_in_game:
            asyncio.create_task(self.message_sender.move(Direction.RIGHT))
    
    def _on_open_inventory(self):
        if self.renderer:
            self.renderer.ui_renderer.toggle_panel("inventory")
    
    def _on_open_equipment(self):
        if self.renderer:
            self.renderer.ui_renderer.toggle_panel("equipment")
    
    def _on_open_stats(self):
        if self.renderer:
            self.renderer.ui_renderer.toggle_panel("stats")
    
    def _on_toggle_chat(self):
        if self.input_manager:
            self.input_manager.start_chat_input()
    
    def _on_hide_chat(self):
        if self.renderer:
            self.renderer.ui_renderer.toggle_panel("chat")
    
    def _on_close_panels(self):
        if self.renderer:
            self.renderer.ui_renderer.hide_all_panels()
    
    # =========================================================================
    # Event Handlers
    # =========================================================================
    
    def _on_connecting(self, event):
        """Handle connecting event."""
        logger.info("Connecting to server...")
    
    def _on_connected(self, event):
        """Handle connected event."""
        logger.info("Connected to server")
    
    def _on_disconnected(self, event):
        """Handle disconnected event."""
        logger.info("Disconnected from server")
        self.game_state.is_connected = False
        self.game_state.is_authenticated = False
        self.state_machine.transition_to(GameState.SERVER_SELECT)
    
    def _on_authenticated(self, event):
        """Handle authenticated event."""
        logger.info("Successfully authenticated")
        self.game_state.is_authenticated = True
        
        # Query initial data
        asyncio.create_task(self.message_sender.query_inventory())
        asyncio.create_task(self.message_sender.query_equipment())
        asyncio.create_task(self.message_sender.query_stats())
        
        # Request map chunks around current position
        x = self.game_state.position.get("x", 0)
        y = self.game_state.position.get("y", 0)
        asyncio.create_task(self.message_sender.query_map_chunks(x, y))
        
        # Transition to playing state
        self.state_machine.transition_to(GameState.PLAYING)
    
    def _on_auth_failed(self, event):
        """Handle authentication failure."""
        error = event.data.get("error", "Unknown error")
        logger.error(f"Authentication failed: {error}")
        self.state_machine.transition_to(GameState.LOGIN, {"error": error})
    
    def _on_connection_error(self, event):
        """Handle connection error."""
        error = event.data.get("error", "Unknown error")
        logger.error(f"Connection error: {error}")
    
    # =========================================================================
    # Public API
    # =========================================================================
    
    async def login(self, username: str, password: str) -> bool:
        """
        Login and get JWT token.
        
        Args:
            username: Player username
            password: Player password
            
        Returns:
            True if login successful
        """
        try:
            url = f"{self.config.server.base_url}/auth/login"
            payload = {"username": username, "password": password}
            
            async with self.http_session.post(url, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    self._jwt_token = data.get("access_token")
                    
                    if self._jwt_token:
                        # Store username in game state
                        self.game_state.username = username
                        
                        # Transition to connecting state
                        self.state_machine.transition_to(GameState.CONNECTING)
                        
                        # Connect to WebSocket
                        success = await self.connection.connect(self._jwt_token)
                        return success
                else:
                    error_text = await response.text()
                    logger.error(f"Login failed: {error_text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Login error: {e}")
            return False
        
        return False
    
    async def register(self, username: str, password: str) -> bool:
        """
        Register a new account.
        
        Args:
            username: Desired username
            password: Desired password
            
        Returns:
            True if registration successful
        """
        try:
            url = f"{self.config.server.base_url}/auth/register"
            payload = {"username": username, "password": password}
            
            async with self.http_session.post(url, json=payload) as response:
                if response.status == 201:
                    logger.info("Registration successful")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"Registration failed: {error_text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Registration error: {e}")
            return False
    
    async def logout(self):
        """Logout and disconnect."""
        await self.connection.disconnect()
        self._jwt_token = None
        self.game_state.clear()
        self.state_machine.transition_to(GameState.SERVER_SELECT)
    
    async def shutdown(self):
        """Shutdown the client gracefully."""
        logger.info("Shutting down client...")
        self._running = False
        
        # Disconnect from server
        await self.connection.disconnect()
        
        # Cleanup pygame
        if self.renderer:
            self.renderer.cleanup()
        
        # Close HTTP session
        if self.http_session:
            await self.http_session.close()
        
        logger.info("Client shutdown complete")


async def main():
    """Main entry point."""
    client = Client()
    await client.run()


if __name__ == "__main__":
    asyncio.run(main())
