from marshmallow import Schema, fields, validate

from app.models.availability import AVAILABILITY_SOURCES


class AvailabilityBlockSchema(Schema):
    id = fields.Str(dump_only=True)
    property_id = fields.Str(data_key="propertyId", dump_only=True)
    start_date = fields.Date(data_key="startDate", required=True)
    end_date = fields.Date(data_key="endDate", required=True)
    source = fields.Str(dump_only=True, validate=validate.OneOf(AVAILABILITY_SOURCES))
    ical_uid = fields.Str(data_key="icalUid", dump_only=True, allow_none=True)
    note = fields.Str(allow_none=True, validate=validate.Length(max=255))


class AvailabilityBlockCreateSchema(Schema):
    start_date = fields.Date(data_key="startDate", required=True)
    end_date = fields.Date(data_key="endDate", required=True)
    note = fields.Str(allow_none=True, validate=validate.Length(max=255))


class IcalSyncSchema(Schema):
    ical_url = fields.Url(data_key="icalUrl", required=True)
