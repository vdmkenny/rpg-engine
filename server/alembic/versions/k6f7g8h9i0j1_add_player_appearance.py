"""add player appearance column

Revision ID: k6f7g8h9i0j1
Revises: j5e6f7g8h9i0
Create Date: 2026-02-02 02:00:00.000000

Adds appearance JSON column to players table for paperdoll rendering.
Structure: {"skin_tone": str, "hair_style": str, "hair_color": str, "body_type": str}
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'k6f7g8h9i0j1'
down_revision: Union[str, None] = 'j5e6f7g8h9i0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add appearance JSON column (nullable - existing players will have NULL)
    op.add_column('players', sa.Column('appearance', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('players', 'appearance')
