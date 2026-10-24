from flask import Blueprint

bp = Blueprint("reports", __name__, url_prefix="/api/reports")

from app.blueprints.reports import routes  # noqa: E402,F401
