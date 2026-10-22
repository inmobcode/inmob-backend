"""XML feeds: Kyero v3 (what most CRMs in Spain, Portugal, Cyprus and Malta
export) and Tivvo's own XML (what an agency produces from its own system).

Both return raw per-field values for `records.normalize_record`, one dict per
listing. Parsing goes through defusedxml: feeds come from third parties.
"""
from xml.etree.ElementTree import Element

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from app.services.importers.fields import IMPORT_FIELDS
from app.services.importers.records import MAX_RECORDS, ImportParseError

LANGUAGE_PREFERENCE = ("en", "es", "pt", "el", "de", "fr")


def _parse(content: bytes) -> Element:
    try:
        return ElementTree.fromstring(content)
    except DefusedXmlException as err:
        raise ImportParseError("El XML usa entidades o DTD externas, que no se aceptan.") from err
    except ElementTree.ParseError as err:
        raise ImportParseError(f"El XML no es válido: {err}") from err


def _local(tag) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _child(element: Element, name: str) -> Element | None:
    for child in element:
        if _local(child.tag) == name:
            return child
    return None


def _children(element: Element | None, name: str) -> list[Element]:
    if element is None:
        return []
    return [child for child in element if _local(child.tag) == name]


def _text(element: Element | None) -> str | None:
    if element is None:
        return None
    text = "".join(element.itertext()).strip()
    return text or None


def _localized(element: Element | None) -> str | None:
    """Plain text, or the best language out of <en>…</en><es>…</es> children
    (also <x lang="en">). English first, then the others, then whatever exists."""
    if element is None:
        return None
    options: dict[str, str] = {}
    for child in element:
        text = _text(child)
        if text:
            options[_local(child.tag).lower()] = text
    if not options:
        return _text(element)
    for lang in LANGUAGE_PREFERENCE:
        if lang in options:
            return options[lang]
    return next(iter(options.values()))


def _listings(root: Element, names: tuple[str, ...]) -> list[Element]:
    found = [el for el in root.iter() if _local(el.tag) in names]
    if not found:
        raise ImportParseError(f"No se encontró ningún <{names[0]}> en el XML.")
    if len(found) > MAX_RECORDS:
        raise ImportParseError(f"El feed tiene más de {MAX_RECORDS} propiedades. Dividilo en partes.")
    return found


def _title_from(kind: str | None, town: str | None) -> str | None:
    if not (kind or town):
        return None
    kind_text = (kind or "Propiedad").replace("_", " ").strip().capitalize()
    return f"{kind_text} en {town}" if town else kind_text


def parse_kyero(content: bytes) -> list[dict]:
    root = _parse(content)
    raws: list[dict] = []
    for item in _listings(root, ("property",)):
        def value(*path: str, localized: bool = False):
            node: Element | None = item
            for step in path:
                node = _child(node, step) if node is not None else None
            return _localized(node) if localized else _text(node)

        kind = value("type")
        town = value("town")
        price_freq = (value("price_freq") or "sale").lower()
        features = [text for f in _children(_child(item, "features"), "feature") if (text := _text(f))]
        if value("pool") in ("1", "true", "yes"):
            features.append("Pool")
        photos = []
        for image in _children(_child(item, "images"), "image"):
            url = _text(_child(image, "url"))
            if url:
                photos.append(url)

        raws.append(
            {
                "external_id": value("ref") or value("id"),
                # Kyero v3 has no title field.
                "title": value("title", localized=True) or _title_from(kind, town),
                "listing_type": "SALE" if price_freq == "sale" else "RENT",
                "category": kind,
                "price": None if value("price_on_request") in ("1", "true") else value("price"),
                "currency": value("currency"),
                "country": value("country"),
                "region": value("province"),
                "area": town,
                "address": value("location_detail"),
                "lat": value("location", "latitude"),
                "lng": value("location", "longitude"),
                "bedrooms": value("beds"),
                "bathrooms": value("baths"),
                "area_sqm": value("surface_area", "built"),
                "plot_area": value("surface_area", "plot"),
                "energy_certificate": value("energy_rating", "consumption"),
                "description": value("desc", localized=True),
                "website_url": value("url", localized=True),
                "features": features,
                "photos": photos,
            }
        )
    return raws


def parse_tivvo_xml(content: bytes) -> list[dict]:
    """<tivvo><listing><external_id/><title/>…<features><feature/></features>
    <photos><photo/></photos><owner><name/><email/><phone/></owner></listing></tivvo>
    Field names are the import field keys (see fields.py)."""
    root = _parse(content)
    raws: list[dict] = []
    scalar_keys = [f.key for f in IMPORT_FIELDS if f.kind != "list" and not f.key.startswith("owner_")]
    for item in _listings(root, ("listing", "property")):
        raw: dict = {key: _localized(_child(item, key)) for key in scalar_keys}
        owner = _child(item, "owner")
        raw["owner_name"] = _text(_child(owner, "name")) if owner is not None else None
        raw["owner_email"] = _text(_child(owner, "email")) if owner is not None else None
        raw["owner_phone"] = _text(_child(owner, "phone")) if owner is not None else None
        raw["features"] = [t for f in _children(_child(item, "features"), "feature") if (t := _text(f))]
        raw["photos"] = [t for p in _children(_child(item, "photos"), "photo") if (t := _text(p))]
        raws.append(raw)
    return raws


def detect_format(content: bytes) -> str:
    """"kyero" or "tivvo_xml", from the feed itself: a Kyero feed has a <kyero>
    header or Kyero's own field names (ref, beds, town…) in its <property>
    nodes. People pick the wrong one of the two XML options, and the rows would
    all come out empty, so the content decides."""
    root = _parse(content)
    if any(_local(el.tag) == "kyero" for el in root.iter()):
        return "kyero"
    first = next((el for el in root.iter() if _local(el.tag) == "property"), None)
    if first is not None and {_local(c.tag) for c in first} & {"ref", "beds", "baths", "town", "price_freq", "surface_area"}:
        return "kyero"
    return "tivvo_xml"


def parse_auto(content: bytes) -> list[dict]:
    return parse_kyero(content) if detect_format(content) == "kyero" else parse_tivvo_xml(content)
