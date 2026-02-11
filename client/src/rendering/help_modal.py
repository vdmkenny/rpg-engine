"""
Help modal - Full-screen modal showing controls and commands.

Provides keyboard controls and slash commands reference.
Modal can be opened via "?" button or /help command.
"""

import pygame
from typing import Dict, List, Optional, Callable, Any, Tuple

from client.src.ui.colors import Colors


class HelpModal:
    """Full-screen help modal showing controls and commands."""
    
    # Layout constants
    PADDING = 40
    BUTTON_SIZE = 32
    
    def __init__(
        self,
        screen_width: int,
        screen_height: int,
        on_close: Optional[Callable[[], None]] = None,
    ):
        """Initialize the help modal.
        
        Args:
            screen_width: Screen width in pixels
            screen_height: Screen height in pixels
            on_close: Callback when modal is closed
        """
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.on_close = on_close
        
        # Modal state
        self.visible = False
        self._close_hovered = False
        
        # Calculate layout
        self._calculate_layout()
        
        # Fonts
        try:
            self.title_font = pygame.font.Font("client/assets/fonts/RetroRPG.ttf", 32)
            self.section_font = pygame.font.Font("client/assets/fonts/RetroRPG.ttf", 22)
            self.text_font = pygame.font.Font("client/assets/fonts/RetroRPG.ttf", 18)
            self.small_font = pygame.font.Font("client/assets/fonts/RetroRPG.ttf", 16)
        except:
            self.title_font = pygame.font.Font(None, 32)
            self.section_font = pygame.font.Font(None, 22)
            self.text_font = pygame.font.Font(None, 18)
            self.small_font = pygame.font.Font(None, 16)
    
    def _calculate_layout(self) -> None:
        """Calculate modal layout rectangles."""
        # Full screen modal with dark overlay
        self.modal_rect = pygame.Rect(0, 0, self.screen_width, self.screen_height)
        
        # Main panel (centered, leaves margin for dark overlay)
        margin = 60
        self.panel_rect = pygame.Rect(
            margin, margin,
            self.screen_width - margin * 2,
            self.screen_height - margin * 2
        )
        
        # Close button (top-right corner of panel)
        self.close_rect = pygame.Rect(
            self.panel_rect.right - self.BUTTON_SIZE - 10,
            self.panel_rect.y + 10,
            self.BUTTON_SIZE,
            self.BUTTON_SIZE
        )
        
        # Content area (below title, above close button)
        self.content_rect = pygame.Rect(
            self.panel_rect.x + self.PADDING,
            self.panel_rect.y + 70,
            self.panel_rect.width - self.PADDING * 2,
            self.panel_rect.height - 100
        )
        
        # Split content into two columns
        col_width = (self.content_rect.width - 40) // 2
        self.left_col = pygame.Rect(
            self.content_rect.x,
            self.content_rect.y,
            col_width,
            self.content_rect.height
        )
        self.right_col = pygame.Rect(
            self.content_rect.x + col_width + 40,
            self.content_rect.y,
            col_width,
            self.content_rect.height
        )
    
    def show(self) -> None:
        """Show the help modal."""
        self.visible = True
        self._close_hovered = False
    
    def hide(self) -> None:
        """Hide the help modal."""
        self.visible = False
        if self.on_close:
            self.on_close()
    
    def is_visible(self) -> bool:
        """Check if modal is visible."""
        return self.visible
    
    def handle_event(self, event: pygame.event.Event) -> Optional[str]:
        """Handle input events."""
        if not self.visible:
            return None
        
        if event.type == pygame.MOUSEMOTION:
            mouse_pos = event.pos
            self._close_hovered = self.close_rect.collidepoint(mouse_pos)
        
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:  # Left click
                mouse_pos = event.pos
                
                # Check close button
                if self.close_rect.collidepoint(mouse_pos):
                    self.hide()
                    return "help_closed"
                
                # Check if clicked outside panel (close modal)
                if not self.panel_rect.collidepoint(mouse_pos):
                    self.hide()
                    return "help_closed"
        
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.hide()
                return "help_closed"
            elif event.key == pygame.K_F1 or event.key == pygame.K_QUESTION:
                self.hide()
                return "help_closed"
        
        return None
    
    def draw(self, screen: pygame.Surface) -> None:
        """Draw the help modal."""
        if not self.visible:
            return
        
        # Dark overlay
        overlay = pygame.Surface((self.screen_width, self.screen_height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        screen.blit(overlay, (0, 0))
        
        # Main panel background
        pygame.draw.rect(screen, Colors.PANEL_BG, self.panel_rect)
        pygame.draw.rect(screen, Colors.PANEL_BORDER, self.panel_rect, 2)
        pygame.draw.rect(screen, Colors.PANEL_INNER_BORDER, self.panel_rect.inflate(-4, -4), 1)
        
        # Title
        title_surface = self.title_font.render("Controls & Help", True, Colors.TEXT_ORANGE)
        title_x = self.panel_rect.centerx - title_surface.get_width() // 2
        screen.blit(title_surface, (title_x, self.panel_rect.y + 20))
        
        # Close button (X)
        close_color = Colors.BUTTON_HOVER if self._close_hovered else Colors.BUTTON_BG
        pygame.draw.rect(screen, close_color, self.close_rect)
        pygame.draw.rect(screen, Colors.PANEL_BORDER, self.close_rect, 1)
        
        # Draw X
        x_surface = self.text_font.render("X", True, Colors.TEXT_WHITE)
        x_x = self.close_rect.centerx - x_surface.get_width() // 2
        x_y = self.close_rect.centery - x_surface.get_height() // 2
        screen.blit(x_surface, (x_x, x_y))
        
        # Draw content columns
        self._draw_controls_column(screen)
        self._draw_commands_column(screen)
    
    def _draw_controls_column(self, screen: pygame.Surface) -> None:
        """Draw keyboard controls in left column."""
        y = self.left_col.y
        
        # Section header
        header = self.section_font.render("Keyboard Controls", True, Colors.TEXT_YELLOW)
        screen.blit(header, (self.left_col.x, y))
        y += 35
        
        # Control entries
        controls = [
            ("Movement", "WASD / Arrow Keys"),
            ("Chat", "Enter / C"),
            ("Unfocus Chat", "ESC"),
            ("Inventory", "I"),
            ("Equipment", "E"),
            ("Stats", "S"),
            ("Settings", "O"),
            ("Minimap", "M (toggle)"),
            ("Help", "? / F1"),
            ("Scroll Chat", "Page Up/Down"),
        ]
        
        for label, key in controls:
            # Label
            label_surface = self.text_font.render(label, True, Colors.TEXT_WHITE)
            screen.blit(label_surface, (self.left_col.x, y))
            
            # Key (right-aligned)
            key_surface = self.small_font.render(key, True, Colors.TEXT_CYAN)
            key_x = self.left_col.right - key_surface.get_width()
            screen.blit(key_surface, (key_x, y + 2))
            
            y += 28
    
    def _draw_commands_column(self, screen: pygame.Surface) -> None:
        """Draw slash commands in right column."""
        y = self.right_col.y
        
        # Section header
        header = self.section_font.render("Slash Commands", True, Colors.TEXT_YELLOW)
        screen.blit(header, (self.right_col.x, y))
        y += 35
        
        # Command entries
        commands = [
            ("/help", "Show this help"),
            ("/customize", "Character customisation"),
            ("/logout", "Log out"),
        ]
        
        for cmd, desc in commands:
            # Command
            cmd_surface = self.text_font.render(cmd, True, Colors.TEXT_ORANGE)
            screen.blit(cmd_surface, (self.right_col.x, y))
            
            # Description (right-aligned or below)
            desc_surface = self.small_font.render(desc, True, Colors.TEXT_GRAY)
            desc_x = self.right_col.right - desc_surface.get_width()
            # If description fits to the right, put it there
            cmd_width = cmd_surface.get_width() + 20
            if desc_x > self.right_col.x + cmd_width:
                screen.blit(desc_surface, (desc_x, y + 2))
            else:
                # Put description below
                y += 20
                screen.blit(desc_surface, (self.right_col.x + 10, y))
            
            y += 28
        
        # Add tip at bottom
        y += 20
        tip_surface = self.small_font.render("Tip: Click ? button or press ?/F1 anytime!", True, Colors.TEXT_GREEN)
        screen.blit(tip_surface, (self.right_col.x, y))


class HelpButton:
    """Small "?" button for top-right corner of screen."""
    
    SIZE = 28
    
    def __init__(self, x: int, y: int):
        """Initialize help button.
        
        Args:
            x: Button x position
            y: Button y position
        """
        self.rect = pygame.Rect(x, y, self.SIZE, self.SIZE)
        self.hovered = False
        
        # Font
        try:
            self.font = pygame.font.Font("client/assets/fonts/RetroRPG.ttf", 18)
        except:
            self.font = pygame.font.Font(None, 18)
    
    def draw(self, screen: pygame.Surface) -> None:
        """Draw the help button."""
        # Background
        bg_color = Colors.BUTTON_HOVER if self.hovered else Colors.BUTTON_BG
        pygame.draw.rect(screen, bg_color, self.rect)
        pygame.draw.rect(screen, Colors.PANEL_BORDER, self.rect, 1)
        
        # Inner highlight
        if self.hovered:
            pygame.draw.rect(screen, Colors.STONE_HIGHLIGHT, self.rect.inflate(-2, -2), 1)
        
        # Question mark
        text_surface = self.font.render("?", True, Colors.TEXT_YELLOW)
        text_x = self.rect.centerx - text_surface.get_width() // 2
        text_y = self.rect.centery - text_surface.get_height() // 2
        screen.blit(text_surface, (text_x, text_y))
    
    def handle_event(self, event: pygame.event.Event) -> Optional[str]:
        """Handle mouse events.
        
        Returns:
            "help_opened" if clicked, None otherwise
        """
        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.rect.collidepoint(event.pos)
        
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1 and self.rect.collidepoint(event.pos):
                return "help_opened"
        
        return None
