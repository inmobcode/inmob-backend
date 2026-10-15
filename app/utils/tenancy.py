from functools import wraps

from flask import jsonify
from flask_jwt_extended import get_jwt, get_jwt_identity, verify_jwt_in_request


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


def current_user_id() -> str:
    verify_jwt_in_request()
    return get_jwt_identity()


def is_member(agency_id: str, user_id: str) -> bool:
    """Whether the user can work in the agency (used before assigning something to them)."""
    from app.models import AgencyMembership

    return (
        AgencyMembership.query.filter_by(agency_id=agency_id, user_id=user_id).first() is not None
    )


def agent_scope() -> str | None:
    """The user id whose records the request is limited to, or None for no limit.

    An AGENT works only with what is theirs; owners and admins see the whole
    agency. Read from the JWT, so it can be called from services without
    threading the role through every signature. Outside a request that carries
    a token (public pages) there is no scope.
    """
    verify_jwt_in_request(optional=True)
    claims = get_jwt()
    if claims.get("role") == "AGENT":
        return get_jwt_identity()
    return None
