"""Systematic extraction validator.

Scrapes a PDF locally and audits every product on every page for
extraction quality issues. Produces a detailed report with page-by-page
findings and a summary of issue categories.

Usage:
  python -m scripts.validate_extraction <pdf> -d nj-fedway
  python -m scripts.validate_extraction <pdf> -d nj-allied
  python -m scripts.validate_extraction <pdf> -d nj-fedway --page 91
  python -m scripts.validate_extraction <pdf> -d nj-fedway --csv report.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ── Issue categories ─────────────────────────────────────────────────────

ISSUE_GARBLED_DESC = "garbled_description"
ISSUE_MISSING_DESC = "missing_description"
ISSUE_MISSING_PRICE = "missing_case_cost"
ISSUE_MISSING_BRAND = "missing_brand"
ISSUE_BRAND_IS_DESC = "brand_looks_like_description"
ISSUE_EXTREME_PRICE = "extreme_price"
ISSUE_DUP_DESC = "duplicate_description_on_page"
ISSUE_PRICE_PERIOD_IN_DESC = "price_period_in_description"
ISSUE_OCR_IN_DESC = "ocr_noise_in_description"
ISSUE_MISSING_SIZE = "missing_size"
ISSUE_MISSING_CODE = "missing_code"
ISSUE_BRAND_TRUNCATED = "brand_truncated"
ISSUE_BRAND_IS_OCR = "brand_is_ocr_noise"
ISSUE_BRAND_BLEED = "brand_bleed_suspected"
ISSUE_PRICE_VS_PACK = "price_pack_mismatch"
ISSUE_CODE_FORMAT = "invalid_code_format"


# ── Checks ───────────────────────────────────────────────────────────────

_SPACED_RE = re.compile(r"[A-Z]\s[A-Z]\s[A-Z]\s[A-Z]")
_DOLLAR_IN_DESC = re.compile(r"\$\d")
_DATE_RANGE_RE = re.compile(r"\d{2}/\d{2}\s*-\s*\d{2}/\d{2}")
_PERIOD_WORDS = {"ALL MONTH", "LIMITED TIME OFFER", "SPECTACULAR"}

# Words that suggest a "brand" is actually a description fragment
_DESC_MARKER_WORDS = {
    "YEAR", "OLD", "BLEND", "RESERVE", "BARREL", "SINGLE", "MALT",
    "CABERNET", "CHARDONNAY", "PINOT", "ROUGE", "BLANC", "CASK",
    "VINTAGE", "SPECIAL", "LIMITED", "EDITION", "AGED", "PROOF",
    "SAUVIGNON", "MERLOT", "SYRAH", "ZINFANDEL", "RIESLING",
    "PROSECCO", "BRUT", "CUVEE", "NOIR", "GRIGIO",
}

# Known single words that usually indicate a truncated brand name
_TRUNCATED_BRAND_WORDS = {
    "VELVET", "CANADIAN", "CLUB", "ROYAL", "TURKEY", "GOOSE", "BEAM",
    "DANIEL", "DANIELS", "WALKER", "LABEL", "HORSE", "NECK", "BULL",
    "MONK", "HARBOR", "COMFORT", "RUSSIA", "STAG", "EAGLE", "RARE",
    "MAKER", "MAKERS", "KNOB", "CREEK", "WOODFORD", "RESERVE",
    "FORESTER", "GROUSE",
}

# OCR noise detection patterns for brand names
_BRAND_OCR_DOLLAR = re.compile(r"\$")
_BRAND_OCR_SPACED = re.compile(r"^([A-Z]\s){3,}")  # spaced-out single letters
_BRAND_OCR_DIGIT_ALPHA_MIX = re.compile(r"[A-Z]\d[A-Z]|[0-9]{2,}[A-Z]|[A-Z][0-9]{2,}[A-Z]")
_BRAND_MOSTLY_NON_ALPHA = re.compile(r"[^A-Za-z\s]")

# Code format: 4-9 digits, possibly with leading zeros
_VALID_CODE_RE = re.compile(r"^\d{4,9}$")

# Well-known multi-word brand names (used for brand bleed detection)
_KNOWN_BRANDS = {
    "JACK DANIELS", "JACK DANIEL'S", "JOHNNY WALKER", "JOHNNIE WALKER",
    "MAKERS MARK", "MAKER'S MARK", "WILD TURKEY", "GREY GOOSE",
    "BLACK VELVET", "CANADIAN CLUB", "CROWN ROYAL", "JIM BEAM",
    "WOODFORD RESERVE", "KNOB CREEK", "OLD FORESTER", "FAMOUS GROUSE",
    "BUFFALO TRACE", "ANGELS ENVY", "ANGEL'S ENVY", "HENNESSY",
    "UNCLE NEAREST", "BULLEIT", "FOUR ROSES", "STARWARD",
    "MONKEY SHOULDER", "GLENLIVET", "GLENFIDDICH", "MACALLAN",
    "PATRON", "DON JULIO", "CASAMIGOS", "TITOS", "TITO'S",
    "ABSOLUT", "SMIRNOFF", "KETEL ONE", "BELVEDERE", "CIROC",
    "BACARDI", "CAPTAIN MORGAN", "MALIBU", "TANQUERAY", "BOMBAY",
    "HENDRICKS", "HENDRICK'S", "JAMESON", "BUSHMILLS", "TULLAMORE",
}

# Single-word tokens from known brands (for detecting bleed candidates in descriptions)
_KNOWN_BRAND_TOKENS = set()
for _b in _KNOWN_BRANDS:
    for _w in _b.replace("'", "").split():
        if len(_w) > 3:  # skip short words like "OLD", "DON"
            _KNOWN_BRAND_TOKENS.add(_w.upper())


def _check_product(product: dict) -> list[dict]:
    """Run all checks on one product, return list of issues found."""
    issues = []
    code = product.get("code", "?")
    page = product.get("page", "?")
    lane = product.get("lane", "?")
    desc = product.get("sub_brand") or ""
    brand = product.get("brand_header") or ""
    case_cost = product.get("case_cost")
    btl_cost = product.get("btl_cost")
    size = product.get("size")

    def _issue(category: str, detail: str, severity: str = "warning"):
        issues.append({
            "code": code,
            "page": page,
            "lane": lane,
            "category": category,
            "severity": severity,
            "detail": detail,
            "brand": brand,
            "description": desc[:80],
            "case_cost": str(case_cost) if case_cost else "",
        })

    # 1. Missing or empty description
    # Note: desc matching brand is OK — many products use the brand as their description
    if not desc.strip():
        _issue(ISSUE_MISSING_DESC, "No product description", "error")

    # 2. Garbled description (spaced-out OCR text)
    if _SPACED_RE.search(desc):
        _issue(ISSUE_GARBLED_DESC,
               f"Spaced-out OCR text in description: ...{desc[desc.find('  '):desc.find('  ')+30]}...",
               "error")

    # 3. Dollar signs / prices in description
    if _DOLLAR_IN_DESC.search(desc):
        _issue(ISSUE_OCR_IN_DESC,
               f"Price data in description: {desc[:60]}",
               "error")

    # 4. Date range or period label in description
    if _DATE_RANGE_RE.search(desc):
        _issue(ISSUE_PRICE_PERIOD_IN_DESC,
               f"Date range in description: {desc[:60]}",
               "error")
    for pw in _PERIOD_WORDS:
        if pw in desc.upper():
            _issue(ISSUE_PRICE_PERIOD_IN_DESC,
                   f"Period label '{pw}' in description",
                   "error")
            break

    # 5. Missing case cost
    if case_cost is None:
        _issue(ISSUE_MISSING_PRICE, "No case cost", "warning")

    # 6. Extreme price (likely OCR error or wrong assignment)
    if case_cost is not None:
        try:
            cc = float(str(case_cost))
            if cc > 10000:
                _issue(ISSUE_EXTREME_PRICE,
                       f"Case cost ${cc:,.2f} — verify against PDF",
                       "warning")
            elif cc < 1:
                _issue(ISSUE_EXTREME_PRICE,
                       f"Case cost ${cc:.2f} — suspiciously low",
                       "warning")
        except (ValueError, TypeError):
            pass

    # 7. Missing brand
    if not brand.strip():
        _issue(ISSUE_MISSING_BRAND, "No brand extracted", "info")

    # 8. Brand looks like a description fragment
    if brand:
        brand_words = set(brand.upper().split())
        overlap = brand_words & _DESC_MARKER_WORDS
        if overlap and len(brand.split()) > 1:
            _issue(ISSUE_BRAND_IS_DESC,
                   f"Brand '{brand}' contains description words: {overlap}",
                   "warning")

    # 9. Missing size
    if not size:
        _issue(ISSUE_MISSING_SIZE, "No size extracted", "warning")

    # 10. Brand truncated — single word that's a known truncation artifact
    if brand.strip():
        brand_upper = brand.strip().upper()
        brand_tokens = brand_upper.split()
        if len(brand_tokens) == 1 and brand_tokens[0] in _TRUNCATED_BRAND_WORDS:
            _issue(ISSUE_BRAND_TRUNCATED,
                   f"Brand '{brand}' is a single word likely truncated from a longer name",
                   "warning")

    # 11. Brand is OCR noise
    if brand.strip():
        brand_stripped = brand.strip()
        alpha_chars = sum(1 for c in brand_stripped if c.isalpha())
        total_chars = len(brand_stripped.replace(" ", ""))
        is_ocr = False
        ocr_reason = ""
        if _BRAND_OCR_DOLLAR.search(brand_stripped):
            is_ocr = True
            ocr_reason = "contains dollar sign"
        elif _BRAND_OCR_SPACED.search(brand_stripped):
            is_ocr = True
            ocr_reason = "spaced-out single letters (OCR artifact)"
        elif _BRAND_OCR_DIGIT_ALPHA_MIX.search(brand_stripped):
            is_ocr = True
            ocr_reason = "unnatural digit/letter mix"
        elif total_chars > 0 and alpha_chars / total_chars < 0.5:
            is_ocr = True
            ocr_reason = f"mostly non-alpha ({alpha_chars}/{total_chars} alpha chars)"
        if is_ocr:
            _issue(ISSUE_BRAND_IS_OCR,
                   f"Brand '{brand}' appears to be OCR noise: {ocr_reason}",
                   "warning")

    # 12. Brand bleed — brand appears in description alongside a different brand name
    if brand.strip() and desc.strip():
        desc_upper = desc.strip().upper()
        brand_upper = brand.strip().upper()
        if brand_upper in desc_upper:
            # Look for capitalized multi-word sequences in the description
            # that differ from the brand and could be another brand
            remaining = desc_upper.replace(brand_upper, "", 1).strip()
            # Check if any known brand token appears in the remaining text
            remaining_words = set(remaining.split())
            suspect_tokens = remaining_words & _KNOWN_BRAND_TOKENS
            # Filter out tokens that are part of the current brand
            brand_word_set = set(brand_upper.split())
            suspect_tokens -= brand_word_set
            if suspect_tokens:
                _issue(ISSUE_BRAND_BLEED,
                       f"Brand '{brand}' in desc with other brand tokens: {suspect_tokens}",
                       "warning")

    # 13. Price vs pack mismatch
    pack = product.get("pack")
    if case_cost is not None and btl_cost is not None:
        try:
            cc = float(str(case_cost))
            bc = float(str(btl_cost))
            if bc > 0 and cc < bc:
                _issue(ISSUE_PRICE_VS_PACK,
                       f"Case cost ${cc:.2f} < bottle cost ${bc:.2f}",
                       "warning")
            if pack is not None and bc > 0:
                pk = int(str(pack))
                if pk > 0:
                    implied_btl = cc / pk
                    ratio = implied_btl / bc if bc > 0 else 0
                    if ratio < 0.5 or ratio > 1.5:
                        _issue(ISSUE_PRICE_VS_PACK,
                               f"case/pack=${implied_btl:.2f} vs btl=${bc:.2f} "
                               f"(ratio {ratio:.2f}, pack={pk}) — exceeds 50% tolerance",
                               "warning")
        except (ValueError, TypeError, ZeroDivisionError):
            pass

    # 14. Invalid code format
    code_str = str(code).strip() if code else ""
    if code_str and code_str != "?":
        if not _VALID_CODE_RE.match(code_str):
            _issue(ISSUE_CODE_FORMAT,
                   f"Code '{code_str}' is not 4-9 digits",
                   "warning")

    return issues


def _check_page_duplicates(products: list[dict]) -> list[dict]:
    """Check for products on the same page+lane with identical descriptions."""
    issues = []
    by_page_lane = defaultdict(list)
    for p in products:
        key = (p.get("page"), p.get("lane"))
        by_page_lane[key].append(p)

    for (page, lane), prods in by_page_lane.items():
        descs = Counter()
        for p in prods:
            d = (p.get("sub_brand") or "").strip()
            if d:
                descs[d] += 1
        for desc_text, count in descs.items():
            if count > 5:  # more than 5 with same desc is suspicious (size variants normally share descriptions)
                for p in prods:
                    if (p.get("sub_brand") or "").strip() == desc_text:
                        issues.append({
                            "code": p.get("code", "?"),
                            "page": page,
                            "lane": lane,
                            "category": ISSUE_DUP_DESC,
                            "severity": "warning",
                            "detail": f"Description repeated {count}x on page {page} lane {lane}: {desc_text[:50]}",
                            "brand": p.get("brand_header") or "",
                            "description": desc_text[:80],
                            "case_cost": str(p.get("case_cost", "")),
                        })
    return issues


def _check_brand_consistency(products: list[dict]) -> list[dict]:
    """Cross-product brand consistency checks.

    Groups products by brand_header per page/lane and flags:
    - Same brand with wildly different description prefixes (brand bleed)
    - A brand appearing on only 1 product on a page that matches a well-known
      brand name used elsewhere in the catalog
    """
    issues = []

    # Group by (page, lane, brand_header)
    by_page_lane_brand: dict[tuple, list[dict]] = defaultdict(list)
    # Track global brand usage counts
    global_brand_counts: Counter = Counter()
    for p in products:
        brand = (p.get("brand_header") or "").strip()
        if not brand:
            continue
        key = (p.get("page", "?"), p.get("lane", "?"), brand)
        by_page_lane_brand[key].append(p)
        global_brand_counts[brand.upper()] += 1

    # All brands used across the entire catalog (for singleton comparison)
    all_brands_upper = set(global_brand_counts.keys())

    for (page, lane, brand), prods in by_page_lane_brand.items():
        # --- Check 1: Divergent description prefixes under same brand ---
        if len(prods) >= 2:
            prefixes = []
            for p in prods:
                desc = (p.get("sub_brand") or "").strip().upper()
                # Use the first two words as the prefix
                words = desc.split()[:2]
                prefix = " ".join(words) if words else ""
                prefixes.append(prefix)

            unique_prefixes = set(pf for pf in prefixes if pf)
            # If there are many different prefixes relative to the product count,
            # and at least one prefix doesn't start with the brand, flag it
            if len(unique_prefixes) >= 2:
                brand_upper = brand.upper()
                non_matching = [
                    pf for pf in unique_prefixes
                    if not pf.startswith(brand_upper.split()[0]) and pf != brand_upper
                ]
                if non_matching and len(non_matching) >= len(unique_prefixes) * 0.5:
                    for p in prods:
                        desc = (p.get("sub_brand") or "").strip().upper()
                        desc_prefix = " ".join(desc.split()[:2])
                        if desc_prefix in non_matching:
                            issues.append({
                                "code": p.get("code", "?"),
                                "page": page,
                                "lane": lane,
                                "category": ISSUE_BRAND_BLEED,
                                "severity": "warning",
                                "detail": (
                                    f"Brand '{brand}' has divergent desc prefix "
                                    f"'{desc_prefix}' vs other products under same brand"
                                ),
                                "brand": brand,
                                "description": (p.get("sub_brand") or "")[:80],
                                "case_cost": str(p.get("case_cost", "")),
                            })

        # --- Check 2: Singleton brand on a page that matches a known brand elsewhere ---
        if len(prods) == 1:
            brand_upper = brand.upper()
            # Check if this brand name is a well-known brand used elsewhere
            # (i.e., it appears on other pages too, but only once on this page —
            # could be a bleed from an adjacent column)
            if brand_upper in all_brands_upper and global_brand_counts[brand_upper] > 1:
                # Only flag if there are OTHER brands on this same page/lane
                same_page_brands = [
                    k[2] for k in by_page_lane_brand
                    if k[0] == page and k[1] == lane and k[2] != brand
                ]
                if same_page_brands:
                    p = prods[0]
                    desc = (p.get("sub_brand") or "").strip().upper()
                    # Check if the description doesn't start with this brand
                    if desc and not desc.startswith(brand_upper.split()[0]):
                        issues.append({
                            "code": p.get("code", "?"),
                            "page": page,
                            "lane": lane,
                            "category": ISSUE_BRAND_BLEED,
                            "severity": "warning",
                            "detail": (
                                f"Brand '{brand}' has only 1 product on page {page} "
                                f"but {global_brand_counts[brand_upper]} total — "
                                f"possible bleed from adjacent brand"
                            ),
                            "brand": brand,
                            "description": (p.get("sub_brand") or "")[:80],
                            "case_cost": str(p.get("case_cost", "")),
                        })

    return issues


# ── Main ─────────────────────────────────────────────────────────────────

def validate(pdf_path: Path, distributor: str, page_filter: int | None = None) -> list[dict]:
    """Scrape a PDF and validate all extracted products."""
    if distributor == "nj-fedway":
        from templates.Fedway import scrape_pdf
    else:
        from templates.NjAllied import scrape_pdf

    results, diag = scrape_pdf(pdf_path, source_name=pdf_path.name)

    products = results.get("main_catalog", [])
    if page_filter is not None:
        products = [p for p in products if p.get("page") == page_filter]

    print(f"Scrape complete: {len(results.get('main_catalog', []))} total products")
    print(f"Validating {len(products)} products" +
          (f" (page {page_filter})" if page_filter else "") + "...")
    print()

    all_issues = []

    # Per-product checks
    for p in products:
        all_issues.extend(_check_product(p))

    # Cross-product checks (duplicate descriptions)
    all_issues.extend(_check_page_duplicates(products))

    # Cross-product checks (brand consistency)
    all_issues.extend(_check_brand_consistency(products))

    return all_issues


def print_report(issues: list[dict], verbose: bool = False):
    """Print a summary report of all issues found."""
    if not issues:
        print("No issues found!")
        return

    # Summary by category
    by_cat = Counter(i["category"] for i in issues)
    by_severity = Counter(i["severity"] for i in issues)

    print("=" * 70)
    print("EXTRACTION VALIDATION REPORT")
    print("=" * 70)
    print()
    print(f"Total issues: {len(issues)}")
    print(f"  Errors:   {by_severity.get('error', 0)}")
    print(f"  Warnings: {by_severity.get('warning', 0)}")
    print(f"  Info:     {by_severity.get('info', 0)}")
    print()
    print("By category:")
    for cat, count in by_cat.most_common():
        print(f"  {count:5d}  {cat}")
    print()

    # Group by page for page-by-page view
    by_page = defaultdict(list)
    for i in issues:
        by_page[i["page"]].append(i)

    # Show errors first, then optionally all
    errors = [i for i in issues if i["severity"] == "error"]
    if errors:
        print("-" * 70)
        print(f"ERRORS ({len(errors)} issues requiring attention)")
        print("-" * 70)
        for i in errors[:50]:  # cap at 50
            print(f"  p{str(i['page']):>4s} L{str(i['lane']):>2s} | {str(i['code']):>12s} | {i['category']:30s} | {i['detail'][:60]}")
        if len(errors) > 50:
            print(f"  ... and {len(errors) - 50} more errors")
        print()

    if verbose:
        print("-" * 70)
        print("ALL ISSUES BY PAGE")
        print("-" * 70)
        for page in sorted(by_page.keys(), key=lambda x: int(x) if str(x).isdigit() else 0):
            page_issues = by_page[page]
            print(f"\n  Page {page} ({len(page_issues)} issues):")
            for i in page_issues:
                sev = {"error": "ERR", "warning": "WRN", "info": "INF"}[i["severity"]]
                print(f"    [{sev}] {str(i['code']):>12s} {i['category']:30s} {i['detail'][:55]}")

    # Top pages with most issues
    print("-" * 70)
    print("PAGES WITH MOST ISSUES")
    print("-" * 70)
    page_counts = Counter(i["page"] for i in issues if i["severity"] in ("error", "warning"))
    for page, count in page_counts.most_common(20):
        cats = Counter(i["category"] for i in by_page[page])
        cats_str = ", ".join(f"{c}={n}" for c, n in cats.most_common(3))
        print(f"  Page {str(page):>4s}: {count:3d} issues  ({cats_str})")


def write_csv(issues: list[dict], path: str):
    """Write issues to CSV for spreadsheet analysis."""
    if not issues:
        return
    fields = ["severity", "page", "lane", "code", "category", "brand",
              "description", "case_cost", "detail"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(issues, key=lambda i: (
            {"error": 0, "warning": 1, "info": 2}[i["severity"]],
            int(i["page"]) if str(i["page"]).isdigit() else 0,
            i["code"],
        )))
    print(f"CSV written: {path} ({len(issues)} rows)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate PDF extraction quality page-by-page"
    )
    parser.add_argument("pdf", type=Path, help="Path to the PDF file")
    parser.add_argument(
        "-d", "--distributor", default="nj-fedway",
        help="Distributor slug (default: nj-fedway)",
    )
    parser.add_argument(
        "--page", type=int, default=None,
        help="Validate only this page number",
    )
    parser.add_argument(
        "--csv", type=str, default=None,
        help="Write issues to CSV file",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Show all issues by page (not just errors)",
    )
    args = parser.parse_args(argv)

    if not args.pdf.exists():
        print(f"ERROR: File not found: {args.pdf}", file=sys.stderr)
        return 1

    issues = validate(args.pdf, args.distributor, args.page)
    print_report(issues, verbose=args.verbose)

    if args.csv:
        write_csv(issues, args.csv)

    return 0


if __name__ == "__main__":
    sys.exit(main())
