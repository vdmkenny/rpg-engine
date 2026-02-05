"""
Skills management - Tier 2 data with auto-loading.

Pure persistence layer: CRUD operations only, no business logic.
XP calculations and level requirements handled by SkillService.
"""

import traceback
from typing import Any, Dict, List, Optional

from glide import GlideClient
from sqlalchemy import select, delete
from sqlalchemy.orm import sessionmaker

from server.src.core.config import settings
from server.src.core.logging_config import get_logger

from .base_manager import BaseManager, SKILLS_TTL

logger = get_logger(__name__)

SKILLS_KEY = "skills:{player_id}"
DIRTY_SKILLS_KEY = "dirty:skills"


class SkillsManager(BaseManager):
    """Manages player skills persistence with transparent auto-loading."""

    def __init__(
        self,
        valkey_client: Optional[GlideClient] = None,
        session_factory: Optional[sessionmaker] = None,
    ):
        super().__init__(valkey_client, session_factory)

    # =========================================================================
    # Skills CRUD
    # =========================================================================

    async def get_skill(
        self, player_id: int, skill_name: str
    ) -> Optional[Dict[str, Any]]:
        """Get specific skill data."""
        skills = await self.get_all_skills(player_id)
        return skills.get(skill_name.lower())

    async def get_all_skills(self, player_id: int) -> Dict[str, Dict[str, Any]]:
        """Get all skills with transparent auto-loading from DB."""
        if not settings.USE_VALKEY or not self._valkey:
            return await self._load_skills_from_db(player_id)

        key = SKILLS_KEY.format(player_id=player_id)

        async def load_from_db():
            return await self._load_skills_from_db(player_id)

        skills = await self.auto_load_with_ttl(
            key, load_from_db, SKILLS_TTL, decoder={"level": int, "experience": int}
        )
        return skills or {}

    async def _load_skills_from_db(self, player_id: int) -> Dict[str, Dict[str, Any]]:
        if not self._session_factory:
            return {}

        from server.src.models.skill import PlayerSkill, Skill

        async with self._db_session() as db:
            result = await db.execute(
                select(PlayerSkill, Skill)
                .join(Skill, PlayerSkill.skill_id == Skill.id)
                .where(PlayerSkill.player_id == player_id)
            )

            skills_data = {}
            for player_skill, skill in result:
                skill_name = skill.name.lower()
                skills_data[skill_name] = {
                    "skill_id": skill.id,
                    "level": player_skill.current_level,
                    "experience": player_skill.experience,
                }

            return skills_data

    async def set_skill(
        self, player_id: int, skill_name: str, level: int, experience: int
    ) -> None:
        """Set skill level and XP for a player."""
        # Convert SkillType enum to string name
        if hasattr(skill_name, 'name'):
            skill_name = skill_name.name
        
        if not settings.USE_VALKEY or not self._valkey:
            await self._update_skill_in_db(player_id, skill_name, level, experience)
            return

        key = SKILLS_KEY.format(player_id=player_id)

        # Get current skills
        skills = await self._get_from_valkey(key) or {}

        # Update skill (lowercase to match database)
        skill_name_lower = skill_name.lower()
        skills[skill_name_lower] = {
            "level": level,
            "experience": experience,
        }

        await self._cache_in_valkey(key, skills, SKILLS_TTL)
        await self._valkey.sadd(DIRTY_SKILLS_KEY, [str(player_id)])

    async def _update_skill_in_db(
        self, player_id: int, skill_name: str, level: int, experience: int
    ) -> None:
        if not self._session_factory:
            return

        # Convert SkillType enum to string name
        if hasattr(skill_name, 'name'):
            skill_name = skill_name.name

        from server.src.models.skill import PlayerSkill, Skill
        from sqlalchemy.dialects.postgresql import insert

        async with self._db_session() as db:
            # Get skill ID
            skill_result = await db.execute(
                select(Skill.id).where(Skill.name.ilike(skill_name))
            )
            skill_id = skill_result.scalar_one_or_none()

            if not skill_id:
                logger.warning(f"Skill not found: {skill_name}")
                return

            # Upsert player skill
            stmt = insert(PlayerSkill).values(
                player_id=player_id,
                skill_id=skill_id,
                current_level=level,
                experience=experience,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["player_id", "skill_id"],
                set_={"current_level": level, "experience": experience},
            )
            await db.execute(stmt)
            await self._commit_if_not_test_session(db)

    async def grant_all_skills(self, player_id: int) -> None:
        """Create skill entries for all skills at level 1 (for new players)."""
        if not self._session_factory:
            return

        from server.src.models.skill import PlayerSkill, Skill
        from sqlalchemy.dialects.postgresql import insert

        async with self._db_session() as db:
            # Get all skill IDs
            result = await db.execute(select(Skill.id, Skill.name))
            skills = result.all()

            for skill_id, skill_name in skills:
                stmt = insert(PlayerSkill).values(
                    player_id=player_id,
                    skill_id=skill_id,
                    current_level=1,
                    experience=0,
                )
                stmt = stmt.on_conflict_do_nothing()
                await db.execute(stmt)

            await self._commit_if_not_test_session(db)

            # Also cache in Valkey if available - only set skills that don't exist
            if self._valkey and settings.USE_VALKEY:
                key = SKILLS_KEY.format(player_id=player_id)
                existing_skills = await self._get_from_valkey(key) or {}
                
                # Only add skills that don't already exist in cache
                for _, name in skills:
                    skill_name_lower = name.lower()
                    if skill_name_lower not in existing_skills:
                        existing_skills[skill_name_lower] = {"level": 1, "experience": 0}
                
                await self._cache_in_valkey(key, existing_skills, SKILLS_TTL)

    async def clear_skills(self, player_id: int) -> None:
        """Remove all skills from player."""
        if not settings.USE_VALKEY or not self._valkey:
            await self._clear_skills_from_db(player_id)
            return

        key = SKILLS_KEY.format(player_id=player_id)
        await self._delete_from_valkey(key)
        await self._valkey.sadd(DIRTY_SKILLS_KEY, [str(player_id)])

    async def _clear_skills_from_db(self, player_id: int) -> None:
        if not self._session_factory:
            return

        from server.src.models.skill import PlayerSkill

        async with self._db_session() as db:
            await db.execute(
                delete(PlayerSkill).where(PlayerSkill.player_id == player_id)
            )
            await self._commit_if_not_test_session(db)

    # =========================================================================
    # Batch Sync Support
    # =========================================================================

    async def get_dirty_skills(self) -> List[int]:
        if not self._valkey:
            return []

        dirty = await self._valkey.smembers(DIRTY_SKILLS_KEY)
        return [int(self._decode_bytes(d)) for d in dirty]

    async def clear_dirty_skills(self, player_id: int) -> None:
        if self._valkey:
            await self._valkey.srem(DIRTY_SKILLS_KEY, [str(player_id)])

    async def sync_skills_to_db(self, player_id: int, db) -> None:
        if not self._valkey:
            return

        from server.src.models.skill import PlayerSkill, Skill
        from sqlalchemy.dialects.postgresql import insert

        key = SKILLS_KEY.format(player_id=player_id)
        skills = await self._get_from_valkey(key)

        if skills is None:
            return

        # Get skill name to ID mapping
        skill_result = await db.execute(select(Skill.id, Skill.name))
        skill_map = {name.lower(): id for id, name in skill_result}

        # Upsert each skill
        for skill_name, skill_data in skills.items():
            skill_id = skill_map.get(skill_name.lower())
            if not skill_id:
                continue

            level = self._decode_from_valkey(skill_data.get("level"), int)
            experience = self._decode_from_valkey(skill_data.get("experience"), int)

            stmt = insert(PlayerSkill).values(
                player_id=player_id,
                skill_id=skill_id,
                current_level=level or 1,
                experience=experience or 0,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["player_id", "skill_id"],
                set_={"current_level": level or 1, "experience": experience or 0},
            )
            await db.execute(stmt)


# Singleton instance
_skills_manager: Optional[SkillsManager] = None


def init_skills_manager(
    valkey_client: Optional[GlideClient] = None,
    session_factory: Optional[sessionmaker] = None,
) -> SkillsManager:
    global _skills_manager
    _skills_manager = SkillsManager(valkey_client, session_factory)
    return _skills_manager


def get_skills_manager() -> SkillsManager:
    if _skills_manager is None:
        raise RuntimeError("SkillsManager not initialized")
    return _skills_manager


def reset_skills_manager() -> None:
    global _skills_manager
    _skills_manager = None
