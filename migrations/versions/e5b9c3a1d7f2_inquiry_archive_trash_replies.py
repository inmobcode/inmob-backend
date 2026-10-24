"""inquiries: archive, trash, replies from the dashboard and reply templates

Revision ID: e5b9c3a1d7f2
Revises: d2a7e5c9b1f4
Create Date: 2026-10-24 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5b9c3a1d7f2'
down_revision = 'd2a7e5c9b1f4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('inquiries', schema=None) as batch_op:
        batch_op.add_column(sa.Column('deleted_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('archived_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('replied_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('replied_by', sa.String(length=36), nullable=True))
        batch_op.create_index(batch_op.f('ix_inquiries_deleted_at'), ['deleted_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_inquiries_archived_at'), ['archived_at'], unique=False)
        batch_op.create_foreign_key('fk_inquiries_replied_by_users', 'users', ['replied_by'], ['id'])

    op.create_table(
        'reply_templates',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('agency_id', sa.String(length=36), nullable=False),
        sa.Column('created_by', sa.String(length=36), nullable=True),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('subject', sa.String(length=200), nullable=True),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['agency_id'], ['agencies.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('reply_templates', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_reply_templates_agency_id'), ['agency_id'], unique=False)


def downgrade():
    with op.batch_alter_table('reply_templates', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_reply_templates_agency_id'))
    op.drop_table('reply_templates')

    with op.batch_alter_table('inquiries', schema=None) as batch_op:
        batch_op.drop_constraint('fk_inquiries_replied_by_users', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_inquiries_archived_at'))
        batch_op.drop_index(batch_op.f('ix_inquiries_deleted_at'))
        batch_op.drop_column('replied_by')
        batch_op.drop_column('replied_at')
        batch_op.drop_column('archived_at')
        batch_op.drop_column('deleted_at')
