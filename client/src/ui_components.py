"""
UI components - InputField, Button, ChatWindow.
"""

import pygame
import os
import sys
from typing import Optional, Dict, Any

# Import common constants
workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.append(workspace_root)
from common.src.constants import (
    BLACK,
    WHITE,
    RED,
    GREEN,
    BLUE,
    GRAY,
    DARK_GRAY,
)


class InputField:
    """Input field for forms."""

    def __init__(self, x, y, width, height, font, placeholder="", password=False):
        self.rect = pygame.Rect(x, y, width, height)
        self.font = font
        self.text = ""
        self.placeholder = placeholder
        self.password = password
        self.active = False
        self.cursor_pos = 0

    def handle_event(self, event):
        """Handle input events."""
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.active = self.rect.collidepoint(event.pos)
        elif event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_BACKSPACE:
                if self.cursor_pos > 0:
                    self.text = (
                        self.text[: self.cursor_pos - 1] + self.text[self.cursor_pos :]
                    )
                    self.cursor_pos -= 1
            elif event.unicode.isprintable():
                self.text = (
                    self.text[: self.cursor_pos]
                    + event.unicode
                    + self.text[self.cursor_pos :]
                )
                self.cursor_pos += 1

    def draw(self, screen):
        """Draw the input field."""
        color = WHITE if self.active else GRAY
        pygame.draw.rect(screen, DARK_GRAY, self.rect)
        pygame.draw.rect(screen, color, self.rect, 2)

        display_text = self.text
        if self.password:
            display_text = "*" * len(self.text)

        if not display_text and not self.active:
            display_text = self.placeholder
            text_color = GRAY
        else:
            text_color = WHITE

        text_surface = self.font.render(display_text, True, text_color)
        screen.blit(text_surface, (self.rect.x + 5, self.rect.y + 10))


class Button:
    """Button UI element."""

    def __init__(self, x, y, width, height, text, font):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text
        self.font = font
        self.hovered = False

    def handle_event(self, event):
        """Handle button events."""
        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                return True
        return False

    def draw(self, screen):
        """Draw the button."""
        color = WHITE if self.hovered else GRAY
        pygame.draw.rect(screen, color, self.rect)
        pygame.draw.rect(screen, BLACK, self.rect, 2)

        text_surface = self.font.render(self.text, True, BLACK)
        text_rect = text_surface.get_rect(center=self.rect.center)
        screen.blit(text_surface, text_rect)


class ChatWindow:
    """Chat window with tabbed interface."""

    def __init__(self, x, y, width, height, font, client):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.font = font
        self.client = client  # Store reference to client for async calls
        self.visible = True

        # Chat state
        self.active_tab = "local"
        self.tabs = {
            "global": {"messages": [], "hover": False},
            "local": {"messages": [], "hover": False},
            "dm": {"messages": [], "hover": False},
        }

        # Input state
        self.input_text = ""
        self.input_focused = False
        self.input_cursor_pos = 0
        self.pending_message = None  # Store message to send later

    def add_message(self, username, message, channel):
        """Add a message to the appropriate channel."""
        if channel in self.tabs:
            self.tabs[channel]["messages"].append({
                "username": username,
                "text": message,
                "channel": channel
            })

            # Keep only last 100 messages per channel
            if len(self.tabs[channel]["messages"]) > 100:
                self.tabs[channel]["messages"] = self.tabs[channel]["messages"][-100:]

    def handle_event(self, event):
        """Handle chat window events."""
        if not self.visible:
            return False

        if event.type == pygame.MOUSEBUTTONDOWN:
            mouse_x, mouse_y = event.pos

            # Check if click is within window bounds
            if not (self.x <= mouse_x <= self.x + self.width and 
                   self.y <= mouse_y <= self.y + self.height):
                self.input_focused = False
                return False

            # Check tab clicks
            tab_height = 30
            tab_width = self.width // 3
            if self.y <= mouse_y <= self.y + tab_height:
                tab_index = (mouse_x - self.x) // tab_width
                tabs = list(self.tabs.keys())
                if 0 <= tab_index < len(tabs):
                    self.active_tab = tabs[tab_index]
                    return True

            # Check input area click
            input_y = self.y + self.height - 30
            if input_y <= mouse_y <= input_y + 25:
                self.input_focused = True
                return True

            return True  # Consumed the click

        elif event.type == pygame.KEYDOWN and self.input_focused:
            if event.key == pygame.K_RETURN:
                if self.input_text.strip():
                    self.pending_message = (self.active_tab, self.input_text.strip())
                    self.input_text = ""
                    self.input_cursor_pos = 0
                return True
            elif event.key == pygame.K_ESCAPE:
                self.input_focused = False
                return True
            elif event.key == pygame.K_BACKSPACE:
                if self.input_cursor_pos > 0:
                    self.input_text = (
                        self.input_text[:self.input_cursor_pos-1] + 
                        self.input_text[self.input_cursor_pos:]
                    )
                    self.input_cursor_pos -= 1
                return True
            elif event.unicode.isprintable():
                self.input_text = (
                    self.input_text[:self.input_cursor_pos] + 
                    event.unicode + 
                    self.input_text[self.input_cursor_pos:]
                )
                self.input_cursor_pos += 1
                return True

        return False

    def draw(self, screen):
        """Draw the chat window."""
        if not self.visible:
            return

        # Draw main window background
        window_surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        pygame.draw.rect(window_surface, (0, 0, 0, 120), window_surface.get_rect(), border_radius=8)
        pygame.draw.rect(window_surface, (100, 100, 100), window_surface.get_rect(), 2, border_radius=8)

        # Draw tabs
        tab_height = 30
        tab_width = self.width // 3

        for i, (channel, tab_info) in enumerate(self.tabs.items()):
            tab_x = i * tab_width
            tab_rect = pygame.Rect(tab_x, 0, tab_width, tab_height)

            # Tab background color
            if channel == self.active_tab:
                tab_color = (80, 80, 80)
            elif tab_info.get("hover", False):
                tab_color = (60, 60, 60)
            else:
                tab_color = (40, 40, 40)

            pygame.draw.rect(window_surface, tab_color, tab_rect)
            pygame.draw.rect(window_surface, (100, 100, 100), tab_rect, 1)

            # Tab text
            tab_text = self.font.render(channel.title(), True, WHITE)
            text_x = tab_x + (tab_width - tab_text.get_width()) // 2
            text_y = (tab_height - tab_text.get_height()) // 2
            window_surface.blit(tab_text, (text_x, text_y))

        # Draw messages area
        messages_rect = pygame.Rect(5, tab_height + 5, self.width - 10, self.height - tab_height - 40)
        pygame.draw.rect(window_surface, (0, 0, 0, 80), messages_rect)
        pygame.draw.rect(window_surface, (100, 100, 100), messages_rect, 1)

        # Render messages
        active_messages = self.tabs[self.active_tab]["messages"]
        line_height = self.font.get_height() + 2
        max_lines = messages_rect.height // line_height
        visible_messages = active_messages[-max_lines:] if len(active_messages) > max_lines else active_messages

        y_offset = messages_rect.y + 5
        for message in visible_messages:
            # Format message
            if message.get("channel") == "local":
                text = f"[Local] {message['username']}: {message['text']}"
                color = GREEN
            elif message.get("channel") == "global":
                text = f"[Global] {message['username']}: {message['text']}"
                color = (0, 255, 255)  # Cyan
            elif message.get("channel") == "dm":
                text = f"[DM] {message['username']}: {message['text']}"
                color = (255, 0, 255)  # Magenta
            else:
                text = f"{message['username']}: {message['text']}"
                color = WHITE

            # Render message
            text_surface = self.font.render(text, True, color)
            window_surface.blit(text_surface, (messages_rect.x + 5, y_offset))
            y_offset += line_height

        # Draw input area
        input_rect = pygame.Rect(5, self.height - 30, self.width - 10, 25)
        input_color = (30, 30, 30, 100)
        border_color = WHITE if self.input_focused else (80, 80, 80)

        pygame.draw.rect(window_surface, input_color, input_rect)
        pygame.draw.rect(window_surface, border_color, input_rect, 2)

        # Render input text
        input_text = self.input_text
        if self.input_focused and (pygame.time.get_ticks() // 500) % 2:
            input_text = (self.input_text[:self.input_cursor_pos] + "|" + 
                         self.input_text[self.input_cursor_pos:])

        text_surface = self.font.render(input_text, True, WHITE)
        window_surface.blit(text_surface, (input_rect.x + 5, input_rect.y + 5))

        # Blit the window to the main screen
        screen.blit(window_surface, (self.x, self.y))