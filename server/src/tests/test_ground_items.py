"""
Tests for the ground items system.

Tests cover:
- Creating ground items
- Dropping items from inventory
- Picking up items (including race conditions)
- Visibility rules (loot protection)
- Cleanup of expired items
- Death drops (inventory + equipment)
"""

import uuid
import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from server.src.core.items import ItemType, ItemRarity, EquipmentSlot
from server.src.core.config import settings
from server.src.models.item import Item, PlayerInventory, PlayerEquipment, GroundItem
from server.src.models.skill import Skill, PlayerSkill
from server.src.services.item_service import ItemService
from server.src.services.inventory_service import InventoryService
from server.src.services.equipment_service import EquipmentService
from server.src.services.ground_item_service import GroundItemService


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest_asyncio.fixture
async def items_synced(session: AsyncSession):
    """Ensure items are synced to database."""
    await ItemService.sync_items_to_db(session)


@pytest_asyncio.fixture
async def player_for_ground_items(
    session: AsyncSession, create_test_player, items_synced
):
    """Create a test player ready for ground item tests."""
    unique_name = f"ground_test_{uuid.uuid4().hex[:8]}"
    player = await create_test_player(
        unique_name, "password123", x=10, y=10, map_id="testmap"
    )
    return player


@pytest_asyncio.fixture
async def second_player(session: AsyncSession, create_test_player, items_synced):
    """Create a second test player for pickup tests."""
    unique_name = f"second_{uuid.uuid4().hex[:8]}"
    player = await create_test_player(
        unique_name, "password123", x=10, y=10, map_id="testmap"
    )
    return player


async def give_player_skill_level(
    session: AsyncSession, player_id: int, skill_name: str, level: int
):
    """Helper to give a player a specific skill level."""
    result = await session.execute(select(Skill).where(Skill.name == skill_name))
    skill = result.scalar_one_or_none()
    if not skill:
        skill = Skill(name=skill_name)
        session.add(skill)
        await session.flush()

    result = await session.execute(
        select(PlayerSkill)
        .where(PlayerSkill.player_id == player_id)
        .where(PlayerSkill.skill_id == skill.id)
    )
    player_skill = result.scalar_one_or_none()

    if player_skill:
        player_skill.current_level = level
    else:
        player_skill = PlayerSkill(
            player_id=player_id,
            skill_id=skill.id,
            current_level=level,
            experience=0,
        )
        session.add(player_skill)

    await session.commit()


# =============================================================================
# Create Ground Item Tests
# =============================================================================


class TestCreateGroundItem:
    """Test creating ground items."""

    @pytest.mark.asyncio
    async def test_create_ground_item_basic(
        self, session: AsyncSession, player_for_ground_items
    ):
        """Basic ground item creation should work."""
        player = player_for_ground_items
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        ground_item = await GroundItemService.create_ground_item(
            db=session,
            item_id=item.id,
            map_id="testmap",
            x=10,
            y=10,
            quantity=1,
            dropped_by=player.id,
        )

        assert ground_item is not None
        assert ground_item.item_id == item.id
        assert ground_item.map_id == "testmap"
        assert ground_item.x == 10
        assert ground_item.y == 10
        assert ground_item.quantity == 1
        assert ground_item.dropped_by == player.id

    @pytest.mark.asyncio
    async def test_create_ground_item_rarity_timers(
        self, session: AsyncSession, player_for_ground_items
    ):
        """Ground items should have rarity-based despawn timers."""
        player = player_for_ground_items
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        ground_item = await GroundItemService.create_ground_item(
            db=session,
            item_id=item.id,
            map_id="testmap",
            x=10,
            y=10,
            dropped_by=player.id,
        )

        # Should have public_at and despawn_at set
        assert ground_item.public_at is not None
        assert ground_item.despawn_at is not None

        # public_at should be in the future (protection period)
        assert ground_item.public_at > now

        # despawn_at should be after public_at
        assert ground_item.despawn_at > ground_item.public_at

    @pytest.mark.asyncio
    async def test_create_ground_item_invalid_item(
        self, session: AsyncSession, player_for_ground_items
    ):
        """Creating with invalid item ID should return None."""
        player = player_for_ground_items

        ground_item = await GroundItemService.create_ground_item(
            db=session,
            item_id=99999,
            map_id="testmap",
            x=10,
            y=10,
            dropped_by=player.id,
        )

        assert ground_item is None

    @pytest.mark.asyncio
    async def test_create_ground_item_with_durability(
        self, session: AsyncSession, player_for_ground_items
    ):
        """Ground items should preserve durability."""
        player = player_for_ground_items
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        ground_item = await GroundItemService.create_ground_item(
            db=session,
            item_id=item.id,
            map_id="testmap",
            x=10,
            y=10,
            dropped_by=player.id,
            current_durability=250,
        )

        assert ground_item.current_durability == 250


# =============================================================================
# Drop From Inventory Tests
# =============================================================================


class TestDropFromInventory:
    """Test dropping items from inventory."""

    @pytest.mark.asyncio
    async def test_drop_entire_stack(
        self, session: AsyncSession, player_for_ground_items
    ):
        """Dropping entire stack should work."""
        player = player_for_ground_items
        item = await ItemService.get_item_by_name(session, "copper_ore")

        # Add to inventory
        await InventoryService.add_item(session, player.id, item.id, quantity=10)

        # Drop
        result = await GroundItemService.drop_from_inventory(
            db=session,
            player_id=player.id,
            inventory_slot=0,
            map_id="testmap",
            x=10,
            y=10,
        )

        assert result.success is True
        assert result.ground_item_id is not None

        # Inventory should be empty
        inv = await InventoryService.get_item_at_slot(session, player.id, 0)
        assert inv is None

    @pytest.mark.asyncio
    async def test_drop_partial_stack(
        self, session: AsyncSession, player_for_ground_items
    ):
        """Dropping partial stack should leave remainder."""
        player = player_for_ground_items
        item = await ItemService.get_item_by_name(session, "copper_ore")

        # Add to inventory
        await InventoryService.add_item(session, player.id, item.id, quantity=10)

        # Drop partial
        result = await GroundItemService.drop_from_inventory(
            db=session,
            player_id=player.id,
            inventory_slot=0,
            map_id="testmap",
            x=10,
            y=10,
            quantity=3,
        )

        assert result.success is True

        # Inventory should have remainder
        inv = await InventoryService.get_item_at_slot(session, player.id, 0)
        assert inv is not None
        assert inv.quantity == 7

    @pytest.mark.asyncio
    async def test_drop_from_empty_slot(
        self, session: AsyncSession, player_for_ground_items
    ):
        """Dropping from empty slot should fail."""
        player = player_for_ground_items

        result = await GroundItemService.drop_from_inventory(
            db=session,
            player_id=player.id,
            inventory_slot=0,
            map_id="testmap",
            x=10,
            y=10,
        )

        assert result.success is False
        assert "empty" in result.message.lower()

    @pytest.mark.asyncio
    async def test_drop_more_than_available(
        self, session: AsyncSession, player_for_ground_items
    ):
        """Dropping more than available should fail."""
        player = player_for_ground_items
        item = await ItemService.get_item_by_name(session, "copper_ore")

        # Add to inventory
        await InventoryService.add_item(session, player.id, item.id, quantity=5)

        # Try to drop more
        result = await GroundItemService.drop_from_inventory(
            db=session,
            player_id=player.id,
            inventory_slot=0,
            map_id="testmap",
            x=10,
            y=10,
            quantity=10,
        )

        assert result.success is False

    @pytest.mark.asyncio
    async def test_drop_preserves_durability(
        self, session: AsyncSession, player_for_ground_items
    ):
        """Dropped items should preserve durability."""
        player = player_for_ground_items
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        # Add with durability
        await InventoryService.add_item(session, player.id, item.id, durability=250)

        # Drop
        result = await GroundItemService.drop_from_inventory(
            db=session,
            player_id=player.id,
            inventory_slot=0,
            map_id="testmap",
            x=10,
            y=10,
        )

        # Check ground item has durability
        ground_item = await GroundItemService.get_ground_item(
            session, result.ground_item_id
        )
        assert ground_item.current_durability == 250


# =============================================================================
# Pickup Item Tests
# =============================================================================


class TestPickupItem:
    """Test picking up ground items."""

    @pytest.mark.asyncio
    async def test_pickup_own_item(
        self, session: AsyncSession, player_for_ground_items
    ):
        """Owner should be able to pick up their item during protection."""
        player = player_for_ground_items
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        # Create ground item
        ground_item = await GroundItemService.create_ground_item(
            db=session,
            item_id=item.id,
            map_id="testmap",
            x=10,
            y=10,
            dropped_by=player.id,
        )

        # Pick up (player is on same tile)
        result = await GroundItemService.pickup_item(
            db=session,
            player_id=player.id,
            ground_item_id=ground_item.id,
            player_x=10,
            player_y=10,
            player_map_id="testmap",
        )

        assert result.success is True
        assert result.inventory_slot is not None

        # Should be in inventory
        inv = await InventoryService.get_item_at_slot(
            session, player.id, result.inventory_slot
        )
        assert inv is not None
        assert inv.item_id == item.id

        # Ground item should be gone
        ground = await GroundItemService.get_ground_item(session, ground_item.id)
        assert ground is None

    @pytest.mark.asyncio
    async def test_pickup_wrong_tile(
        self, session: AsyncSession, player_for_ground_items
    ):
        """Cannot pick up item from different tile."""
        player = player_for_ground_items
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        # Create ground item
        ground_item = await GroundItemService.create_ground_item(
            db=session,
            item_id=item.id,
            map_id="testmap",
            x=10,
            y=10,
            dropped_by=player.id,
        )

        # Try to pick up from wrong tile
        result = await GroundItemService.pickup_item(
            db=session,
            player_id=player.id,
            ground_item_id=ground_item.id,
            player_x=15,
            player_y=10,
            player_map_id="testmap",
        )

        assert result.success is False
        assert "same tile" in result.message.lower()

    @pytest.mark.asyncio
    async def test_pickup_protected_item(
        self, session: AsyncSession, player_for_ground_items, second_player
    ):
        """Other players cannot pick up protected items."""
        player = player_for_ground_items
        other = second_player
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        # Create ground item (owned by player, still protected)
        ground_item = await GroundItemService.create_ground_item(
            db=session,
            item_id=item.id,
            map_id="testmap",
            x=10,
            y=10,
            dropped_by=player.id,
        )

        # Other player tries to pick up during protection
        result = await GroundItemService.pickup_item(
            db=session,
            player_id=other.id,
            ground_item_id=ground_item.id,
            player_x=10,
            player_y=10,
            player_map_id="testmap",
        )

        assert result.success is False
        assert "protected" in result.message.lower()

    @pytest.mark.asyncio
    async def test_pickup_public_item(
        self, session: AsyncSession, player_for_ground_items, second_player
    ):
        """Anyone can pick up public (unprotected) items."""
        player = player_for_ground_items
        other = second_player
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        # Create ground item
        ground_item = await GroundItemService.create_ground_item(
            db=session,
            item_id=item.id,
            map_id="testmap",
            x=10,
            y=10,
            dropped_by=player.id,
        )

        # Make item public (protection expired)
        ground_item.public_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
        await session.commit()

        # Other player picks up
        result = await GroundItemService.pickup_item(
            db=session,
            player_id=other.id,
            ground_item_id=ground_item.id,
            player_x=10,
            player_y=10,
            player_map_id="testmap",
        )

        assert result.success is True

    @pytest.mark.asyncio
    async def test_pickup_nonexistent_item(
        self, session: AsyncSession, player_for_ground_items
    ):
        """Picking up nonexistent item should fail."""
        player = player_for_ground_items

        result = await GroundItemService.pickup_item(
            db=session,
            player_id=player.id,
            ground_item_id=99999,
            player_x=10,
            player_y=10,
            player_map_id="testmap",
        )

        assert result.success is False
        assert "not found" in result.message.lower()

    @pytest.mark.asyncio
    async def test_pickup_despawned_item(
        self, session: AsyncSession, player_for_ground_items
    ):
        """Picking up despawned item should fail."""
        player = player_for_ground_items
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        # Create ground item
        ground_item = await GroundItemService.create_ground_item(
            db=session,
            item_id=item.id,
            map_id="testmap",
            x=10,
            y=10,
            dropped_by=player.id,
        )

        # Make item despawned
        ground_item.despawn_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
        await session.commit()

        # Try to pick up
        result = await GroundItemService.pickup_item(
            db=session,
            player_id=player.id,
            ground_item_id=ground_item.id,
            player_x=10,
            player_y=10,
            player_map_id="testmap",
        )

        assert result.success is False
        assert "despawned" in result.message.lower()

    @pytest.mark.asyncio
    async def test_pickup_preserves_durability(
        self, session: AsyncSession, player_for_ground_items
    ):
        """Picked up items should preserve durability."""
        player = player_for_ground_items
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        # Create ground item with durability
        ground_item = await GroundItemService.create_ground_item(
            db=session,
            item_id=item.id,
            map_id="testmap",
            x=10,
            y=10,
            dropped_by=player.id,
            current_durability=150,
        )

        # Pick up
        result = await GroundItemService.pickup_item(
            db=session,
            player_id=player.id,
            ground_item_id=ground_item.id,
            player_x=10,
            player_y=10,
            player_map_id="testmap",
        )

        # Check inventory has durability
        inv = await InventoryService.get_item_at_slot(
            session, player.id, result.inventory_slot
        )
        assert inv.current_durability == 150

    @pytest.mark.asyncio
    async def test_pickup_wrong_map_fails(
        self, session: AsyncSession, player_for_ground_items
    ):
        """Cannot pick up item from different map even with matching x,y coords.

        This is a critical security test - players should not be able to pick up
        items from other maps by knowing the ground_item_id and standing at
        matching coordinates on their own map.
        """
        player = player_for_ground_items
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        # Create ground item on "othermap"
        ground_item = await GroundItemService.create_ground_item(
            db=session,
            item_id=item.id,
            map_id="othermap",
            x=10,
            y=10,
            dropped_by=player.id,
        )

        # Try to pick up while player is on "testmap" at same x,y
        result = await GroundItemService.pickup_item(
            db=session,
            player_id=player.id,
            ground_item_id=ground_item.id,
            player_x=10,
            player_y=10,
            player_map_id="testmap",  # Player is on different map
        )

        assert result.success is False
        # Error message should be generic to not leak info about other maps
        assert "not found" in result.message.lower()

        # Item should still exist on ground (not picked up)
        ground = await GroundItemService.get_ground_item(session, ground_item.id)
        assert ground is not None

    @pytest.mark.asyncio
    async def test_pickup_cross_map_generic_error(
        self, session: AsyncSession, player_for_ground_items
    ):
        """Cross-map pickup error message should be generic.

        Security requirement: The error message for cross-map pickup attempts
        should be identical to "item not found" to prevent attackers from
        determining if an item exists on another map.
        """
        player = player_for_ground_items
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        # Create item on different map
        ground_item = await GroundItemService.create_ground_item(
            db=session,
            item_id=item.id,
            map_id="secretmap",
            x=10,
            y=10,
            dropped_by=player.id,
        )

        # Attempt cross-map pickup
        cross_map_result = await GroundItemService.pickup_item(
            db=session,
            player_id=player.id,
            ground_item_id=ground_item.id,
            player_x=10,
            player_y=10,
            player_map_id="testmap",
        )

        # Attempt pickup of nonexistent item
        nonexistent_result = await GroundItemService.pickup_item(
            db=session,
            player_id=player.id,
            ground_item_id=99999,
            player_x=10,
            player_y=10,
            player_map_id="testmap",
        )

        # Both should fail with the same generic message
        assert cross_map_result.success is False
        assert nonexistent_result.success is False
        assert cross_map_result.message == nonexistent_result.message


# =============================================================================
# Visibility Tests
# =============================================================================


class TestVisibility:
    """Test ground item visibility rules."""

    @pytest.mark.asyncio
    async def test_own_items_always_visible(
        self, session: AsyncSession, player_for_ground_items
    ):
        """Own items should always be visible (even during protection)."""
        player = player_for_ground_items
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        # Create ground item
        await GroundItemService.create_ground_item(
            db=session,
            item_id=item.id,
            map_id="testmap",
            x=10,
            y=10,
            dropped_by=player.id,
        )

        # Get visible items
        response = await GroundItemService.get_visible_ground_items(
            db=session,
            player_id=player.id,
            map_id="testmap",
            center_x=10,
            center_y=10,
        )

        assert len(response.items) == 1
        assert response.items[0].is_yours is True

    @pytest.mark.asyncio
    async def test_other_protected_items_hidden(
        self, session: AsyncSession, player_for_ground_items, second_player
    ):
        """Other players' protected items should be hidden."""
        player = player_for_ground_items
        other = second_player
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        # Create ground item by player (protected)
        await GroundItemService.create_ground_item(
            db=session,
            item_id=item.id,
            map_id="testmap",
            x=10,
            y=10,
            dropped_by=player.id,
        )

        # Get visible items for other player
        response = await GroundItemService.get_visible_ground_items(
            db=session,
            player_id=other.id,
            map_id="testmap",
            center_x=10,
            center_y=10,
        )

        # Should not see the protected item
        assert len(response.items) == 0

    @pytest.mark.asyncio
    async def test_public_items_visible(
        self, session: AsyncSession, player_for_ground_items, second_player
    ):
        """Public items should be visible to everyone."""
        player = player_for_ground_items
        other = second_player
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        # Create ground item and make it public
        ground_item = await GroundItemService.create_ground_item(
            db=session,
            item_id=item.id,
            map_id="testmap",
            x=10,
            y=10,
            dropped_by=player.id,
        )
        ground_item.public_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
        await session.commit()

        # Get visible items for other player
        response = await GroundItemService.get_visible_ground_items(
            db=session,
            player_id=other.id,
            map_id="testmap",
            center_x=10,
            center_y=10,
        )

        assert len(response.items) == 1
        assert response.items[0].is_yours is False
        assert response.items[0].is_protected is False

    @pytest.mark.asyncio
    async def test_visibility_respects_range(
        self, session: AsyncSession, player_for_ground_items
    ):
        """Items outside range should not be visible."""
        player = player_for_ground_items
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        # Create ground item far away
        await GroundItemService.create_ground_item(
            db=session,
            item_id=item.id,
            map_id="testmap",
            x=100,
            y=100,
            dropped_by=player.id,
        )

        # Get visible items with small radius
        response = await GroundItemService.get_visible_ground_items(
            db=session,
            player_id=player.id,
            map_id="testmap",
            center_x=10,
            center_y=10,
            tile_radius=16,
        )

        # Should not see item at 100, 100
        assert len(response.items) == 0


# =============================================================================
# Cleanup Tests
# =============================================================================


class TestCleanupExpiredItems:
    """Test cleanup of expired items."""

    @pytest.mark.asyncio
    async def test_cleanup_removes_expired(
        self, session: AsyncSession, player_for_ground_items
    ):
        """Cleanup should remove expired items."""
        player = player_for_ground_items
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        # Create ground item
        ground_item = await GroundItemService.create_ground_item(
            db=session,
            item_id=item.id,
            map_id="testmap",
            x=10,
            y=10,
            dropped_by=player.id,
        )

        # Make it expired
        ground_item.despawn_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
        await session.commit()

        # Run cleanup
        count = await GroundItemService.cleanup_expired_items(session)

        assert count == 1

        # Item should be gone
        result = await GroundItemService.get_ground_item(session, ground_item.id)
        assert result is None

    @pytest.mark.asyncio
    async def test_cleanup_keeps_valid_items(
        self, session: AsyncSession, player_for_ground_items
    ):
        """Cleanup should not remove valid items."""
        player = player_for_ground_items
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        # Create ground item (not expired)
        ground_item = await GroundItemService.create_ground_item(
            db=session,
            item_id=item.id,
            map_id="testmap",
            x=10,
            y=10,
            dropped_by=player.id,
        )

        # Run cleanup
        count = await GroundItemService.cleanup_expired_items(session)

        assert count == 0

        # Item should still exist
        result = await GroundItemService.get_ground_item(session, ground_item.id)
        assert result is not None


# =============================================================================
# Death Drop Tests
# =============================================================================


class TestDropPlayerItemsOnDeath:
    """Test dropping all items on death."""

    @pytest.mark.asyncio
    async def test_death_drops_inventory(
        self, session: AsyncSession, player_for_ground_items
    ):
        """Death should drop all inventory items."""
        player = player_for_ground_items
        item = await ItemService.get_item_by_name(session, "copper_ore")

        # Add items to inventory
        await InventoryService.add_item(session, player.id, item.id, quantity=10)

        # Die
        count = await GroundItemService.drop_player_items_on_death(
            db=session,
            player_id=player.id,
            map_id="testmap",
            x=10,
            y=10,
        )

        assert count == 1

        # Inventory should be empty
        inv = await InventoryService.get_inventory(session, player.id)
        assert len(inv) == 0

        # Item should be on ground
        items = await GroundItemService.get_items_at_position(
            session, "testmap", 10, 10
        )
        assert len(items) == 1
        assert items[0].quantity == 10

    @pytest.mark.asyncio
    async def test_death_drops_equipment(
        self, session: AsyncSession, player_for_ground_items
    ):
        """Death should drop all equipped items."""
        player = player_for_ground_items
        sword = await ItemService.get_item_by_name(session, "bronze_sword")

        # Give skill and equip
        await give_player_skill_level(session, player.id, "attack", 1)
        await InventoryService.add_item(session, player.id, sword.id)
        await EquipmentService.equip_from_inventory(session, player.id, 0)

        # Die
        count = await GroundItemService.drop_player_items_on_death(
            db=session,
            player_id=player.id,
            map_id="testmap",
            x=10,
            y=10,
        )

        assert count == 1

        # Equipment should be empty
        equipment = await EquipmentService.get_equipment(session, player.id)
        assert len(equipment) == 0

        # Item should be on ground
        items = await GroundItemService.get_items_at_position(
            session, "testmap", 10, 10
        )
        assert len(items) == 1
        assert items[0].item_id == sword.id

    @pytest.mark.asyncio
    async def test_death_drops_multiple_items(
        self, session: AsyncSession, player_for_ground_items
    ):
        """Death should drop inventory and equipment."""
        player = player_for_ground_items
        sword = await ItemService.get_item_by_name(session, "bronze_sword")
        ore = await ItemService.get_item_by_name(session, "copper_ore")

        # Give skill, equip sword, add ore to inventory
        await give_player_skill_level(session, player.id, "attack", 1)
        await InventoryService.add_item(session, player.id, sword.id)
        await EquipmentService.equip_from_inventory(session, player.id, 0)
        await InventoryService.add_item(session, player.id, ore.id, quantity=5)

        # Die
        count = await GroundItemService.drop_player_items_on_death(
            db=session,
            player_id=player.id,
            map_id="testmap",
            x=10,
            y=10,
        )

        assert count == 2  # sword + ore

        # Both should be empty
        inv = await InventoryService.get_inventory(session, player.id)
        equipment = await EquipmentService.get_equipment(session, player.id)
        assert len(inv) == 0
        assert len(equipment) == 0

    @pytest.mark.asyncio
    async def test_death_with_empty_inventory(
        self, session: AsyncSession, player_for_ground_items
    ):
        """Death with no items should drop nothing."""
        player = player_for_ground_items

        count = await GroundItemService.drop_player_items_on_death(
            db=session,
            player_id=player.id,
            map_id="testmap",
            x=10,
            y=10,
        )

        assert count == 0


# =============================================================================
# Get Items At Position Tests
# =============================================================================


class TestGetItemsAtPosition:
    """Test getting items at a specific position."""

    @pytest.mark.asyncio
    async def test_get_items_at_position(
        self, session: AsyncSession, player_for_ground_items
    ):
        """Should return all items at position."""
        player = player_for_ground_items
        sword = await ItemService.get_item_by_name(session, "bronze_sword")
        ore = await ItemService.get_item_by_name(session, "copper_ore")

        # Create two items at same position
        await GroundItemService.create_ground_item(
            db=session, item_id=sword.id, map_id="testmap", x=10, y=10, dropped_by=player.id
        )
        await GroundItemService.create_ground_item(
            db=session, item_id=ore.id, map_id="testmap", x=10, y=10, dropped_by=player.id, quantity=5
        )

        items = await GroundItemService.get_items_at_position(
            session, "testmap", 10, 10
        )

        assert len(items) == 2

    @pytest.mark.asyncio
    async def test_get_items_empty_position(
        self, session: AsyncSession, player_for_ground_items
    ):
        """Empty position should return empty list."""
        items = await GroundItemService.get_items_at_position(
            session, "testmap", 50, 50
        )

        assert len(items) == 0
