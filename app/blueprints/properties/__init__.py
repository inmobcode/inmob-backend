from flask import Blueprint

bp = Blueprint("properties", __name__, url_prefix="/api/properties")

from app.blueprints.properties import routes  # noqa: E402,F401
