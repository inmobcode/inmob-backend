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
