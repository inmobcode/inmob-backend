from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models.base import TimestampMixin, uuid_pk

ROLES = ("OWNER", "ADMIN", "AGENT")


class User(db.Model, TimestampMixin):
    __tablename__ = "users"

    id = uuid_pk()
    agency_id = db.Column(db.String(36), db.ForeignKey("agencies.id"), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    # Email is the global login identifier (one account = one agency in this MVP),
    # so it must be unique platform-wide, not just within an agency.
    email = db.Column(db.String(200), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="AGENT")
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    agency = db.relationship("Agency", back_populates="users")

    def set_password(self, raw_password: str) -> None:
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)
