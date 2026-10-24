"""password recovery: emailed code on users

Revision ID: c4e9a1f7b3d2
Revises: b7d3f1a9c5e2
Create Date: 2026-10-24 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c4e9a1f7b3d2'
down_revision = 'b7d3f1a9c5e2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('reset_code_hash', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('reset_code_expires_at', sa.DateTime(), nullable=True))
        batch_op.add_column(
            sa.Column('reset_code_attempts', sa.Integer(), nullable=False, server_default='0')
        )


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('reset_code_attempts')
        batch_op.drop_column('reset_code_expires_at')
        batch_op.drop_column('reset_code_hash')
