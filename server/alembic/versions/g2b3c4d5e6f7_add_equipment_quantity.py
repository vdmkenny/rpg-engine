"""Add quantity column to player_equipment for stackable ammo

Revision ID: g2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-01-17 16:00:00.000000

This migration adds the quantity column to player_equipment table
to support stackable ammunition (arrows, bolts) being equipped.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "g2b3c4d5e6f7"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add quantity column to player_equipment
    # Default to 1 for existing equipment (non-stackable items)
    op.add_column(
        "player_equipment",
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    # Remove quantity column
    op.drop_column("player_equipment", "quantity")
