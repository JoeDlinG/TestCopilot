"""Timezone helpers — single source of truth for "what time is it".

Issue #7 (timezone): the project stored ``datetime.utcnow()`` (naive UTC) and
the API serialised it **without** any offset (``2026-10-09T12:00:00``).  The
frontend renders those with ``new Date(t).toLocaleString()``, and JavaScript
parses an ISO string *without* an offset as **local** time — so every timestamp
was displayed 8 hours behind on UTC+8 machines.

Fix: keep every datetime **timezone-aware in UTC** across the whole app, so the
serialised form carries an explicit offset (``+00:00``) and JavaScript resolves
it correctly.  Storage stays a naive UTC string (see ``UTCDateTime``) so older
rows keep their existing semantics and ordering.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.types import DateTime, TypeDecorator


def utc_now() -> datetime:
    """Current time as a timezone-aware UTC datetime.

    Replaces every ``datetime.utcnow()`` call — those returned *naive* UTC and
    were the root of the display bug.
    """
    return datetime.now(timezone.utc)


def from_timestamp(ts: float) -> datetime:
    """Convert a POSIX timestamp (e.g. ``os.path.getmtime``) to aware UTC.

    ``datetime.fromtimestamp()`` returns **local** time while
    ``datetime.utcfromtimestamp()`` returns naive UTC; using this helper keeps
    every call site on the same representation.
    """
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def parse_iso_utc(text: str) -> Optional[datetime]:
    """Parse an ISO timestamp coming from the API into aware UTC.

    Clients may send a string without an offset (``2026-10-09T12:00:00``); it is
    interpreted as UTC, matching how the value would have been stored.
    """
    if not text:
        return None
    try:
        value = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class UTCDateTime(TypeDecorator):
    """A DateTime column that speaks aware-UTC in Python and naive-UTC in SQLite.

    SQLite has no timezone type, so:

    * **write** — the offset is stripped and the value stored as a naive UTC
      string, byte-identical to what ``datetime.utcnow()`` used to produce
      (existing rows and their lexicographic ordering are unaffected);
    * **read** — the stored naive value is re-attached to UTC, so application
      code always sees an aware datetime and Pydantic serialises it with an
      explicit offset.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            # Legacy naive value: it has always been UTC by convention.
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
