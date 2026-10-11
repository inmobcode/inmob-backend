from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity
from marshmallow import ValidationError

from app.blueprints.clients import bp
from app.schemas.client import ClientSchema, ClientUpdateSchema, InteractionSchema
from app.services import crm_service
from app.utils.tenancy import current_agency_id

client_schema = ClientSchema()
clients_schema = ClientSchema(many=True)
interaction_schema = InteractionSchema()
interactions_schema = InteractionSchema(many=True)


def _load(schema, partial=False):
    try:
        return schema.load(request.get_json(silent=True) or {}, partial=partial), None
    except ValidationError as err:
        return None, (jsonify({"message": "Validation error", "errors": err.messages}), 400)


@bp.route("/", methods=["GET"])
def list_clients():
    clients = crm_service.list_clients(current_agency_id())
    return jsonify(clients_schema.dump(clients))


@bp.route("/", methods=["POST"])
def create_client():
    data, error = _load(ClientSchema())
    if error:
        return error
    client = crm_service.create_client(current_agency_id(), data)
    return jsonify(client_schema.dump(client)), 201


@bp.route("/<client_id>", methods=["GET"])
def get_client(client_id):
    try:
        client = crm_service.get_client(current_agency_id(), client_id)
    except crm_service.ClientError as err:
        return jsonify({"message": err.message}), err.status_code

    payload = client_schema.dump(client)
    payload["interactions"] = interactions_schema.dump(client.interactions)
    return jsonify(payload)


@bp.route("/<client_id>", methods=["PATCH"])
def update_client(client_id):
    data, error = _load(ClientUpdateSchema(), partial=True)
    if error:
        return error

    try:
        client = crm_service.update_client(current_agency_id(), client_id, data)
    except crm_service.ClientError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(client_schema.dump(client))


@bp.route("/<client_id>/interactions", methods=["POST"])
def add_interaction(client_id):
    data, error = _load(InteractionSchema())
    if error:
        return error

    try:
        interaction = crm_service.add_interaction(
            current_agency_id(), client_id, get_jwt_identity(), data
        )
    except crm_service.ClientError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(interaction_schema.dump(interaction)), 201
