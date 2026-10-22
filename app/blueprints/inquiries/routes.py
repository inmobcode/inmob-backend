from datetime import datetime, timezone

from flask import jsonify, request

from app.blueprints.inquiries import bp
from app.extensions import db
from app.models import Client, Inquiry, Offer, Property
from app.services.crm_service import visible_inquiries
from app.utils.tenancy import current_agency_id


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(value: datetime | None) -> str | None:
    """Timestamps are stored as naive UTC; say so, or browsers read them as local time."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _cover(prop: Property) -> str | None:
    photos = sorted(prop.photos, key=lambda photo: (not photo.is_cover, photo.position))
    return photos[0].url if photos else None


def _serialize(inquiry: Inquiry, clients: dict, properties: dict, offers: dict) -> dict:
    client = clients.get(inquiry.client_id)
    prop = properties.get(inquiry.property_id)
    offer = offers.get(inquiry.offer_id)
    return {
        "id": inquiry.id,
        "type": inquiry.inquiry_type,
        "name": inquiry.name,
        "email": inquiry.email,
        "phone": inquiry.phone,
        "message": inquiry.message,
        "createdAt": _iso(inquiry.created_at),
        "readAt": _iso(inquiry.read_at),
        "client": {"id": client.id, "name": client.name, "stage": client.stage} if client else None,
        "property": (
            {"id": prop.id, "title": prop.title, "slug": prop.slug, "coverUrl": _cover(prop)} if prop else None
        ),
        "offer": {"id": offer.id, "title": offer.title} if offer else None,
    }


def _serialize_many(inquiries: list[Inquiry]) -> list[dict]:
    """Loads the related client, property and offer of the whole page in three queries."""

    def by_id(model, ids):
        ids = {value for value in ids if value}
        return {row.id: row for row in model.query.filter(model.id.in_(ids)).all()} if ids else {}

    clients = by_id(Client, (inquiry.client_id for inquiry in inquiries))
    properties = by_id(Property, (inquiry.property_id for inquiry in inquiries))
    offers = by_id(Offer, (inquiry.offer_id for inquiry in inquiries))
    return [_serialize(inquiry, clients, properties, offers) for inquiry in inquiries]


def _get_or_404(inquiry_id: str):
    return visible_inquiries(Inquiry.query.filter_by(id=inquiry_id, agency_id=current_agency_id())).first()


@bp.route("/", methods=["GET"])
def list_inquiries():
    """Newest first. `?status=new` keeps only the ones nobody opened yet."""
    query = visible_inquiries(Inquiry.query.filter_by(agency_id=current_agency_id()))
    if request.args.get("status") == "new":
        query = query.filter(Inquiry.read_at.is_(None))
    inquiries = query.order_by(Inquiry.created_at.desc()).limit(200).all()
    return jsonify(_serialize_many(inquiries))


@bp.route("/unread-count", methods=["GET"])
def unread_count():
    query = visible_inquiries(Inquiry.query.filter_by(agency_id=current_agency_id()))
    count = query.filter(Inquiry.read_at.is_(None)).count()
    return jsonify({"count": count})


@bp.route("/<inquiry_id>", methods=["PATCH"])
def mark_inquiry(inquiry_id):
    """`{"read": true}` marks it read, `{"read": false}` back to new."""
    inquiry = _get_or_404(inquiry_id)
    if inquiry is None:
        return jsonify({"message": "Not found"}), 404
    body = request.get_json(silent=True) or {}
    if not isinstance(body.get("read"), bool):
        return jsonify({"message": "Validation error", "errors": {"read": ["Debe ser true o false."]}}), 400
    inquiry.read_at = _now() if body["read"] else None
    db.session.commit()
    return jsonify(_serialize_many([inquiry])[0])


@bp.route("/read-all", methods=["POST"])
def mark_all_read():
    ids = [
        row.id
        for row in visible_inquiries(Inquiry.query.filter_by(agency_id=current_agency_id()))
        .filter(Inquiry.read_at.is_(None))
        .with_entities(Inquiry.id)
        .all()
    ]
    updated = (
        Inquiry.query.filter(Inquiry.id.in_(ids)).update({Inquiry.read_at: _now()}, synchronize_session=False)
        if ids
        else 0
    )
    db.session.commit()
    return jsonify({"updated": updated})
