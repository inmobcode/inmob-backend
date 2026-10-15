import re

from marshmallow import Schema, ValidationError, fields, post_dump, post_load, validate, validates

from app.utils import rich_text

SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
HEX_COLOR_RE = r"^#[0-9a-fA-F]{6}$"

SITE_TEMPLATES = ("portada", "editorial", "compacto", "dividido", "mosaico")
SITE_SECTION_TYPES = ("location", "promo", "featured", "destinations", "text", "cta")
# Every layout any block can use; the frontend offers the ones that fit each type
# and falls back to the type's first layout for anything else.
SITE_SECTION_LAYOUTS = (
    "split",
    "banner",
    "band",
    "carousel",
    "grid",
    "tiles",
    "image-left",
    "image-right",
    "centered",
    "color",
    "photo",
)
SITE_BUTTON_TARGETS = ("contact", "whatsapp", "properties")
ISO_DATE_RE = r"^\d{4}-\d{2}-\d{2}$"
SITE_FONTS = ("moderna", "clasica", "sobria", "elegante", "editorial", "calida", "urbana", "arquitectonica")


def _validate_slug(value: str) -> None:
    if not SLUG_RE.match(value):
        raise ValidationError(
            "Solo minúsculas, números y guiones (sin guiones al principio/final)."
        )


class DestinationSchema(Schema):
    """One place inside a "destinations" block."""

    id = fields.Str(required=True, validate=validate.Length(min=1, max=40))
    name = fields.Str(allow_none=True, validate=validate.Length(max=80))
    zone = fields.Str(allow_none=True, validate=validate.Length(max=120))
    image_url = fields.Str(data_key="imageUrl", allow_none=True, validate=validate.Length(max=500))


class SiteSectionSchema(Schema):
    """A content block on the agency's home page: a featured location, a
    promotion, hand-picked listings, a set of destinations, free text with an
    image, or a call to action."""

    id = fields.Str(required=True, validate=validate.Length(min=1, max=40))
    type = fields.Str(required=True, validate=validate.OneOf(SITE_SECTION_TYPES))
    visible = fields.Bool()
    layout = fields.Str(allow_none=True, validate=validate.OneOf(SITE_SECTION_LAYOUTS))
    title = fields.Str(allow_none=True, validate=validate.Length(max=120))
    # Formatted text (HTML) in "text" blocks, plain in the rest; room for the markup.
    text = fields.Str(allow_none=True, validate=validate.Length(max=5000))
    image_url = fields.Str(data_key="imageUrl", allow_none=True, validate=validate.Length(max=500))
    # location: which properties belong to it (matched against area, region or
    # country) unless specific ones are chosen in property_ids.
    zone = fields.Str(allow_none=True, validate=validate.Length(max=120))
    # promo: the label on the block and on each included listing, e.g. "15% OFF".
    badge = fields.Str(allow_none=True, validate=validate.Length(max=40))
    property_ids = fields.List(
        fields.Str(validate=validate.Length(max=40)),
        data_key="propertyIds",
        validate=validate.Length(max=12),
    )
    # Kept as an ISO date string so it stores as plain JSON.
    ends_at = fields.Str(
        data_key="endsAt", allow_none=True, validate=validate.Regexp(ISO_DATE_RE, error="Fecha inválida")
    )

    destinations = fields.List(fields.Nested(DestinationSchema), validate=validate.Length(max=12))
    # text / cta: an optional button and where it leads.
    button_label = fields.Str(data_key="buttonLabel", allow_none=True, validate=validate.Length(max=40))
    button_target = fields.Str(
        data_key="buttonTarget", allow_none=True, validate=validate.OneOf(SITE_BUTTON_TARGETS)
    )

    @post_load
    def fill_defaults(self, data, **kwargs):
        # The site PATCH loads with partial=True, which skips load_default in
        # nested schemas; a block is always a whole object, so complete it here.
        data.setdefault("visible", True)
        data.setdefault("property_ids", [])
        data.setdefault("destinations", [])
        if data.get("type") == "text" and "text" in data:
            data["text"] = rich_text.sanitize(data["text"])
        return data

    @post_dump
    def clean_text_out(self, data, **kwargs):
        # Also on the way out: text written before the editor existed never went through it.
        if data.get("type") == "text" and data.get("text"):
            data["text"] = rich_text.sanitize(data["text"])
        return data


class SiteSettingsSchema(Schema):
    """What an agency can customize on its public site. Every key is optional:
    the frontend fills in anything missing with its defaults."""

    template = fields.Str(validate=validate.OneOf(SITE_TEMPLATES))
    # A different layout on phones; null means the same one as on desktop.
    template_mobile = fields.Str(data_key="templateMobile", allow_none=True, validate=validate.OneOf(SITE_TEMPLATES))
    accent = fields.Str(validate=validate.Regexp(HEX_COLOR_RE, error="Color inválido"))
    fonts = fields.Str(validate=validate.OneOf(SITE_FONTS))
    hero_title = fields.Str(data_key="heroTitle", allow_none=True, validate=validate.Length(max=120))
    hero_subtitle = fields.Str(data_key="heroSubtitle", allow_none=True, validate=validate.Length(max=240))
    cover_url = fields.Str(data_key="coverUrl", allow_none=True, validate=validate.Length(max=500))
    # The "mosaico" layout's collage, in order; empty uses the listings' cover photos.
    mosaic_photos = fields.List(
        fields.Str(validate=validate.Length(max=500)), data_key="mosaicPhotos", validate=validate.Length(max=4)
    )
    # Formatted text (see app/utils/rich_text.py); room for the markup.
    about = fields.Str(allow_none=True, validate=validate.Length(max=10000))
    show_about = fields.Bool(data_key="showAbout")
    phone = fields.Str(allow_none=True, validate=validate.Length(max=40))
    whatsapp = fields.Str(allow_none=True, validate=validate.Length(max=40))
    address = fields.Str(allow_none=True, validate=validate.Length(max=200))
    instagram = fields.Str(allow_none=True, validate=validate.Length(max=100))
    sections = fields.List(fields.Nested(SiteSectionSchema), validate=validate.Length(max=12))

    @post_load
    def clean_about(self, data, **kwargs):
        if "about" in data:
            data["about"] = rich_text.sanitize(data["about"])
        return data

    @post_dump
    def clean_about_out(self, data, **kwargs):
        if data.get("about"):
            data["about"] = rich_text.sanitize(data["about"])
        return data


class AgencySchema(Schema):
    id = fields.Str(dump_only=True)
    name = fields.Str()
    slug = fields.Str()
    logo_url = fields.Str(data_key="logoUrl", allow_none=True)
    contact_email = fields.Str(data_key="contactEmail", allow_none=True)
    locale = fields.Str()
    currency = fields.Str()
    owner_portal_shows_commission = fields.Bool(data_key="ownerPortalShowsCommission")
    site = fields.Method("dump_site")

    def dump_site(self, agency):
        return SiteSettingsSchema().dump(agency.site or {})


class AgencyUpdateSchema(Schema):
    owner_portal_shows_commission = fields.Bool(data_key="ownerPortalShowsCommission")
    name = fields.Str(validate=validate.Length(min=2, max=200))
    slug = fields.Str(validate=validate.Length(min=2, max=200))
    contact_email = fields.Email(data_key="contactEmail", allow_none=True)
    locale = fields.Str(validate=validate.Length(equal=2))
    currency = fields.Str(validate=validate.Length(equal=3))

    @validates("slug")
    def validate_slug(self, value, **kwargs):
        _validate_slug(value)


class AgencyPublicSchema(Schema):
    name = fields.Str()
    logo_url = fields.Str(data_key="logoUrl", allow_none=True)
    contact_email = fields.Str(data_key="contactEmail", allow_none=True)
    site = fields.Method("dump_site")

    def dump_site(self, agency):
        return SiteSettingsSchema().dump(agency.site or {})
