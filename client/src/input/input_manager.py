"""
Input handling for the client.

Manages keyboard and mouse input, maps inputs to game actions.
"""

import pygame
from typing import Dict, Set, Optional, Callable
from enum import Enum, auto

from ..config import get_config
from ..core import get_state_machine, GameState, get_event_bus, EventType
from ..logging_config import get_logger

logger = get_logger(__name__)


class InputAction(Enum):
    """Input actions that can be triggered."""
    # Movement
    MOVE_UP = auto()
    MOVE_DOWN = auto()
    MOVE_LEFT = auto()
    MOVE_RIGHT = auto()
    
    # UI
    OPEN_INVENTORY = auto()
    OPEN_EQUIPMENT = auto()
    OPEN_STATS = auto()
    TOGGLE_CHAT = auto()
    HIDE_CHAT = auto()
    OPEN_HELP = auto()
    CLOSE_PANELS = auto()
    
    # Actions
    ATTACK = auto()
    INTERACT = auto()
    PICKUP = auto()
    
    # Menu
    ESCAPE = auto()


class InputManager:
    """Central input manager for keyboard and mouse."""
    
    def __init__(self):
        self.config = get_config()
        self.state_machine = get_state_machine()
        self.event_bus = get_event_bus()
        
        # Key states
        self.keys_pressed: Set[int] = set()
        self.keys_just_pressed: Set[int] = set()
        
        # Mouse state
        self.mouse_pos = (0, 0)
        self.mouse_buttons = [False, False, False]  # Left, Middle, Right
        self.mouse_just_pressed = [False, False, False]
        
        # Action handlers
        self.action_handlers: Dict[InputAction, Callable] = {}
        
        # Movement cooldown
        self.last_move_time = 0.0
        self.move_cooldown = self.config.game.move_cooldown
        
        # Chat input mode
        self.chat_input_active = False
        self.chat_input_text = ""
        
        # Key mapping
        self._setup_key_mapping()
    
    def _setup_key_mapping(self) -> None:
        """Setup key to action mapping from config."""
        self.key_map: Dict[int, InputAction] = {}
        
        # Movement
        for key_name in self.config.key_bindings.move_up:
            key = self._key_name_to_code(key_name)
            if key:
                self.key_map[key] = InputAction.MOVE_UP
        
        for key_name in self.config.key_bindings.move_down:
            key = self._key_name_to_code(key_name)
            if key:
                self.key_map[key] = InputAction.MOVE_DOWN
        
        for key_name in self.config.key_bindings.move_left:
            key = self._key_name_to_code(key_name)
            if key:
                self.key_map[key] = InputAction.MOVE_LEFT
        
        for key_name in self.config.key_bindings.move_right:
            key = self._key_name_to_code(key_name)
            if key:
                self.key_map[key] = InputAction.MOVE_RIGHT
        
        # Actions
        self.key_map[self._key_name_to_code(self.config.key_bindings.open_inventory)] = InputAction.OPEN_INVENTORY
        self.key_map[self._key_name_to_code(self.config.key_bindings.open_equipment)] = InputAction.OPEN_EQUIPMENT
        self.key_map[self._key_name_to_code(self.config.key_bindings.open_stats)] = InputAction.OPEN_STATS
        self.key_map[self._key_name_to_code(self.config.key_bindings.toggle_chat)] = InputAction.TOGGLE_CHAT
        self.key_map[self._key_name_to_code(self.config.key_bindings.hide_chat)] = InputAction.HIDE_CHAT
        self.key_map[self._key_name_to_code(self.config.key_bindings.help)] = InputAction.OPEN_HELP
        self.key_map[self._key_name_to_code(self.config.key_bindings.escape)] = InputAction.CLOSE_PANELS
    
    def _key_name_to_code(self, key_name: str) -> int:
        """Convert key name to pygame key code."""
        key_map = {
            "up": pygame.K_UP,
            "down": pygame.K_DOWN,
            "left": pygame.K_LEFT,
            "right": pygame.K_RIGHT,
            "w": pygame.K_w,
            "a": pygame.K_a,
            "s": pygame.K_s,
            "d": pygame.K_d,
            "i": pygame.K_i,
            "e": pygame.K_e,
            "s": pygame.K_s,
            "t": pygame.K_t,
            "c": pygame.K_c,
            "?": pygame.K_QUESTION,
            "escape": pygame.K_ESCAPE,
            "space": pygame.K_SPACE,
            "return": pygame.K_RETURN,
            "tab": pygame.K_TAB,
        }
        return key_map.get(key_name.lower(), 0)
    
    def register_action_handler(self, action: InputAction, handler: Callable) -> None:
        """Register a handler for an input action."""
        self.action_handlers[action] = handler
    
    def process_events(self) -> bool:
        """
        Process all pending pygame events.
        
        Returns:
            False if quit event received, True otherwise
        """
        # Clear just-pressed states
        self.keys_just_pressed.clear()
        self.mouse_just_pressed = [False, False, False]
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            
            elif event.type == pygame.KEYDOWN:
                self.keys_pressed.add(event.key)
                self.keys_just_pressed.add(event.key)
                
                # Handle chat input
                if self.chat_input_active:
                    self._handle_chat_input(event)
                else:
                    self._handle_key_down(event.key)
            
            elif event.type == pygame.KEYUP:
                self.keys_pressed.discard(event.key)
            
            elif event.type == pygame.MOUSEMOTION:
                self.mouse_pos = event.pos
            
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button <= 3:
                    self.mouse_buttons[event.button - 1] = True
                    self.mouse_just_pressed[event.button - 1] = True
                    self._handle_mouse_down(event.button, event.pos)
            
            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button <= 3:
                    self.mouse_buttons[event.button - 1] = False
            
            elif event.type == pygame.VIDEORESIZE:
                # Handle window resize
                pass
        
        # Process continuous key presses (for movement)
        if not self.chat_input_active:
            self._process_continuous_keys()
        
        return True
    
    def _handle_key_down(self, key: int) -> None:
        """Handle key press (not chat input)."""
        action = self.key_map.get(key)
        if not action:
            return
        
        handler = self.action_handlers.get(action)
        if handler:
            handler()
    
    def _handle_chat_input(self, event: pygame.event.Event) -> None:
        """Handle text input for chat."""
        if event.key == pygame.K_RETURN:
            # Send chat
            if self.chat_input_text.strip():
                self._submit_chat()
            self.chat_input_active = False
            self.chat_input_text = ""
        elif event.key == pygame.K_ESCAPE:
            # Cancel chat
            self.chat_input_active = False
            self.chat_input_text = ""
        elif event.key == pygame.K_BACKSPACE:
            # Backspace
            self.chat_input_text = self.chat_input_text[:-1]
        else:
            # Add character
            if event.unicode.isprintable():
                self.chat_input_text += event.unicode
    
    def _submit_chat(self) -> None:
        """Submit chat message."""
        from ..network.message_sender import get_message_sender
        sender = get_message_sender()
        
        # Send chat (fire and forget)
        asyncio.create_task(sender.chat_send(self.chat_input_text))
        
        # Add to local history immediately
        self.event_bus.emit(EventType.CHAT_SENT, {"message": self.chat_input_text})
    
    def _handle_mouse_down(self, button: int, pos: tuple) -> None:
        """Handle mouse button press."""
        if button == 1:  # Left click
            self._handle_left_click(pos)
        elif button == 3:  # Right click
            self._handle_right_click(pos)
    
    def _handle_left_click(self, pos: tuple) -> None:
        """Handle left mouse click."""
        # Convert screen to tile coordinates
        from ..rendering.renderer import Renderer
        # Would need access to camera for this conversion
        pass
    
    def _handle_right_click(self, pos: tuple) -> None:
        """Handle right mouse click (context menu)."""
        pass
    
    def _process_continuous_keys(self) -> None:
        """Process keys that are held down (for movement)."""
        current_time = pygame.time.get_ticks() / 1000.0
        
        if current_time - self.last_move_time < self.move_cooldown:
            return
        
        # Check for movement keys
        direction = None
        
        if pygame.K_UP in self.keys_pressed or pygame.K_w in self.keys_pressed:
            direction = "UP"
        elif pygame.K_DOWN in self.keys_pressed or pygame.K_s in self.keys_pressed:
            direction = "DOWN"
        elif pygame.K_LEFT in self.keys_pressed or pygame.K_a in self.keys_pressed:
            direction = "LEFT"
        elif pygame.K_RIGHT in self.keys_pressed or pygame.K_d in self.keys_pressed:
            direction = "RIGHT"
        
        if direction:
            handler = self.action_handlers.get(self._get_direction_action(direction))
            if handler:
                handler()
                self.last_move_time = current_time
    
    def _get_direction_action(self, direction: str) -> InputAction:
        """Convert direction string to action."""
        return {
            "UP": InputAction.MOVE_UP,
            "DOWN": InputAction.MOVE_DOWN,
            "LEFT": InputAction.MOVE_LEFT,
            "RIGHT": InputAction.MOVE_RIGHT
        }.get(direction, InputAction.MOVE_UP)
    
    def is_chat_active(self) -> bool:
        """Check if chat input is active."""
        return self.chat_input_active
    
    def get_chat_text(self) -> str:
        """Get current chat input text."""
        return self.chat_input_text
    
    def start_chat_input(self) -> None:
        """Start chat input mode."""
        self.chat_input_active = True
        self.chat_input_text = ""
