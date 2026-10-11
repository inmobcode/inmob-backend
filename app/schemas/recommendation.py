from marshmallow import Schema, fields, validate

from app.constants.property_catalogs import RECOMMENDATION_PRIORITIES, RECOMMENDATION_STATUSES


class RecommendationSchema(Schema):
    id = fields.Str(dump_only=True)
    property_id = fields.Str(data_key="propertyId", dump_only=True)
    title = fields.Str(required=True, validate=validate.Length(min=2, max=200))
    details = fields.Str(allow_none=True)
    priority = fields.Str(load_default="MEDIUM", validate=validate.OneOf(RECOMMENDATION_PRIORITIES))
    est_cost = fields.Float(data_key="estCost", allow_none=True)
    pdf_url = fields.Str(data_key="pdfUrl", allow_none=True)
    status = fields.Str(dump_only=True)
    created_at = fields.DateTime(data_key="createdAt", dump_only=True)


class RecommendationUpdateSchema(Schema):
    title = fields.Str(validate=validate.Length(min=2, max=200))
    details = fields.Str(allow_none=True)
    priority = fields.Str(validate=validate.OneOf(RECOMMENDATION_PRIORITIES))
    est_cost = fields.Float(data_key="estCost", allow_none=True)
    pdf_url = fields.Str(data_key="pdfUrl", allow_none=True)
    status = fields.Str(validate=validate.OneOf(RECOMMENDATION_STATUSES))
