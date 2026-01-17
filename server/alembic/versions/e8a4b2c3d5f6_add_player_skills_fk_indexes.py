"""Add indexes to player_skills foreign keys

Revision ID: e8a4b2c3d5f6
Revises: d7f3a8b9c1e2
Create Date: 2026-01-17 14:00:00.000000

This migration adds indexes to the player_id and skill_id columns
in the player_skills table for improved JOIN and lookup performance.
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e8a4b2c3d5f6"
down_revision: Union[str, None] = "d7f3a8b9c1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add indexes to foreign key columns for better JOIN performance
    op.create_index(
        "ix_player_skills_player_id",
        "player_skills",
        ["player_id"],
        unique=False,
    )
    op.create_index(
        "ix_player_skills_skill_id",
        "player_skills",
        ["skill_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_player_skills_skill_id", table_name="player_skills")
    op.drop_index("ix_player_skills_player_id", table_name="player_skills")
