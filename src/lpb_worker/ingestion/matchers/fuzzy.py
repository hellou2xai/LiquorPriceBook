"""Fuzzy match partials, combos and keg_list rows to products.

Partials/combos rows in the price book don't always carry the canonical 7-digit
product code. They give us a description (and sometimes a 6-7 digit number
that's a substring of the real code) and a size. We resolve to the real product
record using two signals:

  1. Exact code match (when the partial's product_number does match a product
     code in the same edition).
  2. Token-set similarity on description, weighted by size match.

Anything under ``min_confidence`` (default 0.85) goes to the ``low_confidence_matches``
queue for human review rather than being silently linked to the wrong SKU.

Approach
--------
- Build an in-memory index of products in the target edition, keyed by code
  and by a (tokenised description, size) shingle.
- For each unlinked row, score every candidate and take the top one.

We deliberately avoid pulling in rapidfuzz/python-Levenshtein as a dependency
- the token-set Jaccard approach below is plenty for description-vs-description
  comparison and ships zero extra wheels.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

DEFAULT_MIN_CONFIDENCE = 0.85
SIZE_NORMALISE_RE = re.compile(r"\s+")


def _tokenise(text: str | None) -> frozenset[str]:
    if not text:
        return frozenset()
    # uppercase, strip non-alnum (keeps numbers like '750'), split on whitespace
    cleaned = re.sub(r"[^A-Z0-9 ]+", " ", text.upper())
    tokens = [t for t in cleaned.split() if len(t) >= 2]
    return frozenset(tokens)


def _normalise_size(size: str | None) -> str:
    if not size:
        return ""
    return SIZE_NORMALISE_RE.sub("", size.upper())


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    intersect = len(a & b)
    union = len(a | b)
    return intersect / union if union else 0.0


@dataclass(frozen=True)
class _ProductCandidate:
    product_id: UUID
    code: str
    description_tokens: frozenset[str]
    size_norm: str


@dataclass(frozen=True)
class MatchResult:
    product_id: UUID | None
    confidence: float
    code_match: bool

    @property
    def is_confident(self) -> bool:
        return self.confidence >= DEFAULT_MIN_CONFIDENCE


class FuzzyProductMatcher:
    """Builds an in-memory product index once per ingest and scores candidates."""

    def __init__(
        self,
        products: Sequence[tuple[UUID, str, str | None, str | None]],
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    ) -> None:
        """``products`` is an iterable of (product_id, code, description, size)."""
        self.min_confidence = min_confidence
        self._by_code: dict[str, _ProductCandidate] = {}
        self._all: list[_ProductCandidate] = []
        for pid, code, desc, size in products:
            cand = _ProductCandidate(
                product_id=pid,
                code=code,
                description_tokens=_tokenise(desc),
                size_norm=_normalise_size(size),
            )
            self._by_code[code] = cand
            self._all.append(cand)

    def match(
        self,
        description: str | None,
        size: str | None = None,
        candidate_code: str | None = None,
    ) -> MatchResult:
        """Return the best product match for a partial/combo/keg row."""
        # 1. Exact code match wins outright.
        if candidate_code:
            hit = self._by_code.get(candidate_code)
            if hit is not None:
                return MatchResult(hit.product_id, 1.0, code_match=True)
        # 2. Token-set similarity, optionally boosted by size match.
        desc_tokens = _tokenise(description)
        size_norm = _normalise_size(size)
        if not desc_tokens:
            return MatchResult(None, 0.0, code_match=False)
        best: _ProductCandidate | None = None
        best_score = 0.0
        for cand in self._all:
            score = _jaccard(desc_tokens, cand.description_tokens)
            if size_norm and cand.size_norm:
                # Same size = +0.10 boost; mismatching size = -0.20 penalty.
                if size_norm == cand.size_norm:
                    score = min(1.0, score + 0.10)
                else:
                    score = max(0.0, score - 0.20)
            if score > best_score:
                best_score = score
                best = cand
        if best is None:
            return MatchResult(None, 0.0, code_match=False)
        return MatchResult(best.product_id, best_score, code_match=False)
