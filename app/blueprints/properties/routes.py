from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity
from marshmallow import ValidationError

from app.blueprints.properties import bp
from app.schemas.pool import PoolCreateSchema, PoolSchema, PoolUpdateSchema
from app.schemas.property import (
    PropertyCreateSchema,
    PropertyOwnerSchema,
    PropertyPhotoSchema,
    PropertySchema,
    PropertyUpdateSchema,
)
from app.schemas.rate_period import RatePeriodSchema, RatePeriodUpdateSchema
from app.schemas.recommendation import RecommendationSchema, RecommendationUpdateSchema
from app.services import property_service, storage_service
from app.utils.tenancy import current_agency_id

property_schema = PropertySchema()
properties_schema = PropertySchema(many=True)
owner_schema = PropertyOwnerSchema()
owners_schema = PropertyOwnerSchema(many=True)
pool_schema = PoolSchema()
pools_schema = PoolSchema(many=True)
rate_period_schema = RatePeriodSchema()
rate_periods_schema = RatePeriodSchema(many=True)
recommendation_schema = RecommendationSchema()
recommendations_schema = RecommendationSchema(many=True)

MAX_PHOTO_BYTES = 15 * 1024 * 1024  # 15MB — plenty for a compressed WebP


def _load_json(schema, partial=False):
    try:
        return schema.load(request.get_json(silent=True) or {}, partial=partial), None
    except ValidationError as err:
        return None, (jsonify({"message": "Validation error", "errors": err.messages}), 400)


@bp.route("/", methods=["GET"])
def list_properties():
    agency_id = current_agency_id()
    status = request.args.get("status")
    listing_type = request.args.get("listingType")
    properties = property_service.list_properties(agency_id, status=status, listing_type=listing_type)
    return jsonify(properties_schema.dump(properties))


@bp.route("/", methods=["POST"])
def create_property():
    data, error = _load_json(PropertyCreateSchema())
    if error:
        return error

    agency_id = current_agency_id()
    prop = property_service.create_property(agency_id, get_jwt_identity(), data)
    return jsonify(property_schema.dump(prop)), 201


@bp.route("/owners", methods=["GET"])
def list_owners():
    return jsonify(owners_schema.dump(property_service.list_owners(current_agency_id())))


@bp.route("/owners", methods=["POST"])
def create_owner():
    data, error = _load_json(PropertyOwnerSchema())
    if error:
        return error
    owner = property_service.create_owner(current_agency_id(), data)
    return jsonify(owner_schema.dump(owner)), 201


@bp.route("/owners/<owner_id>/regenerate-token", methods=["POST"])
def regenerate_owner_token(owner_id):
    try:
        owner = property_service.regenerate_owner_token(current_agency_id(), owner_id)
    except property_service.PropertyError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(owner_schema.dump(owner))


@bp.route("/<property_id>", methods=["GET"])
def get_property(property_id):
    try:
        prop = property_service.get_property(current_agency_id(), property_id)
    except property_service.PropertyError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(property_schema.dump(prop))


@bp.route("/<property_id>", methods=["PATCH"])
def update_property(property_id):
    data, error = _load_json(PropertyUpdateSchema(), partial=True)
    if error:
        return error

    try:
        prop = property_service.update_property(current_agency_id(), property_id, data)
    except property_service.PropertyError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(property_schema.dump(prop))


@bp.route("/<property_id>", methods=["DELETE"])
def delete_property(property_id):
    try:
        property_service.delete_property(current_agency_id(), property_id)
    except property_service.PropertyError as err:
        return jsonify({"message": err.message}), err.status_code
    return "", 204

@bp.route("/trash", methods=["GET"])
def list_trashed_properties():
    """What's in the trash; anything older than TRASH_DAYS is deleted for good first."""
    items = property_service.list_trashed_properties(current_agency_id())
    return jsonify(properties_schema.dump(items))


@bp.route("/<property_id>/restore", methods=["POST"])
def restore_property(property_id):
    try:
        item = property_service.restore_property(current_agency_id(), property_id)
    except property_service.PropertyError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(property_schema.dump(item))


@bp.route("/<property_id>/permanent", methods=["DELETE"])
def delete_property_forever(property_id):
    try:
        property_service.delete_property_forever(current_agency_id(), property_id)
    except property_service.PropertyError as err:
        return jsonify({"message": err.message}), err.status_code
    return "", 204



@bp.route("/<property_id>/publish", methods=["POST"])
def publish_property(property_id):
    try:
        prop = property_service.set_status(current_agency_id(), property_id, "PUBLISHED")
    except property_service.PropertyError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(property_schema.dump(prop))


@bp.route("/<property_id>/archive", methods=["POST"])
def archive_property(property_id):
    try:
        prop = property_service.set_status(current_agency_id(), property_id, "ARCHIVED")
    except property_service.PropertyError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(property_schema.dump(prop))


@bp.route("/<property_id>/unpublish", methods=["POST"])
def unpublish_property(property_id):
    try:
        prop = property_service.set_status(current_agency_id(), property_id, "DRAFT")
    except property_service.PropertyError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(property_schema.dump(prop))


@bp.route("/<property_id>/rooms", methods=["POST"])
def create_room(property_id):
    try:
        room = property_service.create_room(current_agency_id(), get_jwt_identity(), property_id)
    except property_service.PropertyError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(property_schema.dump(room)), 201


@bp.route("/<property_id>/photos", methods=["POST"])
def add_photo(property_id):
    agency_id = current_agency_id()

    uploaded = request.files.get("file")
    if uploaded is not None:
        content = uploaded.read()
        if len(content) > MAX_PHOTO_BYTES:
            return jsonify({"message": "Photo is too large"}), 400

        try:
            url = storage_service.upload_photo(
                agency_id,
                property_id,
                uploaded.filename or "photo.webp",
                content,
                uploaded.mimetype or "image/webp",
            )
        except storage_service.StorageError as err:
            return jsonify({"message": err.message}), err.status_code

        data = {
            "url": url,
            "is_cover": request.form.get("isCover") == "true",
            "section": request.form.get("section", "GENERAL"),
            "section_detail": request.form.get("sectionDetail") or None,
        }
    else:
        data, error = _load_json(PropertyPhotoSchema())
        if error:
            return error

    try:
        prop = property_service.add_photo(agency_id, property_id, data)
    except property_service.PropertyError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(property_schema.dump(prop)), 201


@bp.route("/<property_id>/photos/<photo_id>", methods=["DELETE"])
def remove_photo(property_id, photo_id):
    try:
        prop = property_service.remove_photo(current_agency_id(), property_id, photo_id)
    except property_service.PropertyError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(property_schema.dump(prop))


@bp.route("/<property_id>/pools", methods=["GET"])
def list_pools(property_id):
    try:
        pools = property_service.list_pools(current_agency_id(), property_id)
    except property_service.PropertyError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(pools_schema.dump(pools))


@bp.route("/<property_id>/pools", methods=["POST"])
def create_pool(property_id):
    data, error = _load_json(PoolCreateSchema())
    if error:
        return error
    try:
        pool = property_service.create_pool(current_agency_id(), property_id, data)
    except property_service.PropertyError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(pool_schema.dump(pool)), 201


@bp.route("/<property_id>/pools/<pool_id>", methods=["PATCH"])
def update_pool(property_id, pool_id):
    data, error = _load_json(PoolUpdateSchema(), partial=True)
    if error:
        return error
    try:
        pool = property_service.update_pool(current_agency_id(), property_id, pool_id, data)
    except property_service.PropertyError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(pool_schema.dump(pool))


@bp.route("/<property_id>/pools/<pool_id>", methods=["DELETE"])
def delete_pool(property_id, pool_id):
    try:
        property_service.delete_pool(current_agency_id(), property_id, pool_id)
    except property_service.PropertyError as err:
        return jsonify({"message": err.message}), err.status_code
    return "", 204


@bp.route("/<property_id>/rates", methods=["GET"])
def list_rate_periods(property_id):
    try:
        periods = property_service.list_rate_periods(current_agency_id(), property_id)
    except property_service.PropertyError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(rate_periods_schema.dump(periods))


@bp.route("/<property_id>/rates", methods=["POST"])
def create_rate_period(property_id):
    data, error = _load_json(RatePeriodSchema())
    if error:
        return error
    try:
        period = property_service.create_rate_period(current_agency_id(), property_id, data)
    except property_service.PropertyError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(rate_period_schema.dump(period)), 201


@bp.route("/<property_id>/rates/<period_id>", methods=["PATCH"])
def update_rate_period(property_id, period_id):
    data, error = _load_json(RatePeriodUpdateSchema(), partial=True)
    if error:
        return error
    try:
        period = property_service.update_rate_period(current_agency_id(), property_id, period_id, data)
    except property_service.PropertyError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(rate_period_schema.dump(period))


@bp.route("/<property_id>/rates/<period_id>", methods=["DELETE"])
def delete_rate_period(property_id, period_id):
    try:
        property_service.delete_rate_period(current_agency_id(), property_id, period_id)
    except property_service.PropertyError as err:
        return jsonify({"message": err.message}), err.status_code
    return "", 204


@bp.route("/<property_id>/recommendations", methods=["GET"])
def list_recommendations(property_id):
    try:
        recommendations = property_service.list_recommendations(current_agency_id(), property_id)
    except property_service.PropertyError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(recommendations_schema.dump(recommendations))


@bp.route("/<property_id>/recommendations", methods=["POST"])
def create_recommendation(property_id):
    data, error = _load_json(RecommendationSchema())
    if error:
        return error
    try:
        recommendation = property_service.create_recommendation(current_agency_id(), property_id, data)
    except property_service.PropertyError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(recommendation_schema.dump(recommendation)), 201


@bp.route("/<property_id>/recommendations/<recommendation_id>", methods=["PATCH"])
def update_recommendation(property_id, recommendation_id):
    data, error = _load_json(RecommendationUpdateSchema(), partial=True)
    if error:
        return error
    try:
        recommendation = property_service.update_recommendation(
            current_agency_id(), property_id, recommendation_id, data
        )
    except property_service.PropertyError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(recommendation_schema.dump(recommendation))


@bp.route("/<property_id>/recommendations/<recommendation_id>", methods=["DELETE"])
def delete_recommendation(property_id, recommendation_id):
    try:
        property_service.delete_recommendation(current_agency_id(), property_id, recommendation_id)
    except property_service.PropertyError as err:
        return jsonify({"message": err.message}), err.status_code
    return "", 204
