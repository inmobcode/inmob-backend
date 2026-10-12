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

    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
