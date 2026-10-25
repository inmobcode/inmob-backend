"""payments move from Stripe to Paddle: rename the customer and subscription ids

Revision ID: d9f5a2b7c3e1
Revises: c8e4f1a2b6d3
Create Date: 2026-10-26 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd9f5a2b7c3e1'
down_revision = 'c8e4f1a2b6d3'
branch_labels = None
depends_on = None


def _rename(old: str, new: str) -> None:
    # Separate batches: SQLite rebuilds the table on each, and an index can't name a column that isn't renamed yet.
    with op.batch_alter_table('agencies', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f(f'ix_agencies_{old}_customer_id'))
        batch_op.drop_index(batch_op.f(f'ix_agencies_{old}_subscription_id'))
    with op.batch_alter_table('agencies', schema=None) as batch_op:
        batch_op.alter_column(f'{old}_customer_id', new_column_name=f'{new}_customer_id', existing_type=sa.String(length=64), existing_nullable=True)
        batch_op.alter_column(f'{old}_subscription_id', new_column_name=f'{new}_subscription_id', existing_type=sa.String(length=64), existing_nullable=True)
    with op.batch_alter_table('agencies', schema=None) as batch_op:
        batch_op.create_index(batch_op.f(f'ix_agencies_{new}_customer_id'), [f'{new}_customer_id'], unique=False)
        batch_op.create_index(batch_op.f(f'ix_agencies_{new}_subscription_id'), [f'{new}_subscription_id'], unique=False)


def upgrade():
    _rename('stripe', 'paddle')


def downgrade():
    _rename('paddle', 'stripe')
