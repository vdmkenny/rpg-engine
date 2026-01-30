"""
Tests for the item system.

Tests cover:
- Item enums and definitions
- ItemType metadata
- Item service operations (sync, lookup)
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from server.src.core.items import (
    ItemType,
    ItemRarity,
    ItemCategory,
    EquipmentSlot,
    AmmoType,
    RequiredSkill,
    InventorySortType,
    CATEGORY_SORT_ORDER,
    RARITY_SORT_ORDER,
    EQUIPMENT_SLOT_SORT_ORDER,
    STACK_SIZE_SINGLE,
    STACK_SIZE_MATERIALS,
    STACK_SIZE_AMMUNITION,
    STACK_SIZE_CURRENCY,
)
from server.src.models.item import Item
from server.src.services.item_service import ItemService


# =============================================================================
# Item Enum Tests
# =============================================================================


class TestItemRarity:
    """Test ItemRarity enum and properties."""

    def test_all_rarities_have_colors(self):
        """Every rarity should have an associated hex color."""
        for rarity in ItemRarity:
            assert rarity.color is not None
            assert rarity.color.startswith("#")
            assert len(rarity.color) == 7  # #RRGGBB format

    def test_rarity_values(self):
        """Test expected rarity values exist."""
        expected = ["poor", "common", "uncommon", "rare", "epic", "legendary"]
        actual = [r.value for r in ItemRarity]
        for rarity in expected:
            assert rarity in actual

    def test_rarity_sort_order_covers_all(self):
        """RARITY_SORT_ORDER should cover all rarities."""
        for rarity in ItemRarity:
            assert rarity in RARITY_SORT_ORDER


class TestItemCategory:
    """Test ItemCategory enum."""

    def test_all_expected_categories_exist(self):
        """All expected categories should be defined."""
        expected = [
            "normal", "tool", "weapon", "armor", "consumable",
            "quest", "material", "currency", "ammunition"
        ]
        actual = [c.value for c in ItemCategory]
        for category in expected:
            assert category in actual

    def test_category_sort_order_covers_all(self):
        """CATEGORY_SORT_ORDER should cover all categories."""
        for category in ItemCategory:
            assert category in CATEGORY_SORT_ORDER


class TestEquipmentSlot:
    """Test EquipmentSlot enum."""

    def test_eleven_equipment_slots(self):
        """There should be exactly 11 equipment slots."""
        assert len(EquipmentSlot) == 11

    def test_expected_slots_exist(self):
        """All expected equipment slots should exist."""
        expected = [
            "head", "cape", "amulet", "weapon", "body",
            "shield", "legs", "gloves", "boots", "ring", "ammo"
        ]
        actual = [s.value for s in EquipmentSlot]
        for slot in expected:
            assert slot in actual

    def test_slot_sort_order_covers_all(self):
        """EQUIPMENT_SLOT_SORT_ORDER should cover all slots."""
        for slot in EquipmentSlot:
            assert slot in EQUIPMENT_SLOT_SORT_ORDER


class TestInventorySortType:
    """Test InventorySortType enum."""

    def test_all_sort_types_exist(self):
        """All expected sort types should be defined."""
        expected = [
            "category", "rarity", "value", "name",
            "stack_merge", "equipment_slot"
        ]
        actual = [s.value for s in InventorySortType]
        for sort_type in expected:
            assert sort_type in actual


# =============================================================================
# Item Definition Tests
# =============================================================================


class TestItemDefinitions:
    """Test ItemType enum and item metadata."""

    def test_all_items_have_display_names(self):
        """Every item should have a non-empty display name."""
        for item in ItemType:
            assert item.value.display_name
            assert len(item.value.display_name) > 0

    def test_all_items_have_descriptions(self):
        """Every item should have a non-empty description."""
        for item in ItemType:
            assert item.value.description
            assert len(item.value.description) > 0

    def test_all_items_have_valid_categories(self):
        """Every item should have a valid category."""
        for item in ItemType:
            assert isinstance(item.value.category, ItemCategory)

    def test_all_items_have_valid_rarity(self):
        """Every item should have a valid rarity."""
        for item in ItemType:
            assert isinstance(item.value.rarity, ItemRarity)

    def test_from_name_case_insensitive(self):
        """from_name should be case-insensitive."""
        assert ItemType.from_name("bronze_sword") == ItemType.BRONZE_SWORD
        assert ItemType.from_name("BRONZE_SWORD") == ItemType.BRONZE_SWORD
        assert ItemType.from_name("Bronze_Sword") == ItemType.BRONZE_SWORD

    def test_from_name_returns_none_for_invalid(self):
        """from_name should return None for invalid item names."""
        assert ItemType.from_name("invalid_item") is None
        assert ItemType.from_name("") is None

    def test_all_item_names_returns_lowercase(self):
        """all_item_names should return lowercase names."""
        names = ItemType.all_item_names()
        for name in names:
            assert name == name.lower()

    def test_equipable_items_have_equipment_slot(self):
        """Items returned by get_equipable_items should have equipment_slot."""
        equipable = ItemType.get_equipable_items()
        for item in equipable:
            assert item.value.equipment_slot is not None

    def test_is_stackable_property(self):
        """is_stackable should return True only when max_stack_size > 1."""
        # Gold coins should be stackable
        assert ItemType.GOLD_COINS.value.is_stackable is True
        assert ItemType.GOLD_COINS.value.max_stack_size == STACK_SIZE_CURRENCY

        # Bronze sword should not be stackable
        assert ItemType.BRONZE_SWORD.value.is_stackable is False
        assert ItemType.BRONZE_SWORD.value.max_stack_size == STACK_SIZE_SINGLE


class TestStackSizes:
    """Test stack size constants and item stack sizes."""

    def test_stack_size_constants(self):
        """Stack size constants should have expected values."""
        assert STACK_SIZE_SINGLE == 1
        assert STACK_SIZE_MATERIALS == 64
        assert STACK_SIZE_AMMUNITION == 8192
        assert STACK_SIZE_CURRENCY == 2147483647

    def test_equipment_not_stackable(self):
        """Equipment items (except ammunition) should have max_stack_size of 1."""
        for item in ItemType.get_equipable_items():
            # Ammunition is special - equipable but stackable
            if item.value.category == ItemCategory.AMMUNITION:
                assert item.value.max_stack_size == STACK_SIZE_AMMUNITION
            else:
                assert item.value.max_stack_size == 1

    def test_materials_stackable(self):
        """Material items should have appropriate stack size."""
        materials = ItemType.get_by_category(ItemCategory.MATERIAL)
        for item in materials:
            assert item.value.max_stack_size == STACK_SIZE_MATERIALS

    def test_ammunition_stackable(self):
        """Ammunition items should have large stack size."""
        ammo = ItemType.get_by_category(ItemCategory.AMMUNITION)
        for item in ammo:
            assert item.value.max_stack_size == STACK_SIZE_AMMUNITION

    def test_currency_highly_stackable(self):
        """Currency items should have maximum stack size."""
        currency = ItemType.get_by_category(ItemCategory.CURRENCY)
        for item in currency:
            assert item.value.max_stack_size == STACK_SIZE_CURRENCY


class TestItemStats:
    """Test item stat definitions."""

    def test_bronze_platebody_has_negative_magic_bonus(self):
        """Heavy metal armor should have negative magic attack bonus."""
        platebody = ItemType.BRONZE_PLATEBODY.value
        assert platebody.magic_attack_bonus < 0
        assert platebody.physical_defence_bonus > 0

    def test_bronze_platebody_has_negative_speed(self):
        """Heavy armor should have negative speed bonus."""
        platebody = ItemType.BRONZE_PLATEBODY.value
        assert platebody.speed_bonus < 0

    def test_weapons_have_positive_attack_stats(self):
        """Weapons should have positive attack bonuses."""
        sword = ItemType.BRONZE_SWORD.value
        assert sword.attack_bonus > 0 or sword.strength_bonus > 0

    def test_ranged_weapons_have_ranged_stats(self):
        """Ranged weapons should have ranged attack bonuses."""
        bow = ItemType.SHORTBOW.value
        assert bow.ranged_attack_bonus > 0 or bow.ranged_strength_bonus > 0

    def test_tools_have_gathering_bonuses(self):
        """Gathering tools should have appropriate bonuses."""
        pickaxe = ItemType.BRONZE_PICKAXE.value
        assert pickaxe.mining_bonus > 0

        axe = ItemType.BRONZE_AXE.value
        assert axe.woodcutting_bonus > 0

        net = ItemType.FISHING_NET.value
        assert net.fishing_bonus > 0


class TestTwoHandedItems:
    """Test two-handed weapon logic."""

    def test_two_handed_sword_is_marked(self):
        """Two-handed sword should have is_two_handed=True."""
        sword = ItemType.BRONZE_2H_SWORD.value
        assert sword.is_two_handed is True
        assert sword.equipment_slot == EquipmentSlot.WEAPON

    def test_bows_are_two_handed(self):
        """Bows should be two-handed."""
        shortbow = ItemType.SHORTBOW.value
        assert shortbow.is_two_handed is True

        oak_shortbow = ItemType.OAK_SHORTBOW.value
        assert oak_shortbow.is_two_handed is True

    def test_regular_sword_is_one_handed(self):
        """Regular swords should not be two-handed."""
        sword = ItemType.BRONZE_SWORD.value
        assert sword.is_two_handed is False


# =============================================================================
# Item Service Tests (Database)
# =============================================================================


class TestItemServiceSync:
    """Test item synchronization to database."""

    @pytest.mark.asyncio
    async def test_sync_items_creates_all_items(self, session: AsyncSession, gsm):
        """sync_items_to_db should ensure all items exist in the database."""
        await ItemService.sync_items_to_db()

        # Verify all items are in database (might have been synced by fixtures)
        from sqlalchemy import select
        from server.src.models.item import Item
        result = await session.execute(select(Item))
        items = result.scalars().all()
        
        # Should have at least as many items as ItemType defines
        assert len(items) >= len(ItemType)

        # Verify all ItemType items exist by name
        item_names = {i.name for i in items}
        for item_type in ItemType:
            assert item_type.name.lower() in item_names

    @pytest.mark.asyncio
    async def test_sync_items_is_idempotent(self, session: AsyncSession, gsm):
        """Calling sync_items_to_db multiple times should not create duplicates."""
        # Get initial count
        from sqlalchemy import select
        from server.src.models.item import Item
        initial_result = await session.execute(select(Item))
        initial_count = len(initial_result.scalars().all())
        
        # Sync items twice
        await ItemService.sync_items_to_db()
        await ItemService.sync_items_to_db()

        # Verify count didn't change (idempotent)
        final_result = await session.execute(select(Item))
        final_items = final_result.scalars().all()
        assert len(final_items) == initial_count
        
        # Verify all ItemType items still exist
        item_names = {i.name for i in final_items}
        for item_type in ItemType:
            assert item_type.name.lower() in item_names

    @pytest.mark.asyncio
    async def test_synced_items_have_correct_stats(self, session: AsyncSession, gsm):
        """Synced items should have correct stats from definitions."""
        await ItemService.sync_items_to_db()

        item = await ItemService.get_item_by_name("bronze_sword")
        assert item is not None
        assert item.attack_bonus == ItemType.BRONZE_SWORD.value.attack_bonus
        assert item.strength_bonus == ItemType.BRONZE_SWORD.value.strength_bonus


class TestItemServiceLookup:
    """Test item lookup operations."""

    @pytest.mark.asyncio
    async def test_get_item_by_name(self, session: AsyncSession, gsm):
        """get_item_by_name should return the correct item."""
        await ItemService.sync_items_to_db()

        item = await ItemService.get_item_by_name("bronze_sword")
        assert item is not None
        assert item.display_name == "Bronze Sword"

    @pytest.mark.asyncio
    async def test_get_item_by_name_case_insensitive(self, session: AsyncSession, gsm):
        """get_item_by_name should be case-insensitive."""
        await ItemService.sync_items_to_db()

        item1 = await ItemService.get_item_by_name("bronze_sword")
        item2 = await ItemService.get_item_by_name("BRONZE_SWORD")
        assert item1 is not None
        assert item2 is not None
        assert item1.id == item2.id

    @pytest.mark.asyncio
    async def test_get_item_by_name_returns_none_for_invalid(
        self, session: AsyncSession, gsm
    ):
        """get_item_by_name should return None for invalid names."""
        await ItemService.sync_items_to_db()

        item = await ItemService.get_item_by_name("invalid_item")
        assert item is None

    @pytest.mark.asyncio
    async def test_get_item_by_id(self, session: AsyncSession, gsm):
        """get_item_by_id should return the correct item."""
        await ItemService.sync_items_to_db()

        item = await ItemService.get_item_by_name("bronze_sword")
        assert item is not None

        item_by_id = await ItemService.get_item_by_id(item.id)
        assert item_by_id is not None
        assert item_by_id.id == item.id

    @pytest.mark.asyncio
    async def test_get_item_by_id_returns_none_for_invalid(self, session: AsyncSession, gsm):
        """get_item_by_id should return None for invalid IDs."""
        await ItemService.sync_items_to_db()

        item = await ItemService.get_item_by_id(99999)
        assert item is None

class TestItemToInfo:
    """Test item_to_info conversion."""

    @pytest.mark.asyncio
    async def test_item_to_info_includes_all_fields(self, session: AsyncSession, gsm):
        """item_to_info should return all expected fields."""
        await ItemService.sync_items_to_db()

        item = await ItemService.get_item_by_name("bronze_sword")
        assert item is not None

        info = ItemService.item_to_info(item._data)

        assert info.id == item.id
        assert info.name == item.name
        assert info.display_name == item.display_name
        assert info.description == item.description
        assert info.category == item.category
        assert info.rarity == item.rarity
        assert info.equipment_slot == item.equipment_slot
        assert info.max_stack_size == item.max_stack_size
        assert info.value == item.value

    @pytest.mark.asyncio
    async def test_item_to_info_includes_stats(self, session: AsyncSession, gsm):
        """item_to_info should include all stat bonuses."""
        await ItemService.sync_items_to_db()

        item = await ItemService.get_item_by_name("bronze_platebody")
        assert item is not None

        info = ItemService.item_to_info(item._data)

        assert info.stats.attack_bonus == item.attack_bonus
        assert info.stats.physical_defence_bonus == item.physical_defence_bonus
        assert info.stats.magic_attack_bonus == item.magic_attack_bonus
        assert info.stats.health_bonus == item.health_bonus

    @pytest.mark.asyncio
    async def test_item_to_info_includes_rarity_color(self, session: AsyncSession, gsm):
        """item_to_info should include rarity color for UI display."""
        await ItemService.sync_items_to_db()

        item = await ItemService.get_item_by_name("gold_coins")
        assert item is not None

        info = ItemService.item_to_info(item._data)

        # Check that rarity color is included
        assert hasattr(info, 'rarity_color')
        assert info.rarity_color is not None
        assert info.rarity_color.startswith("#")
