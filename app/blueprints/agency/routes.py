from flask import jsonify, request
from marshmallow import ValidationError

from app.blueprints.agency import bp
from app.extensions import db
from app.models import Agency
from app.schemas.agency import AgencySchema, AgencyUpdateSchema
from app.services import storage_service
from app.utils.tenancy import current_agency_id

agency_schema = AgencySchema()

MAX_LOGO_BYTES = 5 * 1024 * 1024  # 5MB


def _get_current_agency() -> Agency:
    return db.session.get(Agency, current_agency_id())


@bp.route("/", methods=["GET"])
def get_agency():
    return jsonify(agency_schema.dump(_get_current_agency()))


@bp.route("/", methods=["PATCH"])
def update_agency():
    try:
        data = AgencyUpdateSchema().load(request.get_json(silent=True) or {}, partial=True)
    except ValidationError as err:
        return jsonify({"message": "Validation error", "errors": err.messages}), 400

    agency = _get_current_agency()

    if "slug" in data and data["slug"] != agency.slug:
        existing = Agency.query.filter_by(slug=data["slug"]).first()
        if existing is not None:
            return jsonify({"message": "Ese slug ya está en uso"}), 409
        agency.slug = data["slug"]

    for field in ("name", "contact_email", "locale", "currency"):
        if field in data:
            setattr(agency, field, data[field])

    db.session.commit()
    return jsonify(agency_schema.dump(agency))


@bp.route("/logo", methods=["POST"])
def upload_logo():
    agency = _get_current_agency()

    uploaded = request.files.get("file")
    if uploaded is None:
        return jsonify({"message": "Falta el archivo"}), 400

    content = uploaded.read()
    if len(content) > MAX_LOGO_BYTES:
        return jsonify({"message": "El logo es demasiado grande"}), 400

    try:
        url = storage_service.upload_agency_logo(
            agency.id,
            uploaded.filename or "logo.webp",
            content,
            uploaded.mimetype or "image/webp",
        )
    except storage_service.StorageError as err:
        return jsonify({"message": err.message}), err.status_code

    agency.logo_url = url
    db.session.commit()
    return jsonify(agency_schema.dump(agency))
