import secrets
from html import escape

from flask import current_app

from app.extensions import db
from app.models import Agency, AgencyMembership, User
from app.services import email_service


class TeamError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _send_invite_email(to_email: str, name: str, agency: Agency, temp_password: str) -> None:
    login_url = f"{current_app.config['FRONTEND_URL'].rstrip('/')}/login"
    email_service.send_email(
        [to_email],
        f"Te invitaron a {agency.name} en Tivvo",
        '<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;font-size:15px;'
        'line-height:1.55;color:#1b201e;max-width:560px;margin:0 auto;padding:24px">'
        f'<h1 style="font-size:20px;margin:0 0 16px">Hola {escape(name)}</h1>'
        f'<p style="margin:0 0 12px">Ya tenés acceso a <strong>{escape(agency.name)}</strong> en Tivvo.</p>'
        f'<p style="margin:0 0 12px">Email: {escape(to_email)}<br>'
        f'Contraseña temporal: <strong>{escape(temp_password)}</strong></p>'
        f'<p style="margin:24px 0 0"><a href="{login_url}" style="background:#164832;color:#fff;'
        'padding:10px 16px;border-radius:8px;text-decoration:none">Entrar</a></p>'
        '<p style="margin:16px 0 0;color:#646b67;font-size:13px">'
        "Te recomendamos cambiar la contraseña la primera vez que entres.</p>"
        "</div>",
        from_name=agency.name,
    )


def list_team(agency_id: str) -> list[tuple[User, str]]:
    memberships = (
        AgencyMembership.query.filter_by(agency_id=agency_id)
        .order_by(AgencyMembership.created_at.asc())
        .all()
    )
    return [(m.user, m.role) for m in memberships]


def _other_owners_count(agency_id: str, exclude_membership_id: str) -> int:
    return AgencyMembership.query.filter(
        AgencyMembership.agency_id == agency_id,
        AgencyMembership.role == "OWNER",
        AgencyMembership.id != exclude_membership_id,
    ).count()


def invite_member(agency_id: str, data: dict) -> tuple[User, bool]:
    """Returns (user, linked_existing) — linked_existing is True when the
    email already had an account and we just added a membership to it."""
    email = data["email"]
    role = data["role"]
    agency = db.session.get(Agency, agency_id)

    user = User.query.filter_by(email=email).first()
    if user is not None:
        if AgencyMembership.query.filter_by(user_id=user.id, agency_id=agency_id).first() is not None:
            raise TeamError("Esa persona ya es parte de tu equipo", 409)
        db.session.add(AgencyMembership(user_id=user.id, agency_id=agency_id, role=role))
        db.session.commit()
        return user, True

    temp_password = secrets.token_urlsafe(9)
    user = User(agency_id=agency_id, name=data["name"], email=email, role=role)
    user.set_password(temp_password)
    db.session.add(user)
    db.session.flush()  # assigns user.id for the membership FK below
    db.session.add(AgencyMembership(user_id=user.id, agency_id=agency_id, role=role))
    db.session.commit()

    _send_invite_email(email, data["name"], agency, temp_password)

    return user, False


def update_member(agency_id: str, user_id: str, data: dict) -> tuple[User, str]:
    membership = AgencyMembership.query.filter_by(user_id=user_id, agency_id=agency_id).first()
    if membership is None:
        raise TeamError("Not found", 404)

    if "role" in data:
        if (
            data["role"] != "OWNER"
            and membership.role == "OWNER"
            and _other_owners_count(agency_id, membership.id) == 0
        ):
            raise TeamError("La agencia necesita al menos un propietario", 400)
        membership.role = data["role"]

    user = db.session.get(User, user_id)
    if "is_active" in data:
        user.is_active = data["is_active"]

    db.session.commit()
    return user, membership.role


def remove_member(agency_id: str, user_id: str) -> None:
    membership = AgencyMembership.query.filter_by(user_id=user_id, agency_id=agency_id).first()
    if membership is None:
        raise TeamError("Not found", 404)

    if membership.role == "OWNER" and _other_owners_count(agency_id, membership.id) == 0:
        raise TeamError("No podés quitar al único propietario de la agencia", 400)

    db.session.delete(membership)
    db.session.commit()
