from flask import jsonify, request

from app.blueprints.notifications import bp
from app.services import feed
from app.utils.tenancy import current_agency_id, current_user_id


def _iso(value):
    return value.isoformat() + "Z" if value else None


def serialize(notification) -> dict:
    return {
        "id": notification.id,
        "type": notification.type,
        "title": notification.title,
        "body": notification.body,
        "link": notification.link,
        "createdAt": _iso(notification.created_at),
        "readAt": _iso(notification.read_at),
    }


@bp.route("/", methods=["GET"])
def list_notifications():
    agency_id, user_id = current_agency_id(), current_user_id()
    items = feed.list_for_user(user_id, agency_id)
    return jsonify(
        {
            "unread": feed.unread_count(user_id, agency_id),
            "items": [serialize(item) for item in items],
        }
    )


@bp.route("/unread-count", methods=["GET"])
def unread_count():
    return jsonify({"count": feed.unread_count(current_user_id(), current_agency_id())})


@bp.route("/<notification_id>", methods=["PATCH"])
def mark(notification_id):
    """`{"read": true}` clears it, `{"read": false}` brings it back."""
    body = request.get_json(silent=True) or {}
    if not isinstance(body.get("read"), bool):
        return jsonify({"message": "Validation error", "errors": {"read": ["Debe ser true o false."]}}), 400
    notification = feed.mark_read(current_user_id(), current_agency_id(), notification_id, body["read"])
    if notification is None:
        return jsonify({"message": "Not found"}), 404
    return jsonify(serialize(notification))


@bp.route("/read-all", methods=["POST"])
def mark_all():
    return jsonify({"updated": feed.mark_all_read(current_user_id(), current_agency_id())})
