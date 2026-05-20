"""Fedway Combo Packs parser.

Combo pages use the same 3-column layout as the main catalog but with
COMBO-specific entries. We reuse the main catalog parser with section_name="COMBOS".
"""

from __future__ import annotations

from .main_catalog import parse_main_catalog


def parse_combo_packs(pages: list, source: str) -> list[dict]:
    """Parse Combo Packs pages."""
    return parse_main_catalog(pages, source, section_name="COMBOS")
