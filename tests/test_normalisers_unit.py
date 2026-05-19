"""Unit tests for cleaning-layer pieces that don't need a database."""

from lpb_worker.ingestion.normalisers.brands import (
    _is_sales_rep_tag,
    _slugify,
    _strip_territory_paren,
    derive_brand_name,
)
from lpb_worker.ingestion.normalisers.codes import resolve_duplicate_code_categories


# ----- brand deriver -----

def test_sales_rep_only_tag_detected():
    assert _is_sales_rep_tag("GS ( L FB JD IV )")
    assert _is_sales_rep_tag("FB ( L GS JD IV )")
    assert _is_sales_rep_tag("L GS FB JD IV")


def test_real_brand_header_not_misclassified():
    assert not _is_sales_rep_tag("GLENDALOUGH WILD BOTANICAL GIN GS ( L FB JD IV )")
    assert not _is_sales_rep_tag("ELF BUTTERSCOTCH WHISKEY JD ( L GS FB IV )")


def test_strip_territory_paren():
    assert _strip_territory_paren("FOO BAR ( L GS )") == "FOO BAR"
    assert _strip_territory_paren("FOO BAR") == "FOO BAR"


def test_slugify():
    assert _slugify("Admiral Nel") == "admiral-nel"
    assert _slugify("Makers Mark!") == "makers-mark"
    assert _slugify("  Foo   Bar ") == "foo-bar"


def test_derive_brand_from_description_only():
    assert derive_brand_name("ADMIRAL NEL SPICED") == "ADMIRAL NEL"
    assert derive_brand_name("MAKERS MARK CASK STRENGTH") == "MAKERS MARK"


def test_derive_brand_stops_at_size_or_digit():
    # 1.75L is a size; should not pollute the brand name
    assert derive_brand_name("BASIL HAYDEN 1.75L") == "BASIL HAYDEN"


def test_derive_brand_prefers_useful_brand_header():
    assert derive_brand_name(
        description="WILD BOTANICAL GIN",
        brand_header="GLENDALOUGH WILD BOTANICAL GIN GS ( L FB JD IV )",
    ) == "GLENDALOUGH WILD"


def test_derive_brand_falls_back_when_brand_header_is_sales_rep():
    assert derive_brand_name(
        description="JOHN DOE WHISKEY",
        brand_header="GS ( L FB JD IV )",
    ) == "JOHN DOE"


def test_derive_brand_returns_none_when_empty():
    assert derive_brand_name(None) is None
    assert derive_brand_name("") is None
    assert derive_brand_name("123 456") is None


# ----- duplicate-code reconciler -----

def test_majority_wins():
    rows = [
        {"code": "0050840", "category_id": "gin"},
        {"code": "0050840", "category_id": "gin"},
        {"code": "0050840", "category_id": "irish"},
    ]
    assert resolve_duplicate_code_categories(rows) == {"0050840": "gin"}


def test_tie_broken_by_sort_order():
    rows = [
        {"code": "x", "category_id": "a"},
        {"code": "x", "category_id": "b"},
    ]
    res = resolve_duplicate_code_categories(
        rows, sort_order_by_category_id={"a": 200, "b": 100}
    )
    # Tied 1-1; lower sort_order wins -> b
    assert res == {"x": "b"}


def test_unresolved_categories_ignored():
    rows = [
        {"code": "x", "category_id": None},
        {"code": "x", "category_id": "gin"},
    ]
    assert resolve_duplicate_code_categories(rows) == {"x": "gin"}


def test_all_unresolved_returns_none():
    rows = [
        {"code": "x", "category_id": None},
        {"code": "x", "category_id": None},
    ]
    assert resolve_duplicate_code_categories(rows) == {"x": None}
