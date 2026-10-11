import secrets
import uuid
from datetime import datetime, timezone

from app.extensions import db


def uuid_pk():
    return db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))


def generate_token() -> str:
    return secrets.token_urlsafe(8)


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
