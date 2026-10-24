from unittest.mock import patch

from tests.test_crm import _create_published_property


def _ask(client, slug, **overrides):
    payload = {"name": "Lucía", "email": "lucia@demo.com", "message": "¿Sigue disponible?", **overrides}
    return client.post(f"/api/public/{slug}/inquiries", json=payload)


def test_inbox_lists_inquiries_with_their_listing_newest_first(client, register_agency):
    agency = register_agency(agency_name="Agencia Bandeja", email="owner@bandeja.com")
    prop = _create_published_property(client, agency["headers"], title="Casa en La Barra")
    _ask(client, "agencia-bandeja", message="Primera")
    _ask(client, "agencia-bandeja", propertyId=prop["id"], inquiryType="PROPERTY", message="Segunda")

    inbox = client.get("/api/inquiries/", headers=agency["headers"]).get_json()
    assert [item["message"] for item in inbox] == ["Segunda", "Primera"]
    assert inbox[0]["property"]["title"] == "Casa en La Barra"
    assert inbox[0]["client"]["name"] == "Lucía"
    assert inbox[0]["readAt"] is None
    assert inbox[1]["property"] is None


def test_unread_count_and_marking_read(client, register_agency):
    agency = register_agency(agency_name="Agencia Leidas", email="owner@leidas.com")
    _ask(client, "agencia-leidas")
    _ask(client, "agencia-leidas", email="otro@demo.com")
    headers = agency["headers"]

    assert client.get("/api/inquiries/unread-count", headers=headers).get_json()["count"] == 2
    first = client.get("/api/inquiries/", headers=headers).get_json()[0]

    marked = client.patch(f"/api/inquiries/{first['id']}", headers=headers, json={"read": True}).get_json()
    assert marked["readAt"] is not None
    assert client.get("/api/inquiries/unread-count", headers=headers).get_json()["count"] == 1
    assert len(client.get("/api/inquiries/?status=new", headers=headers).get_json()) == 1

    client.patch(f"/api/inquiries/{first['id']}", headers=headers, json={"read": False})
    assert client.get("/api/inquiries/unread-count", headers=headers).get_json()["count"] == 2

    assert client.post("/api/inquiries/read-all", headers=headers).get_json()["updated"] == 2
    assert client.get("/api/inquiries/unread-count", headers=headers).get_json()["count"] == 0


def test_marking_requires_a_boolean(client, register_agency):
    agency = register_agency(agency_name="Agencia Bool", email="owner@bool.com")
    _ask(client, "agencia-bool")
    item = client.get("/api/inquiries/", headers=agency["headers"]).get_json()[0]
    res = client.patch(f"/api/inquiries/{item['id']}", headers=agency["headers"], json={"read": "si"})
    assert res.status_code == 400


def test_inbox_only_shows_the_agencys_own_inquiries(client, register_agency):
    mine = register_agency(agency_name="Agencia Mia", email="owner@mia.com")
    other = register_agency(agency_name="Agencia Otra", email="owner@otra.com")
    _ask(client, "agencia-otra")

    assert client.get("/api/inquiries/", headers=mine["headers"]).get_json() == []
    foreign = client.get("/api/inquiries/", headers=other["headers"]).get_json()[0]
    res = client.patch(f"/api/inquiries/{foreign['id']}", headers=mine["headers"], json={"read": True})
    assert res.status_code == 404


def test_inquiry_emails_the_agency_and_confirms_to_the_person(client, register_agency):
    agency = register_agency(agency_name="Agencia Avisos", email="owner@avisos.com")
    prop = _create_published_property(client, agency["headers"], title="Depto con vista")

    with patch("app.services.notifications.email_service.send_email") as send:
        _ask(client, "agencia-avisos", propertyId=prop["id"], inquiryType="PROPERTY")

    assert send.call_count == 2
    to_agency, to_person = send.call_args_list
    # No contact email set: the owner gets it, and replying goes straight to the person.
    assert to_agency.args[0] == ["owner@avisos.com"]
    assert "Depto con vista" in to_agency.args[1]
    assert to_agency.kwargs["reply_to"] == "lucia@demo.com"
    assert to_person.args[0] == ["lucia@demo.com"]
    assert to_person.kwargs["from_name"] == "Agencia Avisos"


def test_agency_contact_email_receives_the_notice_when_set(client, register_agency):
    agency = register_agency(agency_name="Agencia Contacto", email="owner@contacto.com")
    client.patch("/api/agency/", headers=agency["headers"], json={"contactEmail": "ventas@contacto.com"})

    with patch("app.services.notifications.email_service.send_email") as send:
        _ask(client, "agencia-contacto")

    assert send.call_args_list[0].args[0] == ["ventas@contacto.com"]


def test_confirmation_never_repeats_what_the_sender_wrote(client, register_agency):
    register_agency(agency_name="Agencia Eco", email="owner@eco.com")

    with patch("app.services.notifications.email_service.send_email") as send:
        _ask(client, "agencia-eco", name="Click http://phish.example", message="Ganaste: http://phish.example")

    confirmation = send.call_args_list[1]
    html = confirmation.args[2]
    assert "phish.example" not in html
    assert "phish.example" not in confirmation.args[1]


def test_confirmation_goes_out_once_a_day_per_address(client, register_agency):
    register_agency(agency_name="Agencia Una", email="owner@una.com")

    with patch("app.services.notifications.email_service.send_email") as send:
        _ask(client, "agencia-una")
        _ask(client, "agencia-una", email="LUCIA@demo.com", message="Otra vez")

    recipients = [call.args[0] for call in send.call_args_list]
    # Both reach the agency; only the first is confirmed to the person.
    assert recipients.count(["owner@una.com"]) == 2
    assert recipients.count(["lucia@demo.com"]) == 1


def test_from_display_name_cannot_change_the_sender_address(app):
    from app.services.email_service import _display_name

    assert _display_name('Banco "Seguro" <ceo@bank.com>\r\nBcc: x@y.com') == "Banco Seguro ceo@bank.com Bcc: x@y.com vía Tivvu"
    assert _display_name("   ") == "Tivvu"
    assert len(_display_name("x" * 200)) <= 60 + len(" vía Tivvu")


def test_inbox_timestamps_say_they_are_utc(client, register_agency):
    agency = register_agency(agency_name="Agencia Hora", email="owner@hora.com")
    _ask(client, "agencia-hora")
    item = client.get("/api/inquiries/", headers=agency["headers"]).get_json()[0]
    # Without the offset, browsers read the time as local and it drifts by the timezone.
    assert item["createdAt"].endswith("+00:00")


def test_archived_inquiries_leave_the_inbox_and_the_unread_count(client, register_agency):
    agency = register_agency(agency_name="Agencia Archivo", email="owner@archivo.com")
    headers = agency["headers"]
    _ask(client, "agencia-archivo")
    _ask(client, "agencia-archivo", email="otro@demo.com")
    first = client.get("/api/inquiries/", headers=headers).get_json()[0]

    res = client.patch(f"/api/inquiries/{first['id']}", headers=headers, json={"archived": True})
    assert res.status_code == 200 and res.get_json()["archivedAt"]
    assert len(client.get("/api/inquiries/", headers=headers).get_json()) == 1
    assert client.get("/api/inquiries/unread-count", headers=headers).get_json()["count"] == 1
    archived = client.get("/api/inquiries/?status=archived", headers=headers).get_json()
    assert [item["id"] for item in archived] == [first["id"]]

    client.patch(f"/api/inquiries/{first['id']}", headers=headers, json={"archived": False})
    assert len(client.get("/api/inquiries/", headers=headers).get_json()) == 2
    assert client.patch(f"/api/inquiries/{first['id']}", headers=headers, json={"archived": "yes"}).status_code == 400


def test_deleted_inquiry_goes_to_trash_and_comes_back(client, register_agency):
    agency = register_agency(agency_name="Agencia Papelera", email="owner@papelera.com")
    headers = agency["headers"]
    _ask(client, "agencia-papelera")
    inquiry = client.get("/api/inquiries/", headers=headers).get_json()[0]

    assert client.delete(f"/api/inquiries/{inquiry['id']}", headers=headers).status_code == 204
    assert client.get("/api/inquiries/", headers=headers).get_json() == []
    assert client.get("/api/inquiries/unread-count", headers=headers).get_json()["count"] == 0
    trashed = client.get("/api/inquiries/trash", headers=headers).get_json()
    assert [item["id"] for item in trashed] == [inquiry["id"]] and trashed[0]["deletedAt"]
    # The client stays.
    assert len(client.get("/api/clients/", headers=headers).get_json()) == 1

    assert client.post(f"/api/inquiries/{inquiry['id']}/restore", headers=headers).status_code == 200
    assert len(client.get("/api/inquiries/", headers=headers).get_json()) == 1

    client.delete(f"/api/inquiries/{inquiry['id']}", headers=headers)
    assert client.delete(f"/api/inquiries/{inquiry['id']}/permanent", headers=headers).status_code == 204
    assert client.get("/api/inquiries/trash", headers=headers).get_json() == []


def test_reply_emails_the_sender_and_logs_it_in_the_client_history(client, register_agency):
    agency = register_agency(agency_name="Agencia Responde", email="owner@responde.com")
    headers = agency["headers"]
    _ask(client, "agencia-responde")
    inquiry = client.get("/api/inquiries/", headers=headers).get_json()[0]

    with patch("app.services.email_service.send_email") as send:
        res = client.post(
            f"/api/inquiries/{inquiry['id']}/reply",
            headers=headers,
            json={"subject": "Re: tu consulta", "body": "Hola Lucía,\nSí, sigue disponible."},
        )
    assert res.status_code == 200
    body = res.get_json()
    assert body["repliedAt"] and body["repliedBy"] == "Owner" and body["readAt"]
    send.assert_called_once()
    args, kwargs = send.call_args
    assert args[0] == ["lucia@demo.com"] and args[1] == "Re: tu consulta"
    assert "Sí, sigue disponible." in args[2]
    assert kwargs["from_name"] == "Agencia Responde" and kwargs["reply_to"] == "owner@responde.com"

    detail = client.get(f"/api/clients/{inquiry['client']['id']}", headers=headers).get_json()
    assert detail["interactions"][0]["type"] == "EMAIL"
    assert "Sí, sigue disponible." in detail["interactions"][0]["content"]

    empty = client.post(f"/api/inquiries/{inquiry['id']}/reply", headers=headers, json={"subject": "", "body": "x"})
    assert empty.status_code == 400


def test_reply_templates_crud_is_scoped_to_the_agency(client, register_agency):
    headers = register_agency(agency_name="Agencia Plantillas", email="owner@plantillas.com")["headers"]
    other = register_agency(agency_name="Otra", email="owner@otra.com")["headers"]

    res = client.post(
        "/api/inquiries/templates",
        headers=headers,
        json={"name": "Disponible", "subject": "Sobre {property}", "body": "Hola {firstName}, sigue disponible."},
    )
    assert res.status_code == 201
    template = res.get_json()
    assert [item["name"] for item in client.get("/api/inquiries/templates", headers=headers).get_json()] == ["Disponible"]
    assert client.get("/api/inquiries/templates", headers=other).get_json() == []
    assert client.patch(f"/api/inquiries/templates/{template['id']}", headers=other, json={"name": "X"}).status_code == 404

    res = client.patch(f"/api/inquiries/templates/{template['id']}", headers=headers, json={"name": "Sigue disponible"})
    assert res.get_json()["name"] == "Sigue disponible"
    assert client.post("/api/inquiries/templates", headers=headers, json={"name": "Sin texto"}).status_code == 400
    assert client.delete(f"/api/inquiries/templates/{template['id']}", headers=headers).status_code == 204
    assert client.get("/api/inquiries/templates", headers=headers).get_json() == []
