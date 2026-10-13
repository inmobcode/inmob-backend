from marshmallow import Schema, fields, validate

from app.models.offer import DISCOUNT_TYPES, OFFER_OPERATIONS


class OfferPropertyItemSchema(Schema):
    property_id = fields.Str(required=True, data_key="propertyId")
    price_override = fields.Float(allow_none=True, data_key="priceOverride")
    discount_type = fields.Str(
        data_key="discountType", load_default="NONE", validate=validate.OneOf(DISCOUNT_TYPES)
    )
    discount_value = fields.Float(data_key="discountValue", load_default=0)
    security_deposit = fields.Float(data_key="securityDeposit", allow_none=True)
    bottom_text = fields.Str(data_key="bottomText", allow_none=True, validate=validate.Length(max=500))


class OfferSectionItemSchema(Schema):
    title = fields.Str(allow_none=True, validate=validate.Length(max=200))
    text = fields.Str(allow_none=True)
    properties = fields.List(fields.Nested(OfferPropertyItemSchema), load_default=list)


class OfferCreateSchema(Schema):
    title = fields.Str(required=True, validate=validate.Length(min=2, max=200))
    operation = fields.Str(load_default="BOTH", validate=validate.OneOf(OFFER_OPERATIONS))
    currency = fields.Str(load_default="USD", validate=validate.Length(equal=3))
    show_price = fields.Bool(data_key="showPrice", load_default=True)
    branded = fields.Bool(load_default=True)
    expires_at = fields.DateTime(data_key="expiresAt", allow_none=True)
    welcome_title = fields.Str(data_key="welcomeTitle", allow_none=True, validate=validate.Length(max=255))
    welcome_date_label = fields.Str(
        data_key="welcomeDateLabel", allow_none=True, validate=validate.Length(max=100)
    )
    welcome_content = fields.Str(data_key="welcomeContent", allow_none=True)
    # A CRM client: the offer copies its name, email and phone, and "send" emails it the link.
    client_id = fields.Str(data_key="clientId", allow_none=True)
    client_name = fields.Str(data_key="clientName", allow_none=True, validate=validate.Length(max=200))
    client_email = fields.Email(data_key="clientEmail", allow_none=True)
    client_phone = fields.Str(data_key="clientPhone", allow_none=True, validate=validate.Length(max=50))
    sections = fields.List(fields.Nested(OfferSectionItemSchema), load_default=list)


class OfferUpdateSchema(Schema):
    title = fields.Str(validate=validate.Length(min=2, max=200))
    operation = fields.Str(validate=validate.OneOf(OFFER_OPERATIONS))
    currency = fields.Str(validate=validate.Length(equal=3))
    show_price = fields.Bool(data_key="showPrice")
    branded = fields.Bool()
    expires_at = fields.DateTime(data_key="expiresAt", allow_none=True)
    welcome_title = fields.Str(data_key="welcomeTitle", allow_none=True, validate=validate.Length(max=255))
    welcome_date_label = fields.Str(
        data_key="welcomeDateLabel", allow_none=True, validate=validate.Length(max=100)
    )
    welcome_content = fields.Str(data_key="welcomeContent", allow_none=True)
    # A CRM client: the offer copies its name, email and phone, and "send" emails it the link.
    client_id = fields.Str(data_key="clientId", allow_none=True)
    client_name = fields.Str(data_key="clientName", allow_none=True, validate=validate.Length(max=200))
    client_email = fields.Email(data_key="clientEmail", allow_none=True)
    client_phone = fields.Str(data_key="clientPhone", allow_none=True, validate=validate.Length(max=50))
    sections = fields.List(fields.Nested(OfferSectionItemSchema))


class PublicOfferInquirySchema(Schema):
    name = fields.Str(required=True, validate=validate.Length(min=2, max=200))
    email = fields.Email(required=True)
    phone = fields.Str(allow_none=True, validate=validate.Length(max=50))
    message = fields.Str(allow_none=True)
