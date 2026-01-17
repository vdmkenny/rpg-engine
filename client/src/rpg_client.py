"""
Refactored RPG Client - Main client class using separated components.
"""

import pygame
import asyncio
import websockets
import msgpack
import aiohttp
import sys
import json
import os
import time
from typing import Optional, Dict, Any, List

# Import common protocol
workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.append(workspace_root)
from common.src.protocol import MessageType, GameMessage

# Import our separated components
from game_states import GameState
from entities import Player, FloatingMessage
from chunk_manager import ChunkManager
from ui_components import InputField, Button, ChatWindow
from tileset_manager import TilesetManager

# Screen Constants
WINDOW_WIDTH = 1024
WINDOW_HEIGHT = 768
FPS = 60

# Colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
GRAY = (128, 128, 128)
BROWN = (139, 69, 19)

# Game Constants
TILE_SIZE = 32
MILLISECONDS_TO_SECONDS = 1000.0
MOVEMENT_ANIMATION_DURATION = 0.2  # seconds
CLIENT_MOVE_COOLDOWN = 0.2  # seconds
ANIMATION_START = -1000.0  # Far in the past so first move is allowed
ANIMATION_COMPLETE = 1.0
WEBSOCKET_TIMEOUT = 0.1  # seconds
CHUNK_REQUEST_DISTANCE = 8  # tiles


class RPGClient:
    """
    Main RPG client application using Pygame.
    """

    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("RPG Client")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 36)
        self.small_font = pygame.font.Font(None, 24)

        # Game state
        self.state = GameState.LOGIN
        self.player = Player()
        self.other_players = {}  # Track other players by username
        self.camera_x = 0
        self.camera_y = 0
        self.target_camera_x = 0
        self.target_camera_y = 0
        self.chunk_manager = ChunkManager()
        
        # Tileset management
        self.tileset_manager = TilesetManager()
        self.current_map_id = None

        # Network
        self.websocket = None
        self.jwt_token = None

        # Movement and timing
        self.keys_pressed = set()  # Track currently held keys
        self.last_move_time = ANIMATION_START  # Track timing for movement rate limiting
        self.move_cooldown = CLIENT_MOVE_COOLDOWN  # Minimum time between moves (configurable)

        # UI elements
        self.create_ui_elements()

        # Status
        self.status_message = ""
        self.status_color = BLACK

        # Chat system
        chat_x = 10
        chat_y = WINDOW_HEIGHT - 250
        chat_width = 400
        chat_height = 200
        self.chat_window = ChatWindow(chat_x, chat_y, chat_width, chat_height, self.small_font, self)

    def create_ui_elements(self):
        """Create UI elements for forms."""
        center_x = WINDOW_WIDTH // 2

        # Login form
        self.username_field = InputField(
            center_x - 150, 300, 300, 40, self.font, "Username"
        )
        self.password_field = InputField(
            center_x - 150, 360, 300, 40, self.font, "Password", password=True
        )
        self.email_field = InputField(center_x - 150, 420, 300, 40, self.font, "Email")

        self.login_button = Button(center_x - 80, 480, 160, 40, "Login", self.font)
        self.register_button = Button(
            center_x - 80, 530, 160, 40, "Register", self.font
        )
        self.switch_button = Button(
            center_x - 80, 580, 160, 40, "Switch to Register", self.font
        )

    def set_status(self, message, color=BLACK):
        """Set status message."""
        self.status_message = message
        self.status_color = color

    async def send_message(self, message):
        """Send a message via WebSocket."""
        if not self.websocket:
            return
            
        packed_data = msgpack.packb(message.model_dump())
        if packed_data is not None:
            await self.websocket.send(packed_data)

    async def send_chat_message(self, channel, message):
        """Send a chat message through WebSocket."""
        if not self.websocket:
            print("Cannot send message - not connected to server")
            return

        try:
            chat_message = GameMessage(
                type=MessageType.SEND_CHAT_MESSAGE,
                payload={
                    "channel": channel.lower(),
                    "message": message
                }
            )

            await self.send_message(chat_message)
        except Exception as e:
            print(f"Error sending chat message: {e}")

    async def process_pending_chat(self):
        """Process any pending chat messages from the chat window."""
        if self.chat_window.pending_message:
            channel, message = self.chat_window.pending_message
            self.chat_window.pending_message = None
            await self.send_chat_message(channel, message)

    async def attempt_login(self):
        """Attempt to login with entered credentials."""
        username = self.username_field.text
        password = self.password_field.text

        if not username or not password:
            self.set_status("Please enter username and password", RED)
            return

        self.set_status("Logging in...", WHITE)

        try:
            async with aiohttp.ClientSession() as session:
                login_data = {"username": username, "password": password}

                async with session.post(
                    "http://localhost:8000/auth/login", data=login_data
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        self.set_status(f"Login failed: {error_text}", RED)
                        return

                    login_response = await resp.json()
                    self.jwt_token = login_response.get("access_token")

                    if not self.jwt_token:
                        self.set_status("No access token received", RED)
                        return
                    
                    # Set up tileset manager with authentication
                    self.tileset_manager.set_auth_token(self.jwt_token)

            # Connect WebSocket
            try:
                self.websocket = await websockets.connect(
                    "ws://localhost:8000/ws", 
                    additional_headers={"Authorization": f"Bearer {self.jwt_token}"}
                )

                # Send authentication message
                auth_message = GameMessage(
                    type=MessageType.AUTHENTICATE,
                    payload={"token": self.jwt_token}
                )

                await self.send_message(auth_message)

                self.player.username = username
                self.state = GameState.PLAYING
                self.set_status("Connected!", GREEN)

            except Exception as e:
                self.set_status(f"WebSocket connection failed: {e}", RED)

        except Exception as e:
            self.set_status(f"Connection error: {e}", RED)

    async def attempt_register(self):
        """Attempt to register with entered credentials."""
        username = self.username_field.text
        password = self.password_field.text
        email = self.email_field.text

        if not username or not password or not email:
            self.set_status("Please fill all fields", RED)
            return

        self.set_status("Registering...", WHITE)

        try:
            async with aiohttp.ClientSession() as session:
                register_data = {
                    "username": username,
                    "password": password,
                    "email": email,
                }

                async with session.post(
                    "http://localhost:8000/auth/register", json=register_data
                ) as resp:
                    if resp.status == 201:  # HTTP 201 Created
                        self.set_status(
                            "Registration successful! You can now login.", GREEN
                        )
                        self.state = GameState.LOGIN
                        self.switch_button.text = "Switch to Register"
                    else:
                        error_text = await resp.text()
                        self.set_status(f"Registration failed: {error_text}", RED)

        except Exception as e:
            self.set_status(f"Connection error: {e}", RED)

    def draw_login_form(self):
        """Draw login/register form."""
        self.screen.fill(BLACK)

        # Draw title
        title = "Login" if self.state == GameState.LOGIN else "Register"
        title_surface = self.font.render(title, True, WHITE)
        title_rect = title_surface.get_rect(center=(WINDOW_WIDTH // 2, 200))
        self.screen.blit(title_surface, title_rect)

        # Draw fields
        if self.state == GameState.LOGIN:
            fields = [self.username_field, self.password_field]
            buttons = [self.login_button, self.switch_button]
        else:
            fields = [self.username_field, self.password_field, self.email_field]
            buttons = [self.register_button, self.switch_button]

        for field in fields:
            field.draw(self.screen)

        for button in buttons:
            button.draw(self.screen)

        # Draw status message
        if self.status_message:
            status_surface = self.font.render(self.status_message, True, self.status_color)
            status_rect = status_surface.get_rect(center=(WINDOW_WIDTH // 2, 650))
            self.screen.blit(status_surface, status_rect)

    def draw_game(self):
        """Draw the game view."""
        # Clear screen
        self.screen.fill(BLACK)

        # Draw chunks
        for chunk_key, chunk_data in self.chunk_manager.chunks.items():
            chunk_x, chunk_y = chunk_key
            self.draw_chunk(chunk_x, chunk_y, chunk_data)

        # Draw players
        self.draw_player(self.player.username, self.player)
        for player_id, player in self.other_players.items():
            self.draw_player(player_id, player)

        # Draw floating messages
        self.draw_floating_messages()

        # Draw UI
        fps = int(self.clock.get_fps())
        fps_text = self.small_font.render(f"FPS: {fps}", True, WHITE)
        self.screen.blit(fps_text, (10, 10))

        # Draw chat window
        self.chat_window.draw(self.screen)

    def draw_chunk(self, chunk_x, chunk_y, chunk_data):
        """Draw a single chunk."""
        # Calculate chunk position in world coordinates
        chunk_size = 16  # tiles per chunk
        chunk_world_x = chunk_x * chunk_size * TILE_SIZE
        chunk_world_y = chunk_y * chunk_size * TILE_SIZE

        # Convert to screen coordinates
        chunk_screen_x, chunk_screen_y = self.world_to_screen(chunk_world_x, chunk_world_y)

        # Skip if chunk is not visible
        if (chunk_screen_x > WINDOW_WIDTH or 
            chunk_screen_y > WINDOW_HEIGHT or
            chunk_screen_x + chunk_size * TILE_SIZE < 0 or
            chunk_screen_y + chunk_size * TILE_SIZE < 0):
            return

        # Draw tiles in the chunk
        tiles = chunk_data.get("tiles", [])
        
        if not tiles:
            return
        
        # Handle both flat array and 2D array formats
        if tiles and isinstance(tiles[0], list):
            # 2D array format
            for tile_y in range(min(chunk_size, len(tiles))):
                for tile_x in range(min(chunk_size, len(tiles[tile_y]))):
                    tile_type = tiles[tile_y][tile_x]
                    self.draw_tile(
                        chunk_screen_x + tile_x * TILE_SIZE,
                        chunk_screen_y + tile_y * TILE_SIZE,
                        tile_type
                    )
        else:
            # Flat array format
            for tile_y in range(chunk_size):
                for tile_x in range(chunk_size):
                    tile_index = tile_y * chunk_size + tile_x
                    if tile_index < len(tiles):
                        tile_type = tiles[tile_index]
                        self.draw_tile(
                            chunk_screen_x + tile_x * TILE_SIZE,
                            chunk_screen_y + tile_y * TILE_SIZE,
                            tile_type
                        )

    def draw_tile(self, screen_x, screen_y, tile_data):
        """Draw a single tile using sprites when available, otherwise colors."""
        # Handle new tile format with layers and properties
        if isinstance(tile_data, dict):
            properties = tile_data.get('properties', {})
            collision_layers = properties.get('collision_layers', {})
            
            # Check if it's out of bounds
            if properties.get('out_of_bounds', False):
                color = (64, 64, 64)  # Dark gray for out of bounds
                pygame.draw.rect(
                    self.screen,
                    color,
                    (int(screen_x), int(screen_y), TILE_SIZE, TILE_SIZE)
                )
                return
            
            # Handle multi-layer tiles
            layers = tile_data.get('layers', [])
            if layers:
                # Draw each layer in order (bottom to top)
                sprites_rendered = 0
                for layer_info in layers:
                    gid = layer_info.get('gid', 0)
                    if gid > 0 and self.current_map_id:
                        # Enable sprite rendering with correct tileset mapping
                        sprite = self.tileset_manager.get_tile_sprite(gid, self.current_map_id)
                        if sprite:
                            self.screen.blit(sprite, (int(screen_x), int(screen_y)))
                            sprites_rendered += 1
                        # Continue to next layer even if this one fails - don't break!
                        # Each layer should be independent
                            
                # Add collision overlay if needed
                if collision_layers:
                    self._draw_collision_overlay(screen_x, screen_y, collision_layers)
                return
            
            # Handle single-layer tiles (backward compatibility)
            tile_type = tile_data.get('gid', 0)
            if tile_type > 0 and self.current_map_id:
                sprite = self.tileset_manager.get_tile_sprite(tile_type, self.current_map_id)
                if sprite:
                    self.screen.blit(sprite, (int(screen_x), int(screen_y)))
                    if collision_layers:
                        self._draw_collision_overlay(screen_x, screen_y, collision_layers)
                    return
                else:
                    # Fallback to colored rectangle
                    self._draw_fallback_tile(screen_x, screen_y, tile_type, collision_layers)
                    return
        else:
            # Handle legacy integer tile types
            tile_type = tile_data
            self._draw_fallback_tile(screen_x, screen_y, tile_type, {})

    def _draw_fallback_tile(self, screen_x, screen_y, tile_type, collision_layers):
        """Draw a colored rectangle as fallback when sprites aren't available."""
        # Determine color based on tile type or collision info
        if collision_layers:
            # Prioritize collision layers for visual feedback
            if 'tree' in collision_layers:
                color = (34, 139, 34)  # Forest green for trees
            elif 'building' in collision_layers:
                color = (139, 69, 19)  # Saddle brown for buildings
            elif 'water' in collision_layers:
                color = (30, 144, 255)  # Dodger blue for water
            elif 'farm' in collision_layers:
                color = (255, 215, 0)  # Gold for farm areas
            elif 'grass' in collision_layers:
                color = (50, 205, 50)  # Lime green for grass
            elif 'obstacles' in collision_layers or 'collision' in collision_layers:
                color = (105, 105, 105)  # Dim gray for obstacles
            else:
                # Fallback for unknown collision layers
                color = (255, 69, 0)  # Red orange for unknown collision
        elif isinstance(tile_type, int):
            # Enhanced color mapping based on more granular GID ranges
            if tile_type == 0:
                color = (0, 0, 0)  # Black for empty
            elif 1 <= tile_type <= 20:  # Basic ground tiles
                color = (85, 107, 47)  # Dark olive green for ground
            elif 21 <= tile_type <= 100:  # Decorative ground
                color = (107, 142, 35)  # Olive drab
            elif 101 <= tile_type <= 200:  # Various terrain
                color = (154, 205, 50)  # Yellow green
            elif 201 <= tile_type <= 300:  # More terrain
                color = (124, 252, 0)  # Lawn green
            elif 301 <= tile_type <= 400:  # Tree/nature tiles (this should be our tree layer!)
                color = (34, 139, 34)  # Forest green for trees
            elif 401 <= tile_type <= 576:  # Upper waterfall range
                color = (70, 130, 180)  # Steel blue for waterfall
            elif 577 <= tile_type <= 1000:  # Base chip tiles
                color = (160, 82, 45)  # Saddle brown for base terrain
            elif 1001 <= tile_type <= 1640:  # More base tiles
                color = (210, 180, 140)  # Tan
            elif 1641 <= tile_type <= 2000:  # Grass range start
                color = (0, 128, 0)  # Green
            elif 2001 <= tile_type <= 2168:  # Grass range end
                color = (50, 205, 50)  # Lime green
            elif 2169 <= tile_type <= 3000:  # Water range start
                color = (0, 191, 255)  # Deep sky blue
            elif 3001 <= tile_type <= 5240:  # Water range middle-end
                color = (30, 144, 255)  # Dodger blue
            elif 5241 <= tile_type <= 5288:  # Flower range
                color = (255, 20, 147)  # Deep pink for flowers
            else:
                color = (128, 128, 128)  # Gray for unknown
        else:
            # Handle legacy types
            if tile_type == 0:  # Grass
                color = GREEN
            elif tile_type == 1:  # Stone
                color = GRAY
            elif tile_type == 2:  # Water
                color = BLUE
            elif tile_type == 3:  # Sand
                color = (255, 255, 0)  # Yellow
            elif tile_type == 4:  # Wall/Rock
                color = BROWN
            else:
                color = RED

        # Draw colored rectangle
        pygame.draw.rect(
            self.screen,
            color,
            (int(screen_x), int(screen_y), TILE_SIZE, TILE_SIZE)
        )

    def _draw_collision_overlay(self, screen_x, screen_y, collision_layers):
        """Draw semi-transparent collision overlays."""
        overlay = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
        if 'tree' in collision_layers:
            overlay.fill((34, 139, 34, 80))  # Semi-transparent green
        elif 'building' in collision_layers:
            overlay.fill((139, 69, 19, 80))  # Semi-transparent brown
        elif 'water' in collision_layers:
            overlay.fill((30, 144, 255, 80))  # Semi-transparent blue
        elif 'farm' in collision_layers:
            overlay.fill((255, 215, 0, 80))  # Semi-transparent gold
        elif 'grass' in collision_layers:
            overlay.fill((50, 205, 50, 80))  # Semi-transparent lime
        elif 'obstacles' in collision_layers or 'collision' in collision_layers:
            overlay.fill((105, 105, 105, 80))  # Semi-transparent gray
        else:
            overlay.fill((255, 69, 0, 80))  # Semi-transparent red orange
        self.screen.blit(overlay, (int(screen_x), int(screen_y)))

    def draw_player(self, player_id, player):
        """Draw a player."""
        # Convert world position to screen position
        screen_x, screen_y = self.world_to_screen(
            player.display_x * TILE_SIZE, 
            player.display_y * TILE_SIZE
        )

        # Skip if player is not visible
        if (screen_x < -TILE_SIZE or screen_y < -TILE_SIZE or
            screen_x > WINDOW_WIDTH or screen_y > WINDOW_HEIGHT):
            return

        # Draw player sprite
        color = self.get_player_color(player_id)
        pygame.draw.rect(
            self.screen,
            color,
            (int(screen_x), int(screen_y), TILE_SIZE, TILE_SIZE)
        )

        # Draw player name
        name_surface = self.small_font.render(player.username, True, WHITE)
        name_x = int(screen_x + TILE_SIZE // 2 - name_surface.get_width() // 2)
        name_y = int(screen_y - 20)
        self.screen.blit(name_surface, (name_x, name_y))

    def draw_floating_messages(self):
        """Draw floating chat messages above players."""
        current_time = time.time()

        # Draw messages for main player
        self.draw_player_floating_messages(self.player, current_time)

        # Draw messages for other players
        for player in self.other_players.values():
            self.draw_player_floating_messages(player, current_time)

    def draw_player_floating_messages(self, player, current_time):
        """Draw floating messages for a specific player."""
        screen_x, screen_y = self.world_to_screen(
            player.display_x * TILE_SIZE, 
            player.display_y * TILE_SIZE
        )

        # Draw messages stacked above the player
        y_offset = 0
        for message in player.floating_messages:
            if not message.is_expired(current_time):
                self.draw_floating_message(
                    screen_x + TILE_SIZE // 2,
                    screen_y - 40 - y_offset,
                    message.message,
                    message.get_alpha(current_time)
                )
                y_offset += 25

    def draw_floating_message(self, center_x, center_y, text, alpha):
        """Draw a single floating message."""
        # Create message surface
        text_surface = self.small_font.render(text, True, WHITE)
        text_width, text_height = text_surface.get_size()

        # Create bubble background
        bubble_padding = 8
        bubble_width = text_width + bubble_padding * 2
        bubble_height = text_height + bubble_padding * 2

        bubble_surface = pygame.Surface((bubble_width, bubble_height), pygame.SRCALPHA)
        bubble_color = (0, 0, 0, min(180, alpha))
        pygame.draw.rect(bubble_surface, bubble_color, bubble_surface.get_rect(), border_radius=8)

        # Position bubble centered above player
        bubble_x = int(center_x - bubble_width // 2)
        bubble_y = int(center_y - bubble_height)

        # Apply alpha to text
        if alpha < 255:
            text_surface.set_alpha(alpha)

        # Draw bubble and text
        self.screen.blit(bubble_surface, (bubble_x, bubble_y))
        self.screen.blit(text_surface, (bubble_x + bubble_padding, bubble_y + bubble_padding))

    def world_to_screen(self, world_x, world_y):
        """Convert world coordinates to screen coordinates."""
        return world_x - self.camera_x, world_y - self.camera_y

    def get_player_color(self, player_id):
        """Get a color for a player based on their ID."""
        # Generate a color based on player ID
        hash_val = hash(player_id)
        r = (hash_val & 0xFF0000) >> 16
        g = (hash_val & 0x00FF00) >> 8
        b = hash_val & 0x0000FF

        # Ensure colors are bright enough
        r = max(100, r)
        g = max(100, g)
        b = max(100, b)

        return (r, g, b)

    async def handle_login_events(self, event):
        """Handle login/register form events."""
        if self.state == GameState.LOGIN:
            fields = [self.username_field, self.password_field]
            buttons = [self.login_button, self.switch_button]
        else:  # REGISTER
            fields = [self.username_field, self.password_field, self.email_field]
            buttons = [self.register_button, self.switch_button]

        # Handle field events
        for field in fields:
            field.handle_event(event)

        # Handle button events
        for button in buttons:
            if button.handle_event(event):
                if button == self.login_button:
                    await self.attempt_login()
                elif button == self.register_button:
                    await self.attempt_register()
                elif button == self.switch_button:
                    if self.state == GameState.LOGIN:
                        self.state = GameState.REGISTER
                        self.switch_button.text = "Switch to Login"
                    else:
                        self.state = GameState.LOGIN
                        self.switch_button.text = "Switch to Register"

    async def handle_game_events(self, event):
        """Handle game events."""
        # Handle chat window events first
        if self.chat_window.handle_event(event):
            return

        # Handle movement
        if event.type == pygame.KEYDOWN:
            self.keys_pressed.add(event.key)
        elif event.type == pygame.KEYUP:
            self.keys_pressed.discard(event.key)

        # Handle chat toggle
        if event.type == pygame.KEYDOWN and event.key == pygame.K_t:
            if not self.chat_window.input_focused:
                self.chat_window.input_focused = True

    def handle_chat_message(self, payload):
        """Handle incoming chat messages."""
        chat_username = payload.get("username", "Unknown")
        chat_message = payload.get("message", "")
        channel = payload.get("channel", "local")

        # Add to chat window
        self.chat_window.add_message(chat_username, chat_message, channel)

        # For local chat, add floating message above player's head
        if channel == "local":
            current_time = time.time()
            floating_msg = FloatingMessage(chat_message, current_time)

            if chat_username == self.player.username:
                self.player.floating_messages.append(floating_msg)
            elif chat_username in self.other_players:
                self.other_players[chat_username].floating_messages.append(floating_msg)

    def update_camera(self):
        """Update camera to follow player's animated position with smooth interpolation."""
        # Calculate target camera position
        self.target_camera_x = self.player.display_x * TILE_SIZE - WINDOW_WIDTH // 2
        self.target_camera_y = self.player.display_y * TILE_SIZE - WINDOW_HEIGHT // 2
        
        # Smooth camera interpolation (0.1 = smooth, 0.5 = responsive, 1.0 = instant)
        camera_speed = 0.15
        self.camera_x += (self.target_camera_x - self.camera_x) * camera_speed
        self.camera_y += (self.target_camera_y - self.camera_y) * camera_speed

    async def process_movement(self):
        """Process continuous movement based on held keys."""
        if not self.websocket:
            return

        current_time = pygame.time.get_ticks() / MILLISECONDS_TO_SECONDS

        # Check if enough time has passed since last move
        if current_time - self.last_move_time < self.move_cooldown:
            return

        # Allow next movement when animation is nearly complete (85% done) for smoother continuous movement
        if self.player.is_moving:
            animation_progress = (current_time - self.player.move_start_time) / MOVEMENT_ANIMATION_DURATION
            if animation_progress < 0.95:  # Still too early in the animation
                return

        # Don't move if chat is focused
        if self.chat_window.input_focused:
            return

        direction = None
        if pygame.K_w in self.keys_pressed or pygame.K_UP in self.keys_pressed:
            direction = "UP"
        elif pygame.K_s in self.keys_pressed or pygame.K_DOWN in self.keys_pressed:
            direction = "DOWN"
        elif pygame.K_a in self.keys_pressed or pygame.K_LEFT in self.keys_pressed:
            direction = "LEFT"
        elif pygame.K_d in self.keys_pressed or pygame.K_RIGHT in self.keys_pressed:
            direction = "RIGHT"

        if direction:
            try:
                move_message = GameMessage(
                    type=MessageType.MOVE_INTENT,
                    payload={"direction": direction}
                )

                await self.send_message(move_message)
                self.last_move_time = current_time

            except Exception as e:
                print(f"Error sending move: {e}")

    def update_animations(self):
        """Update player movement animations."""
        current_time = pygame.time.get_ticks() / MILLISECONDS_TO_SECONDS

        # Update main player animation
        self.update_player_animation(self.player, current_time)

        # Update other players' animations
        for other_player in self.other_players.values():
            self.update_player_animation(other_player, current_time)

        # Update floating messages
        self.update_floating_messages()

    def update_player_animation(self, player, current_time):
        """Update animation for a specific player."""
        if player.is_moving:
            elapsed_time = current_time - player.move_start_time
            animation_progress = min(elapsed_time / player.move_duration, ANIMATION_COMPLETE)

            if animation_progress >= ANIMATION_COMPLETE:
                # Animation complete
                player.display_x = float(player.x)
                player.display_y = float(player.y)
                player.is_moving = False
            else:
                # Interpolate position
                start_x = getattr(player, '_start_x', float(player.x))
                start_y = getattr(player, '_start_y', float(player.y))

                player.display_x = start_x + (player.x - start_x) * animation_progress
                player.display_y = start_y + (player.y - start_y) * animation_progress

    def update_floating_messages(self):
        """Remove expired floating messages from all players."""
        current_time = time.time()

        # Clean up player's messages
        self.player.floating_messages = [
            msg for msg in self.player.floating_messages 
            if not msg.is_expired(current_time)
        ]

        # Clean up other players' messages
        for other_player in self.other_players.values():
            other_player.floating_messages = [
                msg for msg in other_player.floating_messages 
                if not msg.is_expired(current_time)
            ]

    async def request_chunks(self, map_id, center_x, center_y, radius=2):
        """Request map chunks from the server."""
        if not self.websocket:
            return

        try:
            chunk_request = GameMessage(
                type=MessageType.REQUEST_CHUNKS,
                payload={
                    "map_id": map_id,
                    "center_x": center_x,
                    "center_y": center_y,
                    "radius": radius
                }
            )

            await self.send_message(chunk_request)
        except Exception as e:
            print(f"Error requesting chunks: {e}")

    async def websocket_handler(self):
        """Handle WebSocket messages."""
        while self.websocket and self.state == GameState.PLAYING:
            try:
                message_data = await asyncio.wait_for(
                    self.websocket.recv(), 
                    timeout=WEBSOCKET_TIMEOUT
                )
                message = msgpack.unpackb(message_data, raw=False)

                await self.handle_server_message(message)

            except asyncio.TimeoutError:
                # Timeout is normal, continue listening
                continue
            except Exception as e:
                print(f"WebSocket error: {e}")
                break

    async def handle_server_message(self, message):
        """Handle incoming server messages."""
        msg_type = message.get("type")
        payload = message.get("payload", {})

        if msg_type == MessageType.WELCOME.value:
            await self.handle_welcome_message(payload)
        elif msg_type == MessageType.CHUNK_DATA.value:
            self.handle_chunk_data(payload)
        elif msg_type == MessageType.GAME_STATE_UPDATE.value:
            await self.handle_game_state_update(payload)
        elif msg_type == MessageType.NEW_CHAT_MESSAGE.value:
            self.handle_chat_message(payload)
        elif msg_type == MessageType.PLAYER_DISCONNECT.value:
            self.handle_player_disconnect(payload)
        elif msg_type == MessageType.ERROR.value:
            self.handle_error_message(payload)

    async def handle_welcome_message(self, payload):
        """Handle welcome message and initial player data."""
        player_data = payload.get("player", {})
        config_data = payload.get("config", {})

        if player_data:
            self.player.x = player_data.get("x", self.player.x)
            self.player.y = player_data.get("y", self.player.y)
            self.player.map_id = player_data.get("map_id", self.player.map_id)

            # Initialize display coordinates to match logical position
            self.player.display_x = float(self.player.x)
            self.player.display_y = float(self.player.y)

            self.update_camera()
            # Initialize chunk request tracking
            self.player.last_chunk_request_x = self.player.x
            self.player.last_chunk_request_y = self.player.y
            
            # Load tilesets for the current map
            if self.player.map_id and self.player.map_id != self.current_map_id:
                self.current_map_id = self.player.map_id
                try:
                    await self.tileset_manager.load_map_tilesets(self.current_map_id)
                    print(f"Loaded tilesets for map: {self.current_map_id}")
                except Exception as e:
                    print(f"Failed to load tilesets for map {self.current_map_id}: {e}")

        # Update timing from server config
        if config_data:
            self.move_cooldown = config_data.get("move_cooldown", self.move_cooldown)
            self.player.move_duration = config_data.get(
                "animation_duration", self.player.move_duration
            )

        # Request initial chunks
        await self.request_chunks(self.player.map_id, self.player.x, self.player.y)

    def handle_chunk_data(self, payload):
        """Handle chunk data from server."""
        chunks = payload.get("chunks", [])
        for chunk in chunks:
            self.chunk_manager.add_chunk(chunk)

    async def handle_game_state_update(self, payload):
        """Handle position updates from server."""
        entities = payload.get("entities", [])

        for entity in entities:
            if entity.get("type") == "player":
                username = entity.get("username")

                if username == self.player.username:
                    await self.update_own_player(entity)
                else:
                    self.update_other_player(username, entity)

    async def update_own_player(self, entity):
        """Update our own player from server data."""
        # Store old position for animation
        old_x, old_y = self.player.x, self.player.y

        # Update our player's position based on server
        new_x = entity.get("x", self.player.x)
        new_y = entity.get("y", self.player.y)

        # Check if position actually changed
        if new_x != old_x or new_y != old_y:
            self.player.x = new_x
            self.player.y = new_y

            # Start smooth animation from old position to new position
            self.player._start_x = float(old_x)
            self.player._start_y = float(old_y)
            self.player.display_x = float(old_x)
            self.player.display_y = float(old_y)
            self.player.is_moving = True
            self.player.move_start_time = pygame.time.get_ticks() / MILLISECONDS_TO_SECONDS

            # Update facing direction based on movement
            if new_x > old_x:
                self.player.facing_direction = "RIGHT"
            elif new_x < old_x:
                self.player.facing_direction = "LEFT"
            elif new_y > old_y:
                self.player.facing_direction = "DOWN"
            elif new_y < old_y:
                self.player.facing_direction = "UP"

            self.update_camera()

        # Check if we need to request new chunks
        distance_from_last_request = abs(
            self.player.x - self.player.last_chunk_request_x
        ) + abs(self.player.y - self.player.last_chunk_request_y)

        if distance_from_last_request >= CHUNK_REQUEST_DISTANCE:
            await self.request_chunks(
                self.player.map_id, self.player.x, self.player.y
            )
            self.player.last_chunk_request_x = self.player.x
            self.player.last_chunk_request_y = self.player.y

    def update_other_player(self, username, entity):
        """Update other players from server data."""
        new_x = entity.get("x", 0)
        new_y = entity.get("y", 0)

        if username not in self.other_players:
            # New player joined
            self.other_players[username] = Player()
            self.other_players[username].username = username

        other_player = self.other_players[username]
        old_x, old_y = other_player.x, other_player.y

        # Update position if changed
        if new_x != old_x or new_y != old_y:
            other_player.x = new_x
            other_player.y = new_y

            # Start smooth animation for other player too
            other_player._start_x = float(old_x) if old_x else float(new_x)
            other_player._start_y = float(old_y) if old_y else float(new_y)
            other_player.display_x = float(old_x) if old_x else float(new_x)
            other_player.display_y = float(old_y) if old_y else float(new_y)
            other_player.is_moving = True
            other_player.move_start_time = pygame.time.get_ticks() / MILLISECONDS_TO_SECONDS

            # Update facing direction
            if new_x > old_x:
                other_player.facing_direction = "RIGHT"
            elif new_x < old_x:
                other_player.facing_direction = "LEFT"
            elif new_y > old_y:
                other_player.facing_direction = "DOWN"
            elif new_y < old_y:
                other_player.facing_direction = "UP"

    def handle_player_disconnect(self, payload):
        """Handle player disconnection."""
        disconnected_username = payload.get("username")
        if disconnected_username and disconnected_username in self.other_players:
            del self.other_players[disconnected_username]

    def handle_error_message(self, payload):
        """Handle error messages from server."""
        error_msg = payload.get("message", "Unknown error")
        self.set_status(f"Server error: {error_msg}", RED)

    async def run(self):
        """Main game loop with separate WebSocket task."""
        running = True
        websocket_task = None

        while running:
            # Handle events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

                if self.state in [GameState.LOGIN, GameState.REGISTER]:
                    await self.handle_login_events(event)
                elif self.state == GameState.PLAYING:
                    await self.handle_game_events(event)

            # Start WebSocket handler when entering PLAYING state
            if self.websocket and self.state == GameState.PLAYING and websocket_task is None:
                websocket_task = asyncio.create_task(self.websocket_handler())
            elif self.state != GameState.PLAYING and websocket_task is not None:
                # Cancel WebSocket task when leaving PLAYING state
                websocket_task.cancel()
                websocket_task = None

            # Process continuous movement and animations
            if self.state == GameState.PLAYING:
                await self.process_movement()
                await self.process_pending_chat()  # Process any pending chat messages
                self.update_animations()
                self.update_camera()  # Update camera every frame for smooth movement

            # Draw
            if self.state in [GameState.LOGIN, GameState.REGISTER]:
                self.draw_login_form()
            elif self.state == GameState.PLAYING:
                self.draw_game()

            pygame.display.flip()
            self.clock.tick(FPS)
            
            # Small yield to allow other async tasks to run
            await asyncio.sleep(0)

        # Cleanup
        if websocket_task:
            websocket_task.cancel()
            try:
                await websocket_task
            except asyncio.CancelledError:
                pass
        
        if self.websocket:
            await self.websocket.close()
        
        # Cleanup tileset manager
        await self.tileset_manager.close()
        
        pygame.quit()


async def main():
    """Main function."""
    client = RPGClient()
    await client.run()


if __name__ == "__main__":
    asyncio.run(main())