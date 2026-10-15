"""In-app notifications: the bell in the dashboard.

Separate from services/notifications.py, which sends emails. Each event writes
one row per person who should hear about it, so everyone reads (and clears)
their own. A failure here is logged and swallowed: it must never undo or block
the action that caused it.
"""
from datetime import datetime, timezone

from flask import current_app
from sqlalchemy import func

from app.extensions import db
from app.models import AgencyMembership, Client, Notification, Offer, Payment, User


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


def notify(
    agency_id: str,
    kind: str,
    title: str,
    *,
    body: str | None = None,
    link: str | None = None,
    user_ids: set[str],
    skip: str | None = None,
) -> None:
    """Writes the notification for each user (except `skip`, who did the thing themselves)."""
    recipients = {user_id for user_id in user_ids if user_id and user_id != skip}
    if not recipients:
        return
    try:
        now = _now()
        for user_id in recipients:
            db.session.add(
                Notification(
                    agency_id=agency_id,
                    user_id=user_id,
                    type=kind,
                    title=title[:200],
                    body=body[:500] if body else None,
                    link=link,
                    created_at=now,
                )
            )
        db.session.commit()
    except Exception:  # noqa: BLE001 - never break the caller over a bell
        db.session.rollback()
        current_app.logger.exception("Could not write in-app notification %s", kind)


def notify_inquiry(inquiry, client: Client | None) -> None:
    about = inquiry.message or "Dejó sus datos de contacto."
    people = _managers(inquiry.agency_id)
    if client is not None and client.assigned_agent_id:
        people.add(client.assigned_agent_id)
    notify(
        inquiry.agency_id,
        "INQUIRY",
        f"Nueva consulta de {inquiry.name}",
        body=about,
        link="/inquiries",
        user_ids=people,
    )


def notify_offer_viewed(offer: Offer) -> None:
    who = offer.client_name or "Tu cliente"
    notify(
        offer.agency_id,
        "OFFER_VIEWED",
        f"{who} abrió la oferta",
        body=offer.title,
        link=f"/offers/{offer.id}",
        user_ids=_managers(offer.agency_id) | {offer.created_by},
    )


def notify_payment(booking, payment: Payment) -> None:
    amount = f"{payment.amount:g} {payment.currency}"
    notify(
        booking.agency_id,
        "PAYMENT",
        f"Pago registrado: {amount}",
        body=booking.property.title if booking.property else None,
        link=f"/bookings/{booking.id}",
        user_ids=_managers(booking.agency_id) | {booking.created_by},
    )


def notify_task_assigned(task, by_user_id: str | None) -> None:
    due = f" · para el {task.due_date.strftime('%d/%m')}" if task.due_date else ""
    notify(
        task.agency_id,
        "TASK",
        "Te asignaron una tarea",
        body=f"{task.title}{due}",
        link="/clients" if not task.client_id else f"/clients/{task.client_id}",
        user_ids={task.assigned_agent_id} if task.assigned_agent_id else set(),
        skip=by_user_id,
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
