def _register_owner(client):
    res = client.post(
        "/api/auth/register",
        json={
            "agencyName": "Agencia Demo",
            "name": "Owner",
            "email": "owner@demo.com",
            "password": "password123",
        },
    )
    return res.get_json()["accessToken"]


def test_owner_can_list_and_create_team_members(client):
    owner_token = _register_owner(client)
    headers = {"Authorization": f"Bearer {owner_token}"}

    create_res = client.post(
        "/api/team/",
        headers=headers,
        json={
            "name": "Agent One",
            "email": "agent1@demo.com",
            "password": "password123",
            "role": "AGENT",
        },
    )
    assert create_res.status_code == 201

    list_res = client.get("/api/team/", headers=headers)
    assert list_res.status_code == 200
    assert len(list_res.get_json()) == 2


def test_cannot_assign_owner_role_via_team_create(client):
    owner_token = _register_owner(client)
    res = client.post(
        "/api/team/",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "name": "Sneaky",
            "email": "sneaky@demo.com",
            "password": "password123",
            "role": "OWNER",
        },
    )
    assert res.status_code == 400


def test_agent_cannot_create_team_members(client):
    owner_token = _register_owner(client)
    client.post(
        "/api/team/",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "name": "Agent One",
            "email": "agent1@demo.com",
            "password": "password123",
            "role": "AGENT",
        },
    )
    agent_login = client.post(
        "/api/auth/login", json={"email": "agent1@demo.com", "password": "password123"}
    ).get_json()

    res = client.post(
        "/api/team/",
        headers={"Authorization": f"Bearer {agent_login['accessToken']}"},
        json={
            "name": "Another",
            "email": "another@demo.com",
            "password": "password123",
            "role": "AGENT",
        },
    )
    assert res.status_code == 403
