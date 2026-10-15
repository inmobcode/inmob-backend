from datetime import date, timedelta


def _days(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()


def _setup(client, headers):
    """An owner with a rental that has one booking: 1000 total, 100 commission, 600 paid."""
    owner = client.post("/api/properties/owners", headers=headers, json={"name": "Juan"}).get_json()
    prop = client.post(
        "/api/properties/", headers=headers, json={"title": "Casa Juan", "listingType": "RENT", "category": "HOUSE"}
    ).get_json()
    client.patch(f"/api/properties/{prop['id']}", headers=headers, json={"ownerId": owner["id"]})
    booking = client.post(
        "/api/bookings/",
        headers=headers,
        json={
            "propertyId": prop["id"],
            "startDate": _days(10),
            "endDate": _days(14),
            "totalPrice": 1000,
            "currency": "USD",
            "commissionAmount": 100,
        },
    ).get_json()
    for amount, kind in ((400, "DEPOSIT"), (200, "BALANCE")):
        payment = client.post(
            f"/api/bookings/{booking['id']}/payments", headers=headers, json={"amount": amount, "type": kind}
        ).get_json()
        client.post(f"/api/bookings/{booking['id']}/payments/{payment['id']}/mark-paid", headers=headers)
    # A pending payment and a commission payment never count as collected for the owner.
    client.post(f"/api/bookings/{booking['id']}/payments", headers=headers, json={"amount": 400, "type": "BALANCE"})
    commission = client.post(
        f"/api/bookings/{booking['id']}/payments", headers=headers, json={"amount": 100, "type": "COMMISSION"}
    ).get_json()
    client.post(f"/api/bookings/{booking['id']}/payments/{commission['id']}/mark-paid", headers=headers)
    return owner, prop, booking


def test_statement_deducts_the_commission_from_what_was_collected(client, register_agency):
    agency = register_agency()
    owner, _, _ = _setup(client, agency["headers"])

    statement = client.get(f"/api/owner-accounts/{owner['id']}", headers=agency["headers"]).get_json()
    assert statement["totals"] == [
        {"currency": "USD", "booked": 1000.0, "collected": 600.0, "due": 500.0, "paidOut": 0.0, "balance": 500.0, "commission": 100.0}
    ]
    row = statement["bookings"][0]
    assert (row["total"], row["collected"], row["commission"], row["due"]) == (1000.0, 600.0, 100.0, 500.0)


def test_payouts_reduce_the_balance_and_can_be_removed(client, register_agency):
    agency = register_agency()
    owner, _, _ = _setup(client, agency["headers"])
    base = f"/api/owner-accounts/{owner['id']}"

    res = client.post(f"{base}/payouts", headers=agency["headers"], json={"amount": 200, "currency": "USD", "paidAt": _days(0), "method": "Transferencia"})
    assert res.status_code == 201
    payout = res.get_json()

    totals = client.get(base, headers=agency["headers"]).get_json()["totals"][0]
    assert totals["paidOut"] == 200.0 and totals["balance"] == 300.0

    assert client.delete(f"{base}/payouts/{payout['id']}", headers=agency["headers"]).status_code == 204
    assert client.get(base, headers=agency["headers"]).get_json()["totals"][0]["balance"] == 500.0


def test_cancelled_bookings_and_bad_payouts_are_left_out(client, register_agency):
    agency = register_agency()
    owner, _, booking = _setup(client, agency["headers"])
    client.post(f"/api/bookings/{booking['id']}/cancel", headers=agency["headers"])
    assert client.get(f"/api/owner-accounts/{owner['id']}", headers=agency["headers"]).get_json()["totals"] == []

    base = f"/api/owner-accounts/{owner['id']}/payouts"
    for body in ({"amount": 0, "paidAt": _days(0)}, {"amount": 10}, {"amount": -5, "paidAt": _days(0)}):
        assert client.post(base, headers=agency["headers"], json=body).status_code == 400


def test_statement_is_private_to_the_agency_and_to_managers(client, register_agency):
    agency = register_agency(agency_name="Agencia A", email="a@demo.com")
    other = register_agency(agency_name="Agencia B", email="b@demo.com")
    owner, _, _ = _setup(client, agency["headers"])

    assert client.get(f"/api/owner-accounts/{owner['id']}", headers=other["headers"]).status_code == 404
    assert client.post(f"/api/owner-accounts/{owner['id']}/payouts", headers=other["headers"], json={"amount": 5, "paidAt": _days(0)}).status_code == 404
    assert client.get(f"/api/owner-accounts/{owner['id']}").status_code == 401


def test_owner_portal_hides_the_commission_unless_the_agency_allows_it(client, register_agency):
    agency = register_agency(agency_name="Agencia P", email="p@demo.com")
    owner, _, _ = _setup(client, agency["headers"])
    client.post(f"/api/owner-accounts/{owner['id']}/payouts", headers=agency["headers"], json={"amount": 150, "paidAt": _days(0)})

    portal = client.get(f"/api/public/owners/{owner['accessToken']}").get_json()
    totals = portal["statement"]["totals"][0]
    assert "commission" not in totals and "commission" not in portal["statement"]["bookings"][0]
    assert (totals["due"], totals["paidOut"], totals["balance"]) == (500.0, 150.0, 350.0)

    res = client.patch("/api/agency/", headers=agency["headers"], json={"ownerPortalShowsCommission": True})
    assert res.status_code == 200 and res.get_json()["ownerPortalShowsCommission"] is True
    portal = client.get(f"/api/public/owners/{owner['accessToken']}").get_json()
    assert portal["statement"]["totals"][0]["commission"] == 100.0
    assert portal["statement"]["bookings"][0]["commission"] == 100.0
