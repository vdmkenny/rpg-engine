"""
Service for managing player hitpoints (HP).

Handles:
- Damage dealing
- Healing
- Death handling (drop items, broadcast, respawn)
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional, Tuple

from glide import GlideClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.src.core.config import settings
from server.src.core.skills import HITPOINTS_START_LEVEL
from server.src.models.player import Player
from server.src.services.equipment_service import EquipmentService
from server.src.services.ground_item_service import GroundItemService
from server.src.services.map_service import get_map_manager

logger = logging.getLogger(__name__)


@dataclass
class DamageResult:
    """Result of dealing damage to a player."""

    success: bool
    new_hp: int
    max_hp: int
    damage_dealt: int
    player_died: bool
    message: str


@dataclass
class HealResult:
    """Result of healing a player."""

    success: bool
    new_hp: int
    max_hp: int
    amount_healed: int
    message: str


@dataclass
class RespawnResult:
    """Result of respawning a player."""

    success: bool
    map_id: str
    x: int
    y: int
    new_hp: int
    message: str


class HpService:
    """Service for managing player HP."""

    @staticmethod
    async def get_hp_from_valkey(
        valkey: GlideClient, username: str
    ) -> Tuple[int, int]:
        """
        Get current and max HP from Valkey cache.

        Args:
            valkey: Valkey client
            username: Player's username

        Returns:
            Tuple of (current_hp, max_hp)
        """
        player_key = f"player:{username}"
        data = await valkey.hgetall(player_key)
        if data:
            current_hp = int(data.get(b"current_hp", b"10"))
            max_hp = int(data.get(b"max_hp", b"10"))
            return current_hp, max_hp
        return HITPOINTS_START_LEVEL, HITPOINTS_START_LEVEL

    @staticmethod
    async def set_hp_in_valkey(
        valkey: GlideClient, username: str, current_hp: int, max_hp: Optional[int] = None
    ) -> None:
        """
        Update HP in Valkey cache.

        Args:
            valkey: Valkey client
            username: Player's username
            current_hp: New current HP value
            max_hp: Optional new max HP value
        """
        player_key = f"player:{username}"
        update_data = {"current_hp": str(current_hp)}
        if max_hp is not None:
            update_data["max_hp"] = str(max_hp)
        await valkey.hset(player_key, update_data)

    @staticmethod
    async def deal_damage(
        db: AsyncSession,
        valkey: GlideClient,
        username: str,
        damage: int,
    ) -> DamageResult:
        """
        Deal damage to a player.

        Args:
            db: Database session
            valkey: Valkey client
            username: Player's username
            damage: Amount of damage to deal

        Returns:
            DamageResult with damage info and whether player died
        """
        if damage < 0:
            return DamageResult(
                success=False,
                new_hp=0,
                max_hp=0,
                damage_dealt=0,
                player_died=False,
                message="Damage must be non-negative",
            )

        # Get current HP from Valkey
        current_hp, max_hp = await HpService.get_hp_from_valkey(valkey, username)

        # Calculate new HP
        actual_damage = min(damage, current_hp)  # Can't deal more damage than HP
        new_hp = max(0, current_hp - damage)
        player_died = new_hp == 0

        # Update Valkey
        await HpService.set_hp_in_valkey(valkey, username, new_hp)

        logger.info(
            "Dealt damage to player",
            extra={
                "username": username,
                "damage": damage,
                "actual_damage": actual_damage,
                "old_hp": current_hp,
                "new_hp": new_hp,
                "player_died": player_died,
            },
        )

        return DamageResult(
            success=True,
            new_hp=new_hp,
            max_hp=max_hp,
            damage_dealt=actual_damage,
            player_died=player_died,
            message="Player died" if player_died else f"Dealt {actual_damage} damage",
        )

    @staticmethod
    async def heal(
        db: AsyncSession,
        valkey: GlideClient,
        username: str,
        amount: int,
    ) -> HealResult:
        """
        Heal a player.

        Args:
            db: Database session
            valkey: Valkey client
            username: Player's username
            amount: Amount to heal

        Returns:
            HealResult with healing info
        """
        if amount < 0:
            return HealResult(
                success=False,
                new_hp=0,
                max_hp=0,
                amount_healed=0,
                message="Heal amount must be non-negative",
            )

        # Get current HP from Valkey
        current_hp, max_hp = await HpService.get_hp_from_valkey(valkey, username)

        # Calculate healing (cap at max HP)
        new_hp = min(current_hp + amount, max_hp)
        amount_healed = new_hp - current_hp

        if amount_healed == 0:
            return HealResult(
                success=True,
                new_hp=new_hp,
                max_hp=max_hp,
                amount_healed=0,
                message="Already at full HP",
            )

        # Update Valkey
        await HpService.set_hp_in_valkey(valkey, username, new_hp)

        logger.info(
            "Healed player",
            extra={
                "username": username,
                "amount": amount,
                "amount_healed": amount_healed,
                "old_hp": current_hp,
                "new_hp": new_hp,
            },
        )

        return HealResult(
            success=True,
            new_hp=new_hp,
            max_hp=max_hp,
            amount_healed=amount_healed,
            message=f"Healed {amount_healed} HP",
        )

    @staticmethod
    async def set_hp(
        db: AsyncSession,
        valkey: GlideClient,
        username: str,
        new_hp: int,
    ) -> Tuple[int, int]:
        """
        Set player HP to a specific value.

        Args:
            db: Database session
            valkey: Valkey client
            username: Player's username
            new_hp: New HP value

        Returns:
            Tuple of (new_hp, max_hp)
        """
        _, max_hp = await HpService.get_hp_from_valkey(valkey, username)
        new_hp = max(0, min(new_hp, max_hp))
        await HpService.set_hp_in_valkey(valkey, username, new_hp)
        return new_hp, max_hp

    @staticmethod
    async def handle_death(
        db: AsyncSession,
        valkey: GlideClient,
        username: str,
    ) -> Tuple[str, int, int, int]:
        """
        Handle player death: drop all items at death location.

        Args:
            db: Database session
            valkey: Valkey client
            username: Player's username

        Returns:
            Tuple of (map_id, x, y, items_dropped) - death location and item count
        """
        # Get player position from Valkey
        player_key = f"player:{username}"
        data = await valkey.hgetall(player_key)

        if not data:
            logger.error(
                "No player data in Valkey for death handling",
                extra={"username": username},
            )
            return settings.DEFAULT_MAP, 0, 0, 0

        death_map_id = data.get(b"map_id", settings.DEFAULT_MAP.encode()).decode()
        death_x = int(data.get(b"x", b"0"))
        death_y = int(data.get(b"y", b"0"))
        player_id_str = data.get(b"player_id", b"0")
        player_id = int(player_id_str)

        if player_id == 0:
            # Need to look up player ID from database
            result = await db.execute(
                select(Player).where(Player.username == username)
            )
            player = result.scalar_one_or_none()
            if player:
                player_id = player.id
            else:
                logger.error(
                    "Could not find player for death handling",
                    extra={"username": username},
                )
                return death_map_id, death_x, death_y, 0

        # Drop all items at death location
        items_dropped = await GroundItemService.drop_player_items_on_death(
            db=db,
            player_id=player_id,
            map_id=death_map_id,
            x=death_x,
            y=death_y,
        )

        logger.info(
            "Player died",
            extra={
                "username": username,
                "player_id": player_id,
                "death_location": {"map_id": death_map_id, "x": death_x, "y": death_y},
                "items_dropped": items_dropped,
            },
        )

        return death_map_id, death_x, death_y, items_dropped

    @staticmethod
    async def respawn_player(
        db: AsyncSession,
        valkey: GlideClient,
        username: str,
    ) -> RespawnResult:
        """
        Respawn a player at the default spawn location with full HP.

        Args:
            db: Database session
            valkey: Valkey client
            username: Player's username

        Returns:
            RespawnResult with new location and HP
        """
        # Get spawn position
        map_manager = get_map_manager()
        spawn_map_id, spawn_x, spawn_y = map_manager.get_default_spawn_position()

        # Get player from database to calculate max HP
        result = await db.execute(
            select(Player).where(Player.username == username)
        )
        player = result.scalar_one_or_none()

        if not player:
            return RespawnResult(
                success=False,
                map_id=spawn_map_id,
                x=spawn_x,
                y=spawn_y,
                new_hp=HITPOINTS_START_LEVEL,
                message="Player not found",
            )

        # Calculate max HP (equipment was dropped, so just base HP now)
        max_hp = await EquipmentService.get_max_hp(db, player.id)

        # Update player position and HP in database
        player.map_id = spawn_map_id
        player.x_coord = spawn_x
        player.y_coord = spawn_y
        player.current_hp = max_hp  # Full HP on respawn
        await db.commit()

        # Update Valkey
        player_key = f"player:{username}"
        await valkey.hset(
            player_key,
            {
                "x": str(spawn_x),
                "y": str(spawn_y),
                "map_id": spawn_map_id,
                "current_hp": str(max_hp),
                "max_hp": str(max_hp),
            },
        )

        logger.info(
            "Player respawned",
            extra={
                "username": username,
                "spawn_location": {"map_id": spawn_map_id, "x": spawn_x, "y": spawn_y},
                "new_hp": max_hp,
            },
        )

        return RespawnResult(
            success=True,
            map_id=spawn_map_id,
            x=spawn_x,
            y=spawn_y,
            new_hp=max_hp,
            message="Respawned successfully",
        )

    @staticmethod
    async def full_death_sequence(
        db: AsyncSession,
        valkey: GlideClient,
        username: str,
        broadcast_callback=None,
    ) -> RespawnResult:
        """
        Execute the full death sequence:
        1. Drop all items at death location
        2. Broadcast PLAYER_DIED to nearby players
        3. Wait for respawn delay
        4. Respawn at spawn point with full HP
        5. Broadcast PLAYER_RESPAWN

        Args:
            db: Database session
            valkey: Valkey client
            username: Player's username
            broadcast_callback: Optional async callback(message_type, payload, username)
                for broadcasting messages to nearby players

        Returns:
            RespawnResult with respawn info
        """
        # Step 1: Handle death (drop items)
        death_map_id, death_x, death_y, items_dropped = await HpService.handle_death(
            db, valkey, username
        )

        # Step 2: Broadcast PLAYER_DIED
        if broadcast_callback:
            await broadcast_callback(
                "PLAYER_DIED",
                {
                    "username": username,
                    "x": death_x,
                    "y": death_y,
                    "map_id": death_map_id,
                    "items_dropped": items_dropped,
                },
                username,
            )

        # Step 3: Wait for respawn delay
        await asyncio.sleep(settings.DEATH_RESPAWN_DELAY)

        # Step 4: Respawn player
        respawn_result = await HpService.respawn_player(db, valkey, username)

        # Step 5: Broadcast PLAYER_RESPAWN
        if broadcast_callback and respawn_result.success:
            await broadcast_callback(
                "PLAYER_RESPAWN",
                {
                    "username": username,
                    "x": respawn_result.x,
                    "y": respawn_result.y,
                    "map_id": respawn_result.map_id,
                    "current_hp": respawn_result.new_hp,
                    "max_hp": respawn_result.new_hp,
                },
                username,
            )

        return respawn_result
