"""add_referral_fields_and_stats

Revision ID: 7a7b7c7d7e7f
Revises: 034d80e2fb54
Create Date: 2026-03-31 01:28:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a7b7c7d7e7f'
down_revision: Union[str, Sequence[str], None] = '034d80e2fb54'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add referral_balance and total_earned columns to users table
    op.add_column('users', sa.Column('referral_balance', sa.Float(), nullable=False, server_default='0.0'))
    op.add_column('users', sa.Column('total_earned', sa.Float(), nullable=False, server_default='0.0'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'total_earned')
    op.drop_column('users', 'referral_balance')
