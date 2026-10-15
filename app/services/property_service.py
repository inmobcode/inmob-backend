from sqlalchemy.orm import joinedload, selectinload

from app.extensions import db
from app.models.base import generate_token
from app.models.booking import Booking
from app.models.offer import OfferProperty
from app.models.property import (
    Classification,
    Description,
    ImprovementRecommendation,
    Pool,
    Property,
    PropertyOwner,
    PropertyPhoto,
    RatePeriod,
)
from app.schemas.agency import AgencyPublicSchema
from app.schemas.property import PublicPropertySchema
from app.utils import trash
from app.services import owner_account_service
from app.utils.slugify import slugify
from app.utils.tenancy import agent_scope, is_member


class PropertyError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _unique_slug(agency_id: str, title: str, *, exclude_id: str | None = None) -> str:
    base = slugify(title) or "propiedad"
    slug = base
    suffix = 1
    while True:
        query = Property.query.filter_by(agency_id=agency_id, slug=slug)
        if exclude_id:
            query = query.filter(Property.id != exclude_id)
        if query.first() is None:
            return slug
        suffix += 1
        slug = f"{base}-{suffix}"


def property_load_options():
    """Everything PropertySchema reads, fetched with the property instead of
    one query per relationship per property (each query is a round trip to
    the database)."""
    return (
        joinedload(Property.agency),
        joinedload(Property.owner),
        joinedload(Property.classification),
        joinedload(Property.content),
        selectinload(Property.photos),
    )


def _own_properties(query):
    """An AGENT sees only the properties assigned to them."""
    scope = agent_scope()
    return query.filter(Property.assigned_agent_id == scope) if scope else query


def list_properties(agency_id: str, *, status: str | None = None, listing_type: str | None = None):
    query = _own_properties(
        Property.query.options(*property_load_options()).filter_by(agency_id=agency_id, deleted_at=None)
    )
    if status:
        query = query.filter_by(status=status)
    if listing_type:
        query = query.filter_by(listing_type=listing_type)
    return query.order_by(Property.created_at.desc()).all()


def get_property(agency_id: str, property_id: str, *, trashed: bool = False) -> Property:
    """A live property, or with trashed=True one in the trash."""
    query = Property.query.options(*property_load_options()).filter_by(id=property_id, agency_id=agency_id)
    query = _own_properties(query)
    query = query.filter(Property.deleted_at.isnot(None) if trashed else Property.deleted_at.is_(None))
    prop = query.first()
    if prop is None:
        raise PropertyError("Property not found", 404)
    return prop


def create_property(agency_id: str, created_by: str, data: dict) -> Property:
    prop = Property(
        agency_id=agency_id,
        created_by=created_by,
        assigned_agent_id=created_by,
        title=data["title"],
        slug=_unique_slug(agency_id, data["title"]),
        listing_type=data["listing_type"],
        category=data["category"],
        country=data.get("country"),
        region=data.get("region"),
        area=data.get("area"),
        status="DRAFT",
    )
    db.session.add(prop)
    db.session.commit()
    return prop


def _upsert_classification(prop: Property, data: dict) -> None:
    classification = prop.classification
    if classification is None:
        classification = Classification(property_id=prop.id)
        db.session.add(classification)
        prop.classification = classification
    for field, value in data.items():
        setattr(classification, field, value)


def _upsert_description(prop: Property, data: dict) -> None:
    content = prop.content
    if content is None:
        content = Description(property_id=prop.id)
        db.session.add(content)
        prop.content = content
    for field, value in data.items():
        setattr(content, field, value)


def update_property(agency_id: str, property_id: str, data: dict) -> Property:
    prop = get_property(agency_id, property_id)

    if "owner_id" in data and data["owner_id"]:
        owner = PropertyOwner.query.filter_by(id=data["owner_id"], agency_id=agency_id).first()
        if owner is None:
            raise PropertyError("Owner not found", 404)

    if "assigned_agent_id" in data:
        # Handing a property to someone else is for owners and admins.
        if agent_scope():
            raise PropertyError("Forbidden", 403)
        if data["assigned_agent_id"] and not is_member(agency_id, data["assigned_agent_id"]):
            raise PropertyError("Agent not found", 404)

    if "title" in data and data["title"] != prop.title:
        prop.slug = _unique_slug(agency_id, data["title"], exclude_id=prop.id)

    classification_data = data.pop("classification", None)
    content_data = data.pop("content", None)

    for field, value in data.items():
        setattr(prop, field, value)

    if classification_data is not None:
        _upsert_classification(prop, classification_data)
    if content_data is not None:
        _upsert_description(prop, content_data)

    db.session.commit()
    return prop


def delete_property(agency_id: str, property_id: str) -> None:
    """Moves the property to the trash: off the app and the public site, restorable."""
    prop = get_property(agency_id, property_id)
    prop.deleted_at = trash.now()
    db.session.commit()


def list_trashed_properties(agency_id: str):
    purge_trashed_properties(agency_id)
    return (
        _own_properties(
            Property.query.options(*property_load_options()).filter(
                Property.agency_id == agency_id, Property.deleted_at.isnot(None)
            )
        )
        .order_by(Property.deleted_at.desc())
        .all()
    )


def restore_property(agency_id: str, property_id: str) -> Property:
    prop = get_property(agency_id, property_id, trashed=True)
    prop.deleted_at = None
    db.session.commit()
    return prop


def _is_referenced(prop: Property) -> bool:
    """Bookings and offers keep pointing at it, so it can't be deleted for good."""
    return (
        Booking.query.filter_by(property_id=prop.id).first() is not None
        or OfferProperty.query.filter_by(property_id=prop.id).first() is not None
    )


def delete_property_forever(agency_id: str, property_id: str) -> None:
    prop = get_property(agency_id, property_id, trashed=True)
    if _is_referenced(prop):
        raise PropertyError(
            "No se puede borrar definitivamente: tiene reservas u ofertas. Queda en la papelera.", 409
        )
    db.session.delete(prop)
    db.session.commit()


def purge_trashed_properties(agency_id: str) -> None:
    """Deletes for good what has been in the trash longer than TRASH_DAYS,
    except properties bookings or offers still point at."""
    expired = Property.query.filter(
        Property.agency_id == agency_id,
        Property.deleted_at.isnot(None),
        Property.deleted_at < trash.purge_cutoff(),
    ).all()
    for prop in expired:
        if not _is_referenced(prop):
            db.session.delete(prop)
    db.session.commit()


def set_status(agency_id: str, property_id: str, status: str) -> Property:
    prop = get_property(agency_id, property_id)
    prop.status = status
    db.session.commit()
    return prop


def create_room(agency_id: str, created_by: str, parent_property_id: str) -> Property:
    parent = get_property(agency_id, parent_property_id)
    if parent.category != "HOTEL":
        raise PropertyError("Only HOTEL properties can have rooms", 400)

    room = Property(
        agency_id=agency_id,
        created_by=created_by,
        assigned_agent_id=parent.assigned_agent_id,
        parent_property_id=parent.id,
        title=f"{parent.title} — New Room",
        slug=_unique_slug(agency_id, f"{parent.title}-room"),
        listing_type=parent.listing_type,
        category="HOTEL_ROOM",
        country=parent.country,
        region=parent.region,
        area=parent.area,
        status="DRAFT",
    )
    db.session.add(room)
    db.session.commit()
    return room


def add_photo(agency_id: str, property_id: str, data: dict) -> Property:
    prop = get_property(agency_id, property_id)
    photo = PropertyPhoto(
        property_id=prop.id,
        url=data["url"],
        position=data.get("position", len(prop.photos)),
        is_cover=data.get("is_cover", False),
        section=data.get("section", "GENERAL"),
        section_detail=data.get("section_detail"),
    )
    if photo.is_cover:
        for existing in prop.photos:
            existing.is_cover = False
    db.session.add(photo)
    db.session.commit()
    return prop


def remove_photo(agency_id: str, property_id: str, photo_id: str) -> Property:
    prop = get_property(agency_id, property_id)
    photo = next((p for p in prop.photos if p.id == photo_id), None)
    if photo is None:
        raise PropertyError("Photo not found", 404)
    db.session.delete(photo)
    db.session.commit()
    return prop


def update_photo(agency_id: str, property_id: str, photo_id: str, data: dict) -> Property:
    prop = get_property(agency_id, property_id)
    photo = next((p for p in prop.photos if p.id == photo_id), None)
    if photo is None:
        raise PropertyError("Photo not found", 404)

    if data.get("is_cover"):
        for existing in prop.photos:
            existing.is_cover = existing.id == photo_id
    for field in ("section", "section_detail"):
        if field in data:
            setattr(photo, field, data[field])

    db.session.commit()
    return prop


def reorder_photos(agency_id: str, property_id: str, photo_ids: list[str]) -> Property:
    prop = get_property(agency_id, property_id)
    by_id = {photo.id: photo for photo in prop.photos}
    if set(photo_ids) != set(by_id):
        raise PropertyError("photoIds must list every photo exactly once", 400)

    for position, photo_id in enumerate(photo_ids):
        by_id[photo_id].position = position

    db.session.commit()
    return prop


def list_owners(agency_id: str):
    return PropertyOwner.query.filter_by(agency_id=agency_id).order_by(PropertyOwner.name).all()


def create_owner(agency_id: str, data: dict) -> PropertyOwner:
    owner = PropertyOwner(agency_id=agency_id, **data)
    db.session.add(owner)
    db.session.commit()
    return owner


def regenerate_owner_token(agency_id: str, owner_id: str) -> PropertyOwner:
    owner = PropertyOwner.query.filter_by(id=owner_id, agency_id=agency_id).first()
    if owner is None:
        raise PropertyError("Owner not found", 404)
    owner.access_token = generate_token()
    db.session.commit()
    return owner


def get_owner_by_token(token: str) -> PropertyOwner | None:
    return PropertyOwner.query.filter_by(access_token=token).first()


def serialize_owner_portal(owner: PropertyOwner) -> dict:
    public_property_schema = PublicPropertySchema()
    properties = []
    for prop in owner.properties.filter(Property.deleted_at.is_(None)):
        bookings = (
            Booking.query.filter_by(property_id=prop.id, deleted_at=None)
            .order_by(Booking.start_date.desc())
            .all()
        )
        properties.append(
            {
                **public_property_schema.dump(prop),
                # The owner sees whether it's live; only published ones have a page to link to.
                "status": prop.status,
                "published": prop.status == "PUBLISHED",
                "bookings": [
                    {
                        "startDate": booking.start_date.isoformat() if booking.start_date else None,
                        "endDate": booking.end_date.isoformat() if booking.end_date else None,
                        "status": booking.status,
                        "totalPrice": booking.total_price,
                        "currency": booking.currency,
                        "payments": [
                            {
                                "amount": payment.amount,
                                "currency": payment.currency,
                                "type": payment.type,
                                "status": payment.status,
                                "paidAt": payment.paid_at.isoformat() if payment.paid_at else None,
                            }
                            for payment in booking.payments
                            if payment.type != "COMMISSION"
                        ],
                    }
                    for booking in bookings
                ],
                "recommendations": [
                    {
                        "id": rec.id,
                        "title": rec.title,
                        "details": rec.details,
                        "priority": rec.priority,
                        "estCost": rec.est_cost,
                        "pdfUrl": rec.pdf_url,
                        "status": rec.status,
                        "createdAt": rec.created_at.isoformat() if rec.created_at else None,
                    }
                    for rec in prop.recommendations
                ],
            }
        )

    return {
        "ownerName": owner.name,
        "agencyName": owner.agency.name,
        # Branding and contact, like the client's booking page.
        "agency": {**AgencyPublicSchema().dump(owner.agency), "slug": owner.agency.slug},
        "properties": properties,
        # Money: what's been collected, what's due to the owner and what was handed over.
        "statement": owner_account_service.build_statement(
            owner, with_commission=bool(owner.agency.owner_portal_shows_commission)
        ),
    }


# --- Pools / Jacuzzis -----------------------------------------------------

def list_pools(agency_id: str, property_id: str):
    get_property(agency_id, property_id)
    return Pool.query.filter_by(property_id=property_id).all()


def create_pool(agency_id: str, property_id: str, data: dict) -> Pool:
    get_property(agency_id, property_id)
    pool = Pool(property_id=property_id, **data)
    db.session.add(pool)
    db.session.commit()
    return pool


def update_pool(agency_id: str, property_id: str, pool_id: str, data: dict) -> Pool:
    get_property(agency_id, property_id)
    pool = Pool.query.filter_by(id=pool_id, property_id=property_id).first()
    if pool is None:
        raise PropertyError("Pool not found", 404)
    for field, value in data.items():
        setattr(pool, field, value)
    db.session.commit()
    return pool


def delete_pool(agency_id: str, property_id: str, pool_id: str) -> None:
    get_property(agency_id, property_id)
    pool = Pool.query.filter_by(id=pool_id, property_id=property_id).first()
    if pool is None:
        raise PropertyError("Pool not found", 404)
    db.session.delete(pool)
    db.session.commit()


# --- Rate periods (rental seasonal pricing) --------------------------------

def list_rate_periods(agency_id: str, property_id: str):
    get_property(agency_id, property_id)
    return RatePeriod.query.filter_by(property_id=property_id).order_by(RatePeriod.start_date).all()


def create_rate_period(agency_id: str, property_id: str, data: dict) -> RatePeriod:
    get_property(agency_id, property_id)
    if data["start_date"] > data["end_date"]:
        raise PropertyError("startDate must be on or before endDate", 400)
    period = RatePeriod(property_id=property_id, **data)
    db.session.add(period)
    db.session.commit()
    return period


def update_rate_period(agency_id: str, property_id: str, period_id: str, data: dict) -> RatePeriod:
    get_property(agency_id, property_id)
    period = RatePeriod.query.filter_by(id=period_id, property_id=property_id).first()
    if period is None:
        raise PropertyError("Rate period not found", 404)
    for field, value in data.items():
        setattr(period, field, value)
    db.session.commit()
    return period


def delete_rate_period(agency_id: str, property_id: str, period_id: str) -> None:
    get_property(agency_id, property_id)
    period = RatePeriod.query.filter_by(id=period_id, property_id=property_id).first()
    if period is None:
        raise PropertyError("Rate period not found", 404)
    db.session.delete(period)
    db.session.commit()


# --- Improvement recommendations -------------------------------------------

def list_recommendations(agency_id: str, property_id: str):
    get_property(agency_id, property_id)
    return (
        ImprovementRecommendation.query.filter_by(property_id=property_id)
        .order_by(ImprovementRecommendation.created_at.desc())
        .all()
    )


def create_recommendation(agency_id: str, property_id: str, data: dict) -> ImprovementRecommendation:
    get_property(agency_id, property_id)
    recommendation = ImprovementRecommendation(property_id=property_id, status="PROPOSED", **data)
    db.session.add(recommendation)
    db.session.commit()
    return recommendation


def update_recommendation(
    agency_id: str, property_id: str, recommendation_id: str, data: dict
) -> ImprovementRecommendation:
    get_property(agency_id, property_id)
    recommendation = ImprovementRecommendation.query.filter_by(
        id=recommendation_id, property_id=property_id
    ).first()
    if recommendation is None:
        raise PropertyError("Recommendation not found", 404)
    for field, value in data.items():
        setattr(recommendation, field, value)
    db.session.commit()
    return recommendation


def delete_recommendation(agency_id: str, property_id: str, recommendation_id: str) -> None:
    get_property(agency_id, property_id)
    recommendation = ImprovementRecommendation.query.filter_by(
        id=recommendation_id, property_id=property_id
    ).first()
    if recommendation is None:
        raise PropertyError("Recommendation not found", 404)
    db.session.delete(recommendation)
    db.session.commit()
