import secrets
from datetime import datetime, timedelta, timezone
from html import escape
from urllib.parse import urlencode

from flask import current_app
from flask_jwt_extended import create_access_token, create_refresh_token
from werkzeug.security import check_password_hash, generate_password_hash

from app import i18n
from app.extensions import db
from app.models import Agency, AgencyMembership, User
from app.services import email_service
from app.utils.slugify import slugify

# Password recovery: how long an emailed code works, how many wrong tries it
# takes before it's burned, and how soon another one can be asked for.
RESET_CODE_MINUTES = 15
RESET_CODE_MAX_ATTEMPTS = 5
RESET_CODE_RESEND_SECONDS = 60


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


def _utcnow() -> datetime:
    # Naive UTC, as SQLite hands DateTime columns back.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _send_reset_email(user: User, code: str, locale: str) -> None:
    query = urlencode({"email": user.email, "lang": locale})
    reset_url = f"{current_app.config['FRONTEND_URL'].rstrip('/')}/reset-password?{query}"
    email_service.send_email(
        [user.email],
        i18n.t(locale, "reset.subject", code=code),
        '<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;font-size:15px;'
        'line-height:1.55;color:#1b201e;max-width:560px;margin:0 auto;padding:24px">'
        f'<h1 style="font-size:20px;margin:0 0 16px">{escape(i18n.t(locale, "reset.hello", name=user.name))}</h1>'
        f'<p style="margin:0 0 12px">{escape(i18n.t(locale, "reset.lead"))}</p>'
        '<p style="margin:16px 0;font-size:32px;font-weight:600;letter-spacing:8px;'
        f'font-family:SFMono-Regular,Menlo,Consolas,monospace">{code}</p>'
        f'<p style="margin:0 0 12px">{escape(i18n.t(locale, "reset.expires", minutes=RESET_CODE_MINUTES))}</p>'
        f'<p style="margin:24px 0 0"><a href="{escape(reset_url)}" style="background:#164832;color:#fff;'
        f'padding:10px 16px;border-radius:8px;text-decoration:none">{escape(i18n.t(locale, "reset.open"))}</a></p>'
        '<p style="margin:16px 0 0;color:#646b67;font-size:13px">'
        f'{escape(i18n.t(locale, "reset.ignore"))}</p>'
        "</div>",
        locale=locale,
    )


def request_password_reset(email: str) -> None:
    """Emails a 6-digit code to reset the password. Says nothing either way about
    whether the account exists: the route answers the same for any email."""
    user = User.query.filter_by(email=email).first()
    if user is None or not user.is_active:
        return

    now = _utcnow()
    if user.reset_code_expires_at is not None:
        sent_at = user.reset_code_expires_at - timedelta(minutes=RESET_CODE_MINUTES)
        if now - sent_at < timedelta(seconds=RESET_CODE_RESEND_SECONDS):
            return  # one was just sent: don't let the form flood their inbox

    code = f"{secrets.randbelow(10**6):06d}"
    user.reset_code_hash = generate_password_hash(code)
    user.reset_code_expires_at = now + timedelta(minutes=RESET_CODE_MINUTES)
    user.reset_code_attempts = 0
    db.session.commit()

    # The language of the page they asked from, else the one they use the dashboard in.
    _send_reset_email(user, code, i18n.pick(i18n.request_locale(), user.locale))


def _clear_reset_code(user: User) -> None:
    user.reset_code_hash = None
    user.reset_code_expires_at = None
    user.reset_code_attempts = 0


def reset_password(email: str, code: str, password: str) -> None:
    invalid = AuthError("Invalid or expired code", 400)
    user = User.query.filter_by(email=email).first()
    if (
        user is None
        or not user.is_active
        or user.reset_code_hash is None
        or user.reset_code_expires_at is None
        or user.reset_code_expires_at < _utcnow()
    ):
        raise invalid

    if not check_password_hash(user.reset_code_hash, code):
        user.reset_code_attempts += 1
        # Six digits are a million options: a handful of tries, then ask for a new one.
        if user.reset_code_attempts >= RESET_CODE_MAX_ATTEMPTS:
            _clear_reset_code(user)
        db.session.commit()
        raise invalid

    user.set_password(password)
    _clear_reset_code(user)
    db.session.commit()


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
