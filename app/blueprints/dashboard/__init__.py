from flask import Blueprint

bp = Blueprint("dashboard", __name__, url_prefix="/api/dashboard")

from app.blueprints.dashboard import routes  # noqa: E402,F401
