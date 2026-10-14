"""widen property_photos.section for custom section names

Revision ID: e8c4b2a7f1d9
Revises: d3f7a1b9c2e4
Create Date: 2026-10-13 15:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e8c4b2a7f1d9'
down_revision = 'd3f7a1b9c2e4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('property_photos', schema=None) as batch_op:
        batch_op.alter_column(
            'section', existing_type=sa.String(length=20), type_=sa.String(length=60)
        )


def downgrade():
    with op.batch_alter_table('property_photos', schema=None) as batch_op:
        batch_op.alter_column(
            'section', existing_type=sa.String(length=60), type_=sa.String(length=20)
        )
