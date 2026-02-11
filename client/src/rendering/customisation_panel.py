"""
Character customisation panel - Full-screen modal for paperdoll customization.

Provides a two-column interface:
- Left/Center: Scrollable list of appearance fields with arrow cycling
- Right: Live paperdoll preview with animated walk cycle

First-time players (no appearance data) are forced to apply a customisation
before they can close the panel. Cancel button is hidden and ESC is blocked.
"""

import asyncio
import pygame
from typing import Dict, List, Optional, Callable, Any, Tuple
from dataclasses import dataclass

from client.src.ui.colors import Colors
from client.src.rendering.paperdoll_renderer import PaperdollRenderer

from protocol import Direction
from sprites.enums import BodyType, AnimationType
from sprites.animation import AnimationState


@dataclass
class FieldInfo:
    """Information about an appearance field with its options."""
    field: str
    label: str
    options: List[Dict[str, str]]  # Each option has "value" and "label"
    current_index: int = 0
    restrictions: Optional[Dict[str, Any]] = None  # Server restrictions metadata


class CustomisationPanel:
    """Full-screen character customisation modal panel."""
    
    # Layout constants
    PADDING = 20
    PREVIEW_WIDTH = 280
    BUTTON_HEIGHT = 40
    ROW_HEIGHT = 40
    ARROW_WIDTH = 24
    
    # Preview constants
    PREVIEW_SIZE = 192  # 3x the native 64px sprite size
    DIRECTION_CYCLE = [Direction.DOWN, Direction.LEFT, Direction.UP, Direction.RIGHT]
    DIRECTION_LABELS = {
        Direction.DOWN: "Front",
        Direction.LEFT: "Left",
        Direction.UP: "Back",
        Direction.RIGHT: "Right",
    }
    
    def __init__(
        self,
        screen_width: int,
        screen_height: int,
        paperdoll_renderer: PaperdollRenderer,
        on_apply: Optional[Callable[[Dict[str, str]], None]] = None,
        on_cancel: Optional[Callable[[], None]] = None,
    ):
        """Initialize the customisation panel.
        
        Args:
            screen_width: Screen width in pixels
            screen_height: Screen height in pixels
            paperdoll_renderer: Renderer for the paperdoll preview
            on_apply: Callback when Apply is clicked, receives changes dict
            on_cancel: Callback when Cancel or ESC is pressed
        """
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.paperdoll_renderer = paperdoll_renderer
        self.on_apply = on_apply
        self.on_cancel = on_cancel
        
        # Panel state
        self.visible = False
        self.fields: List[FieldInfo] = []
        self.preview_appearance: Dict[str, str] = {}
        self._is_first_time = False  # True when player has no appearance data
        
        # Animation state for walk preview
        self.animation_state = AnimationState()
        self.animation_state.play(AnimationType.WALK)
        
        # Scroll state
        self.scroll_offset = 0
        self.max_scroll = 0
        
        # Calculate layout
        self._calculate_layout()
        
        # Fonts
        try:
            self.title_font = pygame.font.Font("client/assets/fonts/RetroRPG.ttf", 32)
            self.field_font = pygame.font.Font("client/assets/fonts/RetroRPG.ttf", 20)
            self.button_font = pygame.font.Font("client/assets/fonts/RetroRPG.ttf", 20)
            self.arrow_font = pygame.font.Font("client/assets/fonts/RetroRPG.ttf", 20)
        except:
            self.title_font = pygame.font.Font(None, 32)
            self.field_font = pygame.font.Font(None, 20)
            self.button_font = pygame.font.Font(None, 20)
            self.arrow_font = pygame.font.Font(None, 20)
        
        # Hover state
        self.hovered_row_idx: Optional[int] = None
        self.hovered_arrow: Optional[Tuple[int, str]] = None  # (row_idx, 'left'/'right')
        self.hovered_apply = False
        self.hovered_cancel = False
        self.hovered_randomize = False
        self.hovered_preview_arrow: Optional[str] = None  # 'left' or 'right' direction arrows
        self._loading_sprites = False
        
        # Preview direction state (cycles through DIRECTION_CYCLE)
        self.preview_direction_idx = 0  # Start facing DOWN
        
        # Preview state
        self._preview_visual_state: Optional[Dict[str, Any]] = None
        self._preview_visual_hash: Optional[str] = None
    
    def _calculate_layout(self) -> None:
        """Calculate panel layout rectangles."""
        # Full screen modal with dark overlay
        self.modal_rect = pygame.Rect(0, 0, self.screen_width, self.screen_height)
        
        # Main panel (centered, leaves margin for dark overlay)
        margin = 40
        self.panel_rect = pygame.Rect(
            margin, margin,
            self.screen_width - margin * 2,
            self.screen_height - margin * 2
        )
        
        # Title area
        self.title_rect = pygame.Rect(
            self.panel_rect.x,
            self.panel_rect.y,
            self.panel_rect.width,
            50
        )
        
        # Content area (below title, above buttons)
        content_top = self.panel_rect.y + 60
        content_bottom = self.panel_rect.bottom - 70
        content_height = content_bottom - content_top
        
        # Preview column (right)
        self.preview_rect = pygame.Rect(
            self.panel_rect.right - self.PREVIEW_WIDTH - self.PADDING,
            content_top,
            self.PREVIEW_WIDTH,
            content_height
        )
        
        # Direction arrow buttons below preview (centered, 40px wide each)
        preview_bg_bottom = content_top + content_height - 60  # Above info text area
        arrow_y = preview_bg_bottom + 10
        arrow_spacing = 20
        arrow_width = 40
        arrow_height = 30
        arrow_center_x = self.preview_rect.centerx
        
        self.preview_left_arrow_rect = pygame.Rect(
            arrow_center_x - arrow_spacing - arrow_width,
            arrow_y,
            arrow_width,
            arrow_height
        )
        self.preview_right_arrow_rect = pygame.Rect(
            arrow_center_x + arrow_spacing,
            arrow_y,
            arrow_width,
            arrow_height
        )
        
        # Fields area (left/center, between panel edge and preview)
        fields_left = self.panel_rect.x + self.PADDING
        fields_right = self.preview_rect.left - self.PADDING
        self.fields_rect = pygame.Rect(
            fields_left,
            content_top,
            fields_right - fields_left,
            content_height
        )
        
        # Button area (bottom, centered)
        button_y = self.panel_rect.bottom - 60
        button_spacing = 20
        button_width = 200
        randomize_width = 120
        
        # Calculate centered positions for 3 buttons
        total_width_3btn = button_width + button_spacing + button_width + button_spacing + randomize_width
        center_x = self.panel_rect.centerx - total_width_3btn // 2
        
        # Cancel button (only shown when not first-time) - leftmost
        self.cancel_rect = pygame.Rect(
            center_x,
            button_y,
            button_width,
            self.BUTTON_HEIGHT
        )
        
        # Apply button - middle
        self.apply_rect = pygame.Rect(
            center_x + button_width + button_spacing,
            button_y,
            button_width,
            self.BUTTON_HEIGHT
        )
        
        # Randomize button - rightmost (narrower)
        self.randomize_rect = pygame.Rect(
            self.apply_rect.right + button_spacing,
            button_y,
            randomize_width,
            self.BUTTON_HEIGHT
        )
        
        # When cancel is hidden, center apply with randomize to the right
        total_width_2btn = button_width + button_spacing + randomize_width
        center_x_2btn = self.panel_rect.centerx - total_width_2btn // 2
        
        self.apply_only_rect = pygame.Rect(
            center_x_2btn,
            button_y,
            button_width,
            self.BUTTON_HEIGHT
        )
        
        self.randomize_only_rect = pygame.Rect(
            center_x_2btn + button_width + button_spacing,
            button_y,
            randomize_width,
            self.BUTTON_HEIGHT
        )
    
    def set_categories(self, categories_data: List[Dict[str, Any]]) -> None:
        """Set the available appearance fields from server response.
        
        Args:
            categories_data: List of category dicts from GET /api/appearance/options
        """
        self.fields = [
            FieldInfo(
                field=cat["field"],
                label=cat["label"],
                options=cat["options"],
                current_index=0,  # Default to first option
                restrictions=cat.get("restrictions")  # Server restriction metadata
            )
            for cat in categories_data
        ]
        self.scroll_offset = 0
    
    def set_current_appearance(self, appearance: Dict[str, str]) -> None:
        """Set the current player appearance.
        
        If appearance is empty, this is a first-time player and
        cancel/esc will be blocked.
        
        Args:
            appearance: Dict with current appearance values
        """
        self._is_first_time = not appearance
        
        # Set each field's current_index to match the appearance value
        for field_info in self.fields:
            current_value = appearance.get(field_info.field)
            if current_value:
                # Find the index of the matching option value
                for idx, opt in enumerate(field_info.options):
                    if opt["value"] == current_value:
                        field_info.current_index = idx
                        break
            # If no match found, keep index 0 (first option)
        
        # Build preview appearance from current indices
        self.preview_appearance = {
            field_info.field: field_info.options[field_info.current_index]["value"]
            for field_info in self.fields
        }
        
        self._preload_preview_sprites()
    
    def _preload_preview_sprites(self) -> None:
        """Preload sprites for the current preview appearance."""
        visual_state = self._build_visual_state(self.preview_appearance)
        if not visual_state:
            return
        
        import json
        import hashlib
        visual_hash = hashlib.md5(
            json.dumps(visual_state, sort_keys=True).encode()
        ).hexdigest()[:12]
        
        # Store for render() to check is_loaded
        self._preview_visual_hash = visual_hash
        self._preview_visual_state = visual_state
        self._loading_sprites = True
        
        # Actually trigger the async preload
        asyncio.create_task(
            self.paperdoll_renderer.preload_character(visual_state, visual_hash)
        )
    
    def _build_visual_state(self, appearance: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """Build visual_state dict from appearance values."""
        if not appearance:
            return None
        
        return {
            "appearance": {
                "body_type": appearance.get("body_type", "male"),
                "skin_tone": appearance.get("skin_tone", "light"),
                "head_type": appearance.get("head_type", "human/male"),
                "hair_style": appearance.get("hair_style", "bald"),
                "hair_color": appearance.get("hair_color", "dark_brown"),
                "eye_color": appearance.get("eye_color", "brown"),
                "facial_hair_style": appearance.get("facial_hair_style", "none"),
                "facial_hair_color": appearance.get("facial_hair_color", "dark_brown"),
                "shirt_style": appearance.get("shirt_style", "longsleeve2"),
                "shirt_color": appearance.get("shirt_color", "white"),
                "pants_style": appearance.get("pants_style", "pants"),
                "pants_color": appearance.get("pants_color", "brown"),
                "shoes_style": appearance.get("shoes_style", "shoes/basic"),
                "shoes_color": appearance.get("shoes_color", "brown"),
            },
            "equipment": {}
        }
    
    def show(self) -> None:
        """Show the customisation panel."""
        self.visible = True
        self.scroll_offset = 0
        self.preview_direction_idx = 0  # Reset to face front (DOWN)
        # Reset animation
        self.animation_state = AnimationState()
        self.animation_state.play(AnimationType.WALK)
    
    def hide(self) -> None:
        """Hide the customisation panel."""
        self.visible = False
    
    def is_visible(self) -> bool:
        """Check if panel is visible."""
        return self.visible
    
    def update(self, delta_time: float) -> None:
        """Update animation state."""
        if not self.visible:
            return
        
        body_type_str = self.preview_appearance.get("body_type", "male")
        try:
            body_type = BodyType(body_type_str)
        except (ValueError, KeyError):
            body_type = BodyType.MALE
        
        self.animation_state.update(delta_time, body_type)
    
    def _get_row_rect(self, idx: int) -> Tuple[pygame.Rect, bool]:
        """Get rectangle for a field row.
        
        Returns:
            (rect, is_visible) tuple
        """
        y = self.fields_rect.y + idx * (self.ROW_HEIGHT + 8) - self.scroll_offset
        rect = pygame.Rect(self.fields_rect.x, y, self.fields_rect.width, self.ROW_HEIGHT)
        is_visible = (
            rect.bottom > self.fields_rect.top and
            rect.top < self.fields_rect.bottom
        )
        return (rect, is_visible)
    
    def _get_arrow_rects(self, row_rect: pygame.Rect) -> Tuple[pygame.Rect, pygame.Rect]:
        """Get left and right arrow rectangles for a row."""
        # Value area is in the center of the row
        value_width = 200
        value_x = row_rect.centerx - value_width // 2
        
        left_rect = pygame.Rect(
            value_x - self.ARROW_WIDTH - 8,
            row_rect.centery - 10,
            self.ARROW_WIDTH,
            20
        )
        right_rect = pygame.Rect(
            value_x + value_width + 8,
            row_rect.centery - 10,
            self.ARROW_WIDTH,
            20
        )
        return (left_rect, right_rect)
    
    def handle_event(self, event: pygame.event.Event) -> Optional[str]:
        """Handle input events."""
        if not self.visible:
            return None
        
        if event.type == pygame.MOUSEMOTION:
            mouse_pos = event.pos
            
            # Check field row hover
            self.hovered_row_idx = None
            self.hovered_arrow = None
            for i in range(len(self.fields)):
                row_rect, visible = self._get_row_rect(i)
                if not visible:
                    continue
                if row_rect.collidepoint(mouse_pos):
                    self.hovered_row_idx = i
                    # Check arrow hover
                    left_rect, right_rect = self._get_arrow_rects(row_rect)
                    if left_rect.collidepoint(mouse_pos):
                        self.hovered_arrow = (i, 'left')
                    elif right_rect.collidepoint(mouse_pos):
                        self.hovered_arrow = (i, 'right')
                    break
            
            # Check button hover
            if self._is_first_time:
                # Apply and randomize visible
                self.hovered_apply = self.apply_only_rect.collidepoint(mouse_pos)
                self.hovered_cancel = False
                self.hovered_randomize = self.randomize_only_rect.collidepoint(mouse_pos)
            else:
                # All three buttons visible
                self.hovered_apply = self.apply_rect.collidepoint(mouse_pos)
                self.hovered_cancel = self.cancel_rect.collidepoint(mouse_pos)
                self.hovered_randomize = self.randomize_rect.collidepoint(mouse_pos)
            
            # Check preview direction arrow hover
            self.hovered_preview_arrow = None
            if self.preview_left_arrow_rect.collidepoint(mouse_pos):
                self.hovered_preview_arrow = 'left'
            elif self.preview_right_arrow_rect.collidepoint(mouse_pos):
                self.hovered_preview_arrow = 'right'
        
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:  # Left click
                mouse_pos = event.pos
                
                # Check arrow clicks
                if self.hovered_arrow:
                    row_idx, arrow = self.hovered_arrow
                    self._cycle_field(row_idx, arrow == 'right')
                    return None
                
                # Check cancel button (only if not first-time)
                if not self._is_first_time and self.cancel_rect.collidepoint(mouse_pos):
                    if self.on_cancel:
                        self.on_cancel()
                    self.hide()
                    return "customisation_cancel"
                
                # Check apply button
                apply_rect = self.apply_only_rect if self._is_first_time else self.apply_rect
                if apply_rect.collidepoint(mouse_pos):
                    changes = self._get_changes()
                    if changes and self.on_apply:
                        self.on_apply(changes)
                    # After apply, reset first-time flag
                    self._is_first_time = False
                    self.hide()
                    return "customisation_apply"
                
                # Check randomize button
                randomize_rect = self.randomize_only_rect if self._is_first_time else self.randomize_rect
                if randomize_rect.collidepoint(mouse_pos):
                    self._randomize_all()
                    return None
                
                # Check preview direction arrows
                if self.preview_left_arrow_rect.collidepoint(mouse_pos):
                    # Cycle left (previous direction)
                    self.preview_direction_idx = (self.preview_direction_idx - 1) % len(self.DIRECTION_CYCLE)
                    return None
                elif self.preview_right_arrow_rect.collidepoint(mouse_pos):
                    # Cycle right (next direction)
                    self.preview_direction_idx = (self.preview_direction_idx + 1) % len(self.DIRECTION_CYCLE)
                    return None
        
        elif event.type == pygame.MOUSEWHEEL:
            # Scroll fields
            if self.fields_rect.collidepoint(pygame.mouse.get_pos()):
                total_height = len(self.fields) * (self.ROW_HEIGHT + 8)
                self.max_scroll = max(0, total_height - self.fields_rect.height)
                self.scroll_offset = max(0, min(self.scroll_offset - event.y * 30, self.max_scroll))
        
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                # Block ESC when first-time
                if self._is_first_time:
                    return None
                if self.on_cancel:
                    self.on_cancel()
                self.hide()
                return "customisation_cancel"
        
        return None
    
    def _get_valid_options(self, field_info: FieldInfo) -> List[Dict[str, str]]:
        """Get valid options for a field, applying cross-field restrictions.
        
        Filters out options that are restricted based on current appearance values.
        """
        options = field_info.options
        restrictions = field_info.restrictions
        
        if not restrictions:
            return options
        
        # Apply body_type_filter (e.g., corset only for female)
        if "body_type_filter" in restrictions:
            current_body_type = self.preview_appearance.get("body_type", "male")
            options = [
                opt for opt in options
                if opt["value"] not in restrictions["body_type_filter"]
                or current_body_type in restrictions["body_type_filter"][opt["value"]]
            ]
        
        # Apply shirt_style_filter (e.g., robe limited colors)
        if "shirt_style_filter" in restrictions and field_info.field == "shirt_color":
            current_shirt_style = self.preview_appearance.get("shirt_style", "longsleeve2")
            if current_shirt_style in restrictions["shirt_style_filter"]:
                valid_colors = restrictions["shirt_style_filter"][current_shirt_style]
                options = [opt for opt in options if opt["value"] in valid_colors]
        
        return options
    
    def _cycle_field(self, row_idx: int, forward: bool) -> None:
        """Cycle a field's value forward or backward, skipping invalid options."""
        field_info = self.fields[row_idx]
        valid_options = self._get_valid_options(field_info)
        num_options = len(valid_options)
        
        if num_options == 0:
            return
        
        # Find the index of current value in valid options
        current_value = field_info.options[field_info.current_index]["value"]
        current_valid_idx = next(
            (i for i, opt in enumerate(valid_options) if opt["value"] == current_value),
            0
        )
        
        # Cycle within valid options
        if forward:
            new_valid_idx = (current_valid_idx + 1) % num_options
        else:
            new_valid_idx = (current_valid_idx - 1) % num_options
        
        # Update field to the new valid option index
        new_value = valid_options[new_valid_idx]["value"]
        # Find this value's index in the full options list
        for idx, opt in enumerate(field_info.options):
            if opt["value"] == new_value:
                field_info.current_index = idx
                break
        
        # Update preview appearance
        self.preview_appearance[field_info.field] = new_value
        
        # Check if other fields need re-filtering due to this change
        self._check_field_dependencies(field_info.field)
        
        # Trigger sprite reload
        self._preload_preview_sprites()
    
    def _check_field_dependencies(self, changed_field: str) -> None:
        """Check if changing a field requires re-filtering other fields.
        
        E.g., changing body_type may invalidate current shirt_style selection.
        """
        # If body_type changed, check if shirt_style is still valid
        if changed_field == "body_type":
            shirt_field = next((f for f in self.fields if f.field == "shirt_style"), None)
            if shirt_field and shirt_field.restrictions:
                valid_options = self._get_valid_options(shirt_field)
                current_value = shirt_field.options[shirt_field.current_index]["value"]
                if not any(opt["value"] == current_value for opt in valid_options):
                    # Current selection invalid, move to first valid option
                    if valid_options:
                        for idx, opt in enumerate(shirt_field.options):
                            if opt["value"] == valid_options[0]["value"]:
                                shirt_field.current_index = idx
                                self.preview_appearance["shirt_style"] = valid_options[0]["value"]
                                break
        
        # If shirt_style changed, re-filter shirt_color if robe
        if changed_field == "shirt_style":
            color_field = next((f for f in self.fields if f.field == "shirt_color"), None)
            if color_field and color_field.restrictions:
                valid_options = self._get_valid_options(color_field)
                current_value = color_field.options[color_field.current_index]["value"]
                if not any(opt["value"] == current_value for opt in valid_options):
                    # Current selection invalid, move to first valid option
                    if valid_options:
                        for idx, opt in enumerate(color_field.options):
                            if opt["value"] == valid_options[0]["value"]:
                                color_field.current_index = idx
                                self.preview_appearance["shirt_color"] = valid_options[0]["value"]
                                break
    
    def _randomize_all(self) -> None:
        """Randomize all appearance fields to valid random values."""
        import random
        for field_info in self.fields:
            valid_options = self._get_valid_options(field_info)
            if valid_options:
                chosen = random.choice(valid_options)
                # Find index in full options list
                for idx, opt in enumerate(field_info.options):
                    if opt["value"] == chosen["value"]:
                        field_info.current_index = idx
                        break
                self.preview_appearance[field_info.field] = chosen["value"]
        
        # Re-check cross-field dependencies after randomization
        self._check_field_dependencies("body_type")
        self._check_field_dependencies("shirt_style")
        
        # Trigger sprite reload
        self._preload_preview_sprites()
    
    def _get_changes(self) -> Dict[str, str]:
        """Get appearance changes."""
        # Compare preview_appearance to what was originally set
        # We track this by building a dict from current field indices
        current_appearance = {
            field_info.field: field_info.options[field_info.current_index]["value"]
            for field_info in self.fields
        }
        return current_appearance
    
    def draw(self, screen: pygame.Surface) -> None:
        """Draw the customisation panel."""
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
        title_surface = self.title_font.render("Character Customisation", True, Colors.TEXT_ORANGE)
        title_x = self.panel_rect.centerx - title_surface.get_width() // 2
        screen.blit(title_surface, (title_x, self.panel_rect.y + 15))
        
        # Fields area
        self._draw_fields(screen)
        
        # Preview
        self._draw_preview(screen)
        
        # Buttons
        self._draw_buttons(screen)
    
    def _draw_fields(self, screen: pygame.Surface) -> None:
        """Draw scrollable list of appearance fields."""
        # Header
        header_surface = self.field_font.render("Customize Appearance", True, Colors.TEXT_YELLOW)
        screen.blit(header_surface, (self.fields_rect.x, self.fields_rect.y - 25))
        
        # Clip to fields area
        fields_clip = screen.get_clip()
        screen.set_clip(self.fields_rect)
        
        # Draw each field row
        for i, field_info in enumerate(self.fields):
            row_rect, visible = self._get_row_rect(i)
            if not visible:
                continue
            
            is_hovered = self.hovered_row_idx == i
            bg_color = Colors.BUTTON_HOVER if is_hovered else Colors.BUTTON_BG
            
            # Draw row background
            pygame.draw.rect(screen, bg_color, row_rect)
            pygame.draw.rect(screen, Colors.PANEL_BORDER, row_rect, 1)
            
            # Draw field label
            label_surface = self.field_font.render(field_info.label, True, Colors.WHITE)
            screen.blit(label_surface, (row_rect.x + 10, row_rect.centery - label_surface.get_height() // 2))
            
            # Draw current value with arrows
            current_value = field_info.options[field_info.current_index]["label"]
            left_rect, right_rect = self._get_arrow_rects(row_rect)
            
            # Arrow colors
            left_color = Colors.TEXT_ORANGE if self.hovered_arrow == (i, 'left') else Colors.WHITE
            right_color = Colors.TEXT_ORANGE if self.hovered_arrow == (i, 'right') else Colors.WHITE
            
            # Draw arrows
            left_surface = self.arrow_font.render("<", True, left_color)
            right_surface = self.arrow_font.render(">", True, right_color)
            screen.blit(left_surface, (left_rect.centerx - left_surface.get_width() // 2, 
                                      left_rect.centery - left_surface.get_height() // 2))
            screen.blit(right_surface, (right_rect.centerx - right_surface.get_width() // 2,
                                       right_rect.centery - right_surface.get_height() // 2))
            
            # Draw value label
            value_surface = self.field_font.render(current_value, True, Colors.TEXT_YELLOW)
            value_x = row_rect.centerx - value_surface.get_width() // 2
            screen.blit(value_surface, (value_x, row_rect.centery - value_surface.get_height() // 2))
        
        # Restore clip
        screen.set_clip(fields_clip)
        
        # Draw scrollbar if needed
        total_height = len(self.fields) * (self.ROW_HEIGHT + 8)
        if total_height > self.fields_rect.height:
            self._draw_scrollbar(screen, total_height)
    
    def _draw_scrollbar(self, screen: pygame.Surface, total_height: int) -> None:
        """Draw scrollbar for fields area."""
        scrollbar_x = self.fields_rect.right - 8
        scrollbar_width = 6
        
        # Track
        track_rect = pygame.Rect(
            scrollbar_x, self.fields_rect.y,
            scrollbar_width, self.fields_rect.height
        )
        pygame.draw.rect(screen, Colors.PANEL_BORDER, track_rect)
        
        # Thumb
        thumb_height = max(30, self.fields_rect.height * self.fields_rect.height / total_height)
        max_scroll = total_height - self.fields_rect.height
        if max_scroll > 0:
            thumb_y = self.fields_rect.y + (self.scroll_offset / max_scroll) * (self.fields_rect.height - thumb_height)
        else:
            thumb_y = self.fields_rect.y
        
        thumb_rect = pygame.Rect(scrollbar_x, thumb_y, scrollbar_width, thumb_height)
        pygame.draw.rect(screen, Colors.TEXT_YELLOW, thumb_rect)
    
    def _draw_preview(self, screen: pygame.Surface) -> None:
        """Draw animated walk preview."""
        # Header
        header_surface = self.field_font.render("Preview", True, Colors.TEXT_YELLOW)
        screen.blit(header_surface, (self.preview_rect.x, self.preview_rect.y - 25))
        
        # Preview background
        preview_bg = pygame.Rect(
            self.preview_rect.x,
            self.preview_rect.y,
            self.preview_rect.width,
            self.preview_rect.height - 60
        )
        pygame.draw.rect(screen, (40, 40, 40), preview_bg)
        pygame.draw.rect(screen, Colors.PANEL_BORDER, preview_bg, 2)
        
        # Draw character
        if self._preview_visual_state and self._preview_visual_hash:
            if self.paperdoll_renderer.is_loaded(self._preview_visual_state):
                self._loading_sprites = False
                
                frame = self.animation_state.frame
                
                current_direction = self.DIRECTION_CYCLE[self.preview_direction_idx]
                char_surface = self.paperdoll_renderer.get_frame(
                    visual_state=self._preview_visual_state,
                    visual_hash=self._preview_visual_hash,
                    animation=AnimationType.WALK,
                    direction=current_direction,
                    frame=frame,
                    render_size=self.PREVIEW_SIZE
                )
                
                if char_surface:
                    char_x = preview_bg.centerx - char_surface.get_width() // 2
                    char_y = preview_bg.centery - char_surface.get_height() // 2
                    screen.blit(char_surface, (char_x, char_y))
            else:
                self._loading_sprites = True
                loading_surface = self.field_font.render("Loading...", True, Colors.TEXT_YELLOW)
                text_x = preview_bg.centerx - loading_surface.get_width() // 2
                text_y = preview_bg.centery - loading_surface.get_height() // 2
                screen.blit(loading_surface, (text_x, text_y))
        
        # Draw direction arrows below preview
        self._draw_preview_direction_arrows(screen)
    
    def _draw_buttons(self, screen: pygame.Surface) -> None:
        """Draw Apply, Cancel, and Randomize buttons."""
        # When first-time, show Apply and Randomize buttons
        if self._is_first_time:
            # Create Character button
            apply_color = Colors.BUTTON_HOVER if self.hovered_apply else Colors.BUTTON_BG
            pygame.draw.rect(screen, apply_color, self.apply_only_rect)
            pygame.draw.rect(screen, Colors.TEXT_ORANGE, self.apply_only_rect, 2)
            
            apply_text = self.button_font.render("Create Character", True, Colors.TEXT_ORANGE)
            text_x = self.apply_only_rect.centerx - apply_text.get_width() // 2
            text_y = self.apply_only_rect.centery - apply_text.get_height() // 2
            screen.blit(apply_text, (text_x, text_y))
            
            # Randomize button
            randomize_color = Colors.BUTTON_HOVER if self.hovered_randomize else Colors.BUTTON_BG
            pygame.draw.rect(screen, randomize_color, self.randomize_only_rect)
            pygame.draw.rect(screen, Colors.TEXT_YELLOW, self.randomize_only_rect, 2)
            
            randomize_text = self.button_font.render("Randomize", True, Colors.TEXT_YELLOW)
            text_x = self.randomize_only_rect.centerx - randomize_text.get_width() // 2
            text_y = self.randomize_only_rect.centery - randomize_text.get_height() // 2
            screen.blit(randomize_text, (text_x, text_y))
            return
        
        # Normal mode: three buttons visible
        # Cancel button
        cancel_color = Colors.BUTTON_HOVER if self.hovered_cancel else Colors.BUTTON_BG
        pygame.draw.rect(screen, cancel_color, self.cancel_rect)
        pygame.draw.rect(screen, Colors.PANEL_BORDER, self.cancel_rect, 2)
        
        cancel_text = self.button_font.render("Cancel", True, Colors.WHITE)
        text_x = self.cancel_rect.centerx - cancel_text.get_width() // 2
        text_y = self.cancel_rect.centery - cancel_text.get_height() // 2
        screen.blit(cancel_text, (text_x, text_y))
        
        # Apply button
        apply_color = Colors.BUTTON_HOVER if self.hovered_apply else Colors.BUTTON_BG
        pygame.draw.rect(screen, apply_color, self.apply_rect)
        pygame.draw.rect(screen, Colors.TEXT_ORANGE, self.apply_rect, 2)
        
        apply_text = self.button_font.render("Apply Changes", True, Colors.TEXT_ORANGE)
        text_x = self.apply_rect.centerx - apply_text.get_width() // 2
        text_y = self.apply_rect.centery - apply_text.get_height() // 2
        screen.blit(apply_text, (text_x, text_y))
        
        # Randomize button
        randomize_color = Colors.BUTTON_HOVER if self.hovered_randomize else Colors.BUTTON_BG
        pygame.draw.rect(screen, randomize_color, self.randomize_rect)
        pygame.draw.rect(screen, Colors.TEXT_YELLOW, self.randomize_rect, 2)
        
        randomize_text = self.button_font.render("Randomize", True, Colors.TEXT_YELLOW)
        text_x = self.randomize_rect.centerx - randomize_text.get_width() // 2
        text_y = self.randomize_rect.centery - randomize_text.get_height() // 2
        screen.blit(randomize_text, (text_x, text_y))
    
    def _draw_preview_direction_arrows(self, screen: pygame.Surface) -> None:
        """Draw direction arrows and label below the character preview."""
        # Loading status or direction label
        if self._loading_sprites:
            label_text = "Loading..."
        else:
            current_direction = self.DIRECTION_CYCLE[self.preview_direction_idx]
            label_text = self.DIRECTION_LABELS[current_direction]
        
        label_surface = self.field_font.render(label_text, True, Colors.TEXT_YELLOW)
        label_x = self.preview_rect.centerx - label_surface.get_width() // 2
        label_y = self.preview_rect.bottom - 35
        screen.blit(label_surface, (label_x, label_y))
        
        # Left arrow button
        left_color = Colors.BUTTON_HOVER if self.hovered_preview_arrow == 'left' else Colors.BUTTON_BG
        pygame.draw.rect(screen, left_color, self.preview_left_arrow_rect)
        pygame.draw.rect(screen, Colors.PANEL_BORDER, self.preview_left_arrow_rect, 1)
        if self.hovered_preview_arrow == 'left':
            pygame.draw.rect(screen, Colors.STONE_HIGHLIGHT, self.preview_left_arrow_rect.inflate(-2, -2), 1)
        
        left_arrow_surface = self.arrow_font.render("<", True, Colors.TEXT_WHITE)
        left_arrow_x = self.preview_left_arrow_rect.centerx - left_arrow_surface.get_width() // 2
        left_arrow_y = self.preview_left_arrow_rect.centery - left_arrow_surface.get_height() // 2
        screen.blit(left_arrow_surface, (left_arrow_x, left_arrow_y))
        
        # Right arrow button
        right_color = Colors.BUTTON_HOVER if self.hovered_preview_arrow == 'right' else Colors.BUTTON_BG
        pygame.draw.rect(screen, right_color, self.preview_right_arrow_rect)
        pygame.draw.rect(screen, Colors.PANEL_BORDER, self.preview_right_arrow_rect, 1)
        if self.hovered_preview_arrow == 'right':
            pygame.draw.rect(screen, Colors.STONE_HIGHLIGHT, self.preview_right_arrow_rect.inflate(-2, -2), 1)
        
        right_arrow_surface = self.arrow_font.render(">", True, Colors.TEXT_WHITE)
        right_arrow_x = self.preview_right_arrow_rect.centerx - right_arrow_surface.get_width() // 2
        right_arrow_y = self.preview_right_arrow_rect.centery - right_arrow_surface.get_height() // 2
        screen.blit(right_arrow_surface, (right_arrow_x, right_arrow_y))
