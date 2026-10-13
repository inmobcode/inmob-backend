from marshmallow import Schema, fields, validate

from app.models.user import ROLES

ASSIGNABLE_ROLES = [role for role in ROLES if role != "OWNER"]


class UserSchema(Schema):
    id = fields.Str(dump_only=True)
    agency_id = fields.Str(data_key="agencyId", dump_only=True)
    name = fields.Str()
    email = fields.Str()
    role = fields.Str()
    is_active = fields.Bool(data_key="isActive")
    avatar_url = fields.Str(data_key="avatarUrl", dump_only=True, allow_none=True)
    created_at = fields.DateTime(data_key="createdAt", dump_only=True)


class CreateTeamUserSchema(Schema):
    # Only used if the email doesn't belong to an existing account yet —
    # ignored (that account already has its own name) when linking one.
    name = fields.Str(required=True, validate=validate.Length(min=2, max=200))
    email = fields.Email(required=True)
    role = fields.Str(required=True, validate=validate.OneOf(ASSIGNABLE_ROLES))


class UpdateTeamUserSchema(Schema):
    role = fields.Str(validate=validate.OneOf(ASSIGNABLE_ROLES))
    is_active = fields.Bool(data_key="isActive")
