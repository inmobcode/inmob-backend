"""Every field written with the formatting editor keeps its formatting and
loses anything else, and plain text from before the editor becomes paragraphs."""

DIRTY = '<h2>Título</h2><p><strong>Hola</strong></p><script>alert(1)</script><p onclick="x()">ok</p>'


def _assert_clean(html):
    assert "<h2>Título</h2>" in html
    assert "<strong>Hola</strong>" in html
    assert "script" not in html and "onclick" not in html


def test_property_description_is_sanitized(client, register_agency):
    agency = register_agency()
    prop = client.post(
        "/api/properties/", headers=agency["headers"], json={"title": "Casa", "listingType": "SALE", "category": "HOUSE"}
    ).get_json()
    res = client.patch(
        f"/api/properties/{prop['id']}",
        headers=agency["headers"],
        json={"content": {"description": DIRTY, "summary": "Una línea"}},
    )
    content = res.get_json()["content"]
    _assert_clean(content["description"])
    assert content["summary"] == "Una línea"


def test_site_about_and_text_blocks_are_sanitized_other_blocks_stay_plain(client, register_agency):
    agency = register_agency()
    res = client.patch(
        "/api/agency/site",
        headers=agency["headers"],
        json={
            "about": DIRTY,
            "sections": [
                {"id": "a", "type": "text", "text": DIRTY},
                {"id": "b", "type": "promo", "text": "15% en <verano>"},
            ],
        },
    )
    site = res.get_json()["site"]
    _assert_clean(site["about"])
    _assert_clean(site["sections"][0]["text"])
    assert site["sections"][1]["text"] == "15% en <verano>"


def test_offer_section_text_keeps_only_inline_formatting(client, register_agency):
    agency = register_agency()
    res = client.post(
        "/api/offers/",
        headers=agency["headers"],
        json={"title": "Oferta", "sections": [{"text": DIRTY, "properties": []}]},
    )
    text = res.get_json()["sections"][0]["text"]
    assert "<strong>Hola</strong>" in text
    assert "<h2>" not in text and "script" not in text


def test_client_notes_are_sanitized_and_plain_notes_become_paragraphs(client, register_agency):
    agency = register_agency()
    crm_client = client.post(
        "/api/clients/", headers=agency["headers"], json={"name": "Ana", "email": "ana@example.com", "notes": "Busca\ncasa"}
    ).get_json()
    assert crm_client["notes"] == "<p>Busca</p><p>casa</p>"

    res = client.patch(f"/api/clients/{crm_client['id']}", headers=agency["headers"], json={"notes": DIRTY})
    _assert_clean(res.get_json()["notes"])
