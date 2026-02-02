"""
OSRS-style UI components for the RPG client.
Stone/brown themed interface panels with classic MMO aesthetics.
"""

import pygame
from typing import Dict, List, Optional, Tuple, Callable, Any
from enum import Enum
from dataclasses import dataclass

import sys
import os
workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.append(workspace_root)

from common.src.protocol import ChatChannel


# =============================================================================
# COLOR PALETTE (Classic MMO Theme)
# =============================================================================

class Colors:
    """OSRS-inspired color palette."""
    # Stone/Brown Theme
    STONE_DARK = (59, 50, 41)
    STONE_MEDIUM = (79, 67, 55)
    STONE_LIGHT = (99, 84, 69)
    STONE_HIGHLIGHT = (139, 119, 99)
    
    # Panel backgrounds
    PANEL_BG = (49, 42, 35)
    PANEL_BORDER = (29, 25, 21)
    PANEL_INNER_BORDER = (69, 59, 49)
    
    # Slot backgrounds
    SLOT_BG = (39, 33, 27)
    SLOT_BORDER = (79, 67, 55)
    SLOT_HOVER = (59, 50, 41)
    SLOT_SELECTED = (99, 84, 69)
    
    # Text colors
    TEXT_YELLOW = (255, 255, 0)
    TEXT_WHITE = (255, 255, 255)
    TEXT_ORANGE = (255, 152, 31)
    TEXT_GREEN = (0, 255, 0)
    TEXT_RED = (255, 0, 0)
    TEXT_CYAN = (0, 255, 255)
    TEXT_PURPLE = (255, 0, 255)
    TEXT_GRAY = (128, 128, 128)
    TEXT_DARK = (49, 42, 35)
    
    # Health bar colors
    HP_GREEN = (0, 255, 0)
    HP_RED = (255, 0, 0)
    HP_BG = (0, 0, 0)
    HP_BORDER = (0, 0, 0)
    
    # XP bar colors
    XP_GREEN = (0, 180, 0)
    XP_BG = (40, 40, 40)
    
    # Rarity colors
    RARITY_COMMON = (255, 255, 255)
    RARITY_UNCOMMON = (30, 255, 0)
    RARITY_RARE = (0, 112, 221)
    RARITY_EPIC = (163, 53, 238)
    RARITY_LEGENDARY = (255, 128, 0)
    
    # Minimap
    MINIMAP_BG = (0, 0, 0)
    MINIMAP_PLAYER = (255, 255, 255)
    MINIMAP_OTHER_PLAYER = (0, 255, 255)
    MINIMAP_NPC = (255, 255, 0)
    MINIMAP_MONSTER = (255, 0, 0)
    
    # Combat
    HIT_SPLAT_DAMAGE = (255, 0, 0)
    HIT_SPLAT_MISS = (0, 128, 255)
    HIT_SPLAT_HEAL = (0, 255, 0)


# =============================================================================
# BASE UI PANEL
# =============================================================================

class UIPanel:
    """Base class for UI panels with stone-themed styling."""
    
    def __init__(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        title: str = "",
        visible: bool = True,
        draggable: bool = False
    ):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.title = title
        self.visible = visible
        self.draggable = draggable
        
        # Drag state
        self.is_dragging = False
        self.drag_offset_x = 0
        self.drag_offset_y = 0
        
        # Pre-render background
        self._bg_surface: Optional[pygame.Surface] = None
        self._dirty = True
    
    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(self.x, self.y, self.width, self.height)
    
    def set_position(self, x: int, y: int) -> None:
        self.x = x
        self.y = y
    
    def _render_background(self) -> pygame.Surface:
        """Render the stone-themed panel background."""
        surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        
        # Main background
        pygame.draw.rect(surface, Colors.PANEL_BG, (0, 0, self.width, self.height))
        
        # Outer border (dark)
        pygame.draw.rect(surface, Colors.PANEL_BORDER, (0, 0, self.width, self.height), 2)
        
        # Inner border (lighter, 3D effect)
        pygame.draw.rect(surface, Colors.PANEL_INNER_BORDER, (2, 2, self.width - 4, self.height - 4), 1)
        
        # Top/left highlight
        pygame.draw.line(surface, Colors.STONE_HIGHLIGHT, (3, 3), (self.width - 4, 3), 1)
        pygame.draw.line(surface, Colors.STONE_HIGHLIGHT, (3, 3), (3, self.height - 4), 1)
        
        # Bottom/right shadow
        pygame.draw.line(surface, Colors.PANEL_BORDER, (3, self.height - 4), (self.width - 4, self.height - 4), 1)
        pygame.draw.line(surface, Colors.PANEL_BORDER, (self.width - 4, 3), (self.width - 4, self.height - 4), 1)
        
        return surface
    
    def draw(self, screen: pygame.Surface, font: pygame.font.Font) -> None:
        """Draw the panel to the screen."""
        if not self.visible:
            return
        
        # Render background if dirty
        if self._dirty or self._bg_surface is None:
            self._bg_surface = self._render_background()
            self._dirty = False
        
        screen.blit(self._bg_surface, (self.x, self.y))
        
        # Draw title if present
        if self.title:
            title_surface = font.render(self.title, True, Colors.TEXT_ORANGE)
            title_x = self.x + (self.width - title_surface.get_width()) // 2
            screen.blit(title_surface, (title_x, self.y + 5))
    
    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle events. Returns True if event was consumed."""
        if not self.visible:
            return False
        
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                if self.draggable and event.button == 1:
                    self.is_dragging = True
                    self.drag_offset_x = event.pos[0] - self.x
                    self.drag_offset_y = event.pos[1] - self.y
                return True
        
        elif event.type == pygame.MOUSEBUTTONUP:
            if self.is_dragging:
                self.is_dragging = False
        
        elif event.type == pygame.MOUSEMOTION:
            if self.is_dragging:
                self.x = event.pos[0] - self.drag_offset_x
                self.y = event.pos[1] - self.drag_offset_y
                return True
        
        return False


# =============================================================================
# INVENTORY PANEL (28 slots, 4 columns x 7 rows)
# =============================================================================

class InventoryPanel(UIPanel):
    """OSRS-style 28-slot inventory panel."""
    
    SLOT_SIZE = 36
    SLOT_PADDING = 2
    COLUMNS = 4
    ROWS = 7
    
    def __init__(self, x: int, y: int, on_slot_click: Optional[Callable[[int, int], None]] = None):
        # Calculate dimensions
        width = self.COLUMNS * (self.SLOT_SIZE + self.SLOT_PADDING) + self.SLOT_PADDING + 12
        height = self.ROWS * (self.SLOT_SIZE + self.SLOT_PADDING) + self.SLOT_PADDING + 32
        
        super().__init__(x, y, width, height, title="Inventory")
        
        self.on_slot_click = on_slot_click
        self.hovered_slot: Optional[int] = None
        self.selected_slot: Optional[int] = None
        
        # Item data (slot -> item info dict)
        self.items: Dict[int, dict] = {}
        
        # Item sprites cache
        self.item_sprites: Dict[int, pygame.Surface] = {}
    
    def set_items(self, items: Dict[int, dict]) -> None:
        """Set inventory items."""
        self.items = items
    
    def _get_slot_rect(self, slot: int) -> pygame.Rect:
        """Get the rectangle for a specific slot."""
        col = slot % self.COLUMNS
        row = slot // self.COLUMNS
        
        x = self.x + 6 + col * (self.SLOT_SIZE + self.SLOT_PADDING)
        y = self.y + 26 + row * (self.SLOT_SIZE + self.SLOT_PADDING)
        
        return pygame.Rect(x, y, self.SLOT_SIZE, self.SLOT_SIZE)
    
    def _get_slot_at_pos(self, pos: Tuple[int, int]) -> Optional[int]:
        """Get slot index at mouse position."""
        for slot in range(28):
            if self._get_slot_rect(slot).collidepoint(pos):
                return slot
        return None
    
    def draw(self, screen: pygame.Surface, font: pygame.font.Font) -> None:
        """Draw the inventory panel."""
        if not self.visible:
            return
        
        super().draw(screen, font)
        
        # Draw slots
        small_font = pygame.font.Font(None, 18)
        
        for slot in range(28):
            rect = self._get_slot_rect(slot)
            
            # Slot background
            if slot == self.selected_slot:
                pygame.draw.rect(screen, Colors.SLOT_SELECTED, rect)
            elif slot == self.hovered_slot:
                pygame.draw.rect(screen, Colors.SLOT_HOVER, rect)
            else:
                pygame.draw.rect(screen, Colors.SLOT_BG, rect)
            
            # Slot border
            pygame.draw.rect(screen, Colors.SLOT_BORDER, rect, 1)
            
            # Draw item if present
            if slot in self.items:
                item = self.items[slot]
                self._draw_item(screen, rect, item, small_font)
    
    def _draw_item(self, screen: pygame.Surface, rect: pygame.Rect, item: dict, font: pygame.font.Font) -> None:
        """Draw an item in a slot."""
        # For now, draw a colored rectangle based on item category
        item_rect = rect.inflate(-4, -4)
        
        # Color based on rarity
        rarity = item.get("rarity", "common")
        if rarity == "legendary":
            color = Colors.RARITY_LEGENDARY
        elif rarity == "epic":
            color = Colors.RARITY_EPIC
        elif rarity == "rare":
            color = Colors.RARITY_RARE
        elif rarity == "uncommon":
            color = Colors.RARITY_UNCOMMON
        else:
            color = Colors.RARITY_COMMON
        
        # Draw item placeholder (colored square)
        pygame.draw.rect(screen, color, item_rect)
        pygame.draw.rect(screen, Colors.PANEL_BORDER, item_rect, 1)
        
        # Draw quantity if > 1
        quantity = item.get("quantity", 1)
        if quantity > 1:
            qty_text = str(quantity) if quantity < 100000 else f"{quantity // 1000}K"
            qty_surface = font.render(qty_text, True, Colors.TEXT_YELLOW)
            screen.blit(qty_surface, (rect.x + 2, rect.y + 2))
    
    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle inventory events."""
        if not self.visible:
            return False
        
        if event.type == pygame.MOUSEMOTION:
            self.hovered_slot = self._get_slot_at_pos(event.pos)
        
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                slot = self._get_slot_at_pos(event.pos)
                if slot is not None:
                    if event.button == 1:  # Left click
                        if self.on_slot_click:
                            self.on_slot_click(slot, 1)
                    elif event.button == 3:  # Right click
                        if self.on_slot_click:
                            self.on_slot_click(slot, 3)
                return True
        
        return super().handle_event(event)


# =============================================================================
# EQUIPMENT PANEL
# =============================================================================

class EquipmentPanel(UIPanel):
    """OSRS-style equipment panel with slot layout."""
    
    SLOT_SIZE = 36
    
    # Slot positions relative to panel (x, y)
    SLOT_POSITIONS = {
        "head": (70, 30),
        "cape": (30, 70),
        "neck": (70, 70),
        "ammunition": (110, 70),
        "weapon": (30, 110),
        "body": (70, 110),
        "shield": (110, 110),
        "legs": (70, 150),
        "hands": (30, 150),
        "feet": (70, 190),
        "ring": (110, 150),
    }
    
    def __init__(self, x: int, y: int, on_slot_click: Optional[Callable[[str, int], None]] = None):
        super().__init__(x, y, 160, 240, title="Equipment")
        
        self.on_slot_click = on_slot_click
        self.hovered_slot: Optional[str] = None
        
        # Equipment data (slot name -> item info dict)
        self.equipment: Dict[str, dict] = {}
    
    def set_equipment(self, equipment: Dict[str, dict]) -> None:
        """Set equipment data."""
        self.equipment = equipment
    
    def _get_slot_rect(self, slot_name: str) -> pygame.Rect:
        """Get rectangle for a slot."""
        pos = self.SLOT_POSITIONS.get(slot_name, (0, 0))
        return pygame.Rect(
            self.x + pos[0],
            self.y + pos[1],
            self.SLOT_SIZE,
            self.SLOT_SIZE
        )
    
    def _get_slot_at_pos(self, pos: Tuple[int, int]) -> Optional[str]:
        """Get slot name at mouse position."""
        for slot_name in self.SLOT_POSITIONS:
            if self._get_slot_rect(slot_name).collidepoint(pos):
                return slot_name
        return None
    
    def draw(self, screen: pygame.Surface, font: pygame.font.Font) -> None:
        """Draw the equipment panel."""
        if not self.visible:
            return
        
        super().draw(screen, font)
        
        small_font = pygame.font.Font(None, 14)
        
        for slot_name, pos in self.SLOT_POSITIONS.items():
            rect = self._get_slot_rect(slot_name)
            
            # Slot background
            if slot_name == self.hovered_slot:
                pygame.draw.rect(screen, Colors.SLOT_HOVER, rect)
            else:
                pygame.draw.rect(screen, Colors.SLOT_BG, rect)
            
            # Slot border
            pygame.draw.rect(screen, Colors.SLOT_BORDER, rect, 1)
            
            # Draw slot label
            label = slot_name[0].upper()
            label_surface = small_font.render(label, True, Colors.TEXT_GRAY)
            label_x = rect.x + (rect.width - label_surface.get_width()) // 2
            label_y = rect.y + rect.height - label_surface.get_height() - 1
            screen.blit(label_surface, (label_x, label_y))
            
            # Draw item if present
            if slot_name in self.equipment:
                item = self.equipment[slot_name]
                self._draw_item(screen, rect, item)
    
    def _draw_item(self, screen: pygame.Surface, rect: pygame.Rect, item: dict) -> None:
        """Draw an equipped item."""
        item_rect = rect.inflate(-6, -6)
        
        # Color based on rarity
        rarity = item.get("rarity", "common")
        if rarity == "legendary":
            color = Colors.RARITY_LEGENDARY
        elif rarity == "epic":
            color = Colors.RARITY_EPIC
        elif rarity == "rare":
            color = Colors.RARITY_RARE
        elif rarity == "uncommon":
            color = Colors.RARITY_UNCOMMON
        else:
            color = Colors.RARITY_COMMON
        
        pygame.draw.rect(screen, color, item_rect)
        pygame.draw.rect(screen, Colors.PANEL_BORDER, item_rect, 1)
    
    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle equipment events."""
        if not self.visible:
            return False
        
        if event.type == pygame.MOUSEMOTION:
            self.hovered_slot = self._get_slot_at_pos(event.pos)
        
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                slot = self._get_slot_at_pos(event.pos)
                if slot is not None and self.on_slot_click:
                    self.on_slot_click(slot, event.button)
                return True
        
        return super().handle_event(event)


# =============================================================================
# STATS PANEL
# =============================================================================

class StatsPanel(UIPanel):
    """OSRS-style stats/skills panel."""
    
    SKILL_ICON_SIZE = 24
    SKILLS_PER_ROW = 3
    
    SKILL_ORDER = [
        "attack", "hitpoints", "mining",
        "strength", "agility", "smithing",
        "defence", "herblore", "fishing",
        "ranged", "thieving", "cooking",
        "prayer", "crafting", "firemaking",
        "magic", "fletching", "woodcutting",
        "runecraft", "slayer", "farming",
        "construction", "hunter", "summoning",
    ]
    
    def __init__(self, x: int, y: int):
        super().__init__(x, y, 200, 280, title="Skills")
        
        # Skills data (skill name -> {level, xp, next_level_xp})
        self.skills: Dict[str, dict] = {}
        
        self.hovered_skill: Optional[str] = None
    
    def set_skills(self, skills: Dict[str, dict]) -> None:
        """Set skills data."""
        self.skills = skills
    
    def draw(self, screen: pygame.Surface, font: pygame.font.Font) -> None:
        """Draw the stats panel."""
        if not self.visible:
            return
        
        super().draw(screen, font)
        
        small_font = pygame.font.Font(None, 16)
        tiny_font = pygame.font.Font(None, 14)
        
        start_y = self.y + 28
        
        for i, skill_name in enumerate(self.SKILL_ORDER):
            if skill_name not in self.skills:
                continue
            
            skill = self.skills[skill_name]
            col = i % self.SKILLS_PER_ROW
            row = i // self.SKILLS_PER_ROW
            
            x = self.x + 8 + col * 64
            y = start_y + row * 30
            
            rect = pygame.Rect(x, y, 60, 26)
            
            # Background
            if skill_name == self.hovered_skill:
                pygame.draw.rect(screen, Colors.SLOT_HOVER, rect)
            else:
                pygame.draw.rect(screen, Colors.SLOT_BG, rect)
            pygame.draw.rect(screen, Colors.SLOT_BORDER, rect, 1)
            
            # Skill name abbreviation
            abbr = skill_name[:3].capitalize()
            abbr_surface = tiny_font.render(abbr, True, Colors.TEXT_GRAY)
            screen.blit(abbr_surface, (x + 2, y + 2))
            
            # Level
            level = skill.get("level", 1)
            level_surface = small_font.render(str(level), True, Colors.TEXT_YELLOW)
            screen.blit(level_surface, (x + 38, y + 6))
    
    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle stats events."""
        return super().handle_event(event)


# =============================================================================
# HEALTH/PRAYER/RUN ORBS
# =============================================================================

class StatusOrb:
    """Circular status orb (HP, Prayer, Run Energy)."""
    
    def __init__(
        self,
        x: int,
        y: int,
        radius: int = 20,
        color: Tuple[int, int, int] = Colors.HP_GREEN,
        label: str = ""
    ):
        self.x = x
        self.y = y
        self.radius = radius
        self.color = color
        self.label = label
        
        self.current_value: int = 10
        self.max_value: int = 10
    
    def set_value(self, current: int, maximum: int) -> None:
        """Set current and max values."""
        self.current_value = current
        self.max_value = maximum
    
    def draw(self, screen: pygame.Surface, font: pygame.font.Font) -> None:
        """Draw the status orb."""
        # Background circle (dark)
        pygame.draw.circle(screen, Colors.PANEL_BG, (self.x, self.y), self.radius)
        
        # Progress arc
        if self.max_value > 0:
            ratio = self.current_value / self.max_value
            # Draw as a filled portion
            end_angle = 3.14159 * 2 * ratio - 3.14159 / 2
            
            # Simple filled circle approach for now
            fill_height = int(self.radius * 2 * ratio)
            fill_rect = pygame.Rect(
                self.x - self.radius,
                self.y + self.radius - fill_height,
                self.radius * 2,
                fill_height
            )
            
            # Create a clipping mask
            clip_surface = pygame.Surface((self.radius * 2, self.radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(clip_surface, self.color, (self.radius, self.radius), self.radius - 2)
            
            # Apply fill ratio
            fill_surface = pygame.Surface((self.radius * 2, self.radius * 2), pygame.SRCALPHA)
            pygame.draw.rect(
                fill_surface,
                self.color,
                (0, self.radius * 2 - fill_height, self.radius * 2, fill_height)
            )
            
            # Combine
            clip_surface.blit(fill_surface, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
            screen.blit(clip_surface, (self.x - self.radius, self.y - self.radius))
        
        # Border
        pygame.draw.circle(screen, Colors.PANEL_BORDER, (self.x, self.y), self.radius, 2)
        
        # Value text
        small_font = pygame.font.Font(None, 18)
        value_text = f"{self.current_value}"
        text_surface = small_font.render(value_text, True, Colors.TEXT_WHITE)
        text_x = self.x - text_surface.get_width() // 2
        text_y = self.y - text_surface.get_height() // 2
        screen.blit(text_surface, (text_x, text_y))


# =============================================================================
# MINIMAP
# =============================================================================

class Minimap(UIPanel):
    """Circular minimap showing nearby area."""
    
    def __init__(self, x: int, y: int, radius: int = 60):
        super().__init__(x - radius, y - radius, radius * 2, radius * 2)
        self.center_x = x
        self.center_y = y
        self.radius = radius
        
        # Map data
        self.player_x: int = 0
        self.player_y: int = 0
        self.other_players: List[Tuple[int, int]] = []
        self.npcs: List[Tuple[int, int]] = []
        self.monsters: List[Tuple[int, int]] = []
    
    def update(
        self,
        player_x: int,
        player_y: int,
        other_players: List[Tuple[int, int]],
        npcs: List[Tuple[int, int]],
        monsters: List[Tuple[int, int]]
    ) -> None:
        """Update minimap data."""
        self.player_x = player_x
        self.player_y = player_y
        self.other_players = other_players
        self.npcs = npcs
        self.monsters = monsters
    
    def draw(self, screen: pygame.Surface, font: pygame.font.Font) -> None:
        """Draw the minimap."""
        if not self.visible:
            return
        
        # Create circular surface
        minimap_surface = pygame.Surface((self.radius * 2, self.radius * 2), pygame.SRCALPHA)
        
        # Background
        pygame.draw.circle(minimap_surface, Colors.MINIMAP_BG, (self.radius, self.radius), self.radius)
        
        # Draw entities relative to player
        scale = 3  # pixels per tile
        
        # Draw other players
        for px, py in self.other_players:
            dx = (px - self.player_x) * scale
            dy = (py - self.player_y) * scale
            if dx * dx + dy * dy < (self.radius - 5) ** 2:
                pygame.draw.circle(
                    minimap_surface,
                    Colors.MINIMAP_OTHER_PLAYER,
                    (self.radius + dx, self.radius + dy),
                    2
                )
        
        # Draw NPCs
        for nx, ny in self.npcs:
            dx = (nx - self.player_x) * scale
            dy = (ny - self.player_y) * scale
            if dx * dx + dy * dy < (self.radius - 5) ** 2:
                pygame.draw.circle(
                    minimap_surface,
                    Colors.MINIMAP_NPC,
                    (self.radius + dx, self.radius + dy),
                    2
                )
        
        # Draw monsters
        for mx, my in self.monsters:
            dx = (mx - self.player_x) * scale
            dy = (my - self.player_y) * scale
            if dx * dx + dy * dy < (self.radius - 5) ** 2:
                pygame.draw.circle(
                    minimap_surface,
                    Colors.MINIMAP_MONSTER,
                    (self.radius + dx, self.radius + dy),
                    2
                )
        
        # Draw player (center, white arrow/dot)
        pygame.draw.circle(minimap_surface, Colors.MINIMAP_PLAYER, (self.radius, self.radius), 3)
        
        # Border
        pygame.draw.circle(minimap_surface, Colors.STONE_DARK, (self.radius, self.radius), self.radius, 3)
        pygame.draw.circle(minimap_surface, Colors.STONE_HIGHLIGHT, (self.radius, self.radius), self.radius - 2, 1)
        
        screen.blit(minimap_surface, (self.center_x - self.radius, self.center_y - self.radius))


# =============================================================================
# CHAT WINDOW (Updated with OSRS style)
# =============================================================================

class ChatWindow(UIPanel):
    """OSRS-style chat window with tabs."""
    
    TAB_HEIGHT = 24
    
    def __init__(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        font: pygame.font.Font,
        on_send: Optional[Callable[[str, str], None]] = None
    ):
        super().__init__(x, y, width, height, title="")
        
        self.font = font
        self.on_send = on_send
        
        # Chat tabs
        self.tabs = {
            ChatChannel.LOCAL.value: {"messages": [], "color": Colors.TEXT_GREEN},
            ChatChannel.GLOBAL.value: {"messages": [], "color": Colors.TEXT_CYAN},
            ChatChannel.DM.value: {"messages": [], "color": Colors.TEXT_PURPLE},
        }
        self.active_tab = ChatChannel.LOCAL.value
        
        # Input state
        self.input_text = ""
        self.input_focused = False
        self.input_cursor_pos = 0
        
        # Pending message for async send
        self.pending_message: Optional[Tuple[str, str]] = None
    
    def add_message(self, username: str, message: str, channel: str) -> None:
        """Add a message to a channel."""
        if channel in self.tabs:
            self.tabs[channel]["messages"].append({
                "username": username,
                "text": message,
            })
            # Keep only last 100 messages
            if len(self.tabs[channel]["messages"]) > 100:
                self.tabs[channel]["messages"] = self.tabs[channel]["messages"][-100:]
    
    def _wrap_text(self, text: str, max_width: int) -> list:
        """Wrap text to fit within max_width pixels."""
        words = text.split(' ')
        lines = []
        current_line = ""
        
        for word in words:
            test_line = current_line + (" " if current_line else "") + word
            if self.font.size(test_line)[0] <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                # If single word is too long, force it on its own line
                if self.font.size(word)[0] > max_width:
                    lines.append(word)
                    current_line = ""
                else:
                    current_line = word
        
        if current_line:
            lines.append(current_line)
        
        return lines if lines else [""]
    
    def toggle_visibility(self) -> None:
        """Toggle chat window visibility."""
        self.visible = not self.visible
    
    def draw(self, screen: pygame.Surface, font: pygame.font.Font) -> None:
        """Draw the chat window."""
        if not self.visible:
            return
        
        # Background
        pygame.draw.rect(screen, (*Colors.PANEL_BG, 200), (self.x, self.y, self.width, self.height))
        pygame.draw.rect(screen, Colors.PANEL_BORDER, (self.x, self.y, self.width, self.height), 2)
        
        # Draw tabs
        tab_width = self.width // 3
        for i, (channel, tab_data) in enumerate(self.tabs.items()):
            tab_x = self.x + i * tab_width
            tab_rect = pygame.Rect(tab_x, self.y, tab_width, self.TAB_HEIGHT)
            
            # Tab background
            if channel == self.active_tab:
                pygame.draw.rect(screen, Colors.STONE_MEDIUM, tab_rect)
            else:
                pygame.draw.rect(screen, Colors.STONE_DARK, tab_rect)
            pygame.draw.rect(screen, Colors.PANEL_BORDER, tab_rect, 1)
            
            # Tab text
            tab_text = self.font.render(channel.title(), True, tab_data["color"])
            text_x = tab_x + (tab_width - tab_text.get_width()) // 2
            screen.blit(tab_text, (text_x, self.y + 4))
        
        # Messages area
        messages_y = self.y + self.TAB_HEIGHT + 4
        messages_height = self.height - self.TAB_HEIGHT - 34
        max_text_width = self.width - 10  # Padding on both sides
        
        # Build wrapped lines from messages
        active_messages = self.tabs[self.active_tab]["messages"]
        line_height = self.font.get_height() + 2
        max_lines = messages_height // line_height
        
        # Collect all wrapped lines
        all_lines = []
        color = self.tabs[self.active_tab]["color"]
        for msg in active_messages:
            text = f"{msg['username']}: {msg['text']}"
            wrapped = self._wrap_text(text, max_text_width)
            all_lines.extend(wrapped)
        
        # Get only the visible lines (last N lines)
        visible_lines = all_lines[-max_lines:] if len(all_lines) > max_lines else all_lines
        
        y_offset = messages_y
        for line in visible_lines:
            text_surface = self.font.render(line, True, color)
            screen.blit(text_surface, (self.x + 5, y_offset))
            y_offset += line_height
        
        # Input area
        input_y = self.y + self.height - 28
        input_rect = pygame.Rect(self.x + 4, input_y, self.width - 8, 24)
        
        pygame.draw.rect(screen, Colors.SLOT_BG, input_rect)
        border_color = Colors.TEXT_WHITE if self.input_focused else Colors.SLOT_BORDER
        pygame.draw.rect(screen, border_color, input_rect, 1)
        
        # Input text with cursor
        display_text = self.input_text
        if self.input_focused and (pygame.time.get_ticks() // 500) % 2:
            display_text = self.input_text[:self.input_cursor_pos] + "|" + self.input_text[self.input_cursor_pos:]
        
        text_surface = self.font.render(display_text, True, Colors.TEXT_WHITE)
        screen.blit(text_surface, (input_rect.x + 4, input_rect.y + 4))
    
    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle chat events."""
        if not self.visible:
            return False
        
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                mouse_x, mouse_y = event.pos
                
                # Check tab clicks
                if mouse_y < self.y + self.TAB_HEIGHT:
                    tab_width = self.width // 3
                    tab_index = (mouse_x - self.x) // tab_width
                    tabs = list(self.tabs.keys())
                    if 0 <= tab_index < len(tabs):
                        self.active_tab = tabs[tab_index]
                        return True
                
                # Check input area
                input_y = self.y + self.height - 28
                if mouse_y >= input_y:
                    self.input_focused = True
                    return True
                
                return True
            else:
                self.input_focused = False
        
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
                    self.input_text = self.input_text[:self.input_cursor_pos - 1] + self.input_text[self.input_cursor_pos:]
                    self.input_cursor_pos -= 1
                return True
            elif event.unicode and event.unicode.isprintable():
                self.input_text = self.input_text[:self.input_cursor_pos] + event.unicode + self.input_text[self.input_cursor_pos:]
                self.input_cursor_pos += 1
                return True
        
        return False


# =============================================================================
# CONTEXT MENU
# =============================================================================

@dataclass
class ContextMenuItem:
    """Item in a context menu."""
    label: str
    action: Callable[[], None]
    color: Tuple[int, int, int] = Colors.TEXT_WHITE


class ContextMenu:
    """Right-click context menu."""
    
    ITEM_HEIGHT = 20
    PADDING = 4
    
    def __init__(self):
        self.visible = False
        self.x = 0
        self.y = 0
        self.items: List[ContextMenuItem] = []
        self.hovered_index: int = -1
    
    def show(self, x: int, y: int, items: List[ContextMenuItem]) -> None:
        """Show the context menu at position."""
        self.x = x
        self.y = y
        self.items = items
        self.visible = True
        self.hovered_index = -1
    
    def hide(self) -> None:
        """Hide the context menu."""
        self.visible = False
        self.items = []
    
    @property
    def width(self) -> int:
        # Calculate based on longest item
        return 150  # Fixed width for now
    
    @property
    def height(self) -> int:
        return len(self.items) * self.ITEM_HEIGHT + self.PADDING * 2
    
    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(self.x, self.y, self.width, self.height)
    
    def draw(self, screen: pygame.Surface, font: pygame.font.Font) -> None:
        """Draw the context menu."""
        if not self.visible or not self.items:
            return
        
        # Background
        pygame.draw.rect(screen, Colors.PANEL_BG, self.rect)
        pygame.draw.rect(screen, Colors.PANEL_BORDER, self.rect, 2)
        
        # Items
        for i, item in enumerate(self.items):
            item_y = self.y + self.PADDING + i * self.ITEM_HEIGHT
            item_rect = pygame.Rect(self.x + 2, item_y, self.width - 4, self.ITEM_HEIGHT)
            
            # Highlight hovered item
            if i == self.hovered_index:
                pygame.draw.rect(screen, Colors.SLOT_HOVER, item_rect)
            
            # Text
            text_surface = font.render(item.label, True, item.color)
            screen.blit(text_surface, (self.x + self.PADDING + 2, item_y + 2))
    
    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle context menu events."""
        if not self.visible:
            return False
        
        if event.type == pygame.MOUSEMOTION:
            if self.rect.collidepoint(event.pos):
                relative_y = event.pos[1] - self.y - self.PADDING
                self.hovered_index = relative_y // self.ITEM_HEIGHT
                if self.hovered_index >= len(self.items):
                    self.hovered_index = -1
            else:
                self.hovered_index = -1
        
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                if 0 <= self.hovered_index < len(self.items):
                    self.items[self.hovered_index].action()
                self.hide()
                return True
            else:
                self.hide()
        
        return False


# =============================================================================
# HELP PANEL
# =============================================================================

class HelpPanel(UIPanel):
    """Help panel showing game controls and keybindings."""
    
    CONTROLS = [
        ("Movement", [
            ("W / Up Arrow", "Move up"),
            ("S / Down Arrow", "Move down"),
            ("A / Left Arrow", "Move left"),
            ("D / Right Arrow", "Move right"),
        ]),
        ("UI Panels", [
            ("I", "Toggle inventory"),
            ("E", "Toggle equipment"),
            ("S", "Toggle stats/skills"),
            ("C", "Toggle chat window"),
            ("ESC", "Close panels/menus"),
        ]),
        ("Interaction", [
            ("Left Click", "Attack / Pickup / Use"),
            ("Right Click", "Context menu"),
            ("T", "Open chat input"),
            ("Enter", "Send chat message"),
        ]),
    ]
    
    def __init__(self, x: int, y: int):
        super().__init__(x, y, 280, 340, title="Controls", draggable=True)
        self.visible = False
    
    def draw(self, screen: pygame.Surface, font: pygame.font.Font) -> None:
        """Draw the help panel."""
        if not self.visible:
            return
        
        super().draw(screen, font)
        
        small_font = pygame.font.Font(None, 20)
        tiny_font = pygame.font.Font(None, 18)
        
        y_offset = self.y + 30
        
        for section_name, keybindings in self.CONTROLS:
            # Section header
            header_surface = small_font.render(section_name, True, Colors.TEXT_ORANGE)
            screen.blit(header_surface, (self.x + 10, y_offset))
            y_offset += 22
            
            # Keybindings
            for key, description in keybindings:
                # Key
                key_surface = tiny_font.render(key, True, Colors.TEXT_YELLOW)
                screen.blit(key_surface, (self.x + 20, y_offset))
                
                # Description
                desc_surface = tiny_font.render(f"- {description}", True, Colors.TEXT_WHITE)
                screen.blit(desc_surface, (self.x + 120, y_offset))
                
                y_offset += 18
            
            y_offset += 8  # Space between sections
        
        # Close hint at bottom
        close_text = tiny_font.render("Press ? or click X to close", True, Colors.TEXT_GRAY)
        screen.blit(close_text, (self.x + (self.width - close_text.get_width()) // 2, self.y + self.height - 24))
        
        # Close button (X)
        close_rect = pygame.Rect(self.x + self.width - 24, self.y + 6, 18, 18)
        pygame.draw.rect(screen, Colors.STONE_DARK, close_rect)
        pygame.draw.rect(screen, Colors.SLOT_BORDER, close_rect, 1)
        x_surface = small_font.render("X", True, Colors.TEXT_RED)
        screen.blit(x_surface, (close_rect.x + 4, close_rect.y + 1))
    
    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle help panel events."""
        if not self.visible:
            return False
        
        if event.type == pygame.MOUSEBUTTONDOWN:
            # Check close button
            close_rect = pygame.Rect(self.x + self.width - 24, self.y + 6, 18, 18)
            if close_rect.collidepoint(event.pos):
                self.visible = False
                return True
        
        return super().handle_event(event)


class HelpButton:
    """Small '?' button to toggle help panel."""
    
    def __init__(self, x: int, y: int, size: int = 28):
        self.x = x
        self.y = y
        self.size = size
        self.hovered = False
    
    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(self.x, self.y, self.size, self.size)
    
    def draw(self, screen: pygame.Surface, font: pygame.font.Font) -> None:
        """Draw the help button."""
        # Background
        if self.hovered:
            pygame.draw.rect(screen, Colors.STONE_LIGHT, self.rect)
        else:
            pygame.draw.rect(screen, Colors.STONE_MEDIUM, self.rect)
        
        # Border
        pygame.draw.rect(screen, Colors.STONE_HIGHLIGHT, self.rect, 2)
        
        # Question mark
        q_font = pygame.font.Font(None, 24)
        q_surface = q_font.render("?", True, Colors.TEXT_WHITE)
        q_x = self.x + (self.size - q_surface.get_width()) // 2
        q_y = self.y + (self.size - q_surface.get_height()) // 2
        screen.blit(q_surface, (q_x, q_y))
    
    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle events. Returns True if button was clicked."""
        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos) and event.button == 1:
                return True
        return False


class LogoutButton:
    """Small logout button to disconnect and return to login screen."""
    
    def __init__(self, x: int, y: int, width: int = 60, height: int = 24):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.hovered = False
    
    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(self.x, self.y, self.width, self.height)
    
    def draw(self, screen: pygame.Surface, font: pygame.font.Font) -> None:
        """Draw the logout button."""
        # Background
        if self.hovered:
            pygame.draw.rect(screen, (120, 60, 60), self.rect)  # Darker red on hover
        else:
            pygame.draw.rect(screen, (100, 50, 50), self.rect)  # Dark red
        
        # Border
        pygame.draw.rect(screen, Colors.STONE_HIGHLIGHT, self.rect, 2)
        
        # Text
        text_font = pygame.font.Font(None, 18)
        text_surface = text_font.render("Logout", True, Colors.TEXT_WHITE)
        text_x = self.x + (self.width - text_surface.get_width()) // 2
        text_y = self.y + (self.height - text_surface.get_height()) // 2
        screen.blit(text_surface, (text_x, text_y))
    
    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle events. Returns True if button was clicked."""
        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos) and event.button == 1:
                return True
        return False


class TabbedSidePanel:
    """
    OSRS-style tabbed side panel that combines inventory, equipment, stats, and settings.
    Positioned below the minimap on the right side.
    """
    
    TAB_HEIGHT = 32
    TAB_ICON_SIZE = 24
    PANEL_WIDTH = 204
    PANEL_HEIGHT = 280
    
    # Tab definitions: (name, icon_char, tooltip)
    TABS = [
        ("inventory", "I", "Inventory"),
        ("equipment", "E", "Equipment"),
        ("stats", "S", "Stats"),
        ("settings", "O", "Settings"),
    ]
    
    def __init__(
        self,
        x: int,
        y: int,
        on_inventory_click: Optional[Callable[[int, int], None]] = None,
        on_equipment_click: Optional[Callable[[str, int], None]] = None,
        on_logout: Optional[Callable[[], None]] = None
    ):
        self.x = x
        self.y = y
        self.width = self.PANEL_WIDTH
        self.height = self.TAB_HEIGHT + self.PANEL_HEIGHT
        
        self.active_tab = "inventory"
        self.hovered_tab: Optional[str] = None
        
        self.on_logout = on_logout
        
        # Create embedded panels (positioned relative to content area)
        content_y = y + self.TAB_HEIGHT
        
        # Inventory panel - 4x7 grid
        self.inventory_items: Dict[int, dict] = {}
        self.inventory_hovered_slot: Optional[int] = None
        self.inventory_selected_slot: Optional[int] = None
        self.on_inventory_click = on_inventory_click
        
        # Equipment panel
        self.equipment_items: Dict[str, dict] = {}
        self.equipment_hovered_slot: Optional[str] = None
        self.on_equipment_click = on_equipment_click
        
        # Stats data
        self.skills: Dict[str, dict] = {}
        
        # Settings - logout button hovered state
        self.logout_hovered = False
    
    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(self.x, self.y, self.width, self.height)
    
    def _get_tab_rect(self, index: int) -> pygame.Rect:
        """Get rectangle for a tab button."""
        tab_width = self.width // len(self.TABS)
        return pygame.Rect(
            self.x + index * tab_width,
            self.y,
            tab_width,
            self.TAB_HEIGHT
        )
    
    def _get_tab_at_pos(self, pos: Tuple[int, int]) -> Optional[str]:
        """Get tab name at mouse position."""
        for i, (name, _, _) in enumerate(self.TABS):
            if self._get_tab_rect(i).collidepoint(pos):
                return name
        return None
    
    def set_items(self, items: Dict[int, dict]) -> None:
        """Set inventory items."""
        self.inventory_items = items
    
    def set_equipment(self, equipment: Dict[str, dict]) -> None:
        """Set equipment data."""
        self.equipment_items = equipment
    
    def set_skills(self, skills: Dict[str, dict]) -> None:
        """Set skills data."""
        self.skills = skills
    
    def draw(self, screen: pygame.Surface, font: pygame.font.Font) -> None:
        """Draw the tabbed panel."""
        # Draw main panel background
        panel_rect = pygame.Rect(self.x, self.y + self.TAB_HEIGHT, self.width, self.PANEL_HEIGHT)
        pygame.draw.rect(screen, Colors.PANEL_BG, panel_rect)
        pygame.draw.rect(screen, Colors.PANEL_BORDER, panel_rect, 2)
        
        # Draw tabs
        tab_font = pygame.font.Font(None, 20)
        for i, (name, icon, tooltip) in enumerate(self.TABS):
            tab_rect = self._get_tab_rect(i)
            
            # Tab background
            if name == self.active_tab:
                pygame.draw.rect(screen, Colors.PANEL_BG, tab_rect)
                # Connect to panel below (no bottom border)
                pygame.draw.rect(screen, Colors.PANEL_BORDER, tab_rect, 2)
                pygame.draw.line(screen, Colors.PANEL_BG, 
                               (tab_rect.left + 2, tab_rect.bottom - 1),
                               (tab_rect.right - 3, tab_rect.bottom - 1), 2)
            elif name == self.hovered_tab:
                pygame.draw.rect(screen, Colors.STONE_LIGHT, tab_rect)
                pygame.draw.rect(screen, Colors.PANEL_BORDER, tab_rect, 2)
            else:
                pygame.draw.rect(screen, Colors.STONE_DARK, tab_rect)
                pygame.draw.rect(screen, Colors.PANEL_BORDER, tab_rect, 2)
            
            # Tab icon/text
            icon_surface = tab_font.render(icon, True, 
                Colors.TEXT_YELLOW if name == self.active_tab else Colors.TEXT_WHITE)
            icon_x = tab_rect.x + (tab_rect.width - icon_surface.get_width()) // 2
            icon_y = tab_rect.y + (tab_rect.height - icon_surface.get_height()) // 2
            screen.blit(icon_surface, (icon_x, icon_y))
        
        # Draw active tab content
        content_rect = pygame.Rect(self.x + 4, self.y + self.TAB_HEIGHT + 4, 
                                   self.width - 8, self.PANEL_HEIGHT - 8)
        
        if self.active_tab == "inventory":
            self._draw_inventory(screen, font, content_rect)
        elif self.active_tab == "equipment":
            self._draw_equipment(screen, font, content_rect)
        elif self.active_tab == "stats":
            self._draw_stats(screen, font, content_rect)
        elif self.active_tab == "settings":
            self._draw_settings(screen, font, content_rect)
    
    def _draw_inventory(self, screen: pygame.Surface, font: pygame.font.Font, content_rect: pygame.Rect) -> None:
        """Draw inventory grid."""
        slot_size = 32
        padding = 2
        cols = 4
        rows = 7
        
        # Center the grid
        grid_width = cols * (slot_size + padding) - padding
        grid_height = rows * (slot_size + padding) - padding
        start_x = content_rect.x + (content_rect.width - grid_width) // 2
        start_y = content_rect.y + 4
        
        small_font = pygame.font.Font(None, 16)
        
        for slot in range(28):
            col = slot % cols
            row = slot // cols
            
            x = start_x + col * (slot_size + padding)
            y = start_y + row * (slot_size + padding)
            rect = pygame.Rect(x, y, slot_size, slot_size)
            
            # Background
            if slot == self.inventory_selected_slot:
                pygame.draw.rect(screen, Colors.SLOT_SELECTED, rect)
            elif slot == self.inventory_hovered_slot:
                pygame.draw.rect(screen, Colors.SLOT_HOVER, rect)
            else:
                pygame.draw.rect(screen, Colors.SLOT_BG, rect)
            
            pygame.draw.rect(screen, Colors.SLOT_BORDER, rect, 1)
            
            # Draw item if present
            if slot in self.inventory_items:
                item = self.inventory_items[slot]
                item_name = item.get("name", "?")[:3]
                quantity = item.get("quantity", 1)
                
                # Item name abbreviation
                name_surface = small_font.render(item_name, True, Colors.TEXT_ORANGE)
                screen.blit(name_surface, (x + 2, y + 2))
                
                # Quantity
                if quantity > 1:
                    qty_surface = small_font.render(str(quantity), True, Colors.TEXT_YELLOW)
                    screen.blit(qty_surface, (x + 2, y + slot_size - 12))
    
    def _draw_equipment(self, screen: pygame.Surface, font: pygame.font.Font, content_rect: pygame.Rect) -> None:
        """Draw equipment slots."""
        slot_size = 34
        
        # OSRS-style equipment layout - centered
        center_x = content_rect.x + content_rect.width // 2
        
        slot_positions = {
            "head": (center_x - slot_size // 2, content_rect.y + 8),
            "cape": (center_x - slot_size - 20, content_rect.y + 50),
            "neck": (center_x - slot_size // 2, content_rect.y + 50),
            "ammunition": (center_x + 20, content_rect.y + 50),
            "weapon": (center_x - slot_size - 20, content_rect.y + 92),
            "body": (center_x - slot_size // 2, content_rect.y + 92),
            "shield": (center_x + 20, content_rect.y + 92),
            "hands": (center_x - slot_size - 20, content_rect.y + 134),
            "legs": (center_x - slot_size // 2, content_rect.y + 134),
            "ring": (center_x + 20, content_rect.y + 134),
            "feet": (center_x - slot_size // 2, content_rect.y + 176),
        }
        
        small_font = pygame.font.Font(None, 12)
        
        # Slot labels (single letter)
        slot_labels = {
            "head": "H", "cape": "C", "neck": "N", "ammunition": "A",
            "weapon": "W", "body": "B", "shield": "S",
            "hands": "H", "legs": "L", "ring": "R", "feet": "F"
        }
        
        for slot_name, (sx, sy) in slot_positions.items():
            rect = pygame.Rect(sx, sy, slot_size, slot_size)
            
            # Background
            if slot_name == self.equipment_hovered_slot:
                pygame.draw.rect(screen, Colors.SLOT_HOVER, rect)
            else:
                pygame.draw.rect(screen, Colors.SLOT_BG, rect)
            
            pygame.draw.rect(screen, Colors.SLOT_BORDER, rect, 1)
            
            # Draw item or slot label
            if slot_name in self.equipment_items and self.equipment_items[slot_name]:
                item = self.equipment_items[slot_name]
                item_name = item.get("name", "?")[:3]
                name_surface = small_font.render(item_name, True, Colors.TEXT_ORANGE)
                screen.blit(name_surface, (sx + 2, sy + 2))
            else:
                # Slot label
                label = slot_labels.get(slot_name, "?")
                label_surface = small_font.render(label, True, Colors.TEXT_GRAY)
                lx = sx + (slot_size - label_surface.get_width()) // 2
                ly = sy + (slot_size - label_surface.get_height()) // 2
                screen.blit(label_surface, (lx, ly))
    
    def _draw_stats(self, screen: pygame.Surface, font: pygame.font.Font, content_rect: pygame.Rect) -> None:
        """Draw skills/stats."""
        small_font = pygame.font.Font(None, 18)
        
        # Title
        title_surface = small_font.render("Skills", True, Colors.TEXT_YELLOW)
        screen.blit(title_surface, (content_rect.x + 4, content_rect.y + 4))
        
        y = content_rect.y + 24
        line_height = 18
        
        # Common skills to display
        skill_order = ["attack", "strength", "defence", "hitpoints", "ranged", "magic", 
                      "mining", "woodcutting", "fishing", "cooking", "crafting"]
        
        for skill_name in skill_order:
            if skill_name in self.skills:
                skill = self.skills[skill_name]
                level = skill.get("level", 1)
                xp = skill.get("xp", 0)
                
                # Skill name and level
                text = f"{skill_name.capitalize()}: {level}"
                text_surface = small_font.render(text, True, Colors.TEXT_WHITE)
                screen.blit(text_surface, (content_rect.x + 4, y))
                
                y += line_height
                
                if y > content_rect.y + content_rect.height - 20:
                    break
        
        if not self.skills:
            no_skills = small_font.render("No skills data", True, Colors.TEXT_GRAY)
            screen.blit(no_skills, (content_rect.x + 4, y))
    
    def _draw_settings(self, screen: pygame.Surface, font: pygame.font.Font, content_rect: pygame.Rect) -> None:
        """Draw settings panel with logout button."""
        small_font = pygame.font.Font(None, 20)
        
        # Title
        title_surface = small_font.render("Settings", True, Colors.TEXT_YELLOW)
        screen.blit(title_surface, (content_rect.x + 4, content_rect.y + 4))
        
        # Logout button
        logout_rect = pygame.Rect(
            content_rect.x + 20,
            content_rect.y + 40,
            content_rect.width - 40,
            30
        )
        
        if self.logout_hovered:
            pygame.draw.rect(screen, (120, 60, 60), logout_rect)
        else:
            pygame.draw.rect(screen, (100, 50, 50), logout_rect)
        pygame.draw.rect(screen, Colors.STONE_HIGHLIGHT, logout_rect, 2)
        
        logout_text = small_font.render("Logout", True, Colors.TEXT_WHITE)
        text_x = logout_rect.x + (logout_rect.width - logout_text.get_width()) // 2
        text_y = logout_rect.y + (logout_rect.height - logout_text.get_height()) // 2
        screen.blit(logout_text, (text_x, text_y))
        
        # Store logout rect for hit detection
        self._logout_rect = logout_rect
        
        # Other settings options could go here
        y = content_rect.y + 90
        
        # Placeholder settings
        settings_options = [
            "Audio: On",
            "Music: On",
            "Show FPS: Yes",
        ]
        
        tiny_font = pygame.font.Font(None, 18)
        for option in settings_options:
            text_surface = tiny_font.render(option, True, Colors.TEXT_GRAY)
            screen.blit(text_surface, (content_rect.x + 10, y))
            y += 20
    
    def handle_event(self, event: pygame.event.Event) -> Optional[str]:
        """
        Handle events. Returns action string if action taken:
        - "logout" if logout clicked
        - "tab_changed" if tab was changed
        - None otherwise
        """
        if event.type == pygame.MOUSEMOTION:
            pos = event.pos
            
            # Check tab hover
            self.hovered_tab = self._get_tab_at_pos(pos)
            
            # Check content area hover based on active tab
            content_rect = pygame.Rect(self.x + 4, self.y + self.TAB_HEIGHT + 4,
                                       self.width - 8, self.PANEL_HEIGHT - 8)
            
            if self.active_tab == "inventory":
                self.inventory_hovered_slot = self._get_inventory_slot_at_pos(pos, content_rect)
            elif self.active_tab == "equipment":
                self.equipment_hovered_slot = self._get_equipment_slot_at_pos(pos, content_rect)
            elif self.active_tab == "settings":
                if hasattr(self, '_logout_rect'):
                    self.logout_hovered = self._logout_rect.collidepoint(pos)
        
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos
            
            # Check if clicking on panel
            if not self.rect.collidepoint(pos):
                return None
            
            # Check tab click
            clicked_tab = self._get_tab_at_pos(pos)
            if clicked_tab and clicked_tab != self.active_tab:
                self.active_tab = clicked_tab
                return "tab_changed"
            
            # Check content area click based on active tab
            content_rect = pygame.Rect(self.x + 4, self.y + self.TAB_HEIGHT + 4,
                                       self.width - 8, self.PANEL_HEIGHT - 8)
            
            if self.active_tab == "inventory":
                slot = self._get_inventory_slot_at_pos(pos, content_rect)
                if slot is not None and self.on_inventory_click:
                    self.on_inventory_click(slot, event.button)
                    return "inventory_click"
            
            elif self.active_tab == "equipment":
                slot = self._get_equipment_slot_at_pos(pos, content_rect)
                if slot is not None and self.on_equipment_click:
                    self.on_equipment_click(slot, event.button)
                    return "equipment_click"
            
            elif self.active_tab == "settings":
                if hasattr(self, '_logout_rect') and self._logout_rect.collidepoint(pos):
                    if self.on_logout:
                        self.on_logout()
                    return "logout"
        
        return None
    
    def _get_inventory_slot_at_pos(self, pos: Tuple[int, int], content_rect: pygame.Rect) -> Optional[int]:
        """Get inventory slot at mouse position."""
        slot_size = 32
        padding = 2
        cols = 4
        
        grid_width = cols * (slot_size + padding) - padding
        start_x = content_rect.x + (content_rect.width - grid_width) // 2
        start_y = content_rect.y + 4
        
        for slot in range(28):
            col = slot % cols
            row = slot // cols
            
            x = start_x + col * (slot_size + padding)
            y = start_y + row * (slot_size + padding)
            rect = pygame.Rect(x, y, slot_size, slot_size)
            
            if rect.collidepoint(pos):
                return slot
        
        return None
    
    def _get_equipment_slot_at_pos(self, pos: Tuple[int, int], content_rect: pygame.Rect) -> Optional[str]:
        """Get equipment slot at mouse position."""
        slot_size = 34
        center_x = content_rect.x + content_rect.width // 2
        
        slot_positions = {
            "head": (center_x - slot_size // 2, content_rect.y + 8),
            "cape": (center_x - slot_size - 20, content_rect.y + 50),
            "neck": (center_x - slot_size // 2, content_rect.y + 50),
            "ammunition": (center_x + 20, content_rect.y + 50),
            "weapon": (center_x - slot_size - 20, content_rect.y + 92),
            "body": (center_x - slot_size // 2, content_rect.y + 92),
            "shield": (center_x + 20, content_rect.y + 92),
            "hands": (center_x - slot_size - 20, content_rect.y + 134),
            "legs": (center_x - slot_size // 2, content_rect.y + 134),
            "ring": (center_x + 20, content_rect.y + 134),
            "feet": (center_x - slot_size // 2, content_rect.y + 176),
        }
        
        for slot_name, (sx, sy) in slot_positions.items():
            rect = pygame.Rect(sx, sy, slot_size, slot_size)
            if rect.collidepoint(pos):
                return slot_name
        
        return None


# =============================================================================
# TOOLTIP
# =============================================================================

class Tooltip:
    """Item/skill tooltip."""
    
    PADDING = 6
    LINE_SPACING = 2
    
    def __init__(self):
        self.visible = False
        self.x = 0
        self.y = 0
        self.lines: List[Tuple[str, Tuple[int, int, int]]] = []
    
    def show(self, x: int, y: int, lines: List[Tuple[str, Tuple[int, int, int]]]) -> None:
        """Show tooltip at position with lines of (text, color)."""
        self.x = x
        self.y = y
        self.lines = lines
        self.visible = True
    
    def hide(self) -> None:
        """Hide the tooltip."""
        self.visible = False
        self.lines = []
    
    def draw(self, screen: pygame.Surface, font: pygame.font.Font) -> None:
        """Draw the tooltip."""
        if not self.visible or not self.lines:
            return
        
        # Calculate dimensions
        line_height = font.get_height() + self.LINE_SPACING
        max_width = max(font.size(line[0])[0] for line in self.lines)
        width = max_width + self.PADDING * 2
        height = len(self.lines) * line_height + self.PADDING * 2
        
        # Adjust position to stay on screen
        screen_rect = screen.get_rect()
        x = min(self.x, screen_rect.width - width - 5)
        y = min(self.y, screen_rect.height - height - 5)
        
        # Background
        pygame.draw.rect(screen, Colors.PANEL_BG, (x, y, width, height))
        pygame.draw.rect(screen, Colors.PANEL_BORDER, (x, y, width, height), 1)
        
        # Lines
        current_y = y + self.PADDING
        for text, color in self.lines:
            text_surface = font.render(text, True, color)
            screen.blit(text_surface, (x + self.PADDING, current_y))
            current_y += line_height
