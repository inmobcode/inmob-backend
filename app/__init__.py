from flask import Flask, jsonify

from app.config import Config
from app.extensions import cors, db, jwt, migrate


def create_app(config_class: type = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    cors.init_app(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})
    register_jwt_error_handlers(app)

    with app.app_context():
        from app import models  # noqa: F401  (registers models on db.metadata)

    register_blueprints(app)

    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok"})

    return app


def register_jwt_error_handlers(app: Flask) -> None:
    @jwt.unauthorized_loader
    def _missing_token(reason):
        return jsonify({"message": reason}), 401

    @jwt.invalid_token_loader
    def _invalid_token(reason):
        return jsonify({"message": reason}), 422

    @jwt.expired_token_loader
    def _expired_token(_jwt_header, _jwt_payload):
        return jsonify({"message": "Token expired"}), 401


def register_blueprints(app: Flask) -> None:
    from app.blueprints.agency import bp as agency_bp
    from app.blueprints.auth import bp as auth_bp
    from app.blueprints.availability import bp as availability_bp
    from app.blueprints.bookings import bp as bookings_bp
    from app.blueprints.clients import bp as clients_bp
    from app.blueprints.documents import bp as documents_bp
    from app.blueprints.offers import bp as offers_bp
    from app.blueprints.payments import bp as payments_bp
    from app.blueprints.properties import bp as properties_bp
    from app.blueprints.public import bp as public_bp
    from app.blueprints.team import bp as team_bp

    for bp in (
        auth_bp,
        agency_bp,
        properties_bp,
        availability_bp,
        offers_bp,
        clients_bp,
        bookings_bp,
        payments_bp,
        documents_bp,
        team_bp,
        public_bp,
    ):
        app.register_blueprint(bp)
