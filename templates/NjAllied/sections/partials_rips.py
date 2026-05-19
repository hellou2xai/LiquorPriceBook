"""Partials / Web RIPs section.

Layout (pages 10-11 in May 2026 book):
  Header: MAY 2026 PARTIALS/WEB RIPS / **WEB SPECIALS IN GREEN**
  Column header: DESCRIPTION SIZE START_DATE END_DATE RIP
  Example rows:
    BASIL HAYDEN 1.75L 5/1/2026 5/5/2026 1CASE=$36
    CSJ CHARD CARNR21 6P 750ML 5/1/2026 5/12/2026 1CASE=$36
        2CASES=$90              <- a tier-only continuation line
    KNOB CREEK BBN & RYE 1.75L 5/1/2026 5/5/2026 1CASE=$30
        3CASES=$180

Tier-only continuation lines (no dates) belong to the preceding item.
"""

import re

from ..utils import parse_date

# Full row: DESCRIPTION  SIZE  M/D/YYYY  M/D/YYYY  TIER=$AMOUNT
# Description may include spaces; size may be 750ML, 1.75L, LITER, 19.5L, etc.
FULL_RE = re.compile(
    r"^(.+?)\s+(\S+)\s+(\d{1,2}/\d{1,2}/\d{4})\s+(\d{1,2}/\d{1,2}/\d{4})\s+(.+)$"
)
TIER_ONLY_RE = re.compile(r"^(\d+\s*CASES?)\s*=\s*\$([\d,]+)$", re.IGNORECASE)


def parse_partials_rips(pages, source):
    rows = []
    last_item = None
    for page in pages:
        text = page.extract_text() or ""
        for raw in text.split("\n"):
            line = raw.strip()
            if not line:
                continue
            # Skip headers
            if "PARTIALS/WEB RIPS" in line or "WEB SPECIALS" in line \
                or line.startswith("DESCRIPTION"):
                continue

            tonly = TIER_ONLY_RE.match(line)
            if tonly and last_item is not None:
                rows.append({
                    **last_item,
                    "tier": tonly.group(1).replace(" ", "").upper(),
                    "rip_price": float(tonly.group(2).replace(",", "")),
                    "rip_raw": line,
                })
                continue

            m = FULL_RE.match(line)
            if not m:
                continue
            description = m.group(1).strip()
            size = m.group(2)
            start = parse_date(m.group(3))
            end = parse_date(m.group(4))
            tier_raw = m.group(5).strip()
            tier_m = re.match(r"(\d+\s*CASES?)\s*=\s*\$([\d,]+)", tier_raw, re.IGNORECASE)
            tier = tier_m.group(1).replace(" ", "").upper() if tier_m else None
            rip_price = float(tier_m.group(2).replace(",", "")) if tier_m else None

            base = {
                "source": source,
                "section": "Partials_RIPs",
                "description": description,
                "size": size,
                "start_date": start,
                "end_date": end,
                "page": page.page_number,
            }
            rows.append({
                **base,
                "tier": tier,
                "rip_price": rip_price,
                "rip_raw": tier_raw,
            })
            last_item = base
    return rows
