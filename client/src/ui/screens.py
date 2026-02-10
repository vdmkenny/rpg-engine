"""
Screen management for the RPG client.

Handles different game screens: Server Select, Login, Register, and Game.
"""

import pygame
from typing import Optional, Tuple

from ..logging_config import get_logger
from ..ui.colors import Colors

logger = get_logger(__name__)


class BaseScreen:
    """Base class for all screens."""
    
    def __init__(self, screen: pygame.Surface):
        self.screen = screen
        self.width = screen.get_width()
        self.height = screen.get_height()
        
        # Try to load retro font, fall back to default
        font_path = "client/assets/fonts/RetroRPG.ttf"
        try:
            self.font = pygame.font.Font(font_path, 24)
            self.small_font = pygame.font.Font(font_path, 18)
            self.tiny_font = pygame.font.Font(font_path, 14)
        except:
            self.font = pygame.font.Font(None, 36)
            self.small_font = pygame.font.Font(None, 24)
            self.tiny_font = pygame.font.Font(None, 18)
    
    def draw(self) -> None:
        """Draw the screen. Override in subclasses."""
        pass
    
    def handle_event(self, event: pygame.event.Event) -> Optional[str]:
        """
        Handle pygame event. Returns action string if something happens.
        Override in subclasses.
        """
        return None


class ServerSelectScreen(BaseScreen):
    """Server selection screen."""
    
    def __init__(self, screen: pygame.Surface, servers: list):
        super().__init__(screen)
        self.servers = servers
        self.selected_index = 0
        self.server_status = {}  # index -> status dict
    
    def draw(self) -> None:
        """Draw server selection screen."""
        self.screen.fill(Colors.PANEL_BG)
        
        center_x = self.width // 2
        
        # Title
        title = self.font.render("Select Server", True, Colors.TEXT_ORANGE)
        self.screen.blit(title, (center_x - title.get_width() // 2, 50))
        
        # Instructions
        instructions = self.tiny_font.render(
            "Use arrow keys or click to select, ENTER to connect, R to refresh", 
            True, Colors.TEXT_GRAY
        )
        self.screen.blit(instructions, (center_x - instructions.get_width() // 2, 100))
        
        # Server list
        start_y = 200
        for i, server in enumerate(self.servers):
            item_y = start_y + (i * 100)
            is_selected = i == self.selected_index
            
            # Server item background
            bg_color = Colors.STONE_MEDIUM if is_selected else Colors.STONE_DARK
            item_rect = pygame.Rect(center_x - 300, item_y, 600, 90)
            pygame.draw.rect(self.screen, bg_color, item_rect)
            
            border_color = Colors.TEXT_ORANGE if is_selected else Colors.SLOT_BORDER
            pygame.draw.rect(self.screen, border_color, item_rect, 3 if is_selected else 1)
            
            # Server name
            name_surface = self.font.render(server.get("name", "Unknown"), True, Colors.TEXT_WHITE)
            self.screen.blit(name_surface, (center_x - 280, item_y + 15))
            
            # Server description
            desc_surface = self.small_font.render(
                server.get("description", ""), 
                True, Colors.TEXT_GRAY
            )
            self.screen.blit(desc_surface, (center_x - 280, item_y + 45))
            
            # Status (right side)
            status = self.server_status.get(i, {})
            if status.get("status") == "ok":
                # Extract player count and capacity
                capacity = status.get("capacity", {})
                current_players = capacity.get("current_players", 0)
                max_players = capacity.get("max_players", 100)
                status_text = f"{current_players}/{max_players} players"
                status_color = Colors.TEXT_GREEN
            else:
                status_text = status.get("error", "Checking...")
                status_color = Colors.TEXT_RED
            
            status_surface = self.tiny_font.render(status_text, True, status_color)
            # Right-align at x+420 (right side of item)
            self.screen.blit(status_surface, (center_x + 280 - status_surface.get_width(), item_y + 15))
            
            # MOTD (below description)
            motd = status.get("motd", "")
            if motd:
                motd_truncated = motd[:50] + ("..." if len(motd) > 50 else "")
                motd_surface = self.tiny_font.render(motd_truncated, True, Colors.TEXT_GRAY)
                self.screen.blit(motd_surface, (center_x - 280, item_y + 65))
    
    def handle_event(self, event: pygame.event.Event) -> Optional[str]:
        """Handle input events."""
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_UP:
                self.selected_index = max(0, self.selected_index - 1)
            elif event.key == pygame.K_DOWN:
                self.selected_index = min(len(self.servers) - 1, self.selected_index + 1)
            elif event.key == pygame.K_RETURN:
                return f"select_server:{self.selected_index}"
            elif event.key == pygame.K_r:
                return "refresh_status"
        
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:  # Left click
                mouse_pos = pygame.mouse.get_pos()
                center_x = self.width // 2
                start_y = 200
                
                for i in range(len(self.servers)):
                    item_y = start_y + (i * 100)
                    item_rect = pygame.Rect(center_x - 300, item_y, 600, 90)
                    
                    if item_rect.collidepoint(mouse_pos):
                        self.selected_index = i
                        return f"select_server:{i}"
        
        return None


class LoginScreen(BaseScreen):
    """Login/Register screen."""
    
    def __init__(self, screen: pygame.Surface, is_register: bool = False):
        super().__init__(screen)
        self.is_register = is_register
        self.username = ""
        self.password = ""
        self.email = ""  # Only for register
        self.active_field = "username"
        self.status_message = ""
        self.status_color = Colors.TEXT_WHITE
    
    def draw(self) -> None:
        """Draw login/register form."""
        self.screen.fill(Colors.PANEL_BG)
        
        center_x = self.width // 2
        
        # Title
        title = "Register" if self.is_register else "Login"
        title_surface = self.font.render(title, True, Colors.TEXT_ORANGE)
        self.screen.blit(title_surface, (center_x - title_surface.get_width() // 2, 150))
        
        # Fields
        fields = [
            ("Username", self.username, "username", 300),
            ("Password", "*" * len(self.password), "password", 360),
        ]
        
        if self.is_register:
            fields.append(("Email", self.email, "email", 420))
        
        for label, value, field_name, y_pos in fields:
            # Label
            label_surface = self.small_font.render(label, True, Colors.TEXT_WHITE)
            self.screen.blit(label_surface, (center_x - 150, y_pos - 20))
            
            # Field background
            field_rect = pygame.Rect(center_x - 150, y_pos, 300, 40)
            pygame.draw.rect(self.screen, Colors.SLOT_BG, field_rect)
            
            # Border (highlight if active)
            border_color = Colors.TEXT_ORANGE if self.active_field == field_name else Colors.SLOT_BORDER
            pygame.draw.rect(self.screen, border_color, field_rect, 2)
            
            # Field text
            text_surface = self.font.render(value, True, Colors.TEXT_WHITE)
            self.screen.blit(text_surface, (field_rect.x + 10, field_rect.y + 8))
        
        # Buttons
        btn_y = 480 if not self.is_register else 500
        
        # Main action button
        btn_rect = pygame.Rect(center_x - 80, btn_y, 160, 40)
        pygame.draw.rect(self.screen, Colors.STONE_MEDIUM, btn_rect)
        pygame.draw.rect(self.screen, Colors.STONE_HIGHLIGHT, btn_rect, 2)
        
        btn_text = "Register" if self.is_register else "Login"
        btn_surface = self.font.render(btn_text, True, Colors.TEXT_WHITE)
        self.screen.blit(btn_surface, (center_x - btn_surface.get_width() // 2, btn_y + 8))
        
        # Switch mode button
        switch_rect = pygame.Rect(center_x - 80, btn_y + 50, 160, 40)
        pygame.draw.rect(self.screen, Colors.STONE_DARK, switch_rect)
        pygame.draw.rect(self.screen, Colors.SLOT_BORDER, switch_rect, 2)
        
        switch_text = "Login" if self.is_register else "Register"
        switch_surface = self.small_font.render(f"Go to {switch_text}", True, Colors.TEXT_GRAY)
        self.screen.blit(switch_surface, (center_x - switch_surface.get_width() // 2, btn_y + 60))
        
        # Status message
        if self.status_message:
            status_surface = self.small_font.render(self.status_message, True, self.status_color)
            self.screen.blit(status_surface, (center_x - status_surface.get_width() // 2, 650))
    
    def handle_event(self, event: pygame.event.Event) -> Optional[str]:
        """Handle input events."""
        center_x = self.width // 2
        
        if event.type == pygame.KEYDOWN:
            # Enter submits
            if event.key == pygame.K_RETURN:
                return "submit"
            
            # Tab switches fields
            if event.key == pygame.K_TAB:
                if self.active_field == "username":
                    self.active_field = "password"
                elif self.active_field == "password":
                    if self.is_register:
                        self.active_field = "email"
                    else:
                        self.active_field = "username"
                elif self.active_field == "email":
                    self.active_field = "username"
            
            # Backspace
            elif event.key == pygame.K_BACKSPACE:
                if self.active_field == "username":
                    self.username = self.username[:-1]
                elif self.active_field == "password":
                    self.password = self.password[:-1]
                elif self.active_field == "email":
                    self.email = self.email[:-1]
            
            # Regular text input
            elif event.unicode.isalnum() or event.unicode in "._-@":
                if self.active_field == "username":
                    self.username += event.unicode
                elif self.active_field == "password":
                    self.password += event.unicode
                elif self.active_field == "email":
                    self.email += event.unicode
        
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                mouse_pos = pygame.mouse.get_pos()
                btn_y = 480 if not self.is_register else 500
                
                # Check field clicks
                fields_y = [
                    ("username", 300),
                    ("password", 360),
                ]
                if self.is_register:
                    fields_y.append(("email", 420))
                
                for field_name, y_pos in fields_y:
                    field_rect = pygame.Rect(center_x - 150, y_pos, 300, 40)
                    if field_rect.collidepoint(mouse_pos):
                        self.active_field = field_name
                        return None
                
                # Check button clicks
                btn_rect = pygame.Rect(center_x - 80, btn_y, 160, 40)
                if btn_rect.collidepoint(mouse_pos):
                    return "submit"
                
                # Check switch button
                switch_rect = pygame.Rect(center_x - 80, btn_y + 50, 160, 40)
                if switch_rect.collidepoint(mouse_pos):
                    return "switch_mode"
        
        return None
    
    def get_credentials(self) -> Tuple[str, str, Optional[str]]:
        """Get the entered credentials."""
        return (self.username, self.password, self.email if self.is_register else None)
    
    def set_status(self, message: str, color: Tuple[int, int, int] = Colors.TEXT_WHITE) -> None:
        """Set status message."""
        self.status_message = message
        self.status_color = color


class GameScreen(BaseScreen):
    """Main game screen - renders the world and UI."""
    
    def __init__(self, screen: pygame.Surface, renderer):
        super().__init__(screen)
        self.renderer = renderer
    
    def draw(self, game_state) -> None:
        """Draw the game world and UI."""
        # The renderer handles all the game drawing
        if self.renderer:
            self.renderer.render()
    
    def handle_event(self, event: pygame.event.Event, game_state=None) -> Optional[str]:
        """Handle events - pass to UI renderer."""
        if self.renderer and self.renderer.ui_renderer:
            action = self.renderer.ui_renderer.handle_event(event, game_state)
            if action:
                return action
        return None
