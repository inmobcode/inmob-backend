"""The fields an import can fill, and the column names that usually mean each one.

Every importer (CSV/Excel, Kyero, Tivvu XML) produces records keyed by these
`key`s; `import_service` is the only place that knows how they land in the
database. `aliases` also feed the automatic column suggestion for CSV/Excel,
so they include the RESO Data Dictionary names and the usual Spanish /
Portuguese / Greek-CRM export headers.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ImportField:
    key: str
    label: str
    kind: str  # text | number | integer | list | url
    aliases: tuple[str, ...] = ()


IMPORT_FIELDS: tuple[ImportField, ...] = (
    ImportField(
        "external_id",
        "Referencia / ID en la plataforma",
        "text",
        ("id", "ref", "reference", "referencia", "ref.", "listingkey", "listingid", "codigo", "code", "property id"),
    ),
    ImportField("title", "Título", "text", ("title", "titulo", "name", "nombre", "headline", "listing title")),
    ImportField(
        "listing_type",
        "Operación (venta / alquiler)",
        "text",
        ("operation", "operacion", "listing type", "transaction", "transactiontype", "tipo operacion", "for", "status type"),
    ),
    ImportField(
        "category",
        "Tipo de propiedad",
        "text",
        ("type", "tipo", "property type", "propertytype", "propertysubtype", "tipologia", "category", "categoria"),
    ),
    ImportField("price", "Precio", "number", ("price", "precio", "listprice", "asking price", "preco", "valor")),
    ImportField("currency", "Moneda", "text", ("currency", "moneda", "pricecurrency", "divisa")),
    ImportField("country", "País", "text", ("country", "pais", "país", "countryorregion")),
    ImportField("region", "Región / provincia", "text", ("region", "province", "provincia", "stateorprovince", "state", "distrito", "prefecture")),
    ImportField("area", "Zona / ciudad", "text", ("area", "zona", "town", "city", "ciudad", "localidad", "municipality", "municipio", "location", "neighborhood", "barrio")),
    ImportField("address", "Dirección", "text", ("address", "direccion", "dirección", "street", "calle", "unparsedaddress")),
    ImportField("lat", "Latitud", "number", ("latitude", "latitud", "lat")),
    ImportField("lng", "Longitud", "number", ("longitude", "longitud", "lng", "lon", "long")),
    ImportField("bedrooms", "Dormitorios", "integer", ("bedrooms", "beds", "dormitorios", "habitaciones", "quartos", "bedroomstotal", "rooms", "hab")),
    ImportField("bathrooms", "Baños", "integer", ("bathrooms", "baths", "banos", "baños", "casas de banho", "bathroomstotalinteger", "wc")),
    ImportField("area_sqm", "Superficie construida (m²)", "number", ("built", "built area", "surface", "superficie", "m2", "sqm", "livingarea", "area construida", "construido", "size")),
    ImportField("plot_area", "Superficie de parcela (m²)", "number", ("plot", "plot area", "parcela", "lotsizearea", "terreno", "land area", "plot size")),
    ImportField("construction_year", "Año de construcción", "integer", ("year built", "yearbuilt", "ano construccion", "año construcción", "año", "construction year")),
    ImportField("energy_certificate", "Certificado energético", "text", ("energy", "energy rating", "energy certificate", "certificado energetico", "calificacion energetica", "epc")),
    ImportField("summary", "Resumen", "text", ("summary", "resumen", "short description", "descripcion corta")),
    ImportField("description", "Descripción", "text", ("description", "descripcion", "descripción", "desc", "publicremarks", "details", "remarks")),
    ImportField("website_url", "Link a la ficha original", "url", ("url", "link", "website", "listing url", "enlace", "web")),
    ImportField("features", "Características (separadas por , ; o |)", "list", ("features", "caracteristicas", "características", "amenities", "extras", "equipamiento")),
    ImportField("photos", "Fotos (URLs separadas por , ; | o espacio)", "list", ("photos", "images", "fotos", "imagenes", "imágenes", "pictures", "photo urls", "image urls", "media")),
    ImportField("parking_spaces", "Plazas de parking", "integer", ("parking", "parking spaces", "garage", "garaje", "plazas parking", "parkingtotal")),
    ImportField("owner_name", "Propietario: nombre", "text", ("owner", "owner name", "propietario", "vendor", "vendedor", "landlord")),
    ImportField("owner_email", "Propietario: email", "text", ("owner email", "email propietario", "vendor email")),
    ImportField("owner_phone", "Propietario: teléfono", "text", ("owner phone", "telefono propietario", "vendor phone", "owner mobile")),
)

FIELDS_BY_KEY = {field.key: field for field in IMPORT_FIELDS}
