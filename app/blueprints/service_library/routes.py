from flask import jsonify, request
from marshmallow import ValidationError

from app.blueprints.service_library import bp
from app.schemas.service import ServiceSchema
from app.services import service_library, storage_service
from app.utils.tenancy import current_agency_id

MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8MB, like the site images

service_schema = ServiceSchema()
services_schema = ServiceSchema(many=True)


def _load(partial=False):
    try:
        return ServiceSchema().load(request.get_json(silent=True) or {}, partial=partial), None
    except ValidationError as err:
        return None, (jsonify({"message": "Validation error", "errors": err.messages}), 400)


@bp.route("/", methods=["GET"])
def list_services():
    return jsonify(services_schema.dump(service_library.list_services(current_agency_id())))


@bp.route("/", methods=["POST"])
def create_service():
    data, error = _load()
    if error:
        return error
    service = service_library.create_service(current_agency_id(), data)
    return jsonify(service_schema.dump(service)), 201


@bp.route("/<service_id>", methods=["GET"])
def get_service(service_id):
    try:
        service = service_library.get_service(current_agency_id(), service_id)
    except service_library.ServiceError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(service_schema.dump(service))


@bp.route("/<service_id>", methods=["PATCH"])
def update_service(service_id):
    data, error = _load(partial=True)
    if error:
        return error
    try:
        service = service_library.update_service(current_agency_id(), service_id, data)
    except service_library.ServiceError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(service_schema.dump(service))


@bp.route("/<service_id>", methods=["DELETE"])
def delete_service(service_id):
    try:
        service_library.delete_service(current_agency_id(), service_id)
    except service_library.ServiceError as err:
        return jsonify({"message": err.message}), err.status_code
    return "", 204


@bp.route("/image", methods=["POST"])
def upload_service_image():
    """Uploads a service's photo and returns its URL; saving the service is a separate request.
    Open to the whole team (unlike the site images), since agents build offers too."""
    agency_id = current_agency_id()
    uploaded = request.files.get("file")
    if uploaded is None:
        return jsonify({"message": "Falta el archivo"}), 400
    content = uploaded.read()
    if len(content) > MAX_IMAGE_BYTES:
        return jsonify({"message": "La imagen es demasiado grande"}), 400
    try:
        url = storage_service.upload_agency_site_image(
            agency_id, uploaded.filename or "image.webp", content, uploaded.mimetype or "image/webp"
        )
    except storage_service.StorageError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify({"url": url})
