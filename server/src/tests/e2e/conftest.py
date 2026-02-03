"""
Test fixtures for E2E WebSocket tests.

Fixtures for full WebSocket client testing.
"""

import pytest
import pytest_asyncio


@pytest.fixture
def authenticated_websocket_client(test_client):
    """Factory fixture for authenticated WebSocket client."""
    async def _create(username="test_user", password="test_pass"):
        # Create player and authenticate
        from server.src.services.player_service import PlayerService
        from server.src.schemas.player import PlayerCreate
        
        player_data = PlayerCreate(username=username, password=password)
        try:
            player = await PlayerService.create_player(player_data)
        except Exception:
            # Player might already exist
            pass
        
        # Return authenticated client
        return test_client
    return _create


@pytest.fixture
def multiplayer_test_context(test_client, create_test_player):
    """Fixture for multiplayer scenario testing."""
    async def _setup(num_players=2):
        players = []
        for i in range(num_players):
            player = await create_test_player(f"multiplayer_test_{i}", "password123")
            players.append(player)
        return players
    return _setup
