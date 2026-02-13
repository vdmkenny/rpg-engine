"""
UI renderer.

Renders OSRS-style UI panels and overlays on top of the game world.
Uses stone-themed panels with 3D borders matching classic OSRS aesthetic.
"""

import pygame
from typing import Dict, Any, Optional, Tuple, Callable

from ..ui.colors import Colors
from .ui_panels import TabbedSidePanel, ChatWindow, ContextMenu, ContextMenuItem, Tooltip
from .customisation_panel import CustomisationPanel
from .help_modal import HelpModal, HelpButton


class UIRenderer:
    """Renders UI panels and overlays using OSRS-style stone theme."""
    
    def __init__(self, screen: pygame.Surface):
        self.screen = screen
        
        # UI state
        self.show_chat = True
        self.show_minimap = True
        
        # Create panels
        screen_width = screen.get_width()
        screen_height = screen.get_height()
        
        # Tabbed side panel (Inventory, Equipment, Stats, Settings) - right side
        # Initialize without callback, will be set via property
        self.side_panel = TabbedSidePanel(
            screen_width - 204,
            screen_height - 312 - 10,
            on_logout=None
        )
        
        # Chat window - bottom left
        self.chat_window = ChatWindow(
            10,
            screen_height - 160,
            400,
            150
        )
        
        # Minimap - top right
        self.minimap = Minimap(
            screen_width - 70,
            70,
            60
        )
        
        # Context menu system
        self.context_menu = ContextMenu()
        
        # Tooltip system
        self.tooltip = Tooltip()
        self.tooltip_target = None  # What the tooltip is currently showing for
        
        # Callbacks for interactions
        self.on_inventory_action: Optional[Callable[[str, Any], None]] = None
        self.on_equipment_action: Optional[Callable[[str, str], None]] = None
        self.on_world_action: Optional[Callable[[str, Any], None]] = None
        self.on_logout: Optional[Callable[[], None]] = None
        self.on_inventory_sort: Optional[Callable[[str], None]] = None
        
        # Customisation panel (initially None, initialized by client)
        self.customisation_panel: Optional[CustomisationPanel] = None
        
        # Help modal and button
        screen_width = screen.get_width()
        screen_height = screen.get_height()
        self.help_modal = HelpModal(screen_width, screen_height)
        self.help_button = HelpButton(screen_width - 42, 10)  # Top-right corner
        
        # Fonts
        try:
            self.font = pygame.font.Font("client/assets/fonts/RetroRPG.ttf", 24)
            self.small_font = pygame.font.Font("client/assets/fonts/RetroRPG.ttf", 18)
            self.tiny_font = pygame.font.Font("client/assets/fonts/RetroRPG.ttf", 14)
        except:
            self.font = pygame.font.Font(None, 24)
            self.small_font = pygame.font.Font(None, 18)
            self.tiny_font = pygame.font.Font(None, 14)
        
        # Cached fonts for shutdown warning (H5 fix)
        self._shutdown_title_font = pygame.font.SysFont("sans-serif", 14, bold=True)
        self._shutdown_text_font = pygame.font.SysFont("sans-serif", 12)
    
    def render(self, game_state: Any) -> None:
        """Render all UI elements."""
        # Render minimap (if enabled)
        if self.show_minimap:
            self.minimap.draw(self.screen, game_state)
        
        # Render side panel (always visible in game)
        self.side_panel.inventory_items = {
            k: {
                "name": v.name,
                "quantity": v.quantity,
                "rarity": v.rarity,
                "is_equippable": v.is_equippable,
                "icon_sprite_id": v.icon_sprite_id
            } for k, v in game_state.inventory.items()
        }
        self.side_panel.equipment_items = {
            k: {
                "name": v.name,
                "icon_sprite_id": v.icon_sprite_id
            } for k, v in game_state.equipment.items()
        }
        self.side_panel.skills = {
            k: {
                "level": v.level,
                "xp": v.xp,
                "xp_to_next": v.xp_to_next,
                "category": getattr(v, 'category', 'other')
            } for k, v in game_state.skills.items()
        }
        self.side_panel.total_level = game_state.total_level
        self.side_panel.draw(self.screen)
        
        # Render chat
        if self.show_chat:
            self.chat_window.draw(self.screen)
        else:
            # UI hint: show chat availability when hidden
            self._render_chat_hint()

        # Render tooltip (on top of panels)
        self.tooltip.draw(self.screen)
        
        # Render context menu (always on top)
        self.context_menu.draw(self.screen)
        
        # Render customisation panel (highest priority - full screen modal)
        if self.customisation_panel and self.customisation_panel.is_visible():
            self.customisation_panel.draw(self.screen)
        
        # Render help modal (second highest priority)
        if self.help_modal.is_visible():
            self.help_modal.draw(self.screen)
        else:
            # Draw help button when modal is not visible
            self.help_button.draw(self.screen)
        
        # Render server shutdown warning if active
        if game_state.server_shutdown_warning:
            self._render_shutdown_warning(game_state.server_shutdown_warning)
    
    def _render_chat_hint(self) -> None:
        """Render a subtle hint that chat is available (shown when chat is hidden)."""
        # Position at bottom left where chat window would be
        hint_x = 10
        hint_y = self.screen.get_height() - 24

        # Small pill-shaped background
        hint_text = "Press C for chat"
        text_surface = self.chat_window.tiny_font.render(hint_text, True, (150, 150, 150))
        padding = 6
        bg_rect = pygame.Rect(
            hint_x,
            hint_y,
            text_surface.get_width() + padding * 2,
            20
        )

        # Semi-transparent background
        bg_surface = pygame.Surface((bg_rect.width, bg_rect.height), pygame.SRCALPHA)
        bg_surface.fill((30, 30, 30, 180))
        self.screen.blit(bg_surface, (bg_rect.x, bg_rect.y))

        # Border
        pygame.draw.rect(self.screen, (79, 67, 55), bg_rect, 1)

        # Text
        self.screen.blit(text_surface, (hint_x + padding, hint_y + 3))

    def _render_shutdown_warning(self, warning: Dict[str, Any]) -> None:
        """Render server shutdown warning."""
        width = 300
        height = 80
        x = (self.screen.get_width() - width) // 2
        y = 50
        
        # Draw warning box
        rect = pygame.Rect(x, y, width, height)
        pygame.draw.rect(self.screen, (150, 50, 50), rect, border_radius=5)
        pygame.draw.rect(self.screen, (255, 100, 100), rect, 3, border_radius=5)
        
        # Text (use cached fonts)
        title = self._shutdown_title_font.render("SERVER SHUTDOWN WARNING", True, (255, 255, 255))
        self.screen.blit(title, (x + 10, y + 10))
        
        reason = warning.get("reason", "Maintenance")
        countdown = warning.get("countdown", 0)
        
        info_text = f"Reason: {reason} | Time: {countdown}s"
        text = self._shutdown_text_font.render(info_text, True, (255, 200, 200))
        self.screen.blit(text, (x + 10, y + 45))
    
    def handle_event(self, event: pygame.event.Event, game_state: Any = None) -> Optional[str]:
        """Handle UI events."""
        # Customisation panel has highest priority when visible (full-screen modal)
        if self.customisation_panel and self.customisation_panel.is_visible():
            action = self.customisation_panel.handle_event(event)
            if action:
                return action
            # If customisation panel is visible and we didn't handle the event, don't pass to other panels
            return None
        
        # Help modal has next priority when visible
        if self.help_modal.is_visible():
            action = self.help_modal.handle_event(event)
            if action:
                return action
            # If help modal is visible and we didn't handle the event, don't pass to other panels
            return None
        
        # Check help button click before other panels
        action = self.help_button.handle_event(event)
        if action == "help_opened":
            self.help_modal.show()
            return action
        
        # Context menu has next priority when visible
        if self.context_menu.visible:
            action = self.context_menu.handle_event(event)
            if action:
                return action
            # If context menu is visible and we didn't handle the event, don't pass to other panels
            return None
        
        # Pass events to panels
        action = self.side_panel.handle_event(event)
        if action:
            return action
        
        action = self.chat_window.handle_event(event)
        if action == "chat_send":
            return "chat_send"
        
        # Handle right-click for context menus
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            # Check inventory slots
            if self.side_panel.active_tab == "inventory":
                clicked_slot = self._get_inventory_slot_at(event.pos, game_state)
                if clicked_slot is not None and clicked_slot in game_state.inventory:
                    self._show_inventory_context_menu(event.pos, clicked_slot, game_state)
                    return None
            
            # Check equipment slots
            if self.side_panel.active_tab == "equipment":
                clicked_slot = self._get_equipment_slot_at(event.pos)
                if clicked_slot and clicked_slot in game_state.equipment:
                    self._show_equipment_context_menu(event.pos, clicked_slot, game_state)
                    return None
        
        # Handle left-click for inventory/equipment actions
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # Check inventory slots
            if self.side_panel.active_tab == "inventory":
                clicked_slot = self._get_inventory_slot_at(event.pos, game_state)
                if clicked_slot is not None:
                    if clicked_slot in game_state.inventory:
                        item = game_state.inventory[clicked_slot]
                        if item.is_equippable and self.on_inventory_action:
                            self.on_inventory_action("equip", clicked_slot)
                    return None
            
            # Check equipment slots
            if self.side_panel.active_tab == "equipment":
                clicked_slot = self._get_equipment_slot_at(event.pos)
                if clicked_slot and clicked_slot in game_state.equipment:
                    if self.on_equipment_action:
                        self.on_equipment_action("unequip", clicked_slot)
                    return None
        
        # Handle hover for tooltips
        if event.type == pygame.MOUSEMOTION and game_state:
            self._update_tooltip(event.pos, game_state)
        
        return None
    
    def _get_inventory_slot_at(self, pos: Tuple[int, int], game_state: Any) -> Optional[int]:
        """Get inventory slot index at screen position."""
        if not self.side_panel or self.side_panel.active_tab != "inventory":
            return None
        
        slot_size = 32
        cols = 4
        grid_width = cols * (slot_size + 2) - 2
        content_rect = self.side_panel._get_content_rect()
        start_x = content_rect.x + (content_rect.width - grid_width) // 2
        start_y = content_rect.y + 8
        
        for slot in range(28):
            col = slot % cols
            row = slot // cols
            slot_rect = pygame.Rect(start_x + col * (slot_size + 2), start_y + row * (slot_size + 2), slot_size, slot_size)
            if slot_rect.collidepoint(pos):
                return slot
        return None
    
    def _get_equipment_slot_at(self, pos: Tuple[int, int]) -> Optional[str]:
        """Get equipment slot name at screen position."""
        if not self.side_panel or self.side_panel.active_tab != "equipment":
            return None
        
        content_rect = self.side_panel._get_content_rect()
        center_x = content_rect.centerx
        content_y = content_rect.y + 8
        slot_size = 34
        
        # Must match _draw_equipment_content() in ui_panels.py exactly
        col_left = center_x - 55
        col_mid = center_x - 17
        col_right = center_x + 21
        row_step = 38

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
        
        for slot_name, sx, sy in slots:
            slot_rect = pygame.Rect(sx, sy, slot_size, slot_size)
            if slot_rect.collidepoint(pos):
                return slot_name
        return None
    
    def _show_inventory_context_menu(self, pos: Tuple[int, int], slot: int, game_state: Any) -> None:
        """Show context menu for inventory item."""
        if slot not in game_state.inventory:
            return
        
        item = game_state.inventory[slot]
        items = [
            ContextMenuItem(f"Use {item.name}", "use", Colors.TEXT_WHITE, slot),
            ContextMenuItem(f"Examine {item.name}", "examine", Colors.TEXT_CYAN, slot),
        ]
        
        if item.is_equippable:
            items.insert(1, ContextMenuItem("Equip", "equip", Colors.TEXT_WHITE, slot))
        
        items.append(ContextMenuItem("Drop", "drop", Colors.TEXT_RED, slot))
        
        self.context_menu.show(pos[0], pos[1], items, self._on_inventory_menu_select)
    
    def _show_equipment_context_menu(self, pos: Tuple[int, int], slot: str, game_state: Any) -> None:
        """Show context menu for equipped item."""
        if slot not in game_state.equipment:
            return
        
        item = game_state.equipment[slot]
        items = [
            ContextMenuItem("Unequip", "unequip", Colors.TEXT_WHITE, slot),
            ContextMenuItem(f"Examine {item.name}", "examine", Colors.TEXT_CYAN, slot),
        ]
        
        self.context_menu.show(pos[0], pos[1], items, self._on_equipment_menu_select)
    
    def _on_inventory_menu_select(self, item: ContextMenuItem) -> None:
        """Handle inventory context menu selection."""
        if self.on_inventory_action:
            self.on_inventory_action(item.action, item.data)
    
    def _on_equipment_menu_select(self, item: ContextMenuItem) -> None:
        """Handle equipment context menu selection."""
        if self.on_equipment_action:
            self.on_equipment_action(item.action, item.data)
    
    def _update_tooltip(self, pos: Tuple[int, int], game_state: Any) -> None:
        """Update tooltip based on hover position."""
        tooltip_data = None
        
        # Check inventory hover
        if self.side_panel.active_tab == "inventory":
            hovered_slot = self._get_inventory_slot_at(pos, game_state)
            if hovered_slot is not None and hovered_slot in game_state.inventory:
                item = game_state.inventory[hovered_slot]
                tooltip_data = [
                    (item.name, Colors.TEXT_YELLOW),
                    (f"Quantity: {item.quantity}", Colors.TEXT_WHITE),
                    (f"Rarity: {item.rarity.title()}", Colors.TEXT_CYAN),
                ]
                if item.is_equippable:
                    tooltip_data.append(("Right-click for options", Colors.TEXT_GRAY))
        
        # Check equipment hover
        if self.side_panel.active_tab == "equipment":
            hovered_slot = self._get_equipment_slot_at(pos)
            if hovered_slot and hovered_slot in game_state.equipment:
                item = game_state.equipment[hovered_slot]
                tooltip_data = [
                    (item.name, Colors.TEXT_YELLOW),
                    (f"Slot: {hovered_slot.title()}", Colors.TEXT_WHITE),
                    ("Click to unequip", Colors.TEXT_GRAY),
                ]
        
        if tooltip_data:
            self.tooltip.show(pos[0] + 15, pos[1] + 15, tooltip_data)
        else:
            self.tooltip.hide()
    
    def toggle_panel(self, panel_name: str) -> None:
        """Toggle a UI panel visibility."""
        if panel_name == "inventory":
            self.side_panel.active_tab = "inventory"
        elif panel_name == "equipment":
            self.side_panel.active_tab = "equipment"
        elif panel_name == "stats":
            self.side_panel.active_tab = "stats"
        elif panel_name == "settings":
            self.side_panel.active_tab = "settings"
        elif panel_name == "chat":
            self.show_chat = not self.show_chat
        elif panel_name == "minimap":
            self.show_minimap = not self.show_minimap
    
    def set_chat_input_active(self, active: bool) -> None:
        """Set whether chat input is active."""
        self.chat_window.input_focused = active
    
    def is_chat_input_active(self) -> bool:
        """Check if chat input is active."""
        return self.chat_window.input_focused

    def set_logout_callback(self, callback: Callable[[], None]) -> None:
        """Set the logout callback."""
        self.on_logout = callback
        self.side_panel.on_logout = callback
    
    def set_inventory_sort_callback(self, callback: Callable[[str], None]) -> None:
        """Set the inventory sort callback."""
        self.on_inventory_sort = callback
        self.side_panel.on_inventory_sort = callback
    
    def show_customisation_panel(self) -> None:
        """Show the customisation panel."""
        if self.customisation_panel:
            self.customisation_panel.show()
    
    def hide_customisation_panel(self) -> None:
        """Hide the customisation panel."""
        if self.customisation_panel:
            self.customisation_panel.hide()
    
    def is_customisation_visible(self) -> bool:
        """Check if customisation panel is visible."""
        if self.customisation_panel:
            return self.customisation_panel.is_visible()
        return False
    
    def show_help_modal(self) -> None:
        """Show the help modal."""
        self.help_modal.show()
    
    def hide_help_modal(self) -> None:
        """Hide the help modal."""
        self.help_modal.hide()
    
    def is_help_visible(self) -> bool:
        """Check if help modal is visible."""
        return self.help_modal.is_visible()


class Minimap:
    """Circular minimap showing player and nearby entities."""
    
    def __init__(self, x: int, y: int, radius: int = 60):
        self.x = x
        self.y = y
        self.radius = radius
    
    def draw(self, screen: pygame.Surface, game_state: Any) -> None:
        """Render minimap."""
        # Draw stone-themed border (3 layers for 3D effect)
        center = (self.x, self.y)
        
        # Outer dark border
        pygame.draw.circle(screen, Colors.STONE_DARK, center, self.radius, 3)
        # Inner highlight
        pygame.draw.circle(screen, Colors.STONE_HIGHLIGHT, center, self.radius - 2, 1)
        
        # Black background
        pygame.draw.circle(screen, Colors.MINIMAP_BG, center, self.radius - 4)
        
        # Draw dots for entities
        # Scale: 3 pixels per tile
        scale = 3
        
        # Other players (cyan)
        for player_id, player in game_state.other_players.items():
            px = player.get("position", {}).get("x", 0)
            py = player.get("position", {}).get("y", 0)
            
            my_x = game_state.position.get("x", 0)
            my_y = game_state.position.get("y", 0)
            
            dx = (px - my_x) * scale
            dy = (py - my_y) * scale
            
            dot_x = center[0] + dx
            dot_y = center[1] + dy
            
            # Check if within circle
            dist = ((dot_x - center[0]) ** 2 + (dot_y - center[1]) ** 2) ** 0.5
            if dist < self.radius - 8:
                pygame.draw.circle(screen, Colors.MINIMAP_OTHER_PLAYER, (int(dot_x), int(dot_y)), 2)
        
        # Extract player position once (H9 fix)
        my_x = game_state.position.get("x", 0)
        my_y = game_state.position.get("y", 0)
        
        # NPCs (yellow) and Monsters (red) - single pass iteration (H8 fix)
        for entity_id, entity in getattr(game_state, 'entities', {}).items():
            entity_type = entity.entity_type.value
            if entity_type not in ('humanoid_npc', 'monster'):
                continue
                
            ex = entity.x
            ey = entity.y
            
            dx = (ex - my_x) * scale
            dy = (ey - my_y) * scale
            
            dot_x = center[0] + dx
            dot_y = center[1] + dy
            
            dist = ((dot_x - center[0]) ** 2 + (dot_y - center[1]) ** 2) ** 0.5
            if dist < self.radius - 8:
                if entity_type == 'humanoid_npc':
                    pygame.draw.circle(screen, Colors.MINIMAP_NPC, (int(dot_x), int(dot_y)), 2)
                else:  # monster
                    pygame.draw.circle(screen, Colors.MINIMAP_MONSTER, (int(dot_x), int(dot_y)), 2)
        
        # Player dot (white, larger, in center)
        pygame.draw.circle(screen, Colors.MINIMAP_PLAYER, center, 3)
