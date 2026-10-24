from marshmallow import Schema, fields, validate

from app.models.booking import PAYMENT_STATUSES, PAYMENT_TYPES

_POSITIVE = validate.Range(min=0, min_inclusive=False)


class PaymentSchema(Schema):
    id = fields.Str(dump_only=True)
    booking_id = fields.Str(data_key="bookingId", dump_only=True)
    amount = fields.Float(required=True, validate=_POSITIVE)
    currency = fields.Str(load_default="USD", validate=validate.Length(equal=3))
    type = fields.Str(validate=validate.OneOf(PAYMENT_TYPES))
    # Registering one that's already collected skips the "mark as paid" step.
    status = fields.Str(load_default="PENDING", validate=validate.OneOf(PAYMENT_STATUSES))
    paid_at = fields.DateTime(data_key="paidAt", allow_none=True)
    method = fields.Str(allow_none=True, validate=validate.Length(max=50))
    note = fields.Str(allow_none=True, validate=validate.Length(max=200))
    created_at = fields.DateTime(data_key="createdAt", dump_only=True)


class PaymentUpdateSchema(Schema):
    amount = fields.Float(validate=_POSITIVE)
    type = fields.Str(validate=validate.OneOf(PAYMENT_TYPES))
    status = fields.Str(validate=validate.OneOf(PAYMENT_STATUSES))
    paid_at = fields.DateTime(data_key="paidAt", allow_none=True)
    method = fields.Str(allow_none=True, validate=validate.Length(max=50))
    note = fields.Str(allow_none=True, validate=validate.Length(max=200))


class BookingSchema(Schema):
    id = fields.Str(dump_only=True)
    agency_id = fields.Str(data_key="agencyId", dump_only=True)
    token = fields.Str(dump_only=True)
    property_id = fields.Str(data_key="propertyId", required=True)
    client_id = fields.Str(data_key="clientId", allow_none=True)
    offer_id = fields.Str(data_key="offerId", allow_none=True)
    start_date = fields.Date(data_key="startDate", allow_none=True)
    end_date = fields.Date(data_key="endDate", allow_none=True)
    status = fields.Str(dump_only=True)
    total_price = fields.Float(data_key="totalPrice", allow_none=True)
    currency = fields.Str(load_default="USD", validate=validate.Length(equal=3))
    commission_amount = fields.Float(data_key="commissionAmount", allow_none=True)
    guests = fields.Int(allow_none=True, validate=validate.Range(min=1, max=999))
    notes = fields.Str(allow_none=True, validate=validate.Length(max=5000))
    created_at = fields.DateTime(data_key="createdAt", dump_only=True)
    updated_at = fields.DateTime(data_key="updatedAt", dump_only=True)
    deleted_at = fields.DateTime(data_key="deletedAt", dump_only=True)
    payments = fields.Nested(PaymentSchema, many=True, dump_only=True)

    property_title = fields.Method("get_property_title", data_key="propertyTitle", dump_only=True)
    client_name = fields.Method("get_client_name", data_key="clientName", dump_only=True)

    def get_property_title(self, obj):
        return obj.property.title if obj.property else None

    def get_client_name(self, obj):
        return obj.client.name if obj.client else None


class BookingUpdateSchema(Schema):
    start_date = fields.Date(data_key="startDate", allow_none=True)
    end_date = fields.Date(data_key="endDate", allow_none=True)
    total_price = fields.Float(data_key="totalPrice", allow_none=True)
    currency = fields.Str(validate=validate.Length(equal=3))
    commission_amount = fields.Float(data_key="commissionAmount", allow_none=True)
    client_id = fields.Str(data_key="clientId", allow_none=True)
    guests = fields.Int(allow_none=True, validate=validate.Range(min=1, max=999))
    notes = fields.Str(allow_none=True, validate=validate.Length(max=5000))
