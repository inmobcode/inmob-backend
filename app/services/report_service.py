"""The agency's reports: money per month, occupancy per property, how inquiries
turn into bookings, and each team member's results, for a range of months.

Definitions (the dashboard explains them with the same words):
- A booking counts once it's CONFIRMED or COMPLETED, in the month of its
  check-in, or of its creation when it has no dates (a sale).
- "Booked" is the total price of those bookings; "commission" is their
  commission amount. "Collected" is the client payments (deposits and
  balances) marked paid in the month, whatever the booking's status.
- Occupancy counts nights: a night is taken by a booking or a block synced by
  iCal, and out of the market when the owner or the agency blocked it by hand.
- Money is never added across currencies: each amount is per currency.
"""
from collections import defaultdict
from datetime import date, datetime, timedelta

from app.models import (
    AgencyMembership,
    AvailabilityBlock,
    Booking,
    Client,
    Inquiry,
    Offer,
    Payment,
    Property,
    User,
)

COUNTED = ("CONFIRMED", "COMPLETED")
MAX_MONTHS = 36


class ReportError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _month(value: date) -> str:
    return value.strftime("%Y-%m")


def _months(start: date, end: date) -> list[str]:
    months, current = [], start.replace(day=1)
    while current <= end:
        months.append(_month(current))
        current = (current.replace(day=28) + timedelta(days=4)).replace(day=1)
    return months


def period(from_: str | None, to: str | None) -> tuple[date, date]:
    """Whole months: from the first day of `from_`'s month to the last of `to`'s.
    By default the last 12 months, this one included."""
    today = date.today()
    try:
        end = date.fromisoformat(to) if to else today
        start = date.fromisoformat(from_) if from_ else (end.replace(day=1) - timedelta(days=330)).replace(day=1)
    except ValueError as err:
        raise ReportError("Invalid date", 400) from err
    start = start.replace(day=1)
    end = (end.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    if end < start:
        raise ReportError("Invalid date", 400)
    if len(_months(start, end)) > MAX_MONTHS:
        raise ReportError("Invalid date", 400)
    return start, end


def _booking_day(booking: Booking) -> date:
    return booking.start_date or booking.created_at.date()


def _in(day: date, start: date, end: date) -> bool:
    return start <= day <= end


def _counted_bookings(agency_id: str, start: date, end: date) -> list[Booking]:
    bookings = Booking.query.filter(
        Booking.agency_id == agency_id, Booking.deleted_at.is_(None), Booking.status.in_(COUNTED)
    ).all()
    return [booking for booking in bookings if _in(_booking_day(booking), start, end)]


def _money(agency_id: str, start: date, end: date, bookings: list[Booking]) -> dict:
    """{currency: [{month, booked, collected, commission, bookings}]}, one row per month."""
    months = _months(start, end)
    table: dict[str, dict[str, dict]] = defaultdict(
        lambda: {month: {"month": month, "booked": 0.0, "collected": 0.0, "commission": 0.0, "bookings": 0} for month in months}
    )
    for booking in bookings:
        row = table[booking.currency][_month(_booking_day(booking))]
        row["booked"] += booking.total_price or 0
        row["commission"] += booking.commission_amount or 0
        row["bookings"] += 1

    payments = (
        Payment.query.join(Booking, Booking.id == Payment.booking_id)
        .filter(
            Booking.agency_id == agency_id,
            Booking.deleted_at.is_(None),
            Payment.status == "PAID",
            Payment.type != "COMMISSION",
            Payment.paid_at >= datetime.combine(start, datetime.min.time()),
            Payment.paid_at < datetime.combine(end + timedelta(days=1), datetime.min.time()),
        )
        .all()
    )
    for payment in payments:
        table[payment.currency][_month(payment.paid_at.date())]["collected"] += payment.amount
    return {currency: list(rows.values()) for currency, rows in sorted(table.items())}


def _nights(block_start: date, block_end: date, start: date, end: date) -> set[date]:
    """The nights of [block_start, block_end) that fall inside the period."""
    first, last = max(block_start, start), min(block_end, end + timedelta(days=1))
    return {first + timedelta(days=offset) for offset in range((last - first).days)} if last > first else set()


def _occupancy(agency_id: str, start: date, end: date) -> list[dict]:
    """Per rental: nights in the period, taken (bookings, iCal), blocked by hand, and the rate."""
    total = (end - start).days + 1
    rentals = Property.query.filter_by(agency_id=agency_id, listing_type="RENT", deleted_at=None).all()
    blocks = AvailabilityBlock.query.filter(
        AvailabilityBlock.property_id.in_([prop.id for prop in rentals] or [""]),
        AvailabilityBlock.start_date <= end,
        AvailabilityBlock.end_date > start,
    ).all()
    by_property: dict[str, dict[str, set[date]]] = defaultdict(lambda: {"BOOKING": set(), "ICAL": set(), "MANUAL": set()})
    for block in blocks:
        by_property[block.property_id][block.source] |= _nights(block.start_date, block.end_date, start, end)

    rows = []
    for prop in rentals:
        nights = by_property[prop.id]
        booked = nights["BOOKING"]
        external = nights["ICAL"] - booked
        blocked = nights["MANUAL"] - booked - external
        available = total - len(blocked)
        taken = len(booked) + len(external)
        rows.append(
            {
                "propertyId": prop.id,
                "title": prop.title,
                "nights": total,
                "booked": len(booked),
                "external": len(external),
                "blocked": len(blocked),
                "rate": round(taken / available, 4) if available > 0 else None,
            }
        )
    return sorted(rows, key=lambda row: (row["rate"] is None, -(row["rate"] or 0), row["title"]))


def _conversion(agency_id: str, start: date, end: date) -> dict:
    """Of the people who wrote in during the period: how many got an offer, and
    how many booked (anything but a cancelled booking), after their first inquiry."""
    inquiries = Inquiry.query.filter(
        Inquiry.agency_id == agency_id,
        Inquiry.deleted_at.is_(None),
        Inquiry.created_at >= datetime.combine(start, datetime.min.time()),
        Inquiry.created_at < datetime.combine(end + timedelta(days=1), datetime.min.time()),
    ).all()
    first_contact: dict[str, datetime] = {}
    by_type: dict[str, set[str]] = defaultdict(set)
    for inquiry in inquiries:
        if not inquiry.client_id:
            continue
        seen = first_contact.get(inquiry.client_id)
        first_contact[inquiry.client_id] = min(seen, inquiry.created_at) if seen else inquiry.created_at
        by_type[inquiry.inquiry_type].add(inquiry.client_id)

    ids = list(first_contact)
    offered, booked = set(), set()
    if ids:
        for offer in Offer.query.filter(
            Offer.client_id.in_(ids), Offer.deleted_at.is_(None), Offer.is_template.is_(False), Offer.status != "DRAFT"
        ).all():
            if offer.created_at >= first_contact[offer.client_id]:
                offered.add(offer.client_id)
        for booking in Booking.query.filter(
            Booking.client_id.in_(ids), Booking.deleted_at.is_(None), Booking.status != "CANCELLED"
        ).all():
            if booking.created_at >= first_contact[booking.client_id]:
                booked.add(booking.client_id)

    # How fast the team answers from the dashboard: the median, in hours.
    waits = sorted(
        (inquiry.replied_at - inquiry.created_at).total_seconds() / 3600
        for inquiry in inquiries
        if inquiry.replied_at
    )
    median = waits[len(waits) // 2] if waits else None

    return {
        "inquiries": len(inquiries),
        "clients": len(ids),
        "offered": len(offered),
        "booked": len(booked),
        "rate": round(len(booked) / len(ids), 4) if ids else None,
        "replied": len(waits),
        "medianReplyHours": round(median, 1) if median is not None else None,
        "byType": [
            {
                "type": kind,
                "clients": len(clients),
                "booked": len(clients & booked),
            }
            for kind, clients in sorted(by_type.items())
        ],
    }


def _team(agency_id: str, start: date, end: date, bookings: list[Booking]) -> list[dict]:
    """Per member: clients they took on, offers they sent, bookings they closed and what those add up to."""
    in_period = lambda value: value is not None and _in(value.date(), start, end)  # noqa: E731
    members = (
        AgencyMembership.query.join(User, User.id == AgencyMembership.user_id)
        .filter(AgencyMembership.agency_id == agency_id)
        .order_by(AgencyMembership.created_at)
        .all()
    )
    clients = Client.query.filter(Client.agency_id == agency_id, Client.deleted_at.is_(None)).all()
    offers = Offer.query.filter(
        Offer.agency_id == agency_id, Offer.deleted_at.is_(None), Offer.is_template.is_(False), Offer.status != "DRAFT"
    ).all()

    rows = []
    for membership in members:
        user_id = membership.user_id
        mine = [booking for booking in bookings if booking.created_by == user_id]
        booked: dict[str, float] = defaultdict(float)
        commission: dict[str, float] = defaultdict(float)
        for booking in mine:
            booked[booking.currency] += booking.total_price or 0
            commission[booking.currency] += booking.commission_amount or 0
        rows.append(
            {
                "userId": user_id,
                "name": membership.user.name,
                "role": membership.role,
                "active": membership.user.is_active,
                "clients": sum(1 for client in clients if client.assigned_agent_id == user_id and in_period(client.created_at)),
                "offers": sum(1 for offer in offers if offer.created_by == user_id and in_period(offer.created_at)),
                "bookings": len(mine),
                "booked": dict(booked),
                "commission": dict(commission),
            }
        )
    return rows


def report(agency_id: str, from_: str | None, to: str | None) -> dict:
    start, end = period(from_, to)
    bookings = _counted_bookings(agency_id, start, end)
    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "money": _money(agency_id, start, end, bookings),
        "occupancy": _occupancy(agency_id, start, end),
        "conversion": _conversion(agency_id, start, end),
        "team": _team(agency_id, start, end, bookings),
    }
