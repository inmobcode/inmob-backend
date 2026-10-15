def _create(client, headers, title):
    return client.post(
        "/api/properties/",
        headers=headers,
        json={"title": title, "listingType": "SALE", "category": "HOUSE"},
    ).get_json()


def test_sitemap_lists_agencies_and_only_published_listings(client, register_agency):
    agency = register_agency(agency_name="Agencia Sitemap", email="sitemap@demo.com")
    published = _create(client, agency["headers"], "Casa Publicada")
    client.post(f"/api/properties/{published['id']}/publish", headers=agency["headers"])
    _create(client, agency["headers"], "Casa Borrador")

    body = client.get("/api/public/sitemap").get_json()

    listed = next(item for item in body["agencies"] if item["slug"] == "agencia-sitemap")
    assert listed["name"] == "Agencia Sitemap"
    listings = [item for item in body["properties"] if item["agencySlug"] == "agencia-sitemap"]
    assert [item["slug"] for item in listings] == [published["slug"]]
    assert listings[0]["updatedAt"]


def test_sitemap_leaves_out_trashed_listings(client, register_agency):
    agency = register_agency(agency_name="Agencia Papelera", email="papelera@demo.com")
    prop = _create(client, agency["headers"], "Casa Al Tacho")
    client.post(f"/api/properties/{prop['id']}/publish", headers=agency["headers"])
    client.delete(f"/api/properties/{prop['id']}", headers=agency["headers"])

    body = client.get("/api/public/sitemap").get_json()

    assert [item for item in body["properties"] if item["agencySlug"] == "agencia-papelera"] == []
