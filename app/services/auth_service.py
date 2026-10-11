from flask_jwt_extended import create_access_token, create_refresh_token

from app.extensions import db
from app.models import Agency, User
from app.utils.slugify import slugify


class AuthError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _unique_slug(name: str) -> str:
    base = slugify(name) or "agencia"
    slug = base
    suffix = 1
    while Agency.query.filter_by(slug=slug).first() is not None:
        suffix += 1
        slug = f"{base}-{suffix}"
    return slug


def _claims_for(user: User) -> dict:
    return {
        "agency_id": user.agency_id,
        "role": user.role,
        "name": user.name,
        "email": user.email,
    }


def _tokens_for(user: User) -> dict:
    claims = _claims_for(user)
    return {
        "access_token": create_access_token(identity=user.id, additional_claims=claims),
        "refresh_token": create_refresh_token(identity=user.id, additional_claims=claims),
    }


def register_agency(data: dict) -> dict:
    if User.query.filter_by(email=data["email"]).first() is not None:
        raise AuthError("Email already in use", 409)

    agency = Agency(
        name=data["agency_name"],
        slug=_unique_slug(data["agency_name"]),
        contact_email=data["email"],
    )
    db.session.add(agency)
    db.session.flush()  # assigns agency.id for the FK below

    user = User(agency_id=agency.id, name=data["name"], email=data["email"], role="OWNER")
    user.set_password(data["password"])
    db.session.add(user)
    db.session.commit()

    return {"user": user, **_tokens_for(user)}


def authenticate(email: str, password: str) -> dict:
    user = User.query.filter_by(email=email).first()
    if user is None or not user.is_active or not user.check_password(password):
        raise AuthError("Invalid credentials", 401)

    return {"user": user, **_tokens_for(user)}
