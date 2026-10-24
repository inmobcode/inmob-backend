from flask import Blueprint

bp = Blueprint("reviews", __name__, url_prefix="/api/reviews")

from app.blueprints.reviews import routes  # noqa: E402,F401
