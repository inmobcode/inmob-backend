from flask import jsonify, request
from flask_jwt_extended import create_access_token, get_jwt, get_jwt_identity, jwt_required
from marshmallow import ValidationError

from app.blueprints.auth import bp
from app.extensions import db
from app.models import User
from app.schemas.auth import LoginSchema, RegisterAgencySchema
from app.schemas.user import UserSchema
from app.services import auth_service

user_schema = UserSchema()


def _auth_payload(result: dict) -> dict:
    return {
        "accessToken": result["access_token"],
        "refreshToken": result["refresh_token"],
        "user": user_schema.dump(result["user"]),
    }


@bp.route("/register", methods=["POST"])
def register():
    try:
        data = RegisterAgencySchema().load(request.get_json(silent=True) or {})
    except ValidationError as err:
        return jsonify({"message": "Validation error", "errors": err.messages}), 400

    try:
        result = auth_service.register_agency(data)
    except auth_service.AuthError as err:
        return jsonify({"message": err.message}), err.status_code

    return jsonify(_auth_payload(result)), 201


@bp.route("/login", methods=["POST"])
def login():
    try:
        data = LoginSchema().load(request.get_json(silent=True) or {})
    except ValidationError as err:
        return jsonify({"message": "Validation error", "errors": err.messages}), 400

    try:
        result = auth_service.authenticate(data["email"], data["password"])
    except auth_service.AuthError as err:
        return jsonify({"message": err.message}), err.status_code

    return jsonify(_auth_payload(result))


@bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    claims = get_jwt()
    additional_claims = {
        key: claims[key] for key in ("agency_id", "role", "name", "email")
    }
    access_token = create_access_token(
        identity=get_jwt_identity(), additional_claims=additional_claims
    )
    return jsonify({"accessToken": access_token})


@bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    user = db.session.get(User, get_jwt_identity())
    if user is None:
        return jsonify({"message": "Not found"}), 404
    return jsonify(user_schema.dump(user))
