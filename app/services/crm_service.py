from app import i18n
from app.extensions import db
from app.models import Agency, Client, Inquiry, Interaction, Offer, Property
from app.services import feed
from app.services.notifications import notify_new_inquiry, staff_locale
from app.utils.tenancy import agent_scope, is_member


class ClientError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def visible_clients(query):
    """An AGENT sees their own clients plus the ones nobody has taken yet (new web leads)."""
    scope = agent_scope()
    if scope:
        return query.filter(db.or_(Client.assigned_agent_id == scope, Client.assigned_agent_id.is_(None)))
    return query


def visible_inquiries(query):
    """An AGENT sees the inquiries of the clients they can see."""
    if not agent_scope():
        return query
    visible = visible_clients(db.session.query(Client.id))
    return query.filter(db.or_(Inquiry.client_id.is_(None), Inquiry.client_id.in_(visible)))


def list_clients(agency_id: str):
    return visible_clients(Client.query.filter_by(agency_id=agency_id)).order_by(Client.created_at.desc()).all()


def get_client(agency_id: str, client_id: str) -> Client:
    client = visible_clients(Client.query.filter_by(id=client_id, agency_id=agency_id)).first()
    if client is None:
        raise ClientError("Client not found", 404)
    return client


def _check_assignee(agency_id: str, data: dict) -> None:
    """Handing a client to someone else is for owners and admins; an agent can only take one."""
    if "assigned_agent_id" not in data:
        return
    target = data["assigned_agent_id"]
    scope = agent_scope()
    if scope and target not in (scope, None):
        raise ClientError("Forbidden", 403)
    if target and not is_member(agency_id, target):
        raise ClientError("Agent not found", 404)


def create_client(agency_id: str, created_by: str, data: dict) -> Client:
    _check_assignee(agency_id, data)
    # Whoever adds a client looks after them; only web leads start unassigned.
    if not data.get("assigned_agent_id"):
        data = {**data, "assigned_agent_id": created_by}
    client = Client(agency_id=agency_id, source="MANUAL", **data)
    db.session.add(client)
    db.session.commit()
    return client


def update_client(agency_id: str, client_id: str, data: dict) -> Client:
    client = get_client(agency_id, client_id)
    _check_assignee(agency_id, data)
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
    locale: str | None = None,
) -> Inquiry:
    """Dual-write: upsert the Client, log an Interaction on it, and record
    the raw Inquiry — mirrors the Kennedys owner-intake pattern (structured
    lead record + notification), minus the actual email send for now."""

    client = find_or_create_client(agency_id, name=name, email=email, phone=phone, source=source)
    # Remember the language they wrote in: their booking and offer emails use it.
    if i18n.normalize(locale):
        client.locale = i18n.normalize(locale)

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

    # The client's history is read by the team, so the note is in the team's language.
    agency = db.session.get(Agency, agency_id)
    lang = staff_locale(agency)
    interaction_label = i18n.t(
        lang, {"PROPERTY": "note.property_generic", "OFFER": "note.offer_generic"}.get(inquiry_type, "note.general")
    )
    # Name what they asked about, so the client's history says which listing or offer.
    if property_id:
        prop = db.session.get(Property, property_id)
        if prop is not None:
            interaction_label = i18n.t(lang, "note.property", property=prop.title)
    elif offer_id:
        offer = db.session.get(Offer, offer_id)
        if offer is not None:
            interaction_label = i18n.t(lang, "note.offer", offer=offer.title)
    db.session.add(
        Interaction(
            client_id=client.id,
            type="NOTE",
            content=f"{interaction_label}: {message}" if message else interaction_label,
        )
    )

    db.session.commit()
    notify_new_inquiry(inquiry, locale)
    feed.notify_inquiry(inquiry, client)
    return inquiry
