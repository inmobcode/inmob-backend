from datetime import date, datetime, timedelta, timezone

from app.extensions import db
from app.models import Agency, AvailabilityBlock, Booking, Client, Offer, Payment, Property
from app.schemas.agency import AgencyPublicSchema
from app.schemas.property import PublicPropertySchema
from app.services.notifications import notify_booking
from app.utils import trash

TERMINAL_STATUSES = ("CANCELLED", "COMPLETED")


class BookingError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _validate_scoped(agency_id: str, model, record_id: str, label: str):
    record = model.query.filter_by(id=record_id, agency_id=agency_id).first()
    # Something in the trash can't be booked or linked.
    if record is None or getattr(record, "deleted_at", None) is not None:
        raise BookingError(f"{label} not found", 404)
    return record


def list_bookings(agency_id: str):
    return (
        Booking.query.filter_by(agency_id=agency_id, deleted_at=None).order_by(Booking.created_at.desc()).all()
    )


def get_booking(agency_id: str, booking_id: str, *, trashed: bool = False) -> Booking:
    """A live booking, or with trashed=True one in the trash."""
    query = Booking.query.filter_by(id=booking_id, agency_id=agency_id)
    query = query.filter(Booking.deleted_at.isnot(None) if trashed else Booking.deleted_at.is_(None))
    booking = query.first()
    if booking is None:
        raise BookingError("Booking not found", 404)
    return booking


def get_booking_by_token(token: str) -> Booking:
    booking = Booking.query.filter_by(token=token, deleted_at=None).first()
    if booking is None:
        raise BookingError("Booking not found", 404)
    return booking


def serialize_public_booking(booking: Booking) -> dict:
    """What the client sees on their booking page: no commission, no internal
    notes, and only the payments they make (deposit and balance)."""
    agency = db.session.get(Agency, booking.agency_id)
    prop = booking.property
    return {
        "status": booking.status,
        "startDate": booking.start_date.isoformat() if booking.start_date else None,
        "endDate": booking.end_date.isoformat() if booking.end_date else None,
        "totalPrice": booking.total_price,
        "currency": booking.currency,
        "clientName": booking.client.name if booking.client else None,
        "createdAt": booking.created_at.isoformat() + "+00:00",
        "payments": [
            {
                "amount": payment.amount,
                "currency": payment.currency,
                "type": payment.type,
                "status": payment.status,
                "paidAt": payment.paid_at.isoformat() + "+00:00" if payment.paid_at else None,
            }
            for payment in booking.payments
            if payment.type != "COMMISSION"
        ],
        "property": {
            **PublicPropertySchema().dump(prop),
            # Drafts have no public page to link to.
            "published": prop.status == "PUBLISHED",
        },
        "agency": {**AgencyPublicSchema().dump(agency), "slug": agency.slug},
    }


def _check_dates(start: date | None, end: date | None) -> None:
    """New dates can't be in the past, and the check-out comes after the check-in.

    "Past" is judged a day behind UTC: the server doesn't know the agency's
    timezone, and late at night in the Americas UTC is already tomorrow. The
    date picker holds the exact line in the agency's own browser.
    """
    earliest = datetime.now(timezone.utc).date() - timedelta(days=1)
    if start and start < earliest:
        raise BookingError("La fecha de entrada ya pasó. Elegí una fecha de hoy en adelante.", 400)
    if start and end and end <= start:
        raise BookingError("La fecha de salida tiene que ser posterior a la de entrada.", 400)


def create_booking(agency_id: str, created_by: str, data: dict) -> Booking:
    _check_dates(data.get("start_date"), data.get("end_date"))
    _validate_scoped(agency_id, Property, data["property_id"], "Property")
    if data.get("client_id"):
        _validate_scoped(agency_id, Client, data["client_id"], "Client")
    if data.get("offer_id"):
        _validate_scoped(agency_id, Offer, data["offer_id"], "Offer")

    booking = Booking(
        agency_id=agency_id,
        created_by=created_by,
        property_id=data["property_id"],
        client_id=data.get("client_id"),
        offer_id=data.get("offer_id"),
        start_date=data.get("start_date"),
        end_date=data.get("end_date"),
        total_price=data.get("total_price"),
        currency=data.get("currency", "USD"),
        commission_amount=data.get("commission_amount"),
        status="PENDING",
    )
    db.session.add(booking)
    db.session.commit()
    notify_booking(booking, "created")
    return booking


def update_booking(agency_id: str, booking_id: str, data: dict) -> Booking:
    booking = get_booking(agency_id, booking_id)
    if booking.status in TERMINAL_STATUSES:
        raise BookingError("Cannot edit a cancelled or completed booking", 400)
    if data.get("client_id"):
        _validate_scoped(agency_id, Client, data["client_id"], "Client")
    # Only dates that change are checked: a past stay keeps its dates when other fields are edited.
    new_start = data.get("start_date", booking.start_date)
    new_end = data.get("end_date", booking.end_date)
    if new_start != booking.start_date or new_end != booking.end_date:
        _check_dates(new_start if new_start != booking.start_date else None, new_end)
        if new_start and new_end and new_end <= new_start:
            raise BookingError("La fecha de salida tiene que ser posterior a la de entrada.", 400)

    had_client = booking.client_id is not None
    for field, value in data.items():
        setattr(booking, field, value)

    db.session.commit()
    # A client added after the fact gets the same email as if they'd been
    # there from the start; changing an existing client sends nothing.
    if not had_client and booking.client_id:
        notify_booking(booking, "created")
    return booking


def _free_dates(booking: Booking) -> None:
    if booking.availability_block_id:
        block = db.session.get(AvailabilityBlock, booking.availability_block_id)
        if block is not None:
            db.session.delete(block)
        booking.availability_block_id = None


def _block_dates(booking: Booking) -> None:
    """A confirmed rental holds its dates in the property's calendar."""
    if booking.property.listing_type == "RENT" and booking.start_date and booking.end_date:
        block = AvailabilityBlock(
            property_id=booking.property_id,
            start_date=booking.start_date,
            end_date=booking.end_date,
            source="BOOKING",
        )
        db.session.add(block)
        db.session.flush()
        booking.availability_block_id = block.id


def delete_booking(agency_id: str, booking_id: str) -> None:
    """Moves the booking to the trash and frees its dates in the calendar."""
    booking = get_booking(agency_id, booking_id)
    _free_dates(booking)
    booking.deleted_at = trash.now()
    db.session.commit()


def list_trashed_bookings(agency_id: str):
    purge_trashed_bookings(agency_id)
    return (
        Booking.query.filter(Booking.agency_id == agency_id, Booking.deleted_at.isnot(None))
        .order_by(Booking.deleted_at.desc())
        .all()
    )


def restore_booking(agency_id: str, booking_id: str) -> Booking:
    """Back from the trash; a confirmed one takes its dates in the calendar again."""
    booking = get_booking(agency_id, booking_id, trashed=True)
    if booking.property.deleted_at is not None:
        raise BookingError("Restaurá primero la propiedad: está en la papelera.", 409)
    booking.deleted_at = None
    if booking.status == "CONFIRMED":
        _block_dates(booking)
    db.session.commit()
    return booking


def delete_booking_forever(agency_id: str, booking_id: str) -> None:
    booking = get_booking(agency_id, booking_id, trashed=True)
    db.session.delete(booking)
    db.session.commit()


def purge_trashed_bookings(agency_id: str) -> None:
    """Deletes for good what has been in the trash longer than TRASH_DAYS."""
    for booking in Booking.query.filter(
        Booking.agency_id == agency_id,
        Booking.deleted_at.isnot(None),
        Booking.deleted_at < trash.purge_cutoff(),
    ).all():
        db.session.delete(booking)
    db.session.commit()


def confirm_booking(agency_id: str, booking_id: str) -> Booking:
    booking = get_booking(agency_id, booking_id)
    if booking.status != "PENDING":
        raise BookingError("Only pending bookings can be confirmed", 400)

    _block_dates(booking)
    booking.status = "CONFIRMED"
    db.session.commit()
    notify_booking(booking, "confirmed")
    return booking


def cancel_booking(agency_id: str, booking_id: str) -> Booking:
    booking = get_booking(agency_id, booking_id)
    if booking.status in TERMINAL_STATUSES:
        raise BookingError("Booking is already closed", 400)

    _free_dates(booking)
    booking.status = "CANCELLED"
    db.session.commit()
    notify_booking(booking, "cancelled")
    return booking


def complete_booking(agency_id: str, booking_id: str) -> Booking:
    booking = get_booking(agency_id, booking_id)
    if booking.status != "CONFIRMED":
        raise BookingError("Only confirmed bookings can be completed", 400)
    booking.status = "COMPLETED"
    db.session.commit()
    return booking


def add_payment(agency_id: str, booking_id: str, data: dict) -> Payment:
    get_booking(agency_id, booking_id)
    payment = Payment(
        booking_id=booking_id,
        amount=data["amount"],
        currency=data.get("currency", "USD"),
        type=data.get("type", "DEPOSIT"),
        method=data.get("method"),
        status="PENDING",
    )
    db.session.add(payment)
    db.session.commit()
    return payment


def mark_payment_paid(agency_id: str, booking_id: str, payment_id: str) -> Payment:
    booking = get_booking(agency_id, booking_id)
    payment = next((p for p in booking.payments if p.id == payment_id), None)
    if payment is None:
        raise BookingError("Payment not found", 404)
    payment.status = "PAID"
    payment.paid_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.session.commit()
    return payment
