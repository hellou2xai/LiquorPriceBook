"""Admin ingest endpoints.

  POST /api/v1/admin/ingest                  upload a PDF, enqueue an ingest run
  GET  /api/v1/admin/ingest/runs             list recent runs
  GET  /api/v1/admin/ingest/runs/{run_id}    detailed status of one run
  GET  /api/v1/admin/distributors            list distributors (for the upload form)

PDFs land in ``book_editions.pdf_bytes`` so we don't need an object-storage
dependency in MVP. The actual scrape + cleaning runs in-process via FastAPI
BackgroundTasks (so we don't need to pay for a separate worker service).
The IngestRun row tracks status; the UI polls /ingest/runs until completed.

In Week 11 we'll add back a real worker service when alert evaluation arrives.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from pydantic import BaseModel, ConfigDict
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from lpb_core.db import SessionLocal, get_session
from lpb_core.db.models import BookEdition, Distributor, IngestRun
from lpb_worker.ingestion.pipeline import compute_content_hash, run_ingest

from .auth import get_current_user

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

# Filename like "2026-05 Price Book.pdf" or "2026-05" anywhere -> (2026, 5)
_YEAR_MONTH_RE = re.compile(r"(\d{4})[-/_](\d{2})")
_MAX_PDF_BYTES = 25 * 1024 * 1024   # 25MB ceiling


# ---------- response shapes -----------------------------------------------

class DistributorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    slug: str
    name: str
    state: str


class IngestRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    book_edition_id: UUID
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    rows_by_section: dict
    error: dict | None
    created_at: datetime


class IngestEnqueueResult(BaseModel):
    ingest_run_id: UUID
    book_edition_id: UUID
    distributor_slug: str
    year: int
    month: int
    content_hash: str
    reused_existing_edition: bool


# ---------- helpers --------------------------------------------------------

def _parse_year_month(filename: str, override_year: int | None,
                      override_month: int | None) -> tuple[int, int]:
    if override_year and override_month:
        return override_year, override_month
    m = _YEAR_MONTH_RE.search(filename)
    if m:
        return int(m.group(1)), int(m.group(2))
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            "Could not infer year/month from filename. Either name the file like "
            "'2026-05 Price Book.pdf' or pass year and month explicitly."
        ),
    )


# ---------- routes ---------------------------------------------------------

@router.get("/distributors", response_model=list[DistributorOut])
def list_distributors(
    user: dict = Depends(get_current_user),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
):
    rows = session.execute(
        select(Distributor).where(Distributor.is_active.is_(True)).order_by(Distributor.name)
    ).scalars().all()
    return rows


def _run_ingest_background(ingest_run_id) -> None:
    """Open a fresh session and run the ingest pipeline. Used as a
    FastAPI BackgroundTask so the HTTP request returns immediately
    with 202 while the actual scraping happens behind the scenes.

    We open our own session because the request-scoped session has
    already been closed by the time BackgroundTasks fires.
    """
    import logging
    log = logging.getLogger("lpb_api.ingest")
    try:
        with SessionLocal() as bg_session:
            run_ingest(bg_session, ingest_run_id)
    except Exception as exc:  # noqa: BLE001 - we want to catch every failure mode
        log.exception("background ingest failed run_id=%s", ingest_run_id)
        # Mark the run failed so the UI doesn't spin forever.
        from datetime import datetime

        from sqlalchemy import update

        try:
            with SessionLocal() as cleanup:
                cleanup.execute(
                    update(IngestRun)
                    .where(IngestRun.id == ingest_run_id)
                    .values(
                        status="failed",
                        finished_at=datetime.now(UTC),
                        error={"type": type(exc).__name__, "message": str(exc)},
                    )
                )
                cleanup.commit()
        except Exception:  # noqa: BLE001
            log.exception("could not mark run failed run_id=%s", ingest_run_id)


@router.post(
    "/ingest",
    response_model=IngestEnqueueResult,
    status_code=status.HTTP_202_ACCEPTED,
)
async def enqueue_ingest(
    background_tasks: BackgroundTasks,
    pdf: Annotated[UploadFile, File(description="The price-book PDF to ingest")],
    distributor: Annotated[str, Form(description="Distributor slug, e.g. nj-allied")],
    year: Annotated[int | None, Form()] = None,
    month: Annotated[int | None, Form()] = None,
    user: dict = Depends(get_current_user),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
):
    # 1. Read + validate the upload
    if not pdf.filename or not pdf.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Expected a .pdf file",
        )
    pdf_bytes = await pdf.read()
    if not pdf_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file",
        )
    if len(pdf_bytes) > _MAX_PDF_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"PDF exceeds {_MAX_PDF_BYTES // 1024 // 1024}MB ceiling",
        )

    # 2. Find the distributor
    dist = session.execute(
        select(Distributor).where(Distributor.slug == distributor)
    ).scalar_one_or_none()
    if dist is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown distributor slug: {distributor}",
        )

    parsed_year, parsed_month = _parse_year_month(pdf.filename, year, month)
    content_hash = compute_content_hash(pdf_bytes)

    # 3. Idempotency: reuse an existing edition with the same content_hash
    edition = session.execute(
        select(BookEdition).where(
            BookEdition.distributor_id == dist.id,
            BookEdition.content_hash == content_hash,
        )
    ).scalar_one_or_none()
    reused = edition is not None
    if edition is None:
        edition = BookEdition(
            distributor_id=dist.id,
            year=parsed_year,
            month=parsed_month,
            source_filename=pdf.filename,
            content_hash=content_hash,
            pdf_bytes=pdf_bytes,
        )
        session.add(edition)
        session.flush()
    else:
        # Re-upload of the same hash: re-attach bytes (cheap) so re-ingest works.
        if edition.pdf_bytes is None:
            edition.pdf_bytes = pdf_bytes
            session.flush()

    # 4. Create a fresh ingest_run and schedule it to run in-process
    #    via FastAPI BackgroundTasks (no separate worker service needed).
    run = IngestRun(book_edition_id=edition.id, status="pending")
    session.add(run)
    session.commit()
    session.refresh(run)

    background_tasks.add_task(_run_ingest_background, run.id)

    return IngestEnqueueResult(
        ingest_run_id=run.id,
        book_edition_id=edition.id,
        distributor_slug=dist.slug,
        year=parsed_year,
        month=parsed_month,
        content_hash=content_hash,
        reused_existing_edition=reused,
    )


@router.get("/ingest/runs", response_model=list[IngestRunOut])
def list_ingest_runs(
    limit: int = 50,
    user: dict = Depends(get_current_user),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
):
    limit = max(1, min(limit, 200))
    rows = session.execute(
        select(IngestRun).order_by(desc(IngestRun.created_at)).limit(limit)
    ).scalars().all()
    return rows


@router.get("/ingest/runs/{run_id}", response_model=IngestRunOut)
def get_ingest_run(
    run_id: UUID,
    user: dict = Depends(get_current_user),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
):
    run = session.get(IngestRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return run
