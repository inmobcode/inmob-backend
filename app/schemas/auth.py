from marshmallow import Schema, fields, validate


class RegisterAgencySchema(Schema):
    agency_name = fields.Str(
        required=True, data_key="agencyName", validate=validate.Length(min=2, max=200)
    )
    name = fields.Str(required=True, validate=validate.Length(min=2, max=200))
    email = fields.Email(required=True)
    password = fields.Str(required=True, load_only=True, validate=validate.Length(min=8))


class LoginSchema(Schema):
    email = fields.Email(required=True)
    password = fields.Str(required=True, load_only=True)
