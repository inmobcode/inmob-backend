"""inquiries read_at, for the dashboard's inbox

Revision ID: a1c4e7f9b2d3
Revises: f3b8c1d2a4e5
Create Date: 2026-10-12 23:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1c4e7f9b2d3'
down_revision = 'f3b8c1d2a4e5'
branch_labels = None
depends_on = None


def upgrade():
    # Null means "not read yet": existing inquiries show up as new in the inbox.
    with op.batch_alter_table('inquiries', schema=None) as batch_op:
        batch_op.add_column(sa.Column('read_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('inquiries', schema=None) as batch_op:
        batch_op.drop_column('read_at')
