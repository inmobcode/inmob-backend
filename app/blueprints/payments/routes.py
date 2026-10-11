from flask import jsonify

from app.blueprints.payments import bp


@bp.route("/", methods=["GET"])
def status():
    return jsonify({"module": "payments", "status": "not_implemented"}), 501
