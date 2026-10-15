"""What an agency owes a property owner, and what it has already handed over.

The agency collects the booking money from the guest and keeps its commission
out of it; the rest is the owner's. For each booking:

    collected = payments marked paid (the commission-type ones don't count)
    due       = max(0, collected - commission)   # the commission comes out first
    balance   = sum of due - sum of payouts       # what's left to hand over

Cancelled bookings are left out. Amounts are grouped by currency, never mixed.
"""
from collections import defaultdict

from app.extensions import db
from app.models import Booking, OwnerPayout, Property, PropertyOwner


class OwnerAccountError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def get_owner(agency_id: str, owner_id: str) -> PropertyOwner:
    owner = PropertyOwner.query.filter_by(id=owner_id, agency_id=agency_id).first()
    if owner is None:
        raise OwnerAccountError("Owner not found", 404)
    return owner


def _iso(value):
    return value.isoformat() if value else None


def _round(value: float) -> float:
    return round(value + 0.0, 2)


def build_statement(owner: PropertyOwner, *, with_commission: bool = True) -> dict:
    """The owner's statement. Without `with_commission` the commission has to stay
    undeducible: `due` is collected minus commission, so showing the gross figures
    next to it would give the commission away by subtraction. The owner then only
    gets the net ones (due, handed over, balance)."""
    properties = Property.query.filter_by(owner_id=owner.id, deleted_at=None).all()
    titles = {prop.id: prop.title for prop in properties}
    bookings = (
        Booking.query.filter(
            Booking.property_id.in_(list(titles) or [""]),
            Booking.deleted_at.is_(None),
            Booking.status != "CANCELLED",
        )
        .order_by(Booking.start_date.desc())
        .all()
    )

    totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    rows = []
    for booking in bookings:
        currency = booking.currency
        total = booking.total_price or 0.0
        commission = booking.commission_amount or 0.0
        collected = sum(
            payment.amount
            for payment in booking.payments
            if payment.status == "PAID" and payment.type != "COMMISSION" and payment.currency == currency
        )
        due = max(0.0, collected - commission)

        bucket = totals[currency]
        bucket["booked"] += total
        bucket["collected"] += collected
        bucket["commission"] += commission
        bucket["due"] += due

        row = {
            "propertyTitle": titles.get(booking.property_id),
            "startDate": _iso(booking.start_date),
            "endDate": _iso(booking.end_date),
            "status": booking.status,
            "currency": currency,
            "due": _round(due),
        }
        if with_commission:
            row.update(total=_round(total), collected=_round(collected), commission=_round(commission))
        rows.append(row)

    payouts = (
        OwnerPayout.query.filter_by(owner_id=owner.id).order_by(OwnerPayout.paid_at.desc(), OwnerPayout.created_at.desc()).all()
    )
    for payout in payouts:
        totals[payout.currency]["paidOut"] += payout.amount

    summary = []
    for currency in sorted(totals):
        bucket = totals[currency]
        line = {
            "currency": currency,
            "due": _round(bucket["due"]),
            "paidOut": _round(bucket["paidOut"]),
            # Negative means the agency has handed over more than has been collected so far.
            "balance": _round(bucket["due"] - bucket["paidOut"]),
        }
        if with_commission:
            line.update(
                booked=_round(bucket["booked"]),
                collected=_round(bucket["collected"]),
                commission=_round(bucket["commission"]),
            )
        summary.append(line)

    return {
        "totals": summary,
        "bookings": rows,
        "payouts": [serialize_payout(payout) for payout in payouts],
    }


def serialize_payout(payout: OwnerPayout) -> dict:
    return {
        "id": payout.id,
        "amount": _round(payout.amount),
        "currency": payout.currency,
        "paidAt": _iso(payout.paid_at),
        "method": payout.method,
        "note": payout.note,
    }


def create_payout(agency_id: str, owner_id: str, created_by: str, data: dict) -> OwnerPayout:
    owner = get_owner(agency_id, owner_id)
    payout = OwnerPayout(
        agency_id=agency_id,
        owner_id=owner.id,
        created_by=created_by,
        amount=data["amount"],
        currency=data.get("currency", "USD").upper(),
        paid_at=data["paid_at"],
        method=data.get("method"),
        note=data.get("note"),
    )
    db.session.add(payout)
    db.session.commit()
    return payout


def delete_payout(agency_id: str, owner_id: str, payout_id: str) -> None:
    owner = get_owner(agency_id, owner_id)
    payout = OwnerPayout.query.filter_by(id=payout_id, owner_id=owner.id).first()
    if payout is None:
        raise OwnerAccountError("Payout not found", 404)
    db.session.delete(payout)
    db.session.commit()
