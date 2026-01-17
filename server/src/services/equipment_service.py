"""
Service for managing player equipment.
"""

import logging
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.config import settings
from ..core.items import EquipmentSlot, ItemCategory
from ..models.item import Item, PlayerEquipment, PlayerInventory
from ..models.player import Player
from ..models.skill import PlayerSkill, Skill
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

logger = logging.getLogger(__name__)


class EquipmentService:
    """Service for managing player equipment."""

    @staticmethod
    async def get_equipment(
        db: AsyncSession, player_id: int
    ) -> dict[str, PlayerEquipment]:
        """
        Get all equipped items for a player.

        Args:
            db: Database session
            player_id: Player ID

        Returns:
            Dictionary mapping slot name to PlayerEquipment
        """
        result = await db.execute(
            select(PlayerEquipment)
            .where(PlayerEquipment.player_id == player_id)
            .options(selectinload(PlayerEquipment.item))
        )
        equipment = result.scalars().all()
        return {eq.equipment_slot: eq for eq in equipment}

    @staticmethod
    async def get_equipment_response(
        db: AsyncSession, player_id: int
    ) -> EquipmentResponse:
        """
        Get full equipment state for API response.

        Args:
            db: Database session
            player_id: Player ID

        Returns:
            EquipmentResponse with all slots and total stats
        """
        equipment = await EquipmentService.get_equipment(db, player_id)
        total_stats = await EquipmentService.get_total_stats(db, player_id)

        slots = []
        for slot in EquipmentSlot:
            eq = equipment.get(slot.value)
            if eq:
                item_info = ItemService.item_to_info(eq.item)
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
        db: AsyncSession, player_id: int, slot: EquipmentSlot
    ) -> Optional[PlayerEquipment]:
        """
        Get the item equipped in a specific slot.

        Args:
            db: Database session
            player_id: Player ID
            slot: Equipment slot

        Returns:
            PlayerEquipment if slot is occupied, None if empty
        """
        result = await db.execute(
            select(PlayerEquipment)
            .where(PlayerEquipment.player_id == player_id)
            .where(PlayerEquipment.equipment_slot == slot.value)
            .options(selectinload(PlayerEquipment.item))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_total_stats(db: AsyncSession, player_id: int) -> ItemStats:
        """
        Calculate total stats from all equipped items.

        Sums all stat bonuses across equipment slots.
        Negative stats reduce totals.

        Args:
            db: Database session
            player_id: Player ID

        Returns:
            ItemStats with aggregated values
        """
        equipment = await EquipmentService.get_equipment(db, player_id)

        stats = ItemStats()
        for eq in equipment.values():
            item = eq.item
            stats.attack_bonus += item.attack_bonus
            stats.strength_bonus += item.strength_bonus
            stats.ranged_attack_bonus += item.ranged_attack_bonus
            stats.ranged_strength_bonus += item.ranged_strength_bonus
            stats.magic_attack_bonus += item.magic_attack_bonus
            stats.magic_damage_bonus += item.magic_damage_bonus
            stats.physical_defence_bonus += item.physical_defence_bonus
            stats.magic_defence_bonus += item.magic_defence_bonus
            stats.health_bonus += item.health_bonus
            stats.speed_bonus += item.speed_bonus
            stats.mining_bonus += item.mining_bonus
            stats.woodcutting_bonus += item.woodcutting_bonus
            stats.fishing_bonus += item.fishing_bonus

        return stats

    @staticmethod
    async def get_max_hp(db: AsyncSession, player_id: int) -> int:
        """
        Calculate max HP for a player.

        Max HP = Hitpoints skill level + equipment health_bonus.

        Args:
            db: Database session
            player_id: Player ID

        Returns:
            Maximum HP value
        """
        # Get base HP from Hitpoints skill level
        base_hp = await SkillService.get_hitpoints_level(db, player_id)

        # Get equipment health bonus
        equipment_stats = await EquipmentService.get_total_stats(db, player_id)
        health_bonus = equipment_stats.health_bonus

        return base_hp + health_bonus

    @staticmethod
    async def adjust_hp_for_equip(
        db: AsyncSession, player_id: int, health_bonus: int
    ) -> int:
        """
        Adjust player's current HP when equipping item with health bonus.

        Equipping adds to both max HP and current HP.

        Args:
            db: Database session
            player_id: Player ID
            health_bonus: Health bonus from the equipped item

        Returns:
            New current HP value
        """
        if health_bonus <= 0:
            return -1  # No adjustment needed

        result = await db.execute(
            select(Player).where(Player.id == player_id)
        )
        player = result.scalar_one_or_none()
        if not player:
            return -1

        # Add health bonus to current HP
        player.current_hp += health_bonus
        await db.commit()

        logger.info(
            "Adjusted HP for equip",
            extra={
                "player_id": player_id,
                "health_bonus": health_bonus,
                "new_current_hp": player.current_hp,
            },
        )

        return player.current_hp

    @staticmethod
    async def adjust_hp_for_unequip(
        db: AsyncSession, player_id: int, health_bonus: int
    ) -> int:
        """
        Adjust player's current HP when unequipping item with health bonus.

        Unequipping removes from current HP, capped at new max HP.
        Current HP will never drop below 1 from unequipping.

        Args:
            db: Database session
            player_id: Player ID
            health_bonus: Health bonus from the unequipped item

        Returns:
            New current HP value
        """
        if health_bonus <= 0:
            return -1  # No adjustment needed

        result = await db.execute(
            select(Player).where(Player.id == player_id)
        )
        player = result.scalar_one_or_none()
        if not player:
            return -1

        # Calculate new max HP (after unequipping, so without this item's bonus)
        new_max_hp = await EquipmentService.get_max_hp(db, player_id)

        # Remove health bonus from current HP, cap at new max, min 1
        new_current_hp = player.current_hp - health_bonus
        new_current_hp = max(1, min(new_current_hp, new_max_hp))

        player.current_hp = new_current_hp
        await db.commit()

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
    async def can_equip(
        db: AsyncSession, player_id: int, item: Item
    ) -> CanEquipResult:
        """
        Check if a player meets requirements to equip an item.

        Args:
            db: Database session
            player_id: Player ID
            item: Item to check

        Returns:
            CanEquipResult with status and reason
        """
        if not item.equipment_slot:
            return CanEquipResult(can_equip=False, reason="Item is not equipable")

        if not item.required_skill:
            return CanEquipResult(can_equip=True, reason="OK")

        # Get player's skill level
        result = await db.execute(
            select(PlayerSkill)
            .join(Skill)
            .where(PlayerSkill.player_id == player_id)
            .where(Skill.name == item.required_skill)
        )
        player_skill = result.scalar_one_or_none()

        if not player_skill:
            return CanEquipResult(
                can_equip=False,
                reason=f"Missing {item.required_skill} skill",
            )

        if player_skill.current_level < item.required_level:
            return CanEquipResult(
                can_equip=False,
                reason=f"Requires {item.required_skill} level {item.required_level} (you have {player_skill.current_level})",
            )

        return CanEquipResult(can_equip=True, reason="OK")

    @staticmethod
    async def equip_from_inventory(
        db: AsyncSession, player_id: int, inventory_slot: int
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
            db: Database session
            player_id: Player ID
            inventory_slot: Inventory slot containing item to equip

        Returns:
            EquipItemResult with status and updated stats
        """
        # Get item from inventory
        inv = await InventoryService.get_item_at_slot(db, player_id, inventory_slot)
        if not inv:
            return EquipItemResult(success=False, message="Inventory slot is empty")

        item = inv.item

        # Check if item is equipable
        if not item.equipment_slot:
            return EquipItemResult(success=False, message="Item cannot be equipped")

        # Check requirements
        can_equip = await EquipmentService.can_equip(db, player_id, item)
        if not can_equip.can_equip:
            return EquipItemResult(success=False, message=can_equip.reason)

        equipment_slot = EquipmentSlot(item.equipment_slot)
        unequipped_item_id = None

        # Check if this is stackable ammunition
        is_stackable_ammo = (
            item.category == ItemCategory.AMMUNITION.value
            and item.max_stack_size > 1
            and equipment_slot == EquipmentSlot.AMMO
        )

        # Get currently equipped item in target slot
        current_equipped = await EquipmentService.get_equipped_in_slot(
            db, player_id, equipment_slot
        )

        # Handle stackable ammunition - add to existing stack if same item
        if is_stackable_ammo and current_equipped and current_equipped.item_id == item.id:
            # Same ammo type already equipped - add to stack
            max_stack = item.max_stack_size
            current_qty = current_equipped.quantity
            add_qty = inv.quantity
            
            new_total = current_qty + add_qty
            
            if new_total <= max_stack:
                # All ammo fits in equipped stack
                current_equipped.quantity = new_total
                await db.delete(inv)
                await db.commit()
                
                updated_stats = await EquipmentService.get_total_stats(db, player_id)
                
                logger.info(
                    "Added ammo to equipped stack",
                    extra={
                        "player_id": player_id,
                        "item_id": item.id,
                        "added_qty": add_qty,
                        "new_total": new_total,
                    },
                )
                
                return EquipItemResult(
                    success=True,
                    message=f"Added {add_qty} {item.display_name} (now {new_total})",
                    updated_stats=updated_stats,
                )
            else:
                # Partial fit - equip what we can, leave rest in inventory
                amount_to_add = max_stack - current_qty
                current_equipped.quantity = max_stack
                inv.quantity = new_total - max_stack
                
                await db.commit()
                
                updated_stats = await EquipmentService.get_total_stats(db, player_id)
                
                logger.info(
                    "Partially added ammo to equipped stack",
                    extra={
                        "player_id": player_id,
                        "item_id": item.id,
                        "added_qty": amount_to_add,
                        "remaining_in_inv": inv.quantity,
                    },
                )
                
                return EquipItemResult(
                    success=True,
                    message=f"Added {amount_to_add} {item.display_name} (stack full at {max_stack}, {inv.quantity} remain in inventory)",
                    updated_stats=updated_stats,
                )

        # Handle two-handed weapon logic
        items_to_unequip = []

        if item.is_two_handed and equipment_slot == EquipmentSlot.WEAPON:
            # Unequip shield if equipping two-handed weapon
            shield = await EquipmentService.get_equipped_in_slot(
                db, player_id, EquipmentSlot.SHIELD
            )
            if shield:
                items_to_unequip.append(shield)

        if equipment_slot == EquipmentSlot.SHIELD:
            # Check if current weapon is two-handed
            weapon = await EquipmentService.get_equipped_in_slot(
                db, player_id, EquipmentSlot.WEAPON
            )
            if weapon and weapon.item.is_two_handed:
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
            inv_count = await InventoryService.get_inventory_count(db, player_id)
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
        await db.delete(inv)
        await db.flush()

        # Unequip items that need to be moved to inventory
        for eq in items_to_unequip:
            unequip_qty = eq.quantity  # Preserve quantity for ammo
            await db.delete(eq)
            await db.flush()

            # Add to inventory
            free_slot = await InventoryService.get_free_slot(db, player_id)
            if free_slot is not None:
                new_inv = PlayerInventory(
                    player_id=player_id,
                    item_id=eq.item_id,
                    slot=free_slot,
                    quantity=unequip_qty,
                    current_durability=eq.current_durability,
                )
                db.add(new_inv)
                unequipped_item_id = eq.item_id

        # Equip the new item
        new_equipment = PlayerEquipment(
            player_id=player_id,
            equipment_slot=equipment_slot.value,
            item_id=item.id,
            quantity=equip_quantity if is_stackable_ammo else 1,
            current_durability=inv.current_durability,
        )
        db.add(new_equipment)

        await db.commit()

        # Handle HP adjustment for health_bonus changes
        # Calculate net health bonus change (new item's bonus minus any unequipped item's bonus)
        health_bonus_gained = item.health_bonus if item.health_bonus else 0
        health_bonus_lost = 0
        for eq in items_to_unequip:
            if eq.item.health_bonus:
                health_bonus_lost += eq.item.health_bonus

        net_health_change = health_bonus_gained - health_bonus_lost
        if net_health_change != 0:
            result = await db.execute(
                select(Player).where(Player.id == player_id)
            )
            player = result.scalar_one_or_none()
            if player:
                if net_health_change > 0:
                    # Gained health bonus - add to current HP
                    player.current_hp += net_health_change
                else:
                    # Lost health bonus - subtract from current HP, cap at max, min 1
                    new_max_hp = await EquipmentService.get_max_hp(db, player_id)
                    new_current_hp = player.current_hp + net_health_change  # net_health_change is negative
                    player.current_hp = max(1, min(new_current_hp, new_max_hp))
                await db.commit()

        # Get updated stats
        updated_stats = await EquipmentService.get_total_stats(db, player_id)

        logger.info(
            "Equipped item",
            extra={
                "player_id": player_id,
                "item_id": item.id,
                "slot": equipment_slot.value,
                "quantity": equip_quantity if is_stackable_ammo else 1,
            },
        )

        return EquipItemResult(
            success=True,
            message=f"Equipped {item.display_name}" + (f" x{equip_quantity}" if is_stackable_ammo and equip_quantity > 1 else ""),
            unequipped_item_id=unequipped_item_id,
            updated_stats=updated_stats,
        )

    @staticmethod
    async def unequip_to_inventory(
        db: AsyncSession,
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
            db: Database session
            player_id: Player ID
            equipment_slot: Slot to unequip from
            map_id: Optional map ID for dropping to ground if inventory full
            player_x: Optional player X position for dropping
            player_y: Optional player Y position for dropping

        Returns:
            UnequipItemResult with status
        """
        # Get equipped item
        equipped = await EquipmentService.get_equipped_in_slot(
            db, player_id, equipment_slot
        )
        if not equipped:
            return UnequipItemResult(
                success=False,
                message="Nothing equipped in that slot",
            )

        item = equipped.item
        quantity = equipped.quantity  # Preserve quantity for stackable items (ammo)

        # Try to add to inventory (handles stacking for stackable items)
        add_result = await InventoryService.add_item(
            db=db,
            player_id=player_id,
            item_id=equipped.item_id,
            quantity=quantity,
            durability=equipped.current_durability,
        )

        if add_result.success and add_result.overflow_quantity == 0:
            # Successfully added all to inventory
            health_bonus_lost = item.health_bonus if item.health_bonus else 0
            await db.delete(equipped)
            await db.commit()

            # Handle HP adjustment for health_bonus loss
            if health_bonus_lost > 0:
                await EquipmentService.adjust_hp_for_unequip(db, player_id, health_bonus_lost)

            updated_stats = await EquipmentService.get_total_stats(db, player_id)

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
                message=f"Unequipped {item.display_name}" + (f" x{quantity}" if quantity > 1 else ""),
                inventory_slot=add_result.slot,
                updated_stats=updated_stats,
            )

        # Inventory full or partial - try to drop to ground
        if map_id is not None and player_x is not None and player_y is not None:
            # Determine how many need to be dropped
            dropped_quantity = quantity if not add_result.success else add_result.overflow_quantity

            ground_item = await GroundItemService.create_ground_item(
                db=db,
                item_id=equipped.item_id,
                map_id=map_id,
                x=player_x,
                y=player_y,
                quantity=dropped_quantity,
                dropped_by=player_id,
                current_durability=equipped.current_durability,
            )

            if ground_item:
                health_bonus_lost = item.health_bonus if item.health_bonus else 0
                await db.delete(equipped)
                await db.commit()

                # Handle HP adjustment for health_bonus loss
                if health_bonus_lost > 0:
                    await EquipmentService.adjust_hp_for_unequip(db, player_id, health_bonus_lost)

                updated_stats = await EquipmentService.get_total_stats(db, player_id)

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
                        message=f"Unequipped {item.display_name} ({quantity - dropped_quantity} to inventory, {dropped_quantity} dropped)",
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
                            "ground_item_id": ground_item.id,
                            "quantity": dropped_quantity,
                        },
                    )
                    return UnequipItemResult(
                        success=True,
                        message=f"Inventory full - {item.display_name} dropped to ground",
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
        db: AsyncSession,
        player_id: int,
        slot: EquipmentSlot,
        amount: int = 1,
    ) -> Optional[int]:
        """
        Reduce durability of an equipped item.

        Args:
            db: Database session
            player_id: Player ID
            slot: Equipment slot
            amount: Amount to reduce (default 1)

        Returns:
            Remaining durability, or None if item broke/doesn't have durability
        """
        equipped = await EquipmentService.get_equipped_in_slot(db, player_id, slot)
        if not equipped:
            return None

        if equipped.current_durability is None:
            return None  # Item has no durability

        if equipped.item.is_indestructible:
            return equipped.current_durability  # Item cannot degrade

        amount = amount * settings.EQUIPMENT_DURABILITY_LOSS_PER_HIT
        equipped.current_durability = max(0, equipped.current_durability - amount)

        if equipped.current_durability == 0:
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

        await db.commit()
        return equipped.current_durability

    @staticmethod
    async def repair_equipment(
        db: AsyncSession,
        player_id: int,
        slot: EquipmentSlot,
    ) -> tuple[bool, int]:
        """
        Restore an equipped item to full durability.

        Args:
            db: Database session
            player_id: Player ID
            slot: Equipment slot

        Returns:
            Tuple of (success, repair_cost)
        """
        equipped = await EquipmentService.get_equipped_in_slot(db, player_id, slot)
        if not equipped:
            return (False, 0)

        if equipped.current_durability is None:
            return (False, 0)  # Item has no durability

        if equipped.item.max_durability is None:
            return (False, 0)

        # Calculate repair cost
        damage_percent = 1 - (equipped.current_durability / equipped.item.max_durability)
        repair_cost = int(
            equipped.item.value
            * settings.EQUIPMENT_REPAIR_COST_MULTIPLIER
            * damage_percent
        )

        equipped.current_durability = equipped.item.max_durability
        await db.commit()

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
        db: AsyncSession,
        player_id: int,
        amount: int = 1,
    ) -> tuple[bool, int]:
        """
        Consume ammunition from the equipped AMMO slot.

        Used when firing ranged weapons. Reduces quantity by amount.
        If quantity reaches 0, removes the equipment entry.

        Args:
            db: Database session
            player_id: Player ID
            amount: Number of ammo to consume (default 1)

        Returns:
            Tuple of (success, remaining_quantity)
            Returns (False, 0) if no ammo equipped or not enough ammo
        """
        equipped = await EquipmentService.get_equipped_in_slot(
            db, player_id, EquipmentSlot.AMMO
        )
        if not equipped:
            return (False, 0)

        if equipped.quantity < amount:
            return (False, equipped.quantity)

        equipped.quantity -= amount

        if equipped.quantity == 0:
            # No ammo left - remove from equipment
            await db.delete(equipped)
            await db.commit()

            logger.info(
                "Ammo depleted",
                extra={
                    "player_id": player_id,
                    "item_id": equipped.item_id,
                },
            )
            return (True, 0)

        await db.commit()

        logger.debug(
            "Consumed ammo",
            extra={
                "player_id": player_id,
                "item_id": equipped.item_id,
                "consumed": amount,
                "remaining": equipped.quantity,
            },
        )

        return (True, equipped.quantity)

    @staticmethod
    async def clear_equipment(db: AsyncSession, player_id: int) -> int:
        """
        Remove all equipped items (for death drops).

        Args:
            db: Database session
            player_id: Player ID

        Returns:
            Number of items unequipped
        """
        result = await db.execute(
            delete(PlayerEquipment).where(PlayerEquipment.player_id == player_id)
        )
        await db.commit()
        return result.rowcount or 0

    @staticmethod
    async def get_all_equipped_items(
        db: AsyncSession, player_id: int
    ) -> list[tuple[PlayerEquipment, Item]]:
        """
        Get all equipped items with their item data.

        Args:
            db: Database session
            player_id: Player ID

        Returns:
            List of (PlayerEquipment, Item) tuples
        """
        result = await db.execute(
            select(PlayerEquipment)
            .where(PlayerEquipment.player_id == player_id)
            .options(selectinload(PlayerEquipment.item))
        )
        equipment = result.scalars().all()
        return [(eq, eq.item) for eq in equipment]
