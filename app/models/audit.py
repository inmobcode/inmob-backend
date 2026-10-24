from app.extensions import db
from app.models.base import uuid_pk

AUDIT_ENTITIES = ("PROPERTY", "OFFER", "BOOKING")
AUDIT_ACTIONS = ("CREATED", "UPDATED", "TRASHED", "RESTORED", "DELETED")


class AuditEvent(db.Model):
    """One change to a property, offer or booking: who, when and which fields
    (see app/services/audit.py, which writes them on every flush)."""

    __tablename__ = "audit_events"
    __table_args__ = (db.Index("ix_audit_events_entity", "entity_type", "entity_id", "created_at"),)

    id = uuid_pk()
    agency_id = db.Column(db.String(36), db.ForeignKey("agencies.id"), nullable=False, index=True)
    entity_type = db.Column(db.String(10), nullable=False)
    entity_id = db.Column(db.String(36), nullable=False)
    # Null when nobody was signed in: the client on a public link, or the system (iCal, expiry).
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(10), nullable=False)
    # {field: {"from": old, "to": new}}; long or private values keep only that they changed.
    changes = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, index=True)
