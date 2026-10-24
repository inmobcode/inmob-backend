from app.extensions import db
from app.models.base import TimestampMixin, TrashMixin, uuid_pk

CLIENT_STAGES = ("LEAD", "CONTACTED", "NEGOTIATING", "CLIENT", "LOST")
CLIENT_SOURCES = ("WEBSITE", "MANUAL", "OFFER")
INTERACTION_TYPES = ("NOTE", "CALL", "EMAIL", "MEETING")
INQUIRY_TYPES = ("PROPERTY", "OFFER", "GENERAL")


class Client(db.Model, TimestampMixin, TrashMixin):
    __tablename__ = "clients"
    __table_args__ = (db.UniqueConstraint("agency_id", "email", name="uq_client_agency_email"),)

    id = uuid_pk()
    agency_id = db.Column(db.String(36), db.ForeignKey("agencies.id"), nullable=False, index=True)
    assigned_agent_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)

    name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(50), nullable=True)
    source = db.Column(db.String(20), nullable=False, default="MANUAL")
    stage = db.Column(db.String(20), nullable=False, default="LEAD")
    notes = db.Column(db.Text, nullable=True)
    # The language they last wrote to the agency in (from its public site);
    # booking and offer emails use it before falling back to the site's.
    locale = db.Column(db.String(5), nullable=True)
    # The agency's own labels ("VIP", "inversor", "verano 2027"), to filter and export by.
    tags = db.Column(db.JSON, nullable=False, default=list)

    # What they're looking for. The budget is in the agency's currency.
    budget_min = db.Column(db.Float, nullable=True)
    budget_max = db.Column(db.Float, nullable=True)
    guests = db.Column(db.Integer, nullable=True)
    zones = db.Column(db.String(300), nullable=True)
    desired_from = db.Column(db.Date, nullable=True)
    desired_to = db.Column(db.Date, nullable=True)

    interactions = db.relationship(
        "Interaction",
        back_populates="client",
        order_by="Interaction.created_at.desc()",
        cascade="all, delete-orphan",
    )


class Interaction(db.Model, TimestampMixin):
    __tablename__ = "interactions"

    id = uuid_pk()
    client_id = db.Column(db.String(36), db.ForeignKey("clients.id"), nullable=False, index=True)
    created_by = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)

    type = db.Column(db.String(10), nullable=False, default="NOTE")
    content = db.Column(db.Text, nullable=False)

    client = db.relationship("Client", back_populates="interactions")


class Inquiry(db.Model, TimestampMixin, TrashMixin):
    __tablename__ = "inquiries"

    id = uuid_pk()
    agency_id = db.Column(db.String(36), db.ForeignKey("agencies.id"), nullable=False, index=True)
    client_id = db.Column(db.String(36), db.ForeignKey("clients.id"), nullable=True, index=True)
    property_id = db.Column(db.String(36), db.ForeignKey("properties.id"), nullable=True)
    offer_id = db.Column(db.String(36), db.ForeignKey("offers.id"), nullable=True)

    inquiry_type = db.Column(db.String(20), nullable=False, default="GENERAL")
    name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(50), nullable=True)
    message = db.Column(db.Text, nullable=True)
    # When someone on the agency's team opened it in the inbox; null means new.
    read_at = db.Column(db.DateTime, nullable=True)
    # Out of the inbox but kept: dealt with, or nothing to do.
    archived_at = db.Column(db.DateTime, nullable=True, index=True)
    # The last answer sent from the dashboard (the answers themselves go to the client's history).
    replied_at = db.Column(db.DateTime, nullable=True)
    replied_by = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)


class ReplyTemplate(db.Model, TimestampMixin):
    """A ready-made answer the team picks when replying to an inquiry. Its text
    carries placeholders ({name}, {property}…) the dashboard fills in."""

    __tablename__ = "reply_templates"

    id = uuid_pk()
    agency_id = db.Column(db.String(36), db.ForeignKey("agencies.id"), nullable=False, index=True)
    created_by = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)

    name = db.Column(db.String(120), nullable=False)
    subject = db.Column(db.String(200), nullable=True)
    body = db.Column(db.Text, nullable=False)
