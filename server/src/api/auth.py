from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError

from server.src.core.database import get_db
from server.src.core.logging_config import get_logger
from server.src.core.metrics import (
    metrics,
    players_registered_total,
    auth_tokens_issued_total,
)
from server.src.core.security import (
    create_access_token,
    get_password_hash,
    verify_password,
)
from server.src.core.skills import HITPOINTS_START_LEVEL
from server.src.models.player import Player
from server.src.schemas.player import PlayerCreate, PlayerPublic
from server.src.schemas.token import Token
from server.src.services.map_service import map_manager
from server.src.services.skill_service import SkillService

router = APIRouter()
logger = get_logger(__name__)


@router.post(
    "/register",
    response_model=PlayerPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new player",
)
async def register_player(
    *, db: AsyncSession = Depends(get_db), player_in: PlayerCreate
) -> Player:
    """
    Create a new player in the database.

    - **username**: The player's unique username.
    - **password**: The player's password.
    """
    hashed_password = get_password_hash(player_in.password)

    # Get default spawn position
    default_map_id, spawn_x, spawn_y = map_manager.get_default_spawn_position()

    db_player = Player(
        username=player_in.username,
        hashed_password=hashed_password,
        x_coord=spawn_x,
        y_coord=spawn_y,
        map_id=default_map_id,
        current_hp=HITPOINTS_START_LEVEL,  # HP = Hitpoints level
    )

    db.add(db_player)
    try:
        await db.commit()
        await db.refresh(db_player)

        # Grant all skills to the new player
        await SkillService.grant_all_skills_to_player(db_player.id)

        # Refresh to get clean state (without lazy-loaded relationships that could
        # cause serialization issues with PlayerPublic response model)
        await db.refresh(db_player)

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
    except IntegrityError:
        await db.rollback()
        logger.warning(
            "Registration failed - username already exists",
            extra={"username": player_in.username},
        )
        metrics.track_auth_attempt("register", "failure")
        metrics.track_auth_failure("username_exists")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A player with this username already exists.",
        )

    return db_player


@router.post("/login", response_model=Token)
async def login_for_access_token(
    db: AsyncSession = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()
):
    """
    OAuth2-compatible login, returns an access token.
    """
    result = await db.execute(
        select(Player).where(Player.username == form_data.username)
    )
    player = result.scalar_one_or_none()

    if not player or not verify_password(form_data.password, player.hashed_password):
        logger.warning(
            "Login attempt failed",
            extra={"username": form_data.username, "reason": "invalid_credentials"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if player is banned
    if player.is_banned:
        logger.warning(
            "Banned player attempted login",
            extra={"username": form_data.username},
        )
        metrics.track_auth_attempt("login", "failure")
        metrics.track_auth_failure("banned")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is banned",
        )

    # Check if player is timed out
    if player.timeout_until:
        # Handle both timezone-aware and naive datetimes (SQLite vs PostgreSQL)
        timeout_until = player.timeout_until
        if timeout_until.tzinfo is None:
            timeout_until = timeout_until.replace(tzinfo=timezone.utc)
        if timeout_until > datetime.now(timezone.utc):
            logger.warning(
                "Timed out player attempted login",
                extra={"username": form_data.username, "timeout_until": str(player.timeout_until)},
            )
            metrics.track_auth_attempt("login", "failure")
            metrics.track_auth_failure("timeout")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Account is timed out until {player.timeout_until.isoformat()}",
            )

    access_token_expires = timedelta(minutes=30)
    access_token = create_access_token(
        data={"sub": player.username}, expires_delta=access_token_expires
    )

    logger.info("Player logged in successfully", extra={"username": player.username})
    metrics.track_auth_attempt("login", "success")
    auth_tokens_issued_total.inc()
    return {"access_token": access_token, "token_type": "bearer"}
