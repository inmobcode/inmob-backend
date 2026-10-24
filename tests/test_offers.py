from unittest.mock import patch


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
    # Reading the link isn't an open (link previews read it too); the page reports opens.
    assert body["status"] == "SENT"
    # agency-internal fields must not leak publicly
    assert "agencyId" not in body
    assert "clientId" not in body
    assert "viewCount" not in body

    assert client.post(f"/api/public/offers/{offer['token']}/views", json={"device": "MOBILE"}).status_code == 204
    detail = client.get(f"/api/offers/{offer['id']}", headers=agency["headers"]).get_json()
    assert detail["status"] == "VIEWED" and detail["viewCount"] == 1
    assert detail["views"][0]["device"] == "MOBILE"


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


def test_offer_operation_limits_which_properties_it_holds(client, register_agency):
    agency = register_agency()
    rental = _create_property(client, agency["headers"], title="Depto temporario")
    sale = client.post(
        "/api/properties/",
        headers=agency["headers"],
        json={"title": "Casa en venta", "listingType": "SALE", "category": "HOUSE"},
    ).get_json()

    # Defaults to BOTH, which takes either kind.
    both = _create_offer(
        client,
        agency["headers"],
        "Mixta",
        [{"properties": [{"propertyId": rental["id"]}, {"propertyId": sale["id"]}]}],
    )
    assert both.status_code == 201
    assert both.get_json()["operation"] == "BOTH"

    res = client.post(
        "/api/offers/",
        headers=agency["headers"],
        json={
            "title": "Solo venta",
            "operation": "SALE",
            "sections": [{"properties": [{"propertyId": rental["id"]}]}],
        },
    )
    assert res.status_code == 400
    assert "alquiler" in res.get_json()["message"]

    # Narrowing an offer that already holds the other kind is refused too.
    res = client.patch(
        f"/api/offers/{both.get_json()['id']}", headers=agency["headers"], json={"operation": "RENT"}
    )
    assert res.status_code == 400


def _create_client(client, headers, name="Ana Pérez", email="ana@example.com"):
    return client.post("/api/clients/", headers=headers, json={"name": name, "email": email}).get_json()


def test_assigning_a_client_copies_its_contact_details(client, register_agency):
    agency = register_agency()
    crm_client = _create_client(client, agency["headers"])
    offer = _create_offer(client, agency["headers"], "Oferta", sections=[]).get_json()

    res = client.patch(f"/api/offers/{offer['id']}", headers=agency["headers"], json={"clientId": crm_client["id"]})
    body = res.get_json()
    assert body["clientId"] == crm_client["id"]
    assert body["clientName"] == "Ana Pérez"
    assert body["clientEmail"] == "ana@example.com"

    res = client.patch(f"/api/offers/{offer['id']}", headers=agency["headers"], json={"clientId": None})
    body = res.get_json()
    assert body["clientId"] is None
    assert body["clientEmail"] is None


def test_assigning_a_client_from_another_agency_fails(client, register_agency):
    agency = register_agency()
    other = register_agency(agency_name="Otra", email="owner@otra.com")
    foreign = _create_client(client, other["headers"])
    offer = _create_offer(client, agency["headers"], "Oferta", sections=[]).get_json()

    res = client.patch(f"/api/offers/{offer['id']}", headers=agency["headers"], json={"clientId": foreign["id"]})
    assert res.status_code == 404


def test_sending_an_offer_emails_its_client_and_logs_it(client, register_agency):
    agency = register_agency()
    crm_client = _create_client(client, agency["headers"])
    offer = _create_offer(client, agency["headers"], "Oferta verano", sections=[]).get_json()
    client.patch(f"/api/offers/{offer['id']}", headers=agency["headers"], json={"clientId": crm_client["id"]})

    with patch("app.services.notifications.email_service.send_email") as send:
        client.post(f"/api/offers/{offer['id']}/send", headers=agency["headers"])

    send.assert_called_once()
    to, subject, html = send.call_args.args
    assert to == ["ana@example.com"]
    assert "Oferta verano" in subject
    assert f"/offer/{offer['token']}" in html

    history = client.get(f"/api/clients/{crm_client['id']}", headers=agency["headers"]).get_json()["interactions"]
    assert any("Oferta verano" in item["content"] for item in history)


def test_sending_an_offer_without_client_sends_no_email(client, register_agency):
    agency = register_agency()
    offer = _create_offer(client, agency["headers"], "Oferta", sections=[]).get_json()

    with patch("app.services.notifications.email_service.send_email") as send:
        res = client.post(f"/api/offers/{offer['id']}/send", headers=agency["headers"])

    assert res.get_json()["status"] == "SENT"
    send.assert_not_called()


def test_resending_an_offer_emails_the_client_again_without_changing_status(client, register_agency):
    agency = register_agency()
    offer = _create_offer(client, agency["headers"], "Oferta", sections=[]).get_json()
    client.post(f"/api/offers/{offer['id']}/send", headers=agency["headers"])

    # Out already and still without client: nothing to send it to.
    res = client.post(f"/api/offers/{offer['id']}/send", headers=agency["headers"])
    assert res.status_code == 400

    crm_client = _create_client(client, agency["headers"])
    client.patch(f"/api/offers/{offer['id']}", headers=agency["headers"], json={"clientId": crm_client["id"]})
    with patch("app.services.notifications.email_service.send_email") as send:
        res = client.post(f"/api/offers/{offer['id']}/send", headers=agency["headers"])

    assert res.get_json()["status"] == "SENT"
    send.assert_called_once()


def test_welcome_content_keeps_formatting_and_drops_anything_else(client, register_agency):
    agency = register_agency()
    offer = _create_offer(client, agency["headers"], "Oferta", sections=[]).get_json()

    html = (
        '<h2>Hola</h2><p><strong>Una</strong> <em>propuesta</em> <a href="https://x.com" onclick="evil()">link</a></p>'
        '<script>alert(1)</script><p style="color:red">sin estilo</p><a href="javascript:alert(1)">no</a>'
    )
    res = client.patch(f"/api/offers/{offer['id']}", headers=agency["headers"], json={"welcomeContent": html})
    saved = res.get_json()["welcomeContent"]

    assert "<h2>Hola</h2>" in saved
    assert "<strong>Una</strong>" in saved and "<em>propuesta</em>" in saved
    assert 'href="https://x.com"' in saved
    for banned in ("script", "onclick", "style=", "javascript:"):
        assert banned not in saved


def test_welcome_content_plain_text_becomes_paragraphs_and_empty_becomes_null(client, register_agency):
    agency = register_agency()
    offer = _create_offer(client, agency["headers"], "Oferta", sections=[]).get_json()
    url = f"/api/offers/{offer['id']}"

    res = client.patch(url, headers=agency["headers"], json={"welcomeContent": "Hola\n\n<b>Chau</b>"})
    assert res.get_json()["welcomeContent"] == "<p>Hola</p><p>&lt;b&gt;Chau&lt;/b&gt;</p>"

    res = client.patch(url, headers=agency["headers"], json={"welcomeContent": "<p></p>"})
    assert res.get_json()["welcomeContent"] is None


def _sent_offer(client, headers, prop_id, title="Oferta"):
    offer = _create_offer(client, headers, title, sections=[{"properties": [{"propertyId": prop_id}]}]).get_json()
    client.post(f"/api/offers/{offer['id']}/send", headers=headers)
    return offer


def test_opens_are_counted_merged_and_ring_again_when_they_come_back(client, register_agency, app):
    from datetime import timedelta

    from app.extensions import db
    from app.models import Offer

    agency = register_agency()
    headers = agency["headers"]
    offer = _sent_offer(client, headers, _create_property(client, headers)["id"])
    views = f"/api/public/offers/{offer['token']}/views"
    bell = lambda: client.get("/api/notifications/unread-count", headers=headers).get_json()["count"]

    client.post(views, json={"device": "DESKTOP"})
    client.post(views, json={"device": "DESKTOP"})  # a reload: same visit
    detail = client.get(f"/api/offers/{offer['id']}", headers=headers).get_json()
    assert detail["viewCount"] == 1 and detail["firstViewedAt"] == detail["lastViewedAt"]
    assert bell() == 1

    # Two days later they open it again: counted, and the bell rings again.
    with app.app_context():
        row = db.session.get(Offer, offer["id"])
        row.last_viewed_at -= timedelta(days=2)
        db.session.commit()
    client.post(views, json={"device": "something else"})
    detail = client.get(f"/api/offers/{offer['id']}", headers=headers).get_json()
    assert detail["viewCount"] == 2 and detail["views"][0]["device"] is None
    assert bell() == 2
    listed = client.get("/api/offers/", headers=headers).get_json()[0]
    assert listed["viewCount"] == 2 and "views" not in listed

    draft = _create_offer(client, headers, "Borrador", sections=[]).get_json()
    assert client.post(f"/api/public/offers/{draft['token']}/views", json={}).status_code == 404


def test_duplicate_and_templates(client, register_agency):
    agency = register_agency()
    headers = agency["headers"]
    prop = _create_property(client, headers)
    lead = client.post("/api/clients/", headers=headers, json={"name": "Lucía", "email": "lucia@demo.com"}).get_json()
    offer = client.post(
        "/api/offers/",
        headers=headers,
        json={
            "title": "Verano",
            "clientId": lead["id"],
            "sections": [{"title": "Casas", "properties": [{"propertyId": prop["id"], "priceOverride": 900}]}],
        },
    ).get_json()

    copy = client.post(f"/api/offers/{offer['id']}/duplicate", headers=headers, json={}).get_json()
    assert copy["id"] != offer["id"] and copy["token"] != offer["token"]
    assert copy["status"] == "DRAFT" and copy["clientId"] is None and copy["isTemplate"] is False
    assert copy["sections"][0]["title"] == "Casas"
    assert copy["sections"][0]["properties"][0]["priceOverride"] == 900

    template = client.post(
        f"/api/offers/{offer['id']}/duplicate", headers=headers, json={"asTemplate": True, "title": "Base verano"}
    ).get_json()
    assert template["isTemplate"] is True and template["title"] == "Base verano"
    assert {item["id"] for item in client.get("/api/offers/", headers=headers).get_json()} == {offer["id"], copy["id"]}
    assert [item["id"] for item in client.get("/api/offers/?templates=1", headers=headers).get_json()] == [template["id"]]

    # A template has no public life.
    assert client.post(f"/api/offers/{template['id']}/send", headers=headers).status_code == 400
    assert client.get(f"/api/public/offers/{template['token']}").status_code == 404

    started = client.post(f"/api/offers/{template['id']}/duplicate", headers=headers, json={"title": "Para Tomás"})
    assert started.status_code == 201 and started.get_json()["isTemplate"] is False
    assert client.post(f"/api/offers/{offer['id']}/duplicate", headers=headers, json={"title": "x"}).status_code == 400


def test_booking_from_an_offer_accepts_it(client, register_agency):
    agency = register_agency()
    headers = agency["headers"]
    prop = _create_property(client, headers)
    offer = _sent_offer(client, headers, prop["id"])

    booking = client.post(
        "/api/bookings/", headers=headers, json={"propertyId": prop["id"], "offerId": offer["id"], "totalPrice": 1200}
    )
    assert booking.status_code == 201
    detail = client.get(f"/api/offers/{offer['id']}", headers=headers).get_json()
    assert detail["status"] == "ACCEPTED"
    assert [item["id"] for item in detail["bookings"]] == [booking.get_json()["id"]]

    # Accepted stays accepted: opening it doesn't turn it back into VIEWED.
    client.post(f"/api/public/offers/{offer['token']}/views", json={})
    assert client.get(f"/api/offers/{offer['id']}", headers=headers).get_json()["status"] == "ACCEPTED"

    template = client.post(f"/api/offers/{offer['id']}/duplicate", headers=headers, json={"asTemplate": True}).get_json()
    res = client.post("/api/bookings/", headers=headers, json={"propertyId": prop["id"], "offerId": template["id"]})
    assert res.status_code == 404
