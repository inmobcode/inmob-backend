"""In-app notifications: the bell in the dashboard.

Separate from services/notifications.py, which sends emails. Each event writes
one row per person who should hear about it, so everyone reads (and clears)
their own. A failure here is logged and swallowed: it must never undo or block
the action that caused it.
"""
from datetime import date, datetime, timezone

from flask import current_app
from sqlalchemy import func

from app import i18n
from app.extensions import db
from app.models import Agency, AgencyMembership, Client, Notification, Offer, Payment, User


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _managers(agency_id: str) -> set[str]:
    """Owners and admins of the agency."""
    rows = (
        db.session.query(AgencyMembership.user_id)
        .join(User, User.id == AgencyMembership.user_id)
        .filter(
            AgencyMembership.agency_id == agency_id,
            AgencyMembership.role.in_(("OWNER", "ADMIN")),
            User.is_active.is_(True),
        )
        .all()
    )
    return {row[0] for row in rows}


def render(kind: str, params: dict, locale: str) -> tuple[str, str | None]:
    """Title and body of a notification in `locale`. The dashboard renders the
    same thing from `params` with its own messages; this is the written copy."""
    if kind == "INQUIRY":
        return i18n.t(locale, "notif.inquiry", name=params["name"]), params.get("message") or i18n.t(
            locale, "notif.inquiry_no_message"
        )
    if kind == "OFFER_VIEWED":
        title = (
            i18n.t(locale, "notif.offer_viewed", who=params["who"])
            if params.get("who")
            else i18n.t(locale, "notif.offer_viewed_anon")
        )
        return title, params.get("offer")
    if kind == "PAYMENT":
        return i18n.t(locale, "notif.payment", amount=params["amount"]), params.get("property")
    if kind == "TASK":
        due = params.get("due")
        body = (
            i18n.t(locale, "notif.task_due", title=params["title"], date=i18n.short_date(locale, date.fromisoformat(due)))
            if due
            else params["title"]
        )
        return i18n.t(locale, "notif.task"), body
    if kind == "CLIENT":
        return i18n.t(locale, "notif.client"), params["name"]
    if kind == "REVIEW":
        return i18n.t(locale, "notif.review", name=params["name"], rating=params["rating"]), params.get("text")
    raise ValueError(kind)


def notify(
    agency_id: str,
    kind: str,
    params: dict,
    *,
    link: str | None = None,
    user_ids: set[str],
    skip: str | None = None,
) -> None:
    """Writes the notification for each user (except `skip`, who did the thing
    themselves), with its title in that user's language."""
    recipients = {user_id for user_id in user_ids if user_id and user_id != skip}
    if not recipients:
        return
    try:
        now = _now()
        agency = db.session.get(Agency, agency_id)
        readers = {user.id: user for user in User.query.filter(User.id.in_(recipients)).all()}
        for user_id in recipients:
            reader = readers.get(user_id)
            title, body = render(kind, params, i18n.pick(reader.locale if reader else None, agency.locale if agency else None))
            db.session.add(
                Notification(
                    agency_id=agency_id,
                    user_id=user_id,
                    type=kind,
                    title=title[:200],
                    body=body[:500] if body else None,
                    params=params,
                    link=link,
                    created_at=now,
                )
            )
        db.session.commit()
    except Exception:  # noqa: BLE001 - never break the caller over a bell
        db.session.rollback()
        current_app.logger.exception("Could not write in-app notification %s", kind)


def notify_inquiry(inquiry, client: Client | None) -> None:
    people = _managers(inquiry.agency_id)
    if client is not None and client.assigned_agent_id:
        people.add(client.assigned_agent_id)
    notify(
        inquiry.agency_id,
        "INQUIRY",
        {"name": inquiry.name, "message": (inquiry.message or "")[:500] or None},
        link="/inquiries",
        user_ids=people,
    )


def notify_offer_viewed(offer: Offer) -> None:
    notify(
        offer.agency_id,
        "OFFER_VIEWED",
        {"who": offer.client_name or None, "offer": offer.title},
        link=f"/offers/{offer.id}",
        user_ids=_managers(offer.agency_id) | {offer.created_by},
    )


def notify_payment(booking, payment: Payment) -> None:
    notify(
        booking.agency_id,
        "PAYMENT",
        {
            "amount": f"{payment.amount:g} {payment.currency}",
            "property": booking.property.title if booking.property else None,
        },
        link=f"/bookings/{booking.id}",
        user_ids=_managers(booking.agency_id) | {booking.created_by},
    )


def notify_task_assigned(task, by_user_id: str | None) -> None:
    notify(
        task.agency_id,
        "TASK",
        {"title": task.title, "due": task.due_date.isoformat() if task.due_date else None},
        link="/clients" if not task.client_id else f"/clients/{task.client_id}",
        user_ids={task.assigned_agent_id} if task.assigned_agent_id else set(),
        skip=by_user_id,
    )


def notify_client_assigned(client: Client, by_user_id: str | None) -> None:
    notify(
        client.agency_id,
        "CLIENT",
        {"name": client.name},
        link=f"/clients/{client.id}",
        user_ids={client.assigned_agent_id} if client.assigned_agent_id else set(),
        skip=by_user_id,
    )


def notify_review(review) -> None:
    """A guest left a review: whoever can publish it (owners and admins) hears about it."""
    notify(
        review.agency_id,
        "REVIEW",
        {"name": review.author_name, "rating": review.rating, "text": (review.text or "")[:500] or None},
        link="/reviews",
        user_ids=_managers(review.agency_id),
    )


def list_for_user(user_id: str, agency_id: str, *, limit: int = 30) -> list[Notification]:
    return (
        Notification.query.filter_by(user_id=user_id, agency_id=agency_id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .all()
    )


def unread_count(user_id: str, agency_id: str) -> int:
    return (
        db.session.query(func.count(Notification.id))
        .filter(
            Notification.user_id == user_id,
            Notification.agency_id == agency_id,
            Notification.read_at.is_(None),
        )
        .scalar()
    )


def mark_read(user_id: str, agency_id: str, notification_id: str, read: bool) -> Notification | None:
    notification = Notification.query.filter_by(id=notification_id, user_id=user_id, agency_id=agency_id).first()
    if notification is None:
        return None
    notification.read_at = _now() if read else None
    db.session.commit()
    return notification


def mark_all_read(user_id: str, agency_id: str) -> int:
    updated = (
        Notification.query.filter_by(user_id=user_id, agency_id=agency_id)
        .filter(Notification.read_at.is_(None))
        .update({Notification.read_at: _now()}, synchronize_session=False)
    )
    db.session.commit()
    return updated


def delete(user_id: str, agency_id: str, notification_id: str) -> bool:
    """Removes one of the user's own notifications; False if it isn't theirs or doesn't exist."""
    notification = Notification.query.filter_by(id=notification_id, user_id=user_id, agency_id=agency_id).first()
    if notification is None:
        return False
    db.session.delete(notification)
    db.session.commit()
    return True
