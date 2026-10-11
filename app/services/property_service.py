from app.extensions import db
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
from app.utils.slugify import slugify


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


def list_properties(agency_id: str, *, status: str | None = None, listing_type: str | None = None):
    query = Property.query.filter_by(agency_id=agency_id)
    if status:
        query = query.filter_by(status=status)
    if listing_type:
        query = query.filter_by(listing_type=listing_type)
    return query.order_by(Property.created_at.desc()).all()


def get_property(agency_id: str, property_id: str) -> Property:
    prop = Property.query.filter_by(id=property_id, agency_id=agency_id).first()
    if prop is None:
        raise PropertyError("Property not found", 404)
    return prop


def create_property(agency_id: str, created_by: str, data: dict) -> Property:
    prop = Property(
        agency_id=agency_id,
        created_by=created_by,
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
    prop = get_property(agency_id, property_id)
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


def list_owners(agency_id: str):
    return PropertyOwner.query.filter_by(agency_id=agency_id).order_by(PropertyOwner.name).all()


def create_owner(agency_id: str, data: dict) -> PropertyOwner:
    owner = PropertyOwner(agency_id=agency_id, **data)
    db.session.add(owner)
    db.session.commit()
    return owner


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
