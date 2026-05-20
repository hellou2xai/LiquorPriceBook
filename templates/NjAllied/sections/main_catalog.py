"""Main Catalog section (pages 75-256 in May 2026 book).

Each page has a category banner at the top (e.g. BLENDED WHISKEY, VODKA, WINES OF CALIFORNIA)
and three side-by-side columns. Each column has 8 fields:

    Code No.  Size  Pk  P.O.Cost  Case Cost  Btl Cost  Best Buy  Best Rip

Between product rows there are brand-header lines such as
    "ELF BUTTERSCOTCH WHISKEY JD ( L GS FB IV )"
which carry the brand name and (in parentheses) the territory/division codes.

Strategy:
  1. Use extract_words() to get word positions.
  2. Cluster words into rows by y-coordinate (within ~3pt).
  3. Within each row, split words into 3 lanes by x-coordinate.
  4. For each lane:
       - If first word in the lane is a 7-digit code -> emit a product row,
         snapping subsequent words to the 8 field x-bands.
       - Otherwise -> accumulate as the current brand header for that lane.
  5. The most recent category banner (page-wide centered text near the top)
     is attached to each product row.

Notes:
  - "Best Rip" column may contain non-money tokens like "50.00/10C" or "200.00/5C"
    (case-tier RIP offer). We keep that as raw text.
  - Some rows have a "$XX.XX ON nCS" rip annotation occupying multiple x-positions;
    we capture it best-effort into best_rip.
"""

import re
from collections import defaultdict

from ..config import CATALOG_LANES_X, CATALOG_COLUMN_ANCHORS, CATALOG_SNAP_TOL
from ..utils import is_product_code

ROW_Y_TOL = 2.5   # words within this y-difference are on the same row
PAGE_HEADER_Y = 50  # skip the column header rows above this y
PAGE_FOOTER_Y = 770


def cluster_rows(words):
    """Group words into rows by y-coordinate. Returns list of (y_mid, [words])."""
    if not words:
        return []
    sorted_w = sorted(words, key=lambda w: (w["top"], w["x0"]))
    clusters = []
    for w in sorted_w:
        placed = False
        for c in clusters:
            if abs(w["top"] - c["y"]) <= ROW_Y_TOL:
                c["words"].append(w)
                c["y"] = (c["y"] * (len(c["words"]) - 1) + w["top"]) / len(c["words"])
                placed = True
                break
        if not placed:
            clusters.append({"y": w["top"], "words": [w]})
    clusters.sort(key=lambda c: c["y"])
    return clusters


def lane_of(x):
    for i, (lo, hi) in enumerate(CATALOG_LANES_X):
        if lo <= x < hi:
            return i
    return None


def field_of_word(word, lane):
    """Snap a word to its closest field anchor in the given lane.
    Left-aligned fields use word's x0; right-aligned fields use word's x1."""
    best = None
    best_dist = None
    for name, kind, target_x in CATALOG_COLUMN_ANCHORS[lane]:
        x = word["x0"] if kind == "L" else word["x1"]
        d = abs(x - target_x)
        if best_dist is None or d < best_dist:
            best_dist = d
            best = name
    if best_dist > CATALOG_SNAP_TOL:
        return None
    return best


def split_lane(row_words, lane):
    lo, hi = CATALOG_LANES_X[lane]
    return [w for w in row_words if lo <= w["x0"] < hi]


def get_category(page):
    """Extract the centered category header at the top of the page.

    Headers appear like 'BLENDED WHISKEY' near y=12-18 in either the left
    third (for odd pages: ELIZABETH ... Allied Beverage Group CATEGORY) or
    the right side. They are all caps."""
    words = page.extract_words()
    top_words = [w for w in words if w["top"] < 25]
    # Drop the banner pieces we don't want
    banned = {"ELIZABETH", "(800)", "272-1323", "272�1323", "Allied", "Beverage", "Group"}
    cat_words = [w for w in top_words if w["text"] not in banned]
    if not cat_words:
        return None
    # The category text is the contiguous run that's all caps (and not the phone).
    cat_words.sort(key=lambda w: w["x0"])
    pieces = []
    for w in cat_words:
        t = w["text"].strip()
        if not t:
            continue
        # all-uppercase letters/numbers/spaces/&/-
        if re.match(r"^[A-Z0-9&\-/.,]+$", t):
            pieces.append(t)
    return " ".join(pieces) if pieces else None


def assemble_row_values(lane_words, lane):
    """Given lane words for one row, snap each word to its nearest field anchor.
    Multiple words landing in the same field are concatenated in x0 order."""
    field_vals = defaultdict(list)
    for w in lane_words:
        f = field_of_word(w, lane)
        if f is None:
            continue
        field_vals[f].append(w["text"])
    return {k: " ".join(v) for k, v in field_vals.items()}


def parse_pack(s):
    if not s:
        return None
    try:
        return int(s.strip())
    except ValueError:
        return None


# Territory/division codes inside parentheses in brand headers.
# e.g. "OLD GRAND-DAD ( L GS FB IV )" -> "L GS FB IV"
_TERRITORY_PAREN_RE = re.compile(r"\(([^)]+)\)")

# Known valid NJ Allied sales division codes.
_VALID_DIVISIONS = {"L", "S", "D", "GS", "FB", "JD", "IV"}


def extract_divisions(text):
    """Extract division codes from parenthesized block.

    Only whitelisted NJ Allied division codes are accepted.
    A valid block has at least 2 such codes, e.g. ``( L GS FB IV )``.
    """
    m = _TERRITORY_PAREN_RE.search(text)
    if not m:
        return None
    tokens = m.group(1).strip().split()
    valid = [t for t in tokens if t in _VALID_DIVISIONS]
    if len(valid) >= 2:
        return " ".join(valid)
    return None


# RIP annotation lines like "$31.44 ON 1CS 114.54 19.09" sit between
# product rows in the same lane. They describe a discount: save $X on
# N cases, with new case and bottle prices.
RIP_ANNOT_RE = re.compile(
    r"^\$?([\d,]+\.\d{2})\s+ON\s+(\d+)\s*CS\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s*$",
    re.IGNORECASE,
)
# Some RIP lines come through pdfplumber as a sequence of single-glyph words
# ("$ 1 2 . 0 0 O N 1 CS 1 7 4 . 5 4 2 9 . 0 9"). Match the whitespace-stripped form.
RIP_ANNOT_COMPRESSED_RE = re.compile(
    r"^\$?([\d,]+\.\d{2})ON(\d+)CS([\d,]+\.\d{2})([\d,]+\.\d{2})$",
    re.IGNORECASE,
)


def parse_rip_annot(text):
    """If text is a RIP annotation, return parsed fields; else None."""
    text = text.strip()
    m = RIP_ANNOT_RE.match(text)
    if not m:
        compressed = re.sub(r"\s+", "", text)
        m = RIP_ANNOT_COMPRESSED_RE.match(compressed)
        if not m:
            return None
    return {
        "rip_save_amount": float(m.group(1).replace(",", "")),
        "rip_tier": f"{m.group(2)}CS",
        "rip_case_price": float(m.group(3).replace(",", "")),
        "rip_btl_price": float(m.group(4).replace(",", "")),
    }


def parse_main_catalog(pages, source):
    rows = []
    current_brand = [None, None, None]   # one per lane
    current_divisions = [None, None, None]  # division codes per lane
    # row index in `rows` of the most recent product per lane
    last_product_idx = [None, None, None]

    for page in pages:
        category = get_category(page)
        words = page.extract_words()
        words = [w for w in words
                 if PAGE_HEADER_Y < w["top"] < PAGE_FOOTER_Y]
        clusters = cluster_rows(words)

        # Reset last-product trackers per page so a RIP at the top of a new page
        # doesn't accidentally attach to the previous page's last row.
        # (Actually keep them: RIPs can legitimately apply to the same brand
        # continuing across pages. Leave alone.)

        for cluster in clusters:
            row_words = cluster["words"]
            for lane in range(3):
                lane_words = split_lane(row_words, lane)
                if not lane_words:
                    continue
                lane_words.sort(key=lambda w: w["x0"])
                first_text = lane_words[0]["text"].strip()

                if is_product_code(first_text):
                    vals = assemble_row_values(lane_words, lane)
                    rows.append({
                        "source": source,
                        "section": "MainCatalog",
                        "category": category,
                        "brand_header": current_brand[lane],
                        "divisions": current_divisions[lane],
                        "code": vals.get("code"),
                        "size": vals.get("size"),
                        "pack": parse_pack(vals.get("pack")),
                        "po_cost": vals.get("po_cost"),
                        "case_cost": vals.get("case_cost"),
                        "btl_cost": vals.get("btl_cost"),
                        "best_buy": vals.get("best_buy"),
                        "best_rip": vals.get("best_rip"),
                        "rip_save_amount": None,
                        "rip_tier": None,
                        "rip_case_price": None,
                        "rip_btl_price": None,
                        "rip_offers": [],
                        "page": page.page_number,
                        "lane": lane + 1,
                    })
                    last_product_idx[lane] = len(rows) - 1
                    continue

                text = " ".join(w["text"] for w in lane_words).strip()

                # Skip column-header lines that slipped through
                if text.startswith("Code Size Pk") or text.startswith("No. Cost") \
                    or "Best Buy" in text and "Best Rip" in text:
                    continue
                # Skip page-number-only lines
                if re.match(r"^\d{1,3}$", text):
                    continue
                # Skip boilerplate
                if "STANDARD PACKED" in text or "ABC Reg" in text \
                    or "STAN" in text and "PA" in text and "M E" in text:
                    continue

                # RIP annotation: attach to previous product in this lane
                rip = parse_rip_annot(text)
                if rip is not None:
                    if last_product_idx[lane] is not None:
                        prod = rows[last_product_idx[lane]]
                        prod["rip_offers"].append(rip)
                        # Keep the best (highest save) as top-level fields
                        prev = prod["rip_save_amount"]
                        if prev is None or rip["rip_save_amount"] > prev:
                            prod.update(rip)
                    continue

                # Otherwise: brand header / sub-header
                if re.search(r"[A-Z]{2,}", text):
                    current_brand[lane] = text
                    divs = extract_divisions(text)
                    if divs:
                        current_divisions[lane] = divs
    return rows
