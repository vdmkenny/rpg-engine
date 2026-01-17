"""
Service layer for skill operations.

Handles skill synchronization, granting skills to players,
and experience/level calculations.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from server.src.models.skill import Skill, PlayerSkill
from server.src.core.skills import (
    SkillType,
    get_skill_xp_multiplier,
    level_for_xp,
    xp_for_level,
    xp_to_next_level,
    progress_to_next_level,
    MAX_LEVEL,
)

logger = logging.getLogger(__name__)


@dataclass
class LevelUpResult:
    """Result of adding experience to a skill."""

    skill_name: str
    previous_level: int
    new_level: int
    current_xp: int
    xp_to_next: int
    leveled_up: bool

    @property
    def levels_gained(self) -> int:
        return self.new_level - self.previous_level


class SkillService:
    """Service for managing player skills."""

    @staticmethod
    async def sync_skills_to_db(db: AsyncSession) -> list[Skill]:
        """
        Ensure all SkillType entries exist in the skills table.

        This should be called on server startup to ensure the database
        has all skills defined in the SkillType enum.

        Args:
            db: Database session

        Returns:
            List of all Skill records in the database
        """
        skill_names = SkillType.all_skill_names()

        # Get existing skills
        result = await db.execute(select(Skill))
        existing_skills = {s.name: s for s in result.scalars().all()}

        # Insert missing skills
        for skill_name in skill_names:
            if skill_name not in existing_skills:
                new_skill = Skill(name=skill_name)
                db.add(new_skill)
                logger.info(f"Added new skill to database: {skill_name}")

        await db.commit()

        # Return all skills
        result = await db.execute(select(Skill))
        return list(result.scalars().all())

    @staticmethod
    async def get_skill_id_map(db: AsyncSession) -> dict[str, int]:
        """
        Get a mapping of skill names to their database IDs.

        Args:
            db: Database session

        Returns:
            Dict mapping lowercase skill name to skill ID
        """
        result = await db.execute(select(Skill))
        return {s.name: s.id for s in result.scalars().all()}

    @staticmethod
    async def grant_all_skills_to_player(
        db: AsyncSession, player_id: int
    ) -> list[PlayerSkill]:
        """
        Create PlayerSkill rows for all skills at level 1 with 0 XP.

        This is called when a new player is created to give them
        all available skills. Uses INSERT ON CONFLICT for efficiency
        and idempotency.

        Args:
            db: Database session
            player_id: The player's database ID

        Returns:
            List of all PlayerSkill records for the player
        """
        skill_id_map = await SkillService.get_skill_id_map(db)

        if not skill_id_map:
            # No skills in database yet, sync them first
            await SkillService.sync_skills_to_db(db)
            skill_id_map = await SkillService.get_skill_id_map(db)

        if not skill_id_map:
            # Still no skills, return empty list
            return []

        # Build values for all skills in a single INSERT
        values = [
            {
                "player_id": player_id,
                "skill_id": skill_id,
                "current_level": 1,
                "experience": 0,
            }
            for skill_id in skill_id_map.values()
        ]

        # Use INSERT ON CONFLICT DO NOTHING for idempotency
        # If the player already has a skill, it won't be overwritten
        stmt = pg_insert(PlayerSkill).values(values)
        stmt = stmt.on_conflict_do_nothing(constraint="_player_skill_uc")
        await db.execute(stmt)
        await db.commit()

        # Fetch and return all player skills
        result = await db.execute(
            select(PlayerSkill).where(PlayerSkill.player_id == player_id)
        )
        player_skills = list(result.scalars().all())

        logger.info(
            "Granted skills to player",
            extra={"player_id": player_id, "total_skills": len(player_skills)},
        )

        return player_skills

    @staticmethod
    async def add_experience(
        db: AsyncSession,
        player_id: int,
        skill: SkillType,
        xp_amount: int,
    ) -> Optional[LevelUpResult]:
        """
        Add experience to a player's skill.

        Automatically recalculates the level based on new XP total.

        Args:
            db: Database session
            player_id: The player's database ID
            skill: The skill to add XP to
            xp_amount: Amount of XP to add (must be positive)

        Returns:
            LevelUpResult with details, or None if skill not found
        """
        if xp_amount <= 0:
            return None

        skill_name = skill.name.lower()
        xp_multiplier = get_skill_xp_multiplier(skill)

        # Get the skill ID
        skill_result = await db.execute(select(Skill).where(Skill.name == skill_name))
        skill_record = skill_result.scalar_one_or_none()

        if skill_record is None:
            logger.warning(f"Skill not found in database: {skill_name}")
            return None

        # Get player's current progress
        result = await db.execute(
            select(PlayerSkill).where(
                PlayerSkill.player_id == player_id,
                PlayerSkill.skill_id == skill_record.id,
            )
        )
        player_skill = result.scalar_one_or_none()

        if player_skill is None:
            logger.warning(
                f"Player does not have skill",
                extra={"player_id": player_id, "skill": skill_name},
            )
            return None

        previous_level = player_skill.current_level
        previous_xp = player_skill.experience

        # Calculate new XP and level
        new_xp = previous_xp + xp_amount
        new_level = level_for_xp(new_xp, xp_multiplier)

        # Cap at max level
        if new_level > MAX_LEVEL:
            new_level = MAX_LEVEL

        # Update the record
        player_skill.experience = new_xp
        player_skill.current_level = new_level

        await db.commit()

        leveled_up = new_level > previous_level
        if leveled_up:
            logger.info(
                f"Player leveled up",
                extra={
                    "player_id": player_id,
                    "skill": skill_name,
                    "previous_level": previous_level,
                    "new_level": new_level,
                    "xp_gained": xp_amount,
                },
            )

        return LevelUpResult(
            skill_name=skill.value.name,
            previous_level=previous_level,
            new_level=new_level,
            current_xp=new_xp,
            xp_to_next=xp_to_next_level(new_xp, xp_multiplier),
            leveled_up=leveled_up,
        )

    @staticmethod
    async def get_player_skills(
        db: AsyncSession, player_id: int
    ) -> list[dict]:
        """
        Fetch all skills for a player with computed metadata.

        Args:
            db: Database session
            player_id: The player's database ID

        Returns:
            List of skill info dicts with name, category, level, xp, etc.
        """
        result = await db.execute(
            select(PlayerSkill, Skill)
            .join(Skill, PlayerSkill.skill_id == Skill.id)
            .where(PlayerSkill.player_id == player_id)
        )

        skills_data = []
        for player_skill, skill in result.all():
            skill_type = SkillType.from_name(skill.name)
            if skill_type is None:
                continue

            xp_multiplier = get_skill_xp_multiplier(skill_type)
            current_xp = player_skill.experience
            current_level = player_skill.current_level

            skills_data.append({
                "name": skill_type.value.name,
                "category": skill_type.value.category.value,
                "description": skill_type.value.description,
                "current_level": current_level,
                "experience": current_xp,
                "xp_for_current_level": xp_for_level(current_level, xp_multiplier),
                "xp_for_next_level": xp_for_level(current_level + 1, xp_multiplier) if current_level < MAX_LEVEL else 0,
                "xp_to_next_level": xp_to_next_level(current_xp, xp_multiplier),
                "xp_multiplier": xp_multiplier,
                "progress_percent": progress_to_next_level(current_xp, xp_multiplier),
                "max_level": MAX_LEVEL,
            })

        return skills_data

    @staticmethod
    async def get_total_level(db: AsyncSession, player_id: int) -> int:
        """
        Calculate the sum of all skill levels for a player.

        Args:
            db: Database session
            player_id: The player's database ID

        Returns:
            Total level across all skills
        """
        result = await db.execute(
            select(PlayerSkill).where(PlayerSkill.player_id == player_id)
        )
        player_skills = result.scalars().all()
        return sum(ps.current_level for ps in player_skills)
