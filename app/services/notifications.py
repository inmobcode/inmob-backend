from datetime import datetime, timedelta, timezone
from html import escape

from flask import current_app
from sqlalchemy import func

from app.extensions import db
from app import i18n
from app.models import Agency, AgencyMembership, Booking, Client, Inquiry, Offer, Property, User
from app.services import email_service
from app.utils import rich_text


def staff_locale(agency: Agency) -> str:
    """The language the agency's team works in: its owner's dashboard language,
    else the site's. Used for things the whole team reads (history notes, the
    shared contact inbox)."""
    owner = (
        User.query.join(AgencyMembership, AgencyMembership.user_id == User.id)
        .filter(AgencyMembership.agency_id == agency.id, AgencyMembership.role == "OWNER", User.locale.isnot(None))
        .order_by(AgencyMembership.created_at)
        .first()
    )
    return i18n.pick(owner.locale if owner else None, agency.locale)


def client_locale(client: Client | None, agency: Agency) -> str:
    """A client reads in the language they wrote in, else the agency site's."""
    return i18n.pick(client.locale if client else None, agency.locale)


def _agency_recipients(agency: Agency) -> list[tuple[str, str]]:
    """(email, language) of who hears about the agency's inquiries: its contact
    email if it set one, otherwise its owners and admins, each in their own language."""
    if agency.contact_email:
        return [(agency.contact_email, staff_locale(agency))]
    users = User.query.filter(
        User.agency_id == agency.id,
        User.role.in_(("OWNER", "ADMIN")),
        User.is_active.is_(True),
    ).all()
    return [(user.email, i18n.pick(user.locale, agency.locale)) for user in users]


def _by_locale(recipients: list[tuple[str, str]]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for email, locale in recipients:
        groups.setdefault(locale, []).append(email)
    return groups


def _paragraphs(text: str) -> str:
    return "".join(f"<p style=\"margin:0 0 12px\">{escape(line)}</p>" for line in text.splitlines() if line.strip())


def _layout(body: str) -> str:
    return (
        '<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;font-size:15px;'
        'line-height:1.55;color:#1b201e;max-width:560px;margin:0 auto;padding:24px">'
        f"{body}</div>"
    )


def _button(url: str, label: str, color: str = "#1b201e") -> str:
    return (
        f'<p style="margin:24px 0 0"><a href="{url}" style="background:{color};color:#fff;'
        f'padding:10px 16px;border-radius:8px;text-decoration:none">{escape(label)}</a></p>'
    )


def _muted(text: str) -> str:
    return f'<p style="margin:16px 0 0;color:#646b67;font-size:13px">{escape(text)}</p>'


def public_url(locale: str, path: str) -> str:
    """A link to the public site in the reader's language (/en/booking/…; Spanish has no prefix)."""
    return f"{current_app.config['PUBLIC_SITE_URL'].rstrip('/')}{i18n.public_path(locale, path)}"


def notify_new_inquiry(inquiry: Inquiry, locale: str | None = None) -> None:
    """Tells the agency a question arrived, and tells the person it was received.

    The agency hears in each recipient's language; the person, in the one they
    wrote in (`locale`, from the public site) or the site's. Both go out through
    email_service, which only logs them when no email provider is configured.
    """
    agency = db.session.get(Agency, inquiry.agency_id)
    if agency is None:
        return
    prop = db.session.get(Property, inquiry.property_id) if inquiry.property_id else None
    current_app.logger.info(
        "New inquiry for agency %s: %s <%s> about %s",
        agency.id, inquiry.name, inquiry.email, prop.title if prop else "the agency",
    )

    inbox_url = f"{current_app.config['FRONTEND_URL'].rstrip('/')}/inquiries"
    for lang, recipients in _by_locale(_agency_recipients(agency)).items():
        details = [
            (i18n.t(lang, "alert.name"), inquiry.name),
            (i18n.t(lang, "alert.email"), inquiry.email),
            (i18n.t(lang, "alert.phone"), inquiry.phone),
            (i18n.t(lang, "alert.property"), prop.title if prop else None),
        ]
        rows = "".join(
            f'<tr><td style="padding:4px 16px 4px 0;color:#646b67">{escape(label)}</td><td style="padding:4px 0">{escape(value)}</td></tr>'
            for label, value in details
            if value
        )
        message = (
            _paragraphs(inquiry.message)
            if inquiry.message
            else f'<p style="color:#646b67">{escape(i18n.t(lang, "alert.no_message"))}</p>'
        )
        subject = (
            i18n.t(lang, "alert.subject_property", name=inquiry.name, property=prop.title)
            if prop
            else i18n.t(lang, "alert.subject", name=inquiry.name)
        )
        heading = (
            i18n.t(lang, "alert.heading_property", property=prop.title) if prop else i18n.t(lang, "alert.heading_general")
        )
        email_service.send_email(
            recipients,
            subject,
            _layout(
                f'<h1 style="font-size:20px;margin:0 0 16px">{escape(heading)}</h1>'
                f'<table style="border-collapse:collapse;margin:0 0 16px">{rows}</table>'
                f"{message}"
                + _button(inbox_url, i18n.t(lang, "alert.open"), "#164832")
                + _muted(i18n.t(lang, "alert.reply_hint"))
            ),
            reply_to=inquiry.email,
            locale=lang,
        )

    # The confirmation goes to whatever address was typed in a public form, so it
    # must not become a way to email strangers: it carries none of the text the
    # sender wrote, and each address gets at most one per agency a day.
    if _confirmed_recently(inquiry):
        return
    lang = i18n.pick(locale, agency.locale)
    email_service.send_email(
        [inquiry.email],
        i18n.t(lang, "confirm.subject_property", property=prop.title) if prop else i18n.t(lang, "confirm.subject"),
        _layout(
            f'<h1 style="font-size:20px;margin:0 0 16px">{escape(i18n.t(lang, "confirm.heading"))}</h1>'
            '<p style="margin:0 0 12px">'
            + escape(
                i18n.t(lang, "confirm.body_property", property=prop.title) if prop else i18n.t(lang, "confirm.body_general")
            )
            + "</p>"
            f'<p style="margin:24px 0 0">{escape(agency.name)}</p>'
            + _muted(i18n.t(lang, "confirm.ignore"))
        ),
        reply_to=agency.contact_email,
        from_name=agency.name,
        locale=lang,
    )


def send_inquiry_reply(
    inquiry: Inquiry, agency: Agency, client: Client | None, user: User | None, subject: str, body: str
) -> None:
    """The answer someone on the team wrote in the dashboard, from the agency's
    name. Answers go back to the agency's contact email, else to whoever wrote."""
    lang = client_locale(client, agency)
    email_service.send_email(
        [inquiry.email],
        subject,
        _layout(_paragraphs(body) + _muted(i18n.t(lang, "reply.footer", agency=agency.name))),
        reply_to=agency.contact_email or (user.email if user else None),
        from_name=agency.name,
        locale=lang,
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


def booking_url(booking: Booking, locale: str = i18n.DEFAULT_LOCALE) -> str:
    return public_url(locale, f"/booking/{booking.token}")


def notify_booking(booking: Booking, event: str) -> None:
    """Tells the booking's client it was created, confirmed or cancelled, with
    the link to their booking page, in their language. Without a client (or
    its email) nothing goes out."""
    client = booking.client
    if client is None or not client.email:
        return
    agency = db.session.get(Agency, booking.agency_id)
    lang = client_locale(client, agency)
    title = booking.property.title if booking.property else i18n.t(lang, "booking.the_property")

    dates = ""
    if booking.start_date and booking.end_date:
        dates = '<p style="margin:0 0 12px">' + escape(
            i18n.t(
                lang,
                "booking.dates",
                start=i18n.long_date(lang, booking.start_date),
                end=i18n.long_date(lang, booking.end_date),
            )
        ) + "</p>"
    first_name = client.name.split()[0] if client.name.strip() else ""
    email_service.send_email(
        [client.email],
        i18n.t(lang, f"booking.{event}.subject", property=title),
        _layout(
            f'<h1 style="font-size:20px;margin:0 0 16px">{escape(i18n.t(lang, f"booking.{event}.heading"))}</h1>'
            + (f'<p style="margin:0 0 12px">{escape(i18n.t(lang, "booking.hello", name=first_name))}</p>' if first_name else "")
            + f'<p style="margin:0 0 12px">{escape(i18n.t(lang, f"booking.{event}.lead", property=title))}</p>'
            + dates
            # Once the stay is over, the button goes straight to the review form.
            + (
                _button(f"{booking_url(booking, lang)}#review", i18n.t(lang, "booking.completed.button"))
                if event == "completed"
                else _button(booking_url(booking, lang), i18n.t(lang, "booking.view"))
            )
            + f'<p style="margin:24px 0 0">{escape(agency.name)}</p>'
        ),
        reply_to=agency.contact_email,
        from_name=agency.name,
        locale=lang,
    )


def notify_offer_sent(offer: Offer) -> None:
    """Emails the offer's CRM client the link to the offer, in their language.
    Without a linked client nothing goes out: the agency shares the link by hand."""
    client = db.session.get(Client, offer.client_id) if offer.client_id else None
    if client is None or not client.email:
        return
    agency = db.session.get(Agency, offer.agency_id)
    lang = client_locale(client, agency)
    url = public_url(lang, f"/offer/{offer.token}")
    first_name = client.name.split()[0] if client.name.strip() else ""
    # Stored already clean; sanitize also turns older plain text into paragraphs.
    welcome = rich_text.sanitize(offer.welcome_content) or ""
    email_service.send_email(
        [client.email],
        i18n.t(lang, "offer.subject", agency=agency.name, title=offer.title),
        _layout(
            f'<h1 style="font-size:20px;margin:0 0 16px">{escape(offer.title)}</h1>'
            + (f'<p style="margin:0 0 12px">{escape(i18n.t(lang, "offer.hello", name=first_name))}</p>' if first_name else "")
            + f'<p style="margin:0 0 12px">{escape(i18n.t(lang, "offer.lead", agency=agency.name))}</p>'
            + welcome
            + _button(url, i18n.t(lang, "offer.view"))
            + f'<p style="margin:24px 0 0">{escape(agency.name)}</p>'
            + _muted(i18n.t(lang, "offer.reply_hint"))
        ),
        reply_to=agency.contact_email,
        from_name=agency.name,
        locale=lang,
    )


def notify_demo_request(data: dict) -> None:
    """A prospect asked for a demo from the landing. Goes to the Tivvu team, not an agency."""
    email_service.send_email(
        current_app.config["TEAM_NOTIFICATION_EMAILS"],
        f"Pedido de demo: {data['agency']}",
        _layout(
            '<h1 style="font-size:20px;margin:0 0 16px">Pedido de demo</h1>'
            f'<p style="margin:0 0 12px"><strong>{escape(data["name"])}</strong>, de {escape(data["agency"])}</p>'
            f'<p style="margin:0 0 12px">Email: {escape(data["email"])}</p>'
            f'<p style="margin:0 0 12px">Tamaño del equipo: {escape(data["team_size"])}</p>'
        ),
        reply_to=data["email"],
    )


def notify_contact_request(data: dict) -> None:
    """Someone wrote in from the landing's help/contact page. Goes to the Tivvu team."""
    email_service.send_email(
        current_app.config["TEAM_NOTIFICATION_EMAILS"],
        f"Contacto desde Tivvu: {data['name']}",
        _layout(
            '<h1 style="font-size:20px;margin:0 0 16px">Nuevo mensaje de contacto</h1>'
            f'<p style="margin:0 0 12px"><strong>{escape(data["name"])}</strong> — {escape(data["email"])}</p>'
            + _paragraphs(data["message"])
        ),
        reply_to=data["email"],
    )
