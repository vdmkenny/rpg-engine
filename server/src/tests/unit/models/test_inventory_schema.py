"""
Unit tests for inventory schema and item enums.
"""

import pytest

from server.src.core.items import (
    ItemType,
    ItemCategory,
    ItemRarity,
    InventorySortType,
    STACK_SIZE_MATERIALS,
)


class TestItemTypeEnum:
    """Test ItemType enum values."""

    def test_item_type_is_enum(self):
        """Test that ItemType is an enum with specific item definitions."""
        # ItemType contains specific items, not generic categories
        # Examples: BRONZE_DAGGER, IRON_SHORTSWORD, etc.
        from server.src.core.items import ItemType
        
        # Check some specific item types exist
        assert hasattr(ItemType, 'BRONZE_DAGGER')
        assert hasattr(ItemType, 'IRON_SHORTSWORD')
        assert hasattr(ItemType, 'LEATHER_BODY')
        
    def test_item_type_has_item_definitions(self):
        """Test that ItemType members have ItemDefinition values."""
        from server.src.core.items import ItemDefinition
        
        # ItemType values are ItemDefinition objects, not strings
        dagger = ItemType.BRONZE_DAGGER
        assert isinstance(dagger.value, ItemDefinition)
        assert dagger.value.display_name == "Bronze Dagger"
        assert dagger.value.category == ItemCategory.WEAPON


class TestItemCategoryEnum:
    """Test ItemCategory enum values."""

    def test_item_category_values(self):
        """Test that ItemCategory enum has expected values."""
        assert ItemCategory.WEAPON.value == "weapon"
        assert ItemCategory.ARMOR.value == "armor"
        assert ItemCategory.AMMUNITION.value == "ammunition"
        assert ItemCategory.CONSUMABLE.value == "consumable"
        assert ItemCategory.MATERIAL.value == "material"
        assert ItemCategory.TOOL.value == "tool"
        assert ItemCategory.QUEST.value == "quest"
        assert ItemCategory.CURRENCY.value == "currency"
        assert ItemCategory.NORMAL.value == "normal"

    def test_item_category_from_string(self):
        """Test that ItemCategory can be created from string."""
        assert ItemCategory("weapon") == ItemCategory.WEAPON
        assert ItemCategory("armor") == ItemCategory.ARMOR
        assert ItemCategory("ammunition") == ItemCategory.AMMUNITION


class TestItemRarityEnum:
    """Test ItemRarity enum values."""

    def test_item_rarity_values(self):
        """Test that ItemRarity enum has expected values."""
        assert ItemRarity.POOR.value == "poor"
        assert ItemRarity.COMMON.value == "common"
        assert ItemRarity.UNCOMMON.value == "uncommon"
        assert ItemRarity.RARE.value == "rare"
        assert ItemRarity.EPIC.value == "epic"
        assert ItemRarity.LEGENDARY.value == "legendary"


class TestInventorySortTypeEnum:
    """Test InventorySortType enum."""

    def test_inventory_sort_type_exists(self):
        """Test that InventorySortType enum exists."""
        # Enum should exist even if implementation varies
        assert InventorySortType is not None
