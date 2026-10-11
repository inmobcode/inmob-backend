from flask import current_app

from app.models import Inquiry


def notify_new_inquiry(inquiry: Inquiry) -> None:
    """Placeholder for the real notification channel (email/Slack/etc).

    Swap this for an actual provider (e.g. SES, Postmark) when the agency
    needs to actually be notified; logging is enough to prove the dual-write
    path (Client + Interaction + Inquiry) fires correctly for now.
    """
    current_app.logger.info(
        "New inquiry for agency %s: %s <%s> — %s",
        inquiry.agency_id,
        inquiry.name,
        inquiry.email,
        inquiry.message or "(no message)",
    )
