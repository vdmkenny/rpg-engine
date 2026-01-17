"""Add skills system with configurable XP scaling

Revision ID: d7f3a8b9c1e2
Revises: ab543bb48349
Create Date: 2026-01-17 12:00:00.000000

This migration:
1. Removes the max_level column from player_skills (now configured in config.yml)
2. Inserts the 8 base skills into the skills table
3. Grants all skills to existing players at level 1 with 0 XP
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d7f3a8b9c1e2"
down_revision: Union[str, None] = "ab543bb48349"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Define the skills to insert
SKILLS = [
    "attack",
    "strength",
    "defence",
    "mining",
    "fishing",
    "woodcutting",
    "cooking",
    "crafting",
]


def upgrade() -> None:
    # 1. Remove max_level column from player_skills
    op.drop_column("player_skills", "max_level")

    # 2. Insert base skills into skills table
    connection = op.get_bind()

    # Check which skills already exist
    existing_skills = connection.execute(
        sa.text("SELECT name FROM skills")
    ).fetchall()
    existing_skill_names = {row[0] for row in existing_skills}

    # Insert only missing skills
    for skill_name in SKILLS:
        if skill_name not in existing_skill_names:
            connection.execute(
                sa.text("INSERT INTO skills (name) VALUES (:name)"),
                {"name": skill_name},
            )

    # 3. Grant all skills to existing players
    # Get all skill IDs
    skill_rows = connection.execute(
        sa.text("SELECT id, name FROM skills")
    ).fetchall()
    skill_ids = {row[1]: row[0] for row in skill_rows}

    # Get all player IDs
    player_rows = connection.execute(
        sa.text("SELECT id FROM players")
    ).fetchall()
    player_ids = [row[0] for row in player_rows]

    # Insert player_skills for each player and skill combination
    for player_id in player_ids:
        for skill_name, skill_id in skill_ids.items():
            # Check if player already has this skill
            existing = connection.execute(
                sa.text(
                    "SELECT id FROM player_skills WHERE player_id = :player_id AND skill_id = :skill_id"
                ),
                {"player_id": player_id, "skill_id": skill_id},
            ).fetchone()

            if existing is None:
                connection.execute(
                    sa.text(
                        """
                        INSERT INTO player_skills (player_id, skill_id, current_level, experience)
                        VALUES (:player_id, :skill_id, 1, 0)
                        """
                    ),
                    {"player_id": player_id, "skill_id": skill_id},
                )


def downgrade() -> None:
    # 1. Add max_level column back to player_skills
    op.add_column(
        "player_skills",
        sa.Column("max_level", sa.Integer(), nullable=True),
    )

    # Set default value for max_level
    connection = op.get_bind()
    connection.execute(sa.text("UPDATE player_skills SET max_level = 1"))

    # Make it not nullable
    op.alter_column("player_skills", "max_level", nullable=False)

    # Note: We don't remove the skills or player_skills data on downgrade
    # as that could cause data loss. The skills will remain in the database.
