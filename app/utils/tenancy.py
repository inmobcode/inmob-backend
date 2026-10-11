from functools import wraps

from flask import jsonify
from flask_jwt_extended import get_jwt, verify_jwt_in_request


def current_agency_id() -> str:
    """Agency id for the authenticated request, read from the JWT claims.

    Every query in a blueprint must filter by this id instead of trusting
    any agency_id that arrives in the request body/query string.
    """
    verify_jwt_in_request()
    return get_jwt()["agency_id"]


def require_role(*allowed_roles: str):
    """Restrict a route to users whose JWT role claim is in allowed_roles."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            role = get_jwt().get("role")
            if role not in allowed_roles:
                return jsonify({"message": "Forbidden"}), 403
            return fn(*args, **kwargs)

        return wrapper

    return decorator
