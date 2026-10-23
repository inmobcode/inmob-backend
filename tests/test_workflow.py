from unittest.mock import patch


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _invite_agent(client, owner_headers, email="agent@demo.com", name="Agente Uno"):
    """Invites an AGENT and returns their headers and user id."""
    with patch("app.services.team_service._send_invite_email") as mock_send:
        res = client.post("/api/team/", headers=owner_headers, json={"name": name, "email": email, "role": "AGENT"})
    assert res.status_code == 201
    temp_password = mock_send.call_args[0][3]
    login = client.post("/api/auth/login", json={"email": email, "password": temp_password}).get_json()
    return {"headers": _auth(login["accessToken"]), "id": login["user"]["id"]}


def _owner_id(client, owner):
    return client.get("/api/auth/me", headers=owner["headers"]).get_json()["id"]


def _property(client, headers, title="Casa"):
    res = client.post(
        "/api/properties/", headers=headers, json={"title": title, "listingType": "SALE", "category": "HOUSE"}
    )
    assert res.status_code == 201
    return res.get_json()


def _client(client, headers, name="Lucía", email="lucia@demo.com"):
    res = client.post("/api/clients/", headers=headers, json={"name": name, "email": email})
    assert res.status_code == 201
    return res.get_json()


# --- roles ---------------------------------------------------------------


def test_agent_only_sees_their_own_properties(client, register_agency):
    owner = register_agency()
    agent = _invite_agent(client, owner["headers"])

    mine = _property(client, agent["headers"], "De la agente")
    theirs = _property(client, owner["headers"], "Del dueño")

    listed = client.get("/api/properties/", headers=agent["headers"]).get_json()
    assert [p["id"] for p in listed] == [mine["id"]]
    assert client.get(f"/api/properties/{theirs['id']}", headers=agent["headers"]).status_code == 404

    # Owners see everything.
    assert len(client.get("/api/properties/", headers=owner["headers"]).get_json()) == 2


def test_admin_can_reassign_a_property_but_an_agent_cannot(client, register_agency):
    owner = register_agency()
    agent = _invite_agent(client, owner["headers"])
    prop = _property(client, owner["headers"])

    res = client.patch(f"/api/properties/{prop['id']}", headers=owner["headers"], json={"assignedAgentId": agent["id"]})
    assert res.status_code == 200
    assert res.get_json()["assignedAgentId"] == agent["id"]
    assert len(client.get("/api/properties/", headers=agent["headers"]).get_json()) == 1

    res = client.patch(f"/api/properties/{prop['id']}", headers=agent["headers"], json={"assignedAgentId": None})
    assert res.status_code == 403


def test_cannot_assign_to_someone_outside_the_agency(client, register_agency):
    owner = register_agency()
    other = register_agency(agency_name="Otra", email="otra@demo.com")
    other_user = _owner_id(client, other)
    prop = _property(client, owner["headers"])

    res = client.patch(f"/api/properties/{prop['id']}", headers=owner["headers"], json={"assignedAgentId": other_user})
    assert res.status_code == 404


def test_agent_sees_own_clients_and_unassigned_leads_only(client, register_agency):
    owner = register_agency(agency_name="Agencia L", email="l@demo.com")
    agent = _invite_agent(client, owner["headers"])
    other_agent = _invite_agent(client, owner["headers"], email="agent2@demo.com", name="Agente Dos")

    mine = _client(client, agent["headers"], "Mía", "mia@demo.com")
    assert mine["assignedAgentId"] == agent["id"]
    _client(client, other_agent["headers"], "Ajena", "ajena@demo.com")
    _client(client, owner["headers"], "Del dueño", "dueno@demo.com")
    # A lead from the website starts with nobody.
    client.post("/api/public/agencia-l/inquiries", json={"name": "Lead", "email": "lead@demo.com"})
    everyone = client.get("/api/clients/", headers=owner["headers"]).get_json()
    lead = next(c for c in everyone if c["name"] == "Lead")
    assert lead["assignedAgentId"] is None

    names = {c["name"] for c in client.get("/api/clients/", headers=agent["headers"]).get_json()}
    assert names == {"Mía", "Lead"}
    assert len(everyone) == 4

    # An agent can take a lead, but not hand it to a colleague.
    taken = client.patch(f"/api/clients/{lead['id']}", headers=agent["headers"], json={"assignedAgentId": agent["id"]})
    assert taken.status_code == 200
    handed = client.patch(f"/api/clients/{lead['id']}", headers=agent["headers"], json={"assignedAgentId": other_agent["id"]})
    assert handed.status_code == 403

    ajena = next(c for c in everyone if c["name"] == "Ajena")
    assert client.get(f"/api/clients/{ajena['id']}", headers=agent["headers"]).status_code == 404


def test_agent_only_sees_their_own_offers(client, register_agency):
    owner = register_agency()
    agent = _invite_agent(client, owner["headers"])
    client.post("/api/offers/", headers=owner["headers"], json={"title": "Del dueño"})
    mine = client.post("/api/offers/", headers=agent["headers"], json={"title": "De la agente"}).get_json()

    offers = client.get("/api/offers/", headers=agent["headers"]).get_json()
    assert [o["id"] for o in offers] == [mine["id"]]
    assert len(client.get("/api/offers/", headers=owner["headers"]).get_json()) == 2


def test_agent_cannot_reach_team_settings(client, register_agency):
    owner = register_agency()
    agent = _invite_agent(client, owner["headers"])
    assert client.get("/api/team/", headers=agent["headers"]).status_code == 403


def test_agent_inquiries_follow_client_visibility(client, register_agency):
    owner = register_agency(agency_name="Agencia Q", email="q@demo.com")
    agent = _invite_agent(client, owner["headers"])
    other = _invite_agent(client, owner["headers"], email="o@demo.com", name="Otra")
    _client(client, other["headers"], "Ajena", "ajena@demo.com")

    for name, email in (("Ajena", "ajena@demo.com"), ("Nueva", "nueva@demo.com")):
        res = client.post("/api/public/agencia-q/inquiries", json={"name": name, "email": email, "message": "Hola"})
        assert res.status_code == 201

    seen = {i["name"] for i in client.get("/api/inquiries/", headers=agent["headers"]).get_json()}
    assert seen == {"Nueva"}
    assert client.get("/api/inquiries/unread-count", headers=agent["headers"]).get_json()["count"] == 1
    assert client.get("/api/inquiries/unread-count", headers=owner["headers"]).get_json()["count"] == 2


# --- tasks ---------------------------------------------------------------


def test_task_lifecycle(client, register_agency):
    owner = register_agency()
    lead = _client(client, owner["headers"])

    res = client.post(
        "/api/tasks/",
        headers=owner["headers"],
        json={"title": "Llamar a Lucía", "dueDate": "2020-01-01", "clientId": lead["id"]},
    )
    assert res.status_code == 201
    task = res.get_json()
    assert task["overdue"] is True
    assert task["client"]["name"] == "Lucía"

    open_tasks = client.get("/api/tasks/", headers=owner["headers"]).get_json()
    assert [t["id"] for t in open_tasks] == [task["id"]]
    assert len(client.get(f"/api/tasks/?clientId={lead['id']}", headers=owner["headers"]).get_json()) == 1

    done = client.patch(f"/api/tasks/{task['id']}", headers=owner["headers"], json={"done": True}).get_json()
    assert done["doneAt"] is not None and done["overdue"] is False
    assert client.get("/api/tasks/", headers=owner["headers"]).get_json() == []
    assert len(client.get("/api/tasks/?status=done", headers=owner["headers"]).get_json()) == 1

    assert client.delete(f"/api/tasks/{task['id']}", headers=owner["headers"]).status_code == 204


def test_task_validation_and_tenancy(client, register_agency):
    owner = register_agency()
    other = register_agency(agency_name="Otra", email="otra@demo.com")
    foreign_client = _client(client, other["headers"], "Ajeno", "ajeno@demo.com")

    assert client.post("/api/tasks/", headers=owner["headers"], json={"title": "x"}).status_code == 400
    res = client.post("/api/tasks/", headers=owner["headers"], json={"title": "Algo", "clientId": foreign_client["id"]})
    assert res.status_code == 404

    task = client.post("/api/tasks/", headers=owner["headers"], json={"title": "Mía"}).get_json()
    assert client.patch(f"/api/tasks/{task['id']}", headers=other["headers"], json={"done": True}).status_code == 404


def test_agent_tasks_are_limited_and_assignment_notifies(client, register_agency):
    owner = register_agency()
    agent = _invite_agent(client, owner["headers"])
    other = _invite_agent(client, owner["headers"], email="o@demo.com", name="Otra")

    client.post("/api/tasks/", headers=owner["headers"], json={"title": "Del dueño"})
    given = client.post(
        "/api/tasks/", headers=owner["headers"], json={"title": "Para la agente", "assignedAgentId": agent["id"]}
    ).get_json()

    seen = client.get("/api/tasks/", headers=agent["headers"]).get_json()
    assert [t["id"] for t in seen] == [given["id"]]

    # The agent is told about it; the owner who assigned it isn't.
    bell = client.get("/api/notifications/", headers=agent["headers"]).get_json()
    assert bell["unread"] == 1 and bell["items"][0]["type"] == "TASK"
    assert client.get("/api/notifications/unread-count", headers=owner["headers"]).get_json()["count"] == 0

    # An agent can't give work to a colleague.
    res = client.post("/api/tasks/", headers=agent["headers"], json={"title": "Para otra", "assignedAgentId": other["id"]})
    assert res.status_code == 403


# --- notifications -------------------------------------------------------


def test_inquiry_notifies_managers_and_can_be_cleared(client, register_agency):
    owner = register_agency(agency_name="Agencia N", email="n@demo.com")
    client.post("/api/public/agencia-n/inquiries", json={"name": "Ana", "email": "ana@demo.com", "message": "Hola"})

    bell = client.get("/api/notifications/", headers=owner["headers"]).get_json()
    assert bell["unread"] == 1
    item = bell["items"][0]
    assert item["type"] == "INQUIRY" and "Ana" in item["title"] and item["link"] == "/inquiries"

    res = client.patch(f"/api/notifications/{item['id']}", headers=owner["headers"], json={"read": True})
    assert res.get_json()["readAt"] is not None
    assert client.get("/api/notifications/unread-count", headers=owner["headers"]).get_json()["count"] == 0
    assert client.patch(f"/api/notifications/{item['id']}", headers=owner["headers"], json={"read": "x"}).status_code == 400

    client.post("/api/public/agencia-n/inquiries", json={"name": "Beto", "email": "beto@demo.com"})
    assert client.post("/api/notifications/read-all", headers=owner["headers"]).get_json()["updated"] == 1


def test_notifications_are_private_per_user(client, register_agency):
    owner = register_agency(agency_name="Agencia P", email="p@demo.com")
    agent = _invite_agent(client, owner["headers"])
    client.post("/api/public/agencia-p/inquiries", json={"name": "Ana", "email": "ana@demo.com"})

    item = client.get("/api/notifications/", headers=owner["headers"]).get_json()["items"][0]
    res = client.patch(f"/api/notifications/{item['id']}", headers=agent["headers"], json={"read": True})
    assert res.status_code == 404
    assert client.delete(f"/api/notifications/{item['id']}", headers=agent["headers"]).status_code == 404


def test_notification_can_be_deleted(client, register_agency):
    owner = register_agency(agency_name="Agencia B", email="b@demo.com")
    client.post("/api/public/agencia-b/inquiries", json={"name": "Ana", "email": "ana@demo.com"})
    item = client.get("/api/notifications/", headers=owner["headers"]).get_json()["items"][0]

    assert client.delete(f"/api/notifications/{item['id']}", headers=owner["headers"]).status_code == 204
    bell = client.get("/api/notifications/", headers=owner["headers"]).get_json()
    assert bell == {"unread": 0, "items": []}
    assert client.delete(f"/api/notifications/{item['id']}", headers=owner["headers"]).status_code == 404


# --- dashboard -----------------------------------------------------------


def test_dashboard_summary_counts_and_scopes(client, register_agency):
    owner = register_agency(agency_name="Agencia D", email="d@demo.com")
    agent = _invite_agent(client, owner["headers"])

    lead = _client(client, owner["headers"], "Lead", "lead@demo.com")
    client.patch(f"/api/clients/{lead['id']}", headers=owner["headers"], json={"stage": "NEGOTIATING"})
    _client(client, owner["headers"], "Otro", "otro@demo.com")
    client.post("/api/tasks/", headers=owner["headers"], json={"title": "Vencida", "dueDate": "2020-01-01"})
    client.post("/api/tasks/", headers=owner["headers"], json={"title": "Sin fecha"})
    client.post("/api/public/agencia-d/inquiries", json={"name": "Ana", "email": "ana@demo.com", "message": "Hola"})

    summary = client.get("/api/dashboard/summary", headers=owner["headers"]).get_json()
    counts = summary["counts"]
    assert counts["unreadInquiries"] == 1
    assert counts["openTasks"] == 2 and counts["overdueTasks"] == 1
    assert summary["funnel"]["NEGOTIATING"] == 1
    assert summary["funnel"]["LEAD"] == 2  # Otro and Ana (the web lead)
    assert [i["name"] for i in summary["recentInquiries"]] == ["Ana"]
    assert summary["tasks"][0]["title"] == "Vencida" and summary["tasks"][0]["overdue"] is True

    mine = client.get("/api/dashboard/summary", headers=agent["headers"]).get_json()
    assert mine["counts"]["openTasks"] == 0
    assert mine["funnel"]["NEGOTIATING"] == 0  # the owner's clients aren't the agent's
    assert mine["funnel"]["LEAD"] == 1  # but the unassigned web lead is up for grabs


def test_workflow_endpoints_require_login(client):
    assert client.get("/api/dashboard/summary").status_code == 401
    assert client.get("/api/tasks/").status_code == 401
    assert client.get("/api/notifications/").status_code == 401


# --- an agent can't reach other people's records through side doors -----------


def test_agent_cannot_use_a_colleagues_property_client_or_offer(client, register_agency):
    owner = register_agency(agency_name="Agencia S", email="s@demo.com")
    agent = _invite_agent(client, owner["headers"])

    theirs = _property(client, owner["headers"], "Del dueño")
    their_client = _client(client, owner["headers"], "Del dueño", "dueno@demo.com")
    their_offer = client.post("/api/offers/", headers=owner["headers"], json={"title": "Oferta ajena"}).get_json()
    mine = _property(client, agent["headers"], "De la agente")

    # Calendar of someone else's property
    res = client.get(f"/api/properties/{theirs['id']}/availability/", headers=agent["headers"])
    assert res.status_code == 404

    # Booking someone else's property, client or offer
    for body in (
        {"propertyId": theirs["id"]},
        {"propertyId": mine["id"], "clientId": their_client["id"]},
        {"propertyId": mine["id"], "offerId": their_offer["id"]},
    ):
        assert client.post("/api/bookings/", headers=agent["headers"], json=body).status_code == 404, body

    # Putting someone else's property or client into their own offer
    own_offer = client.post("/api/offers/", headers=agent["headers"], json={"title": "Mía"}).get_json()
    res = client.patch(f"/api/offers/{own_offer['id']}", headers=agent["headers"], json={"clientId": their_client["id"]})
    assert res.status_code == 404
    assert client.post("/api/bookings/", headers=agent["headers"], json={"propertyId": mine["id"]}).status_code == 201


def test_agent_calendar_only_lists_their_rentals(client, register_agency):
    owner = register_agency(agency_name="Agencia K", email="k@demo.com")
    agent = _invite_agent(client, owner["headers"])
    for headers, title in ((owner["headers"], "Del dueño"), (agent["headers"], "De la agente")):
        client.post("/api/properties/", headers=headers, json={"title": title, "listingType": "RENT", "category": "HOUSE"})

    titles = lambda headers: [p["title"] for p in client.get("/api/properties/calendar", headers=headers).get_json()["properties"]]  # noqa: E731
    assert titles(agent["headers"]) == ["De la agente"]
    assert sorted(titles(owner["headers"])) == ["De la agente", "Del dueño"]
