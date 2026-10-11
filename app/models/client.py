from app.extensions import db
from app.models.base import TimestampMixin, uuid_pk

CLIENT_STAGES = ("LEAD", "CONTACTED", "NEGOTIATING", "CLIENT", "LOST")
CLIENT_SOURCES = ("WEBSITE", "MANUAL", "OFFER")
INTERACTION_TYPES = ("NOTE", "CALL", "EMAIL", "MEETING")
INQUIRY_TYPES = ("PROPERTY", "OFFER", "GENERAL")


class Client(db.Model, TimestampMixin):
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


class Inquiry(db.Model, TimestampMixin):
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
