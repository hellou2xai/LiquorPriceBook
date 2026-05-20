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
