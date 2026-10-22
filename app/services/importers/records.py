"""Shared last step of every importer: loose per-field values → one typed record."""
from app.services.importers import normalize as n
from app.services.importers.fields import FIELDS_BY_KEY

MAX_RECORDS = 3000


class ImportParseError(Exception):
    """The input can't be read at all (wrong format, corrupt, too big)."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def normalize_record(raw: dict) -> tuple[dict, list[str]]:
    """Returns (record, warnings). Empty values are left out of the record on
    purpose: re-importing a row with a blank cell must not wipe the data
    already in the property."""
    record: dict = {}
    warnings: list[str] = []

    def put(key, value):
        if value is not None and value != "" and value != []:
            record[key] = value

    for key in ("external_id", "title", "country", "region", "area", "address", "owner_name", "owner_email", "owner_phone"):
        put(key, n.clean_text(raw.get(key)))
    if "external_id" in record:
        record["external_id"] = record["external_id"][:200]

    put("summary", n.clean_text(raw.get("summary")))
    put("description", n.clean_text(raw.get("description")))

    website = n.clean_text(raw.get("website_url"))
    if website:
        if website.lower().startswith(("http://", "https://")) and len(website) <= 1000:
            record["website_url"] = website
        else:
            warnings.append("El link a la ficha original no es una URL válida; se ignoró.")

    raw_type = raw.get("listing_type")
    if n.clean_text(raw_type):
        listing_type = n.parse_listing_type(raw_type)
        if listing_type:
            record["listing_type"] = listing_type
        else:
            warnings.append(f"No se entendió la operación «{raw_type}»; se tomó como venta.")

    raw_category = raw.get("category")
    if n.clean_text(raw_category):
        category = n.parse_category(raw_category)
        if category:
            record["category"] = category
        else:
            warnings.append(f"Tipo de propiedad «{raw_category}» no reconocido; se tomó como casa.")

    for key in ("price", "area_sqm", "plot_area"):
        raw_value = raw.get(key)
        if n.clean_text(raw_value) is None and not isinstance(raw_value, (int, float)):
            continue
        number = n.parse_number(raw_value)
        if number is None or number < 0:
            warnings.append(f"{FIELDS_BY_KEY[key].label}: «{raw_value}» no es un número.")
        elif number > 0:
            record[key] = number

    for key in ("lat", "lng"):
        raw_value = raw.get(key)
        if n.clean_text(raw_value) is None and not isinstance(raw_value, (int, float)):
            continue
        number = n.parse_number(raw_value, coordinate=True)
        limit = 90 if key == "lat" else 180
        if number is None or abs(number) > limit:
            warnings.append(f"{FIELDS_BY_KEY[key].label}: «{raw_value}» no es una coordenada válida.")
        else:
            record[key] = number
    if ("lat" in record) != ("lng" in record):
        record.pop("lat", None)
        record.pop("lng", None)
        warnings.append("Faltaba una de las dos coordenadas; se ignoraron.")
    elif record.get("lat") == 0 and record.get("lng") == 0:
        record.pop("lat")
        record.pop("lng")

    for key in ("bedrooms", "bathrooms", "construction_year", "parking_spaces"):
        raw_value = raw.get(key)
        if n.clean_text(raw_value) is None and not isinstance(raw_value, (int, float)):
            continue
        number = n.parse_int(raw_value)
        if number is None or number < 0:
            warnings.append(f"{FIELDS_BY_KEY[key].label}: «{raw_value}» no es un número.")
        elif key == "construction_year" and not 1000 <= number <= 2100:
            warnings.append(f"Año de construcción «{raw_value}» fuera de rango; se ignoró.")
        elif number > 0 or key in ("bedrooms", "bathrooms", "parking_spaces"):
            record[key] = number

    currency = n.parse_currency(raw.get("currency"))
    if currency:
        record["currency"] = currency
    elif n.clean_text(raw.get("currency")):
        warnings.append(f"Moneda «{raw.get('currency')}» no reconocida; se usó la de la propiedad.")

    if n.clean_text(raw.get("energy_certificate")):
        energy = n.parse_energy(raw.get("energy_certificate"))
        if energy:
            record["energy_certificate"] = energy

    features = n.split_list(raw.get("features"))
    if features:
        record["features"] = features

    photos = n.split_urls(raw.get("photos"))
    if photos:
        unique = list(dict.fromkeys(url for url in photos if len(url) <= 1000))
        if len(unique) > n.MAX_PHOTOS:
            warnings.append(f"Tiene {len(unique)} fotos; se importan las primeras {n.MAX_PHOTOS}.")
        record["photos"] = unique[: n.MAX_PHOTOS]

    return record, warnings
