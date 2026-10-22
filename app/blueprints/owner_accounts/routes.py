from flask import jsonify, request
from marshmallow import ValidationError

from app.blueprints.owner_accounts import bp
from app.schemas.owner_payout import OwnerPayoutSchema
from app.services import owner_account_service as accounts
from app.utils.tenancy import current_agency_id, current_user_id, require_role

# Money between the agency and an owner: owners and admins only.


@bp.route("/<owner_id>", methods=["GET"])
@require_role("OWNER", "ADMIN")
def get_statement(owner_id):
    try:
        owner = accounts.get_owner(current_agency_id(), owner_id)
    except accounts.OwnerAccountError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(accounts.build_statement(owner))


@bp.route("/<owner_id>/payouts", methods=["POST"])
@require_role("OWNER", "ADMIN")
def create_payout(owner_id):
    try:
        data = OwnerPayoutSchema().load(request.get_json(silent=True) or {})
    except ValidationError as err:
        return jsonify({"message": "Validation error", "errors": err.messages}), 400
    try:
        payout = accounts.create_payout(current_agency_id(), owner_id, current_user_id(), data)
    except accounts.OwnerAccountError as err:
        return jsonify({"message": err.message}), err.status_code
    return jsonify(accounts.serialize_payout(payout)), 201


@bp.route("/<owner_id>/payouts/<payout_id>", methods=["DELETE"])
@require_role("OWNER", "ADMIN")
def delete_payout(owner_id, payout_id):
    try:
        accounts.delete_payout(current_agency_id(), owner_id, payout_id)
    except accounts.OwnerAccountError as err:
        return jsonify({"message": err.message}), err.status_code
    return "", 204
