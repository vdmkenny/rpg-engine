"""
Tests for the equipment system.

Tests cover:
- Getting equipment
- Equipment requirements (skill levels)
- Equipping from inventory (including 2H logic)
- Unequipping to inventory
- Stats aggregation
- Durability (degrade, repair)
- Clearing equipment
"""

import uuid
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from server.src.core.items import ItemType, EquipmentSlot
from server.src.core.config import settings
from server.src.models.item import Item, PlayerInventory, PlayerEquipment
from server.src.models.skill import Skill, PlayerSkill
from server.src.services.item_service import ItemService
from server.src.services.inventory_service import InventoryService
from server.src.services.equipment_service import EquipmentService
from server.src.services.skill_service import SkillService


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest_asyncio.fixture
async def skills_synced(session: AsyncSession, gsm):
    """Ensure skills are synced to database."""
    await SkillService.sync_skills_to_db()


@pytest_asyncio.fixture
async def player_with_equipment(
    session: AsyncSession, create_test_player, items_synced, skills_synced, gsm
):
    """Create a test player ready for equipment tests."""
    unique_name = f"equip_test_{uuid.uuid4().hex[:8]}"
    player = await create_test_player(unique_name, "password123")
    
    # Login player to register with GSM (GSM singleton is already initialized by gsm fixture)
    from server.src.services.player_service import PlayerService
    await PlayerService.login_player(session, player)
    
    return player


async def give_player_skill_level(
    session: AsyncSession, player_id: int, skill_name: str, level: int
):
    """Set player skill level for testing equipment requirements."""
    from server.src.services.game_state_manager import get_game_state_manager
    
    # Get skill ID from database for GSM
    result = await session.execute(select(Skill).where(Skill.name == skill_name))
    skill = result.scalar_one_or_none()
    if not skill:
        raise ValueError(f"Skill {skill_name} not found")
    
    gsm = get_game_state_manager()
    await gsm.set_skill(player_id, skill_name, skill.id, level, 0)


# =============================================================================
# Get Equipment Tests
# =============================================================================


class TestGetEquipment:
    """Test getting equipment state."""

    @pytest.mark.asyncio
    async def test_get_equipment_empty(
        self, session: AsyncSession, player_with_equipment, gsm
    ):
        """Empty equipment should return empty dict."""
        player = player_with_equipment

        equipment = await EquipmentService.get_equipment(session, player.id)

        assert equipment == {}

    @pytest.mark.asyncio
    async def test_get_equipment_with_items(
        self, session: AsyncSession, player_with_equipment, gsm
    ):
        """Equipment with items should return dict of slots."""
        player = player_with_equipment
        item = await ItemService.get_item_by_name(session, "bronze_sword")
        
        # Get test item
        item = await ItemService.get_item_by_name(session, "bronze_sword")
        
        # Login player with proper state loading (GSM singleton is already initialized by gsm fixture)
        from server.src.services.player_service import PlayerService
        await PlayerService.login_player(session, player)

        # Add item to inventory and equip
        print(f"Player online status: {gsm.is_online(player.id)}")
        
        # Debug: Check what skills are loaded in GSM
        all_skills = await gsm.get_all_skills(player.id)
        print(f"All skills in GSM: {all_skills}")
        
        attack_skill = await gsm.get_skill(player.id, "attack")
        print(f"Attack skill from GSM: {attack_skill}")
        
        add_result = await InventoryService.add_item(player.id, item.id)
        print(f"Add item result: {add_result}")
        
        # Debug: Check what's in GSM inventory state immediately after add
        inventory_data = await gsm.get_inventory(player.id)
        print(f"Inventory data in GSM after add: {inventory_data}")
        
        # Check specific slot 0
        slot_0_data = await gsm.get_inventory_slot(player.id, 0)
        print(f"Slot 0 data: {slot_0_data}")
        
        equip_result = await EquipmentService.equip_from_inventory(session, player.id, 0)
        print(f"Equip result: success={equip_result.success}, message={equip_result.message}")

        equipment = await EquipmentService.get_equipment(session, player.id)
        print(f"Equipment after equip: {equipment}")

        assert EquipmentSlot.WEAPON.value in equipment
        assert equipment[EquipmentSlot.WEAPON.value].item_id == item.id

    @pytest.mark.asyncio
    async def test_get_equipment_response_structure(
        self, session: AsyncSession, player_with_equipment, gsm
    ):
        """Equipment response should have all slots."""
        player = player_with_equipment

        response = await EquipmentService.get_equipment_response(session, player.id)

        # Should have one slot per EquipmentSlot
        assert len(response.slots) == len(EquipmentSlot)

        # All should be empty (item=None)
        for slot_info in response.slots:
            assert slot_info.item is None


# =============================================================================
# Can Equip Tests
# =============================================================================


class TestCanEquip:
    """Test equipment requirement checks."""

    @pytest.mark.asyncio
    async def test_can_equip_no_requirements(
        self, session: AsyncSession, player_with_equipment, gsm
    ):
        """Item with no requirements should be equippable."""
        player = player_with_equipment
        # Bronze arrows have no skill requirements
        item = await ItemService.get_item_by_name(session, "bronze_arrows")

        result = await EquipmentService.can_equip(player.id, item)

        assert result.can_equip is True

    @pytest.mark.asyncio
    async def test_can_equip_with_default_skills(
        self, session: AsyncSession, player_with_equipment, gsm
    ):
        """Should succeed when player has default skill levels."""
        player = player_with_equipment
        # Login player to load skills (GSM singleton is already initialized by gsm fixture)
        from server.src.services.player_service import PlayerService
        await PlayerService.login_player(session, player)
        
        # Bronze sword requires attack level 1 (default)
        item = await ItemService.get_item_by_name(session, "bronze_sword")
        
        result = await EquipmentService.can_equip(player.id, item)
        
        assert result.can_equip is True
        assert result.reason == "OK"

    @pytest.mark.asyncio
    async def test_can_equip_insufficient_level(
        self, session: AsyncSession, player_with_equipment, gsm
    ):
        """Should fail if skill level is too low."""
        player = player_with_equipment
        # Iron sword requires attack level 10
        item = await ItemService.get_item_by_name(session, "iron_sword")

        # Give player attack level 5 (not enough)
        await give_player_skill_level(session, player.id, "attack", 5)

        result = await EquipmentService.can_equip(player.id, item)

        assert result.can_equip is False
        assert "10" in result.reason  # Required level
        assert "5" in result.reason  # Current level

    @pytest.mark.asyncio
    async def test_can_equip_meets_requirements(
        self, session: AsyncSession, player_with_equipment, gsm
    ):
        """Should succeed if requirements are met."""
        player = player_with_equipment
        # Iron sword requires attack level 10
        item = await ItemService.get_item_by_name(session, "iron_sword")

        # Give player attack level 10 (exactly enough)
        await give_player_skill_level(session, player.id, "attack", 10)

        result = await EquipmentService.can_equip(player.id, item)

        assert result.can_equip is True

    @pytest.mark.asyncio
    async def test_can_equip_non_equipable_item(
        self, session: AsyncSession, player_with_equipment, gsm
    ):
        """Non-equipable items should fail."""
        player = player_with_equipment
        # Copper ore cannot be equipped
        item = await ItemService.get_item_by_name(session, "copper_ore")

        result = await EquipmentService.can_equip(player.id, item)

        assert result.can_equip is False
        assert "not equipable" in result.reason.lower()


# =============================================================================
# Equip From Inventory Tests
# =============================================================================


class TestEquipFromInventory:
    """Test equipping items from inventory."""

    @pytest.mark.asyncio
    async def test_equip_basic(
        self, session: AsyncSession, player_with_equipment, gsm
    ):
        """Basic equip should work."""
        player = player_with_equipment
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        # Give required skill
        await give_player_skill_level(session, player.id, "attack", 1)

        # Add to inventory
        await InventoryService.add_item(player.id, item.id)

        # Equip
        result = await EquipmentService.equip_from_inventory(session, player.id, 0)

        assert result.success is True
        assert "Bronze Sword" in result.message

        # Verify equipped
        equipped = await EquipmentService.get_equipped_in_slot(
            session, player.id, EquipmentSlot.WEAPON
        )
        assert equipped is not None
        assert equipped.item_id == item.id

        # Verify removed from inventory
        inv = await InventoryService.get_item_at_slot(player.id, 0)
        assert inv is None

    @pytest.mark.asyncio
    async def test_equip_empty_slot(
        self, session: AsyncSession, player_with_equipment, gsm
    ):
        """Equipping from empty inventory slot should fail."""
        player = player_with_equipment

        result = await EquipmentService.equip_from_inventory(session, player.id, 0)

        assert result.success is False
        assert "empty" in result.message.lower()

    @pytest.mark.asyncio
    async def test_equip_non_equipable_item(
        self, session: AsyncSession, player_with_equipment, gsm
    ):
        """Equipping non-equipable item should fail."""
        player = player_with_equipment
        item = await ItemService.get_item_by_name(session, "copper_ore")

        # Add to inventory
        await InventoryService.add_item(player.id, item.id, quantity=10)

        result = await EquipmentService.equip_from_inventory(session, player.id, 0)

        assert result.success is False
        assert "cannot be equipped" in result.message.lower()

    @pytest.mark.asyncio
    async def test_equip_swaps_current_item(
        self, session: AsyncSession, player_with_equipment, gsm
    ):
        """Equipping should swap with currently equipped item."""
        player = player_with_equipment
        sword = await ItemService.get_item_by_name(session, "bronze_sword")
        pickaxe = await ItemService.get_item_by_name(session, "bronze_pickaxe")

        # Give required skills
        await give_player_skill_level(session, player.id, "attack", 1)
        await give_player_skill_level(session, player.id, "mining", 1)

        # Add both to inventory
        await InventoryService.add_item(player.id, sword.id)
        await InventoryService.add_item(player.id, pickaxe.id)

        # Equip sword (slot 0)
        await EquipmentService.equip_from_inventory(session, player.id, 0)

        # Equip pickaxe (slot 1) - should swap with sword
        result = await EquipmentService.equip_from_inventory(session, player.id, 1)

        assert result.success is True

        # Pickaxe should be equipped
        equipped = await EquipmentService.get_equipped_in_slot(
            session, player.id, EquipmentSlot.WEAPON
        )
        assert equipped.item_id == pickaxe.id

        # Sword should be back in inventory
        inv = await InventoryService.get_inventory(player.id)
        assert len(inv) == 1
        assert inv[0].item_id == sword.id

    @pytest.mark.asyncio
    async def test_equip_two_handed_unequips_shield(
        self, session: AsyncSession, player_with_equipment, gsm
    ):
        """Equipping two-handed weapon should unequip shield."""
        player = player_with_equipment
        two_handed = await ItemService.get_item_by_name(session, "bronze_2h_sword")
        shield = await ItemService.get_item_by_name(session, "bronze_shield")

        # Give required skills
        await give_player_skill_level(session, player.id, "attack", 1)
        await give_player_skill_level(session, player.id, "defence", 1)

        # Add shield to inventory and equip it
        await InventoryService.add_item(player.id, shield.id)
        await EquipmentService.equip_from_inventory(session, player.id, 0)

        # Verify shield is equipped
        equipped_shield = await EquipmentService.get_equipped_in_slot(
            session, player.id, EquipmentSlot.SHIELD
        )
        assert equipped_shield is not None

        # Add two-handed weapon and equip it
        await InventoryService.add_item(player.id, two_handed.id)
        result = await EquipmentService.equip_from_inventory(session, player.id, 0)

        assert result.success is True

        # Two-handed should be equipped
        equipped = await EquipmentService.get_equipped_in_slot(
            session, player.id, EquipmentSlot.WEAPON
        )
        assert equipped.item_id == two_handed.id

        # Shield should be unequipped (in inventory)
        equipped_shield = await EquipmentService.get_equipped_in_slot(
            session, player.id, EquipmentSlot.SHIELD
        )
        assert equipped_shield is None

        inv = await InventoryService.get_inventory(player.id)
        assert len(inv) == 1
        assert inv[0].item_id == shield.id

    @pytest.mark.asyncio
    async def test_equip_shield_with_two_handed_unequips_weapon(
        self, session: AsyncSession, player_with_equipment, gsm
    ):
        """Equipping shield when using two-handed weapon should unequip weapon."""
        player = player_with_equipment
        two_handed = await ItemService.get_item_by_name(session, "bronze_2h_sword")
        shield = await ItemService.get_item_by_name(session, "bronze_shield")

        # Give required skills
        await give_player_skill_level(session, player.id, "attack", 1)
        await give_player_skill_level(session, player.id, "defence", 1)

        # Add two-handed to inventory and equip it
        await InventoryService.add_item(player.id, two_handed.id)
        await EquipmentService.equip_from_inventory(session, player.id, 0)

        # Verify two-handed is equipped
        equipped_weapon = await EquipmentService.get_equipped_in_slot(
            session, player.id, EquipmentSlot.WEAPON
        )
        assert equipped_weapon is not None
        assert equipped_weapon.item.is_two_handed is True

        # Add shield and equip it
        await InventoryService.add_item(player.id, shield.id)
        result = await EquipmentService.equip_from_inventory(session, player.id, 0)

        assert result.success is True

        # Shield should be equipped
        equipped_shield = await EquipmentService.get_equipped_in_slot(
            session, player.id, EquipmentSlot.SHIELD
        )
        assert equipped_shield.item_id == shield.id

        # Two-handed weapon should be unequipped (in inventory)
        equipped_weapon = await EquipmentService.get_equipped_in_slot(
            session, player.id, EquipmentSlot.WEAPON
        )
        assert equipped_weapon is None

        inv = await InventoryService.get_inventory(player.id)
        assert len(inv) == 1
        assert inv[0].item_id == two_handed.id

    @pytest.mark.asyncio
    async def test_equip_preserves_durability(
        self, session: AsyncSession, player_with_equipment, gsm
    ):
        """Durability should be preserved when equipping."""
        player = player_with_equipment
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        # Give required skill
        await give_player_skill_level(session, player.id, "attack", 1)

        # Add to inventory with specific durability
        await InventoryService.add_item(player.id, item.id, durability=250)

        # Equip
        await EquipmentService.equip_from_inventory(session, player.id, 0)

        # Check durability is preserved
        equipped = await EquipmentService.get_equipped_in_slot(
            session, player.id, EquipmentSlot.WEAPON
        )
        assert equipped.current_durability == 250


# =============================================================================
# Unequip To Inventory Tests
# =============================================================================


class TestUnequipToInventory:
    """Test unequipping items to inventory."""

    @pytest.mark.asyncio
    async def test_unequip_basic(
        self, session: AsyncSession, player_with_equipment, gsm):
        """Basic unequip should work."""
        player = player_with_equipment
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        # Give required skill
        await give_player_skill_level(session, player.id, "attack", 1)

        # Add to inventory and equip
        await InventoryService.add_item(player.id, item.id)
        await EquipmentService.equip_from_inventory(session, player.id, 0)

        # Unequip
        result = await EquipmentService.unequip_to_inventory(
            session, player.id, EquipmentSlot.WEAPON)

        assert result.success is True
        assert result.inventory_slot is not None

        # Slot should be empty
        equipped = await EquipmentService.get_equipped_in_slot(
            session, player.id, EquipmentSlot.WEAPON)
        assert equipped is None

        # Item should be in inventory
        inv = await InventoryService.get_item_at_slot(
            player.id, result.inventory_slot
        )
        assert inv is not None
        assert inv.item_id == item.id

    @pytest.mark.asyncio
    async def test_unequip_empty_slot(
        self, session: AsyncSession, player_with_equipment, gsm):
        """Unequipping empty slot should fail."""
        player = player_with_equipment

        result = await EquipmentService.unequip_to_inventory(
            session, player.id, EquipmentSlot.WEAPON)

        assert result.success is False
        assert "nothing equipped" in result.message.lower()

    @pytest.mark.asyncio
    async def test_unequip_full_inventory(
        self, session: AsyncSession, player_with_equipment, gsm):
        """Unequipping with full inventory should fail."""
        player = player_with_equipment
        sword = await ItemService.get_item_by_name(session, "bronze_sword")
        ore = await ItemService.get_item_by_name(session, "copper_ore")

        # Give required skill
        await give_player_skill_level(session, player.id, "attack", 1)

        # Add sword and equip
        await InventoryService.add_item(player.id, sword.id)
        await EquipmentService.equip_from_inventory(session, player.id, 0)

        # Fill inventory with non-stackable items to ensure all slots are used
        non_stackable_items = [
            "bronze_helmet", "bronze_platebody", "bronze_platelegs", "bronze_boots", 
            "bronze_gloves", "bronze_shield", "leather_body", "leather_chaps",
            "bronze_pickaxe", "iron_pickaxe", "bronze_axe", "iron_axe", 
            "fishing_net", "fishing_rod", "shortbow", "oak_shortbow",
            "iron_sword", "bronze_2h_sword"
        ] * 2  # Ensure we have enough items for all 28 slots
        
        for i in range(settings.INVENTORY_MAX_SLOTS):
            item_name = non_stackable_items[i]
            item = await ItemService.get_item_by_name(session, item_name)
            await InventoryService.add_item(player.id, item.id, quantity=1)

        # Try to unequip
        result = await EquipmentService.unequip_to_inventory(
            session, player.id, EquipmentSlot.WEAPON)

        assert result.success is False
        assert "full" in result.message.lower()

    @pytest.mark.asyncio
    async def test_unequip_preserves_durability(
        self, session: AsyncSession, player_with_equipment, gsm):
        """Durability should be preserved when unequipping."""
        player = player_with_equipment
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        # Keep player online to ensure all operations go through Valkey (cache layer)
        # This matches real-world usage and avoids database session isolation issues
        # gsm.unregister_online_player(player.id)  # Don't make offline
        print(f"DEBUG: Player {player.id} is online: {gsm.is_online(player.id)}")
        print(f"DEBUG: GSM bound session: {gsm._bound_test_session}")
        print(f"DEBUG: Test session: {session}")

        # Give required skill
        await give_player_skill_level(session, player.id, "attack", 1)

        # Add to inventory with durability and equip
        add_result = await InventoryService.add_item(player.id, item.id, durability=300)
        print(f"DEBUG: Add item result: {add_result}")
        
        # Check what's in Valkey after add
        inventory_key = f"inventory:{player.id}"
        valkey_data = gsm._valkey.get_hash_data(inventory_key)
        print(f"DEBUG: Valkey inventory data after add: {valkey_data}")
        
        equip_result = await EquipmentService.equip_from_inventory(session, player.id, 0)
        print(f"DEBUG: Equip result: {equip_result}")
        
        # Check if item is actually equipped
        equipped = await EquipmentService.get_equipped_in_slot(session, player.id, EquipmentSlot.WEAPON)
        print(f"DEBUG: Item equipped in weapon slot: {equipped}")

        # Use equipment service to degrade durability to 150
        await EquipmentService.degrade_equipment(
            session, player.id, EquipmentSlot.WEAPON, 150)

        # Unequip
        result = await EquipmentService.unequip_to_inventory(
            session, player.id, EquipmentSlot.WEAPON)

        print(f"DEBUG: Unequip result: {result}")
        print(f"DEBUG: Unequip success: {result.success}")
        print(f"DEBUG: Inventory slot: {result.inventory_slot}")

        # Check durability
        inv = await InventoryService.get_item_at_slot(
            player.id, result.inventory_slot
        )
        print(f"DEBUG: Item at slot {result.inventory_slot}: {inv}")
        
        # Check all inventory items for debugging
        all_inv = await InventoryService.get_inventory(player.id)
        print(f"DEBUG: All inventory items: {all_inv}")
        
        assert inv is not None, f"No item found at slot {result.inventory_slot}"
        assert inv.current_durability == 150


# =============================================================================
# Stats Aggregation Tests
# =============================================================================


class TestGetTotalStats:
    """Test equipment stats aggregation."""

    @pytest.mark.asyncio
    async def test_empty_equipment_zero_stats(
        self, session: AsyncSession, player_with_equipment, gsm):
        """Empty equipment should have zero stats."""
        player = player_with_equipment

        stats = await EquipmentService.get_total_stats(player.id)

        assert stats.attack_bonus == 0
        assert stats.strength_bonus == 0
        assert stats.physical_defence_bonus == 0
        assert stats.health_bonus == 0

    @pytest.mark.asyncio
    async def test_single_item_stats(
        self, session: AsyncSession, player_with_equipment, gsm):
        """Single equipped item should contribute its stats."""
        player = player_with_equipment
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        # Give required skill and equip
        await give_player_skill_level(session, player.id, "attack", 1)
        await InventoryService.add_item(player.id, item.id)
        await EquipmentService.equip_from_inventory(session, player.id, 0)

        stats = await EquipmentService.get_total_stats(player.id)

        # Bronze sword has attack_bonus=4, strength_bonus=3
        assert stats.attack_bonus == 4
        assert stats.strength_bonus == 3

    @pytest.mark.asyncio
    async def test_multiple_items_aggregate(
        self, session: AsyncSession, player_with_equipment, gsm):
        """Multiple items should aggregate stats."""
        player = player_with_equipment
        sword = await ItemService.get_item_by_name(session, "bronze_sword")
        helmet = await ItemService.get_item_by_name(session, "bronze_helmet")
        platebody = await ItemService.get_item_by_name(session, "bronze_platebody")

        # Give required skills
        await give_player_skill_level(session, player.id, "attack", 1)
        await give_player_skill_level(session, player.id, "defence", 1)

        # Equip all items
        await InventoryService.add_item(player.id, sword.id)
        await EquipmentService.equip_from_inventory(session, player.id, 0)

        await InventoryService.add_item(player.id, helmet.id)
        await EquipmentService.equip_from_inventory(session, player.id, 0)

        await InventoryService.add_item(player.id, platebody.id)
        await EquipmentService.equip_from_inventory(session, player.id, 0)

        stats = await EquipmentService.get_total_stats(player.id)

        # Bronze sword: attack=4, strength=3
        # Bronze helmet: physical_defence=3, magic_defence=1, magic_attack=-1
        # Bronze platebody: physical_defence=8, magic_defence=2, health=5, magic_attack=-3, speed=-1
        assert stats.attack_bonus == 4
        assert stats.strength_bonus == 3
        assert stats.physical_defence_bonus == 11  # 3 + 8
        assert stats.magic_defence_bonus == 3  # 1 + 2
        assert stats.health_bonus == 5

    @pytest.mark.asyncio
    async def test_negative_stats_reduce_total(
        self, session: AsyncSession, player_with_equipment, gsm):
        """Negative stats should reduce totals."""
        player = player_with_equipment
        platebody = await ItemService.get_item_by_name(session, "bronze_platebody")

        # Give required skill
        await give_player_skill_level(session, player.id, "defence", 1)

        # Equip platebody (has negative magic attack)
        await InventoryService.add_item(player.id, platebody.id)
        await EquipmentService.equip_from_inventory(session, player.id, 0)

        stats = await EquipmentService.get_total_stats(player.id)

        # Bronze platebody has magic_attack_bonus=-3
        assert stats.magic_attack_bonus == -3
        assert stats.speed_bonus == -1


# =============================================================================
# Durability Tests
# =============================================================================


class TestDurability:
    """Test equipment durability mechanics."""

    @pytest.mark.asyncio
    async def test_degrade_reduces_durability(
        self, session: AsyncSession, player_with_equipment, gsm):
        """Degrading should reduce durability."""
        player = player_with_equipment
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        # Give required skill and equip with full durability
        await give_player_skill_level(session, player.id, "attack", 1)
        await InventoryService.add_item(player.id, item.id, durability=500)
        await EquipmentService.equip_from_inventory(session, player.id, 0)

        # Degrade
        remaining = await EquipmentService.degrade_equipment(
            session, player.id, EquipmentSlot.WEAPON, amount=1)

        # Should be reduced by EQUIPMENT_DURABILITY_LOSS_PER_HIT
        expected = 500 - settings.EQUIPMENT_DURABILITY_LOSS_PER_HIT
        assert remaining == expected

    @pytest.mark.asyncio
    async def test_degrade_empty_slot_returns_none(
        self, session: AsyncSession, player_with_equipment, gsm):
        """Degrading empty slot should return None."""
        player = player_with_equipment

        remaining = await EquipmentService.degrade_equipment(
            session, player.id, EquipmentSlot.WEAPON)

        assert remaining is None

    @pytest.mark.asyncio
    async def test_degrade_to_zero(
        self, session: AsyncSession, player_with_equipment, gsm):
        """Durability should not go below zero."""
        player = player_with_equipment
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        # Give required skill and equip with low durability
        await give_player_skill_level(session, player.id, "attack", 1)
        await InventoryService.add_item(player.id, item.id, durability=1)
        await EquipmentService.equip_from_inventory(session, player.id, 0)

        # Degrade a lot
        remaining = await EquipmentService.degrade_equipment(
            session, player.id, EquipmentSlot.WEAPON, amount=100)

        assert remaining == 0

    @pytest.mark.asyncio
    async def test_repair_restores_durability(
        self, session: AsyncSession, player_with_equipment, gsm):
        """Repairing should restore to max durability."""
        player = player_with_equipment
        item = await ItemService.get_item_by_name(session, "bronze_sword")

        # Give required skill and equip with partial durability
        await give_player_skill_level(session, player.id, "attack", 1)
        await InventoryService.add_item(player.id, item.id, durability=250)
        await EquipmentService.equip_from_inventory(session, player.id, 0)

        # Repair
        success, cost = await EquipmentService.repair_equipment(
            session, player.id, EquipmentSlot.WEAPON)

        assert success is True
        assert cost > 0  # Repair should cost something

        # Check durability is restored
        equipped = await EquipmentService.get_equipped_in_slot(
            session, player.id, EquipmentSlot.WEAPON)
        assert equipped.current_durability == item.max_durability

    @pytest.mark.asyncio
    async def test_repair_empty_slot(
        self, session: AsyncSession, player_with_equipment, gsm):
        """Repairing empty slot should fail."""
        player = player_with_equipment

        success, cost = await EquipmentService.repair_equipment(
            session, player.id, EquipmentSlot.WEAPON)

        assert success is False
        assert cost == 0


# =============================================================================
# Clear Equipment Tests
# =============================================================================


class TestClearEquipment:
    """Test clearing all equipment."""

    @pytest.mark.asyncio
    async def test_clear_equipment(
        self, session: AsyncSession, player_with_equipment, gsm):
        """Clear should remove all equipment."""
        player = player_with_equipment
        sword = await ItemService.get_item_by_name(session, "bronze_sword")
        helmet = await ItemService.get_item_by_name(session, "bronze_helmet")

        # Give required skills and equip
        await give_player_skill_level(session, player.id, "attack", 1)
        await give_player_skill_level(session, player.id, "defence", 1)

        await InventoryService.add_item(player.id, sword.id)
        await EquipmentService.equip_from_inventory(session, player.id, 0)

        await InventoryService.add_item(player.id, helmet.id)
        await EquipmentService.equip_from_inventory(session, player.id, 0)

        # Clear
        count = await EquipmentService.clear_equipment(session, player.id)

        assert count == 2

        # All slots should be empty
        equipment = await EquipmentService.get_equipment(session, player.id)
        assert equipment == {}

    @pytest.mark.asyncio
    async def test_clear_empty_equipment(
        self, session: AsyncSession, player_with_equipment, gsm):
        """Clearing empty equipment should return 0."""
        player = player_with_equipment

        count = await EquipmentService.clear_equipment(session, player.id)

        assert count == 0


# =============================================================================
# Get All Equipped Items Tests
# =============================================================================


class TestGetAllEquippedItems:
    """Test getting all equipped items with data."""

    @pytest.mark.asyncio
    async def test_get_all_equipped_items(
        self, session: AsyncSession, player_with_equipment, gsm):
        """Should return list of (equipment, item) tuples."""
        player = player_with_equipment
        sword = await ItemService.get_item_by_name(session, "bronze_sword")

        # Give required skill and equip
        await give_player_skill_level(session, player.id, "attack", 1)
        await InventoryService.add_item(player.id, sword.id)
        await EquipmentService.equip_from_inventory(session, player.id, 0)

        items = await EquipmentService.get_all_equipped_items(session, player.id)

        assert len(items) == 1
        eq, item = items[0]
        assert eq.item_id == sword.id
        assert item.display_name == "Bronze Sword"


# =============================================================================
# Stackable Ammunition Tests
# =============================================================================


class TestStackableAmmunition:
    """Test stackable ammunition in equipment."""

    @pytest.mark.asyncio
    async def test_equip_arrows_to_empty_slot(
        self, session: AsyncSession, player_with_equipment, gsm):
        """Equipping arrows to empty AMMO slot should work."""
        player = player_with_equipment
        arrows = await ItemService.get_item_by_name(session, "bronze_arrows")

        # Add arrows to inventory (stack of 100)
        await InventoryService.add_item(player.id, arrows.id, quantity=100)

        # Equip
        result = await EquipmentService.equip_from_inventory(session, player.id, 0)

        assert result.success is True
        assert "Bronze Arrows" in result.message

        # Verify equipped with correct quantity
        equipped = await EquipmentService.get_equipped_in_slot(
            session, player.id, EquipmentSlot.AMMO)
        assert equipped is not None
        assert equipped.item_id == arrows.id
        assert equipped.quantity == 100

        # Verify removed from inventory
        inv = await InventoryService.get_item_at_slot(player.id, 0)
        assert inv is None

    @pytest.mark.asyncio
    async def test_equip_same_arrows_adds_to_stack(
        self, session: AsyncSession, player_with_equipment, gsm):
        """Equipping more of the same arrow type should add to existing stack."""
        player = player_with_equipment
        arrows = await ItemService.get_item_by_name(session, "bronze_arrows")

        # Add first batch of arrows and equip
        await InventoryService.add_item(player.id, arrows.id, quantity=100)
        await EquipmentService.equip_from_inventory(session, player.id, 0)

        # Add second batch of arrows
        await InventoryService.add_item(player.id, arrows.id, quantity=50)

        # Equip second batch - should add to existing
        result = await EquipmentService.equip_from_inventory(session, player.id, 0)

        assert result.success is True
        assert "Added 50" in result.message
        assert "now 150" in result.message

        # Verify quantity increased
        equipped = await EquipmentService.get_equipped_in_slot(
            session, player.id, EquipmentSlot.AMMO)
        assert equipped.quantity == 150

        # Verify inventory is empty
        inv = await InventoryService.get_inventory(player.id)
        assert len(inv) == 0

    @pytest.mark.asyncio
    async def test_equip_arrows_partial_stack_full(
        self, session: AsyncSession, player_with_equipment, gsm):
        """When equipped stack is near max, should only add what fits."""
        player = player_with_equipment
        arrows = await ItemService.get_item_by_name(session, "bronze_arrows")
        max_stack = arrows.max_stack_size  # 8192

        # Create equipped arrows near max using service layer
        # First add the arrows to inventory, then equip them
        await InventoryService.add_item(player.id, arrows.id, quantity=max_stack - 100)
        await EquipmentService.equip_from_inventory(session, player.id, 0)

        # Add 200 arrows to inventory (more than can fit)
        await InventoryService.add_item(player.id, arrows.id, quantity=200)

        # Equip - should add 100, leave 100 in inventory
        result = await EquipmentService.equip_from_inventory(session, player.id, 0)

        assert result.success is True
        assert "100" in result.message  # Added 100
        assert "100 remain" in result.message  # 100 left in inventory

        # Verify equipped is at max
        equipped = await EquipmentService.get_equipped_in_slot(
            session, player.id, EquipmentSlot.AMMO)
        assert equipped.quantity == max_stack

        # Verify remainder in inventory
        inv = await InventoryService.get_item_at_slot(player.id, 0)
        assert inv is not None
        assert inv.quantity == 100

    @pytest.mark.asyncio
    async def test_equip_different_arrows_swaps(
        self, session: AsyncSession, player_with_equipment, gsm):
        """Equipping different arrow type should swap (old goes to inventory)."""
        player = player_with_equipment
        bronze_arrows = await ItemService.get_item_by_name(session, "bronze_arrows")
        iron_arrows = await ItemService.get_item_by_name(session, "iron_arrows")

        # Equip bronze arrows (quantity 100)
        await InventoryService.add_item(player.id, bronze_arrows.id, quantity=100)

        # Add iron arrows
        await InventoryService.add_item(player.id, iron_arrows.id, quantity=50)

        # Equip iron arrows - should swap with bronze
        result = await EquipmentService.equip_from_inventory(session, player.id, 0)

        assert result.success is True

        # Verify iron arrows equipped with correct quantity
        equipped = await EquipmentService.get_equipped_in_slot(
            session, player.id, EquipmentSlot.AMMO)
        assert equipped.item_id == iron_arrows.id
        assert equipped.quantity == 50

        # Verify bronze arrows in inventory with preserved quantity
        inv = await InventoryService.get_inventory(player.id)
        assert len(inv) == 1
        assert inv[0].item_id == bronze_arrows.id
        assert inv[0].quantity == 100

    @pytest.mark.asyncio
    async def test_unequip_ammo_preserves_quantity(
        self, session: AsyncSession, player_with_equipment, gsm):
        """Unequipping ammo should preserve quantity."""
        player = player_with_equipment
        arrows = await ItemService.get_item_by_name(session, "bronze_arrows")

        # Equip arrows
        await InventoryService.add_item(player.id, arrows.id, quantity=500)
        await EquipmentService.equip_from_inventory(session, player.id, 0)

        # Unequip
        result = await EquipmentService.unequip_to_inventory(
            session, player.id, EquipmentSlot.AMMO)

        assert result.success is True

        # Slot should be empty
        equipped = await EquipmentService.get_equipped_in_slot(
            session, player.id, EquipmentSlot.AMMO)
        assert equipped is None

        # Inventory should have arrows with preserved quantity
        inv = await InventoryService.get_item_at_slot(
            player.id, result.inventory_slot
        )
        assert inv is not None
        assert inv.item_id == arrows.id
        assert inv.quantity == 500

    @pytest.mark.asyncio
    async def test_unequip_ammo_merges_with_inventory_stack(
        self, session: AsyncSession, player_with_equipment, gsm):
        """Unequipping ammo should merge with existing inventory stack."""
        player = player_with_equipment
        arrows = await ItemService.get_item_by_name(session, "bronze_arrows")

        # Add arrows to inventory
        await InventoryService.add_item(player.id, arrows.id, quantity=200)

        # Equip separate stack of arrows using service layer (not direct DB access)
        await InventoryService.add_item(player.id, arrows.id, quantity=300)
        await EquipmentService.equip_from_inventory(session, player.id, 0)  # Equip the 300 arrows

        # Unequip - should merge with existing stack
        result = await EquipmentService.unequip_to_inventory(
            session, player.id, EquipmentSlot.AMMO)

        assert result.success is True

        # Check inventory - should have merged stack of 500
        inv = await InventoryService.get_inventory(player.id)
        total_arrows = sum(i.quantity for i in inv if i.item_id == arrows.id)
        assert total_arrows == 500

    @pytest.mark.asyncio
    async def test_consume_ammo_reduces_quantity(
        self, session: AsyncSession, player_with_equipment, gsm):
        """Consuming ammo should reduce equipped quantity."""
        player = player_with_equipment
        arrows = await ItemService.get_item_by_name(session, "bronze_arrows")

        # Equip arrows
        await InventoryService.add_item(player.id, arrows.id, quantity=100)
        await EquipmentService.equip_from_inventory(session, player.id, 0)

        # Consume 1 arrow
        success, remaining = await EquipmentService.consume_ammo(session, player.id, 1)

        assert success is True
        assert remaining == 99

        # Verify equipped quantity
        equipped = await EquipmentService.get_equipped_in_slot(
            session, player.id, EquipmentSlot.AMMO)
        assert equipped.quantity == 99

    @pytest.mark.asyncio
    async def test_consume_ammo_removes_when_depleted(
        self, session: AsyncSession, player_with_equipment, gsm):
        """Consuming last ammo should remove equipment entry."""
        player = player_with_equipment
        arrows = await ItemService.get_item_by_name(session, "bronze_arrows")

        # Equip single arrow
        await InventoryService.add_item(player.id, arrows.id, quantity=1)
        await EquipmentService.equip_from_inventory(session, player.id, 0)

        # Consume the arrow
        success, remaining = await EquipmentService.consume_ammo(session, player.id, 1)

        assert success is True
        assert remaining == 0

        # Slot should be empty
        equipped = await EquipmentService.get_equipped_in_slot(
            session, player.id, EquipmentSlot.AMMO)
        assert equipped is None

    @pytest.mark.asyncio
    async def test_consume_ammo_fails_when_not_enough(
        self, session: AsyncSession, player_with_equipment, gsm):
        """Consuming more ammo than available should fail."""
        player = player_with_equipment
        arrows = await ItemService.get_item_by_name(session, "bronze_arrows")

        # Equip 5 arrows
        await InventoryService.add_item(player.id, arrows.id, quantity=5)
        await EquipmentService.equip_from_inventory(session, player.id, 0)

        # Try to consume 10
        success, remaining = await EquipmentService.consume_ammo(session, player.id, 10)

        assert success is False
        assert remaining == 5  # Returns current quantity

        # Quantity should be unchanged
        equipped = await EquipmentService.get_equipped_in_slot(
            session, player.id, EquipmentSlot.AMMO)
        assert equipped.quantity == 5

    @pytest.mark.asyncio
    async def test_consume_ammo_no_ammo_equipped(
        self, session: AsyncSession, player_with_equipment, gsm):
        """Consuming ammo with nothing equipped should fail."""
        player = player_with_equipment

        success, remaining = await EquipmentService.consume_ammo(session, player.id, 1)

        assert success is False
        assert remaining == 0

    @pytest.mark.asyncio
    async def test_equipment_response_includes_quantity(
        self, session: AsyncSession, player_with_equipment, gsm):
        """Equipment response should include quantity for ammo slot."""
        player = player_with_equipment
        arrows = await ItemService.get_item_by_name(session, "bronze_arrows")

        # Equip arrows
        await InventoryService.add_item(player.id, arrows.id, quantity=250)
        await EquipmentService.equip_from_inventory(session, player.id, 0)

        # Get response
        response = await EquipmentService.get_equipment_response(session, player.id)

        # Find AMMO slot in response
        ammo_slot = next(
            (s for s in response.slots if s.slot == EquipmentSlot.AMMO.value), None
        )
        assert ammo_slot is not None
        assert ammo_slot.item is not None
        assert ammo_slot.quantity == 250

    @pytest.mark.asyncio
    async def test_unequip_ammo_drops_to_ground_when_inventory_full(
        self, session: AsyncSession, player_with_equipment, gsm):
        """Unequipping ammo with full inventory should drop to ground."""
        player = player_with_equipment
        arrows = await ItemService.get_item_by_name(session, "bronze_arrows")
        ore = await ItemService.get_item_by_name(session, "copper_ore")

        # Equip arrows using service layer
        await InventoryService.add_item(player.id, arrows.id, quantity=100)
        await EquipmentService.equip_from_inventory(session, player.id, 0)

        # Fill inventory with non-stackable items to ensure all slots are used
        non_stackable_items = [
            "bronze_helmet", "bronze_platebody", "bronze_platelegs", "bronze_boots", 
            "bronze_gloves", "bronze_shield", "leather_body", "leather_chaps",
            "bronze_pickaxe", "iron_pickaxe", "bronze_axe", "iron_axe", 
            "fishing_net", "fishing_rod", "shortbow", "oak_shortbow",
            "iron_sword", "bronze_2h_sword"
        ] * 2  # Ensure we have enough items for all 28 slots
        
        for i in range(settings.INVENTORY_MAX_SLOTS):
            item_name = non_stackable_items[i]
            item = await ItemService.get_item_by_name(session, item_name)
            await InventoryService.add_item(player.id, item.id, quantity=1)

        # Unequip with position (should drop to ground)
        result = await EquipmentService.unequip_to_inventory(
            session,
            player.id,
            EquipmentSlot.AMMO,
            map_id="test_map",
            player_x=10,
            player_y=20)

        assert result.success is True
        assert "dropped" in result.message.lower()

        # Slot should be empty
        equipped = await EquipmentService.get_equipped_in_slot(
            session, player.id, EquipmentSlot.AMMO)
        assert equipped is None
