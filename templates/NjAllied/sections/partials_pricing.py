"""Partials / Web PRICING section.

Layout (pages 12-13 in May 2026 book):
  Header: MAY 2026 PARTIALS/WEB PRICING / **WEB SPECIALS IN GREEN**
  Column header: DESCRIPTION PRODUCT# START_DATE END_DATE BEST_CASE BEST_BTL
  Example:
    GLENMO 12YEAR 4PK 165020 5/12/2026 5/19/2026 $288.36/4CASES $72.09
    MCMANIS CAB SAUV 23 8662640 5/12/2026 5/31/2026 $87.96/5CASES $7.33
"""

import re

from ..utils import parse_date, parse_money

# Case price may or may not carry a /<N>CASES tier suffix:
#   "$87.96/5CASES $7.33"  or  "$59.91 $4.99"
ROW_RE = re.compile(
    r"^(.+?)\s+(\d{6,7})\s+"
    r"(\d{1,2}/\d{1,2}/\d{4})\s+(\d{1,2}/\d{1,2}/\d{4})\s+"
    r"\$([\d,]+\.\d{2})(?:/(\d+\s*CASES?))?\s+\$([\d,]+\.\d{2})\s*$",
    re.IGNORECASE,
)


def parse_partials_pricing(pages, source):
    rows = []
    for page in pages:
        text = page.extract_text() or ""
        for raw in text.split("\n"):
            line = raw.strip()
            if not line:
                continue
            if "PARTIALS/WEB PRICING" in line or "WEB SPECIALS" in line \
                or line.startswith("DESCRIPTION"):
                continue
            m = ROW_RE.match(line)
            if not m:
                continue
            tier = m.group(6)
            rows.append({
                "source": source,
                "section": "Partials_Pricing",
                "description": m.group(1).strip(),
                "product_number": m.group(2),
                "start_date": parse_date(m.group(3)),
                "end_date": parse_date(m.group(4)),
                "best_case_price": parse_money(m.group(5)),
                "best_case_tier": tier.replace(" ", "").upper() if tier else None,
                "best_bottle_price": parse_money(m.group(7)),
                "page": page.page_number,
            })
    return rows
