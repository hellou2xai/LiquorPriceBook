"""Section detection rules for NjAllied price books.

Section boundaries are detected by text patterns rather than hardcoded page numbers,
so the template survives page-count drift between monthly editions.
"""

# Patterns matched against the first ~3 lines of each page to assign it to a section.
# Tested in order. First match wins.
SECTION_PATTERNS = [
    ("inventory_reduction", r"INVENTORY REDUCTION"),
    ("new_items",           r"NEW ITEMS"),
    ("partials_rips",       r"PARTIALS/WEB RIPS"),
    ("partials_pricing",    r"PARTIALS/WEB PRICING"),
    ("keg_list",            r"Keg List"),
    # Tighten to the dedicated section banner only ("ABG MAY 2026 COMBOS"),
    # otherwise in-catalog subheaders like "MACALLAN COMBOS" misclassify a page.
    ("combos",              r"ABG\s+\w+\s+\d{4}\s+COMBOS"),
    ("alphabetical_index",  r"Alphabetical Index"),
    ("table_of_contents",   r"Table of Contents"),
    # Producer pages span pages 32-73 in the May 2026 book. They have repeating
    # "Retail Incentives for ... 2026" structure. Catch with that header.
    ("producer_pages",      r"Retail Incentives for"),
    # Main Catalog pages have category headers like "BLENDED WHISKEY", "VODKA",
    # "WINES OF CALIFORNIA", along with the column header "Code Size Pk P.O."
    ("main_catalog",        r"Code\s+Size\s+Pk\s+P\.O\."),
]

# Sections we actively parse this pass (per user choice):
ENABLED_SECTIONS = {
    "inventory_reduction",
    "new_items",
    "partials_rips",
    "partials_pricing",
    "keg_list",
    "combos",
    "main_catalog",
}

# Main catalog three-column layout. Each column has 8 fields.
# Each field has a snap anchor: left-aligned fields anchor on x0 (left edge),
# right-aligned numeric fields anchor on x1 (right edge).
# Values measured from extract_words() on May 2026 p75.
#
# Format: (field_name, anchor_kind, target_x).  anchor_kind = "L" or "R".
CATALOG_COLUMN_ANCHORS = [
    # Column 1 (lane 0)
    [
        ("code",      "L",  32),
        ("size",      "L",  58),
        ("pack",      "L",  80),
        ("po_cost",   "R", 105),
        ("case_cost", "R", 126),
        ("btl_cost",  "R", 149),
        ("best_buy",  "R", 181),
        ("best_rip",  "R", 213),
    ],
    # Column 2 (lane 1)
    [
        ("code",      "L", 218),
        ("size",      "L", 243),
        ("pack",      "L", 264),
        ("po_cost",   "R", 289),
        ("case_cost", "R", 310),
        ("btl_cost",  "R", 333),
        ("best_buy",  "R", 365),
        ("best_rip",  "R", 397),
    ],
    # Column 3 (lane 2)
    [
        ("code",      "L", 401),
        ("size",      "L", 426),
        ("pack",      "L", 447),
        ("po_cost",   "R", 473),
        ("case_cost", "R", 494),
        ("btl_cost",  "R", 517),
        ("best_buy",  "R", 549),
        ("best_rip",  "R", 581),
    ],
]

# Per-lane snap tolerance (pixels). If the nearest anchor is farther than
# this, we mark the word's field as None instead of forcing a bad fit.
CATALOG_SNAP_TOL = 12

# Catalog lane x-ranges used to group lines by column.
CATALOG_LANES_X = [(28, 215), (218, 400), (401, 595)]
