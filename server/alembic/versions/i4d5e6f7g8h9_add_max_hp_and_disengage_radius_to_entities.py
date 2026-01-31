"""add max_hp and disengage_radius to entities

Revision ID: i4d5e6f7g8h9
Revises: f2f7f95b2638
Create Date: 2026-01-30 19:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'i4d5e6f7g8h9'
down_revision: Union[str, None] = 'f2f7f95b2638'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add max_hp column
    op.add_column('entities', sa.Column('max_hp', sa.Integer(), nullable=False, server_default='10'))
    
    # Add disengage_radius column
    op.add_column('entities', sa.Column('disengage_radius', sa.Integer(), nullable=False, server_default='0'))
    
    # Remove server defaults after initial values are set
    op.alter_column('entities', 'max_hp', server_default=None)
    op.alter_column('entities', 'disengage_radius', server_default=None)


def downgrade() -> None:
    # Remove added columns
    op.drop_column('entities', 'disengage_radius')
    op.drop_column('entities', 'max_hp')
