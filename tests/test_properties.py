def _create_property(client, headers, title="Casa en la playa"):
    return client.post(
        "/api/properties/",
        headers=headers,
        json={"title": title, "listingType": "SALE", "category": "HOUSE"},
    )


def test_create_and_get_property(client, register_agency):
    agency = register_agency()
    create_res = _create_property(client, agency["headers"])
    assert create_res.status_code == 201
    body = create_res.get_json()
    assert body["status"] == "DRAFT"
    assert body["slug"] == "casa-en-la-playa"

    get_res = client.get(f"/api/properties/{body['id']}", headers=agency["headers"])
    assert get_res.status_code == 200
    assert get_res.get_json()["title"] == "Casa en la playa"


def test_update_property_regenerates_slug_on_title_change(client, register_agency):
    agency = register_agency()
    prop = _create_property(client, agency["headers"]).get_json()

    res = client.patch(
        f"/api/properties/{prop['id']}",
        headers=agency["headers"],
        json={"title": "Casa Renovada", "price": 250000, "bedrooms": 3},
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body["slug"] == "casa-renovada"
    assert body["price"] == 250000
    assert body["bedrooms"] == 3


def test_publish_and_archive_lifecycle(client, register_agency):
    agency = register_agency()
    prop = _create_property(client, agency["headers"]).get_json()

    publish_res = client.post(
        f"/api/properties/{prop['id']}/publish", headers=agency["headers"]
    )
    assert publish_res.get_json()["status"] == "PUBLISHED"

    archive_res = client.post(
        f"/api/properties/{prop['id']}/archive", headers=agency["headers"]
    )
    assert archive_res.get_json()["status"] == "ARCHIVED"


def test_agency_cannot_access_another_agencys_property(client, register_agency):
    agency_a = register_agency(agency_name="Agencia A", email="a@demo.com")
    agency_b = register_agency(agency_name="Agencia B", email="b@demo.com")

    prop = _create_property(client, agency_a["headers"]).get_json()

    res = client.get(f"/api/properties/{prop['id']}", headers=agency_b["headers"])
    assert res.status_code == 404

    res = client.patch(
        f"/api/properties/{prop['id']}", headers=agency_b["headers"], json={"price": 1}
    )
    assert res.status_code == 404

    res = client.delete(f"/api/properties/{prop['id']}", headers=agency_b["headers"])
    assert res.status_code == 404


def test_list_properties_only_returns_own_agency(client, register_agency):
    agency_a = register_agency(agency_name="Agencia A", email="a@demo.com")
    agency_b = register_agency(agency_name="Agencia B", email="b@demo.com")

    _create_property(client, agency_a["headers"], title="Depto A")
    _create_property(client, agency_b["headers"], title="Depto B")

    res = client.get("/api/properties/", headers=agency_a["headers"])
    titles = [p["title"] for p in res.get_json()]
    assert titles == ["Depto A"]


def test_photos_lifecycle(client, register_agency):
    agency = register_agency()
    prop = _create_property(client, agency["headers"]).get_json()

    add_res = client.post(
        f"/api/properties/{prop['id']}/photos",
        headers=agency["headers"],
        json={"url": "https://example.com/photo.jpg", "isCover": True},
    )
    assert add_res.status_code == 201
    photos = add_res.get_json()["photos"]
    assert len(photos) == 1
    assert photos[0]["isCover"] is True

    remove_res = client.delete(
        f"/api/properties/{prop['id']}/photos/{photos[0]['id']}",
        headers=agency["headers"],
    )
    assert remove_res.get_json()["photos"] == []


def test_owner_crud_and_assignment(client, register_agency):
    agency = register_agency()
    owner_res = client.post(
        "/api/properties/owners",
        headers=agency["headers"],
        json={"name": "Juan Propietario", "email": "juan@demo.com"},
    )
    assert owner_res.status_code == 201
    owner_id = owner_res.get_json()["id"]

    prop = _create_property(client, agency["headers"]).get_json()
    update_res = client.patch(
        f"/api/properties/{prop['id']}", headers=agency["headers"], json={"ownerId": owner_id}
    )
    assert update_res.get_json()["owner"]["name"] == "Juan Propietario"


def test_public_endpoint_only_returns_published_properties(client, register_agency):
    agency = register_agency(agency_name="Agencia Publica", email="public@demo.com")
    prop = _create_property(client, agency["headers"], title="Depto Publico").get_json()

    # Agency slug is derived from the agency name at registration time.
    public_list_before = client.get("/api/public/agencia-publica/properties")
    assert public_list_before.get_json() == []

    client.post(f"/api/properties/{prop['id']}/publish", headers=agency["headers"])

    public_list_after = client.get("/api/public/agencia-publica/properties")
    assert len(public_list_after.get_json()) == 1

    public_detail = client.get("/api/public/agencia-publica/properties/depto-publico")
    assert public_detail.status_code == 200
    assert public_detail.get_json()["title"] == "Depto Publico"
