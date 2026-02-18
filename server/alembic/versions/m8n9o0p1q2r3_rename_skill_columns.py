"""Rename skill columns to align with protocol

Revision ID: m8n9o0p1q2r3
Revises: l7m8n9o0p1q2
Create Date: 2025-01-17

"""
from alembic import op


revision = 'm8n9o0p1q2r3'
down_revision = '9e1a169531d4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column('player_skills', 'current_level', new_column_name='level')
    op.alter_column('player_skills', 'experience', new_column_name='xp')


def downgrade() -> None:
    op.alter_column('player_skills', 'level', new_column_name='current_level')
    op.alter_column('player_skills', 'xp', new_column_name='experience')
