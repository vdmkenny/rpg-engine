"""
Integration tests for entity visibility in WebSocket game loop.

These tests verify that entities are properly broadcast to players
via the WebSocket game loop.

NOTE: These tests require the game loop to be running, which is started
in FastAPI's lifespan. The ASGIWebSocketTransport used by httpx-ws doesn't
trigger lifespan events, so these tests are skipped in the test environment.

To run these tests, use a real server with the game loop active.
"""

import pytest
import asyncio

from common.src.protocol import MessageType
from server.src.tests.websocket_test_utils import (
    WebSocketTestClient,
    ResponseTimeoutError,
    ENTITY_SPAWN_WAIT,
    GAME_TICK_WAIT,
)


# Constants for entity spawning
GOBLIN_MAX_HP = 10
GIANT_RAT_MAX_HP = 5
GUARD_MAX_HP = 50
MERCHANT_MAX_HP = 50

# Skip reason for game loop dependent tests
GAME_LOOP_SKIP_REASON = (
    "These tests require the game loop to be running. "
    "The ASGIWebSocketTransport used in tests doesn't trigger FastAPI lifespan events, "
    "so the game loop never starts. Run these tests against a real server."
)


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skip(reason=GAME_LOOP_SKIP_REASON)
class TestEntityVisibilityIntegration:
    """Integration tests for entity visibility in game loop."""
    
    async def test_entity_appears_in_state_update(self, test_client: WebSocketTestClient):
        """Test that a spawned entity appears in game state updates."""
        from server.src.services.game_state_manager import get_game_state_manager
        
        gsm = get_game_state_manager()
        
        # test_client player is at position (10, 10) on "samplemap"
        spawn_x, spawn_y = 15, 15  # Near player, within visibility range
        
        # Spawn an entity near the player
        instance_id = await gsm.spawn_entity_instance(
            entity_name="GOBLIN",
            map_id="samplemap",
            x=spawn_x,
            y=spawn_y,
            spawn_x=spawn_x,
            spawn_y=spawn_y,
            max_hp=GOBLIN_MAX_HP,
            wander_radius=5,
            spawn_point_id=1
        )
        
        assert instance_id is not None, "Failed to spawn entity"
        
        # Wait for next game loop tick (should include the entity)
        # Game loop runs at 20 TPS = every 0.05s, wait up to 2 seconds
        entity_seen = False
        for _ in range(40):  # Try for 2 seconds (40 * 0.05s)
            try:
                state_update = await test_client.expect_event(
                    MessageType.EVENT_STATE_UPDATE,
                    timeout=0.1
                )
                
                entities = state_update.payload.get("entities", [])
                
                # Check if our entity is in the update
                for entity in entities:
                    if (entity.get("type") == "entity" and 
                        entity.get("id") == instance_id):
                        entity_seen = True
                        
                        # Verify entity data
                        assert entity["entity_name"] == "GOBLIN"
                        assert entity["x"] == spawn_x
                        assert entity["y"] == spawn_y
                        assert entity["max_hp"] == GOBLIN_MAX_HP
                        assert entity["current_hp"] == GOBLIN_MAX_HP
                        assert entity["state"] == "idle"
                        
                        break
                
                if entity_seen:
                    break
                    
            except ResponseTimeoutError:
                await asyncio.sleep(GAME_TICK_WAIT)
                continue
        
        assert entity_seen, f"Entity {instance_id} did not appear in state updates"
    
    async def test_entity_visibility_range(self, test_client: WebSocketTestClient):
        """Test that entities only appear when within visibility range."""
        from server.src.services.game_state_manager import get_game_state_manager
        
        gsm = get_game_state_manager()
        
        # Spawn entity out of range (player at 10,10, visibility = 32 tiles)
        far_x, far_y = 100, 100  # Far away
        far_entity_id = await gsm.spawn_entity_instance(
            entity_name="GIANT_RAT",
            map_id="samplemap",
            x=far_x,
            y=far_y,
            spawn_x=far_x,
            spawn_y=far_y,
            max_hp=GIANT_RAT_MAX_HP,
            wander_radius=3,
            spawn_point_id=2
        )
        
        # Spawn entity in range
        near_x, near_y = 13, 13  # Close by
        near_entity_id = await gsm.spawn_entity_instance(
            entity_name="GOBLIN",
            map_id="samplemap",
            x=near_x,
            y=near_y,
            spawn_x=near_x,
            spawn_y=near_y,
            max_hp=GOBLIN_MAX_HP,
            wander_radius=5,
            spawn_point_id=3
        )
        
        # Wait for state updates and verify visibility
        near_seen = False
        far_seen = False
        
        for _ in range(40):
            try:
                state_update = await test_client.expect_event(
                    MessageType.EVENT_STATE_UPDATE,
                    timeout=0.1
                )
                
                entities = state_update.payload.get("entities", [])
                
                for entity in entities:
                    if entity.get("id") == near_entity_id:
                        near_seen = True
                    if entity.get("id") == far_entity_id:
                        far_seen = True
                
                if near_seen:
                    break
                    
            except ResponseTimeoutError:
                await asyncio.sleep(GAME_TICK_WAIT)
                continue
        
        assert near_seen, "Nearby entity should be visible"
        assert not far_seen, "Far away entity should NOT be visible"
    
    async def test_dying_entity_visible_dead_hidden(self, test_client: WebSocketTestClient):
        """Test that dying entities are visible but dead entities are hidden."""
        from server.src.services.game_state_manager import get_game_state_manager
        
        gsm = get_game_state_manager()
        
        spawn_x, spawn_y = 15, 15
        
        # Spawn entity
        entity_id = await gsm.spawn_entity_instance(
            entity_name="GOBLIN",
            map_id="samplemap",
            x=spawn_x,
            y=spawn_y,
            spawn_x=spawn_x,
            spawn_y=spawn_y,
            max_hp=GOBLIN_MAX_HP,
            wander_radius=5,
            spawn_point_id=4
        )
        
        # Wait for entity to appear
        entity_seen = False
        for _ in range(20):
            try:
                state_update = await test_client.expect_event(
                    MessageType.EVENT_STATE_UPDATE,
                    timeout=0.1
                )
                
                entities = state_update.payload.get("entities", [])
                if any(e.get("id") == entity_id for e in entities):
                    entity_seen = True
                    break
            except ResponseTimeoutError:
                await asyncio.sleep(GAME_TICK_WAIT)
        
        assert entity_seen, "Entity should initially be visible"
        
        # Mark entity as dying (death animation state)
        from server.src.game.game_loop import _global_tick_counter
        death_tick = _global_tick_counter + 10
        await gsm.despawn_entity(entity_id, death_tick=death_tick, respawn_delay_seconds=30)
        
        # Entity should still be visible in "dying" state
        dying_seen = False
        for _ in range(20):
            try:
                state_update = await test_client.expect_event(
                    MessageType.EVENT_STATE_UPDATE,
                    timeout=0.1
                )
                
                entities = state_update.payload.get("entities", [])
                for entity in entities:
                    if entity.get("id") == entity_id:
                        if entity.get("state") == "dying":
                            dying_seen = True
                            assert entity["is_attackable"] is False, "Dying entity should not be attackable"
                            assert entity["current_hp"] == 0, "Dying entity should have 0 HP"
                        break
                
                if dying_seen:
                    break
            except ResponseTimeoutError:
                await asyncio.sleep(GAME_TICK_WAIT)
        
        assert dying_seen, "Entity should be visible in 'dying' state"
        
        # Wait for death animation to complete (10 ticks = 0.5s @ 20 TPS)
        await asyncio.sleep(1.0)
        
        # Entity should now be hidden (state == "dead")
        # Check that entity is no longer in updates
        entity_still_visible = False
        for _ in range(20):
            try:
                state_update = await test_client.expect_event(
                    MessageType.EVENT_STATE_UPDATE,
                    timeout=0.1
                )
                
                entities = state_update.payload.get("entities", [])
                if any(e.get("id") == entity_id for e in entities):
                    entity_still_visible = True
                    break
            except ResponseTimeoutError:
                await asyncio.sleep(GAME_TICK_WAIT)
        
        assert not entity_still_visible, "Entity should be hidden after death animation completes"
    
    async def test_entity_npc_types(self, test_client: WebSocketTestClient):
        """Test different NPC types (guards, merchants, quest givers)."""
        from server.src.services.game_state_manager import get_game_state_manager
        
        gsm = get_game_state_manager()
        
        # Spawn different NPC types near the player
        guard_x, guard_y = 12, 12
        guard_id = await gsm.spawn_entity_instance(
            entity_name="VILLAGE_GUARD",
            map_id="samplemap",
            x=guard_x,
            y=guard_y,
            spawn_x=guard_x,
            spawn_y=guard_y,
            max_hp=GUARD_MAX_HP,
            wander_radius=0,
            spawn_point_id=5
        )
        
        merchant_x, merchant_y = 14, 14
        merchant_id = await gsm.spawn_entity_instance(
            entity_name="SHOPKEEPER_BOB",
            map_id="samplemap",
            x=merchant_x,
            y=merchant_y,
            spawn_x=merchant_x,
            spawn_y=merchant_y,
            max_hp=MERCHANT_MAX_HP,
            wander_radius=0,
            spawn_point_id=6
        )
        
        # Wait for NPCs to appear
        npcs_found = {"guard": False, "merchant": False}
        
        for _ in range(40):
            try:
                state_update = await test_client.expect_event(
                    MessageType.EVENT_STATE_UPDATE,
                    timeout=0.1
                )
                
                entities = state_update.payload.get("entities", [])
                
                for entity in entities:
                    if entity.get("id") == guard_id:
                        npcs_found["guard"] = True
                        assert entity["display_name"] == "Village Guard"
                        assert entity["behavior_type"] == "GUARD"
                        assert entity["is_attackable"] is True
                    
                    if entity.get("id") == merchant_id:
                        npcs_found["merchant"] = True
                        assert entity["display_name"] == "Bob"
                        assert entity["behavior_type"] == "MERCHANT"
                        assert entity["is_attackable"] is False
                
                if all(npcs_found.values()):
                    break
                    
            except ResponseTimeoutError:
                await asyncio.sleep(GAME_TICK_WAIT)
                continue
        
        assert all(npcs_found.values()), f"Not all NPCs found: {npcs_found}"
