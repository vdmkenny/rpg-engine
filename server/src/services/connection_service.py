"""
Service for managing WebSocket connection lifecycle.

Handles player connection initialization, disconnection cleanup, and broadcasting.
"""

from typing import Dict, List, Optional, Any
import traceback

from ..core.logging_config import get_logger
from .game_state import get_player_state_manager
from .player_service import PlayerService
from .movement_service import MovementService

logger = get_logger(__name__)


class ConnectionService:
    """Service for managing WebSocket connection lifecycle."""

    @staticmethod
    async def initialize_player_connection(
        player_id: int, username: str, x: int, y: int, 
        map_id: str, current_hp: int, max_hp: int,
        appearance: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Initialize a player's WebSocket connection state.

        Sets up all necessary game state for a newly connected player.

        Args:
            player_id: Player ID
            username: Player username
            x: Player's X coordinate
            y: Player's Y coordinate
            map_id: Player's map ID
            current_hp: Player's current HP
            max_hp: Player's maximum HP
            appearance: Player appearance data to cache in Valkey

        Returns:
            Dict with initialization data
        """
        try:
            player_mgr = get_player_state_manager()

            # Use provided position and HP data to initialize player state
            position_data = {
                "x": x,
                "y": y,
                "map_id": map_id,
                "player_id": player_id
            }
            
            # Initialize position through MovementService
            position_success = await MovementService.initialize_player_position(
                player_id, x, y, map_id
            )
            
            if not position_success:
                logger.error(
                    "Failed to initialize player position during connection",
                    extra={"player_id": player_id, "position": {"x": x, "y": y, "map_id": map_id}}
                )

            # Set HP data through HpService
            from server.src.services.hp_service import HpService
            hp_data = {"current_hp": current_hp, "max_hp": max_hp}
            await HpService.set_hp(player_id, current_hp, max_hp)
            
            # Cache appearance data if provided
            if appearance:
                await player_mgr.cache_player_appearance(player_id, appearance)

            # Get nearby players for initial state
            nearby_players = await PlayerService.get_nearby_players(
                player_id, radius=80
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
                    "error": str(e),
                    "traceback": traceback.format_exc(),
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
                player_id, radius=80
            )

            notified_players = []
            for nearby_player in nearby_players:
                notified_players.append(nearby_player.player_id)

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
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }
            )
            return []

    @staticmethod
    async def handle_player_disconnect(
        player_id: int, player_map: Optional[str] = None, 
        manager = None, operation_rate_limiter = None
    ) -> Dict[str, Any]:
        """
        Handle player disconnection cleanup.

        Saves player state, notifies nearby players, and cleans up resources.

        Args:
            player_id: Disconnecting player ID
            player_map: Player's current map (optional)
            manager: Connection manager instance (optional)
            operation_rate_limiter: Rate limiter instance (optional)

        Returns:
            Dict with disconnection result
        """
        try:
            # Get username for logging if available
            player_mgr = get_player_state_manager()
            username = await player_mgr.get_username_for_player(player_id)

            # Get nearby players before cleanup for notifications
            nearby_players = await PlayerService.get_nearby_players(
                player_id, radius=80
            )

            # Save player state and logout
            await PlayerService.logout_player(player_id)

            # Cleanup any additional connection-specific resources
            await ConnectionService._cleanup_connection_resources(player_id)

            disconnection_data = {
                "player_id": player_id,
                "username": username,
                "nearby_players_to_notify": [p.player_id for p in nearby_players],
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
            # Get username for logging if possible
            username = None
            try:
                player_mgr = get_player_state_manager()
                username = await player_mgr.get_username_for_player(player_id)
            except Exception:
                pass

            logger.error(
                "Error handling player disconnect",
                extra={
                    "player_id": player_id,
                    "username": username,
                    "error": str(e),
                    "traceback": traceback.format_exc(),
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
                        "cleanup_error": str(cleanup_error),
                        "traceback": traceback.format_exc(),
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
            player_mgr = get_player_state_manager()
            
            # Check if player is registered as online
            is_online = await player_mgr.is_online(player_id)
            
            # Verify username matches
            stored_username = await player_mgr.get_username_for_player(player_id)
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
                    "traceback": traceback.format_exc(),
                }
            )
            return {
                "valid": False,
                "error": str(e)
            }

    @staticmethod
    async def get_existing_players_on_map(
        map_id: str, exclude_username: str
    ) -> List[Dict[str, Any]]:
        """
        Get data for existing players on a specific map, excluding one player.
        
        Args:
            map_id: Map to get players for
            exclude_username: Username to exclude from results
            
        Returns:
            List of player entity data for broadcasting
        """
        try:
            from server.src.api.connection_manager import ConnectionManager
            from server.src.services.visual_state_service import VisualStateService
            
            # Get connection manager instance (should be singleton)
            manager = ConnectionManager()
            existing_players = []
            
            # Get all connected usernames on the map
            connected_usernames = manager.connections_by_map.get(map_id, {})
            
            # In integration tests, this is usually empty, so return early
            if not connected_usernames:
                logger.debug(
                    "No existing players on map",
                    extra={"map_id": map_id, "exclude_username": exclude_username}
                )
                return existing_players
            
            # For each connected player (excluding the new one)
            for other_username in connected_usernames:
                if other_username != exclude_username:
                    # Get position using PlayerService
                    try:
                        # First get player ID for this username - use PlayerService to avoid direct DB access
                        player = await PlayerService.get_player_by_username(other_username)
                        
                        if player and await PlayerService.is_player_online(player.id):
                            position_data = await PlayerService.get_player_position(player.id)
                            if position_data:
                                # Get visual state via service layer
                                visual_data = await VisualStateService.get_player_visual_state(player.id)
                                
                                player_data = {
                                    "type": "player",
                                    "player_id": player.id,
                                    "username": other_username,
                                    "x": position_data.x,
                                    "y": position_data.y, 
                                    "map_id": position_data.map_id,
                                }
                                
                                # Add visual state if available
                                if visual_data:
                                    player_data["visual_hash"] = visual_data["visual_hash"]
                                    player_data["visual_state"] = visual_data["visual_state"]
                                
                                existing_players.append(player_data)
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
                    "traceback": traceback.format_exc(),
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

    # =========================================================================
    # ONLINE PLAYER MANAGEMENT
    # =========================================================================
    
    @staticmethod
    async def get_online_player_ids() -> set[int]:
        """
        Get set of all online player IDs.
        
        Returns:
            Set of online player IDs
        """
        player_mgr = get_player_state_manager()
        player_ids = await player_mgr.get_all_online_player_ids()
        return set(player_ids)
    
    @staticmethod
    async def get_online_player_id_by_username(username: str) -> Optional[int]:
        """
        Get player ID by username for currently connected players.
        
        Args:
            username: Player username to look up
            
        Returns:
            Player ID if online, None otherwise
        """
        player = await PlayerService.get_player_by_username(username)
        if player and await PlayerService.is_player_online(player.id):
            return player.id
        return None
    
    @staticmethod 
    async def get_all_online_players() -> List[Dict[str, Any]]:
        """
        Get all online players with basic info for broadcasting and administration.
        
        Returns:
            List of online player data with player_id and username
        """
        player_mgr = get_player_state_manager()
        online_players = []
        
        player_ids = await player_mgr.get_all_online_player_ids()
        for player_id in player_ids:
            username = await player_mgr.get_username_for_player(player_id)
            if username:
                online_players.append({
                    "player_id": player_id,
                    "username": username
                })
        
        return online_players
    
    @staticmethod
    async def is_player_online(player_id: int) -> bool:
        """
        Check if a player is currently connected.
        
        Args:
            player_id: Player ID to check
            
        Returns:
            True if player is online, False otherwise
        """
        player_mgr = get_player_state_manager()
        return await player_mgr.is_online(player_id)