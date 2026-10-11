from flask import jsonify, request
from marshmallow import ValidationError

from app.blueprints.team import bp
from app.extensions import db
from app.models import User
from app.schemas.user import CreateTeamUserSchema, UpdateTeamUserSchema, UserSchema
from app.utils.tenancy import current_agency_id, require_role

user_schema = UserSchema()
users_schema = UserSchema(many=True)


@bp.route("/", methods=["GET"])
def list_team():
    agency_id = current_agency_id()
    users = User.query.filter_by(agency_id=agency_id).order_by(User.created_at.asc()).all()
    return jsonify(users_schema.dump(users))


@bp.route("/", methods=["POST"])
@require_role("OWNER", "ADMIN")
def create_team_member():
    try:
        data = CreateTeamUserSchema().load(request.get_json(silent=True) or {})
    except ValidationError as err:
        return jsonify({"message": "Validation error", "errors": err.messages}), 400

    if User.query.filter_by(email=data["email"]).first() is not None:
        return jsonify({"message": "Email already in use"}), 409

    user = User(
        agency_id=current_agency_id(),
        name=data["name"],
        email=data["email"],
        role=data["role"],
    )
    user.set_password(data["password"])
    db.session.add(user)
    db.session.commit()

    return jsonify(user_schema.dump(user)), 201


@bp.route("/<user_id>", methods=["PATCH"])
@require_role("OWNER")
def update_team_member(user_id):
    user = User.query.filter_by(id=user_id, agency_id=current_agency_id()).first()
    if user is None:
        return jsonify({"message": "Not found"}), 404

    try:
        data = UpdateTeamUserSchema().load(request.get_json(silent=True) or {}, partial=True)
    except ValidationError as err:
        return jsonify({"message": "Validation error", "errors": err.messages}), 400

    if "role" in data:
        user.role = data["role"]
    if "is_active" in data:
        user.is_active = data["is_active"]

    db.session.commit()
    return jsonify(user_schema.dump(user))
