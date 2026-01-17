"""Add current_hp column to players table

Revision ID: h3c4d5e6f7g8
Revises: g2b3c4d5e6f7
Create Date: 2026-01-17 17:00:00.000000

This migration adds the current_hp column to track player health.
Hitpoints starts at level 10, so default current_hp is 10.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "h3c4d5e6f7g8"
down_revision: Union[str, None] = "g2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add current_hp column to players
    # Default to 10 (starting Hitpoints level)
    op.add_column(
        "players",
        sa.Column("current_hp", sa.Integer(), nullable=False, server_default="10"),
    )


def downgrade() -> None:
    # Remove current_hp column
    op.drop_column("players", "current_hp")
