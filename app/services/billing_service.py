"""Subscriptions: the free trial and the Pro plan, both sold through Paddle.

Paddle is the merchant of record: it charges the card, issues the invoice and
handles the taxes. The flow is: we create a Paddle customer for the agency and a
transaction for the chosen price (so what is bought and for whom is decided here,
not in the browser); Paddle.js opens that transaction as a checkout; Paddle tells
us what happened (the return from checkout and the webhook), and
`apply_subscription` is the only place that moves an agency between states.

The free trial is a Pro price with a 14-day trial that asks for a card: Paddle
charges nothing for the trial and then starts billing Pro by itself.
"""
import hashlib
import hmac
import re
import time
from datetime import datetime, timedelta, timezone

import requests
from flask import current_app

from app.extensions import db
from app.models import Agency, TrialCard
from app.services import feed

# Statuses that can use the app. PAST_DUE keeps working while Paddle retries the card.
ACCESS_STATUSES = ("TRIALING", "ACTIVE", "PAST_DUE")

_PADDLE_STATUS = {
    "trialing": "TRIALING",
    "active": "ACTIVE",
    "past_due": "PAST_DUE",
    "paused": "CANCELED",
    "canceled": "CANCELED",
}

API_URLS = {"sandbox": "https://sandbox-api.paddle.com", "production": "https://api.paddle.com"}
# How many days before the trial ends the owners get a heads-up in the bell.
TRIAL_REMINDER_DAYS = 3
WEBHOOK_TOLERANCE_SECONDS = 300


class BillingError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def enabled() -> bool:
    return bool(current_app.config["BILLING_ENABLED"])


def has_access(agency: Agency) -> bool:
    return not enabled() or agency.subscription_status in ACCESS_STATUSES


def features(agency: Agency) -> dict:
    """What the plan includes. The free trial is full access except the data-migration tool."""
    return {"import": agency.plan != "trial"}


def checkout_config() -> dict | None:
    """What Paddle.js needs in the browser (public values only)."""
    token = current_app.config["PADDLE_CLIENT_TOKEN"]
    if not enabled() or not token:
        return None
    return {"clientToken": token, "environment": current_app.config["PADDLE_ENV"]}


def status_payload(agency: Agency) -> dict:
    return {
        "plan": agency.plan,
        "status": agency.subscription_status,
        "trialEndsAt": agency.trial_ends_at.isoformat() + "Z" if agency.trial_ends_at else None,
        "billingEnabled": enabled(),
        "trialAvailable": not agency.trial_used,
        "features": features(agency),
        "paddle": checkout_config(),
    }


def start_without_billing(agency: Agency) -> None:
    """Billing off (local development): the chosen plan starts right away."""
    agency.subscription_status = "TRIALING" if agency.plan == "trial" else "ACTIVE"


# --- Paddle API -------------------------------------------------------------


def _request(method: str, path: str, *, body: dict | None = None, params: dict | None = None) -> dict:
    """One call to Paddle's API; returns its `data`. Network and API failures become BillingError."""
    key = current_app.config["PADDLE_API_KEY"]
    if not key:
        raise BillingError("Billing isn't configured", 503)
    base = API_URLS.get(current_app.config["PADDLE_ENV"], API_URLS["sandbox"])
    try:
        response = requests.request(
            method,
            f"{base}{path}",
            json=body,
            params=params,
            headers={"Authorization": f"Bearer {key}", "Paddle-Version": "1"},
            timeout=15,
        )
    except requests.RequestException as err:
        current_app.logger.exception("Paddle %s %s failed", method, path)
        raise BillingError("We couldn't start the payment. Try again in a few minutes.", 502) from err
    if response.status_code >= 400:
        detail = ""
        try:
            error = response.json().get("error", {})
            detail = f"{error.get('code')}: {error.get('detail')}"
        except ValueError:
            pass
        current_app.logger.error("Paddle %s %s -> %s %s", method, path, response.status_code, detail)
        raise PaddleAPIError(response.status_code, detail)
    return response.json().get("data")


class PaddleAPIError(BillingError):
    def __init__(self, status: int, detail: str):
        super().__init__("We couldn't start the payment. Try again in a few minutes.", 502)
        self.paddle_status = status
        self.detail = detail


def _customer_for(agency: Agency, email: str) -> str:
    if agency.paddle_customer_id:
        return agency.paddle_customer_id
    try:
        customer = _request(
            "POST", "/customers", body={"email": email, "name": agency.name, "custom_data": {"agency_id": agency.id}}
        )
        customer_id = customer["id"]
    except PaddleAPIError as err:
        # Paddle keeps one customer per email: if this person already had one, reuse it.
        match = re.search(r"ctm_[a-z0-9]+", err.detail) if err.paddle_status == 409 else None
        if match is None:
            raise
        customer_id = match.group(0)
    agency.paddle_customer_id = customer_id
    db.session.commit()
    return customer_id


def create_checkout(agency: Agency, plan: str, email: str) -> str:
    """Creates the transaction for the chosen plan and returns its id; the browser opens it with
    Paddle.js. The card is always asked for, also for the trial, so the first charge happens
    without anyone coming back."""
    if agency.subscription_status in ("TRIALING", "ACTIVE", "PAST_DUE"):
        raise BillingError("This agency already has a subscription", 409)
    if plan == "trial" and agency.trial_used:
        raise BillingError("The free trial was already used", 409)
    price = current_app.config["PADDLE_PRICE_TRIAL" if plan == "trial" else "PADDLE_PRICE_PRO"]
    if not price or not current_app.config["PADDLE_CLIENT_TOKEN"]:
        raise BillingError("Billing isn't configured", 503)

    transaction = _request(
        "POST",
        "/transactions",
        body={
            "items": [{"price_id": price, "quantity": 1}],
            "customer_id": _customer_for(agency, email),
            "collection_mode": "automatic",
            "custom_data": {"agency_id": agency.id, "plan": plan},
        },
    )
    agency.plan = plan
    db.session.commit()
    return transaction["id"]


def create_portal(agency: Agency) -> str:
    """A temporary link to Paddle's customer portal: change the card, see invoices, cancel."""
    if not agency.paddle_customer_id:
        raise BillingError("This agency has no subscription to manage", 404)
    body = {"subscription_ids": [agency.paddle_subscription_id]} if agency.paddle_subscription_id else {}
    try:
        session = _request("POST", f"/customers/{agency.paddle_customer_id}/portal-sessions", body=body)
    except PaddleAPIError as err:
        raise BillingError("We couldn't open the billing portal.", 502) from err
    return session["urls"]["general"]["overview"]


def _end_trial_early(subscription_id: str) -> None:
    try:
        _request("POST", f"/subscriptions/{subscription_id}/cancel", body={"effective_from": "immediately"})
    except BillingError:
        current_app.logger.exception("Could not cancel the repeated trial %s", subscription_id)


# --- State ------------------------------------------------------------------


def _card_fingerprint(subscription: dict) -> str | None:
    """A hash of the card saved by the checkout (type, last four digits, expiry and holder), or None.
    Paddle gives no card fingerprint, so this is a best effort: the same physical card gives the same hash."""
    try:
        methods = _request("GET", f"/customers/{subscription['customer_id']}/payment-methods")
    except BillingError:
        current_app.logger.warning("Could not read the card behind subscription %s", subscription.get("id"))
        return None
    for method in methods or []:
        card = method.get("card") or {}
        if card.get("last4"):
            parts = (
                card.get("type"),
                card.get("last4"),
                card.get("expiry_month"),
                card.get("expiry_year"),
                (card.get("cardholder_name") or "").strip().lower(),
            )
            return hashlib.sha256("|".join(str(part) for part in parts).encode()).hexdigest()
    return None


def _trial_card_allowed(agency: Agency, subscription: dict) -> bool:
    """One free trial per card: a card that already started another agency's trial can't start this one.
    If the card can't be read the trial goes ahead rather than punishing a hiccup."""
    if TrialCard.query.filter_by(agency_id=agency.id).first() is not None:
        return True
    fingerprint = _card_fingerprint(subscription)
    if fingerprint is None:
        return True
    if TrialCard.query.filter_by(fingerprint=fingerprint).first() is not None:
        return False
    db.session.add(TrialCard(fingerprint=fingerprint, agency_id=agency.id))
    return True


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)


def _trial_end(subscription: dict) -> datetime | None:
    for item in subscription.get("items") or []:
        ends = (item.get("trial_dates") or {}).get("ends_at")
        if ends:
            return _parse_time(ends)
    return _parse_time(subscription.get("next_billed_at"))


def apply_subscription(agency: Agency, subscription: dict) -> None:
    """Brings the agency in line with a Paddle subscription."""
    previous = agency.subscription_status
    status = _PADDLE_STATUS.get(subscription["status"], "INCOMPLETE")
    agency.paddle_subscription_id = subscription["id"]
    agency.subscription_status = status
    agency.trial_ends_at = _trial_end(subscription) if status == "TRIALING" else agency.trial_ends_at
    # Trialing is the only state with the trial's limits: once Paddle charges, it's Pro.
    if status == "TRIALING":
        agency.plan = "trial"
        agency.trial_used = True
        if not _trial_card_allowed(agency, subscription):
            # The subscription is canceled, not charged: the agency can still pick Pro.
            agency.subscription_status = "CANCELED"
            _end_trial_early(subscription["id"])
    elif status in ("ACTIVE", "PAST_DUE"):
        agency.plan = "pro"
    db.session.commit()
    if status == "PAST_DUE" and previous != "PAST_DUE":
        feed.notify_payment_failed(agency)


def confirm_checkout(agency: Agency, transaction_id: str) -> None:
    """The person came back from Paddle: read the transaction instead of waiting for the webhook."""
    try:
        transaction = _request("GET", f"/transactions/{transaction_id}")
    except PaddleAPIError as err:
        raise BillingError("We couldn't verify the payment.", 502) from err
    if (transaction.get("custom_data") or {}).get("agency_id") != agency.id:
        raise BillingError("Forbidden", 403)
    subscription_id = transaction.get("subscription_id")
    if not subscription_id:
        raise BillingError("The payment isn't complete yet.", 409)
    apply_subscription(agency, _request("GET", f"/subscriptions/{subscription_id}"))


def maybe_remind_trial_end(agency: Agency) -> None:
    """Paddle sends no "trial ending" event, so the bell checks the date itself."""
    if agency.subscription_status != "TRIALING" or agency.trial_ends_at is None:
        return
    if agency.trial_ends_at - datetime.now(timezone.utc).replace(tzinfo=None) <= timedelta(days=TRIAL_REMINDER_DAYS):
        feed.notify_trial_ending(agency)


# --- Webhook ----------------------------------------------------------------


def verify_signature(raw_body: bytes, header: str) -> bool:
    """Paddle-Signature is `ts=<unix>;h1=<hex>` (h1 can repeat while a secret is rotated):
    the HMAC-SHA256 of `<ts>:<raw body>` with the endpoint's secret."""
    secret = current_app.config["PADDLE_WEBHOOK_SECRET"]
    if not secret or not header:
        return False
    pairs = [part.split("=", 1) for part in header.split(";") if "=" in part]
    timestamp = next((value for key, value in pairs if key == "ts"), None)
    signatures = [value for key, value in pairs if key == "h1"]
    if timestamp is None or not timestamp.isdigit() or not signatures:
        return False
    if abs(time.time() - int(timestamp)) > WEBHOOK_TOLERANCE_SECONDS:
        return False
    expected = hmac.new(secret.encode(), timestamp.encode() + b":" + raw_body, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, signature) for signature in signatures)


def _agency_of(subscription: dict) -> Agency | None:
    agency = Agency.query.filter_by(paddle_customer_id=subscription.get("customer_id")).first()
    if agency is None:
        agency = db.session.get(Agency, (subscription.get("custom_data") or {}).get("agency_id") or "")
    return agency


def handle_event(event: dict) -> None:
    kind = event.get("event_type", "")
    if not kind.startswith("subscription."):
        return
    subscription = event["data"]
    agency = _agency_of(subscription)
    if agency is None:
        return
    # An old subscription (replaced, or from an abandoned checkout) must not override the current one.
    if agency.paddle_subscription_id and agency.paddle_subscription_id != subscription["id"]:
        return
    if not agency.paddle_customer_id:
        agency.paddle_customer_id = subscription.get("customer_id")
    apply_subscription(agency, subscription)
