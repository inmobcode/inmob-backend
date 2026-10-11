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
    assert "Consultó por una propiedad" in detail["interactions"][0]["content"]


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
