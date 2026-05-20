"""Cross-distributor product linker.

Fetches products from both distributors via the Render API, fuzzy-matches
them by brand + size + description, and POSTs the resulting links back to
a server-side admin endpoint that creates product_links rows and sets
link_id on both Product records.

Usage:
  python -m scripts.link_products --api-url https://lpb-api-41nh.onrender.com --token TOKEN
  python -m scripts.link_products --api-url https://lpb-api-41nh.onrender.com --token TOKEN --dry-run
  python -m scripts.link_products --api-url ... --token ... --threshold 0.70
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
log = logging.getLogger("link_products")

DISTRIBUTORS = ["nj-allied", "nj-fedway"]
PAGE_SIZE = 1000


# ---------------------------------------------------------------------------
# HTTP helpers (matching local_ingest.py pattern)
# ---------------------------------------------------------------------------

def _api_get(url: str, token: str) -> dict:
    """GET a JSON endpoint, return parsed body."""
    req = Request(
        url,
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    try:
        with urlopen(req) as resp:
            return json.loads(resp.read())
    except HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        log.error("API GET error %d: %s  url=%s", e.code, detail, url)
        raise


def _api_post(url: str, token: str, payload: dict) -> dict:
    """POST JSON to an endpoint, return parsed body."""
    body = json.dumps(payload).encode("utf-8")
    req = Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    try:
        with urlopen(req) as resp:
            return json.loads(resp.read())
    except HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        log.error("API POST error %d: %s", e.code, detail)
        raise


# ---------------------------------------------------------------------------
# Fetch all products for a distributor (paginated)
# ---------------------------------------------------------------------------

def _fetch_all_products(api_url: str, token: str, distributor: str) -> list[dict]:
    """Paginate through GET /api/v1/catalog/products for a distributor."""
    all_items: list[dict] = []
    offset = 0
    while True:
        params = urlencode({
            "distributor": distributor,
            "limit": PAGE_SIZE,
            "offset": offset,
        })
        url = f"{api_url}/api/v1/catalog/products?{params}"
        data = _api_get(url, token)
        items = data.get("items", [])
        total = data.get("total", 0)
        all_items.extend(items)
        log.info(
            "  %s: fetched %d/%d (offset=%d)",
            distributor, len(all_items), total, offset,
        )
        if len(all_items) >= total or not items:
            break
        offset += PAGE_SIZE
    return all_items


# ---------------------------------------------------------------------------
# Fuzzy matching
# ---------------------------------------------------------------------------

def _normalise_desc(desc: str | None) -> str:
    """Lowercase, strip whitespace for fuzzy comparison."""
    if not desc:
        return ""
    return " ".join(desc.lower().split())


def _normalise_size(size: str | None) -> str:
    """Normalise size strings: '750ML' and '750 ML' -> '750ml'."""
    if not size:
        return ""
    return size.lower().replace(" ", "")


def _extract_key_words(desc: str) -> set[str]:
    """Extract significant words (3+ chars) from a normalised description."""
    return {w for w in desc.split() if len(w) >= 3}


def _fuzzy_match(
    allied_products: list[dict],
    fedway_products: list[dict],
    threshold: float,
) -> list[dict]:
    """Match products across distributors by size, then fuzzy-match
    descriptions within each size group.

    Most Fedway products lack category_slug and brand_slug, so we group
    by size only. Within each group we require >= 2 shared keywords (3+
    chars) before doing the expensive SequenceMatcher comparison. This
    keeps the search tractable even for large size groups.

    Returns a list of link dicts ready for the API.
    """
    # Index by normalised size (e.g. "750ml")
    allied_by_size: dict[str, list[dict]] = defaultdict(list)
    for p in allied_products:
        ns = _normalise_size(p.get("size"))
        desc = p.get("description") or ""
        if ns and desc:
            allied_by_size[ns].append(p)

    fedway_by_size: dict[str, list[dict]] = defaultdict(list)
    for p in fedway_products:
        ns = _normalise_size(p.get("size"))
        desc = p.get("description") or ""
        if ns and desc:
            fedway_by_size[ns].append(p)

    common_sizes = set(allied_by_size.keys()) & set(fedway_by_size.keys())
    log.info(
        "Size groups: allied=%d, fedway=%d, shared=%d",
        len(allied_by_size), len(fedway_by_size), len(common_sizes),
    )

    links: list[dict] = []
    matched_allied: set[str] = set()
    matched_fedway: set[str] = set()
    comparisons = 0
    MIN_SHARED_KW = 2  # require at least 2 shared keywords

    for size in sorted(common_sizes):
        a_list = allied_by_size[size]
        f_list = fedway_by_size[size]

        # Pre-compute normalised descriptions and keywords
        a_normed = [(a, _normalise_desc(a.get("description")), _extract_key_words(_normalise_desc(a.get("description")))) for a in a_list]
        f_normed = [(f, _normalise_desc(f.get("description")), _extract_key_words(_normalise_desc(f.get("description")))) for f in f_list]

        # Build pairwise scores for pairs sharing >= MIN_SHARED_KW keywords
        pairs: list[tuple[float, dict, dict]] = []
        for a, a_desc, a_kw in a_normed:
            for f, f_desc, f_kw in f_normed:
                if len(a_kw & f_kw) < MIN_SHARED_KW:
                    continue
                comparisons += 1
                ratio = SequenceMatcher(None, a_desc, f_desc).ratio()
                if ratio >= threshold:
                    pairs.append((ratio, a, f))

        # Greedy best-first matching
        pairs.sort(key=lambda x: x[0], reverse=True)
        for ratio, a, f in pairs:
            a_code = a["code"]
            f_code = f["code"]
            if a_code in matched_allied or f_code in matched_fedway:
                continue
            matched_allied.add(a_code)
            matched_fedway.add(f_code)

            a_desc_raw = a.get("description") or ""
            f_desc_raw = f.get("description") or ""
            canonical = a_desc_raw if len(a_desc_raw) >= len(f_desc_raw) else f_desc_raw

            links.append({
                "allied_code": a_code,
                "fedway_code": f_code,
                "confidence": round(ratio, 4),
                "canonical_description": canonical,
                "size": a.get("size"),
                "pack": a.get("pack"),
                "brand_slug": a.get("brand_slug"),
                "category_slug": a.get("category_slug"),
            })

    log.info("Total pairwise comparisons: %d", comparisons)
    return links


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fuzzy-match products across distributors and create product_links"
    )
    parser.add_argument(
        "--api-url",
        default=os.environ.get("LPB_API_URL", ""),
        help="Render API base URL (or LPB_API_URL env var)",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("LPB_ADMIN_TOKEN", "lpb-static-admin-token"),
        help="Admin bearer token (or LPB_ADMIN_TOKEN env var)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.65,
        help="Minimum SequenceMatcher ratio to accept a match (default: 0.65)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute matches but don't POST to the API",
    )
    args = parser.parse_args(argv)

    if not args.api_url:
        print(
            "ERROR: --api-url is required (or set LPB_API_URL env var).\n"
            "  Example: python -m scripts.link_products "
            "--api-url https://lpb-api-41nh.onrender.com --token TOKEN",
            file=sys.stderr,
        )
        return 1

    # ---- Stage 1: Fetch products from both distributors ----
    log.info("Fetching products from both distributors...")
    allied = _fetch_all_products(args.api_url, args.token, "nj-allied")
    fedway = _fetch_all_products(args.api_url, args.token, "nj-fedway")
    log.info("Allied: %d products,  Fedway: %d products", len(allied), len(fedway))

    if not allied or not fedway:
        log.warning("One or both distributors have no products. Nothing to match.")
        return 0

    # ---- Stage 2: Fuzzy match ----
    log.info("Running fuzzy matching (threshold=%.2f)...", args.threshold)
    links = _fuzzy_match(allied, fedway, args.threshold)

    # ---- Stage 3: Summary stats ----
    if links:
        confidences = [lnk["confidence"] for lnk in links]
        avg_conf = sum(confidences) / len(confidences)
        min_conf = min(confidences)
        max_conf = max(confidences)
    else:
        avg_conf = min_conf = max_conf = 0.0

    log.info("=" * 60)
    log.info("SUMMARY")
    log.info("  Allied products:        %d", len(allied))
    log.info("  Fedway products:        %d", len(fedway))
    log.info("  Matches found:          %d", len(links))
    log.info("  Average confidence:     %.4f", avg_conf)
    log.info("  Min confidence:         %.4f", min_conf)
    log.info("  Max confidence:         %.4f", max_conf)
    log.info("=" * 60)

    if not links:
        log.info("No matches found. Done.")
        return 0

    # Show a sample of matches
    log.info("Sample matches (first 10):")
    for lnk in links[:10]:
        log.info(
            "  [%.3f] Allied=%s  Fedway=%s  %s",
            lnk["confidence"],
            lnk["allied_code"],
            lnk["fedway_code"],
            lnk["canonical_description"][:60],
        )

    if args.dry_run:
        log.info("--dry-run: skipping API upload. %d links would be created.", len(links))
        return 0

    # ---- Stage 4: POST to admin endpoint ----
    url = f"{args.api_url}/api/v1/admin/link-products"
    payload = {"links": links}
    payload_size = len(json.dumps(payload))
    log.info("Uploading %d links (%s bytes) to %s ...", len(links), f"{payload_size:,}", url)

    result = _api_post(url, args.token, payload)
    log.info(
        "Done! created=%d, updated=%d, skipped=%d",
        result.get("created", 0),
        result.get("updated", 0),
        result.get("skipped", 0),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
