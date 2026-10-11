from marshmallow import Schema, fields, validate

from app.constants.property_catalogs import POOL_ENTITY_TYPES


class PoolSchema(Schema):
    id = fields.Str(dump_only=True)
    property_id = fields.Str(data_key="propertyId", dump_only=True)
    type = fields.Str(validate=validate.OneOf(POOL_ENTITY_TYPES))
    quantity = fields.Int(load_default=1)
    pool_type = fields.List(fields.Str(), data_key="poolType", load_default=list)


class PoolCreateSchema(Schema):
    type = fields.Str(required=True, validate=validate.OneOf(POOL_ENTITY_TYPES))
    quantity = fields.Int(load_default=1)
    pool_type = fields.List(fields.Str(), data_key="poolType", load_default=list)


class PoolUpdateSchema(Schema):
    quantity = fields.Int()
    pool_type = fields.List(fields.Str(), data_key="poolType")
