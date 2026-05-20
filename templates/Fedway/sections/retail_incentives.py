"""Fedway Retail Incentives parser.

Format: Free-form text with brand names, deal numbers in parens, and tier pricing.
  BOMBAY SAPPHIRE LARGE SIZES INCLUDES # (239)
  3 Cs/$24, 8 Cs/$160, 15 Cs/$450

This is analogous to Allied's "Retail Incentives for" (producer pages) section.
We extract the deal number, description, and tier pricing.
"""

from __future__ import annotations

import re

_DEAL_NUM_RE = re.compile(r"\((\d{1,4})\)\s*$")
_TIER_RE = re.compile(r"(\d+)\s*(Cs?|Bt?|Cases?|Bottles?)/\$?([\d,.]+)", re.IGNORECASE)


def parse_retail_incentives(pages: list, source: str) -> list[dict]:
    """Parse Retail Incentives pages into deal entries."""
    rows = []

    for page in pages:
        text = page.extract_text() or ""
        lines = text.split("\n")

        i = 0
        while i < len(lines):
            line = lines[i].strip()
            i += 1

            if not line or line.startswith("Order Phone"):
                continue

            # Look for a deal number at end of line
            m = _DEAL_NUM_RE.search(line)
            if not m:
                continue

            deal_number = m.group(1)
            description = line[: m.start()].strip()

            # Collect tier lines that follow
            tiers = []
            while i < len(lines):
                next_line = lines[i].strip()
                # If next line has tiers (e.g. "3 Cs/$24, 8 Cs/$160")
                tier_matches = _TIER_RE.findall(next_line)
                if tier_matches:
                    for qty_str, unit, amount_str in tier_matches:
                        tiers.append({
                            "qty": int(qty_str),
                            "unit": "CS" if unit[0].upper() == "C" else "BT",
                            "amount": amount_str.replace(",", ""),
                        })
                    i += 1
                # If next line continues the description (no deal number, no tiers)
                elif not _DEAL_NUM_RE.search(next_line) and not _TIER_RE.search(next_line):
                    if next_line and not next_line.startswith("Order Phone"):
                        description += " " + next_line
                        i += 1
                    else:
                        break
                else:
                    break

            rows.append({
                "deal_number": deal_number,
                "description": description,
                "tiers": tiers,
                "page": page.page_number,
                "source": source,
            })

    return rows
