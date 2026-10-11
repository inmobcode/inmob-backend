from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity
from marshmallow import ValidationError

from app.blueprints.offers import bp
from app.schemas.offer import OfferCreateSchema, OfferUpdateSchema
from app.services import offer_service
from app.utils.tenancy import current_agency_id


def _load(schema, partial=False):
    try:
        return schema.load(request.get_json(silent=True) or {}, partial=partial), None
    except ValidationError as err:
        return None, (jsonify({"message": "Validation error", "errors": err.messages}), 400)


@bp.route("/", methods=["GET"])
def list_offers():
    offers = offer_service.list_offers(current_agency_id())
    return jsonify([offer_service.serialize_offer(offer) for offer in offers])


@bp.route("/", methods=["POST"])
def create_offer():
    data, error = _load(OfferCreateSchema())
    if error:
        return error

    try:
        offer = offer_service.create_offer(current_agency_id(), get_jwt_identity(), data)
    except offer_service.OfferError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(offer_service.serialize_offer(offer)), 201


@bp.route("/<offer_id>", methods=["GET"])
def get_offer(offer_id):
    try:
        offer = offer_service.get_offer(current_agency_id(), offer_id)
    except offer_service.OfferError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(offer_service.serialize_offer(offer))


@bp.route("/<offer_id>", methods=["PATCH"])
def update_offer(offer_id):
    data, error = _load(OfferUpdateSchema(), partial=True)
    if error:
        return error

    try:
        offer = offer_service.update_offer(current_agency_id(), offer_id, data)
    except offer_service.OfferError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(offer_service.serialize_offer(offer))


@bp.route("/<offer_id>", methods=["DELETE"])
def delete_offer(offer_id):
    try:
        offer_service.delete_offer(current_agency_id(), offer_id)
    except offer_service.OfferError as err:
        return jsonify({"message": err.message}), err.status_code
    return "", 204


@bp.route("/<offer_id>/send", methods=["POST"])
def send_offer(offer_id):
    try:
        offer = offer_service.send_offer(current_agency_id(), offer_id)
    except offer_service.OfferError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(offer_service.serialize_offer(offer))


