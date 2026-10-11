from app.extensions import db
from app.models import Client, Inquiry, Interaction
from app.services.notifications import notify_new_inquiry


class ClientError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def list_clients(agency_id: str):
    return Client.query.filter_by(agency_id=agency_id).order_by(Client.created_at.desc()).all()


def get_client(agency_id: str, client_id: str) -> Client:
    client = Client.query.filter_by(id=client_id, agency_id=agency_id).first()
    if client is None:
        raise ClientError("Client not found", 404)
    return client


def create_client(agency_id: str, data: dict) -> Client:
    client = Client(agency_id=agency_id, source="MANUAL", **data)
    db.session.add(client)
    db.session.commit()
    return client


def update_client(agency_id: str, client_id: str, data: dict) -> Client:
    client = get_client(agency_id, client_id)
    for field, value in data.items():
        setattr(client, field, value)
    db.session.commit()
    return client


def add_interaction(agency_id: str, client_id: str, created_by: str | None, data: dict) -> Interaction:
    client = get_client(agency_id, client_id)
    interaction = Interaction(
        client_id=client.id,
        created_by=created_by,
        type=data.get("type", "NOTE"),
        content=data["content"],
    )
    db.session.add(interaction)
    db.session.commit()
    return interaction


def find_or_create_client(agency_id: str, *, name: str, email: str, phone: str | None, source: str) -> Client:
    client = Client.query.filter_by(agency_id=agency_id, email=email).first()
    if client is None:
        client = Client(agency_id=agency_id, name=name, email=email, phone=phone, source=source, stage="LEAD")
        db.session.add(client)
    else:
        client.name = name
        if phone:
            client.phone = phone
    db.session.flush()
    return client


def log_inquiry(
    agency_id: str,
    *,
    name: str,
    email: str,
    phone: str | None,
    message: str | None,
    inquiry_type: str,
    source: str,
    property_id: str | None = None,
    offer_id: str | None = None,
) -> Inquiry:
    """Dual-write: upsert the Client, log an Interaction on it, and record
    the raw Inquiry — mirrors the Kennedys owner-intake pattern (structured
    lead record + notification), minus the actual email send for now."""

    client = find_or_create_client(agency_id, name=name, email=email, phone=phone, source=source)

    inquiry = Inquiry(
        agency_id=agency_id,
        client_id=client.id,
        property_id=property_id,
        offer_id=offer_id,
        inquiry_type=inquiry_type,
        name=name,
        email=email,
        phone=phone,
        message=message,
    )
    db.session.add(inquiry)

    interaction_label = {
        "PROPERTY": "Consultó por una propiedad",
        "OFFER": "Respondió a una oferta",
        "GENERAL": "Dejó una consulta",
    }.get(inquiry_type, "Dejó una consulta")
    db.session.add(
        Interaction(
            client_id=client.id,
            type="NOTE",
            content=f"{interaction_label}: {message}" if message else interaction_label,
        )
    )

    db.session.commit()
    notify_new_inquiry(inquiry)
    return inquiry
