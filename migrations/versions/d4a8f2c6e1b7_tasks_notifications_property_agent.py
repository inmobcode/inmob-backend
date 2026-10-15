"""tasks, notifications and the agent a property is assigned to

Revision ID: d4a8f2c6e1b7
Revises: 398a483d100b
Create Date: 2026-10-15 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4a8f2c6e1b7'
down_revision = '398a483d100b'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'tasks',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('agency_id', sa.String(length=36), nullable=False),
        sa.Column('client_id', sa.String(length=36), nullable=True),
        sa.Column('assigned_agent_id', sa.String(length=36), nullable=True),
        sa.Column('created_by', sa.String(length=36), nullable=True),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('done_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['agency_id'], ['agencies.id']),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id']),
        sa.ForeignKeyConstraint(['assigned_agent_id'], ['users.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tasks_agency_id'), ['agency_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tasks_client_id'), ['client_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tasks_assigned_agent_id'), ['assigned_agent_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tasks_due_date'), ['due_date'], unique=False)

    op.create_table(
        'notifications',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('agency_id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('type', sa.String(length=20), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('body', sa.String(length=500), nullable=True),
        sa.Column('link', sa.String(length=300), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('read_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['agency_id'], ['agencies.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_notifications_agency_id'), ['agency_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_notifications_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_notifications_created_at'), ['created_at'], unique=False)

    with op.batch_alter_table('properties', schema=None) as batch_op:
        batch_op.add_column(sa.Column('assigned_agent_id', sa.String(length=36), nullable=True))
        batch_op.create_index(batch_op.f('ix_properties_assigned_agent_id'), ['assigned_agent_id'], unique=False)
        batch_op.create_foreign_key('fk_properties_assigned_agent_id_users', 'users', ['assigned_agent_id'], ['id'])

    # Until now every property belonged to whoever created it.
    op.execute('UPDATE properties SET assigned_agent_id = created_by WHERE assigned_agent_id IS NULL')


def downgrade():
    with op.batch_alter_table('properties', schema=None) as batch_op:
        batch_op.drop_constraint('fk_properties_assigned_agent_id_users', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_properties_assigned_agent_id'))
        batch_op.drop_column('assigned_agent_id')

    op.drop_table('notifications')
    op.drop_table('tasks')
