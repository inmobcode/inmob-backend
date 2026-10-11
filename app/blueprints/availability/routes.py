from flask import jsonify, request
from marshmallow import ValidationError

from app.blueprints.availability import bp
from app.schemas.availability import AvailabilityBlockCreateSchema, AvailabilityBlockSchema, IcalSyncSchema
from app.services import availability_service
from app.utils.tenancy import current_agency_id

block_schema = AvailabilityBlockSchema()
blocks_schema = AvailabilityBlockSchema(many=True)


def _load(schema):
    try:
        return schema.load(request.get_json(silent=True) or {}), None
    except ValidationError as err:
        return None, (jsonify({"message": "Validation error", "errors": err.messages}), 400)


@bp.route("/", methods=["GET"])
def list_blocks(property_id):
    try:
        blocks = availability_service.list_blocks(current_agency_id(), property_id)
    except availability_service.AvailabilityError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(blocks_schema.dump(blocks))


@bp.route("/", methods=["POST"])
def create_block(property_id):
    data, error = _load(AvailabilityBlockCreateSchema())
    if error:
        return error

    try:
        block = availability_service.create_block(current_agency_id(), property_id, data)
    except availability_service.AvailabilityError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(block_schema.dump(block)), 201


@bp.route("/<block_id>", methods=["DELETE"])
def delete_block(property_id, block_id):
    try:
        availability_service.delete_block(current_agency_id(), property_id, block_id)
    except availability_service.AvailabilityError as err:
        return jsonify({"message": err.message}), err.status_code
    return "", 204


@bp.route("/sync", methods=["POST"])
def sync_ical(property_id):
    data, error = _load(IcalSyncSchema())
    if error:
        return error

    try:
        result = availability_service.sync_ical(current_agency_id(), property_id, data["ical_url"])
    except availability_service.AvailabilityError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(result)
