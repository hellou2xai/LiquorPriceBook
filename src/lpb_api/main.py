"""FastAPI application entry point.

Started by Render with:
    uvicorn lpb_api.main:app --host 0.0.0.0 --port $PORT

Routes are added under ``/api/v1`` and grouped per resource. Health endpoints
live at the root so Render's healthCheckPath works without an auth round-trip.
"""

from contextlib import asynccontextmanager
from datetime import UTC

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from lpb_api.routes import ai as ai_routes
from lpb_api.routes import auth as auth_routes
from lpb_api.routes import catalog as catalog_routes
from lpb_api.routes import ingest as ingest_routes
from lpb_api.routes import insights as insights_routes
from lpb_api.routes import watchlist as watchlist_routes
from lpb_core.settings import settings


def _init_sentry() -> None:
    if settings.sentry_dsn:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.app_env,
            traces_sample_rate=0.05 if settings.is_production else 1.0,
        )


def _recover_orphaned_ingest_runs() -> None:
    """If the process restarted while ingests were active, two failure modes:

      * status='running' - the worker died mid-scrape. Mark failed so the
        UI doesn't spin forever; admin can re-upload or hit the retry
        endpoint.
      * status='pending' for more than 60 seconds - the BackgroundTask
        either never fired (process crashed before the task was scheduled)
        or fired but its worker has long died. Re-enqueue it.

    Safe to call repeatedly; idempotent.
    """
    import logging
    from datetime import datetime, timedelta

    from sqlalchemy import select, update

    from lpb_core.db import SessionLocal
    from lpb_core.db.models import IngestRun

    log = logging.getLogger("lpb_api.startup")
    try:
        with SessionLocal() as session:
            now = datetime.now(UTC)
            # 1. Bury 'running' orphans.
            res_running = session.execute(
                update(IngestRun)
                .where(IngestRun.status == "running")
                .values(
                    status="failed",
                    finished_at=now,
                    error={"reason": "interrupted by process restart"},
                )
            )
            if res_running.rowcount:
                log.warning("buried %d orphaned 'running' runs", res_running.rowcount)
            # 2. Re-enqueue stuck 'pending' rows. We can't fire a
            # FastAPI BackgroundTask from here (no request scope), so we
            # spawn a thread per stuck run. They share the same process.
            stuck = session.execute(
                select(IngestRun.id).where(
                    IngestRun.status == "pending",
                    IngestRun.created_at < now - timedelta(seconds=60),
                )
            ).scalars().all()
            session.commit()

        if stuck:
            import threading

            from lpb_api.routes.ingest import _run_ingest_background

            log.warning("re-enqueuing %d stuck 'pending' runs", len(stuck))
            for run_id in stuck:
                threading.Thread(
                    target=_run_ingest_background, args=(run_id,), daemon=True,
                ).start()
    except Exception:  # noqa: BLE001
        log.exception("could not recover orphaned ingest runs")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _init_sentry()
    _recover_orphaned_ingest_runs()
    yield


app = FastAPI(
    title="LiquorPriceBook API",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)


# ----- CORS (web origin only) -----
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["*"],
)


# ----- health endpoints -----
@app.get("/healthz", tags=["meta"])
def healthz() -> dict:
    """Liveness probe. Returns 200 if the process is up."""
    return {"status": "ok", "env": settings.app_env}


@app.get("/readyz", tags=["meta"])
def readyz() -> dict:
    """Readiness probe. Checks the DB is reachable."""
    from sqlalchemy import text

    from lpb_core.db import engine

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:  # noqa: BLE001 - we want to capture any DB failure
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "db": "up" if db_ok else "down",
    }


app.include_router(auth_routes.router)
app.include_router(ingest_routes.router)
app.include_router(catalog_routes.router)
app.include_router(watchlist_routes.router)
app.include_router(insights_routes.router)
app.include_router(ai_routes.router)

# Later routers (admin tools for AI-C alert configs) will land here:
# from lpb_api.routes import catalog, watchlists, alerts, ingest
# app.include_router(catalog.router)
# ...
