def _history(client, headers, kind, entity_id):
    return client.get(f"/api/{kind}/{entity_id}/history", headers=headers).get_json()


def test_property_history_says_who_changed_what(client, register_agency):
    headers = register_agency()["headers"]
    prop = client.post(
        "/api/properties/", headers=headers, json={"title": "Casa", "listingType": "RENT", "category": "HOUSE"}
    ).get_json()
    client.patch(f"/api/properties/{prop['id']}", headers=headers, json={"price": 120, "title": "Casa del Lago"})
    client.post(f"/api/properties/{prop['id']}/rates", headers=headers, json={"startDate": "2027-01-01", "endDate": "2027-01-31"})
    client.delete(f"/api/properties/{prop['id']}", headers=headers)
    client.post(f"/api/properties/{prop['id']}/restore", headers=headers)

    events = _history(client, headers, "properties", prop["id"])
    assert [event["action"] for event in events][-1] == "CREATED"
    actions = [event["action"] for event in events]
    assert actions[:2] == ["RESTORED", "TRASHED"]
    edit = next(event for event in events if "price" in event["changes"])
    assert edit["changes"]["price"] == {"from": None, "to": 120}
    assert edit["changes"]["title"] == {"from": "Casa", "to": "Casa del Lago"}
    assert edit["userName"] == "Owner" and edit["byUser"] is True
    assert any(event["changes"].get("rates") == {"changed": True} for event in events)
    # Bookkeeping isn't listed.
    assert all("updated_at" not in event["changes"] for event in events)


def test_booking_and_offer_history(client, register_agency):
    headers = register_agency(agency_name="Agencia Historia", email="owner@historia.com")["headers"]
    prop = client.post(
        "/api/properties/", headers=headers, json={"title": "Casa", "listingType": "SALE", "category": "HOUSE"}
    ).get_json()
    booking = client.post("/api/bookings/", headers=headers, json={"propertyId": prop["id"], "totalPrice": 1000}).get_json()
    client.post(f"/api/bookings/{booking['id']}/payments", headers=headers, json={"amount": 100, "type": "DEPOSIT"})
    client.post(f"/api/bookings/{booking['id']}/confirm", headers=headers)
    client.patch(f"/api/bookings/{booking['id']}", headers=headers, json={"notes": "Llega tarde"})

    events = _history(client, headers, "bookings", booking["id"])
    changes = [event["changes"] for event in events]
    assert {"status": {"from": "PENDING", "to": "CONFIRMED"}}.items() <= next(c for c in changes if "status" in c).items()
    assert any("payments" in change for change in changes)
    # Notes are private: that they changed, not what they say.
    assert next(c for c in changes if "notes" in c)["notes"] == {"from": None, "to": None}

    offer = client.post("/api/offers/", headers=headers, json={"title": "Oferta", "sections": []}).get_json()
    client.patch(
        f"/api/offers/{offer['id']}", headers=headers, json={"sections": [{"properties": [{"propertyId": prop["id"]}]}]}
    )
    client.post(f"/api/offers/{offer['id']}/send", headers=headers)
    # The client opening the link isn't a change anyone made.
    client.post(f"/api/public/offers/{offer['token']}/views", json={})
    events = _history(client, headers, "offers", offer["id"])
    assert [event["action"] for event in events][-1] == "CREATED"
    assert any("properties" in event["changes"] for event in events)
    assert all("view_count" not in event["changes"] for event in events)
    # DRAFT -> SENT by the owner; SENT -> VIEWED when the client opened it, by nobody signed in.
    statuses = [event for event in events if "status" in event["changes"]]
    assert [(e["changes"]["status"]["to"], e["byUser"]) for e in statuses] == [("VIEWED", False), ("SENT", True)]

    # The client writing from the offer's page fills in its client: no user did that.
    client.post(f"/api/public/offers/{offer['token']}/inquiries", json={"name": "Lucía", "email": "lucia@demo.com"})
    latest = _history(client, headers, "offers", offer["id"])[0]
    assert latest["byUser"] is False and "client_id" in latest["changes"]


def test_saving_the_same_form_again_adds_nothing(client, register_agency):
    headers = register_agency(agency_name="Agencia Igual", email="owner@igual.com")["headers"]
    prop = client.post(
        "/api/properties/", headers=headers, json={"title": "Casa", "listingType": "RENT", "category": "HOUSE"}
    ).get_json()
    form = {"price": 100, "classification": {"parkingSpaces": 2}, "content": {"summary": "Linda"}}
    client.patch(f"/api/properties/{prop['id']}", headers=headers, json=form)
    before = len(_history(client, headers, "properties", prop["id"]))
    client.patch(f"/api/properties/{prop['id']}", headers=headers, json=form)
    assert len(_history(client, headers, "properties", prop["id"])) == before

    client.patch(f"/api/properties/{prop['id']}", headers=headers, json={**form, "classification": {"parkingSpaces": 3}})
    latest = _history(client, headers, "properties", prop["id"])[0]
    assert latest["changes"] == {"classification": {"changed": True}}
