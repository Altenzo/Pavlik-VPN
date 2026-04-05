"""add vpn_uuid to users

Revision ID: a1b2c3d4e5f6
Revises: 1de4c83c38e4
Create Date: 2026-04-01 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '1de4c83c38e4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('vpn_uuid', sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'vpn_uuid')

