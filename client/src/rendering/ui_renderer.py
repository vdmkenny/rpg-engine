"""
UI renderer.

Renders UI panels and overlays on top of the game world.
"""

import pygame
from typing import Dict, Any, Optional


class UIRenderer:
    """Renders UI panels and overlays."""
    
    def __init__(self, screen: pygame.Surface):
        self.screen = screen
        
        # UI state
        self.show_inventory = False
        self.show_equipment = False
        self.show_stats = False
        self.show_chat = True
        self.show_minimap = True
        
        # Colors
        self.panel_bg = (30, 30, 30, 200)
        self.panel_border = (100, 100, 100)
        self.text_color = (255, 255, 255)
    
    def render(self, game_state: Any) -> None:
        """Render all UI elements."""
        # Render minimap
        if self.show_minimap:
            self._render_minimap(game_state)
        
        # Render status orbs (HP, Prayer, Run)
        self._render_status_orbs(game_state)
        
        # Render inventory panel
        if self.show_inventory:
            self._render_inventory(game_state)
        
        # Render equipment panel
        if self.show_equipment:
            self._render_equipment(game_state)
        
        # Render stats panel
        if self.show_stats:
            self._render_stats(game_state)
        
        # Render chat
        if self.show_chat:
            self._render_chat(game_state)
        
        # Render server shutdown warning if active
        if game_state.server_shutdown_warning:
            self._render_shutdown_warning(game_state.server_shutdown_warning)
    
    def _render_minimap(self, game_state: Any) -> None:
        """Render the circular minimap."""
        size = 150
        margin = 10
        x = self.screen.get_width() - size - margin
        y = margin
        
        # Draw background circle
        center = (x + size // 2, y + size // 2)
        radius = size // 2
        
        # Background
        pygame.draw.circle(self.screen, (20, 20, 20), center, radius)
        pygame.draw.circle(self.screen, (100, 100, 100), center, radius, 2)
        
        # Draw player dot (center)
        pygame.draw.circle(self.screen, (0, 255, 0), center, 4)
        
        # Draw other players as dots
        for player_id, player in game_state.other_players.items():
            # Calculate relative position
            px = player.get("position", {}).get("x", 0)
            py = player.get("position", {}).get("y", 0)
            
            my_x = game_state.position.get("x", 0)
            my_y = game_state.position.get("y", 0)
            
            rel_x = (px - my_x) * 2  # Scale factor
            rel_y = (py - my_y) * 2
            
            dot_x = center[0] + rel_x
            dot_y = center[1] + rel_y
            
            # Check if within circle
            dist = ((dot_x - center[0]) ** 2 + (dot_y - center[1]) ** 2) ** 0.5
            if dist < radius - 5:
                pygame.draw.circle(self.screen, (255, 200, 0), (int(dot_x), int(dot_y)), 3)
    
    def _render_status_orbs(self, game_state: Any) -> None:
        """Render HP, Prayer, and Run orbs."""
        orb_size = 50
        spacing = 10
        margin = 10
        
        screen_width = self.screen.get_width()
        
        # HP Orb (bottom right, next to minimap)
        hp_x = screen_width - orb_size - margin
        hp_y = 170
        
        hp_percent = game_state.current_hp / max(1, game_state.max_hp)
        self._render_orb(hp_x, hp_y, orb_size, hp_percent, (200, 50, 50), "HP")
        
        # Prayer orb (below HP)
        prayer_x = hp_x
        prayer_y = hp_y + orb_size + spacing
        self._render_orb(prayer_x, prayer_y, orb_size, 1.0, (50, 100, 200), "Pray")
        
        # Run orb (below Prayer)
        run_x = hp_x
        run_y = prayer_y + orb_size + spacing
        self._render_orb(run_x, run_y, orb_size, 1.0, (200, 200, 50), "Run")
    
    def _render_orb(self, x: int, y: int, size: int, fill_percent: float, color: tuple, label: str) -> None:
        """Render a status orb."""
        center = (x + size // 2, y + size // 2)
        radius = size // 2
        
        # Background
        pygame.draw.circle(self.screen, (30, 30, 30), center, radius)
        
        # Filled portion (arc)
        if fill_percent > 0:
            # Simplified: draw filled circle with color intensity
            fill_color = (
                int(color[0] * fill_percent + 30 * (1 - fill_percent)),
                int(color[1] * fill_percent + 30 * (1 - fill_percent)),
                int(color[2] * fill_percent + 30 * (1 - fill_percent))
            )
            pygame.draw.circle(self.screen, fill_color, center, radius - 2)
        
        # Border
        pygame.draw.circle(self.screen, (150, 150, 150), center, radius, 2)
        
        # Label
        font = pygame.font.SysFont("sans-serif", 10, bold=True)
        text = font.render(label, True, (255, 255, 255))
        text_rect = text.get_rect(center=center)
        self.screen.blit(text, text_rect)
    
    def _render_inventory(self, game_state: Any) -> None:
        """Render inventory panel."""
        slot_size = 40
        slots_per_row = 4
        num_rows = 7
        
        panel_width = slots_per_row * slot_size + 30
        panel_height = num_rows * slot_size + 50
        
        x = self.screen.get_width() - panel_width - 10
        y = self.screen.get_height() - panel_height - 10
        
        # Draw panel background
        panel_rect = pygame.Rect(x, y, panel_width, panel_height)
        pygame.draw.rect(self.screen, (40, 40, 40), panel_rect, border_radius=5)
        pygame.draw.rect(self.screen, (100, 100, 100), panel_rect, 2, border_radius=5)
        
        # Title
        font = pygame.font.SysFont("sans-serif", 14, bold=True)
        title = font.render("Inventory", True, (255, 255, 255))
        self.screen.blit(title, (x + 10, y + 5))
        
        # Draw slots
        slot_rects = []
        for i in range(game_state.inventory_capacity):
            row = i // slots_per_row
            col = i % slots_per_row
            
            slot_x = x + 10 + col * slot_size
            slot_y = y + 25 + row * slot_size
            
            slot_rect = pygame.Rect(slot_x, slot_y, slot_size - 2, slot_size - 2)
            slot_rects.append(slot_rect)
            
            # Background
            pygame.draw.rect(self.screen, (60, 60, 60), slot_rect, border_radius=2)
            
            # Border (highlight if item present)
            if i in game_state.inventory:
                pygame.draw.rect(self.screen, (150, 150, 150), slot_rect, 2, border_radius=2)
                
                # Draw item name (abbreviated)
                item = game_state.inventory[i]
                item_font = pygame.font.SysFont("sans-serif", 8)
                name_text = item_font.render(item.name[:8], True, (255, 255, 255))
                self.screen.blit(name_text, (slot_x + 2, slot_y + 2))
                
                # Draw quantity if > 1
                if item.quantity > 1:
                    qty_text = item_font.render(str(item.quantity), True, (255, 255, 0))
                    self.screen.blit(qty_text, (slot_x + slot_size - 15, slot_y + slot_size - 12))
            else:
                pygame.draw.rect(self.screen, (80, 80, 80), slot_rect, 1, border_radius=2)
    
    def _render_equipment(self, game_state: Any) -> None:
        """Render equipment panel."""
        panel_width = 200
        panel_height = 350
        
        x = self.screen.get_width() - panel_width - 10
        y = (self.screen.get_height() - panel_height) // 2
        
        # Draw panel
        panel_rect = pygame.Rect(x, y, panel_width, panel_height)
        pygame.draw.rect(self.screen, (40, 40, 40), panel_rect, border_radius=5)
        pygame.draw.rect(self.screen, (100, 100, 100), panel_rect, 2, border_radius=5)
        
        # Title
        font = pygame.font.SysFont("sans-serif", 14, bold=True)
        title = font.render("Equipment", True, (255, 255, 255))
        self.screen.blit(title, (x + 10, y + 10))
        
        # Equipment slots
        slot_names = [
            "head", "cape", "neck", "ammunition",
            "weapon", "body", "shield", "legs", "hands", "feet", "ring"
        ]
        
        slot_y = y + 40
        for slot_name in slot_names:
            # Slot label
            label_font = pygame.font.SysFont("sans-serif", 11)
            label = label_font.render(slot_name.capitalize() + ":", True, (200, 200, 200))
            self.screen.blit(label, (x + 10, slot_y))
            
            # Item name if equipped
            if slot_name in game_state.equipment:
                item = game_state.equipment[slot_name]
                item_font = pygame.font.SysFont("sans-serif", 11, bold=True)
                item_text = item_font.render(item.name, True, (255, 215, 0))
                self.screen.blit(item_text, (x + 80, slot_y))
            else:
                empty_font = pygame.font.SysFont("sans-serif", 10, italic=True)
                empty_text = empty_font.render("(empty)", True, (100, 100, 100))
                self.screen.blit(empty_text, (x + 80, slot_y))
            
            slot_y += 25
    
    def _render_stats(self, game_state: Any) -> None:
        """Render stats panel."""
        panel_width = 200
        panel_height = 400
        
        x = 10
        y = (self.screen.get_height() - panel_height) // 2
        
        # Draw panel
        panel_rect = pygame.Rect(x, y, panel_width, panel_height)
        pygame.draw.rect(self.screen, (40, 40, 40), panel_rect, border_radius=5)
        pygame.draw.rect(self.screen, (100, 100, 100), panel_rect, 2, border_radius=5)
        
        # Title
        font = pygame.font.SysFont("sans-serif", 14, bold=True)
        title = font.render(f"Stats (Lvl {game_state.combat_level})", True, (255, 255, 255))
        self.screen.blit(title, (x + 10, y + 10))
        
        # Skills
        skill_y = y + 40
        skill_font = pygame.font.SysFont("sans-serif", 11)
        
        for skill_name, skill in sorted(game_state.skills.items()):
            skill_text = f"{skill_name}: {skill.level}"
            text = skill_font.render(skill_text, True, (200, 200, 200))
            self.screen.blit(text, (x + 10, skill_y))
            skill_y += 18
        
        # Totals
        totals_y = skill_y + 10
        totals_font = pygame.font.SysFont("sans-serif", 11, bold=True)
        totals_text = f"Total: {game_state.total_level} | XP: {game_state.total_xp}"
        text = totals_font.render(totals_text, True, (255, 255, 255))
        self.screen.blit(text, (x + 10, totals_y))
    
    def _render_chat(self, game_state: Any) -> None:
        """Render chat window."""
        width = 400
        height = 150
        x = 10
        y = self.screen.get_height() - height - 10
        
        # Draw background
        chat_rect = pygame.Rect(x, y, width, height)
        pygame.draw.rect(self.screen, (30, 30, 30, 200), chat_rect, border_radius=5)
        pygame.draw.rect(self.screen, (80, 80, 80), chat_rect, 1, border_radius=5)
        
        # Messages
        font = pygame.font.SysFont("sans-serif", 11)
        msg_y = y + height - 20
        
        # Show last 6 messages
        recent_messages = game_state.chat_history[-6:]
        for msg in reversed(recent_messages):
            channel = msg.get("channel", "local")
            sender = msg.get("sender", "?")
            message = msg.get("message", "")
            
            # Color based on channel
            if channel == "global":
                color = (255, 200, 100)
            elif channel == "dm":
                color = (200, 150, 255)
            else:
                color = (200, 200, 200)
            
            full_text = f"[{channel[0].upper()}] {sender}: {message}"
            text_surface = font.render(full_text[:60], True, color)
            self.screen.blit(text_surface, (x + 5, msg_y))
            
            msg_y -= 18
            if msg_y < y + 5:
                break
    
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
        
        # Text
        title_font = pygame.font.SysFont("sans-serif", 14, bold=True)
        text_font = pygame.font.SysFont("sans-serif", 12)
        
        title = title_font.render("SERVER SHUTDOWN WARNING", True, (255, 255, 255))
        self.screen.blit(title, (x + 10, y + 10))
        
        reason = warning.get("reason", "Maintenance")
        countdown = warning.get("countdown", 0)
        
        info_text = f"Reason: {reason} | Time: {countdown}s"
        text = text_font.render(info_text, True, (255, 200, 200))
        self.screen.blit(text, (x + 10, y + 45))
    
    def toggle_panel(self, panel_name: str) -> None:
        """Toggle a UI panel visibility."""
        if panel_name == "inventory":
            self.show_inventory = not self.show_inventory
        elif panel_name == "equipment":
            self.show_equipment = not self.show_equipment
        elif panel_name == "stats":
            self.show_stats = not self.show_stats
        elif panel_name == "chat":
            self.show_chat = not self.show_chat
        elif panel_name == "minimap":
            self.show_minimap = not self.show_minimap
    
    def hide_all_panels(self) -> None:
        """Hide all panels."""
        self.show_inventory = False
        self.show_equipment = False
        self.show_stats = False
