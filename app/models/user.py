from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models.base import TimestampMixin, uuid_pk

ROLES = ("OWNER", "ADMIN", "AGENT")


class User(db.Model, TimestampMixin):
    __tablename__ = "users"

    id = uuid_pk()
    # The agency this account lands in in the absence of any other signal —
    # updated whenever the user switches agencies, so the next login resumes
    # where they left off. Not the only agency they can access: see
    # AgencyMembership for that. Every tenancy-scoped query elsewhere in the
    # app still reads the *active* agency from the JWT, never this column.
    agency_id = db.Column(db.String(36), db.ForeignKey("agencies.id"), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    # Email is the global login identifier, so it must be unique platform-wide,
    # not just within an agency — one account can belong to several agencies.
    email = db.Column(db.String(200), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    # Role at the default agency above. The role that actually governs a
    # request is the one in the JWT claims (set from AgencyMembership.role at
    # login/switch time), not this column.
    role = db.Column(db.String(20), nullable=False, default="AGENT")
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    avatar_url = db.Column(db.String(500), nullable=True)
    # The language they use the dashboard in (synced from the X-Locale header);
    # emails meant for them go out in it. Null until they first use the app.
    locale = db.Column(db.String(5), nullable=True)

    agency = db.relationship("Agency", back_populates="users")
    memberships = db.relationship(
        "AgencyMembership", back_populates="user", cascade="all, delete-orphan"
    )

    def set_password(self, raw_password: str) -> None:
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)


class AgencyMembership(db.Model, TimestampMixin):
    """Which agencies a user can work in, and their role at each one."""

    __tablename__ = "agency_memberships"
    __table_args__ = (
        db.UniqueConstraint("user_id", "agency_id", name="uq_membership_user_agency"),
    )

    id = uuid_pk()
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False, index=True)
    agency_id = db.Column(db.String(36), db.ForeignKey("agencies.id"), nullable=False, index=True)
    role = db.Column(db.String(20), nullable=False, default="AGENT")

    user = db.relationship("User", back_populates="memberships")
    agency = db.relationship("Agency")
