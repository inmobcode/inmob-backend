from flask import Blueprint

bp = Blueprint("service_library", __name__, url_prefix="/api/services")

from app.blueprints.service_library import routes  # noqa: E402,F401
