"""Keg List section.

Layout (page 14 in May 2026 book):
  Header: Keg List MAY 2026 / preamble lines about 750ml comparison
  Column header:
    Type  ABG_CODE  Long_Description  Size  Best_KEG_Price  750ml_Value_Reg  Best_Btl_Per_Ounce  In_Stock
  Example row:
    Deposit 7570010 13 Celsius Sauvignon Blanc Keg 19.5L $ 209.00 $ 8.04 $ 10.08 $ 0.31
    Disposable 3360610 3 Pears Pinot Grigio California 2023 19.5L $ 220.00 $ 8.46 $ 10.61 $ 0.33 x
"""

import re

from ..utils import parse_money

# Type tokens we've seen
TYPE_RE = re.compile(r"^(Deposit|Disposable)\s+(\d{7})\s+(.+?)\s+(\S+)\s+"
                     r"\$\s*([\d,]+\.\d{2})\s+"
                     r"\$\s*([\d,]+\.\d{2})\s+"
                     r"\$\s*([\d,]+\.\d{2})\s+"
                     r"\$\s*([\d,]+\.\d{2})\s*(x?)\s*$")


def parse_keg_list(pages, source):
    rows = []
    for page in pages:
        text = page.extract_text() or ""
        for raw in text.split("\n"):
            line = raw.strip()
            if not line:
                continue
            m = TYPE_RE.match(line)
            if not m:
                continue
            rows.append({
                "source": source,
                "section": "KegList",
                "type": m.group(1),
                "abg_code": m.group(2),
                "description": m.group(3).strip(),
                "size": m.group(4),
                "best_keg_price": parse_money(m.group(5)),
                "value_per_750ml": parse_money(m.group(6)),
                "best_btl_reg": parse_money(m.group(7)),
                "per_ounce_estimate": parse_money(m.group(8)),
                "in_stock": m.group(9).lower() == "x",
                "page": page.page_number,
            })
    return rows
