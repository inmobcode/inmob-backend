import secrets

from app.extensions import db
from app.models.base import TimestampMixin, TrashMixin, uuid_pk

BOOKING_STATUSES = ("PENDING", "CONFIRMED", "CANCELLED", "COMPLETED")
PAYMENT_TYPES = ("DEPOSIT", "BALANCE", "COMMISSION")
PAYMENT_STATUSES = ("PENDING", "PAID")


def generate_booking_token() -> str:
    # Longer than offer tokens: the link shows a person's dates and payments.
    return secrets.token_urlsafe(16)


class Booking(db.Model, TimestampMixin, TrashMixin):
    __tablename__ = "bookings"

    id = uuid_pk()
    agency_id = db.Column(db.String(36), db.ForeignKey("agencies.id"), nullable=False, index=True)
    property_id = db.Column(db.String(36), db.ForeignKey("properties.id"), nullable=False, index=True)
    client_id = db.Column(db.String(36), db.ForeignKey("clients.id"), nullable=True, index=True)
    offer_id = db.Column(db.String(36), db.ForeignKey("offers.id"), nullable=True)
    created_by = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    # Opens the client's read-only page at /booking/<token>; whoever has the
    # link can see it, so it is only ever sent to the booking's client.
    token = db.Column(
        db.String(32), nullable=False, unique=True, index=True, default=generate_booking_token
    )
    # Set while CONFIRMED so the property calendar shows these dates as unavailable;
    # cleared (and the block removed) if the booking is cancelled.
    availability_block_id = db.Column(
        db.String(36), db.ForeignKey("availability_blocks.id"), nullable=True
    )

    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(10), nullable=False, default="PENDING")
    total_price = db.Column(db.Float, nullable=True)
    currency = db.Column(db.String(3), nullable=False, default="USD")
    commission_amount = db.Column(db.Float, nullable=True)
    guests = db.Column(db.Integer, nullable=True)
    # For the team only: never on the client's page or receipt.
    notes = db.Column(db.Text, nullable=True)

    property = db.relationship("Property")
    client = db.relationship("Client")
    payments = db.relationship(
        "Payment",
        back_populates="booking",
        order_by="Payment.created_at",
        cascade="all, delete-orphan",
    )


class Payment(db.Model, TimestampMixin):
    __tablename__ = "payments"

    id = uuid_pk()
    booking_id = db.Column(db.String(36), db.ForeignKey("bookings.id"), nullable=False, index=True)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(3), nullable=False, default="USD")
    type = db.Column(db.String(12), nullable=False, default="DEPOSIT")
    status = db.Column(db.String(10), nullable=False, default="PENDING")
    paid_at = db.Column(db.DateTime, nullable=True)
    method = db.Column(db.String(50), nullable=True)
    # A short reference for the team ("transfer 0042", "card ending 1234").
    note = db.Column(db.String(200), nullable=True)

    booking = db.relationship("Booking", back_populates="payments")
