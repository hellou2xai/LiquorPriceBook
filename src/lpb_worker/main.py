"""Worker entry point. Polls ``ingest_runs`` for pending jobs and processes them.

Started by Render with:
    python -m lpb_worker.main
"""

import logging
import signal
import sys
import time
from datetime import UTC, datetime

import sentry_sdk
from sqlalchemy import select, update

from lpb_core.db import SessionLocal
from lpb_core.db.models import IngestRun
from lpb_core.settings import settings

POLL_INTERVAL_SECONDS = 5

log = logging.getLogger("lpb_worker")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
)

_should_stop = False


def _handle_signal(signum, _frame) -> None:
    global _should_stop
    log.info("received signal %s, draining and shutting down", signum)
    _should_stop = True


def _init_observability() -> None:
    if settings.sentry_dsn:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.app_env,
            traces_sample_rate=0.05 if settings.is_production else 1.0,
        )


def claim_next_run() -> IngestRun | None:
    """Atomically pick up the next pending ingest run."""
    with SessionLocal() as session:
        stmt = (
            select(IngestRun)
            .where(IngestRun.status == "pending")
            .order_by(IngestRun.created_at.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        run = session.execute(stmt).scalar_one_or_none()
        if run is None:
            return None
        session.execute(
            update(IngestRun)
            .where(IngestRun.id == run.id)
            .values(status="running", started_at=datetime.now(UTC))
        )
        session.commit()
        session.refresh(run)
        return run


def process_ingest_run(run: IngestRun) -> None:
    """Run the ingestion pipeline for one ``IngestRun``.

    Placeholder for now - the real pipeline (PDF -> staging -> cleaning ->
    final tables -> materialised views -> alert evaluation) lands in week 3-4.
    """
    log.info("processing ingest run id=%s book_edition_id=%s",
             run.id, run.book_edition_id)
    with SessionLocal() as session:
        session.execute(
            update(IngestRun)
            .where(IngestRun.id == run.id)
            .values(
                status="completed",
                finished_at=datetime.now(UTC),
            )
        )
        session.commit()


def main() -> int:
    _init_observability()
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    log.info("worker started, polling every %ss", POLL_INTERVAL_SECONDS)

    while not _should_stop:
        try:
            run = claim_next_run()
            if run is None:
                time.sleep(POLL_INTERVAL_SECONDS)
                continue
            try:
                process_ingest_run(run)
            except Exception as exc:  # noqa: BLE001
                log.exception("ingest run failed id=%s", run.id)
                sentry_sdk.capture_exception(exc)
                with SessionLocal() as session:
                    session.execute(
                        update(IngestRun)
                        .where(IngestRun.id == run.id)
                        .values(
                            status="failed",
                            finished_at=datetime.now(UTC),
                            error={"type": type(exc).__name__, "message": str(exc)},
                        )
                    )
                    session.commit()
        except Exception as exc:  # noqa: BLE001
            log.exception("worker loop error")
            sentry_sdk.capture_exception(exc)
            time.sleep(POLL_INTERVAL_SECONDS)

    log.info("worker exited cleanly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
