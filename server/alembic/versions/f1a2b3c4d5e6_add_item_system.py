"""Add item system with inventory, equipment, and ground items

Revision ID: f1a2b3c4d5e6
Revises: e8a4b2c3d5f6
Create Date: 2026-01-17 14:00:00.000000

This migration:
1. Creates the items table with all stat columns
2. Creates the player_inventory table for player bag slots
3. Creates the player_equipment table for equipped items
4. Creates the ground_items table for dropped items
5. Syncs all item definitions from ItemType enum to items table
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "e8a4b2c3d5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Stack size constants (base-2)
STACK_SIZE_SINGLE = 1
STACK_SIZE_MATERIALS = 64  # 2^6
STACK_SIZE_CONSUMABLES = 64  # 2^6
STACK_SIZE_AMMUNITION = 8192  # 2^13
STACK_SIZE_CURRENCY = 2147483647  # int max


# Item definitions to insert (synced from ItemType enum)
# Format: (name, display_name, description, category, rarity, equipment_slot,
#          max_stack_size, is_two_handed, max_durability, is_indestructible, is_tradeable,
#          required_skill, required_level, ammo_type, value,
#          attack_bonus, strength_bonus, ranged_attack_bonus, ranged_strength_bonus,
#          magic_attack_bonus, magic_damage_bonus, physical_defence_bonus, magic_defence_bonus,
#          health_bonus, speed_bonus, mining_bonus, woodcutting_bonus, fishing_bonus)
ITEMS = [
    # Weapons - Melee
    ("bronze_sword", "Bronze Sword", "A basic bronze sword.", "weapon", "common", "weapon",
     STACK_SIZE_SINGLE, False, 500, False, True, "attack", 1, None, 20,
     4, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    ("iron_sword", "Iron Sword", "A sturdy iron sword.", "weapon", "common", "weapon",
     STACK_SIZE_SINGLE, False, 750, False, True, "attack", 10, None, 50,
     10, 7, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    ("bronze_2h_sword", "Bronze Two-Handed Sword", "A large bronze sword requiring two hands.", "weapon", "common", "weapon",
     STACK_SIZE_SINGLE, True, 600, False, True, "attack", 1, None, 30,
     6, 8, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),

    # Weapons - Ranged
    ("shortbow", "Shortbow", "A basic wooden shortbow.", "weapon", "common", "weapon",
     STACK_SIZE_SINGLE, True, 500, False, True, "ranged", 1, None, 25,
     0, 0, 4, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    ("oak_shortbow", "Oak Shortbow", "A shortbow made from oak wood.", "weapon", "common", "weapon",
     STACK_SIZE_SINGLE, True, 650, False, True, "ranged", 10, None, 60,
     0, 0, 10, 6, 0, 0, 0, 0, 0, 0, 0, 0, 0),

    # Armor - Bronze (heavy, negative magic stats)
    ("bronze_helmet", "Bronze Helmet", "Basic head protection made of bronze.", "armor", "common", "head",
     STACK_SIZE_SINGLE, False, 400, False, True, "defence", 1, None, 15,
     0, 0, 0, 0, -1, 0, 3, 1, 0, 0, 0, 0, 0),
    ("bronze_platebody", "Bronze Platebody", "Heavy bronze chest armor.", "armor", "common", "body",
     STACK_SIZE_SINGLE, False, 600, False, True, "defence", 1, None, 40,
     0, 0, 0, 0, -3, 0, 8, 2, 5, -1, 0, 0, 0),
    ("bronze_platelegs", "Bronze Platelegs", "Heavy bronze leg armor.", "armor", "common", "legs",
     STACK_SIZE_SINGLE, False, 500, False, True, "defence", 1, None, 30,
     0, 0, 0, 0, -2, 0, 5, 1, 0, 0, 0, 0, 0),
    ("bronze_boots", "Bronze Boots", "Heavy bronze boots.", "armor", "common", "boots",
     STACK_SIZE_SINGLE, False, 300, False, True, "defence", 1, None, 12,
     0, 0, 0, 0, -1, 0, 1, 0, 0, 0, 0, 0, 0),
    ("bronze_gloves", "Bronze Gloves", "Heavy bronze gauntlets.", "armor", "common", "gloves",
     STACK_SIZE_SINGLE, False, 300, False, True, "defence", 1, None, 10,
     0, 0, 0, 0, -1, 0, 1, 0, 0, 0, 0, 0, 0),
    ("bronze_shield", "Bronze Shield", "A basic bronze shield.", "armor", "common", "shield",
     STACK_SIZE_SINGLE, False, 450, False, True, "defence", 1, None, 25,
     0, 0, 0, 0, -2, 0, 4, 1, 0, 0, 0, 0, 0),

    # Armor - Leather (balanced, no magic penalty)
    ("leather_body", "Leather Body", "Light leather chest armor.", "armor", "common", "body",
     STACK_SIZE_SINGLE, False, 400, False, True, "defence", 1, None, 25,
     0, 0, 2, 0, 0, 0, 4, 4, 0, 0, 0, 0, 0),
    ("leather_chaps", "Leather Chaps", "Light leather leg armor.", "armor", "common", "legs",
     STACK_SIZE_SINGLE, False, 350, False, True, "defence", 1, None, 18,
     0, 0, 1, 0, 0, 0, 2, 2, 0, 0, 0, 0, 0),

    # Tools
    ("bronze_pickaxe", "Bronze Pickaxe", "A basic pickaxe for mining ores.", "tool", "common", "weapon",
     STACK_SIZE_SINGLE, False, 500, False, True, "mining", 1, None, 20,
     2, 1, 0, 0, 0, 0, 0, 0, 0, 0, 5, 0, 0),
    ("iron_pickaxe", "Iron Pickaxe", "A sturdy iron pickaxe.", "tool", "common", "weapon",
     STACK_SIZE_SINGLE, False, 750, False, True, "mining", 10, None, 50,
     4, 2, 0, 0, 0, 0, 0, 0, 0, 0, 10, 0, 0),
    ("bronze_axe", "Bronze Axe", "A basic axe for chopping trees.", "tool", "common", "weapon",
     STACK_SIZE_SINGLE, False, 500, False, True, "woodcutting", 1, None, 20,
     3, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 5, 0),
    ("iron_axe", "Iron Axe", "A sturdy iron axe.", "tool", "common", "weapon",
     STACK_SIZE_SINGLE, False, 750, False, True, "woodcutting", 10, None, 50,
     6, 4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 10, 0),
    ("fishing_net", "Fishing Net", "A net for catching small fish.", "tool", "common", "weapon",
     STACK_SIZE_SINGLE, False, 300, False, True, "fishing", 1, None, 10,
     0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3),
    ("fishing_rod", "Fishing Rod", "A rod for catching fish with bait.", "tool", "common", "weapon",
     STACK_SIZE_SINGLE, False, 400, False, True, "fishing", 5, None, 20,
     0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 5),

    # Materials (stackable to 64)
    ("copper_ore", "Copper Ore", "Raw copper ore, used in smelting.", "material", "common", None,
     STACK_SIZE_MATERIALS, False, None, False, True, None, 1, None, 5,
     0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    ("tin_ore", "Tin Ore", "Raw tin ore, used in smelting.", "material", "common", None,
     STACK_SIZE_MATERIALS, False, None, False, True, None, 1, None, 5,
     0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    ("bronze_bar", "Bronze Bar", "A bar of bronze, made from copper and tin.", "material", "common", None,
     STACK_SIZE_MATERIALS, False, None, False, True, None, 1, None, 15,
     0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    ("iron_ore", "Iron Ore", "Raw iron ore, used in smelting.", "material", "common", None,
     STACK_SIZE_MATERIALS, False, None, False, True, None, 1, None, 12,
     0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    ("iron_bar", "Iron Bar", "A bar of iron.", "material", "common", None,
     STACK_SIZE_MATERIALS, False, None, False, True, None, 1, None, 30,
     0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    ("oak_logs", "Oak Logs", "Logs from an oak tree.", "material", "common", None,
     STACK_SIZE_MATERIALS, False, None, False, True, None, 1, None, 10,
     0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    ("willow_logs", "Willow Logs", "Logs from a willow tree.", "material", "common", None,
     STACK_SIZE_MATERIALS, False, None, False, True, None, 1, None, 20,
     0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    ("raw_shrimp", "Raw Shrimp", "A raw shrimp, needs cooking.", "material", "poor", None,
     STACK_SIZE_MATERIALS, False, None, False, True, None, 1, None, 3,
     0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    ("raw_trout", "Raw Trout", "A raw trout, needs cooking.", "material", "common", None,
     STACK_SIZE_MATERIALS, False, None, False, True, None, 1, None, 15,
     0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),

    # Consumables (stackable to 64)
    ("cooked_shrimp", "Cooked Shrimp", "A tasty cooked shrimp. Heals a small amount.", "consumable", "poor", None,
     STACK_SIZE_CONSUMABLES, False, None, False, True, None, 1, None, 5,
     0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    ("cooked_trout", "Cooked Trout", "A delicious cooked trout. Heals a moderate amount.", "consumable", "common", None,
     STACK_SIZE_CONSUMABLES, False, None, False, True, None, 1, None, 25,
     0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    ("bread", "Bread", "A loaf of bread. Heals a small amount.", "consumable", "poor", None,
     STACK_SIZE_CONSUMABLES, False, None, False, True, None, 1, None, 8,
     0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),

    # Ammunition (stackable to 8192)
    ("bronze_arrows", "Bronze Arrows", "Basic arrows with bronze tips.", "ammunition", "common", "ammo",
     STACK_SIZE_AMMUNITION, False, None, False, True, None, 1, "arrows", 1,
     0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    ("iron_arrows", "Iron Arrows", "Arrows with iron tips.", "ammunition", "common", "ammo",
     STACK_SIZE_AMMUNITION, False, None, False, True, None, 1, "arrows", 3,
     0, 0, 0, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0),

    # Currency (stackable to int max)
    ("gold_coins", "Gold Coins", "The standard currency.", "currency", "common", None,
     STACK_SIZE_CURRENCY, False, None, False, True, None, 1, None, 1,
     0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
]


def upgrade() -> None:
    # 1. Create items table
    op.create_table(
        "items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), unique=True, nullable=False, index=True),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("rarity", sa.String(), nullable=False, server_default="common"),
        sa.Column("equipment_slot", sa.String(), nullable=True),
        sa.Column("max_stack_size", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_two_handed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("max_durability", sa.Integer(), nullable=True),
        sa.Column("is_indestructible", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_tradeable", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("required_skill", sa.String(), nullable=True),
        sa.Column("required_level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("ammo_type", sa.String(), nullable=True),
        sa.Column("value", sa.Integer(), nullable=False, server_default="0"),
        # Combat stats (offensive)
        sa.Column("attack_bonus", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("strength_bonus", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ranged_attack_bonus", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ranged_strength_bonus", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("magic_attack_bonus", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("magic_damage_bonus", sa.Integer(), nullable=False, server_default="0"),
        # Combat stats (defensive)
        sa.Column("physical_defence_bonus", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("magic_defence_bonus", sa.Integer(), nullable=False, server_default="0"),
        # Other stats
        sa.Column("health_bonus", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("speed_bonus", sa.Integer(), nullable=False, server_default="0"),
        # Gathering stats
        sa.Column("mining_bonus", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("woodcutting_bonus", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fishing_bonus", sa.Integer(), nullable=False, server_default="0"),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # 2. Create player_inventory table
    op.create_table(
        "player_inventory",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id"), nullable=False, index=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False, index=True),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("current_durability", sa.Integer(), nullable=True),
        sa.UniqueConstraint("player_id", "slot", name="_player_inventory_slot_uc"),
    )

    # 3. Create player_equipment table
    op.create_table(
        "player_equipment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id"), nullable=False, index=True),
        sa.Column("equipment_slot", sa.String(), nullable=False),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False, index=True),
        sa.Column("current_durability", sa.Integer(), nullable=True),
        sa.UniqueConstraint("player_id", "equipment_slot", name="_player_equipment_slot_uc"),
    )

    # 4. Create ground_items table
    op.create_table(
        "ground_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False, index=True),
        sa.Column("map_id", sa.String(), nullable=False, index=True),
        sa.Column("x", sa.Integer(), nullable=False),
        sa.Column("y", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("current_durability", sa.Integer(), nullable=True),
        sa.Column("dropped_by", sa.Integer(), sa.ForeignKey("players.id"), nullable=True, index=True),
        sa.Column("dropped_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("public_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("despawn_at", sa.DateTime(timezone=True), nullable=False, index=True),
    )

    # Create composite index for location lookups
    op.create_index("ix_ground_items_location", "ground_items", ["map_id", "x", "y"])

    # 5. Insert all item definitions
    connection = op.get_bind()

    for item in ITEMS:
        (name, display_name, description, category, rarity, equipment_slot,
         max_stack_size, is_two_handed, max_durability, is_indestructible, is_tradeable,
         required_skill, required_level, ammo_type, value,
         attack_bonus, strength_bonus, ranged_attack_bonus, ranged_strength_bonus,
         magic_attack_bonus, magic_damage_bonus, physical_defence_bonus, magic_defence_bonus,
         health_bonus, speed_bonus, mining_bonus, woodcutting_bonus, fishing_bonus) = item

        connection.execute(
            sa.text("""
                INSERT INTO items (
                    name, display_name, description, category, rarity, equipment_slot,
                    max_stack_size, is_two_handed, max_durability, is_indestructible, is_tradeable,
                    required_skill, required_level, ammo_type, value,
                    attack_bonus, strength_bonus, ranged_attack_bonus, ranged_strength_bonus,
                    magic_attack_bonus, magic_damage_bonus, physical_defence_bonus, magic_defence_bonus,
                    health_bonus, speed_bonus, mining_bonus, woodcutting_bonus, fishing_bonus
                ) VALUES (
                    :name, :display_name, :description, :category, :rarity, :equipment_slot,
                    :max_stack_size, :is_two_handed, :max_durability, :is_indestructible, :is_tradeable,
                    :required_skill, :required_level, :ammo_type, :value,
                    :attack_bonus, :strength_bonus, :ranged_attack_bonus, :ranged_strength_bonus,
                    :magic_attack_bonus, :magic_damage_bonus, :physical_defence_bonus, :magic_defence_bonus,
                    :health_bonus, :speed_bonus, :mining_bonus, :woodcutting_bonus, :fishing_bonus
                )
            """),
            {
                "name": name,
                "display_name": display_name,
                "description": description,
                "category": category,
                "rarity": rarity,
                "equipment_slot": equipment_slot,
                "max_stack_size": max_stack_size,
                "is_two_handed": is_two_handed,
                "max_durability": max_durability,
                "is_indestructible": is_indestructible,
                "is_tradeable": is_tradeable,
                "required_skill": required_skill,
                "required_level": required_level,
                "ammo_type": ammo_type,
                "value": value,
                "attack_bonus": attack_bonus,
                "strength_bonus": strength_bonus,
                "ranged_attack_bonus": ranged_attack_bonus,
                "ranged_strength_bonus": ranged_strength_bonus,
                "magic_attack_bonus": magic_attack_bonus,
                "magic_damage_bonus": magic_damage_bonus,
                "physical_defence_bonus": physical_defence_bonus,
                "magic_defence_bonus": magic_defence_bonus,
                "health_bonus": health_bonus,
                "speed_bonus": speed_bonus,
                "mining_bonus": mining_bonus,
                "woodcutting_bonus": woodcutting_bonus,
                "fishing_bonus": fishing_bonus,
            },
        )


def downgrade() -> None:
    # Drop tables in reverse order (due to foreign key constraints)
    op.drop_index("ix_ground_items_location", table_name="ground_items")
    op.drop_table("ground_items")
    op.drop_table("player_equipment")
    op.drop_table("player_inventory")
    op.drop_table("items")
