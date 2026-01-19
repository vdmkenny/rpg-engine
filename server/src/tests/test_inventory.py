"""
Tests for the inventory system.

Tests cover:
- Adding items to inventory (stacking logic)
- Removing items from inventory
- Moving items between slots
- Inventory sorting
- Stack merging
"""

import uuid
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from server.src.core.items import (
    ItemType,
    ItemCategory,
    ItemRarity,
    InventorySortType,
    STACK_SIZE_MATERIALS,
)
from server.src.core.config import settings
from server.src.models.item import Item, PlayerInventory
from server.src.services.item_service import ItemService
from server.src.services.inventory_service import InventoryService


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest_asyncio.fixture
async def items_synced(session: AsyncSession):
    """Ensure items are synced to database."""
    await ItemService.sync_items_to_db(session)


@pytest_asyncio.fixture
async def player_with_inventory(session: AsyncSession, create_test_player, items_synced):
    """Create a test player ready for inventory tests."""
    unique_name = f"inv_test_{uuid.uuid4().hex[:8]}"
    player = await create_test_player(unique_name, "password123")
    return player


# =============================================================================
# Add Item Tests
# =============================================================================


class TestAddItem:
    """Test adding items to inventory."""

    @pytest.mark.asyncio
    async def test_add_single_item(
        self, session: AsyncSession, player_with_inventory, gsm
    ):
        """Adding a single item should create inventory entry."""
        player = player_with_inventory
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        # Login player to initialize state in GSM (GSM singleton is already initialized by gsm fixture)
        from server.src.services.player_service import PlayerService
        await PlayerService.login_player(session, player)

        result = await InventoryService.add_item(session, player.id, item.id)

        assert result.success is True
        assert result.slot is not None
        assert result.overflow_quantity == 0

        # Verify item is in inventory
        inv = await InventoryService.get_item_at_slot(session, player.id, result.slot)
        assert inv is not None
        assert inv.item_id == item.id
        assert inv.quantity == 1

    @pytest.mark.asyncio
    async def test_add_stackable_item(
        self, session: AsyncSession, player_with_inventory, gsm
    ):
        """Adding stackable items should create correct quantity."""
        player = player_with_inventory
        item = await ItemService.get_item_by_name(session, "copper_ore")

        # Login player to initialize state in GSM (GSM singleton is already initialized by gsm fixture)
        from server.src.services.player_service import PlayerService
        await PlayerService.login_player(session, player)

        result = await InventoryService.add_item(
            session, player.id, item.id, quantity=10
        )

        assert result.success is True

        inv = await InventoryService.get_item_at_slot(session, player.id, result.slot)
        assert inv is not None
        assert inv.quantity == 10

    @pytest.mark.asyncio
    async def test_add_to_existing_stack(
        self, session: AsyncSession, player_with_inventory, gsm
    ):
        """Adding to existing stack should increase quantity."""
        player = player_with_inventory
        item = await ItemService.get_item_by_name(session, "copper_ore")

        # Login player to initialize state in GSM (GSM singleton is already initialized by gsm fixture)
        from server.src.services.player_service import PlayerService
        await PlayerService.login_player(session, player)

        # Add first batch
        await InventoryService.add_item(session, player.id, item.id, quantity=10)

        # Add second batch
        result = await InventoryService.add_item(
            session, player.id, item.id, quantity=5
        )

        assert result.success is True

        # Check total quantity
        inv = await InventoryService.get_inventory(session, player.id)
        total = sum(i.quantity for i in inv if i.item_id == item.id)
        assert total == 15

    @pytest.mark.asyncio
    async def test_add_exceeds_stack_size_creates_new_stack(
        self, session: AsyncSession, player_with_inventory, gsm
    ):
        """Adding more than max stack should create additional slots."""
        player = player_with_inventory
        item = await ItemService.get_item_by_name(session, "copper_ore")

        # Login player to initialize state in GSM (GSM singleton is already initialized by gsm fixture)
        from server.src.services.player_service import PlayerService
        await PlayerService.login_player(session, player)

        # Add more than one stack can hold
        quantity = STACK_SIZE_MATERIALS + 10
        result = await InventoryService.add_item(
            session, player.id, item.id, quantity=quantity
        )

        assert result.success is True

        # Should have multiple inventory entries
        inv = await InventoryService.get_inventory(session, player.id)
        item_entries = [i for i in inv if i.item_id == item.id]
        assert len(item_entries) >= 2

        total = sum(i.quantity for i in item_entries)
        assert total == quantity

    @pytest.mark.asyncio
    async def test_add_item_invalid_quantity(
        self, session: AsyncSession, player_with_inventory, gsm
    ):
        """Adding zero or negative quantity should fail."""
        player = player_with_inventory
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        # Login player to initialize state in GSM (GSM singleton is already initialized by gsm fixture)
        from server.src.services.player_service import PlayerService
        await PlayerService.login_player(session, player)

        result = await InventoryService.add_item(
            session, player.id, item.id, quantity=0
        )
        assert result.success is False

        result = await InventoryService.add_item(
            session, player.id, item.id, quantity=-1
        )
        assert result.success is False

    @pytest.mark.asyncio
    async def test_add_item_invalid_item_id(
        self, session: AsyncSession, player_with_inventory, gsm
    ):
        """Adding non-existent item should fail."""
        player = player_with_inventory

        # Login player to initialize state in GSM (GSM singleton is already initialized by gsm fixture)
        from server.src.services.player_service import PlayerService
        await PlayerService.login_player(session, player)

        result = await InventoryService.add_item(session, player.id, 99999)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_add_item_with_durability(
        self, session: AsyncSession, player_with_inventory
    ):
        """Adding item with durability should set current durability."""
        player = player_with_inventory
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        result = await InventoryService.add_item(
            session, player.id, item.id, durability=100
        )

        assert result.success is True

        inv = await InventoryService.get_item_at_slot(session, player.id, result.slot)
        assert inv.current_durability == 100


# =============================================================================
# Remove Item Tests
# =============================================================================


class TestRemoveItem:
    """Test removing items from inventory."""

    @pytest.mark.asyncio
    async def test_remove_entire_stack(
        self, session: AsyncSession, player_with_inventory
    ):
        """Removing all items should delete the inventory entry."""
        player = player_with_inventory
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        add_result = await InventoryService.add_item(session, player.id, item.id)
        slot = add_result.slot

        result = await InventoryService.remove_item(session, player.id, slot)

        assert result.success is True
        assert result.removed_quantity == 1

        # Slot should be empty
        inv = await InventoryService.get_item_at_slot(session, player.id, slot)
        assert inv is None

    @pytest.mark.asyncio
    async def test_remove_partial_stack(
        self, session: AsyncSession, player_with_inventory
    ):
        """Removing part of a stack should reduce quantity."""
        player = player_with_inventory
        item = await ItemService.get_item_by_name(session, "copper_ore")

        add_result = await InventoryService.add_item(
            session, player.id, item.id, quantity=10
        )
        slot = add_result.slot

        result = await InventoryService.remove_item(session, player.id, slot, quantity=3)

        assert result.success is True
        assert result.removed_quantity == 3

        inv = await InventoryService.get_item_at_slot(session, player.id, slot)
        assert inv.quantity == 7

    @pytest.mark.asyncio
    async def test_remove_from_empty_slot(
        self, session: AsyncSession, player_with_inventory
    ):
        """Removing from empty slot should fail."""
        player = player_with_inventory

        result = await InventoryService.remove_item(session, player.id, 0)

        assert result.success is False
        assert result.removed_quantity == 0

    @pytest.mark.asyncio
    async def test_remove_more_than_available(
        self, session: AsyncSession, player_with_inventory
    ):
        """Removing more than available should fail."""
        player = player_with_inventory
        item = await ItemService.get_item_by_name(session, "copper_ore")

        add_result = await InventoryService.add_item(
            session, player.id, item.id, quantity=5
        )
        slot = add_result.slot

        result = await InventoryService.remove_item(
            session, player.id, slot, quantity=10
        )

        assert result.success is False
        assert result.removed_quantity == 0


# =============================================================================
# Move Item Tests
# =============================================================================


class TestMoveItem:
    """Test moving items between inventory slots."""

    @pytest.mark.asyncio
    async def test_move_to_empty_slot(
        self, session: AsyncSession, player_with_inventory
    ):
        """Moving to empty slot should work."""
        player = player_with_inventory
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        add_result = await InventoryService.add_item(session, player.id, item.id)
        from_slot = add_result.slot
        to_slot = from_slot + 1

        result = await InventoryService.move_item(
            session, player.id, from_slot, to_slot
        )

        assert result.success is True

        # Original slot should be empty
        assert await InventoryService.get_item_at_slot(session, player.id, from_slot) is None

        # New slot should have item
        inv = await InventoryService.get_item_at_slot(session, player.id, to_slot)
        assert inv is not None
        assert inv.item_id == item.id

    @pytest.mark.asyncio
    async def test_swap_items(
        self, session: AsyncSession, player_with_inventory
    ):
        """Moving to occupied slot should swap items."""
        player = player_with_inventory
        sword = await ItemService.get_item_by_name(session, "bronze_sword")
        pickaxe = await ItemService.get_item_by_name(session, "bronze_pickaxe")

        # Add both items
        sword_result = await InventoryService.add_item(session, player.id, sword.id)
        sword_slot = sword_result.slot

        pickaxe_result = await InventoryService.add_item(session, player.id, pickaxe.id)
        pickaxe_slot = pickaxe_result.slot

        # Swap them
        result = await InventoryService.move_item(
            session, player.id, sword_slot, pickaxe_slot
        )

        assert result.success is True

        # Verify swap
        inv_at_sword_slot = await InventoryService.get_item_at_slot(
            session, player.id, sword_slot
        )
        inv_at_pickaxe_slot = await InventoryService.get_item_at_slot(
            session, player.id, pickaxe_slot
        )

        assert inv_at_sword_slot.item_id == pickaxe.id
        assert inv_at_pickaxe_slot.item_id == sword.id

    @pytest.mark.asyncio
    async def test_merge_stacks_on_move(
        self, session: AsyncSession, player_with_inventory
    ):
        """Moving stackable item to same item type should merge."""
        player = player_with_inventory
        item = await ItemService.get_item_by_name(session, "copper_ore")

        # Add two separate stacks by using different slots
        result1 = await InventoryService.add_item(
            session, player.id, item.id, quantity=10
        )
        slot1 = result1.slot

        # Force second stack to different slot
        inv1 = await InventoryService.get_item_at_slot(session, player.id, slot1)
        inv1.quantity = item.max_stack_size  # Fill first stack
        await session.commit()

        result2 = await InventoryService.add_item(
            session, player.id, item.id, quantity=5
        )
        slot2 = result2.slot

        # Reset first stack for merge test
        inv1.quantity = 10
        await session.commit()

        # Move second stack to first
        result = await InventoryService.move_item(session, player.id, slot2, slot1)

        assert result.success is True

        # First slot should have combined quantity (up to max)
        inv = await InventoryService.get_item_at_slot(session, player.id, slot1)
        assert inv.quantity == 15

    @pytest.mark.asyncio
    async def test_move_same_slot(
        self, session: AsyncSession, player_with_inventory
    ):
        """Moving to same slot should succeed (no-op)."""
        player = player_with_inventory
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        add_result = await InventoryService.add_item(session, player.id, item.id)
        slot = add_result.slot

        result = await InventoryService.move_item(session, player.id, slot, slot)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_move_from_empty_slot(
        self, session: AsyncSession, player_with_inventory
    ):
        """Moving from empty slot should fail."""
        player = player_with_inventory

        result = await InventoryService.move_item(session, player.id, 0, 1)

        assert result.success is False

    @pytest.mark.asyncio
    async def test_move_to_invalid_slot(
        self, session: AsyncSession, player_with_inventory
    ):
        """Moving to invalid slot should fail."""
        player = player_with_inventory
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        add_result = await InventoryService.add_item(session, player.id, item.id)
        slot = add_result.slot

        result = await InventoryService.move_item(
            session, player.id, slot, -1
        )
        assert result.success is False

        result = await InventoryService.move_item(
            session, player.id, slot, settings.INVENTORY_MAX_SLOTS + 1
        )
        assert result.success is False


# =============================================================================
# Sort Inventory Tests
# =============================================================================


class TestSortInventory:
    """Test inventory sorting functionality."""

    @pytest.mark.asyncio
    async def test_sort_by_category(
        self, session: AsyncSession, player_with_inventory
    ):
        """Sorting by category should group items correctly."""
        player = player_with_inventory

        # Add items from different categories
        sword = await ItemService.get_item_by_name(session, "bronze_sword")
        ore = await ItemService.get_item_by_name(session, "copper_ore")
        gold = await ItemService.get_item_by_name(session, "gold_coins")

        await InventoryService.add_item(session, player.id, ore.id, quantity=10)
        await InventoryService.add_item(session, player.id, sword.id)
        await InventoryService.add_item(session, player.id, gold.id, quantity=100)

        # Sort by category
        result = await InventoryService.sort_inventory(
            session, player.id, InventorySortType.BY_CATEGORY
        )

        assert result.success is True

        # Verify order: currency first, then weapon, then material
        inv = await InventoryService.get_inventory(session, player.id)
        categories = [i.item.category for i in inv]

        # Find indices
        currency_idx = next(i for i, c in enumerate(categories) if c == "currency")
        weapon_idx = next(i for i, c in enumerate(categories) if c == "weapon")
        material_idx = next(i for i, c in enumerate(categories) if c == "material")

        assert currency_idx < weapon_idx < material_idx

    @pytest.mark.asyncio
    async def test_sort_by_rarity(
        self, session: AsyncSession, player_with_inventory
    ):
        """Sorting by rarity should put legendary first, poor last."""
        player = player_with_inventory

        # Add items with different rarities
        shrimp = await ItemService.get_item_by_name(session, "raw_shrimp")  # poor
        sword = await ItemService.get_item_by_name(session, "bronze_sword")  # common

        await InventoryService.add_item(session, player.id, shrimp.id, quantity=5)
        await InventoryService.add_item(session, player.id, sword.id)

        result = await InventoryService.sort_inventory(
            session, player.id, InventorySortType.BY_RARITY
        )

        assert result.success is True

        inv = await InventoryService.get_inventory(session, player.id)
        rarities = [i.item.rarity for i in inv]

        # Common should come before poor
        common_idx = next(i for i, r in enumerate(rarities) if r == "common")
        poor_idx = next(i for i, r in enumerate(rarities) if r == "poor")
        assert common_idx < poor_idx

    @pytest.mark.asyncio
    async def test_sort_by_value(
        self, session: AsyncSession, player_with_inventory
    ):
        """Sorting by value should put highest value first."""
        player = player_with_inventory

        # Add items with different values
        ore = await ItemService.get_item_by_name(session, "copper_ore")  # 5
        sword = await ItemService.get_item_by_name(session, "bronze_sword")  # 20

        await InventoryService.add_item(session, player.id, ore.id, quantity=5)
        await InventoryService.add_item(session, player.id, sword.id)

        result = await InventoryService.sort_inventory(
            session, player.id, InventorySortType.BY_VALUE
        )

        assert result.success is True

        inv = await InventoryService.get_inventory(session, player.id)
        values = [i.item.value for i in inv]

        # Should be descending
        assert values == sorted(values, reverse=True)

    @pytest.mark.asyncio
    async def test_sort_by_name(
        self, session: AsyncSession, player_with_inventory
    ):
        """Sorting by name should be alphabetical."""
        player = player_with_inventory

        sword = await ItemService.get_item_by_name(session, "bronze_sword")
        arrows = await ItemService.get_item_by_name(session, "bronze_arrows")

        await InventoryService.add_item(session, player.id, sword.id)
        await InventoryService.add_item(session, player.id, arrows.id, quantity=50)

        result = await InventoryService.sort_inventory(
            session, player.id, InventorySortType.BY_NAME
        )

        assert result.success is True

        inv = await InventoryService.get_inventory(session, player.id)
        names = [i.item.display_name for i in inv]

        # "Bronze Arrows" comes before "Bronze Sword"
        assert names[0] == "Bronze Arrows"
        assert names[1] == "Bronze Sword"

    @pytest.mark.asyncio
    async def test_sort_compacts_items(
        self, session: AsyncSession, player_with_inventory
    ):
        """Sorting should compact items to front of inventory."""
        player = player_with_inventory

        sword = await ItemService.get_item_by_name(session, "bronze_sword")
        pickaxe = await ItemService.get_item_by_name(session, "bronze_pickaxe")

        # Add items to non-contiguous slots
        await InventoryService.add_item(session, player.id, sword.id)
        await InventoryService.add_item(session, player.id, pickaxe.id)

        # Move first item to slot 10 to create gap
        await InventoryService.move_item(session, player.id, 0, 10)

        # Sort should compact
        result = await InventoryService.sort_inventory(
            session, player.id, InventorySortType.BY_NAME
        )

        assert result.success is True

        inv = await InventoryService.get_inventory(session, player.id)
        slots = [i.slot for i in inv]

        # Should be 0, 1 (contiguous from start)
        assert 0 in slots
        assert 1 in slots

    @pytest.mark.asyncio
    async def test_sort_empty_inventory(
        self, session: AsyncSession, player_with_inventory
    ):
        """Sorting empty inventory should succeed."""
        player = player_with_inventory

        result = await InventoryService.sort_inventory(
            session, player.id, InventorySortType.BY_NAME
        )

        assert result.success is True
        assert result.items_moved == 0


# =============================================================================
# Merge Stacks Tests
# =============================================================================


class TestMergeStacks:
    """Test stack merging functionality."""

    @pytest.mark.asyncio
    async def test_merge_split_stacks(
        self, session: AsyncSession, player_with_inventory
    ):
        """Merge stacks should combine split stacks of same item."""
        player = player_with_inventory
        item = await ItemService.get_item_by_name(session, "copper_ore")

        # Create two separate stacks by manually inserting
        inv1 = PlayerInventory(
            player_id=player.id, item_id=item.id, slot=0, quantity=10
        )
        inv2 = PlayerInventory(
            player_id=player.id, item_id=item.id, slot=5, quantity=20
        )
        session.add(inv1)
        session.add(inv2)
        await session.commit()

        result = await InventoryService.merge_stacks(session, player.id)

        assert result.success is True
        assert result.stacks_merged >= 1

        # Should now have single stack with 30
        inv = await InventoryService.get_inventory(session, player.id)
        item_entries = [i for i in inv if i.item_id == item.id]

        total = sum(i.quantity for i in item_entries)
        assert total == 30

    @pytest.mark.asyncio
    async def test_merge_frees_slots(
        self, session: AsyncSession, player_with_inventory
    ):
        """Merging stacks should free up inventory slots."""
        player = player_with_inventory
        item = await ItemService.get_item_by_name(session, "copper_ore")

        # Create two small stacks
        inv1 = PlayerInventory(
            player_id=player.id, item_id=item.id, slot=0, quantity=10
        )
        inv2 = PlayerInventory(
            player_id=player.id, item_id=item.id, slot=1, quantity=10
        )
        session.add(inv1)
        session.add(inv2)
        await session.commit()

        count_before = await InventoryService.get_inventory_count(session, player.id)
        assert count_before == 2

        result = await InventoryService.merge_stacks(session, player.id)

        assert result.slots_freed >= 1

        count_after = await InventoryService.get_inventory_count(session, player.id)
        assert count_after == 1


# =============================================================================
# Inventory Response Tests
# =============================================================================


class TestInventoryResponse:
    """Test inventory response generation."""

    @pytest.mark.asyncio
    async def test_inventory_response_structure(
        self, session: AsyncSession, player_with_inventory
    ):
        """Inventory response should have all required fields."""
        player = player_with_inventory
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        await InventoryService.add_item(session, player.id, item.id)

        response = await InventoryService.get_inventory_response(session, player.id)

        assert response.max_slots == settings.INVENTORY_MAX_SLOTS
        assert response.used_slots == 1
        assert response.free_slots == settings.INVENTORY_MAX_SLOTS - 1
        assert len(response.slots) == 1

    @pytest.mark.asyncio
    async def test_inventory_slot_info_includes_item(
        self, session: AsyncSession, player_with_inventory
    ):
        """Each slot should include item info."""
        player = player_with_inventory
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        await InventoryService.add_item(session, player.id, item.id)

        response = await InventoryService.get_inventory_response(session, player.id)

        slot_info = response.slots[0]
        assert slot_info.item is not None
        assert slot_info.item.display_name == "Bronze Sword"
        assert slot_info.quantity == 1


# =============================================================================
# Has Item Tests
# =============================================================================


class TestHasItem:
    """Test checking if player has items."""

    @pytest.mark.asyncio
    async def test_has_item_true(
        self, session: AsyncSession, player_with_inventory
    ):
        """has_item should return True when player has enough."""
        player = player_with_inventory
        item = await ItemService.get_item_by_name(session, "copper_ore")

        await InventoryService.add_item(session, player.id, item.id, quantity=10)

        assert await InventoryService.has_item(session, player.id, item.id, 5) is True
        assert await InventoryService.has_item(session, player.id, item.id, 10) is True

    @pytest.mark.asyncio
    async def test_has_item_false(
        self, session: AsyncSession, player_with_inventory
    ):
        """has_item should return False when player doesn't have enough."""
        player = player_with_inventory
        item = await ItemService.get_item_by_name(session, "copper_ore")

        await InventoryService.add_item(session, player.id, item.id, quantity=5)

        assert await InventoryService.has_item(session, player.id, item.id, 10) is False

    @pytest.mark.asyncio
    async def test_has_item_across_stacks(
        self, session: AsyncSession, player_with_inventory
    ):
        """has_item should sum across multiple stacks."""
        player = player_with_inventory
        item = await ItemService.get_item_by_name(session, "copper_ore")

        # Create two stacks
        inv1 = PlayerInventory(
            player_id=player.id, item_id=item.id, slot=0, quantity=30
        )
        inv2 = PlayerInventory(
            player_id=player.id, item_id=item.id, slot=1, quantity=20
        )
        session.add(inv1)
        session.add(inv2)
        await session.commit()

        assert await InventoryService.has_item(session, player.id, item.id, 50) is True
        assert await InventoryService.has_item(session, player.id, item.id, 51) is False
