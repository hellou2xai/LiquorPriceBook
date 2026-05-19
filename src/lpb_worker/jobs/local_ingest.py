"""Local-only CLI: ingest a PDF straight from disk against the configured DB.

    python -m lpb_worker.jobs.local_ingest "path/to/2026-05 Price Book.pdf" --distributor nj-allied

Used for verifying the ingest pipeline end-to-end without standing up the API.
Reads the PDF, computes content_hash, upserts a BookEdition + IngestRun row,
then runs the pipeline inline.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from lpb_core.db import SessionLocal
from lpb_core.db.models import BookEdition, Distributor, IngestRun
from lpb_worker.ingestion.pipeline import compute_content_hash, run_ingest

log = logging.getLogger("lpb_local_ingest")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")


_YEAR_MONTH_RE = re.compile(r"(\d{4})-(\d{2})")


def _parse_year_month(filename: str) -> tuple[int, int]:
    m = _YEAR_MONTH_RE.search(filename)
    if not m:
        raise SystemExit(f"Cannot derive year/month from filename: {filename}")
    return int(m.group(1)), int(m.group(2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path, help="Path to the price-book PDF")
    parser.add_argument(
        "--distributor", default="nj-allied",
        help="Distributor slug (default: nj-allied)",
    )
    args = parser.parse_args(argv)

    if not args.pdf.exists():
        print(f"PDF not found: {args.pdf}", file=sys.stderr)
        return 2

    pdf_bytes = args.pdf.read_bytes()
    content_hash = compute_content_hash(pdf_bytes)
    year, month = _parse_year_month(args.pdf.name)

    with SessionLocal() as session:
        dist = session.execute(
            select(Distributor).where(Distributor.slug == args.distributor)
        ).scalar_one_or_none()
        if dist is None:
            print(f"distributor not seeded: {args.distributor}", file=sys.stderr)
            return 2

        # Idempotent: re-use the existing edition if content_hash matches.
        edition = session.execute(
            select(BookEdition).where(
                BookEdition.distributor_id == dist.id,
                BookEdition.content_hash == content_hash,
            )
        ).scalar_one_or_none()

        if edition is None:
            edition = BookEdition(
                distributor_id=dist.id,
                year=year,
                month=month,
                source_filename=args.pdf.name,
                content_hash=content_hash,
                pdf_bytes=pdf_bytes,
            )
            session.add(edition)
            session.flush()
            log.info("created book_edition id=%s %s-%02d", edition.id, year, month)
        else:
            # If a prior run cleared pdf_bytes (e.g. test) re-attach them.
            if edition.pdf_bytes is None:
                edition.pdf_bytes = pdf_bytes
                session.flush()
            log.info("reusing book_edition id=%s %s-%02d", edition.id, year, month)

        run = IngestRun(
            book_edition_id=edition.id,
            status="running",
            started_at=datetime.now(UTC),
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        log.info("created ingest_run id=%s", run.id)

    # Pipeline opens its own session and commits.
    with SessionLocal() as session:
        rows = run_ingest(session, run.id)

    print("ingest complete; rows_by_section:")
    for k, v in rows.items():
        print(f"  {k:24s} {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
