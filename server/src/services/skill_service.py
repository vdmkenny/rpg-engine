"""
Service layer for skill operations.

Handles skill synchronization, granting skills to players,
and experience/level calculations using GameStateManager.
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any, List

from server.src.core.logging_config import get_logger
from server.src.core.skills import SkillType
from server.src.services.game_state_manager import get_game_state_manager

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
    """Service for managing player skills via GameStateManager."""

    @staticmethod
    async def sync_skills_to_db() -> list:
        """
        Ensure all SkillType entries exist in the skills table.

        This should be called on server startup to ensure the database
        has all skills defined in the SkillType enum.

        Returns:
            List of all Skill records in the database
        """
        gsm = get_game_state_manager()
        return await gsm.sync_skills_to_db_offline()

    @staticmethod
    async def get_skill_id_map() -> Dict[str, int]:
        """
        Get a mapping of skill names to their database IDs.

        Returns:
            Dict mapping lowercase skill name to skill ID
        """
        gsm = get_game_state_manager()
        return await gsm.get_skill_id_map_offline()

    @staticmethod
    async def grant_all_skills_to_player(player_id: int) -> list:
        """
        Create PlayerSkill rows for all skills.

        Most skills start at level 1 with 0 XP.
        Hitpoints starts at level 10 with the XP required for level 10.

        This is called when a new player is created to give them
        all available skills. Uses INSERT ON CONFLICT for efficiency
        and idempotency.

        Args:
            player_id: The player's database ID

        Returns:
            List of all PlayerSkill records for the player
        """
        gsm = get_game_state_manager()
        return await gsm.grant_all_skills_to_player_offline(player_id)

    @staticmethod
    async def add_experience(
        player_id: int,
        skill: SkillType,
        xp_amount: int,
    ) -> Optional[LevelUpResult]:
        """
        Add experience to a player's skill with transparent online/offline handling.

        Uses GSM auto-loading to handle both online (Valkey) and offline (database) players
        identically. All XP calculation business logic is consolidated here.

        Args:
            player_id: The player's database ID
            skill: The skill to add XP to
            xp_amount: Amount of XP to add (must be positive)

        Returns:
            LevelUpResult with details, or None if skill not found
        """
        if xp_amount <= 0:
            return None

        gsm = get_game_state_manager()
        skill_name = skill.name.lower()

        # Get current skill data using auto-loading GSM
        current_skill = await gsm.get_skill(player_id, skill_name)
        if not current_skill:
            logger.warning(
                "Player skill not found",
                extra={"player_id": player_id, "skill": skill_name}
            )
            return None

        # Business logic: Calculate new XP and level
        from server.src.core.skills import (
            get_skill_xp_multiplier, level_for_xp, xp_to_next_level, MAX_LEVEL
        )
        
        xp_multiplier = get_skill_xp_multiplier(skill)
        previous_level = current_skill["level"]
        previous_xp = current_skill["experience"]
        
        # Calculate new XP and level
        new_xp = previous_xp + xp_amount
        new_level = level_for_xp(new_xp, xp_multiplier)
        
        # Cap at max level
        if new_level > MAX_LEVEL:
            new_level = MAX_LEVEL
        
        # Update skill data via GSM (handles online/offline transparently)
        await gsm.set_skill(
            player_id, skill_name, current_skill["skill_id"], new_level, new_xp
        )
        
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
        Handles both online and offline players.

        Args:
            player_id: The player's database ID

        Returns:
            List of skill info dicts with name, category, level, xp, etc.
        """
        gsm = get_game_state_manager()
        
        # Always use offline method for now to ensure consistency
        # TODO: Add Valkey support for skill metadata computations
        return await gsm.get_player_skills_offline(player_id)

    @staticmethod
    async def get_total_level(player_id: int) -> int:
        """
        Calculate the sum of all skill levels for a player using auto-loading.
        
        Uses GSM transparent access - no difference between online/offline players.

        Args:
            player_id: The player's database ID

        Returns:
            Total level across all skills
        """
        gsm = get_game_state_manager()
        
        # Use auto-loading GSM method - works for both online and offline players
        skills = await gsm.get_all_skills(player_id)
        return sum(skill_data["level"] for skill_data in skills.values())

    @staticmethod
    async def get_hitpoints_level(player_id: int) -> int:
        """
        Get the player's Hitpoints skill level using auto-loading.
        
        Uses GSM transparent access - no difference between online/offline players.
        This is the base max HP before equipment bonuses.

        Args:
            player_id: The player's database ID

        Returns:
            Hitpoints level (minimum HITPOINTS_START_LEVEL if not found)
        """
        gsm = get_game_state_manager()
        
        # Use auto-loading GSM method - works for both online and offline players
        hitpoints_skill = await gsm.get_skill(player_id, "hitpoints")
        if hitpoints_skill:
            return hitpoints_skill["level"]
            
        # If skill not found, fallback to offline method for safety
        return await gsm.get_hitpoints_level_offline(player_id)
