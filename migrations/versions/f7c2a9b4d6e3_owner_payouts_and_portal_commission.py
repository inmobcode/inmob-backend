"""owner payouts (liquidaciones) and the portal commission switch

Revision ID: f7c2a9b4d6e3
Revises: d4a8f2c6e1b7
Create Date: 2026-10-15 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f7c2a9b4d6e3'
down_revision = 'd4a8f2c6e1b7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'owner_payouts',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('agency_id', sa.String(length=36), nullable=False),
        sa.Column('owner_id', sa.String(length=36), nullable=False),
        sa.Column('created_by', sa.String(length=36), nullable=True),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('paid_at', sa.Date(), nullable=False),
        sa.Column('method', sa.String(length=50), nullable=True),
        sa.Column('note', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['agency_id'], ['agencies.id']),
        sa.ForeignKeyConstraint(['owner_id'], ['property_owners.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('owner_payouts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_owner_payouts_agency_id'), ['agency_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_owner_payouts_owner_id'), ['owner_id'], unique=False)

    with op.batch_alter_table('agencies', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('owner_portal_shows_commission', sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade():
    with op.batch_alter_table('agencies', schema=None) as batch_op:
        batch_op.drop_column('owner_portal_shows_commission')

    op.drop_table('owner_payouts')
