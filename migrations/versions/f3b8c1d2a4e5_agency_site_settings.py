"""agency public site settings

Revision ID: f3b8c1d2a4e5
Revises: e6f152e5f98a
Create Date: 2026-10-12 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f3b8c1d2a4e5'
down_revision = 'e6f152e5f98a'
branch_labels = None
depends_on = None


def upgrade():
    # Nullable: agencies that never customized their site fall back to the
    # defaults defined in the frontend.
    with op.batch_alter_table('agencies', schema=None) as batch_op:
        batch_op.add_column(sa.Column('site', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('agencies', schema=None) as batch_op:
        batch_op.drop_column('site')
