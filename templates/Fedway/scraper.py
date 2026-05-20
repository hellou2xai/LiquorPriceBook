"""Fedway orchestrator: detects sections and dispatches to per-section parsers."""

import re
from pathlib import Path

import pdfplumber

from .config import (
    CATALOG_FORMAT_SECTIONS,
    ENABLED_SECTIONS,
    SECTION_PATTERNS,
)
from .sections import (
    parse_best_deal,
    parse_combo_packs,
    parse_craft_distilled,
    parse_main_catalog,
    parse_partial_month,
    parse_retail_incentives,
)

MONTH_NAMES = {
    "JANUARY": 1, "FEBRUARY": 2, "MARCH": 3, "APRIL": 4, "MAY": 5, "JUNE": 6,
    "JULY": 7, "AUGUST": 8, "SEPTEMBER": 9, "OCTOBER": 10, "NOVEMBER": 11, "DECEMBER": 12,
}


def parse_book_period(pdf_path, pdf):
    """Identify the book's (year, month) from the PDF filename first,
    falling back to text on the first ~10 pages.

    Fedway filenames: "Fedway+Pricebook+Full+June+2026.pdf"
    """
    stem = Path(pdf_path).stem
    # Pattern: "YYYY-MM"
    m = re.match(r"(\d{4})-(\d{2})\b", stem)
    if m:
        return int(m.group(1)), int(m.group(2))
    # Pattern: "Month+YYYY" in filename
    for month_name, month_num in MONTH_NAMES.items():
        if month_name.lower() in stem.lower() or month_name.capitalize() in stem:
            year_m = re.search(r"(\d{4})", stem)
            if year_m:
                return int(year_m.group(1)), month_num
    # Fallback: scan pages for "Fedway Pricebook - June 2026" pattern
    for i in range(min(10, len(pdf.pages))):
        text = (pdf.pages[i].extract_text() or "").upper()
        m = re.search(r"\b(" + "|".join(MONTH_NAMES) + r")[, ]+(\d{4})\b", text)
        if m:
            return int(m.group(2)), MONTH_NAMES[m.group(1)]
    return None, None


def classify_pages(pdf):
    """Walk all pages and assign each one to a section name."""
    page_section = []
    for page in pdf.pages:
        text = page.extract_text() or ""
        head = "\n".join(text.split("\n")[:4])
        section = "unknown"
        for name, pat in SECTION_PATTERNS:
            if re.search(pat, head):
                section = name
                break
        page_section.append(section)
    return page_section


def group_runs(page_section):
    """Group consecutive same-section pages into runs.
    Returns list of (section_name, [page_index, ...])."""
    runs = []
    for i, sec in enumerate(page_section):
        if runs and runs[-1][0] == sec:
            runs[-1][1].append(i)
        else:
            runs.append((sec, [i]))
    return runs


# Map raw section names to handler functions
SECTION_HANDLERS = {
    "best_deal": parse_best_deal,
    "partial_month": parse_partial_month,
    "retail_incentives": parse_retail_incentives,
    "combo_packs": parse_combo_packs,
    "craft_distilled": parse_craft_distilled,
    "featured_sake": parse_craft_distilled,  # Same tabular format
}

# Map section name to its display name for the catalog
_CATALOG_SECTION_LABELS = {
    "spirits": "SPIRITS",
    "wine": "WINE",
    "cans_cocktails": "CANS AND COCKTAILS",
    "malt_products": "MALT PRODUCTS",
    "non_alcoholic": "NON ALCOHOLIC",
    "mixers": "MIXERS AND MORE",
}


def scrape_pdf(pdf_path, source_name=None):
    """Scrape a Fedway Price Book PDF.

    Returns (results, diagnostics) where results has section keys matching
    the pipeline's expectations:
      - main_catalog: products from all catalog sections (Spirits, Wine, etc.)
      - partials_rips: from Partial Month section
      - combos: from Combo Packs section
      - retail_incentives: RIP deal descriptions (informational)
    """
    pdf_path = Path(pdf_path)
    source = source_name or pdf_path.stem
    results = {
        "main_catalog": [],
        "partials_rips": [],
        "combos": [],
        "inventory_reduction": [],
        "partials_pricing": [],
        "keg_list": [],
        "new_items": [],
    }
    diagnostics = {"sections_detected": [], "skipped": []}

    with pdfplumber.open(pdf_path) as pdf:
        year, month = parse_book_period(pdf_path, pdf)
        book_label = f"{year:04d}-{month:02d}" if year and month else source
        diagnostics["book_year"] = year
        diagnostics["book_month"] = month
        diagnostics["book_label"] = book_label
        diagnostics["source"] = source

        page_section = classify_pages(pdf)
        runs = group_runs(page_section)
        diagnostics["sections_detected"] = [
            {"section": s, "pages": f"{p[0]+1}-{p[-1]+1}", "count": len(p)}
            for s, p in runs
        ]

        for section, page_indices in runs:
            pages = [pdf.pages[i] for i in page_indices]

            if section in CATALOG_FORMAT_SECTIONS:
                # These are all main catalog format (3-column product listings)
                label = _CATALOG_SECTION_LABELS.get(section, section.upper())
                rows = parse_main_catalog(pages, source, section_name=label)
                for r in rows:
                    r["book_year"] = year
                    r["book_month"] = month
                    r["book_label"] = book_label
                results["main_catalog"].extend(rows)

            elif section == "combo_packs":
                rows = parse_combo_packs(pages, source)
                for r in rows:
                    r["book_year"] = year
                    r["book_month"] = month
                    r["book_label"] = book_label
                results["combos"].extend(rows)

            elif section == "partial_month":
                rows = parse_partial_month(pages, source)
                for r in rows:
                    r["book_year"] = year
                    r["book_month"] = month
                    r["book_label"] = book_label
                results["partials_rips"].extend(rows)

            elif section == "craft_distilled" or section == "featured_sake":
                rows = parse_craft_distilled(pages, source)
                for r in rows:
                    r["book_year"] = year
                    r["book_month"] = month
                    r["book_label"] = book_label
                results["main_catalog"].extend(rows)

            elif section in ("best_deal", "retail_incentives"):
                # Informational — extract but don't push to main_catalog
                handler = SECTION_HANDLERS.get(section)
                if handler:
                    rows = handler(pages, source)
                    for r in rows:
                        r["book_year"] = year
                        r["book_month"] = month
                        r["book_label"] = book_label
                    diagnostics[f"{section}_rows"] = len(rows)

            elif section not in ENABLED_SECTIONS and section != "unknown":
                diagnostics["skipped"].append({
                    "section": section,
                    "pages": f"{page_indices[0]+1}-{page_indices[-1]+1}",
                })

    return results, diagnostics
