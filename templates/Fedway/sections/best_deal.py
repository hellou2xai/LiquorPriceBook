"""Fedway Best Deal / All Buy-Ins parser.

Format: Two-column layout with lines like:
  BROWNE FAMILY VYDS SB/PG GIGI GARDEN - 1 LT (000433050) 12 $-12.00 MAY
  ITEM_NAME - SIZE (ITEM_CODE) PACK $RIP_AMOUNT BUY_MONTH
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

_LINE_RE = re.compile(
    r"(.+?)\s*-\s*"               # description (before dash-size)
    r"([\d.]+\s*(?:ML|LT|OZ|L))"  # size
    r"\s*\((\d+)\)"               # item code in parens
    r"\s+(\d+)"                    # pack
    r"\s+\$?([-\d,.]+)"           # RIP amount (can be negative)
    r"\s+(\w+)",                   # buy month
    re.IGNORECASE,
)


def parse_best_deal(pages: list, source: str) -> list[dict]:
    """Parse Best Deal / All Buy-Ins pages."""
    rows = []

    for page in pages:
        text = page.extract_text() or ""
        for line in text.split("\n"):
            line = line.strip()
            if not line or line.startswith("Order Phone") or line.startswith("ITEM"):
                continue
            if line in ("VAR",):
                continue

            m = _LINE_RE.search(line)
            if m:
                description = m.group(1).strip()
                size = m.group(2).strip()
                code = m.group(3).strip()
                pack_str = m.group(4).strip()
                rip_str = m.group(5).strip().replace(",", "")
                buy_month = m.group(6).strip()

                try:
                    rip_amount = Decimal(rip_str)
                except (InvalidOperation, ValueError):
                    rip_amount = None

                try:
                    pack = int(pack_str)
                except ValueError:
                    pack = None

                rows.append({
                    "code": code,
                    "description": description,
                    "size": size,
                    "pack": pack,
                    "rip_amount": rip_amount,
                    "buy_month": buy_month,
                    "page": page.page_number,
                    "source": source,
                })

    return rows
