def _create_published_property(client, headers, title="Depto Centro"):
    res = client.post(
        "/api/properties/",
        headers=headers,
        json={"title": title, "listingType": "RENT", "category": "APARTMENT"},
    )
    prop = res.get_json()
    client.post(f"/api/properties/{prop['id']}/publish", headers=headers)
    return prop


def test_public_property_inquiry_creates_client_and_interaction(client, register_agency):
    agency = register_agency(agency_name="Agencia Inquiry", email="owner@inquiry.com")
    prop = _create_published_property(client, agency["headers"])

    res = client.post(
        "/api/public/agencia-inquiry/inquiries",
        json={
            "name": "Lucía",
            "email": "lucia@demo.com",
            "message": "Me interesa esta propiedad",
            "propertyId": prop["id"],
            "inquiryType": "PROPERTY",
        },
    )
    assert res.status_code == 201

    clients = client.get("/api/clients/", headers=agency["headers"]).get_json()
    assert len(clients) == 1
    assert clients[0]["email"] == "lucia@demo.com"
    assert clients[0]["stage"] == "LEAD"
    assert clients[0]["source"] == "WEBSITE"

    detail = client.get(f"/api/clients/{clients[0]['id']}", headers=agency["headers"]).get_json()
    assert len(detail["interactions"]) == 1
    # The note names the listing, so the history says what they asked about.
    assert "Consultó por «Depto Centro»" in detail["interactions"][0]["content"]


def test_repeat_inquiry_same_email_reuses_client(client, register_agency):
    agency = register_agency(agency_name="Agencia Repeat", email="owner@repeat.com")
    _create_published_property(client, agency["headers"])

    payload = {"name": "Lucía", "email": "lucia@demo.com", "message": "Hola"}
    client.post("/api/public/agencia-repeat/inquiries", json=payload)
    client.post("/api/public/agencia-repeat/inquiries", json={**payload, "message": "De nuevo"})

    clients = client.get("/api/clients/", headers=agency["headers"]).get_json()
    assert len(clients) == 1

    detail = client.get(f"/api/clients/{clients[0]['id']}", headers=agency["headers"]).get_json()
    assert len(detail["interactions"]) == 2


def test_inquiry_for_unpublished_property_is_rejected(client, register_agency):
    agency = register_agency(agency_name="Agencia Draft", email="owner@draft.com")
    prop_res = client.post(
        "/api/properties/",
        headers=agency["headers"],
        json={"title": "Sin publicar", "listingType": "SALE", "category": "HOUSE"},
    )
    prop = prop_res.get_json()

    res = client.post(
        "/api/public/agencia-draft/inquiries",
        json={"name": "Visitante", "email": "x@demo.com", "propertyId": prop["id"]},
    )
    assert res.status_code == 404


def test_offer_inquiry_dual_writes_into_crm_and_links_offer(client, register_agency):
    agency = register_agency(agency_name="Agencia Crm Offer", email="owner@crmoffer.com")
    prop_res = client.post(
        "/api/properties/",
        headers=agency["headers"],
        json={"title": "Casa Oferta", "listingType": "RENT", "category": "HOUSE"},
    )
    prop_id = prop_res.get_json()["id"]
    client.patch(f"/api/properties/{prop_id}", headers=agency["headers"], json={"price": 1000})

    offer_res = client.post(
        "/api/offers/",
        headers=agency["headers"],
        json={"title": "Oferta CRM", "sections": [{"properties": [{"propertyId": prop_id}]}]},
    )
    offer = offer_res.get_json()
    client.post(f"/api/offers/{offer['id']}/send", headers=agency["headers"])

    client.post(
        f"/api/public/offers/{offer['token']}/inquiries",
        json={"name": "Pedro", "email": "pedro@demo.com", "message": "Me interesa"},
    )

    clients = client.get("/api/clients/", headers=agency["headers"]).get_json()
    assert len(clients) == 1
    assert clients[0]["source"] == "OFFER"

    offer_detail = client.get(f"/api/offers/{offer['id']}", headers=agency["headers"]).get_json()
    assert offer_detail["clientId"] == clients[0]["id"]


def test_manual_client_create_update_and_interaction(client, register_agency):
    agency = register_agency()

    create_res = client.post(
        "/api/clients/",
        headers=agency["headers"],
        json={"name": "Ana", "email": "ana@demo.com"},
    )
    assert create_res.status_code == 201
    client_id = create_res.get_json()["id"]

    update_res = client.patch(
        f"/api/clients/{client_id}",
        headers=agency["headers"],
        json={"stage": "CONTACTED", "notes": "Llamar la próxima semana"},
    )
    assert update_res.get_json()["stage"] == "CONTACTED"

    interaction_res = client.post(
        f"/api/clients/{client_id}/interactions",
        headers=agency["headers"],
        json={"type": "CALL", "content": "Llamada inicial"},
    )
    assert interaction_res.status_code == 201


def test_agency_cannot_access_another_agencys_client(client, register_agency):
    agency_a = register_agency(agency_name="Agencia A", email="a@demo.com")
    agency_b = register_agency(agency_name="Agencia B", email="b@demo.com")

    create_res = client.post(
        "/api/clients/", headers=agency_a["headers"], json={"name": "Ana", "email": "ana@demo.com"}
    )
    client_id = create_res.get_json()["id"]

    res = client.get(f"/api/clients/{client_id}", headers=agency_b["headers"])
    assert res.status_code == 404


def test_deleted_client_goes_to_trash_and_comes_back(client, register_agency):
    headers = register_agency()["headers"]
    created = client.post("/api/clients/", headers=headers, json={"name": "Lucía", "email": "lucia@demo.com"}).get_json()
    client.post("/api/tasks/", headers=headers, json={"title": "Llamar", "clientId": created["id"]})

    assert client.delete(f"/api/clients/{created['id']}", headers=headers).status_code == 204
    assert client.get("/api/clients/", headers=headers).get_json() == []
    assert client.get(f"/api/clients/{created['id']}", headers=headers).status_code == 404
    assert client.get("/api/tasks/", headers=headers).get_json() == []
    trashed = client.get("/api/clients/trash", headers=headers).get_json()
    assert [item["id"] for item in trashed] == [created["id"]] and trashed[0]["deletedAt"]

    # The same email can't be added again while it waits in the trash.
    again = client.post("/api/clients/", headers=headers, json={"name": "Lucía", "email": "lucia@demo.com"})
    assert again.status_code == 409

    res = client.post(f"/api/clients/{created['id']}/restore", headers=headers)
    assert res.status_code == 200 and res.get_json()["deletedAt"] is None
    assert len(client.get("/api/clients/", headers=headers).get_json()) == 1
    assert len(client.get("/api/tasks/", headers=headers).get_json()) == 1


def test_new_inquiry_brings_a_trashed_client_back(client, register_agency):
    agency = register_agency(agency_name="Agencia Vuelve", email="owner@vuelve.com")
    payload = {"name": "Lucía", "email": "lucia@demo.com", "message": "Hola"}
    client.post("/api/public/agencia-vuelve/inquiries", json=payload)
    lead = client.get("/api/clients/", headers=agency["headers"]).get_json()[0]
    client.delete(f"/api/clients/{lead['id']}", headers=agency["headers"])

    client.post("/api/public/agencia-vuelve/inquiries", json={**payload, "message": "De nuevo"})
    clients = client.get("/api/clients/", headers=agency["headers"]).get_json()
    assert [item["id"] for item in clients] == [lead["id"]]


def test_client_with_bookings_cant_be_deleted_for_good(client, register_agency):
    headers = register_agency()["headers"]
    prop = client.post(
        "/api/properties/", headers=headers, json={"title": "Casa", "listingType": "RENT", "category": "HOUSE"}
    ).get_json()
    booked = client.post("/api/clients/", headers=headers, json={"name": "Lucía", "email": "lucia@demo.com"}).get_json()
    client.post("/api/bookings/", headers=headers, json={"propertyId": prop["id"], "clientId": booked["id"]})
    other = client.post("/api/clients/", headers=headers, json={"name": "Tomás", "email": "tomas@demo.com"}).get_json()
    offer = client.post(
        "/api/offers/", headers=headers, json={"title": "Oferta", "sections": [], "clientId": other["id"]}
    ).get_json()
    for item in (booked, other):
        client.delete(f"/api/clients/{item['id']}", headers=headers)

    assert client.delete(f"/api/clients/{booked['id']}/permanent", headers=headers).status_code == 409
    assert client.delete(f"/api/clients/{other['id']}/permanent", headers=headers).status_code == 204
    assert [item["id"] for item in client.get("/api/clients/trash", headers=headers).get_json()] == [booked["id"]]
    # The offer keeps its copy of the contact details.
    kept = client.get(f"/api/offers/{offer['id']}", headers=headers).get_json()
    assert kept["clientId"] is None and kept["clientName"] == "Tomás"


def test_client_tags_and_preferences(client, register_agency):
    headers = register_agency()["headers"]
    created = client.post("/api/clients/", headers=headers, json={"name": "Lucía", "email": "lucia@demo.com"}).get_json()
    assert created["tags"] == []

    res = client.patch(
        f"/api/clients/{created['id']}",
        headers=headers,
        json={
            "tags": [" VIP ", "vip", "Inversor"],
            "budgetMin": 1000,
            "budgetMax": 2500,
            "guests": 4,
            "zones": "Centro, Costa",
            "desiredFrom": "2027-01-10",
            "desiredTo": "2027-01-20",
        },
    )
    body = res.get_json()
    assert res.status_code == 200
    assert body["tags"] == ["VIP", "Inversor"]
    assert (body["budgetMin"], body["budgetMax"], body["guests"]) == (1000, 2500, 4)
    assert (body["desiredFrom"], body["desiredTo"]) == ("2027-01-10", "2027-01-20")

    # Checked against what's saved, so changing one end alone can't cross the other.
    assert client.patch(f"/api/clients/{created['id']}", headers=headers, json={"budgetMin": 3000}).status_code == 400
    assert (
        client.patch(f"/api/clients/{created['id']}", headers=headers, json={"desiredTo": "2027-01-01"}).status_code
        == 400
    )

