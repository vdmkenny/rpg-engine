"""
Service for managing player operations.

Handles player creation, login/logout, and core player state management.
"""

import traceback
from typing import Optional, TYPE_CHECKING, Dict, Any, List
from fastapi import HTTPException, status

from ..core.config import settings
from ..core.security import get_password_hash
from ..models.player import Player
from ..schemas.player import PlayerCreate, PlayerRole
from ..core.logging_config import get_logger
from .game_state import get_player_state_manager, get_reference_data_manager
from .inventory_service import InventoryService
from .equipment_service import EquipmentService
from .skill_service import SkillService

logger = get_logger(__name__)


class PlayerService:
    """Service for managing player operations."""

    @staticmethod
    def _dict_to_player(player_data: Dict[str, Any]) -> Player:
        """
        Convert GSM dict data to Player model.
        
        This is a helper method to consolidate the repeated dict-to-model
        conversion logic used across multiple methods.
        
        Args:
            player_data: Player data dictionary from GSM
            
        Returns:
            Player model instance
        """
        player = Player()
        player.id = player_data["id"]
        player.username = player_data["username"]
        player.hashed_password = player_data.get("hashed_password", "")
        player.x_coord = player_data.get("x_coord", 10)
        player.y_coord = player_data.get("y_coord", 10)
        player.map_id = player_data.get("map_id", "samplemap")
        player.role = player_data.get("role", "player")
        player.is_banned = player_data.get("is_banned", False)
        player.timeout_until = player_data.get("timeout_until")
        player.current_hp = player_data.get("current_hp", 100)
        return player

    @staticmethod
    async def create_player(
        player_data: PlayerCreate, 
        x: Optional[int] = None,
        y: Optional[int] = None,
        map_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new player with proper initialization.
        
        Creates player record via PlayerStateManager and initializes all skills.

        Args:
            player_data: Player creation data

        Returns:
            Dict with player data including id

        Raises:
            HTTPException: If username already exists
        """
        from sqlalchemy.exc import IntegrityError
        
        player_mgr = get_player_state_manager()
        
        try:
            hashed_password = get_password_hash(player_data.password)
            
            # Check if username already exists
            if await player_mgr.username_exists(player_data.username):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A player with this username already exists.",
                )
            
            # Create player record via manager
            player_id = await player_mgr.create_player_record(
                username=player_data.username,
                hashed_password=hashed_password,
                x=x or getattr(player_data, 'x', 10),
                y=y or getattr(player_data, 'y', 10),
                map_id=map_id or getattr(player_data, 'map_id', "samplemap"),
                current_hp=100,
                max_hp=100,
            )
            
            # Initialize skills for the player
            await SkillService.grant_all_skills_to_player(player_id)
            
            logger.info("Player created", extra={"username": player_data.username, "player_id": player_id})
            return {
                "id": player_id,
                "username": player_data.username,
                "x": x or getattr(player_data, 'x', 10),
                "y": y or getattr(player_data, 'y', 10),
                "map_id": map_id or getattr(player_data, 'map_id', "samplemap"),
                "current_hp": 100,
                "max_hp": 100,
            }
                
        except IntegrityError:
            logger.warning("Player creation failed - duplicate username", extra={"username": player_data.username})
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A player with this username already exists.",
            )
        except Exception as e:
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
        
        Registers player as online.

        Args:
            player: Player instance
        """
        player_mgr = get_player_state_manager()
        
        # Register as online
        player_mgr.register_online_player(player.id, player.username)
        
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
        
        Cleans up active session.

        Args:
            player_id: Player ID
            username: Player username
        """        
        try:
            player_mgr = get_player_state_manager()
            
            # Unregister player
            await player_mgr.unregister_online_player(player_id)
            
            # Clean up player lock to prevent memory leaks
            try:
                from ..core.concurrency import get_player_lock_manager
                lock_manager = get_player_lock_manager()
                await lock_manager.cleanup_player_lock(player_id)
            except RuntimeError:
                pass
            
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
                    "traceback": traceback.format_exc(),
                }
            )
            raise

    @staticmethod
    async def get_player_by_username(
        username: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get player by username.

        Args:
            username: Player username

        Returns:
            Player dict if found, None otherwise
        """
        player_mgr = get_player_state_manager()
        return await player_mgr.get_player_record_by_username(username)

    @staticmethod
    async def get_player_by_id(
        player_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get player by ID.

        Args:
            player_id: Player ID

        Returns:
            Player dict if found, None otherwise
        """
        player_mgr = get_player_state_manager()
        return await player_mgr.get_player_record_by_id(player_id)

    @staticmethod
    def is_player_online(player_id: int) -> bool:
        """
        Check if a player is currently online.

        Args:
            player_id: Player ID to check

        Returns:
            True if player is online, False otherwise
        """
        player_mgr = get_player_state_manager()
        return player_mgr.is_online(player_id)

    @staticmethod
    async def get_player_position(player_id: int) -> Optional[Dict[str, Any]]:
        """
        Get player's current position and basic state from GameStateManager.

        Args:
            player_id: Player ID

        Returns:
            Dict with position data (x, y, map_id, etc.) or None if not online
        """
        player_mgr = get_player_state_manager()
        
        # Check if player is online
        if not PlayerService.is_player_online(player_id):
            logger.debug(
                "Player position requested but player not online",
                extra={"player_id": player_id}
            )
            return None
        
        # Get player position from PlayerStateManager
        return await player_mgr.get_player_position(player_id)

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
        player_mgr = get_player_state_manager()
        
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
                    continue
                    
                other_position = await player_mgr.get_player_position(other_player_id)
                if not other_position or other_position["map_id"] != center_position["map_id"]:
                    continue
                
                dx = abs(other_position["x"] - center_position["x"])
                dy = abs(other_position["y"] - center_position["y"])
                
                if dx <= range_tiles and dy <= range_tiles:
                    username = player_mgr.get_username_for_player(other_player_id)
                    if username:
                        nearby_players.append({
                            "player_id": other_player_id,
                            "username": username,
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
                    "traceback": traceback.format_exc(),
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
        Get player's role.

        Args:
            player_id: Player ID

        Returns:
            PlayerRole if player found, None otherwise
        """
        player_mgr = get_player_state_manager()
        
        try:
            player_record = await player_mgr.get_player_record_by_id(player_id)
            if not player_record:
                return None
            
            role_str = player_record.get("role", "player")
            if role_str == "admin":
                return PlayerRole.ADMIN
            elif role_str == "moderator":
                return PlayerRole.MODERATOR
            else:
                return PlayerRole.PLAYER
            
        except Exception as e:
            logger.error(
                "Error getting player role",
                extra={
                    "player_id": player_id,
                    "error": str(e),
                    "traceback": traceback.format_exc(),
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
                    "traceback": traceback.format_exc(),
                }
            )
            return False

    @staticmethod
    async def get_player_data_by_id(
        player_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get complete player data including role using GSM (alias for get_player_by_id with explicit naming).

        Args:
            player_id: Player ID

        Returns:
            Complete player dict if found, None otherwise
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
        player_mgr = get_player_state_manager()
        
        # Check online players first for performance
        username = player_mgr.get_username_for_player(player_id)
        if username:
            return username
        
        # Load from player record for offline players
        player_record = await player_mgr.get_player_record_by_id(player_id)
        if player_record:
            return player_record.get("username")
        return None

    @staticmethod
    async def delete_player(player_id: int) -> bool:
        """
        Completely delete a player from the game.
        
        Removes player from cache, online registry, and database.
        This is a destructive operation and cannot be undone.

        Args:
            player_id: Player ID to delete

        Returns:
            True if player was deleted, False if player didn't exist
        """
        player_mgr = get_player_state_manager()
        
        try:
            # Check if player exists
            player_record = await player_mgr.get_player_record_by_id(player_id)
            if not player_record:
                logger.debug("Player not found for deletion", extra={"player_id": player_id})
                return False
            
            # If online, unregister first
            if player_mgr.is_online(player_id):
                await player_mgr.unregister_online_player(player_id)
            
            # Delete from database via manager
            await player_mgr.delete_player_record(player_id)
            
            logger.info("Player deleted via service", extra={"player_id": player_id})
            return True
            
        except Exception as e:
            logger.error(
                "Error deleting player",
                extra={
                    "player_id": player_id,
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }
            )
            raise

    @staticmethod
    async def get_players_on_map(map_id: str) -> List[Dict[str, Any]]:
        """
        Get all online players on a specific map with their positions.
        
        Used by AI system to check for nearby players within aggro range.
        
        Args:
            map_id: Map identifier
            
        Returns:
            List of dicts with player_id, username, x, y for each online player on the map
        """
        from .connection_service import ConnectionService
        
        player_mgr = get_player_state_manager()
        online_player_ids = ConnectionService.get_online_player_ids()
        
        players_on_map: List[Dict[str, Any]] = []
        
        for player_id in online_player_ids:
            position = await player_mgr.get_player_position(player_id)
            if not position:
                continue
            
            if position.get("map_id") != map_id:
                continue
            
            username = await PlayerService.get_username_by_player_id(player_id)
            
            players_on_map.append({
                "player_id": player_id,
                "username": username,
                "x": position.get("x"),
                "y": position.get("y"),
            })
        
        return players_on_map
    
    @staticmethod
    async def get_player_appearance(player_id: int) -> Optional[Dict[str, Any]]:
        """
        Get player's appearance data from game state.
        
        Note: For online players only (welcome/join messages). 
        Returns appearance from player record.
        
        Args:
            player_id: Player ID
            
        Returns:
            Appearance dict or None if not found
        """
        player_mgr = get_player_state_manager()
        
        # Load appearance from player record
        player_record = await player_mgr.get_player_record_by_id(player_id)
        if player_record:
            appearance = player_record.get("appearance")
            return appearance if appearance else None
        return None