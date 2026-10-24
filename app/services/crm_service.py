from app import i18n
from app.extensions import db
from app.models import Agency, Booking, Client, Inquiry, Interaction, Offer, Property, Task
from app.services import feed
from app.services.notifications import notify_new_inquiry, staff_locale
from app.utils import trash
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


def live_clients(query):
    """The clients someone can see, leaving out the ones in the trash."""
    return visible_clients(query).filter(Client.deleted_at.is_(None))


def visible_inquiries(query):
    """An AGENT sees the inquiries of the clients they can see."""
    if not agent_scope():
        return query
    visible = visible_clients(db.session.query(Client.id))
    return query.filter(db.or_(Inquiry.client_id.is_(None), Inquiry.client_id.in_(visible)))


def list_clients(agency_id: str):
    return live_clients(Client.query.filter_by(agency_id=agency_id)).order_by(Client.created_at.desc()).all()


def get_client(agency_id: str, client_id: str, *, trashed: bool = False) -> Client:
    """A live client, or with trashed=True one in the trash."""
    query = visible_clients(Client.query.filter_by(id=client_id, agency_id=agency_id))
    query = query.filter(Client.deleted_at.isnot(None) if trashed else Client.deleted_at.is_(None))
    client = query.first()
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


def _check_preferences(budget_min, budget_max, desired_from, desired_to) -> None:
    if budget_min is not None and budget_max is not None and budget_min > budget_max:
        raise ClientError("The minimum budget can't be higher than the maximum", 400)
    if desired_from and desired_to and desired_to < desired_from:
        raise ClientError("The end date can't be before the start date", 400)


def create_client(agency_id: str, created_by: str, data: dict) -> Client:
    _check_assignee(agency_id, data)
    _check_preferences(
        data.get("budget_min"), data.get("budget_max"), data.get("desired_from"), data.get("desired_to")
    )
    # One client per email in an agency, the trashed ones included.
    existing = Client.query.filter_by(agency_id=agency_id, email=data["email"]).first()
    if existing is not None:
        if existing.deleted_at is not None:
            raise ClientError("A client with that email is in the trash", 409)
        raise ClientError("A client with that email already exists", 409)
    # Whoever adds a client looks after them; only web leads start unassigned.
    if not data.get("assigned_agent_id"):
        data = {**data, "assigned_agent_id": created_by}
    client = Client(agency_id=agency_id, source="MANUAL", **data)
    db.session.add(client)
    db.session.commit()
    return client


def update_client(agency_id: str, client_id: str, data: dict, by_user_id: str | None = None) -> Client:
    client = get_client(agency_id, client_id)
    reassigned = "assigned_agent_id" in data and data["assigned_agent_id"] != client.assigned_agent_id
    _check_assignee(agency_id, data)
    _check_preferences(
        data.get("budget_min", client.budget_min),
        data.get("budget_max", client.budget_max),
        data.get("desired_from", client.desired_from),
        data.get("desired_to", client.desired_to),
    )
    for field, value in data.items():
        setattr(client, field, value)
    db.session.commit()
    if reassigned:
        feed.notify_client_assigned(client, by_user_id)
    return client


def delete_client(agency_id: str, client_id: str) -> None:
    """Moves the client to the trash. Their offers, bookings and history stay as they are."""
    client = get_client(agency_id, client_id)
    client.deleted_at = trash.now()
    db.session.commit()


def list_trashed_clients(agency_id: str):
    purge_trashed_clients(agency_id)
    return (
        visible_clients(Client.query.filter(Client.agency_id == agency_id, Client.deleted_at.isnot(None)))
        .order_by(Client.deleted_at.desc())
        .all()
    )


def restore_client(agency_id: str, client_id: str) -> Client:
    client = get_client(agency_id, client_id, trashed=True)
    client.deleted_at = None
    db.session.commit()
    return client


def _has_bookings(client: Client) -> bool:
    """Bookings are the agency's accounts and show who stayed, so the client has to stay too."""
    return Booking.query.filter_by(client_id=client.id).first() is not None


def _delete_for_good(client: Client) -> None:
    # Offers keep their own copy of the contact details; inquiries keep the name and email they came with.
    Offer.query.filter_by(client_id=client.id).update({"client_id": None})
    Inquiry.query.filter_by(client_id=client.id).update({"client_id": None})
    Task.query.filter_by(client_id=client.id).delete()
    db.session.delete(client)


def delete_client_forever(agency_id: str, client_id: str) -> None:
    client = get_client(agency_id, client_id, trashed=True)
    if _has_bookings(client):
        raise ClientError("The client has bookings, so it stays in the trash", 409)
    _delete_for_good(client)
    db.session.commit()


def purge_trashed_clients(agency_id: str) -> None:
    """Deletes for good what has been in the trash longer than TRASH_DAYS,
    except clients with bookings."""
    for client in Client.query.filter(
        Client.agency_id == agency_id,
        Client.deleted_at.isnot(None),
        Client.deleted_at < trash.purge_cutoff(),
    ).all():
        if not _has_bookings(client):
            _delete_for_good(client)
    db.session.commit()


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
    # Someone who writes again is back: a client in the trash comes out of it.
    if client is not None and client.deleted_at is not None:
        client.deleted_at = None
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
