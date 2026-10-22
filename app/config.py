import os
from datetime import timedelta


class Config:
    """Base config, read from environment variables (see .env.example)."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me-32-bytes-minimum")
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-jwt-secret-change-me-32-bytes-minimum")
    # No refresh flow is wired up on the frontend yet, so the access token
    # itself has to carry the whole session — 6 months, same as the refresh
    # token, so a user isn't logged out while it's still technically "valid".
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(days=180)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=180)

    # Falls back to a local SQLite file so the app runs out of the box
    # without Supabase credentials. Point DATABASE_URL at your Supabase
    # Postgres connection string for real use.
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///" + os.path.join(os.getcwd(), "dev.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    CORS_ORIGINS = os.environ.get(
        "CORS_ORIGINS", "http://localhost:3000,http://app.localhost:3000"
    ).split(",")

    # Transactional email through Resend. Without an API key, emails are only
    # written to the log, so local development needs no account.
    RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
    EMAIL_FROM = os.environ.get("EMAIL_FROM", "Tivvo <avisos@tivvo.app>")
    # Who gets notified when someone fills the landing's demo or contact form.
    TEAM_NOTIFICATION_EMAILS = [
        address.strip()
        for address in os.environ.get(
            "TEAM_NOTIFICATION_EMAILS", "facugirardi22@gmail.com,alejo.voyrnet31@gmail.com"
        ).split(",")
        if address.strip()
    ]
    # The dashboard itself: used to build login/inbox links inside emails.
    # It lives on the app subdomain (see frontend/src/proxy.ts).
    FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://app.localhost:3000")
    # Client-facing pages (booking/offer links, the agency's public site) live
    # on the apex domain instead — never the app subdomain above.
    PUBLIC_SITE_URL = os.environ.get("PUBLIC_SITE_URL", "http://localhost:3000")

    # The property importer refuses URLs that point at internal addresses (SSRF
    # guard). Local development needs it off to read a feed served from
    # localhost; never set this in production.
    IMPORT_ALLOW_PRIVATE_URLS = os.environ.get("IMPORT_ALLOW_PRIVATE_URLS") == "1"
