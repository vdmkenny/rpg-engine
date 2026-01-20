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

from server.src.models.skill import Skill, PlayerSkill
from server.src.services.item_service import ItemService
from server.src.services.ground_item_service import GroundItemService
from server.src.services.game_state_manager import GameStateManager


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest_asyncio.fixture
async def items_synced(session: AsyncSession):
    """Ensure items are synced to database."""
    await ItemService.sync_items_to_db(session)


@pytest_asyncio.fixture
async def player_for_ground_items(
    session: AsyncSession, gsm: GameStateManager, create_test_player, items_synced
):
    """Create a test player ready for ground item tests."""
    unique_name = f"ground_test_{uuid.uuid4().hex[:8]}"
    player = await create_test_player(
        unique_name, "password123", x=10, y=10, map_id="testmap"
    )
    
    # Register player as online in GSM
    gsm.register_online_player(player.id, player.username)
    await gsm.set_player_full_state(
        player_id=player.id,
        x=10,
        y=10,
        map_id="testmap",
        current_hp=10,
        max_hp=10,
    )
    
    return player


@pytest_asyncio.fixture
async def second_player(
    session: AsyncSession, gsm: GameStateManager, create_test_player, items_synced
):
    """Create a second test player for pickup tests."""
    unique_name = f"second_{uuid.uuid4().hex[:8]}"
    player = await create_test_player(
        unique_name, "password123", x=10, y=10, map_id="testmap"
    )
    
    gsm.register_online_player(player.id, player.username)
    await gsm.set_player_full_state(
        player_id=player.id,
        
        x=10,
        y=10,
        map_id="testmap",
        current_hp=10,
        max_hp=10,
    )
    
    return player


async def give_player_skill_level(
    session: AsyncSession, gsm: GameStateManager, player_id: int, skill_name: str, level: int
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
    await gsm.set_skill(player_id, skill_name, skill.id, level, 0)


# =============================================================================
# Create Ground Item Tests
# =============================================================================


class TestCreateGroundItem:
    """Test creating ground items."""

    @pytest.mark.asyncio
    async def test_create_ground_item_basic(
        self, session: AsyncSession, gsm: GameStateManager, player_for_ground_items
    ):
        """Basic ground item creation should work."""
        player = player_for_ground_items
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        ground_item_id = await GroundItemService.create_ground_item(
            item_id=item.id,
            map_id="testmap",
            x=10,
            y=10,
            quantity=1,
            dropped_by=player.id,
        )

        assert ground_item_id is not None
        
        ground_item = await gsm.get_ground_item(ground_item_id)
        assert ground_item["item_id"] == item.id
        assert ground_item["map_id"] == "testmap"
        assert ground_item["x"] == 10
        assert ground_item["y"] == 10
        assert ground_item["quantity"] == 1
        assert ground_item["dropped_by_player_id"] == player.id

    @pytest.mark.asyncio
    async def test_create_ground_item_rarity_timers(
        self, session: AsyncSession, gsm: GameStateManager, player_for_ground_items
    ):
        """Ground items should have rarity-based despawn timers."""
        player = player_for_ground_items
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        now = datetime.now(timezone.utc).timestamp()
        ground_item_id = await GroundItemService.create_ground_item(
            item_id=item.id,
            map_id="testmap",
            x=10,
            y=10,
            dropped_by=player.id,
        )

        ground_item = await gsm.get_ground_item(ground_item_id)
        
        # Should have loot_protection_expires_at and despawn_at set
        assert ground_item["loot_protection_expires_at"] is not None
        assert ground_item["despawn_at"] is not None

        # loot_protection_expires_at should be in the future (protection period)
        assert ground_item["loot_protection_expires_at"] > now

        # despawn_at should be after loot_protection_expires_at
        assert ground_item["despawn_at"] > ground_item["loot_protection_expires_at"]

    @pytest.mark.asyncio
    async def test_create_ground_item_invalid_item(
        self, session: AsyncSession, gsm: GameStateManager, player_for_ground_items
    ):
        """Creating with invalid item ID should return None."""
        player = player_for_ground_items

        ground_item_id = await GroundItemService.create_ground_item(
            item_id=99999,
            map_id="testmap",
            x=10,
            y=10,
            dropped_by=player.id,
        )

        assert ground_item_id is None


# =============================================================================
# Drop From Inventory Tests
# =============================================================================


class TestDropFromInventory:
    """Test dropping items from inventory."""

    @pytest.mark.asyncio
    async def test_drop_entire_stack(
        self, session: AsyncSession, gsm: GameStateManager, player_for_ground_items
    ):
        """Dropping entire stack should work."""
        player = player_for_ground_items
        item = await ItemService.get_item_by_name(session, "copper_ore")

        # Add to inventory via GSM
        await gsm.set_inventory_slot(player.id, 0, item.id, 10, None)

        result = await GroundItemService.drop_from_inventory(
            player_id=player.id,
            inventory_slot=0,
            map_id="testmap",
            x=10,
            y=10,
        )

        assert result.success is True
        assert result.ground_item_id is not None

        # Inventory should be empty
        inv = await gsm.get_inventory_slot(player.id, 0)
        assert inv is None

    @pytest.mark.asyncio
    async def test_drop_partial_stack(
        self, session: AsyncSession, gsm: GameStateManager, player_for_ground_items
    ):
        """Dropping partial stack should leave remainder."""
        player = player_for_ground_items
        item = await ItemService.get_item_by_name(session, "copper_ore")

        await gsm.set_inventory_slot(player.id, 0, item.id, 10, None)

        result = await GroundItemService.drop_from_inventory(
            player_id=player.id,
            inventory_slot=0,
            map_id="testmap",
            x=10,
            y=10,
            quantity=3,
        )

        assert result.success is True

        # Inventory should have remainder
        inv = await gsm.get_inventory_slot(player.id, 0)
        assert inv is not None
        assert inv["quantity"] == 7

    @pytest.mark.asyncio
    async def test_drop_from_empty_slot(
        self, session: AsyncSession, gsm: GameStateManager, player_for_ground_items
    ):
        """Dropping from empty slot should fail."""
        player = player_for_ground_items

        result = await GroundItemService.drop_from_inventory(
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
        self, session: AsyncSession, gsm: GameStateManager, player_for_ground_items
    ):
        """Dropping more than available should fail."""
        player = player_for_ground_items
        item = await ItemService.get_item_by_name(session, "copper_ore")

        await gsm.set_inventory_slot(player.id, 0, item.id, 5, None)

        result = await GroundItemService.drop_from_inventory(
            player_id=player.id,
            inventory_slot=0,
            map_id="testmap",
            x=10,
            y=10,
            quantity=10,
        )

        assert result.success is False


# =============================================================================
# Pickup Item Tests
# =============================================================================


class TestPickupItem:
    """Test picking up ground items."""

    @pytest.mark.asyncio
    async def test_pickup_own_item(
        self, session: AsyncSession, gsm: GameStateManager, player_for_ground_items
    ):
        """Owner should be able to pick up their item during protection."""
        player = player_for_ground_items
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        ground_item_id = await GroundItemService.create_ground_item(
            item_id=item.id,
            map_id="testmap",
            x=10,
            y=10,
            dropped_by=player.id,
        )

        result = await GroundItemService.pickup_item(
            player_id=player.id,
            ground_item_id=ground_item_id,
            player_x=10,
            player_y=10,
            player_map_id="testmap",
        )

        assert result.success is True
        assert result.inventory_slot is not None

        # Should be in inventory
        inv = await gsm.get_inventory_slot(player.id, result.inventory_slot)
        assert inv is not None
        assert inv["item_id"] == item.id

        # Ground item should be gone
        ground = await gsm.get_ground_item(ground_item_id)
        assert ground is None

    @pytest.mark.asyncio
    async def test_pickup_wrong_tile(
        self, session: AsyncSession, gsm: GameStateManager, player_for_ground_items
    ):
        """Cannot pick up item from different tile."""
        player = player_for_ground_items
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        ground_item_id = await GroundItemService.create_ground_item(
            item_id=item.id,
            map_id="testmap",
            x=10,
            y=10,
            dropped_by=player.id,
        )

        result = await GroundItemService.pickup_item(
            player_id=player.id,
            ground_item_id=ground_item_id,
            player_x=15,
            player_y=10,
            player_map_id="testmap",
        )

        assert result.success is False
        assert "same tile" in result.message.lower()

    @pytest.mark.asyncio
    async def test_pickup_protected_item(
        self, session: AsyncSession, gsm: GameStateManager, player_for_ground_items, second_player
    ):
        """Other players cannot pick up protected items."""
        player = player_for_ground_items
        other = second_player
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        ground_item_id = await GroundItemService.create_ground_item(
            item_id=item.id,
            map_id="testmap",
            x=10,
            y=10,
            dropped_by=player.id,
        )

        result = await GroundItemService.pickup_item(
            player_id=other.id,
            ground_item_id=ground_item_id,
            player_x=10,
            player_y=10,
            player_map_id="testmap",
        )

        assert result.success is False
        assert "protected" in result.message.lower()

    @pytest.mark.asyncio
    async def test_pickup_public_item(
        self, session: AsyncSession, gsm: GameStateManager, player_for_ground_items, second_player
    ):
        """Anyone can pick up public (unprotected) items."""
        player = player_for_ground_items
        other = second_player
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        ground_item_id = await GroundItemService.create_ground_item(
            item_id=item.id,
            map_id="testmap",
            x=10,
            y=10,
            dropped_by=player.id,
        )

        # Make item public by modifying the Valkey data directly
        item_key = f"ground_item:{ground_item_id}"
        past_time = datetime.now(timezone.utc).timestamp() - 1
        await gsm._valkey.hset(item_key, {"loot_protection_expires_at": str(past_time)})

        result = await GroundItemService.pickup_item(
            player_id=other.id,
            ground_item_id=ground_item_id,
            player_x=10,
            player_y=10,
            player_map_id="testmap",
        )

        assert result.success is True

    @pytest.mark.asyncio
    async def test_pickup_nonexistent_item(
        self, session: AsyncSession, gsm: GameStateManager, player_for_ground_items
    ):
        """Picking up nonexistent item should fail."""
        player = player_for_ground_items

        result = await GroundItemService.pickup_item(
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
        self, session: AsyncSession, gsm: GameStateManager, player_for_ground_items
    ):
        """Picking up despawned item should fail."""
        player = player_for_ground_items
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        ground_item_id = await GroundItemService.create_ground_item(
            item_id=item.id,
            map_id="testmap",
            x=10,
            y=10,
            dropped_by=player.id,
        )

        # Make item despawned
        item_key = f"ground_item:{ground_item_id}"
        past_time = datetime.now(timezone.utc).timestamp() - 1
        await gsm._valkey.hset(item_key, {"despawn_at": str(past_time)})

        result = await GroundItemService.pickup_item(
            player_id=player.id,
            ground_item_id=ground_item_id,
            player_x=10,
            player_y=10,
            player_map_id="testmap",
        )

        assert result.success is False
        assert "despawned" in result.message.lower()

    @pytest.mark.asyncio
    async def test_pickup_wrong_map_fails(
        self, session: AsyncSession, gsm: GameStateManager, player_for_ground_items
    ):
        """Cannot pick up item from different map."""
        player = player_for_ground_items
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        ground_item_id = await GroundItemService.create_ground_item(
            item_id=item.id,
            map_id="othermap",
            x=10,
            y=10,
            dropped_by=player.id,
        )

        result = await GroundItemService.pickup_item(
            player_id=player.id,
            ground_item_id=ground_item_id,
            player_x=10,
            player_y=10,
            player_map_id="testmap",
        )

        assert result.success is False
        assert "not found" in result.message.lower()

        # Item should still exist
        ground = await gsm.get_ground_item(ground_item_id)
        assert ground is not None


# =============================================================================
# Visibility Tests
# =============================================================================


class TestVisibility:
    """Test ground item visibility rules."""

    @pytest.mark.asyncio
    async def test_own_items_always_visible(
        self, session: AsyncSession, gsm: GameStateManager, player_for_ground_items
    ):
        """Own items should always be visible (even during protection)."""
        player = player_for_ground_items
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        await GroundItemService.create_ground_item(
            item_id=item.id,
            map_id="testmap",
            x=10,
            y=10,
            dropped_by=player.id,
        )

        response = await GroundItemService.get_visible_ground_items(
            player_id=player.id,
            map_id="testmap",
            center_x=10,
            center_y=10,
        )

        assert len(response.items) == 1
        assert response.items[0].is_yours is True

    @pytest.mark.asyncio
    async def test_other_protected_items_hidden(
        self, session: AsyncSession, gsm: GameStateManager, player_for_ground_items, second_player
    ):
        """Other players' protected items should be hidden."""
        player = player_for_ground_items
        other = second_player
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        await GroundItemService.create_ground_item(
            item_id=item.id,
            map_id="testmap",
            x=10,
            y=10,
            dropped_by=player.id,
        )

        response = await GroundItemService.get_visible_ground_items(
            player_id=other.id,
            map_id="testmap",
            center_x=10,
            center_y=10,
        )

        assert len(response.items) == 0

    @pytest.mark.asyncio
    async def test_public_items_visible(
        self, session: AsyncSession, gsm: GameStateManager, player_for_ground_items, second_player
    ):
        """Public items should be visible to everyone."""
        player = player_for_ground_items
        other = second_player
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        ground_item_id = await GroundItemService.create_ground_item(
            item_id=item.id,
            map_id="testmap",
            x=10,
            y=10,
            dropped_by=player.id,
        )

        # Make item public
        item_key = f"ground_item:{ground_item_id}"
        past_time = datetime.now(timezone.utc).timestamp() - 1
        await gsm._valkey.hset(item_key, {"loot_protection_expires_at": str(past_time)})

        response = await GroundItemService.get_visible_ground_items(
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
        self, session: AsyncSession, gsm: GameStateManager, player_for_ground_items
    ):
        """Items outside range should not be visible."""
        player = player_for_ground_items
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        await GroundItemService.create_ground_item(
            item_id=item.id,
            map_id="testmap",
            x=100,
            y=100,
            dropped_by=player.id,
        )

        response = await GroundItemService.get_visible_ground_items(
            player_id=player.id,
            map_id="testmap",
            center_x=10,
            center_y=10,
            tile_radius=16,
        )

        assert len(response.items) == 0


# =============================================================================
# Cleanup Tests
# =============================================================================


class TestCleanupExpiredItems:
    """Test cleanup of expired items."""

    @pytest.mark.asyncio
    async def test_cleanup_removes_expired(
        self, session: AsyncSession, gsm: GameStateManager, player_for_ground_items
    ):
        """Cleanup should remove expired items."""
        player = player_for_ground_items
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        ground_item_id = await GroundItemService.create_ground_item(
            item_id=item.id,
            map_id="testmap",
            x=10,
            y=10,
            dropped_by=player.id,
        )

        # Make it expired
        item_key = f"ground_item:{ground_item_id}"
        past_time = datetime.now(timezone.utc).timestamp() - 1
        await gsm._valkey.hset(item_key, {"despawn_at": str(past_time)})

        count = await GroundItemService.cleanup_expired_items("testmap")

        assert count == 1

        # Item should be gone
        result = await gsm.get_ground_item(ground_item_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_cleanup_keeps_valid_items(
        self, session: AsyncSession, gsm: GameStateManager, player_for_ground_items
    ):
        """Cleanup should not remove valid items."""
        player = player_for_ground_items
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        ground_item_id = await GroundItemService.create_ground_item(
            item_id=item.id,
            map_id="testmap",
            x=10,
            y=10,
            dropped_by=player.id,
        )

        count = await GroundItemService.cleanup_expired_items("testmap")

        assert count == 0

        # Item should still exist
        result = await gsm.get_ground_item(ground_item_id)
        assert result is not None


# =============================================================================
# Death Drop Tests
# =============================================================================


class TestDropPlayerItemsOnDeath:
    """Test dropping all items on death."""

    @pytest.mark.asyncio
    async def test_death_drops_inventory(
        self, session: AsyncSession, gsm: GameStateManager, player_for_ground_items
    ):
        """Death should drop all inventory items."""
        player = player_for_ground_items
        item = await ItemService.get_item_by_name(session, "copper_ore")

        await gsm.set_inventory_slot(player.id, slot=0, item_id=item.id, quantity=10, durability=None)

        count = await GroundItemService.drop_player_items_on_death(
            player_id=player.id,
            map_id="testmap",
            x=10,
            y=10,
        )

        assert count == 1

        inv = await gsm.get_inventory(player.id)
        assert len(inv) == 0

        ground_items = await gsm.get_ground_items_on_map("testmap")
        items_at_pos = [i for i in ground_items if i["x"] == 10 and i["y"] == 10]
        assert len(items_at_pos) == 1
        assert items_at_pos[0]["quantity"] == 10

    @pytest.mark.asyncio
    async def test_death_drops_equipment(
        self, session: AsyncSession, gsm: GameStateManager, player_for_ground_items
    ):
        """Death should drop all equipped items."""
        player = player_for_ground_items
        sword = await ItemService.get_item_by_name(session, "bronze_sword")

        await give_player_skill_level(session, gsm, player.id, "attack", 1)
        
        await gsm.set_equipment_slot(
            player.id,
            slot="weapon",
            item_id=sword.id,
            quantity=1,
            durability=sword.max_durability,
        )

        count = await GroundItemService.drop_player_items_on_death(
            player_id=player.id,
            map_id="testmap",
            x=10,
            y=10,
        )

        assert count == 1

        equipment = await gsm.get_equipment(player.id)
        assert len(equipment) == 0

        ground_items = await gsm.get_ground_items_on_map("testmap")
        items_at_pos = [i for i in ground_items if i["x"] == 10 and i["y"] == 10]
        assert len(items_at_pos) == 1
        assert items_at_pos[0]["item_id"] == sword.id

    @pytest.mark.asyncio
    async def test_death_drops_multiple_items(
        self, session: AsyncSession, gsm: GameStateManager, player_for_ground_items
    ):
        """Death should drop inventory and equipment."""
        player = player_for_ground_items
        sword = await ItemService.get_item_by_name(session, "bronze_sword")
        ore = await ItemService.get_item_by_name(session, "copper_ore")

        await give_player_skill_level(session, gsm, player.id, "attack", 1)
        
        await gsm.set_equipment_slot(
            player.id,
            slot="weapon",
            item_id=sword.id,
            quantity=1,
            durability=sword.max_durability,
        )
        
        await gsm.set_inventory_slot(player.id, slot=0, item_id=ore.id, quantity=5, durability=None)

        count = await GroundItemService.drop_player_items_on_death(
            player_id=player.id,
            map_id="testmap",
            x=10,
            y=10,
        )

        assert count == 2

        inv = await gsm.get_inventory(player.id)
        equipment = await gsm.get_equipment(player.id)
        assert len(inv) == 0
        assert len(equipment) == 0

    @pytest.mark.asyncio
    async def test_death_with_empty_inventory(
        self, session: AsyncSession, gsm: GameStateManager, player_for_ground_items
    ):
        """Death with no items should drop nothing."""
        player = player_for_ground_items

        count = await GroundItemService.drop_player_items_on_death(
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
        self, session: AsyncSession, gsm: GameStateManager, player_for_ground_items
    ):
        """Should return all items at position."""
        player = player_for_ground_items
        sword = await ItemService.get_item_by_name(session, "bronze_sword")
        ore = await ItemService.get_item_by_name(session, "copper_ore")

        await GroundItemService.create_ground_item(
            item_id=sword.id, map_id="testmap", x=10, y=10, dropped_by=player.id
        )
        await GroundItemService.create_ground_item(
            item_id=ore.id, map_id="testmap", x=10, y=10, dropped_by=player.id, quantity=5
        )

        items = await GroundItemService.get_items_at_position("testmap", 10, 10)

        assert len(items) == 2

    @pytest.mark.asyncio
    async def test_get_items_empty_position(
        self, session: AsyncSession, gsm: GameStateManager, player_for_ground_items
    ):
        """Empty position should return empty list."""
        items = await GroundItemService.get_items_at_position("testmap", 50, 50)

        assert len(items) == 0
