"""
Service for managing item definitions.
"""

from typing import Optional, Dict, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..core.items import ItemType, ItemRarity
from ..core.logging_config import get_logger
from ..models.item import Item
from ..schemas.item import ItemInfo, ItemStats

logger = get_logger(__name__)


class ItemService:
    """Service for managing item definitions."""

    @staticmethod
    async def sync_items_to_db() -> list[Item]:
        """
        Ensure all ItemType entries exist in the items table.
        
        ARCHITECTURAL QUESTION: This method performs bulk reference data setup
        by syncing ItemType enum definitions to the database. This is different
        from regular item access operations.
        
        Options:
        1. Keep this as direct database operation in ItemService (reference data setup)
        2. Move to GSM as a reference data sync method
        3. Create a separate ReferenceDataService for this type of operation
        
        For now, keeping as direct GSM database access since this is setup operation.

        Uses INSERT ON CONFLICT DO NOTHING for efficient bulk upsert.
        This should be called on server startup.

        Returns:
            List of all Item records in the database
        """
        from server.src.services.game_state_manager import get_game_state_manager
        
        gsm = get_game_state_manager()
        
        # This is reference data setup, not regular data access
        # Using GSM's database session for this bulk operation
        async with gsm._db_session() as db:
            # Prepare all item data for bulk insert
            items_data = []
            for item_type in ItemType:
                defn = item_type.value
                items_data.append(
                    {
                        "name": item_type.name.lower(),
                        "display_name": defn.display_name,
                        "description": defn.description,
                        "category": defn.category.value,
                        "rarity": defn.rarity.value,
                        "equipment_slot": defn.equipment_slot.value if defn.equipment_slot else None,
                        "max_stack_size": defn.max_stack_size,
                        "is_two_handed": defn.is_two_handed,
                        "max_durability": defn.max_durability,
                        "is_indestructible": defn.is_indestructible,
                        "is_tradeable": defn.is_tradeable,
                        "required_skill": defn.required_skill.value if defn.required_skill else None,
                        "required_level": defn.required_level,
                        "ammo_type": defn.ammo_type.value if defn.ammo_type else None,
                        "value": defn.value,
                        "attack_bonus": defn.attack_bonus,
                        "strength_bonus": defn.strength_bonus,
                        "ranged_attack_bonus": defn.ranged_attack_bonus,
                        "ranged_strength_bonus": defn.ranged_strength_bonus,
                        "magic_attack_bonus": defn.magic_attack_bonus,
                        "magic_damage_bonus": defn.magic_damage_bonus,
                        "physical_defence_bonus": defn.physical_defence_bonus,
                        "magic_defence_bonus": defn.magic_defence_bonus,
                        "health_bonus": defn.health_bonus,
                        "speed_bonus": defn.speed_bonus,
                        "mining_bonus": defn.mining_bonus,
                        "woodcutting_bonus": defn.woodcutting_bonus,
                        "fishing_bonus": defn.fishing_bonus,
                    }
                )

            # Bulk upsert using PostgreSQL INSERT ON CONFLICT
            if items_data:
                stmt = pg_insert(Item).values(items_data)
                stmt = stmt.on_conflict_do_nothing(index_elements=["name"])
                await db.execute(stmt)
                await db.commit()

            # Return all items and trigger cache reload
            result = await db.execute(select(Item))
            items = list(result.scalars().all())

            # Reload GSM item cache with fresh data
            await gsm.load_item_cache_from_db()

            logger.info(
                "Synced items to database and reloaded GSM cache",
                extra={"total_items": len(items), "enum_items": len(ItemType)},
            )

            return items

    @staticmethod
    async def get_item_by_name(name: str) -> Optional[Item]:
        """
        Get an item by its internal name using GSM cached methods.
        
        Note: This iterates through cached items since GSM doesn't have
        a direct get_item_by_name method. This should be optimized
        if performance becomes an issue.

        Args:
            name: Internal item name (e.g., "bronze_sword")

        Returns:
            Item if found, None otherwise
        """
        from server.src.services.game_state_manager import get_game_state_manager
        
        gsm = get_game_state_manager()
        name_lower = name.lower()
        
        # Check if GSM has item cache loaded
        if hasattr(gsm, '_item_cache') and gsm._item_cache:
            # Search through cached items by name
            for item_id, item_data in gsm._item_cache.items():
                if item_data.get("name") == name_lower:
                    return ItemService._dict_to_item_model(item_data)
        
        # If not found in cache, this might indicate we need a GSM method
        # for get_item_by_name, or that cache isn't loaded
        # For now, return None and let caller handle
        logger.warning(
            "Item not found by name in GSM cache",
            extra={"item_name": name, "cache_size": len(getattr(gsm, '_item_cache', {}))}
        )
        return None

    @staticmethod
    async def get_item_by_id(item_id: int) -> Optional[Item]:
        """
        Get an item by its database ID using GSM cached methods.

        Args:
            item_id: Item database ID

        Returns:
            Item if found, None otherwise
        """
        from server.src.services.game_state_manager import get_game_state_manager
        
        gsm = get_game_state_manager()
        
        # Try cached lookup first (synchronous)
        cached_item = gsm.get_cached_item_meta(item_id)
        if cached_item:
            # Convert GSM dict back to Item model
            return ItemService._dict_to_item_model(cached_item)
        
        # Fall back to GSM's database lookup with caching
        item_data = await gsm.get_item_meta(item_id)
        if item_data:
            return ItemService._dict_to_item_model(item_data)
        
        return None

    @staticmethod
    async def get_all_items() -> list[Item]:
        """
        Get all items using GSM preload and cache methods.
        
        This ensures all items are cached and then returns them as Item models.

        Returns:
            List of all items
        """
        from server.src.services.game_state_manager import get_game_state_manager
        
        gsm = get_game_state_manager()
        
        # Ensure item cache is loaded
        await gsm.preload_item_cache()
        
        # Convert all cached items to Item models
        items = []
        if hasattr(gsm, '_item_cache') and gsm._item_cache:
            for item_data in gsm._item_cache.values():
                item_model = ItemService._dict_to_item_model(item_data)
                items.append(item_model)
        
        return items

    @staticmethod
    def item_to_info(item: Item) -> ItemInfo:
        """
        Convert a database Item to an ItemInfo schema.

        Args:
            item: Database Item model

        Returns:
            ItemInfo schema for client
        """
        # Get rarity color from enum
        try:
            rarity_enum = ItemRarity.from_value(item.rarity)
            rarity_color = rarity_enum.color
        except ValueError:
            rarity_color = "#ffffff"  # Default to white

        stats = ItemStats(
            attack_bonus=item.attack_bonus,
            strength_bonus=item.strength_bonus,
            ranged_attack_bonus=item.ranged_attack_bonus,
            ranged_strength_bonus=item.ranged_strength_bonus,
            magic_attack_bonus=item.magic_attack_bonus,
            magic_damage_bonus=item.magic_damage_bonus,
            physical_defence_bonus=item.physical_defence_bonus,
            magic_defence_bonus=item.magic_defence_bonus,
            health_bonus=item.health_bonus,
            speed_bonus=item.speed_bonus,
            mining_bonus=item.mining_bonus,
            woodcutting_bonus=item.woodcutting_bonus,
            fishing_bonus=item.fishing_bonus,
        )

        return ItemInfo(
            id=item.id,
            name=item.name,
            display_name=item.display_name,
            description=item.description or "",
            category=item.category,
            rarity=item.rarity,
            rarity_color=rarity_color,
            equipment_slot=item.equipment_slot,
            max_stack_size=item.max_stack_size,
            is_two_handed=item.is_two_handed,
            max_durability=item.max_durability,
            is_indestructible=item.is_indestructible,
            required_skill=item.required_skill,
            required_level=item.required_level,
            is_tradeable=item.is_tradeable,
            value=item.value,
            stats=stats,
        )

    @staticmethod
    def _dict_to_item_model(item_data: Dict[str, Any]) -> Item:
        """
        Convert GSM item dictionary back to Item SQLAlchemy model.
        
        This is a temporary conversion method until we decide whether
        ItemService should work with Dict or Item models.

        Args:
            item_data: Item data dictionary from GSM

        Returns:
            Item SQLAlchemy model instance
        """
        # Create Item model instance from dict data
        item = Item()
        
        # Map GSM dict fields to Item model fields
        item.id = item_data.get("id")
        item.name = item_data.get("name")
        item.display_name = item_data.get("display_name")
        item.description = item_data.get("description")
        item.category = item_data.get("category")
        item.rarity = item_data.get("rarity")
        item.equipment_slot = item_data.get("equipment_slot")
        item.max_stack_size = item_data.get("max_stack_size")
        item.is_two_handed = item_data.get("is_two_handed", False)
        item.max_durability = item_data.get("max_durability")
        item.is_indestructible = item_data.get("is_indestructible", False)
        item.is_tradeable = item_data.get("is_tradeable", True)
        item.required_skill = item_data.get("required_skill")
        item.required_level = item_data.get("required_level", 1)
        item.ammo_type = item_data.get("ammo_type")
        item.value = item_data.get("value", 0)
        
        # Stats
        item.attack_bonus = item_data.get("attack_bonus", 0)
        item.strength_bonus = item_data.get("strength_bonus", 0)
        item.ranged_attack_bonus = item_data.get("ranged_attack_bonus", 0)
        item.ranged_strength_bonus = item_data.get("ranged_strength_bonus", 0)
        item.magic_attack_bonus = item_data.get("magic_attack_bonus", 0)
        item.magic_damage_bonus = item_data.get("magic_damage_bonus", 0)
        item.physical_defence_bonus = item_data.get("physical_defence_bonus", 0)
        item.magic_defence_bonus = item_data.get("magic_defence_bonus", 0)
        item.health_bonus = item_data.get("health_bonus", 0)
        item.speed_bonus = item_data.get("speed_bonus", 0)
        item.mining_bonus = item_data.get("mining_bonus", 0)
        item.woodcutting_bonus = item_data.get("woodcutting_bonus", 0)
        item.fishing_bonus = item_data.get("fishing_bonus", 0)
        
        return item

