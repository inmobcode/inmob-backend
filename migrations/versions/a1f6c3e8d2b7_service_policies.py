"""services reservation and cancellation policies

Revision ID: a1f6c3e8d2b7
Revises: c7a2e9f4b1d3
Create Date: 2026-10-14 18:30:00.000000

"""
import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = 'a1f6c3e8d2b7'
down_revision = 'c7a2e9f4b1d3'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('services', sa.Column('reservation_policy', sa.Text(), nullable=True))
    op.add_column('services', sa.Column('cancellation_policy', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('services', 'cancellation_policy')
    op.drop_column('services', 'reservation_policy')
