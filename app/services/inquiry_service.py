"""The inquiry inbox: archive, trash, answers sent from the dashboard and the
team's reply templates. Inquiries themselves are created in crm_service.log_inquiry."""
from app import i18n
from app.extensions import db
from app.models import Agency, Client, Inquiry, Interaction, ReplyTemplate, User
from app.services import notifications
from app.services.crm_service import visible_inquiries
from app.utils import trash

MAX_TEMPLATES = 50


class InquiryError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def live_inquiries(agency_id: str):
    """The inquiries someone can see, leaving out the ones in the trash."""
    return visible_inquiries(Inquiry.query.filter_by(agency_id=agency_id)).filter(Inquiry.deleted_at.is_(None))


def inbox(agency_id: str):
    """What's waiting in the inbox: not archived, not in the trash."""
    return live_inquiries(agency_id).filter(Inquiry.archived_at.is_(None))


def get_inquiry(agency_id: str, inquiry_id: str, *, trashed: bool = False) -> Inquiry:
    query = visible_inquiries(Inquiry.query.filter_by(id=inquiry_id, agency_id=agency_id))
    query = query.filter(Inquiry.deleted_at.isnot(None) if trashed else Inquiry.deleted_at.is_(None))
    inquiry = query.first()
    if inquiry is None:
        raise InquiryError("Not found", 404)
    return inquiry


def mark(agency_id: str, inquiry_id: str, *, read: bool | None = None, archived: bool | None = None) -> Inquiry:
    inquiry = get_inquiry(agency_id, inquiry_id)
    if read is not None:
        inquiry.read_at = trash.now() if read else None
    if archived is not None:
        inquiry.archived_at = trash.now() if archived else None
    db.session.commit()
    return inquiry


def delete_inquiry(agency_id: str, inquiry_id: str) -> None:
    """Moves it to the trash. The client and the note in their history stay."""
    inquiry = get_inquiry(agency_id, inquiry_id)
    inquiry.deleted_at = trash.now()
    db.session.commit()


def list_trashed(agency_id: str):
    purge_trashed(agency_id)
    return (
        visible_inquiries(Inquiry.query.filter(Inquiry.agency_id == agency_id, Inquiry.deleted_at.isnot(None)))
        .order_by(Inquiry.deleted_at.desc())
        .all()
    )


def restore_inquiry(agency_id: str, inquiry_id: str) -> Inquiry:
    inquiry = get_inquiry(agency_id, inquiry_id, trashed=True)
    inquiry.deleted_at = None
    db.session.commit()
    return inquiry


def delete_forever(agency_id: str, inquiry_id: str) -> None:
    db.session.delete(get_inquiry(agency_id, inquiry_id, trashed=True))
    db.session.commit()


def purge_trashed(agency_id: str) -> None:
    """Deletes for good what has been in the trash longer than TRASH_DAYS."""
    Inquiry.query.filter(
        Inquiry.agency_id == agency_id,
        Inquiry.deleted_at.isnot(None),
        Inquiry.deleted_at < trash.purge_cutoff(),
    ).delete(synchronize_session=False)
    db.session.commit()


def reply(agency_id: str, inquiry_id: str, user_id: str, subject: str, body: str) -> Inquiry:
    """Emails the answer to whoever sent the inquiry, and logs it in their client's history."""
    inquiry = get_inquiry(agency_id, inquiry_id)
    agency = db.session.get(Agency, agency_id)
    user = db.session.get(User, user_id)
    client = db.session.get(Client, inquiry.client_id) if inquiry.client_id else None
    if client is not None and client.deleted_at is not None:
        client = None

    notifications.send_inquiry_reply(inquiry, agency, client, user, subject, body)

    now = trash.now()
    inquiry.replied_at = now
    inquiry.replied_by = user_id
    inquiry.read_at = inquiry.read_at or now
    if client is not None:
        label = i18n.t(notifications.staff_locale(agency), "note.reply", subject=subject)
        db.session.add(Interaction(client_id=client.id, created_by=user_id, type="EMAIL", content=f"{label}\n\n{body}"))
    db.session.commit()
    return inquiry


def list_templates(agency_id: str):
    return ReplyTemplate.query.filter_by(agency_id=agency_id).order_by(ReplyTemplate.name).all()


def _get_template(agency_id: str, template_id: str) -> ReplyTemplate:
    template = ReplyTemplate.query.filter_by(id=template_id, agency_id=agency_id).first()
    if template is None:
        raise InquiryError("Not found", 404)
    return template


def create_template(agency_id: str, user_id: str, data: dict) -> ReplyTemplate:
    if ReplyTemplate.query.filter_by(agency_id=agency_id).count() >= MAX_TEMPLATES:
        raise InquiryError("Too many reply templates", 400)
    template = ReplyTemplate(agency_id=agency_id, created_by=user_id, **data)
    db.session.add(template)
    db.session.commit()
    return template


def update_template(agency_id: str, template_id: str, data: dict) -> ReplyTemplate:
    template = _get_template(agency_id, template_id)
    for field, value in data.items():
        setattr(template, field, value)
    db.session.commit()
    return template


def delete_template(agency_id: str, template_id: str) -> None:
    db.session.delete(_get_template(agency_id, template_id))
    db.session.commit()
