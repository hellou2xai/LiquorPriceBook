"""Local PDF ingest - scrape on your machine, push to the remote DB.

Bypasses the 512MB Render instance entirely. Runs the same pipeline as the
server-side ingest but uses your local RAM for pdfplumber parsing.

Usage:
  python -m scripts.local_ingest <pdf> --distributor nj-allied [--year 2026 --month 5]

Requires DATABASE_URL in .env (or as an env var) pointing at the Render
Postgres instance.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path so imports work when running as `python -m scripts.local_ingest`
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

import re
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from lpb_core.db import SessionLocal
from lpb_core.db.models import BookEdition, Distributor, IngestRun
from lpb_worker.ingestion.pipeline import compute_content_hash, run_ingest

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ingest a price-book PDF locally and push to the remote DB"
    )
    parser.add_argument("pdf", type=Path, help="Path to the PDF file")
    parser.add_argument(
        "-d", "--distributor", default="nj-allied", help="Distributor slug (default: nj-allied)"
    )
    parser.add_argument("--year", type=int, default=None, help="Edition year (e.g. 2026)")
    parser.add_argument("--month", type=int, default=None, help="Edition month (1-12)")
    parser.add_argument(
        "--dry-run", action="store_true", help="Scrape locally but don't touch the DB"
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
    content_hash = compute_content_hash(pdf_bytes)
    log.info("PDF: %s  (%s bytes, hash=%s)", pdf_path.name, f"{len(pdf_bytes):,}", content_hash[:12])
    log.info("Edition: %d-%02d  distributor=%s", year, month, args.distributor)

    if args.dry_run:
        log.info("--dry-run: scraping locally only (no DB writes)")
        from templates.NjAllied import scrape_pdf

        results, diag = scrape_pdf(pdf_path, source_name=pdf_path.name)
        for section, rows in results.items():
            log.info("  %-24s %6d rows", section, len(rows))
        log.info("Dry run complete. No data pushed to DB.")
        return 0

    # ---- Connect to DB and run the full pipeline ----
    with SessionLocal() as session:
        # 1. Find the distributor
        dist = session.execute(
            select(Distributor).where(Distributor.slug == args.distributor)
        ).scalar_one_or_none()
        if dist is None:
            print(f"Unknown distributor slug: {args.distributor}", file=sys.stderr)
            return 1

        # 2. Idempotent BookEdition upsert (same logic as the API endpoint)
        edition = session.execute(
            select(BookEdition).where(
                BookEdition.distributor_id == dist.id,
                BookEdition.content_hash == content_hash,
            )
        ).scalar_one_or_none()

        if edition is not None:
            log.info("Reusing existing BookEdition %s (same content hash)", edition.id)
            if edition.pdf_bytes is None:
                edition.pdf_bytes = pdf_bytes
                session.flush()
        else:
            edition = BookEdition(
                distributor_id=dist.id,
                year=year,
                month=month,
                source_filename=pdf_path.name,
                content_hash=content_hash,
                pdf_bytes=pdf_bytes,
            )
            session.add(edition)
            session.flush()
            log.info("Created BookEdition %s", edition.id)

        # 3. Create IngestRun
        run = IngestRun(book_edition_id=edition.id, status="pending")
        session.add(run)
        session.commit()
        session.refresh(run)
        log.info("Created IngestRun %s", run.id)

        # 4. Run the pipeline (locally, with full RAM)
        log.info("Starting ingest pipeline...")
        try:
            rows_by_section = run_ingest(session, run.id)
        except Exception:
            log.exception("Pipeline failed!")
            # Mark run as failed
            run_obj = session.get(IngestRun, run.id)
            if run_obj:
                run_obj.status = "failed"
                run_obj.finished_at = datetime.now(UTC)
                session.commit()
            return 1

        log.info("Ingest complete!")
        for section, count in rows_by_section.items():
            log.info("  %-24s %6d", section, count)

    return 0


if __name__ == "__main__":
    sys.exit(main())
