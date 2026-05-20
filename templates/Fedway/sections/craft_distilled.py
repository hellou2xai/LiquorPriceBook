"""Fedway Craft Distilled / Featured Sake parser.

Format: Two-month comparison table (simpler than main catalog)
  ITEM (ALPHA)  PACK  QTY  CASE  BOTTLE  RIP  QTY  CASE  BOTTLE  RIP  BUY
  BUCKHORN HONEY WHISKEY - 750 ML (000277540) 12 1 $193.08 $16.09 5C$150 1 $193.08 $16.09 5C$150

Each line has: description - size (code) pack [month1_data] [month2_data]
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from .main_catalog import _resolve_fedway_category

_LINE_RE = re.compile(
    r"(.+?)\s*-\s*"                # description
    r"([\d.]+\s*(?:ML|LT|OZ|L))"  # size
    r"\s*\((\d+)\)"                # code in parens
    r"\s+(\d+)"                    # pack
    r"\s+(.*)",                     # rest (pricing data)
    re.IGNORECASE,
)

_PRICE_RE = re.compile(r"\$([\d,.]+)")
_BUY_RE = re.compile(r"(\d+[CB]\\?\$\d+)")


def parse_craft_distilled(pages: list, source: str) -> list[dict]:
    """Parse Craft Distilled and Featured Sake pages."""
    rows = []
    current_category = None

    for page in pages:
        text = page.extract_text() or ""
        for line in text.split("\n"):
            line = line.strip()
            if not line or line.startswith("Order Phone"):
                continue
            if line.startswith("ITEM") or line.startswith("2026/"):
                continue

            # Category headers (all caps, no digits, no parens)
            if (
                line.isupper()
                and "(" not in line
                and not re.search(r"\d", line)
                and len(line) < 40
            ):
                current_category = line
                continue

            m = _LINE_RE.match(line)
            if not m:
                continue

            description = m.group(1).strip()
            size = m.group(2).strip()
            code = m.group(3).strip()
            pack_str = m.group(4).strip()
            rest = m.group(5).strip()

            try:
                pack = int(pack_str)
            except ValueError:
                pack = None

            # Strip BUY deal amounts before extracting prices
            # BUY deals: "3C\$90", "6C$240" — these are NOT case/bottle prices
            rest_clean = _BUY_RE.sub("", rest)
            prices = _PRICE_RE.findall(rest_clean)
            case_cost = None
            btl_cost = None
            if len(prices) >= 2:
                try:
                    case_cost = Decimal(prices[-2].replace(",", ""))
                    btl_cost = Decimal(prices[-1].replace(",", ""))
                except (InvalidOperation, ValueError):
                    pass
            elif len(prices) == 1:
                try:
                    btl_cost = Decimal(prices[0].replace(",", ""))
                except (InvalidOperation, ValueError):
                    pass

            # Extract buy deal
            buy_m = _BUY_RE.search(rest)
            buy_deal = buy_m.group(1).replace("\\", "") if buy_m else None

            rows.append({
                "code": code,
                "sub_brand": description,
                "brand_header": description.split()[0] if description else None,
                "category": _resolve_fedway_category(current_category or "CRAFT DISTILLED", None, None) or current_category or "Cordials",
                "size": size,
                "pack": pack,
                "case_cost": case_cost,
                "btl_cost": btl_cost,
                "best_buy": buy_deal,
                "page": page.page_number,
                "source": source,
            })

    return rows
