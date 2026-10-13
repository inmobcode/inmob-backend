"""offer operation: sale, rent or both

Revision ID: c4f1a9e3d2b6
Revises: b7e2d4f6a8c1
Create Date: 2026-10-13 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c4f1a9e3d2b6'
down_revision = 'b7e2d4f6a8c1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('offers', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('operation', sa.String(length=4), nullable=False, server_default='BOTH')
        )

    # Existing offers take the operation of their properties: all for sale is
    # SALE, all for rent is RENT, mixed or empty stays BOTH.
    op.execute(
        """
        UPDATE offers SET operation = picked.listing_type
        FROM (
            SELECT op.offer_id, MIN(p.listing_type) AS listing_type
            FROM offer_properties op JOIN properties p ON p.id = op.property_id
            GROUP BY op.offer_id
            HAVING COUNT(DISTINCT p.listing_type) = 1
        ) AS picked
        WHERE offers.id = picked.offer_id
        """
    )


def downgrade():
    with op.batch_alter_table('offers', schema=None) as batch_op:
        batch_op.drop_column('operation')
