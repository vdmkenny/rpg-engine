"""
Service for managing player equipment.
"""

from typing import Optional, TYPE_CHECKING, Dict, Any
from dataclasses import dataclass

from ..core.config import settings
from ..core.items import EquipmentSlot, ItemCategory
from ..core.skills import SkillType
from ..core.logging_config import get_logger
from ..schemas.item import (
    ItemStats,
    EquipItemResult,
    UnequipItemResult,
    EquipmentSlotInfo,
    EquipmentResponse,
    CanEquipResult,
)
from .item_service import ItemService
from .inventory_service import InventoryService
from .ground_item_service import GroundItemService
from .skill_service import SkillService
from .game_state import (
    get_equipment_manager,
    get_reference_data_manager,
)

if TYPE_CHECKING:
    from .hp_service import HpService

logger = get_logger(__name__)


@dataclass
class EquipmentItem:
    """Pure data structure for equipped items (replaces PlayerEquipment ORM model)."""
    player_id: int
    equipment_slot: str
    item_id: int
    quantity: int
    current_durability: Optional[int]
    item_data: Dict[str, Any]  # Item metadata from ItemService
    
    def get_stats(self) -> ItemStats:
        """Get item stats for this equipment piece."""
        return ItemStats(
            attack_bonus=self.item_data.get("attack_bonus", 0),
            strength_bonus=self.item_data.get("strength_bonus", 0),
            physical_defence_bonus=self.item_data.get("physical_defence_bonus", 0),
            ranged_attack_bonus=self.item_data.get("ranged_attack_bonus", 0),
            ranged_strength_bonus=self.item_data.get("ranged_strength_bonus", 0),
            magic_attack_bonus=self.item_data.get("magic_attack_bonus", 0),
            magic_damage_bonus=self.item_data.get("magic_damage_bonus", 0),
            magic_defence_bonus=self.item_data.get("magic_defence_bonus", 0),
            health_bonus=self.item_data.get("health_bonus", 0),
            speed_bonus=self.item_data.get("speed_bonus", 0),
            mining_bonus=self.item_data.get("mining_bonus", 0),
            woodcutting_bonus=self.item_data.get("woodcutting_bonus", 0),
            fishing_bonus=self.item_data.get("fishing_bonus", 0),
        )


class EquipmentService:
    """Service for managing player equipment."""

    @staticmethod
    async def get_equipment_raw(player_id: int) -> dict[str, dict]:
        """
        Get raw equipment data for a player (for game loop rendering).

        This method returns the raw dict format without converting to
        EquipmentItem objects, optimized for high-frequency game loop calls.

        Args:
            player_id: Player ID

        Returns:
            Dictionary mapping slot name to raw equipment data dict
        """
        equipment_mgr = get_equipment_manager()
        return await equipment_mgr.get_equipment(player_id) or {}

    @staticmethod
    async def get_equipment(player_id: int) -> dict[str, EquipmentItem]:
        """
        Get all equipped items for a player.

        Args:
            player_id: Player ID

        Returns:
            Dictionary mapping slot name to EquipmentItem
        """
        # Get all equipment data for player
        equipment_mgr = get_equipment_manager()
        equipment_data = await equipment_mgr.get_equipment(player_id)
        
        if not equipment_data:
            return {}
            
        # Convert raw data to structured equipment objects with metadata
        equipment = {}
        for slot, slot_data in equipment_data.items():
            item_id = slot_data["item_id"]
            
            # Get item metadata for equipped item
            item_wrapper = await ItemService.get_item_by_id(item_id)
            if item_wrapper:
                # Create structured equipment business object
                eq = EquipmentItem(
                    player_id=player_id,
                    equipment_slot=slot,
                    item_id=item_id,
                    quantity=slot_data.get("quantity", 1),
                    current_durability=slot_data.get("current_durability"),
                    item_data=item_wrapper._data  # Raw dict from ItemService
                )
                equipment[slot] = eq
                
        return equipment

    @staticmethod
    async def get_equipment_response(player_id: int) -> EquipmentResponse:
        """
        Get full equipment state for API response.

        Args:
            player_id: Player ID

        Returns:
            EquipmentResponse with all slots and total stats
        """
        equipment = await EquipmentService.get_equipment(player_id)
        
        total_stats = await EquipmentService.get_total_stats(player_id)

        slots = []
        for slot in EquipmentSlot:
            eq = equipment.get(slot.value)
            if eq:
                item_info = ItemService.item_to_info(eq.item_data)
                slots.append(
                    EquipmentSlotInfo(
                        slot=slot.value,
                        item=item_info,
                        quantity=eq.quantity,
                        current_durability=eq.current_durability,
                    )
                )
            else:
                slots.append(EquipmentSlotInfo(slot=slot.value, item=None))

        return EquipmentResponse(slots=slots, total_stats=total_stats)

    @staticmethod
    async def get_equipped_in_slot(
        player_id: int, slot: EquipmentSlot
    ) -> Optional[EquipmentItem]:
        """
        Get the item equipped in a specific slot.

        Args:
            player_id: Player ID
            slot: Equipment slot

        Returns:
            EquipmentItem if slot is occupied, None if empty
        """
        # Use EquipmentManager for all equipment access (online/offline transparent)
        equipment_mgr = get_equipment_manager()
        slot_data = await equipment_mgr.get_equipment_slot(player_id, slot.value)
        
        if not slot_data:
            return None
            
        # Get item metadata for equipped item
        item_wrapper = await ItemService.get_item_by_id(slot_data["item_id"])
        if not item_wrapper:
            return None
            
        # Create structured equipment business object
        eq = EquipmentItem(
            player_id=player_id,
            equipment_slot=slot.value,
            item_id=slot_data["item_id"],
            quantity=slot_data.get("quantity", 1),
            current_durability=slot_data.get("current_durability"),
            item_data=item_wrapper._data  # Extract raw dict from ItemWrapper
        )
        return eq

    @staticmethod
    def _calculate_stats_from_equipment(equipment_data: Dict[str, Dict[str, Any]]) -> ItemStats:
        """
        Calculate total stats from equipment data.
        
        Helper method for testing - calculates stats from equipment dict
        without requiring database access.
        
        Args:
            equipment_data: Dict mapping slot names to item data dicts
            
        Returns:
            ItemStats with aggregated values
        """
        stats = ItemStats()
        
        for slot_data in equipment_data.values():
            if slot_data:
                stats.attack_bonus += slot_data.get("attack_bonus", 0)
                stats.strength_bonus += slot_data.get("strength_bonus", 0)
                stats.ranged_attack_bonus += slot_data.get("ranged_attack_bonus", 0)
                stats.ranged_strength_bonus += slot_data.get("ranged_strength_bonus", 0)
                stats.magic_attack_bonus += slot_data.get("magic_attack_bonus", 0)
                stats.magic_damage_bonus += slot_data.get("magic_damage_bonus", 0)
                stats.physical_defence_bonus += slot_data.get("physical_defence_bonus", 0)
                stats.magic_defence_bonus += slot_data.get("magic_defence_bonus", 0)
                stats.health_bonus += slot_data.get("health_bonus", 0)
                stats.speed_bonus += slot_data.get("speed_bonus", 0)
        
        return stats

    @staticmethod
    async def get_total_stats(player_id: int) -> ItemStats:
        """
        Calculate total stats from all equipped items.

        Sums all stat bonuses across equipment slots.
        Negative stats reduce totals.

        Args:
            player_id: Player ID

        Returns:
            ItemStats with aggregated values
        """
        # Get all equipment data for stat calculation
        equipment_mgr = get_equipment_manager()
        equipment_data = await equipment_mgr.get_equipment(player_id)
        if not equipment_data:
            return ItemStats()
        
        # Calculate total stats from equipped items
        item_ids = [slot_data["item_id"] for slot_data in equipment_data.values()]
        if not item_ids:
            return ItemStats()
        
        # Get item statistics for calculation
        items_stats = {}
        ref_mgr = get_reference_data_manager()
        for item_id in item_ids:
            item_info = ref_mgr.get_cached_item_meta(item_id)
            if item_info:
                items_stats[item_id] = item_info
        
        # Use helper method for calculation
        return EquipmentService._calculate_stats_from_equipment(items_stats)

    @staticmethod
    async def get_max_hp(player_id: int) -> int:
        """
        Calculate max HP for a player.

        Max HP = Hitpoints skill level + equipment health_bonus.

        Reads from managers (Valkey cache) for online players.

        Args:
            player_id: Player ID

        Returns:
            Maximum HP value
        """
        from server.src.core.skills import HITPOINTS_START_LEVEL

        equipment_mgr = get_equipment_manager()
        ref_mgr = get_reference_data_manager()

        # Get base HP from Hitpoints skill level
        base_hp = await SkillService.get_skill_level(player_id, SkillType.HITPOINTS.name.lower())

        # Calculate equipment health bonuses for HP calculation
        equipment = await equipment_mgr.get_equipment(player_id)
        if not equipment:
            return base_hp

        # Get item metadata for health bonus calculation
        health_bonus = 0
        for slot_data in equipment.values():
            item_meta = ref_mgr.get_cached_item_meta(slot_data["item_id"])
            if item_meta and item_meta.get("health_bonus"):
                health_bonus += item_meta["health_bonus"]

        return base_hp + health_bonus

    @staticmethod
    async def adjust_hp_for_equip(player_id: int, health_bonus: int) -> int:
        """
        Adjust player's current HP when equipping item with health bonus.

        Equipping adds to both max HP and current HP.

        Args:
            player_id: Player ID
            health_bonus: Health bonus from the equipped item

        Returns:
            New current HP value
        """
        if health_bonus <= 0:
            return -1  # No adjustment needed

        from .hp_service import HpService
        
        # Get current HP for player
        current_hp, max_hp = await HpService.get_hp(player_id)
        new_hp = current_hp + health_bonus
        
        # Update player's current HP
        await HpService.set_hp(player_id, new_hp)

        logger.info(
            "Adjusted HP for equip",
            extra={
                "player_id": player_id,
                "health_bonus": health_bonus,
                "new_current_hp": new_hp,
            },
        )

        return new_hp

    @staticmethod
    async def adjust_hp_for_unequip(player_id: int, health_bonus: int) -> int:
        """
        Reduce player's current health when removing equipment that provided health bonus.

        Unequipping removes from current HP, capped at new max HP.
        Current HP will never drop below 1 from unequipping.

        Args:
            player_id: Player ID
            health_bonus: Health bonus from the unequipped item

        Returns:
            New current HP value
        """
        if health_bonus <= 0:
            return -1  # No adjustment needed

        from .hp_service import HpService

        # Calculate new max HP (after unequipping, so without this item's bonus)
        new_max_hp = await EquipmentService.get_max_hp(player_id)

        # Get current HP for player
        current_hp, _ = await HpService.get_hp(player_id)

        # Remove health bonus from current HP, cap at new max, min 1
        new_current_hp = current_hp - health_bonus
        new_current_hp = max(1, min(new_current_hp, new_max_hp))

        await HpService.set_hp(player_id, new_current_hp)

        logger.info(
            "Adjusted HP for unequip",
            extra={
                "player_id": player_id,
                "health_bonus": health_bonus,
                "new_current_hp": new_current_hp,
                "new_max_hp": new_max_hp,
            },
        )

        return new_current_hp

    @staticmethod
    async def can_equip(player_id: int, item_data: Dict[str, Any]) -> CanEquipResult:
        """
        Check if player meets skill requirements to equip an item.

        Args:
            player_id: Player ID
            item_data: Item data dict from ItemService

        Returns:
            CanEquipResult with status and reason
        """
        if not item_data.get("equipment_slot"):
            return CanEquipResult(can_equip=False, reason="Item is not equipable")

        if not item_data.get("required_skill"):
            return CanEquipResult(can_equip=True, reason="OK")

        required_skill = item_data.get("required_skill")
        if not required_skill or not isinstance(required_skill, str):
            return CanEquipResult(can_equip=True, reason="OK")

        # Convert skill name string to SkillType enum
        skill_type = SkillType.from_name(required_skill)
        if not skill_type:
            logger.warning(
                "Unknown skill requirement",
                extra={"required_skill": required_skill}
            )
            return CanEquipResult(can_equip=True, reason="OK")

        # Check skill level for equipment requirements
        current_level = await SkillService.get_skill_level(player_id, skill_type.name.lower())

        required_level = item_data.get("required_level", 1)
        if current_level < required_level:
            return CanEquipResult(
                can_equip=False,
                reason=f"Requires {required_skill} level {required_level} (you have {current_level})",
            )

        return CanEquipResult(can_equip=True, reason="OK")

    @staticmethod
    async def equip_from_inventory(
        player_id: int, inventory_slot: int
    ) -> EquipItemResult:
        """
        Equip an item from the player's inventory.

        Handles:
        - Requirement checks
        - Two-handed weapon logic (unequips shield)
        - Shield with two-handed equipped (unequips weapon)
        - Swapping currently equipped item to inventory
        - Stackable ammunition (adds to existing stack if same type)

        Args:
            player_id: Player ID
            inventory_slot: Inventory slot containing item to equip

        Returns:
            EquipItemResult with status and updated stats
        """
        equipment_mgr = get_equipment_manager()
        
        # Get item from inventory
        inv = await InventoryService.get_item_at_slot(player_id, inventory_slot)
        if not inv:
            return EquipItemResult(success=False, message="Inventory slot is empty")

        item_wrapper = await ItemService.get_item_by_id(inv.item_id)
        if not item_wrapper:
            return EquipItemResult(success=False, message="Item not found")

        # Check if item is equipable
        if not item_wrapper.get("equipment_slot"):
            return EquipItemResult(success=False, message="Item cannot be equipped")

        # Check requirements
        can_equip = await EquipmentService.can_equip(player_id, item_wrapper._data)
        if not can_equip.can_equip:
            return EquipItemResult(success=False, message=can_equip.reason)

        equipment_slot = EquipmentSlot(item_data.get("equipment_slot"))
        unequipped_item_id = None

        # Check if this is stackable ammunition
        is_stackable_ammo = (
            item_data.get("category") == ItemCategory.AMMUNITION.value
            and item_data.get("max_stack_size", 1) > 1
            and equipment_slot == EquipmentSlot.AMMO
        )

        # Get currently equipped item in target slot
        current_equipped = await EquipmentService.get_equipped_in_slot(
            player_id, equipment_slot
        )

        # Handle stackable ammunition - add to existing stack if same item
        if is_stackable_ammo and current_equipped and current_equipped.item_id == item_data.get("id"):
            # Same ammo type already equipped - add to stack
            max_stack = item_data.get("max_stack_size", 1)
            current_qty = current_equipped.quantity
            add_qty = inv.quantity
            
            new_total = current_qty + add_qty
            
            if new_total <= max_stack:
                # All ammo fits in equipped stack
                # Update equipment (preserving durability)
                current_durability = current_equipped.current_durability or 1.0
                await equipment_mgr.set_equipment_slot(
                    player_id, equipment_slot.value, item_data.get("id"), new_total, current_durability
                )
                # Remove the inventory item using service layer
                await InventoryService.remove_item(player_id, inventory_slot, add_qty)
                
                updated_stats = await EquipmentService.get_total_stats(player_id)
                
                logger.info(
                    "Added ammo to equipped stack",
                    extra={
                        "player_id": player_id,
                        "item_id": item_data.get("id"),
                        "added_qty": add_qty,
                        "new_total": new_total,
                    },
                )
                
                return EquipItemResult(
                    success=True,
                    message=f"Added {add_qty} {item_data.get('display_name')} (now {new_total})",
                    updated_stats=updated_stats,
                )
            else:
                # Partial fit - equip what we can, leave rest in inventory
                amount_to_add = max_stack - current_qty
                remaining_qty = new_total - max_stack
                
                # Update equipment to max stack
                current_durability = current_equipped.current_durability or 1.0
                await equipment_mgr.set_equipment_slot(
                    player_id, equipment_slot.value, item_data.get("id"), max_stack, current_durability
                )
                
                # Remove amount_to_add from inventory (leaving remaining_qty)
                await InventoryService.remove_item(player_id, inventory_slot, amount_to_add)
                
                updated_stats = await EquipmentService.get_total_stats(player_id)
                
                logger.info(
                    "Partially added ammo to equipped stack",
                    extra={
                        "player_id": player_id,
                        "item_id": item_data.get("id"),
                        "added_qty": amount_to_add,
                        "remaining_in_inv": remaining_qty,
                    },
                )
                
                return EquipItemResult(
                    success=True,
                    message=f"Added {amount_to_add} {item_data.get('display_name')} (stack full at {max_stack}, {remaining_qty} remain in inventory)",
                    updated_stats=updated_stats,
                )

        # Handle two-handed weapon logic
        items_to_unequip = []

        if item_data.get("is_two_handed") and equipment_slot == EquipmentSlot.WEAPON:
            # Unequip shield if equipping two-handed weapon
            shield = await EquipmentService.get_equipped_in_slot(
                player_id, EquipmentSlot.SHIELD
            )
            if shield:
                items_to_unequip.append(shield)

        if equipment_slot == EquipmentSlot.SHIELD:
            # Check if current weapon is two-handed
            weapon = await EquipmentService.get_equipped_in_slot(
                player_id, EquipmentSlot.WEAPON
            )
            if weapon:
                weapon_item_wrapper = await ItemService.get_item_by_id(weapon.item_id)
                if weapon_item_wrapper and weapon_item_wrapper.get("is_two_handed"):
                    items_to_unequip.append(weapon)

        # Add currently equipped item to unequip list (if different from what we're equipping)
        if current_equipped:
            items_to_unequip.append(current_equipped)

        # Check if we have inventory space for all items to unequip
        # We'll be freeing one slot (the one we're equipping from)
        slots_needed = len(items_to_unequip)
        slots_available = 1  # The slot we're equipping from

        if slots_needed > slots_available:
            # Check for additional free slots
            inv_count = await InventoryService.get_inventory_count(player_id)
            max_slots = settings.INVENTORY_MAX_SLOTS
            free_slots = max_slots - inv_count
            # We get back 1 slot from removing the item we're equipping
            if free_slots + 1 < slots_needed:
                return EquipItemResult(
                    success=False,
                    message="Not enough inventory space to unequip items",
                )

        # Remove item from inventory
        equip_quantity = inv.quantity  # For stackable ammo
        await InventoryService.remove_item(player_id, inventory_slot, equip_quantity)

        # Unequip items that need to be moved to inventory
        for eq in items_to_unequip:
            unequip_qty = eq.quantity  # Preserve quantity for ammo
            
            # Remove from equipment
            try:
                eq_slot = EquipmentSlot(eq.equipment_slot)
                await equipment_mgr.delete_equipment_slot(player_id, eq_slot.value)
            except ValueError:
                logger.warning(
                    "Unknown equipment slot during unequip",
                    extra={"player_id": player_id, "slot": eq.equipment_slot}
                )

            # Add to inventory using service
            add_result = await InventoryService.add_item(
                player_id=player_id,
                item_id=eq.item_id,
                quantity=unequip_qty,
                durability=eq.current_durability,
            )
            if add_result.success and add_result.overflow_quantity == 0:
                unequipped_item_id = eq.item_id

        # Equip the new item
        await equipment_mgr.set_equipment_slot(
            player_id, 
            equipment_slot.value, 
            item_data.get("id"), 
            equip_quantity if is_stackable_ammo else 1,
            float(inv.durability) if inv.durability is not None else 1.0
        )

        # Handle HP adjustment for health bonus changes
        health_bonus_gained = item_data.get("health_bonus", 0)
        health_bonus_lost = 0
        for eq in items_to_unequip:
            eq_item_wrapper = await ItemService.get_item_by_id(eq.item_id)
            if eq_item_wrapper and eq_item_wrapper.get("health_bonus"):
                health_bonus_lost += eq_item_wrapper.get("health_bonus", 0)

        net_health_change = health_bonus_gained - health_bonus_lost
        if net_health_change != 0:
            from .hp_service import HpService
            
            current_hp, max_hp = await HpService.get_hp(player_id)
            if net_health_change > 0:
                # Gained health bonus - add to current HP
                new_hp = current_hp + net_health_change
            else:
                # Lost health bonus - reduce current HP, minimum 1
                new_hp = max(1, min(current_hp + net_health_change, max_hp))
            
            await HpService.set_hp(player_id, new_hp)

        # Get updated stats for return value
        updated_stats = await EquipmentService.get_total_stats(player_id)

        logger.info(
            "Equipped item",
            extra={
                "player_id": player_id,
                "item_id": item_data.get("id"),
                "slot": equipment_slot.value,
                "quantity": equip_quantity if is_stackable_ammo else 1,
            },
        )

        return EquipItemResult(
            success=True,
            message=f"Equipped {item_data.get('display_name')}" + (f" x{equip_quantity}" if is_stackable_ammo and equip_quantity > 1 else ""),
            unequipped_item_id=unequipped_item_id,
            updated_stats=updated_stats,
        )

    @staticmethod
    async def unequip_to_inventory(
        player_id: int,
        equipment_slot: EquipmentSlot,
        map_id: Optional[str] = None,
        player_x: Optional[int] = None,
        player_y: Optional[int] = None,
    ) -> UnequipItemResult:
        """
        Move an equipped item to inventory, or drop to ground if inventory full.

        For stackable items (ammo), attempts to merge with existing inventory stacks.
        If inventory is full and player position is provided, drops to ground.

        Args:
            player_id: Player ID
            equipment_slot: Slot to unequip from
            map_id: Optional map ID for dropping to ground if inventory full
            player_x: Optional player X position for dropping
            player_y: Optional player Y position for dropping

        Returns:
            UnequipItemResult with status
        """
        equipment_mgr = get_equipment_manager()
        
        # Get equipped item
        equipped = await EquipmentService.get_equipped_in_slot(
            player_id, equipment_slot
        )
        if not equipped:
            return UnequipItemResult(
                success=False,
                message="Nothing equipped in that slot",
            )

        item_wrapper = await ItemService.get_item_by_id(equipped.item_id)
        if not item_wrapper:
            return UnequipItemResult(
                success=False,
                message="Item not found",
            )
            
        quantity = equipped.quantity  # Preserve quantity for stackable items (ammo)

        # Try to add to inventory (handles stacking for stackable items)
        add_result = await InventoryService.add_item(
            player_id=player_id,
            item_id=equipped.item_id,
            quantity=quantity,
            durability=equipped.current_durability,
        )

        if add_result.success and add_result.overflow_quantity == 0:
            # Successfully added all to inventory
            health_bonus_lost = item_wrapper.get("health_bonus", 0)
            
            # Remove from equipment
            await equipment_mgr.delete_equipment_slot(player_id, equipment_slot.value)

            # Handle HP adjustment for health_bonus loss
            if health_bonus_lost > 0:
                from .hp_service import HpService
                
                current_hp, max_hp = await HpService.get_hp(player_id)
                new_hp = max(1, min(current_hp - health_bonus_lost, max_hp))
                await HpService.set_hp(player_id, new_hp)

            updated_stats = await EquipmentService.get_total_stats(player_id)

            logger.info(
                "Unequipped item to inventory",
                extra={
                    "player_id": player_id,
                    "slot": equipment_slot.value,
                    "to_inventory_slot": add_result.slot,
                    "quantity": quantity,
                },
            )

            return UnequipItemResult(
                success=True,
                message=f"Unequipped {item_wrapper.get('display_name')}" + (f" x{quantity}" if quantity > 1 else ""),
                inventory_slot=add_result.slot,
                updated_stats=updated_stats,
            )

        # Inventory full or partial - try to drop to ground
        if map_id is not None and player_x is not None and player_y is not None:
            # Determine how many need to be dropped
            dropped_quantity = quantity if not add_result.success else add_result.overflow_quantity

            ground_item_id = await GroundItemService.create_ground_item(
                item_id=equipped.item_id,
                map_id=map_id,
                x=player_x,
                y=player_y,
                quantity=dropped_quantity,
                dropped_by=player_id,
                current_durability=equipped.current_durability,
            )

            if ground_item_id:
                health_bonus_lost = item_wrapper.get("health_bonus", 0)
                
                # Remove from equipment
                await equipment_mgr.delete_equipment_slot(player_id, equipment_slot.value)

                # Handle HP adjustment for health_bonus loss
                if health_bonus_lost > 0:
                    from .hp_service import HpService
                    
                    current_hp, max_hp = await HpService.get_hp(player_id)
                    new_hp = max(1, min(current_hp - health_bonus_lost, max_hp))
                    await HpService.set_hp(player_id, new_hp)

                updated_stats = await EquipmentService.get_total_stats(player_id)

                if add_result.success and add_result.overflow_quantity > 0:
                    # Partial inventory, rest dropped
                    logger.info(
                        "Unequipped item partially to inventory, rest dropped",
                        extra={
                            "player_id": player_id,
                            "slot": equipment_slot.value,
                            "to_inventory_qty": quantity - dropped_quantity,
                            "dropped_qty": dropped_quantity,
                        },
                    )
                    
                    return UnequipItemResult(
                        success=True,
                        message=f"Unequipped {item_wrapper.get('display_name')} ({quantity - dropped_quantity} to inventory, {dropped_quantity} dropped)",
                        inventory_slot=add_result.slot,
                        updated_stats=updated_stats,
                    )
                else:
                    # All dropped to ground
                    logger.info(
                        "Unequipped item dropped to ground (inventory full)",
                        extra={
                            "player_id": player_id,
                            "slot": equipment_slot.value,
                            "ground_item_id": ground_item_id,
                            "quantity": dropped_quantity,
                        },
                    )
                    
                    return UnequipItemResult(
                        success=True,
                        message=f"Inventory full - {item_wrapper.get('display_name')} dropped to ground",
                        inventory_slot=None,
                        updated_stats=updated_stats,
                    )

        # No position provided and inventory full - fail
        return UnequipItemResult(
            success=False,
            message="Inventory is full",
        )

    @staticmethod
    async def degrade_equipment(
        player_id: int,
        slot: EquipmentSlot,
        amount: int = 1,
    ) -> Optional[int]:
        """
        Reduce durability of an equipped item.

        Args:
            player_id: Player ID
            slot: Equipment slot
            amount: Amount to reduce (default 1)

        Returns:
            Remaining durability, or None if item broke/doesn't have durability
        """
        equipment_mgr = get_equipment_manager()
        equipped = await EquipmentService.get_equipped_in_slot(player_id, slot)
        if not equipped:
            return None

        if equipped.current_durability is None:
            return None  # Item has no durability

        item_wrapper = await ItemService.get_item_by_id(equipped.item_id)
        if not item_wrapper:
            return None

        if item_wrapper.get("is_indestructible", False):
            return equipped.current_durability  # Item cannot degrade

        amount = amount * settings.EQUIPMENT_DURABILITY_LOSS_PER_HIT
        new_durability = max(0, equipped.current_durability - amount)
        
        # Update durability
        await equipment_mgr.set_equipment_slot(
            player_id,
            slot.value,
            equipped.item_id,
            equipped.quantity,
            int(new_durability)
        )

        if new_durability == 0:
            # Item broke - move to inventory in broken state
            # (or could be destroyed - depends on game design)
            logger.warning(
                "Equipment broke",
                extra={
                    "player_id": player_id,
                    "slot": slot.value,
                    "item_id": equipped.item_id,
                },
            )

        return new_durability

    @staticmethod
    async def repair_equipment(
        player_id: int,
        slot: EquipmentSlot,
    ) -> tuple[bool, int]:
        """
        Restore an equipped item to full durability.

        Args:
            player_id: Player ID
            slot: Equipment slot

        Returns:
            Tuple of (success, repair_cost)
        """
        equipment_mgr = get_equipment_manager()
        equipped = await EquipmentService.get_equipped_in_slot(player_id, slot)
        if not equipped:
            return (False, 0)

        if equipped.current_durability is None:
            return (False, 0)  # Item has no durability

        item_wrapper = await ItemService.get_item_by_id(equipped.item_id)
        if not item_wrapper or item_wrapper.get("max_durability") is None:
            return (False, 0)

        # Calculate repair cost
        damage_percent = 1 - (equipped.current_durability / item_wrapper.get("max_durability"))
        repair_cost = int(
            item_wrapper.get("value", 0)
            * settings.EQUIPMENT_REPAIR_COST_MULTIPLIER
            * damage_percent
        )

        # Update durability to max
        await equipment_mgr.set_equipment_slot(
            player_id,
            slot.value,
            equipped.item_id,
            equipped.quantity,
            float(item_wrapper.get("max_durability"))
        )

        logger.info(
            "Repaired equipment",
            extra={
                "player_id": player_id,
                "slot": slot.value,
                "cost": repair_cost,
            },
        )

        return (True, repair_cost)

    @staticmethod
    async def consume_ammo(
        player_id: int,
        amount: int = 1,
    ) -> tuple[bool, int]:
        """
        Consume ammunition from the equipped AMMO slot.

        Used when firing ranged weapons. Reduces quantity by amount.
        If quantity reaches 0, removes the equipment entry.

        Args:
            player_id: Player ID
            amount: Number of ammo to consume (default 1)

        Returns:
            Tuple of (success, remaining_quantity)
            Returns (False, 0) if no ammo equipped or not enough ammo
        """
        equipment_mgr = get_equipment_manager()
        equipped = await EquipmentService.get_equipped_in_slot(
            player_id, EquipmentSlot.AMMO
        )
        if not equipped:
            return (False, 0)

        if equipped.quantity < amount:
            return (False, equipped.quantity)

        new_quantity = equipped.quantity - amount

        if new_quantity == 0:
            # No ammo left - remove from equipment
            await equipment_mgr.delete_equipment_slot(player_id, EquipmentSlot.AMMO.value)

            logger.info(
                "Ammo depleted",
                extra={
                    "player_id": player_id,
                    "item_id": equipped.item_id,
                },
            )
            return (True, 0)

        # Update quantity
        await equipment_mgr.set_equipment_slot(
            player_id,
            EquipmentSlot.AMMO.value,
            equipped.item_id,
            new_quantity,
            float(equipped.current_durability) if equipped.current_durability else 0.0
        )

        logger.debug(
            "Consumed ammo",
            extra={
                "player_id": player_id,
                "item_id": equipped.item_id,
                "consumed": amount,
                "remaining": new_quantity,
            },
        )

        return (True, new_quantity)

    @staticmethod
    async def clear_equipment(player_id: int) -> int:
        """
        Remove all equipped items (for death drops).

        Args:
            player_id: Player ID

        Returns:
            Number of items unequipped
        """
        equipment_mgr = get_equipment_manager()
        
        # Get all equipment first to count items
        equipment = await equipment_mgr.get_equipment(player_id)
        if not equipment:
            return 0
        
        item_count = len(equipment)
        
        # Clear all equipment
        await equipment_mgr.clear_equipment(player_id)
        
        return item_count

    @staticmethod
    async def get_all_equipped_items(player_id: int) -> list[EquipmentItem]:
        """
        Get all equipped items with their item data.

        Args:
            player_id: Player ID

        Returns:
            List of EquipmentItem objects
        """
        equipment_mgr = get_equipment_manager()
        equipment_data = await equipment_mgr.get_equipment(player_id)
        
        if not equipment_data:
            return []
        
        # Build list of EquipmentItem objects using ItemService
        equipped_items = []
        for slot, slot_data in equipment_data.items():
            item_id = slot_data["item_id"]
            
            # Use ItemService for item data (service-first architecture)
            item_wrapper = await ItemService.get_item_by_id(item_id)
            if item_wrapper:
                # Create EquipmentItem business object
                eq = EquipmentItem(
                    player_id=player_id,
                    equipment_slot=slot,
                    item_id=item_id,
                    quantity=slot_data.get("quantity", 1),
                    current_durability=slot_data.get("current_durability"),
                    item_data=item_wrapper._data  # Raw dict from ItemService
                )
                equipped_items.append(eq)
                
        return equipped_items
