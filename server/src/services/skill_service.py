"""
Service layer for skill operations.

Handles skill synchronization, granting skills to players,
and experience/level calculations using SkillsManager.
"""

from typing import Optional, List

from server.src.core.logging_config import get_logger
from server.src.core.skills import SkillType
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
            get_skill_xp_multiplier, level_for_xp, xp_to_next_level, MAX_LEVEL
        )

        if xp_amount <= 0:
            return None

        skills_mgr = get_skills_manager()
        skill_name = skill.name.lower()

        # Get current skill data
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
        previous_xp = current_skill["experience"]

        # Calculate new XP and level
        new_xp = previous_xp + xp_amount
        new_level = level_for_xp(new_xp, xp_multiplier)

        # Cap at max level
        if new_level > MAX_LEVEL:
            new_level = MAX_LEVEL

        # Update skill data via manager
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
            current_xp=new_xp,
            current_level=new_level,
            previous_level=previous_level,
            xp_to_next_level=xp_to_next_level(new_xp, xp_multiplier),
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
            experience = skill_data.get("experience", 0)
            xp_multiplier = get_skill_xp_multiplier(skill_type)

            result.append(
                SkillData(
                    name=skill_type.value.name,
                    category=skill_type.value.category.value,
                    description=skill_type.value.description,
                    current_level=level,
                    experience=experience,
                    xp_for_current_level=xp_for_current_level(experience, xp_multiplier),
                    xp_for_next_level=xp_for_level(level + 1, xp_multiplier),
                    xp_to_next_level=xp_to_next_level(experience, xp_multiplier),
                    xp_multiplier=xp_multiplier,
                    progress_percent=progress_to_next_level(experience, xp_multiplier),
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

    @staticmethod
    async def get_hitpoints_level(player_id: int) -> int:
        """
        Get the player's Hitpoints skill level.

        Args:
            player_id: The player's database ID

        Returns:
            Hitpoints level, or 10 if not found
        """
        from server.src.services.game_state import get_skills_manager

        skills_mgr = get_skills_manager()
        skill_data = await skills_mgr.get_skill(player_id, "hitpoints")

        if skill_data:
            return skill_data.get("level", 10)
        return 10
