"""
SQLAlchemy models for items, inventory, equipment, and ground items.
"""

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Index,
    func,
)
from sqlalchemy.orm import relationship
from .base import Base


class Item(Base):
    """
    Static definition of an item.

    Item metadata (display_name, stats, requirements) is defined in
    server/src/core/items.py. This table stores item data for database
    relationships and querying.
    """

    __tablename__ = "items"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False, index=True)
    display_name = Column(String, nullable=False)
    description = Column(String, nullable=True)

    # Item classification
    category = Column(String, nullable=False)  # ItemCategory value
    rarity = Column(String, nullable=False, default="common")  # ItemRarity value
    equipment_slot = Column(String, nullable=True)  # EquipmentSlot value

    # Item properties
    max_stack_size = Column(Integer, default=1, nullable=False)  # 1 = not stackable
    is_two_handed = Column(Boolean, default=False, nullable=False)
    max_durability = Column(Integer, nullable=True)  # NULL = no durability
    is_indestructible = Column(Boolean, default=False, nullable=False)
    is_tradeable = Column(Boolean, default=True, nullable=False)

    # Requirements
    required_skill = Column(String, nullable=True)  # RequiredSkill value
    required_level = Column(Integer, default=1, nullable=False)

    # Ammunition
    ammo_type = Column(String, nullable=True)  # AmmoType value

    # Value
    value = Column(Integer, default=0, nullable=False)

    # Combat stats (offensive)
    attack_bonus = Column(Integer, default=0, nullable=False)
    strength_bonus = Column(Integer, default=0, nullable=False)
    ranged_attack_bonus = Column(Integer, default=0, nullable=False)
    ranged_strength_bonus = Column(Integer, default=0, nullable=False)
    magic_attack_bonus = Column(Integer, default=0, nullable=False)
    magic_damage_bonus = Column(Integer, default=0, nullable=False)

    # Combat stats (defensive)
    physical_defence_bonus = Column(Integer, default=0, nullable=False)
    magic_defence_bonus = Column(Integer, default=0, nullable=False)

    # Other stats
    health_bonus = Column(Integer, default=0, nullable=False)
    speed_bonus = Column(Integer, default=0, nullable=False)

    # Gathering stats
    mining_bonus = Column(Integer, default=0, nullable=False)
    woodcutting_bonus = Column(Integer, default=0, nullable=False)
    fishing_bonus = Column(Integer, default=0, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    inventory_items = relationship(
        "PlayerInventory", back_populates="item", cascade="all, delete-orphan"
    )
    equipment_items = relationship(
        "PlayerEquipment", back_populates="item", cascade="all, delete-orphan"
    )
    ground_items = relationship(
        "GroundItem", back_populates="item", cascade="all, delete-orphan"
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

    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False, index=True)

    slot = Column(Integer, nullable=False)  # 0-27 for 28-slot inventory
    quantity = Column(Integer, default=1, nullable=False)
    current_durability = Column(Integer, nullable=True)  # NULL if item has no durability

    # Relationships
    player = relationship("Player", back_populates="inventory")
    item = relationship("Item", back_populates="inventory_items")

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

    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False, index=True)
    equipment_slot = Column(String, nullable=False)  # EquipmentSlot value
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False, index=True)

    quantity = Column(Integer, default=1, nullable=False)  # For stackable items (ammo)
    current_durability = Column(Integer, nullable=True)

    # Relationships
    player = relationship("Player", back_populates="equipment")
    item = relationship("Item", back_populates="equipment_items")

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

    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False, index=True)

    # Location
    map_id = Column(String, nullable=False, index=True)
    x = Column(Integer, nullable=False)
    y = Column(Integer, nullable=False)

    # Item state
    quantity = Column(Integer, default=1, nullable=False)
    current_durability = Column(Integer, nullable=True)

    # Ownership and timing
    dropped_by = Column(Integer, ForeignKey("players.id"), nullable=True, index=True)
    dropped_at = Column(DateTime(timezone=True), server_default=func.now())
    public_at = Column(DateTime(timezone=True), nullable=False)  # When loot protection ends
    despawn_at = Column(DateTime(timezone=True), nullable=False, index=True)  # When item disappears

    # Relationships
    item = relationship("Item", back_populates="ground_items")
    dropped_by_player = relationship("Player", back_populates="dropped_items")

    __table_args__ = (
        Index("ix_ground_items_location", "map_id", "x", "y"),
        {"extend_existing": True},
    )

    def __repr__(self):
        return f"<GroundItem(id={self.id}, item_id={self.item_id}, map='{self.map_id}', pos=({self.x},{self.y}))>"
