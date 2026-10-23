from unittest.mock import patch

from app.extensions import db
from app.models import Client, User
from tests.test_bookings import _create_client, _create_property
from tests.test_crm import _create_published_property

SEND = "app.services.notifications.email_service.send_email"


def test_errors_come_back_in_the_requested_language(client, register_agency):
    agency = register_agency()
    res = client.get("/api/offers/no-existe", headers={**agency["headers"], "X-Locale": "de"})
    assert res.status_code == 404
    assert res.get_json()["message"] == "Angebot nicht gefunden."

    res = client.get("/api/offers/no-existe", headers={**agency["headers"], "X-Locale": "es"})
    assert res.get_json()["message"] == "No encontramos la oferta."


def test_without_a_language_errors_are_untouched(client, register_agency):
    agency = register_agency()
    res = client.get("/api/offers/no-existe", headers=agency["headers"])
    assert res.get_json()["message"] == "Offer not found"


def test_field_errors_are_translated_too(client):
    res = client.post("/api/auth/login", json={"email": "no-es-email"}, headers={"X-Locale": "en"})
    body = res.get_json()
    assert body["message"] == "Please check the form: some fields have errors."
    assert body["errors"]["email"] == ["The email address isn’t valid."]
    assert body["errors"]["password"] == ["This field is required."]


def test_the_dashboard_language_is_remembered(client, app, register_agency):
    agency = register_agency(email="owner@idioma.com")
    client.get("/api/auth/me", headers={**agency["headers"], "X-Locale": "it"})
    assert User.query.filter_by(email="owner@idioma.com").one().locale == "it"


def test_inquiry_emails_speak_each_readers_language(client, app, register_agency):
    agency = register_agency(agency_name="Agencia Idiomas", email="owner@idiomas.com")
    prop = _create_published_property(client, agency["headers"], title="Casa Azul")
    client.get("/api/auth/me", headers={**agency["headers"], "X-Locale": "de"})

    with patch(SEND) as send:
        client.post(
            "/api/public/agencia-idiomas/inquiries",
            json={"name": "John", "email": "john@demo.com", "propertyId": prop["id"], "inquiryType": "PROPERTY"},
            headers={"X-Locale": "en"},
        )

    alert, confirmation = send.call_args_list
    assert alert.args[1] == "Neue Anfrage von John zu Casa Azul"
    assert confirmation.args[0] == ["john@demo.com"]
    assert confirmation.args[1] == "We received your inquiry about Casa Azul"
    assert confirmation.kwargs["locale"] == "en"
    assert Client.query.filter_by(email="john@demo.com").one().locale == "en"

    detail = client.get("/api/clients/", headers=agency["headers"]).get_json()
    person = client.get(f"/api/clients/{detail[0]['id']}", headers=agency["headers"]).get_json()
    assert person["interactions"][0]["content"] == "Hat zu „Casa Azul“ angefragt"


def test_bell_keeps_the_values_and_titles_in_the_readers_language(client, register_agency):
    agency = register_agency(agency_name="Agencia Campana", email="owner@campana.com")
    client.get("/api/auth/me", headers={**agency["headers"], "X-Locale": "fr"})
    client.post("/api/public/agencia-campana/inquiries", json={"name": "Ana", "email": "ana@demo.com"})

    item = client.get("/api/notifications/", headers=agency["headers"]).get_json()["items"][0]
    assert item["params"] == {"name": "Ana", "message": None}
    assert item["title"] == "Nouvelle demande de Ana"
    assert item["body"] == "A laissé ses coordonnées."


def test_booking_emails_use_the_clients_language_and_link(client, register_agency):
    agency = register_agency(agency_name="Agencia Booking Idioma", email="owner@bi.com")
    prop = _create_property(client, agency["headers"])
    person = _create_client(client, agency["headers"])
    record = db.session.get(Client, person["id"])
    record.locale = "pt"
    db.session.commit()

    with patch(SEND) as send:
        booking = client.post(
            "/api/bookings/", headers=agency["headers"], json={"propertyId": prop["id"], "clientId": person["id"]}
        ).get_json()

    assert send.call_args.args[1] == "A sua reserva em Casa Booking"
    assert f"/pt/booking/{booking['token']}" in send.call_args.args[2]
    assert send.call_args.kwargs["locale"] == "pt"


def test_the_importer_speaks_the_dashboard_language(client, register_agency):
    from tests.test_imports import _post

    agency = register_agency(agency_name="Agencia Importa", email="owner@importa.com")
    headers = {**agency["headers"], "X-Locale": "en"}
    fields = client.get("/api/imports/fields", headers=headers).get_json()
    assert next(f for f in fields if f["key"] == "area_sqm")["label"] == "Built area (m²)"

    csv = "Ref;Tipo;Precio;Ciudad\nA1;Castillo;muchos;Madrid\n"
    preview = _post(client, headers, "preview", fmt="table", content=csv).get_json()
    warnings = preview["rows"][0]["warnings"]
    assert "Property type “Castillo” not recognised; it was taken as a house." in warnings
    assert "Price: “muchos” isn’t a number." in warnings

    res = _post(client, headers, "preview", fmt="nope", content=csv)
    assert res.get_json()["message"] == "Unknown import format"
