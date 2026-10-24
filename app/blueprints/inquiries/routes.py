from datetime import datetime, timezone

from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity
from marshmallow import ValidationError

from app.blueprints.inquiries import bp
from app.extensions import db
from app.models import Client, Inquiry, Offer, Property, User
from app.schemas.client import InquiryReplySchema, ReplyTemplateSchema
from app.services import inquiry_service
from app.utils.tenancy import current_agency_id

template_schema = ReplyTemplateSchema()
templates_schema = ReplyTemplateSchema(many=True)


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


def _serialize(inquiry: Inquiry, clients: dict, properties: dict, offers: dict, users: dict) -> dict:
    client = clients.get(inquiry.client_id)
    # A client in the trash has no page to open; the inquiry keeps its own name and email.
    if client is not None and client.deleted_at is not None:
        client = None
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
        "archivedAt": _iso(inquiry.archived_at),
        "deletedAt": _iso(inquiry.deleted_at),
        "repliedAt": _iso(inquiry.replied_at),
        "repliedBy": users[inquiry.replied_by].name if inquiry.replied_by in users else None,
        "client": (
            {"id": client.id, "name": client.name, "stage": client.stage, "assignedAgentId": client.assigned_agent_id}
            if client
            else None
        ),
        "property": (
            {"id": prop.id, "title": prop.title, "slug": prop.slug, "coverUrl": _cover(prop)} if prop else None
        ),
        "offer": {"id": offer.id, "title": offer.title} if offer else None,
    }


def _serialize_many(inquiries: list[Inquiry]) -> list[dict]:
    """Loads the related clients, properties, offers and repliers of the whole page in four queries."""

    def by_id(model, ids):
        ids = {value for value in ids if value}
        return {row.id: row for row in model.query.filter(model.id.in_(ids)).all()} if ids else {}

    clients = by_id(Client, (inquiry.client_id for inquiry in inquiries))
    properties = by_id(Property, (inquiry.property_id for inquiry in inquiries))
    offers = by_id(Offer, (inquiry.offer_id for inquiry in inquiries))
    users = by_id(User, (inquiry.replied_by for inquiry in inquiries))
    return [_serialize(inquiry, clients, properties, offers, users) for inquiry in inquiries]


def _load(schema, partial=False):
    try:
        return schema.load(request.get_json(silent=True) or {}, partial=partial), None
    except ValidationError as err:
        return None, (jsonify({"message": "Validation error", "errors": err.messages}), 400)


def _error(err: inquiry_service.InquiryError):
    return jsonify({"message": err.message}), err.status_code


@bp.route("/", methods=["GET"])
def list_inquiries():
    """Newest first. `?status=new` keeps only the ones nobody opened yet,
    `?status=archived` shows the archived ones instead of the inbox."""
    agency_id = current_agency_id()
    status = request.args.get("status")
    if status == "archived":
        query = inquiry_service.live_inquiries(agency_id).filter(Inquiry.archived_at.isnot(None))
    else:
        query = inquiry_service.inbox(agency_id)
        if status == "new":
            query = query.filter(Inquiry.read_at.is_(None))
    inquiries = query.order_by(Inquiry.created_at.desc()).limit(200).all()
    return jsonify(_serialize_many(inquiries))


@bp.route("/unread-count", methods=["GET"])
def unread_count():
    count = inquiry_service.inbox(current_agency_id()).filter(Inquiry.read_at.is_(None)).count()
    return jsonify({"count": count})


@bp.route("/trash", methods=["GET"])
def list_trashed_inquiries():
    """What's in the trash; anything older than TRASH_DAYS is deleted for good first."""
    return jsonify(_serialize_many(inquiry_service.list_trashed(current_agency_id())))


@bp.route("/<inquiry_id>", methods=["PATCH"])
def mark_inquiry(inquiry_id):
    """`{"read": bool}` marks it read or back to new; `{"archived": bool}` archives it or brings it back."""
    body = request.get_json(silent=True) or {}
    changes = {key: body[key] for key in ("read", "archived") if key in body}
    invalid = {key: ["Debe ser true o false."] for key, value in changes.items() if not isinstance(value, bool)}
    if not changes or invalid:
        return jsonify({"message": "Validation error", "errors": invalid or {"read": ["Debe ser true o false."]}}), 400
    try:
        inquiry = inquiry_service.mark(current_agency_id(), inquiry_id, **changes)
    except inquiry_service.InquiryError as err:
        return _error(err)
    return jsonify(_serialize_many([inquiry])[0])


@bp.route("/<inquiry_id>", methods=["DELETE"])
def delete_inquiry(inquiry_id):
    try:
        inquiry_service.delete_inquiry(current_agency_id(), inquiry_id)
    except inquiry_service.InquiryError as err:
        return _error(err)
    return "", 204


@bp.route("/<inquiry_id>/restore", methods=["POST"])
def restore_inquiry(inquiry_id):
    try:
        inquiry = inquiry_service.restore_inquiry(current_agency_id(), inquiry_id)
    except inquiry_service.InquiryError as err:
        return _error(err)
    return jsonify(_serialize_many([inquiry])[0])


@bp.route("/<inquiry_id>/permanent", methods=["DELETE"])
def delete_inquiry_forever(inquiry_id):
    try:
        inquiry_service.delete_forever(current_agency_id(), inquiry_id)
    except inquiry_service.InquiryError as err:
        return _error(err)
    return "", 204


@bp.route("/<inquiry_id>/reply", methods=["POST"])
def reply_to_inquiry(inquiry_id):
    data, error = _load(InquiryReplySchema())
    if error:
        return error
    try:
        inquiry = inquiry_service.reply(
            current_agency_id(), inquiry_id, get_jwt_identity(), data["subject"], data["body"]
        )
    except inquiry_service.InquiryError as err:
        return _error(err)
    return jsonify(_serialize_many([inquiry])[0])


@bp.route("/read-all", methods=["POST"])
def mark_all_read():
    ids = [
        row.id
        for row in inquiry_service.inbox(current_agency_id())
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


@bp.route("/templates", methods=["GET"])
def list_templates():
    return jsonify(templates_schema.dump(inquiry_service.list_templates(current_agency_id())))


@bp.route("/templates", methods=["POST"])
def create_template():
    data, error = _load(ReplyTemplateSchema())
    if error:
        return error
    try:
        template = inquiry_service.create_template(current_agency_id(), get_jwt_identity(), data)
    except inquiry_service.InquiryError as err:
        return _error(err)
    return jsonify(template_schema.dump(template)), 201


@bp.route("/templates/<template_id>", methods=["PATCH"])
def update_template(template_id):
    data, error = _load(ReplyTemplateSchema(), partial=True)
    if error:
        return error
    try:
        template = inquiry_service.update_template(current_agency_id(), template_id, data)
    except inquiry_service.InquiryError as err:
        return _error(err)
    return jsonify(template_schema.dump(template))


@bp.route("/templates/<template_id>", methods=["DELETE"])
def delete_template(template_id):
    try:
        inquiry_service.delete_template(current_agency_id(), template_id)
    except inquiry_service.InquiryError as err:
        return _error(err)
    return "", 204
