"""
OSRS-Style UI Panels - Tabbed side panel, chat window, minimap, etc.

Ported from legacy_ui_panels.py with modern architecture.
"""

import pygame
from typing import Dict, List, Tuple, Optional, Callable, Any
import time
from dataclasses import dataclass

from ..ui.colors import Colors
from .icon_manager import get_icon_manager


# =============================================================================
# BASE PANEL CLASS
# =============================================================================

class UIPanel:
    """Base class for UI panels with 3D stone border styling."""
    
    def __init__(self, x: int, y: int, width: int, height: int, title: str = "", visible: bool = True):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.title = title
        self.visible = visible
        
        # Pre-rendered background
        self._bg_surface = None
        self._bg_dirty = True
        
        # Fonts
        try:
            self.font = pygame.font.Font("client/assets/fonts/RetroRPG.ttf", 24)
            self.small_font = pygame.font.Font("client/assets/fonts/RetroRPG.ttf", 18)
            self.tiny_font = pygame.font.Font("client/assets/fonts/RetroRPG.ttf", 14)
        except:
            self.font = pygame.font.Font(None, 24)
            self.small_font = pygame.font.Font(None, 18)
            self.tiny_font = pygame.font.Font(None, 14)
    
    @property
    def rect(self) -> pygame.Rect:
        """Get panel rectangle."""
        return pygame.Rect(self.x, self.y, self.width, self.height)
    
    def _render_background(self) -> pygame.Surface:
        """Render 3D stone-themed background."""
        surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        
        # Main fill
        surface.fill(Colors.PANEL_BG)
        
        # Outer border (2px dark)
        pygame.draw.rect(surface, Colors.PANEL_BORDER, (0, 0, self.width, self.height), 2)
        
        # Inner border (1px light)
        pygame.draw.rect(surface, Colors.PANEL_INNER_BORDER, (2, 2, self.width-4, self.height-4), 1)
        
        # Top/left highlight
        pygame.draw.line(surface, Colors.STONE_HIGHLIGHT, (3, 3), (self.width-3, 3), 1)
        pygame.draw.line(surface, Colors.STONE_HIGHLIGHT, (3, 3), (3, self.height-3), 1)
        
        # Bottom/right shadow
        pygame.draw.line(surface, Colors.PANEL_BORDER, (3, self.height-3), (self.width-3, self.height-3), 1)
        pygame.draw.line(surface, Colors.PANEL_BORDER, (self.width-3, 3), (self.width-3, self.height-3), 1)
        
        return surface
    
    def draw(self, screen: pygame.Surface) -> None:
        """Draw the panel."""
        if not self.visible:
            return
        
        if self._bg_dirty:
            self._bg_surface = self._render_background()
            self._bg_dirty = False
        
        # Blit background
        screen.blit(self._bg_surface, (self.x, self.y))
        
        # Draw title
        if self.title:
            title_surface = self.font.render(self.title, True, Colors.TEXT_ORANGE)
            screen.blit(title_surface, (self.x + self.width//2 - title_surface.get_width()//2, self.y + 5))
    
    def handle_event(self, event: pygame.event.Event) -> Optional[str]:
        """Handle input events. Override in subclasses."""
        return None


# =============================================================================
# TABBED SIDE PANEL
# =============================================================================

class TabbedSidePanel(UIPanel):
    """Main tabbed panel with Inventory, Equipment, Stats, Settings tabs."""

    TAB_HEIGHT = 32
    PANEL_WIDTH = 200
    PANEL_HEIGHT = 280

    def __init__(self, x: int, y: int, on_logout: Optional[Callable[[], None]] = None):
        super().__init__(
            x, y,
            self.PANEL_WIDTH,
            self.TAB_HEIGHT + self.PANEL_HEIGHT,
            ""
        )

        self.tabs = [
            ("inventory", "I", "Inventory"),
            ("equipment", "E", "Equipment"),
            ("stats", "S", "Stats"),
            ("settings", "O", "Settings"),
        ]

        self.active_tab = "inventory"
        self.hovered_tab = -1

        # Inventory state
        self.inventory_items: Dict[int, Dict[str, Any]] = {}
        self.inventory_hovered_slot = -1
        self.inventory_selected_slot = -1
        self.on_inventory_click: Optional[Callable[[int, int], None]] = None
        self.inventory_sort_criteria = "category"
        self.on_inventory_sort: Optional[Callable[[str], None]] = None
        self._sort_button_rects: Dict[str, pygame.Rect] = {}

        # Equipment state
        self.equipment_items: Dict[str, Dict[str, Any]] = {}

        # Stats
        self.skills: Dict[str, Dict[str, Any]] = {}
        self.total_level = 0

        # Settings - logout button
        self.on_logout = on_logout
        self.logout_hovered = False
        self._logout_rect: Optional[pygame.Rect] = None

        # Fonts
        try:
            self.tab_font = pygame.font.Font("client/assets/fonts/RetroRPG.ttf", 18)
        except:
            self.tab_font = pygame.font.Font(None, 18)
    
    def _get_tab_rect(self, tab_idx: int) -> pygame.Rect:
        """Get rect for a tab."""
        tab_width = self.PANEL_WIDTH // 4
        return pygame.Rect(self.x + tab_idx * tab_width, self.y, tab_width, self.TAB_HEIGHT)
    
    def _get_content_rect(self) -> pygame.Rect:
        """Get rect for content area below tabs."""
        return pygame.Rect(
            self.x,
            self.y + self.TAB_HEIGHT,
            self.PANEL_WIDTH,
            self.PANEL_HEIGHT
        )
    
    def draw(self, screen: pygame.Surface) -> None:
        """Draw the tabbed panel."""
        if not self.visible:
            return
        
        content_rect = self._get_content_rect()
        
        # Draw panel background (below tabs)
        pygame.draw.rect(screen, Colors.PANEL_BG, content_rect)
        pygame.draw.rect(screen, Colors.PANEL_BORDER, content_rect, 2)
        
        # Draw tabs
        for tab_idx, (tab_key, icon, label) in enumerate(self.tabs):
            tab_rect = self._get_tab_rect(tab_idx)
            
            # Background
            if tab_key == self.active_tab:
                bg_color = Colors.PANEL_BG
                # Draw connection to panel (hide bottom border)
                pygame.draw.line(screen, Colors.PANEL_BG, tab_rect.bottomleft, tab_rect.bottomright, 2)
            elif tab_idx == self.hovered_tab:
                bg_color = Colors.STONE_LIGHT
            else:
                bg_color = Colors.STONE_DARK
            
            pygame.draw.rect(screen, bg_color, tab_rect)
            pygame.draw.rect(screen, Colors.PANEL_BORDER, tab_rect, 1)
            
            # Icon
            icon_color = Colors.TEXT_YELLOW if tab_key == self.active_tab else Colors.TEXT_WHITE
            icon_text = self.tab_font.render(icon, True, icon_color)
            screen.blit(icon_text, (
                tab_rect.centerx - icon_text.get_width() // 2,
                tab_rect.centery - icon_text.get_height() // 2
            ))
        
        # Draw active tab content
        if self.active_tab == "inventory":
            self._draw_inventory_content(screen, content_rect)
        elif self.active_tab == "equipment":
            self._draw_equipment_content(screen, content_rect)
        elif self.active_tab == "stats":
            self._draw_stats_content(screen, content_rect)
        elif self.active_tab == "settings":
            self._draw_settings_content(screen, content_rect)
    
    def _draw_inventory_content(self, screen: pygame.Surface, content_rect: pygame.Rect) -> None:
        """Draw inventory grid with sort buttons."""
        # Sort buttons at top
        btn_height = 18
        btn_width = 45
        btn_gap = 4
        sort_y = content_rect.y + 6
        sort_start_x = content_rect.x + (content_rect.width - (4 * btn_width + 3 * btn_gap)) // 2
        
        sort_buttons = [
            ("Cat", "category"),
            ("Rar", "rarity"),
            ("Val", "value"),
            ("A-Z", "name")
        ]
        
        for i, (label, criteria) in enumerate(sort_buttons):
            btn_x = sort_start_x + i * (btn_width + btn_gap)
            btn_rect = pygame.Rect(btn_x, sort_y, btn_width, btn_height)
            
            # Check if this is the active sort
            is_active = getattr(self, 'inventory_sort_criteria', 'category') == criteria
            
            # Button background
            if is_active:
                pygame.draw.rect(screen, (100, 100, 140), btn_rect)  # Highlighted
                pygame.draw.rect(screen, (140, 140, 180), btn_rect, 2)  # Bright border
            else:
                pygame.draw.rect(screen, (60, 60, 80), btn_rect)  # Normal
                pygame.draw.rect(screen, Colors.SLOT_BORDER, btn_rect, 1)  # Normal border
            
            # Button text
            text = self.tiny_font.render(label, True, Colors.TEXT_WHITE)
            text_x = btn_rect.x + (btn_width - text.get_width()) // 2
            text_y = btn_rect.y + (btn_height - text.get_height()) // 2
            screen.blit(text, (text_x, text_y))
            
            # Store rect for click detection
            if not hasattr(self, '_sort_button_rects'):
                self._sort_button_rects = {}
            self._sort_button_rects[criteria] = btn_rect
        
        # Inventory grid below buttons
        slot_size = 32
        cols = 4
        rows = 7
        grid_width = cols * (slot_size + 2) - 2
        start_x = content_rect.x + (content_rect.width - grid_width) // 2
        start_y = content_rect.y + 8 + btn_height + 6  # Shift down for buttons
        
        for slot in range(cols * rows):
            col = slot % cols
            row = slot // cols
            slot_rect = pygame.Rect(start_x + col * (slot_size + 2), start_y + row * (slot_size + 2), slot_size, slot_size)
            
            # Background
            if slot == self.inventory_selected_slot:
                bg = Colors.SLOT_SELECTED
            elif slot == self.inventory_hovered_slot:
                bg = Colors.SLOT_HOVER
            else:
                bg = Colors.SLOT_BG
            
            pygame.draw.rect(screen, bg, slot_rect)
            pygame.draw.rect(screen, Colors.SLOT_BORDER, slot_rect, 1)
            
            # Item
            if slot in self.inventory_items:
                item = self.inventory_items[slot]
                icon_sprite_id = item.get("icon_sprite_id")
                icon_manager = get_icon_manager()
                
                # Try to render icon if available
                icon_surface = None
                if icon_manager and icon_sprite_id:
                    icon_surface = icon_manager.get_icon_surface_sync(icon_sprite_id)
                    if icon_surface is None:
                        # Not cached - schedule background download
                        icon_manager.schedule_download(icon_sprite_id)
                
                if icon_surface:
                    # Scale icon to fit slot (32x32 icons should fit perfectly)
                    icon_rect = icon_surface.get_rect(center=slot_rect.center)
                    screen.blit(icon_surface, icon_rect)
                else:
                    # Fallback: show rarity-colored background with name abbreviation
                    pygame.draw.rect(screen, Colors.RARITY_UNCOMMON, slot_rect.inflate(-4, -4))
                    name = item.get("name", "?")[:2]
                    text = self.tiny_font.render(name, True, Colors.TEXT_ORANGE)
                    screen.blit(text, (slot_rect.x + 4, slot_rect.y + 4))
                
                # Draw quantity if stackable
                quantity = item.get("quantity", 1)
                if quantity > 1:
                    qty_text = self.tiny_font.render(str(quantity), True, Colors.TEXT_WHITE)
                    screen.blit(qty_text, (slot_rect.x + 2, slot_rect.y + slot_size - 12))
    
    def _draw_equipment_content(self, screen: pygame.Surface, content_rect: pygame.Rect) -> None:
        """Draw equipment paperdoll-style layout."""
        center_x = content_rect.centerx
        content_y = content_rect.y + 8
        slot_size = 34
        
        # All 11 equipment slots in paperdoll layout
        # Proper 3-column centered layout with 4px gaps between columns
        # Left: center_x - 55, Middle: center_x - 17, Right: center_x + 21
        col_left = center_x - 55
        col_mid = center_x - 17
        col_right = center_x + 21
        row_step = 38  # slot_size + 4px gap

        slots = [
            ("head", col_mid, content_y),
            ("cape", col_left, content_y + row_step),
            ("neck", col_mid, content_y + row_step),
            ("ammunition", col_right, content_y + row_step),
            ("weapon", col_left, content_y + 2 * row_step),
            ("body", col_mid, content_y + 2 * row_step),
            ("shield", col_right, content_y + 2 * row_step),
            ("hands", col_left, content_y + 3 * row_step),
            ("legs", col_mid, content_y + 3 * row_step),
            ("ring", col_right, content_y + 3 * row_step),
            ("boots", col_mid, content_y + 4 * row_step),
        ]
        
        # Slot abbreviations for display
        slot_abbreviations = {
            "head": "H", "cape": "C", "neck": "N", "ammunition": "A",
            "weapon": "W", "body": "B", "shield": "S", "hands": "Ha",
            "legs": "L", "ring": "R", "boots": "Bo"
        }
        
        for slot_name, sx, sy in slots:
            slot_rect = pygame.Rect(sx, sy, slot_size, slot_size)
            
            # Check if something is equipped in this slot
            equipped_item = self.equipment_items.get(slot_name)
            
            if equipped_item:
                icon_sprite_id = equipped_item.get("icon_sprite_id")
                icon_manager = get_icon_manager()
                
                # Try to render icon if available
                icon_surface = None
                if icon_manager and icon_sprite_id:
                    icon_surface = icon_manager.get_icon_surface_sync(icon_sprite_id)
                    if icon_surface is None:
                        # Not cached - schedule background download
                        icon_manager.schedule_download(icon_sprite_id)
                
                if icon_surface:
                    # Draw icon centered in slot
                    icon_rect = icon_surface.get_rect(center=slot_rect.center)
                    screen.blit(icon_surface, icon_rect)
                    # Add border around icon
                    pygame.draw.rect(screen, Colors.PANEL_BORDER, slot_rect, 1)
                else:
                    # Fallback: show rarity-colored background with name abbreviation
                    pygame.draw.rect(screen, Colors.RARITY_UNCOMMON, slot_rect)
                    pygame.draw.rect(screen, Colors.PANEL_BORDER, slot_rect, 1)
                    
                    item_name = equipped_item.get("name", "?")[:3]
                    text = self.tiny_font.render(item_name, True, Colors.TEXT_ORANGE)
                    text_x = slot_rect.x + (slot_size - text.get_width()) // 2
                    text_y = slot_rect.y + (slot_size - text.get_height()) // 2
                    screen.blit(text, (text_x, text_y))
            else:
                # Draw empty slot
                pygame.draw.rect(screen, Colors.SLOT_BG, slot_rect)
                pygame.draw.rect(screen, Colors.SLOT_BORDER, slot_rect, 1)
                
                # Slot abbreviation label
                label = slot_abbreviations.get(slot_name, slot_name[0].upper())
                label_text = self.tiny_font.render(label, True, Colors.TEXT_GRAY)
                text_x = slot_rect.x + (slot_size - label_text.get_width()) // 2
                text_y = slot_rect.y + (slot_size - label_text.get_height()) // 2
                screen.blit(label_text, (text_x, text_y))
    
    def _draw_stats_content(self, screen: pygame.Surface, content_rect: pygame.Rect) -> None:
        """Draw skills list with progress bars."""
        # Title with total level
        title_text = f"Skills (Total: {self.total_level})"
        title = self.small_font.render(title_text, True, Colors.TEXT_YELLOW)
        screen.blit(title, (content_rect.x + 8, content_rect.y + 6))
        
        # Skill categories with colors
        category_colors = {
            "combat": (255, 100, 100),      # Red
            "gathering": (100, 255, 100),   # Green
            "crafting": (100, 200, 255),    # Blue
            "other": (200, 200, 200)        # Gray
        }
        
        y = content_rect.y + 32
        skill_height = 22
        max_display = 10
        
        # Sort skills by category then by level
        sorted_skills = sorted(
            self.skills.items(),
            key=lambda x: (x[1].get("category", "other"), -x[1].get("level", 1))
        )[:max_display]
        
        for skill_name, skill_data in sorted_skills:
            level = skill_data.get("level", 1)
            xp = skill_data.get("xp", 0)
            xp_to_next = skill_data.get("xp_to_next", 0)
            category = skill_data.get("category", "other")
            
            # Skill name and level
            name_text = self.tiny_font.render(f"{skill_name.title()}", True, Colors.TEXT_WHITE)
            screen.blit(name_text, (content_rect.x + 8, y))
            
            # Level number on the right
            level_text = self.tiny_font.render(str(level), True, Colors.TEXT_YELLOW)
            level_x = content_rect.right - level_text.get_width() - 8
            screen.blit(level_text, (level_x, y))
            
            # XP progress bar (thin, 3px height)
            if xp_to_next > 0:
                bar_width = content_rect.width - 16
                bar_x = content_rect.x + 8
                bar_y = y + 14
                
                # Calculate progress
                progress = min(1.0, xp / xp_to_next) if xp_to_next > 0 else 0
                fill_width = int(bar_width * progress)
                
                # Background (dark)
                pygame.draw.rect(screen, (40, 40, 40), (bar_x, bar_y, bar_width, 3))
                
                # Fill (category color or green)
                cat_color = category_colors.get(category, (100, 255, 100))
                if fill_width > 0:
                    pygame.draw.rect(screen, cat_color, (bar_x, bar_y, fill_width, 3))
            
            y += skill_height
    
    def _draw_settings_content(self, screen: pygame.Surface, content_rect: pygame.Rect) -> None:
        """Draw settings."""
        title = self.small_font.render("Settings", True, Colors.TEXT_YELLOW)
        screen.blit(title, (content_rect.x + 8, content_rect.y + 8))

        # Logout button
        btn_rect = pygame.Rect(content_rect.x + 20, content_rect.y + 40, content_rect.width - 40, 30)

        # Highlight if hovered - bright red for visibility
        if self.logout_hovered:
            pygame.draw.rect(screen, (180, 80, 80), btn_rect)  # Much brighter red
            pygame.draw.rect(screen, (220, 120, 120), btn_rect, 3)  # Bright border
        else:
            pygame.draw.rect(screen, (100, 50, 50), btn_rect)
            pygame.draw.rect(screen, Colors.STONE_HIGHLIGHT, btn_rect, 2)

        btn_text = self.font.render("Logout", True, Colors.TEXT_WHITE)
        screen.blit(btn_text, (
            btn_rect.centerx - btn_text.get_width() // 2,
            btn_rect.centery - btn_text.get_height() // 2
        ))

        # Store rect for click detection
        self._logout_rect = btn_rect
    
    def handle_event(self, event: pygame.event.Event) -> Optional[str]:
        """Handle events."""
        if event.type == pygame.MOUSEMOTION:
            pos = event.pos

            # Update tab hover
            self.hovered_tab = -1
            for i, _ in enumerate(self.tabs):
                if self._get_tab_rect(i).collidepoint(pos):
                    self.hovered_tab = i
                    break
            
            # Check logout hover (independent of tab hover)
            if self.active_tab == "settings" and self._logout_rect:
                self.logout_hovered = self._logout_rect.collidepoint(pos)
            else:
                self.logout_hovered = False

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos

            # Check if clicking on panel
            if not self.rect.collidepoint(pos):
                return None

            # Check tab clicks
            for i, (tab_key, _, _) in enumerate(self.tabs):
                if self._get_tab_rect(i).collidepoint(pos):
                    self.active_tab = tab_key
                    return "tab_changed"

            # Check inventory sort button clicks (only in inventory tab)
            if self.active_tab == "inventory":
                for criteria, btn_rect in self._sort_button_rects.items():
                    if btn_rect.collidepoint(pos):
                        self.inventory_sort_criteria = criteria
                        if self.on_inventory_sort:
                            self.on_inventory_sort(criteria)
                        return "inventory_sort"

            # Check logout button click (only in settings tab)
            if self.active_tab == "settings" and self._logout_rect:
                if self._logout_rect.collidepoint(pos):
                    if self.on_logout:
                        self.on_logout()
                    return "logout"

        return None


# =============================================================================
# CHAT WINDOW
# =============================================================================

class ChatWindow(UIPanel):
    """Chat with channel tabs (Local, Global, DM)."""
    
    TAB_HEIGHT = 24
    
    def __init__(self, x: int, y: int, width: int = 400, height: int = 150):
        super().__init__(x, y, width, height, "")
        
        self.channels = {
            "local": {"messages": [], "color": Colors.TEXT_GREEN},
            "global": {"messages": [], "color": Colors.TEXT_CYAN},
            "dm": {"messages": [], "color": Colors.TEXT_PURPLE},
        }
        self.active_channel = "local"
        
        self.input_text = ""
        self.pending_message = None  # Message pending to be sent (Fix A)
        self.input_focused = False
        self.input_cursor_pos = 0
        self._last_blink_update = time.time()
        self.username = ""  # For display in input box (Fix B)

        # Scroll support (Fix 4, 5)
        self.scroll_offset = 0  # 0 = at bottom (viewing newest)
        self._line_height = 16
        self._msg_area_top = self.y + self.TAB_HEIGHT + 4
        self._msg_area_height = self.height - self.TAB_HEIGHT - 24 - 4  # minus tabs, input, padding
        self._max_visible_lines = self._msg_area_height // self._line_height

        # Cached background surfaces - tabs more opaque than message body (Fix 2)
        # Tab background (nearly opaque, readable)
        self._tab_bg_surface = pygame.Surface((self.width, self.TAB_HEIGHT), pygame.SRCALPHA)
        self._tab_bg_surface.fill((*Colors.PANEL_BG, 200))
        # Message body background (more translucent)
        self._msg_bg_surface = pygame.Surface((self.width, self._msg_area_height + 4), pygame.SRCALPHA)
        self._msg_bg_surface.fill((*Colors.PANEL_BG, 100))
        # Input area background (opaque like tabs, covers full width)
        self._input_bg_surface = pygame.Surface((self.width, 24), pygame.SRCALPHA)
        self._input_bg_surface.fill((*Colors.PANEL_BG, 200))
    
    def _wrap_text(self, text: str, max_width: int) -> list[str]:
        """Wrap text to fit within max_width pixels."""
        words = text.split()
        lines = []
        current_line = []
        current_width = 0

        for word in words:
            word_surface = self.tiny_font.render(word, True, (255, 255, 255))
            word_width = word_surface.get_width()
            space_width = self.tiny_font.size(" ")[0]

            if current_width + word_width + (len(current_line) * space_width) <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(" ".join(current_line))
                # If single word is too long, break it
                if word_width > max_width:
                    partial = ""
                    for char in word:
                        test = partial + char
                        if self.tiny_font.size(test)[0] <= max_width:
                            partial = test
                        else:
                            if partial:
                                lines.append(partial)
                            partial = char
                    if partial:
                        current_line = [partial]
                        current_width = self.tiny_font.size(partial)[0]
                else:
                    current_line = [word]
                    current_width = word_width

        if current_line:
            lines.append(" ".join(current_line))

        return lines

    def draw(self, screen: pygame.Surface) -> None:
        """Draw chat window with word wrap, scroll, and scrollbar."""
        if not self.visible:
            return

        # Tab background (more opaque)
        screen.blit(self._tab_bg_surface, (self.x, self.y))

        # Message body background (more translucent)
        msg_bg_y = self.y + self.TAB_HEIGHT
        screen.blit(self._msg_bg_surface, (self.x, msg_bg_y))

        # Border around entire window
        pygame.draw.rect(screen, Colors.PANEL_BORDER, (self.x, self.y, self.width, self.height), 2)

        # Tabs
        tab_width = self.width // 3
        for tab_idx, (ch_name, ch_data) in enumerate(self.channels.items()):
            tab_rect = pygame.Rect(self.x + tab_idx * tab_width, self.y, tab_width, self.TAB_HEIGHT)

            if ch_name == self.active_channel:
                pygame.draw.rect(screen, Colors.STONE_MEDIUM, tab_rect)
            else:
                pygame.draw.rect(screen, Colors.STONE_DARK, tab_rect)

            pygame.draw.rect(screen, Colors.PANEL_BORDER, tab_rect, 1)

            tab_text = self.tiny_font.render(ch_name.title(), True, ch_data["color"])
            screen.blit(tab_text, (
                tab_rect.centerx - tab_text.get_width() // 2,
                tab_rect.centery - tab_text.get_height() // 2
            ))

        # Messages area with word wrap and scroll
        max_text_width = self.width - 16  # 8px padding each side
        scrollbar_visible = False
        all_lines = []

        for msg_data in self.channels[self.active_channel]["messages"]:
            username = msg_data.get('username', '?')
            text = msg_data.get('text', '')
            full_text = f"{username}: {text}"
            wrapped = self._wrap_text(full_text, max_text_width)
            color = self.channels[self.active_channel]["color"]
            for line in wrapped:
                all_lines.append((line, color))

        total_lines = len(all_lines)
        if total_lines > self._max_visible_lines:
            scrollbar_visible = True
            max_text_width -= 12  # Make room for scrollbar
            # Re-wrap with reduced width
            all_lines = []
            for msg_data in self.channels[self.active_channel]["messages"]:
                username = msg_data.get('username', '?')
                text = msg_data.get('text', '')
                full_text = f"{username}: {text}"
                wrapped = self._wrap_text(full_text, max_text_width)
                color = self.channels[self.active_channel]["color"]
                for line in wrapped:
                    all_lines.append((line, color))
            total_lines = len(all_lines)

        # Calculate visible range based on scroll offset
        # scroll_offset 0 = view from bottom (newest messages)
        if total_lines <= self._max_visible_lines:
            # All messages fit, show them all
            visible_lines = all_lines
            self.scroll_offset = 0
        else:
            # Need to scroll
            max_scroll = total_lines - self._max_visible_lines
            self.scroll_offset = min(self.scroll_offset, max_scroll)
            end_idx = total_lines - self.scroll_offset
            start_idx = max(0, end_idx - self._max_visible_lines)
            visible_lines = all_lines[start_idx:end_idx]

        # Render visible messages
        msg_y = self.y + self.TAB_HEIGHT + 4
        for line_text, color in visible_lines:
            msg_surface = self.tiny_font.render(line_text, True, color)
            screen.blit(msg_surface, (self.x + 6, msg_y))
            msg_y += self._line_height

        # Scrollbar (if content overflows)
        if scrollbar_visible and total_lines > 0:
            scrollbar_width = 6
            track_x = self.x + self.width - 10
            track_y = self.y + self.TAB_HEIGHT + 2
            track_height = self._msg_area_height

            # Track background (brighter for visibility)
            pygame.draw.rect(screen, Colors.STONE_DARK, (track_x, track_y, scrollbar_width, track_height))

            # Thumb - proportional size and position
            thumb_height = max(12, int((self._max_visible_lines / total_lines) * track_height))
            max_scroll = total_lines - self._max_visible_lines
            # scroll_offset 0 = thumb at bottom
            if max_scroll > 0:
                scroll_ratio = self.scroll_offset / max_scroll
                thumb_y = track_y + int((1.0 - scroll_ratio) * (track_height - thumb_height))
            else:
                thumb_y = track_y + track_height - thumb_height

            pygame.draw.rect(screen, Colors.STONE_LIGHT, (track_x, thumb_y, scrollbar_width, thumb_height))

        # Input area background (full width)
        input_y = self.y + self.height - 24
        screen.blit(self._input_bg_surface, (self.x, input_y))
        
        # Input field
        pygame.draw.rect(screen, Colors.SLOT_BG, (self.x + 4, input_y, self.width - 8, 20))
        border_color = Colors.TEXT_WHITE if self.input_focused else Colors.SLOT_BORDER
        pygame.draw.rect(screen, border_color, (self.x + 4, input_y, self.width - 8, 20), 1)

        # Input text with username prefix (Fix B)
        prefix = f"{self.username}: " if self.username else ""
        prefix_surface = self.tiny_font.render(prefix, True, self.channels[self.active_channel]["color"])
        screen.blit(prefix_surface, (self.x + 6, input_y + 2))

        input_text_surface = self.tiny_font.render(self.input_text, True, Colors.TEXT_WHITE)
        screen.blit(input_text_surface, (self.x + 6 + prefix_surface.get_width(), input_y + 2))

        # Cursor (time-based blink instead of frame-based for M5 fix)
        elapsed = time.time() - self._last_blink_update
        if self.input_focused and int(elapsed * 2) % 2 == 0:
            cursor_x = self.x + 6 + prefix_surface.get_width() + input_text_surface.get_width()
            pygame.draw.line(screen, Colors.TEXT_WHITE, (cursor_x, input_y + 2), (cursor_x, input_y + 18))
    
    def add_message(self, channel: str, username: str, text: str) -> None:
        """Add a message to a channel."""
        if channel in self.channels:
            self.channels[channel]["messages"].append({
                "username": username,
                "text": text,
            })
            # Keep last 100 messages
            if len(self.channels[channel]["messages"]) > 100:
                self.channels[channel]["messages"].pop(0)
    
    def handle_event(self, event: pygame.event.Event) -> Optional[str]:
        """Handle chat input."""
        if event.type == pygame.MOUSEBUTTONDOWN:
            # Check tab clicks
            tab_width = self.width // 3
            for tab_idx, ch_name in enumerate(self.channels.keys()):
                tab_rect = pygame.Rect(self.x + tab_idx * tab_width, self.y, tab_width, self.TAB_HEIGHT)
                if tab_rect.collidepoint(event.pos):
                    self.active_channel = ch_name
                    return None
            
            # Check input focus
            input_y = self.y + self.height - 24
            input_rect = pygame.Rect(self.x + 4, input_y, self.width - 8, 20)
            self.input_focused = input_rect.collidepoint(event.pos)
        
        elif event.type == pygame.KEYDOWN and self.input_focused:
            if event.key == pygame.K_RETURN:
                if self.input_text.strip():
                    # Send message - store in pending_message before clearing (Fix A)
                    self.pending_message = self.input_text
                    # Only add to chat log if it's NOT a command (commands handled separately)
                    if not self.input_text.startswith("/"):
                        self.add_message(self.active_channel, "You", self.input_text)
                    self.scroll_offset = 0  # Scroll to bottom when sending
                    self.input_text = ""
                    self.input_cursor_pos = 0
                    return "chat_send"
            # ESC handling removed - parent (client.py) now handles defocusing (Fix 1)
            elif event.key == pygame.K_BACKSPACE:
                self.input_text = self.input_text[:-1]
            elif event.unicode.isprintable():
                self.input_text += event.unicode

        # Page Up / Page Down for scrolling (always active when chat visible, Fix 6)
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_PAGEUP:
                # Scroll up one page
                self.scroll_offset += self._max_visible_lines
                return None
            elif event.key == pygame.K_PAGEDOWN:
                # Scroll down one page
                self.scroll_offset = max(0, self.scroll_offset - self._max_visible_lines)
                return None

        # Mouse wheel scrolling (Fix 5)
        elif event.type == pygame.MOUSEWHEEL:
            # Check if mouse is within chat window
            mouse_pos = pygame.mouse.get_pos()
            chat_rect = pygame.Rect(self.x, self.y, self.width, self.height)
            if chat_rect.collidepoint(mouse_pos):
                if event.y > 0:  # Scroll up (away from user)
                    self.scroll_offset += 3
                elif event.y < 0:  # Scroll down (toward user)
                    self.scroll_offset = max(0, self.scroll_offset - 3)
                return None

        return None


# =============================================================================
# CONTEXT MENU
# =============================================================================

@dataclass
class ContextMenuItem:
    """A single item in a context menu."""
    label: str
    action: str
    color: Tuple[int, int, int] = Colors.TEXT_WHITE
    data: Any = None


class ContextMenu:
    """
    Right-click context menu system.
    
    Used for inventory items, equipment slots, entities, and ground items.
    """
    
    ITEM_HEIGHT = 20
    PADDING = 4
    WIDTH = 150
    
    def __init__(self):
        self.visible = False
        self.x = 0
        self.y = 0
        self.items: List[ContextMenuItem] = []
        self.hovered_index = -1
        self.on_select: Optional[Callable[[ContextMenuItem], None]] = None
        
        # Cached font for performance
        self._font = pygame.font.SysFont("sans-serif", 12)
    
    def show(self, x: int, y: int, items: List[ContextMenuItem], on_select: Optional[Callable[[ContextMenuItem], None]] = None) -> None:
        """Show the context menu at the specified position."""
        self.x = x
        self.y = y
        self.items = items
        self.hovered_index = -1
        self.on_select = on_select
        self.visible = True
    
    def hide(self) -> None:
        """Hide the context menu."""
        self.visible = False
        self.items = []
        self.hovered_index = -1
    
    def draw(self, screen: pygame.Surface) -> None:
        """Draw the context menu."""
        if not self.visible:
            return
        
        # Calculate height based on items
        height = len(self.items) * self.ITEM_HEIGHT + self.PADDING * 2
        
        # Draw background
        menu_rect = pygame.Rect(self.x, self.y, self.WIDTH, height)
        pygame.draw.rect(screen, Colors.PANEL_BG, menu_rect)
        pygame.draw.rect(screen, Colors.PANEL_BORDER, menu_rect, 2)
        
        # Draw items
        for i, item in enumerate(self.items):
            item_y = self.y + self.PADDING + i * self.ITEM_HEIGHT
            item_rect = pygame.Rect(self.x, item_y, self.WIDTH, self.ITEM_HEIGHT)
            
            # Highlight if hovered
            if i == self.hovered_index:
                pygame.draw.rect(screen, Colors.SLOT_HOVER, item_rect)
            
            # Draw text
            text_surface = self._font.render(item.label, True, item.color)
            screen.blit(text_surface, (self.x + self.PADDING, item_y + 3))
    
    def handle_event(self, event: pygame.event.Event) -> Optional[str]:
        """Handle mouse events for the context menu."""
        if not self.visible:
            return None
        
        if event.type == pygame.MOUSEMOTION:
            # Update hover
            height = len(self.items) * self.ITEM_HEIGHT + self.PADDING * 2
            menu_rect = pygame.Rect(self.x, self.y, self.WIDTH, height)
            
            if menu_rect.collidepoint(event.pos):
                relative_y = event.pos[1] - self.y - self.PADDING
                if relative_y >= 0:
                    self.hovered_index = relative_y // self.ITEM_HEIGHT
                    self.hovered_index = max(0, min(self.hovered_index, len(self.items) - 1))
            else:
                self.hovered_index = -1
        
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:  # Left click
                height = len(self.items) * self.ITEM_HEIGHT + self.PADDING * 2
                menu_rect = pygame.Rect(self.x, self.y, self.WIDTH, height)
                
                if menu_rect.collidepoint(event.pos):
                    # Clicked on menu
                    if 0 <= self.hovered_index < len(self.items):
                        item = self.items[self.hovered_index]
                        if self.on_select:
                            self.on_select(item)
                        self.hide()
                        return item.action
                else:
                    # Clicked outside - close menu
                    self.hide()
        
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.hide()
        
        return None


# =============================================================================
# TOOLTIP
# =============================================================================

class Tooltip:
    """
    Hover tooltip for items and entities.
    
    Shows multi-line information with color coding.
    """
    
    PADDING = 6
    LINE_SPACING = 2
    MAX_WIDTH = 250
    
    def __init__(self):
        self.visible = False
        self.x = 0
        self.y = 0
        self.lines: List[Tuple[str, Tuple[int, int, int]]] = []
        self.width = 0
        self.height = 0
        
        # Cached font for performance
        self._font = pygame.font.SysFont("sans-serif", 11)
    
    def show(self, x: int, y: int, lines: List[Tuple[str, Tuple[int, int, int]]]) -> None:
        """
        Show tooltip at position.
        
        Args:
            x, y: Position (usually mouse position)
            lines: List of (text, color) tuples
        """
        self.lines = lines
        self.visible = True
        
        # Calculate dimensions
        self.width = 0
        total_height = 0
        
        for text, _ in lines:
            text_surface = self._font.render(text, True, Colors.TEXT_WHITE)
            self.width = max(self.width, text_surface.get_width())
            total_height += text_surface.get_height() + self.LINE_SPACING
        
        self.width = min(self.width + self.PADDING * 2, self.MAX_WIDTH)
        self.height = total_height + self.PADDING * 2 - self.LINE_SPACING
        
        # Adjust position to stay on screen
        screen_width = pygame.display.get_surface().get_width()
        screen_height = pygame.display.get_surface().get_height()
        
        self.x = min(x, screen_width - self.width - 5)
        self.y = min(y, screen_height - self.height - 5)
    
    def hide(self) -> None:
        """Hide the tooltip."""
        self.visible = False
        self.lines = []
    
    def draw(self, screen: pygame.Surface) -> None:
        """Draw the tooltip."""
        if not self.visible or not self.lines:
            return
        
        # Background
        tooltip_rect = pygame.Rect(self.x, self.y, self.width, self.height)
        pygame.draw.rect(screen, Colors.PANEL_BG, tooltip_rect)
        pygame.draw.rect(screen, Colors.PANEL_BORDER, tooltip_rect, 1)
        
        # Lines
        line_y = self.y + self.PADDING
        
        for text, color in self.lines:
            text_surface = self._font.render(text, True, color)
            screen.blit(text_surface, (self.x + self.PADDING, line_y))
            line_y += text_surface.get_height() + self.LINE_SPACING

