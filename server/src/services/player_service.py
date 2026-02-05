"""
Service for managing player operations.

Handles player creation, login/logout, and core player state management.
Returns Pydantic models throughout for type safety.
"""

import traceback
from typing import Optional, List
from fastapi import HTTPException, status

from ..core.config import settings
from ..core.security import get_password_hash
from ..schemas.player import (
    PlayerCreate, PlayerData, PlayerPosition, NearbyPlayer,
    PlayerRole, Direction, AnimationState
)
from ..core.logging_config import get_logger
from .game_state import get_player_state_manager
from .skill_service import SkillService

logger = get_logger(__name__)


class PlayerService:
    """Service for managing player operations."""

    @staticmethod
    async def create_player(
        player_data: PlayerCreate, 
        x: Optional[int] = None,
        y: Optional[int] = None,
        map_id: Optional[str] = None
    ) -> PlayerData:
        """
        Create a new player with proper initialization.
        
        Creates player record via PlayerStateManager and initializes all skills.

        Args:
            player_data: Player creation data
            x: Initial X position (default: 10)
            y: Initial Y position (default: 10)
            map_id: Initial map (default: "samplemap")

        Returns:
            PlayerData Pydantic model with player information

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
            final_x = x if x is not None else 10
            final_y = y if y is not None else 10
            final_map = map_id if map_id is not None else "samplemap"
            
            player_id = await player_mgr.create_player_record(
                username=player_data.username,
                hashed_password=hashed_password,
                x=final_x,
                y=final_y,
                map_id=final_map,
                current_hp=100,
                max_hp=100,
            )
            
            # Initialize skills for the player
            await SkillService.grant_all_skills_to_player(player_id)
            
            logger.info(
                "Player created",
                extra={"username": player_data.username, "player_id": player_id}
            )
            
            # Return as Pydantic model
            return PlayerData(
                id=player_id,
                username=player_data.username,
                x=final_x,
                y=final_y,
                map_id=final_map,
                current_hp=100,
                max_hp=100,
                role=PlayerRole.PLAYER,
                is_banned=False,
                is_online=False,
                facing_direction=Direction.SOUTH,
                animation_state=AnimationState.IDLE,
                total_level=0,
            )
                
        except IntegrityError:
            logger.warning(
                "Player creation failed - duplicate username",
                extra={"username": player_data.username}
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A player with this username already exists.",
            )
        except HTTPException:
            raise
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
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create player.",
            )

    @staticmethod
    async def get_player_by_username(username: str) -> Optional[PlayerData]:
        """
        Get player data by username.

        Args:
            username: Player username

        Returns:
            PlayerData if found, None otherwise
        """
        player_mgr = get_player_state_manager()
        player_record = await player_mgr.get_player_record_by_username(username)
        
        if not player_record:
            return None
        
        # player_record is already a PlayerData Pydantic model, just return it
        # Note: is_online status is fetched separately when needed
        return player_record

    @staticmethod
    async def get_player_by_id(player_id: int) -> Optional[PlayerData]:
        """
        Get player data by ID.

        Args:
            player_id: Player ID

        Returns:
            PlayerData if found, None otherwise
        """
        player_mgr = get_player_state_manager()
        player_record = await player_mgr.get_player_record_by_id(player_id)
        
        if not player_record:
            return None
        
        # player_record is already a PlayerData Pydantic model, just return it
        # Note: is_online status is fetched separately when needed
        return player_record

    @staticmethod
    async def get_player_position(player_id: int) -> Optional[PlayerPosition]:
        """
        Get player position for movement and visibility calculations.

        Args:
            player_id: Player ID

        Returns:
            PlayerPosition if online, None if offline or not found
        """
        player_mgr = get_player_state_manager()
        
        # Check if online first
        if not await player_mgr.is_online(player_id):
            return None
        
        position_data = await player_mgr.get_player_position(player_id)
        if not position_data:
            return None
        
        return PlayerPosition(
            player_id=player_id,
            x=position_data.get("x", 0),
            y=position_data.get("y", 0),
            map_id=position_data.get("map_id", ""),
            direction=Direction(position_data.get("facing_direction", "south")),
            is_moving=position_data.get("is_moving", False),
        )

    @staticmethod
    async def get_nearby_players(
        player_id: int, radius: int = 10
    ) -> List[NearbyPlayer]:
        """
        Get players within visibility radius of given player.

        Args:
            player_id: Center player ID
            radius: Visibility radius in tiles

        Returns:
            List of NearbyPlayer models within range
        """
        player_mgr = get_player_state_manager()
        
        # Get requesting player's position
        my_position = await player_mgr.get_player_position(player_id)
        if not my_position:
            return []
        
        my_x = my_position.get("x", 0)
        my_y = my_position.get("y", 0)
        my_map = my_position.get("map_id", "")
        
        nearby = []
        online_players = await player_mgr.get_all_online_player_ids()
        
        for other_id in online_players:
            if other_id == player_id:
                continue
            
            other_position = await player_mgr.get_player_position(other_id)
            if not other_position:
                continue
            
            other_x = other_position.get("x", 0)
            other_y = other_position.get("y", 0)
            other_map = other_position.get("map_id", "")
            
            # Check same map and within radius
            if other_map != my_map:
                continue
            
            distance = max(abs(other_x - my_x), abs(other_y - my_y))
            if distance <= radius:
                # Get username from manager's registry
                username = await player_mgr.get_username_for_player(other_id) or f"Player_{other_id}"
                
                nearby.append(NearbyPlayer(
                    player_id=other_id,
                    username=username,
                    x=other_x,
                    y=other_y,
                    direction=Direction(other_position.get("facing_direction", "south")),
                    animation_state=AnimationState(other_position.get("animation_state", "idle")),
                ))
        
        return nearby

    @staticmethod
    async def login_player(player_id: int) -> None:
        """
        Mark player as online and load their state.
        
        Args:
            player_id: Player database ID
        """
        player_mgr = get_player_state_manager()
        await player_mgr.register_online_player(player_id)
        
        # Get username for logging
        username = await player_mgr.get_username_for_player(player_id)
        logger.info("Player logged in", extra={"player_id": player_id, "username": username})

    @staticmethod
    async def logout_player(player_id: int) -> None:
        """
        Mark player as offline and persist their state.
        
        Args:
            player_id: Player database ID
        """
        player_mgr = get_player_state_manager()
        await player_mgr.unregister_online_player(player_id)
        logger.info("Player logged out", extra={"player_id": player_id})

    @staticmethod
    async def is_player_online(player_id: int) -> bool:
        """
        Check if player is currently online.
        
        Args:
            player_id: Player ID
            
        Returns:
            True if online, False otherwise
        """
        player_mgr = get_player_state_manager()
        return await player_mgr.is_online(player_id)

    @staticmethod
    async def get_players_on_map(map_id: str) -> List[NearbyPlayer]:
        """
        Get all online players on a specific map.
        
        Args:
            map_id: Map identifier
            
        Returns:
            List of NearbyPlayer models on the map
        """
        player_mgr = get_player_state_manager()
        online_players = await player_mgr.get_all_online_player_ids()
        
        players_on_map = []
        for player_id in online_players:
            position = await player_mgr.get_player_position(player_id)
            if not position:
                continue
            
            if position.get("map_id") == map_id:
                username = await player_mgr.get_username_for_player(player_id) or f"Player_{player_id}"
                players_on_map.append(NearbyPlayer(
                    player_id=player_id,
                    username=username,
                    x=position.get("x", 0),
                    y=position.get("y", 0),
                    direction=Direction(position.get("facing_direction", "south")),
                    animation_state=AnimationState(position.get("animation_state", "idle")),
                ))
        
        return players_on_map

    @staticmethod
    async def delete_player(player_id: int) -> bool:
        """
        Delete a player and all associated data.
        
        Args:
            player_id: Player ID to delete
            
        Returns:
            True if deleted, False if not found
        """
        player_mgr = get_player_state_manager()
        
        # Ensure player is offline
        if await player_mgr.is_online(player_id):
            await player_mgr.unregister_online_player(player_id)
        
        # Delete from database
        success = await player_mgr.delete_player_record(player_id)
        
        if success:
            logger.info("Player deleted", extra={"player_id": player_id})
        
        return success

    @staticmethod
    async def get_player_appearance(player_id: int) -> Optional[dict]:
        """
        Get player's appearance data from database.
        
        Args:
            player_id: Player ID
            
        Returns:
            Appearance dict if found, None otherwise
        """
        try:
            psm = get_player_state_manager()
            return await psm.get_player_appearance(player_id)
        except Exception as e:
            logger.error(
                "Error getting player appearance",
                extra={"player_id": player_id, "error": str(e)}
            )
            return None

    @staticmethod
    async def update_player_appearance(player_id: int, appearance_dict: dict) -> bool:
        """
        Update player's appearance data in database.
        
        Args:
            player_id: Player ID
            appearance_dict: Appearance data dict to save
            
        Returns:
            True if updated successfully, False otherwise
        """
        try:
            psm = get_player_state_manager()
            return await psm.update_player_appearance(player_id, appearance_dict)
        except Exception as e:
            logger.error(
                "Error updating player appearance",
                extra={"player_id": player_id, "error": str(e)}
            )
            return False
