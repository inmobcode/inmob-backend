import pytest

from app import create_app
from app.config import Config
from app.extensions import db


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    BILLING_ENABLED = False


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
        res = client.post(
            "/api/auth/register",
            json={
                "agencyName": agency_name,
                "name": "Owner",
                "email": email,
                "password": "password123",
                "plan": plan,
            },
        )
        body = res.get_json()
        return {
            "access_token": body["accessToken"],
            "agency_id": body["user"]["agencyId"],
            "headers": {"Authorization": f"Bearer {body['accessToken']}"},
        }

    return _register
