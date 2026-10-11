from flask import Blueprint

bp = Blueprint("offers", __name__, url_prefix="/api/offers")

from app.blueprints.offers import routes  # noqa: E402,F401
