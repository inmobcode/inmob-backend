from marshmallow import Schema, fields


class RatePeriodSchema(Schema):
    id = fields.Str(dump_only=True)
    property_id = fields.Str(data_key="propertyId", dump_only=True)
    label = fields.Str(allow_none=True)
    start_date = fields.Date(data_key="startDate", required=True)
    end_date = fields.Date(data_key="endDate", required=True)
    official_price_per_night = fields.Float(data_key="officialPricePerNight", allow_none=True)
    management_fee_pct = fields.Float(data_key="managementFeePct", load_default=10)
    agency_commission_pct = fields.Float(data_key="agencyCommissionPct", load_default=20)
    net_owner_per_night = fields.Float(data_key="netOwnerPerNight", allow_none=True)
    min_stay = fields.Int(data_key="minStay", allow_none=True)
    included_services = fields.Str(data_key="includedServices", allow_none=True)


class RatePeriodUpdateSchema(Schema):
    label = fields.Str(allow_none=True)
    start_date = fields.Date(data_key="startDate")
    end_date = fields.Date(data_key="endDate")
    official_price_per_night = fields.Float(data_key="officialPricePerNight", allow_none=True)
    management_fee_pct = fields.Float(data_key="managementFeePct")
    agency_commission_pct = fields.Float(data_key="agencyCommissionPct")
    net_owner_per_night = fields.Float(data_key="netOwnerPerNight", allow_none=True)
    min_stay = fields.Int(data_key="minStay", allow_none=True)
    included_services = fields.Str(data_key="includedServices", allow_none=True)
