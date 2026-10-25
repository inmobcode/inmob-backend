"""agency plan and Stripe subscription

Existing agencies predate billing: they keep full access (plan "pro", status ACTIVE).

Revision ID: b7d3e9a1c4f2
Revises: b6d2f8a4c1e7
Create Date: 2026-10-24 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7d3e9a1c4f2'
down_revision = 'b6d2f8a4c1e7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('agencies', schema=None) as batch_op:
        batch_op.add_column(sa.Column('plan', sa.String(length=20), nullable=False, server_default='pro'))
        batch_op.add_column(sa.Column('trial_ends_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('stripe_customer_id', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('stripe_subscription_id', sa.String(length=64), nullable=True))
        batch_op.create_index(batch_op.f('ix_agencies_stripe_customer_id'), ['stripe_customer_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agencies_stripe_subscription_id'), ['stripe_subscription_id'], unique=False)
    op.execute("UPDATE agencies SET subscription_status = 'ACTIVE'")


def downgrade():
    with op.batch_alter_table('agencies', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_agencies_stripe_subscription_id'))
        batch_op.drop_index(batch_op.f('ix_agencies_stripe_customer_id'))
        batch_op.drop_column('stripe_subscription_id')
        batch_op.drop_column('stripe_customer_id')
        batch_op.drop_column('trial_ends_at')
        batch_op.drop_column('plan')
