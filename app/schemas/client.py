from marshmallow import Schema, fields, post_dump, post_load, validate

from app.models.client import CLIENT_SOURCES, CLIENT_STAGES, INQUIRY_TYPES, INTERACTION_TYPES
from app.utils import rich_text


MAX_TAGS = 20


def _clean_notes(data):
    """Notes are formatted text (see app/utils/rich_text.py)."""
    if data.get("notes"):
        data["notes"] = rich_text.sanitize(data["notes"])
    return data


def _clean_tags(data):
    """Trimmed, without repeats ("VIP" and "vip" are the same tag; the first spelling stays)."""
    if "tags" not in data:
        return data
    seen, tags = set(), []
    for tag in data["tags"] or []:
        tag = " ".join(tag.split())
        if tag and tag.casefold() not in seen:
            seen.add(tag.casefold())
            tags.append(tag)
    data["tags"] = tags
    return data


def _preference_fields():
    """What the client is looking for, shared by create and update."""
    return {
        "tags": fields.List(
            fields.Str(validate=validate.Length(max=40)), validate=validate.Length(max=MAX_TAGS)
        ),
        "budget_min": fields.Float(data_key="budgetMin", allow_none=True, validate=validate.Range(min=0)),
        "budget_max": fields.Float(data_key="budgetMax", allow_none=True, validate=validate.Range(min=0)),
        "guests": fields.Int(allow_none=True, validate=validate.Range(min=1, max=999)),
        "zones": fields.Str(allow_none=True, validate=validate.Length(max=300)),
        "desired_from": fields.Date(data_key="desiredFrom", allow_none=True),
        "desired_to": fields.Date(data_key="desiredTo", allow_none=True),
    }


class ClientSchema(Schema.from_dict(_preference_fields())):
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
    deleted_at = fields.DateTime(data_key="deletedAt", dump_only=True)

    @post_load
    def clean_notes(self, data, **kwargs):
        return _clean_tags(_clean_notes(data))

    @post_dump
    def clean_notes_out(self, data, **kwargs):
        return _clean_notes(data)


class ClientUpdateSchema(Schema.from_dict(_preference_fields())):
    name = fields.Str(validate=validate.Length(min=2, max=200))
    phone = fields.Str(allow_none=True, validate=validate.Length(max=50))
    assigned_agent_id = fields.Str(data_key="assignedAgentId", allow_none=True)
    stage = fields.Str(validate=validate.OneOf(CLIENT_STAGES))
    notes = fields.Str(allow_none=True)

    @post_load
    def clean_notes(self, data, **kwargs):
        return _clean_tags(_clean_notes(data))


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


class InquiryReplySchema(Schema):
    """An answer written in the dashboard: plain text, sent as email."""

    subject = fields.Str(required=True, validate=validate.Length(min=1, max=200))
    body = fields.Str(required=True, validate=validate.Length(min=1, max=10000))


class ReplyTemplateSchema(Schema):
    id = fields.Str(dump_only=True)
    name = fields.Str(required=True, validate=validate.Length(min=1, max=120))
    subject = fields.Str(allow_none=True, validate=validate.Length(max=200))
    body = fields.Str(required=True, validate=validate.Length(min=1, max=10000))
    created_at = fields.DateTime(data_key="createdAt", dump_only=True)
    updated_at = fields.DateTime(data_key="updatedAt", dump_only=True)
