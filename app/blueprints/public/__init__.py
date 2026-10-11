from flask import Blueprint

bp = Blueprint("public", __name__, url_prefix="/api/public")

from app.blueprints.public import routes  # noqa: E402,F401
