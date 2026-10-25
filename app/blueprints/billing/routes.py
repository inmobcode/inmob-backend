import json

from flask import current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from marshmallow import Schema, ValidationError, fields, validate

from app.blueprints.billing import bp
from app.extensions import db
from app.models import Agency, User
from app.services import billing_service
from app.utils.tenancy import current_agency_id, require_role


class CheckoutSchema(Schema):
    plan = fields.Str(required=True, validate=validate.OneOf(("trial", "pro")))


def _agency() -> Agency:
    return db.get_or_404(Agency, current_agency_id())


@bp.route("/status", methods=["GET"])
@jwt_required()
def status():
    return jsonify(billing_service.status_payload(_agency()))


@bp.route("/checkout", methods=["POST"])
@require_role("OWNER")
def checkout():
    try:
        data = CheckoutSchema().load(request.get_json(silent=True) or {})
    except ValidationError as err:
        return jsonify({"message": "Validation error", "errors": err.messages}), 400

    agency = _agency()
    if not billing_service.enabled():
        agency.plan = data["plan"]
        billing_service.start_without_billing(agency)
        db.session.commit()
        return jsonify({"checkout": None})

    user = db.session.get(User, get_jwt_identity())
    try:
        transaction_id = billing_service.create_checkout(agency, data["plan"], user.email)
    except billing_service.BillingError as err:
        return jsonify({"message": err.message}), err.status_code
    # The browser opens this transaction with Paddle.js.
    return jsonify({"checkout": {"transactionId": transaction_id, **billing_service.checkout_config()}})


@bp.route("/confirm", methods=["POST"])
@require_role("OWNER")
def confirm():
    transaction_id = (request.get_json(silent=True) or {}).get("transactionId")
    if not isinstance(transaction_id, str) or not transaction_id.startswith("txn_"):
        return jsonify({"message": "Validation error", "errors": {"transactionId": ["Required"]}}), 400
    agency = _agency()
    try:
        billing_service.confirm_checkout(agency, transaction_id)
    except billing_service.BillingError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(billing_service.status_payload(agency))


@bp.route("/portal", methods=["POST"])
@require_role("OWNER")
def portal():
    try:
        url = billing_service.create_portal(_agency())
    except billing_service.BillingError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify({"url": url})


@bp.route("/webhook", methods=["POST"])
def webhook():
    """Paddle's events. Not behind a login: the signature is what proves it's Paddle."""
    if not current_app.config["PADDLE_WEBHOOK_SECRET"]:
        return jsonify({"message": "Webhook not configured"}), 503
    raw = request.get_data()
    if not billing_service.verify_signature(raw, request.headers.get("Paddle-Signature", "")):
        return jsonify({"message": "Invalid signature"}), 400
    try:
        event = json.loads(raw)
    except ValueError:
        event = None
    if not isinstance(event, dict):
        return jsonify({"message": "Invalid payload"}), 400
    try:
        billing_service.handle_event(event)
    except billing_service.BillingError as err:
        return jsonify({"message": err.message}), err.status_code
    return "", 200
