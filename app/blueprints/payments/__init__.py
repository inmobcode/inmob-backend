from flask import Blueprint

bp = Blueprint("payments", __name__, url_prefix="/api/payments")

from app.blueprints.payments import routes  # noqa: E402,F401
