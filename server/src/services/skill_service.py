"""
Service layer for skill operations.

Handles skill synchronization, granting skills to players,
and experience/level calculations using SkillsManager.
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any, List

from server.src.core.logging_config import get_logger
from server.src.core.skills import SkillType

logger = get_logger(__name__)


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
    async def get_skill_level(player_id: int, skill_type: str) -> int:
        """
        Get player's current level for a specific skill.
        
        Used by other services (e.g., EquipmentService) for requirement checking.

        Args:
            player_id: The player's database ID
            skill_type: Skill name (e.g., "attack", "strength", "hitpoints")

        Returns:
            Current skill level, or 1 if skill not found
        """
        from server.src.services.game_state import get_skills_manager

        skills_mgr = get_skills_manager()
        skill_data = await skills_mgr.get_skill(player_id, skill_type)

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
    ) -> Optional[LevelUpResult]:
        """
        Add experience to a player's skill.

        All XP calculation business logic is consolidated here.

        Args:
            player_id: The player's database ID
            skill: The skill to add XP to
            xp_amount: Amount of XP to add (must be positive)

        Returns:
            LevelUpResult with details, or None if skill not found
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

        return LevelUpResult(
            skill_name=skill.value.name,
            previous_level=previous_level,
            new_level=new_level,
            current_xp=new_xp,
            xp_to_next=xp_to_next_level(new_xp, xp_multiplier),
            leveled_up=leveled_up,
        )

    @staticmethod
    async def get_player_skills(player_id: int) -> List[Dict]:
        """
        Fetch all skills for a player with computed metadata.

        Args:
            player_id: The player's database ID

        Returns:
            List of skill info dicts with name, category, level, xp, etc.
        """
        from server.src.services.game_state import get_skills_manager

        skills_mgr = get_skills_manager()
        skills_data = await skills_mgr.get_all_skills(player_id)

        result = []
        for skill_name, skill_data in skills_data.items():
            result.append({
                "name": skill_name,
                "level": skill_data.get("level", 1),
                "experience": skill_data.get("experience", 0),
            })

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
