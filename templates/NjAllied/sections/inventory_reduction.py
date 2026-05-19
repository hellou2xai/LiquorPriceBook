"""Inventory Reduction section.

Layout (pages 2-7 in May 2026 book):
  Header banner: INVENTORY REDUCTION MAY 2026 / LAST CALL... / LIMITED QUANTITIES
  Subheader: SPIRITS or WINES (subcategory)
  Column header:
    PRODUCT  DESCRIPTION  SIZE  PACK  ORIGINAL_CASE  ORIGINAL_BTL  BEST_CASE  BEST_BTL  CASE_SAVE  BTL_SAVE
  Rows:
    7-digit-code  DESCRIPTION...  SIZE  PACK  $orig_case  $orig_btl  $best_case  $best_btl  $case_save  $btl_save
"""

import re

from ..utils import is_product_code, parse_money

ROW_RE = re.compile(
    r"^(\d{7})\s+(.+?)\s+(\S+)\s+(\d+)\s+"
    r"\$([\d,]+\.\d{2})\s+\$([\d,]+\.\d{2})\s+"
    r"\$([\d,]+\.\d{2})\s+\$([\d,]+\.\d{2})\s+"
    r"\$([\d,]+\.\d{2})\s+\$([\d,]+\.\d{2})\s*$"
)


def parse_inventory_reduction(pages, source):
    rows = []
    current_subcategory = None
    for page in pages:
        text = page.extract_text() or ""
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line in ("SPIRITS", "WINES", "NON ALCOHOL"):
                current_subcategory = line
                continue
            m = ROW_RE.match(line)
            if not m:
                continue
            rows.append({
                "source": source,
                "section": "InventoryReduction",
                "subcategory": current_subcategory,
                "product_code": m.group(1),
                "description": m.group(2).strip(),
                "size": m.group(3),
                "pack": int(m.group(4)),
                "original_case": parse_money(m.group(5)),
                "original_bottle": parse_money(m.group(6)),
                "best_case": parse_money(m.group(7)),
                "best_bottle": parse_money(m.group(8)),
                "case_save": parse_money(m.group(9)),
                "bottle_save": parse_money(m.group(10)),
                "page": page.page_number,
            })
    return rows
