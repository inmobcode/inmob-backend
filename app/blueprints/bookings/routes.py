from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity
from marshmallow import ValidationError

from app.blueprints.bookings import bp
from app.schemas.booking import BookingSchema, BookingUpdateSchema, PaymentSchema, PaymentUpdateSchema
from app.services import audit, booking_service
from app.utils.tenancy import current_agency_id

booking_schema = BookingSchema()
bookings_schema = BookingSchema(many=True)
payment_schema = PaymentSchema()
payments_schema = PaymentSchema(many=True)


def _load(schema, partial=False):
    try:
        return schema.load(request.get_json(silent=True) or {}, partial=partial), None
    except ValidationError as err:
        return None, (jsonify({"message": "Validation error", "errors": err.messages}), 400)


@bp.route("/", methods=["GET"])
def list_bookings():
    bookings = booking_service.list_bookings(current_agency_id())
    return jsonify(bookings_schema.dump(bookings))


@bp.route("/", methods=["POST"])
def create_booking():
    data, error = _load(BookingSchema())
    if error:
        return error

    try:
        booking = booking_service.create_booking(current_agency_id(), get_jwt_identity(), data)
    except booking_service.BookingError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(booking_schema.dump(booking)), 201


@bp.route("/<booking_id>", methods=["GET"])
def get_booking(booking_id):
    try:
        booking = booking_service.get_booking(current_agency_id(), booking_id)
    except booking_service.BookingError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(booking_schema.dump(booking))


@bp.route("/<booking_id>", methods=["PATCH"])
def update_booking(booking_id):
    data, error = _load(BookingUpdateSchema(), partial=True)
    if error:
        return error

    try:
        booking = booking_service.update_booking(current_agency_id(), booking_id, data)
    except booking_service.BookingError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(booking_schema.dump(booking))


@bp.route("/<booking_id>", methods=["DELETE"])
def delete_booking(booking_id):
    try:
        booking_service.delete_booking(current_agency_id(), booking_id)
    except booking_service.BookingError as err:
        return jsonify({"message": err.message}), err.status_code
    return "", 204

@bp.route("/trash", methods=["GET"])
def list_trashed_bookings():
    """What's in the trash; anything older than TRASH_DAYS is deleted for good first."""
    items = booking_service.list_trashed_bookings(current_agency_id())
    return jsonify(bookings_schema.dump(items))


@bp.route("/<booking_id>/restore", methods=["POST"])
def restore_booking(booking_id):
    try:
        item = booking_service.restore_booking(current_agency_id(), booking_id)
    except booking_service.BookingError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(booking_schema.dump(item))


@bp.route("/<booking_id>/permanent", methods=["DELETE"])
def delete_booking_forever(booking_id):
    try:
        booking_service.delete_booking_forever(current_agency_id(), booking_id)
    except booking_service.BookingError as err:
        return jsonify({"message": err.message}), err.status_code
    return "", 204



@bp.route("/<booking_id>/confirm", methods=["POST"])
def confirm_booking(booking_id):
    try:
        booking = booking_service.confirm_booking(current_agency_id(), booking_id)
    except booking_service.BookingError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(booking_schema.dump(booking))


@bp.route("/<booking_id>/cancel", methods=["POST"])
def cancel_booking(booking_id):
    try:
        booking = booking_service.cancel_booking(current_agency_id(), booking_id)
    except booking_service.BookingError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(booking_schema.dump(booking))


@bp.route("/<booking_id>/complete", methods=["POST"])
def complete_booking(booking_id):
    try:
        booking = booking_service.complete_booking(current_agency_id(), booking_id)
    except booking_service.BookingError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(booking_schema.dump(booking))


@bp.route("/<booking_id>/payments", methods=["POST"])
def add_payment(booking_id):
    data, error = _load(PaymentSchema())
    if error:
        return error

    try:
        payment = booking_service.add_payment(current_agency_id(), booking_id, data)
    except booking_service.BookingError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(payment_schema.dump(payment)), 201


@bp.route("/<booking_id>/payments/<payment_id>", methods=["PATCH"])
def update_payment(booking_id, payment_id):
    data, error = _load(PaymentUpdateSchema(), partial=True)
    if error:
        return error
    try:
        payment = booking_service.update_payment(current_agency_id(), booking_id, payment_id, data)
    except booking_service.BookingError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(payment_schema.dump(payment))


@bp.route("/<booking_id>/payments/<payment_id>", methods=["DELETE"])
def delete_payment(booking_id, payment_id):
    try:
        booking_service.delete_payment(current_agency_id(), booking_id, payment_id)
    except booking_service.BookingError as err:
        return jsonify({"message": err.message}), err.status_code
    return "", 204


@bp.route("/<booking_id>/payments/<payment_id>/mark-paid", methods=["POST"])
def mark_payment_paid(booking_id, payment_id):
    try:
        payment = booking_service.mark_payment_paid(current_agency_id(), booking_id, payment_id)
    except booking_service.BookingError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(payment_schema.dump(payment))


@bp.route("/<booking_id>/history", methods=["GET"])
def booking_history(booking_id):
    try:
        booking = booking_service.get_booking(current_agency_id(), booking_id)
    except booking_service.BookingError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(audit.serialize(audit.history("BOOKING", booking.id)))
