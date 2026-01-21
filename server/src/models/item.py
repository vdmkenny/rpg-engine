"""
SQLAlchemy models for items, inventory, equipment, and ground items.
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    String,
    Boolean,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Index,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base


class Item(Base):
    """
    Static definition of an item.

    Item metadata (display_name, stats, requirements) is defined in
    server/src/core/items.py. This table stores item data for database
    relationships and querying.
    """

    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Item classification
    category: Mapped[str] = mapped_column(String)  # ItemCategory value
    rarity: Mapped[str] = mapped_column(String, default="common")  # ItemRarity value
    equipment_slot: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # EquipmentSlot value

    # Item properties
    max_stack_size: Mapped[int] = mapped_column(default=1)  # 1 = not stackable
    is_two_handed: Mapped[bool] = mapped_column(Boolean, default=False)
    max_durability: Mapped[Optional[int]] = mapped_column(nullable=True)  # NULL = no durability
    is_indestructible: Mapped[bool] = mapped_column(Boolean, default=False)
    is_tradeable: Mapped[bool] = mapped_column(Boolean, default=True)

    # Requirements
    required_skill: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # RequiredSkill value
    required_level: Mapped[int] = mapped_column(default=1)

    # Ammunition
    ammo_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # AmmoType value

    # Value
    value: Mapped[int] = mapped_column(default=0)

    # Combat stats (offensive)
    attack_bonus: Mapped[int] = mapped_column(default=0)
    strength_bonus: Mapped[int] = mapped_column(default=0)
    ranged_attack_bonus: Mapped[int] = mapped_column(default=0)
    ranged_strength_bonus: Mapped[int] = mapped_column(default=0)
    magic_attack_bonus: Mapped[int] = mapped_column(default=0)
    magic_damage_bonus: Mapped[int] = mapped_column(default=0)

    # Combat stats (defensive)
    physical_defence_bonus: Mapped[int] = mapped_column(default=0)
    magic_defence_bonus: Mapped[int] = mapped_column(default=0)

    # Other stats
    health_bonus: Mapped[int] = mapped_column(default=0)
    speed_bonus: Mapped[int] = mapped_column(default=0)

    # Gathering stats
    mining_bonus: Mapped[int] = mapped_column(default=0)
    woodcutting_bonus: Mapped[int] = mapped_column(default=0)
    fishing_bonus: Mapped[int] = mapped_column(default=0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    inventory_items: Mapped[List["PlayerInventory"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )
    equipment_items: Mapped[List["PlayerEquipment"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )
    ground_items: Mapped[List["GroundItem"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Item(id={self.id}, name='{self.name}')>"

    __table_args__ = {"extend_existing": True}


class PlayerInventory(Base):
    """
    Player's inventory slots.

    Each row represents one slot in the player's inventory.
    Stackable items have quantity > 1, non-stackable items have quantity = 1.
    """

    __tablename__ = "player_inventory"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)

    slot: Mapped[int] = mapped_column()  # 0-27 for 28-slot inventory
    quantity: Mapped[int] = mapped_column(default=1)
    current_durability: Mapped[Optional[int]] = mapped_column(nullable=True)  # NULL if item has no durability

    # Relationships
    player: Mapped["Player"] = relationship(back_populates="inventory")
    item: Mapped["Item"] = relationship(back_populates="inventory_items")

    __table_args__ = (
        UniqueConstraint("player_id", "slot", name="_player_inventory_slot_uc"),
        {"extend_existing": True},
    )

    def __repr__(self):
        return f"<PlayerInventory(player_id={self.player_id}, slot={self.slot}, item_id={self.item_id}, qty={self.quantity})>"


class PlayerEquipment(Base):
    """
    Player's equipped items.

    Each row represents one equipment slot.
    Maximum 11 rows per player (one per EquipmentSlot).
    Ammunition is stackable - quantity tracks how many are equipped.
    """

    __tablename__ = "player_equipment"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    equipment_slot: Mapped[str] = mapped_column(String)  # EquipmentSlot value
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)

    quantity: Mapped[int] = mapped_column(default=1)  # For stackable items (ammo)
    current_durability: Mapped[Optional[int]] = mapped_column(nullable=True)

    # Relationships
    player: Mapped["Player"] = relationship(back_populates="equipment")
    item: Mapped["Item"] = relationship(back_populates="equipment_items")

    __table_args__ = (
        UniqueConstraint(
            "player_id", "equipment_slot", name="_player_equipment_slot_uc"
        ),
        {"extend_existing": True},
    )

    def __repr__(self):
        return f"<PlayerEquipment(player_id={self.player_id}, slot='{self.equipment_slot}', item_id={self.item_id}, qty={self.quantity})>"


class GroundItem(Base):
    """
    Items dropped on the ground.

    Items have a despawn timer based on rarity and a loot protection
    period where only the original dropper can pick them up.
    """

    __tablename__ = "ground_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)

    # Location
    map_id: Mapped[str] = mapped_column(String, index=True)
    x: Mapped[int] = mapped_column()
    y: Mapped[int] = mapped_column()

    # Item state
    quantity: Mapped[int] = mapped_column(default=1)
    current_durability: Mapped[Optional[int]] = mapped_column(nullable=True)

    # Ownership and timing
    dropped_by: Mapped[Optional[int]] = mapped_column(ForeignKey("players.id"), nullable=True, index=True)
    dropped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    public_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # When loot protection ends
    despawn_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)  # When item disappears

    # Relationships
    item: Mapped["Item"] = relationship(back_populates="ground_items")
    dropped_by_player: Mapped[Optional["Player"]] = relationship(back_populates="dropped_items")

    __table_args__ = (
        Index("ix_ground_items_location", "map_id", "x", "y"),
        {"extend_existing": True},
    )

    def __repr__(self):
        return f"<GroundItem(id={self.id}, item_id={self.item_id}, map='{self.map_id}', pos=({self.x},{self.y}))>"
