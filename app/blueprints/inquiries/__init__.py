from flask import Blueprint

bp = Blueprint("inquiries", __name__, url_prefix="/api/inquiries")

from app.blueprints.inquiries import routes  # noqa: E402,F401
