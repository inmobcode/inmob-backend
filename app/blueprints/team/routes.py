from flask import jsonify, request
from marshmallow import ValidationError

from app.blueprints.team import bp
from app.schemas.user import CreateTeamUserSchema, UpdateTeamUserSchema, UserSchema
from app.services import team_service
from app.utils.tenancy import current_agency_id, require_role

user_schema = UserSchema()
users_schema = UserSchema(many=True)


@bp.route("/", methods=["GET"])
@require_role("OWNER", "ADMIN")
def list_team():
    members = team_service.list_team(current_agency_id())
    return jsonify(
        [{**user_schema.dump(user), "role": role} for user, role in members]
    )


@bp.route("/", methods=["POST"])
@require_role("OWNER", "ADMIN")
def create_team_member():
    try:
        data = CreateTeamUserSchema().load(request.get_json(silent=True) or {})
    except ValidationError as err:
        return jsonify({"message": "Validation error", "errors": err.messages}), 400

    try:
        user, linked_existing = team_service.invite_member(current_agency_id(), data)
    except team_service.TeamError as err:
        return jsonify({"message": err.message}), err.status_code

    return jsonify({**user_schema.dump(user), "role": data["role"], "linkedExisting": linked_existing}), 201


@bp.route("/<user_id>", methods=["PATCH"])
@require_role("OWNER", "ADMIN")
def update_team_member(user_id):
    try:
        data = UpdateTeamUserSchema().load(request.get_json(silent=True) or {}, partial=True)
    except ValidationError as err:
        return jsonify({"message": "Validation error", "errors": err.messages}), 400

    try:
        user, role = team_service.update_member(current_agency_id(), user_id, data)
    except team_service.TeamError as err:
        return jsonify({"message": err.message}), err.status_code

    return jsonify({**user_schema.dump(user), "role": role})


@bp.route("/<user_id>", methods=["DELETE"])
@require_role("OWNER", "ADMIN")
def remove_team_member(user_id):
    try:
        team_service.remove_member(current_agency_id(), user_id)
    except team_service.TeamError as err:
        return jsonify({"message": err.message}), err.status_code
    return "", 204
