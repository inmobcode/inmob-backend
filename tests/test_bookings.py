def _create_property(client, headers, listing_type="RENT", title="Casa Booking"):
    res = client.post(
        "/api/properties/",
        headers=headers,
        json={"title": title, "listingType": listing_type, "category": "HOUSE"},
    )
    return res.get_json()


def test_create_booking_requires_property_in_same_agency(client, register_agency):
    agency_a = register_agency(agency_name="Agencia A", email="a@demo.com")
    agency_b = register_agency(agency_name="Agencia B", email="b@demo.com")
    prop_b = _create_property(client, agency_b["headers"])

    res = client.post(
        "/api/bookings/", headers=agency_a["headers"], json={"propertyId": prop_b["id"]}
    )
    assert res.status_code == 404


def test_confirm_rental_booking_blocks_availability(client, register_agency):
    agency = register_agency()
    prop = _create_property(client, agency["headers"], listing_type="RENT")

    create_res = client.post(
        "/api/bookings/",
        headers=agency["headers"],
        json={
            "propertyId": prop["id"],
            "startDate": "2026-09-01",
            "endDate": "2026-09-10",
            "totalPrice": 900,
        },
    )
    assert create_res.status_code == 201
    booking = create_res.get_json()
    assert booking["status"] == "PENDING"

    confirm_res = client.post(
        f"/api/bookings/{booking['id']}/confirm", headers=agency["headers"]
    )
    assert confirm_res.get_json()["status"] == "CONFIRMED"

    blocks = client.get(
        f"/api/properties/{prop['id']}/availability/", headers=agency["headers"]
    ).get_json()
    assert len(blocks) == 1
    assert blocks[0]["source"] == "BOOKING"
    assert blocks[0]["startDate"] == "2026-09-01"


def test_cancel_confirmed_booking_frees_availability(client, register_agency):
    agency = register_agency()
    prop = _create_property(client, agency["headers"], listing_type="RENT")
    booking = client.post(
        "/api/bookings/",
        headers=agency["headers"],
        json={"propertyId": prop["id"], "startDate": "2026-09-01", "endDate": "2026-09-10"},
    ).get_json()
    client.post(f"/api/bookings/{booking['id']}/confirm", headers=agency["headers"])

    cancel_res = client.post(f"/api/bookings/{booking['id']}/cancel", headers=agency["headers"])
    assert cancel_res.get_json()["status"] == "CANCELLED"

    blocks = client.get(
        f"/api/properties/{prop['id']}/availability/", headers=agency["headers"]
    ).get_json()
    assert blocks == []


def test_sale_booking_does_not_create_availability_block(client, register_agency):
    agency = register_agency()
    prop = _create_property(client, agency["headers"], listing_type="SALE")
    booking = client.post(
        "/api/bookings/", headers=agency["headers"], json={"propertyId": prop["id"]}
    ).get_json()
    client.post(f"/api/bookings/{booking['id']}/confirm", headers=agency["headers"])

    blocks = client.get(
        f"/api/properties/{prop['id']}/availability/", headers=agency["headers"]
    ).get_json()
    assert blocks == []


def test_cannot_confirm_twice(client, register_agency):
    agency = register_agency()
    prop = _create_property(client, agency["headers"])
    booking = client.post(
        "/api/bookings/", headers=agency["headers"], json={"propertyId": prop["id"]}
    ).get_json()
    client.post(f"/api/bookings/{booking['id']}/confirm", headers=agency["headers"])

    res = client.post(f"/api/bookings/{booking['id']}/confirm", headers=agency["headers"])
    assert res.status_code == 400


def test_complete_requires_confirmed_first(client, register_agency):
    agency = register_agency()
    prop = _create_property(client, agency["headers"])
    booking = client.post(
        "/api/bookings/", headers=agency["headers"], json={"propertyId": prop["id"]}
    ).get_json()

    res = client.post(f"/api/bookings/{booking['id']}/complete", headers=agency["headers"])
    assert res.status_code == 400

    client.post(f"/api/bookings/{booking['id']}/confirm", headers=agency["headers"])
    res = client.post(f"/api/bookings/{booking['id']}/complete", headers=agency["headers"])
    assert res.get_json()["status"] == "COMPLETED"


def test_payments_lifecycle(client, register_agency):
    agency = register_agency()
    prop = _create_property(client, agency["headers"])
    booking = client.post(
        "/api/bookings/", headers=agency["headers"], json={"propertyId": prop["id"], "totalPrice": 1000}
    ).get_json()

    payment_res = client.post(
        f"/api/bookings/{booking['id']}/payments",
        headers=agency["headers"],
        json={"amount": 300, "type": "DEPOSIT"},
    )
    assert payment_res.status_code == 201
    payment = payment_res.get_json()
    assert payment["status"] == "PENDING"

    paid_res = client.post(
        f"/api/bookings/{booking['id']}/payments/{payment['id']}/mark-paid",
        headers=agency["headers"],
    )
    assert paid_res.get_json()["status"] == "PAID"
    assert paid_res.get_json()["paidAt"] is not None

    detail = client.get(f"/api/bookings/{booking['id']}", headers=agency["headers"]).get_json()
    assert len(detail["payments"]) == 1


def test_agency_cannot_access_another_agencys_booking(client, register_agency):
    agency_a = register_agency(agency_name="Agencia A", email="a@demo.com")
    agency_b = register_agency(agency_name="Agencia B", email="b@demo.com")
    prop = _create_property(client, agency_a["headers"])
    booking = client.post(
        "/api/bookings/", headers=agency_a["headers"], json={"propertyId": prop["id"]}
    ).get_json()

    res = client.get(f"/api/bookings/{booking['id']}", headers=agency_b["headers"])
    assert res.status_code == 404
