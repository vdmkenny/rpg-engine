#!/usr/bin/env python3
"""
Script to add items to a player's inventory in production.

Usage:
    docker exec -it docker-server-1 python /app/scripts/add_items_to_player.py <username> <item_name> [quantity]
    
Example:
    docker exec -it docker-server-1 python /app/scripts/add_items_to_player.py test5 "Copper Dagger" 1
    docker exec -it docker-server-1 python /app/scripts/add_items_to_player.py test5 --demo
"""

import asyncio
import sys

# Add the server src to path
sys.path.insert(0, '/app/server/src')
sys.path.insert(0, '/app')

from server.src.core.database import AsyncSessionLocal
from server.src.models.player import Player
from server.src.models.item import Item
from server.src.services.inventory_service import InventoryService
from sqlalchemy import select


async def find_player_by_username(username: str):
    """Get player ID by username."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Player).where(Player.username == username)
        )
        player = result.scalar_one_or_none()
        return player


async def find_item_by_name(item_name: str):
    """Find item by display name or name."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Item).where(
                (Item.display_name.ilike(f"%{item_name}%")) | 
                (Item.name.ilike(f"%{item_name}%"))
            )
        )
        return result.scalar_one_or_none()


async def list_available_items():
    """List all available items in the database."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Item))
        items = result.scalars().all()
        return items


async def add_item_to_player(username: str, item_name: str, quantity: int = 1):
    """Add an item to a player's inventory."""
    # Find player
    player = await find_player_by_username(username)
    if not player:
        print(f"Error: Player '{username}' not found")
        return False
    
    print(f"Found player: {player.username} (ID: {player.id})")
    
    # Find item
    item = await find_item_by_name(item_name)
    if not item:
        print(f"Error: Item '{item_name}' not found")
        return False
    
    print(f"Found item: {item.display_name} (ID: {item.id}, icon: {item.icon_sprite_id})")
    
    # Add item to inventory
    result = await InventoryService.add_item(
        player_id=player.id,
        item_id=item.id,
        quantity=quantity
    )
    
    if result.success:
        print(f"\nSuccess: {result.message}")
        if result.data:
            print(f"Slot: {result.data.get('slot', 'N/A')}")
        return True
    else:
        print(f"\nFailed: {result.message}")
        return False


async def main():
    # Check command line args
    if len(sys.argv) < 2:
        print("Usage:")
        print(f"  {sys.argv[0]} <username>  # Show player's current inventory")
        print(f"  {sys.argv[0]} <username> --list  # List available items")
        print(f"  {sys.argv[0]} <username> <item_name> [quantity]  # Add specific item")
        print(f"  {sys.argv[0]} <username> --demo  # Add demo items")
        print("\nExamples:")
        print(f"  {sys.argv[0]} test5")
        print(f"  {sys.argv[0]} test5 --list")
        print(f"  {sys.argv[0]} test5 'Copper Dagger' 1")
        print(f"  {sys.argv[0]} test5 --demo")
        sys.exit(1)
    
    username = sys.argv[1]
    
    if len(sys.argv) == 2:
        # Just show player info
        player = await find_player_by_username(username)
        if player:
            print(f"Player: {player.username} (ID: {player.id})")
        else:
            print(f"Player '{username}' not found")
    elif sys.argv[2] == '--list':
        # List available items
        print("\nAvailable items in database:")
        print("-" * 60)
        items = await list_available_items()
        for item in items:
            print(f"  {item.display_name:30} (icon: {item.icon_sprite_id or 'N/A'})")
        print(f"\nTotal: {len(items)} items")
    elif sys.argv[2] == '--demo':
        # Add demo items for testing icons
        print(f"\nAdding demo items to {username}...\n")
        
        # Get available items first
        items = await list_available_items()
        item_names = {item.display_name.lower(): item for item in items}
        
        # Items to add (with variations to test different icon packs)
        demo_items = [
            ("Copper Dagger", 1),
            ("Bronze Shortsword", 1),
            ("Iron Longsword", 1),
            ("Copper Helm", 1),
            ("Copper Chainbody", 1),
            ("Bread", 10),
            ("Leather", 3),
        ]
        
        for item_name, qty in demo_items:
            # Try to find the item (case insensitive)
            found = False
            for db_item in items:
                if item_name.lower() in db_item.display_name.lower():
                    print(f"Adding {db_item.display_name} x{qty}...")
                    success = await add_item_to_player(username, db_item.display_name, qty)
                    if success:
                        found = True
                        break
            
            if not found:
                print(f"Warning: Could not find item matching '{item_name}'")
    else:
        # Add specific item
        item_name = sys.argv[2]
        quantity = int(sys.argv[3]) if len(sys.argv) > 3 else 1
        await add_item_to_player(username, item_name, quantity)


if __name__ == "__main__":
    asyncio.run(main())
