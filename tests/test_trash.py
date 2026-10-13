from datetime import date, timedelta

from app.extensions import db
from app.models import Booking, Offer, Property
from app.utils import trash


def _days_ahead(days: int) -> str:
    """A date that stays in the future whenever the tests run."""
    return (date.today() + timedelta(days=days)).isoformat()


def _property(client, headers, title="Casa", listing_type="SALE"):
    return client.post(
        "/api/properties/", headers=headers, json={"title": title, "listingType": listing_type, "category": "HOUSE"}
    ).get_json()


def test_deleted_property_goes_to_trash_off_the_site_and_comes_back(client, register_agency):
    agency = register_agency()
    headers = agency["headers"]
    prop = _property(client, headers)
    client.post(f"/api/properties/{prop['id']}/publish", headers=headers)
    slug = client.get("/api/agency/", headers=headers).get_json()["slug"]

    assert client.delete(f"/api/properties/{prop['id']}", headers=headers).status_code == 204
    assert client.get("/api/properties/", headers=headers).get_json() == []
    assert client.get(f"/api/properties/{prop['id']}", headers=headers).status_code == 404
    assert client.get(f"/api/public/{slug}/properties/{prop['slug']}").status_code == 404
    trashed = client.get("/api/properties/trash", headers=headers).get_json()
    assert [item["id"] for item in trashed] == [prop["id"]]
    assert trashed[0]["deletedAt"]

    res = client.post(f"/api/properties/{prop['id']}/restore", headers=headers)
    assert res.status_code == 200 and res.get_json()["deletedAt"] is None
    assert len(client.get("/api/properties/", headers=headers).get_json()) == 1
    assert client.get(f"/api/public/{slug}/properties/{prop['slug']}").status_code == 200


def test_property_with_bookings_cant_be_deleted_for_good(client, register_agency):
    agency = register_agency()
    headers = agency["headers"]
    prop = _property(client, headers)
    client.post("/api/bookings/", headers=headers, json={"propertyId": prop["id"]})
    client.delete(f"/api/properties/{prop['id']}", headers=headers)

    assert client.delete(f"/api/properties/{prop['id']}/permanent", headers=headers).status_code == 409

    other = _property(client, headers, title="Otra")
    client.delete(f"/api/properties/{other['id']}", headers=headers)
    assert client.delete(f"/api/properties/{other['id']}/permanent", headers=headers).status_code == 204
    assert [item["id"] for item in client.get("/api/properties/trash", headers=headers).get_json()] == [prop["id"]]


def test_trashed_offer_hides_its_public_link_until_restored(client, register_agency):
    agency = register_agency()
    headers = agency["headers"]
    offer = client.post("/api/offers/", headers=headers, json={"title": "Oferta", "sections": []}).get_json()
    client.post(f"/api/offers/{offer['id']}/send", headers=headers)

    client.delete(f"/api/offers/{offer['id']}", headers=headers)
    assert client.get("/api/offers/", headers=headers).get_json() == []
    assert client.get(f"/api/public/offers/{offer['token']}").status_code == 404

    client.post(f"/api/offers/{offer['id']}/restore", headers=headers)
    assert client.get(f"/api/public/offers/{offer['token']}").status_code == 200


def test_trashed_booking_frees_its_dates_and_takes_them_back_on_restore(client, register_agency, app):
    agency = register_agency()
    headers = agency["headers"]
    prop = _property(client, headers, listing_type="RENT")
    booking = client.post(
        "/api/bookings/",
        headers=headers,
        json={"propertyId": prop["id"], "startDate": _days_ahead(60), "endDate": _days_ahead(64)},
    ).get_json()
    client.post(f"/api/bookings/{booking['id']}/confirm", headers=headers)
    blocks = lambda: client.get(f"/api/properties/{prop['id']}/availability/", headers=headers).get_json()
    assert len(blocks()) == 1

    client.delete(f"/api/bookings/{booking['id']}", headers=headers)
    assert blocks() == []
    assert client.get("/api/bookings/", headers=headers).get_json() == []

    client.post(f"/api/bookings/{booking['id']}/restore", headers=headers)
    assert len(blocks()) == 1


def test_trash_is_emptied_after_thirty_days(client, register_agency, app):
    agency = register_agency()
    headers = agency["headers"]
    prop = _property(client, headers)
    offer = client.post("/api/offers/", headers=headers, json={"title": "Oferta", "sections": []}).get_json()
    booking = client.post("/api/bookings/", headers=headers, json={"propertyId": _property(client, headers, "Bungalow")["id"]}).get_json()
    for url in (f"/api/properties/{prop['id']}", f"/api/offers/{offer['id']}", f"/api/bookings/{booking['id']}"):
        client.delete(url, headers=headers)

    with app.app_context():
        old = trash.now() - timedelta(days=31)
        for model, record_id in ((Property, prop["id"]), (Offer, offer["id"]), (Booking, booking["id"])):
            db.session.get(model, record_id).deleted_at = old
        db.session.commit()

    for kind in ("properties", "offers", "bookings"):
        assert client.get(f"/api/{kind}/trash", headers=headers).get_json() == []
