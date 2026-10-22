"""properties.source / external_id for imported listings

Revision ID: d5a8c2e6f1b4
Revises: f7c2a9b4d6e3
Create Date: 2026-10-22 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd5a8c2e6f1b4'
down_revision = 'f7c2a9b4d6e3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('properties') as batch_op:
        batch_op.add_column(sa.Column('source', sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column('external_id', sa.String(length=200), nullable=True))
        batch_op.create_unique_constraint(
            'uq_property_agency_source_external', ['agency_id', 'source', 'external_id']
        )


def downgrade():
    with op.batch_alter_table('properties') as batch_op:
        batch_op.drop_constraint('uq_property_agency_source_external', type_='unique')
        batch_op.drop_column('external_id')
        batch_op.drop_column('source')
