from flask import jsonify

from app.blueprints.dashboard import bp
from app.services import dashboard_service
from app.utils.tenancy import current_agency_id, current_user_id


@bp.route("/summary", methods=["GET"])
def summary():
    return jsonify(dashboard_service.summary(current_agency_id(), current_user_id()))
