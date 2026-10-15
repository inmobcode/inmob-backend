from marshmallow import Schema, fields, post_dump, post_load, validate

from app.constants.property_catalogs import (
    ENERGY_CERTIFICATE_OPTIONS,
    LOCATION_CATEGORY_OPTIONS,
)
from app.models.property import CATEGORIES, LISTING_TYPES
from app.utils import rich_text


class PropertyOwnerSchema(Schema):
    id = fields.Str(dump_only=True)
    name = fields.Str(required=True, validate=validate.Length(min=2, max=200))
    email = fields.Email(allow_none=True)
    phone = fields.Str(allow_none=True, validate=validate.Length(max=50))
    notes = fields.Str(allow_none=True)
    access_token = fields.Str(data_key="accessToken", dump_only=True)


class PropertyPhotoSchema(Schema):
    id = fields.Str(dump_only=True)
    url = fields.Str(required=True, validate=validate.Length(max=1000))
    position = fields.Int(load_default=0)
    is_cover = fields.Bool(data_key="isCover", load_default=False)
    # Not restricted to the fixed catalog: agents can name their own sections too.
    section = fields.Str(load_default="GENERAL", validate=validate.Length(min=1, max=60))
    section_detail = fields.Str(data_key="sectionDetail", allow_none=True)


class PropertyPhotoUpdateSchema(Schema):
    is_cover = fields.Bool(data_key="isCover")
    section = fields.Str(validate=validate.Length(min=1, max=60))
    section_detail = fields.Str(data_key="sectionDetail", allow_none=True)


class ClassificationSchema(Schema):
    floor_numbers = fields.List(fields.Int(), data_key="floorNumbers", load_default=list)
    parking_spaces = fields.Int(data_key="parkingSpaces", allow_none=True)
    storage_spaces = fields.Int(data_key="storageSpaces", allow_none=True)
    staff_room = fields.Int(data_key="staffRoom", allow_none=True)
    location_category = fields.Str(
        data_key="locationCategory", allow_none=True, validate=validate.OneOf(LOCATION_CATEGORY_OPTIONS)
    )
    layout_and_living_spaces = fields.Dict(data_key="layoutAndLivingSpaces", allow_none=True)
    master_bedroom_qty = fields.Int(data_key="masterBedroomQty", allow_none=True)
    double_bedroom_qty = fields.Int(data_key="doubleBedroomQty", allow_none=True)
    twin_bedroom_qty = fields.Int(data_key="twinBedroomQty", allow_none=True)
    single_bedroom_qty = fields.Int(data_key="singleBedroomQty", allow_none=True)
    bedroom_with_bunk_beds_qty = fields.Int(data_key="bedroomWithBunkBedsQty", allow_none=True)
    guest_bedroom_qty = fields.Int(data_key="guestBedroomQty", allow_none=True)
    management_name = fields.Str(data_key="managementName", allow_none=True)
    management_email = fields.Str(data_key="managementEmail", allow_none=True)
    management_phone = fields.Str(data_key="managementPhone", allow_none=True)
    management_company = fields.Str(data_key="managementCompany", allow_none=True)
    vendor_property_name = fields.Str(data_key="vendorPropertyName", allow_none=True)
    website = fields.Str(allow_none=True)
    commission = fields.Str(allow_none=True)
    license = fields.Str(allow_none=True)
    third_party_permission = fields.Bool(data_key="thirdPartyPermission", allow_none=True)


class PublicClassificationSchema(Schema):
    """Only the non-operational bits — no management/vendor/licensing contact info."""

    floor_numbers = fields.List(fields.Int(), data_key="floorNumbers")
    location_category = fields.Str(data_key="locationCategory", allow_none=True)
    layout_and_living_spaces = fields.Dict(data_key="layoutAndLivingSpaces", allow_none=True)
    master_bedroom_qty = fields.Int(data_key="masterBedroomQty", allow_none=True)
    double_bedroom_qty = fields.Int(data_key="doubleBedroomQty", allow_none=True)
    twin_bedroom_qty = fields.Int(data_key="twinBedroomQty", allow_none=True)
    single_bedroom_qty = fields.Int(data_key="singleBedroomQty", allow_none=True)
    bedroom_with_bunk_beds_qty = fields.Int(data_key="bedroomWithBunkBedsQty", allow_none=True)
    guest_bedroom_qty = fields.Int(data_key="guestBedroomQty", allow_none=True)


class DescriptionSchema(Schema):
    summary = fields.Str(allow_none=True)
    description = fields.Str(allow_none=True)
    extra_info = fields.Str(data_key="extraInfo", allow_none=True)
    included_services = fields.List(fields.Str(), data_key="includedServices", load_default=list)
    additional_notes = fields.Str(data_key="additionalNotes", allow_none=True)
    our_note = fields.Str(data_key="ourNote", allow_none=True)
    outdoor_title = fields.Str(data_key="outdoorTitle", allow_none=True)
    outdoor_description = fields.Str(data_key="outdoorDescription", allow_none=True)
    outdoor_image_url = fields.Str(data_key="outdoorImageUrl", allow_none=True)
    the_villa = fields.Dict(data_key="theVilla", allow_none=True)

    # The description is formatted text (see app/utils/rich_text.py): cleaned
    # on save, and on the way out for text stored before the editor existed.
    @post_load
    def clean_description(self, data, **kwargs):
        if "description" in data:
            data["description"] = rich_text.sanitize(data["description"])
        return data

    @post_dump
    def clean_description_out(self, data, **kwargs):
        if data.get("description"):
            data["description"] = rich_text.sanitize(data["description"])
        return data


PublicDescriptionSchema = DescriptionSchema  # all of it is public-facing marketing content


class PropertySchema(Schema):
    id = fields.Str(dump_only=True)
    agency_id = fields.Str(data_key="agencyId", dump_only=True)
    agency_slug = fields.Method("get_agency_slug", data_key="agencySlug", dump_only=True)
    owner_id = fields.Str(data_key="ownerId", allow_none=True)
    assigned_agent_id = fields.Str(data_key="assignedAgentId", allow_none=True)
    parent_property_id = fields.Str(data_key="parentPropertyId", allow_none=True)
    title = fields.Str(required=True, validate=validate.Length(min=2, max=200))
    slug = fields.Str(dump_only=True)
    listing_type = fields.Str(
        data_key="listingType", required=True, validate=validate.OneOf(LISTING_TYPES)
    )
    category = fields.Str(required=True, validate=validate.OneOf(CATEGORIES))
    status = fields.Str(dump_only=True)
    price = fields.Float(allow_none=True)
    currency = fields.Str(load_default="USD", validate=validate.Length(equal=3))
    country = fields.Str(allow_none=True)
    region = fields.Str(allow_none=True)
    area = fields.Str(allow_none=True)
    address = fields.Str(allow_none=True)
    lat = fields.Float(allow_none=True)
    lng = fields.Float(allow_none=True)
    google_map_url = fields.Str(data_key="googleMapUrl", allow_none=True)
    brochure_url = fields.Str(data_key="brochureUrl", allow_none=True, validate=validate.Length(max=1000))
    website_url = fields.Str(data_key="websiteUrl", allow_none=True, validate=validate.Length(max=1000))
    bedrooms = fields.Int(allow_none=True)
    bathrooms = fields.Int(allow_none=True)
    area_sqm = fields.Float(data_key="areaSqm", allow_none=True)
    plot_area = fields.Float(data_key="plotArea", allow_none=True)
    construction_year = fields.Int(data_key="constructionYear", allow_none=True)
    renovation_year = fields.Int(data_key="renovationYear", allow_none=True)
    energy_certificate = fields.Str(
        data_key="energyCertificate", allow_none=True, validate=validate.OneOf(ENERGY_CERTIFICATE_OPTIONS)
    )
    amenities = fields.List(fields.Str(), load_default=list)
    outdoor_amenities = fields.List(fields.Str(), data_key="outdoorAmenities", load_default=list)
    indoor_amenities = fields.List(fields.Str(), data_key="indoorAmenities", load_default=list)
    custom_facilities = fields.List(fields.Str(), data_key="customFacilities", load_default=list)
    location_features = fields.List(fields.Str(), data_key="locationFeatures", load_default=list)
    view = fields.List(fields.Str(), load_default=list)
    property_status = fields.List(fields.Str(), data_key="propertyStatus", load_default=list)
    enjoy = fields.Str(allow_none=True)
    outdoor_shower = fields.Int(data_key="outdoorShower", allow_none=True)
    agent_friendly_name = fields.Str(data_key="agentFriendlyName", allow_none=True)
    visible_location = fields.Str(data_key="visibleLocation", allow_none=True)
    guests = fields.Str(allow_none=True)
    stars = fields.Int(allow_none=True)
    watermark_photos = fields.Bool(data_key="watermarkPhotos")
    video_urls = fields.List(fields.Dict(), data_key="videoUrls", load_default=list)
    ical_import_url = fields.Str(data_key="icalImportUrl", dump_only=True, allow_none=True)
    owner = fields.Nested(PropertyOwnerSchema, dump_only=True)
    photos = fields.Nested(PropertyPhotoSchema, many=True, dump_only=True)
    classification = fields.Nested(ClassificationSchema, allow_none=True)
    content = fields.Nested(DescriptionSchema, allow_none=True)
    created_at = fields.DateTime(data_key="createdAt", dump_only=True)
    updated_at = fields.DateTime(data_key="updatedAt", dump_only=True)
    deleted_at = fields.DateTime(data_key="deletedAt", dump_only=True)

    def get_agency_slug(self, obj):
        return obj.agency.slug if obj.agency else None


class PublicPropertySchema(Schema):
    """Dump-only view for public consumption: no agencyId, owner contact info,
    management/vendor/licensing, or internal status/audit fields."""

    id = fields.Str(dump_only=True)
    title = fields.Str()
    slug = fields.Str()
    listing_type = fields.Str(data_key="listingType")
    category = fields.Str()
    price = fields.Float(allow_none=True)
    currency = fields.Str()
    country = fields.Str(allow_none=True)
    region = fields.Str(allow_none=True)
    area = fields.Str(allow_none=True)
    address = fields.Str(allow_none=True)
    lat = fields.Float(allow_none=True)
    lng = fields.Float(allow_none=True)
    brochure_url = fields.Str(data_key="brochureUrl", allow_none=True)
    website_url = fields.Str(data_key="websiteUrl", allow_none=True)
    bedrooms = fields.Int(allow_none=True)
    bathrooms = fields.Int(allow_none=True)
    area_sqm = fields.Float(data_key="areaSqm", allow_none=True)
    plot_area = fields.Float(data_key="plotArea", allow_none=True)
    construction_year = fields.Int(data_key="constructionYear", allow_none=True)
    renovation_year = fields.Int(data_key="renovationYear", allow_none=True)
    energy_certificate = fields.Str(data_key="energyCertificate", allow_none=True)
    amenities = fields.List(fields.Str())
    outdoor_amenities = fields.List(fields.Str(), data_key="outdoorAmenities")
    indoor_amenities = fields.List(fields.Str(), data_key="indoorAmenities")
    location_features = fields.List(fields.Str(), data_key="locationFeatures")
    view = fields.List(fields.Str())
    property_status = fields.List(fields.Str(), data_key="propertyStatus")
    enjoy = fields.Str(allow_none=True)
    outdoor_shower = fields.Int(data_key="outdoorShower", allow_none=True)
    visible_location = fields.Str(data_key="visibleLocation", allow_none=True)
    guests = fields.Str(allow_none=True)
    stars = fields.Int(allow_none=True)
    video_urls = fields.List(fields.Dict(), data_key="videoUrls")
    photos = fields.Nested(PropertyPhotoSchema, many=True)
    classification = fields.Nested(PublicClassificationSchema, allow_none=True)
    content = fields.Nested(PublicDescriptionSchema, allow_none=True)


class PropertyCreateSchema(Schema):
    title = fields.Str(required=True, validate=validate.Length(min=2, max=200))
    listing_type = fields.Str(
        data_key="listingType", required=True, validate=validate.OneOf(LISTING_TYPES)
    )
    category = fields.Str(required=True, validate=validate.OneOf(CATEGORIES))
    country = fields.Str(allow_none=True)
    region = fields.Str(allow_none=True)
    area = fields.Str(allow_none=True)


class PropertyUpdateSchema(Schema):
    title = fields.Str(validate=validate.Length(min=2, max=200))
    owner_id = fields.Str(data_key="ownerId", allow_none=True)
    assigned_agent_id = fields.Str(data_key="assignedAgentId", allow_none=True)
    listing_type = fields.Str(data_key="listingType", validate=validate.OneOf(LISTING_TYPES))
    category = fields.Str(validate=validate.OneOf(CATEGORIES))
    price = fields.Float(allow_none=True)
    currency = fields.Str(validate=validate.Length(equal=3))
    country = fields.Str(allow_none=True)
    region = fields.Str(allow_none=True)
    area = fields.Str(allow_none=True)
    address = fields.Str(allow_none=True)
    lat = fields.Float(allow_none=True)
    lng = fields.Float(allow_none=True)
    google_map_url = fields.Str(data_key="googleMapUrl", allow_none=True)
    brochure_url = fields.Str(data_key="brochureUrl", allow_none=True, validate=validate.Length(max=1000))
    website_url = fields.Str(data_key="websiteUrl", allow_none=True, validate=validate.Length(max=1000))
    bedrooms = fields.Int(allow_none=True)
    bathrooms = fields.Int(allow_none=True)
    area_sqm = fields.Float(data_key="areaSqm", allow_none=True)
    plot_area = fields.Float(data_key="plotArea", allow_none=True)
    construction_year = fields.Int(data_key="constructionYear", allow_none=True)
    renovation_year = fields.Int(data_key="renovationYear", allow_none=True)
    energy_certificate = fields.Str(
        data_key="energyCertificate", allow_none=True, validate=validate.OneOf(ENERGY_CERTIFICATE_OPTIONS)
    )
    amenities = fields.List(fields.Str())
    outdoor_amenities = fields.List(fields.Str(), data_key="outdoorAmenities")
    indoor_amenities = fields.List(fields.Str(), data_key="indoorAmenities")
    custom_facilities = fields.List(fields.Str(), data_key="customFacilities")
    location_features = fields.List(fields.Str(), data_key="locationFeatures")
    view = fields.List(fields.Str())
    property_status = fields.List(fields.Str(), data_key="propertyStatus")
    enjoy = fields.Str(allow_none=True)
    outdoor_shower = fields.Int(data_key="outdoorShower", allow_none=True)
    agent_friendly_name = fields.Str(data_key="agentFriendlyName", allow_none=True)
    visible_location = fields.Str(data_key="visibleLocation", allow_none=True)
    guests = fields.Str(allow_none=True)
    stars = fields.Int(allow_none=True)
    watermark_photos = fields.Bool(data_key="watermarkPhotos")
    video_urls = fields.List(fields.Dict(), data_key="videoUrls")
    classification = fields.Nested(ClassificationSchema, allow_none=True)
    content = fields.Nested(DescriptionSchema, allow_none=True)
