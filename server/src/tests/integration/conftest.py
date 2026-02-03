"""
Test fixtures for integration tests.

Fixtures that require database and manager access.
"""

import pytest
import pytest_asyncio


@pytest.fixture
def create_test_player_with_skills(create_test_player, skills_synced):
    """Factory fixture to create player with skills pre-granted."""
    async def _create(username, password):
        from server.src.services.skill_service import SkillService
        from server.src.services.game_state import get_skills_manager
        
        player = await create_test_player(username, password)
        await SkillService.grant_all_skills_to_player(player["id"])
        return player
    return _create


@pytest.fixture
def create_test_player_with_inventory(create_test_player):
    """Factory fixture to create player with initial inventory."""
    async def _create(username, password, items=None):
        from server.src.services.inventory_service import InventoryService
        
        player = await create_test_player(username, password)
        
        if items:
            for item_id, quantity in items:
                await InventoryService.add_item(player["id"], item_id, quantity)
        
        return player
    return _create


@pytest.fixture
def create_test_player_with_equipment(create_test_player):
    """Factory fixture to create player with equipment."""
    async def _create(username, password, equipment=None):
        from server.src.services.equipment_service import EquipmentService
        from server.src.services.inventory_service import InventoryService
        
        player = await create_test_player(username, password)
        
        if equipment:
            # Add items to inventory first
            for slot, item_id in equipment.items():
                await InventoryService.add_item(player["id"], item_id, 1)
                # Get free slot
                inv = await InventoryService.get_inventory(player["id"])
                slot_num = inv[-1].slot if inv else 0
                # Equip
                await EquipmentService.equip_from_inventory(player["id"], slot_num)
        
        return player
    return _create
