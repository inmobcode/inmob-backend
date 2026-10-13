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
    subscription_status = db.Column(db.String(20), nullable=False, default="TRIALING")
    # Public site customization (template, colors, cover, texts, contact).
    # Shape is defined by SiteSettingsSchema; null means "use the defaults".
    site = db.Column(db.JSON, nullable=True)

    users = db.relationship("User", back_populates="agency", lazy="dynamic")
