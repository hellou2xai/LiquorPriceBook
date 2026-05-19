"""FastAPI application entry point.

Started by Render with:
    uvicorn lpb_api.main:app --host 0.0.0.0 --port $PORT

Routes are added under ``/api/v1`` and grouped per resource. Health endpoints
live at the root so Render's healthCheckPath works without an auth round-trip.
"""

from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from lpb_api.routes import auth as auth_routes
from lpb_api.routes import ingest as ingest_routes
from lpb_core.settings import settings


def _init_sentry() -> None:
    if settings.sentry_dsn:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.app_env,
            traces_sample_rate=0.05 if settings.is_production else 1.0,
        )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _init_sentry()
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

# More routers will be wired here as they come online:
# from lpb_api.routes import catalog, watchlists, alerts, ingest
# app.include_router(catalog.router)
# ...
