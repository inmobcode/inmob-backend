"""The numbers behind the dashboard's home screen, limited to what the viewer can see."""
from datetime import date, timedelta

from sqlalchemy import func

from app.extensions import db
from app.models import Booking, Client, Inquiry, Offer, Payment
from app.models.client import CLIENT_STAGES
from app.services import crm_service, inquiry_service, task_service
from app.utils.tenancy import agent_scope

WINDOW_DAYS = 14


def _iso(value) -> str | None:
    return value.isoformat() + "Z" if value else None


def _bookings(agency_id: str):
    query = Booking.query.filter_by(agency_id=agency_id, deleted_at=None)
    scope = agent_scope()
    return query.filter(Booking.created_by == scope) if scope else query


def _offers(agency_id: str):
    query = Offer.query.filter_by(agency_id=agency_id, deleted_at=None, is_template=False)
    scope = agent_scope()
    return query.filter(Offer.created_by == scope) if scope else query


def summary(agency_id: str, user_id: str) -> dict:
    today = date.today()
    horizon = today + timedelta(days=WINDOW_DAYS)

    # Inquiries
    inquiries = inquiry_service.inbox(agency_id)
    unread = inquiries.filter(Inquiry.read_at.is_(None)).count()
    recent = inquiries.order_by(Inquiry.created_at.desc()).limit(5).all()

    # Offers
    offer_counts = dict(
        _offers(agency_id)
        .with_entities(Offer.status, func.count(Offer.id))
        .group_by(Offer.status)
        .all()
    )

    # Bookings
    live = _bookings(agency_id).filter(Booking.status.in_(("PENDING", "CONFIRMED")))
    upcoming = (
        live.filter(Booking.start_date >= today, Booking.start_date <= horizon)
        .order_by(Booking.start_date)
        .limit(6)
        .all()
    )
    pending_bookings = live.filter(Booking.status == "PENDING").count()

    # Money still to collect, per currency
    booking_ids = [row.id for row in live.with_entities(Booking.id).all()]
    pending_payments: dict[str, float] = {}
    pending_count = 0
    if booking_ids:
        rows = (
            db.session.query(Payment.currency, func.sum(Payment.amount), func.count(Payment.id))
            .filter(Payment.booking_id.in_(booking_ids), Payment.status == "PENDING")
            .group_by(Payment.currency)
            .all()
        )
        for currency, total, count in rows:
            pending_payments[currency] = float(total or 0)
            pending_count += count

    # Funnel
    stage_counts = dict(
        crm_service.live_clients(Client.query.filter_by(agency_id=agency_id))
        .with_entities(Client.stage, func.count(Client.id))
        .group_by(Client.stage)
        .all()
    )

    # My follow-ups (what's on the viewer's plate)
    open_tasks = task_service.list_tasks(agency_id, status="open", assigned_to=user_id)
    overdue = [task for task in open_tasks if task_service.is_overdue(task)]
    names = task_service.client_names(open_tasks)

    return {
        "counts": {
            "unreadInquiries": unread,
            "offersSent": offer_counts.get("SENT", 0),
            "offersViewed": offer_counts.get("VIEWED", 0),
            "offersDraft": offer_counts.get("DRAFT", 0),
            "upcomingCheckIns": len(upcoming),
            "pendingBookings": pending_bookings,
            "pendingPayments": pending_count,
            "openTasks": len(open_tasks),
            "overdueTasks": len(overdue),
        },
        "pendingPaymentTotals": pending_payments,
        "funnel": {stage: stage_counts.get(stage, 0) for stage in CLIENT_STAGES},
        "upcomingBookings": [
            {
                "id": booking.id,
                "propertyTitle": booking.property.title if booking.property else None,
                "clientName": booking.client.name if booking.client else None,
                "startDate": booking.start_date.isoformat() if booking.start_date else None,
                "endDate": booking.end_date.isoformat() if booking.end_date else None,
                "status": booking.status,
            }
            for booking in upcoming
        ],
        "tasks": [
            {
                "id": task.id,
                "title": task.title,
                "dueDate": task.due_date.isoformat() if task.due_date else None,
                "overdue": task_service.is_overdue(task),
                "client": {"id": task.client_id, "name": names.get(task.client_id, "")} if task.client_id else None,
            }
            for task in open_tasks[:6]
        ],
        "recentInquiries": [
            {
                "id": inquiry.id,
                "name": inquiry.name,
                "message": inquiry.message,
                "createdAt": _iso(inquiry.created_at),
                "read": inquiry.read_at is not None,
            }
            for inquiry in recent
        ],
    }
