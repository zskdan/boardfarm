"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-05-17
"""
from alembic import op
import sqlalchemy as sa

revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'agents',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('url', sa.String(), nullable=False),
        sa.Column('last_seen', sa.DateTime(), nullable=False),
        sa.Column('agent_token', sa.String(), nullable=False, server_default=''),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.create_table(
        'boards',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=False, server_default=''),
        sa.Column('location', sa.String(), nullable=False, server_default=''),
        sa.Column('current_notes', sa.String(), nullable=False, server_default=''),
        sa.Column('agent_id', sa.String(), sa.ForeignKey('agents.id', ondelete='SET NULL'), nullable=True),
        sa.Column('host_ip', sa.String(), nullable=True),
        sa.Column('features', sa.String(), nullable=False, server_default='{}'),
        sa.Column('jtag_port', sa.Integer(), nullable=False, server_default='3121'),
        sa.Column('ssh_user', sa.String(), nullable=False, server_default='root'),
        sa.Column('ssh_port', sa.Integer(), nullable=False, server_default='22'),
        sa.Column('power_script', sa.String(), nullable=False, server_default=''),
        sa.Column('power_args', sa.String(), nullable=False, server_default='{}'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.create_table(
        'tools',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('board_id', sa.String(), sa.ForeignKey('boards.id', ondelete='CASCADE'), nullable=False),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('model', sa.String(), nullable=False, server_default=''),
        sa.Column('connection', sa.String(), nullable=False, server_default='usb'),
        sa.Column('connection_detail', sa.String(), nullable=False, server_default=''),
        sa.Column('notes', sa.String(), nullable=False, server_default=''),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'bookings',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('board_id', sa.String(), sa.ForeignKey('boards.id'), nullable=False),
        sa.Column('username', sa.String(), nullable=False),
        sa.Column('start_time', sa.DateTime(), nullable=False),
        sa.Column('end_time', sa.DateTime(), nullable=False),
        sa.Column('extended', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('release_reason', sa.String(), nullable=False, server_default=''),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('uq_active_booking', 'bookings', ['board_id'], unique=True,
                    sqlite_where=sa.text('active = 1'))


def downgrade() -> None:
    op.drop_index('uq_active_booking', table_name='bookings')
    op.drop_table('bookings')
    op.drop_table('tools')
    op.drop_table('boards')
    op.drop_table('agents')
