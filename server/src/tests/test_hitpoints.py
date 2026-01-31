"""
Tests for the hitpoints (HP) system.

Tests cover:
- HP service operations (damage, heal, set HP)
- Max HP calculation with equipment
- Death handling (item drop)
- Respawn mechanics
- WebSocket protocol HP integration
"""

import os
import uuid
import pytest
import pytest_asyncio
import msgpack
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from server.src.main import app
from server.src.core.database import reset_engine, reset_valkey
from server.src.core.security import create_access_token
from server.src.core.skills import HITPOINTS_START_LEVEL
from server.src.models.player import Player
from server.src.models.skill import Skill, PlayerSkill
from server.src.services.hp_service import HpService
from server.src.services.equipment_service import EquipmentService
from server.src.services.inventory_service import InventoryService
from server.src.services.item_service import ItemService
from server.src.services.skill_service import SkillService
from server.src.services.ground_item_service import GroundItemService
from server.src.models.item import Item
from server.src.tests.conftest import FakeValkey
from server.src.services.game_state_manager import GameStateManager
from common.src.protocol import MessageType


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest_asyncio.fixture
async def skills_synced(session: AsyncSession, gsm):
    """Ensure skills are synced to database."""
    await SkillService.sync_skills_to_db()


@pytest_asyncio.fixture
async def player_with_hp(
    session: AsyncSession, create_test_player, skills_synced
):
    """Create a test player with HP initialized."""
    unique_name = f"hp_test_{uuid.uuid4().hex[:8]}"
    player = await create_test_player(
        unique_name, 
        "password123",
        current_hp=HITPOINTS_START_LEVEL,
    )
    # CRITICAL: Commit the player to database before calling GSM methods
    # GSM uses its own session and cannot see uncommitted changes
    await session.commit()
    
    # Grant skills including Hitpoints - now GSM can see the committed player
    await SkillService.grant_all_skills_to_player(player.id)
    await session.refresh(player)
    return player


@pytest_asyncio.fixture
async def player_with_gsm(
    session: AsyncSession, 
    gsm: GameStateManager,
    player_with_hp,
):
    """Create a test player with state loaded into GSM."""
    player = player_with_hp
    
    # Register player as online in GSM
    gsm.register_online_player(player.id, player.username)
    
    # Set up player state in GSM
    await gsm.set_player_full_state(
        player_id=player.id,
        x=10,
        y=10,
        map_id="samplemap",
        current_hp=HITPOINTS_START_LEVEL,
        max_hp=HITPOINTS_START_LEVEL,
    )
    
    # Skills were already granted by player_with_hp fixture
    # No need to duplicate the grant_all_skills_to_player_offline call
    
    return player


def unique_username(prefix: str = "user") -> str:
    """Generate a unique username for testing."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


# =============================================================================
# HP Service Unit Tests
# =============================================================================


class TestHpServiceDamage:
    """Tests for damage dealing."""

    @pytest.mark.asyncio
    async def test_deal_damage_basic(
        self, session: AsyncSession, gsm: GameStateManager, player_with_gsm
    ):
        """Dealing damage should reduce HP."""
        player = player_with_gsm
        
        result = await HpService.deal_damage(player.id, 3)
        
        assert result.success is True
        assert result.damage_dealt == 3
        assert result.new_hp == HITPOINTS_START_LEVEL - 3
        assert result.player_died is False

    @pytest.mark.asyncio
    async def test_deal_damage_kills_player(
        self, session: AsyncSession, gsm: GameStateManager, player_with_gsm
    ):
        """Damage exceeding HP should kill player."""
        player = player_with_gsm
        
        result = await HpService.deal_damage(player.id, 100)
        
        assert result.success is True
        assert result.new_hp == 0
        assert result.player_died is True
        assert "died" in result.message.lower()

    @pytest.mark.asyncio
    async def test_deal_damage_exact_kill(
        self, session: AsyncSession, gsm: GameStateManager, player_with_gsm
    ):
        """Damage exactly equal to HP should kill player."""
        player = player_with_gsm
        
        result = await HpService.deal_damage(player.id, HITPOINTS_START_LEVEL)
        
        assert result.success is True
        assert result.new_hp == 0
        assert result.player_died is True

    @pytest.mark.asyncio
    async def test_deal_damage_negative_rejected(
        self, session: AsyncSession, gsm: GameStateManager, player_with_gsm
    ):
        """Negative damage should be rejected."""
        player = player_with_gsm
        
        result = await HpService.deal_damage(player.id, -5)
        
        assert result.success is False
        assert "non-negative" in result.message.lower()

    @pytest.mark.asyncio
    async def test_deal_zero_damage(
        self, session: AsyncSession, gsm: GameStateManager, player_with_gsm
    ):
        """Zero damage should succeed but not change HP."""
        player = player_with_gsm
        
        result = await HpService.deal_damage(player.id, 0)
        
        assert result.success is True
        assert result.damage_dealt == 0
        assert result.new_hp == HITPOINTS_START_LEVEL


class TestHpServiceHeal:
    """Tests for healing."""

    @pytest.mark.asyncio
    async def test_heal_basic(
        self, session: AsyncSession, gsm: GameStateManager, player_with_gsm
    ):
        """Healing should increase HP."""
        player = player_with_gsm
        
        # First damage the player
        await HpService.deal_damage(player.id, 5)
        
        # Then heal
        result = await HpService.heal(player.id, 3)
        
        assert result.success is True
        assert result.amount_healed == 3
        assert result.new_hp == HITPOINTS_START_LEVEL - 5 + 3

    @pytest.mark.asyncio
    async def test_heal_capped_at_max(
        self, session: AsyncSession, gsm: GameStateManager, player_with_gsm
    ):
        """Healing should not exceed max HP."""
        player = player_with_gsm
        
        # Damage player by 2
        await HpService.deal_damage(player.id, 2)
        
        # Try to heal by 100
        result = await HpService.heal(player.id, 100)
        
        assert result.success is True
        assert result.amount_healed == 2  # Only healed what was missing
        assert result.new_hp == HITPOINTS_START_LEVEL

    @pytest.mark.asyncio
    async def test_heal_at_full_hp(
        self, session: AsyncSession, gsm: GameStateManager, player_with_gsm
    ):
        """Healing at full HP should heal 0."""
        player = player_with_gsm
        
        result = await HpService.heal(player.id, 10)
        
        assert result.success is True
        assert result.amount_healed == 0
        assert "full" in result.message.lower()

    @pytest.mark.asyncio
    async def test_heal_negative_rejected(
        self, session: AsyncSession, gsm: GameStateManager, player_with_gsm
    ):
        """Negative healing should be rejected."""
        player = player_with_gsm
        
        result = await HpService.heal(player.id, -5)
        
        assert result.success is False


class TestHpServiceSetHp:
    """Tests for setting HP directly."""

    @pytest.mark.asyncio
    async def test_set_hp(
        self, session: AsyncSession, gsm: GameStateManager, player_with_gsm
    ):
        """Should set HP to specific value."""
        player = player_with_gsm
        
        new_hp, max_hp = await HpService.set_hp_value(player.id, 5)
        
        assert new_hp == 5
        assert max_hp == HITPOINTS_START_LEVEL

    @pytest.mark.asyncio
    async def test_set_hp_capped_at_max(
        self, session: AsyncSession, gsm: GameStateManager, player_with_gsm
    ):
        """Setting HP above max should cap at max."""
        player = player_with_gsm
        
        new_hp, max_hp = await HpService.set_hp_value(player.id, 999)
        
        assert new_hp == max_hp

    @pytest.mark.asyncio
    async def test_set_hp_minimum_zero(
        self, session: AsyncSession, gsm: GameStateManager, player_with_gsm
    ):
        """Setting HP below 0 should cap at 0."""
        player = player_with_gsm
        
        new_hp, _ = await HpService.set_hp_value(player.id, -10)
        
        assert new_hp == 0


# =============================================================================
# Max HP Calculation Tests
# =============================================================================


class TestMaxHpCalculation:
    """Tests for max HP calculation with equipment."""

    @pytest.mark.asyncio
    async def test_max_hp_base_only(
        self, session: AsyncSession, gsm: GameStateManager, player_with_gsm
    ):
        """Max HP without equipment should be Hitpoints level."""
        player = player_with_gsm
        
        max_hp = await EquipmentService.get_max_hp(player.id)
        
        assert max_hp == HITPOINTS_START_LEVEL

    @pytest.mark.asyncio
    async def test_max_hp_with_health_bonus(
        self, session: AsyncSession, gsm: GameStateManager, player_with_gsm, items_synced
    ):
        """Max HP with health bonus equipment should increase."""
        player = player_with_gsm
        
        # Find an item with health_bonus
        result = await session.execute(
            select(Item).where(Item.health_bonus > 0).limit(1)
        )
        health_item = result.scalar_one_or_none()
        
        if health_item is None:
            pytest.skip("No items with health_bonus in database")
        
        # Get required skill level if needed
        if health_item.required_skill and health_item.required_level:
            result = await session.execute(
                select(Skill).where(Skill.name == health_item.required_skill)
            )
            skill = result.scalar_one_or_none()
            if skill:
                result = await session.execute(
                    select(PlayerSkill)
                    .where(PlayerSkill.player_id == player.id)
                    .where(PlayerSkill.skill_id == skill.id)
                )
                player_skill = result.scalar_one_or_none()
                if player_skill:
                    player_skill.current_level = health_item.required_level
                    await session.commit()
                    # Update skill in GSM
                    await gsm.set_skill(
                        player.id, 
                        skill.name, 
                        skill.id, 
                        health_item.required_level, 
                        player_skill.experience
                    )
        
        # Set equipment directly in GSM
        await gsm.set_equipment_slot(
            player.id, 
            health_item.equipment_slot, 
            health_item.id, 
            1, 
            health_item.max_durability
        )
        
        # Check max HP increased
        max_hp = await EquipmentService.get_max_hp(player.id)
        
        assert max_hp == HITPOINTS_START_LEVEL + health_item.health_bonus


# =============================================================================
# Death and Respawn Tests
# =============================================================================


class TestDeathHandling:
    """Tests for death handling."""

    @pytest.mark.asyncio
    async def test_handle_death_drops_items(
        self, session: AsyncSession, gsm: GameStateManager, player_with_gsm, items_synced
    ):
        """Death should drop all inventory items."""
        player = player_with_gsm
        
        # Give player some items via GSM
        bronze_sword = await ItemService.get_item_by_name("bronze_sword")
        if bronze_sword:
            await gsm.set_inventory_slot(player.id, 0, bronze_sword.id, 1, bronze_sword.max_durability)
        
        # Handle death
        map_id, x, y, items_dropped = await HpService.handle_death(player.id)
        
        assert map_id == "samplemap"
        assert x == 10
        assert y == 10
        if bronze_sword:
            assert items_dropped >= 1

    @pytest.mark.asyncio
    async def test_death_clears_inventory(
        self, session: AsyncSession, gsm: GameStateManager, player_with_gsm, items_synced
    ):
        """Death should clear player inventory."""
        player = player_with_gsm
        
        # Give player items
        bronze_sword = await ItemService.get_item_by_name("bronze_sword")
        if bronze_sword:
            await gsm.set_inventory_slot(player.id, 0, bronze_sword.id, 1, bronze_sword.max_durability)
            await gsm.set_inventory_slot(player.id, 1, bronze_sword.id, 1, bronze_sword.max_durability)
        
        # Verify inventory has items
        inventory = await gsm.get_inventory(player.id)
        assert len(inventory) == 2
        
        # Handle death
        await HpService.handle_death(player.id)
        
        # Verify inventory is cleared
        inventory = await gsm.get_inventory(player.id)
        assert len(inventory) == 0


class TestRespawn:
    """Tests for respawn mechanics."""

    @pytest.mark.asyncio
    async def test_respawn_restores_full_hp(
        self, session: AsyncSession, gsm: GameStateManager, player_with_gsm
    ):
        """Respawn should restore player to full HP."""
        player = player_with_gsm
        
        # Damage player to 0
        await HpService.deal_damage(player.id, HITPOINTS_START_LEVEL)
        
        # Respawn
        result = await HpService.respawn_player(player.id)
        
        assert result.success is True
        assert result.new_hp == HITPOINTS_START_LEVEL

    @pytest.mark.asyncio
    async def test_respawn_updates_gsm(
        self, session: AsyncSession, gsm: GameStateManager, player_with_gsm
    ):
        """Respawn should update position and HP in GSM."""
        player = player_with_gsm
        
        # Respawn
        result = await HpService.respawn_player(player.id)
        
        # Check GSM was updated
        current_hp, max_hp = await HpService.get_hp(player.id)
        
        assert current_hp == result.new_hp
        assert max_hp == result.new_hp


# =============================================================================
# WebSocket Integration Tests
# =============================================================================


# Skip WebSocket integration tests unless RUN_INTEGRATION_TESTS is set
SKIP_WS_INTEGRATION = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS", "").lower() not in ("1", "true", "yes"),
    reason="WebSocket integration tests require RUN_INTEGRATION_TESTS=1"
)


@SKIP_WS_INTEGRATION
class TestWebSocketHpIntegration:
    """Tests for HP in WebSocket protocol."""

    @pytest.fixture(autouse=True)
    def reset_db_engine(self):
        """Reset the database engine and Valkey before each test."""
        reset_engine()
        reset_valkey()

    @pytest.mark.asyncio
    async def test_welcome_message_includes_hp(self):
        """WELCOME message should include current_hp and max_hp."""
        from httpx_ws import aconnect_ws
        from httpx_ws.transport import ASGIWebSocketTransport
        
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Create user via API
            username = unique_username("hptest")
            response = await client.post(
                "/auth/register",
                json={"username": username, "password": "password123"},
            )
            assert response.status_code == 201
            
            # Login to get token
            response = await client.post(
                "/auth/login",
                data={"username": username, "password": "password123"},
            )
            assert response.status_code == 200
            token = response.json()["access_token"]
            
            # Connect via WebSocket and authenticate using httpx-ws
            ws_transport = ASGIWebSocketTransport(app)
            async with AsyncClient(transport=ws_transport, base_url="http://test") as ws_client:
                async with aconnect_ws("http://test/ws", ws_client) as websocket:
                    auth_message = {
                        "type": MessageType.CMD_AUTHENTICATE,
                        "payload": {"token": token},
                    }
                    await websocket.send_bytes(msgpack.packb(auth_message, use_bin_type=True))
                    
                    response_bytes = await websocket.receive_bytes()
                    response = msgpack.unpackb(response_bytes, raw=False)
                    
                    assert response["type"] == MessageType.EVENT_WELCOME
                    assert "player" in response["payload"]
                    player_data = response["payload"]["player"]
                    
                    # Check HP fields are present in nested hp object
                    assert "hp" in player_data
                    hp_data = player_data["hp"]
                    assert "current_hp" in hp_data
                    assert "max_hp" in hp_data
                    assert hp_data["current_hp"] == HITPOINTS_START_LEVEL
                    assert hp_data["max_hp"] == HITPOINTS_START_LEVEL


# =============================================================================
# Game Loop HP Regen Tests
# =============================================================================


class TestHpRegeneration:
    """Tests for HP regeneration in game loop."""

    @pytest.mark.asyncio
    async def test_player_login_tick_tracking(self):
        """Player login tick should be tracked for staggered regen."""
        from server.src.game.game_loop import (
            register_player_login,
            cleanup_disconnected_player,
            player_login_ticks,
            _global_tick_counter,
        )
        
        test_username = "regen_test_user"
        
        # Register player login
        register_player_login(test_username)
        
        assert test_username in player_login_ticks
        assert player_login_ticks[test_username] == _global_tick_counter
        
        # Cleanup
        await cleanup_disconnected_player(test_username)
        
        assert test_username not in player_login_ticks

    @pytest.mark.asyncio
    async def test_entity_diff_includes_hp_changes(self):
        """Entity diff should detect HP changes."""
        from server.src.game.game_loop import compute_entity_diff
        
        last_visible = {
            "player1": {"username": "player1", "x": 10, "y": 10, "current_hp": 10, "max_hp": 10},
        }
        
        current_visible = {
            "player1": {"username": "player1", "x": 10, "y": 10, "current_hp": 8, "max_hp": 10},
        }
        
        diff = compute_entity_diff(current_visible, last_visible)
        
        # Should detect HP change as an update
        assert len(diff["updated"]) == 1
        assert diff["updated"][0]["current_hp"] == 8

    @pytest.mark.asyncio
    async def test_entity_diff_no_change_no_update(self):
        """Entity diff should not include unchanged entities."""
        from server.src.game.game_loop import compute_entity_diff
        
        last_visible = {
            "player1": {"username": "player1", "x": 10, "y": 10, "current_hp": 10, "max_hp": 10},
        }
        
        current_visible = {
            "player1": {"username": "player1", "x": 10, "y": 10, "current_hp": 10, "max_hp": 10},
        }
        
        diff = compute_entity_diff(current_visible, last_visible)
        
        assert len(diff["updated"]) == 0
        assert len(diff["added"]) == 0
        assert len(diff["removed"]) == 0
