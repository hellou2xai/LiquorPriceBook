"""NjAllied orchestrator: detects sections and dispatches to per-section parsers."""

import re
from datetime import date
from pathlib import Path

import pdfplumber

from .config import SECTION_PATTERNS, ENABLED_SECTIONS
from .sections import (
    parse_inventory_reduction,
    parse_new_items,
    parse_partials_rips,
    parse_partials_pricing,
    parse_keg_list,
    parse_combos,
    parse_main_catalog,
)

MONTH_NAMES = {
    "JANUARY": 1, "FEBRUARY": 2, "MARCH": 3, "APRIL": 4, "MAY": 5, "JUNE": 6,
    "JULY": 7, "AUGUST": 8, "SEPTEMBER": 9, "OCTOBER": 10, "NOVEMBER": 11, "DECEMBER": 12,
}


def parse_book_period(pdf_path, pdf):
    """Identify the book's (year, month) from the PDF filename first,
    falling back to text on the first ~3 pages.

    Returns (year:int, month:int) or (None, None) if unknown.
    """
    stem = Path(pdf_path).stem
    # Filename pattern "YYYY-MM Price Book"
    m = re.match(r"(\d{4})-(\d{2})\b", stem)
    if m:
        return int(m.group(1)), int(m.group(2))
    # Fallback: scan first few pages for "MAY 2026" / "MAY, 2026" patterns
    for i in range(min(3, len(pdf.pages))):
        text = (pdf.pages[i].extract_text() or "").upper()
        m = re.search(r"\b(" + "|".join(MONTH_NAMES) + r")[, ]+(\d{4})\b", text)
        if m:
            return int(m.group(2)), MONTH_NAMES[m.group(1)]
    return None, None

SECTION_HANDLERS = {
    "inventory_reduction": parse_inventory_reduction,
    "new_items":           parse_new_items,
    "partials_rips":       parse_partials_rips,
    "partials_pricing":    parse_partials_pricing,
    "keg_list":            parse_keg_list,
    "combos":              parse_combos,
    "main_catalog":        parse_main_catalog,
}


def classify_pages(pdf):
    """Walk all pages and assign each one to a section name."""
    page_section = []
    for page in pdf.pages:
        text = page.extract_text() or ""
        head = "\n".join(text.split("\n")[:6])
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


def scrape_pdf(pdf_path, source_name=None):
    """Scrape a Price Book PDF. Returns (results, diagnostics) where results is
    dict[section_name -> list[dict]] and every row carries book_year, book_month,
    book_label, source so downstream consumers (DB, app) can slice by edition."""
    pdf_path = Path(pdf_path)
    source = source_name or pdf_path.stem
    results = {name: [] for name in ENABLED_SECTIONS}
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
            if section not in ENABLED_SECTIONS:
                diagnostics["skipped"].append({"section": section,
                                               "pages": f"{page_indices[0]+1}-{page_indices[-1]+1}"})
                continue
            handler = SECTION_HANDLERS[section]
            pages = [pdf.pages[i] for i in page_indices]
            rows = handler(pages, source)
            # Tag every row with the book edition
            for r in rows:
                r["book_year"] = year
                r["book_month"] = month
                r["book_label"] = book_label
            results[section].extend(rows)

    return results, diagnostics
