from collections import defaultdict
from datetime import date, datetime, timedelta

import requests
from icalendar import Calendar, Event
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.availability import AvailabilityBlock
from app.models.booking import Booking
from app.models.property import Property
from app.utils.tenancy import agent_scope

ICAL_FETCH_TIMEOUT_SECONDS = 10
CALENDAR_WINDOW_DAYS = 90
ICAL_MAX_BYTES = 2 * 1024 * 1024  # 2MB is already generous for a calendar feed


class AvailabilityError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _get_property(agency_id: str, property_id: str) -> Property:
    query = Property.query.filter_by(id=property_id, agency_id=agency_id, deleted_at=None)
    # An agent only manages the calendar of what's assigned to them.
    scope = agent_scope()
    if scope:
        query = query.filter(Property.assigned_agent_id == scope)
    prop = query.first()
    if prop is None:
        raise AvailabilityError("Property not found", 404)
    return prop


def list_blocks(agency_id: str, property_id: str) -> list[AvailabilityBlock]:
    _get_property(agency_id, property_id)
    return (
        AvailabilityBlock.query.filter_by(property_id=property_id)
        .order_by(AvailabilityBlock.start_date)
        .all()
    )


def create_block(agency_id: str, property_id: str, data: dict) -> AvailabilityBlock:
    _get_property(agency_id, property_id)
    if data["start_date"] > data["end_date"]:
        raise AvailabilityError("startDate must be on or before endDate", 400)

    block = AvailabilityBlock(
        property_id=property_id,
        start_date=data["start_date"],
        end_date=data["end_date"],
        note=data.get("note"),
        source="MANUAL",
    )
    db.session.add(block)
    db.session.commit()
    return block


def delete_block(agency_id: str, property_id: str, block_id: str) -> None:
    _get_property(agency_id, property_id)
    block = AvailabilityBlock.query.filter_by(id=block_id, property_id=property_id).first()
    if block is None:
        raise AvailabilityError("Block not found", 404)
    if block.source != "MANUAL":
        raise AvailabilityError(f"Cannot delete a block synced from {block.source}", 400)

    db.session.delete(block)
    db.session.commit()


def _as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    return value


def parse_ical_blocks(ical_text: str) -> list[dict]:
    """Extract (uid, start_date, end_date) for every VEVENT in a raw ICS feed."""
    calendar = Calendar.from_ical(ical_text)
    blocks = []
    for component in calendar.walk("VEVENT"):
        dtstart = component.get("dtstart")
        dtend = component.get("dtend")
        if dtstart is None:
            continue
        start = _as_date(dtstart.dt)
        end = _as_date(dtend.dt) if dtend is not None else start
        uid = str(component.get("uid") or f"{start.isoformat()}-{end.isoformat()}")
        blocks.append({"uid": uid, "start_date": start, "end_date": end})
    return blocks


def sync_ical(agency_id: str, property_id: str, ical_url: str) -> dict:
    prop = _get_property(agency_id, property_id)

    try:
        response = requests.get(ical_url, timeout=ICAL_FETCH_TIMEOUT_SECONDS, stream=True)
        response.raise_for_status()
        content = response.raw.read(ICAL_MAX_BYTES + 1, decode_content=True)
    except requests.RequestException as err:
        raise AvailabilityError(f"Could not fetch calendar: {err}", 400)

    if len(content) > ICAL_MAX_BYTES:
        raise AvailabilityError("Calendar feed is too large", 400)

    try:
        parsed = parse_ical_blocks(content.decode("utf-8", errors="replace"))
    except ValueError as err:
        raise AvailabilityError(f"Invalid iCal feed: {err}", 400)

    existing = {b.ical_uid: b for b in AvailabilityBlock.query.filter_by(
        property_id=property_id, source="ICAL"
    )}
    seen_uids = set()

    for item in parsed:
        seen_uids.add(item["uid"])
        block = existing.get(item["uid"])
        if block is None:
            db.session.add(
                AvailabilityBlock(
                    property_id=property_id,
                    start_date=item["start_date"],
                    end_date=item["end_date"],
                    source="ICAL",
                    ical_uid=item["uid"],
                )
            )
        else:
            block.start_date = item["start_date"]
            block.end_date = item["end_date"]

    for uid, block in existing.items():
        if uid not in seen_uids:
            db.session.delete(block)

    prop.ical_import_url = ical_url
    db.session.commit()
    return {"importedCount": len(parsed)}


def export_ics(property_: Property) -> bytes:
    calendar = Calendar()
    calendar.add("prodid", "-//Inmobiliario//Availability//ES")
    calendar.add("version", "2.0")

    blocks = AvailabilityBlock.query.filter_by(property_id=property_.id).all()
    for block in blocks:
        event = Event()
        event.add("uid", block.ical_uid or block.id)
        event.add("summary", f"No disponible — {property_.title}")
        event.add("dtstart", block.start_date)
        event.add("dtend", block.end_date)
        calendar.add_component(event)

    return calendar.to_ical()


def _cover_url(property_: Property) -> str | None:
    photos = sorted(property_.photos, key=lambda photo: (not photo.is_cover, photo.position))
    return photos[0].url if photos else None


def agency_calendar(
    agency_id: str,
    *,
    published_only: bool,
    window_days: int = CALENDAR_WINDOW_DAYS,
    start: date | None = None,
) -> dict:
    """Every rental property's availability for `window_days` days from `start`
    (today by default), as a set of blocked dates per property — the data behind
    the agency-wide calendar (dashboard grid and month view, and the public share link).

    `published_only=True` is what the public link shows; the dashboard passes
    False so staff also see draft/unpublished listings they're tracking.
    """
    query = Property.query.options(selectinload(Property.photos)).filter_by(
        agency_id=agency_id, listing_type="RENT", parent_property_id=None, deleted_at=None
    )
    if published_only:
        query = query.filter_by(status="PUBLISHED")
    elif agent_scope():
        # In the dashboard an agent only sees the listings assigned to them.
        query = query.filter(Property.assigned_agent_id == agent_scope())
    properties = query.order_by(Property.title).all()

    today = start or date.today()
    window_end = today + timedelta(days=window_days - 1)

    blocked_by_property: dict[str, set[date]] = defaultdict(set)
    # Pending bookings don't block the calendar yet (only a confirmed one does),
    # but the agency wants to see them. Never shown on the public link.
    pending_by_property: dict[str, set[date]] = defaultdict(set)
    if properties and not published_only:
        pending = Booking.query.filter(
            Booking.property_id.in_([prop.id for prop in properties]),
            Booking.status == "PENDING",
            Booking.deleted_at.is_(None),
            Booking.start_date.isnot(None),
            Booking.end_date.isnot(None),
            Booking.start_date <= window_end,
            Booking.end_date >= today,
        ).all()
        for booking in pending:
            cursor = max(booking.start_date, today)
            last = min(booking.end_date, window_end)
            while cursor <= last:
                pending_by_property[booking.property_id].add(cursor)
                cursor += timedelta(days=1)
    if properties:
        property_ids = [prop.id for prop in properties]
        blocks = AvailabilityBlock.query.filter(
            AvailabilityBlock.property_id.in_(property_ids),
            AvailabilityBlock.start_date <= window_end,
            AvailabilityBlock.end_date >= today,
        ).all()
        for block in blocks:
            cursor = max(block.start_date, today)
            last = min(block.end_date, window_end)
            while cursor <= last:
                blocked_by_property[block.property_id].add(cursor)
                cursor += timedelta(days=1)

    return {
        "from": today.isoformat(),
        "to": window_end.isoformat(),
        "properties": [
            {
                "id": prop.id,
                "title": prop.title,
                "slug": prop.slug,
                "category": prop.category,
                "country": prop.country,
                "region": prop.region,
                "area": prop.area,
                "price": prop.price,
                "currency": prop.currency,
                "coverUrl": _cover_url(prop),
                "blockedDates": sorted(d.isoformat() for d in blocked_by_property.get(prop.id, ())),
                "pendingDates": sorted(d.isoformat() for d in pending_by_property.get(prop.id, ())),
            }
            for prop in properties
        ],
    }
