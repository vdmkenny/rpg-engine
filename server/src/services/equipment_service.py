"""
Service for managing player equipment.
"""

from typing import Optional, TYPE_CHECKING

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.config import settings
from ..core.items import EquipmentSlot, ItemCategory
from ..core.logging_config import get_logger
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
from .game_state_manager import get_game_state_manager

if TYPE_CHECKING:
    from .game_state_manager import GameStateManager

logger = get_logger(__name__)


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
        # Get equipment state from GameStateManager
        state_manager = get_game_state_manager()
        if state_manager.is_online(player_id):
            equipment_data = await state_manager.get_equipment(player_id)
            if equipment_data:
                # Convert GSM data to PlayerEquipment-like objects
                equipment = {}
                item_ids = [slot_data["item_id"] for slot_data in equipment_data.values()]
                
                # Get item data from database
                if item_ids:
                    result = await db.execute(
                        select(Item).where(Item.id.in_(item_ids))
                    )
                    items_by_id = {item.id: item for item in result.scalars().all()}
                    
                    for slot, slot_data in equipment_data.items():
                        item = items_by_id.get(slot_data["item_id"])
                        if item:
                            # Create a PlayerEquipment-like object
                            eq = PlayerEquipment(
                                player_id=player_id,
                                equipment_slot=slot,
                                item_id=slot_data["item_id"],
                                quantity=slot_data.get("quantity", 1),
                                current_durability=slot_data.get("current_durability"),
                            )
                            eq.item = item  # Attach item data
                            equipment[slot] = eq
                            
                return equipment
            return {}
        
        # Use GameStateManager for consistent state access
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
        
        total_stats = await EquipmentService.get_total_stats(player_id)

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
        # Always use GameStateManager for consistent state access
        state_manager = get_game_state_manager()
        if state_manager.is_online(player_id):
            slot_data = await state_manager.get_equipment_slot(player_id, slot.value)
            if slot_data:
                # Get item data from database
                result = await db.execute(
                    select(Item).where(Item.id == slot_data["item_id"])
                )
                item = result.scalar_one_or_none()
                if item:
                    eq = PlayerEquipment(
                        player_id=player_id,
                        equipment_slot=slot.value,
                        item_id=slot_data["item_id"],
                        quantity=slot_data.get("quantity", 1),
                        current_durability=slot_data.get("durability"),
                    )
                    eq.item = item  # Attach item data
                    return eq
            return None
        
        # Fallback to database if player is offline
        result = await db.execute(
            select(PlayerEquipment)
            .where(PlayerEquipment.player_id == player_id)
            .where(PlayerEquipment.equipment_slot == slot.value)
            .options(selectinload(PlayerEquipment.item))
        )
        return result.scalar_one_or_none()

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
        # Get all equipment from GSM
        state_manager = get_game_state_manager()
        equipment_data = await state_manager.get_equipment(player_id)
        if not equipment_data:
            return ItemStats()
        
        # Get item data for stat calculation
        item_ids = [slot_data["item_id"] for slot_data in equipment_data.values()]
        if not item_ids:
            return ItemStats()
        
        # Get item stats for calculation
        items_stats = {}
        for item_id in item_ids:
            item_info = state_manager.get_item_meta(item_id)
            if item_info:
                items_stats[item_id] = item_info
        
        # Calculate total stats
        stats = ItemStats()
        for slot_data in equipment_data.values():
            item_info = items_stats.get(slot_data["item_id"])
            if item_info:
                stats.attack_bonus += item_info.get("attack_bonus", 0)
                stats.strength_bonus += item_info.get("strength_bonus", 0)
                stats.ranged_attack_bonus += item_info.get("ranged_attack_bonus", 0)
                stats.ranged_strength_bonus += item_info.get("ranged_strength_bonus", 0)
                stats.magic_attack_bonus += item_info.get("magic_attack_bonus", 0)
                stats.magic_damage_bonus += item_info.get("magic_damage_bonus", 0)
                stats.physical_defence_bonus += item_info.get("physical_defence_bonus", 0)
                stats.magic_defence_bonus += item_info.get("magic_defence_bonus", 0)
                stats.health_bonus += item_info.get("health_bonus", 0)
                stats.speed_bonus += item_info.get("speed_bonus", 0)
                stats.mining_bonus += item_info.get("mining_bonus", 0)
                stats.woodcutting_bonus += item_info.get("woodcutting_bonus", 0)
                stats.fishing_bonus += item_info.get("fishing_bonus", 0)

        return stats

    @staticmethod
    async def get_max_hp(player_id: int) -> int:
        """
        Calculate max HP for a player.

        Max HP = Hitpoints skill level + equipment health_bonus.

        Reads from GSM (Valkey cache) for online players.

        Args:
            player_id: Player ID

        Returns:
            Maximum HP value
        """
        from server.src.core.skills import HITPOINTS_START_LEVEL

        gsm = get_game_state_manager()

        # Get base HP from Hitpoints skill level in GSM
        hitpoints_skill = await gsm.get_skill(player_id, "hitpoints")
        if hitpoints_skill:
            base_hp = hitpoints_skill.get("level", HITPOINTS_START_LEVEL)
        else:
            base_hp = HITPOINTS_START_LEVEL

        # Get equipment from GSM and calculate total health bonus
        equipment = await gsm.get_equipment(player_id)
        if not equipment:
            return base_hp

        # Get item metadata from GSM cache (NO database session creation)
        health_bonus = 0
        item_ids = [slot_data["item_id"] for slot_data in equipment.values()]

        if item_ids:
            # Use GSM's item metadata cache instead of direct database query
            items_meta = await gsm.get_items_meta(item_ids)
            
            for slot_data in equipment.values():
                item_meta = items_meta.get(slot_data["item_id"])
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

        gsm = get_game_state_manager()
        
        # Get current HP through GSM
        hp_data = await gsm.get_player_hp(player_id)
        if not hp_data:
            return -1
            
        current_hp = hp_data.get("current_hp", 0)
        new_hp = current_hp + health_bonus
        
        # Update HP through GSM (handles both cache and database)
        await gsm.update_player_hp(player_id, new_hp)

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

        gsm = get_game_state_manager()
        hp_data = await gsm.get_player_hp(player_id)
        if not hp_data:
            return -1

        # Calculate new max HP (after unequipping, so without this item's bonus)
        new_max_hp = await EquipmentService.get_max_hp(player_id)

        # Remove health bonus from current HP, cap at new max, min 1
        new_current_hp = hp_data["current_hp"] - health_bonus
        new_current_hp = max(1, min(new_current_hp, new_max_hp))

        await gsm.update_player_hp(player_id, new_current_hp)

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
    async def can_equip(player_id: int, item: Item) -> CanEquipResult:
        """
        Check if player meets skill requirements to equip an item.

        Args:
            player_id: Player ID
            item: Item to check

        Returns:
            CanEquipResult with status and reason
        """
        if not item.equipment_slot:
            return CanEquipResult(can_equip=False, reason="Item is not equipable")

        if not item.required_skill:
            return CanEquipResult(can_equip=True, reason="OK")

        # Check skill level for equipment requirements
        gsm = get_game_state_manager()
        
        if gsm.is_online(player_id):
            # Player is online, use cached skills
            skill_data = await gsm.get_skill(player_id, item.required_skill)
            if not skill_data:
                return CanEquipResult(
                    can_equip=False,
                    reason=f"Missing {item.required_skill} skill",
                )
            
            current_level = skill_data.get("level", 1)
        else:
            # Player is offline, get skills from database via GSM
            skills_data = await gsm.get_skills_offline(player_id)
            skill_data = skills_data.get(item.required_skill)
            
            if not skill_data:
                return CanEquipResult(
                    can_equip=False,
                    reason=f"Missing {item.required_skill} skill",
                )
            
            current_level = skill_data.get("level", 1)

        if current_level < item.required_level:
            return CanEquipResult(
                can_equip=False,
                reason=f"Requires {item.required_skill} level {item.required_level} (you have {current_level})",
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
        state_manager = get_game_state_manager()
        
        # Get item from inventory
        inv = await InventoryService.get_item_at_slot(db, player_id, inventory_slot)
        if not inv:
            return EquipItemResult(success=False, message="Inventory slot is empty")

        item = inv.item

        # Check if item is equipable
        if not item.equipment_slot:
            return EquipItemResult(success=False, message="Item cannot be equipped")

        # Check requirements
        can_equip = await EquipmentService.can_equip(player_id, item)
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
                
                updated_stats = await EquipmentService.get_total_stats(player_id)
                
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
                
                updated_stats = await EquipmentService.get_total_stats(player_id)
                
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
        await state_manager.delete_inventory_slot(player_id, inventory_slot)

        # Unequip items that need to be moved to inventory
        for eq in items_to_unequip:
            unequip_qty = eq.quantity  # Preserve quantity for ammo
            
            # Remove from equipment
            await state_manager.delete_equipment_slot(player_id, eq.equipment_slot)

            # Add to inventory
            free_slot = await state_manager.get_free_inventory_slot(player_id)
            if free_slot is not None:
                await state_manager.set_inventory_slot(
                    player_id, free_slot, eq.item_id, unequip_qty, eq.current_durability
                )
                unequipped_item_id = eq.item_id

        # Equip the new item
        await state_manager.set_equipment_slot(
            player_id, 
            equipment_slot.value, 
            item.id, 
            equip_quantity if is_stackable_ammo else 1,
            int(inv.current_durability) if inv.current_durability is not None else None
        )

        # Handle HP adjustment for health bonus changes
        health_bonus_gained = item.health_bonus if item.health_bonus else 0
        health_bonus_lost = 0
        for eq in items_to_unequip:
            if eq.item.health_bonus:
                health_bonus_lost += eq.item.health_bonus

        net_health_change = health_bonus_gained - health_bonus_lost
        if net_health_change != 0:
            current_hp = await state_manager.get_player_hp(player_id)
            if current_hp is not None:
                if net_health_change > 0:
                    # Gained health bonus - add to current HP
                    new_hp = current_hp + net_health_change
                else:
                    # Lost health bonus - reduce current HP, minimum 1
                    stats = await EquipmentService.get_total_stats(player_id)
                    max_hp = stats.get("max_hp", 100)
                    new_hp = max(1, min(current_hp + net_health_change, max_hp))
                
                await state_manager.set_player_hp(player_id, new_hp)

        # Get updated stats for return value
        updated_stats = await EquipmentService.get_total_stats(player_id)

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
        state_manager = get_game_state_manager()
        
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
            
            # Remove from equipment using GSM
            await state_manager.delete_equipment_slot(player_id, equipment_slot.value)

            # Handle HP adjustment for health_bonus loss
            if health_bonus_lost > 0:
                current_hp = await state_manager.get_player_hp(player_id)
                if current_hp is not None:
                    max_hp = await EquipmentService.get_max_hp(player_id)
                    new_hp = max(1, min(current_hp - health_bonus_lost, max_hp))
                    await state_manager.set_player_hp(player_id, new_hp)

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
                message=f"Unequipped {item.display_name}" + (f" x{quantity}" if quantity > 1 else ""),
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
                health_bonus_lost = item.health_bonus if item.health_bonus else 0
                
                # Remove from equipment using GSM
                await state_manager.delete_equipment_slot(player_id, equipment_slot.value)

                # Handle HP adjustment for health_bonus loss
                if health_bonus_lost > 0:
                    current_hp = await state_manager.get_player_hp(player_id)
                    if current_hp is not None:
                        max_hp = await EquipmentService.get_max_hp(player_id)
                        new_hp = max(1, min(current_hp - health_bonus_lost, max_hp))
                        await state_manager.set_player_hp(player_id, new_hp)

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
                            "ground_item_id": ground_item_id,
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
        state_manager = get_game_state_manager()
        equipped = await EquipmentService.get_equipped_in_slot(db, player_id, slot)
        if not equipped:
            return None

        if equipped.current_durability is None:
            return None  # Item has no durability

        if equipped.item.is_indestructible:
            return equipped.current_durability  # Item cannot degrade

        amount = amount * settings.EQUIPMENT_DURABILITY_LOSS_PER_HIT
        new_durability = max(0, equipped.current_durability - amount)
        
        # Update durability in GSM
        await state_manager.set_equipment_slot(
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
        state_manager = get_game_state_manager()
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

        # Update durability to max in GSM
        await state_manager.set_equipment_slot(
            player_id,
            slot.value,
            equipped.item_id,
            equipped.quantity,
            int(equipped.item.max_durability)
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
        state_manager = get_game_state_manager()
        equipped = await EquipmentService.get_equipped_in_slot(
            db, player_id, EquipmentSlot.AMMO
        )
        if not equipped:
            return (False, 0)

        if equipped.quantity < amount:
            return (False, equipped.quantity)

        new_quantity = equipped.quantity - amount

        if new_quantity == 0:
            # No ammo left - remove from equipment using GSM
            await state_manager.delete_equipment_slot(player_id, EquipmentSlot.AMMO.value)

            logger.info(
                "Ammo depleted",
                extra={
                    "player_id": player_id,
                    "item_id": equipped.item_id,
                },
            )
            return (True, 0)

        # Update quantity in GSM
        await state_manager.set_equipment_slot(
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
    async def clear_equipment(db: AsyncSession, player_id: int) -> int:
        """
        Remove all equipped items (for death drops).

        Args:
            db: Database session
            player_id: Player ID

        Returns:
            Number of items unequipped
        """
        state_manager = get_game_state_manager()
        
        # Get all equipment first to count items
        equipment = await state_manager.get_equipment(player_id)
        if not equipment:
            return 0
        
        item_count = len(equipment)
        
        # Clear all equipment in GSM
        await state_manager.clear_equipment(player_id)
        
        return item_count

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
        state_manager = get_game_state_manager()
        equipment_data = await state_manager.get_equipment(player_id)
        
        if not equipment_data:
            return []
        
        # Get item data from database for the equipped items
        item_ids = [slot_data["item_id"] for slot_data in equipment_data.values()]
        if not item_ids:
            return []
            
        result = await db.execute(
            select(Item).where(Item.id.in_(item_ids))
        )
        items_by_id = {item.id: item for item in result.scalars().all()}
        
        # Build list of (PlayerEquipment, Item) tuples
        equipped_items = []
        for slot, slot_data in equipment_data.items():
            item = items_by_id.get(slot_data["item_id"])
            if item:
                # Create a PlayerEquipment-like object
                eq = PlayerEquipment(
                    player_id=player_id,
                    equipment_slot=slot,
                    item_id=slot_data["item_id"],
                    quantity=slot_data.get("quantity", 1),
                    current_durability=slot_data.get("current_durability"),
                )
                eq.item = item  # Attach item data
                equipped_items.append((eq, item))
                
        return equipped_items
