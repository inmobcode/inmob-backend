from app.extensions import db
from app.models.base import TimestampMixin, uuid_pk

REVIEW_STATUSES = ("PENDING", "PUBLISHED", "HIDDEN")
# GUEST: left by the client from their booking page. MANUAL: typed in by the
# agency, e.g. one it got on another channel.
REVIEW_SOURCES = ("GUEST", "MANUAL")


class Review(db.Model, TimestampMixin):
    """A guest's opinion of a stay, shown on the agency's site once the agency publishes it."""

    __tablename__ = "reviews"

    id = uuid_pk()
    agency_id = db.Column(db.String(36), db.ForeignKey("agencies.id"), nullable=False, index=True)
    property_id = db.Column(db.String(36), db.ForeignKey("properties.id"), nullable=True, index=True)
    # One review per booking.
    booking_id = db.Column(db.String(36), db.ForeignKey("bookings.id"), nullable=True, unique=True)

    author_name = db.Column(db.String(120), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    text = db.Column(db.Text, nullable=True)
    # When the stay was, shown as "octubre 2026".
    stayed_on = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(10), nullable=False, default="PENDING", index=True)
    source = db.Column(db.String(10), nullable=False, default="GUEST")

    property = db.relationship("Property")
