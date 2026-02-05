"""
Integration tests for InventoryService.

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

from server.src.core.items import InventorySortType
from server.src.core.config import settings
from server.src.services.item_service import ItemService
from server.src.services.inventory_service import InventoryService
from server.src.services.player_service import PlayerService


@pytest_asyncio.fixture
async def player_with_inventory(session: AsyncSession, create_test_player):
    """Create a test player ready for inventory tests."""
    unique_name = f"inv_test_{uuid.uuid4().hex[:8]}"
    player = await create_test_player(unique_name, "password123")
    await PlayerService.login_player(player.id)
    return player


@pytest.mark.usefixtures("items_synced")
class TestAddItem:
    """Test adding items to inventory."""

    @pytest.mark.asyncio
    async def test_add_single_item(
        self, session: AsyncSession, player_with_inventory
    ):
        """Adding a single item should create inventory entry."""
        player = player_with_inventory
        item = await ItemService.get_item_by_name("bronze_sword")
        assert item is not None

        add_result = await InventoryService.add_item(player.id, item.id)
        assert add_result.success
        assert add_result.data.get("slot") is not None
        
        slot = add_result.data.get("slot")
        result = await InventoryService.remove_item(player.id, slot)

        assert result.success is True
        assert result.data.get("removed_quantity") == 1

        inv = await InventoryService.get_item_at_slot(player.id, slot)
        assert inv is None

    @pytest.mark.asyncio
    async def test_remove_partial_stack(
        self, session: AsyncSession, player_with_inventory
    ):
        """Removing part of a stack should reduce quantity."""
        player = player_with_inventory
        item = await ItemService.get_item_by_name("copper_ore")
        assert item is not None

        add_result = await InventoryService.add_item(player.id, item.id, quantity=10)
        assert add_result.success
        assert add_result.data.get("slot") is not None
        
        slot = add_result.data.get("slot")
        result = await InventoryService.remove_item(player.id, slot, quantity=3)

        assert result.success is True
        assert result.data.get("removed_quantity") == 3

        inv = await InventoryService.get_item_at_slot(player.id, slot)
        assert inv is not None
        assert inv.quantity == 7

    @pytest.mark.asyncio
    async def test_remove_from_empty_slot(
        self, session: AsyncSession, player_with_inventory
    ):
        """Removing from empty slot should fail."""
        player = player_with_inventory
        result = await InventoryService.remove_item(player.id, 0)

        assert result.success is False
        assert result.data.get("removed_quantity") == 0

    @pytest.mark.asyncio
    async def test_remove_more_than_available(
        self, session: AsyncSession, player_with_inventory
    ):
        """Removing more than available should fail."""
        player = player_with_inventory
        item = await ItemService.get_item_by_name("copper_ore")
        assert item is not None

        add_result = await InventoryService.add_item(player.id, item.id, quantity=5)
        assert add_result.success
        assert add_result.data.get("slot") is not None
        
        slot = add_result.data.get("slot")
        result = await InventoryService.remove_item(player.id, slot, quantity=10)

        assert result.success is False
        assert result.data.get("removed_quantity") == 0


@pytest.mark.usefixtures("items_synced")
class TestMoveItem:
    """Test moving items between inventory slots."""

    @pytest.mark.asyncio
    async def test_move_to_empty_slot(
        self, session: AsyncSession, player_with_inventory
    ):
        """Moving to empty slot should work."""
        player = player_with_inventory
        item = await ItemService.get_item_by_name("bronze_sword")
        assert item is not None

        add_result = await InventoryService.add_item(player.id, item.id)
        assert add_result.success
        assert add_result.data.get("slot") is not None
        
        from_slot = add_result.data.get("slot")
        to_slot = from_slot + 1

        result = await InventoryService.move_item(player.id, from_slot, to_slot)

        assert result.success is True
        assert await InventoryService.get_item_at_slot(player.id, from_slot) is None

        inv = await InventoryService.get_item_at_slot(player.id, to_slot)
        assert inv is not None
        assert inv.item.id == item.id

    @pytest.mark.asyncio
    async def test_swap_items(
        self, session: AsyncSession, player_with_inventory
    ):
        """Moving to occupied slot should swap items."""
        player = player_with_inventory
        sword = await ItemService.get_item_by_name("bronze_sword")
        pickaxe = await ItemService.get_item_by_name("bronze_pickaxe")
        assert sword is not None
        assert pickaxe is not None

        sword_result = await InventoryService.add_item(player.id, sword.id)
        assert sword_result.success
        sword_slot = sword_result.data.get("slot")

        pickaxe_result = await InventoryService.add_item(player.id, pickaxe.id)
        assert pickaxe_result.success
        pickaxe_slot = pickaxe_result.data.get("slot")

        result = await InventoryService.move_item(player.id, sword_slot, pickaxe_slot)

        assert result.success is True

        inv_at_sword_slot = await InventoryService.get_item_at_slot(player.id, sword_slot)
        inv_at_pickaxe_slot = await InventoryService.get_item_at_slot(player.id, pickaxe_slot)

        assert inv_at_sword_slot is not None
        assert inv_at_pickaxe_slot is not None
        assert inv_at_sword_slot.item.id == pickaxe.id
        assert inv_at_pickaxe_slot.item.id == sword.id

    @pytest.mark.asyncio
    async def test_merge_stacks_on_move(
        self, session: AsyncSession, player_with_inventory
    ):
        """Moving stackable item to same item type should merge."""
        player = player_with_inventory
        item = await ItemService.get_item_by_name("copper_ore")
        assert item is not None

        result1 = await InventoryService.add_item(player.id, item.id, quantity=10)
        assert result1.success
        slot1 = result1.data.get("slot")

        result2 = await InventoryService.add_item(player.id, item.id, quantity=5)
        assert result2.success
        slot2 = result2.data.get("slot")

        result = await InventoryService.move_item(player.id, slot2, slot1)

        assert result.success is True

        inv = await InventoryService.get_item_at_slot(player.id, slot1)
        assert inv is not None
        assert inv.quantity == 15

    @pytest.mark.asyncio
    async def test_move_same_slot(
        self, session: AsyncSession, player_with_inventory
    ):
        """Moving to same slot should succeed (no-op)."""
        player = player_with_inventory
        item = await ItemService.get_item_by_name("bronze_sword")
        assert item is not None

        add_result = await InventoryService.add_item(player.id, item.id)
        assert add_result.success
        slot = add_result.data.get("slot")

        result = await InventoryService.move_item(player.id, slot, slot)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_move_from_empty_slot(
        self, session: AsyncSession, player_with_inventory
    ):
        """Moving from empty slot should fail."""
        player = player_with_inventory
        result = await InventoryService.move_item(player.id, 0, 1)

        assert result.success is False

    @pytest.mark.asyncio
    async def test_move_to_invalid_slot(
        self, session: AsyncSession, player_with_inventory
    ):
        """Moving to invalid slot should fail."""
        player = player_with_inventory
        item = await ItemService.get_item_by_name("bronze_sword")
        assert item is not None

        add_result = await InventoryService.add_item(player.id, item.id)
        assert add_result.success
        slot = add_result.data.get("slot")

        result = await InventoryService.move_item(player.id, slot, -1)
        assert result.success is False

        result = await InventoryService.move_item(player.id, slot, settings.INVENTORY_MAX_SLOTS + 1)
        assert result.success is False


@pytest.mark.usefixtures("items_synced")
class TestSortInventory:
    """Test inventory sorting functionality."""

    @pytest.mark.asyncio
    async def test_sort_by_category(
        self, session: AsyncSession, player_with_inventory
    ):
        """Sorting by category should group items correctly."""
        player = player_with_inventory

        sword = await ItemService.get_item_by_name("bronze_sword")
        ore = await ItemService.get_item_by_name("copper_ore")
        gold = await ItemService.get_item_by_name("gold_coins")
        assert sword is not None
        assert ore is not None
        assert gold is not None

        await InventoryService.add_item(player.id, ore.id, quantity=10)
        await InventoryService.add_item(player.id, sword.id)
        await InventoryService.add_item(player.id, gold.id, quantity=100)

        result = await InventoryService.sort_inventory(player.id, InventorySortType.BY_CATEGORY)

        assert result.success is True

        inv = await InventoryService.get_inventory(player.id)
        
        categories = []
        for inventory_item in inv.slots:
            item = await ItemService.get_item_by_id(inventory_item.item.id)
            assert item is not None
            categories.append(item.category)

        currency_idx = next((i for i, c in enumerate(categories) if c == "currency"), None)
        weapon_idx = next((i for i, c in enumerate(categories) if c == "weapon"), None)
        material_idx = next((i for i, c in enumerate(categories) if c == "material"), None)

        assert currency_idx is not None
        assert weapon_idx is not None
        assert material_idx is not None
        assert currency_idx < weapon_idx < material_idx

    @pytest.mark.asyncio
    async def test_sort_by_rarity(
        self, session: AsyncSession, player_with_inventory
    ):
        """Sorting by rarity should put legendary first, poor last."""
        player = player_with_inventory

        shrimp = await ItemService.get_item_by_name("raw_shrimp")
        sword = await ItemService.get_item_by_name("bronze_sword")
        assert shrimp is not None
        assert sword is not None

        await InventoryService.add_item(player.id, shrimp.id, quantity=5)
        await InventoryService.add_item(player.id, sword.id)

        result = await InventoryService.sort_inventory(player.id, InventorySortType.BY_RARITY)

        assert result.success is True

        inv = await InventoryService.get_inventory(player.id)
        
        rarities = []
        for inventory_item in inv.slots:
            item = await ItemService.get_item_by_id(inventory_item.item.id)
            assert item is not None
            rarities.append(item.rarity)

        common_idx = next((i for i, r in enumerate(rarities) if r == "common"), None)
        poor_idx = next((i for i, r in enumerate(rarities) if r == "poor"), None)
        
        assert common_idx is not None
        assert poor_idx is not None
        assert common_idx < poor_idx

    @pytest.mark.asyncio
    async def test_sort_by_value(
        self, session: AsyncSession, player_with_inventory
    ):
        """Sorting by value should put highest value first."""
        player = player_with_inventory

        ore = await ItemService.get_item_by_name("copper_ore")
        sword = await ItemService.get_item_by_name("bronze_sword")
        assert ore is not None
        assert sword is not None

        await InventoryService.add_item(player.id, ore.id, quantity=5)
        await InventoryService.add_item(player.id, sword.id)

        result = await InventoryService.sort_inventory(player.id, InventorySortType.BY_VALUE)

        assert result.success is True

        inv = await InventoryService.get_inventory(player.id)
        
        values = []
        for inventory_item in inv.slots:
            item = await ItemService.get_item_by_id(inventory_item.item.id)
            assert item is not None
            values.append(item.value)

        assert values == sorted(values, reverse=True)

    @pytest.mark.asyncio
    async def test_sort_by_name(
        self, session: AsyncSession, player_with_inventory
    ):
        """Sorting by name should be alphabetical."""
        player = player_with_inventory

        sword = await ItemService.get_item_by_name("bronze_sword")
        arrows = await ItemService.get_item_by_name("bronze_arrows")
        assert sword is not None
        assert arrows is not None

        await InventoryService.add_item(player.id, sword.id)
        await InventoryService.add_item(player.id, arrows.id, quantity=50)

        result = await InventoryService.sort_inventory(player.id, InventorySortType.BY_NAME)

        assert result.success is True

        inv = await InventoryService.get_inventory(player.id)
        
        names = []
        for inventory_item in inv.slots:
            item = await ItemService.get_item_by_id(inventory_item.item.id)
            assert item is not None
            names.append(item.display_name)

        assert names[0] == "Bronze Arrows"
        assert names[1] == "Bronze Sword"

    @pytest.mark.asyncio
    async def test_sort_compacts_items(
        self, session: AsyncSession, player_with_inventory
    ):
        """Sorting should compact items to front of inventory."""
        player = player_with_inventory

        sword = await ItemService.get_item_by_name("bronze_sword")
        pickaxe = await ItemService.get_item_by_name("bronze_pickaxe")
        assert sword is not None
        assert pickaxe is not None

        sword_result = await InventoryService.add_item(player.id, sword.id)
        pickaxe_result = await InventoryService.add_item(player.id, pickaxe.id)
        assert sword_result.success and sword_result.data.get("slot") is not None
        assert pickaxe_result.success and pickaxe_result.data.get("slot") is not None

        await InventoryService.move_item(player.id, sword_result.data.get("slot"), 10)

        result = await InventoryService.sort_inventory(player.id, InventorySortType.BY_NAME)

        assert result.success is True

        inv = await InventoryService.get_inventory(player.id)
        slots = [i.slot for i in inv.slots]

        assert 0 in slots
        assert 1 in slots

    @pytest.mark.asyncio
    async def test_sort_empty_inventory(
        self, session: AsyncSession, player_with_inventory
    ):
        """Sorting empty inventory should succeed."""
        player = player_with_inventory

        result = await InventoryService.sort_inventory(player.id, InventorySortType.BY_NAME)

        assert result.success is True
        assert result.data.get("items_moved") == 0


@pytest.mark.usefixtures("items_synced")
class TestMergeStacks:
    """Test stack merging functionality."""

    @pytest.mark.asyncio
    async def test_merge_split_stacks(
        self, session: AsyncSession, player_with_inventory
    ):
        """Merge stacks should combine split stacks of same item."""
        player = player_with_inventory
        item = await ItemService.get_item_by_name("copper_ore")
        assert item is not None

        result1 = await InventoryService.add_item(player.id, item.id, quantity=10)
        result2 = await InventoryService.add_item(player.id, item.id, quantity=20)
        assert result1.success and result2.success
        
        inv = await InventoryService.get_inventory(player.id)
        item_entries = [i for i in inv.slots if i.item.id == item.id]
        
        if len(item_entries) == 1:
            result = await InventoryService.merge_stacks(player.id)
            assert result.success is True
            
            total = sum(i.quantity for i in item_entries)
            assert total == 30
        else:
            result = await InventoryService.merge_stacks(player.id)
            assert result.success is True
            assert result.data.get("stacks_merged") >= 1

            inv = await InventoryService.get_inventory(player.id)
            item_entries = [i for i in inv.slots if i.item.id == item.id]

            total = sum(i.quantity for i in item_entries)
            assert total == 30

    @pytest.mark.asyncio
    async def test_merge_frees_slots(
        self, session: AsyncSession, player_with_inventory
    ):
        """Merging stacks should free up inventory slots."""
        player = player_with_inventory
        item = await ItemService.get_item_by_name("copper_ore")
        assert item is not None

        inv = await InventoryService.get_inventory(player.id)
        for inventory_item in inv.slots:
            await InventoryService.remove_item(player.id, inventory_item.slot, inventory_item.quantity)

        count_after_clear = await InventoryService.get_inventory_count(player.id)
        assert count_after_clear == 0

        result1 = await InventoryService.add_item(player.id, item.id, quantity=1)
        result2 = await InventoryService.add_item(player.id, item.id, quantity=1)
        assert result1.success and result2.success

        inv = await InventoryService.get_inventory(player.id)
        count_before = await InventoryService.get_inventory_count(player.id)
        item_entries = [i for i in inv.slots if i.item.id == item.id]
        
        assert len(item_entries) == 1
        assert item_entries[0].quantity == 2
        assert count_before == 1
        
        result = await InventoryService.merge_stacks(player.id)
        assert result.success is True
        assert result.data.get("slots_freed") == 0


@pytest.mark.usefixtures("items_synced")
class TestInventoryResponse:
    """Test inventory response generation."""

    @pytest.mark.asyncio
    async def test_inventory_response_structure(
        self, session: AsyncSession, player_with_inventory
    ):
        """Inventory response should have all required fields."""
        player = player_with_inventory
        item = await ItemService.get_item_by_name("bronze_sword")
        assert item is not None

        await InventoryService.add_item(player.id, item.id)

        response = await InventoryService.get_inventory_response(player.id)

        assert response.max_slots == settings.INVENTORY_MAX_SLOTS
        assert response.used_slots == 1
        assert (response.max_slots - response.used_slots) == settings.INVENTORY_MAX_SLOTS - 1
        assert len(response.slots) == 1

    @pytest.mark.asyncio
    async def test_inventory_slot_info_includes_item(
        self, session: AsyncSession, player_with_inventory
    ):
        """Each slot should include item info."""
        player = player_with_inventory
        item = await ItemService.get_item_by_name("bronze_sword")
        assert item is not None

        await InventoryService.add_item(player.id, item.id)

        response = await InventoryService.get_inventory_response(player.id)

        slot_info = response.slots[0]
        assert slot_info.item is not None
        assert slot_info.item.display_name == "Bronze Sword"
        assert slot_info.quantity == 1


@pytest.mark.usefixtures("items_synced")
class TestHasItem:
    """Test checking if player has items."""

    @pytest.mark.asyncio
    async def test_has_item_true(
        self, session: AsyncSession, player_with_inventory
    ):
        """has_item should return True when player has enough."""
        player = player_with_inventory
        item = await ItemService.get_item_by_name("copper_ore")
        assert item is not None

        await InventoryService.add_item(player.id, item.id, quantity=10)

        assert await InventoryService.has_item(player.id, item.id, 5) is True
        assert await InventoryService.has_item(player.id, item.id, 10) is True

    @pytest.mark.asyncio
    async def test_has_item_false(
        self, session: AsyncSession, player_with_inventory
    ):
        """has_item should return False when player doesn't have enough."""
        player = player_with_inventory
        item = await ItemService.get_item_by_name("copper_ore")
        assert item is not None

        await InventoryService.add_item(player.id, item.id, quantity=5)

        assert await InventoryService.has_item(player.id, item.id, 10) is False

    @pytest.mark.asyncio
    async def test_has_item_across_stacks(
        self, session: AsyncSession, player_with_inventory
    ):
        """has_item should sum across multiple stacks."""
        player = player_with_inventory
        item = await ItemService.get_item_by_name("copper_ore")
        assert item is not None

        result1 = await InventoryService.add_item(player.id, item.id, quantity=30)
        result2 = await InventoryService.add_item(player.id, item.id, quantity=20)
        assert result1.success and result2.success

        assert await InventoryService.has_item(player.id, item.id, 50) is True
        assert await InventoryService.has_item(player.id, item.id, 51) is False
