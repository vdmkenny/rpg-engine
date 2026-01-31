"""
Tests for Entity database synchronization.
"""

import pytest
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from server.src.models.entity import Entity
from server.src.services.entity_service import EntityService
from server.src.services.game_state_manager import get_game_state_manager

@pytest.mark.asyncio
async def test_sync_entities(session: AsyncSession, gsm):
    """
    Test that entities defined in EntityID enum are correctly synced to the database.
    """
    # 1. Clear existing entities to ensure clean state
    await session.execute(delete(Entity))
    await session.commit()
    
    # Verify empty
    result = await session.execute(select(Entity))
    assert len(result.scalars().all()) == 0
    
    # 2. Trigger sync via Service -> GSM
    # Note: gsm fixture initializes the global GSM singleton, which is what EntityService uses
    await EntityService.sync_entities_to_db()
    
    # 3. Verify entities were created
    # We need to check specific entities we know exist in EntityID
    # GOBLIN, VILLAGE_GUARD, SHOPKEEPER_BOB
    
    result = await session.execute(select(Entity).where(Entity.name == "GOBLIN"))
    goblin = result.scalar_one_or_none()
    
    assert goblin is not None
    assert goblin.display_name == "Goblin"
    assert goblin.behavior == "aggressive"
    assert goblin.level == 2
    assert goblin.skills.get("attack") == 5
    
    result = await session.execute(select(Entity).where(Entity.name == "SHOPKEEPER_BOB"))
    bob = result.scalar_one_or_none()
    
    assert bob is not None
    assert bob.behavior == "merchant"
    assert bob.shop_id == "general_store"
    assert "Welcome to Bob's General Store!" in bob.dialogue

@pytest.mark.asyncio
async def test_sync_updates_existing(session: AsyncSession, gsm):
    """
    Test that sync updates existing records rather than failing or duplicating.
    """
    # 0. Clear existing entities to ensure clean state
    await session.execute(delete(Entity))
    await session.commit()
    
    # 1. Manually insert a "stale" version of GOBLIN
    stale_goblin = Entity(
        name="GOBLIN",
        display_name="Old Goblin",
        behavior="passive", # Wrong behavior
        level=1
    )
    session.add(stale_goblin)
    await session.commit()
    
    # 2. Run sync
    await EntityService.sync_entities_to_db()
    
    # 3. Expire the session cache to force re-fetch from database
    await session.rollback()  # Refresh session to see changes from GSM's session
    session.expire_all()  # Force all cached objects to be refetched
    
    # 4. Verify it was updated to match code definition
    result = await session.execute(select(Entity).where(Entity.name == "GOBLIN"))
    goblin = result.scalar_one()
    
    assert goblin.display_name == "Goblin" # Updated
    assert goblin.behavior == "aggressive" # Updated
    assert goblin.level == 2 # Updated
