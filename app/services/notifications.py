from html import escape

from flask import current_app

from app.extensions import db
from app.models import Agency, Inquiry, Property, User
from app.services import email_service


def _agency_recipients(agency: Agency) -> list[str]:
    """The agency's contact email if it set one, otherwise its owners and admins."""
    if agency.contact_email:
        return [agency.contact_email]
    users = User.query.filter(
        User.agency_id == agency.id,
        User.role.in_(("OWNER", "ADMIN")),
        User.is_active.is_(True),
    ).all()
    return [user.email for user in users]


def _paragraphs(text: str) -> str:
    return "".join(f"<p style=\"margin:0 0 12px\">{escape(line)}</p>" for line in text.splitlines() if line.strip())


def _layout(body: str) -> str:
    return (
        '<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;font-size:15px;'
        'line-height:1.55;color:#1b201e;max-width:560px;margin:0 auto;padding:24px">'
        f"{body}</div>"
    )


def notify_new_inquiry(inquiry: Inquiry) -> None:
    """Tells the agency a question arrived, and tells the person it was received.

    Both go out through email_service, which only logs them when no email
    provider is configured.
    """
    agency = db.session.get(Agency, inquiry.agency_id)
    if agency is None:
        return
    prop = db.session.get(Property, inquiry.property_id) if inquiry.property_id else None
    about = f"«{prop.title}»" if prop else "tu inmobiliaria"
    current_app.logger.info("New inquiry for agency %s: %s <%s> about %s", agency.id, inquiry.name, inquiry.email, about)

    inbox_url = f"{current_app.config['FRONTEND_URL'].rstrip('/')}/inquiries"
    details = [
        ("Nombre", inquiry.name),
        ("Email", inquiry.email),
        ("Teléfono", inquiry.phone),
        ("Propiedad", prop.title if prop else None),
    ]
    rows = "".join(
        f'<tr><td style="padding:4px 16px 4px 0;color:#646b67">{label}</td><td style="padding:4px 0">{escape(value)}</td></tr>'
        for label, value in details
        if value
    )
    message = _paragraphs(inquiry.message) if inquiry.message else '<p style="color:#646b67">Sin mensaje.</p>'
    email_service.send_email(
        _agency_recipients(agency),
        f"Nueva consulta de {inquiry.name}" + (f" por {prop.title}" if prop else ""),
        _layout(
            f'<h1 style="font-size:20px;margin:0 0 16px">Nueva consulta por {escape(about)}</h1>'
            f'<table style="border-collapse:collapse;margin:0 0 16px">{rows}</table>'
            f"{message}"
            f'<p style="margin:24px 0 0"><a href="{inbox_url}" style="background:#164832;color:#fff;'
            f'padding:10px 16px;border-radius:8px;text-decoration:none">Ver en Consultas</a></p>'
            '<p style="margin:16px 0 0;color:#646b67;font-size:13px">Respondé este email para escribirle directamente.</p>'
        ),
        reply_to=inquiry.email,
    )

    email_service.send_email(
        [inquiry.email],
        f"Recibimos tu consulta" + (f" por {prop.title}" if prop else ""),
        _layout(
            f'<h1 style="font-size:20px;margin:0 0 16px">Hola, {escape(inquiry.name)}</h1>'
            f"<p style=\"margin:0 0 12px\">Recibimos tu consulta por {escape(about)}. "
            "Te vamos a responder por email o por teléfono a la brevedad.</p>"
            + (f'<p style="margin:16px 0 4px;color:#646b67">Tu mensaje:</p>{_paragraphs(inquiry.message)}' if inquiry.message else "")
            + f'<p style="margin:24px 0 0">{escape(agency.name)}</p>'
        ),
        reply_to=agency.contact_email,
        from_name=agency.name,
    )
