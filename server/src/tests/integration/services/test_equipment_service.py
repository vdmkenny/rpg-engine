"""
Integration tests for EquipmentService.

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

from server.src.core.items import ItemType
from server.src.core.skills import SkillType
from server.src.core.config import settings
from server.src.models.skill import Skill, PlayerSkill
from server.src.schemas.item import EquipmentData, EquipmentSlot
from server.src.services.item_service import ItemService
from server.src.services.inventory_service import InventoryService
from server.src.services.equipment_service import EquipmentService
from server.src.services.skill_service import SkillService
from server.src.services.game_state import get_skills_manager


@pytest_asyncio.fixture
async def player_with_equipment(
    session: AsyncSession, create_test_player
):
    """Create a test player ready for equipment tests."""
    unique_name = f"equip_test_{uuid.uuid4().hex[:8]}"
    player = await create_test_player(unique_name, "password123")
    
    from server.src.services.player_service import PlayerService
    await PlayerService.login_player(player.id)
    
    return player


async def give_player_skill_level(
    session: AsyncSession, player_id: int, skill_name: str, level: int
):
    """Set player skill level for testing equipment requirements."""
    from server.src.core.skills import SkillType
    
    skill_type = SkillType.from_name(skill_name)
    if not skill_type:
        raise ValueError(f"Skill {skill_name} not found in SkillType enum")
    
    skills_manager = get_skills_manager()
    await skills_manager.set_skill(player_id, skill_type.value.name, level, 0)


@pytest.mark.usefixtures("items_synced")
class TestGetEquipment:
    """Test getting equipment state."""

    @pytest.mark.asyncio
    async def test_get_equipment_empty(
        self, session: AsyncSession, player_with_equipment
    ):
        """Empty equipment should return EquipmentData with all slots empty."""
        player = player_with_equipment
        equipment = await EquipmentService.get_equipment(player.id)
        
        assert isinstance(equipment, EquipmentData)
        assert len(equipment.slots) == len(EquipmentSlot)
        
        # All slots should be empty (item=None)
        for slot_data in equipment.slots:
            assert slot_data.item is None

    @pytest.mark.asyncio
    async def test_get_equipment_with_items(
        self, session: AsyncSession, player_with_equipment
    ):
        """Equipment with items should return EquipmentData with filled slots."""
        player = player_with_equipment
        item = await ItemService.get_item_by_name("bronze_sword")
        
        from server.src.services.player_service import PlayerService
        await PlayerService.login_player(player.id)

        await give_player_skill_level(session, player.id, "attack", 1)
        add_result = await InventoryService.add_item(player.id, item.id)
        assert add_result.success
        
        equip_result = await EquipmentService.equip_from_inventory(player.id, 0)
        assert equip_result.success, f"Equip failed: {equip_result.message}"

        equipment = await EquipmentService.get_equipment(player.id)

        # Find the weapon slot in the equipment data
        weapon_slot = next(
            (slot for slot in equipment.slots if slot.slot == EquipmentSlot.WEAPON),
            None
        )
        assert weapon_slot is not None
        assert weapon_slot.item is not None
        assert weapon_slot.item.id == item.id

    @pytest.mark.asyncio
    async def test_get_equipment_response_structure(
        self, session: AsyncSession, player_with_equipment
    ):
        """Equipment response should have all slots."""
        player = player_with_equipment
        response = await EquipmentService.get_equipment(player.id)

        assert len(response.slots) == len(EquipmentSlot)

        for slot_info in response.slots:
            assert slot_info.item is None


@pytest.mark.usefixtures("items_synced")
class TestCanEquip:
    """Test equipment requirement checks."""

    @pytest.mark.asyncio
    async def test_can_equip_no_requirements(
        self, session: AsyncSession, player_with_equipment
    ):
        """Item with no requirements should be equippable."""
        player = player_with_equipment
        item = await ItemService.get_item_by_name("bronze_arrows")

        result = await EquipmentService.can_equip(player.id, item._data)

        assert result.data.get("can_equip") is True

    @pytest.mark.asyncio
    async def test_can_equip_with_default_skills(
        self, session: AsyncSession, player_with_equipment
    ):
        """Should succeed when player has default skill levels."""
        player = player_with_equipment
        from server.src.services.player_service import PlayerService
        await PlayerService.login_player(player.id)
        
        item = await ItemService.get_item_by_name("bronze_sword")
        
        result = await EquipmentService.can_equip(player.id, item._data)
        
        assert result.data.get("can_equip") is True
        assert result.message == "OK"

    @pytest.mark.asyncio
    async def test_can_equip_insufficient_level(
        self, session: AsyncSession, player_with_equipment
    ):
        """Should fail if skill level is too low."""
        player = player_with_equipment
        item = await ItemService.get_item_by_name("iron_sword")

        await give_player_skill_level(session, player.id, "attack", 5)

        result = await EquipmentService.can_equip(player.id, item._data)

        assert result.data.get("can_equip") is False
        assert "10" in result.message
        assert "5" in result.message

    @pytest.mark.asyncio
    async def test_can_equip_meets_requirements(
        self, session: AsyncSession, player_with_equipment
    ):
        """Should succeed if requirements are met."""
        player = player_with_equipment
        item = await ItemService.get_item_by_name("iron_sword")

        await give_player_skill_level(session, player.id, "attack", 10)

        result = await EquipmentService.can_equip(player.id, item._data)

        assert result.data.get("can_equip") is True

    @pytest.mark.asyncio
    async def test_can_equip_non_equipable_item(
        self, session: AsyncSession, player_with_equipment
    ):
        """Non-equipable items should fail."""
        player = player_with_equipment
        item = await ItemService.get_item_by_name("copper_ore")

        result = await EquipmentService.can_equip(player.id, item._data)

        assert result.data.get("can_equip") is False
        assert "not equipable" in result.message.lower()


@pytest.mark.usefixtures("items_synced")
class TestEquipFromInventory:
    """Test equipping items from inventory."""

    @pytest.mark.asyncio
    async def test_equip_basic(
        self, session: AsyncSession, player_with_equipment
    ):
        """Basic equip should work."""
        player = player_with_equipment
        item = await ItemService.get_item_by_name("bronze_sword")

        await give_player_skill_level(session, player.id, "attack", 1)
        await InventoryService.add_item(player.id, item.id)

        result = await EquipmentService.equip_from_inventory(player.id, 0)

        assert result.success is True
        assert "Bronze Sword" in result.message

        equipped = await EquipmentService.get_equipped_in_slot(player.id, EquipmentSlot.WEAPON)
        assert equipped is not None
        assert equipped.item is not None
        assert equipped.item.id == item.id

        inv = await InventoryService.get_item_at_slot(player.id, 0)
        assert inv is None

    @pytest.mark.asyncio
    async def test_equip_empty_slot(
        self, session: AsyncSession, player_with_equipment
    ):
        """Equipping from empty inventory slot should fail."""
        player = player_with_equipment
        result = await EquipmentService.equip_from_inventory(player.id, 0)

        assert result.success is False
        assert "empty" in result.message.lower()

    @pytest.mark.asyncio
    async def test_equip_non_equipable_item(
        self, session: AsyncSession, player_with_equipment
    ):
        """Equipping non-equipable item should fail."""
        player = player_with_equipment
        item = await ItemService.get_item_by_name("copper_ore")

        await InventoryService.add_item(player.id, item.id, quantity=10)

        result = await EquipmentService.equip_from_inventory(player.id, 0)

        assert result.success is False
        assert "cannot be equipped" in result.message.lower()

    @pytest.mark.asyncio
    async def test_equip_swaps_current_item(
        self, session: AsyncSession, player_with_equipment
    ):
        """Equipping should swap with currently equipped item."""
        player = player_with_equipment
        sword = await ItemService.get_item_by_name("bronze_shortsword")
        pickaxe = await ItemService.get_item_by_name("bronze_pickaxe")

        await give_player_skill_level(session, player.id, "attack", 1)
        await give_player_skill_level(session, player.id, "mining", 1)

        await InventoryService.add_item(player.id, sword.id)
        await InventoryService.add_item(player.id, pickaxe.id)

        await EquipmentService.equip_from_inventory(player.id, 0)
        result = await EquipmentService.equip_from_inventory(player.id, 1)

        assert result.success is True

        equipped = await EquipmentService.get_equipped_in_slot(player.id, EquipmentSlot.WEAPON)
        assert equipped.item.id == pickaxe.id

        inv = await InventoryService.get_inventory(player.id)
        assert len(inv.slots) == 1
        assert inv.slots[0].item.id == sword.id

    @pytest.mark.asyncio
    async def test_equip_two_handed_unequips_shield(
        self, session: AsyncSession, player_with_equipment
    ):
        """Equipping two-handed weapon should unequip shield."""
        player = player_with_equipment
        two_handed = await ItemService.get_item_by_name("copper_2h_sword")
        shield = await ItemService.get_item_by_name("wooden_shield")

        await give_player_skill_level(session, player.id, "attack", 1)
        await give_player_skill_level(session, player.id, "defence", 1)

        await InventoryService.add_item(player.id, shield.id)
        await EquipmentService.equip_from_inventory(player.id, 0)

        equipped_shield = await EquipmentService.get_equipped_in_slot(player.id, EquipmentSlot.SHIELD)
        assert equipped_shield is not None

        await InventoryService.add_item(player.id, two_handed.id)
        result = await EquipmentService.equip_from_inventory(player.id, 0)

        assert result.success is True

        equipped = await EquipmentService.get_equipped_in_slot(player.id, EquipmentSlot.WEAPON)
        assert equipped.item.id == two_handed.id

        equipped_shield = await EquipmentService.get_equipped_in_slot(player.id, EquipmentSlot.SHIELD)
        assert equipped_shield is None

        inv = await InventoryService.get_inventory(player.id)
        assert len(inv.slots) == 1
        assert inv.slots[0].item.id == shield.id


@pytest.mark.usefixtures("items_synced")
class TestUnequipToInventory:
    """Test unequipping items to inventory."""

    @pytest.mark.asyncio
    async def test_unequip_basic(
        self, session: AsyncSession, player_with_equipment):
        """Basic unequip should work."""
        player = player_with_equipment
        item = await ItemService.get_item_by_name("bronze_sword")

        await give_player_skill_level(session, player.id, "attack", 1)
        await InventoryService.add_item(player.id, item.id)
        await EquipmentService.equip_from_inventory(player.id, 0)

        result = await EquipmentService.unequip_to_inventory(player.id, EquipmentSlot.WEAPON)

        assert result.success is True
        assert result.data.get("inventory_slot") is not None

        equipped = await EquipmentService.get_equipped_in_slot(player.id, EquipmentSlot.WEAPON)
        assert equipped is None

        inv = await InventoryService.get_item_at_slot(player.id, result.data.get("inventory_slot"))
        assert inv is not None
        assert inv.item.id == item.id

    @pytest.mark.asyncio
    async def test_unequip_empty_slot(
        self, session: AsyncSession, player_with_equipment):
        """Unequipping empty slot should fail."""
        player = player_with_equipment
        result = await EquipmentService.unequip_to_inventory(player.id, EquipmentSlot.WEAPON)

        assert result.success is False
        assert "nothing equipped" in result.message.lower()

    @pytest.mark.asyncio
    async def test_unequip_preserves_durability(
        self, session: AsyncSession, player_with_equipment):
        """Durability should be preserved when unequipping."""
        player = player_with_equipment
        item = await ItemService.get_item_by_name("bronze_sword")

        await give_player_skill_level(session, player.id, "attack", 1)
        await InventoryService.add_item(player.id, item.id, durability=300)
        await EquipmentService.equip_from_inventory(player.id, 0)

        await EquipmentService.degrade_equipment(player.id, EquipmentSlot.WEAPON, 150)

        result = await EquipmentService.unequip_to_inventory(player.id, EquipmentSlot.WEAPON)

        inv = await InventoryService.get_item_at_slot(player.id, result.data.get("inventory_slot"))
        assert inv is not None
        assert inv.current_durability == 150


@pytest.mark.usefixtures("items_synced")
class TestGetTotalStats:
    """Test equipment stats aggregation."""

    @pytest.mark.asyncio
    async def test_empty_equipment_zero_stats(
        self, session: AsyncSession, player_with_equipment):
        """Empty equipment should have zero stats."""
        player = player_with_equipment
        stats = await EquipmentService.get_total_stats(player.id)

        assert stats.attack_bonus == 0
        assert stats.strength_bonus == 0
        assert stats.physical_defence_bonus == 0
        assert stats.health_bonus == 0

    @pytest.mark.asyncio
    async def test_single_item_stats(
        self, session: AsyncSession, player_with_equipment):
        """Single equipped item should contribute its stats."""
        player = player_with_equipment
        item = await ItemService.get_item_by_name("bronze_sword")

        await give_player_skill_level(session, player.id, "attack", 1)
        await InventoryService.add_item(player.id, item.id)
        await EquipmentService.equip_from_inventory(player.id, 0)

        stats = await EquipmentService.get_total_stats(player.id)

        assert stats.attack_bonus == 4
        assert stats.strength_bonus == 3

    @pytest.mark.asyncio
    async def test_multiple_items_aggregate(
        self, session: AsyncSession, player_with_equipment):
        """Multiple items should aggregate stats."""
        player = player_with_equipment
        sword = await ItemService.get_item_by_name("bronze_shortsword")
        helmet = await ItemService.get_item_by_name("copper_helmet")
        platebody = await ItemService.get_item_by_name("copper_platebody")

        await give_player_skill_level(session, player.id, "attack", 1)
        await give_player_skill_level(session, player.id, "defence", 1)

        await InventoryService.add_item(player.id, sword.id)
        await EquipmentService.equip_from_inventory(player.id, 0)

        await InventoryService.add_item(player.id, helmet.id)
        await EquipmentService.equip_from_inventory(player.id, 0)

        await InventoryService.add_item(player.id, platebody.id)
        await EquipmentService.equip_from_inventory(player.id, 0)

        stats = await EquipmentService.get_total_stats(player.id)

        assert stats.attack_bonus == 4
        assert stats.strength_bonus == 3
        assert stats.physical_defence_bonus == 7
        assert stats.magic_defence_bonus == 1
        assert stats.health_bonus == 3


@pytest.mark.usefixtures("items_synced")
class TestDurability:
    """Test equipment durability mechanics."""

    @pytest.mark.asyncio
    async def test_degrade_reduces_durability(
        self, session: AsyncSession, player_with_equipment):
        """Degrading should reduce durability."""
        player = player_with_equipment
        item = await ItemService.get_item_by_name("bronze_sword")

        await give_player_skill_level(session, player.id, "attack", 1)
        await InventoryService.add_item(player.id, item.id, durability=500)
        await EquipmentService.equip_from_inventory(player.id, 0)

        remaining = await EquipmentService.degrade_equipment(
            player.id, EquipmentSlot.WEAPON, amount=1
        )

        expected = 500 - settings.EQUIPMENT_DURABILITY_LOSS_PER_HIT
        assert remaining == expected

    @pytest.mark.asyncio
    async def test_degrade_empty_slot_returns_none(
        self, session: AsyncSession, player_with_equipment):
        """Degrading empty slot should return None."""
        player = player_with_equipment
        remaining = await EquipmentService.degrade_equipment(player.id, EquipmentSlot.WEAPON)

        assert remaining is None

    @pytest.mark.asyncio
    async def test_degrade_to_zero(
        self, session: AsyncSession, player_with_equipment):
        """Durability should not go below zero."""
        player = player_with_equipment
        item = await ItemService.get_item_by_name("bronze_sword")

        await give_player_skill_level(session, player.id, "attack", 1)
        await InventoryService.add_item(player.id, item.id, durability=1)
        await EquipmentService.equip_from_inventory(player.id, 0)

        remaining = await EquipmentService.degrade_equipment(
            player.id, EquipmentSlot.WEAPON, amount=100
        )

        assert remaining == 0

    @pytest.mark.asyncio
    async def test_repair_restores_durability(
        self, session: AsyncSession, player_with_equipment):
        """Repairing should restore to max durability."""
        player = player_with_equipment
        item = await ItemService.get_item_by_name("bronze_sword")

        await give_player_skill_level(session, player.id, "attack", 1)
        await InventoryService.add_item(player.id, item.id, durability=250)
        await EquipmentService.equip_from_inventory(player.id, 0)

        success, cost = await EquipmentService.repair_equipment(player.id, EquipmentSlot.WEAPON)

        assert success is True
        assert cost > 0

        equipped = await EquipmentService.get_equipped_in_slot(player.id, EquipmentSlot.WEAPON)
        assert equipped.current_durability == item.max_durability


@pytest.mark.usefixtures("items_synced")
class TestClearEquipment:
    """Test clearing all equipment."""

    @pytest.mark.asyncio
    async def test_clear_equipment(
        self, session: AsyncSession, player_with_equipment):
        """Clear should remove all equipment."""
        player = player_with_equipment
        sword = await ItemService.get_item_by_name("bronze_shortsword")
        helmet = await ItemService.get_item_by_name("copper_helmet")

        await give_player_skill_level(session, player.id, "attack", 1)
        await give_player_skill_level(session, player.id, "defence", 1)

        await InventoryService.add_item(player.id, sword.id)
        await EquipmentService.equip_from_inventory(player.id, 0)

        await InventoryService.add_item(player.id, helmet.id)
        await EquipmentService.equip_from_inventory(player.id, 0)

        count = await EquipmentService.clear_equipment(player.id)

        assert count == 2

        equipment = await EquipmentService.get_equipment(player.id)
        # Check that all slots are empty
        for slot_data in equipment.slots:
            assert slot_data.item is None

    @pytest.mark.asyncio
    async def test_clear_empty_equipment(
        self, session: AsyncSession, player_with_equipment):
        """Clearing empty equipment should return 0."""
        player = player_with_equipment
        count = await EquipmentService.clear_equipment(player.id)

        assert count == 0


@pytest.mark.usefixtures("items_synced")
class TestGetAllEquippedItems:
    """Test getting all equipped items with data."""

    @pytest.mark.asyncio
    async def test_get_all_equipped_items(
        self, session: AsyncSession, player_with_equipment):
        """Should return list of (equipment, item) tuples."""
        player = player_with_equipment
        sword = await ItemService.get_item_by_name("bronze_shortsword")

        await give_player_skill_level(session, player.id, "attack", 1)
        await InventoryService.add_item(player.id, sword.id)
        await EquipmentService.equip_from_inventory(player.id, 0)

        items = await EquipmentService.get_all_equipped_items(player.id)

        assert len(items) == 1
        eq = items[0]
        assert eq.item.id == sword.id
        assert eq.item.display_name == "Bronze Sword"


@pytest.mark.usefixtures("items_synced")
class TestStackableAmmunition:
    """Test stackable ammunition in equipment."""

    @pytest.mark.asyncio
    async def test_equip_arrows_to_empty_slot(
        self, session: AsyncSession, player_with_equipment):
        """Equipping arrows to empty AMMO slot should work."""
        player = player_with_equipment
        arrows = await ItemService.get_item_by_name("bronze_arrows")

        await InventoryService.add_item(player.id, arrows.id, quantity=100)
        result = await EquipmentService.equip_from_inventory(player.id, 0)

        assert result.success is True
        assert "Bronze Arrows" in result.message

        equipped = await EquipmentService.get_equipped_in_slot(player.id, EquipmentSlot.AMMO)
        assert equipped is not None
        assert equipped.item.id == arrows.id
        assert equipped.quantity == 100

        inv = await InventoryService.get_item_at_slot(player.id, 0)
        assert inv is None

    @pytest.mark.asyncio
    async def test_unequip_ammo_preserves_quantity(
        self, session: AsyncSession, player_with_equipment):
        """Unequipping ammo should preserve quantity."""
        player = player_with_equipment
        arrows = await ItemService.get_item_by_name("bronze_arrows")

        await InventoryService.add_item(player.id, arrows.id, quantity=500)
        await EquipmentService.equip_from_inventory(player.id, 0)

        result = await EquipmentService.unequip_to_inventory(player.id, EquipmentSlot.AMMO)

        assert result.success is True

        equipped = await EquipmentService.get_equipped_in_slot(player.id, EquipmentSlot.AMMO)
        assert equipped is None

        inv = await InventoryService.get_item_at_slot(player.id, result.data.get("inventory_slot"))
        assert inv is not None
        assert inv.item.id == arrows.id
        assert inv.quantity == 500

    @pytest.mark.asyncio
    async def test_consume_ammo_reduces_quantity(
        self, session: AsyncSession, player_with_equipment):
        """Consuming ammo should reduce equipped quantity."""
        player = player_with_equipment
        arrows = await ItemService.get_item_by_name("bronze_arrows")

        await InventoryService.add_item(player.id, arrows.id, quantity=100)
        await EquipmentService.equip_from_inventory(player.id, 0)

        success, remaining = await EquipmentService.consume_ammo(player.id, 1)

        assert success is True
        assert remaining == 99

        equipped = await EquipmentService.get_equipped_in_slot(player.id, EquipmentSlot.AMMO)
        assert equipped.quantity == 99

    @pytest.mark.asyncio
    async def test_consume_ammo_removes_when_depleted(
        self, session: AsyncSession, player_with_equipment):
        """Consuming last ammo should remove equipment entry."""
        player = player_with_equipment
        arrows = await ItemService.get_item_by_name("bronze_arrows")

        await InventoryService.add_item(player.id, arrows.id, quantity=1)
        await EquipmentService.equip_from_inventory(player.id, 0)

        success, remaining = await EquipmentService.consume_ammo(player.id, 1)

        assert success is True
        assert remaining == 0

        equipped = await EquipmentService.get_equipped_in_slot(player.id, EquipmentSlot.AMMO)
        assert equipped is None

    @pytest.mark.asyncio
    async def test_consume_ammo_fails_when_not_enough(
        self, session: AsyncSession, player_with_equipment):
        """Consuming more ammo than available should fail."""
        player = player_with_equipment
        arrows = await ItemService.get_item_by_name("bronze_arrows")

        await InventoryService.add_item(player.id, arrows.id, quantity=5)
        await EquipmentService.equip_from_inventory(player.id, 0)

        success, remaining = await EquipmentService.consume_ammo(player.id, 10)

        assert success is False
        assert remaining == 5

        equipped = await EquipmentService.get_equipped_in_slot(player.id, EquipmentSlot.AMMO)
        assert equipped.quantity == 5
