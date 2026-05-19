"""Brand deriver.

The scraped ``brand_header`` column is unusable (~51% of values are sales-rep
tags like ``GS ( L FB JD IV )`` rather than brand names). We derive brand
from the product *description* instead.

Heuristic for v1
----------------
Take the first N tokens of the description, where N stops at the first
"product-modifier" token (digit-bearing, slash-bearing, or a known modifier).
We cap at 2 tokens by default so e.g. ``ADMIRAL NEL SPICED 200ML`` -> brand
``ADMIRAL NEL``, ``MAKERS MARK CASK STRENGTH`` -> ``MAKERS MARK``.

This produces a fragmented dim on day 1 (single-word brands like ``BAYOU
SPICED`` collapse to ``BAYOU SPICED`` rather than just ``BAYOU``). That is
fine - the admin can later merge by adding aliases to ``brands.raw_aliases``.
The slug is the dedup key, so calling ``ensure_brand`` twice with the same
2-token prefix returns the same id.

When brand_header is itself salvageable (has a paren block like
``GLENDALOUGH WILD BOTANICAL GIN GS ( L FB JD IV )``), we prefer it over
the description because it usually carries the full brand + line.
"""

from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from lpb_core.db.models import Brand

# Tokens with a digit or slash mean we've crossed into product modifiers.
_PRODUCT_MODIFIER_RE = re.compile(r"[\d/]")
# Words we treat as product modifiers even if they look like brand candidates.
_MODIFIER_WORDS = {
    "GIN", "VODKA", "RUM", "WHISKEY", "WHISKY", "BOURBON", "TEQUILA",
    "MEZCAL", "BRANDY", "COGNAC", "RYE", "SCOTCH", "MALT", "BLEND",
    "BLANCO", "REPOSADO", "ANEJO", "SPICED", "GOLD", "SILVER", "PROOF",
    "BBN", "CASK", "BARREL", "STRAIGHT", "LIGHT", "DARK",
    "WHITE", "RED", "ROSE", "BRUT", "DRY", "SWEET", "EXTRA",
}
DEFAULT_TOKEN_LIMIT = 2

# Extract the "brand chunk" out of a brand_header that includes territory parens.
_TERRITORY_PAREN_RE = re.compile(r"\s*\([^)]*\)\s*")
# Detect a brand_header that is *just* sales-rep tags (one or more 1-3 letter
# all-caps tokens, optionally with a paren block of more tags). These get
# rejected.
_SALES_REP_ONLY_RE = re.compile(r"^[A-Z]{1,3}(\s+[A-Z]{1,3})*(\s*\([^)]*\))?\s*$")


def _slugify(name: str) -> str:
    """ASCII slug; brand keys ignore punctuation."""
    s = name.upper().strip()
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    s = re.sub(r"\s+", "-", s.strip())
    return s.lower()


def _strip_territory_paren(brand_header: str) -> str:
    return _TERRITORY_PAREN_RE.sub(" ", brand_header).strip()


def _is_sales_rep_tag(brand_header: str) -> bool:
    return bool(_SALES_REP_ONLY_RE.match(brand_header.strip()))


def _take_n_tokens(text: str, limit: int) -> str:
    tokens = text.split()
    out: list[str] = []
    for tok in tokens:
        if _PRODUCT_MODIFIER_RE.search(tok):
            break
        if tok.upper() in _MODIFIER_WORDS and out:
            break
        out.append(tok)
        if len(out) >= limit:
            break
    return " ".join(out)


def derive_brand_name(
    description: str | None,
    brand_header: str | None = None,
    token_limit: int = DEFAULT_TOKEN_LIMIT,
) -> str | None:
    """Return a best-effort brand display name, or None if both inputs are useless."""
    # Try brand_header first if it's salvageable.
    if brand_header and not _is_sales_rep_tag(brand_header):
        chunk = _strip_territory_paren(brand_header)
        candidate = _take_n_tokens(chunk, token_limit)
        if candidate:
            return candidate
    # Fallback: derive from description.
    if description:
        candidate = _take_n_tokens(description.strip(), token_limit)
        if candidate:
            return candidate
    return None


class BrandDeriver:
    """Caches brand lookups within an ingest run so we don't roundtrip per row."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self._by_slug: dict[str, UUID] = {}
        self._load()

    def _load(self) -> None:
        for slug, brand_id in self.session.execute(
            select(Brand.slug, Brand.id)
        ).all():
            self._by_slug[slug] = brand_id

    def ensure(
        self,
        description: str | None,
        brand_header: str | None = None,
    ) -> UUID | None:
        """Resolve to an existing brand_id or insert a new one. Returns None
        only when neither description nor brand_header give us a candidate."""
        display = derive_brand_name(description, brand_header)
        if display is None:
            return None
        slug = _slugify(display)
        if not slug:
            return None
        cached = self._by_slug.get(slug)
        if cached is not None:
            return cached
        # Insert (idempotent via slug unique constraint)
        stmt = (
            pg_insert(Brand)
            .values(slug=slug, display_name=display)
            .on_conflict_do_nothing(index_elements=["slug"])
            .returning(Brand.id)
        )
        res = self.session.execute(stmt).scalar_one_or_none()
        if res is None:
            # Lost the race or already inserted in this txn - re-read.
            res = self.session.execute(
                select(Brand.id).where(Brand.slug == slug)
            ).scalar_one()
        self._by_slug[slug] = res
        return res
