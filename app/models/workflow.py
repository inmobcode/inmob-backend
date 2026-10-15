from app.extensions import db
from app.models.base import TimestampMixin, uuid_pk

NOTIFICATION_TYPES = ("INQUIRY", "OFFER_VIEWED", "OFFER_REPLY", "PAYMENT", "TASK", "BOOKING")


class Task(db.Model, TimestampMixin):
    """A follow-up on someone on the team's plate: "call Lucía on Thursday"."""

    __tablename__ = "tasks"

    id = uuid_pk()
    agency_id = db.Column(db.String(36), db.ForeignKey("agencies.id"), nullable=False, index=True)
    client_id = db.Column(db.String(36), db.ForeignKey("clients.id"), nullable=True, index=True)
    assigned_agent_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True, index=True)
    created_by = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)

    title = db.Column(db.String(200), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    due_date = db.Column(db.Date, nullable=True, index=True)
    # Set when it's done; null means still open.
    done_at = db.Column(db.DateTime, nullable=True)

    client = db.relationship("Client")


class Notification(db.Model):
    """One row per person who should hear about something, so each reads it on their own."""

    __tablename__ = "notifications"

    id = uuid_pk()
    agency_id = db.Column(db.String(36), db.ForeignKey("agencies.id"), nullable=False, index=True)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False, index=True)

    type = db.Column(db.String(20), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.String(500), nullable=True)
    # Path inside the dashboard (without the agency slug), e.g. "/offers/<id>".
    link = db.Column(db.String(300), nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, index=True)
    read_at = db.Column(db.DateTime, nullable=True)
