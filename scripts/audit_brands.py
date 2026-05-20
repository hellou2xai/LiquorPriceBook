"""Audit brands for misextracted names.

Hits the live API to fetch all brands, then flags suspicious ones:
  1. Single-word brands that are common modifiers/colors/flavors
  2. Brands with very few products (likely sub-variant noise)
  3. Brands that look like proof/year/size descriptors

Usage:
    python -m scripts.audit_brands --api-url https://lpb-api-41nh.onrender.com --token <TOKEN>
"""

from __future__ import annotations

import argparse
import json
import re
import sys

import requests

# Words that should never be standalone brand names — they're modifiers.
SUSPECT_WORDS = {
    # Colors (common spirit variant names)
    "BLUE", "RED", "BLACK", "WHITE", "GREEN", "GOLD", "SILVER",
    "PLATINUM", "PINK", "AMBER", "COPPER", "BRONZE",
    # Spirit types / modifiers
    "GIN", "VODKA", "RUM", "WHISKEY", "WHISKY", "BOURBON", "TEQUILA",
    "MEZCAL", "BRANDY", "COGNAC", "RYE", "SCOTCH", "MALT", "BLEND",
    "BLANCO", "REPOSADO", "ANEJO", "SPICED", "PROOF",
    "BBN", "CASK", "BARREL", "STRAIGHT", "LIGHT", "DARK",
    # Wine varietals
    "CABERNET", "SAUVIGNON", "PINOT", "NOIR", "GRIGIO", "GRIS",
    "CHARDONNAY", "MERLOT", "ZINFANDEL", "SYRAH", "SHIRAZ", "MALBEC",
    "RIESLING", "MOSCATO", "PROSECCO", "CHAMPAGNE", "SPARKLING",
    "BLANC", "VIOGNIER", "ROSE", "BRUT", "DRY", "SWEET",
    # Flavors
    "PINEAPPLE", "COCONUT", "PEACH", "MANGO", "LIME", "LEMON",
    "ORANGE", "RASPBERRY", "STRAWBERRY", "WATERMELON", "VANILLA",
    "CHERRY", "GRAPE", "APPLE", "GRAPEFRUIT", "CRANBERRY",
    "ESPRESSO", "COFFEE", "HONEY", "CUCUMBER", "CITRON", "CITRUS",
    "TROPICAL", "BERRY", "TRIPLE", "PUNCH",
    # Pack/size
    "COMBO", "COMBOS", "BOX", "GIFT", "PACK", "VAP", "LTO", "PET",
    # Other
    "RESERVE", "SINGLE", "IMPERIAL", "EXTRA", "SPECIAL", "ORIGINAL",
    "CLASSIC", "PREMIUM", "SELECT", "AGED",
}

# Patterns that look like sub-variant descriptors, not brands
SUSPECT_PATTERNS = [
    re.compile(r"^\d+\s*(PROOF|YR|YEAR|OLD|ML|LTR|CS|PK)", re.I),
    re.compile(r"^[A-Z]+\s+\d+$", re.I),  # e.g. "Blue 80"
    re.compile(r"^\d+$"),  # just a number
]


def fetch_brands(api_url: str, token: str) -> list[dict]:
    """Fetch all brands from the API."""
    url = f"{api_url.rstrip('/')}/api/v1/catalog/brands"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers, params={"limit": 2000})
    resp.raise_for_status()
    return resp.json()


def audit(brands: list[dict]) -> list[dict]:
    """Return list of flagged brands with reasons."""
    flagged = []

    for b in brands:
        name = b.get("display_name", "")
        slug = b.get("slug", "")
        count = b.get("product_count", 0)
        reasons = []

        upper = name.upper().strip()
        tokens = upper.split()

        # Check 1: Single-word brand that's a known modifier
        if len(tokens) == 1 and upper in SUSPECT_WORDS:
            reasons.append(f"single modifier word: '{name}'")

        # Check 2: All tokens are modifiers
        if len(tokens) >= 1 and all(t in SUSPECT_WORDS for t in tokens):
            reasons.append(f"all tokens are modifiers: {tokens}")

        # Check 3: Matches sub-variant patterns
        for pat in SUSPECT_PATTERNS:
            if pat.match(upper):
                reasons.append(f"matches sub-variant pattern: '{name}'")
                break

        # Check 4: Very short name (1-3 chars) — likely a code fragment
        if len(name.replace(" ", "")) <= 3:
            reasons.append(f"very short name: '{name}'")

        # Check 5: Very few products — noise brands often have 1-2 products
        if count <= 2 and not reasons:
            reasons.append(f"only {count} product(s) — possible noise")

        # Check 6: Contains digits (e.g. "100" or "1792" which might be
        # valid like 1792 Bourbon, so just flag for review)
        if re.search(r"\d", name) and len(tokens) == 1:
            reasons.append(f"single numeric-containing token: '{name}'")

        if reasons:
            flagged.append({
                "brand": name,
                "slug": slug,
                "product_count": count,
                "reasons": reasons,
            })

    # Sort by product count desc so high-impact issues come first
    flagged.sort(key=lambda x: -x["product_count"])
    return flagged


def main():
    parser = argparse.ArgumentParser(description="Audit brands for misextraction")
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    print(f"Fetching brands from {args.api_url}...")
    brands = fetch_brands(args.api_url, args.token)
    print(f"Found {len(brands)} brands total.\n")

    flagged = audit(brands)

    if args.json:
        print(json.dumps(flagged, indent=2))
        return

    if not flagged:
        print("No suspicious brands found.")
        return

    print(f"{'='*70}")
    print(f"FLAGGED: {len(flagged)} / {len(brands)} brands look suspicious")
    print(f"{'='*70}\n")

    for f in flagged:
        print(f"  {f['brand']:<30} ({f['product_count']} products)")
        for r in f["reasons"]:
            print(f"    -> {r}")
        print()

    print(f"\nTo fix: add correct brand names to the scraper's _MODIFIER_WORDS")
    print(f"or adjust _is_brand_header() heuristics, then re-ingest.")


if __name__ == "__main__":
    main()
