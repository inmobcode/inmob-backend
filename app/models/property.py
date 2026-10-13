from app.constants.property_catalogs import ALL_PROPERTY_TYPES
from app.extensions import db
from app.models.base import TimestampMixin, TrashMixin, generate_token, uuid_pk

LISTING_TYPES = ("SALE", "RENT")
CATEGORIES = ALL_PROPERTY_TYPES
STATUSES = ("DRAFT", "PUBLISHED", "ARCHIVED")


class PropertyOwner(db.Model, TimestampMixin):
    __tablename__ = "property_owners"

    id = uuid_pk()
    agency_id = db.Column(db.String(36), db.ForeignKey("agencies.id"), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(200), nullable=True)
    phone = db.Column(db.String(50), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    access_token = db.Column(
        db.String(32), nullable=False, unique=True, index=True, default=generate_token
    )

    agency = db.relationship("Agency")
    properties = db.relationship("Property", back_populates="owner", lazy="dynamic")


class Property(db.Model, TimestampMixin, TrashMixin):
    __tablename__ = "properties"
    __table_args__ = (db.UniqueConstraint("agency_id", "slug", name="uq_property_agency_slug"),)

    id = uuid_pk()
    agency_id = db.Column(db.String(36), db.ForeignKey("agencies.id"), nullable=False, index=True)
    owner_id = db.Column(db.String(36), db.ForeignKey("property_owners.id"), nullable=True)
    created_by = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    # Set when this property is a hotel room: points at the parent HOTEL property.
    parent_property_id = db.Column(db.String(36), db.ForeignKey("properties.id"), nullable=True)

    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(220), nullable=False)
    listing_type = db.Column(db.String(10), nullable=False, default="SALE")
    category = db.Column(db.String(30), nullable=False, default="HOUSE")
    status = db.Column(db.String(20), nullable=False, default="DRAFT")

    price = db.Column(db.Float, nullable=True)
    currency = db.Column(db.String(3), nullable=False, default="USD")

    country = db.Column(db.String(100), nullable=True)
    region = db.Column(db.String(100), nullable=True)
    area = db.Column(db.String(100), nullable=True)
    address = db.Column(db.String(255), nullable=True)
    lat = db.Column(db.Float, nullable=True)
    lng = db.Column(db.Float, nullable=True)
    google_map_url = db.Column(db.String(1000), nullable=True)
    # Shown as "View Brochure"/"View Website" buttons on offer cards.
    brochure_url = db.Column(db.String(1000), nullable=True)
    website_url = db.Column(db.String(1000), nullable=True)

    bedrooms = db.Column(db.Integer, nullable=True)
    bathrooms = db.Column(db.Integer, nullable=True)
    area_sqm = db.Column(db.Float, nullable=True)
    plot_area = db.Column(db.Float, nullable=True)
    # Replaces the old Phase-2 `year_built` — same concept, one field.
    construction_year = db.Column(db.Integer, nullable=True)
    renovation_year = db.Column(db.Integer, nullable=True)
    energy_certificate = db.Column(db.String(20), nullable=True)

    amenities = db.Column(db.JSON, nullable=False, default=list)
    outdoor_amenities = db.Column(db.JSON, nullable=False, default=list)
    indoor_amenities = db.Column(db.JSON, nullable=False, default=list)
    custom_facilities = db.Column(db.JSON, nullable=False, default=list)
    location_features = db.Column(db.JSON, nullable=False, default=list)
    view = db.Column(db.JSON, nullable=False, default=list)
    property_status = db.Column(db.JSON, nullable=False, default=list)
    enjoy = db.Column(db.Text, nullable=True)
    outdoor_shower = db.Column(db.Integer, nullable=True)

    agent_friendly_name = db.Column(db.String(200), nullable=True)
    visible_location = db.Column(db.String(255), nullable=True)
    guests = db.Column(db.String(50), nullable=True)
    stars = db.Column(db.Integer, nullable=True)
    watermark_photos = db.Column(db.Boolean, nullable=False, default=True)
    video_urls = db.Column(db.JSON, nullable=False, default=list)

    # External calendar (e.g. Airbnb/Booking.com export URL) to pull blocked dates from.
    ical_import_url = db.Column(db.String(1000), nullable=True)

    agency = db.relationship("Agency")
    owner = db.relationship("PropertyOwner", back_populates="properties")
    parent_property = db.relationship("Property", remote_side=[id], backref="rooms")
    photos = db.relationship(
        "PropertyPhoto",
        back_populates="property",
        order_by="PropertyPhoto.position",
        cascade="all, delete-orphan",
    )
    classification = db.relationship(
        "Classification", back_populates="property", uselist=False, cascade="all, delete-orphan"
    )
    content = db.relationship(
        "Description", back_populates="property", uselist=False, cascade="all, delete-orphan"
    )
    pools = db.relationship("Pool", back_populates="property", cascade="all, delete-orphan")
    rate_periods = db.relationship(
        "RatePeriod",
        back_populates="property",
        order_by="RatePeriod.start_date",
        cascade="all, delete-orphan",
    )
    recommendations = db.relationship(
        "ImprovementRecommendation",
        back_populates="property",
        order_by="ImprovementRecommendation.created_at.desc()",
        cascade="all, delete-orphan",
    )


class PropertyPhoto(db.Model, TimestampMixin):
    __tablename__ = "property_photos"

    id = uuid_pk()
    property_id = db.Column(db.String(36), db.ForeignKey("properties.id"), nullable=False, index=True)
    url = db.Column(db.String(1000), nullable=False)
    position = db.Column(db.Integer, nullable=False, default=0)
    is_cover = db.Column(db.Boolean, nullable=False, default=False)
    section = db.Column(db.String(20), nullable=False, default="GENERAL")
    section_detail = db.Column(db.String(255), nullable=True)  # bedroom number, or "added facilities" text

    property = db.relationship("Property", back_populates="photos")


class Classification(db.Model, TimestampMixin):
    """1:1 with Property — mirrors kennedys-api's Classification table."""

    __tablename__ = "classifications"

    id = uuid_pk()
    property_id = db.Column(
        db.String(36), db.ForeignKey("properties.id"), nullable=False, unique=True, index=True
    )

    floor_numbers = db.Column(db.JSON, nullable=False, default=list)
    parking_spaces = db.Column(db.Integer, nullable=True)
    storage_spaces = db.Column(db.Integer, nullable=True)
    staff_room = db.Column(db.Integer, nullable=True)

    # Sale-only
    location_category = db.Column(db.String(30), nullable=True)
    layout_and_living_spaces = db.Column(db.JSON, nullable=True)

    # Rent-only ("Accommodation" block)
    master_bedroom_qty = db.Column(db.Integer, nullable=True)
    double_bedroom_qty = db.Column(db.Integer, nullable=True)
    twin_bedroom_qty = db.Column(db.Integer, nullable=True)
    single_bedroom_qty = db.Column(db.Integer, nullable=True)
    bedroom_with_bunk_beds_qty = db.Column(db.Integer, nullable=True)
    guest_bedroom_qty = db.Column(db.Integer, nullable=True)

    # Essentials: Management + Vendor & Licensing (Owner Contact reuses PropertyOwner)
    management_name = db.Column(db.String(200), nullable=True)
    management_email = db.Column(db.String(200), nullable=True)
    management_phone = db.Column(db.String(50), nullable=True)
    management_company = db.Column(db.String(200), nullable=True)
    vendor_property_name = db.Column(db.String(200), nullable=True)
    website = db.Column(db.String(500), nullable=True)
    commission = db.Column(db.String(50), nullable=True)
    license = db.Column(db.String(200), nullable=True)
    third_party_permission = db.Column(db.Boolean, nullable=True)

    property = db.relationship("Property", back_populates="classification")


class Description(db.Model, TimestampMixin):
    """1:1 with Property — mirrors kennedys-api's Description table."""

    __tablename__ = "descriptions"

    id = uuid_pk()
    property_id = db.Column(
        db.String(36), db.ForeignKey("properties.id"), nullable=False, unique=True, index=True
    )

    # Short teaser/header blurb, same purpose for both SALE and RENT (Kennedys
    # used different field names per listing type for the same concept —
    # consolidated here so the editor doesn't have to guess which one to show).
    summary = db.Column(db.Text, nullable=True)
    # Full detailed body copy. Supersedes the old Property.description.
    description = db.Column(db.Text, nullable=True)
    extra_info = db.Column(db.Text, nullable=True)
    included_services = db.Column(db.JSON, nullable=False, default=list)
    # Free-form notes that don't fit elsewhere (replaces the old separate
    # extra_services/added_values/staff_and_services fields — same purpose,
    # just one field instead of three near-duplicates).
    additional_notes = db.Column(db.Text, nullable=True)
    our_note = db.Column(db.Text, nullable=True)

    # Villa Page "Outdoor Block" (rental only)
    outdoor_title = db.Column(db.String(200), nullable=True)
    outdoor_description = db.Column(db.Text, nullable=True)
    outdoor_image_url = db.Column(db.String(1000), nullable=True)

    # Villa Page "The Villa" + Experiences (rental only)
    # {groups: [{title, items: []}], featuredExperienceIds: [], hideNearbyExperiences: bool}
    the_villa = db.Column(db.JSON, nullable=True)

    property = db.relationship("Property", back_populates="content")


class Pool(db.Model, TimestampMixin):
    __tablename__ = "pools"

    id = uuid_pk()
    property_id = db.Column(db.String(36), db.ForeignKey("properties.id"), nullable=False, index=True)
    type = db.Column(db.String(10), nullable=False, default="POOL")
    quantity = db.Column(db.Integer, nullable=False, default=1)
    pool_type = db.Column(db.JSON, nullable=False, default=list)

    property = db.relationship("Property", back_populates="pools")


class RatePeriod(db.Model, TimestampMixin):
    """Seasonal rate card entry — rental properties only."""

    __tablename__ = "rate_periods"

    id = uuid_pk()
    property_id = db.Column(db.String(36), db.ForeignKey("properties.id"), nullable=False, index=True)

    label = db.Column(db.String(200), nullable=True)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    official_price_per_night = db.Column(db.Float, nullable=True)
    management_fee_pct = db.Column(db.Float, nullable=False, default=10)
    agency_commission_pct = db.Column(db.Float, nullable=False, default=20)
    net_owner_per_night = db.Column(db.Float, nullable=True)
    min_stay = db.Column(db.Integer, nullable=True)
    included_services = db.Column(db.Text, nullable=True)

    property = db.relationship("Property", back_populates="rate_periods")


class ImprovementRecommendation(db.Model, TimestampMixin):
    __tablename__ = "improvement_recommendations"

    id = uuid_pk()
    property_id = db.Column(db.String(36), db.ForeignKey("properties.id"), nullable=False, index=True)

    title = db.Column(db.String(200), nullable=False)
    details = db.Column(db.Text, nullable=True)
    priority = db.Column(db.String(10), nullable=False, default="MEDIUM")
    est_cost = db.Column(db.Float, nullable=True)
    pdf_url = db.Column(db.String(1000), nullable=True)
    status = db.Column(db.String(10), nullable=False, default="PROPOSED")

    property = db.relationship("Property", back_populates="recommendations")
