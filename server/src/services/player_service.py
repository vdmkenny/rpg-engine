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

    @staticmethod
    async def get_player_position(player_id: int) -> Optional[Dict[str, Any]]:
        """
        Get player's current position and basic state from GameStateManager.

        Args:
            player_id: Player ID

        Returns:
            Dict with position data (x, y, map_id, etc.) or None if not online
        """
        from .game_state_manager import get_game_state_manager
        
        state_manager = get_game_state_manager()
        
        # Check if player is online
        if not state_manager.is_player_online(player_id):
            logger.debug(
                "Player position requested but player not online",
                extra={"player_id": player_id}
            )
            return None
        
        try:
            # Get position data from GSM
            position_data = await state_manager.get_player_position(player_id)
            if position_data:
                return {
                    "x": position_data["x"],
                    "y": position_data["y"], 
                    "map_id": position_data["map_id"],
                    "player_id": player_id
                }
            return None
            
        except Exception as e:
            logger.error(
                "Error getting player position",
                extra={
                    "player_id": player_id,
                    "error": str(e),
                }
            )
            return None

    @staticmethod
    async def get_nearby_players(
        player_id: int, range_tiles: int = 80
    ) -> List[Dict[str, Any]]:
        """
        Get players within range of the specified player for chat/visibility.

        Args:
            player_id: Center player ID
            range_tiles: Range in tiles to search

        Returns:
            List of nearby player data dicts
        """
        from .game_state_manager import get_game_state_manager
        
        state_manager = get_game_state_manager()
        
        # Get current player's position
        center_position = await PlayerService.get_player_position(player_id)
        if not center_position:
            return []
        
        try:
            # Get all online players on the same map
            online_players = state_manager.get_online_players()
            nearby_players = []
            
            for other_player_id in online_players:
                if other_player_id == player_id:
                    continue  # Skip self
                    
                other_position = await state_manager.get_player_position(other_player_id)
                if not other_position or other_position["map_id"] != center_position["map_id"]:
                    continue  # Skip if different map or no position
                
                # Calculate distance
                dx = abs(other_position["x"] - center_position["x"])
                dy = abs(other_position["y"] - center_position["y"])
                
                # Use Manhattan distance for simplicity (good enough for chat range)
                if dx <= range_tiles and dy <= range_tiles:
                    nearby_players.append({
                        "player_id": other_player_id,
                        "username": state_manager.get_username_by_id(other_player_id),
                        "x": other_position["x"],
                        "y": other_position["y"],
                        "map_id": other_position["map_id"]
                    })
            
            return nearby_players
            
        except Exception as e:
            logger.error(
                "Error getting nearby players",
                extra={
                    "player_id": player_id,
                    "range_tiles": range_tiles,
                    "error": str(e),
                }
            )
            return []

    @staticmethod
    async def validate_player_position_access(
        player_id: int, requested_map_id: str, requested_x: int, requested_y: int
    ) -> bool:
        """
        Validate that a player can access the requested position (security check).

        Used to prevent players from requesting chunks or performing actions
        on maps/positions they shouldn't have access to.

        Args:
            player_id: Player ID making the request
            requested_map_id: Map ID being requested
            requested_x: X coordinate being requested  
            requested_y: Y coordinate being requested

        Returns:
            True if player can access this position, False otherwise
        """
        # Get player's actual position
        actual_position = await PlayerService.get_player_position(player_id)
        if not actual_position:
            logger.warning(
                "Position access validation failed - player not online",
                extra={"player_id": player_id}
            )
            return False
        
        # Must be on the same map
        if actual_position["map_id"] != requested_map_id:
            logger.warning(
                "Position access validation failed - wrong map",
                extra={
                    "player_id": player_id,
                    "actual_map": actual_position["map_id"],
                    "requested_map": requested_map_id,
                }
            )
            return False
        
        # Calculate distance from player's actual position
        dx = abs(requested_x - actual_position["x"])
        dy = abs(requested_y - actual_position["y"])
        
        # Allow access within reasonable range (e.g., 5 chunks = 80 tiles)
        max_distance = 80  # tiles
        if dx > max_distance or dy > max_distance:
            logger.warning(
                "Position access validation failed - too far from player",
                extra={
                    "player_id": player_id,
                    "distance": {"dx": dx, "dy": dy},
                    "max_distance": max_distance,
                }
            )
            return False
        
        return True