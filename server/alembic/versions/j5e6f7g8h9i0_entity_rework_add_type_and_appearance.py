"""entity rework - add entity_type, appearance, equipped_items, sprite_sheet_id

Revision ID: j5e6f7g8h9i0
Revises: i4d5e6f7g8h9
Create Date: 2026-02-02 01:30:00.000000

This migration supports the entity rework phase 1:
- Adds entity_type to distinguish humanoid_npc vs monster
- Adds sprite_sheet_id for monster sprite sheets
- Adds appearance JSON for humanoid paperdoll rendering
- Adds equipped_items JSON for humanoid equipment
- Removes old sprite_name column
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'j5e6f7g8h9i0'
down_revision: Union[str, None] = 'i4d5e6f7g8h9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add entity_type column (defaults to 'monster' for existing rows)
    op.add_column('entities', sa.Column('entity_type', sa.String(), nullable=False, server_default='monster'))
    
    # Add sprite_sheet_id column (nullable, only used by monsters)
    op.add_column('entities', sa.Column('sprite_sheet_id', sa.String(), nullable=True))
    
    # Add appearance JSON column (nullable, only used by humanoids)
    op.add_column('entities', sa.Column('appearance', sa.JSON(), nullable=True))
    
    # Add equipped_items JSON column (nullable, only used by humanoids)
    op.add_column('entities', sa.Column('equipped_items', sa.JSON(), nullable=True))
    
    # Remove old sprite_name column
    op.drop_column('entities', 'sprite_name')
    
    # Remove server defaults after initial values are set
    op.alter_column('entities', 'entity_type', server_default=None)


def downgrade() -> None:
    # Add back sprite_name column
    op.add_column('entities', sa.Column('sprite_name', sa.String(), nullable=False, server_default='default'))
    op.alter_column('entities', 'sprite_name', server_default=None)
    
    # Remove new columns
    op.drop_column('entities', 'equipped_items')
    op.drop_column('entities', 'appearance')
    op.drop_column('entities', 'sprite_sheet_id')
    op.drop_column('entities', 'entity_type')
