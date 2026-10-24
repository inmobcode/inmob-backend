"""clients: trash, tags and what they're looking for

Revision ID: d2a7e5c9b1f4
Revises: c4e9a1f7b3d2
Create Date: 2026-10-24 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd2a7e5c9b1f4'
down_revision = 'c4e9a1f7b3d2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('clients', schema=None) as batch_op:
        batch_op.add_column(sa.Column('deleted_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('tags', sa.JSON(), nullable=False, server_default='[]'))
        batch_op.add_column(sa.Column('budget_min', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('budget_max', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('guests', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('zones', sa.String(length=300), nullable=True))
        batch_op.add_column(sa.Column('desired_from', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('desired_to', sa.Date(), nullable=True))
        batch_op.create_index(batch_op.f('ix_clients_deleted_at'), ['deleted_at'], unique=False)


def downgrade():
    with op.batch_alter_table('clients', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_clients_deleted_at'))
        batch_op.drop_column('desired_to')
        batch_op.drop_column('desired_from')
        batch_op.drop_column('zones')
        batch_op.drop_column('guests')
        batch_op.drop_column('budget_max')
        batch_op.drop_column('budget_min')
        batch_op.drop_column('tags')
        batch_op.drop_column('deleted_at')
