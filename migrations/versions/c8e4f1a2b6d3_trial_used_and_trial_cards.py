"""one free trial per agency and per card

Revision ID: c8e4f1a2b6d3
Revises: b7d3e9a1c4f2
Create Date: 2026-10-25 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c8e4f1a2b6d3'
down_revision = 'b7d3e9a1c4f2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('agencies', schema=None) as batch_op:
        batch_op.add_column(sa.Column('trial_used', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        'trial_cards',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('fingerprint', sa.String(length=64), nullable=False),
        sa.Column('agency_id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['agency_id'], ['agencies.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('fingerprint'),
    )
    with op.batch_alter_table('trial_cards', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_trial_cards_agency_id'), ['agency_id'], unique=False)


def downgrade():
    with op.batch_alter_table('trial_cards', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_trial_cards_agency_id'))
    op.drop_table('trial_cards')
    with op.batch_alter_table('agencies', schema=None) as batch_op:
        batch_op.drop_column('trial_used')
