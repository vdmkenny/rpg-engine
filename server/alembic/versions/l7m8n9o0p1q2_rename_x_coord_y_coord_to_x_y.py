"""rename x_coord and y_coord to x and y

Revision ID: l7m8n9o0p1q2
Revises: k6f7g8h9i0j1
Create Date: 2026-02-04 00:00:00.000000

Renames x_coord → x and y_coord → y for consistency with Pydantic schemas.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'l7m8n9o0p1q2'
down_revision: Union[str, None] = 'k6f7g8h9i0j1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename columns to match Pydantic schema
    op.alter_column('players', 'x_coord', new_column_name='x')
    op.alter_column('players', 'y_coord', new_column_name='y')


def downgrade() -> None:
    # Revert column names
    op.alter_column('players', 'x', new_column_name='x_coord')
    op.alter_column('players', 'y', new_column_name='y_coord')
