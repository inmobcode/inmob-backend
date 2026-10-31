"""email verification: verified flag and emailed code on users

Revision ID: e1b6c9d4a7f3
Revises: d9f5a2b7c3e1
Create Date: 2026-10-31 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e1b6c9d4a7f3'
down_revision = 'd9f5a2b7c3e1'
branch_labels = None
depends_on = None


def upgrade():
    # Everyone who already has an account counts as verified: the default only
    # exists to fill the existing rows, new accounts start unverified.
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('email_verified', sa.Boolean(), nullable=False, server_default=sa.true())
        )
        batch_op.add_column(sa.Column('verify_code_hash', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('verify_code_expires_at', sa.DateTime(), nullable=True))
        batch_op.add_column(
            sa.Column('verify_code_attempts', sa.Integer(), nullable=False, server_default='0')
        )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('email_verified', server_default=None)


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('verify_code_attempts')
        batch_op.drop_column('verify_code_expires_at')
        batch_op.drop_column('verify_code_hash')
        batch_op.drop_column('email_verified')
