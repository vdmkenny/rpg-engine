"""
Integration tests for the admin /give command handler.

Tests cover:
- Non-admin rejected with ADMIN_NOT_AUTHORIZED
- Invalid item name returns ADMIN_ITEM_NOT_FOUND
- Non-existent target player returns ADMIN_PLAYER_NOT_FOUND
- Full inventory returns ADMIN_INVENTORY_FULL
- Invalid quantity returns ADMIN_INVALID_QUANTITY
- Successful give (single item)
- Successful give with stacking
"""

import uuid
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

from server.src.core.constants import PlayerRole
from server.src.services.player_service import PlayerService
from server.src.services.inventory_service import InventoryService
from server.src.services.item_service import ItemService

from common.src.protocol import (
    WSMessage,
    MessageType,
    ErrorCodes,
    ErrorCategory,
    AdminGivePayload,
)

from server.src.api.handlers.admin_mixin import AdminHandlerMixin, MAX_GIVE_QUANTITY


class FakeAdminHandler(AdminHandlerMixin):
    """
    Minimal concrete handler that inherits AdminHandlerMixin and stubs
    the BaseHandlerMixin helpers so we can test the mixin in isolation.
    """

    def __init__(self, player_id: int, username: str):
        self.player_id = player_id
        self.username = username
        self.websocket = MagicMock()

        # Capture outgoing responses
        self.success_responses: list = []
        self.error_responses: list = []

    async def _send_success_response(self, correlation_id, payload, **kwargs):
        self.success_responses.append(
            {"correlation_id": correlation_id, "payload": payload}
        )

    async def _send_error_response(
        self, correlation_id, error_code, error_category, message, **kwargs
    ):
        self.error_responses.append(
            {
                "correlation_id": correlation_id,
                "error_code": error_code,
                "error_category": error_category,
                "message": message,
                "kwargs": kwargs,
            }
        )


def _make_message(target_username: str, item_name: str, quantity: int = 1) -> WSMessage:
    """Create a CMD_ADMIN_GIVE WSMessage."""
    return WSMessage(
        id="test-correlation-id",
        type=MessageType.CMD_ADMIN_GIVE,
        payload={
            "target_username": target_username,
            "item_name": item_name,
            "quantity": quantity,
        },
        version="2.0",
    )


@pytest_asyncio.fixture
async def admin_player(session: AsyncSession, create_test_player):
    """Create a test player with admin role."""
    unique_name = f"admin_{uuid.uuid4().hex[:8]}"
    player = await create_test_player(unique_name, "password123", role=PlayerRole.ADMIN)
    await PlayerService.login_player(player.id)
    return player


@pytest_asyncio.fixture
async def target_player(session: AsyncSession, create_test_player):
    """Create a regular test player to receive items."""
    unique_name = f"target_{uuid.uuid4().hex[:8]}"
    player = await create_test_player(unique_name, "password123")
    await PlayerService.login_player(player.id)
    return player


@pytest_asyncio.fixture
async def regular_player(session: AsyncSession, create_test_player):
    """Create a regular (non-admin) test player."""
    unique_name = f"regular_{uuid.uuid4().hex[:8]}"
    player = await create_test_player(unique_name, "password123")
    await PlayerService.login_player(player.id)
    return player


@pytest.mark.usefixtures("items_synced")
class TestAdminGiveAuthorization:
    """Test admin role enforcement."""

    @pytest.mark.asyncio
    async def test_non_admin_rejected(self, session, regular_player, target_player):
        """Non-admin player should receive ADMIN_NOT_AUTHORIZED error."""
        handler = FakeAdminHandler(regular_player.id, regular_player.username)
        msg = _make_message(target_player.username, "bronze_shortsword")

        await handler._handle_cmd_admin_give(msg)

        assert len(handler.error_responses) == 1
        assert handler.error_responses[0]["error_code"] == ErrorCodes.ADMIN_NOT_AUTHORIZED
        assert handler.error_responses[0]["error_category"] == ErrorCategory.PERMISSION
        assert len(handler.success_responses) == 0

    @pytest.mark.asyncio
    async def test_admin_authorized(self, session, admin_player, target_player):
        """Admin player should succeed when giving a valid item."""
        handler = FakeAdminHandler(admin_player.id, admin_player.username)
        msg = _make_message(target_player.username, "bronze_shortsword")

        # Patch out the target inventory update since there is no real websocket
        with patch.object(handler, "_send_target_inventory_update", new_callable=AsyncMock):
            await handler._handle_cmd_admin_give(msg)

        assert len(handler.success_responses) == 1
        assert len(handler.error_responses) == 0
        assert "bronze_shortsword" in handler.success_responses[0]["payload"]["message"].lower() or \
               "Bronze Shortsword" in handler.success_responses[0]["payload"]["message"]


@pytest.mark.usefixtures("items_synced")
class TestAdminGiveValidation:
    """Test input validation for the admin give command."""

    @pytest.mark.asyncio
    async def test_item_not_found(self, session, admin_player, target_player):
        """Non-existent item name should return ADMIN_ITEM_NOT_FOUND."""
        handler = FakeAdminHandler(admin_player.id, admin_player.username)
        msg = _make_message(target_player.username, "nonexistent_item_xyz")

        await handler._handle_cmd_admin_give(msg)

        assert len(handler.error_responses) == 1
        assert handler.error_responses[0]["error_code"] == ErrorCodes.ADMIN_ITEM_NOT_FOUND

    @pytest.mark.asyncio
    async def test_player_not_found(self, session, admin_player):
        """Non-existent target player should return ADMIN_PLAYER_NOT_FOUND."""
        handler = FakeAdminHandler(admin_player.id, admin_player.username)
        msg = _make_message("totally_fake_player_xyz", "bronze_shortsword")

        await handler._handle_cmd_admin_give(msg)

        assert len(handler.error_responses) == 1
        assert handler.error_responses[0]["error_code"] == ErrorCodes.ADMIN_PLAYER_NOT_FOUND

    @pytest.mark.asyncio
    async def test_invalid_quantity_zero(self, session, admin_player, target_player):
        """Quantity of 0 should return ADMIN_INVALID_QUANTITY."""
        handler = FakeAdminHandler(admin_player.id, admin_player.username)
        msg = _make_message(target_player.username, "bronze_shortsword", quantity=0)

        await handler._handle_cmd_admin_give(msg)

        assert len(handler.error_responses) == 1
        assert handler.error_responses[0]["error_code"] == ErrorCodes.ADMIN_INVALID_QUANTITY

    @pytest.mark.asyncio
    async def test_invalid_quantity_negative(self, session, admin_player, target_player):
        """Negative quantity should return ADMIN_INVALID_QUANTITY."""
        handler = FakeAdminHandler(admin_player.id, admin_player.username)
        msg = _make_message(target_player.username, "bronze_shortsword", quantity=-5)

        await handler._handle_cmd_admin_give(msg)

        assert len(handler.error_responses) == 1
        assert handler.error_responses[0]["error_code"] == ErrorCodes.ADMIN_INVALID_QUANTITY

    @pytest.mark.asyncio
    async def test_invalid_quantity_exceeds_max(self, session, admin_player, target_player):
        """Quantity exceeding MAX_GIVE_QUANTITY should return ADMIN_INVALID_QUANTITY."""
        handler = FakeAdminHandler(admin_player.id, admin_player.username)
        msg = _make_message(target_player.username, "bronze_shortsword", quantity=MAX_GIVE_QUANTITY + 1)

        await handler._handle_cmd_admin_give(msg)

        assert len(handler.error_responses) == 1
        assert handler.error_responses[0]["error_code"] == ErrorCodes.ADMIN_INVALID_QUANTITY

    @pytest.mark.asyncio
    async def test_invalid_payload(self, session, admin_player):
        """Malformed payload should return ADMIN_INVALID_QUANTITY (validation error)."""
        handler = FakeAdminHandler(admin_player.id, admin_player.username)
        msg = WSMessage(
            id="test-id",
            type=MessageType.CMD_ADMIN_GIVE,
            payload={"bad_field": "nonsense"},
        )

        await handler._handle_cmd_admin_give(msg)

        assert len(handler.error_responses) == 1
        assert handler.error_responses[0]["error_code"] == ErrorCodes.ADMIN_INVALID_QUANTITY


@pytest.mark.usefixtures("items_synced")
class TestAdminGiveSuccess:
    """Test successful admin give operations."""

    @pytest.mark.asyncio
    async def test_give_single_item(self, session, admin_player, target_player):
        """Giving a single item should succeed and appear in target inventory."""
        handler = FakeAdminHandler(admin_player.id, admin_player.username)
        msg = _make_message(target_player.username, "bronze_shortsword", quantity=1)

        with patch.object(handler, "_send_target_inventory_update", new_callable=AsyncMock):
            await handler._handle_cmd_admin_give(msg)

        assert len(handler.success_responses) == 1
        assert handler.success_responses[0]["payload"]["quantity"] == 1
        assert handler.success_responses[0]["payload"]["target_player_id"] == target_player.id

        # Verify item is actually in the target's inventory
        inventory = await InventoryService.get_inventory(target_player.id)
        items = [slot for slot in inventory.slots if slot is not None]
        assert len(items) >= 1

    @pytest.mark.asyncio
    async def test_give_stackable_items(self, session, admin_player, target_player):
        """Giving stackable items should stack correctly."""
        handler = FakeAdminHandler(admin_player.id, admin_player.username)

        # Give 5 copper ores (stackable)
        msg = _make_message(target_player.username, "copper_ore", quantity=5)

        with patch.object(handler, "_send_target_inventory_update", new_callable=AsyncMock):
            await handler._handle_cmd_admin_give(msg)

        assert len(handler.success_responses) == 1
        assert handler.success_responses[0]["payload"]["quantity"] == 5

        # Give 3 more - should stack on top
        handler.success_responses.clear()
        msg2 = _make_message(target_player.username, "copper_ore", quantity=3)

        with patch.object(handler, "_send_target_inventory_update", new_callable=AsyncMock):
            await handler._handle_cmd_admin_give(msg2)

        assert len(handler.success_responses) == 1
        assert handler.success_responses[0]["payload"]["quantity"] == 3

    @pytest.mark.asyncio
    async def test_give_to_self(self, session, admin_player):
        """Admin should be able to give items to themselves."""
        handler = FakeAdminHandler(admin_player.id, admin_player.username)
        msg = _make_message(admin_player.username, "bronze_shortsword", quantity=1)

        with patch.object(handler, "_send_target_inventory_update", new_callable=AsyncMock):
            await handler._handle_cmd_admin_give(msg)

        assert len(handler.success_responses) == 1
        assert handler.success_responses[0]["payload"]["target_player_id"] == admin_player.id

    @pytest.mark.asyncio
    async def test_inventory_full(self, session, admin_player, target_player):
        """Giving items when inventory is full should return ADMIN_INVENTORY_FULL."""
        handler = FakeAdminHandler(admin_player.id, admin_player.username)

        # Fill target inventory (28 slots) with non-stackable items
        item = await ItemService.get_item_by_name("bronze_shortsword")
        assert item is not None
        for _ in range(28):
            result = await InventoryService.add_item(target_player.id, item.id, quantity=1)
            assert result.success, f"Failed to fill inventory: {result.message}"

        # Now try to give one more
        msg = _make_message(target_player.username, "bronze_shortsword", quantity=1)
        await handler._handle_cmd_admin_give(msg)

        assert len(handler.error_responses) == 1
        assert handler.error_responses[0]["error_code"] == ErrorCodes.ADMIN_INVENTORY_FULL
