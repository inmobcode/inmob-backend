"""booking tokens, for the client's private booking page

Revision ID: b7e2d4f6a8c1
Revises: 83da24333c64
Create Date: 2026-10-13 12:00:00.000000

"""
import secrets

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7e2d4f6a8c1'
down_revision = '83da24333c64'
branch_labels = None
depends_on = None


bookings = sa.table(
    "bookings",
    sa.column("id", sa.String),
    sa.column("token", sa.String),
)


def upgrade():
    # Nullable first so existing bookings can get their token, then tightened
    # to NOT NULL + unique (same steps as the owner access tokens).
    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('token', sa.String(length=32), nullable=True))

    bind = op.get_bind()
    booking_ids = [row[0] for row in bind.execute(sa.select(bookings.c.id))]
    for booking_id in booking_ids:
        bind.execute(
            bookings.update()
            .where(bookings.c.id == booking_id)
            .values(token=secrets.token_urlsafe(16))
        )

    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.alter_column('token', nullable=False)
        batch_op.create_index(batch_op.f('ix_bookings_token'), ['token'], unique=True)


def downgrade():
    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_bookings_token'))
        batch_op.drop_column('token')
