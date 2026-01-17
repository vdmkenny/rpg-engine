"""
Service for managing item definitions.
"""

from typing import Optional

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
    async def sync_items_to_db(db: AsyncSession) -> list[Item]:
        """
        Ensure all ItemType entries exist in the items table.

        Uses INSERT ON CONFLICT DO NOTHING for efficient bulk upsert.
        This should be called on server startup.

        Args:
            db: Database session

        Returns:
            List of all Item records in the database
        """
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

        # Return all items
        result = await db.execute(select(Item))
        items = list(result.scalars().all())

        logger.info(
            "Synced items to database",
            extra={"total_items": len(items), "enum_items": len(ItemType)},
        )

        return items

    @staticmethod
    async def get_item_by_name(db: AsyncSession, name: str) -> Optional[Item]:
        """
        Get an item by its internal name.

        Args:
            db: Database session
            name: Internal item name (e.g., "bronze_sword")

        Returns:
            Item if found, None otherwise
        """
        result = await db.execute(select(Item).where(Item.name == name.lower()))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_item_by_id(db: AsyncSession, item_id: int) -> Optional[Item]:
        """
        Get an item by its database ID.

        Args:
            db: Database session
            item_id: Item database ID

        Returns:
            Item if found, None otherwise
        """
        result = await db.execute(select(Item).where(Item.id == item_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_all_items(db: AsyncSession) -> list[Item]:
        """
        Get all items from the database.

        Args:
            db: Database session

        Returns:
            List of all items
        """
        result = await db.execute(select(Item))
        return list(result.scalars().all())

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
