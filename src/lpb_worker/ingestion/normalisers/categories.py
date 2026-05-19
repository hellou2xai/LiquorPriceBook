"""Category resolver.

The scraper emits category strings exactly as they appear in the PDF, which
includes OCR-garbled forms like ``STRAIGHTW HISKEY,B OURBON,& M OONSHINE``.
We resolve these against the seeded ``categories`` table where each canonical
category carries a ``raw_aliases`` JSONB array of every observed garbling.

Unknown raw strings are returned as None and a marker is appended to a
``new_aliases`` set so the worker can log them for human review.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from lpb_core.db.models import Category


def _canonical_key(raw: str | None) -> str:
    """Normalise whitespace so 'STRAIGHTW HISKEY' and 'STRAIGHT WHISKEY' both
    look up under the same key."""
    if raw is None:
        return ""
    # collapse any run of whitespace to a single space, strip, uppercase
    return " ".join(raw.split()).strip().upper()


class CategoryResolver:
    """Loads the category dim into memory once per ingest; resolves raw strings."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self._by_key: dict[str, UUID] = {}
        self.unknown: dict[str, int] = {}   # raw_key -> hit count, for the review log
        self._load()

    def _load(self) -> None:
        rows = self.session.execute(select(Category)).scalars().all()
        for cat in rows:
            # Always allow the canonical display_name as an alias.
            self._by_key[_canonical_key(cat.display_name)] = cat.id
            self._by_key[_canonical_key(cat.slug.replace("-", " "))] = cat.id
            for alias in (cat.raw_aliases or []):
                self._by_key[_canonical_key(alias)] = cat.id

    def resolve(self, raw_category: str | None) -> UUID | None:
        if not raw_category:
            return None
        key = _canonical_key(raw_category)
        cat_id = self._by_key.get(key)
        if cat_id is None:
            self.unknown[key] = self.unknown.get(key, 0) + 1
        return cat_id
