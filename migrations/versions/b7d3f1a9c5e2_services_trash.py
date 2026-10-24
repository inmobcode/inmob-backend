"""trash: deleted_at on services

Revision ID: b7d3f1a9c5e2
Revises: a9e4c2d7b5f1
Create Date: 2026-10-24 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7d3f1a9c5e2'
down_revision = 'a9e4c2d7b5f1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('services', schema=None) as batch_op:
        batch_op.add_column(sa.Column('deleted_at', sa.DateTime(), nullable=True))
        batch_op.create_index(batch_op.f('ix_services_deleted_at'), ['deleted_at'], unique=False)


def downgrade():
    with op.batch_alter_table('services', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_services_deleted_at'))
        batch_op.drop_column('deleted_at')
