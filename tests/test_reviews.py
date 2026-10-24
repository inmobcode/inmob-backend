from tests.test_workflow import _invite_agent


def _completed_booking(client, headers, slug_title="Villa"):
    prop = client.post(
        "/api/properties/", headers=headers, json={"title": slug_title, "listingType": "RENT", "category": "HOUSE"}
    ).get_json()
    client.post(f"/api/properties/{prop['id']}/publish", headers=headers)
    lead = client.post("/api/clients/", headers=headers, json={"name": "Lucía Fernández", "email": "lucia@demo.com"}).get_json()
    booking = client.post("/api/bookings/", headers=headers, json={"propertyId": prop["id"], "clientId": lead["id"]}).get_json()
    return prop, booking


def test_guest_reviews_wait_for_the_agency_and_then_show_on_the_site(client, register_agency):
    owner = register_agency(agency_name="Agencia Resenas", email="owner@resenas.com")
    headers = owner["headers"]
    prop, booking = _completed_booking(client, headers)
    review_url = f"/api/public/bookings/{booking['token']}/review"

    # Not before the stay is over.
    assert client.post(review_url, json={"rating": 5}).status_code == 400
    client.post(f"/api/bookings/{booking['id']}/confirm", headers=headers)
    client.post(f"/api/bookings/{booking['id']}/complete", headers=headers)
    page = client.get(f"/api/public/bookings/{booking['token']}").get_json()
    assert page["canReview"] is True and page["review"] is None

    assert client.post(review_url, json={"rating": 6}).status_code == 400
    res = client.post(review_url, json={"rating": 5, "text": "Hermosa casa"})
    assert res.status_code == 201
    assert res.get_json()["review"] == {"rating": 5, "text": "Hermosa casa", "status": "PENDING"}
    assert res.get_json()["canReview"] is False
    assert client.post(review_url, json={"rating": 4}).status_code == 409

    bell = client.get("/api/notifications/", headers=headers).get_json()
    assert bell["items"][0]["type"] == "REVIEW" and bell["items"][0]["params"]["rating"] == 5

    # Pending: not on the site yet.
    public = client.get(f"/api/public/agencia-resenas/properties/{prop['slug']}").get_json()
    assert public["reviews"] == [] and public["rating"] == {"average": None, "count": 0}

    pending = client.get("/api/reviews/?status=PENDING", headers=headers).get_json()
    assert len(pending) == 1 and pending[0]["authorName"] == "Lucía F." and pending[0]["source"] == "GUEST"
    review_id = pending[0]["id"]
    # The guest's words are theirs.
    assert client.patch(f"/api/reviews/{review_id}", headers=headers, json={"text": "Otra cosa"}).status_code == 400
    assert client.patch(f"/api/reviews/{review_id}", headers=headers, json={"status": "PUBLISHED"}).status_code == 200

    public = client.get(f"/api/public/agencia-resenas/properties/{prop['slug']}").get_json()
    assert public["rating"] == {"average": 5.0, "count": 1}
    assert public["reviews"][0]["authorName"] == "Lucía F." and public["reviews"][0]["text"] == "Hermosa casa"
    listed = client.get("/api/public/agencia-resenas/properties").get_json()
    assert listed[0]["rating"] == {"average": 5.0, "count": 1}


def test_manual_reviews_and_who_can_moderate(client, register_agency):
    owner = register_agency(agency_name="Agencia Manual", email="owner@manual.com")
    headers = owner["headers"]
    agent = _invite_agent(client, headers)
    prop = client.post(
        "/api/properties/", headers=headers, json={"title": "Casa", "listingType": "RENT", "category": "HOUSE"}
    ).get_json()

    assert client.get("/api/reviews/", headers=agent["headers"]).status_code == 403
    res = client.post(
        "/api/reviews/",
        headers=headers,
        json={"propertyId": prop["id"], "authorName": "Tomás", "rating": 4, "text": "Muy bien", "stayedOn": "2026-08-01"},
    )
    assert res.status_code == 201
    review = res.get_json()
    assert review["status"] == "PUBLISHED" and review["source"] == "MANUAL"
    assert client.patch(f"/api/reviews/{review['id']}", headers=headers, json={"rating": 3}).get_json()["rating"] == 3

    agency = client.get("/api/public/agencia-manual").get_json()
    assert agency["rating"] == {"average": 3.0, "count": 1} and agency["reviews"][0]["propertyTitle"] == "Casa"

    assert client.delete(f"/api/reviews/{review['id']}", headers=headers).status_code == 204
    assert client.get("/api/reviews/", headers=headers).get_json() == []
