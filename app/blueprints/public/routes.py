from flask import Response, jsonify, request
from marshmallow import ValidationError

from app.blueprints.public import bp
from app.models import Agency, Property
from app.schemas.agency import AgencyPublicSchema
from app.schemas.client import PublicInquirySchema
from app.schemas.offer import PublicOfferInquirySchema
from app.schemas.property import PublicPropertySchema
from app.services import availability_service, booking_service, crm_service, offer_service, property_service

property_schema = PublicPropertySchema()
properties_schema = PublicPropertySchema(many=True)
agency_public_schema = AgencyPublicSchema()


def _get_agency_or_404(agency_slug: str) -> Agency | None:
    return Agency.query.filter_by(slug=agency_slug).first()


@bp.route("/<agency_slug>", methods=["GET"])
def get_public_agency(agency_slug):
    agency = _get_agency_or_404(agency_slug)
    if agency is None:
        return jsonify({"message": "Agency not found"}), 404
    return jsonify(agency_public_schema.dump(agency))


@bp.route("/<agency_slug>/properties", methods=["GET"])
def list_public_properties(agency_slug):
    agency = _get_agency_or_404(agency_slug)
    if agency is None:
        return jsonify({"message": "Agency not found"}), 404

    query = Property.query.filter_by(agency_id=agency.id, status="PUBLISHED")

    listing_type = request.args.get("listingType")
    if listing_type:
        query = query.filter_by(listing_type=listing_type)

    category = request.args.get("category")
    if category:
        query = query.filter_by(category=category)

    for field, column in (
        ("country", Property.country),
        ("region", Property.region),
        ("area", Property.area),
    ):
        value = request.args.get(field)
        if value:
            query = query.filter(column == value)

    min_price = request.args.get("minPrice", type=float)
    if min_price is not None:
        query = query.filter(Property.price >= min_price)

    max_price = request.args.get("maxPrice", type=float)
    if max_price is not None:
        query = query.filter(Property.price <= max_price)

    search = request.args.get("q")
    if search:
        query = query.filter(Property.title.ilike(f"%{search}%"))

    properties = query.order_by(Property.created_at.desc()).all()
    return jsonify(properties_schema.dump(properties))


@bp.route("/<agency_slug>/properties/<property_slug>", methods=["GET"])
def get_public_property(agency_slug, property_slug):
    agency = _get_agency_or_404(agency_slug)
    if agency is None:
        return jsonify({"message": "Agency not found"}), 404

    prop = Property.query.filter_by(
        agency_id=agency.id, slug=property_slug, status="PUBLISHED"
    ).first()
    if prop is None:
        return jsonify({"message": "Property not found"}), 404

    return jsonify(property_schema.dump(prop))


@bp.route("/<agency_slug>/properties/<property_slug>/availability.ics", methods=["GET"])
def get_property_ics(agency_slug, property_slug):
    agency = _get_agency_or_404(agency_slug)
    if agency is None:
        return jsonify({"message": "Agency not found"}), 404

    prop = Property.query.filter_by(
        agency_id=agency.id, slug=property_slug, status="PUBLISHED"
    ).first()
    if prop is None:
        return jsonify({"message": "Property not found"}), 404

    ics_bytes = availability_service.export_ics(prop)
    return Response(ics_bytes, mimetype="text/calendar")


@bp.route("/<agency_slug>/inquiries", methods=["POST"])
def create_inquiry(agency_slug):
    agency = _get_agency_or_404(agency_slug)
    if agency is None:
        return jsonify({"message": "Agency not found"}), 404

    try:
        data = PublicInquirySchema().load(request.get_json(silent=True) or {})
    except ValidationError as err:
        return jsonify({"message": "Validation error", "errors": err.messages}), 400

    property_id = data.get("property_id")
    if property_id:
        prop = Property.query.filter_by(id=property_id, agency_id=agency.id, status="PUBLISHED").first()
        if prop is None:
            return jsonify({"message": "Property not found"}), 404

    inquiry = crm_service.log_inquiry(
        agency.id,
        name=data["name"],
        email=data["email"],
        phone=data.get("phone"),
        message=data.get("message"),
        inquiry_type=data.get("inquiry_type", "GENERAL"),
        source="WEBSITE",
        property_id=property_id,
    )
    return jsonify({"id": inquiry.id}), 201


@bp.route("/offers/<token>", methods=["GET"])
def get_public_offer(token):
    try:
        offer = offer_service.get_offer_by_token(token)
    except offer_service.OfferError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(offer_service.serialize_offer(offer, public=True))


@bp.route("/offers/<token>/inquiries", methods=["POST"])
def create_public_offer_inquiry(token):
    try:
        data = PublicOfferInquirySchema().load(request.get_json(silent=True) or {})
    except ValidationError as err:
        return jsonify({"message": "Validation error", "errors": err.messages}), 400

    try:
        offer = offer_service.create_public_offer_inquiry(token, data)
    except offer_service.OfferError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(offer_service.serialize_offer(offer, public=True)), 201


@bp.route("/owners/<token>", methods=["GET"])
def get_public_owner_portal(token):
    owner = property_service.get_owner_by_token(token)
    if owner is None:
        return jsonify({"message": "Not found"}), 404
    return jsonify(property_service.serialize_owner_portal(owner))


@bp.route("/bookings/<token>", methods=["GET"])
def get_public_booking(token):
    try:
        booking = booking_service.get_booking_by_token(token)
    except booking_service.BookingError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(booking_service.serialize_public_booking(booking))
