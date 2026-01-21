"""
Service for managing player movement operations.

Handles movement validation, cooldown management, position calculations, and movement broadcasting.
"""

import time
from typing import Dict, List, Optional, Tuple, Any

from ..core.config import settings
from ..core.logging_config import get_logger
from .game_state_manager import get_game_state_manager
from .map_service import get_map_manager

logger = get_logger(__name__)


class MovementService:
    """Service for managing player movement operations."""

    # Movement cooldown in seconds to prevent spam
    MOVEMENT_COOLDOWN = 0.5  # 500ms between movements

    # Direction mappings
    DIRECTION_OFFSETS = {
        "up": (0, -1),
        "down": (0, 1),
        "left": (-1, 0),
        "right": (1, 0),
        "north": (0, -1),
        "south": (0, 1),
        "west": (-1, 0),
        "east": (1, 0),
    }

    @staticmethod
    async def validate_movement_cooldown(player_id: int) -> Dict[str, Any]:
        """
        Validate that player can move (not in cooldown).

        Args:
            player_id: Player ID requesting movement

        Returns:
            Dict with validation result and timing info
        """
        state_manager = get_game_state_manager()
        
        try:
            # Get player's last movement time from GSM
            last_movement_data = await state_manager.get_player_position(player_id)
            if not last_movement_data:
                return {
                    "can_move": False,
                    "reason": "Player not online",
                    "cooldown_remaining": 0
                }

            current_time = time.time()
            last_movement_time = last_movement_data.get("last_movement_time", 0)
            time_since_last = current_time - last_movement_time

            if time_since_last < MovementService.MOVEMENT_COOLDOWN:
                cooldown_remaining = MovementService.MOVEMENT_COOLDOWN - time_since_last
                logger.debug(
                    "Movement denied - cooldown active",
                    extra={
                        "player_id": player_id,
                        "cooldown_remaining": cooldown_remaining
                    }
                )
                return {
                    "can_move": False,
                    "reason": "Movement cooldown active",
                    "cooldown_remaining": cooldown_remaining
                }

            return {
                "can_move": True,
                "reason": None,
                "cooldown_remaining": 0
            }

        except Exception as e:
            logger.error(
                "Error validating movement cooldown",
                extra={
                    "player_id": player_id,
                    "error": str(e)
                }
            )
            return {
                "can_move": False,
                "reason": "Internal error",
                "cooldown_remaining": 0
            }

    @staticmethod
    def calculate_new_position(
        current_x: int, current_y: int, direction: str
    ) -> Tuple[int, int]:
        """
        Calculate new position based on current position and direction.

        Args:
            current_x: Current X coordinate
            current_y: Current Y coordinate
            direction: Movement direction

        Returns:
            Tuple of new (x, y) coordinates
        """
        direction_lower = direction.lower()
        
        if direction_lower not in MovementService.DIRECTION_OFFSETS:
            logger.warning(
                "Invalid movement direction",
                extra={"direction": direction}
            )
            return current_x, current_y

        dx, dy = MovementService.DIRECTION_OFFSETS[direction_lower]
        new_x = current_x + dx
        new_y = current_y + dy

        # Ensure coordinates don't go negative
        new_x = max(0, new_x)
        new_y = max(0, new_y)

        return new_x, new_y

    @staticmethod
    async def validate_movement_collision(
        map_id: str, from_x: int, from_y: int, to_x: int, to_y: int
    ) -> Dict[str, Any]:
        """
        Validate that the movement doesn't collide with obstacles.

        Args:
            map_id: Map ID
            from_x: Starting X coordinate
            from_y: Starting Y coordinate
            to_x: Target X coordinate
            to_y: Target Y coordinate

        Returns:
            Dict with validation result and collision info
        """
        map_manager = get_map_manager()
        
        try:
            # Check if the movement is valid (no collision)
            is_valid = map_manager.is_valid_move(map_id, from_x, from_y, to_x, to_y)
            
            if not is_valid:
                return {
                    "valid": False,
                    "reason": "Movement blocked by obstacle",
                    "collision_detected": True
                }
            
            return {
                "valid": True,
                "reason": None,
                "collision_detected": False
            }

        except Exception as e:
            logger.error(
                "Error validating movement collision",
                extra={
                    "map_id": map_id,
                    "from": {"x": from_x, "y": from_y},
                    "to": {"x": to_x, "y": to_y},
                    "error": str(e)
                }
            )
            return {
                "valid": False,
                "reason": "Internal error during collision check",
                "collision_detected": True
            }

    @staticmethod
    async def execute_movement(
        player_id: int, direction: str
    ) -> Dict[str, Any]:
        """
        Execute a player movement after all validations.

        Args:
            player_id: Player ID
            direction: Movement direction

        Returns:
            Dict with movement result and new position
        """
        try:
            state_manager = get_game_state_manager()
            
            # Validate direction first
            if not MovementService.is_valid_direction(direction):
                return {
                    "success": False,
                    "reason": "invalid_direction",
                    "new_position": None,
                    "current_position": None
                }

            # Check movement cooldown
            cooldown_check = await MovementService.validate_movement_cooldown(player_id)
            
            if not cooldown_check["can_move"]:
                # Get current position to include in error response
                current_position = await state_manager.get_player_position(player_id)
                return {
                    "success": False,
                    "reason": "rate_limited",
                    "new_position": None,
                    "current_position": current_position,
                    "cooldown_remaining": cooldown_check["cooldown_remaining"]
                }

            # Get current position
            current_position = await state_manager.get_player_position(player_id)
            
            if not current_position:
                return {
                    "success": False,
                    "reason": "player_not_online",
                    "new_position": None,
                    "current_position": None
                }

            current_x = current_position["x"]
            current_y = current_position["y"]
            map_id = current_position["map_id"]

            # Calculate new position
            new_x, new_y = MovementService.calculate_new_position(
                current_x, current_y, direction
            )

            # Validate collision
            collision_check = await MovementService.validate_movement_collision(
                map_id, current_x, current_y, new_x, new_y
            )

            if not collision_check["valid"]:
                return {
                    "success": False,
                    "reason": "blocked",
                    "new_position": None,
                    "current_position": current_position,
                    "collision": True
                }

            # Update position using MovementService method
            current_time = time.time()
            success = await MovementService.set_player_position(player_id, new_x, new_y, map_id)
            
            if not success:
                return {
                    "success": False,
                    "reason": "position_update_failed",
                    "new_position": None,
                    "current_position": current_position
                }
            
            # Update movement timestamp in GSM by updating the position data with timestamp
            old_position = {"x": current_x, "y": current_y, "map_id": map_id}
            new_position = {
                "x": new_x,
                "y": new_y,
                "map_id": map_id,
                "player_id": player_id,
                "timestamp": current_time
            }

            logger.info(
                "Player movement executed successfully",
                extra={
                    "player_id": player_id,
                    "direction": direction,
                    "from": {"x": current_x, "y": current_y},
                    "to": {"x": new_x, "y": new_y}
                }
            )

            return {
                "success": True,
                "reason": None,
                "new_position": new_position,
                "old_position": old_position,
                "collision": False
            }

        except Exception as e:
            logger.error(
                "Error executing movement",
                extra={
                    "player_id": player_id,
                    "direction": direction,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
            return {
                "success": False,
                "reason": "internal_error",
                "new_position": None,
                "current_position": None
            }

    @staticmethod
    def is_valid_direction(direction: str) -> bool:
        """
        Check if the direction is valid.

        Args:
            direction: Direction string to validate

        Returns:
            True if valid direction
        """
        return direction.lower() in MovementService.DIRECTION_OFFSETS

    @staticmethod
    async def get_movement_state(player_id: int) -> Dict[str, Any]:
        """
        Get player's current movement state and cooldown info.

        Args:
            player_id: Player ID

        Returns:
            Dict with movement state information
        """
        try:
            cooldown_check = await MovementService.validate_movement_cooldown(player_id)
            
            return {
                "can_move": cooldown_check["can_move"],
                "cooldown_remaining": cooldown_check["cooldown_remaining"],
                "movement_cooldown": MovementService.MOVEMENT_COOLDOWN
            }

        except Exception as e:
            logger.error(
                "Error getting movement state",
                extra={
                    "player_id": player_id,
                    "error": str(e)
                }
            )
            return {
                "can_move": False,
                "cooldown_remaining": 0,
                "movement_cooldown": MovementService.MOVEMENT_COOLDOWN
            }

    @staticmethod
    async def set_player_position(
        player_id: int, x: int, y: int, map_id: str, update_movement_time: bool = True
    ) -> bool:
        """
        Set player position in game state.

        Args:
            player_id: Player ID
            x: New X coordinate  
            y: New Y coordinate
            map_id: Map identifier
            update_movement_time: Whether to update last_move_time timestamp

        Returns:
            True if position was updated successfully
        """
        state_manager = get_game_state_manager()
        
        try:
            # Get current HP to preserve during position update
            current_state = await state_manager.get_player_full_state(player_id)
            if not current_state:
                # Player doesn't have existing state (new player) - use default HP values
                logger.debug(
                    "Initializing position for player without existing state",
                    extra={"player_id": player_id, "position": {"x": x, "y": y, "map_id": map_id}}
                )
                current_hp = 100  # Default HP for new players
                max_hp = 100      # Default max HP for new players
            else:
                # Player has existing state - preserve current HP values
                current_hp = current_state.get("current_hp", 100)
                max_hp = current_state.get("max_hp", 100)

            # Update complete state with new position
            await state_manager.set_player_full_state(
                player_id, x, y, map_id, int(current_hp), int(max_hp), update_movement_time
            )
            
            logger.debug(
                "Player position updated successfully",
                extra={
                    "player_id": player_id,
                    "position": {"x": x, "y": y, "map_id": map_id},
                    "movement_timestamp_updated": update_movement_time
                }
            )
            return True
            
        except Exception as e:
            logger.error(
                "Error setting player position",
                extra={
                    "player_id": player_id,
                    "position": {"x": x, "y": y, "map_id": map_id},
                    "error": str(e)
                }
            )
            return False

    @staticmethod
    async def initialize_player_position(
        player_id: int, x: int, y: int, map_id: str
    ) -> bool:
        """
        Initialize player position during connection setup.
        This is used during WebSocket connection initialization.

        Args:
            player_id: Player ID
            x: Initial X coordinate
            y: Initial Y coordinate  
            map_id: Map identifier

        Returns:
            True if position was initialized successfully
        """
        # Use set_player_position with update_movement_time=False for initialization
        return await MovementService.set_player_position(player_id, x, y, map_id, update_movement_time=False)

    @staticmethod
    async def teleport_player(
        player_id: int, x: int, y: int, map_id: str, validate_position: bool = True
    ) -> Dict[str, Any]:
        """
        Teleport player to a specific position (admin operation).

        Args:
            player_id: Player ID
            x: Target X coordinate
            y: Target Y coordinate
            map_id: Target map identifier
            validate_position: Whether to validate position (default True)

        Returns:
            Dict with teleport result
        """
        try:
            # Validate position if requested
            if validate_position:
                validation_result = await MovementService.validate_position(map_id, x, y)
                if not validation_result["valid"]:
                    return {
                        "success": False,
                        "reason": validation_result["reason"],
                        "new_position": None
                    }

            # Execute teleport
            success = await MovementService.set_player_position(player_id, x, y, map_id)
            
            if success:
                new_position = {
                    "x": x,
                    "y": y,
                    "map_id": map_id,
                    "player_id": player_id,
                    "timestamp": time.time()
                }
                
                logger.info(
                    "Player teleported successfully",
                    extra={
                        "player_id": player_id,
                        "destination": {"x": x, "y": y, "map_id": map_id}
                    }
                )
                
                return {
                    "success": True,
                    "reason": None,
                    "new_position": new_position
                }
            else:
                return {
                    "success": False,
                    "reason": "Failed to update player position",
                    "new_position": None
                }
                
        except Exception as e:
            logger.error(
                "Error during teleport operation",
                extra={
                    "player_id": player_id,
                    "destination": {"x": x, "y": y, "map_id": map_id},
                    "error": str(e)
                }
            )
            return {
                "success": False,
                "reason": "Internal error during teleport",
                "new_position": None
            }

    @staticmethod
    async def validate_position(map_id: str, x: int, y: int) -> Dict[str, Any]:
        """
        Validate that a position is valid on the map.

        Args:
            map_id: Map identifier
            x: X coordinate to validate
            y: Y coordinate to validate

        Returns:
            Dict with validation result
        """
        map_manager = get_map_manager()
        
        try:
            # Use the map manager to check if position is valid
            # For now, we'll use a simple bounds check - could be enhanced
            if x < 0 or y < 0:
                return {
                    "valid": False,
                    "reason": "Coordinates cannot be negative"
                }
            
            # Check if the position is valid (use same pattern as collision checking)
            # We'll do a simple check - see if moving to this position would be valid
            is_walkable = map_manager.is_valid_move(map_id, x, y, x, y)
            
            if not is_walkable:
                return {
                    "valid": False,
                    "reason": "Position is not walkable"
                }
            
            return {
                "valid": True,
                "reason": None
            }
            
        except Exception as e:
            logger.error(
                "Error validating position",
                extra={
                    "map_id": map_id,
                    "position": {"x": x, "y": y},
                    "error": str(e)
                }
            )
            return {
                "valid": False,
                "reason": "Internal error during position validation"
            }