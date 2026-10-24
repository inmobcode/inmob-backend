from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity
from marshmallow import ValidationError

from app.blueprints.offers import bp
from app.schemas.offer import OfferCreateSchema, OfferUpdateSchema
from app.services import audit, offer_service
from app.utils.tenancy import current_agency_id


def _load(schema, partial=False):
    try:
        return schema.load(request.get_json(silent=True) or {}, partial=partial), None
    except ValidationError as err:
        return None, (jsonify({"message": "Validation error", "errors": err.messages}), 400)


@bp.route("/", methods=["GET"])
def list_offers():
    """The offers; `?templates=1` lists the templates instead."""
    offers = offer_service.list_offers(current_agency_id(), templates=request.args.get("templates") == "1")
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
    return jsonify(offer_service.serialize_offer(offer, detail=True))


@bp.route("/<offer_id>", methods=["PATCH"])
def update_offer(offer_id):
    data, error = _load(OfferUpdateSchema(), partial=True)
    if error:
        return error

    try:
        offer = offer_service.update_offer(current_agency_id(), offer_id, data)
    except offer_service.OfferError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(offer_service.serialize_offer(offer, detail=True))


@bp.route("/<offer_id>", methods=["DELETE"])
def delete_offer(offer_id):
    try:
        offer_service.delete_offer(current_agency_id(), offer_id)
    except offer_service.OfferError as err:
        return jsonify({"message": err.message}), err.status_code
    return "", 204

@bp.route("/trash", methods=["GET"])
def list_trashed_offers():
    """What's in the trash; anything older than TRASH_DAYS is deleted for good first."""
    items = offer_service.list_trashed_offers(current_agency_id())
    return jsonify([offer_service.serialize_offer(item) for item in items])


@bp.route("/<offer_id>/restore", methods=["POST"])
def restore_offer(offer_id):
    try:
        item = offer_service.restore_offer(current_agency_id(), offer_id)
    except offer_service.OfferError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(offer_service.serialize_offer(item))


@bp.route("/<offer_id>/permanent", methods=["DELETE"])
def delete_offer_forever(offer_id):
    try:
        offer_service.delete_offer_forever(current_agency_id(), offer_id)
    except offer_service.OfferError as err:
        return jsonify({"message": err.message}), err.status_code
    return "", 204



@bp.route("/<offer_id>/send", methods=["POST"])
def send_offer(offer_id):
    try:
        offer = offer_service.send_offer(current_agency_id(), offer_id)
    except offer_service.OfferError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(offer_service.serialize_offer(offer, detail=True))


@bp.route("/<offer_id>/duplicate", methods=["POST"])
def duplicate_offer(offer_id):
    """`{"asTemplate": true}` saves it as a template; otherwise a new draft offer
    (from an offer, or from a template). `title` names the copy."""
    body = request.get_json(silent=True) or {}
    as_template = body.get("asTemplate", False)
    title = body.get("title")
    if not isinstance(as_template, bool) or (title is not None and (not isinstance(title, str) or len(title.strip()) < 2)):
        return jsonify({"message": "Validation error", "errors": {"title": ["Mínimo 2 caracteres."]}}), 400
    try:
        offer = offer_service.duplicate_offer(
            current_agency_id(), get_jwt_identity(), offer_id, as_template=as_template, title=title and title.strip()
        )
    except offer_service.OfferError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(offer_service.serialize_offer(offer)), 201




@bp.route("/<offer_id>/history", methods=["GET"])
def offer_history(offer_id):
    try:
        offer = offer_service.get_offer(current_agency_id(), offer_id)
    except offer_service.OfferError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(audit.serialize(audit.history("OFFER", offer.id)))
