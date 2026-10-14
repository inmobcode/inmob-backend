from app.extensions import db
from app.models.base import TimestampMixin, uuid_pk

# What an agency can add to a stay: people, boats, rides, outings.
SERVICE_TYPES = (
    "BUTLER",
    "CHEF",
    "YACHT",
    "TRANSFER",
    "CAR",
    "EXCURSION",
    "SPA",
    "BABYSITTER",
    "HOUSEKEEPING",
    "EVENT",
    "OTHER",
)
# What the price is charged per; a null price means "a consultar".
SERVICE_UNITS = ("SERVICE", "PERSON", "DAY", "NIGHT", "HOUR")


class Service(db.Model, TimestampMixin):
    """A service or experience in an agency's library, ready to add to offers."""

    __tablename__ = "services"

    id = uuid_pk()
    agency_id = db.Column(db.String(36), db.ForeignKey("agencies.id"), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    type = db.Column(db.String(20), nullable=False, default="OTHER")
    description = db.Column(db.Text, nullable=True)
    image_url = db.Column(db.String(500), nullable=True)
    # Where it's offered (towns, regions); empty means anywhere.
    zones = db.Column(db.JSON, nullable=False, default=list)
    # Who provides it, for the agency's own reference; never shown to clients.
    provider = db.Column(db.String(200), nullable=True)
    price = db.Column(db.Float, nullable=True)
    currency = db.Column(db.String(3), nullable=False, default="USD")
    unit = db.Column(db.String(10), nullable=False, default="SERVICE")
    # Inactive services stay in the library but can't be added to offers.
    active = db.Column(db.Boolean, nullable=False, default=True)
    reservation_policy = db.Column(db.Text, nullable=True)
    cancellation_policy = db.Column(db.Text, nullable=True)
