from unittest.mock import patch

from app.services.availability_service import parse_ical_blocks

SAMPLE_ICAL = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:event-1@airbnb.com
DTSTART;VALUE=DATE:20260301
DTEND;VALUE=DATE:20260305
SUMMARY:Reserved
END:VEVENT
BEGIN:VEVENT
UID:event-2@airbnb.com
DTSTART;VALUE=DATE:20260401
DTEND;VALUE=DATE:20260403
SUMMARY:Reserved
END:VEVENT
END:VCALENDAR
"""

SAMPLE_ICAL_UPDATED = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:event-1@airbnb.com
DTSTART;VALUE=DATE:20260302
DTEND;VALUE=DATE:20260306
SUMMARY:Reserved
END:VEVENT
END:VCALENDAR
"""


def _create_property(client, headers, title="Casa Disponibilidad"):
    res = client.post(
        "/api/properties/",
        headers=headers,
        json={"title": title, "listingType": "RENT", "category": "HOUSE"},
    )
    return res.get_json()


def test_parse_ical_blocks_extracts_date_ranges():
    blocks = parse_ical_blocks(SAMPLE_ICAL)
    assert len(blocks) == 2
    assert blocks[0]["uid"] == "event-1@airbnb.com"
    assert blocks[0]["start_date"].isoformat() == "2026-03-01"
    assert blocks[0]["end_date"].isoformat() == "2026-03-05"


def test_create_list_and_delete_manual_block(client, register_agency):
    agency = register_agency()
    prop = _create_property(client, agency["headers"])

    create_res = client.post(
        f"/api/properties/{prop['id']}/availability/",
        headers=agency["headers"],
        json={"startDate": "2026-05-01", "endDate": "2026-05-10", "note": "Reserva familiar"},
    )
    assert create_res.status_code == 201
    block = create_res.get_json()
    assert block["source"] == "MANUAL"

    list_res = client.get(f"/api/properties/{prop['id']}/availability/", headers=agency["headers"])
    assert len(list_res.get_json()) == 1

    delete_res = client.delete(
        f"/api/properties/{prop['id']}/availability/{block['id']}", headers=agency["headers"]
    )
    assert delete_res.status_code == 204


def test_invalid_date_range_is_rejected(client, register_agency):
    agency = register_agency()
    prop = _create_property(client, agency["headers"])

    res = client.post(
        f"/api/properties/{prop['id']}/availability/",
        headers=agency["headers"],
        json={"startDate": "2026-05-10", "endDate": "2026-05-01"},
    )
    assert res.status_code == 400


def test_sync_ical_creates_updates_and_removes_stale_blocks(client, register_agency):
    agency = register_agency()
    prop = _create_property(client, agency["headers"])

    class FakeResponse:
        def raise_for_status(self):
            pass

        class raw:
            @staticmethod
            def read(_size, decode_content=True):
                return SAMPLE_ICAL.encode("utf-8")

    with patch("app.services.availability_service.requests.get", return_value=FakeResponse()):
        sync_res = client.post(
            f"/api/properties/{prop['id']}/availability/sync",
            headers=agency["headers"],
            json={"icalUrl": "https://example.com/calendar.ics"},
        )
    assert sync_res.status_code == 200
    assert sync_res.get_json()["importedCount"] == 2

    blocks = client.get(
        f"/api/properties/{prop['id']}/availability/", headers=agency["headers"]
    ).get_json()
    assert len(blocks) == 2
    assert all(b["source"] == "ICAL" for b in blocks)

    # Re-sync with an updated feed: event-1 shifted, event-2 removed.
    class FakeResponseUpdated(FakeResponse):
        class raw:
            @staticmethod
            def read(_size, decode_content=True):
                return SAMPLE_ICAL_UPDATED.encode("utf-8")

    with patch(
        "app.services.availability_service.requests.get", return_value=FakeResponseUpdated()
    ):
        client.post(
            f"/api/properties/{prop['id']}/availability/sync",
            headers=agency["headers"],
            json={"icalUrl": "https://example.com/calendar.ics"},
        )

    blocks_after = client.get(
        f"/api/properties/{prop['id']}/availability/", headers=agency["headers"]
    ).get_json()
    assert len(blocks_after) == 1
    assert blocks_after[0]["startDate"] == "2026-03-02"


def test_cannot_delete_synced_block_manually(client, register_agency):
    agency = register_agency()
    prop = _create_property(client, agency["headers"])

    class FakeResponse:
        def raise_for_status(self):
            pass

        class raw:
            @staticmethod
            def read(_size, decode_content=True):
                return SAMPLE_ICAL.encode("utf-8")

    with patch("app.services.availability_service.requests.get", return_value=FakeResponse()):
        client.post(
            f"/api/properties/{prop['id']}/availability/sync",
            headers=agency["headers"],
            json={"icalUrl": "https://example.com/calendar.ics"},
        )

    blocks = client.get(
        f"/api/properties/{prop['id']}/availability/", headers=agency["headers"]
    ).get_json()
    res = client.delete(
        f"/api/properties/{prop['id']}/availability/{blocks[0]['id']}", headers=agency["headers"]
    )
    assert res.status_code == 400


def test_public_ics_export_only_for_published_property(client, register_agency):
    agency = register_agency(agency_name="Agencia Ical", email="owner@ical.com")
    prop = _create_property(client, agency["headers"], title="Depto Ical")

    client.post(
        f"/api/properties/{prop['id']}/availability/",
        headers=agency["headers"],
        json={"startDate": "2026-06-01", "endDate": "2026-06-05"},
    )

    not_published = client.get("/api/public/agencia-ical/properties/depto-ical/availability.ics")
    assert not_published.status_code == 404

    client.post(f"/api/properties/{prop['id']}/publish", headers=agency["headers"])
    published = client.get("/api/public/agencia-ical/properties/depto-ical/availability.ics")
    assert published.status_code == 200
    assert b"BEGIN:VEVENT" in published.data
    assert published.content_type.startswith("text/calendar")


def test_availability_isolated_per_agency(client, register_agency):
    agency_a = register_agency(agency_name="Agencia A", email="a@demo.com")
    agency_b = register_agency(agency_name="Agencia B", email="b@demo.com")
    prop = _create_property(client, agency_a["headers"])

    res = client.get(f"/api/properties/{prop['id']}/availability/", headers=agency_b["headers"])
    assert res.status_code == 404


# --- the calendar for any window (the dashboard's month view) -------------------


def _rental(client, headers, title="Casa"):
    prop = client.post(
        "/api/properties/", headers=headers, json={"title": title, "listingType": "RENT", "category": "HOUSE"}
    ).get_json()
    return prop


def test_calendar_accepts_a_window(client, register_agency):
    agency = register_agency(agency_name="Agencia Cal", email="cal@demo.com")
    prop = _rental(client, agency["headers"])
    client.post(
        f"/api/properties/{prop['id']}/availability/",
        headers=agency["headers"],
        json={"startDate": "2031-03-10", "endDate": "2031-03-12"},
    )

    default = client.get("/api/properties/calendar", headers=agency["headers"]).get_json()
    assert default["properties"][0]["blockedDates"] == []

    march = client.get("/api/properties/calendar?from=2031-03-01&days=42", headers=agency["headers"]).get_json()
    assert march["from"] == "2031-03-01" and march["to"] == "2031-04-11"
    assert march["properties"][0]["blockedDates"] == ["2031-03-10", "2031-03-11", "2031-03-12"]


def test_calendar_rejects_bad_windows(client, register_agency):
    agency = register_agency(agency_name="Agencia Bad", email="bad@demo.com")
    for query in ("from=nope", "days=0", "days=500"):
        assert client.get(f"/api/properties/calendar?{query}", headers=agency["headers"]).status_code == 400
