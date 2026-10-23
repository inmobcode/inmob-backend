"""Download a feed from a URL the user typed. The server makes this request, so
it must not be usable to reach internal services (SSRF): only http(s), only
public IPs, every redirect re-checked, size and time capped."""
import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import requests
from flask import current_app

from app.services.importers.records import ImportParseError

MAX_BYTES = 25 * 1024 * 1024
TIMEOUT_SECONDS = 20
MAX_REDIRECTS = 3


def _assert_public(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ImportParseError("La URL debe empezar con http:// o https://")
    if current_app.config.get("IMPORT_ALLOW_PRIVATE_URLS"):
        return  # local development only, see config.py
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(parsed.hostname, parsed.port or 443)}
    except socket.gaierror as err:
        raise ImportParseError("No se pudo resolver el dominio de la URL.") from err
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%")[0])
        if not ip.is_global:
            raise ImportParseError("Esa URL apunta a una dirección interna y no se puede usar.")


def fetch_feed(url: str) -> tuple[bytes, str]:
    """(content, filename) of the file behind the URL."""
    current = url.strip()
    for _ in range(MAX_REDIRECTS + 1):
        _assert_public(current)
        try:
            response = requests.get(
                current,
                timeout=TIMEOUT_SECONDS,
                stream=True,
                allow_redirects=False,
                headers={"User-Agent": "Tivvu-Importer/1.0", "Accept": "application/xml,text/xml,text/csv,*/*"},
            )
        except requests.RequestException as err:
            raise ImportParseError("No se pudo descargar el feed. Revisá que la URL sea pública y esté activa.") from err

        if response.is_redirect:
            current = urljoin(current, response.headers.get("Location", ""))
            response.close()
            continue
        if response.status_code >= 400:
            response.close()
            raise ImportParseError(f"El servidor del feed respondió {response.status_code}.")

        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_content(64 * 1024):
            size += len(chunk)
            if size > MAX_BYTES:
                response.close()
                raise ImportParseError("El feed pesa más de 25 MB.")
            chunks.append(chunk)
        return b"".join(chunks), urlparse(current).path.rsplit("/", 1)[-1]
    raise ImportParseError("La URL redirige demasiadas veces.")
