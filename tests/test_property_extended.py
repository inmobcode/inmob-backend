import io
from unittest.mock import patch


def _create_property(client, headers, listing_type="RENT", category="VILLA", title="Villa Kennedys"):
    res = client.post(
        "/api/properties/",
        headers=headers,
        json={"title": title, "listingType": listing_type, "category": category},
    )
    return res.get_json()


def test_patch_upserts_classification_and_description(client, register_agency):
    agency = register_agency()
    prop = _create_property(client, agency["headers"])

    res = client.patch(
        f"/api/properties/{prop['id']}",
        headers=agency["headers"],
        json={
            "classification": {"parkingSpaces": 2, "masterBedroomQty": 1},
            "content": {"description": "<p>Header</p>", "ourNote": "Special villa"},
        },
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body["classification"]["parkingSpaces"] == 2
    assert body["content"]["ourNote"] == "Special villa"

    # Second PATCH updates in place instead of creating a second row.
    res2 = client.patch(
        f"/api/properties/{prop['id']}",
        headers=agency["headers"],
        json={"classification": {"parkingSpaces": 3}},
    )
    assert res2.get_json()["classification"]["parkingSpaces"] == 3
    assert res2.get_json()["classification"]["masterBedroomQty"] == 1


def test_pools_crud_scoped_by_agency(client, register_agency):
    agency_a = register_agency(agency_name="Agencia A", email="a@demo.com")
    agency_b = register_agency(agency_name="Agencia B", email="b@demo.com")
    prop = _create_property(client, agency_a["headers"], listing_type="SALE", category="VILLA")

    create_res = client.post(
        f"/api/properties/{prop['id']}/pools",
        headers=agency_a["headers"],
        json={"type": "POOL", "quantity": 1, "poolType": ["Private", "Infinity"]},
    )
    assert create_res.status_code == 201
    pool = create_res.get_json()

    cross_res = client.get(f"/api/properties/{prop['id']}/pools", headers=agency_b["headers"])
    assert cross_res.status_code == 404

    update_res = client.patch(
        f"/api/properties/{prop['id']}/pools/{pool['id']}",
        headers=agency_a["headers"],
        json={"quantity": 2},
    )
    assert update_res.get_json()["quantity"] == 2

    delete_res = client.delete(
        f"/api/properties/{prop['id']}/pools/{pool['id']}", headers=agency_a["headers"]
    )
    assert delete_res.status_code == 204


def test_rate_periods_crud_and_validation(client, register_agency):
    agency = register_agency()
    prop = _create_property(client, agency["headers"])

    bad_res = client.post(
        f"/api/properties/{prop['id']}/rates",
        headers=agency["headers"],
        json={"startDate": "2026-08-10", "endDate": "2026-08-01"},
    )
    assert bad_res.status_code == 400

    create_res = client.post(
        f"/api/properties/{prop['id']}/rates",
        headers=agency["headers"],
        json={
            "label": "High Season",
            "startDate": "2026-07-01",
            "endDate": "2026-08-31",
            "officialPricePerNight": 1000,
            "minStay": 7,
        },
    )
    assert create_res.status_code == 201
    period = create_res.get_json()
    assert period["managementFeePct"] == 10
    assert period["agencyCommissionPct"] == 20

    list_res = client.get(f"/api/properties/{prop['id']}/rates", headers=agency["headers"])
    assert len(list_res.get_json()) == 1

    client.delete(f"/api/properties/{prop['id']}/rates/{period['id']}", headers=agency["headers"])
    assert client.get(f"/api/properties/{prop['id']}/rates", headers=agency["headers"]).get_json() == []


def test_improvement_recommendations_lifecycle(client, register_agency):
    agency = register_agency()
    prop = _create_property(client, agency["headers"])

    create_res = client.post(
        f"/api/properties/{prop['id']}/recommendations",
        headers=agency["headers"],
        json={"title": "Repaint facade", "priority": "HIGH", "estCost": 2000},
    )
    assert create_res.status_code == 201
    rec = create_res.get_json()
    assert rec["status"] == "PROPOSED"

    update_res = client.patch(
        f"/api/properties/{prop['id']}/recommendations/{rec['id']}",
        headers=agency["headers"],
        json={"status": "APPROVED"},
    )
    assert update_res.get_json()["status"] == "APPROVED"


def test_create_hotel_room_requires_hotel_parent(client, register_agency):
    agency = register_agency()
    villa = _create_property(client, agency["headers"], category="VILLA")

    res = client.post(f"/api/properties/{villa['id']}/rooms", headers=agency["headers"])
    assert res.status_code == 400

    hotel = _create_property(client, agency["headers"], category="HOTEL", title="Grand Hotel")
    room_res = client.post(f"/api/properties/{hotel['id']}/rooms", headers=agency["headers"])
    assert room_res.status_code == 201
    room = room_res.get_json()
    assert room["parentPropertyId"] == hotel["id"]
    assert room["category"] == "HOTEL_ROOM"


def test_photo_upload_goes_through_storage_service(client, register_agency):
    agency = register_agency()
    prop = _create_property(client, agency["headers"])

    with patch(
        "app.blueprints.properties.routes.storage_service.upload_photo",
        return_value="https://fake-bucket.supabase.co/property-photos/agency/prop/abc.webp",
    ) as mock_upload:
        res = client.post(
            f"/api/properties/{prop['id']}/photos",
            headers=agency["headers"],
            data={
                "file": (io.BytesIO(b"fake-webp-bytes"), "photo.webp"),
                "isCover": "true",
                "section": "POOL",
            },
            content_type="multipart/form-data",
        )
    assert res.status_code == 201
    mock_upload.assert_called_once()
    photos = res.get_json()["photos"]
    assert photos[0]["url"].startswith("https://fake-bucket.supabase.co")
    assert photos[0]["isCover"] is True
    assert photos[0]["section"] == "POOL"


def test_photo_upload_storage_failure_is_surfaced(client, register_agency):
    agency = register_agency()
    prop = _create_property(client, agency["headers"])

    from app.services.storage_service import StorageError

    with patch(
        "app.blueprints.properties.routes.storage_service.upload_photo",
        side_effect=StorageError("bucket unreachable", 502),
    ):
        res = client.post(
            f"/api/properties/{prop['id']}/photos",
            headers=agency["headers"],
            data={"file": (io.BytesIO(b"fake-webp-bytes"), "photo.webp")},
            content_type="multipart/form-data",
        )
    assert res.status_code == 502
