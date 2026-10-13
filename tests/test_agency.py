import io
from unittest.mock import patch


def test_get_and_update_agency_profile(client, register_agency):
    agency = register_agency(agency_name="Agencia Config", email="config@demo.com")

    get_res = client.get("/api/agency/", headers=agency["headers"])
    assert get_res.status_code == 200
    body = get_res.get_json()
    assert body["name"] == "Agencia Config"
    assert body["slug"] == "agencia-config"
    assert body["currency"] == "USD"

    patch_res = client.patch(
        "/api/agency/",
        headers=agency["headers"],
        json={"name": "Agencia Renombrada", "contactEmail": "hola@agencia.com", "currency": "EUR"},
    )
    assert patch_res.status_code == 200
    updated = patch_res.get_json()
    assert updated["name"] == "Agencia Renombrada"
    assert updated["contactEmail"] == "hola@agencia.com"
    assert updated["currency"] == "EUR"
    # Slug is independent of name — renaming must not change the public portal URL.
    assert updated["slug"] == "agencia-config"


def test_slug_update_rejects_duplicate(client, register_agency):
    register_agency(agency_name="Primera Agencia", email="a@demo.com")
    agency_b = register_agency(agency_name="Segunda Agencia", email="b@demo.com")

    res = client.patch(
        "/api/agency/", headers=agency_b["headers"], json={"slug": "primera-agencia"}
    )
    assert res.status_code == 409


def test_slug_update_rejects_invalid_format(client, register_agency):
    agency = register_agency()
    res = client.patch("/api/agency/", headers=agency["headers"], json={"slug": "No Valido!"})
    assert res.status_code == 400


def test_logo_upload_goes_through_storage_service(client, register_agency):
    agency = register_agency()

    with patch(
        "app.blueprints.agency.routes.storage_service.upload_agency_logo",
        return_value="https://fake-bucket.supabase.co/property-photos/agency-logos/abc.webp",
    ) as mock_upload:
        res = client.post(
            "/api/agency/logo",
            headers=agency["headers"],
            data={"file": (io.BytesIO(b"fake-webp-bytes"), "logo.webp")},
            content_type="multipart/form-data",
        )
    assert res.status_code == 200
    mock_upload.assert_called_once()
    assert res.get_json()["logoUrl"].startswith("https://fake-bucket.supabase.co")


def test_public_agency_endpoint_returns_branding(client, register_agency):
    register_agency(agency_name="Agencia Branding", email="branding@demo.com")

    res = client.get("/api/public/agencia-branding")
    assert res.status_code == 200
    body = res.get_json()
    assert body["name"] == "Agencia Branding"
    assert "logoUrl" in body
    assert "id" not in body


def test_public_agency_endpoint_404s_for_unknown_slug(client):
    res = client.get("/api/public/no-existe")
    assert res.status_code == 404


def test_site_settings_default_to_empty_and_merge_on_update(client, register_agency):
    agency = register_agency(agency_name="Agencia Sitio", email="sitio@demo.com")

    assert client.get("/api/agency/", headers=agency["headers"]).get_json()["site"] == {}

    first = client.patch(
        "/api/agency/site",
        headers=agency["headers"],
        json={"template": "editorial", "accent": "#1F6F5C", "heroTitle": "Casas en la costa"},
    )
    assert first.status_code == 200
    second = client.patch("/api/agency/site", headers=agency["headers"], json={"fonts": "clasica"})
    site = second.get_json()["site"]
    # A partial update keeps what was saved before.
    assert site == {
        "template": "editorial",
        "accent": "#1F6F5C",
        "heroTitle": "Casas en la costa",
        "fonts": "clasica",
    }

    public = client.get("/api/public/agencia-sitio").get_json()
    assert public["site"]["template"] == "editorial"
    assert public["site"]["heroTitle"] == "Casas en la costa"


def test_site_settings_reject_unknown_template_and_bad_color(client, register_agency):
    agency = register_agency()
    assert client.patch("/api/agency/site", headers=agency["headers"], json={"template": "otro"}).status_code == 400
    assert client.patch("/api/agency/site", headers=agency["headers"], json={"accent": "verde"}).status_code == 400


def test_cover_upload_goes_through_storage_service(client, register_agency):
    agency = register_agency()

    with patch(
        "app.blueprints.agency.routes.storage_service.upload_agency_cover",
        return_value="https://fake-bucket.supabase.co/property-photos/agency-covers/abc.webp",
    ) as mock_upload:
        res = client.post(
            "/api/agency/cover",
            headers=agency["headers"],
            data={"file": (io.BytesIO(b"fake-webp-bytes"), "cover.webp")},
            content_type="multipart/form-data",
        )
    assert res.status_code == 200
    mock_upload.assert_called_once()
    assert res.get_json()["site"]["coverUrl"].startswith("https://fake-bucket.supabase.co")


def test_site_sections_round_trip_in_order(client, register_agency):
    agency = register_agency(agency_name="Agencia Bloques", email="bloques@demo.com")
    sections = [
        {"id": "ibiza", "type": "location", "title": "Ibiza", "zone": "Ibiza", "imageUrl": "https://img/ibiza.webp"},
        {
            "id": "verano",
            "type": "promo",
            "title": "Verano en la costa",
            "badge": "15% OFF",
            "propertyIds": ["p1", "p2"],
            "endsAt": "2026-12-31",
        },
    ]
    res = client.patch("/api/agency/site", headers=agency["headers"], json={"sections": sections})
    assert res.status_code == 200
    saved = res.get_json()["site"]["sections"]
    assert [section["id"] for section in saved] == ["ibiza", "verano"]
    assert saved[0]["visible"] is True
    assert saved[1]["propertyIds"] == ["p1", "p2"]
    assert saved[1]["endsAt"] == "2026-12-31"

    public = client.get("/api/public/agencia-bloques").get_json()
    assert public["site"]["sections"][0]["title"] == "Ibiza"


def test_site_sections_reject_unknown_type_and_bad_date(client, register_agency):
    agency = register_agency()
    bad_type = {"sections": [{"id": "x", "type": "carousel"}]}
    bad_date = {"sections": [{"id": "x", "type": "promo", "endsAt": "31/12/2026"}]}
    assert client.patch("/api/agency/site", headers=agency["headers"], json=bad_type).status_code == 400
    assert client.patch("/api/agency/site", headers=agency["headers"], json=bad_date).status_code == 400


def test_site_image_upload_returns_url(client, register_agency):
    agency = register_agency()

    with patch(
        "app.blueprints.agency.routes.storage_service.upload_agency_site_image",
        return_value="https://fake-bucket.supabase.co/property-photos/agency-site/abc.webp",
    ):
        res = client.post(
            "/api/agency/site-image",
            headers=agency["headers"],
            data={"file": (io.BytesIO(b"fake-webp-bytes"), "ibiza.webp")},
            content_type="multipart/form-data",
        )
    assert res.status_code == 200
    assert res.get_json()["url"].endswith("abc.webp")


def test_site_sections_support_layouts_and_new_block_types(client, register_agency):
    agency = register_agency(agency_name="Agencia Layouts", email="layouts@demo.com")
    sections = [
        {"id": "a", "type": "location", "layout": "carousel", "zone": "Ibiza", "propertyIds": ["p1"]},
        {
            "id": "b",
            "type": "destinations",
            "layout": "tiles",
            "destinations": [{"id": "d1", "name": "Mykonos", "zone": "Mykonos", "imageUrl": "https://img/m.webp"}],
        },
        {"id": "c", "type": "cta", "layout": "photo", "buttonLabel": "Escribinos", "buttonTarget": "whatsapp"},
        {"id": "d", "type": "text", "layout": "image-right"},
        {"id": "e", "type": "featured", "layout": "grid", "propertyIds": ["p2", "p3"]},
    ]
    res = client.patch("/api/agency/site", headers=agency["headers"], json={"sections": sections})
    assert res.status_code == 200
    saved = {section["id"]: section for section in res.get_json()["site"]["sections"]}
    assert saved["a"]["layout"] == "carousel"
    assert saved["a"]["propertyIds"] == ["p1"]
    assert saved["b"]["destinations"][0]["name"] == "Mykonos"
    assert saved["c"]["buttonTarget"] == "whatsapp"


def test_site_sections_reject_unknown_layout_and_button_target(client, register_agency):
    agency = register_agency()
    bad_layout = {"sections": [{"id": "x", "type": "text", "layout": "zigzag"}]}
    bad_target = {"sections": [{"id": "x", "type": "cta", "buttonTarget": "phone"}]}
    assert client.patch("/api/agency/site", headers=agency["headers"], json=bad_layout).status_code == 400
    assert client.patch("/api/agency/site", headers=agency["headers"], json=bad_target).status_code == 400


def test_agent_cannot_edit_agency_settings(client, register_agency):
    agency = register_agency(agency_name="Agencia Permisos", email="permisos@demo.com")
    with patch("app.services.team_service._send_invite_email") as mock_send:
        client.post(
            "/api/team/",
            headers=agency["headers"],
            json={"name": "Agent", "email": "agent@demo.com", "role": "AGENT"},
        )
    temp_password = mock_send.call_args[0][3]
    agent_token = client.post(
        "/api/auth/login", json={"email": "agent@demo.com", "password": temp_password}
    ).get_json()["accessToken"]
    agent_headers = {"Authorization": f"Bearer {agent_token}"}

    # Reading the agency's basic info stays open (the sidebar needs it for
    # every role), but editing it is OWNER/ADMIN only.
    assert client.get("/api/agency/", headers=agent_headers).status_code == 200
    assert client.patch("/api/agency/", headers=agent_headers, json={"name": "Hackeada"}).status_code == 403
    assert client.patch("/api/agency/site", headers=agent_headers, json={"template": "editorial"}).status_code == 403
