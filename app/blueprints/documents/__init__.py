from flask import Blueprint

bp = Blueprint("documents", __name__, url_prefix="/api/documents")

from app.blueprints.documents import routes  # noqa: E402,F401
