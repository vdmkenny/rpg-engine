"""
Reference data management - permanent caches for static game data.

Handles item definitions, skill definitions, and entity definitions.
Loaded once at startup and cached permanently in Valkey (no TTL).
"""

import traceback
from typing import Any, Dict, List, Optional

from glide import GlideClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.postgresql import insert as pg_insert

from server.src.core.config import settings
from server.src.core.logging_config import get_logger

from .base_manager import BaseManager

logger = get_logger(__name__)

# Reference data keys (no TTL - permanent cache)
ITEM_CACHE_KEY = "ref:items"
SKILL_CACHE_KEY = "ref:skills"
ENTITY_DEFS_KEY = "ref:entity_defs"


class ReferenceDataManager(BaseManager):
    """Manages permanent reference data caches (items, skills, entity definitions)."""

    def __init__(
        self,
        valkey_client: Optional[GlideClient] = None,
        session_factory: Optional[sessionmaker] = None,
    ):
        super().__init__(valkey_client, session_factory)
        # In-memory cache for fast synchronous access
        self._item_cache: Dict[int, Dict[str, Any]] = {}
        self._item_cache_by_name: Dict[str, Dict[str, Any]] = {}

    # =========================================================================
    # Item Reference Data
    # =========================================================================

    async def load_item_cache_from_db(self) -> int:
        """Load all item definitions from database into cache."""
        if not self._session_factory:
            logger.warning("No database connection for loading items")
            return 0

        try:
            from server.src.models.item import Item

            async with self._db_session() as db:
                result = await db.execute(select(Item))
                items = result.scalars().all()

                self._item_cache = {}
                self._item_cache_by_name = {}
                for item in items:
                    item_dict = self._item_to_dict(item)
                    self._item_cache[item.id] = item_dict
                    self._item_cache_by_name[item.name.lower()] = item_dict

                # Also cache in Valkey for other services
                if self._valkey and settings.USE_VALKEY:
                    items_dict = {str(k): v for k, v in self._item_cache.items()}
                    await self._cache_in_valkey(ITEM_CACHE_KEY, items_dict, 0)  # No TTL

                logger.info(f"Loaded {len(self._item_cache)} items into cache")
                return len(self._item_cache)

        except Exception as e:
            logger.error(
                "Failed to load item cache",
                extra={"error": str(e), "traceback": traceback.format_exc()},
            )
            raise

    def _item_to_dict(self, item) -> Dict[str, Any]:
        """Convert Item model to dictionary."""
        return {
            "id": item.id,
            "name": item.name,
            "display_name": item.display_name,
            "description": item.description,
            "category": item.category,
            "rarity": item.rarity,
            "value": item.value,
            "max_durability": item.max_durability,
            "max_stack_size": item.max_stack_size,
            "equipable": item.equipment_slot is not None,
            "equipment_slot": item.equipment_slot,
            "attack_bonus": item.attack_bonus,
            "strength_bonus": item.strength_bonus,
            "physical_defence_bonus": item.physical_defence_bonus,
            "ranged_attack_bonus": item.ranged_attack_bonus,
            "ranged_strength_bonus": item.ranged_strength_bonus,
            "magic_attack_bonus": item.magic_attack_bonus,
            "magic_defence_bonus": item.magic_defence_bonus,
            "health_bonus": item.health_bonus,
            "speed_bonus": item.speed_bonus,
            "required_skill": item.required_skill,
            "required_level": item.required_level,
            "is_two_handed": item.is_two_handed,
            "ammo_type": item.ammo_type,
            "is_indestructible": item.is_indestructible,
            "is_tradeable": item.is_tradeable,
        }

    def get_cached_item_meta(self, item_id: int) -> Optional[Dict[str, Any]]:
        """Get item metadata by ID (synchronous, from memory cache)."""
        return self._item_cache.get(item_id)

    def get_all_cached_items(self) -> Dict[int, Dict[str, Any]]:
        """Get all cached item metadata."""
        return dict(self._item_cache)

    def get_cached_item_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get item metadata by name (case-insensitive, from memory cache)."""
        return self._item_cache_by_name.get(name.lower())

    async def get_item_from_valkey(self, item_id: int) -> Optional[Dict[str, Any]]:
        """Get item from Valkey cache (for cross-service access)."""
        if not self._valkey or not settings.USE_VALKEY:
            return self._item_cache.get(item_id)

        items_data = await self._get_from_valkey(ITEM_CACHE_KEY)
        if items_data:
            item_key = str(item_id)
            if item_key in items_data:
                return items_data[item_key]
        return None

    # =========================================================================
    # Skill Reference Data
    # =========================================================================

    async def load_skill_cache_from_db(self) -> int:
        """Load all skill definitions from database into cache."""
        if not self._session_factory:
            return 0

        from server.src.models.skill import Skill

        async with self._db_session() as db:
            result = await db.execute(select(Skill))
            skills = result.scalars().all()

            skills_data = {}
            for skill in skills:
                skills_data[skill.name.lower()] = {
                    "id": skill.id,
                    "name": skill.name,
                }

            if self._valkey and settings.USE_VALKEY:
                await self._cache_in_valkey(SKILL_CACHE_KEY, skills_data, 0)  # No TTL

            logger.info(f"Loaded {len(skills_data)} skills into cache")
            return len(skills_data)

    async def get_skill_id_by_name(self, skill_name: str) -> Optional[int]:
        """Get skill ID by name."""
        if not self._valkey or not settings.USE_VALKEY:
            return None

        skills_data = await self._get_from_valkey(SKILL_CACHE_KEY)
        if skills_data:
            skill_data = skills_data.get(skill_name.lower())
            if skill_data:
                return self._decode_from_valkey(skill_data.get("id"), int)
        return None

    async def get_all_skill_ids(self) -> Dict[str, int]:
        """Get mapping of skill names to IDs."""
        if not self._valkey or not settings.USE_VALKEY:
            return {}

        skills_data = await self._get_from_valkey(SKILL_CACHE_KEY)
        if skills_data:
            return {
                name: self._decode_from_valkey(data.get("id"), int)
                for name, data in skills_data.items()
            }
        return {}

    # =========================================================================
    # Entity Definition Reference Data
    # =========================================================================

    async def sync_entities_to_database(self) -> int:
        """Sync HumanoidID and MonsterID enum definitions to database."""
        from server.src.core.humanoids import HumanoidID
        from server.src.core.monsters import MonsterID
        from server.src.services.entity_service import EntityService
        from server.src.models.entity import Entity

        if not self._session_factory:
            logger.warning("No database connection for entity sync")
            return 0

        async with self._db_session() as db:
            count = 0

            # Sync humanoids
            for humanoid_enum in HumanoidID:
                entity_data = EntityService.entity_def_to_dict(
                    humanoid_enum.name, humanoid_enum.value
                )

                stmt = pg_insert(Entity).values(**entity_data)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["name"], set_=entity_data
                )
                await db.execute(stmt)
                count += 1

            # Sync monsters
            for monster_enum in MonsterID:
                entity_data = EntityService.entity_def_to_dict(
                    monster_enum.name, monster_enum.value
                )

                stmt = pg_insert(Entity).values(**entity_data)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["name"], set_=entity_data
                )
                await db.execute(stmt)
                count += 1

            await self._commit_if_not_test_session(db)

            # Cache in Valkey
            if self._valkey and settings.USE_VALKEY:
                await self._cache_entity_definitions()

            logger.info(f"Synced {count} entity definitions to database")
            return count

    async def sync_items_to_database(self) -> int:
        """Sync ItemType enum definitions to database."""
        from server.src.core.items import ItemType
        from server.src.models.item import Item

        if not self._session_factory:
            logger.warning("No database connection for item sync")
            return 0

        async with self._db_session() as db:
            count = 0

            for item_enum in ItemType:
                item_def = item_enum.value

                # Build insert values directly from ItemDefinition
                stmt = pg_insert(Item).values(
                    name=item_enum.name.lower(),
                    display_name=item_def.display_name,
                    description=item_def.description,
                    category=item_def.category.value,
                    rarity=item_def.rarity.value,
                    equipment_slot=item_def.equipment_slot.value if item_def.equipment_slot else None,
                    max_stack_size=item_def.max_stack_size,
                    is_two_handed=item_def.is_two_handed,
                    max_durability=item_def.max_durability,
                    is_indestructible=item_def.is_indestructible,
                    is_tradeable=item_def.is_tradeable,
                    required_skill=item_def.required_skill.value if item_def.required_skill else None,
                    required_level=item_def.required_level,
                    ammo_type=item_def.ammo_type.value if item_def.ammo_type else None,
                    value=item_def.value,
                    attack_bonus=item_def.attack_bonus,
                    strength_bonus=item_def.strength_bonus,
                    ranged_attack_bonus=item_def.ranged_attack_bonus,
                    ranged_strength_bonus=item_def.ranged_strength_bonus,
                    magic_attack_bonus=item_def.magic_attack_bonus,
                    magic_damage_bonus=item_def.magic_damage_bonus,
                    physical_defence_bonus=item_def.physical_defence_bonus,
                    magic_defence_bonus=item_def.magic_defence_bonus,
                    health_bonus=item_def.health_bonus,
                    speed_bonus=item_def.speed_bonus,
                    mining_bonus=item_def.mining_bonus,
                    woodcutting_bonus=item_def.woodcutting_bonus,
                    fishing_bonus=item_def.fishing_bonus,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["name"],
                    set_=dict(
                        display_name=item_def.display_name,
                        description=item_def.description,
                        category=item_def.category.value,
                        rarity=item_def.rarity.value,
                        equipment_slot=item_def.equipment_slot.value if item_def.equipment_slot else None,
                        max_stack_size=item_def.max_stack_size,
                        is_two_handed=item_def.is_two_handed,
                        max_durability=item_def.max_durability,
                        is_indestructible=item_def.is_indestructible,
                        is_tradeable=item_def.is_tradeable,
                        required_skill=item_def.required_skill.value if item_def.required_skill else None,
                        required_level=item_def.required_level,
                        ammo_type=item_def.ammo_type.value if item_def.ammo_type else None,
                        value=item_def.value,
                        attack_bonus=item_def.attack_bonus,
                        strength_bonus=item_def.strength_bonus,
                        ranged_attack_bonus=item_def.ranged_attack_bonus,
                        ranged_strength_bonus=item_def.ranged_strength_bonus,
                        magic_attack_bonus=item_def.magic_attack_bonus,
                        magic_damage_bonus=item_def.magic_damage_bonus,
                        physical_defence_bonus=item_def.physical_defence_bonus,
                        magic_defence_bonus=item_def.magic_defence_bonus,
                        health_bonus=item_def.health_bonus,
                        speed_bonus=item_def.speed_bonus,
                        mining_bonus=item_def.mining_bonus,
                        woodcutting_bonus=item_def.woodcutting_bonus,
                        fishing_bonus=item_def.fishing_bonus,
                    )
                )
                await db.execute(stmt)
                count += 1

            await self._commit_if_not_test_session(db)

            # Reload cache after sync
            await self.load_item_cache_from_db()

            logger.info(f"Synced {count} item definitions to database")
            return count

    async def _cache_entity_definitions(self) -> None:
        """Cache entity definitions in Valkey."""
        if not self._session_factory:
            return

        from server.src.models.entity import Entity

        async with self._db_session() as db:
            result = await db.execute(select(Entity))
            entities = result.scalars().all()

            entity_data = {}
            for entity in entities:
                entity_data[entity.name] = {
                    "id": entity.id,
                    "name": entity.name,
                    "entity_type": entity.entity_type,
                    "display_name": entity.display_name,
                    "behavior": entity.behavior,
                    "level": entity.level,
                    "max_hp": entity.max_hp,
                    "skills": entity.skills or {},
                    "aggro_radius": entity.aggro_radius,
                    "disengage_radius": entity.disengage_radius,
                }

            await self._cache_in_valkey(ENTITY_DEFS_KEY, entity_data, 0)

    async def get_entity_definition(self, entity_name: str) -> Optional[Dict[str, Any]]:
        """Get entity definition by name."""
        if not self._valkey or not settings.USE_VALKEY:
            return None

        entity_data = await self._get_from_valkey(ENTITY_DEFS_KEY)
        if entity_data:
            return entity_data.get(entity_name)
        return None

    async def get_entity_id_by_name(self, entity_name: str) -> Optional[int]:
        """Get entity ID by name."""
        definition = await self.get_entity_definition(entity_name)
        if definition:
            return self._decode_from_valkey(definition.get("id"), int)
        return None

    async def get_entity_definition_by_id(self, entity_id: int) -> Optional[Dict[str, Any]]:
        """Get entity definition by ID."""
        if not self._valkey or not settings.USE_VALKEY:
            return None

        entity_data = await self._get_from_valkey(ENTITY_DEFS_KEY)
        if entity_data:
            # Search through all entity definitions to find matching ID
            for entity_name, entity_def in entity_data.items():
                def_id = self._decode_from_valkey(entity_def.get("id"), int)
                if def_id == entity_id:
                    return entity_def
        return None


# Singleton instance
_reference_data_manager: Optional[ReferenceDataManager] = None


def init_reference_data_manager(
    valkey_client: Optional[GlideClient] = None,
    session_factory: Optional[sessionmaker] = None,
) -> ReferenceDataManager:
    global _reference_data_manager
    _reference_data_manager = ReferenceDataManager(valkey_client, session_factory)
    return _reference_data_manager


def get_reference_data_manager() -> ReferenceDataManager:
    if _reference_data_manager is None:
        raise RuntimeError("ReferenceDataManager not initialized")
    return _reference_data_manager


def reset_reference_data_manager() -> None:
    global _reference_data_manager
    _reference_data_manager = None
