def _create_owner(client, headers, name="Juan Propietario"):
    return client.post("/api/properties/owners", headers=headers, json={"name": name}).get_json()


def _create_property(client, headers, owner_id, title="Casa del Owner"):
    prop = client.post(
        "/api/properties/",
        headers=headers,
        json={"title": title, "listingType": "RENT", "category": "HOUSE"},
    ).get_json()
    client.patch(f"/api/properties/{prop['id']}", headers=headers, json={"ownerId": owner_id})
    return prop


def test_owner_is_created_with_an_access_token(client, register_agency):
    agency = register_agency()
    owner = _create_owner(client, agency["headers"])
    assert owner["accessToken"]
    assert len(owner["accessToken"]) > 5


def test_regenerate_owner_token_changes_it(client, register_agency):
    agency = register_agency()
    owner = _create_owner(client, agency["headers"])
    original_token = owner["accessToken"]

    res = client.post(
        f"/api/properties/owners/{owner['id']}/regenerate-token", headers=agency["headers"]
    )
    assert res.status_code == 200
    new_token = res.get_json()["accessToken"]
    assert new_token != original_token

    # The old token no longer resolves.
    assert client.get(f"/api/public/owners/{original_token}").status_code == 404
    assert client.get(f"/api/public/owners/{new_token}").status_code == 200


def test_regenerate_owner_token_rejects_cross_agency(client, register_agency):
    agency_a = register_agency(agency_name="Agencia A", email="a@demo.com")
    agency_b = register_agency(agency_name="Agencia B", email="b@demo.com")
    owner = _create_owner(client, agency_a["headers"])

    res = client.post(
        f"/api/properties/owners/{owner['id']}/regenerate-token", headers=agency_b["headers"]
    )
    assert res.status_code == 404


def test_public_owner_portal_shows_properties_and_filters_commission_payments(
    client, register_agency
):
    agency = register_agency(agency_name="Agencia Owner Portal", email="ownerportal@demo.com")
    owner = _create_owner(client, agency["headers"])
    prop = _create_property(client, agency["headers"], owner["id"])

    booking_res = client.post(
        "/api/bookings/",
        headers=agency["headers"],
        json={
            "propertyId": prop["id"],
            "startDate": "2026-12-01",
            "endDate": "2026-12-10",
            "totalPrice": 1000,
        },
    )
    booking = booking_res.get_json()
    client.post(
        f"/api/bookings/{booking['id']}/payments",
        headers=agency["headers"],
        json={"amount": 300, "type": "DEPOSIT"},
    )
    client.post(
        f"/api/bookings/{booking['id']}/payments",
        headers=agency["headers"],
        json={"amount": 100, "type": "COMMISSION"},
    )

    res = client.get(f"/api/public/owners/{owner['accessToken']}")
    assert res.status_code == 200
    body = res.get_json()
    assert body["ownerName"] == "Juan Propietario"
    assert body["agencyName"] == "Agencia Owner Portal"
    assert len(body["properties"]) == 1

    prop_body = body["properties"][0]
    assert prop_body["title"] == "Casa del Owner"
    assert "agencyId" not in prop_body
    assert len(prop_body["bookings"]) == 1

    booking_body = prop_body["bookings"][0]
    assert booking_body["totalPrice"] == 1000
    payment_types = [p["type"] for p in booking_body["payments"]]
    assert "DEPOSIT" in payment_types
    assert "COMMISSION" not in payment_types


def test_public_owner_portal_404_for_unknown_token(client):
    res = client.get("/api/public/owners/does-not-exist")
    assert res.status_code == 404
