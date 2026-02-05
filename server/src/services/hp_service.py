"""
Service for managing player hitpoints (HP).

Handles:
- Damage dealing
- Healing
- Death handling (drop items, broadcast, respawn)

All state operations go through GameStateManager.
"""

import asyncio
from dataclasses import dataclass
from typing import Optional, Tuple

from server.src.core.config import settings
from server.src.core.logging_config import get_logger
from server.src.core.skills import HITPOINTS_START_LEVEL
from server.src.services.game_state import get_player_state_manager
from server.src.services.equipment_service import EquipmentService
from server.src.services.ground_item_service import GroundItemService
from server.src.services.map_service import get_map_manager

logger = get_logger(__name__)


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
    async def get_hp(player_id: int) -> Tuple[int, int]:
        """
        Get current and max HP from GSM.

        Args:
            player_id: Player's database ID

        Returns:
            Tuple of (current_hp, max_hp)
        """
        player_mgr = get_player_state_manager()
        hp_data = await player_mgr.get_player_hp(player_id)
        if hp_data:
            return hp_data["current_hp"], hp_data["max_hp"]
        return HITPOINTS_START_LEVEL, HITPOINTS_START_LEVEL

    @staticmethod
    async def set_hp(
        player_id: int, current_hp: int, max_hp: Optional[int] = None
    ) -> None:
        """
        Update HP via player state manager.

        Args:
            player_id: Player's database ID
            current_hp: New current HP value
            max_hp: Optional new max HP value
        """
        player_mgr = get_player_state_manager()
        await player_mgr.set_player_hp(player_id, current_hp, max_hp)

    @staticmethod
    async def deal_damage(
        player_id: int,
        damage: int,
    ) -> DamageResult:
        """
        Deal damage to a player.

        Args:
            player_id: Player's database ID
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

        # Get current HP from GSM
        current_hp, max_hp = await HpService.get_hp(player_id)

        # Calculate new HP
        actual_damage = min(damage, current_hp)  # Can't deal more damage than HP
        new_hp = max(0, current_hp - damage)
        player_died = new_hp == 0

        # Update via GSM
        await HpService.set_hp(player_id, new_hp)

        from .player_service import PlayerService
        player_data = await PlayerService.get_player_by_id(player_id)
        username = player_data.username if player_data else "unknown"

        logger.info(
            "Dealt damage to player",
            extra={
                "player_id": player_id,
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
        player_id: int,
        amount: int,
    ) -> HealResult:
        """
        Heal a player.

        Args:
            player_id: Player's database ID
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

        # Get current HP from GSM
        current_hp, max_hp = await HpService.get_hp(player_id)

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

        # Update via GSM
        await HpService.set_hp(player_id, new_hp)

        from .player_service import PlayerService
        player_data = await PlayerService.get_player_by_id(player_id)
        username = player_data.username if player_data else "unknown"

        logger.info(
            "Healed player",
            extra={
                "player_id": player_id,
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
    async def set_hp_value(
        player_id: int,
        new_hp: int,
    ) -> Tuple[int, int]:
        """
        Set player HP to a specific value.

        Args:
            player_id: Player's database ID
            new_hp: New HP value

        Returns:
            Tuple of (new_hp, max_hp)
        """
        _, max_hp = await HpService.get_hp(player_id)
        new_hp = max(0, min(new_hp, max_hp))
        await HpService.set_hp(player_id, new_hp)
        return new_hp, max_hp

    @staticmethod
    async def handle_death(
        player_id: int,
    ) -> Tuple[str, int, int, int]:
        """
        Handle player death: drop all items at death location.

        Args:
            player_id: Player's database ID

        Returns:
            Tuple of (map_id, x, y, items_dropped) - death location and item count
        """
        player_mgr = get_player_state_manager()
        
        # Get player position from player state manager
        player_state = await player_mgr.get_player_full_state(player_id)

        if not player_state:
            logger.error(
                "No player data in player state manager for death handling",
                extra={"player_id": player_id},
            )
            return settings.DEFAULT_MAP, 0, 0, 0

        death_map_id = player_state.get("map_id", settings.DEFAULT_MAP)
        death_x = player_state.get("x", 0)
        death_y = player_state.get("y", 0)
        username = player_state.get("username", "unknown")

        # Drop all items at death location
        items_dropped = await GroundItemService.drop_player_items_on_death(
            player_id=player_id,
            map_id=death_map_id,
            x=death_x,
            y=death_y,
        )

        logger.info(
            "Player died",
            extra={
                "player_id": player_id,
                "username": username,
                "death_location": {"map_id": death_map_id, "x": death_x, "y": death_y},
                "items_dropped": items_dropped,
            },
        )

        return death_map_id, death_x, death_y, items_dropped

    @staticmethod
    async def respawn_player(
        player_id: int,
    ) -> RespawnResult:
        """
        Respawn a player at the default spawn location with full HP.

        Args:
            player_id: Player's database ID

        Returns:
            RespawnResult with new location and HP
        """
        from .player_service import PlayerService
        player_data = await PlayerService.get_player_by_id(player_id)
        username = player_data.username if player_data else None
        
        if not username:
            return RespawnResult(
                success=False,
                map_id=settings.DEFAULT_MAP,
                x=0,
                y=0,
                new_hp=HITPOINTS_START_LEVEL,
                message="Player not found",
            )

        # Get spawn position
        spawn_map_id, spawn_x, spawn_y = HpService._get_spawn_position()
        current_hp, max_hp = await HpService.get_hp(player_id)

        player_mgr = get_player_state_manager()
        # Update player position and HP via player state manager
        await player_mgr.set_player_full_state(
            player_id,
            {
                "x": spawn_x,
                "y": spawn_y,
                "map_id": spawn_map_id,
                "current_hp": max_hp,
                "max_hp": max_hp,
            }
        )

        logger.info(
            "Player respawned",
            extra={
                "player_id": player_id,
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
        player_id: int,
        broadcast_callback=None,
    ) -> RespawnResult:
        """
        Execute the full death sequence:
        1. Drop all items at death location
        2. Broadcast EVENT_PLAYER_DIED to nearby players
        3. Wait for respawn delay
        4. Respawn at spawn point with full HP
        5. Broadcast EVENT_PLAYER_RESPAWN

        Args:
            player_id: Player's database ID
            broadcast_callback: Optional async callback(message_type, payload, username)
                for broadcasting messages to nearby players

        Returns:
            RespawnResult with respawn info
        """
        from .player_service import PlayerService
        player_data = await PlayerService.get_player_by_id(player_id)
        username = player_data.username if player_data else "unknown"

        # Step 1: Handle death (drop items)
        death_map_id, death_x, death_y, items_dropped = await HpService.handle_death(
            player_id
        )

        # Step 2: Broadcast EVENT_PLAYER_DIED
        if broadcast_callback:
            await broadcast_callback(
                "EVENT_PLAYER_DIED",
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
        respawn_result = await HpService.respawn_player(player_id)

        # Step 5: Broadcast EVENT_PLAYER_RESPAWN
        if broadcast_callback and respawn_result.success:
            await broadcast_callback(
                "EVENT_PLAYER_RESPAWN",
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

    @staticmethod
    def _get_spawn_position() -> Tuple[str, int, int]:
        """
        Get default spawn position from configuration.
        
        Returns:
            Tuple of (map_id, x, y) coordinates for respawn location
        """
        return settings.DEFAULT_MAP, settings.DEFAULT_SPAWN_X, settings.DEFAULT_SPAWN_Y

    @staticmethod
    async def batch_regenerate_hp(
        hp_updates: list[tuple[int, int]]
    ) -> int:
        """
        Batch HP regeneration for game loop tick processing.
        
        This method is optimized for high-frequency calls during the game loop
        and uses direct GSM access for performance. It does not log individual
        updates to avoid log spam.
        
        Args:
            hp_updates: List of (player_id, new_hp) tuples
            
        Returns:
            Number of players updated
        """
        if not hp_updates:
            return 0
        
        player_mgr = get_player_state_manager()
        updated = 0
        
        for player_id, new_hp in hp_updates:
            try:
                await player_mgr.set_player_hp(player_id, new_hp)
                updated += 1
            except Exception:
                # Silently skip failed updates to avoid disrupting game loop
                pass
        
        return updated
