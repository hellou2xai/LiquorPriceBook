"""Fedway Partial Month RIPs parser.

Format:
  CASAMIGOS RTS 750ML JUNE 1-2
  2026/06/01 2026/06/02 1C/$5, 2C/$40

Lines alternate: description line, then date+deals line.
"""

from __future__ import annotations

import re
from datetime import date

_DATE_RE = re.compile(r"(\d{4}/\d{2}/\d{2})\s+(\d{4}/\d{2}/\d{2})\s+(.*)")
_DEAL_RE = re.compile(r"(\d+[CB]/\$[\d,.]+)")


def _parse_date(s: str) -> date | None:
    """Parse 'YYYY/MM/DD' into a date."""
    try:
        parts = s.split("/")
        return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        return None


def parse_partial_month(pages: list, source: str) -> list[dict]:
    """Parse Partial Month RIPs pages."""
    rows = []
    pending_desc = None

    for page in pages:
        text = page.extract_text() or ""
        for line in text.split("\n"):
            line = line.strip()
            if not line or line.startswith("Order Phone"):
                continue
            if line.startswith("PARTIAL MONTH") or line.startswith("START DATE"):
                continue
            if line.startswith("**"):
                continue
            # Skip footer lines
            if re.match(r"^\d+\s+Fedway", line):
                continue

            m = _DATE_RE.match(line)
            if m:
                start = _parse_date(m.group(1))
                end = _parse_date(m.group(2))
                deals_str = m.group(3).strip()
                deals = _DEAL_RE.findall(deals_str)

                if pending_desc and start and end:
                    rows.append({
                        "description": pending_desc,
                        "start_date": start,
                        "end_date": end,
                        "rip_deals": ", ".join(deals) if deals else deals_str,
                        "page": page.page_number,
                        "source": source,
                    })
                pending_desc = None
            else:
                # This is a description line
                pending_desc = line

    return rows
