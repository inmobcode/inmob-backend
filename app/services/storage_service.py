import os
import uuid

from supabase import Client, create_client

# Each asset type gets its own bucket, so permissions/policies/cleanup can be
# tuned per kind instead of all sharing one bucket's settings. Override via
# env if a deployment wants different bucket names.
PROPERTY_PHOTOS_BUCKET = os.environ.get("SUPABASE_BUCKET_PROPERTY_PHOTOS", "property-photos")
AGENCY_LOGOS_BUCKET = os.environ.get("SUPABASE_BUCKET_AGENCY_LOGOS", "agency-logos")
AGENCY_COVERS_BUCKET = os.environ.get("SUPABASE_BUCKET_AGENCY_COVERS", "agency-covers")
AGENCY_SITE_BUCKET = os.environ.get("SUPABASE_BUCKET_AGENCY_SITE", "agency-site")
USER_AVATARS_BUCKET = os.environ.get("SUPABASE_BUCKET_USER_AVATARS", "user-avatars")

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


def _upload(bucket: str, path: str, content: bytes, content_type: str, kind: str) -> str:
    client = _get_client()
    try:
        client.storage.from_(bucket).upload(path, content, {"content-type": content_type})
    except Exception as err:  # storage3 raises its own StorageApiError subclasses
        raise StorageError(f"Could not upload {kind}: {err}", 502)
    return client.storage.from_(bucket).get_public_url(path)


def _ext(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else "webp"


def upload_photo(agency_id: str, property_id: str, filename: str, content: bytes, content_type: str) -> str:
    """Uploads already-compressed bytes to Supabase Storage and returns the public URL.

    Path is namespaced by agency/property so two agencies can never collide
    or guess at each other's files.
    """
    path = f"{agency_id}/{property_id}/{uuid.uuid4().hex}.{_ext(filename)}"
    return _upload(PROPERTY_PHOTOS_BUCKET, path, content, content_type, "photo")


def upload_agency_logo(agency_id: str, filename: str, content: bytes, content_type: str) -> str:
    path = f"{agency_id}/{uuid.uuid4().hex}.{_ext(filename)}"
    return _upload(AGENCY_LOGOS_BUCKET, path, content, content_type, "logo")


def upload_agency_cover(agency_id: str, filename: str, content: bytes, content_type: str) -> str:
    """The public site's cover photo."""
    path = f"{agency_id}/{uuid.uuid4().hex}.{_ext(filename)}"
    return _upload(AGENCY_COVERS_BUCKET, path, content, content_type, "cover")


def upload_avatar(user_id: str, filename: str, content: bytes, content_type: str) -> str:
    path = f"{user_id}/{uuid.uuid4().hex}.{_ext(filename)}"
    return _upload(USER_AVATARS_BUCKET, path, content, content_type, "avatar")


def upload_agency_site_image(agency_id: str, filename: str, content: bytes, content_type: str) -> str:
    """Images for the public site's content blocks."""
    path = f"{agency_id}/{uuid.uuid4().hex}.{_ext(filename)}"
    return _upload(AGENCY_SITE_BUCKET, path, content, content_type, "image")
