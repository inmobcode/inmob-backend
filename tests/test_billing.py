import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app import create_app
from app.config import Config
from app.extensions import db
from app.models import Agency
from app.services import billing_service


# The real one, before the autouse fixture below replaces it.
REAL_FINGERPRINT = billing_service._card_fingerprint


class BillingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    BILLING_ENABLED = True
    PADDLE_ENV = "sandbox"
    PADDLE_API_KEY = "pdl_test"
    PADDLE_CLIENT_TOKEN = "test_token"
    PADDLE_WEBHOOK_SECRET = "pdl_ntfset_secret"
    PADDLE_PRICE_PRO = "pri_pro"
    PADDLE_PRICE_TRIAL = "pri_trial"


@pytest.fixture()
def billed_app():
    app = create_app(BillingConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture(autouse=True)
def card():
    """Every test pays with its own card unless it says otherwise (no call to Paddle)."""
    counter = iter(range(1000))
    with patch.object(billing_service, "_card_fingerprint", side_effect=lambda sub: f"fp_{next(counter)}") as mock:
        yield mock


@pytest.fixture()
def billed(billed_app):
    return billed_app.test_client()


@pytest.fixture()
def paddle():
    """Stands in for Paddle's API: answers by (method, path) from `routes`, and records every call."""

    class Fake:
        routes: dict = {}
        calls: list = []

        def __call__(self, method, path, *, body=None, params=None):
            self.calls.append((method, path, body))
            answer = self.routes.get((method, path))
            if answer is None:
                raise AssertionError(f"unexpected Paddle call {method} {path}")
            if isinstance(answer, Exception):
                raise answer
            return answer

    fake = Fake()
    fake.routes, fake.calls = {}, []
    with patch.object(billing_service, "_request", fake):
        yield fake


def _register(client, plan=None, email="owner@demo.com"):
    body = {"agencyName": "Agencia", "name": "Owner", "email": email, "password": "password123"}
    if plan:
        body["plan"] = plan
    res = client.post("/api/auth/register", json=body)
    assert res.status_code == 201
    data = res.get_json()
    return {"Authorization": f"Bearer {data['accessToken']}"}, data["user"]["agencyId"]


def test_without_billing_the_trial_starts_with_access(client, register_agency):
    agency = register_agency(plan="trial")
    body = client.get("/api/billing/status", headers=agency["headers"]).get_json()
    assert body["status"] == "TRIALING"
    assert body["plan"] == "trial"
    assert body["features"]["import"] is False


def test_without_billing_pro_has_the_import_tool(client):
    res = client.post(
        "/api/auth/register",
        json={"agencyName": "Agencia", "name": "Owner", "email": "p@demo.com", "password": "password123", "plan": "pro"},
    )
    headers = {"Authorization": f"Bearer {res.get_json()['accessToken']}"}
    body = client.get("/api/billing/status", headers=headers).get_json()
    assert (body["status"], body["plan"], body["features"]["import"]) == ("ACTIVE", "pro", True)


def test_register_rejects_enterprise(client):
    res = client.post(
        "/api/auth/register",
        json={"agencyName": "Agencia", "name": "Owner", "email": "e@demo.com", "password": "password123", "plan": "enterprise"},
    )
    assert res.status_code == 400


def test_trial_cannot_use_the_import_tool(client, register_agency):
    agency = register_agency(plan="trial")
    assert client.get("/api/imports/fields", headers=agency["headers"]).status_code == 403


def test_pro_can_use_the_import_tool(client, register_agency):
    agency = register_agency()
    assert client.get("/api/imports/fields", headers=agency["headers"]).status_code == 200


def test_new_agency_is_locked_until_it_pays(billed):
    headers, _ = _register(billed, "trial")
    assert billed.get("/api/properties/", headers=headers).status_code == 402
    # Signing in, the plan screens and the public pages stay open.
    assert billed.get("/api/billing/status", headers=headers).get_json()["status"] == "INCOMPLETE"
    assert billed.get("/api/auth/me", headers=headers).status_code == 200


def test_status_gives_the_browser_what_paddlejs_needs(billed):
    headers, _ = _register(billed, "trial")
    body = billed.get("/api/billing/status", headers=headers).get_json()
    assert body["paddle"] == {"clientToken": "test_token", "environment": "sandbox"}
    assert "pdl_test" not in json.dumps(body)


@pytest.mark.parametrize("plan, price", [("trial", "pri_trial"), ("pro", "pri_pro")])
def test_checkout_creates_the_transaction_for_the_plan(billed, paddle, plan, price):
    headers, agency_id = _register(billed, plan)
    paddle.routes = {
        ("POST", "/customers"): {"id": "ctm_1"},
        ("POST", "/transactions"): {"id": "txn_1"},
    }
    res = billed.post("/api/billing/checkout", json={"plan": plan}, headers=headers)
    assert res.get_json() == {"checkout": {"transactionId": "txn_1", "clientToken": "test_token", "environment": "sandbox"}}
    _, _, body = next(call for call in paddle.calls if call[1] == "/transactions")
    assert body["items"] == [{"price_id": price, "quantity": 1}]
    assert body["customer_id"] == "ctm_1"
    # What is bought, and for whom, is decided here: the browser can't change it.
    assert body["custom_data"] == {"agency_id": agency_id, "plan": plan}


def test_checkout_reuses_the_customer_paddle_already_has(billed, paddle):
    headers, _ = _register(billed, "pro")
    paddle.routes = {
        ("POST", "/customers"): billing_service.PaddleAPIError(409, "customer_already_exists: customer of id ctm_old exists"),
        ("POST", "/transactions"): {"id": "txn_1"},
    }
    assert billed.post("/api/billing/checkout", json={"plan": "pro"}, headers=headers).status_code == 200
    _, _, body = next(call for call in paddle.calls if call[1] == "/transactions")
    assert body["customer_id"] == "ctm_old"


def test_checkout_rejects_enterprise(billed):
    headers, _ = _register(billed)
    assert billed.post("/api/billing/checkout", json={"plan": "enterprise"}, headers=headers).status_code == 400


def _subscription(status, sub_id="sub_1", trial_end=None, customer="ctm_1"):
    items = [{"trial_dates": {"starts_at": "2030-01-01T00:00:00Z", "ends_at": trial_end}}] if trial_end else []
    return {"id": sub_id, "status": status, "customer_id": customer, "items": items, "next_billed_at": trial_end}


def _transaction(agency_id, subscription_id="sub_1"):
    return {"custom_data": {"agency_id": agency_id}, "subscription_id": subscription_id}


def test_confirming_a_trial_checkout_unlocks_without_import(billed, paddle):
    headers, agency_id = _register(billed, "trial")
    paddle.routes = {
        ("GET", "/transactions/txn_1"): _transaction(agency_id),
        ("GET", "/subscriptions/sub_1"): _subscription("trialing", trial_end="2030-01-08T00:00:00Z"),
    }
    res = billed.post("/api/billing/confirm", json={"transactionId": "txn_1"}, headers=headers)
    body = res.get_json()
    assert (body["status"], body["plan"], body["features"]["import"]) == ("TRIALING", "trial", False)
    assert body["trialEndsAt"].startswith("2030-01-08")
    assert billed.get("/api/properties/", headers=headers).status_code == 200


def test_confirm_refuses_another_agencys_transaction(billed, paddle):
    headers, _ = _register(billed)
    paddle.routes = {("GET", "/transactions/txn_1"): _transaction("someone-else")}
    assert billed.post("/api/billing/confirm", json={"transactionId": "txn_1"}, headers=headers).status_code == 403


def test_confirm_waits_for_a_payment_that_is_not_complete(billed, paddle):
    headers, agency_id = _register(billed)
    paddle.routes = {("GET", "/transactions/txn_1"): _transaction(agency_id, subscription_id=None)}
    assert billed.post("/api/billing/confirm", json={"transactionId": "txn_1"}, headers=headers).status_code == 409


def test_portal_opens_paddles_customer_portal(billed, billed_app, paddle):
    headers, agency_id = _register(billed, "pro")
    agency = db.session.get(Agency, agency_id)
    agency.paddle_customer_id, agency.paddle_subscription_id = "ctm_1", "sub_1"
    db.session.commit()
    paddle.routes = {
        ("POST", "/customers/ctm_1/portal-sessions"): {"urls": {"general": {"overview": "https://portal.paddle.test/x"}}}
    }
    res = billed.post("/api/billing/portal", headers=headers)
    assert res.get_json() == {"url": "https://portal.paddle.test/x"}
    assert paddle.calls[0][2] == {"subscription_ids": ["sub_1"]}


def _event(kind, subscription):
    return {"event_type": kind, "data": subscription}


def _post_webhook(billed, event, *, secret="pdl_ntfset_secret", ts=None):
    raw = json.dumps(event).encode()
    ts = str(int(time.time()) if ts is None else ts)
    signature = hmac.new(secret.encode(), ts.encode() + b":" + raw, hashlib.sha256).hexdigest()
    return billed.post(
        "/api/billing/webhook", data=raw, headers={"Paddle-Signature": f"ts={ts};h1={signature}"}
    )


def test_webhook_rejects_a_bad_signature(billed):
    assert _post_webhook(billed, _event("subscription.updated", {}), secret="wrong").status_code == 400
    assert billed.post("/api/billing/webhook", data=b"{}").status_code == 400


def test_webhook_rejects_an_old_event(billed):
    old = int(time.time()) - 3600
    assert _post_webhook(billed, _event("subscription.updated", {}), ts=old).status_code == 400


def _linked(billed, plan="trial", status="TRIALING"):
    headers, agency_id = _register(billed, plan)
    agency = db.session.get(Agency, agency_id)
    agency.paddle_customer_id, agency.paddle_subscription_id = "ctm_1", "sub_1"
    agency.subscription_status = status
    db.session.commit()
    return headers, agency_id


def test_the_trial_becomes_pro_when_paddle_charges(billed):
    headers, _ = _linked(billed)
    assert _post_webhook(billed, _event("subscription.activated", _subscription("active"))).status_code == 200
    body = billed.get("/api/billing/status", headers=headers).get_json()
    assert (body["status"], body["plan"], body["features"]["import"]) == ("ACTIVE", "pro", True)


def test_a_canceled_subscription_locks_the_agency(billed):
    headers, _ = _linked(billed, "pro", "ACTIVE")
    _post_webhook(billed, _event("subscription.canceled", _subscription("canceled")))
    assert billed.get("/api/properties/", headers=headers).status_code == 402


def test_an_old_subscription_does_not_override_the_current_one(billed):
    headers, _ = _linked(billed, "pro", "ACTIVE")
    _post_webhook(billed, _event("subscription.canceled", _subscription("canceled", sub_id="sub_old")))
    assert billed.get("/api/billing/status", headers=headers).get_json()["status"] == "ACTIVE"


def test_events_that_are_not_about_subscriptions_are_ignored(billed):
    assert _post_webhook(billed, _event("transaction.completed", {"id": "txn_1"})).status_code == 200


def _trial_agency(billed, email, sub_id, customer):
    headers, agency_id = _register(billed, "trial", email=email)
    agency = db.session.get(Agency, agency_id)
    agency.paddle_customer_id = customer
    db.session.commit()
    return headers, agency_id


def test_the_same_card_cannot_start_a_second_trial(billed, paddle, card):
    card.side_effect = lambda sub: "fp_same"
    first, _ = _trial_agency(billed, "a@demo.com", "sub_a", "ctm_a")
    _post_webhook(billed, _event("subscription.created", _subscription("trialing", "sub_a", "2030-01-08T00:00:00Z", "ctm_a")))
    assert billed.get("/api/billing/status", headers=first).get_json()["status"] == "TRIALING"

    second, _ = _trial_agency(billed, "b@demo.com", "sub_b", "ctm_b")
    paddle.routes = {("POST", "/subscriptions/sub_b/cancel"): {}}
    _post_webhook(billed, _event("subscription.created", _subscription("trialing", "sub_b", "2030-01-08T00:00:00Z", "ctm_b")))
    body = billed.get("/api/billing/status", headers=second).get_json()
    assert body["status"] == "CANCELED"
    assert body["trialAvailable"] is False
    assert paddle.calls == [("POST", "/subscriptions/sub_b/cancel", {"effective_from": "immediately"})]
    assert billed.get("/api/properties/", headers=second).status_code == 402


def test_the_same_agency_keeps_its_trial_when_paddle_repeats_the_event(billed, card):
    card.side_effect = lambda sub: "fp_same"
    headers, _ = _trial_agency(billed, "a@demo.com", "sub_a", "ctm_a")
    event = _event("subscription.created", _subscription("trialing", "sub_a", "2030-01-08T00:00:00Z", "ctm_a"))
    _post_webhook(billed, event)
    _post_webhook(billed, event)
    assert billed.get("/api/billing/status", headers=headers).get_json()["status"] == "TRIALING"


def test_an_agency_cannot_take_the_trial_twice(billed, paddle):
    headers, agency_id = _register(billed, "trial")
    db.session.get(Agency, agency_id).trial_used = True
    db.session.commit()
    assert billed.post("/api/billing/checkout", json={"plan": "trial"}, headers=headers).status_code == 409
    # Pro is still open to it.
    paddle.routes = {("POST", "/customers"): {"id": "ctm_1"}, ("POST", "/transactions"): {"id": "txn_1"}}
    assert billed.post("/api/billing/checkout", json={"plan": "pro"}, headers=headers).status_code == 200


def test_the_card_hash_ignores_case_and_never_holds_the_number(billed_app, paddle):
    card = {"type": "visa", "last4": "4242", "expiry_month": 1, "expiry_year": 2030, "cardholder_name": "Ana Pérez"}
    paddle.routes = {("GET", "/customers/ctm_1/payment-methods"): [{"card": card}]}
    first = REAL_FINGERPRINT({"id": "sub_1", "customer_id": "ctm_1"})
    card["cardholder_name"] = "  ANA PÉREZ "
    assert REAL_FINGERPRINT({"id": "sub_1", "customer_id": "ctm_1"}) == first
    card["last4"] = "1111"
    assert REAL_FINGERPRINT({"id": "sub_1", "customer_id": "ctm_1"}) != first
    assert len(first) == 64 and "4242" not in first


def test_a_card_that_cannot_be_read_does_not_block_the_trial(billed_app, paddle):
    paddle.routes = {("GET", "/customers/ctm_1/payment-methods"): billing_service.BillingError("down", 502)}
    assert REAL_FINGERPRINT({"id": "sub_1", "customer_id": "ctm_1"}) is None


def _notifications(billed, headers):
    return billed.get("/api/notifications/", headers=headers).get_json()["items"]


def test_the_bell_reminds_the_owners_when_the_trial_is_close_to_ending(billed):
    headers, agency_id = _linked(billed)
    agency = db.session.get(Agency, agency_id)
    agency.trial_ends_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=2)
    db.session.commit()

    _notifications(billed, headers)
    items = _notifications(billed, headers)  # opening the bell twice must not double the notice
    assert [item["type"] for item in items] == ["TRIAL_ENDING"]
    assert items[0]["params"] == {"date": agency.trial_ends_at.date().isoformat()}
    assert items[0]["link"] == "/settings"


def test_the_bell_stays_quiet_while_the_trial_is_far_from_ending(billed):
    headers, agency_id = _linked(billed)
    db.session.get(Agency, agency_id).trial_ends_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=6)
    db.session.commit()
    assert _notifications(billed, headers) == []


def test_a_declined_card_warns_the_owner_once(billed):
    headers, _ = _linked(billed)
    past_due = _event("subscription.past_due", _subscription("past_due"))
    _post_webhook(billed, past_due)
    _post_webhook(billed, past_due)

    assert [item["type"] for item in _notifications(billed, headers)] == ["PAYMENT_FAILED"]
    # Still inside, while Paddle retries the card.
    assert billed.get("/api/properties/", headers=headers).status_code == 200
