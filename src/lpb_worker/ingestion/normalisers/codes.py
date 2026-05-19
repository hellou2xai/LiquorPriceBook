"""Duplicate-code reconciler.

The scraped main catalog has ~2,000 rows where the same 7-digit product code
appears under conflicting categories (e.g. code 0050840 listed as both IRISH
WHISKEY and GIN in April). This is real PDF layout drift, not data noise:
catalogues legitimately cross-reference some SKUs.

For the product_editions table we collapse to one (product, edition) row.
Strategy: per code, pick the category that occurs the most times across the
full extract. Ties broken by the category with the smaller ``sort_order``
(i.e. the dim's canonical ordering).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable


def resolve_duplicate_code_categories(
    rows: Iterable[dict],
    sort_order_by_category_id: dict | None = None,
) -> dict[str, str | None]:
    """Given an iterable of dicts each containing at least ``code`` and
    ``category_id`` keys, return a mapping ``{code -> winning_category_id}``.

    None categories (unresolved) are excluded from the vote. If every row for
    a code is unresolved, the code maps to None.
    """
    votes: dict[str, Counter] = defaultdict(Counter)
    seen_codes: set[str] = set()
    for row in rows:
        code = row.get("code")
        cat = row.get("category_id")
        if code is None:
            continue
        seen_codes.add(code)
        if cat is not None:
            votes[code][cat] += 1

    sort_order_by_category_id = sort_order_by_category_id or {}
    winners: dict[str, str | None] = {}

    def tiebreak_key(item):
        category_id, count = item
        return (-count, sort_order_by_category_id.get(category_id, 10_000))

    for code in seen_codes:
        counter = votes.get(code)
        if not counter:
            winners[code] = None
            continue
        ordered = sorted(counter.items(), key=tiebreak_key)
        winners[code] = ordered[0][0]

    return winners
