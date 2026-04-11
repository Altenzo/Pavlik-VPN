"""add promo codes, ban fields, language

Revision ID: a1b2c3d4e5f6
Revises: 87f3a7374695, 7a7b7c7d7e7f
Create Date: 2026-04-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = ('87f3a7374695', '7a7b7c7d7e7f')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── promo_codes table ─────────────────────────────────────────
    op.create_table(
        'promo_codes',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(length=64), nullable=False),
        sa.Column('discount', sa.Integer(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('max_activations', sa.Integer(), nullable=True),
        sa.Column('current_activations', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_by', sa.BigInteger(), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
    )

    # ── promo_code_usages table ───────────────────────────────────
    op.create_table(
        'promo_code_usages',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('promo_code_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['promo_code_id'], ['promo_codes.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── New columns in users ──────────────────────────────────────
    op.add_column('users', sa.Column('is_banned', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('users', sa.Column('ban_reason', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('active_promo_code_id', sa.Integer(), nullable=True))
    op.add_column('users', sa.Column('language', sa.String(length=10), server_default='ru', nullable=False))


def downgrade() -> None:
    op.drop_column('users', 'language')
    op.drop_column('users', 'active_promo_code_id')
    op.drop_column('users', 'ban_reason')
    op.drop_column('users', 'is_banned')
    op.drop_table('promo_code_usages')
    op.drop_table('promo_codes')
