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
        Add experience to a player's skill.

        Automatically recalculates the level based on new XP total.
        Handles both online (Valkey) and offline (database) players.

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

        # Check if player is online - use Valkey if available
        if gsm.is_online(player_id):
            # For online players, update skill in Valkey and mark dirty
            current_skill = await gsm.get_skill(player_id, skill_name)
            if not current_skill:
                logger.warning(
                    "Player skill not found in Valkey",
                    extra={"player_id": player_id, "skill": skill_name}
                )
                return None

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
            
            # Update in Valkey (this marks as dirty for database sync)
            await gsm.set_skill(
                player_id, skill_name, current_skill["skill_id"], new_level, new_xp
            )
            
            leveled_up = new_level > previous_level
            if leveled_up:
                logger.info(
                    "Player leveled up (online)",
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
        else:
            # For offline players, use database directly
            result = await gsm.add_experience_offline(player_id, skill_name, xp_amount)
            if result:
                return LevelUpResult(
                    skill_name=result["skill_name"],
                    previous_level=result["previous_level"],
                    new_level=result["new_level"],
                    current_xp=result["current_xp"],
                    xp_to_next=result["xp_to_next"],
                    leveled_up=result["leveled_up"],
                )
            return None

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
        Calculate the sum of all skill levels for a player.
        Handles both online and offline players.

        Args:
            player_id: The player's database ID

        Returns:
            Total level across all skills
        """
        gsm = get_game_state_manager()
        
        if gsm.is_online(player_id):
            # For online players, get from Valkey
            skills = await gsm.get_all_skills(player_id)
            return sum(skill_data["level"] for skill_data in skills.values())
        else:
            # For offline players, use database
            return await gsm.get_total_level_offline(player_id)

    @staticmethod
    async def get_hitpoints_level(player_id: int) -> int:
        """
        Get the player's Hitpoints skill level.
        Handles both online and offline players.

        This is the base max HP before equipment bonuses.

        Args:
            player_id: The player's database ID

        Returns:
            Hitpoints level (minimum HITPOINTS_START_LEVEL if not found)
        """
        gsm = get_game_state_manager()
        
        if gsm.is_online(player_id):
            # For online players, get from Valkey
            hitpoints_skill = await gsm.get_skill(player_id, "hitpoints")
            if hitpoints_skill:
                return hitpoints_skill["level"]
            
        # Fallback to offline method
        return await gsm.get_hitpoints_level_offline(player_id)
