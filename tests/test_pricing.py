from datetime import date, timedelta


def _day(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


def _rental(client, headers, **rules):
    prop = client.post(
        "/api/properties/", headers=headers, json={"title": "Villa", "listingType": "RENT", "category": "HOUSE"}
    ).get_json()
    client.patch(f"/api/properties/{prop['id']}", headers=headers, json={"price": 100, "currency": "EUR", **rules})
    return prop


def test_quote_prices_each_night_and_applies_the_discounts_in_order(client, register_agency):
    headers = register_agency()["headers"]
    prop = _rental(client, headers, weeklyDiscountPct=10, earlyBirdDiscountPct=5, earlyBirdDays=60)
    client.post(
        f"/api/properties/{prop['id']}/rates",
        headers=headers,
        json={"label": "Alta", "startDate": _day(93), "endDate": _day(95), "officialPricePerNight": 150},
    )
    quote = client.get(f"/api/properties/{prop['id']}/quote?start={_day(90)}&end={_day(98)}", headers=headers).get_json()

    assert quote["nights"] == 8 and quote["currency"] == "EUR"
    assert [(line["label"], line["price"], line["nights"]) for line in quote["lines"]] == [
        (None, 100, 3),
        ("Alta", 150, 3),
        (None, 100, 2),
    ]
    assert quote["subtotal"] == 950
    assert [(item["kind"], item["amount"]) for item in quote["discounts"]] == [("WEEKLY", 95), ("EARLY_BIRD", 42.75)]
    assert quote["total"] == 812.25
    assert quote["meetsMinStay"] and quote["available"]


def test_last_minute_min_stay_and_availability(client, register_agency):
    headers = register_agency()["headers"]
    prop = _rental(client, headers, minStay=2, lastMinuteDiscountPct=20, lastMinuteDays=7)
    # The season around check-in asks for 5 nights.
    client.post(
        f"/api/properties/{prop['id']}/rates",
        headers=headers,
        json={"startDate": _day(0), "endDate": _day(10), "minStay": 5},
    )
    quote = client.get(f"/api/properties/{prop['id']}/quote?start={_day(2)}&end={_day(5)}", headers=headers).get_json()
    assert quote["subtotal"] == 300 and quote["total"] == 240
    assert quote["discounts"][0]["kind"] == "LAST_MINUTE"
    assert quote["minStay"] == 5 and quote["meetsMinStay"] is False

    client.post(
        f"/api/properties/{prop['id']}/availability/", headers=headers, json={"startDate": _day(3), "endDate": _day(4)}
    )
    quote = client.get(f"/api/properties/{prop['id']}/quote?start={_day(2)}&end={_day(5)}", headers=headers).get_json()
    assert quote["available"] is False

    assert client.get(f"/api/properties/{prop['id']}/quote?start={_day(5)}&end={_day(2)}", headers=headers).status_code == 400
    assert client.get(f"/api/properties/{prop['id']}/quote?start=nope", headers=headers).status_code == 400


def test_public_quote_only_for_published_rentals(client, register_agency):
    headers = register_agency(agency_name="Agencia Precios", email="owner@precios.com")["headers"]
    prop = _rental(client, headers)
    url = f"/api/public/agencia-precios/properties/{prop['slug']}/quote?start={_day(30)}&end={_day(33)}"
    assert client.get(url).status_code == 404
    client.post(f"/api/properties/{prop['id']}/publish", headers=headers)
    body = client.get(url).get_json()
    assert body["total"] == 300

    # A rental without a price has no total to show.
    client.patch(f"/api/properties/{prop['id']}", headers=headers, json={"price": None})
    assert client.get(url).get_json()["total"] is None
