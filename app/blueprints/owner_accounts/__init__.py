from flask import Blueprint

bp = Blueprint("owner_accounts", __name__, url_prefix="/api/owner-accounts")

from app.blueprints.owner_accounts import routes  # noqa: E402,F401
