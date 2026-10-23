import io
import json

import pytest
from openpyxl import Workbook

from app.models.property import Property
from app.services.importers import normalize as n
from app.services.importers.fetch import fetch_feed
from app.services.importers.records import ImportParseError

CSV = (
    "Ref;Tipo;Operación;Precio;Dormitorios;Baños;Ciudad;Fotos;Descripción\n"
    "A1;Villa;Venta;€ 1.250.000;4;3;Marbella;https://x.test/1.jpg|https://x.test/2.jpg;Vistas al mar\n"
    "A2;Piso;Alquiler;1.800;2;1;Madrid;;\n"
)

KYERO = """<?xml version="1.0" encoding="UTF-8"?>
<root>
  <kyero><feed_version>3</feed_version></kyero>
  <property>
    <id>77</id><ref>K-77</ref><price>425000</price><currency>EUR</currency><price_freq>sale</price_freq>
    <type>villa</type><town>Estepona</town><province>Málaga</province><country>Spain</country>
    <location><latitude>36.42</latitude><longitude>-5.14</longitude></location>
    <beds>3</beds><baths>2</baths><pool>1</pool>
    <surface_area><built>180</built><plot>800</plot></surface_area>
    <energy_rating><consumption>C</consumption></energy_rating>
    <url><en>https://agency.test/k-77</en></url>
    <desc><en>Sea view villa</en><es>Villa con vistas</es></desc>
    <features><feature>Barbecue</feature><feature>Smart home</feature></features>
    <images><image id="1"><url>https://img.test/a.jpg</url></image><image id="2"><url>https://img.test/b.jpg</url></image></images>
  </property>
</root>"""

TIVVU = """<tivvu version="1">
  <listing>
    <external_id>T-1</external_id>
    <title><en>Loft in Athens</en><el>Loft</el></title>
    <listing_type>RENT</listing_type><category>APARTMENT</category>
    <price>900</price><currency>EUR</currency><area>Athens</area>
    <owner><name>Maria P</name><email>maria@example.com</email></owner>
    <features><feature>Gym</feature></features>
    <photos><photo>https://img.test/t.jpg</photo></photos>
  </listing>
</tivvu>"""


def _post(client, headers, path, *, fmt, content=None, filename="feed.csv", **form):
    data = {"format": fmt, **{k: v for k, v in form.items()}}
    if content is not None:
        data["file"] = (io.BytesIO(content if isinstance(content, bytes) else content.encode()), filename)
    return client.post(f"/api/imports/{path}", headers=headers, data=data, content_type="multipart/form-data")


def _props(app):
    return Property.query.order_by(Property.title).all()


# ------------------------------------------------------------ normalizers


@pytest.mark.parametrize(
    "raw,expected",
    [("€ 1.250.000", 1250000), ("1,250,000.50", 1250000.5), ("89,5", 89.5), ("1.250", 1250), ("250000", 250000), ("n/a", None)],
)
def test_parse_number(raw, expected):
    assert n.parse_number(raw) == expected


def test_coordinates_keep_decimals():
    assert n.parse_number("36.425", coordinate=True) == 36.425
    assert n.parse_number("-5,140", coordinate=True) == -5.14


def test_listing_type_and_category_synonyms():
    assert n.parse_listing_type("Venta") == "SALE"
    assert n.parse_listing_type("Alquiler") == "RENT"
    assert n.parse_listing_type("monthly") == "RENT"
    assert n.parse_category("Villa adosada") == "VILLA"
    assert n.parse_category("Ático") == "PENTHOUSE"
    assert n.parse_category("semi-detached villa") == "SEMI_DETACHED_VILLA"
    assert n.parse_category("something odd") is None


# ------------------------------------------------------------ CSV / Excel


def test_csv_preview_suggests_mapping_and_writes_nothing(app, client, register_agency):
    agency = register_agency()
    res = _post(client, agency["headers"], "preview", fmt="table", content=CSV)
    assert res.status_code == 200
    body = res.get_json()
    mapping = body["table"]["mapping"]
    assert mapping["Ref"] == "external_id"
    assert mapping["Precio"] == "price"
    assert mapping["Ciudad"] == "area"
    assert body["counts"]["create"] == 2
    assert _props(app) == []


def test_csv_apply_creates_drafts_and_normalizes(app, client, register_agency):
    agency = register_agency()
    res = _post(client, agency["headers"], "apply", fmt="table", content=CSV)
    assert res.status_code == 200
    assert res.get_json()["done"]["create"] == 2

    villa = Property.query.filter_by(external_id="A1").one()
    assert villa.status == "DRAFT"
    assert villa.source == "csv"
    assert villa.price == 1250000
    assert villa.category == "VILLA" and villa.listing_type == "SALE"
    assert villa.title == "Villa en Marbella"
    assert [p.url for p in villa.photos] == ["https://x.test/1.jpg", "https://x.test/2.jpg"]
    assert villa.photos[0].is_cover
    assert "Vistas al mar" in villa.content.description
    flat = Property.query.filter_by(external_id="A2").one()
    assert flat.listing_type == "RENT" and flat.category == "APARTMENT" and flat.price == 1800


def test_reimport_is_idempotent_and_blank_cells_do_not_erase(app, client, register_agency):
    agency = register_agency()
    _post(client, agency["headers"], "apply", fmt="table", content=CSV)

    second = _post(client, agency["headers"], "apply", fmt="table", content=CSV)
    assert second.get_json()["done"] == {"create": 0, "update": 0, "failed": 0, "trash": 0}
    assert Property.query.count() == 2

    changed = CSV.replace("1.800", "2.000").replace("Vistas al mar", "")
    preview = _post(client, agency["headers"], "preview", fmt="table", content=changed).get_json()
    assert preview["counts"]["update"] == 1
    assert preview["counts"]["unchanged"] == 1
    _post(client, agency["headers"], "apply", fmt="table", content=changed)
    assert Property.query.filter_by(external_id="A2").one().price == 2000
    assert "Vistas al mar" in Property.query.filter_by(external_id="A1").one().content.description


def test_explicit_mapping_overrides_suggestion(app, client, register_agency):
    agency = register_agency()
    csv = "codigo,nombre,valor\nX1,Casa azul,100000\n"
    mapping = {"codigo": "external_id", "nombre": "title", "valor": "price"}
    res = _post(client, agency["headers"], "apply", fmt="table", content=csv, mapping=json.dumps(mapping), source="ilistcrm")
    assert res.get_json()["done"]["create"] == 1
    prop = Property.query.one()
    assert (prop.title, prop.price, prop.source) == ("Casa azul", 100000, "ilistcrm")


def test_rows_without_title_or_with_repeated_ref_are_rejected(app, client, register_agency):
    agency = register_agency()
    csv = "ref,title\nA,Casa uno\nA,Casa dos\n,\nB,\n"
    preview = _post(client, agency["headers"], "preview", fmt="table", content=csv).get_json()
    actions = [row["action"] for row in preview["rows"]]
    assert actions == ["create", "error", "error"]
    assert preview["counts"]["error"] == 2


def test_xlsx_import(app, client, register_agency):
    agency = register_agency()
    wb = Workbook()
    ws = wb.active
    ws.append(["Reference", "Property Type", "Price", "Bedrooms", "Town"])
    ws.append(["R1", "Apartment", 310000, 2, "Lisbon"])
    buf = io.BytesIO()
    wb.save(buf)
    res = _post(client, agency["headers"], "apply", fmt="table", content=buf.getvalue(), filename="export.xlsx")
    assert res.get_json()["done"]["create"] == 1
    prop = Property.query.one()
    assert (prop.category, prop.price, prop.bedrooms, prop.area) == ("APARTMENT", 310000, 2, "Lisbon")


# ------------------------------------------------------------ XML feeds


def test_kyero_feed(app, client, register_agency):
    agency = register_agency()
    res = _post(client, agency["headers"], "apply", fmt="kyero", content=KYERO, filename="feed.xml", source="casafari")
    assert res.get_json()["done"]["create"] == 1
    prop = Property.query.one()
    assert (prop.source, prop.external_id) == ("casafari", "K-77")
    assert prop.title == "Villa en Estepona"
    assert prop.listing_type == "SALE" and prop.currency == "EUR"
    assert (prop.lat, prop.lng) == (36.42, -5.14)
    assert (prop.area_sqm, prop.plot_area, prop.energy_certificate) == (180, 800, "C")
    assert prop.website_url == "https://agency.test/k-77"
    assert "Sea view villa" in prop.content.description
    assert "Pool" in prop.outdoor_amenities and "BBQ" in prop.outdoor_amenities
    assert "Smart home" in prop.custom_facilities
    assert len(prop.photos) == 2


def test_archive_missing_moves_to_trash_but_never_on_empty_feed(app, client, register_agency):
    agency = register_agency()
    _post(client, agency["headers"], "apply", fmt="table", content=CSV, source="crm")
    only_a1 = "Ref;Tipo;Precio\nA1;Villa;1250000\n"

    preview = _post(client, agency["headers"], "preview", fmt="table", content=only_a1, source="crm", archiveMissing="true").get_json()
    assert preview["counts"]["trash"] == 1
    assert preview["missing"][0]["externalId"] == "A2"

    broken = _post(client, agency["headers"], "preview", fmt="table", content="Ref;Tipo\n;\n;\n", source="crm", archiveMissing="true")
    assert broken.status_code == 400

    _post(client, agency["headers"], "apply", fmt="table", content=only_a1, source="crm", archiveMissing="true")
    assert Property.query.filter_by(external_id="A2").one().deleted_at is not None
    assert Property.query.filter_by(external_id="A1").one().deleted_at is None

    # Back in the feed after being trashed: skipped, never duplicated.
    again = _post(client, agency["headers"], "preview", fmt="table", content=CSV, source="crm").get_json()
    assert again["counts"]["skip"] == 1
    assert Property.query.count() == 2


def test_tivvu_xml_feed_with_owner(app, client, register_agency):
    agency = register_agency()
    res = _post(client, agency["headers"], "apply", fmt="tivvu_xml", content=TIVVU, filename="tivvu.xml", publish="true")
    assert res.get_json()["done"]["create"] == 1
    prop = Property.query.one()
    assert (prop.source, prop.external_id, prop.title, prop.status) == ("tivvu", "T-1", "Loft in Athens", "PUBLISHED")
    assert prop.listing_type == "RENT"
    assert prop.owner.email == "maria@example.com"
    assert "Gym" in prop.indoor_amenities


def test_xml_with_entities_is_refused(app, client, register_agency):
    agency = register_agency()
    evil = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "boom">]><root><property><ref>1</ref><desc>&a;</desc></property></root>'
    res = _post(client, agency["headers"], "preview", fmt="kyero", content=evil, filename="feed.xml")
    assert res.status_code == 400


# ------------------------------------------------------------ access & safety


def test_imports_are_scoped_to_the_agency(app, client, register_agency):
    one = register_agency("Uno", "uno@demo.com")
    two = register_agency("Dos", "dos@demo.com")
    _post(client, one["headers"], "apply", fmt="table", content=CSV)
    res = _post(client, two["headers"], "apply", fmt="table", content=CSV)
    assert res.get_json()["done"]["create"] == 2
    assert Property.query.count() == 4


def test_requires_auth(client):
    assert client.post("/api/imports/preview", data={"format": "table"}).status_code == 401


@pytest.mark.parametrize("url", ["http://127.0.0.1/feed.xml", "http://169.254.169.254/latest/meta-data", "ftp://example.com/x", "http://localhost:8000/api/health"])
def test_url_fetch_blocks_internal_addresses(app, url):
    with pytest.raises(ImportParseError):
        fetch_feed(url)


def test_internal_addresses_are_allowed_only_when_the_dev_switch_is_on(app, monkeypatch):
    class Reply:
        status_code = 200
        is_redirect = False
        headers = {}

        def iter_content(self, size):
            yield b"<root/>"

        def close(self):
            pass

    monkeypatch.setattr("app.services.importers.fetch.requests.get", lambda *a, **k: Reply())
    with pytest.raises(ImportParseError):
        fetch_feed("http://127.0.0.1:3000/feed.xml")

    app.config["IMPORT_ALLOW_PRIVATE_URLS"] = True
    content, _ = fetch_feed("http://127.0.0.1:3000/feed.xml")
    assert content == b"<root/>"
    # The switch relaxes the address check, not the scheme check.
    with pytest.raises(ImportParseError):
        fetch_feed("ftp://127.0.0.1/feed.xml")


def test_csv_can_be_read_from_a_url(app, client, register_agency, monkeypatch):
    agency = register_agency()
    monkeypatch.setattr("app.services.import_service.fetch_feed", lambda url: (CSV.encode(), "export.csv"))
    res = client.post(
        "/api/imports/apply",
        headers=agency["headers"],
        data={"format": "table", "url": "https://crm.example.com/export.csv"},
    )
    assert res.status_code == 200
    assert res.get_json()["done"]["create"] == 2
    assert Property.query.filter_by(external_id="A1").one().source == "csv"


def test_malformed_xml_and_wrong_shape_give_a_clear_error(app, client, register_agency):
    agency = register_agency()
    broken = _post(client, agency["headers"], "preview", fmt="kyero", content="<root><property>", filename="feed.xml")
    assert broken.status_code == 400 and "XML" in broken.get_json()["message"]
    empty = _post(client, agency["headers"], "preview", fmt="kyero", content="<root/>", filename="feed.xml")
    assert empty.status_code == 400


def test_xml_format_is_detected_from_the_content_not_the_choice(app, client, register_agency):
    agency = register_agency()
    # A Kyero feed sent as "Tivvu XML", and a Tivvu feed sent as "Kyero": both must read fine.
    kyero_as_tivvu = _post(client, agency["headers"], "preview", fmt="tivvu_xml", content=KYERO, filename="feed.xml")
    assert kyero_as_tivvu.get_json()["counts"]["create"] == 1
    tivvu_as_kyero = _post(client, agency["headers"], "preview", fmt="kyero", content=TIVVU, filename="feed.xml")
    assert tivvu_as_kyero.get_json()["counts"]["create"] == 1
