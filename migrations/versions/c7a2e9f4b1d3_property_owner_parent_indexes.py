"""index properties.owner_id and properties.parent_property_id

Revision ID: c7a2e9f4b1d3
Revises: b5e9d3c1a7f2
Create Date: 2026-10-14 18:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'c7a2e9f4b1d3'
down_revision = 'b5e9d3c1a7f2'
branch_labels = None
depends_on = None


def upgrade():
    # An owner's properties and a hotel's rooms are looked up by these columns.
    op.create_index('ix_properties_owner_id', 'properties', ['owner_id'])
    op.create_index('ix_properties_parent_property_id', 'properties', ['parent_property_id'])


def downgrade():
    op.drop_index('ix_properties_parent_property_id', table_name='properties')
    op.drop_index('ix_properties_owner_id', table_name='properties')
