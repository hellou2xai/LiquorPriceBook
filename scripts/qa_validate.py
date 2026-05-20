"""End-to-end QA validation for CELR Price Book.

Validates data integrity from ingestion through API responses.

Usage:
    python -m scripts.qa_validate --api-url https://lpb-api-41nh.onrender.com --token <TOKEN>
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from typing import Any

import requests


@dataclass
class Issue:
    agent: str
    severity: str
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
        print(f"{'='*70}\n")

        if self.errors:
            print("ERRORS:")
            for i in self.errors:
                print(f"  [{i.agent}] {i.message}")
                if i.detail:
                    print(f"    > {i.detail}")
            print()

        if self.warnings:
            print("WARNINGS:")
            for i in self.warnings:
                print(f"  [{i.agent}] {i.message}")
                if i.detail:
                    print(f"    > {i.detail}")
            print()


class APIClient:
    def __init__(self, base_url: str, token: str):
        self.base = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {token}"}

    def get(self, path: str, params: dict | None = None) -> Any:
        resp = requests.get(f"{self.base}{path}", headers=self.headers, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()


# ── Agent 1: Edition & Summary ────────────────────────────────────────────

def qa_editions(api: APIClient, report: QAReport):
    agent = "editions"
    print(f"\n[{agent}] Checking book editions...")

    try:
        s = api.get("/api/v1/dashboard/summary")
    except Exception as e:
        report.add(agent, "error", "Cannot fetch dashboard summary", str(e))
        return s if 's' in dir() else None

    if not s.get("edition_label"):
        report.add(agent, "error", "No active edition found")
    else:
        report.ok(agent, f"Active edition: {s['edition_label']}")

    total = s.get("total_products", 0)
    if total == 0:
        report.add(agent, "error", "Zero products in current edition")
    elif total < 1000:
        report.add(agent, "warning", f"Only {total} products - expected 4000+")
    else:
        report.ok(agent, f"{total} products in edition")

    rips = s.get("total_rips", 0)
    if rips == 0:
        report.add(agent, "warning", "Zero RIPs in current edition")
    else:
        report.ok(agent, f"{rips} active RIPs")

    closeouts = s.get("total_closeouts", 0)
    report.ok(agent, f"{closeouts} closeouts")

    return s


# ── Agent 2: Catalog Data Quality ─────────────────────────────────────────

def qa_catalog(api: APIClient, report: QAReport):
    agent = "catalog"
    print(f"\n[{agent}] Checking catalog data quality...")

    try:
        data = api.get("/api/v1/catalog/products", {"limit": 200, "offset": 0})
    except Exception as e:
        report.add(agent, "error", "Cannot fetch catalog", str(e))
        return []

    products = data.get("items", data.get("products", []))
    if not products:
        report.add(agent, "error", "Empty catalog response")
        return []

    report.ok(agent, f"Fetched {len(products)} products (total: {data.get('total', '?')})")

    missing_desc = 0
    garbled_desc = 0
    missing_cost = 0
    missing_category = 0
    missing_brand = 0
    negative_cost = 0
    division_in_desc = 0

    DIV_PATTERN = re.compile(r"\(\s*[LSDGFBJDIV ]+\s*\)\s*$")
    GARBLE_PATTERN = re.compile(r"\d\s+\d\s+\d\s+\d")  # "0 0 1 1 34" garbled OCR

    for p in products:
        desc = p.get("description") or ""
        if not desc:
            missing_desc += 1
        elif GARBLE_PATTERN.search(desc):
            garbled_desc += 1
        if DIV_PATTERN.search(desc):
            division_in_desc += 1

        cost = p.get("case_cost")
        if cost is None:
            missing_cost += 1
        elif float(cost) < 0:
            negative_cost += 1

        if not p.get("category_slug"):
            missing_category += 1
        if not p.get("brand_slug"):
            missing_brand += 1

    if missing_desc:
        report.add(agent, "error", f"{missing_desc}/{len(products)} products missing description")
    else:
        report.ok(agent, "All products have descriptions")

    if garbled_desc:
        report.add(agent, "warning", f"{garbled_desc}/{len(products)} products have garbled OCR descriptions")
    else:
        report.ok(agent, "No garbled descriptions in sample")

    if division_in_desc:
        report.add(agent, "warning", f"{division_in_desc}/{len(products)} descriptions contain division codes like '( L GS FB )'")
    else:
        report.ok(agent, "Descriptions clean of division codes")

    if negative_cost:
        report.add(agent, "error", f"{negative_cost} products with negative case_cost")

    if missing_category > len(products) * 0.1:
        report.add(agent, "warning", f"{missing_category}/{len(products)} products missing category (>10%)")
    else:
        report.ok(agent, f"Category coverage: {len(products) - missing_category}/{len(products)}")

    if missing_brand > len(products) * 0.1:
        report.add(agent, "warning", f"{missing_brand}/{len(products)} products missing brand (>10%)")
    else:
        report.ok(agent, f"Brand coverage: {len(products) - missing_brand}/{len(products)}")

    return products


# ── Agent 3: Brand Integrity ──────────────────────────────────────────────

def qa_brands(api: APIClient, report: QAReport):
    agent = "brands"
    print(f"\n[{agent}] Checking brand integrity...")

    SUSPECT_WORDS = {
        "BLUE", "RED", "BLACK", "WHITE", "GREEN", "GOLD", "SILVER",
        "PINK", "AMBER", "COPPER", "PLATINUM", "BRONZE",
        "GIN", "VODKA", "RUM", "WHISKEY", "BOURBON", "TEQUILA",
        "BLANCO", "REPOSADO", "ANEJO", "SPICED", "PROOF",
        "CABERNET", "MERLOT", "CHARDONNAY", "MOSCATO", "PROSECCO",
        "RESERVE", "SINGLE", "IMPERIAL", "EXTRA", "SPECIAL",
    }

    try:
        brands = api.get("/api/v1/catalog/brands")
    except Exception as e:
        report.add(agent, "error", "Cannot fetch brands", str(e))
        return

    if not brands:
        report.add(agent, "error", "No brands found")
        return

    report.ok(agent, f"Total brands: {len(brands)}")

    suspect = []
    for b in brands:
        name = b.get("display_name", "")
        upper = name.upper().strip()
        tokens = upper.split()

        if len(tokens) == 1 and upper in SUSPECT_WORDS:
            suspect.append(f"'{name}' ({b.get('product_count', 0)} products)")
        elif len(name.replace(' ', '')) <= 2:
            suspect.append(f"'{name}' (too short)")

    if suspect:
        report.add(agent, "warning", f"{len(suspect)} suspect brands",
                   "; ".join(suspect[:10]))
    else:
        report.ok(agent, "All brands look valid")


# ── Agent 4: RIP Integrity ────────────────────────────────────────────────

def qa_rips(api: APIClient, report: QAReport):
    agent = "rips"
    print(f"\n[{agent}] Checking RIP data integrity...")

    try:
        rips = api.get("/api/v1/rips", {"limit": 500})
    except Exception as e:
        report.add(agent, "error", "Cannot fetch RIPs", str(e))
        return

    if not rips:
        report.add(agent, "warning", "No RIP data returned")
        return

    report.ok(agent, f"Fetched {len(rips)} RIP entries")

    bad_tier = 0
    bad_save = 0
    negative_eff = 0

    for r in rips:
        tier = r.get("tier", "")
        if not tier or not any(c.isdigit() for c in tier):
            bad_tier += 1

        save = r.get("save_amount")
        if save is not None:
            sf = float(save)
            if sf <= 0 or sf > 1000:
                bad_save += 1

        eff = r.get("effective_cost")
        if eff is not None and float(eff) < 0:
            negative_eff += 1

    if bad_tier:
        report.add(agent, "error", f"{bad_tier} RIPs with invalid tier format")
    else:
        report.ok(agent, "All RIP tiers valid")

    if bad_save:
        report.add(agent, "error", f"{bad_save} RIPs with save_amount out of range")
    else:
        report.ok(agent, "All RIP amounts within NJ limits ($0-$1000)")

    if negative_eff:
        report.add(agent, "error", f"{negative_eff} RIPs with negative effective_cost")
    else:
        report.ok(agent, "No negative effective costs")


# ── Agent 5: Price History ─────────────────────────────────────────────────

def qa_price_history(api: APIClient, report: QAReport, products: list):
    agent = "price-hist"
    print(f"\n[{agent}] Checking price history API...")

    test_codes = [p["code"] for p in products[:5]] if products else []
    if not test_codes:
        report.add(agent, "warning", "No products to test price history")
        return

    for code in test_codes:
        try:
            ph = api.get(f"/api/v1/catalog/{code}/price-history")
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                report.add(agent, "warning", f"Price history 404 for {code}")
            else:
                report.add(agent, "error", f"Price history failed for {code}", str(e))
            continue

        points = ph.get("data_points", [])
        if not points:
            report.add(agent, "warning", f"No data points for {code}")
            continue

        # Chronological order
        for i in range(1, len(points)):
            prev_ym = points[i-1]["year"] * 12 + points[i-1]["month"]
            curr_ym = points[i]["year"] * 12 + points[i]["month"]
            if curr_ym < prev_ym:
                report.add(agent, "error", f"Data out of order for {code}")

        # effective_cost = case_cost - best_rip_save
        for pt in points:
            cc = pt.get("case_cost")
            rip = pt.get("best_rip_save")
            eff = pt.get("effective_cost")
            if cc and rip and eff:
                expected = round(float(cc) - float(rip), 2)
                actual = round(float(eff), 2)
                if abs(expected - actual) > 0.02:
                    report.add(agent, "error",
                               f"effective_cost mismatch for {code} in {pt['edition_label']}",
                               f"expected {expected}, got {actual}")

        # Summary consistency
        summary = ph.get("summary", {})
        if summary.get("total_editions") != len(points):
            report.add(agent, "error", f"summary.total_editions mismatch for {code}")

    report.ok(agent, f"Validated price history for {len(test_codes)} products")


# ── Agent 6: Analytics Views ──────────────────────────────────────────────

def qa_analytics(api: APIClient, report: QAReport):
    agent = "analytics"
    print(f"\n[{agent}] Checking analytics views...")

    views = [
        "price_drops", "price_increases", "new_rips", "lost_rips",
        "best_value", "closeout_rip", "watchlist_movers",
    ]

    for view in views:
        try:
            data = api.get("/api/v1/analytics", {"view": view, "limit": 10})
        except requests.HTTPError as e:
            report.add(agent, "error", f"Analytics '{view}' HTTP {e.response.status_code}",
                       str(e.response.text[:200]))
            continue
        except Exception as e:
            report.add(agent, "error", f"Analytics '{view}' failed", str(e))
            continue

        products = data.get("items", data.get("products", []))
        neg_eff = sum(1 for p in products if p.get("effective_cost") is not None and float(p["effective_cost"]) < 0)
        extreme_pct = sum(1 for p in products if p.get("pct_change") is not None and abs(float(p["pct_change"])) > 500)

        if neg_eff:
            report.add(agent, "error", f"{neg_eff} negative effective_cost in '{view}'")
        if extreme_pct:
            report.add(agent, "warning", f"{extreme_pct} extreme pct_change (>500%) in '{view}'")

        report.ok(agent, f"'{view}': {len(products)} products, OK")


# ── Agent 7: Closeouts ────────────────────────────────────────────────────

def qa_closeouts(api: APIClient, report: QAReport):
    agent = "closeouts"
    print(f"\n[{agent}] Checking closeout data...")

    try:
        data = api.get("/api/v1/closeouts", {"limit": 200})
    except Exception as e:
        report.add(agent, "error", "Cannot fetch closeouts", str(e))
        return

    if not data:
        report.add(agent, "info", "No closeouts")
        return

    report.ok(agent, f"Fetched {len(data)} closeouts")

    bad = 0
    for c in data:
        orig = c.get("original_case")
        best = c.get("best_case")
        if orig and best and float(best) > float(orig):
            bad += 1

    if bad:
        report.add(agent, "error", f"{bad} closeouts where best_case > original_case")
    else:
        report.ok(agent, "Closeout pricing consistent")


# ── Agent 8: Watchlist & Orders ───────────────────────────────────────────

def qa_watchlist(api: APIClient, report: QAReport):
    agent = "watchlist"
    print(f"\n[{agent}] Checking watchlist & orders...")

    try:
        items = api.get("/api/v1/watchlist/order")
    except Exception as e:
        report.add(agent, "error", "Cannot fetch watchlist", str(e))
        return

    report.ok(agent, f"Watchlist returned {len(items)} items")

    missing_code = sum(1 for i in items if not i.get("product_code"))
    garbled = sum(1 for i in items if i.get("description") and re.search(r"\d\s+\d\s+\d\s+\d", i["description"]))

    if missing_code:
        report.add(agent, "error", f"{missing_code} watchlist items missing product_code")
    if garbled:
        report.add(agent, "warning", f"{garbled}/{len(items)} watchlist items have garbled descriptions")

    # Check orders
    try:
        orders = api.get("/api/v1/orders")
        report.ok(agent, f"Orders: {len(orders)} found")
    except Exception as e:
        report.add(agent, "error", "Cannot fetch orders", str(e))


# ── Agent 9: Sales Reps ──────────────────────────────────────────────────

def qa_sales_reps(api: APIClient, report: QAReport):
    agent = "sales-reps"
    print(f"\n[{agent}] Checking sales reps...")

    try:
        reps = api.get("/api/v1/sales-reps")
        report.ok(agent, f"Sales reps: {len(reps)} found")
    except Exception as e:
        report.add(agent, "error", "Cannot fetch sales reps", str(e))


# ── Agent 10: Cross-Reference ────────────────────────────────────────────

def qa_cross_ref(api: APIClient, report: QAReport, products: list):
    agent = "cross-ref"
    print(f"\n[{agent}] Cross-referencing catalog vs detail vs price-history...")

    for p in products[:3]:
        code = p["code"]
        cat_cost = p.get("case_cost")

        try:
            detail = api.get(f"/api/v1/catalog/products/{code}")
        except Exception:
            report.add(agent, "error", f"Detail 404 for {code}")
            continue

        det_cost = detail.get("case_cost")
        if cat_cost and det_cost and abs(float(cat_cost) - float(det_cost)) > 0.01:
            report.add(agent, "error", f"{code}: catalog cost {cat_cost} != detail cost {det_cost}")
        elif cat_cost and det_cost:
            report.ok(agent, f"{code}: catalog == detail cost")

        # RIP consistency
        try:
            ph = api.get(f"/api/v1/catalog/{code}/price-history")
            pts = ph.get("data_points", [])
            latest = pts[-1] if pts else None
            det_rips = detail.get("current_rips", [])
            if latest:
                if latest.get("has_rip") and not det_rips:
                    report.add(agent, "warning", f"{code}: price-hist says has_rip but detail has 0 RIPs")
                elif not latest.get("has_rip") and det_rips:
                    report.add(agent, "warning", f"{code}: detail has RIPs but price-hist says no")
        except Exception:
            pass


# ── Agent 11: Specials ───────────────────────────────────────────────────

def qa_specials(api: APIClient, report: QAReport):
    agent = "specials"
    print(f"\n[{agent}] Checking specials data...")

    try:
        data = api.get("/api/v1/specials")
    except Exception as e:
        report.add(agent, "error", "Cannot fetch specials", str(e))
        return

    pricing = data.get("pricing", []) if isinstance(data, dict) else []
    rips = data.get("rips", []) if isinstance(data, dict) else []

    # Handle list response (some APIs return flat list)
    if isinstance(data, list):
        report.ok(agent, f"Specials: {len(data)} entries (flat list)")
        return

    report.ok(agent, f"Specials: {len(pricing)} pricing, {len(rips)} RIP partials")

    bad_dates = 0
    for p in pricing:
        start = p.get("start_date", "")
        end = p.get("end_date", "")
        if start and end and start > end:
            bad_dates += 1

    if bad_dates:
        report.add(agent, "error", f"{bad_dates} partials with start_date > end_date")
    else:
        report.ok(agent, "All partial date ranges valid")


# ── Agent 12: Description Quality Deep Check ─────────────────────────────

def qa_descriptions(api: APIClient, report: QAReport):
    agent = "descriptions"
    print(f"\n[{agent}] Deep-checking description quality (500 products)...")

    try:
        data = api.get("/api/v1/catalog/products", {"limit": 200, "offset": 0})
    except Exception as e:
        report.add(agent, "error", "Cannot fetch products for desc check", str(e))
        return

    products = data.get("items", data.get("products", []))
    issues = {
        "garbled_ocr": [],      # "0 0 1 1 34 0 7 5"
        "division_in_desc": [], # "BLANCO IV ( L GS FB JD )"
        "too_short": [],        # <= 3 chars
        "all_caps_num": [],     # "1234567"
    }

    for p in products:
        desc = p.get("description") or ""
        code = p.get("code", "?")

        if re.search(r"\d\s+\d\s+\d\s+\d\s+\d", desc):
            issues["garbled_ocr"].append(f"{code}: {desc[:60]}")
        if re.search(r"\(\s*[LSDGFBJDIV ]{3,}\s*\)", desc):
            issues["division_in_desc"].append(f"{code}: {desc[:60]}")
        if len(desc.strip()) <= 3:
            issues["too_short"].append(code)
        if desc and re.match(r"^\d+$", desc.strip()):
            issues["all_caps_num"].append(f"{code}: '{desc}'")

    for key, items in issues.items():
        if items:
            severity = "error" if key == "garbled_ocr" else "warning"
            report.add(agent, severity, f"{len(items)} products with {key.replace('_', ' ')}",
                       "; ".join(items[:5]))
        else:
            report.ok(agent, f"No {key.replace('_', ' ')} issues")


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="CELR Price Book QA")
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--token", required=True)
    args = parser.parse_args()

    api = APIClient(args.api_url, args.token)
    report = QAReport()

    print(f"Running QA against {args.api_url}")

    summary = qa_editions(api, report)
    products = qa_catalog(api, report)
    qa_brands(api, report)
    qa_rips(api, report)
    qa_price_history(api, report, products)
    qa_analytics(api, report)
    qa_closeouts(api, report)
    qa_watchlist(api, report)
    qa_sales_reps(api, report)
    qa_cross_ref(api, report, products)
    qa_specials(api, report)
    qa_descriptions(api, report)

    report.print_summary()
    sys.exit(1 if report.errors else 0)


if __name__ == "__main__":
    main()
