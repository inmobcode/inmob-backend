from flask import Blueprint

bp = Blueprint("clients", __name__, url_prefix="/api/clients")

from app.blueprints.clients import routes  # noqa: E402,F401
