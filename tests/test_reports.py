from datetime import date, timedelta

from tests.test_workflow import _invite_agent


def _month_start(offset_months: int) -> date:
    """The first day of the month `offset_months` from now, so bookings stay in the future."""
    today = date.today().replace(day=1)
    year, month = divmod(today.month - 1 + offset_months, 12)
    return date(today.year + year, month + 1, 1)


def _rental(client, headers, title):
    return client.post(
        "/api/properties/", headers=headers, json={"title": title, "listingType": "RENT", "category": "HOUSE"}
    ).get_json()


def test_report_is_for_owners_and_admins(client, register_agency):
    owner = register_agency()
    agent = _invite_agent(client, owner["headers"])
    assert client.get("/api/reports/", headers=agent["headers"]).status_code == 403
    assert client.get("/api/reports/", headers=owner["headers"]).status_code == 200
    assert client.get("/api/reports/?from=2026-05-01&to=2026-01-01", headers=owner["headers"]).status_code == 400
    assert client.get("/api/reports/?from=nope", headers=owner["headers"]).status_code == 400


def test_money_occupancy_conversion_and_team(client, register_agency):
    owner = register_agency(agency_name="Agencia Reportes", email="owner@reportes.com")
    headers = owner["headers"]
    agent = _invite_agent(client, headers)
    month = _month_start(2)
    days_in_month = ((month.replace(day=28) + timedelta(days=4)).replace(day=1) - month).days
    window = f"from={month.isoformat()}&to={month.isoformat()}"

    villa = _rental(client, headers, "Villa")
    loft = _rental(client, headers, "Loft")

    # Someone writes in and the agent books them: 5 nights, confirmed, with a paid deposit.
    client.post(f"/api/properties/{villa['id']}/publish", headers=headers)
    client.post("/api/public/agencia-reportes/inquiries", json={"name": "Lucía", "email": "lucia@demo.com"})
    lead = client.get("/api/clients/", headers=headers).get_json()[0]
    client.patch(f"/api/clients/{lead['id']}", headers=headers, json={"assignedAgentId": agent["id"]})
    client.patch(f"/api/properties/{villa['id']}", headers=headers, json={"assignedAgentId": agent["id"]})
    booking = client.post(
        "/api/bookings/",
        headers=agent["headers"],
        json={
            "propertyId": villa["id"],
            "clientId": lead["id"],
            "startDate": (month + timedelta(days=9)).isoformat(),
            "endDate": (month + timedelta(days=14)).isoformat(),
            "totalPrice": 1000,
            "commissionAmount": 150,
            "currency": "EUR",
        },
    )
    assert booking.status_code == 201, booking.get_json()
    booking = booking.get_json()
    client.post(f"/api/bookings/{booking['id']}/confirm", headers=headers)
    client.post(
        f"/api/bookings/{booking['id']}/payments",
        headers=headers,
        json={"amount": 300, "currency": "EUR", "type": "DEPOSIT", "status": "PAID", "paidAt": f"{month.isoformat()}T12:00:00"},
    )
    # The agency's commission isn't money the client paid.
    client.post(
        f"/api/bookings/{booking['id']}/payments",
        headers=headers,
        json={"amount": 150, "currency": "EUR", "type": "COMMISSION", "status": "PAID", "paidAt": f"{month.isoformat()}T12:00:00"},
    )
    # A pending booking doesn't count yet.
    client.post(
        "/api/bookings/",
        headers=headers,
        json={"propertyId": loft["id"], "startDate": (month + timedelta(days=1)).isoformat(), "endDate": (month + timedelta(days=3)).isoformat(), "totalPrice": 999, "currency": "EUR"},
    )
    # The owner blocks 10 nights of the loft by hand: out of the market, not occupied.
    client.post(
        f"/api/properties/{loft['id']}/availability/",
        headers=headers,
        json={"startDate": (month + timedelta(days=4)).isoformat(), "endDate": (month + timedelta(days=14)).isoformat()},
    )

    report = client.get(f"/api/reports/?{window}", headers=headers).get_json()
    assert report["from"] == month.isoformat()

    eur = report["money"]["EUR"]
    assert [row["month"] for row in eur] == [month.strftime("%Y-%m")]
    assert eur[0] == {"month": month.strftime("%Y-%m"), "booked": 1000, "collected": 300, "commission": 150, "bookings": 1}

    occupancy = {row["title"]: row for row in report["occupancy"]}
    assert occupancy["Villa"]["booked"] == 5 and occupancy["Villa"]["nights"] == days_in_month
    assert occupancy["Villa"]["rate"] == round(5 / days_in_month, 4)
    assert occupancy["Loft"]["blocked"] == 10 and occupancy["Loft"]["rate"] == 0

    conversion = report["conversion"]
    # The inquiry was today, not in that month: it doesn't count there.
    assert conversion["inquiries"] == 0
    this_month = date.today().replace(day=1).isoformat()
    conversion = client.get(f"/api/reports/?from={this_month}&to={this_month}", headers=headers).get_json()["conversion"]
    assert (conversion["inquiries"], conversion["clients"], conversion["booked"], conversion["rate"]) == (1, 1, 1, 1)

    team = {row["name"]: row for row in report["team"]}
    assert team["Agente Uno"]["bookings"] == 1
    assert team["Agente Uno"]["booked"] == {"EUR": 1000} and team["Agente Uno"]["commission"] == {"EUR": 150}
    assert team["Owner"]["bookings"] == 0
