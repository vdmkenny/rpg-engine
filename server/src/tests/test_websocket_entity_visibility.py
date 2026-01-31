"""
Integration tests for entity visibility in WebSocket game loop.

These tests verify that entities are properly broadcast to players
via the WebSocket game loop.
"""

import os
import pytest
import asyncio
from server.src.tests.websocket_test_utils import (
    create_test_player, 
    WebSocketTestClient,
)
from common.src.protocol import MessageType


# Skip if RUN_INTEGRATION_TESTS is not set
pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS") != "1",
    reason="Integration tests require RUN_INTEGRATION_TESTS=1"
)


@pytest.mark.asyncio
class TestEntityVisibilityIntegration:
    """Integration tests for entity visibility in game loop."""
    
    async def test_entity_appears_in_state_update(self, test_client):
        """Test that a spawned entity appears in game state updates."""
        from server.src.services.game_state_manager import get_game_state_manager
        
        # Create player and connect
        player_data = await create_test_player(
            test_client, 
            username="entity_test_player",
            password="testpass123"
        )
        
        async with test_client.websocket_connect(
            "/ws",
            headers={"Authorization": f"Bearer {player_data['access_token']}"}
        ) as websocket:
            async with WebSocketTestClient(websocket, default_timeout=5.0) as ws_client:
                # Wait for initial state update
                initial_state = await ws_client.wait_for_event(
                    MessageType.EVENT_STATE_UPDATE,
                    timeout=3.0
                )
                
                # Spawn an entity near the player (at position 30, 30, player spawns at 25, 25)
                gsm = get_game_state_manager()
                instance_id = await gsm.spawn_entity_instance(
                    map_id="samplemap",
                    entity_name="GOBLIN",
                    spawn_x=30,
                    spawn_y=30,
                    wander_radius=5,
                    spawn_point_id=1
                )
                
                assert instance_id is not None, "Failed to spawn entity"
                
                # Wait for next game loop tick (should include the entity)
                # Game loop runs at 20 TPS = every 0.05s, wait up to 2 seconds
                entity_seen = False
                for _ in range(40):  # Try for 2 seconds (40 * 0.05s)
                    try:
                        state_update = await ws_client.wait_for_event(
                            MessageType.EVENT_STATE_UPDATE,
                            timeout=0.1
                        )
                        
                        entities = state_update.get("entities", [])
                        
                        # Check if our entity is in the update
                        for entity in entities:
                            if (entity.get("type") == "entity" and 
                                entity.get("id") == instance_id):
                                entity_seen = True
                                
                                # Verify entity data
                                assert entity["entity_name"] == "GOBLIN"
                                assert entity["display_name"] == "Goblin"
                                assert entity["behavior_type"] == "AGGRESSIVE"
                                assert entity["x"] == 30
                                assert entity["y"] == 30
                                assert entity["max_hp"] == 10
                                assert entity["current_hp"] == 10
                                assert entity["state"] == "idle"
                                assert entity["is_attackable"] is True
                                assert "sprite_info" in entity
                                
                                break
                        
                        if entity_seen:
                            break
                            
                    except asyncio.TimeoutError:
                        await asyncio.sleep(0.05)
                        continue
                
                assert entity_seen, f"Entity {instance_id} did not appear in state updates"
    
    async def test_entity_visibility_range(self, test_client):
        """Test that entities only appear when within visibility range."""
        from server.src.services.game_state_manager import get_game_state_manager
        
        # Create player and connect
        player_data = await create_test_player(
            test_client,
            username="range_test_player",
            password="testpass123"
        )
        
        async with test_client.websocket_connect(
            "/ws",
            headers={"Authorization": f"Bearer {player_data['access_token']}"}
        ) as websocket:
            async with WebSocketTestClient(websocket, default_timeout=5.0) as ws_client:
                # Wait for initial state
                await ws_client.wait_for_event(MessageType.EVENT_STATE_UPDATE, timeout=3.0)
                
                # Spawn entity out of range (player at 25,25, visibility = 32 tiles)
                gsm = get_game_state_manager()
                far_entity_id = await gsm.spawn_entity_instance(
                    map_id="samplemap",
                    entity_name="GIANT_RAT",
                    spawn_x=100,  # Far away
                    spawn_y=100,
                    wander_radius=3,
                    spawn_point_id=2
                )
                
                # Spawn entity in range
                near_entity_id = await gsm.spawn_entity_instance(
                    map_id="samplemap",
                    entity_name="GOBLIN",
                    spawn_x=28,  # Close by
                    spawn_y=28,
                    wander_radius=5,
                    spawn_point_id=3
                )
                
                # Wait for state updates and verify visibility
                near_seen = False
                far_seen = False
                
                for _ in range(40):
                    try:
                        state_update = await ws_client.wait_for_event(
                            MessageType.EVENT_STATE_UPDATE,
                            timeout=0.1
                        )
                        
                        entities = state_update.get("entities", [])
                        
                        for entity in entities:
                            if entity.get("id") == near_entity_id:
                                near_seen = True
                            if entity.get("id") == far_entity_id:
                                far_seen = True
                        
                        if near_seen:
                            break
                            
                    except asyncio.TimeoutError:
                        await asyncio.sleep(0.05)
                        continue
                
                assert near_seen, "Nearby entity should be visible"
                assert not far_seen, "Far away entity should NOT be visible"
    
    async def test_dying_entity_visible_dead_hidden(self, test_client):
        """Test that dying entities are visible but dead entities are hidden."""
        from server.src.services.game_state_manager import get_game_state_manager
        
        # Create player and connect
        player_data = await create_test_player(
            test_client,
            username="death_test_player",
            password="testpass123"
        )
        
        async with test_client.websocket_connect(
            "/ws",
            headers={"Authorization": f"Bearer {player_data['access_token']}"}
        ) as websocket:
            async with WebSocketTestClient(websocket, default_timeout=5.0) as ws_client:
                # Wait for initial state
                await ws_client.wait_for_event(MessageType.EVENT_STATE_UPDATE, timeout=3.0)
                
                # Spawn entity
                gsm = get_game_state_manager()
                entity_id = await gsm.spawn_entity_instance(
                    map_id="samplemap",
                    entity_name="GOBLIN",
                    spawn_x=30,
                    spawn_y=30,
                    wander_radius=5,
                    spawn_point_id=4
                )
                
                # Wait for entity to appear
                entity_seen = False
                for _ in range(20):
                    try:
                        state_update = await ws_client.wait_for_event(
                            MessageType.EVENT_STATE_UPDATE,
                            timeout=0.1
                        )
                        
                        entities = state_update.get("entities", [])
                        if any(e.get("id") == entity_id for e in entities):
                            entity_seen = True
                            break
                    except asyncio.TimeoutError:
                        await asyncio.sleep(0.05)
                
                assert entity_seen, "Entity should initially be visible"
                
                # Mark entity as dying (death animation state)
                from server.src.game.game_loop import _global_tick_counter
                death_tick = _global_tick_counter + 10
                await gsm.despawn_entity(entity_id, death_tick=death_tick, respawn_delay_seconds=30)
                
                # Entity should still be visible in "dying" state
                dying_seen = False
                for _ in range(20):
                    try:
                        state_update = await ws_client.wait_for_event(
                            MessageType.EVENT_STATE_UPDATE,
                            timeout=0.1
                        )
                        
                        entities = state_update.get("entities", [])
                        for entity in entities:
                            if entity.get("id") == entity_id:
                                if entity.get("state") == "dying":
                                    dying_seen = True
                                    assert entity["is_attackable"] is False, "Dying entity should not be attackable"
                                    assert entity["current_hp"] == 0, "Dying entity should have 0 HP"
                                break
                        
                        if dying_seen:
                            break
                    except asyncio.TimeoutError:
                        await asyncio.sleep(0.05)
                
                assert dying_seen, "Entity should be visible in 'dying' state"
                
                # Wait for death animation to complete (10 ticks = 0.5s @ 20 TPS)
                await asyncio.sleep(1.0)
                
                # Entity should now be hidden (state == "dead")
                # Check that entity is no longer in updates
                entity_still_visible = False
                for _ in range(20):
                    try:
                        state_update = await ws_client.wait_for_event(
                            MessageType.EVENT_STATE_UPDATE,
                            timeout=0.1
                        )
                        
                        entities = state_update.get("entities", [])
                        if any(e.get("id") == entity_id for e in entities):
                            entity_still_visible = True
                            break
                    except asyncio.TimeoutError:
                        await asyncio.sleep(0.05)
                
                assert not entity_still_visible, "Entity should be hidden after death animation completes"
    
    async def test_entity_npc_types(self, test_client):
        """Test different NPC types (guards, merchants, quest givers)."""
        from server.src.services.game_state_manager import get_game_state_manager
        
        # Create player and connect
        player_data = await create_test_player(
            test_client,
            username="npc_test_player",
            password="testpass123"
        )
        
        async with test_client.websocket_connect(
            "/ws",
            headers={"Authorization": f"Bearer {player_data['access_token']}"}
        ) as websocket:
            async with WebSocketTestClient(websocket, default_timeout=5.0) as ws_client:
                # Wait for initial state
                await ws_client.wait_for_event(MessageType.EVENT_STATE_UPDATE, timeout=3.0)
                
                # Spawn different NPC types
                gsm = get_game_state_manager()
                
                guard_id = await gsm.spawn_entity_instance(
                    map_id="samplemap",
                    entity_name="VILLAGE_GUARD",
                    spawn_x=26,
                    spawn_y=26,
                    wander_radius=0,
                    spawn_point_id=5
                )
                
                merchant_id = await gsm.spawn_entity_instance(
                    map_id="samplemap",
                    entity_name="SHOPKEEPER_BOB",
                    spawn_x=28,
                    spawn_y=28,
                    wander_radius=0,
                    spawn_point_id=6
                )
                
                # Wait for NPCs to appear
                npcs_found = {"guard": False, "merchant": False}
                
                for _ in range(40):
                    try:
                        state_update = await ws_client.wait_for_event(
                            MessageType.EVENT_STATE_UPDATE,
                            timeout=0.1
                        )
                        
                        entities = state_update.get("entities", [])
                        
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
                            
                    except asyncio.TimeoutError:
                        await asyncio.sleep(0.05)
                        continue
                
                assert all(npcs_found.values()), f"Not all NPCs found: {npcs_found}"
