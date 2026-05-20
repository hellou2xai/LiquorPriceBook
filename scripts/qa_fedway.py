"""Fedway scraper QA validation — runs locally against a PDF.

Validates brand quality, pricing completeness, RIP offers, category coverage,
description quality, and cross-section consistency.

Usage:
    python -m scripts.qa_fedway "Fedway+Pricebook+Full+June+2026.pdf"
    python -m scripts.qa_fedway "Fedway+Pricebook+Full+June+2026.pdf" --verbose
    python -m scripts.qa_fedway "Fedway+Pricebook+Full+June+2026.pdf" --dump-brands
    python -m scripts.qa_fedway "Fedway+Pricebook+Full+June+2026.pdf" --dump-missing-cost
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class Issue:
    agent: str
    severity: str  # error, warning, info
    message: str
    detail: str = ""


@dataclass
class QAReport:
    issues: list[Issue] = field(default_factory=list)
    passed: int = 0
    total: int = 0

    def add(self, agent: str, severity: str, message: str, detail: str = ""):
        self.issues.append(Issue(agent=agent, severity=severity, message=message, detail=detail))
        self.total += 1
        tag = "WARN" if severity == "warning" else severity.upper()
        print(f"  [{tag}] {message}")
        if detail:
            print(f"         {detail[:200]}")

    def ok(self, agent: str, message: str):
        self.passed += 1
        self.total += 1
        print(f"  [PASS] {message}")

    @property
    def errors(self):
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self):
        return [i for i in self.issues if i.severity == "warning"]

    def print_summary(self):
        print(f"\n{'='*70}")
        print(f"QA REPORT: {self.passed}/{self.total} checks passed")
        print(f"  Errors:   {len(self.errors)}")
        print(f"  Warnings: {len(self.warnings)}")
        print(f"{'='*70}")

        if self.errors:
            print("\nERRORS:")
            for i in self.errors:
                print(f"  [{i.agent}] {i.message}")
                if i.detail:
                    print(f"    > {i.detail[:300]}")

        if self.warnings:
            print("\nWARNINGS:")
            for i in self.warnings:
                print(f"  [{i.agent}] {i.message}")
                if i.detail:
                    print(f"    > {i.detail[:300]}")
        print()


# ── Agent 1: Section Detection ────────────────────────────────────────────

def qa_sections(diagnostics: dict, report: QAReport):
    agent = "sections"
    print(f"\n[{agent}] Checking section detection...")

    detected = diagnostics.get("sections_detected", [])
    if not detected:
        report.add(agent, "error", "No sections detected at all")
        return

    section_names = [s["section"] for s in detected]
    report.ok(agent, f"{len(detected)} section runs detected")

    # Must-have sections
    for required in ["spirits", "wine"]:
        if required in section_names:
            pages = [s for s in detected if s["section"] == required]
            total_pages = sum(s["count"] for s in pages)
            report.ok(agent, f"'{required}' found: {total_pages} pages")
        else:
            report.add(agent, "error", f"Required section '{required}' not found")

    # Check for unknown pages
    unknown = [s for s in detected if s["section"] == "unknown"]
    unknown_pages = sum(s["count"] for s in unknown)
    if unknown_pages > 10:
        report.add(agent, "warning", f"{unknown_pages} pages classified as 'unknown'",
                   "; ".join(f"pages {s['pages']}" for s in unknown[:5]))
    else:
        report.ok(agent, f"Only {unknown_pages} unknown pages")

    # Check skipped sections
    skipped = diagnostics.get("skipped", [])
    if skipped:
        report.add(agent, "info", f"{len(skipped)} section runs skipped",
                   "; ".join(f"{s['section']} ({s['pages']})" for s in skipped[:5]))


# ── Agent 2: Product Completeness ─────────────────────────────────────────

def qa_product_completeness(products: list[dict], report: QAReport):
    agent = "completeness"
    print(f"\n[{agent}] Checking product data completeness...")

    n = len(products)
    if n == 0:
        report.add(agent, "error", "Zero products extracted")
        return

    report.ok(agent, f"{n} total products extracted")

    # Required fields
    missing = defaultdict(int)
    for p in products:
        if not p.get("code"):
            missing["code"] += 1
        if not p.get("sub_brand"):
            missing["sub_brand"] += 1
        if not p.get("size"):
            missing["size"] += 1
        if p.get("case_cost") is None:
            missing["case_cost"] += 1
        if p.get("btl_cost") is None:
            missing["btl_cost"] += 1
        if not p.get("brand_header"):
            missing["brand_header"] += 1
        if not p.get("category"):
            missing["category"] += 1
        if p.get("pack") is None:
            missing["pack"] += 1

    for fld, count in sorted(missing.items(), key=lambda x: -x[1]):
        pct = count / n * 100
        if fld in ("code", "sub_brand") and count > 0:
            report.add(agent, "error", f"{count}/{n} ({pct:.1f}%) missing {fld}")
        elif fld == "case_cost" and pct > 30:
            report.add(agent, "error", f"{count}/{n} ({pct:.1f}%) missing {fld} — expected <30%")
        elif fld == "case_cost" and pct > 15:
            report.add(agent, "warning", f"{count}/{n} ({pct:.1f}%) missing {fld}")
        elif pct > 20:
            report.add(agent, "warning", f"{count}/{n} ({pct:.1f}%) missing {fld}")
        else:
            report.ok(agent, f"{fld}: {n - count}/{n} ({100 - pct:.1f}%) present")

    # Check for duplicate codes
    code_counts = Counter(p["code"] for p in products if p.get("code"))
    dupes = {code: cnt for code, cnt in code_counts.items() if cnt > 1}
    if len(dupes) > n * 0.05:
        report.add(agent, "warning", f"{len(dupes)} duplicate codes ({len(dupes)/n*100:.1f}%)",
                   "; ".join(f"{c}x{n}" for c, n in sorted(dupes.items(), key=lambda x: -x[1])[:10]))
    else:
        report.ok(agent, f"{len(dupes)} duplicate codes ({len(dupes)/n*100:.1f}%) — acceptable")


# ── Agent 3: Brand Quality ────────────────────────────────────────────────

SUSPECT_BRAND_WORDS = {
    "BLUE", "RED", "BLACK", "WHITE", "GREEN", "GOLD", "SILVER",
    "PINK", "AMBER", "COPPER", "PLATINUM", "BRONZE",
    "GIN", "VODKA", "RUM", "WHISKEY", "BOURBON", "TEQUILA",
    "BLANCO", "REPOSADO", "ANEJO", "SPICED", "PROOF",
    "CABERNET", "MERLOT", "CHARDONNAY", "MOSCATO", "PROSECCO",
    "RESERVE", "SINGLE", "IMPERIAL", "EXTRA", "SPECIAL",
    "LIGHT", "DARK", "CREAM", "HONEY", "VANILLA",
    "BARREL", "CASK", "AGED", "OLD", "VINTAGE",
}

GARBLED_RE = re.compile(r"^[A-Z /]{1,2}(\s+[A-Z /]{1,2}){2,}$")  # "/ E A" style single-char words


def qa_brands(products: list[dict], report: QAReport, verbose: bool = False):
    agent = "brands"
    print(f"\n[{agent}] Checking brand quality...")

    brands = Counter(p.get("brand_header") for p in products)
    none_count = brands.pop(None, 0)
    total_branded = sum(brands.values())

    report.ok(agent, f"{len(brands)} unique brands, {total_branded} branded products, {none_count} unbranded")

    suspect = []
    garbled = []
    too_short = []
    too_long = []

    for brand, count in brands.most_common():
        if not brand:
            continue

        # Garbled OCR
        if GARBLED_RE.match(brand) or len(brand) <= 1:
            garbled.append(f"'{brand}' ({count} products)")
            continue

        # Single word that's a spirit/wine term
        tokens = brand.upper().split()
        if len(tokens) == 1 and brand.upper() in SUSPECT_BRAND_WORDS:
            suspect.append(f"'{brand}' ({count} products)")

        # Too short (2 chars)
        if len(brand.replace(" ", "")) <= 2:
            too_short.append(f"'{brand}' ({count} products)")

        # Too long (probably a description)
        if len(brand) > 50:
            too_long.append(f"'{brand[:50]}...' ({count} products)")

    if garbled:
        report.add(agent, "error", f"{len(garbled)} garbled brands",
                   "; ".join(garbled[:8]))
    else:
        report.ok(agent, "No garbled brands")

    if suspect:
        report.add(agent, "warning", f"{len(suspect)} suspect single-word brands",
                   "; ".join(suspect[:8]))
    else:
        report.ok(agent, "No suspect single-word brands")

    if too_short:
        report.add(agent, "warning", f"{len(too_short)} very short brands (<=2 chars)",
                   "; ".join(too_short[:8]))

    if too_long:
        report.add(agent, "warning", f"{len(too_long)} very long brands (>50 chars)",
                   "; ".join(too_long[:5]))

    # Check brand concentration — top 10 brands should not cover >50% of products
    top10 = brands.most_common(10)
    top10_products = sum(c for _, c in top10)
    if total_branded > 0:
        pct = top10_products / total_branded * 100
        if pct > 60:
            report.add(agent, "warning", f"Top 10 brands cover {pct:.1f}% of products — might indicate parsing issues",
                       "; ".join(f"{b} ({c})" for b, c in top10))
        else:
            report.ok(agent, f"Top 10 brands cover {pct:.1f}% — good distribution")

    if none_count / len(products) > 0.15:
        report.add(agent, "warning", f"{none_count}/{len(products)} ({none_count/len(products)*100:.1f}%) have no brand")


# ── Agent 4: Pricing Validation ───────────────────────────────────────────

def qa_pricing(products: list[dict], report: QAReport):
    agent = "pricing"
    print(f"\n[{agent}] Checking pricing data quality...")

    n = len(products)
    if n == 0:
        return

    negative_case = []
    negative_btl = []
    extreme_case = []  # > $5000 per case
    extreme_btl = []   # > $2000 per bottle
    btl_gt_case = []   # bottle cost > case cost (should never happen)
    zero_cost = []

    for p in products:
        code = p.get("code", "?")
        cc = p.get("case_cost")
        bc = p.get("btl_cost")

        if cc is not None:
            cc_f = float(cc)
            if cc_f < 0:
                negative_case.append(code)
            elif cc_f == 0:
                zero_cost.append(code)
            elif cc_f > 5000:
                extreme_case.append(f"{code} (${cc_f:.2f})")

        if bc is not None:
            bc_f = float(bc)
            if bc_f < 0:
                negative_btl.append(code)
            elif bc_f > 2000:
                extreme_btl.append(f"{code} (${bc_f:.2f})")

        if cc is not None and bc is not None:
            if float(bc) > float(cc) and float(cc) > 0:
                btl_gt_case.append(f"{code}: btl=${bc} > case=${cc}")

    if negative_case:
        report.add(agent, "error", f"{len(negative_case)} products with negative case_cost",
                   ", ".join(negative_case[:10]))
    else:
        report.ok(agent, "No negative case costs")

    if negative_btl:
        report.add(agent, "error", f"{len(negative_btl)} products with negative btl_cost",
                   ", ".join(negative_btl[:10]))
    else:
        report.ok(agent, "No negative bottle costs")

    if zero_cost:
        sev = "error" if len(zero_cost) > 10 else "warning"
        report.add(agent, sev, f"{len(zero_cost)} products with $0 case cost",
                   ", ".join(zero_cost[:10]))
    else:
        report.ok(agent, "No $0 costs")

    if extreme_case:
        report.add(agent, "warning", f"{len(extreme_case)} products with case_cost > $5000",
                   "; ".join(extreme_case[:5]))
    else:
        report.ok(agent, "No extreme case costs (>$5000)")

    if btl_gt_case:
        sev = "warning" if len(btl_gt_case) < 20 else "error"
        report.add(agent, sev, f"{len(btl_gt_case)} products where btl_cost > case_cost",
                   "; ".join(btl_gt_case[:5]))
    else:
        report.ok(agent, "Bottle cost <= case cost for all products")

    # Price distribution by category
    cat_prices = defaultdict(list)
    for p in products:
        cc = p.get("case_cost")
        if cc is not None:
            cat_prices[p.get("category", "?")].append(float(cc))

    for cat, prices in sorted(cat_prices.items()):
        if len(prices) < 5:
            continue
        avg = sum(prices) / len(prices)
        mn = min(prices)
        mx = max(prices)
        if mx > avg * 20 and mx > 500:
            report.add(agent, "warning",
                       f"'{cat}' has extreme spread: avg=${avg:.0f}, max=${mx:.0f}",
                       f"min=${mn:.2f}, count={len(prices)}")


# ── Agent 5: RIP & BUY Deal Validation ───────────────────────────────────

def qa_rips(products: list[dict], report: QAReport):
    agent = "rips"
    print(f"\n[{agent}] Checking RIP offers and BUY deals...")

    n = len(products)
    with_buy = [p for p in products if p.get("best_buy")]
    with_rip_offers = [p for p in products if p.get("rip_offers")]

    report.ok(agent, f"{len(with_buy)}/{n} ({len(with_buy)/n*100:.1f}%) have BUY deals")
    report.ok(agent, f"{len(with_rip_offers)}/{n} ({len(with_rip_offers)/n*100:.1f}%) have RIP offers")

    if len(with_rip_offers) == 0:
        report.add(agent, "error", "Zero products with RIP offers — parser may be broken")
        return

    # Validate RIP offer structure
    bad_tier = []
    bad_save = []
    extreme_save = []
    total_offers = 0

    for p in with_rip_offers:
        code = p.get("code", "?")
        for offer in p.get("rip_offers", []):
            total_offers += 1
            tier = offer.get("rip_tier", "")
            save = offer.get("rip_save_amount")

            if not tier or not re.match(r"\d+(CS|BT|SL)", tier):
                bad_tier.append(f"{code}: '{tier}'")

            if save is not None:
                sf = float(save)
                if sf <= 0:
                    bad_save.append(f"{code}: ${sf}")
                elif sf > 500:
                    extreme_save.append(f"{code}: ${sf:.2f}/case, tier={tier}")

    report.ok(agent, f"{total_offers} total RIP offers across {len(with_rip_offers)} products")

    if bad_tier:
        report.add(agent, "error", f"{len(bad_tier)} RIP offers with bad tier format",
                   "; ".join(bad_tier[:8]))
    else:
        report.ok(agent, "All RIP tiers properly formatted")

    if bad_save:
        report.add(agent, "error", f"{len(bad_save)} RIP offers with zero/negative save",
                   "; ".join(bad_save[:8]))
    else:
        report.ok(agent, "All RIP save amounts positive")

    if extreme_save:
        report.add(agent, "warning", f"{len(extreme_save)} RIP offers with save > $500/case",
                   "; ".join(extreme_save[:5]))

    # Check BUY deal format validity
    bad_buy_format = []
    for p in with_buy:
        buy = p["best_buy"]
        # Valid formats: "1C$50", "3C$120", "AD", "1B$700", "1C$50,3C$120"
        if buy == "AD":
            continue
        if not re.match(r"^(\d+[CB]\$\d+(?:\.\d+)?(?:\s*,\s*)?)+$", buy):
            bad_buy_format.append(f"{p.get('code', '?')}: '{buy}'")

    if bad_buy_format:
        report.add(agent, "warning", f"{len(bad_buy_format)} products with unusual BUY format",
                   "; ".join(bad_buy_format[:8]))
    else:
        report.ok(agent, "All BUY deal formats valid")


# ── Agent 6: Description Quality ──────────────────────────────────────────

GARBLED_DESC_RE = re.compile(r"\d\s+\d\s+\d\s+\d")
DIVISION_IN_DESC_RE = re.compile(r"\(\s*[LSDGFBJDIV ]{3,}\s*\)")
SINGLE_CHAR_RE = re.compile(r"^[A-Z /]{1,2}(\s+[A-Z /]{1,2}){2,}$")


def qa_descriptions(products: list[dict], report: QAReport):
    agent = "descriptions"
    print(f"\n[{agent}] Checking description quality...")

    n = len(products)
    issues = {
        "garbled_ocr": [],
        "division_in_desc": [],
        "too_short": [],
        "numeric_only": [],
        "single_chars": [],
        "too_long": [],
    }

    for p in products:
        desc = p.get("sub_brand") or ""
        code = p.get("code", "?")

        if not desc:
            continue

        if GARBLED_DESC_RE.search(desc):
            issues["garbled_ocr"].append(f"{code}: '{desc[:60]}'")
        if DIVISION_IN_DESC_RE.search(desc):
            issues["division_in_desc"].append(f"{code}: '{desc[:60]}'")
        if len(desc.strip()) <= 3:
            issues["too_short"].append(f"{code}: '{desc}'")
        if re.match(r"^\d+$", desc.strip()):
            issues["numeric_only"].append(f"{code}: '{desc}'")
        if SINGLE_CHAR_RE.match(desc):
            issues["single_chars"].append(f"{code}: '{desc[:40]}'")
        if len(desc) > 200:
            issues["too_long"].append(f"{code}: {len(desc)} chars")

    for key, items in issues.items():
        label = key.replace("_", " ")
        if items:
            severity = "error" if key in ("garbled_ocr", "single_chars") else "warning"
            report.add(agent, severity, f"{len(items)} products with {label}",
                       "; ".join(items[:5]))
        else:
            report.ok(agent, f"No {label} issues")


# ── Agent 7: Size & Pack Validation ──────────────────────────────────────

def qa_sizes(products: list[dict], report: QAReport):
    agent = "sizes"
    print(f"\n[{agent}] Checking size and pack data...")

    n = len(products)
    size_counts = Counter()
    bad_sizes = []
    bad_packs = []

    for p in products:
        size = p.get("size")
        pack = p.get("pack")
        code = p.get("code", "?")

        if size:
            size_counts[size] += 1
            # Validate size format
            if not re.match(r"\d+(?:\.\d+)?\s*(ML|L|OZ|GAL|PK|CL)", size, re.IGNORECASE):
                bad_sizes.append(f"{code}: '{size}'")
        if pack is not None:
            if pack <= 0 or pack > 500:
                bad_packs.append(f"{code}: pack={pack}")

    report.ok(agent, f"{len(size_counts)} unique sizes")

    # Top sizes should make sense
    top5 = size_counts.most_common(5)
    report.ok(agent, f"Top sizes: {', '.join(f'{s} ({c})' for s, c in top5)}")

    if bad_sizes:
        report.add(agent, "warning", f"{len(bad_sizes)} products with unusual size format",
                   "; ".join(bad_sizes[:5]))
    else:
        report.ok(agent, "All sizes properly formatted")

    if bad_packs:
        report.add(agent, "error", f"{len(bad_packs)} products with out-of-range pack",
                   "; ".join(bad_packs[:5]))
    else:
        report.ok(agent, "All pack values in range")


# ── Agent 8: Category Coverage ────────────────────────────────────────────

def qa_categories(products: list[dict], report: QAReport):
    agent = "categories"
    print(f"\n[{agent}] Checking category coverage...")

    cat_counts = Counter(p.get("category", "UNKNOWN") for p in products)
    report.ok(agent, f"{len(cat_counts)} categories found")

    for cat, count in cat_counts.most_common():
        pct = count / len(products) * 100
        print(f"    {cat:30s} {count:6d} ({pct:5.1f}%)")

    # Spirits and Wine should be the biggest
    spirits = sum(c for cat, c in cat_counts.items()
                  if any(w in cat.upper() for w in ["SPIRIT", "WHISK", "VODKA", "GIN", "RUM", "TEQUILA", "BOURBON", "BRANDY", "COGNAC", "LIQUEUR"]))
    wine = sum(c for cat, c in cat_counts.items()
               if any(w in cat.upper() for w in ["WINE", "STILL", "SPARKLING", "CHAMPAGNE"]))

    if spirits == 0:
        report.add(agent, "error", "No spirits products found")
    else:
        report.ok(agent, f"{spirits} spirits products")

    if wine == 0:
        report.add(agent, "error", "No wine products found")
    else:
        report.ok(agent, f"{wine} wine products")

    # Country coverage
    country_counts = Counter(p.get("country") for p in products if p.get("country"))
    if country_counts:
        report.ok(agent, f"{len(country_counts)} countries: {', '.join(f'{c} ({n})' for c, n in country_counts.most_common(8))}")
    else:
        report.add(agent, "warning", "No country data extracted")


# ── Agent 9: Cross-Section Consistency ────────────────────────────────────

def qa_cross_section(results: dict, report: QAReport):
    agent = "cross-section"
    print(f"\n[{agent}] Checking cross-section consistency...")

    catalog = results.get("main_catalog", [])
    combos = results.get("combos", [])
    partials = results.get("partials_rips", [])

    report.ok(agent, f"main_catalog={len(catalog)}, combos={len(combos)}, partials={len(partials)}")

    catalog_codes = {p["code"] for p in catalog if p.get("code")}
    combo_codes = {p["code"] for p in combos if p.get("code")}
    partial_codes = {p["code"] for p in partials if p.get("code")}

    # Combos referencing non-existent catalog codes (may be expected for combo-only items)
    combo_only = combo_codes - catalog_codes
    if combo_only and len(combo_only) > len(combo_codes) * 0.5:
        report.add(agent, "warning",
                   f"{len(combo_only)}/{len(combo_codes)} combo codes not in main catalog",
                   ", ".join(sorted(combo_only)[:10]))
    elif combo_only:
        report.ok(agent, f"{len(combo_only)} combo-only codes (not in main catalog) — expected for combo items")
    else:
        report.ok(agent, "All combo codes found in main catalog")

    # Partials referencing non-existent catalog codes
    partial_only = partial_codes - catalog_codes
    if partial_only:
        pct = len(partial_only) / max(len(partial_codes), 1) * 100
        if pct > 30:
            report.add(agent, "warning",
                       f"{len(partial_only)}/{len(partial_codes)} ({pct:.0f}%) partial codes not in main catalog",
                       ", ".join(sorted(partial_only)[:10]))
        else:
            report.ok(agent, f"{len(partial_only)} partial-only codes ({pct:.0f}%) — acceptable")


# ── Agent 10: Page Coverage ──────────────────────────────────────────────

def qa_page_coverage(products: list[dict], diagnostics: dict, report: QAReport):
    agent = "pages"
    print(f"\n[{agent}] Checking page coverage...")

    pages_with_products = set()
    for p in products:
        pg = p.get("page")
        if pg:
            pages_with_products.add(pg)

    # Get total page count from diagnostics
    detected = diagnostics.get("sections_detected", [])
    all_pages = set()
    for s in detected:
        pages_str = s["pages"]
        if "-" in pages_str:
            start, end = pages_str.split("-")
            all_pages.update(range(int(start), int(end) + 1))
        else:
            all_pages.add(int(pages_str))

    total_pages = max(all_pages) if all_pages else 0
    report.ok(agent, f"Products found on {len(pages_with_products)} pages (total book: {total_pages} pages)")

    # Products per page distribution
    page_counts = Counter(p.get("page") for p in products if p.get("page"))
    if page_counts:
        avg = sum(page_counts.values()) / len(page_counts)
        max_page = page_counts.most_common(1)[0]
        report.ok(agent, f"Avg {avg:.1f} products/page, max {max_page[1]} on page {max_page[0]}")

        # Pages with very few products (might indicate parsing issues)
        sparse = [(pg, cnt) for pg, cnt in page_counts.items() if cnt <= 2]
        if len(sparse) > len(page_counts) * 0.2:
            report.add(agent, "warning",
                       f"{len(sparse)} pages with <=2 products ({len(sparse)/len(page_counts)*100:.0f}%)")


# ── Agent 11: Comparison with previous month ─────────────────────────────

def qa_cross_month(all_results: list[tuple[str, dict]], report: QAReport):
    """Compare product counts across multiple PDFs if provided."""
    agent = "cross-month"
    if len(all_results) < 2:
        return

    print(f"\n[{agent}] Comparing across {len(all_results)} PDFs...")

    for name, results in all_results:
        n = len(results.get("main_catalog", []))
        print(f"    {name}: {n} products")

    counts = [(name, len(results.get("main_catalog", []))) for name, results in all_results]
    counts.sort(key=lambda x: x[0])

    for i in range(1, len(counts)):
        prev_name, prev_n = counts[i-1]
        curr_name, curr_n = counts[i]
        if prev_n > 0:
            pct_change = (curr_n - prev_n) / prev_n * 100
            if abs(pct_change) > 20:
                report.add(agent, "warning",
                           f"Product count changed {pct_change:+.1f}% from {prev_name} to {curr_name}",
                           f"{prev_n} -> {curr_n}")
            else:
                report.ok(agent, f"{prev_name} -> {curr_name}: {pct_change:+.1f}% change — stable")


# ── Main ──────────────────────────────────────────────────────────────────

def run_qa(pdf_path: Path, verbose: bool = False, dump_brands: bool = False, dump_missing_cost: bool = False) -> QAReport:
    from templates.Fedway import scrape_pdf

    print(f"Scraping {pdf_path.name}...")
    results, diagnostics = scrape_pdf(pdf_path, source_name=pdf_path.name)

    catalog = results.get("main_catalog", [])
    all_products = catalog + results.get("combos", [])

    print(f"\nScrape complete: {len(catalog)} catalog + {len(results.get('combos', []))} combos + {len(results.get('partials_rips', []))} partials")

    report = QAReport()

    qa_sections(diagnostics, report)
    qa_product_completeness(catalog, report)
    qa_brands(catalog, report, verbose=verbose)
    qa_pricing(catalog, report)
    qa_rips(catalog, report)
    qa_descriptions(catalog, report)
    qa_sizes(catalog, report)
    qa_categories(catalog, report)
    qa_cross_section(results, report)
    qa_page_coverage(catalog, diagnostics, report)

    # Optional dumps
    if dump_brands:
        brands = Counter(p.get("brand_header") for p in catalog)
        print(f"\n{'='*70}")
        print("ALL BRANDS (sorted by frequency):")
        print(f"{'='*70}")
        for brand, count in brands.most_common():
            print(f"  {count:5d}  {brand or '(None)'}")

    if dump_missing_cost:
        missing = [p for p in catalog if p.get("case_cost") is None]
        print(f"\n{'='*70}")
        print(f"PRODUCTS MISSING CASE COST ({len(missing)}):")
        print(f"{'='*70}")
        for p in missing[:50]:
            print(f"  {p.get('code', '?'):10s} pg{p.get('page', '?'):>3s} {p.get('sub_brand', '?')[:60]}")

    report.print_summary()
    return report


def main():
    parser = argparse.ArgumentParser(description="Fedway scraper QA validation")
    parser.add_argument("pdfs", nargs="+", type=Path, help="Fedway PDF file(s)")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--dump-brands", action="store_true", help="Print all extracted brands")
    parser.add_argument("--dump-missing-cost", action="store_true", help="Print products missing case_cost")
    args = parser.parse_args()

    all_results = []
    final_report = None

    for pdf_path in args.pdfs:
        if not pdf_path.exists():
            print(f"ERROR: {pdf_path} not found", file=sys.stderr)
            continue
        print(f"\n{'#'*70}")
        print(f"# QA: {pdf_path.name}")
        print(f"{'#'*70}")
        report = run_qa(pdf_path, verbose=args.verbose,
                        dump_brands=args.dump_brands,
                        dump_missing_cost=args.dump_missing_cost)
        final_report = report

    if len(args.pdfs) > 1:
        # Cross-month comparison would need results stored — simplified version
        print(f"\nProcessed {len(args.pdfs)} PDFs")

    sys.exit(1 if final_report and final_report.errors else 0)


if __name__ == "__main__":
    main()
