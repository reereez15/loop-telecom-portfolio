"""멤버십 등급 직접 구매(업그레이드) 테이블

Revision ID: a1f5c9e2b4d7
Revises: 6ddf5e18b8f4
Create Date: 2026-11-02 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1f5c9e2b4d7'
down_revision = '6ddf5e18b8f4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('membership_upgrades',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('from_tier_id', sa.Integer(), nullable=False),
    sa.Column('to_tier_id', sa.Integer(), nullable=False),
    sa.Column('amount', sa.Integer(), nullable=False),
    sa.Column('transaction_ref', sa.String(length=64), nullable=False),
    sa.Column('idempotency_key', sa.String(length=64), nullable=False),
    sa.Column('request_hash', sa.String(length=64), nullable=False),
    sa.Column('method', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('pg_tid', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id']),
    sa.ForeignKeyConstraint(['from_tier_id'], ['membership_tiers.id']),
    sa.ForeignKeyConstraint(['to_tier_id'], ['membership_tiers.id']),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('transaction_ref'),
    sa.UniqueConstraint('pg_tid'),
    sa.UniqueConstraint('user_id', 'idempotency_key', name='uq_membership_upgrade_idem')
    )
    with op.batch_alter_table('membership_upgrades', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_membership_upgrades_user_id'), ['user_id'], unique=False)


def downgrade():
    with op.batch_alter_table('membership_upgrades', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_membership_upgrades_user_id'))
    op.drop_table('membership_upgrades')
