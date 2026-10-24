from flask import Flask, jsonify

from app.config import Config
from app.extensions import compress, cors, db, jwt, migrate


def create_app(config_class: type = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    compress.init_app(app)
    cors.init_app(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})
    register_jwt_error_handlers(app)

    with app.app_context():
        from app import models  # noqa: F401  (registers models on db.metadata)
        from app.services import audit

        audit.register()

    register_blueprints(app)
    register_locale_hooks(app)

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


def register_locale_hooks(app: Flask) -> None:
    """The frontend sends the page's language in X-Locale: error bodies come
    back in it, and a signed-in user's language is remembered for their emails."""
    from flask import request
    from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

    from app.i18n import request_locale
    from app.i18n.errors import localize_payload
    from app.models import User

    @app.before_request
    def _remember_user_locale():
        locale = request_locale()
        if not locale or not request.headers.get("Authorization"):
            return
        try:
            verify_jwt_in_request(optional=True)
            user_id = get_jwt_identity()
        except Exception:  # noqa: BLE001 - a bad token is the route's business, not ours
            return
        if not user_id:
            return
        user = db.session.get(User, user_id)
        if user is not None and user.locale != locale:
            user.locale = locale
            db.session.commit()

    @app.after_request
    def _localize_errors(response):
        locale = request_locale()
        if locale and response.status_code >= 400 and response.is_json:
            payload = response.get_json(silent=True)
            if isinstance(payload, dict):
                response.set_data(app.json.dumps(localize_payload(payload, locale)))
        return response


def register_blueprints(app: Flask) -> None:
    from app.blueprints.agency import bp as agency_bp
    from app.blueprints.auth import bp as auth_bp
    from app.blueprints.availability import bp as availability_bp
    from app.blueprints.bookings import bp as bookings_bp
    from app.blueprints.clients import bp as clients_bp
    from app.blueprints.dashboard import bp as dashboard_bp
    from app.blueprints.documents import bp as documents_bp
    from app.blueprints.imports import bp as imports_bp
    from app.blueprints.inquiries import bp as inquiries_bp
    from app.blueprints.notifications import bp as notifications_bp
    from app.blueprints.offers import bp as offers_bp
    from app.blueprints.owner_accounts import bp as owner_accounts_bp
    from app.blueprints.payments import bp as payments_bp
    from app.blueprints.properties import bp as properties_bp
    from app.blueprints.public import bp as public_bp
    from app.blueprints.reports import bp as reports_bp
    from app.blueprints.reviews import bp as reviews_bp
    from app.blueprints.service_library import bp as service_library_bp
    from app.blueprints.tasks import bp as tasks_bp
    from app.blueprints.team import bp as team_bp

    for bp in (
        auth_bp,
        agency_bp,
        properties_bp,
        imports_bp,
        availability_bp,
        offers_bp,
        clients_bp,
        bookings_bp,
        payments_bp,
        documents_bp,
        inquiries_bp,
        team_bp,
        public_bp,
        service_library_bp,
        tasks_bp,
        notifications_bp,
        dashboard_bp,
        owner_accounts_bp,
        reports_bp,
        reviews_bp,
    ):
        app.register_blueprint(bp)
