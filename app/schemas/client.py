from marshmallow import Schema, fields, post_dump, post_load, validate

from app.models.client import CLIENT_SOURCES, CLIENT_STAGES, INQUIRY_TYPES, INTERACTION_TYPES
from app.utils import rich_text


def _clean_notes(data):
    """Notes are formatted text (see app/utils/rich_text.py)."""
    if data.get("notes"):
        data["notes"] = rich_text.sanitize(data["notes"])
    return data


class ClientSchema(Schema):
    id = fields.Str(dump_only=True)
    agency_id = fields.Str(data_key="agencyId", dump_only=True)
    assigned_agent_id = fields.Str(data_key="assignedAgentId", allow_none=True)
    name = fields.Str(required=True, validate=validate.Length(min=2, max=200))
    email = fields.Email(required=True)
    phone = fields.Str(allow_none=True, validate=validate.Length(max=50))
    source = fields.Str(dump_only=True, validate=validate.OneOf(CLIENT_SOURCES))
    stage = fields.Str(validate=validate.OneOf(CLIENT_STAGES))
    notes = fields.Str(allow_none=True)
    created_at = fields.DateTime(data_key="createdAt", dump_only=True)
    updated_at = fields.DateTime(data_key="updatedAt", dump_only=True)

    @post_load
    def clean_notes(self, data, **kwargs):
        return _clean_notes(data)

    @post_dump
    def clean_notes_out(self, data, **kwargs):
        return _clean_notes(data)


class ClientUpdateSchema(Schema):
    name = fields.Str(validate=validate.Length(min=2, max=200))
    phone = fields.Str(allow_none=True, validate=validate.Length(max=50))
    assigned_agent_id = fields.Str(data_key="assignedAgentId", allow_none=True)
    stage = fields.Str(validate=validate.OneOf(CLIENT_STAGES))
    notes = fields.Str(allow_none=True)

    @post_load
    def clean_notes(self, data, **kwargs):
        return _clean_notes(data)


class InteractionSchema(Schema):
    id = fields.Str(dump_only=True)
    type = fields.Str(validate=validate.OneOf(INTERACTION_TYPES))
    content = fields.Str(required=True)
    created_by = fields.Str(data_key="createdBy", dump_only=True)
    created_at = fields.DateTime(data_key="createdAt", dump_only=True)


class PublicInquirySchema(Schema):
    name = fields.Str(required=True, validate=validate.Length(min=2, max=200))
    email = fields.Email(required=True)
    phone = fields.Str(allow_none=True, validate=validate.Length(max=50))
    message = fields.Str(allow_none=True)
    inquiry_type = fields.Str(
        data_key="inquiryType", load_default="GENERAL", validate=validate.OneOf(INQUIRY_TYPES)
    )
    property_id = fields.Str(data_key="propertyId", allow_none=True)
