from datetime import date, timedelta
from unittest.mock import patch


def _days_ahead(days: int) -> str:
    """A date that stays in the future whenever the tests run."""
    return (date.today() + timedelta(days=days)).isoformat()


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
            "startDate": _days_ahead(30),
            "endDate": _days_ahead(39),
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
    assert blocks[0]["startDate"] == _days_ahead(30)


def test_cancel_confirmed_booking_frees_availability(client, register_agency):
    agency = register_agency()
    prop = _create_property(client, agency["headers"], listing_type="RENT")
    booking = client.post(
        "/api/bookings/",
        headers=agency["headers"],
        json={"propertyId": prop["id"], "startDate": _days_ahead(30), "endDate": _days_ahead(39)},
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


def _create_client(client, headers, email="ana@demo.com"):
    res = client.post(
        "/api/clients/", headers=headers, json={"name": "Ana Pérez", "email": email}
    )
    return res.get_json()


def test_public_booking_page_hides_commission(client, register_agency):
    agency = register_agency(agency_name="Agencia Reservas", email="owner@reservas.com")
    prop = _create_property(client, agency["headers"], title="Casa del lago")
    booking = client.post(
        "/api/bookings/",
        headers=agency["headers"],
        json={
            "propertyId": prop["id"],
            "startDate": _days_ahead(60),
            "endDate": _days_ahead(64),
            "totalPrice": 1200,
            "commissionAmount": 120,
        },
    ).get_json()
    for payment_type in ("DEPOSIT", "COMMISSION"):
        client.post(
            f"/api/bookings/{booking['id']}/payments",
            headers=agency["headers"],
            json={"amount": 100, "type": payment_type},
        )

    page = client.get(f"/api/public/bookings/{booking['token']}").get_json()
    assert page["property"]["title"] == "Casa del lago"
    assert page["agency"]["slug"] == "agencia-reservas"
    assert page["totalPrice"] == 1200
    assert "commissionAmount" not in page
    assert [p["type"] for p in page["payments"]] == ["DEPOSIT"]

    assert client.get("/api/public/bookings/no-existe").status_code == 404


def test_client_gets_an_email_on_each_step(client, register_agency):
    agency = register_agency(agency_name="Agencia Mails", email="owner@mails.com")
    prop = _create_property(client, agency["headers"])
    person = _create_client(client, agency["headers"])

    with patch("app.services.notifications.email_service.send_email") as send:
        booking = client.post(
            "/api/bookings/",
            headers=agency["headers"],
            json={"propertyId": prop["id"], "clientId": person["id"]},
        ).get_json()
        client.post(f"/api/bookings/{booking['id']}/confirm", headers=agency["headers"])
        client.post(f"/api/bookings/{booking['id']}/cancel", headers=agency["headers"])

    subjects = [call.args[1] for call in send.call_args_list]
    assert [call.args[0] for call in send.call_args_list] == [["ana@demo.com"]] * 3
    assert subjects[1].startswith("Reserva confirmada")
    assert subjects[2].startswith("Reserva cancelada")
    assert f"/booking/{booking['token']}" in send.call_args_list[0].args[2]
    assert send.call_args_list[0].kwargs["from_name"] == "Agencia Mails"


def test_booking_without_client_sends_nothing_until_one_is_added(client, register_agency):
    agency = register_agency(agency_name="Agencia Sin", email="owner@sin.com")
    prop = _create_property(client, agency["headers"])
    person = _create_client(client, agency["headers"])

    with patch("app.services.notifications.email_service.send_email") as send:
        booking = client.post(
            "/api/bookings/", headers=agency["headers"], json={"propertyId": prop["id"]}
        ).get_json()
        assert send.call_count == 0
        client.patch(
            f"/api/bookings/{booking['id']}",
            headers=agency["headers"],
            json={"clientId": person["id"]},
        )
    assert send.call_count == 1
    assert send.call_args.args[0] == ["ana@demo.com"]


def test_booking_dates_cant_be_in_the_past_or_backwards(client, register_agency):
    agency = register_agency()
    headers = agency["headers"]
    prop = _create_property(client, headers)

    past = client.post(
        "/api/bookings/",
        headers=headers,
        json={"propertyId": prop["id"], "startDate": _days_ahead(-5), "endDate": _days_ahead(2)},
    )
    assert past.status_code == 400

    backwards = client.post(
        "/api/bookings/",
        headers=headers,
        json={"propertyId": prop["id"], "startDate": _days_ahead(10), "endDate": _days_ahead(8)},
    )
    assert backwards.status_code == 400

    today = client.post(
        "/api/bookings/",
        headers=headers,
        json={"propertyId": prop["id"], "startDate": _days_ahead(0), "endDate": _days_ahead(3)},
    )
    assert today.status_code == 201

    moved_back = client.patch(
        f"/api/bookings/{today.get_json()['id']}", headers=headers, json={"startDate": _days_ahead(-10)}
    )
    assert moved_back.status_code == 400
