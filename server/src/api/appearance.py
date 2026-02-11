"""
API endpoints for character appearance customisation.

Provides REST endpoints for getting allowed appearance options.
These endpoints require authentication and return server-defined options
that the customisation UI should present to the player.
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status

from server.src.core.logging_config import get_logger
from server.src.core.security import get_current_user
from server.src.services.appearance_options_service import (
    get_player_appearance_options,
    is_value_allowed_for_player,
)

router = APIRouter()
logger = get_logger(__name__)


@router.get(
    "/appearance/options",
    response_model=Dict[str, Any],
    summary="Get player appearance customisation options",
    description="Returns all allowed appearance options for the authenticated player. "
                "The client should use these options to populate the customisation UI.",
)
async def get_appearance_options(
    current_user = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Get all appearance options available to players.
    
    Returns a structured response with categories (body_type, skin_tone, etc.)
    and their allowed option values. The client renders whatever the server
    returns without hardcoding any values.
    
    Args:
        current_user: Authenticated user (dependency injection)
        
    Returns:
        Dictionary with categories list containing field names, labels,
        and allowed option values with human-readable labels
        
    Raises:
        HTTPException: If user is not authenticated
    """
    logger.debug(
        "Appearance options requested",
        extra={
            "user_id": getattr(current_user, 'id', None),
            "username": getattr(current_user, 'username', None),
        }
    )
    
    options = get_player_appearance_options()
    
    logger.info(
        "Appearance options served",
        extra={
            "user_id": getattr(current_user, 'id', None),
            "category_count": len(options.get("categories", [])),
        }
    )
    
    return options
