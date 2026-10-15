from marshmallow import Schema, fields, validate


class DemoRequestSchema(Schema):
    """The landing's "Pedir una demo" form."""

    name = fields.Str(required=True, validate=validate.Length(min=2, max=200))
    agency = fields.Str(required=True, validate=validate.Length(min=2, max=200))
    email = fields.Email(required=True)
    team_size = fields.Str(data_key="teamSize", required=True, validate=validate.Length(min=1, max=50))


class ContactRequestSchema(Schema):
    """The landing's help/contact page."""

    name = fields.Str(required=True, validate=validate.Length(min=2, max=200))
    email = fields.Email(required=True)
    message = fields.Str(required=True, validate=validate.Length(min=5, max=4000))
