"""
Service for managing player operations.

Handles player creation, login/logout, and core player state management.
"""

from typing import Optional, TYPE_CHECKING
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from ..core.config import settings
from ..core.security import get_password_hash
from ..models.player import Player
from ..schemas.player import PlayerCreate
from ..core.logging_config import get_logger

if TYPE_CHECKING:
    from .game_state_manager import GameStateManager

logger = get_logger(__name__)


class PlayerService:
    """Service for managing player operations."""

    @staticmethod
    async def create_player(
        db: AsyncSession, 
        player_data: PlayerCreate, 
    ) -> Player:
        """
        Create a new player with proper initialization.
        
        Creates player record and initializes all skills with default values.

        Args:
            db: Database session
            player_data: Player creation data

        Returns:
            Created Player instance

        Raises:
            HTTPException: If username already exists
        """
        try:
            # Create player record
            hashed_password = get_password_hash(player_data.password)
            player = Player(
                username=player_data.username,
                hashed_password=hashed_password,
                x_coord=getattr(player_data, 'x', 10),
                y_coord=getattr(player_data, 'y', 10),
                map_id=getattr(player_data, 'map_id', "samplemap"),
            )
            
            db.add(player)
            await db.flush()  # Get player ID
            
            # Initialize player skills with default values
            from .skill_service import SkillService
            await SkillService.grant_all_skills_to_player(db, player.id)
            
            await db.commit()
            
            logger.info(
                "Player created successfully",
                extra={
                    "player_id": player.id,
                    "username": player.username,
                }
            )
            
            return player
            
        except IntegrityError:
            await db.rollback()
            logger.warning(
                "Player creation failed - username exists",
                extra={"username": player_data.username}
            )
            raise

    @staticmethod
    async def login_player(
        db: AsyncSession,
        player: Player,
    ) -> None:
        """
        Handle player login process.
        
        Registers player as online and loads complete game state.

        Args:
            db: Database session
            player: Player instance
        """
        from .game_state_manager import get_game_state_manager
        
        state_manager = get_game_state_manager()
        
        # Register as online
        state_manager.register_online_player(player.id, player.username)
        
        # Load complete player state
        await state_manager.load_player_state(player.id)
        
        logger.info(
            "Player logged in",
            extra={
                "player_id": player.id,
                "username": player.username,
            }
        )

    @staticmethod
    async def logout_player(
        db: AsyncSession,
        player_id: int,
        username: str,
    ) -> None:
        """
        Handle player logout process.
        
        Saves all player progress and cleans up active session.

        Args:
            db: Database session
            player_id: Player ID
            username: Player username
        """
        from .game_state_manager import get_game_state_manager
        
        state_manager = get_game_state_manager()
        
        try:
            # Save all player progress to database
            await state_manager.sync_player_to_db(player_id, username)
            
            # Clean up active session data
            await state_manager.cleanup_player_state(player_id)
            
            # Mark player as offline
            state_manager.unregister_online_player(player_id)
            
            logger.info(
                "Player logged out",
                extra={
                    "player_id": player_id,
                    "username": username,
                }
            )
            
        except Exception as e:
            logger.error(
                "Error during player logout",
                extra={
                    "player_id": player_id,
                    "username": username,
                    "error": str(e),
                }
            )
            raise

    @staticmethod
    async def get_player_by_username(
        db: AsyncSession, username: str
    ) -> Optional[Player]:
        """
        Get player by username.

        Args:
            db: Database session
            username: Player username

        Returns:
            Player if found, None otherwise
        """
        result = await db.execute(
            select(Player).where(Player.username == username)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_player_by_id(
        db: AsyncSession, player_id: int
    ) -> Optional[Player]:
        """
        Get player by ID.

        Args:
            db: Database session
            player_id: Player ID

        Returns:
            Player if found, None otherwise
        """
        result = await db.execute(
            select(Player).where(Player.id == player_id)
        )
        return result.scalar_one_or_none()