"""
Service for managing WebSocket connection lifecycle.

Handles player connection initialization, disconnection cleanup, and broadcasting.
"""

from typing import Dict, List, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging_config import get_logger
from .game_state_manager import get_game_state_manager
from .player_service import PlayerService

logger = get_logger(__name__)


class ConnectionService:
    """Service for managing WebSocket connection lifecycle."""

    @staticmethod
    async def initialize_player_connection(
        db: AsyncSession, player_id: int, username: str
    ) -> Dict[str, Any]:
        """
        Initialize a player's WebSocket connection state.

        Sets up all necessary game state for a newly connected player.

        Args:
            db: Database session
            player_id: Player ID
            username: Player username

        Returns:
            Dict with initialization data
        """
        try:
            state_manager = get_game_state_manager()

            # Get player's position data
            position_data = await PlayerService.get_player_position(player_id)
            if not position_data:
                # Fallback to database position if not in GSM
                from .player_service import PlayerService
                player = await PlayerService.get_player_by_id(db, player_id)
                if player:
                    position_data = {
                        "x": player.x_coord,
                        "y": player.y_coord,
                        "map_id": player.map_id,
                        "player_id": player_id
                    }
                    # Set initial position in GSM
                    await state_manager.set_player_position(
                        player_id, player.x_coord, player.y_coord, player.map_id
                    )
                else:
                    raise ValueError(f"Player {player_id} not found in database")

            # Get HP data
            hp_data = await state_manager.get_player_hp(player_id)
            if not hp_data:
                # Initialize HP if not set
                await state_manager.set_player_hp(player_id, 100, 100)
                hp_data = {"current_hp": 100, "max_hp": 100}

            # Get nearby players for initial state
            nearby_players = await PlayerService.get_nearby_players(
                player_id, range_tiles=80
            )

            initialization_data = {
                "player_id": player_id,
                "username": username,
                "position": position_data,
                "hp": hp_data,
                "nearby_players": nearby_players,
                "initialized": True
            }

            logger.info(
                "Player connection initialized",
                extra={
                    "player_id": player_id,
                    "username": username,
                    "position": position_data,
                    "nearby_count": len(nearby_players)
                }
            )

            return initialization_data

        except Exception as e:
            logger.error(
                "Error initializing player connection",
                extra={
                    "player_id": player_id,
                    "username": username,
                    "error": str(e)
                }
            )
            raise

    @staticmethod
    async def broadcast_player_join(
        player_id: int, username: str, position_data: Dict[str, Any]
    ) -> List[int]:
        """
        Broadcast player join to other nearby players.

        Args:
            player_id: Joining player ID
            username: Joining player username
            position_data: Player position data

        Returns:
            List of player IDs who were notified
        """
        try:
            # Get nearby players to notify
            nearby_players = await PlayerService.get_nearby_players(
                player_id, range_tiles=80
            )

            notified_players = []
            for nearby_player in nearby_players:
                notified_players.append(nearby_player["player_id"])

            if notified_players:
                logger.info(
                    "Broadcasting player join",
                    extra={
                        "joining_player": username,
                        "notified_players": len(notified_players)
                    }
                )
            
            return notified_players

        except Exception as e:
            logger.error(
                "Error broadcasting player join",
                extra={
                    "player_id": player_id,
                    "username": username,
                    "error": str(e)
                }
            )
            return []

    @staticmethod
    async def handle_player_disconnect(
        db: AsyncSession, player_id: int, username: str
    ) -> Dict[str, Any]:
        """
        Handle player disconnection cleanup.

        Saves player state, notifies nearby players, and cleans up resources.

        Args:
            db: Database session
            player_id: Disconnecting player ID
            username: Disconnecting player username

        Returns:
            Dict with disconnection result
        """
        try:
            # Get nearby players before cleanup for notifications
            nearby_players = await PlayerService.get_nearby_players(
                player_id, range_tiles=80
            )

            # Save player state and logout
            await PlayerService.logout_player(db, player_id, username)

            # Cleanup any additional connection-specific resources
            await ConnectionService._cleanup_connection_resources(player_id)

            disconnection_data = {
                "player_id": player_id,
                "username": username,
                "nearby_players_to_notify": [p["player_id"] for p in nearby_players],
                "cleanup_completed": True
            }

            logger.info(
                "Player disconnection handled",
                extra={
                    "player_id": player_id,
                    "username": username,
                    "notified_players": len(nearby_players)
                }
            )

            return disconnection_data

        except Exception as e:
            logger.error(
                "Error handling player disconnect",
                extra={
                    "player_id": player_id,
                    "username": username,
                    "error": str(e)
                }
            )
            # Still try to clean up even on error
            try:
                await ConnectionService._cleanup_connection_resources(player_id)
            except Exception as cleanup_error:
                logger.error(
                    "Error during cleanup after disconnect error",
                    extra={
                        "player_id": player_id,
                        "cleanup_error": str(cleanup_error)
                    }
                )
            
            return {
                "player_id": player_id,
                "username": username,
                "nearby_players_to_notify": [],
                "cleanup_completed": False,
                "error": str(e)
            }

    @staticmethod
    async def _cleanup_connection_resources(player_id: int) -> None:
        """
        Clean up connection-specific resources.

        Args:
            player_id: Player ID to clean up
        """
        try:
            # Any additional cleanup beyond what PlayerService.logout_player does
            # For now, this is mostly handled by PlayerService.logout_player
            # but we can add WebSocket-specific cleanup here if needed
            
            logger.debug(
                "Connection resources cleaned up",
                extra={"player_id": player_id}
            )

        except Exception as e:
            logger.warning(
                "Error cleaning up connection resources",
                extra={
                    "player_id": player_id,
                    "error": str(e)
                }
            )

    @staticmethod
    async def validate_connection_state(
        player_id: int, username: str
    ) -> Dict[str, Any]:
        """
        Validate the current state of a player connection.

        Args:
            player_id: Player ID to validate
            username: Expected username

        Returns:
            Dict with validation result
        """
        try:
            state_manager = get_game_state_manager()
            
            # Check if player is registered as online
            is_online = state_manager.is_online(player_id)
            
            # Verify username matches
            stored_username = state_manager.get_username_by_player_id(player_id)
            username_matches = stored_username == username

            # Get position data to verify state integrity
            position_data = await PlayerService.get_player_position(player_id)

            validation_result = {
                "valid": is_online and username_matches and position_data is not None,
                "is_online": is_online,
                "username_matches": username_matches,
                "has_position_data": position_data is not None,
                "position": position_data
            }

            if not validation_result["valid"]:
                logger.warning(
                    "Connection state validation failed",
                    extra={
                        "player_id": player_id,
                        "username": username,
                        "validation_result": validation_result
                    }
                )

            return validation_result

        except Exception as e:
            logger.error(
                "Error validating connection state",
                extra={
                    "player_id": player_id,
                    "username": username,
                    "error": str(e),
                    "error_type": type(e).__name__,
                }
            )
            return {
                "valid": False,
                "error": str(e)
            }

    @staticmethod
    async def get_existing_players_on_map(
        db: AsyncSession, map_id: str, exclude_username: str
    ) -> List[Dict[str, Any]]:
        """
        Get data for existing players on a specific map, excluding one player.
        
        Args:
            db: Database session
            map_id: Map to get players for
            exclude_username: Username to exclude from results
            
        Returns:
            List of player entity data for broadcasting
        """
        try:
            from server.src.api.connection_manager import ConnectionManager
            
            # Get connection manager instance (should be singleton)
            manager = ConnectionManager()
            existing_players = []
            
            # Get all connected usernames on the map
            for other_username in manager.connections_by_map.get(map_id, {}):
                if other_username != exclude_username:
                    # Get position using PlayerService instead of direct Valkey
                    try:
                        # First get player ID for this username
                        from server.src.models.player import Player
                        from sqlalchemy.future import select
                        
                        query = select(Player.id).where(Player.username == other_username)
                        result = await db.execute(query)
                        player_id = result.scalar_one_or_none()
                        
                        if player_id:
                            position_data = await PlayerService.get_player_position(player_id)
                            if position_data:
                                existing_players.append({
                                    "type": "player",
                                    "username": other_username,
                                    "x": position_data["x"],
                                    "y": position_data["y"], 
                                    "map_id": position_data["map_id"],
                                })
                    except Exception as e:
                        logger.warning(
                            "Failed to get position for existing player",
                            extra={
                                "username": other_username,
                                "map_id": map_id,
                                "error": str(e)
                            }
                        )
                        continue
            
            logger.debug(
                "Retrieved existing players on map",
                extra={
                    "map_id": map_id,
                    "exclude_username": exclude_username,
                    "player_count": len(existing_players)
                }
            )
            
            return existing_players

        except Exception as e:
            logger.error(
                "Error getting existing players on map",
                extra={
                    "map_id": map_id,
                    "exclude_username": exclude_username,
                    "error": str(e),
                    "error_type": type(e).__name__,
                }
            )
            return []

    @staticmethod
    def create_welcome_message(
        player_id: int, 
        username: str, 
        position_data: Dict[str, Any],
        hp_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create welcome message for newly connected player.

        Args:
            player_id: Player ID
            username: Player username
            position_data: Current position
            hp_data: Current HP data

        Returns:
            Welcome message data
        """
        return {
            "type": "welcome",
            "payload": {
                "player_id": player_id,
                "username": username,
                "current_hp": hp_data.get("current_hp", 100),
                "max_hp": hp_data.get("max_hp", 100),
                "x": position_data.get("x", 0),
                "y": position_data.get("y", 0),
                "map_id": position_data.get("map_id", "default")
            }
        }