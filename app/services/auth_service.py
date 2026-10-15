from flask_jwt_extended import create_access_token, create_refresh_token

from app.extensions import db
from app.models import Agency, AgencyMembership, User
from app.utils.slugify import slugify


class AuthError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _unique_slug(name: str) -> str:
    base = slugify(name) or "agency"
    slug = base
    suffix = 1
    while Agency.query.filter_by(slug=slug).first() is not None:
        suffix += 1
        slug = f"{base}-{suffix}"
    return slug


def _claims_for(user: User, agency: Agency) -> dict:
    return {
        "agency_id": agency.id,
        "agency_slug": agency.slug,
        "role": user.role,
        "name": user.name,
        "email": user.email,
    }


def _tokens_for(user: User, agency: Agency) -> dict:
    claims = _claims_for(user, agency)
    return {
        "access_token": create_access_token(identity=user.id, additional_claims=claims),
        "refresh_token": create_refresh_token(identity=user.id, additional_claims=claims),
    }


def _active_membership(user: User) -> AgencyMembership:
    """The membership that backs the next login: the user's default agency if
    they're still a member there, otherwise whichever membership comes first."""
    membership = AgencyMembership.query.filter_by(
        user_id=user.id, agency_id=user.agency_id
    ).first()
    if membership is not None:
        return membership

    membership = AgencyMembership.query.filter_by(user_id=user.id).order_by(
        AgencyMembership.created_at.asc()
    ).first()
    if membership is None:
        raise AuthError("This account isn't linked to any agency", 403)
    return membership


def register_agency(data: dict) -> dict:
    if User.query.filter_by(email=data["email"]).first() is not None:
        raise AuthError("Email already in use", 409)

    agency = Agency(
        name=data["agency_name"],
        slug=_unique_slug(data["agency_name"]),
        contact_email=data["email"],
    )
    db.session.add(agency)
    db.session.flush()  # assigns agency.id for the FKs below

    user = User(agency_id=agency.id, name=data["name"], email=data["email"], role="OWNER")
    user.set_password(data["password"])
    db.session.add(user)
    db.session.flush()

    db.session.add(AgencyMembership(user_id=user.id, agency_id=agency.id, role="OWNER"))
    db.session.commit()

    return {"user": user, "agency": agency, **_tokens_for(user, agency)}


def authenticate(email: str, password: str) -> dict:
    user = User.query.filter_by(email=email).first()
    if user is None or not user.is_active or not user.check_password(password):
        raise AuthError("Invalid credentials", 401)

    membership = _active_membership(user)
    agency = db.session.get(Agency, membership.agency_id)
    return {"user": user, "agency": agency, **_tokens_for(user, agency)}


def list_my_agencies(user_id: str) -> list[dict]:
    memberships = AgencyMembership.query.filter_by(user_id=user_id).all()
    return [
        {
            "id": m.agency.id,
            "name": m.agency.name,
            "slug": m.agency.slug,
            "logoUrl": m.agency.logo_url,
            "role": m.role,
        }
        for m in memberships
    ]


def switch_agency(user_id: str, agency_id: str) -> dict:
    membership = AgencyMembership.query.filter_by(user_id=user_id, agency_id=agency_id).first()
    if membership is None:
        raise AuthError("You don't have access to that agency", 403)

    user = db.session.get(User, user_id)
    agency = db.session.get(Agency, agency_id)

    # Remember this as the default agency for the next login.
    user.agency_id = agency.id
    user.role = membership.role
    db.session.commit()

    return {"user": user, "agency": agency, **_tokens_for(user, agency)}
