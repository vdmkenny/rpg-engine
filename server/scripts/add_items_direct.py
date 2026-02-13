#!/usr/bin/env python3
"""
Direct database script to add items to a player's inventory in production.
This bypasses the GameStateManager and inserts directly into the database.

Usage:
    docker exec -it rpg_server python /app/server/scripts/add_items_direct.py <username>
"""

import asyncio
import sys
from datetime import datetime

sys.path.insert(0, '/app/server/src')
sys.path.insert(0, '/app')

from sqlalchemy import select, text
from server.src.core.database import AsyncSessionLocal
from server.src.models.player import Player
from server.src.models.item import Item


async def get_player_id(username: str) -> int:
    """Get player ID by username."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Player.id).where(Player.username == username)
        )
        player_id = result.scalar_one_or_none()
        return player_id


async def get_item_id(item_name: str) -> int:
    """Get item ID by name (partial match)."""
    async with AsyncSessionLocal() as session:
        # Try exact match first
        result = await session.execute(
            select(Item).where(Item.display_name == item_name)
        )
        item = result.scalar_one_or_none()
        if item:
            return item.id
        
        # Try partial match
        result = await session.execute(
            select(Item).where(
                (Item.display_name.ilike(f"%{item_name}%")) | 
                (Item.name.ilike(f"%{item_name}%"))
            ).limit(1)
        )
        item = result.scalar_one_or_none()
        return item.id if item else None


async def add_item_to_inventory(player_id: int, item_id: int, slot: int, quantity: int = 1):
    """Add item directly to player's inventory in database."""
    async with AsyncSessionLocal() as session:
        # Check if slot is already occupied
        check_result = await session.execute(
            text("SELECT COUNT(*) FROM player_inventory WHERE player_id = :player_id AND slot = :slot"),
            {"player_id": player_id, "slot": slot}
        )
        count = check_result.scalar()
        
        if count > 0:
            print(f"  Slot {slot} already occupied, skipping...")
            return False
        
        # Insert item into inventory
        await session.execute(
            text("""
                INSERT INTO player_inventory (player_id, item_id, slot, quantity, current_durability)
                VALUES (:player_id, :item_id, :slot, :quantity, 100)
            """),
            {
                "player_id": player_id,
                "item_id": item_id,
                "slot": slot,
                "quantity": quantity
            }
        )
        await session.commit()
        return True


async def list_items_with_icons():
    """List items that have icon_sprite_id set."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Item).where(Item.icon_sprite_id.isnot(None))
        )
        items = result.scalars().all()
        return items


async def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print(f"  {sys.argv[0]} <username>  # Add demo items to player's inventory")
        print(f"  {sys.argv[0]} --list  # List items with icons")
        sys.exit(1)
    
    if sys.argv[1] == '--list':
        items = await list_items_with_icons()
        print("\nItems with icons:")
        print("-" * 60)
        for item in items:
            print(f"  {item.display_name:30} (icon: {item.icon_sprite_id})")
        print(f"\nTotal: {len(items)} items")
        return
    
    username = sys.argv[1]
    
    # Get player ID
    player_id = await get_player_id(username)
    if not player_id:
        print(f"Error: Player '{username}' not found")
        return
    
    print(f"Adding items to {username} (ID: {player_id})...\n")
    
    # Demo items to add with various icon types
    # First 11 slots (0-10) already filled with previous run
    demo_items = [
        ("Leather", 3, 11),                  # Slot 11: material
        ("Leather Body", 1, 12),             # Slot 12: armor
        ("Leather Chaps", 1, 13),            # Slot 13: armor
        ("Shortbow", 1, 14),                 # Slot 14: weapon
        ("Bronze Arrows", 50, 15),           # Slot 15: ammo (stack)
        ("Iron Pickaxe", 1, 16),             # Slot 16: tool
        ("Copper Shield", 1, 17),            # Slot 17: shield
        ("Bronze Shield", 1, 18),            # Slot 18: shield
        ("Leather Boots", 1, 19),            # Slot 19: armor
        ("Leather Gloves", 1, 20),           # Slot 20: armor
    ]
    
    items_added = 0
    for item_name, qty, slot in demo_items:
        item_id = await get_item_id(item_name)
        if item_id:
            success = await add_item_to_inventory(player_id, item_id, slot, qty)
            if success:
                print(f"  Added {item_name} x{qty} to slot {slot}")
                items_added += 1
            else:
                print(f"  Could not add {item_name} to slot {slot}")
        else:
            print(f"  Item not found: {item_name}")
    
    print(f"\nTotal items added: {items_added}")


if __name__ == "__main__":
    asyncio.run(main())
