from datetime import datetime, timezone

from app.extensions import db
from app.models import Agency, AvailabilityBlock, Booking, Client, Offer, Payment, Property
from app.schemas.agency import AgencyPublicSchema
from app.schemas.property import PublicPropertySchema
from app.services.notifications import notify_booking

TERMINAL_STATUSES = ("CANCELLED", "COMPLETED")


class BookingError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _validate_scoped(agency_id: str, model, record_id: str, label: str):
    record = model.query.filter_by(id=record_id, agency_id=agency_id).first()
    if record is None:
        raise BookingError(f"{label} not found", 404)
    return record


def list_bookings(agency_id: str):
    return Booking.query.filter_by(agency_id=agency_id).order_by(Booking.created_at.desc()).all()


def get_booking(agency_id: str, booking_id: str) -> Booking:
    booking = Booking.query.filter_by(id=booking_id, agency_id=agency_id).first()
    if booking is None:
        raise BookingError("Booking not found", 404)
    return booking


def get_booking_by_token(token: str) -> Booking:
    booking = Booking.query.filter_by(token=token).first()
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


def create_booking(agency_id: str, created_by: str, data: dict) -> Booking:
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

    had_client = booking.client_id is not None
    for field, value in data.items():
        setattr(booking, field, value)

    db.session.commit()
    # A client added after the fact gets the same email as if they'd been
    # there from the start; changing an existing client sends nothing.
    if not had_client and booking.client_id:
        notify_booking(booking, "created")
    return booking


def delete_booking(agency_id: str, booking_id: str) -> None:
    booking = get_booking(agency_id, booking_id)
    if booking.availability_block_id:
        block = db.session.get(AvailabilityBlock, booking.availability_block_id)
        if block is not None:
            db.session.delete(block)
    db.session.delete(booking)
    db.session.commit()


def confirm_booking(agency_id: str, booking_id: str) -> Booking:
    booking = get_booking(agency_id, booking_id)
    if booking.status != "PENDING":
        raise BookingError("Only pending bookings can be confirmed", 400)

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

    booking.status = "CONFIRMED"
    db.session.commit()
    notify_booking(booking, "confirmed")
    return booking


def cancel_booking(agency_id: str, booking_id: str) -> Booking:
    booking = get_booking(agency_id, booking_id)
    if booking.status in TERMINAL_STATUSES:
        raise BookingError("Booking is already closed", 400)

    if booking.availability_block_id:
        block = db.session.get(AvailabilityBlock, booking.availability_block_id)
        if block is not None:
            db.session.delete(block)
        booking.availability_block_id = None

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
