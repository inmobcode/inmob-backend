def _create_and_publish(client, headers, title, price, country="Argentina"):
    prop = client.post(
        "/api/properties/",
        headers=headers,
        json={"title": title, "listingType": "SALE", "category": "HOUSE"},
    ).get_json()
    client.patch(
        f"/api/properties/{prop['id']}",
        headers=headers,
        json={"price": price, "country": country},
    )
    client.post(f"/api/properties/{prop['id']}/publish", headers=headers)
    return prop


def test_public_listing_filters_by_price_range_and_country(client, register_agency):
    agency = register_agency(agency_name="Agencia Filtros", email="filtros@demo.com")
    _create_and_publish(client, agency["headers"], "Casa Barata", 100000, country="Argentina")
    _create_and_publish(client, agency["headers"], "Casa Cara", 900000, country="Uruguay")

    res = client.get("/api/public/agencia-filtros/properties?minPrice=500000")
    assert [p["title"] for p in res.get_json()] == ["Casa Cara"]

    res = client.get("/api/public/agencia-filtros/properties?maxPrice=500000")
    assert [p["title"] for p in res.get_json()] == ["Casa Barata"]

    res = client.get("/api/public/agencia-filtros/properties?country=Uruguay")
    assert [p["title"] for p in res.get_json()] == ["Casa Cara"]


def test_public_listing_search_by_title(client, register_agency):
    agency = register_agency(agency_name="Agencia Buscar", email="buscar@demo.com")
    _create_and_publish(client, agency["headers"], "Chalet en la Montaña", 200000)
    _create_and_publish(client, agency["headers"], "Depto Céntrico", 150000)

    res = client.get("/api/public/agencia-buscar/properties?q=chalet")
    assert [p["title"] for p in res.get_json()] == ["Chalet en la Montaña"]
