from flask import Blueprint

bp = Blueprint("imports", __name__, url_prefix="/api/imports")

from app.blueprints.imports import routes  # noqa: E402,F401
