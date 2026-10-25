from app.extensions import db
from app.models.base import TimestampMixin, uuid_pk


class Agency(db.Model, TimestampMixin):
    __tablename__ = "agencies"

    id = uuid_pk()
    name = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(200), unique=True, nullable=False, index=True)
    logo_url = db.Column(db.String(500), nullable=True)
    contact_email = db.Column(db.String(200), nullable=True)
    locale = db.Column(db.String(10), nullable=False, default="es")
    currency = db.Column(db.String(3), nullable=False, default="USD")
    # What the agency pays for. "trial" is the free trial (everything except the
    # data-import tool); it becomes "pro" when Paddle starts charging. Agencies that
    # existed before billing keep "pro" (the column default in the database).
    plan = db.Column(db.String(20), nullable=False, default="trial", server_default="pro")
    # INCOMPLETE (no card yet: locked out), TRIALING, ACTIVE, PAST_DUE (still
    # works, Paddle is retrying the card) or CANCELED (locked out).
    subscription_status = db.Column(db.String(20), nullable=False, default="INCOMPLETE")
    trial_ends_at = db.Column(db.DateTime, nullable=True)
    # The free trial is offered once per agency (and once per card, see TrialCard).
    trial_used = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    paddle_customer_id = db.Column(db.String(64), nullable=True, index=True)
    paddle_subscription_id = db.Column(db.String(64), nullable=True, index=True)
    # Public site customization (template, colors, cover, texts, contact).
    # Shape is defined by SiteSettingsSchema; null means "use the defaults".
    site = db.Column(db.JSON, nullable=True)
    # Whether the owner's portal itemizes the agency's commission in their account
    # statement. Off by default: owners only see what is due to them.
    owner_portal_shows_commission = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())

    users = db.relationship("User", back_populates="agency", lazy="dynamic")


class TrialCard(db.Model, TimestampMixin):
    """A card (a hash of its type, last four digits, expiry and holder: Paddle gives no fingerprint)
    that started a free trial, so a second agency can't repeat it with another email."""

    __tablename__ = "trial_cards"

    id = uuid_pk()
    fingerprint = db.Column(db.String(64), nullable=False, unique=True)
    agency_id = db.Column(db.String(36), db.ForeignKey("agencies.id"), nullable=False, index=True)
