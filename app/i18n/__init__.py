"""Languages: which one a request, a person or an email is in.

The frontend sends the page's language in the `X-Locale` header. Emails go out
in the language of whoever reads them: a client in the one they used on the
agency's site (or the site's language), a teammate in the one they use in the
dashboard (`User.locale`, kept in sync from that header). Spanish is the base
and the fallback for anything missing.
"""
from flask import has_request_context, request

LOCALES = ("es", "en", "pt", "fr", "de", "it", "el", "hr")
DEFAULT_LOCALE = "es"


def normalize(value: str | None) -> str | None:
    """'en-GB' → 'en'; anything we don't speak → None."""
    if not value:
        return None
    code = value.strip().lower().replace("_", "-").split("-")[0]
    return code if code in LOCALES else None


def request_locale() -> str | None:
    """The language the frontend asked for, if any (no header: None)."""
    if not has_request_context():
        return None
    return normalize(request.headers.get("X-Locale"))


def pick(*candidates: str | None) -> str:
    """The first candidate we speak, else Spanish."""
    for candidate in candidates:
        code = normalize(candidate)
        if code:
            return code
    return DEFAULT_LOCALE


def t(locale: str, key: str, **params) -> str:
    """An email/notification string in `locale` (falls back to Spanish)."""
    from app.i18n.messages import MESSAGES

    template = MESSAGES.get(locale, {}).get(key) or MESSAGES[DEFAULT_LOCALE][key]
    return template.format(**params) if params else template


# Month names as they read inside a date ("5 de noviembre", "5. studenoga").
MONTHS = {
    "es": ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"),
    "en": ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"),
    "pt": ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"),
    "fr": ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"),
    "de": ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"),
    "it": ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"),
    "el": ("Ιανουαρίου", "Φεβρουαρίου", "Μαρτίου", "Απριλίου", "Μαΐου", "Ιουνίου", "Ιουλίου", "Αυγούστου", "Σεπτεμβρίου", "Οκτωβρίου", "Νοεμβρίου", "Δεκεμβρίου"),
    "hr": ("siječnja", "veljače", "ožujka", "travnja", "svibnja", "lipnja", "srpnja", "kolovoza", "rujna", "listopada", "studenoga", "prosinca"),
}

LONG_DATE = {
    "es": "{d} de {m} de {y}",
    "en": "{d} {m} {y}",
    "pt": "{d} de {m} de {y}",
    "fr": "{d} {m} {y}",
    "de": "{d}. {m} {y}",
    "it": "{d} {m} {y}",
    "el": "{d} {m} {y}",
    "hr": "{d}. {m} {y}.",
}

SHORT_DATE = {"es": "{d}/{mm}", "en": "{d}/{mm}", "pt": "{d}/{mm}", "fr": "{d}/{mm}", "de": "{d}.{mm}.", "it": "{d}/{mm}", "el": "{d}/{mm}", "hr": "{d}.{mm}."}


def long_date(locale: str, day) -> str:
    return LONG_DATE[locale].format(d=day.day, m=MONTHS[locale][day.month - 1], y=day.year)


def short_date(locale: str, day) -> str:
    return SHORT_DATE[locale].format(d=f"{day.day:02d}", mm=f"{day.month:02d}")


def public_path(locale: str, path: str) -> str:
    """A path on the public site in `locale`: Spanish has no prefix (/booking/x), the rest do (/en/booking/x)."""
    return path if locale == DEFAULT_LOCALE else f"/{locale}{path}"
