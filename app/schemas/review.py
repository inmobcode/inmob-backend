from marshmallow import Schema, fields, validate

from app.models.review import REVIEW_STATUSES

_RATING = validate.Range(min=1, max=5)


class ReviewSchema(Schema):
    id = fields.Str(dump_only=True)
    property_id = fields.Str(data_key="propertyId", allow_none=True)
    property_title = fields.Method("get_property_title", data_key="propertyTitle", dump_only=True)
    booking_id = fields.Str(data_key="bookingId", dump_only=True)
    author_name = fields.Str(data_key="authorName", required=True, validate=validate.Length(min=1, max=120))
    rating = fields.Int(required=True, validate=_RATING)
    text = fields.Str(allow_none=True, validate=validate.Length(max=2000))
    stayed_on = fields.Date(data_key="stayedOn", allow_none=True)
    status = fields.Str(validate=validate.OneOf(REVIEW_STATUSES))
    source = fields.Str(dump_only=True)
    created_at = fields.DateTime(data_key="createdAt", dump_only=True)

    def get_property_title(self, obj):
        return obj.property.title if obj.property else None


class GuestReviewSchema(Schema):
    """What the guest sends from their booking page."""

    rating = fields.Int(required=True, validate=_RATING)
    text = fields.Str(allow_none=True, validate=validate.Length(max=2000))
    author_name = fields.Str(data_key="authorName", allow_none=True, validate=validate.Length(max=120))
