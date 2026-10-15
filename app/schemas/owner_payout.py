from marshmallow import Schema, fields, validate


class OwnerPayoutSchema(Schema):
    id = fields.Str(dump_only=True)
    owner_id = fields.Str(data_key="ownerId", dump_only=True)
    amount = fields.Float(required=True, validate=validate.Range(min=0, min_inclusive=False))
    currency = fields.Str(load_default="USD", validate=validate.Length(equal=3))
    paid_at = fields.Date(data_key="paidAt", required=True)
    method = fields.Str(allow_none=True, validate=validate.Length(max=50))
    note = fields.Str(allow_none=True, validate=validate.Length(max=255))
    created_at = fields.DateTime(data_key="createdAt", dump_only=True)
