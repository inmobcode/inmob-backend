from flask import Blueprint

bp = Blueprint("bookings", __name__, url_prefix="/api/bookings")

from app.blueprints.bookings import routes  # noqa: E402,F401
