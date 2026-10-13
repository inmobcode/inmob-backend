"""trash: deleted_at on properties, offers and bookings

Revision ID: a1d5e8f2c7b3
Revises: c4f1a9e3d2b6
Create Date: 2026-10-13 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1d5e8f2c7b3'
down_revision = 'c4f1a9e3d2b6'
branch_labels = None
depends_on = None

TABLES = ('properties', 'offers', 'bookings')


def upgrade():
    for table in TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column('deleted_at', sa.DateTime(), nullable=True))
            batch_op.create_index(batch_op.f(f'ix_{table}_deleted_at'), ['deleted_at'], unique=False)


def downgrade():
    for table in TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_index(batch_op.f(f'ix_{table}_deleted_at'))
            batch_op.drop_column('deleted_at')
