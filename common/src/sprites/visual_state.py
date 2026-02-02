"""
VisualState - Complete visual representation of a character.

Combines AppearanceData (body/skin/hair/eyes) with equipment visuals
for a complete picture of how a character should be rendered.

The hash of VisualState is used for efficient network broadcasting.

License: Part of the LPC sprite integration.
See server/sprites/CREDITS.csv for sprite attribution.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict
import hashlib
import json

from .appearance import AppearanceData
from .enums import EquipmentSlot


@dataclass(frozen=True)
class EquippedVisuals:
    """
    Visual representation of equipped items.
    
    Maps equipment slots to sprite sheet identifiers.
    Only contains the visual information needed for rendering,
    not the full item data.
    
    This class is immutable (frozen=True) to ensure hash stability.
    
    Attributes:
        head: Helmet/hat sprite ID
        body: Chest armor/robe sprite ID
        legs: Leg armor/pants sprite ID
        feet: Boots/shoes sprite ID
        hands: Gloves/gauntlets sprite ID
        main_hand: Primary weapon sprite ID
        off_hand: Shield/offhand weapon sprite ID
        back: Cape/backpack/quiver sprite ID
        belt: Belt accessory sprite ID
        
        *_tint: Optional hex color for client-side tinting.
                Used when LPC doesn't provide native color variants.
    """
    # Sprite IDs
    head: Optional[str] = None
    body: Optional[str] = None
    legs: Optional[str] = None
    feet: Optional[str] = None
    hands: Optional[str] = None
    main_hand: Optional[str] = None
    off_hand: Optional[str] = None
    back: Optional[str] = None
    belt: Optional[str] = None
    
    # Tint colors (for client-side recoloring)
    head_tint: Optional[str] = None
    body_tint: Optional[str] = None
    legs_tint: Optional[str] = None
    feet_tint: Optional[str] = None
    hands_tint: Optional[str] = None
    main_hand_tint: Optional[str] = None
    off_hand_tint: Optional[str] = None
    back_tint: Optional[str] = None
    belt_tint: Optional[str] = None
    
    def to_dict(self) -> dict:
        """
        Convert to dictionary, excluding None values.
        
        Returns:
            Dictionary with only the equipped slots (non-None values).
            Includes tint fields when present.
        """
        return {
            k: v for k, v in {
                "head": self.head,
                "body": self.body,
                "legs": self.legs,
                "feet": self.feet,
                "hands": self.hands,
                "main_hand": self.main_hand,
                "off_hand": self.off_hand,
                "back": self.back,
                "belt": self.belt,
                "head_tint": self.head_tint,
                "body_tint": self.body_tint,
                "legs_tint": self.legs_tint,
                "feet_tint": self.feet_tint,
                "hands_tint": self.hands_tint,
                "main_hand_tint": self.main_hand_tint,
                "off_hand_tint": self.off_hand_tint,
                "back_tint": self.back_tint,
                "belt_tint": self.belt_tint,
            }.items() if v is not None
        }
    
    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "EquippedVisuals":
        """
        Create EquippedVisuals from a dictionary.
        
        Args:
            data: Dictionary with equipment slot -> sprite ID mappings.
                  May also include *_tint fields for tint colors.
            
        Returns:
            EquippedVisuals instance.
        """
        if data is None:
            return cls()
        
        return cls(
            head=data.get("head"),
            body=data.get("body"),
            legs=data.get("legs"),
            feet=data.get("feet"),
            hands=data.get("hands"),
            main_hand=data.get("main_hand"),
            off_hand=data.get("off_hand"),
            back=data.get("back"),
            belt=data.get("belt"),
            head_tint=data.get("head_tint"),
            body_tint=data.get("body_tint"),
            legs_tint=data.get("legs_tint"),
            feet_tint=data.get("feet_tint"),
            hands_tint=data.get("hands_tint"),
            main_hand_tint=data.get("main_hand_tint"),
            off_hand_tint=data.get("off_hand_tint"),
            back_tint=data.get("back_tint"),
            belt_tint=data.get("belt_tint"),
        )
    
    @classmethod
    def from_equipment_map(cls, equipment: Optional[Dict[str, dict]]) -> "EquippedVisuals":
        """
        Create EquippedVisuals from a full equipment map.
        
        Extracts sprite_id from each equipped item's data, and looks up
        any required tint colors from the equipment mapping.
        
        Args:
            equipment: Dict mapping slot names to item data dicts.
                       Each item dict should have a 'sprite_id' key.
            
        Returns:
            EquippedVisuals instance with sprite IDs and tints.
        """
        if equipment is None:
            return cls()
        
        # Import here to avoid circular dependency
        from .equipment_mapping import get_equipment_sprite
        
        def get_sprite_id(slot_name: str) -> Optional[str]:
            item = equipment.get(slot_name)
            if item is None:
                return None
            return item.get("sprite_id") or item.get("sprite_sheet_id")
        
        def get_tint(slot_name: str) -> Optional[str]:
            item = equipment.get(slot_name)
            if item is None:
                return None
            sprite_id = item.get("sprite_id") or item.get("sprite_sheet_id")
            if sprite_id is None:
                return None
            sprite_info = get_equipment_sprite(sprite_id)
            if sprite_info is None:
                return None
            return sprite_info.tint
        
        return cls(
            head=get_sprite_id("head"),
            body=get_sprite_id("body"),
            legs=get_sprite_id("legs"),
            feet=get_sprite_id("feet"),
            hands=get_sprite_id("hands"),
            main_hand=get_sprite_id("main_hand"),
            off_hand=get_sprite_id("off_hand"),
            back=get_sprite_id("back"),
            belt=get_sprite_id("belt"),
            head_tint=get_tint("head"),
            body_tint=get_tint("body"),
            legs_tint=get_tint("legs"),
            feet_tint=get_tint("feet"),
            hands_tint=get_tint("hands"),
            main_hand_tint=get_tint("main_hand"),
            off_hand_tint=get_tint("off_hand"),
            back_tint=get_tint("back"),
            belt_tint=get_tint("belt"),
        )
    
    def is_empty(self) -> bool:
        """Check if no equipment is equipped."""
        return all(v is None for v in [
            self.head, self.body, self.legs, self.feet,
            self.hands, self.main_hand, self.off_hand, self.back, self.belt
        ])
    
    def get_slot(self, slot: EquipmentSlot) -> Optional[str]:
        """
        Get the sprite ID for a specific slot.
        
        Args:
            slot: The equipment slot to query.
            
        Returns:
            Sprite ID or None if slot is empty.
        """
        slot_map = {
            EquipmentSlot.HEAD: self.head,
            EquipmentSlot.BODY: self.body,
            EquipmentSlot.LEGS: self.legs,
            EquipmentSlot.FEET: self.feet,
            EquipmentSlot.HANDS: self.hands,
            EquipmentSlot.MAIN_HAND: self.main_hand,
            EquipmentSlot.OFF_HAND: self.off_hand,
            EquipmentSlot.BACK: self.back,
            EquipmentSlot.BELT: self.belt,
        }
        return slot_map.get(slot)
    
    def get_slot_tint(self, slot: EquipmentSlot) -> Optional[str]:
        """
        Get the tint color for a specific slot.
        
        Args:
            slot: The equipment slot to query.
            
        Returns:
            Hex color string or None if no tint.
        """
        tint_map = {
            EquipmentSlot.HEAD: self.head_tint,
            EquipmentSlot.BODY: self.body_tint,
            EquipmentSlot.LEGS: self.legs_tint,
            EquipmentSlot.FEET: self.feet_tint,
            EquipmentSlot.HANDS: self.hands_tint,
            EquipmentSlot.MAIN_HAND: self.main_hand_tint,
            EquipmentSlot.OFF_HAND: self.off_hand_tint,
            EquipmentSlot.BACK: self.back_tint,
            EquipmentSlot.BELT: self.belt_tint,
        }
        return tint_map.get(slot)


@dataclass(frozen=True)
class VisualState:
    """
    Complete visual state of a character.
    
    Combines appearance (body/skin/hair/eyes) with equipment for
    the full visual representation. The hash of this state is used
    for efficient network broadcasting.
    
    This class is immutable (frozen=True) to ensure hash stability.
    
    Attributes:
        appearance: Base character appearance
        equipment: Currently equipped items' visual data
    """
    appearance: AppearanceData = field(default_factory=AppearanceData)
    equipment: EquippedVisuals = field(default_factory=EquippedVisuals)
    
    def to_dict(self) -> dict:
        """
        Convert to dictionary for JSON/network serialization.
        
        Returns:
            Dictionary with appearance and equipment sub-dicts.
        """
        return {
            "appearance": self.appearance.to_dict(),
            "equipment": self.equipment.to_dict(),
        }
    
    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "VisualState":
        """
        Create VisualState from a dictionary.
        
        Args:
            data: Dictionary with 'appearance' and 'equipment' keys.
            
        Returns:
            VisualState instance.
        """
        if data is None:
            return cls()
        
        return cls(
            appearance=AppearanceData.from_dict(data.get("appearance")),
            equipment=EquippedVisuals.from_dict(data.get("equipment")),
        )
    
    def compute_hash(self) -> str:
        """
        Compute a stable hash for this complete visual state.
        
        The hash is deterministic - same visual state always produces same hash.
        Used for efficient network broadcasting (send hash instead of full data
        when the visual state hasn't changed).
        
        Returns:
            12-character hexadecimal hash string.
        """
        data_str = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.md5(data_str.encode()).hexdigest()[:12]
    
    def with_appearance(self, appearance: AppearanceData) -> "VisualState":
        """
        Create a new VisualState with different appearance.
        
        Args:
            appearance: New appearance data.
            
        Returns:
            New VisualState with updated appearance.
        """
        return VisualState(appearance=appearance, equipment=self.equipment)
    
    def with_equipment(self, equipment: EquippedVisuals) -> "VisualState":
        """
        Create a new VisualState with different equipment.
        
        Args:
            equipment: New equipment data.
            
        Returns:
            New VisualState with updated equipment.
        """
        return VisualState(appearance=self.appearance, equipment=equipment)
    
    @classmethod
    def from_appearance_and_equipment_map(
        cls,
        appearance: Optional[dict],
        equipment: Optional[Dict[str, dict]],
    ) -> "VisualState":
        """
        Create VisualState from raw appearance dict and equipment map.
        
        Convenience method for server-side construction from database data.
        
        Args:
            appearance: Raw appearance dictionary from database.
            equipment: Equipment map from EquipmentService.
            
        Returns:
            VisualState instance.
        """
        return cls(
            appearance=AppearanceData.from_dict(appearance),
            equipment=EquippedVisuals.from_equipment_map(equipment),
        )
