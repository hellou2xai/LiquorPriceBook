"""New Items section.

Layout (May 2026 book pages 8-9, April 2026 book pages 9-11):
  Header: ABG <MONTH> 2026 NEW ITEMS
  Column header: CATEGORY BRAND DESCRIPTION SIZE SKU PACK ABG

Categories observed across books:
  WINE, WINES, SPIRITS, SPARKLING, NON ALC, NON ALCOHOL, THCB, GLASS

Examples:
  WINE CHLOE Chloe In Bloom Pinot Grigio Sauvignon Blanc 2025 750ML 7531640 12 IV
  WINES SPRITZ DEL CONTE Spritz Del Conte Classic 12Pk 250ML 7950371 12 ALL
  WINES MEZZACORONA 750ML 6764040 12 JD                      <-- no description
  SPIRITS ASTRAL TEQUILA Astral Blanco Tequila ... 50 ML 3600190 5 ALL
  GLASS RIEDEL Riedel Veloce Cabernet/Merlot Glass GLASS 1118340 6 ALL

Brand is one or more consecutive ALL-CAPS tokens after the category.
Description is everything between brand and size; size may be one token
("750ML") or two ("50 ML"/"1.5 L"/"16 OZ") or the literal "GLASS"/"CMB".
SKU is the 7-digit code; pack is the next int; ABG is the rest.
"""

import re

from ..utils import is_product_code

CATEGORY_RE = re.compile(
    r"^(WINE|WINES|SPIRITS|SPARKLING|NON ALCOHOL|NON ALC|THCB|GLASS)\s+(.+)$"
)
UPPER_TOKEN_RE = re.compile(r"^[A-Z0-9&/'.,\-#]+$")
SIZE_SINGLE_RE = re.compile(r"^\d*\.?\d+(?:ML|L|LIT|OZ)$", re.IGNORECASE)
SIZE_TWO_TOKEN_RE = re.compile(r"^\d*\.?\d+$")
SIZE_UNITS = {"ML", "L", "LIT", "OZ"}
SIZE_SPECIAL = {"GLASS", "CMB"}


def consume_brand(tokens):
    """Consume consecutive ALL-CAPS tokens as brand. Return (brand, remaining_tokens)."""
    brand_parts = []
    i = 0
    while i < len(tokens) and UPPER_TOKEN_RE.match(tokens[i]) \
            and not _is_size_token(tokens, i):
        brand_parts.append(tokens[i])
        i += 1
    return " ".join(brand_parts), tokens[i:]


def _is_size_token(tokens, i):
    """Did we just hit a size token? Brand consumption must stop there."""
    t = tokens[i]
    if SIZE_SINGLE_RE.match(t):
        return True
    if t.upper() in SIZE_SPECIAL:
        return True
    if t.upper() in SIZE_UNITS and i > 0 and SIZE_TWO_TOKEN_RE.match(tokens[i - 1]):
        return True
    return False


def extract_size(tokens, sku_idx):
    """Look backwards from sku_idx for the size token(s). Return (size, idx_before_size)."""
    if sku_idx == 0:
        return None, 0
    t_prev = tokens[sku_idx - 1]
    if SIZE_SINGLE_RE.match(t_prev) or t_prev.upper() in SIZE_SPECIAL:
        return t_prev, sku_idx - 1
    if sku_idx >= 2 and t_prev.upper() in SIZE_UNITS \
            and SIZE_TWO_TOKEN_RE.match(tokens[sku_idx - 2]):
        return f"{tokens[sku_idx - 2]} {t_prev}", sku_idx - 2
    return t_prev, sku_idx - 1


def parse_new_items(pages, source):
    rows = []
    for page in pages:
        text = page.extract_text() or ""
        for raw in text.split("\n"):
            line = raw.strip()
            if not line:
                continue
            m = CATEGORY_RE.match(line)
            if not m:
                continue
            category = m.group(1)
            tokens = m.group(2).split()

            # Locate SKU
            sku_idx = next(
                (i for i, t in enumerate(tokens) if is_product_code(t)), None)
            if sku_idx is None or sku_idx < 1:
                continue

            # Brand: leading all-caps tokens
            brand, after_brand = consume_brand(tokens)
            if not brand:
                continue
            brand_len = sku_idx - len(after_brand)  # how many tokens consumed for brand

            # Size: scan backward from SKU
            size, size_start_idx = extract_size(tokens, sku_idx)

            # Description: tokens between brand end and size start
            desc_tokens = tokens[brand_len:size_start_idx]
            description = " ".join(desc_tokens).strip()

            sku = tokens[sku_idx]
            after = tokens[sku_idx + 1:]
            if not after:
                continue
            try:
                pack = int(after[0])
            except ValueError:
                continue
            abg = " ".join(after[1:])
            rows.append({
                "source": source,
                "section": "NewItems",
                "category": category,
                "brand": brand,
                "description": description,
                "size": size,
                "sku": sku,
                "pack": pack,
                "abg": abg,
                "page": page.page_number,
            })
    return rows
