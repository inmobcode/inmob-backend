from flask import jsonify, request

from app.blueprints.reports import bp
from app.services import report_service
from app.utils.tenancy import current_agency_id, require_role


@bp.route("/", methods=["GET"])
@require_role("OWNER", "ADMIN")
def report():
    """The whole report for `?from=YYYY-MM-DD&to=YYYY-MM-DD` (whole months; the last 12 by default).
    For owners and admins: it shows everyone's results and the agency's money."""
    try:
        data = report_service.report(current_agency_id(), request.args.get("from"), request.args.get("to"))
    except report_service.ReportError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(data)
