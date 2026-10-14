from marshmallow import Schema, fields, validate

from app.models.service import SERVICE_TYPES, SERVICE_UNITS


class ServiceSchema(Schema):
    id = fields.Str(dump_only=True)
    name = fields.Str(required=True, validate=validate.Length(min=2, max=200))
    type = fields.Str(load_default="OTHER", validate=validate.OneOf(SERVICE_TYPES))
    description = fields.Str(allow_none=True, validate=validate.Length(max=4000))
    image_url = fields.Str(data_key="imageUrl", allow_none=True, validate=validate.Length(max=500))
    zones = fields.List(fields.Str(validate=validate.Length(min=1, max=120)), load_default=list, validate=validate.Length(max=30))
    provider = fields.Str(allow_none=True, validate=validate.Length(max=200))
    price = fields.Float(allow_none=True, validate=validate.Range(min=0))
    currency = fields.Str(load_default="USD", validate=validate.Length(equal=3))
    unit = fields.Str(load_default="SERVICE", validate=validate.OneOf(SERVICE_UNITS))
    active = fields.Bool(load_default=True)
    reservation_policy = fields.Str(data_key="reservationPolicy", allow_none=True, validate=validate.Length(max=4000))
    cancellation_policy = fields.Str(data_key="cancellationPolicy", allow_none=True, validate=validate.Length(max=4000))
    created_at = fields.DateTime(data_key="createdAt", dump_only=True)
    updated_at = fields.DateTime(data_key="updatedAt", dump_only=True)


class OfferServiceItemSchema(Schema):
    """A service inside an offer, as the editor sends it: the copy the client sees."""

    service_id = fields.Str(data_key="serviceId", allow_none=True)
    name = fields.Str(required=True, validate=validate.Length(min=1, max=200))
    type = fields.Str(load_default="OTHER", validate=validate.OneOf(SERVICE_TYPES))
    description = fields.Str(allow_none=True, validate=validate.Length(max=4000))
    image_url = fields.Str(data_key="imageUrl", allow_none=True, validate=validate.Length(max=500))
    unit = fields.Str(load_default="SERVICE", validate=validate.OneOf(SERVICE_UNITS))
    unit_price = fields.Float(data_key="unitPrice", allow_none=True, validate=validate.Range(min=0))
    quantity = fields.Int(load_default=1, validate=validate.Range(min=1, max=999))
    date = fields.Date(allow_none=True)
    note = fields.Str(allow_none=True, validate=validate.Length(max=500))
