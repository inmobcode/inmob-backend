"""Transactional email through Resend (https://resend.com/docs/api-reference).

Sending happens on a background thread so a slow or failing provider never
delays or breaks the request that triggered it. Without RESEND_API_KEY the
email is only logged, which keeps local development and tests offline.
"""
import logging
import re
import threading

import httpx
from flask import current_app

from app import i18n

logger = logging.getLogger(__name__)

RESEND_URL = "https://api.resend.com/emails"


def _display_name(name: str, locale: str = i18n.DEFAULT_LOCALE) -> str:
    """A safe From display name: no characters that could change which address
    the header points to, no line breaks, short, and marked as sent through
    Tivvo (in the reader's language) so an agency named like a bank can't pass as one."""
    clean = re.sub(r'[<>"\\\r\n]', " ", name)
    clean = re.sub(r"\s+", " ", clean).strip()[:60].strip()
    return i18n.t(locale, "via", name=clean) if clean else "Tivvo"


def _single_line(text: str) -> str:
    return re.sub(r"[\r\n]+", " ", text).strip()


def _post(api_key: str, payload: dict) -> None:
    try:
        response = httpx.post(
            RESEND_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=10,
        )
        if response.status_code >= 400:
            logger.warning("Resend rejected email to %s: %s %s", payload["to"], response.status_code, response.text)
    except httpx.HTTPError as err:
        logger.warning("Could not reach Resend for email to %s: %s", payload["to"], err)


def send_email(
    to: list[str],
    subject: str,
    html: str,
    *,
    reply_to: str | None = None,
    from_name: str | None = None,
    locale: str = i18n.DEFAULT_LOCALE,
) -> None:
    """Queues an email. `from_name` replaces the display name of EMAIL_FROM
    (sanitized, see _display_name) so a client's confirmation shows the agency."""
    recipients = [address for address in to if address]
    if not recipients:
        return

    sender = current_app.config["EMAIL_FROM"]
    if from_name:
        address = sender.split("<")[-1].rstrip(">").strip()
        sender = f'"{_display_name(from_name, locale)}" <{address}>'

    payload = {"from": sender, "to": recipients, "subject": _single_line(subject), "html": html}
    if reply_to:
        payload["reply_to"] = reply_to

    api_key = current_app.config.get("RESEND_API_KEY")
    if not api_key:
        current_app.logger.info("Email (not sent, no RESEND_API_KEY) to %s: %s", ", ".join(recipients), subject)
        return

    threading.Thread(target=_post, args=(api_key, payload), daemon=True).start()
