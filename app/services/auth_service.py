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
from app.services import billing_service, email_service
from app.utils.slugify import slugify

# Password recovery: how long an emailed code works, how many wrong tries it
# takes before it's burned, and how soon another one can be asked for.
RESET_CODE_MINUTES = 15
RESET_CODE_MAX_ATTEMPTS = 5
RESET_CODE_RESEND_SECONDS = 60

# Email verification at sign-up works the same way, with a longer window since
# people open the email after the sign-up form, not in the middle of it.
VERIFY_CODE_MINUTES = 30
VERIFY_CODE_MAX_ATTEMPTS = 5
VERIFY_CODE_RESEND_SECONDS = 60


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
    user = User.query.filter_by(email=data["email"]).first()
    if user is not None and user.email_verified:
        raise AuthError("Email already in use", 409)

    if user is not None:
        # Someone signed up with this email and never confirmed it. They can't have done
        # anything with the account, so signing up again just starts it over; otherwise
        # whoever typed the email first could lock its owner out. The code goes to the
        # inbox, so whoever isn't its owner can't finish either way.
        agency = db.session.get(Agency, user.agency_id)
        agency.name = data["agency_name"]
        agency.plan = data["plan"]
        user.name = data["name"]
        user.set_password(data["password"])
        db.session.commit()
    else:
        agency = Agency(
            name=data["agency_name"],
            slug=_unique_slug(data["agency_name"]),
            contact_email=data["email"],
            plan=data["plan"],
        )
        # With billing on the agency waits (locked out) for the card; without it, access starts now.
        if not billing_service.enabled():
            billing_service.start_without_billing(agency)
        db.session.add(agency)
        db.session.flush()  # assigns agency.id for the FKs below

        user = User(agency_id=agency.id, name=data["name"], email=data["email"], role="OWNER")
        user.set_password(data["password"])
        db.session.add(user)
        db.session.flush()

        db.session.add(AgencyMembership(user_id=user.id, agency_id=agency.id, role="OWNER"))
        db.session.commit()

    _issue_verification_code(user)
    return {"user": user, "agency": agency}


def authenticate(email: str, password: str) -> dict:
    user = User.query.filter_by(email=email).first()
    if user is None or not user.is_active or not user.check_password(password):
        raise AuthError("Invalid credentials", 401)
    # Only said once the password is right, so it doesn't tell strangers which emails are signed up.
    if not user.email_verified:
        raise AuthError("Email not verified", 403)

    membership = _active_membership(user)
    agency = db.session.get(Agency, membership.agency_id)
    return {"user": user, "agency": agency, **_tokens_for(user, agency)}


def _utcnow() -> datetime:
    # Naive UTC, as SQLite hands DateTime columns back.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _code_email_html(
    locale: str, kind: str, name: str, code: str, minutes: int, url: str, logo_url: str
) -> str:
    """Table layout with inline styles: the only thing mail clients render alike."""
    font = "-apple-system,'Segoe UI',Helvetica,Arial,sans-serif"
    mono = "SFMono-Regular,Menlo,Consolas,monospace"
    return (
        f'<div style="margin:0;padding:32px 16px;background:#eef1ea;font-family:{font};color:#1b201e">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="max-width:520px;margin:0 auto;border-collapse:separate">'
        # Header band in the brand forest, with the logo (a PNG: mail clients drop inline SVG).
        '<tr><td style="background:#164832;border-radius:16px 16px 0 0;padding:28px 32px">'
        f'<img src="{escape(logo_url)}" alt="" width="28" height="23" style="display:inline-block;'
        'vertical-align:middle;margin-right:10px;border:0">'
        '<span style="vertical-align:middle;font-size:22px;font-weight:700;letter-spacing:-0.5px;color:#ffffff">Tivvu</span>'
        "</td></tr>"
        '<tr><td style="background:#ffffff;border-radius:0 0 16px 16px;padding:36px 32px 32px">'
        f'<h1 style="margin:0 0 12px;font-size:24px;line-height:1.2;letter-spacing:-0.5px">'
        f'{escape(i18n.t(locale, f"{kind}.hello", name=name))}</h1>'
        f'<p style="margin:0 0 28px;font-size:15px;line-height:1.55;color:#4a524e">'
        f'{escape(i18n.t(locale, f"{kind}.lead"))}</p>'
        # One element, not a box per digit, so a double click selects the whole code.
        '<p style="margin:0 0 12px;padding:20px 8px;background:#f1f5ec;border:1px solid #dbe3d2;'
        'border-radius:12px;text-align:center;font-size:36px;font-weight:700;letter-spacing:12px;'
        f'text-indent:12px;font-family:{mono};color:#0f3524">{code}</p>'
        f'<p style="margin:0 0 32px;text-align:center;font-size:13px;color:#646b67">'
        f'{escape(i18n.t(locale, f"{kind}.expires", minutes=minutes))}</p>'
        '<table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 auto"><tr>'
        '<td style="background:#164832;border-radius:10px">'
        f'<a href="{escape(url)}" style="display:inline-block;padding:14px 28px;font-size:15px;'
        f'font-weight:600;color:#ffffff;text-decoration:none">{escape(i18n.t(locale, f"{kind}.open"))}</a>'
        "</td></tr></table>"
        '<hr style="margin:32px 0 20px;border:0;border-top:1px solid #e4e8df">'
        f'<p style="margin:0;font-size:13px;line-height:1.5;color:#646b67">'
        f'{escape(i18n.t(locale, f"{kind}.ignore"))}</p>'
        "</td></tr></table></div>"
    )


def _send_code_email(
    user: User, code: str, locale: str, *, kind: str, minutes: int, path: str
) -> None:
    """The email with a 6-digit code and a button to the page where it's typed.
    `kind` picks the strings ("reset" or "verify" in app/i18n/messages.py)."""
    base = current_app.config["FRONTEND_URL"].rstrip("/")
    query = urlencode({"email": user.email, "lang": locale})
    email_service.send_email(
        [user.email],
        i18n.t(locale, f"{kind}.subject", code=code),
        _code_email_html(
            locale, kind, user.name, code, minutes, f"{base}{path}?{query}", f"{base}/email/logo.png"
        ),
        locale=locale,
    )


def _send_reset_email(user: User, code: str, locale: str) -> None:
    _send_code_email(user, code, locale, kind="reset", minutes=RESET_CODE_MINUTES, path="/reset-password")


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

    _send_reset_email(user, code, _email_locale(user))


def _clear_reset_code(user: User) -> None:
    user.reset_code_hash = None
    user.reset_code_expires_at = None
    user.reset_code_attempts = 0


def _check_reset_code(email: str, code: str) -> User:
    """Returns the user if the code is right. Wrong tries count, in either step."""
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
    return user


def verify_reset_code(email: str, code: str) -> None:
    """Lets the form tell a wrong code before asking for the new password. Keeps the code."""
    _check_reset_code(email, code)


def reset_password(email: str, code: str, password: str) -> None:
    user = _check_reset_code(email, code)
    # After the code check, so the answer never tells a stranger what the password is.
    # It still says whether a guess is the current password, so each one costs a try
    # of the code: whoever holds it can't sit there probing the old password.
    if user.check_password(password):
        user.reset_code_attempts += 1
        if user.reset_code_attempts >= RESET_CODE_MAX_ATTEMPTS:
            _clear_reset_code(user)
        db.session.commit()
        raise AuthError("New password must differ from the current one", 409)
    user.set_password(password)
    # The code came to their inbox, which is what verifying the email proves.
    user.email_verified = True
    _clear_verify_code(user)
    _clear_reset_code(user)
    db.session.commit()


def _email_locale(user: User) -> str:
    # The language of the page they asked from, else the one they use the dashboard in.
    return i18n.pick(i18n.request_locale(), user.locale)


def _issue_verification_code(user: User) -> None:
    """Emails a fresh verification code, unless one went out a moment ago."""
    now = _utcnow()
    if user.verify_code_expires_at is not None:
        sent_at = user.verify_code_expires_at - timedelta(minutes=VERIFY_CODE_MINUTES)
        if now - sent_at < timedelta(seconds=VERIFY_CODE_RESEND_SECONDS):
            return  # don't let the form flood their inbox

    code = f"{secrets.randbelow(10**6):06d}"
    user.verify_code_hash = generate_password_hash(code)
    user.verify_code_expires_at = now + timedelta(minutes=VERIFY_CODE_MINUTES)
    user.verify_code_attempts = 0
    db.session.commit()

    _send_code_email(
        user, code, _email_locale(user), kind="verify", minutes=VERIFY_CODE_MINUTES, path="/verify-email"
    )


def resend_verification_code(email: str) -> None:
    """Says nothing either way about whether the account exists or is already verified."""
    user = User.query.filter_by(email=email).first()
    if user is None or not user.is_active or user.email_verified:
        return
    _issue_verification_code(user)


def _clear_verify_code(user: User) -> None:
    user.verify_code_hash = None
    user.verify_code_expires_at = None
    user.verify_code_attempts = 0


def verify_email(email: str, code: str) -> dict:
    """The emailed code proves the email is theirs and opens the session."""
    invalid = AuthError("Invalid or expired code", 400)
    user = User.query.filter_by(email=email).first()
    if (
        user is None
        or not user.is_active
        or user.email_verified
        or user.verify_code_hash is None
        or user.verify_code_expires_at is None
        or user.verify_code_expires_at < _utcnow()
    ):
        raise invalid

    if not check_password_hash(user.verify_code_hash, code):
        user.verify_code_attempts += 1
        # Six digits are a million options: a handful of tries, then ask for a new one.
        if user.verify_code_attempts >= VERIFY_CODE_MAX_ATTEMPTS:
            _clear_verify_code(user)
        db.session.commit()
        raise invalid

    user.email_verified = True
    _clear_verify_code(user)
    db.session.commit()

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
