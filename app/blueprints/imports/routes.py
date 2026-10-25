import json

from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity

from app.blueprints.imports import bp
from app.i18n import request_locale
from app.i18n.imports import field_label, localize_plan
from app.extensions import db
from app.models import Agency
from app.services import billing_service, import_service
from app.services.importers.fields import IMPORT_FIELDS
from app.utils.tenancy import current_agency_id, require_role

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
PREVIEW_ROWS = 500


@bp.before_request
def _not_in_the_trial():
    """The data-migration tool is not part of the free trial."""
    agency = db.session.get(Agency, current_agency_id())
    if agency is not None and not billing_service.features(agency)["import"]:
        return jsonify({"message": "Data import isn't included in the free trial"}), 403


def _plan_from_request():
    """Both endpoints take the same multipart form (file or url, format,
    source, mapping, archiveMissing), so the preview and the import are
    computed from identical input."""
    form = request.form
    fmt = form.get("format", "")
    uploaded = request.files.get("file")
    content = uploaded.read() if uploaded else None
    if content is not None and len(content) > MAX_UPLOAD_BYTES:
        raise import_service.ImportFailure("El archivo pesa más de 10 MB.")

    mapping = None
    if form.get("mapping"):
        try:
            mapping = json.loads(form["mapping"])
        except ValueError as err:
            raise import_service.ImportFailure("El mapeo de columnas no es válido.") from err
        if not isinstance(mapping, dict):
            raise import_service.ImportFailure("El mapeo de columnas no es válido.")

    data, filename = import_service.read_input(
        fmt=fmt,
        content=content,
        filename=(uploaded.filename if uploaded else "") or "",
        url=form.get("url"),
    )
    return import_service.analyze(
        current_agency_id(),
        fmt=fmt,
        source=form.get("source"),
        content=data,
        filename=filename,
        mapping=mapping,
        archive_missing=form.get("archiveMissing") == "true",
    )


@bp.route("/fields", methods=["GET"])
@require_role("OWNER", "ADMIN")
def list_fields():
    """What an import can fill: the targets of the column-mapping step."""
    locale = request_locale()
    return jsonify(
        [
            {"key": f.key, "label": field_label(f.key, f.label, locale) if locale else f.label, "kind": f.kind}
            for f in IMPORT_FIELDS
        ],
    )


def _in_locale(payload: dict):
    locale = request_locale()
    return jsonify(localize_plan(payload, locale) if locale else payload)


@bp.route("/preview", methods=["POST"])
@require_role("OWNER", "ADMIN")
def preview():
    """Dry run: what the import would create, update, skip or archive."""
    try:
        plan = _plan_from_request()
    except import_service.ImportFailure as err:
        return jsonify({"message": err.message}), err.status_code
    return _in_locale(plan.to_dict(limit_rows=PREVIEW_ROWS))


@bp.route("/apply", methods=["POST"])
@require_role("OWNER", "ADMIN")
def apply():
    try:
        plan = _plan_from_request()
        result = import_service.run(
            current_agency_id(),
            get_jwt_identity(),
            plan,
            publish=request.form.get("publish") == "true",
        )
    except import_service.ImportFailure as err:
        return jsonify({"message": err.message}), err.status_code
    return _in_locale({**result, "counts": plan.counts()})
