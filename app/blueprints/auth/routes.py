from flask import jsonify, request
from flask_jwt_extended import create_access_token, get_jwt, get_jwt_identity, jwt_required
from marshmallow import ValidationError

from app.blueprints.auth import bp
from app.extensions import db
from app.models import User
from app.schemas.auth import (
    ChangePasswordSchema,
    ForgotPasswordSchema,
    LoginSchema,
    RegisterAgencySchema,
    ResetPasswordSchema,
    UpdateProfileSchema,
)
from app.schemas.user import UserSchema
from app.services import auth_service, storage_service

user_schema = UserSchema()

MAX_AVATAR_BYTES = 5 * 1024 * 1024  # 5MB


def _auth_payload(result: dict) -> dict:
    return {
        "accessToken": result["access_token"],
        "refreshToken": result["refresh_token"],
        "user": {**user_schema.dump(result["user"]), "agencySlug": result["agency"].slug},
    }


def _profile_payload(user: User) -> dict:
    return {**user_schema.dump(user), "agencySlug": user.agency.slug}


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


@bp.route("/password/forgot", methods=["POST"])
def forgot_password():
    try:
        data = ForgotPasswordSchema().load(request.get_json(silent=True) or {})
    except ValidationError as err:
        return jsonify({"message": "Validation error", "errors": err.messages}), 400

    # Same answer whether or not the email has an account.
    auth_service.request_password_reset(data["email"])
    return "", 204


@bp.route("/password/reset", methods=["POST"])
def reset_password():
    try:
        data = ResetPasswordSchema().load(request.get_json(silent=True) or {})
    except ValidationError as err:
        return jsonify({"message": "Validation error", "errors": err.messages}), 400

    try:
        auth_service.reset_password(data["email"], data["code"], data["password"])
    except auth_service.AuthError as err:
        return jsonify({"message": err.message}), err.status_code

    return "", 204


@bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    claims = get_jwt()
    additional_claims = {
        key: claims[key] for key in ("agency_id", "agency_slug", "role", "name", "email")
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
    return jsonify(_profile_payload(user))


@bp.route("/me", methods=["PATCH"])
@jwt_required()
def update_me():
    try:
        data = UpdateProfileSchema().load(request.get_json(silent=True) or {}, partial=True)
    except ValidationError as err:
        return jsonify({"message": "Validation error", "errors": err.messages}), 400

    user = db.session.get(User, get_jwt_identity())
    if user is None:
        return jsonify({"message": "Not found"}), 404

    if "email" in data and data["email"] != user.email:
        if User.query.filter_by(email=data["email"]).first() is not None:
            return jsonify({"message": "Email already in use"}), 409
        user.email = data["email"]

    if "name" in data:
        user.name = data["name"]

    db.session.commit()
    return jsonify(_profile_payload(user))


@bp.route("/me/password", methods=["POST"])
@jwt_required()
def change_password():
    try:
        data = ChangePasswordSchema().load(request.get_json(silent=True) or {})
    except ValidationError as err:
        return jsonify({"message": "Validation error", "errors": err.messages}), 400

    user = db.session.get(User, get_jwt_identity())
    if user is None:
        return jsonify({"message": "Not found"}), 404

    if not user.check_password(data["current_password"]):
        return jsonify({"message": "La contraseña actual es incorrecta"}), 401

    user.set_password(data["new_password"])
    db.session.commit()
    return "", 204


@bp.route("/me/avatar", methods=["POST"])
@jwt_required()
def upload_avatar():
    user = db.session.get(User, get_jwt_identity())
    if user is None:
        return jsonify({"message": "Not found"}), 404

    uploaded = request.files.get("file")
    if uploaded is None:
        return jsonify({"message": "Falta el archivo"}), 400

    content = uploaded.read()
    if len(content) > MAX_AVATAR_BYTES:
        return jsonify({"message": "La imagen es demasiado grande"}), 400

    try:
        url = storage_service.upload_avatar(
            user.id,
            uploaded.filename or "avatar.webp",
            content,
            uploaded.mimetype or "image/webp",
        )
    except storage_service.StorageError as err:
        return jsonify({"message": err.message}), err.status_code

    user.avatar_url = url
    db.session.commit()
    return jsonify(_profile_payload(user))


@bp.route("/me/agencies", methods=["GET"])
@jwt_required()
def my_agencies():
    return jsonify(auth_service.list_my_agencies(get_jwt_identity()))


@bp.route("/switch-agency", methods=["POST"])
@jwt_required()
def switch_agency():
    data = request.get_json(silent=True) or {}
    agency_id = data.get("agencyId")
    if not agency_id:
        return jsonify({"message": "Validation error", "errors": {"agencyId": ["Required"]}}), 400

    try:
        result = auth_service.switch_agency(get_jwt_identity(), agency_id)
    except auth_service.AuthError as err:
        return jsonify({"message": err.message}), err.status_code

    return jsonify(_auth_payload(result))
