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
        state_manager = get_game_state_manager()
        
        try:
            # Get current position
            current_position = await state_manager.get_player_position(player_id)
            if not current_position:
                return {
                    "success": False,
                    "reason": "Player not online",
                    "new_position": None
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
                    "reason": collision_check["reason"],
                    "new_position": None,
                    "collision": True
                }

            # Update position in GSM
            current_time = time.time()
            await state_manager.set_player_position(player_id, new_x, new_y, map_id)
            
            # Update movement timestamp (this would need to be added to GSM)
            # For now, we'll track it in the position data
            
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
                "collision": False
            }

        except Exception as e:
            logger.error(
                "Error executing movement",
                extra={
                    "player_id": player_id,
                    "direction": direction,
                    "error": str(e)
                }
            )
            return {
                "success": False,
                "reason": "Internal error during movement execution",
                "new_position": None
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