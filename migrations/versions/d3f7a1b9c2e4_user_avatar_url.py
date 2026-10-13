"""user avatar url

Revision ID: d3f7a1b9c2e4
Revises: a1d5e8f2c7b3
Create Date: 2026-10-13 14:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd3f7a1b9c2e4'
down_revision = 'a1d5e8f2c7b3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('avatar_url', sa.String(length=500), nullable=True))


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('avatar_url')
