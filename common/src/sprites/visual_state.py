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
        cape: Cape/cloak sprite ID
        weapon: Primary weapon sprite ID
        body: Chest armor/robe sprite ID
        shield: Shield/offhand weapon sprite ID
        legs: Leg armor/pants sprite ID
        gloves: Gloves/gauntlets sprite ID
        boots: Boots/shoes sprite ID
        ammo: Ammunition (quiver) sprite ID

        *_tint: Optional hex color for client-side tinting.
                Used when LPC doesn't provide native color variants.

    Note: AMULET and RING slots are not visible on paperdoll.
    """
    # Sprite IDs (must match EquipmentSlot enum values)
    head: Optional[str] = None
    cape: Optional[str] = None
    weapon: Optional[str] = None
    body: Optional[str] = None
    shield: Optional[str] = None
    legs: Optional[str] = None
    gloves: Optional[str] = None
    boots: Optional[str] = None
    ammo: Optional[str] = None

    # Tint colors (for client-side recoloring)
    head_tint: Optional[str] = None
    cape_tint: Optional[str] = None
    weapon_tint: Optional[str] = None
    body_tint: Optional[str] = None
    shield_tint: Optional[str] = None
    legs_tint: Optional[str] = None
    gloves_tint: Optional[str] = None
    boots_tint: Optional[str] = None
    ammo_tint: Optional[str] = None

    # Legacy field aliases for backward compatibility during migration
    @property
    def main_hand(self) -> Optional[str]:
        """Alias for weapon slot."""
        return self.weapon

    @property
    def off_hand(self) -> Optional[str]:
        """Alias for shield slot."""
        return self.shield

    @property
    def back(self) -> Optional[str]:
        """Alias for cape slot."""
        return self.cape

    @property
    def hands(self) -> Optional[str]:
        """Alias for gloves slot."""
        return self.gloves

    @property
    def feet(self) -> Optional[str]:
        """Alias for boots slot."""
        return self.boots

    @property
    def belt(self) -> Optional[str]:
        """Legacy belt slot - maps to body."""
        return None

    # Tint property aliases for backward compatibility
    @property
    def main_hand_tint(self) -> Optional[str]:
        """Alias for weapon_tint."""
        return self.weapon_tint

    @property
    def off_hand_tint(self) -> Optional[str]:
        """Alias for shield_tint."""
        return self.shield_tint

    @property
    def back_tint(self) -> Optional[str]:
        """Alias for cape_tint."""
        return self.cape_tint

    @property
    def hands_tint(self) -> Optional[str]:
        """Alias for gloves_tint."""
        return self.gloves_tint

    @property
    def feet_tint(self) -> Optional[str]:
        """Alias for boots_tint."""
        return self.boots_tint

    @property
    def belt_tint(self) -> Optional[str]:
        """Legacy belt tint slot - returns None."""
        return None

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
                "cape": self.cape,
                "weapon": self.weapon,
                "body": self.body,
                "shield": self.shield,
                "legs": self.legs,
                "gloves": self.gloves,
                "boots": self.boots,
                "ammo": self.ammo,
                "head_tint": self.head_tint,
                "cape_tint": self.cape_tint,
                "weapon_tint": self.weapon_tint,
                "body_tint": self.body_tint,
                "shield_tint": self.shield_tint,
                "legs_tint": self.legs_tint,
                "gloves_tint": self.gloves_tint,
                "boots_tint": self.boots_tint,
                "ammo_tint": self.ammo_tint,
            }.items() if v is not None
        }

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "EquippedVisuals":
        """
        Create EquippedVisuals from a dictionary.

        Handles backward compatibility with old slot names:
        - main_hand -> weapon
        - off_hand -> shield
        - back -> cape
        - hands -> gloves
        - feet -> boots

        Args:
            data: Dictionary with equipment slot -> sprite ID mappings.
                  May also include *_tint fields for tint colors.

        Returns:
            EquippedVisuals instance.
        """
        if data is None:
            return cls()

        # Handle backward compatibility for slot names
        def get_slot_value(old_key: str, new_key: str) -> Optional[str]:
            """Get value with old key as fallback."""
            return data.get(new_key) or data.get(old_key)

        return cls(
            head=data.get("head"),
            cape=get_slot_value("back", "cape"),
            weapon=get_slot_value("main_hand", "weapon"),
            body=data.get("body"),
            shield=get_slot_value("off_hand", "shield"),
            legs=data.get("legs"),
            gloves=get_slot_value("hands", "gloves"),
            boots=get_slot_value("feet", "boots"),
            ammo=data.get("ammo"),
            head_tint=data.get("head_tint"),
            cape_tint=get_slot_value("back_tint", "cape_tint"),
            weapon_tint=get_slot_value("main_hand_tint", "weapon_tint"),
            body_tint=data.get("body_tint"),
            shield_tint=get_slot_value("off_hand_tint", "shield_tint"),
            legs_tint=data.get("legs_tint"),
            gloves_tint=get_slot_value("hands_tint", "gloves_tint"),
            boots_tint=get_slot_value("feet_tint", "boots_tint"),
            ammo_tint=data.get("ammo_tint"),
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
            cape=get_sprite_id("cape") or get_sprite_id("back"),
            weapon=get_sprite_id("weapon") or get_sprite_id("main_hand"),
            body=get_sprite_id("body"),
            shield=get_sprite_id("shield") or get_sprite_id("off_hand"),
            legs=get_sprite_id("legs"),
            gloves=get_sprite_id("gloves") or get_sprite_id("hands"),
            boots=get_sprite_id("boots") or get_sprite_id("feet"),
            ammo=get_sprite_id("ammo"),
            head_tint=get_tint("head"),
            cape_tint=get_tint("cape") or get_tint("back"),
            weapon_tint=get_tint("weapon") or get_tint("main_hand"),
            body_tint=get_tint("body"),
            shield_tint=get_tint("shield") or get_tint("off_hand"),
            legs_tint=get_tint("legs"),
            gloves_tint=get_tint("gloves") or get_tint("hands"),
            boots_tint=get_tint("boots") or get_tint("feet"),
            ammo_tint=get_tint("ammo"),
        )

    def is_empty(self) -> bool:
        """Check if no equipment is equipped."""
        return all(v is None for v in [
            self.head, self.cape, self.weapon, self.body, self.shield,
            self.legs, self.gloves, self.boots, self.ammo
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
            EquipmentSlot.CAPE: self.cape,
            EquipmentSlot.WEAPON: self.weapon,
            EquipmentSlot.BODY: self.body,
            EquipmentSlot.SHIELD: self.shield,
            EquipmentSlot.LEGS: self.legs,
            EquipmentSlot.GLOVES: self.gloves,
            EquipmentSlot.BOOTS: self.boots,
            EquipmentSlot.AMMO: self.ammo,
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
            EquipmentSlot.CAPE: self.cape_tint,
            EquipmentSlot.WEAPON: self.weapon_tint,
            EquipmentSlot.BODY: self.body_tint,
            EquipmentSlot.SHIELD: self.shield_tint,
            EquipmentSlot.LEGS: self.legs_tint,
            EquipmentSlot.GLOVES: self.gloves_tint,
            EquipmentSlot.BOOTS: self.boots_tint,
            EquipmentSlot.AMMO: self.ammo_tint,
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
