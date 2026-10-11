import os
import uuid

from supabase import Client, create_client

BUCKET_NAME = os.environ.get("SUPABASE_STORAGE_BUCKET", "property-photos")

_client: Client | None = None


class StorageError(Exception):
    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _get_client() -> Client:
    global _client
    if _client is not None:
        return _client

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise StorageError(
            "Photo storage is not configured (missing SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY)", 503
        )
    _client = create_client(url, key)
    return _client


def upload_photo(agency_id: str, property_id: str, filename: str, content: bytes, content_type: str) -> str:
    """Uploads already-compressed bytes to Supabase Storage and returns the public URL.

    Path is namespaced by agency/property so two agencies can never collide
    or guess at each other's files.
    """
    client = _get_client()
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "webp"
    path = f"{agency_id}/{property_id}/{uuid.uuid4().hex}.{ext}"

    try:
        client.storage.from_(BUCKET_NAME).upload(path, content, {"content-type": content_type})
    except Exception as err:  # storage3 raises its own StorageApiError subclasses
        raise StorageError(f"Could not upload photo: {err}", 502)

    return client.storage.from_(BUCKET_NAME).get_public_url(path)
