"""The change history of properties, offers and bookings.

A listener on every flush looks at what's about to be written and leaves one
AuditEvent per changed property, offer or booking: who did it (the signed-in
user, or nobody on a public link), when, and which fields went from what to
what. Changes to what hangs from them (photos, rate periods, an offer's
properties, a booking's payments) count as a change to their parent, named by
what changed. Nothing in the routes has to remember to log.

Bulk `query.update()` calls skip the ORM and so skip this too; they're only
used for bookkeeping (unlinking a deleted client, marking inquiries read).
"""
from datetime import date, datetime, timezone
from uuid import uuid4

from flask import has_request_context
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.models import (
    AuditEvent,
    Booking,
    Classification,
    Description,
    Offer,
    OfferProperty,
    OfferSection,
    OfferService,
    Payment,
    Pool,
    Property,
    PropertyPhoto,
    RatePeriod,
)

ROOTS = {Property: "PROPERTY", Offer: "OFFER", Booking: "BOOKING"}

# Child model -> (its parent's relationship, the name the change goes under).
CHILDREN = {
    OfferSection: ("offer", "sections"),
    OfferProperty: ("offer", "properties"),
    OfferService: ("offer", "services"),
    Payment: ("booking", "payments"),
    PropertyPhoto: ("property", "photos"),
    Classification: ("property", "classification"),
    Description: ("property", "content"),
    Pool: ("property", "pools"),
    RatePeriod: ("property", "rates"),
}

PARENTS = {"offer": Offer, "booking": Booking, "property": Property}

# Bookkeeping, not changes anyone made: never listed.
IGNORED = {
    "id",
    "agency_id",
    "created_at",
    "updated_at",
    "token",
    "deleted_at",
    "availability_block_id",
    "view_count",
    "first_viewed_at",
    "last_viewed_at",
}
# Free text and contact details: the history says they changed, not what they say.
PRIVATE = {"notes", "welcome_content", "client_email", "client_phone", "ical_import_url"}
MAX_VALUE = 120


def _value(field: str, value):
    if field in PRIVATE:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= MAX_VALUE else None
    return None  # lists and JSON: too long to be useful here


def _actor() -> str | None:
    if not has_request_context():
        return None
    try:
        verify_jwt_in_request(optional=True)
        return get_jwt_identity()
    except Exception:  # noqa: BLE001 - an expired or bad token just means "nobody"
        return None


def _field_changes(obj) -> dict:
    state = inspect(obj)
    changes = {}
    for attr in state.mapper.column_attrs:
        key = attr.key
        if key in IGNORED:
            continue
        history = state.attrs[key].history
        if not history.has_changes():
            continue
        old = history.deleted[0] if history.deleted else None
        new = history.added[0] if history.added else None
        if old == new:
            continue
        changes[key] = {"from": _value(key, old), "to": _value(key, new)}
    return changes


def _deleted_at_move(obj) -> str | None:
    history = inspect(obj).attrs["deleted_at"].history
    if not history.has_changes():
        return None
    old = history.deleted[0] if history.deleted else None
    new = history.added[0] if history.added else None
    if old is None and new is not None:
        return "TRASHED"
    if old is not None and new is None:
        return "RESTORED"
    return None


def _before_flush(session: Session, _context, _instances) -> None:
    events: dict[tuple[str, str], dict] = {}
    created = set()

    def entry(obj, action="UPDATED"):
        if obj.id is None:
            obj.id = str(uuid4())
        key = (ROOTS[type(obj)], obj.id)
        if key not in events:
            events[key] = {"agency_id": obj.agency_id, "action": action, "changes": {}}
        elif action != "UPDATED":
            events[key]["action"] = action
        return events[key]

    for obj in session.new:
        if type(obj) in ROOTS:
            entry(obj, "CREATED")
            created.add(id(obj))
    for obj in session.deleted:
        if type(obj) in ROOTS:
            entry(obj, "DELETED")
    for obj in session.dirty:
        if type(obj) not in ROOTS or not session.is_modified(obj, include_collections=False):
            continue
        moved = _deleted_at_move(obj)
        changes = _field_changes(obj)
        if moved or changes:
            item = entry(obj, moved or "UPDATED")
            item["changes"].update(changes)

    # session.dirty builds a new set on each access, so each collection carries its own flag.
    for dirty, collection in ((False, session.new), (True, session.dirty), (False, session.deleted)):
        for obj in collection:
            spec = CHILDREN.get(type(obj))
            if spec is None:
                continue
            # Saving a form rewrites its sub-records whole: only a real change counts.
            if dirty and not _field_changes(obj):
                continue
            relation, label = spec
            parent = getattr(obj, relation, None)
            if parent is None:
                # Created with just the parent's id (Payment(booking_id=...)): look it up.
                parent_id = getattr(obj, f"{relation}_id", None)
                with session.no_autoflush:
                    parent = session.get(PARENTS[relation], parent_id) if parent_id else None
            # A brand-new parent's own "created" already says it all.
            if parent is None or id(parent) in created or parent in session.new:
                continue
            item = entry(parent)
            if item["action"] == "DELETED":
                continue
            item["changes"][label] = {"changed": True}

    if not events:
        return
    user_id = _actor()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for (entity_type, entity_id), item in events.items():
        if item["action"] == "UPDATED" and not item["changes"]:
            continue
        session.add(
            AuditEvent(
                agency_id=item["agency_id"],
                entity_type=entity_type,
                entity_id=entity_id,
                user_id=user_id,
                action=item["action"],
                changes=item["changes"] or None,
                created_at=now,
            )
        )


def register() -> None:
    """Listens on every session; safe to call once per app created."""
    if not event.contains(Session, "before_flush", _before_flush):
        event.listen(Session, "before_flush", _before_flush)


def history(entity_type: str, entity_id: str, limit: int = 100) -> list[AuditEvent]:
    return (
        AuditEvent.query.filter_by(entity_type=entity_type, entity_id=entity_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
        .all()
    )


def serialize(events: list[AuditEvent]) -> list[dict]:
    """With each author's name, loaded in one query."""
    from app.models import User

    ids = {item.user_id for item in events if item.user_id}
    names = {user.id: user.name for user in User.query.filter(User.id.in_(ids)).all()} if ids else {}
    return [
        {
            "id": item.id,
            "action": item.action,
            "changes": item.changes or {},
            "userName": names.get(item.user_id),
            "byUser": item.user_id is not None,
            "at": item.created_at.replace(tzinfo=timezone.utc).isoformat(),
        }
        for item in events
    ]
