from flask import Blueprint

bp = Blueprint("agency", __name__, url_prefix="/api/agency")

from app.blueprints.agency import routes  # noqa: E402,F401
