"""
Service layer for skill operations.

Handles skill synchronization, granting skills to players,
and experience/level calculations using SkillsManager.
"""

from typing import Optional, List

from server.src.core.logging_config import get_logger
from server.src.core.skills import SkillType
from server.src.core.concurrency import get_player_lock_manager, LockType
from server.src.schemas.skill import XPGain, SkillData

logger = get_logger(__name__)


class SkillService:
    """Service for managing player skills."""

    @staticmethod
    async def get_skill_level(player_id: int, skill_type: SkillType) -> int:
        """
        Get player's current level for a specific skill.
        
        Used by other services (e.g., EquipmentService) for requirement checking.

        Args:
            player_id: The player's database ID
            skill_type: SkillType enum (e.g., SkillType.ATTACK, SkillType.HITPOINTS)

        Returns:
            Current skill level, or 1 if skill not found
        """
        from server.src.services.game_state import get_skills_manager

        skills_mgr = get_skills_manager()
        skill_name = skill_type.name.lower()
        skill_data = await skills_mgr.get_skill(player_id, skill_name)

        if skill_data:
            return skill_data.get("level", 1)
        return 1

    @staticmethod
    async def grant_all_skills_to_player(player_id: int) -> None:
        """
        Create PlayerSkill rows for all skills at level 1.

        Hitpoints starts at level 10 with appropriate XP.
        Called when a new player is created.

        Args:
            player_id: The player's database ID
        """
        from server.src.services.game_state import get_skills_manager
        from server.src.core.skills import xp_to_next_level, get_skill_xp_multiplier

        skills_mgr = get_skills_manager()

        # Grant all skills via manager
        await skills_mgr.grant_all_skills(player_id)

        # Set Hitpoints to level 10 with appropriate XP
        hitpoints_xp = xp_to_next_level(10, get_skill_xp_multiplier(SkillType.HITPOINTS))
        await skills_mgr.set_skill(player_id, "hitpoints", 10, hitpoints_xp)

        logger.info("Granted all skills to player", extra={"player_id": player_id})

    @staticmethod
    async def backfill_missing_skills() -> int:
        """
        Ensure all existing players have all skills.

        Players created before new skills were added may be missing rows.
        Hitpoints is set to HITPOINTS_START_LEVEL (10) if missing or below that.
        Other missing skills are created at level 1.

        Returns:
            Number of players that were updated
        """
        from server.src.core.skills import (
            HITPOINTS_START_LEVEL, xp_for_level, get_skill_xp_multiplier
        )
        from server.src.models.player import Player
        from server.src.models.skill import PlayerSkill, Skill
        from server.src.core.database import AsyncSessionLocal
        from sqlalchemy import select
        from sqlalchemy.dialects.postgresql import insert

        hitpoints_xp = xp_for_level(
            HITPOINTS_START_LEVEL,
            get_skill_xp_multiplier(SkillType.HITPOINTS),
        )

        players_updated = 0

        async with AsyncSessionLocal() as db:
            # Get all skill definitions
            skill_result = await db.execute(select(Skill.id, Skill.name))
            all_skills = skill_result.all()

            # Get all player IDs
            player_result = await db.execute(select(Player.id))
            player_ids = [row[0] for row in player_result.all()]

            for player_id in player_ids:
                updated = False

                for skill_id, skill_name in all_skills:
                    is_hitpoints = skill_name.lower() == "hitpoints"

                    if is_hitpoints:
                        # Upsert: create at level 10 if missing, upgrade if below 10
                        stmt = insert(PlayerSkill).values(
                            player_id=player_id,
                            skill_id=skill_id,
                            level=HITPOINTS_START_LEVEL,
                            xp=hitpoints_xp,
                        )
                        stmt = stmt.on_conflict_do_update(
                            index_elements=["player_id", "skill_id"],
                            set_={
                                "level": HITPOINTS_START_LEVEL,
                                "xp": hitpoints_xp,
                            },
                            where=PlayerSkill.level < HITPOINTS_START_LEVEL,
                        )
                    else:
                        # Insert only if missing
                        stmt = insert(PlayerSkill).values(
                            player_id=player_id,
                            skill_id=skill_id,
                            level=1,
                            xp=0,
                        )
                        stmt = stmt.on_conflict_do_nothing()

                    result = await db.execute(stmt)
                    if result.rowcount > 0:
                        updated = True

                if updated:
                    players_updated += 1

            # Also fix current_hp in players table for anyone below start level
            from sqlalchemy import update
            await db.execute(
                update(Player)
                .where(Player.current_hp < HITPOINTS_START_LEVEL)
                .values(current_hp=HITPOINTS_START_LEVEL)
            )

            await db.commit()

        return players_updated

    @staticmethod
    async def add_experience(
        player_id: int,
        skill: SkillType,
        xp_amount: int,
    ) -> Optional[XPGain]:
        """
        Add experience to a player's skill.

        All XP calculation business logic is consolidated here.

        Args:
            player_id: The player's database ID
            skill: The skill to add XP to
            xp_amount: Amount of XP to add (must be positive)

        Returns:
            XPGain with details, or None if skill not found
        """
        from server.src.services.game_state import get_skills_manager
        from server.src.core.skills import (
            get_skill_xp_multiplier, level_for_xp, xp_for_level, xp_to_next_level, MAX_LEVEL
        )

        if xp_amount <= 0:
            return None

        lock_manager = get_player_lock_manager()
        async with lock_manager.acquire_player_lock(
            player_id, LockType.SKILLS, "add_experience"
        ):
            skills_mgr = get_skills_manager()
            skill_name = skill.name.lower()

            # Get current skill data (within lock)
            current_skill = await skills_mgr.get_skill(player_id, skill_name)
            if not current_skill:
                logger.warning(
                    "Player skill not found",
                    extra={"player_id": player_id, "skill": skill_name}
                )
                return None

            # Business logic: Calculate new XP and level
            xp_multiplier = get_skill_xp_multiplier(skill)
            previous_level = current_skill["level"]
            previous_xp = current_skill["xp"]

            # Calculate new XP and level, capping both at max
            max_xp = xp_for_level(MAX_LEVEL, xp_multiplier)
            new_xp = min(previous_xp + xp_amount, max_xp)
            new_level = min(level_for_xp(new_xp, xp_multiplier), MAX_LEVEL)

            # Update skill data via manager (within lock)
            await skills_mgr.set_skill(player_id, skill_name, new_level, new_xp)

            leveled_up = new_level > previous_level
            if leveled_up:
                logger.info(
                    "Player leveled up",
                    extra={
                        "player_id": player_id,
                        "skill": skill_name,
                        "previous_level": previous_level,
                        "new_level": new_level,
                        "xp_gained": xp_amount,
                    }
                )

            return XPGain(
                skill=skill_name,
                xp_gained=xp_amount,
                xp=new_xp,
                level=new_level,
                previous_level=previous_level,
                xp_to_next=xp_to_next_level(new_xp, xp_multiplier),
                leveled_up=leveled_up,
                levels_gained=new_level - previous_level,
            )

    @staticmethod
    async def get_player_skills(player_id: int) -> List[SkillData]:
        """
        Fetch all skills for a player with computed metadata.

        Args:
            player_id: The player's database ID

        Returns:
            List of SkillData with complete skill information
        """
        from server.src.services.game_state import get_skills_manager
        from server.src.core.skills import (
            get_skill_xp_multiplier,
            xp_to_next_level,
            xp_for_level,
            xp_for_current_level,
            progress_to_next_level,
            MAX_LEVEL,
        )

        skills_mgr = get_skills_manager()
        skills_data = await skills_mgr.get_all_skills(player_id)

        result = []
        for skill_name, skill_data in skills_data.items():
            skill_type = SkillType.from_name(skill_name)
            if not skill_type:
                continue

            level = skill_data.get("level", 1)
            xp = skill_data.get("xp", 0)
            xp_multiplier = get_skill_xp_multiplier(skill_type)

            result.append(
                SkillData(
                    name=skill_type.value.name.lower(),
                    category=skill_type.value.category.value,
                    description=skill_type.value.description,
                    level=level,
                    xp=xp,
                    xp_for_current=xp_for_current_level(xp, xp_multiplier),
                    xp_for_next=xp_for_level(level + 1, xp_multiplier),
                    xp_to_next=xp_to_next_level(xp, xp_multiplier),
                    xp_multiplier=xp_multiplier,
                    progress_percent=progress_to_next_level(xp, xp_multiplier),
                    max_level=MAX_LEVEL,
                )
            )

        return result

    @staticmethod
    async def get_total_level(player_id: int) -> int:
        """
        Calculate the sum of all skill levels for a player.

        Args:
            player_id: The player's database ID

        Returns:
            Total level across all skills
        """
        from server.src.services.game_state import get_skills_manager

        skills_mgr = get_skills_manager()
        skills = await skills_mgr.get_all_skills(player_id)
        return sum(skill_data.get("level", 1) for skill_data in skills.values())

