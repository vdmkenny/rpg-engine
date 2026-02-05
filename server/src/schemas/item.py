"""
Pydantic models for item and inventory data.

Consolidated schemas with enums for MMORPG item system.
Replaces all *Result schemas with OperationResult.
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from enum import Enum


class ItemCategory(str, Enum):
    """Item categorization for organization and UI."""
    NORMAL = "normal"
    TOOL = "tool"
    WEAPON = "weapon"
    ARMOR = "armor"
    CONSUMABLE = "consumable"
    QUEST = "quest"
    MATERIAL = "material"
    CURRENCY = "currency"
    AMMUNITION = "ammunition"


class ItemRarity(str, Enum):
    """Item rarity tiers affecting drop rates and UI colors.
    
    Modern str-based enum for JSON serialization with color metadata.
    """
    POOR = "poor"
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"
    
    @property
    def color(self) -> str:
        """Get the hex color for this rarity tier."""
        colors = {
            "poor": "#9d9d9d",      # Gray - vendor trash
            "common": "#ffffff",     # White - basic items
            "uncommon": "#1eff00",   # Green - slightly better
            "rare": "#0070dd",       # Blue - good items
            "epic": "#a335ee",       # Purple - excellent items
            "legendary": "#ff8000",  # Orange - best items
        }
        return colors.get(self.value, "#ffffff")
    
    @classmethod
    def from_value(cls, value: str) -> "ItemRarity":
        """Look up ItemRarity by its string value.
        
        Args:
            value: The rarity string (e.g., "common", "rare")
            
        Returns:
            The matching ItemRarity enum member
            
        Raises:
            ValueError: If no matching rarity is found
        """
        try:
            return cls(value)
        except ValueError:
            raise ValueError(f"'{value}' is not a valid ItemRarity")
    
    @classmethod
    def get_color(cls, rarity_value: str, default: str = "#ffffff") -> str:
        """Get the color for a rarity value with a safe fallback.
        
        This is a convenience method that handles missing/invalid rarity values
        gracefully without raising exceptions.
        
        Args:
            rarity_value: The rarity string (e.g., "common", "rare")
            default: Default color to return if rarity is invalid
            
        Returns:
            Hex color string for the rarity
        """
        if not rarity_value:
            return default
        try:
            rarity_enum = cls.from_value(rarity_value)
            return rarity_enum.color
        except ValueError:
            return default


class EquipmentSlot(str, Enum):
    """Equipment slots - 11 total like classic MMORPGs."""
    HEAD = "head"
    CAPE = "cape"
    AMULET = "amulet"
    WEAPON = "weapon"
    BODY = "body"
    SHIELD = "shield"
    LEGS = "legs"
    GLOVES = "gloves"
    BOOTS = "boots"
    RING = "ring"
    AMMO = "ammo"


class OperationType(str, Enum):
    """Operation types for generic result handling."""
    ADD = "add"
    REMOVE = "remove"
    MOVE = "move"
    EQUIP = "equip"
    UNEQUIP = "unequip"
    PICKUP = "pickup"
    DROP = "drop"
    SORT = "sort"
    MERGE = "merge"


class ItemStats(BaseModel):
    """Combat and skill bonuses from items."""
    attack_bonus: int = Field(default=0, description="Melee accuracy bonus")
    strength_bonus: int = Field(default=0, description="Melee damage bonus")
    ranged_attack_bonus: int = Field(default=0, description="Ranged accuracy bonus")
    ranged_strength_bonus: int = Field(default=0, description="Ranged damage bonus")
    magic_attack_bonus: int = Field(default=0, description="Magic accuracy bonus")
    magic_damage_bonus: int = Field(default=0, description="Magic damage bonus")
    physical_defence_bonus: int = Field(default=0, description="Physical defence bonus")
    magic_defence_bonus: int = Field(default=0, description="Magic defence bonus")
    health_bonus: int = Field(default=0, description="Max HP bonus")
    speed_bonus: int = Field(default=0, description="Movement/attack speed bonus")
    mining_bonus: int = Field(default=0, description="Mining speed bonus")
    woodcutting_bonus: int = Field(default=0, description="Woodcutting speed bonus")
    fishing_bonus: int = Field(default=0, description="Fishing speed bonus")


class ItemInfo(BaseModel):
    """
    Complete item definition with sprite IDs for client rendering.
    Includes both inventory icon and equipped paperdoll sprites.
    """
    model_config = ConfigDict(from_attributes=True)
    
    id: int = Field(..., description="Item ID")
    name: str = Field(..., description="Internal item name (e.g., 'bronze_sword')")
    display_name: str = Field(..., description="Display name (e.g., 'Bronze Sword')")
    description: str = Field(default="", description="Item description")
    category: ItemCategory = Field(..., description="Item category")
    rarity: ItemRarity = Field(..., description="Item rarity")
    rarity_color: str = Field(..., description="Hex color for rarity display")
    equipment_slot: Optional[EquipmentSlot] = Field(default=None, description="Equipment slot if equipable")
    max_stack_size: int = Field(..., description="Maximum stack size (1 = not stackable)")
    is_two_handed: bool = Field(default=False, description="Requires both hands")
    max_durability: Optional[int] = Field(default=None, description="Max durability if applicable")
    is_indestructible: bool = Field(default=False, description="Cannot be destroyed by durability loss")
    required_skill: Optional[str] = Field(default=None, description="Skill required to equip")
    required_level: int = Field(default=1, description="Level required to equip")
    is_tradeable: bool = Field(default=True, description="Can be traded with other players")
    value: int = Field(default=0, description="Base gold value")
    ammo_type: Optional[str] = Field(default=None, description="Ammo type for ranged weapons")
    stats: ItemStats = Field(default_factory=ItemStats, description="Item stat bonuses")
    icon_sprite_id: str = Field(..., description="Sprite for inventory/ground display")
    equipped_sprite_id: Optional[str] = Field(default=None, description="Sprite for paperdoll rendering")
    
    @property
    def is_stackable(self) -> bool:
        """Returns True if item can stack (max_stack_size > 1)."""
        return self.max_stack_size > 1


class InventorySlot(BaseModel):
    """Single inventory slot with item data."""
    model_config = ConfigDict(from_attributes=True)
    
    slot: int = Field(..., ge=0, description="Inventory slot number")
    item: ItemInfo = Field(..., description="Item in this slot")
    quantity: int = Field(..., ge=1, description="Number of items in stack")
    current_durability: Optional[int] = Field(default=None, description="Current durability if applicable")


class EquipmentSlotData(BaseModel):
    """Single equipment slot with equipped item."""
    model_config = ConfigDict(from_attributes=True)
    
    slot: EquipmentSlot = Field(..., description="Equipment slot")
    item: Optional[ItemInfo] = Field(default=None, description="Equipped item or None if empty")
    quantity: int = Field(default=1, ge=1, description="Number of items (for stackable ammo)")
    current_durability: Optional[int] = Field(default=None, description="Current durability if applicable")


class InventoryData(BaseModel):
    """Complete inventory for client UI."""
    slots: List[InventorySlot] = Field(default_factory=list, description="Occupied inventory slots")
    max_slots: int = Field(..., description="Maximum number of inventory slots")
    used_slots: int = Field(..., ge=0, description="Number of occupied slots")


class EquipmentData(BaseModel):
    """Complete equipment with total stats."""
    slots: List[EquipmentSlotData] = Field(..., description="All equipment slots")
    total_stats: ItemStats = Field(..., description="Aggregated stats from all equipped items")


class GroundItem(BaseModel):
    """Item on ground at specific tile."""
    model_config = ConfigDict(from_attributes=True)
    
    id: int = Field(..., description="Ground item ID for pickup")
    item: ItemInfo = Field(..., description="Item information")
    x: int = Field(..., description="Tile X position")
    y: int = Field(..., description="Tile Y position")
    quantity: int = Field(..., ge=1, description="Number of items in stack")
    is_yours: bool = Field(..., description="True if dropped by this player")
    is_protected: bool = Field(..., description="True if still in loot protection period")


class OperationResult(BaseModel):
    """
    Generic operation result - replaces all specific result schemas.
    
    Replaces: AddItemResult, RemoveItemResult, MoveItemResult,
             EquipItemResult, UnequipItemResult, PickupItemResult,
             DropItemResult, SortInventoryResult, MergeStacksResult,
             CanEquipResult, RepairItemResult
    
    Operation-specific fields stored in flexible data dict:
    - slot: int (for inventory operations)
    - equipment_slot: EquipmentSlot (for equipment operations)
    - quantity: int (amount changed)
    - overflow_quantity: int (for add operations)
    - removed_quantity: int (for remove operations)
    - stat_changes: ItemStats (for equipment affecting stats)
    - ground_item_id: int (for ground item operations)
    - unequipped_item_id: int (for equip operations)
    - inventory_slot: int (for unequip/pickup operations)
    - items_moved: int (for sort operations)
    - stacks_merged: int (for merge operations)
    - can_equip: bool (for can_equip check)
    - reason: str (for can_equip check)
    """
    success: bool = Field(..., description="Whether the operation succeeded")
    message: str = Field(..., description="Success or error message")
    operation: OperationType = Field(..., description="Type of operation performed")
    data: Dict[str, Any] = Field(default_factory=dict, description="Operation-specific data")
