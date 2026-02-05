"""
Service for managing player equipment.
"""

from typing import Optional, TYPE_CHECKING, Dict, Any
from dataclasses import dataclass

from ..core.config import settings
from ..core.items import ItemCategory
from ..core.skills import SkillType
from ..core.logging_config import get_logger
from ..core.concurrency import PlayerLockManager, LockType
_lock_manager = PlayerLockManager()
from ..schemas.item import (
    ItemStats,
    OperationResult,
    OperationType,
    EquipmentData,
    EquipmentSlotData,
    EquipmentSlot,
    ItemInfo,
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


class EquipmentService:
    """Service for managing player equipment."""

    @staticmethod
    async def get_equipment(player_id: int) -> EquipmentData:
        """
        Get all equipped items for a player.

        Args:
            player_id: Player ID

        Returns:
            EquipmentData with all slots and total stats
        """
        equipment_mgr = get_equipment_manager()
        equipment_data = await equipment_mgr.get_equipment(player_id)
        
        slots = []
        for slot in EquipmentSlot:
            if equipment_data and slot.value in equipment_data:
                slot_data = equipment_data[slot.value]
                item_id = slot_data["item_id"]
                
                item_wrapper = await ItemService.get_item_by_id(item_id)
                if item_wrapper:
                    item_info = ItemService.item_to_info(item_wrapper._data)
                    slots.append(
                        EquipmentSlotData(
                            slot=slot,
                            item=item_info,
                            quantity=slot_data.get("quantity", 1),
                            current_durability=slot_data.get("current_durability"),
                        )
                    )
                else:
                    slots.append(EquipmentSlotData(slot=slot, item=None))
            else:
                slots.append(EquipmentSlotData(slot=slot, item=None))
        
        total_stats = await EquipmentService.get_total_stats(player_id)
        
        return EquipmentData(slots=slots, total_stats=total_stats)



    @staticmethod
    async def get_equipped_in_slot(
        player_id: int, slot: EquipmentSlot
    ) -> Optional[EquipmentSlotData]:
        """
        Get the item equipped in a specific slot.

        Args:
            player_id: Player ID
            slot: Equipment slot

        Returns:
            EquipmentSlotData if slot is occupied, None if empty
        """
        equipment_mgr = get_equipment_manager()
        slot_data = await equipment_mgr.get_equipment_slot(player_id, slot.value)
        
        if not slot_data:
            return None
            
        item_wrapper = await ItemService.get_item_by_id(slot_data["item_id"])
        if not item_wrapper:
            return None
        
        item_info = ItemService.item_to_info(item_wrapper._data)
        return EquipmentSlotData(
            slot=slot,
            item=item_info,
            quantity=slot_data.get("quantity", 1),
            current_durability=slot_data.get("current_durability"),
        )

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
        base_hp = await SkillService.get_skill_level(player_id, SkillType.HITPOINTS)

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
    async def can_equip(player_id: int, item_data: Dict[str, Any]) -> OperationResult:
        """
        Check if player meets skill requirements to equip an item.

        Args:
            player_id: Player ID
            item_data: Item data dict from ItemService

        Returns:
            OperationResult with can_equip in data dict
        """
        if not item_data.get("equipment_slot"):
            return OperationResult(
                success=False,
                message="Item is not equipable",
                operation=OperationType.EQUIP,
                data={"can_equip": False}
            )

        if not item_data.get("required_skill"):
            return OperationResult(
                success=True,
                message="OK",
                operation=OperationType.EQUIP,
                data={"can_equip": True}
            )

        required_skill = item_data.get("required_skill")
        if not required_skill or not isinstance(required_skill, str):
            return OperationResult(
                success=True,
                message="OK",
                operation=OperationType.EQUIP,
                data={"can_equip": True}
            )

        skill_type = SkillType.from_name(required_skill)
        if not skill_type:
            logger.warning(
                "Unknown skill requirement",
                extra={"required_skill": required_skill}
            )
            return OperationResult(
                success=True,
                message="OK",
                operation=OperationType.EQUIP,
                data={"can_equip": True}
            )

        current_level = await SkillService.get_skill_level(player_id, skill_type)

        required_level = item_data.get("required_level", 1)
        if current_level < required_level:
            return OperationResult(
                success=False,
                message=f"Requires {required_skill} level {required_level} (you have {current_level})",
                operation=OperationType.EQUIP,
                data={"can_equip": False}
            )

        return OperationResult(
            success=True,
            message="OK",
            operation=OperationType.EQUIP,
            data={"can_equip": True}
        )

    @staticmethod
    async def equip_from_inventory(
        player_id: int, inventory_slot: int
    ) -> OperationResult:
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
            OperationResult with status and updated stats
        """
        async with _lock_manager.acquire_player_lock(
            player_id, LockType.EQUIPMENT, "equip_from_inventory"
        ):
            equipment_mgr = get_equipment_manager()
        
            inv = await InventoryService.get_item_at_slot(player_id, inventory_slot)
        if not inv:
            return OperationResult(
                success=False,
                message="Inventory slot is empty",
                operation=OperationType.EQUIP
            )

        item_wrapper = await ItemService.get_item_by_id(inv.item.id)
        if not item_wrapper:
            return OperationResult(
                success=False,
                message="Item not found",
                operation=OperationType.EQUIP
            )

        item_data = item_wrapper._data

        if not item_data.get("equipment_slot"):
            return OperationResult(
                success=False,
                message="Item cannot be equipped",
                operation=OperationType.EQUIP
            )

        can_equip_result = await EquipmentService.can_equip(player_id, item_data)
        if not can_equip_result.data.get("can_equip"):
            return OperationResult(
                success=False,
                message=can_equip_result.message,
                operation=OperationType.EQUIP
            )

        equipment_slot = EquipmentSlot(item_data.get("equipment_slot"))
        unequipped_item_id = None

        is_stackable_ammo = (
            item_data.get("category") == ItemCategory.AMMUNITION.value
            and item_data.get("max_stack_size", 1) > 1
            and equipment_slot == EquipmentSlot.AMMO
        )

        current_equipped = await EquipmentService.get_equipped_in_slot(
            player_id, equipment_slot
        )

        if is_stackable_ammo and current_equipped and current_equipped.item and current_equipped.item.id == item_data.get("id"):
            max_stack = item_data.get("max_stack_size", 1)
            current_qty = current_equipped.quantity
            add_qty = inv.quantity
            
            new_total = current_qty + add_qty
            
            if new_total <= max_stack:
                current_durability = current_equipped.current_durability or 1.0
                await equipment_mgr.set_equipment_slot(
                    player_id, equipment_slot.value, item_data.get("id"), new_total, current_durability
                )
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
                
                return OperationResult(
                    success=True,
                    message=f"Added {add_qty} {item_data.get('display_name')} (now {new_total})",
                    operation=OperationType.EQUIP,
                    data={"slot": equipment_slot.value, "stat_changes": updated_stats}
                )
            else:
                amount_to_add = max_stack - current_qty
                remaining_qty = new_total - max_stack
                
                current_durability = current_equipped.current_durability or 1.0
                await equipment_mgr.set_equipment_slot(
                    player_id, equipment_slot.value, item_data.get("id"), max_stack, current_durability
                )
                
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
                
                return OperationResult(
                    success=True,
                    message=f"Added {amount_to_add} {item_data.get('display_name')} (stack full at {max_stack}, {remaining_qty} remain in inventory)",
                    operation=OperationType.EQUIP,
                    data={"slot": equipment_slot.value, "stat_changes": updated_stats}
                )

        items_to_unequip = []

        if item_data.get("is_two_handed") and equipment_slot == EquipmentSlot.WEAPON:
            shield = await EquipmentService.get_equipped_in_slot(
                player_id, EquipmentSlot.SHIELD
            )
            if shield and shield.item:
                items_to_unequip.append(shield)

        if equipment_slot == EquipmentSlot.SHIELD:
            weapon = await EquipmentService.get_equipped_in_slot(
                player_id, EquipmentSlot.WEAPON
            )
            if weapon and weapon.item:
                weapon_item_wrapper = await ItemService.get_item_by_id(weapon.item.id)
                if weapon_item_wrapper and weapon_item_wrapper.get("is_two_handed"):
                    items_to_unequip.append(weapon)

        if current_equipped and current_equipped.item:
            items_to_unequip.append(current_equipped)

        slots_needed = len(items_to_unequip)
        slots_available = 1

        if slots_needed > slots_available:
            inv_count = await InventoryService.get_inventory_count(player_id)
            max_slots = settings.INVENTORY_MAX_SLOTS
            free_slots = max_slots - inv_count
            if free_slots + 1 < slots_needed:
                return OperationResult(
                    success=False,
                    message="Not enough inventory space to unequip items",
                    operation=OperationType.EQUIP
                )

        equip_quantity = inv.quantity
        await InventoryService.remove_item(player_id, inventory_slot, equip_quantity)

        for eq in items_to_unequip:
            if eq.item:
                unequip_qty = eq.quantity
                
                try:
                    eq_slot = EquipmentSlot(eq.slot.value)
                    await equipment_mgr.delete_equipment_slot(player_id, eq_slot.value)
                except ValueError:
                    logger.warning(
                        "Unknown equipment slot during unequip",
                        extra={"player_id": player_id, "slot": eq.slot.value}
                    )

                add_result = await InventoryService.add_item(
                    player_id=player_id,
                    item_id=eq.item.id,
                    quantity=unequip_qty,
                    durability=eq.current_durability,
                )
                if add_result.success and add_result.data.get("overflow_quantity", 0) == 0:
                    unequipped_item_id = eq.item.id

        await equipment_mgr.set_equipment_slot(
            player_id, 
            equipment_slot.value, 
            item_data.get("id"), 
            equip_quantity if is_stackable_ammo else 1,
            float(inv.current_durability) if inv.current_durability is not None else 1.0
        )

        health_bonus_gained = item_data.get("health_bonus", 0)
        health_bonus_lost = 0
        for eq in items_to_unequip:
            if eq.item:
                eq_item_wrapper = await ItemService.get_item_by_id(eq.item.id)
                if eq_item_wrapper and eq_item_wrapper.get("health_bonus"):
                    health_bonus_lost += eq_item_wrapper.get("health_bonus", 0)

        net_health_change = health_bonus_gained - health_bonus_lost
        if net_health_change != 0:
            from .hp_service import HpService
            
            current_hp, max_hp = await HpService.get_hp(player_id)
            if net_health_change > 0:
                new_hp = current_hp + net_health_change
            else:
                new_hp = max(1, min(current_hp + net_health_change, max_hp))
            
            await HpService.set_hp(player_id, new_hp)

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

        return OperationResult(
            success=True,
            message=f"Equipped {item_data.get('display_name')}" + (f" x{equip_quantity}" if is_stackable_ammo and equip_quantity > 1 else ""),
            operation=OperationType.EQUIP,
            data={"slot": equipment_slot.value, "unequipped_item_id": unequipped_item_id, "stat_changes": updated_stats}
        )

    @staticmethod
    async def unequip_to_inventory(
        player_id: int,
        equipment_slot: EquipmentSlot,
        map_id: Optional[str] = None,
        player_x: Optional[int] = None,
        player_y: Optional[int] = None,
    ) -> OperationResult:
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
            OperationResult with status
        """
        equipment_mgr = get_equipment_manager()
        
        equipped = await EquipmentService.get_equipped_in_slot(
            player_id, equipment_slot
        )
        if not equipped or not equipped.item:
            return OperationResult(
                success=False,
                message="Nothing equipped in that slot",
                operation=OperationType.UNEQUIP
            )

        item_wrapper = await ItemService.get_item_by_id(equipped.item.id)
        if not item_wrapper:
            return OperationResult(
                success=False,
                message="Item not found",
                operation=OperationType.UNEQUIP
            )
            
        quantity = equipped.quantity

        add_result = await InventoryService.add_item(
            player_id=player_id,
            item_id=equipped.item.id,
            quantity=quantity,
            durability=equipped.current_durability,
        )

        if add_result.success and add_result.data.get("overflow_quantity", 0) == 0:
            health_bonus_lost = item_wrapper.get("health_bonus", 0)
            
            await equipment_mgr.delete_equipment_slot(player_id, equipment_slot.value)

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
                    "to_inventory_slot": add_result.data.get("slot"),
                    "quantity": quantity,
                },
            )

            return OperationResult(
                success=True,
                message=f"Unequipped {item_wrapper.get('display_name')}" + (f" x{quantity}" if quantity > 1 else ""),
                operation=OperationType.UNEQUIP,
                data={"slot": equipment_slot.value, "inventory_slot": add_result.data.get("slot"), "stat_changes": updated_stats}
            )

        if map_id is not None and player_x is not None and player_y is not None:
            dropped_quantity = quantity if not add_result.success else add_result.data.get("overflow_quantity", 0)

            ground_item_id = await GroundItemService.create_ground_item(
                item_id=equipped.item.id,
                map_id=map_id,
                x=player_x,
                y=player_y,
                quantity=dropped_quantity,
                dropped_by=player_id,
                current_durability=equipped.current_durability,
            )

            if ground_item_id:
                health_bonus_lost = item_wrapper.get("health_bonus", 0)
                
                await equipment_mgr.delete_equipment_slot(player_id, equipment_slot.value)

                if health_bonus_lost > 0:
                    from .hp_service import HpService
                    
                    current_hp, max_hp = await HpService.get_hp(player_id)
                    new_hp = max(1, min(current_hp - health_bonus_lost, max_hp))
                    await HpService.set_hp(player_id, new_hp)

                updated_stats = await EquipmentService.get_total_stats(player_id)

                if add_result.success and add_result.data.get("overflow_quantity", 0) > 0:
                    logger.info(
                        "Unequipped item partially to inventory, rest dropped",
                        extra={
                            "player_id": player_id,
                            "slot": equipment_slot.value,
                            "to_inventory_qty": quantity - dropped_quantity,
                            "dropped_qty": dropped_quantity,
                        },
                    )
                    
                    return OperationResult(
                        success=True,
                        message=f"Unequipped {item_wrapper.get('display_name')} ({quantity - dropped_quantity} to inventory, {dropped_quantity} dropped)",
                        operation=OperationType.UNEQUIP,
                        data={"slot": equipment_slot.value, "inventory_slot": add_result.data.get("slot"), "stat_changes": updated_stats}
                    )
                else:
                    logger.info(
                        "Unequipped item dropped to ground (inventory full)",
                        extra={
                            "player_id": player_id,
                            "slot": equipment_slot.value,
                            "ground_item_id": ground_item_id,
                            "quantity": dropped_quantity,
                        },
                    )
                    
                    return OperationResult(
                        success=True,
                        message=f"Inventory full - {item_wrapper.get('display_name')} dropped to ground",
                        operation=OperationType.UNEQUIP,
                        data={"slot": equipment_slot.value, "ground_item_id": ground_item_id, "stat_changes": updated_stats}
                    )

        return OperationResult(
            success=False,
            message="Inventory is full",
            operation=OperationType.UNEQUIP
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

        if equipped.current_durability is None or not equipped.item:
            return None

        item_wrapper = await ItemService.get_item_by_id(equipped.item.id)
        if not item_wrapper:
            return None

        if item_wrapper.get("is_indestructible", False):
            return equipped.current_durability

        amount = amount * settings.EQUIPMENT_DURABILITY_LOSS_PER_HIT
        new_durability = max(0, equipped.current_durability - amount)
        
        await equipment_mgr.set_equipment_slot(
            player_id,
            slot.value,
            equipped.item.id,
            equipped.quantity,
            int(new_durability)
        )

        if new_durability == 0:
            logger.warning(
                "Equipment broke",
                extra={
                    "player_id": player_id,
                    "slot": slot.value,
                    "item_id": equipped.item.id,
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
        if not equipped or not equipped.item:
            return (False, 0)

        if equipped.current_durability is None:
            return (False, 0)

        item_wrapper = await ItemService.get_item_by_id(equipped.item.id)
        if not item_wrapper or item_wrapper.get("max_durability") is None:
            return (False, 0)

        damage_percent = 1 - (equipped.current_durability / item_wrapper.get("max_durability"))
        repair_cost = int(
            item_wrapper.get("value", 0)
            * settings.EQUIPMENT_REPAIR_COST_MULTIPLIER
            * damage_percent
        )

        await equipment_mgr.set_equipment_slot(
            player_id,
            slot.value,
            equipped.item.id,
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
            await equipment_mgr.delete_equipment_slot(player_id, EquipmentSlot.AMMO.value)

            if equipped.item:
                logger.info(
                    "Ammo depleted",
                    extra={
                        "player_id": player_id,
                        "item_id": equipped.item.id,
                    },
                )
            return (True, 0)

        if equipped.item:
            await equipment_mgr.set_equipment_slot(
                player_id,
                EquipmentSlot.AMMO.value,
                equipped.item.id,
                new_quantity,
                float(equipped.current_durability) if equipped.current_durability else 0.0
            )

            logger.debug(
                "Consumed ammo",
                extra={
                    "player_id": player_id,
                    "item_id": equipped.item.id,
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
    async def get_all_equipped_items(player_id: int) -> list[EquipmentSlotData]:
        """
        Get all equipped items with their item data.

        Args:
            player_id: Player ID

        Returns:
            List of EquipmentSlotData objects
        """
        equipment_mgr = get_equipment_manager()
        equipment_data = await equipment_mgr.get_equipment(player_id)
        
        if not equipment_data:
            return []
        
        equipped_items = []
        for slot_name, slot_data in equipment_data.items():
            item_id = slot_data["item_id"]
            
            item_wrapper = await ItemService.get_item_by_id(item_id)
            if item_wrapper:
                item_info = ItemService.item_to_info(item_wrapper._data)
                eq = EquipmentSlotData(
                    slot=EquipmentSlot(slot_name),
                    item=item_info,
                    quantity=slot_data.get("quantity", 1),
                    current_durability=slot_data.get("current_durability"),
                )
                equipped_items.append(eq)
                
        return equipped_items
