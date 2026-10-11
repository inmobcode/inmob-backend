import re

from marshmallow import Schema, ValidationError, fields, validate, validates

SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def _validate_slug(value: str) -> None:
    if not SLUG_RE.match(value):
        raise ValidationError(
            "Solo minúsculas, números y guiones (sin guiones al principio/final)."
        )


class AgencySchema(Schema):
    id = fields.Str(dump_only=True)
    name = fields.Str()
    slug = fields.Str()
    logo_url = fields.Str(data_key="logoUrl", allow_none=True)
    contact_email = fields.Str(data_key="contactEmail", allow_none=True)
    locale = fields.Str()
    currency = fields.Str()


class AgencyUpdateSchema(Schema):
    name = fields.Str(validate=validate.Length(min=2, max=200))
    slug = fields.Str(validate=validate.Length(min=2, max=200))
    contact_email = fields.Email(data_key="contactEmail", allow_none=True)
    locale = fields.Str(validate=validate.Length(equal=2))
    currency = fields.Str(validate=validate.Length(equal=3))

    @validates("slug")
    def validate_slug(self, value, **kwargs):
        _validate_slug(value)


class AgencyPublicSchema(Schema):
    name = fields.Str()
    logo_url = fields.Str(data_key="logoUrl", allow_none=True)
    contact_email = fields.Str(data_key="contactEmail", allow_none=True)
