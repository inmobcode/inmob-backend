"""services library and services in offers

Revision ID: b5e9d3c1a7f2
Revises: e8c4b2a7f1d9
Create Date: 2026-10-14 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b5e9d3c1a7f2'
down_revision = 'e8c4b2a7f1d9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'services',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('agency_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('type', sa.String(length=20), nullable=False, server_default='OTHER'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('image_url', sa.String(length=500), nullable=True),
        sa.Column('zones', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('provider', sa.String(length=200), nullable=True),
        sa.Column('price', sa.Float(), nullable=True),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='USD'),
        sa.Column('unit', sa.String(length=10), nullable=False, server_default='SERVICE'),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['agency_id'], ['agencies.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_services_agency_id'), 'services', ['agency_id'], unique=False)

    op.create_table(
        'offer_services',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('offer_id', sa.String(length=36), nullable=False),
        sa.Column('service_id', sa.String(length=36), nullable=True),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('type', sa.String(length=20), nullable=False, server_default='OTHER'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('image_url', sa.String(length=500), nullable=True),
        sa.Column('unit', sa.String(length=10), nullable=False, server_default='SERVICE'),
        sa.Column('unit_price', sa.Float(), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('date', sa.Date(), nullable=True),
        sa.Column('note', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['offer_id'], ['offers.id']),
        sa.ForeignKeyConstraint(['service_id'], ['services.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_offer_services_offer_id'), 'offer_services', ['offer_id'], unique=False)
    op.create_index(op.f('ix_offer_services_service_id'), 'offer_services', ['service_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_offer_services_service_id'), table_name='offer_services')
    op.drop_index(op.f('ix_offer_services_offer_id'), table_name='offer_services')
    op.drop_table('offer_services')
    op.drop_index(op.f('ix_services_agency_id'), table_name='services')
    op.drop_table('services')
