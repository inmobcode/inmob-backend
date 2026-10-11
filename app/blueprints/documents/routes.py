from flask import jsonify

from app.blueprints.documents import bp


@bp.route("/", methods=["GET"])
def status():
    return jsonify({"module": "documents", "status": "not_implemented"}), 501
