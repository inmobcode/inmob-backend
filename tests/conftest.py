import re
from unittest.mock import patch

import pytest

from app import create_app
from app.config import Config
from app.extensions import db


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    BILLING_ENABLED = False


SEND_EMAIL = "app.services.auth_service.email_service.send_email"


def sign_up(
    client,
    *,
    agency_name="Agencia Demo",
    name="Owner",
    email="owner@demo.com",
    password="password123",
    plan=None,
):
    """Registers an agency and verifies the email with the code that was mailed.
    Returns the verification response, which carries the session."""
    body = {"agencyName": agency_name, "name": name, "email": email, "password": password}
    if plan:
        body["plan"] = plan
    with patch(SEND_EMAIL) as send:
        res = client.post("/api/auth/register", json=body)
    assert res.status_code == 201, res.get_json()
    code = re.search(r">(\d{6})</p>", send.call_args.args[2]).group(1)
    return client.post("/api/auth/email/verify", json={"email": email, "code": code})


@pytest.fixture()
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def register_agency(client):
    def _register(agency_name="Agencia Demo", email="owner@demo.com", plan="pro"):
        body = sign_up(client, agency_name=agency_name, email=email, plan=plan).get_json()
        return {
            "access_token": body["accessToken"],
            "agency_id": body["user"]["agencyId"],
            "headers": {"Authorization": f"Bearer {body['accessToken']}"},
        }

    return _register
