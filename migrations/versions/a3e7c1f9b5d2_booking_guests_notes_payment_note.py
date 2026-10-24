"""bookings: guests and internal notes; a note on each payment

Revision ID: a3e7c1f9b5d2
Revises: f4a2d8c6e1b3
Create Date: 2026-10-25 02:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a3e7c1f9b5d2'
down_revision = 'f4a2d8c6e1b3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('guests', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('notes', sa.Text(), nullable=True))
    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('note', sa.String(length=200), nullable=True))


def downgrade():
    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.drop_column('note')
    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.drop_column('notes')
        batch_op.drop_column('guests')
