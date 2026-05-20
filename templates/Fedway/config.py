"""Section detection rules for Fedway price books.

Section boundaries are detected by text patterns matched against page headers.
First match wins.
"""

import re

# Patterns matched against the header area of each page.
# Fedway has a consistent header: "Order Phone: 800-4-FEDWAY <SECTION> Order Fax: ..."
SECTION_PATTERNS = [
    ("best_deal",          r"BEST DEAL"),
    ("partial_month",      r"PARTIAL MONTH"),
    ("retail_incentives",  r"RETAIL INCENTIVES"),
    ("combo_packs",        r"COMBO PACKS"),
    ("craft_distilled",    r"CRAFT DISTILLED"),
    ("featured_sake",      r"FEATURED SAKE"),
    ("highly_rated",       r"HIGHLY RATED"),
    ("cans_cocktails",     r"CANS AND COCKTAILS"),
    ("malt_products",      r"MALT PRODUCTS"),
    ("non_alcoholic",      r"NON ALCOHOLIC"),
    ("mixers",             r"MIXERS AND MORE"),
    ("spirits",            r"(?<!\w)SPIRITS(?!\w)"),
    ("wine",               r"(?<!\w)WINE(?!\w)"),
    ("table_of_contents",  r"Table of Contents|TABLE OF CONTENTS"),
    ("index",              r"\bIndex\b|xednI"),
]

# Sections we actively parse.
ENABLED_SECTIONS = {
    "main_catalog",       # Spirits + Wine + Cans + Malt + Non-Alcoholic + Mixers
    "best_deal",
    "partial_month",
    "retail_incentives",
    "combo_packs",
    "craft_distilled",
}

# Sections that are all "main catalog" format (3-column product listing)
CATALOG_FORMAT_SECTIONS = {
    "spirits",
    "wine",
    "cans_cocktails",
    "malt_products",
    "non_alcoholic",
    "mixers",
}

# Fedway 3-column layout lane x-ranges (from word analysis of spirits pages)
# Column 1: x ~18-210, Column 2: x ~213-397, Column 3: x ~401-595
CATALOG_LANES_X = [(18, 210), (213, 397), (401, 595)]
