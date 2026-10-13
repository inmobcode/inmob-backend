from flask import jsonify, request
from marshmallow import ValidationError

from app.blueprints.agency import bp
from app.extensions import db
from app.models import Agency
from app.schemas.agency import AgencySchema, AgencyUpdateSchema, SiteSettingsSchema
from app.services import storage_service
from app.utils.tenancy import current_agency_id, require_role

agency_schema = AgencySchema()

MAX_LOGO_BYTES = 5 * 1024 * 1024  # 5MB
MAX_COVER_BYTES = 8 * 1024 * 1024  # 8MB


def _get_current_agency() -> Agency:
    return db.session.get(Agency, current_agency_id())


@bp.route("/", methods=["GET"])
def get_agency():
    return jsonify(agency_schema.dump(_get_current_agency()))


@bp.route("/", methods=["PATCH"])
@require_role("OWNER", "ADMIN")
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
@require_role("OWNER", "ADMIN")
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


@bp.route("/site", methods=["PATCH"])
@require_role("OWNER", "ADMIN")
def update_site():
    """Merges the given keys into the site settings; keys not sent stay as they were."""
    try:
        data = SiteSettingsSchema().load(request.get_json(silent=True) or {}, partial=True)
    except ValidationError as err:
        return jsonify({"message": "Validation error", "errors": err.messages}), 400

    agency = _get_current_agency()
    # Stored with the schema's attribute names (snake_case); camelCase only on the wire.
    # Reassign a new dict: SQLAlchemy doesn't track in-place changes to a JSON column.
    agency.site = {**(agency.site or {}), **data}
    db.session.commit()
    return jsonify(agency_schema.dump(agency))


@bp.route("/cover", methods=["POST"])
@require_role("OWNER", "ADMIN")
def upload_cover():
    agency = _get_current_agency()

    uploaded = request.files.get("file")
    if uploaded is None:
        return jsonify({"message": "Falta el archivo"}), 400

    content = uploaded.read()
    if len(content) > MAX_COVER_BYTES:
        return jsonify({"message": "La portada es demasiado grande"}), 400

    try:
        url = storage_service.upload_agency_cover(
            agency.id,
            uploaded.filename or "cover.webp",
            content,
            uploaded.mimetype or "image/webp",
        )
    except storage_service.StorageError as err:
        return jsonify({"message": err.message}), err.status_code

    agency.site = {**(agency.site or {}), "cover_url": url}
    db.session.commit()
    return jsonify(agency_schema.dump(agency))


@bp.route("/site-image", methods=["POST"])
@require_role("OWNER", "ADMIN")
def upload_site_image():
    """Uploads an image for a content block and returns its URL; saving the block is a separate PATCH."""
    agency = _get_current_agency()

    uploaded = request.files.get("file")
    if uploaded is None:
        return jsonify({"message": "Falta el archivo"}), 400

    content = uploaded.read()
    if len(content) > MAX_COVER_BYTES:
        return jsonify({"message": "La imagen es demasiado grande"}), 400

    try:
        url = storage_service.upload_agency_site_image(
            agency.id,
            uploaded.filename or "image.webp",
            content,
            uploaded.mimetype or "image/webp",
        )
    except storage_service.StorageError as err:
        return jsonify({"message": err.message}), err.status_code

    return jsonify({"url": url})
