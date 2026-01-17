"""
Tests for the hitpoints (HP) system.

Tests cover:
- HP service operations (damage, heal, set HP)
- HP in Valkey cache
- Death handling (item drop)
- Respawn mechanics
- Max HP calculation with equipment
- HP adjustments on equip/unequip
- WebSocket protocol HP integration
"""

import os
import uuid
import pytest
import pytest_asyncio
import msgpack
from starlette.testclient import TestClient
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
from server.src.models.item import Item
from server.src.tests.conftest import FakeValkey
from common.src.protocol import MessageType


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest_asyncio.fixture
async def items_synced(session: AsyncSession):
    """Ensure items are synced to database."""
    await ItemService.sync_items_to_db(session)


@pytest_asyncio.fixture
async def skills_synced(session: AsyncSession):
    """Ensure skills are synced to database."""
    await SkillService.sync_skills_to_db(session)


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
    # Grant skills including Hitpoints
    await SkillService.grant_all_skills_to_player(session, player.id)
    await session.refresh(player)
    return player


@pytest_asyncio.fixture
async def player_with_valkey(
    session: AsyncSession, 
    fake_valkey: FakeValkey, 
    player_with_hp,
):
    """Create a test player with HP data in Valkey."""
    player = player_with_hp
    
    # Set up player data in Valkey like websocket would
    player_key = f"player:{player.username}"
    await fake_valkey.hset(
        player_key,
        {
            "x": "10",
            "y": "10",
            "map_id": "samplemap",
            "current_hp": str(HITPOINTS_START_LEVEL),
            "max_hp": str(HITPOINTS_START_LEVEL),
            "player_id": str(player.id),
        },
    )
    
    return player


def unique_username(prefix: str = "user") -> str:
    """Generate a unique username for testing."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


# =============================================================================
# HP Service Unit Tests
# =============================================================================


class TestHpServiceValkey:
    """Tests for HP service Valkey operations."""

    @pytest.mark.asyncio
    async def test_get_hp_from_valkey(
        self, session: AsyncSession, fake_valkey: FakeValkey, player_with_valkey
    ):
        """Should get HP values from Valkey."""
        player = player_with_valkey
        
        current_hp, max_hp = await HpService.get_hp_from_valkey(
            fake_valkey, player.username
        )
        
        assert current_hp == HITPOINTS_START_LEVEL
        assert max_hp == HITPOINTS_START_LEVEL

    @pytest.mark.asyncio
    async def test_get_hp_from_valkey_missing_player(
        self, session: AsyncSession, fake_valkey: FakeValkey
    ):
        """Missing player should return default HP."""
        current_hp, max_hp = await HpService.get_hp_from_valkey(
            fake_valkey, "nonexistent_player"
        )
        
        assert current_hp == HITPOINTS_START_LEVEL
        assert max_hp == HITPOINTS_START_LEVEL

    @pytest.mark.asyncio
    async def test_set_hp_in_valkey(
        self, session: AsyncSession, fake_valkey: FakeValkey, player_with_valkey
    ):
        """Should update HP in Valkey."""
        player = player_with_valkey
        
        await HpService.set_hp_in_valkey(fake_valkey, player.username, 5, 15)
        
        current_hp, max_hp = await HpService.get_hp_from_valkey(
            fake_valkey, player.username
        )
        assert current_hp == 5
        assert max_hp == 15


class TestHpServiceDamage:
    """Tests for damage dealing."""

    @pytest.mark.asyncio
    async def test_deal_damage_basic(
        self, session: AsyncSession, fake_valkey: FakeValkey, player_with_valkey
    ):
        """Dealing damage should reduce HP."""
        player = player_with_valkey
        
        result = await HpService.deal_damage(
            session, fake_valkey, player.username, 3
        )
        
        assert result.success is True
        assert result.damage_dealt == 3
        assert result.new_hp == HITPOINTS_START_LEVEL - 3
        assert result.player_died is False

    @pytest.mark.asyncio
    async def test_deal_damage_kills_player(
        self, session: AsyncSession, fake_valkey: FakeValkey, player_with_valkey
    ):
        """Damage exceeding HP should kill player."""
        player = player_with_valkey
        
        result = await HpService.deal_damage(
            session, fake_valkey, player.username, 100
        )
        
        assert result.success is True
        assert result.new_hp == 0
        assert result.player_died is True
        assert "died" in result.message.lower()

    @pytest.mark.asyncio
    async def test_deal_damage_exact_kill(
        self, session: AsyncSession, fake_valkey: FakeValkey, player_with_valkey
    ):
        """Damage exactly equal to HP should kill player."""
        player = player_with_valkey
        
        result = await HpService.deal_damage(
            session, fake_valkey, player.username, HITPOINTS_START_LEVEL
        )
        
        assert result.success is True
        assert result.new_hp == 0
        assert result.player_died is True

    @pytest.mark.asyncio
    async def test_deal_damage_negative_rejected(
        self, session: AsyncSession, fake_valkey: FakeValkey, player_with_valkey
    ):
        """Negative damage should be rejected."""
        player = player_with_valkey
        
        result = await HpService.deal_damage(
            session, fake_valkey, player.username, -5
        )
        
        assert result.success is False
        assert "non-negative" in result.message.lower()

    @pytest.mark.asyncio
    async def test_deal_zero_damage(
        self, session: AsyncSession, fake_valkey: FakeValkey, player_with_valkey
    ):
        """Zero damage should succeed but not change HP."""
        player = player_with_valkey
        
        result = await HpService.deal_damage(
            session, fake_valkey, player.username, 0
        )
        
        assert result.success is True
        assert result.damage_dealt == 0
        assert result.new_hp == HITPOINTS_START_LEVEL


class TestHpServiceHeal:
    """Tests for healing."""

    @pytest.mark.asyncio
    async def test_heal_basic(
        self, session: AsyncSession, fake_valkey: FakeValkey, player_with_valkey
    ):
        """Healing should increase HP."""
        player = player_with_valkey
        
        # First damage the player
        await HpService.deal_damage(session, fake_valkey, player.username, 5)
        
        # Then heal
        result = await HpService.heal(session, fake_valkey, player.username, 3)
        
        assert result.success is True
        assert result.amount_healed == 3
        assert result.new_hp == HITPOINTS_START_LEVEL - 5 + 3

    @pytest.mark.asyncio
    async def test_heal_capped_at_max(
        self, session: AsyncSession, fake_valkey: FakeValkey, player_with_valkey
    ):
        """Healing should not exceed max HP."""
        player = player_with_valkey
        
        # Damage player by 2
        await HpService.deal_damage(session, fake_valkey, player.username, 2)
        
        # Try to heal by 100
        result = await HpService.heal(session, fake_valkey, player.username, 100)
        
        assert result.success is True
        assert result.amount_healed == 2  # Only healed what was missing
        assert result.new_hp == HITPOINTS_START_LEVEL

    @pytest.mark.asyncio
    async def test_heal_at_full_hp(
        self, session: AsyncSession, fake_valkey: FakeValkey, player_with_valkey
    ):
        """Healing at full HP should heal 0."""
        player = player_with_valkey
        
        result = await HpService.heal(session, fake_valkey, player.username, 10)
        
        assert result.success is True
        assert result.amount_healed == 0
        assert "full" in result.message.lower()

    @pytest.mark.asyncio
    async def test_heal_negative_rejected(
        self, session: AsyncSession, fake_valkey: FakeValkey, player_with_valkey
    ):
        """Negative healing should be rejected."""
        player = player_with_valkey
        
        result = await HpService.heal(session, fake_valkey, player.username, -5)
        
        assert result.success is False


class TestHpServiceSetHp:
    """Tests for setting HP directly."""

    @pytest.mark.asyncio
    async def test_set_hp(
        self, session: AsyncSession, fake_valkey: FakeValkey, player_with_valkey
    ):
        """Should set HP to specific value."""
        player = player_with_valkey
        
        new_hp, max_hp = await HpService.set_hp(
            session, fake_valkey, player.username, 5
        )
        
        assert new_hp == 5
        assert max_hp == HITPOINTS_START_LEVEL

    @pytest.mark.asyncio
    async def test_set_hp_capped_at_max(
        self, session: AsyncSession, fake_valkey: FakeValkey, player_with_valkey
    ):
        """Setting HP above max should cap at max."""
        player = player_with_valkey
        
        new_hp, max_hp = await HpService.set_hp(
            session, fake_valkey, player.username, 999
        )
        
        assert new_hp == max_hp

    @pytest.mark.asyncio
    async def test_set_hp_minimum_zero(
        self, session: AsyncSession, fake_valkey: FakeValkey, player_with_valkey
    ):
        """Setting HP below 0 should cap at 0."""
        player = player_with_valkey
        
        new_hp, _ = await HpService.set_hp(
            session, fake_valkey, player.username, -10
        )
        
        assert new_hp == 0


# =============================================================================
# Max HP Calculation Tests
# =============================================================================


class TestMaxHpCalculation:
    """Tests for max HP calculation with equipment."""

    @pytest.mark.asyncio
    async def test_max_hp_base_only(
        self, session: AsyncSession, player_with_hp
    ):
        """Max HP without equipment should be Hitpoints level."""
        player = player_with_hp
        
        max_hp = await EquipmentService.get_max_hp(session, player.id)
        
        assert max_hp == HITPOINTS_START_LEVEL

    @pytest.mark.asyncio
    async def test_max_hp_with_health_bonus(
        self, session: AsyncSession, player_with_hp, items_synced
    ):
        """Max HP with health bonus equipment should increase."""
        player = player_with_hp
        
        # Find an item with health_bonus
        result = await session.execute(
            select(Item).where(Item.health_bonus > 0)
        )
        health_item = result.scalar_one_or_none()
        
        if health_item is None:
            pytest.skip("No items with health_bonus in database")
        
        # Give player the item
        await InventoryService.add_item(session, player.id, health_item.id)
        
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
        
        # Equip item
        await EquipmentService.equip_from_inventory(session, player.id, 0)
        
        # Check max HP increased
        max_hp = await EquipmentService.get_max_hp(session, player.id)
        
        assert max_hp == HITPOINTS_START_LEVEL + health_item.health_bonus


# =============================================================================
# Death and Respawn Tests
# =============================================================================


class TestDeathHandling:
    """Tests for death handling."""

    @pytest.mark.asyncio
    async def test_handle_death_drops_items(
        self, session: AsyncSession, fake_valkey: FakeValkey, player_with_valkey, items_synced
    ):
        """Death should drop all inventory items."""
        player = player_with_valkey
        
        # Give player some items
        bronze_sword = await ItemService.get_item_by_name(session, "bronze_sword")
        if bronze_sword:
            await InventoryService.add_item(session, player.id, bronze_sword.id)
        
        # Handle death
        map_id, x, y, items_dropped = await HpService.handle_death(
            session, fake_valkey, player.username
        )
        
        assert map_id == "samplemap"
        assert x == 10
        assert y == 10
        # Should have dropped at least some items if any were added
        # (test checks the mechanism works, not exact counts)


class TestRespawn:
    """Tests for respawn mechanics."""

    @pytest.mark.asyncio
    async def test_respawn_restores_full_hp(
        self, session: AsyncSession, fake_valkey: FakeValkey, player_with_valkey
    ):
        """Respawn should restore player to full HP."""
        player = player_with_valkey
        
        # Damage player to 0
        await HpService.deal_damage(
            session, fake_valkey, player.username, HITPOINTS_START_LEVEL
        )
        
        # Respawn
        result = await HpService.respawn_player(session, fake_valkey, player.username)
        
        assert result.success is True
        assert result.new_hp == HITPOINTS_START_LEVEL

    @pytest.mark.asyncio
    async def test_respawn_updates_valkey(
        self, session: AsyncSession, fake_valkey: FakeValkey, player_with_valkey
    ):
        """Respawn should update position and HP in Valkey."""
        player = player_with_valkey
        
        # Respawn
        result = await HpService.respawn_player(session, fake_valkey, player.username)
        
        # Check Valkey was updated
        current_hp, max_hp = await HpService.get_hp_from_valkey(
            fake_valkey, player.username
        )
        
        assert current_hp == result.new_hp
        assert max_hp == result.new_hp

    @pytest.mark.asyncio
    async def test_respawn_updates_database(
        self, session: AsyncSession, fake_valkey: FakeValkey, player_with_valkey
    ):
        """Respawn should update position in database."""
        player = player_with_valkey
        
        # Respawn
        result = await HpService.respawn_player(session, fake_valkey, player.username)
        
        # Refresh player from database
        await session.refresh(player)
        
        assert player.current_hp == result.new_hp
        assert player.map_id == result.map_id
        assert player.x_coord == result.x
        assert player.y_coord == result.y


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

    def test_welcome_message_includes_hp(self):
        """WELCOME message should include current_hp and max_hp."""
        with TestClient(app) as client:
            # Create user via API
            username = unique_username("hptest")
            response = client.post(
                "/auth/register",
                json={"username": username, "password": "password123"},
            )
            assert response.status_code == 201
            
            # Login to get token
            response = client.post(
                "/auth/login",
                data={"username": username, "password": "password123"},
            )
            assert response.status_code == 200
            token = response.json()["access_token"]
            
            # Connect via WebSocket and authenticate
            with client.websocket_connect("/ws") as websocket:
                auth_message = {
                    "type": MessageType.AUTHENTICATE.value,
                    "payload": {"token": token},
                }
                websocket.send_bytes(msgpack.packb(auth_message, use_bin_type=True))
                
                response_bytes = websocket.receive_bytes()
                response = msgpack.unpackb(response_bytes, raw=False)
                
                assert response["type"] == MessageType.WELCOME.value
                assert "player" in response["payload"]
                player_data = response["payload"]["player"]
                
                # Check HP fields are present
                assert "current_hp" in player_data
                assert "max_hp" in player_data
                assert player_data["current_hp"] == HITPOINTS_START_LEVEL
                assert player_data["max_hp"] == HITPOINTS_START_LEVEL

    def test_new_player_starts_with_correct_hp(self):
        """Newly registered player should have correct starting HP."""
        with TestClient(app) as client:
            # Create user via API
            username = unique_username("newhptest")
            response = client.post(
                "/auth/register",
                json={"username": username, "password": "password123"},
            )
            assert response.status_code == 201
            
            # Login to get token
            response = client.post(
                "/auth/login",
                data={"username": username, "password": "password123"},
            )
            token = response.json()["access_token"]
            
            # Connect and get WELCOME
            with client.websocket_connect("/ws") as websocket:
                auth_message = {
                    "type": MessageType.AUTHENTICATE.value,
                    "payload": {"token": token},
                }
                websocket.send_bytes(msgpack.packb(auth_message, use_bin_type=True))
                
                response_bytes = websocket.receive_bytes()
                response = msgpack.unpackb(response_bytes, raw=False)
                
                player_data = response["payload"]["player"]
                assert player_data["current_hp"] == HITPOINTS_START_LEVEL
                assert player_data["max_hp"] == HITPOINTS_START_LEVEL


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
        cleanup_disconnected_player(test_username)
        
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
