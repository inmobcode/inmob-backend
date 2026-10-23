from unittest.mock import patch


def _register(client, agency_name="Agencia Demo", email="owner@demo.com"):
    res = client.post(
        "/api/auth/register",
        json={"agencyName": agency_name, "name": "Owner", "email": email, "password": "password123"},
    )
    return res.get_json()["accessToken"]


EMAIL_TARGET = "app.services.team_service._send_invite_email"


def test_invite_creates_new_user_and_emails_temp_password(client):
    owner_token = _register(client)
    headers = {"Authorization": f"Bearer {owner_token}"}

    with patch(EMAIL_TARGET) as mock_send:
        res = client.post(
            "/api/team/",
            headers=headers,
            json={"name": "Agent One", "email": "agent1@demo.com", "role": "AGENT"},
        )
    assert res.status_code == 201
    body = res.get_json()
    assert body["linkedExisting"] is False
    assert body["role"] == "AGENT"
    mock_send.assert_called_once()
    to_email, name, agency, temp_password, locale = mock_send.call_args[0]
    assert to_email == "agent1@demo.com"
    assert agency.name == "Agencia Demo"

    login_res = client.post(
        "/api/auth/login", json={"email": "agent1@demo.com", "password": temp_password}
    )
    assert login_res.status_code == 200

    list_res = client.get("/api/team/", headers=headers)
    assert len(list_res.get_json()) == 2


def test_invite_links_existing_user_without_email(client):
    owner_a_token = _register(client, agency_name="Agencia A", email="a@demo.com")
    _register(client, agency_name="Agencia B", email="b@demo.com")

    with patch(EMAIL_TARGET) as mock_send:
        res = client.post(
            "/api/team/",
            headers={"Authorization": f"Bearer {owner_a_token}"},
            json={"name": "Owner B", "email": "b@demo.com", "role": "AGENT"},
        )
    assert res.status_code == 201
    assert res.get_json()["linkedExisting"] is True
    mock_send.assert_not_called()

    login_res = client.post(
        "/api/auth/login", json={"email": "b@demo.com", "password": "password123"}
    )
    assert login_res.status_code == 200

    agencies = client.get(
        "/api/auth/me/agencies", headers={"Authorization": f"Bearer {login_res.get_json()['accessToken']}"}
    ).get_json()
    assert {a["name"] for a in agencies} == {"Agencia A", "Agencia B"}


def test_invite_rejects_duplicate_membership(client):
    owner_token = _register(client)
    headers = {"Authorization": f"Bearer {owner_token}"}
    with patch(EMAIL_TARGET):
        client.post("/api/team/", headers=headers, json={"name": "Agent", "email": "agent1@demo.com", "role": "AGENT"})
        res = client.post("/api/team/", headers=headers, json={"name": "Agent", "email": "agent1@demo.com", "role": "AGENT"})
    assert res.status_code == 409


def test_cannot_assign_owner_role_via_team_invite(client):
    owner_token = _register(client)
    res = client.post(
        "/api/team/",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"name": "Sneaky", "email": "sneaky@demo.com", "role": "OWNER"},
    )
    assert res.status_code == 400


def test_agent_cannot_invite_or_list_members(client):
    owner_token = _register(client)
    with patch(EMAIL_TARGET) as mock_send:
        client.post(
            "/api/team/",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"name": "Agent One", "email": "agent1@demo.com", "role": "AGENT"},
        )
    temp_password = mock_send.call_args[0][3]
    agent_token = client.post(
        "/api/auth/login", json={"email": "agent1@demo.com", "password": temp_password}
    ).get_json()["accessToken"]
    agent_headers = {"Authorization": f"Bearer {agent_token}"}

    assert client.get("/api/team/", headers=agent_headers).status_code == 403
    assert (
        client.post(
            "/api/team/", headers=agent_headers, json={"name": "Another", "email": "x@demo.com", "role": "AGENT"}
        ).status_code
        == 403
    )


def test_remove_member(client):
    owner_token = _register(client)
    headers = {"Authorization": f"Bearer {owner_token}"}
    with patch(EMAIL_TARGET):
        create_res = client.post(
            "/api/team/", headers=headers, json={"name": "Agent", "email": "agent1@demo.com", "role": "AGENT"}
        )
    user_id = create_res.get_json()["id"]

    delete_res = client.delete(f"/api/team/{user_id}", headers=headers)
    assert delete_res.status_code == 204

    list_res = client.get("/api/team/", headers=headers)
    assert len(list_res.get_json()) == 1

    assert client.delete(f"/api/team/{user_id}", headers=headers).status_code == 404


def test_cannot_remove_only_owner(client):
    owner_token = _register(client)
    headers = {"Authorization": f"Bearer {owner_token}"}
    me = client.get("/api/auth/me", headers=headers).get_json()

    res = client.delete(f"/api/team/{me['id']}", headers=headers)
    assert res.status_code == 400


def test_can_change_role_between_admin_and_agent(client):
    owner_token = _register(client)
    headers = {"Authorization": f"Bearer {owner_token}"}
    with patch(EMAIL_TARGET):
        create_res = client.post(
            "/api/team/", headers=headers, json={"name": "Agent", "email": "agent1@demo.com", "role": "AGENT"}
        )
    user_id = create_res.get_json()["id"]

    res = client.patch(f"/api/team/{user_id}", headers=headers, json={"role": "ADMIN"})
    assert res.status_code == 200
    assert res.get_json()["role"] == "ADMIN"

    list_res = client.get("/api/team/", headers=headers)
    updated = next(m for m in list_res.get_json() if m["id"] == user_id)
    assert updated["role"] == "ADMIN"

    res = client.patch(f"/api/team/{user_id}", headers=headers, json={"role": "AGENT"})
    assert res.status_code == 200
    assert res.get_json()["role"] == "AGENT"
