"""Combos section.

Layout (pages 15-23 in May 2026 book):
  Header: ABG MAY 2026 COMBOS
  Subheader: WINES, SPIRITS, or NON ALCOHOL
  Column header: CATEGORY SKU ITEM CONTAINS FRONT LINE
  Example line as flattened by pdfplumber:
    WINES 0872045 AUSTIN CAB/CHARD 2CS Austin Cabernet/Chardonnay 2cs ... $ 2 65.00

Heuristic for ITEM vs CONTAINS:
  - After the SKU we keep consuming tokens that are entirely UPPERCASE
    (or digit/punctuation) as part of ITEM. The first token containing a
    lowercase letter is where CONTAINS begins.

Price quirk:
  pdfplumber renders prices as `$ 1 50.54` (leading digit space-separated) or
  `$ 1 ,200.00` (with comma). normalize_combo_price collapses both.
"""

import re

CATEGORIES = {"WINES", "SPIRITS", "NON ALCOHOL"}

# Leading anchor + price tail. Price is either a real amount or "$ -" (TBD).
HEAD_RE = re.compile(r"^(WINES|SPIRITS|NON ALCOHOL)\s+(\d{7})\s+(.+?)\s+"
                     r"\$\s*([\d,\s]+\.\d{2}|-)\s*$")
UPPER_TOKEN_RE = re.compile(r"^[A-Z0-9/&\-#.,'+]+$")


def normalize_combo_price(raw):
    """`$ 2 65.00` -> 265.00 ; `$ 1 ,200.00` -> 1200.00 ; `$ 7 99.00` -> 799.00.
    Returns None when the source price is "-" (TBD)."""
    if raw is None or raw.strip() in ("-", ""):
        return None
    cleaned = re.sub(r"[\s,]", "", raw)
    try:
        return float(cleaned)
    except ValueError:
        return None


def split_item_and_contains(body_tokens):
    """body_tokens is the list of whitespace-split tokens after the SKU and
    before the price. Return (item_code, contains)."""
    item_parts = []
    i = 0
    while i < len(body_tokens) and UPPER_TOKEN_RE.match(body_tokens[i]):
        item_parts.append(body_tokens[i])
        i += 1
    item_code = " ".join(item_parts) if item_parts else None
    contains = " ".join(body_tokens[i:]).strip()
    return item_code, contains


def parse_combos(pages, source):
    rows = []
    current_subcategory = None
    for page in pages:
        text = page.extract_text() or ""
        for raw in text.split("\n"):
            line = raw.strip()
            if not line:
                continue
            up = line.upper()
            if up in CATEGORIES:
                current_subcategory = up
                continue
            m = HEAD_RE.match(line)
            if not m:
                continue
            body = m.group(3).strip()
            item_code, contains = split_item_and_contains(body.split())
            rows.append({
                "source": source,
                "section": "Combos",
                "subcategory": current_subcategory or m.group(1),
                "sku": m.group(2),
                "item_code": item_code,
                "contains": contains,
                "front_line_price": normalize_combo_price(m.group(4)),
                "front_line_raw": m.group(4),
                "page": page.page_number,
            })
    return rows
