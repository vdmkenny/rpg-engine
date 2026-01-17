"""
Game State Manager - Abstraction layer for player state operations.

This manager provides a unified interface for accessing and modifying player state
(inventory, equipment, skills) regardless of whether the player is online or offline.

For online players:
- State is read from and written to Valkey (fast in-memory access)
- Changes are marked dirty for periodic batch sync to PostgreSQL

For offline players:
- State is read from and written to PostgreSQL directly

Usage:
    # In WebSocket handlers (player is online)
    manager = GameStateManager(valkey=valkey_client)
    manager.register_online_player(player_id)
    inventory = await manager.get_inventory(player_id)

    # In REST endpoints for offline operations
    manager = GameStateManager()
    inventory = await manager.get_inventory(player_id, db=db_session)
"""

from typing import Dict, List, Optional, Set

from glide import GlideClient
from sqlalchemy.ext.asyncio import AsyncSession

from server.src.core.logging_config import get_logger
from server.src.services.player_state_valkey_service import PlayerStateValkeyService

logger = get_logger(__name__)


class GameStateManager:
    """
    Manages player game state with Valkey-first semantics for online players.

    This class abstracts the decision of whether to use Valkey or the database
    based on player online status. Services should use this manager instead of
    directly calling PlayerStateValkeyService or database queries.
    """

    def __init__(self, valkey: Optional[GlideClient] = None):
        """
        Initialize the GameStateManager.

        Args:
            valkey: Optional Valkey client. If provided, online player operations
                    will use Valkey. If None, all operations fall back to database.
        """
        self._valkey = valkey
        self._online_players: Set[int] = set()

    @property
    def valkey(self) -> Optional[GlideClient]:
        """Get the Valkey client."""
        return self._valkey

    def is_online(self, player_id: int) -> bool:
        """Check if a player is registered as online."""
        return player_id in self._online_players

    def register_online_player(self, player_id: int) -> None:
        """
        Register a player as online (state is in Valkey).

        Call this when a player connects after loading their state to Valkey.
        """
        self._online_players.add(player_id)
        logger.debug("Player registered as online", extra={"player_id": player_id})

    def unregister_online_player(self, player_id: int) -> None:
        """
        Unregister a player as online.

        Call this when a player disconnects after syncing their state to DB.
        """
        self._online_players.discard(player_id)
        logger.debug("Player unregistered as online", extra={"player_id": player_id})

    def get_online_player_ids(self) -> Set[int]:
        """Get all currently online player IDs."""
        return self._online_players.copy()

    # ==================== INVENTORY ====================

    async def get_inventory(
        self, player_id: int, db: Optional[AsyncSession] = None
    ) -> Dict[int, Dict]:
        """
        Get player's inventory.

        For online players, reads from Valkey.
        For offline players, reads from database (requires db session).

        Args:
            player_id: Player's database ID
            db: Database session (required for offline players)

        Returns:
            Dict mapping slot number to item data:
            {slot: {"item_id": int, "quantity": int, "durability": Optional[int]}}
        """
        if self._valkey and self.is_online(player_id):
            return await PlayerStateValkeyService.get_inventory(self._valkey, player_id)

        # Offline player - read from database
        if not db:
            raise ValueError("Database session required for offline player inventory")

        from server.src.models.item import PlayerInventory
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        result = await db.execute(
            select(PlayerInventory)
            .where(PlayerInventory.player_id == player_id)
            .options(selectinload(PlayerInventory.item))
        )
        inventory = {}
        for inv in result.scalars().all():
            inventory[inv.slot] = {
                "item_id": inv.item_id,
                "quantity": inv.quantity,
                "durability": inv.current_durability,
            }
        return inventory

    async def get_inventory_slot(
        self, player_id: int, slot: int, db: Optional[AsyncSession] = None
    ) -> Optional[Dict]:
        """
        Get a single inventory slot.

        Args:
            player_id: Player's database ID
            slot: Inventory slot number
            db: Database session (required for offline players)

        Returns:
            Item data dict or None if slot is empty
        """
        if self._valkey and self.is_online(player_id):
            return await PlayerStateValkeyService.get_inventory_slot(
                self._valkey, player_id, slot
            )

        # Offline player - read from database
        if not db:
            raise ValueError("Database session required for offline player")

        from server.src.models.item import PlayerInventory
        from sqlalchemy import select

        result = await db.execute(
            select(PlayerInventory)
            .where(PlayerInventory.player_id == player_id)
            .where(PlayerInventory.slot == slot)
        )
        inv = result.scalar_one_or_none()
        if not inv:
            return None
        return {
            "item_id": inv.item_id,
            "quantity": inv.quantity,
            "durability": inv.current_durability,
        }

    async def set_inventory_slot(
        self,
        player_id: int,
        slot: int,
        item_id: int,
        quantity: int,
        durability: Optional[int],
        db: Optional[AsyncSession] = None,
    ) -> None:
        """
        Set a single inventory slot.

        For online players, writes to Valkey and marks dirty.
        For offline players, writes directly to database.

        Args:
            player_id: Player's database ID
            slot: Inventory slot number
            item_id: Item's database ID
            quantity: Stack quantity
            durability: Current durability (None if no durability)
            db: Database session (required for offline players)
        """
        if self._valkey and self.is_online(player_id):
            await PlayerStateValkeyService.set_inventory_slot(
                self._valkey, player_id, slot, item_id, quantity, durability
            )
            return

        # Offline player - write to database
        if not db:
            raise ValueError("Database session required for offline player")

        from server.src.models.item import PlayerInventory
        from sqlalchemy import select

        result = await db.execute(
            select(PlayerInventory)
            .where(PlayerInventory.player_id == player_id)
            .where(PlayerInventory.slot == slot)
        )
        inv = result.scalar_one_or_none()

        if inv:
            inv.item_id = item_id
            inv.quantity = quantity
            inv.current_durability = durability
        else:
            inv = PlayerInventory(
                player_id=player_id,
                slot=slot,
                item_id=item_id,
                quantity=quantity,
                current_durability=durability,
            )
            db.add(inv)

        await db.flush()

    async def delete_inventory_slot(
        self, player_id: int, slot: int, db: Optional[AsyncSession] = None
    ) -> None:
        """
        Remove an inventory slot.

        For online players, deletes from Valkey and marks dirty.
        For offline players, deletes directly from database.

        Args:
            player_id: Player's database ID
            slot: Inventory slot number to remove
            db: Database session (required for offline players)
        """
        if self._valkey and self.is_online(player_id):
            await PlayerStateValkeyService.delete_inventory_slot(
                self._valkey, player_id, slot
            )
            return

        # Offline player - delete from database
        if not db:
            raise ValueError("Database session required for offline player")

        from server.src.models.item import PlayerInventory
        from sqlalchemy import delete

        await db.execute(
            delete(PlayerInventory)
            .where(PlayerInventory.player_id == player_id)
            .where(PlayerInventory.slot == slot)
        )
        await db.flush()

    async def get_free_inventory_slot(
        self, player_id: int, max_slots: int = 28, db: Optional[AsyncSession] = None
    ) -> Optional[int]:
        """
        Find the first free inventory slot.

        Args:
            player_id: Player's database ID
            max_slots: Maximum number of inventory slots
            db: Database session (required for offline players)

        Returns:
            First free slot number, or None if inventory is full
        """
        if self._valkey and self.is_online(player_id):
            return await PlayerStateValkeyService.get_free_inventory_slot(
                self._valkey, player_id, max_slots
            )

        # Offline player
        inventory = await self.get_inventory(player_id, db)
        used_slots = set(inventory.keys())

        for slot in range(max_slots):
            if slot not in used_slots:
                return slot

        return None

    async def get_inventory_count(
        self, player_id: int, db: Optional[AsyncSession] = None
    ) -> int:
        """
        Get the number of occupied inventory slots.

        Args:
            player_id: Player's database ID
            db: Database session (required for offline players)

        Returns:
            Number of slots with items
        """
        if self._valkey and self.is_online(player_id):
            return await PlayerStateValkeyService.get_inventory_count(
                self._valkey, player_id
            )

        inventory = await self.get_inventory(player_id, db)
        return len(inventory)

    # ==================== EQUIPMENT ====================

    async def get_equipment(
        self, player_id: int, db: Optional[AsyncSession] = None
    ) -> Dict[str, Dict]:
        """
        Get player's equipment.

        For online players, reads from Valkey.
        For offline players, reads from database (requires db session).

        Args:
            player_id: Player's database ID
            db: Database session (required for offline players)

        Returns:
            Dict mapping equipment slot name to item data:
            {slot: {"item_id": int, "quantity": int, "durability": Optional[int]}}
        """
        if self._valkey and self.is_online(player_id):
            return await PlayerStateValkeyService.get_equipment(self._valkey, player_id)

        # Offline player - read from database
        if not db:
            raise ValueError("Database session required for offline player equipment")

        from server.src.models.item import PlayerEquipment
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        result = await db.execute(
            select(PlayerEquipment)
            .where(PlayerEquipment.player_id == player_id)
            .options(selectinload(PlayerEquipment.item))
        )
        equipment = {}
        for eq in result.scalars().all():
            equipment[eq.equipment_slot] = {
                "item_id": eq.item_id,
                "quantity": eq.quantity,
                "durability": eq.current_durability,
            }
        return equipment

    async def get_equipment_slot(
        self, player_id: int, slot: str, db: Optional[AsyncSession] = None
    ) -> Optional[Dict]:
        """
        Get a single equipment slot.

        Args:
            player_id: Player's database ID
            slot: Equipment slot name (e.g., "head", "weapon")
            db: Database session (required for offline players)

        Returns:
            Item data dict or None if slot is empty
        """
        if self._valkey and self.is_online(player_id):
            return await PlayerStateValkeyService.get_equipment_slot(
                self._valkey, player_id, slot
            )

        # Offline player
        if not db:
            raise ValueError("Database session required for offline player")

        from server.src.models.item import PlayerEquipment
        from sqlalchemy import select

        result = await db.execute(
            select(PlayerEquipment)
            .where(PlayerEquipment.player_id == player_id)
            .where(PlayerEquipment.equipment_slot == slot)
        )
        eq = result.scalar_one_or_none()
        if not eq:
            return None
        return {
            "item_id": eq.item_id,
            "quantity": eq.quantity,
            "durability": eq.current_durability,
        }

    async def set_equipment_slot(
        self,
        player_id: int,
        slot: str,
        item_id: int,
        quantity: int,
        durability: Optional[int],
        db: Optional[AsyncSession] = None,
    ) -> None:
        """
        Set a single equipment slot.

        For online players, writes to Valkey and marks dirty.
        For offline players, writes directly to database.

        Args:
            player_id: Player's database ID
            slot: Equipment slot name (e.g., "head", "weapon")
            item_id: Item's database ID
            quantity: Stack quantity (usually 1, higher for ammo)
            durability: Current durability (None if no durability)
            db: Database session (required for offline players)
        """
        if self._valkey and self.is_online(player_id):
            await PlayerStateValkeyService.set_equipment_slot(
                self._valkey, player_id, slot, item_id, quantity, durability
            )
            return

        # Offline player - write to database
        if not db:
            raise ValueError("Database session required for offline player")

        from server.src.models.item import PlayerEquipment
        from sqlalchemy import select

        result = await db.execute(
            select(PlayerEquipment)
            .where(PlayerEquipment.player_id == player_id)
            .where(PlayerEquipment.equipment_slot == slot)
        )
        eq = result.scalar_one_or_none()

        if eq:
            eq.item_id = item_id
            eq.quantity = quantity
            eq.current_durability = durability
        else:
            eq = PlayerEquipment(
                player_id=player_id,
                equipment_slot=slot,
                item_id=item_id,
                quantity=quantity,
                current_durability=durability,
            )
            db.add(eq)

        await db.flush()

    async def delete_equipment_slot(
        self, player_id: int, slot: str, db: Optional[AsyncSession] = None
    ) -> None:
        """
        Remove an equipment slot.

        For online players, deletes from Valkey and marks dirty.
        For offline players, deletes directly from database.

        Args:
            player_id: Player's database ID
            slot: Equipment slot name to remove
            db: Database session (required for offline players)
        """
        if self._valkey and self.is_online(player_id):
            await PlayerStateValkeyService.delete_equipment_slot(
                self._valkey, player_id, slot
            )
            return

        # Offline player - delete from database
        if not db:
            raise ValueError("Database session required for offline player")

        from server.src.models.item import PlayerEquipment
        from sqlalchemy import delete

        await db.execute(
            delete(PlayerEquipment)
            .where(PlayerEquipment.player_id == player_id)
            .where(PlayerEquipment.equipment_slot == slot)
        )
        await db.flush()

    # ==================== SKILLS ====================

    async def get_skill(
        self, player_id: int, skill_name: str, db: Optional[AsyncSession] = None
    ) -> Optional[Dict]:
        """
        Get a single skill for a player.

        Args:
            player_id: Player's database ID
            skill_name: Skill name (e.g., "attack", "hitpoints")
            db: Database session (required for offline players)

        Returns:
            Skill data dict or None if not found
            {"skill_id": int, "level": int, "experience": int}
        """
        if self._valkey and self.is_online(player_id):
            return await PlayerStateValkeyService.get_skill(
                self._valkey, player_id, skill_name
            )

        # Offline player
        if not db:
            raise ValueError("Database session required for offline player")

        from server.src.models.skill import PlayerSkill, Skill
        from sqlalchemy import select

        result = await db.execute(
            select(PlayerSkill)
            .join(Skill)
            .where(PlayerSkill.player_id == player_id)
            .where(Skill.name == skill_name)
        )
        ps = result.scalar_one_or_none()
        if not ps:
            return None
        return {
            "skill_id": ps.skill_id,
            "level": ps.current_level,
            "experience": ps.experience,
        }

    async def get_all_skills(
        self, player_id: int, db: Optional[AsyncSession] = None
    ) -> Dict[str, Dict]:
        """
        Get all skills for a player.

        Args:
            player_id: Player's database ID
            db: Database session (required for offline players)

        Returns:
            Dict mapping skill name to skill data
        """
        if self._valkey and self.is_online(player_id):
            return await PlayerStateValkeyService.get_all_skills(
                self._valkey, player_id
            )

        # Offline player
        if not db:
            raise ValueError("Database session required for offline player")

        from server.src.models.skill import PlayerSkill, Skill
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        result = await db.execute(
            select(PlayerSkill)
            .where(PlayerSkill.player_id == player_id)
            .options(selectinload(PlayerSkill.skill))
        )
        skills = {}
        for ps in result.scalars().all():
            skills[ps.skill.name] = {
                "skill_id": ps.skill_id,
                "level": ps.current_level,
                "experience": ps.experience,
            }
        return skills

    async def set_skill(
        self,
        player_id: int,
        skill_name: str,
        skill_id: int,
        level: int,
        experience: int,
        db: Optional[AsyncSession] = None,
    ) -> None:
        """
        Update a skill for a player.

        For online players, writes to Valkey and marks dirty.
        For offline players, writes directly to database.

        Args:
            player_id: Player's database ID
            skill_name: Skill name (e.g., "attack", "hitpoints")
            skill_id: Skill's database ID
            level: Current skill level
            experience: Total experience points
            db: Database session (required for offline players)
        """
        if self._valkey and self.is_online(player_id):
            await PlayerStateValkeyService.set_skill(
                self._valkey, player_id, skill_name, skill_id, level, experience
            )
            return

        # Offline player - update database
        if not db:
            raise ValueError("Database session required for offline player")

        from server.src.models.skill import PlayerSkill
        from sqlalchemy import select

        result = await db.execute(
            select(PlayerSkill)
            .where(PlayerSkill.player_id == player_id)
            .where(PlayerSkill.skill_id == skill_id)
        )
        ps = result.scalar_one_or_none()

        if ps:
            ps.current_level = level
            ps.experience = experience
            await db.flush()
        else:
            # Skill record should already exist from player creation
            logger.warning(
                "Attempted to set non-existent skill",
                extra={
                    "player_id": player_id,
                    "skill_name": skill_name,
                    "skill_id": skill_id,
                },
            )


# Global instance for use across the application
# Initialized with Valkey client when server starts
_game_state_manager: Optional[GameStateManager] = None


def get_game_state_manager() -> GameStateManager:
    """Get the global GameStateManager instance."""
    global _game_state_manager
    if _game_state_manager is None:
        # Create a fallback instance without Valkey
        # This allows DB-only operations to work
        _game_state_manager = GameStateManager()
    return _game_state_manager


def init_game_state_manager(valkey: GlideClient) -> GameStateManager:
    """
    Initialize the global GameStateManager with a Valkey client.

    Should be called once during server startup.

    Args:
        valkey: Valkey client instance

    Returns:
        The initialized GameStateManager
    """
    global _game_state_manager
    _game_state_manager = GameStateManager(valkey=valkey)
    logger.info("GameStateManager initialized with Valkey client")
    return _game_state_manager
