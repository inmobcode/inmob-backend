def _register(client, email="owner@demo.com"):
    return client.post(
        "/api/auth/register",
        json={
            "agencyName": "Agencia Demo",
            "name": "Owner",
            "email": email,
            "password": "password123",
        },
    )


def test_register_creates_agency_and_owner(client):
    res = _register(client)
    assert res.status_code == 201
    body = res.get_json()
    assert body["user"]["role"] == "OWNER"
    assert body["accessToken"]
    assert body["refreshToken"]


def test_register_duplicate_email_is_rejected(client):
    _register(client)
    res = _register(client)
    assert res.status_code == 409


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
    reg_b = client.post(
        "/api/auth/register",
        json={"agencyName": "Agencia B", "name": "Owner B", "email": "b@demo.com", "password": "password123"},
    ).get_json()
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
    client.post(
        "/api/auth/register",
        json={"agencyName": "Agencia B", "name": "Owner B", "email": "b@demo.com", "password": "password123"},
    )
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
