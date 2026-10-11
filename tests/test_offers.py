def _create_property(client, headers, title="Casa Linda", price=1000):
    res = client.post(
        "/api/properties/",
        headers=headers,
        json={"title": title, "listingType": "RENT", "category": "HOUSE"},
    )
    prop = res.get_json()
    client.patch(f"/api/properties/{prop['id']}", headers=headers, json={"price": price})
    return prop


def _create_offer(client, headers, title, sections):
    return client.post(
        "/api/offers/", headers=headers, json={"title": title, "sections": sections}
    )


def test_create_offer_with_sections_and_per_property_discount(client, register_agency):
    agency = register_agency()
    prop_a = _create_property(client, agency["headers"], title="Villa A", price=1000)
    prop_b = _create_property(client, agency["headers"], title="Villa B", price=2000)

    res = _create_offer(
        client,
        agency["headers"],
        "Oferta verano",
        sections=[
            {
                "title": "Seleccionadas para usted",
                "text": "Un resumen de nuestras mejores villas",
                "properties": [
                    {"propertyId": prop_a["id"], "discountType": "PERCENT", "discountValue": 10},
                    {
                        "propertyId": prop_b["id"],
                        "discountType": "FIXED",
                        "discountValue": 300,
                        "securityDeposit": 500,
                        "bottomText": "Incluye limpieza final",
                    },
                ],
            }
        ],
    )
    assert res.status_code == 201
    body = res.get_json()
    assert body["status"] == "DRAFT"
    assert len(body["sections"]) == 1
    section = body["sections"][0]
    assert section["title"] == "Seleccionadas para usted"

    item_a, item_b = section["properties"]
    assert item_a["displayPrice"] == 900.0
    assert item_a["initialPrice"] == 1000.0
    assert item_b["displayPrice"] == 1700.0
    assert item_b["initialPrice"] == 2000.0
    assert item_b["securityDeposit"] == 500
    assert item_b["bottomText"] == "Incluye limpieza final"
    assert body["total"] == 2600.0


def test_property_without_discount_has_no_initial_price(client, register_agency):
    agency = register_agency()
    prop = _create_property(client, agency["headers"], price=1000)

    res = _create_offer(
        client, agency["headers"], "Oferta", sections=[{"properties": [{"propertyId": prop["id"]}]}]
    )
    item = res.get_json()["sections"][0]["properties"][0]
    assert item["displayPrice"] == 1000.0
    assert item["initialPrice"] is None


def test_price_override_takes_precedence_over_property_price(client, register_agency):
    agency = register_agency()
    prop = _create_property(client, agency["headers"], price=1000)

    res = _create_offer(
        client,
        agency["headers"],
        "Oferta",
        sections=[{"properties": [{"propertyId": prop["id"], "priceOverride": 500}]}],
    )
    assert res.get_json()["sections"][0]["properties"][0]["displayPrice"] == 500.0


def test_ungrouped_properties_render_as_titleless_trailing_section(client, register_agency):
    agency = register_agency()
    prop = _create_property(client, agency["headers"])

    res = client.post(
        "/api/offers/",
        headers=agency["headers"],
        json={"title": "Oferta", "sections": [{"title": None, "properties": [{"propertyId": prop["id"]}]}]},
    )
    assert res.get_json()["sections"][0]["title"] is None


def test_offer_cannot_include_another_agencys_property(client, register_agency):
    agency_a = register_agency(agency_name="Agencia A", email="a@demo.com")
    agency_b = register_agency(agency_name="Agencia B", email="b@demo.com")
    prop_b = _create_property(client, agency_b["headers"])

    res = _create_offer(
        client, agency_a["headers"], "Oferta cruzada", sections=[{"properties": [{"propertyId": prop_b["id"]}]}]
    )
    assert res.status_code == 404


def test_public_cannot_view_draft_offer(client, register_agency):
    agency = register_agency()
    prop = _create_property(client, agency["headers"])
    offer = _create_offer(
        client, agency["headers"], "Oferta", sections=[{"properties": [{"propertyId": prop["id"]}]}]
    ).get_json()

    res = client.get(f"/api/public/offers/{offer['token']}")
    assert res.status_code == 404


def test_sending_offer_makes_it_publicly_viewable_and_marks_viewed(client, register_agency):
    agency = register_agency()
    prop = _create_property(client, agency["headers"])
    offer = _create_offer(
        client, agency["headers"], "Oferta", sections=[{"properties": [{"propertyId": prop["id"]}]}]
    ).get_json()

    send_res = client.post(f"/api/offers/{offer['id']}/send", headers=agency["headers"])
    assert send_res.get_json()["status"] == "SENT"

    public_res = client.get(f"/api/public/offers/{offer['token']}")
    assert public_res.status_code == 200
    body = public_res.get_json()
    assert body["status"] == "VIEWED"
    # agency-internal fields must not leak publicly
    assert "agencyId" not in body
    assert "clientId" not in body


def test_branded_toggle_persists(client, register_agency):
    agency = register_agency()
    prop = _create_property(client, agency["headers"])
    offer = client.post(
        "/api/offers/",
        headers=agency["headers"],
        json={
            "title": "Oferta",
            "branded": False,
            "welcomeTitle": "Bienvenidos",
            "welcomeDateLabel": "Verano 2026",
            "sections": [{"properties": [{"propertyId": prop["id"]}]}],
        },
    ).get_json()
    assert offer["branded"] is False
    assert offer["welcomeTitle"] == "Bienvenidos"
    assert offer["welcomeDateLabel"] == "Verano 2026"


def test_counteroffer_and_accept_reject_endpoints_no_longer_exist(client, register_agency):
    agency = register_agency()
    prop = _create_property(client, agency["headers"])
    offer = _create_offer(
        client, agency["headers"], "Oferta", sections=[{"properties": [{"propertyId": prop["id"]}]}]
    ).get_json()
    client.post(f"/api/offers/{offer['id']}/send", headers=agency["headers"])

    assert client.post(f"/api/public/offers/{offer['token']}/counteroffers", json={}).status_code == 404
    assert client.post(f"/api/public/offers/{offer['token']}/accept").status_code == 404
    assert client.post(f"/api/public/offers/{offer['token']}/reject").status_code == 404


def test_public_property_response_hides_agency_and_owner_fields(client, register_agency):
    agency = register_agency()
    owner_res = client.post(
        "/api/properties/owners",
        headers=agency["headers"],
        json={"name": "Dueño Privado", "email": "privado@demo.com"},
    )
    prop = _create_property(client, agency["headers"], title="Depto Seguro")
    client.patch(
        f"/api/properties/{prop['id']}",
        headers=agency["headers"],
        json={"ownerId": owner_res.get_json()["id"]},
    )
    client.post(f"/api/properties/{prop['id']}/publish", headers=agency["headers"])

    public_res = client.get("/api/public/agencia-demo/properties/depto-seguro")
    body = public_res.get_json()
    assert "agencyId" not in body
    assert "owner" not in body
    assert "ownerId" not in body
