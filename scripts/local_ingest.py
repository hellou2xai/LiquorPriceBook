"""Local PDF ingest - scrape on your machine, POST to Render API.

Runs pdfplumber locally (unlimited RAM), then sends only the lightweight
structured JSON to the server's /ingest/prescraped endpoint. The Render
instance never touches pdfplumber, so it stays well under 512MB.

Usage:
  python -m scripts.local_ingest <pdf> --api-url https://your-app.onrender.com
  python -m scripts.local_ingest <pdf> --dry-run   # scrape only, no upload

Requires LPB_ADMIN_TOKEN env var (or defaults to 'lpb-static-admin-token').
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

# Add project root to path so templates import works
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
log = logging.getLogger("local_ingest")

_YEAR_MONTH_RE = re.compile(r"(\d{4})[-/_](\d{2})")


def _parse_year_month(
    filename: str, year: int | None, month: int | None
) -> tuple[int, int]:
    if year and month:
        return year, month
    m = _YEAR_MONTH_RE.search(filename)
    if m:
        return int(m.group(1)), int(m.group(2))
    print(
        "ERROR: Could not infer year/month from filename. "
        "Either name the file like '2026-05 Price Book.pdf' or pass --year and --month.",
        file=sys.stderr,
    )
    sys.exit(1)


def _compute_content_hash(pdf_bytes: bytes) -> str:
    return hashlib.sha256(pdf_bytes).hexdigest()


def _scrape_locally(pdf_path: Path) -> dict[str, list[dict]]:
    from templates.NjAllied import scrape_pdf
    results, _diag = scrape_pdf(pdf_path, source_name=pdf_path.name)
    return results


def _post_prescraped(
    api_url: str,
    token: str,
    payload: dict,
) -> dict:
    """POST the prescraped JSON to the Render API and return the response."""
    url = f"{api_url}/api/v1/admin/ingest/prescraped"
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
        log.error("API error %d: %s", e.code, detail)
        raise


def _poll_run(api_url: str, token: str, run_id: str) -> dict:
    """Poll the ingest run until it completes or fails."""
    url = f"{api_url}/api/v1/admin/ingest/runs/{run_id}"
    headers = {"Authorization": f"Bearer {token}"}
    while True:
        req = Request(url, headers=headers)
        with urlopen(req) as resp:
            run = json.loads(resp.read())
        status = run["status"]
        if status == "completed":
            return run
        if status == "failed":
            log.error("Ingest failed: %s", run.get("error"))
            return run
        log.info("  status=%s, waiting...", status)
        time.sleep(3)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scrape a PDF locally and push structured data to the Render API"
    )
    parser.add_argument("pdf", type=Path, help="Path to the PDF file")
    parser.add_argument(
        "-d", "--distributor", default="nj-allied",
        help="Distributor slug (default: nj-allied)",
    )
    parser.add_argument("--year", type=int, default=None, help="Edition year (e.g. 2026)")
    parser.add_argument("--month", type=int, default=None, help="Edition month (1-12)")
    parser.add_argument(
        "--api-url", default=os.environ.get("LPB_API_URL", ""),
        help="Render API base URL (e.g. https://your-app.onrender.com). "
             "Also reads LPB_API_URL env var.",
    )
    parser.add_argument(
        "--token", default=os.environ.get("LPB_ADMIN_TOKEN", "lpb-static-admin-token"),
        help="Admin bearer token (default: LPB_ADMIN_TOKEN env var or 'lpb-static-admin-token')",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Scrape locally but don't upload to the API",
    )
    parser.add_argument(
        "--no-poll", action="store_true",
        help="Don't wait for the ingest to complete — just submit and exit",
    )
    args = parser.parse_args(argv)

    pdf_path: Path = args.pdf
    if not pdf_path.exists():
        print(f"PDF not found: {pdf_path}", file=sys.stderr)
        return 1

    pdf_bytes = pdf_path.read_bytes()
    if not pdf_bytes:
        print("Empty PDF file", file=sys.stderr)
        return 1

    year, month = _parse_year_month(pdf_path.name, args.year, args.month)
    content_hash = _compute_content_hash(pdf_bytes)
    log.info(
        "PDF: %s  (%s bytes, hash=%s)",
        pdf_path.name, f"{len(pdf_bytes):,}", content_hash[:12],
    )
    log.info("Edition: %d-%02d  distributor=%s", year, month, args.distributor)

    # ---- Stage 1: Scrape locally (unlimited RAM) ----
    log.info("Scraping PDF locally...")
    sections = _scrape_locally(pdf_path)
    total_rows = sum(len(v) for v in sections.values())
    for section, rows in sections.items():
        log.info("  %-24s %6d rows", section, len(rows))
    log.info("Scrape complete: %d total rows across %d sections", total_rows, len(sections))

    if args.dry_run:
        log.info("--dry-run: done. No data uploaded.")
        return 0

    # ---- Stage 2: POST to Render API ----
    if not args.api_url:
        print(
            "ERROR: --api-url is required (or set LPB_API_URL env var).\n"
            "  Example: python -m scripts.local_ingest book.pdf "
            "--api-url https://your-app.onrender.com",
            file=sys.stderr,
        )
        return 1

    payload = {
        "distributor": args.distributor,
        "source_filename": pdf_path.name,
        "content_hash": content_hash,
        "year": year,
        "month": month,
        "sections": sections,
    }
    payload_size = len(json.dumps(payload))
    log.info("Uploading %s of structured data to %s ...", f"{payload_size:,} bytes", args.api_url)

    result = _post_prescraped(args.api_url, args.token, payload)
    run_id = result["ingest_run_id"]
    log.info(
        "Accepted! run_id=%s  edition_id=%s  reused=%s",
        run_id, result["book_edition_id"], result["reused_existing_edition"],
    )

    if args.no_poll:
        log.info("--no-poll: exiting. Check status at %s/api/v1/admin/ingest/runs/%s", args.api_url, run_id)
        return 0

    # ---- Stage 3: Poll until done ----
    log.info("Waiting for server-side upserts to finish...")
    run = _poll_run(args.api_url, args.token, run_id)
    if run["status"] == "completed":
        log.info("Ingest complete!")
        for section, count in run.get("rows_by_section", {}).items():
            log.info("  %-24s %6d", section, count)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
