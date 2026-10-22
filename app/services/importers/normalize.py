"""Turns the loose values platforms export ("€ 1.250.000", "Venta", "villa
adosada", "1; 2; 3") into what the Property model stores."""
import re
import unicodedata

from app.constants.property_catalogs import (
    ENERGY_CERTIFICATE_OPTIONS,
    INDOOR_AMENITIES,
    OUTDOOR_AMENITIES,
)
from app.models.property import CATEGORIES

MAX_PHOTOS = 60

_CURRENCY_SYMBOLS = {"€": "EUR", "$": "USD", "£": "GBP"}

_SALE_WORDS = {"sale", "sell", "buy", "venta", "vender", "comprar", "venda", "vendita", "pwlisi", "forsale", "for sale", "sold"}
_RENT_WORDS = {
    "rent", "rental", "let", "lease", "alquiler", "alquilar", "arrendamiento", "arrendar", "aluguer", "arrendamento",
    "month", "monthly", "week", "weekly", "day", "daily", "forrent", "for rent", "long term", "short term",
}

# Free-text property types → our category tokens. Longest match wins.
_CATEGORY_SYNONYMS = {
    "villa": "VILLA",
    "chalet": "VILLA",
    "detached villa": "DETACHED_VILLA",
    "detached": "DETACHED_VILLA",
    "semi detached": "SEMI_DETACHED_VILLA",
    "semi-detached": "SEMI_DETACHED_VILLA",
    "adosado": "TOWNHOUSE",
    "townhouse": "TOWNHOUSE",
    "town house": "TOWNHOUSE",
    "terraced": "TOWNHOUSE",
    "apartment": "APARTMENT",
    "apartamento": "APARTMENT",
    "apartmento": "APARTMENT",
    "flat": "APARTMENT",
    "piso": "APARTMENT",
    "studio": "APARTMENT",
    "estudio": "APARTMENT",
    "condo": "CONDO",
    "condominium": "CONDO",
    "penthouse": "PENTHOUSE",
    "atico": "PENTHOUSE",
    "duplex": "MAISONETTE",
    "maisonette": "MAISONETTE",
    "maisonet": "MAISONETTE",
    "house": "HOUSE",
    "casa": "HOUSE",
    "home": "HOUSE",
    "bungalow": "HOUSE",
    "cottage": "HOUSE",
    "finca": "HOUSE",
    "country house": "HOUSE",
    "farmhouse": "HOUSE",
    "cortijo": "HOUSE",
    "moradia": "HOUSE",
    "land": "LAND",
    "plot": "LAND",
    "terreno": "LAND",
    "parcela": "LAND",
    "solar": "LAND",
    "building": "BUILDING",
    "edificio": "BUILDING",
    "commercial": "COMMERCIAL",
    "comercial": "COMMERCIAL",
    "local": "COMMERCIAL",
    "shop": "COMMERCIAL",
    "retail": "COMMERCIAL",
    "office": "OFFICE",
    "oficina": "OFFICE",
    "hotel": "HOTEL",
}

_OUTDOOR_BY_LOWER = {name.lower(): name for name in OUTDOOR_AMENITIES}
_INDOOR_BY_LOWER = {name.lower(): name for name in INDOOR_AMENITIES}
_FEATURE_ALIASES = {
    "swimming pool": "Pool",
    "private pool": "Pool",
    "piscina": "Pool",
    "pool": "Pool",
    "barbecue": "BBQ",
    "barbacoa": "BBQ",
    "lift": "Elevator",
    "ascensor": "Elevator",
    "elevador": "Elevator",
    "gym": "Gym",
    "gimnasio": "Gym",
    "sauna": "Sauna",
    "jacuzzi": "Jacuzzi",
    "fireplace": "Fireplace",
    "chimenea": "Fireplace",
    "tennis court": "Tennis Court",
    "tenis": "Tennis Court",
    "terrace": "Roof Terrace",
    "garden": "Landscaped Gardens",
    "jardin": "Landscaped Gardens",
    "jardín": "Landscaped Gardens",
}


def strip_accents(value: str) -> str:
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")


def clean_text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_number(value, *, coordinate: bool = False) -> float | None:
    """"1.250.000", "1,250,000.50", "€ 250000", "89,5" → float. None when unreadable."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = re.sub(r"[^\d.,\-]", "", str(value))
    if not re.search(r"\d", text):
        return None
    negative = text.startswith("-")
    text = text.replace("-", "")
    if "." in text and "," in text:
        # The last separator is the decimal one.
        decimal = "," if text.rfind(",") > text.rfind(".") else "."
        thousands = "." if decimal == "," else ","
        text = text.replace(thousands, "").replace(decimal, ".")
    elif "," in text or "." in text:
        sep = "," if "," in text else "."
        head, _, tail = text.rpartition(sep)
        many = text.count(sep) > 1
        # "1.250" or "1,250,000" are thousands in prices; coordinates are always decimal.
        if many or (not coordinate and len(tail) == 3 and head.replace(sep, "").isdigit() and head != "0"):
            text = text.replace(sep, "")
        else:
            text = f"{head}.{tail}"
    try:
        number = float(text)
    except ValueError:
        return None
    return -number if negative else number


def parse_int(value) -> int | None:
    number = parse_number(value)
    if number is None:
        return None
    return int(round(number))


def parse_currency(value) -> str | None:
    text = clean_text(value)
    if text is None:
        return None
    for symbol, code in _CURRENCY_SYMBOLS.items():
        if symbol in text:
            return code
    code = re.sub(r"[^A-Za-z]", "", text).upper()
    return code if len(code) == 3 else None


def parse_listing_type(value) -> str | None:
    text = clean_text(value)
    if text is None:
        return None
    words = strip_accents(text).lower()
    if words in {"sale", "rent"}:
        return words.upper()
    tokens = set(re.split(r"[^a-z]+", words)) | {words}
    if tokens & _RENT_WORDS:
        return "RENT"
    if tokens & _SALE_WORDS:
        return "SALE"
    return None


def parse_category(value) -> str | None:
    text = clean_text(value)
    if text is None:
        return None
    upper = re.sub(r"[\s-]+", "_", text.strip()).upper()
    if upper in CATEGORIES:
        return upper
    lowered = strip_accents(text).lower()
    for phrase in sorted(_CATEGORY_SYNONYMS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(phrase)}\b", lowered):
            return _CATEGORY_SYNONYMS[phrase]
    return None


def parse_energy(value) -> str | None:
    text = clean_text(value)
    if text is None:
        return None
    candidate = text.upper().replace(" ", "")
    return candidate if candidate in ENERGY_CERTIFICATE_OPTIONS else None


def split_list(value, *, pattern: str = r"[|;\n,]+") -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [text for item in value if (text := clean_text(item))]
    return [part.strip() for part in re.split(pattern, str(value)) if part.strip()]


def split_urls(value) -> list[str]:
    """Photo cells: URLs separated by comma, semicolon, pipe, newline or space."""
    urls = split_list(value, pattern=r"[|;,\s]+")
    return [url for url in urls if url.lower().startswith(("http://", "https://"))]


def classify_features(features: list[str]) -> dict[str, list[str]]:
    """Known amenities land in the catalog lists the editor shows as checkboxes;
    anything else is kept as a custom facility instead of being dropped."""
    outdoor: list[str] = []
    indoor: list[str] = []
    custom: list[str] = []
    for feature in features:
        key = feature.strip().lower()
        name = _FEATURE_ALIASES.get(key, feature.strip())
        lowered = name.lower()
        if lowered in _OUTDOOR_BY_LOWER:
            target, label = outdoor, _OUTDOOR_BY_LOWER[lowered]
        elif lowered in _INDOOR_BY_LOWER:
            target, label = indoor, _INDOOR_BY_LOWER[lowered]
        else:
            target, label = custom, feature.strip()[:100]
        if label not in target:
            target.append(label)
    return {"outdoor_amenities": outdoor, "indoor_amenities": indoor, "custom_facilities": custom}


def source_slug(value) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", strip_accents(str(value or "")).lower()).strip("-")
    return text[:40]
