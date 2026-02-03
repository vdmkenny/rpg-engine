import traceback
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from server.src.core.logging_config import get_logger
from server.src.core.config import settings
from server.src.core.metrics import (
    metrics,
    players_registered_total,
    auth_tokens_issued_total,
)
from server.src.core.security import create_access_token
from server.src.schemas.player import PlayerCreate, PlayerPublic
from server.src.schemas.token import Token
from server.src.services.map_service import get_map_manager
from server.src.services.skill_service import SkillService
from server.src.services.player_service import PlayerService
from server.src.services.authentication_service import AuthenticationService
from server.src.services.game_state import get_player_state_manager

router = APIRouter()
logger = get_logger(__name__)


@router.post(
    "/register",
    response_model=PlayerPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new player",
)
async def register_player(*, player_in: PlayerCreate):
    """
    Create a new player in the database.

    - **username**: The player's unique username.
    - **password**: The player's password.
    """
    try:
        # Get default spawn position
        map_manager = get_map_manager()
        default_map_id, spawn_x, spawn_y = map_manager.get_default_spawn_position()

        # Use PlayerService to create the player with spawn position
        db_player = await PlayerService.create_player(
            player_in, 
            x=spawn_x, 
            y=spawn_y, 
            map_id=default_map_id
        )

        logger.info(
            "New player registered",
            extra={
                "username": player_in.username,
                "spawn_position": {"x": spawn_x, "y": spawn_y},
                "map_id": default_map_id,
            },
        )
        metrics.track_auth_attempt("register", "success")
        players_registered_total.inc()

        return db_player

    except HTTPException:
        # Re-raise HTTP exceptions from service layer
        raise
    except Exception as e:
        logger.error(
            "Unexpected error during player registration",
            extra={
                "username": player_in.username,
                "error": str(e),
                "traceback": traceback.format_exc()
            }
        )
        metrics.track_auth_attempt("register", "failure")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during registration",
        )


@router.post("/login", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends()
):
    """
    OAuth2-compatible login, returns an access token.
    """
    try:
        # Authenticate user using service
        player = await AuthenticationService.authenticate_with_password(
            form_data.username, form_data.password
        )
    except PermissionError:
        # Player is banned
        logger.warning(
            "Login attempt failed - banned user",
            extra={"username": form_data.username, "reason": "banned"},
        )
        metrics.track_auth_attempt("login", "failure") 
        metrics.track_auth_failure("banned")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is banned",
        )
    except ValueError as e:
        # Player is timed out
        logger.warning(
            "Login attempt failed - timed out user",
            extra={"username": form_data.username, "reason": "timeout"},
        )
        metrics.track_auth_attempt("login", "failure") 
        metrics.track_auth_failure("timeout")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )

    if not player:
        logger.warning(
            "Login attempt failed",
            extra={"username": form_data.username, "reason": "invalid_credentials"},
        )
        metrics.track_auth_attempt("login", "failure") 
        metrics.track_auth_failure("invalid_credentials")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check server capacity (admins and moderators bypass capacity limits)
    if player.role not in ["ADMIN", "MODERATOR"]:
        player_mgr = get_player_state_manager()
        current_players = player_mgr.get_active_player_count()
        
        if current_players >= settings.MAX_PLAYERS:
            logger.warning(
                "Login attempt rejected due to server capacity",
                extra={
                    "username": form_data.username,
                    "current_players": current_players,
                    "max_players": settings.MAX_PLAYERS
                }
            )
            metrics.track_auth_attempt("login", "failure")
            metrics.track_auth_failure("capacity")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Server at capacity ({current_players}/{settings.MAX_PLAYERS} slots occupied). Please try again later.",
                headers={"Retry-After": "300"}
            )

    access_token_expires = timedelta(minutes=30)
    access_token = create_access_token(
        data={"sub": player.username}, expires_delta=access_token_expires
    )

    logger.info("Player logged in successfully", extra={"username": player.username})
    metrics.track_auth_attempt("login", "success")
    auth_tokens_issued_total.inc()
    return {"access_token": access_token, "token_type": "bearer"}
