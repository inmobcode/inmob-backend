from app.extensions import db
from app.models.base import TimestampMixin, TrashMixin, generate_token, uuid_pk

OFFER_STATUSES = ("DRAFT", "SENT", "VIEWED", "EXPIRED")
DISCOUNT_TYPES = ("NONE", "PERCENT", "FIXED")
# Which properties the offer can hold: only for sale, only for rent, or both.
OFFER_OPERATIONS = ("SALE", "RENT", "BOTH")


class Offer(db.Model, TimestampMixin, TrashMixin):
    __tablename__ = "offers"

    id = uuid_pk()
    agency_id = db.Column(db.String(36), db.ForeignKey("agencies.id"), nullable=False, index=True)
    created_by = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    client_id = db.Column(db.String(36), db.ForeignKey("clients.id"), nullable=True, index=True)

    token = db.Column(db.String(32), nullable=False, unique=True, index=True, default=generate_token)
    title = db.Column(db.String(200), nullable=False)
    operation = db.Column(db.String(4), nullable=False, default="BOTH", server_default="BOTH")
    currency = db.Column(db.String(3), nullable=False, default="USD")
    show_price = db.Column(db.Boolean, nullable=False, default=True)
    status = db.Column(db.String(20), nullable=False, default="DRAFT")
    expires_at = db.Column(db.DateTime, nullable=True)

    # Shown on the public page's welcome block. Kept as three clean fields
    # instead of Kennedys' trick of overloading welcomeTitle with an "@"
    # delimiter to also carry a date range.
    welcome_title = db.Column(db.String(255), nullable=True)
    welcome_date_label = db.Column(db.String(100), nullable=True)
    welcome_content = db.Column(db.Text, nullable=True)
    # Controls whether the agency's own header/footer/contact block show on
    # the public page (no separate marketing domain to switch to, unlike
    # Kennedys' branded-vs-white-label two-domain setup).
    branded = db.Column(db.Boolean, nullable=False, default=True)

    client_name = db.Column(db.String(200), nullable=True)
    client_email = db.Column(db.String(200), nullable=True)
    client_phone = db.Column(db.String(50), nullable=True)

    sections = db.relationship(
        "OfferSection",
        back_populates="offer",
        order_by="OfferSection.position",
        cascade="all, delete-orphan",
    )
    offer_properties = db.relationship(
        "OfferProperty",
        back_populates="offer",
        order_by="OfferProperty.position",
        cascade="all, delete-orphan",
    )


class OfferSection(db.Model, TimestampMixin):
    """A named group of properties within an offer (Kennedys' propertiesToPresent[] entries)."""

    __tablename__ = "offer_sections"

    id = uuid_pk()
    offer_id = db.Column(db.String(36), db.ForeignKey("offers.id"), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=True)
    text = db.Column(db.Text, nullable=True)
    position = db.Column(db.Integer, nullable=False, default=0)

    offer = db.relationship("Offer", back_populates="sections")
    offer_properties = db.relationship(
        "OfferProperty", back_populates="section", order_by="OfferProperty.position"
    )


class OfferProperty(db.Model, TimestampMixin):
    __tablename__ = "offer_properties"

    id = uuid_pk()
    offer_id = db.Column(db.String(36), db.ForeignKey("offers.id"), nullable=False, index=True)
    # Null = ungrouped ("default" section, rendered without its own header).
    section_id = db.Column(db.String(36), db.ForeignKey("offer_sections.id"), nullable=True, index=True)
    property_id = db.Column(db.String(36), db.ForeignKey("properties.id"), nullable=False, index=True)
    position = db.Column(db.Integer, nullable=False, default=0)

    price_override = db.Column(db.Float, nullable=True)
    discount_type = db.Column(db.String(10), nullable=False, default="NONE")
    discount_value = db.Column(db.Float, nullable=False, default=0)
    security_deposit = db.Column(db.Float, nullable=True)
    bottom_text = db.Column(db.String(500), nullable=True)

    offer = db.relationship("Offer", back_populates="offer_properties")
    section = db.relationship("OfferSection", back_populates="offer_properties")
    property = db.relationship("Property")
