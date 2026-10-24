"""offers: opens of the link, templates

Revision ID: f4a2d8c6e1b3
Revises: e5b9c3a1d7f2
Create Date: 2026-10-25 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f4a2d8c6e1b3'
down_revision = 'e5b9c3a1d7f2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('offers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_template', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('view_count', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('first_viewed_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('last_viewed_at', sa.DateTime(), nullable=True))

    op.create_table(
        'offer_views',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('offer_id', sa.String(length=36), nullable=False),
        sa.Column('viewed_at', sa.DateTime(), nullable=False),
        sa.Column('device', sa.String(length=10), nullable=True),
        sa.ForeignKeyConstraint(['offer_id'], ['offers.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('offer_views', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_offer_views_offer_id'), ['offer_id'], unique=False)

    # Offers opened before opens were counted: at least once.
    op.execute("UPDATE offers SET view_count = 1 WHERE status = 'VIEWED'")


def downgrade():
    with op.batch_alter_table('offer_views', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_offer_views_offer_id'))
    op.drop_table('offer_views')

    op.execute("UPDATE offers SET status = 'VIEWED' WHERE status = 'ACCEPTED'")
    with op.batch_alter_table('offers', schema=None) as batch_op:
        batch_op.drop_column('last_viewed_at')
        batch_op.drop_column('first_viewed_at')
        batch_op.drop_column('view_count')
        batch_op.drop_column('is_template')
