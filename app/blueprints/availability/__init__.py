from flask import Blueprint

bp = Blueprint("availability", __name__, url_prefix="/api/properties/<property_id>/availability")

from app.blueprints.availability import routes  # noqa: E402,F401
