from flask import jsonify, request
from marshmallow import ValidationError

from app.blueprints.reviews import bp
from app.schemas.review import ReviewSchema
from app.services import review_service
from app.utils.tenancy import current_agency_id, require_role

review_schema = ReviewSchema()
reviews_schema = ReviewSchema(many=True)

# Publishing is putting words on the agency's site: owners and admins only.
MANAGERS = ("OWNER", "ADMIN")


def _load(partial=False):
    try:
        return ReviewSchema().load(request.get_json(silent=True) or {}, partial=partial), None
    except ValidationError as err:
        return None, (jsonify({"message": "Validation error", "errors": err.messages}), 400)


def _error(err: review_service.ReviewError):
    return jsonify({"message": err.message}), err.status_code


@bp.route("/", methods=["GET"])
@require_role(*MANAGERS)
def list_reviews():
    """Newest first; `?status=PENDING` keeps only the ones waiting to be published."""
    return jsonify(reviews_schema.dump(review_service.list_reviews(current_agency_id(), request.args.get("status"))))


@bp.route("/", methods=["POST"])
@require_role(*MANAGERS)
def create_review():
    data, error = _load()
    if error:
        return error
    try:
        review = review_service.create_review(current_agency_id(), data)
    except review_service.ReviewError as err:
        return _error(err)
    return jsonify(review_schema.dump(review)), 201


@bp.route("/<review_id>", methods=["PATCH"])
@require_role(*MANAGERS)
def update_review(review_id):
    data, error = _load(partial=True)
    if error:
        return error
    try:
        review = review_service.update_review(current_agency_id(), review_id, data)
    except review_service.ReviewError as err:
        return _error(err)
    return jsonify(review_schema.dump(review))


@bp.route("/<review_id>", methods=["DELETE"])
@require_role(*MANAGERS)
def delete_review(review_id):
    try:
        review_service.delete_review(current_agency_id(), review_id)
    except review_service.ReviewError as err:
        return _error(err)
    return "", 204
