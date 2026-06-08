"""Add comment column to bookings

Revision ID: 002
Revises: 001
Create Date: 2026-06-08
"""
from alembic import op
import sqlalchemy as sa

revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('bookings',
        sa.Column('comment', sa.String(), nullable=False, server_default=''))


def downgrade() -> None:
    op.drop_column('bookings', 'comment')
