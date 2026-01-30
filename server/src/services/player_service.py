"""
Service for managing player operations.

Handles player creation, login/logout, and core player state management.
"""

from typing import Optional, TYPE_CHECKING, Dict, Any, List
from fastapi import HTTPException, status

from ..core.config import settings
from ..core.security import get_password_hash
from ..models.player import Player
from ..schemas.player import PlayerCreate, PlayerRole
from ..core.logging_config import get_logger
from .game_state_manager import get_game_state_manager

if TYPE_CHECKING:
    from .game_state_manager import GameStateManager

logger = get_logger(__name__)


class PlayerService:
    """Service for managing player operations."""

    @staticmethod
    async def create_player(
        player_data: PlayerCreate, 
        x: Optional[int] = None,
        y: Optional[int] = None,
        map_id: Optional[str] = None
    ) -> Player:
        """
        Create a new player with proper initialization using GSM.
        
        Creates player record and initializes all skills with default values.

        Args:
            player_data: Player creation data

        Returns:
            Created Player instance

        Raises:
            HTTPException: If username already exists
        """
        gsm = get_game_state_manager()
        
        try:
            # Create player using GSM's complete creation method
            hashed_password = get_password_hash(player_data.password)
            player_complete_data = await gsm.create_player_complete(
                username=player_data.username,
                hashed_password=hashed_password,
                x=x or getattr(player_data, 'x', 10),
                y=y or getattr(player_data, 'y', 10),
                map_id=map_id or getattr(player_data, 'map_id', "samplemap"),
            )
            
            # Convert GSM data back to Player model
            player = Player()
            player.id = player_complete_data["id"]
            player.username = player_complete_data["username"]
            player.hashed_password = player_complete_data["hashed_password"]
            player.x_coord = player_complete_data.get("x_coord", 10)
            player.y_coord = player_complete_data.get("y_coord", 10)  
            player.map_id = player_complete_data.get("map_id", "samplemap")
            player.role = player_complete_data.get("role", "player")
            player.is_banned = player_complete_data.get("is_banned", False)
            player.timeout_until = player_complete_data.get("timeout_until")
            player.current_hp = player_complete_data.get("current_hp", 100)
            
            logger.info("Player created", extra={"username": player.username, "player_id": player.id})
            return player
                
        except Exception as e:
            # GSM will raise IntegrityError for duplicate username, convert to HTTP error
            logger.error(
                "Player creation failed", 
                extra={
                    "username": player_data.username, 
                    "error": str(e),
                    "error_type": type(e).__name__
                },
                exc_info=True
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A player with this username already exists.",
            )

    @staticmethod
    async def login_player(
        player: Player,
    ) -> None:
        """
        Handle player login process.
        
        Registers player as online and loads complete game state.

        Args:
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
        player_id: int,
        username: str,
    ) -> None:
        """
        Handle player logout process.
        
        Saves all player progress and cleans up active session.

        Args:
            player_id: Player ID
            username: Player username
        """        
        try:
            # Get the GameStateManager
            state_manager = get_game_state_manager()
            
            # Unregister player - this handles immediate sync to DB and cache cleanup
            await state_manager.unregister_online_player(player_id)
            
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
        username: str
    ) -> Optional[Player]:
        """
        Get player by username using GSM.

        Args:
            username: Player username

        Returns:
            Player if found, None otherwise
        """
        from .game_state_manager import get_game_state_manager
        
        gsm = get_game_state_manager()
        
        # Use GSM to get player by username
        player_data = await gsm.get_player_by_username(username)
        if not player_data:
            return None
        
        # Convert GSM data back to Player model
        player = Player()
        player.id = player_data["id"]
        player.username = player_data["username"]
        player.hashed_password = player_data["hashed_password"]
        player.x_coord = player_data.get("x_coord", 10)
        player.y_coord = player_data.get("y_coord", 10)  
        player.map_id = player_data.get("map_id", "samplemap")
        player.is_banned = player_data.get("is_banned", False)
        player.timeout_until = player_data.get("timeout_until")
        player.current_hp = player_data.get("current_hp", 100)
        
        return player

    @staticmethod
    async def get_player_by_id(
        player_id: int
    ) -> Optional[Player]:
        """
        Get player by ID using GSM.

        Args:
            player_id: Player ID

        Returns:
            Player if found, None otherwise
        """
        gsm = get_game_state_manager()
        
        # Use GSM to get complete player data
        player_data = await gsm.get_player_complete(player_id)
        if not player_data:
            return None
        
        # Convert GSM data back to Player model
        player = Player()
        player.id = player_data["id"]
        player.username = player_data["username"]
        player.hashed_password = player_data["hashed_password"]
        player.x_coord = player_data.get("x_coord", 10)
        player.y_coord = player_data.get("y_coord", 10)  
        player.map_id = player_data.get("map_id", "samplemap")
        player.role = player_data.get("role", "user")
        player.is_banned = player_data.get("is_banned", False)
        player.timeout_until = player_data.get("timeout_until")
        player.current_hp = player_data.get("current_hp", 100)
        
        return player

    @staticmethod
    def is_player_online(player_id: int) -> bool:
        """
        Check if a player is currently online.

        Args:
            player_id: Player ID to check

        Returns:
            True if player is online, False otherwise
        """
        from .game_state_manager import get_game_state_manager
        
        state_manager = get_game_state_manager()
        return state_manager.is_online(player_id)

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
        if not PlayerService.is_player_online(player_id):
            logger.debug(
                "Player position requested but player not online",
                extra={"player_id": player_id}
            )
            return None
        
        # Get player position from GSM
        return await state_manager.get_player_position(player_id)

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
            # Get all online players for proximity check
            from .connection_service import ConnectionService
            online_players = ConnectionService.get_online_player_ids()
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
                        "username": await PlayerService.get_username_by_player_id(other_player_id),
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

    @staticmethod
    async def get_player_role(
        player_id: int
    ) -> Optional[PlayerRole]:
        """
        Get player's role using GSM.

        Args:
            player_id: Player ID

        Returns:
            PlayerRole if player found, None otherwise
        """
        try:
            gsm = get_game_state_manager()
            permissions = await gsm.get_player_permissions(player_id)
            if permissions and permissions.get("role"):
                # Convert string role to PlayerRole enum
                role_str = permissions["role"]
                if role_str == "admin":
                    return PlayerRole.ADMIN
                elif role_str == "moderator":
                    return PlayerRole.MODERATOR
                else:
                    return PlayerRole.PLAYER
            return None
            
        except Exception as e:
            logger.error(
                "Error getting player role",
                extra={
                    "player_id": player_id,
                    "error": str(e),
                }
            )
            return None

    @staticmethod
    async def check_global_chat_permission(
        player_id: int
    ) -> bool:
        """
        Check if player has permission to send global chat messages using GSM.

        Args:
            player_id: Player ID

        Returns:
            True if player can send global messages, False otherwise
        """
        try:
            # Check if global chat is enabled
            if not settings.CHAT_GLOBAL_ENABLED:
                return False
            
            # Get player role using GSM
            player_role = await PlayerService.get_player_role(player_id)
            if not player_role:
                return False
            
            # Check if role is in allowed roles list
            allowed_roles = settings.CHAT_GLOBAL_ALLOWED_ROLES
            return player_role.value.upper() in [role.upper() for role in allowed_roles]
            
        except Exception as e:
            logger.error(
                "Error checking global chat permission",
                extra={
                    "player_id": player_id,
                    "error": str(e),
                }
            )
            return False

    @staticmethod
    async def get_player_data_by_id(
        player_id: int
    ) -> Optional[Player]:
        """
        Get complete player data including role using GSM (alias for get_player_by_id with explicit naming).

        Args:
            player_id: Player ID

        Returns:
            Complete Player instance if found, None otherwise
        """
        return await PlayerService.get_player_by_id(player_id)

    # =========================================================================
    # PLAYER IDENTITY LOOKUPS
    # =========================================================================
    
    @staticmethod
    async def get_username_by_player_id(player_id: int) -> Optional[str]:
        """
        Get username by player ID with automatic loading for offline players.
        
        Args:
            player_id: Player ID to look up
            
        Returns:
            Player username if found, None otherwise
        """
        state_manager = get_game_state_manager()
        
        # Check online players first for performance
        username = state_manager._id_to_username.get(player_id)
        if username:
            return username
        
        # Use GSM's auto-loading capability for offline players
        player_state = await state_manager.get_player_full_state(player_id)
        return player_state.get("username") if player_state else None