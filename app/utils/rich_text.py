"""Formatted text written in the app's editor (headings, bold, lists, links).

It arrives as HTML and is shown on public pages and in emails, so only the
tags the editor produces survive: anything else (scripts, styles, event
handlers, other URL schemes) is stripped on save.
"""
import re
from html import escape

import nh3

ALLOWED_TAGS = {"p", "br", "strong", "em", "h2", "h3", "ul", "ol", "li", "a"}
# Short texts (a line under a title): emphasis and links, no headings or lists.
INLINE_TAGS = {"p", "br", "strong", "em", "a"}
ALLOWED_ATTRIBUTES = {"a": {"href"}}
URL_SCHEMES = {"http", "https", "mailto"}


def is_html(text: str) -> bool:
    """Plain text written before the editor existed doesn't start with a tag."""
    return text.lstrip().startswith("<")


def plain_to_html(text: str) -> str:
    """One paragraph per non-empty line, as plain text used to be shown."""
    return "".join(f"<p>{escape(line)}</p>" for line in text.splitlines() if line.strip())


def sanitize(text: str | None, *, inline: bool = False) -> str | None:
    """Clean HTML ready to store, or None when nothing readable is left."""
    if text is None:
        return None
    html = text if is_html(text) else plain_to_html(text)
    if inline:
        # Headings and list items become paragraphs instead of loose text, so
        # the result still starts with a tag and cleaning it again changes nothing.
        html = re.sub(r"<(/?)(?:h[1-6]|li)\b[^>]*>", r"<\1p>", html)
    clean = nh3.clean(
        html,
        tags=INLINE_TAGS if inline else ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=URL_SCHEMES,
        link_rel="noopener noreferrer",
    )
    # An emptied editor still sends "<p></p>".
    if not re.sub(r"<[^>]*>", "", clean).strip():
        return None
    # Text outside any tag would read as plain text next time: keep it in a paragraph.
    if not is_html(clean):
        clean = f"<p>{clean}</p>"
    return clean
