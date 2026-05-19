"""Unit tests for the fuzzy product matcher."""

from uuid import uuid4

from lpb_worker.ingestion.matchers.fuzzy import FuzzyProductMatcher


def _matcher_with(products):
    return FuzzyProductMatcher(products)


def test_exact_code_match():
    p1 = uuid4()
    p2 = uuid4()
    m = _matcher_with([
        (p1, "1234567", "BASIL HAYDEN BOURBON", "1.75L"),
        (p2, "1234568", "CSJ CHARD CARNR 21 6P", "750ML"),
    ])
    r = m.match(description="anything", candidate_code="1234567")
    assert r.product_id == p1
    assert r.confidence == 1.0
    assert r.code_match


def test_strong_description_match_with_size_boost():
    p1 = uuid4()
    m = _matcher_with([
        (p1, "1234567", "BASIL HAYDEN BOURBON", "1.75L"),
    ])
    r = m.match(description="BASIL HAYDEN", size="1.75L")
    assert r.product_id == p1
    assert r.confidence >= 0.65  # ~0.5 jaccard + 0.10 size boost


def test_size_mismatch_penalty():
    p1 = uuid4()
    p2 = uuid4()
    m = _matcher_with([
        (p1, "1234567", "BASIL HAYDEN BOURBON", "1.75L"),
        (p2, "9999999", "BASIL HAYDEN BOURBON", "750ML"),
    ])
    # Searching for the 750ml variant - should prefer p2 over p1
    r = m.match(description="BASIL HAYDEN BOURBON", size="750ML")
    assert r.product_id == p2


def test_low_confidence_below_threshold():
    p1 = uuid4()
    m = _matcher_with([
        (p1, "1234567", "BASIL HAYDEN BOURBON", "1.75L"),
    ])
    r = m.match(description="COMPLETELY UNRELATED VODKA")
    assert r.confidence < 0.85
    assert not r.is_confident


def test_no_products():
    m = _matcher_with([])
    r = m.match(description="anything")
    assert r.product_id is None
    assert r.confidence == 0.0


def test_empty_description():
    p1 = uuid4()
    m = _matcher_with([
        (p1, "1234567", "BASIL HAYDEN BOURBON", "1.75L"),
    ])
    r = m.match(description=None)
    assert r.product_id is None
