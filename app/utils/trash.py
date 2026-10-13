"""Shared bits of the trash (see TrashMixin in app/models/base.py)."""
from datetime import datetime, timedelta, timezone

# Days a deleted record stays in the trash before it's deleted for good.
TRASH_DAYS = 30


def now() -> datetime:
    """Naive UTC, like the rest of the stored datetimes."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def purge_cutoff() -> datetime:
    """Anything trashed before this is past its time in the trash."""
    return now() - timedelta(days=TRASH_DAYS)
