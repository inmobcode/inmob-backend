"""languages: user and client locale, notification params

Revision ID: a9e4c2d7b5f1
Revises: d5a8c2e6f1b4
Create Date: 2026-10-23 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a9e4c2d7b5f1'
down_revision = 'd5a8c2e6f1b4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('locale', sa.String(length=5), nullable=True))
    with op.batch_alter_table('clients', schema=None) as batch_op:
        batch_op.add_column(sa.Column('locale', sa.String(length=5), nullable=True))
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.add_column(sa.Column('params', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.drop_column('params')
    with op.batch_alter_table('clients', schema=None) as batch_op:
        batch_op.drop_column('locale')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('locale')
