from app.extensions import db
from app.models.base import TimestampMixin, uuid_pk


class OwnerPayout(db.Model, TimestampMixin):
    """A liquidation: money the agency handed over to a property owner."""

    __tablename__ = "owner_payouts"

    id = uuid_pk()
    agency_id = db.Column(db.String(36), db.ForeignKey("agencies.id"), nullable=False, index=True)
    owner_id = db.Column(db.String(36), db.ForeignKey("property_owners.id"), nullable=False, index=True)
    created_by = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)

    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(3), nullable=False, default="USD")
    paid_at = db.Column(db.Date, nullable=False)
    method = db.Column(db.String(50), nullable=True)
    note = db.Column(db.String(255), nullable=True)
