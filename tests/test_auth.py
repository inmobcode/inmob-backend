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
