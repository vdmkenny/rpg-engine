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
    
    async def _spawn_test_entity(self, entity_manager, entity_name, map_id, x, y, max_hp):
        """Helper to spawn an entity by name."""
        from server.src.core.monsters import MonsterID
        from server.src.core.humanoids import HumanoidID
        
        # Try monsters first, then humanoids
        entity_enum = getattr(MonsterID, entity_name, None)
        if not entity_enum:
            entity_enum = getattr(HumanoidID, entity_name, None)
        
        if not entity_enum:
            raise ValueError(f"Unknown entity: {entity_name}")
        
        entity_id = entity_enum.value.value if hasattr(entity_enum.value, 'value') else entity_enum.value
        
        return await entity_manager.spawn_entity_instance(
            entity_id=entity_id,
            map_id=map_id,
            x=x,
            y=y,
            current_hp=max_hp,
            max_hp=max_hp,
            state="idle",
        )
    
    async def test_entity_appears_in_state_update(self, test_client: WebSocketTestClient):
        """Test that a spawned entity appears in game state updates."""
        from server.src.services.game_state import get_entity_manager
        
        entity_manager = get_entity_manager()
        
        spawn_x, spawn_y = 15, 15
        
        instance_id = await self._spawn_test_entity(
            entity_manager, "GOBLIN", "samplemap", spawn_x, spawn_y, GOBLIN_MAX_HP
        )
        
        assert instance_id is not None, "Failed to spawn entity"
        
        entity_seen = False
        for _ in range(40):
            try:
                state_update = await test_client.expect_event(
                    MessageType.EVENT_STATE_UPDATE,
                    timeout=0.1
                )
                
                entities = state_update.payload.get("entities", [])
                
                for entity in entities:
                    if (entity.get("type") == "entity" and 
                        entity.get("id") == instance_id):
                        entity_seen = True
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
        from server.src.services.game_state import get_entity_manager
        
        entity_manager = get_entity_manager()
        
        far_x, far_y = 100, 100
        far_entity_id = await self._spawn_test_entity(
            entity_manager, "GIANT_RAT", "samplemap", far_x, far_y, GIANT_RAT_MAX_HP
        )
        
        near_x, near_y = 13, 13
        near_entity_id = await self._spawn_test_entity(
            entity_manager, "GOBLIN", "samplemap", near_x, near_y, GOBLIN_MAX_HP
        )
        
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
        from server.src.services.game_state import get_entity_manager
        
        entity_manager = get_entity_manager()
        
        spawn_x, spawn_y = 15, 15
        
        entity_id = await self._spawn_test_entity(
            entity_manager, "GOBLIN", "samplemap", spawn_x, spawn_y, GOBLIN_MAX_HP
        )
        
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
        
        # Mark entity as dying
        key = f"entity_instance:{entity_id}"
        data = await entity_manager._get_from_valkey(key)
        if data:
            data["state"] = "dying"
            data["current_hp"] = 0
            await entity_manager._cache_in_valkey(key, data, 1800)
        
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
                            assert entity["current_hp"] == 0
                        break
                
                if dying_seen:
                    break
            except ResponseTimeoutError:
                await asyncio.sleep(GAME_TICK_WAIT)
        
        assert dying_seen, "Entity should be visible in 'dying' state"
        
        await asyncio.sleep(1.0)
        
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
        from server.src.services.game_state import get_entity_manager
        
        entity_manager = get_entity_manager()
        
        guard_x, guard_y = 12, 12
        guard_id = await self._spawn_test_entity(
            entity_manager, "VILLAGE_GUARD", "samplemap", guard_x, guard_y, GUARD_MAX_HP
        )
        
        merchant_x, merchant_y = 14, 14
        merchant_id = await self._spawn_test_entity(
            entity_manager, "SHOPKEEPER", "samplemap", merchant_x, merchant_y, MERCHANT_MAX_HP
        )
        
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
                    if entity.get("id") == merchant_id:
                        npcs_found["merchant"] = True
                
                if all(npcs_found.values()):
                    break
                    
            except ResponseTimeoutError:
                await asyncio.sleep(GAME_TICK_WAIT)
                continue
        
        assert all(npcs_found.values()), f"Not all NPCs found: {npcs_found}"
