"""Guest reviews: left from a completed booking's page, moderated by the
agency, and shown on its site (each property's page and the reviews block)."""
from collections import defaultdict

from sqlalchemy import func

from app.extensions import db
from app.models import Booking, Property, Review
from app.services import feed


class ReviewError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _guest_name(full_name: str | None) -> str:
    """"Lucía Fernández" -> "Lucía F.": enough to be real, not enough to be found."""
    parts = (full_name or "").split()
    if not parts:
        return ""
    return parts[0] if len(parts) == 1 else f"{parts[0]} {parts[-1][0]}."


def booking_review(booking: Booking) -> Review | None:
    return Review.query.filter_by(booking_id=booking.id).first()


def submit_guest_review(booking: Booking, data: dict) -> Review:
    """Only after the stay (a COMPLETED booking), and once per booking.
    It waits as PENDING until someone at the agency publishes it."""
    if booking.status != "COMPLETED":
        raise ReviewError("Reviews open once the stay is over", 400)
    if booking_review(booking) is not None:
        raise ReviewError("This booking already has a review", 409)
    name = (data.get("author_name") or "").strip() or _guest_name(booking.client.name if booking.client else None)
    review = Review(
        agency_id=booking.agency_id,
        property_id=booking.property_id,
        booking_id=booking.id,
        author_name=name or "—",
        rating=data["rating"],
        text=(data.get("text") or "").strip() or None,
        stayed_on=booking.start_date or booking.created_at.date(),
        status="PENDING",
        source="GUEST",
    )
    db.session.add(review)
    db.session.commit()
    feed.notify_review(review)
    return review


def list_reviews(agency_id: str, status: str | None = None) -> list[Review]:
    query = Review.query.filter_by(agency_id=agency_id)
    if status:
        query = query.filter_by(status=status)
    return query.order_by(Review.created_at.desc()).all()


def _get(agency_id: str, review_id: str) -> Review:
    review = Review.query.filter_by(id=review_id, agency_id=agency_id).first()
    if review is None:
        raise ReviewError("Not found", 404)
    return review


def _check_property(agency_id: str, property_id: str | None) -> None:
    if property_id and Property.query.filter_by(id=property_id, agency_id=agency_id).first() is None:
        raise ReviewError("Property not found", 404)


def create_review(agency_id: str, data: dict) -> Review:
    """A review the agency types in (one it got elsewhere); published unless said otherwise."""
    _check_property(agency_id, data.get("property_id"))
    review = Review(agency_id=agency_id, source="MANUAL", status=data.pop("status", "PUBLISHED"), **data)
    db.session.add(review)
    db.session.commit()
    return review


# What the guest wrote is theirs: the agency publishes or hides it, but doesn't rewrite it.
GUEST_EDITABLE = {"status", "property_id"}


def update_review(agency_id: str, review_id: str, data: dict) -> Review:
    review = _get(agency_id, review_id)
    if review.source == "GUEST" and set(data) - GUEST_EDITABLE:
        raise ReviewError("A guest's review can't be edited", 400)
    if "property_id" in data:
        _check_property(agency_id, data["property_id"])
    for field, value in data.items():
        setattr(review, field, value)
    db.session.commit()
    return review


def delete_review(agency_id: str, review_id: str) -> None:
    db.session.delete(_get(agency_id, review_id))
    db.session.commit()


def public_review(review: Review) -> dict:
    return {
        "id": review.id,
        "authorName": review.author_name,
        "rating": review.rating,
        "text": review.text,
        "stayedOn": review.stayed_on.isoformat() if review.stayed_on else None,
        "propertyTitle": review.property.title if review.property else None,
    }


def _published(agency_id: str):
    return Review.query.filter_by(agency_id=agency_id, status="PUBLISHED")


def summary(query) -> dict:
    average, count = query.with_entities(func.avg(Review.rating), func.count(Review.id)).one()
    return {"average": round(float(average), 2) if average else None, "count": count}


def for_property(agency_id: str, property_id: str, limit: int = 20) -> dict:
    query = _published(agency_id).filter_by(property_id=property_id)
    return {
        "rating": summary(query),
        "reviews": [public_review(item) for item in query.order_by(Review.stayed_on.desc(), Review.created_at.desc()).limit(limit)],
    }


def for_agency(agency_id: str, limit: int = 12) -> dict:
    """For the site's reviews block: the latest published ones, and the agency's average."""
    query = _published(agency_id)
    return {
        "rating": summary(query),
        "reviews": [public_review(item) for item in query.order_by(Review.created_at.desc()).limit(limit)],
    }


def ratings_by_property(agency_id: str, property_ids: list[str]) -> dict[str, dict]:
    """{property_id: {average, count}} for property cards, in one query."""
    if not property_ids:
        return {}
    rows = (
        _published(agency_id)
        .filter(Review.property_id.in_(property_ids))
        .with_entities(Review.property_id, func.avg(Review.rating), func.count(Review.id))
        .group_by(Review.property_id)
        .all()
    )
    result: dict[str, dict] = defaultdict(dict)
    for property_id, average, count in rows:
        result[property_id] = {"average": round(float(average), 2), "count": count}
    return dict(result)
