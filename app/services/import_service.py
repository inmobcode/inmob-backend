"""Migrating properties in from another platform.

`analyze` reads the input and works out what an import would do (create,
update, leave alone, reject) without touching the database: that is the
"modo prueba" the UI shows. `run` applies the same plan. Both start from the
same input, so what the preview showed is what the import does.

Identity is (agency, source, external_id): importing the same feed again
updates the properties it created instead of duplicating them. A blank value
in the input never erases what is already stored.
"""
from dataclasses import dataclass, field

from app.extensions import db
from app.models.agency import Agency
from app.models.property import Classification, Description, Property, PropertyOwner, PropertyPhoto
from app.services import property_service
from app.services.importers import normalize as n
from app.services.importers import tabular, xmlfeeds
from app.services.importers.fetch import fetch_feed
from app.services.importers.records import ImportParseError, normalize_record
from app.utils import rich_text, trash

FORMATS = ("table", "kyero", "tivvo_xml")
DEFAULT_SOURCE = {"table": "csv", "kyero": "kyero", "tivvo_xml": "tivvo"}

# record key → Property column, for the plain scalar fields.
SCALAR_FIELDS = (
    "title",
    "listing_type",
    "category",
    "price",
    "currency",
    "country",
    "region",
    "area",
    "address",
    "lat",
    "lng",
    "bedrooms",
    "bathrooms",
    "area_sqm",
    "plot_area",
    "construction_year",
    "energy_certificate",
    "website_url",
)
FEATURE_COLUMNS = ("outdoor_amenities", "indoor_amenities", "custom_facilities")
MISSING_SAMPLE = 20


class ImportFailure(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass
class Entry:
    row: int
    record: dict
    action: str = "create"  # create | update | unchanged | skip | error
    changes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    prop: Property | None = None

    @property
    def title(self) -> str | None:
        return self.record.get("title")

    def to_dict(self) -> dict:
        return {
            "row": self.row,
            "action": self.action,
            "externalId": self.record.get("external_id"),
            "title": self.title,
            "changes": self.changes,
            "warnings": self.warnings,
            "errors": self.errors,
        }


@dataclass
class Plan:
    entries: list[Entry]
    missing: list[Property]
    warnings: list[str]
    source: str
    currency: str  # the agency's, for properties the input gives no currency for
    table: dict | None = None  # headers / mapping / sample rows, for the column-mapping step

    def counts(self) -> dict:
        counts = {"create": 0, "update": 0, "unchanged": 0, "skip": 0, "error": 0}
        for entry in self.entries:
            counts[entry.action] += 1
        counts["trash"] = len(self.missing)
        return counts

    def to_dict(self, *, limit_rows: int | None = None) -> dict:
        rows = [entry.to_dict() for entry in self.entries]
        return {
            "counts": self.counts(),
            "warnings": self.warnings,
            "rows": rows[:limit_rows] if limit_rows else rows,
            "missing": [{"id": p.id, "title": p.title, "externalId": p.external_id} for p in self.missing[:MISSING_SAMPLE]],
            "table": self.table,
        }


# ---------------------------------------------------------------- reading


def read_input(*, fmt: str, content: bytes | None, filename: str, url: str | None) -> tuple[bytes, str]:
    if fmt not in FORMATS:
        raise ImportFailure("Formato de importación desconocido")
    if content:
        return content, filename
    if url:
        try:
            return fetch_feed(url)
        except ImportParseError as err:
            raise ImportFailure(err.message, err.status_code) from err
    raise ImportFailure("Subí un archivo o pegá la URL del feed.")


def _raw_records(fmt: str, content: bytes, filename: str, mapping: dict | None) -> tuple[list[dict], dict | None]:
    try:
        if fmt == "table":
            headers, rows = tabular.read_table(content, filename)
            suggested = tabular.suggest_mapping(headers)
            used = suggested if mapping is None else {h: mapping.get(h) for h in headers}
            table = {
                "headers": headers,
                "mapping": used,
                "suggested": suggested,
                "sample": [[row[h] for h in headers] for row in rows[: tabular.PREVIEW_ROWS]],
                "totalRows": len(rows),
            }
            return tabular.records_from_table(rows, used), table
        if fmt == "kyero":
            return xmlfeeds.parse_kyero(content), None
        return xmlfeeds.parse_tivvo_xml(content), None
    except ImportParseError as err:
        raise ImportFailure(err.message, err.status_code) from err


# ---------------------------------------------------------------- planning


def _same(a, b) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        return a is not None and b is not None and abs(float(a) - float(b)) < 1e-6
    return a == b


def _changes(prop: Property, record: dict) -> list[str]:
    changed = [key for key in SCALAR_FIELDS if key in record and not _same(getattr(prop, key), record[key])]
    content = prop.content
    for key in ("summary", "description"):
        if key in record:
            current = getattr(content, key, None) if content else None
            if rich_text.sanitize(record[key]) != current:
                changed.append(key)
    if "parking_spaces" in record:
        current = prop.classification.parking_spaces if prop.classification else None
        if current != record["parking_spaces"]:
            changed.append("parking_spaces")
    if "features" in record:
        wanted = n.classify_features(record["features"])
        if any(name not in (getattr(prop, column) or []) for column, names in wanted.items() for name in names):
            changed.append("features")
    if "photos" in record:
        have = {photo.url for photo in prop.photos}
        if any(url not in have for url in record["photos"]):
            changed.append("photos")
    if record.get("owner_name") or record.get("owner_email"):
        owner = prop.owner
        if owner is None or (record.get("owner_email") and (owner.email or "").lower() != record["owner_email"].lower()) or (
            not record.get("owner_email") and owner.name != record.get("owner_name")
        ):
            changed.append("owner")
    return changed


def analyze(
    agency_id: str,
    *,
    fmt: str,
    source: str | None,
    content: bytes,
    filename: str,
    mapping: dict | None = None,
    archive_missing: bool = False,
) -> Plan:
    source = n.source_slug(source) or DEFAULT_SOURCE[fmt]
    raws, table = _raw_records(fmt, content, filename, mapping)
    if fmt == "table" and not any(mapping_key for mapping_key in (table or {}).get("mapping", {}).values()):
        raise ImportFailure("Elegí al menos una columna para importar.")

    agency = db.session.get(Agency, agency_id)
    entries: list[Entry] = []
    plan_warnings: list[str] = []

    for index, raw in enumerate(raws, start=2 if fmt == "table" else 1):
        record, warnings = normalize_record(raw)
        entries.append(Entry(row=index, record=record, warnings=warnings))

    ids = [e.record["external_id"] for e in entries if "external_id" in e.record]
    existing: dict[str, Property] = {}
    if ids:
        for prop in Property.query.filter(
            Property.agency_id == agency_id, Property.source == source, Property.external_id.in_(set(ids))
        ):
            existing[prop.external_id] = prop

    seen: set[str] = set()
    for entry in entries:
        record = entry.record
        external_id = record.get("external_id")

        if external_id:
            if external_id in seen:
                entry.action = "error"
                entry.errors.append(f"La referencia «{external_id}» está repetida en el archivo.")
                continue
            seen.add(external_id)

        prop = existing.get(external_id) if external_id else None
        entry.prop = prop

        if prop is not None and prop.deleted_at is not None:
            entry.action = "skip"
            entry.warnings.append("Está en la papelera: restaurala para que se actualice.")
            continue

        if prop is None:
            if "title" not in record:
                generated = _generated_title(record)
                if generated is None:
                    entry.action = "error"
                    entry.errors.append("Falta el título (y no hay tipo ni zona para armar uno).")
                    continue
                record["title"] = generated
                entry.warnings.append(f"Sin título: se armó «{generated}».")
            if len(record["title"]) < 2:
                entry.action = "error"
                entry.errors.append("El título es demasiado corto.")
                continue
            record["title"] = record["title"][:200]
            if "category" not in record:
                entry.warnings.append("Sin tipo de propiedad: se creará como casa.")
            entry.action = "create"
            entry.changes = [key for key in (*SCALAR_FIELDS, "summary", "description", "features", "photos", "parking_spaces") if key in record]
            if record.get("owner_name") or record.get("owner_email"):
                entry.changes.append("owner")
            continue

        if "title" in record:
            record["title"] = record["title"][:200]
        entry.changes = _changes(prop, record)
        entry.action = "update" if entry.changes else "unchanged"

    if not any(e.record.get("external_id") for e in entries):
        plan_warnings.append(
            "Ninguna fila tiene referencia: cada importación creará propiedades nuevas en lugar de actualizar las anteriores."
        )
    elif any(e.action == "create" and "external_id" not in e.record for e in entries):
        plan_warnings.append("Hay filas sin referencia: se crearán de nuevo cada vez que importes.")

    missing: list[Property] = []
    if archive_missing:
        if not seen:
            raise ImportFailure("Para archivar las que faltan, el archivo necesita referencias (ID) en las propiedades.")
        if not any(e.action != "error" for e in entries):
            raise ImportFailure("No hay ninguna fila válida: no se archiva nada para evitar vaciar tu catálogo por un feed roto.")
        missing = (
            Property.query.filter(
                Property.agency_id == agency_id,
                Property.source == source,
                Property.deleted_at.is_(None),
                Property.external_id.isnot(None),
                Property.external_id.notin_(seen),
            )
            .order_by(Property.title)
            .all()
        )

    return Plan(
        entries=entries,
        missing=missing,
        warnings=plan_warnings,
        source=source,
        currency=agency.currency if agency else "USD",
        table=table,
    )


def _generated_title(record: dict) -> str | None:
    kind = record.get("category")
    place = record.get("area") or record.get("region")
    if not (kind or place):
        return None
    label = (kind or "PROPERTY").replace("_", " ").capitalize()
    return f"{label} en {place}" if place else label


# ---------------------------------------------------------------- applying


def _resolve_owner(agency_id: str, record: dict) -> PropertyOwner | None:
    name = record.get("owner_name")
    email = record.get("owner_email") if "@" in (record.get("owner_email") or "") else None
    if not (name or email):
        return None
    query = PropertyOwner.query.filter_by(agency_id=agency_id)
    owner = None
    if email:
        owner = query.filter(db.func.lower(PropertyOwner.email) == email.lower()).first()
    elif name:
        owner = query.filter(db.func.lower(PropertyOwner.name) == name.lower()).first()
    if owner is None:
        owner = PropertyOwner(agency_id=agency_id, name=(name or email)[:200], email=email, phone=record.get("owner_phone"))
        db.session.add(owner)
        db.session.flush()
    return owner


def _write(agency_id: str, created_by: str, plan: Plan, entry: Entry, *, publish: bool) -> None:
    record = entry.record
    prop = entry.prop
    if prop is None:
        prop = Property(
            agency_id=agency_id,
            created_by=created_by,
            source=plan.source,
            external_id=record.get("external_id"),
            title=record["title"],
            slug=property_service._unique_slug(agency_id, record["title"]),
            listing_type=record.get("listing_type", "SALE"),
            category=record.get("category", "HOUSE"),
            currency=record.get("currency", plan.currency),
            status="PUBLISHED" if publish else "DRAFT",
        )
        db.session.add(prop)
        db.session.flush()
    elif "title" in record and record["title"] != prop.title:
        prop.slug = property_service._unique_slug(agency_id, record["title"], exclude_id=prop.id)

    for key in SCALAR_FIELDS:
        if key in record:
            setattr(prop, key, record[key])

    if "summary" in record or "description" in record:
        if prop.content is None:
            prop.content = Description(property_id=prop.id)
            db.session.add(prop.content)
        for key in ("summary", "description"):
            if key in record:
                setattr(prop.content, key, rich_text.sanitize(record[key]))

    if "parking_spaces" in record:
        if prop.classification is None:
            prop.classification = Classification(property_id=prop.id)
            db.session.add(prop.classification)
        prop.classification.parking_spaces = record["parking_spaces"]

    if "features" in record:
        for column, names in n.classify_features(record["features"]).items():
            current = list(getattr(prop, column) or [])
            merged = current + [name for name in names if name not in current]
            if merged != current:
                setattr(prop, column, merged)  # new list: SQLAlchemy doesn't see in-place JSON edits

    if "photos" in record:
        have = {photo.url for photo in prop.photos}
        position = len(prop.photos)
        for url in record["photos"]:
            if url in have:
                continue
            db.session.add(PropertyPhoto(property_id=prop.id, url=url, position=position, is_cover=position == 0))
            position += 1

    owner = _resolve_owner(agency_id, record)
    if owner is not None:
        prop.owner_id = owner.id


def run(agency_id: str, created_by: str, plan: Plan, *, publish: bool = False) -> dict:
    """Applies the plan. Each row is isolated: one failing row is reported,
    the others still import."""
    done = {"create": 0, "update": 0, "failed": 0, "trash": 0}
    results: list[dict] = []
    for entry in plan.entries:
        if entry.action not in ("create", "update"):
            continue
        try:
            with db.session.begin_nested():
                _write(agency_id, created_by, plan, entry, publish=publish)
            done[entry.action] += 1
        except Exception as err:  # noqa: BLE001  one bad row must not abort the batch
            done["failed"] += 1
            results.append({"row": entry.row, "externalId": entry.record.get("external_id"), "error": str(err)[:300]})
    for prop in plan.missing:
        prop.deleted_at = trash.now()
        done["trash"] += 1
    db.session.commit()
    return {"done": done, "failures": results}
