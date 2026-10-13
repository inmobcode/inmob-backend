import secrets
import uuid
from datetime import datetime, timezone

from app.extensions import db


def uuid_pk():
    return db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))


def generate_token() -> str:
    return secrets.token_urlsafe(8)


class TrashMixin:
    """Deleting moves the record to the trash: it disappears from the app and
    public pages, can be restored, and is deleted for good after TRASH_DAYS."""

    deleted_at = db.Column(db.DateTime, nullable=True, index=True)


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
