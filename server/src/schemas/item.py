"""
Pydantic schemas for items, inventory, equipment, and ground items.
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional


class ItemStats(BaseModel):
    """Stats provided by an item. All values can be negative."""

    # Combat offensive
    attack_bonus: int = Field(default=0, description="Melee accuracy bonus")
    strength_bonus: int = Field(default=0, description="Melee damage bonus")
    ranged_attack_bonus: int = Field(default=0, description="Ranged accuracy bonus")
    ranged_strength_bonus: int = Field(default=0, description="Ranged damage bonus")
    magic_attack_bonus: int = Field(default=0, description="Magic accuracy bonus")
    magic_damage_bonus: int = Field(default=0, description="Magic damage bonus")

    # Combat defensive
    physical_defence_bonus: int = Field(default=0, description="Physical defence bonus")
    magic_defence_bonus: int = Field(default=0, description="Magic defence bonus")

    # Other
    health_bonus: int = Field(default=0, description="Max HP bonus")
    speed_bonus: int = Field(default=0, description="Movement/attack speed bonus")

    # Gathering
    mining_bonus: int = Field(default=0, description="Mining speed bonus")
    woodcutting_bonus: int = Field(default=0, description="Woodcutting speed bonus")
    fishing_bonus: int = Field(default=0, description="Fishing speed bonus")


class ItemInfo(BaseModel):
    """Item definition for client display."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str = Field(..., description="Internal item name (e.g., 'bronze_sword')")
    display_name: str = Field(..., description="Display name (e.g., 'Bronze Sword')")
    description: str = Field(default="", description="Item description")
    category: str = Field(..., description="Item category")
    rarity: str = Field(..., description="Item rarity")
    rarity_color: str = Field(..., description="Hex color for rarity display")
    equipment_slot: Optional[str] = Field(default=None, description="Equipment slot if equipable")
    max_stack_size: int = Field(..., description="Maximum stack size (1 = not stackable)")
    is_two_handed: bool = Field(default=False, description="Requires both hands")
    max_durability: Optional[int] = Field(default=None, description="Max durability if applicable")
    is_indestructible: bool = Field(default=False, description="Cannot be destroyed by durability loss")
    required_skill: Optional[str] = Field(default=None, description="Skill required to equip")
    required_level: int = Field(default=1, description="Level required to equip")
    is_tradeable: bool = Field(default=True, description="Can be traded with other players")
    value: int = Field(default=0, description="Base gold value")
    stats: ItemStats = Field(default_factory=ItemStats, description="Item stat bonuses")

    @property
    def is_stackable(self) -> bool:
        """Returns True if item can stack (max_stack_size > 1)."""
        return self.max_stack_size > 1


class InventorySlotInfo(BaseModel):
    """Single inventory slot with item and quantity."""

    model_config = ConfigDict(from_attributes=True)

    slot: int = Field(..., ge=0, description="Inventory slot number (0-27)")
    item: ItemInfo = Field(..., description="Item in this slot")
    quantity: int = Field(..., ge=1, description="Number of items in stack")
    current_durability: Optional[int] = Field(default=None, description="Current durability if applicable")


class InventoryResponse(BaseModel):
    """Full inventory state for a player."""

    slots: list[InventorySlotInfo] = Field(default_factory=list, description="Occupied inventory slots")
    max_slots: int = Field(..., description="Maximum number of inventory slots")
    used_slots: int = Field(..., ge=0, description="Number of occupied slots")
    free_slots: int = Field(..., ge=0, description="Number of empty slots")


class EquipmentSlotInfo(BaseModel):
    """Single equipment slot with optional item."""

    model_config = ConfigDict(from_attributes=True)

    slot: str = Field(..., description="Equipment slot name (e.g., 'weapon', 'head')")
    item: Optional[ItemInfo] = Field(default=None, description="Equipped item or None if empty")
    quantity: int = Field(default=1, ge=1, description="Number of items (for stackable ammo)")
    current_durability: Optional[int] = Field(default=None, description="Current durability if applicable")


class EquipmentResponse(BaseModel):
    """Full equipment state for a player."""

    slots: list[EquipmentSlotInfo] = Field(..., description="All equipment slots")
    total_stats: ItemStats = Field(..., description="Aggregated stats from all equipped items")


class GroundItemInfo(BaseModel):
    """Ground item visible to a player."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Ground item ID for pickup")
    item: ItemInfo = Field(..., description="Item information")
    x: int = Field(..., description="Tile X position")
    y: int = Field(..., description="Tile Y position")
    quantity: int = Field(..., ge=1, description="Number of items in stack")
    is_yours: bool = Field(..., description="True if dropped by this player")
    is_protected: bool = Field(..., description="True if still in loot protection period")


class GroundItemsResponse(BaseModel):
    """Ground items visible to a player in their area."""

    items: list[GroundItemInfo] = Field(default_factory=list, description="Visible ground items")
    map_id: str = Field(..., description="Map ID")


# ============================================================================
# Request/Response schemas for operations
# ============================================================================


class AddItemResult(BaseModel):
    """Result of adding an item to inventory."""

    success: bool = Field(..., description="Whether the operation succeeded")
    message: str = Field(..., description="Success or error message")
    slot: Optional[int] = Field(default=None, description="Slot where item was added")
    overflow_quantity: int = Field(default=0, description="Quantity that didn't fit")


class RemoveItemResult(BaseModel):
    """Result of removing an item from inventory."""

    success: bool = Field(..., description="Whether the operation succeeded")
    message: str = Field(..., description="Success or error message")
    removed_quantity: int = Field(default=0, description="Quantity actually removed")


class MoveItemResult(BaseModel):
    """Result of moving an item within inventory."""

    success: bool = Field(..., description="Whether the operation succeeded")
    message: str = Field(..., description="Success or error message")


class EquipItemResult(BaseModel):
    """Result of equipping an item."""

    success: bool = Field(..., description="Whether the operation succeeded")
    message: str = Field(..., description="Success or error message")
    unequipped_item_id: Optional[int] = Field(
        default=None, description="Item ID that was unequipped and moved to inventory"
    )
    updated_stats: Optional[ItemStats] = Field(
        default=None, description="New total stats after equipping"
    )


class UnequipItemResult(BaseModel):
    """Result of unequipping an item."""

    success: bool = Field(..., description="Whether the operation succeeded")
    message: str = Field(..., description="Success or error message")
    inventory_slot: Optional[int] = Field(
        default=None, description="Inventory slot where item was placed"
    )
    updated_stats: Optional[ItemStats] = Field(
        default=None, description="New total stats after unequipping"
    )


class PickupItemResult(BaseModel):
    """Result of picking up a ground item."""

    success: bool = Field(..., description="Whether the operation succeeded")
    message: str = Field(..., description="Success or error message")
    inventory_slot: Optional[int] = Field(
        default=None, description="Inventory slot where item was placed"
    )


class DropItemResult(BaseModel):
    """Result of dropping an item."""

    success: bool = Field(..., description="Whether the operation succeeded")
    message: str = Field(..., description="Success or error message")
    ground_item_id: Optional[int] = Field(
        default=None, description="ID of the created ground item"
    )


class RepairItemResult(BaseModel):
    """Result of repairing an item."""

    success: bool = Field(..., description="Whether the operation succeeded")
    message: str = Field(..., description="Success or error message")
    repair_cost: int = Field(default=0, description="Gold cost of repair")
    new_durability: Optional[int] = Field(
        default=None, description="Durability after repair"
    )


class CanEquipResult(BaseModel):
    """Result of checking if a player can equip an item."""

    can_equip: bool = Field(..., description="Whether the player can equip the item")
    reason: str = Field(..., description="Reason if cannot equip, or 'OK' if can")


class SortInventoryResult(BaseModel):
    """Result of sorting inventory."""

    success: bool = Field(..., description="Whether the operation succeeded")
    message: str = Field(..., description="Success or error message")
    items_moved: int = Field(default=0, description="Number of items that changed position")
    stacks_merged: int = Field(default=0, description="Number of stacks that were merged")


class MergeStacksResult(BaseModel):
    """Result of merging split stacks."""

    success: bool = Field(..., description="Whether the operation succeeded")
    message: str = Field(..., description="Success or error message")
    stacks_merged: int = Field(default=0, description="Number of stacks that were merged")
    slots_freed: int = Field(default=0, description="Number of inventory slots freed up")
