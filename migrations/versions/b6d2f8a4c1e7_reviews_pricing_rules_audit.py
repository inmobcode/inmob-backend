"""reviews, pricing rules on properties, and the change history

Revision ID: b6d2f8a4c1e7
Revises: a3e7c1f9b5d2
Create Date: 2026-10-25 04:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b6d2f8a4c1e7'
down_revision = 'a3e7c1f9b5d2'
branch_labels = None
depends_on = None

PRICING = (
    ('min_stay', sa.Integer()),
    ('weekly_discount_pct', sa.Float()),
    ('monthly_discount_pct', sa.Float()),
    ('last_minute_discount_pct', sa.Float()),
    ('last_minute_days', sa.Integer()),
    ('early_bird_discount_pct', sa.Float()),
    ('early_bird_days', sa.Integer()),
)


def upgrade():
    with op.batch_alter_table('properties', schema=None) as batch_op:
        for name, kind in PRICING:
            batch_op.add_column(sa.Column(name, kind, nullable=True))

    op.create_table(
        'reviews',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('agency_id', sa.String(length=36), nullable=False),
        sa.Column('property_id', sa.String(length=36), nullable=True),
        sa.Column('booking_id', sa.String(length=36), nullable=True),
        sa.Column('author_name', sa.String(length=120), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=True),
        sa.Column('stayed_on', sa.Date(), nullable=True),
        sa.Column('status', sa.String(length=10), nullable=False),
        sa.Column('source', sa.String(length=10), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['agency_id'], ['agencies.id']),
        sa.ForeignKeyConstraint(['property_id'], ['properties.id']),
        sa.ForeignKeyConstraint(['booking_id'], ['bookings.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('booking_id'),
    )
    with op.batch_alter_table('reviews', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_reviews_agency_id'), ['agency_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_reviews_property_id'), ['property_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_reviews_status'), ['status'], unique=False)

    op.create_table(
        'audit_events',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('agency_id', sa.String(length=36), nullable=False),
        sa.Column('entity_type', sa.String(length=10), nullable=False),
        sa.Column('entity_id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=True),
        sa.Column('action', sa.String(length=10), nullable=False),
        sa.Column('changes', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['agency_id'], ['agencies.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('audit_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_audit_events_agency_id'), ['agency_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_events_created_at'), ['created_at'], unique=False)
        batch_op.create_index('ix_audit_events_entity', ['entity_type', 'entity_id', 'created_at'], unique=False)


def downgrade():
    with op.batch_alter_table('audit_events', schema=None) as batch_op:
        batch_op.drop_index('ix_audit_events_entity')
        batch_op.drop_index(batch_op.f('ix_audit_events_created_at'))
        batch_op.drop_index(batch_op.f('ix_audit_events_agency_id'))
    op.drop_table('audit_events')

    with op.batch_alter_table('reviews', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_reviews_status'))
        batch_op.drop_index(batch_op.f('ix_reviews_property_id'))
        batch_op.drop_index(batch_op.f('ix_reviews_agency_id'))
    op.drop_table('reviews')

    with op.batch_alter_table('properties', schema=None) as batch_op:
        for name, _ in reversed(PRICING):
            batch_op.drop_column(name)
