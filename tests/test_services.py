import io
from unittest.mock import patch


def _service(client, headers, **fields):
    body = {"name": "Chef privado", "type": "CHEF", "price": 300, "unit": "DAY", "zones": ["Ibiza"], **fields}
    return client.post("/api/services/", headers=headers, json=body)


def test_service_library_crud_is_scoped_to_the_agency(client, register_agency):
    agency = register_agency()
    other = register_agency(agency_name="Otra", email="owner@otra.com")
    created = _service(client, agency["headers"])
    assert created.status_code == 201
    service = created.get_json()
    assert service["unit"] == "DAY" and service["zones"] == ["Ibiza"] and service["active"] is True

    assert len(client.get("/api/services/", headers=agency["headers"]).get_json()) == 1
    assert client.get("/api/services/", headers=other["headers"]).get_json() == []
    assert client.get(f"/api/services/{service['id']}", headers=other["headers"]).status_code == 404

    updated = client.patch(f"/api/services/{service['id']}", headers=agency["headers"], json={"price": None, "active": False})
    assert updated.get_json()["price"] is None and updated.get_json()["active"] is False

    assert client.delete(f"/api/services/{service['id']}", headers=agency["headers"]).status_code == 204
    assert client.get("/api/services/", headers=agency["headers"]).get_json() == []


def test_deleted_service_goes_to_trash_and_comes_back(client, register_agency):
    agency = register_agency()
    other = register_agency(agency_name="Otra", email="owner@otra.com")
    headers = agency["headers"]
    service = _service(client, headers).get_json()

    assert client.delete(f"/api/services/{service['id']}", headers=headers).status_code == 204
    assert client.get("/api/services/", headers=headers).get_json() == []
    assert client.get(f"/api/services/{service['id']}", headers=headers).status_code == 404
    trashed = client.get("/api/services/trash", headers=headers).get_json()
    assert [item["id"] for item in trashed] == [service["id"]] and trashed[0]["deletedAt"]
    assert client.get("/api/services/trash", headers=other["headers"]).get_json() == []
    assert client.post(f"/api/services/{service['id']}/restore", headers=other["headers"]).status_code == 404

    # Only what is in the trash can be deleted for good.
    live = _service(client, headers, name="Yate").get_json()
    assert client.delete(f"/api/services/{live['id']}/permanent", headers=headers).status_code == 404

    restored = client.post(f"/api/services/{service['id']}/restore", headers=headers)
    assert restored.status_code == 200 and restored.get_json()["deletedAt"] is None
    assert len(client.get("/api/services/", headers=headers).get_json()) == 2

    client.delete(f"/api/services/{service['id']}", headers=headers)
    assert client.delete(f"/api/services/{service['id']}/permanent", headers=headers).status_code == 204
    assert client.get("/api/services/trash", headers=headers).get_json() == []


def test_trashed_service_cant_be_linked_to_an_offer(client, register_agency):
    headers = register_agency()["headers"]
    service = _service(client, headers).get_json()
    client.delete(f"/api/services/{service['id']}", headers=headers)
    offer = client.post(
        "/api/offers/",
        headers=headers,
        json={"title": "Oferta", "sections": [], "services": [{"serviceId": service["id"], "name": "Chef privado"}]},
    ).get_json()
    assert offer["services"][0]["serviceId"] is None


def test_service_validation(client, register_agency):
    agency = register_agency()
    assert _service(client, agency["headers"], type="SPACESHIP").status_code == 400
    assert _service(client, agency["headers"], price=-5).status_code == 400
    assert _service(client, agency["headers"], name="x").status_code == 400


def test_offer_keeps_its_own_copy_of_services_and_totals_them(client, register_agency):
    agency = register_agency()
    headers = agency["headers"]
    library = _service(client, headers).get_json()
    offer = client.post("/api/offers/", headers=headers, json={"title": "Oferta", "sections": []}).get_json()

    res = client.patch(
        f"/api/offers/{offer['id']}",
        headers=headers,
        json={
            "services": [
                {"serviceId": library["id"], "name": "Chef privado", "type": "CHEF", "unit": "DAY", "unitPrice": 250, "quantity": 3},
                {"name": "Yate", "type": "YACHT", "unit": "SERVICE", "unitPrice": None, "quantity": 1, "date": "2026-12-20"},
            ]
        },
    )
    body = res.get_json()
    assert [item["name"] for item in body["services"]] == ["Chef privado", "Yate"]
    assert body["services"][0]["total"] == 750 and body["services"][0]["serviceId"] == library["id"]
    assert body["services"][1]["unitPrice"] is None and body["services"][1]["date"] == "2026-12-20"
    assert body["servicesTotal"] == 750

    # Trashing it from the library doesn't touch the offer; deleting it for good only cuts the link.
    client.delete(f"/api/services/{library['id']}", headers=headers)
    again = client.get(f"/api/offers/{offer['id']}", headers=headers).get_json()
    assert again["services"][0]["name"] == "Chef privado" and again["services"][0]["serviceId"] == library["id"]
    client.delete(f"/api/services/{library['id']}/permanent", headers=headers)
    again = client.get(f"/api/offers/{offer['id']}", headers=headers).get_json()
    assert again["services"][0]["name"] == "Chef privado" and again["services"][0]["serviceId"] is None


def test_public_offer_shows_services_and_hides_prices_when_asked(client, register_agency):
    agency = register_agency()
    headers = agency["headers"]
    offer = client.post(
        "/api/offers/",
        headers=headers,
        json={"title": "Oferta", "sections": [], "showPrice": False,
              "services": [{"name": "Mayordomo", "type": "BUTLER", "unitPrice": 100, "quantity": 2}]},
    ).get_json()
    client.post(f"/api/offers/{offer['id']}/send", headers=headers)

    public = client.get(f"/api/public/offers/{offer['token']}").get_json()
    assert public["services"][0]["name"] == "Mayordomo"
    assert public["services"][0]["unitPrice"] is None and public["servicesTotal"] is None
    assert "serviceId" not in public["services"][0]


def test_other_agencies_services_are_not_linked(client, register_agency):
    agency = register_agency()
    other = register_agency(agency_name="Otra", email="owner@otra.com")
    foreign = _service(client, other["headers"]).get_json()
    offer = client.post(
        "/api/offers/",
        headers=agency["headers"],
        json={"title": "Oferta", "sections": [], "services": [{"serviceId": foreign["id"], "name": "Chef"}]},
    ).get_json()
    assert offer["services"][0]["serviceId"] is None


def test_service_image_upload_returns_url(client, register_agency):
    agency = register_agency()
    with patch(
        "app.blueprints.service_library.routes.storage_service.upload_agency_site_image",
        return_value="https://fake-bucket.supabase.co/agency-site/yate.webp",
    ):
        res = client.post(
            "/api/services/image",
            headers=agency["headers"],
            data={"file": (io.BytesIO(b"fake-webp-bytes"), "yate.webp")},
            content_type="multipart/form-data",
        )
    assert res.status_code == 200 and res.get_json()["url"].endswith("yate.webp")
