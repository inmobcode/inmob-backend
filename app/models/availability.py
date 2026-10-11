from app.extensions import db
from app.models.base import TimestampMixin, uuid_pk

AVAILABILITY_SOURCES = ("MANUAL", "ICAL", "BOOKING")


class AvailabilityBlock(db.Model, TimestampMixin):
    __tablename__ = "availability_blocks"

    id = uuid_pk()
    property_id = db.Column(db.String(36), db.ForeignKey("properties.id"), nullable=False, index=True)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    source = db.Column(db.String(10), nullable=False, default="MANUAL")
    # The external event's UID, used to upsert instead of duplicating on re-sync. Only set for source=ICAL.
    ical_uid = db.Column(db.String(255), nullable=True, index=True)
    note = db.Column(db.String(255), nullable=True)
