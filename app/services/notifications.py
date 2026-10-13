from datetime import datetime, timedelta, timezone
from html import escape

from flask import current_app
from sqlalchemy import func

from app.extensions import db
from app.models import Agency, Booking, Inquiry, Property, User
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

    # The confirmation goes to whatever address was typed in a public form, so it
    # must not become a way to email strangers: it carries none of the text the
    # sender wrote, and each address gets at most one per agency a day.
    if _confirmed_recently(inquiry):
        return
    email_service.send_email(
        [inquiry.email],
        "Recibimos tu consulta" + (f" por {prop.title}" if prop else ""),
        _layout(
            '<h1 style="font-size:20px;margin:0 0 16px">Recibimos tu consulta</h1>'
            f'<p style="margin:0 0 12px">Gracias por escribirnos sobre {escape(about)}. '
            "Te vamos a responder por email o por teléfono a la brevedad.</p>"
            f'<p style="margin:24px 0 0">{escape(agency.name)}</p>'
            '<p style="margin:16px 0 0;color:#646b67;font-size:13px">'
            "Si no hiciste esta consulta, podés ignorar este email.</p>"
        ),
        reply_to=agency.contact_email,
        from_name=agency.name,
    )


def _confirmed_recently(inquiry: Inquiry) -> bool:
    """True if this address already asked this agency something in the last day."""
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
    earlier = (
        Inquiry.query.filter(
            Inquiry.agency_id == inquiry.agency_id,
            func.lower(Inquiry.email) == inquiry.email.lower(),
            Inquiry.id != inquiry.id,
            Inquiry.created_at >= since,
        )
        .limit(1)
        .count()
    )
    return earlier > 0


MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
          "septiembre", "octubre", "noviembre", "diciembre")

# Subject, heading and first line of each email the client gets about a booking.
BOOKING_EMAILS = {
    "created": (
        "Tu reserva en {property}",
        "Recibimos tu reserva",
        "Registramos tu reserva en {property}. Te avisamos por este medio cuando esté confirmada.",
    ),
    "confirmed": (
        "Reserva confirmada: {property}",
        "Tu reserva está confirmada",
        "Confirmamos tu reserva en {property}.",
    ),
    "cancelled": (
        "Reserva cancelada: {property}",
        "Tu reserva fue cancelada",
        "Cancelamos tu reserva en {property}. Si tenés dudas, respondé este email.",
    ),
}


def _long_date(day) -> str:
    return f"{day.day} de {MONTHS[day.month - 1]} de {day.year}"


def booking_url(booking: Booking) -> str:
    return f"{current_app.config['FRONTEND_URL'].rstrip('/')}/booking/{booking.token}"


def notify_booking(booking: Booking, event: str) -> None:
    """Tells the booking's client it was created, confirmed or cancelled, with
    the link to their booking page. Without a client (or its email) nothing
    goes out."""
    client = booking.client
    if client is None or not client.email:
        return
    agency = db.session.get(Agency, booking.agency_id)
    title = booking.property.title if booking.property else "la propiedad"
    subject, heading, lead = BOOKING_EMAILS[event]

    dates = ""
    if booking.start_date and booking.end_date:
        dates = (
            '<p style="margin:0 0 12px">'
            f"Del {_long_date(booking.start_date)} al {_long_date(booking.end_date)}.</p>"
        )
    first_name = client.name.split()[0] if client.name.strip() else ""
    email_service.send_email(
        [client.email],
        subject.format(property=title),
        _layout(
            f'<h1 style="font-size:20px;margin:0 0 16px">{heading}</h1>'
            + (f'<p style="margin:0 0 12px">Hola {escape(first_name)},</p>' if first_name else "")
            + f'<p style="margin:0 0 12px">{escape(lead.format(property=title))}</p>'
            + dates
            + f'<p style="margin:24px 0 0"><a href="{booking_url(booking)}" style="background:#1b201e;color:#fff;'
            'padding:10px 16px;border-radius:8px;text-decoration:none">Ver mi reserva</a></p>'
            f'<p style="margin:24px 0 0">{escape(agency.name)}</p>'
        ),
        reply_to=agency.contact_email,
        from_name=agency.name,
    )
