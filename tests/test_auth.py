import re
from datetime import timedelta
from unittest.mock import patch

from app.extensions import db
from app.models import User
from tests.conftest import SEND_EMAIL, sign_up


def _register(client, email="owner@demo.com"):
    """A verified account: the response is the session."""
    return sign_up(client, email=email)


def _sign_up_unverified(client, email="owner@demo.com", password="password123", headers=None):
    """Registers without verifying; returns the response and the code that was mailed."""
    with patch(SEND_EMAIL) as send:
        res = client.post(
            "/api/auth/register",
            json={"agencyName": "Agencia Demo", "name": "Owner", "email": email, "password": password},
            headers=headers or {},
        )
    code = re.search(r">(\d{6})</p>", send.call_args.args[2]).group(1) if send.called else None
    return res, code, send


def test_register_creates_an_unverified_account_without_a_session(client):
    res, code, send = _sign_up_unverified(client)
    assert res.status_code == 201
    assert res.get_json() == {"email": "owner@demo.com"}
    assert send.call_args.args[0] == ["owner@demo.com"]
    assert code in send.call_args.args[1]


def test_verifying_the_code_opens_the_session(client):
    _, code, _ = _sign_up_unverified(client)
    res = client.post("/api/auth/email/verify", json={"email": "owner@demo.com", "code": code})
    assert res.status_code == 200
    body = res.get_json()
    assert body["user"]["role"] == "OWNER"
    assert body["accessToken"]
    assert body["refreshToken"]

    # The code works once.
    again = client.post("/api/auth/email/verify", json={"email": "owner@demo.com", "code": code})
    assert again.status_code == 400


def test_login_is_refused_until_the_email_is_verified(client):
    _, code, _ = _sign_up_unverified(client)
    creds = {"email": "owner@demo.com", "password": "password123"}
    assert client.post("/api/auth/login", json=creds).status_code == 403

    # A wrong password still says so: the 403 doesn't reveal which emails are signed up.
    wrong = client.post("/api/auth/login", json={**creds, "password": "otra-clave"})
    assert wrong.status_code == 401

    client.post("/api/auth/email/verify", json={"email": "owner@demo.com", "code": code})
    assert client.post("/api/auth/login", json=creds).status_code == 200


def test_a_wrong_code_does_not_verify(client):
    _, code, _ = _sign_up_unverified(client)
    wrong = "000000" if code != "000000" else "111111"
    res = client.post("/api/auth/email/verify", json={"email": "owner@demo.com", "code": wrong})
    assert res.status_code == 400
    assert User.query.filter_by(email="owner@demo.com").one().email_verified is False


def test_verification_code_is_burned_after_too_many_wrong_tries(client):
    from app.services.auth_service import VERIFY_CODE_MAX_ATTEMPTS

    _, code, _ = _sign_up_unverified(client)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(VERIFY_CODE_MAX_ATTEMPTS):
        res = client.post("/api/auth/email/verify", json={"email": "owner@demo.com", "code": wrong})
        assert res.status_code == 400

    res = client.post("/api/auth/email/verify", json={"email": "owner@demo.com", "code": code})
    assert res.status_code == 400


def test_expired_verification_code_is_rejected(client):
    _, code, _ = _sign_up_unverified(client)
    user = User.query.filter_by(email="owner@demo.com").one()
    user.verify_code_expires_at -= timedelta(hours=2)
    db.session.commit()

    res = client.post("/api/auth/email/verify", json={"email": "owner@demo.com", "code": code})
    assert res.status_code == 400


def test_resend_sends_a_new_code_but_not_right_away(client):
    _, first, _ = _sign_up_unverified(client)

    with patch(SEND_EMAIL) as send:
        res = client.post("/api/auth/email/resend", json={"email": "owner@demo.com"})
    assert res.status_code == 204
    assert not send.called  # one was just sent

    user = User.query.filter_by(email="owner@demo.com").one()
    user.verify_code_expires_at -= timedelta(minutes=5)
    db.session.commit()
    with patch(SEND_EMAIL) as send:
        client.post("/api/auth/email/resend", json={"email": "owner@demo.com"})
    second = re.search(r">(\d{6})</p>", send.call_args.args[2]).group(1)

    res = client.post("/api/auth/email/verify", json={"email": "owner@demo.com", "code": second})
    assert res.status_code == 200


def test_resend_answers_the_same_for_unknown_and_verified_emails(client):
    _register(client)
    for email in ("nadie@demo.com", "owner@demo.com"):
        with patch(SEND_EMAIL) as send:
            res = client.post("/api/auth/email/resend", json={"email": email})
        assert res.status_code == 204
        assert not send.called


def test_verification_email_goes_out_in_the_page_language(client):
    _, _, send = _sign_up_unverified(client, headers={"X-Locale": "en"})
    assert "email verification code" in send.call_args.args[1]
    assert send.call_args.kwargs["locale"] == "en"


def test_signing_up_again_before_verifying_starts_over(client):
    first, _, _ = _sign_up_unverified(client, password="clave-vieja-1")
    assert first.status_code == 201
    user = User.query.filter_by(email="owner@demo.com").one()
    user.verify_code_expires_at -= timedelta(minutes=5)  # past the resend wait
    db.session.commit()

    second, code, _ = _sign_up_unverified(client, password="clave-nueva-1")
    assert second.status_code == 201
    assert User.query.filter_by(email="owner@demo.com").count() == 1

    client.post("/api/auth/email/verify", json={"email": "owner@demo.com", "code": code})
    assert client.post(
        "/api/auth/login", json={"email": "owner@demo.com", "password": "clave-nueva-1"}
    ).status_code == 200
    assert client.post(
        "/api/auth/login", json={"email": "owner@demo.com", "password": "clave-vieja-1"}
    ).status_code == 401


def test_resetting_the_password_also_verifies_the_email(client):
    _sign_up_unverified(client)
    code, _ = _request_code(client)
    res = client.post(
        "/api/auth/password/reset",
        json={"email": "owner@demo.com", "code": code, "password": "nueva-clave-1"},
    )
    assert res.status_code == 204
    login = client.post("/api/auth/login", json={"email": "owner@demo.com", "password": "nueva-clave-1"})
    assert login.status_code == 200


def test_register_creates_agency_and_owner(client):
    res = _register(client)
    assert res.status_code == 200
    body = res.get_json()
    assert body["user"]["role"] == "OWNER"
    assert body["user"]["agencySlug"] == "agencia-demo"
    assert body["accessToken"]
    assert body["refreshToken"]


def test_register_duplicate_email_is_rejected(client):
    _register(client)
    res, _, send = _sign_up_unverified(client)
    assert res.status_code == 409
    assert not send.called


def test_login_wrong_password_is_rejected(client):
    _register(client)
    res = client.post(
        "/api/auth/login", json={"email": "owner@demo.com", "password": "wrong"}
    )
    assert res.status_code == 401


def test_login_and_me(client):
    _register(client)
    login_res = client.post(
        "/api/auth/login", json={"email": "owner@demo.com", "password": "password123"}
    )
    token = login_res.get_json()["accessToken"]

    me_res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    assert me_res.get_json()["email"] == "owner@demo.com"


def test_me_without_token_is_unauthorized(client):
    res = client.get("/api/auth/me")
    assert res.status_code == 401


def test_refresh_issues_new_access_token(client):
    reg = _register(client).get_json()
    res = client.post(
        "/api/auth/refresh",
        headers={"Authorization": f"Bearer {reg['refreshToken']}"},
    )
    assert res.status_code == 200
    assert res.get_json()["accessToken"]


def test_register_includes_agency_slug_claim(client):
    import flask_jwt_extended

    reg = _register(client).get_json()
    app = client.application
    with app.test_request_context(headers={"Authorization": f"Bearer {reg['accessToken']}"}):
        flask_jwt_extended.verify_jwt_in_request()
        claims = flask_jwt_extended.get_jwt()
    assert claims["agency_slug"] == "agencia-demo"


def test_my_agencies_lists_a_single_agency_after_register(client):
    reg = _register(client).get_json()
    res = client.get(
        "/api/auth/me/agencies", headers={"Authorization": f"Bearer {reg['accessToken']}"}
    )
    assert res.status_code == 200
    agencies = res.get_json()
    assert len(agencies) == 1
    assert agencies[0]["slug"] == "agencia-demo"
    assert agencies[0]["role"] == "OWNER"


def test_switch_agency_rejects_agency_without_membership(client):
    reg_a = _register(client, email="a@demo.com").get_json()
    reg_b = sign_up(client, agency_name="Agencia B", name="Owner B", email="b@demo.com").get_json()
    other_agency_id = client.get(
        "/api/auth/me/agencies",
        headers={"Authorization": f"Bearer {reg_b['accessToken']}"},
    ).get_json()[0]["id"]

    res = client.post(
        "/api/auth/switch-agency",
        headers={"Authorization": f"Bearer {reg_a['accessToken']}"},
        json={"agencyId": other_agency_id},
    )
    assert res.status_code == 403


def test_switch_agency_succeeds_for_a_real_membership(client):
    owner_a = _register(client, email="a@demo.com").get_json()
    sign_up(client, agency_name="Agencia B", name="Owner B", email="b@demo.com")
    owner_b_token = client.post(
        "/api/auth/login", json={"email": "b@demo.com", "password": "password123"}
    ).get_json()["accessToken"]
    # a@demo.com already has an account (Agencia A's owner) — inviting it
    # into Agencia B just links the existing account, no email needed.
    client.post(
        "/api/team/",
        headers={"Authorization": f"Bearer {owner_b_token}"},
        json={"name": "Owner A", "email": "a@demo.com", "role": "ADMIN"},
    )

    agencies = client.get(
        "/api/auth/me/agencies", headers={"Authorization": f"Bearer {owner_a['accessToken']}"}
    ).get_json()
    agencia_b = next(a for a in agencies if a["name"] == "Agencia B")

    res = client.post(
        "/api/auth/switch-agency",
        headers={"Authorization": f"Bearer {owner_a['accessToken']}"},
        json={"agencyId": agencia_b["id"]},
    )
    assert res.status_code == 200
    assert res.get_json()["user"]["role"] == "ADMIN"


RESET_SEND = "app.services.auth_service.email_service.send_email"


def _request_code(client, email="owner@demo.com", headers=None):
    """Asks for a recovery code and returns it, read from the email that went out."""
    from unittest.mock import patch

    with patch(RESET_SEND) as send:
        res = client.post("/api/auth/password/forgot", json={"email": email}, headers=headers or {})
    assert res.status_code == 204
    if not send.called:
        return None, send
    html = send.call_args.args[2]
    import re

    return re.search(r">(\d{6})</p>", html).group(1), send


def test_forgot_password_answers_the_same_for_unknown_emails(client):
    code, send = _request_code(client, email="nadie@demo.com")
    assert code is None
    assert not send.called


def test_reset_password_with_the_emailed_code(client):
    _register(client)
    code, send = _request_code(client)
    assert send.call_args.args[0] == ["owner@demo.com"]
    assert code in send.call_args.args[1]

    res = client.post(
        "/api/auth/password/reset",
        json={"email": "owner@demo.com", "code": code, "password": "nueva-clave-1"},
    )
    assert res.status_code == 204

    login = client.post("/api/auth/login", json={"email": "owner@demo.com", "password": "nueva-clave-1"})
    assert login.status_code == 200

    # The code works once.
    again = client.post(
        "/api/auth/password/reset",
        json={"email": "owner@demo.com", "code": code, "password": "otra-clave-2"},
    )
    assert again.status_code == 400


def test_reset_code_email_goes_out_in_the_page_language(client):
    _register(client)
    _, send = _request_code(client, headers={"X-Locale": "en"})
    assert "password recovery code" in send.call_args.args[1]
    assert send.call_args.kwargs["locale"] == "en"


def test_reset_code_is_burned_after_too_many_wrong_tries(client):
    from app.services.auth_service import RESET_CODE_MAX_ATTEMPTS

    _register(client)
    code, _ = _request_code(client)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(RESET_CODE_MAX_ATTEMPTS):
        res = client.post(
            "/api/auth/password/reset",
            json={"email": "owner@demo.com", "code": wrong, "password": "nueva-clave-1"},
        )
        assert res.status_code == 400

    res = client.post(
        "/api/auth/password/reset",
        json={"email": "owner@demo.com", "code": code, "password": "nueva-clave-1"},
    )
    assert res.status_code == 400


def test_expired_reset_code_is_rejected(client, app):
    from datetime import timedelta

    from app.extensions import db
    from app.models import User

    _register(client)
    code, _ = _request_code(client)
    user = User.query.filter_by(email="owner@demo.com").one()
    user.reset_code_expires_at -= timedelta(hours=1)
    db.session.commit()

    res = client.post(
        "/api/auth/password/reset",
        json={"email": "owner@demo.com", "code": code, "password": "nueva-clave-1"},
        headers={"X-Locale": "es"},
    )
    assert res.status_code == 400
    assert res.get_json()["message"].startswith("El código no es correcto")


def test_a_second_code_is_not_sent_right_away(client):
    _register(client)
    _request_code(client)
    code, send = _request_code(client)
    assert code is None
    assert not send.called
