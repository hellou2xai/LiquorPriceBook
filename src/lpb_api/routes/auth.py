"""Interim static-credential auth.

This module accepts a single hardcoded ``admin / admin`` pair and returns a
fixed bearer token. It exists so the rest of the app can be built and demoed
without Clerk wired up yet. When real auth lands (week ~11+), swap this
module's implementation for Clerk JWT verification - the FastAPI dependency
contract (`get_current_user`) stays the same.

Configuration via env vars (optional, default admin/admin):
    LPB_ADMIN_USERNAME, LPB_ADMIN_PASSWORD, LPB_ADMIN_TOKEN

NEVER ship this static mode to a real customer-facing production tenant.
"""

import os
import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

# Seeded by migration 0004. The static-auth gate hands these back so the
# rest of the app can attribute writes to a real tenant + user without
# needing Clerk wired up.
DEFAULT_TENANT_ID = UUID("00000000-0000-0000-0000-00000000a001")
DEFAULT_USER_ID = UUID("00000000-0000-0000-0000-00000000a002")
DEFAULT_WATCHLIST_ID = UUID("00000000-0000-0000-0000-00000000a003")

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _admin_username() -> str:
    return os.environ.get("LPB_ADMIN_USERNAME", "admin")


def _admin_password() -> str:
    return os.environ.get("LPB_ADMIN_PASSWORD", "admin")


def _admin_token() -> str:
    """The single fixed bearer token returned on successful login."""
    return os.environ.get("LPB_ADMIN_TOKEN", "lpb-static-admin-token")


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    username: str


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest) -> LoginResponse:
    # constant-time comparison to avoid timing leaks
    user_ok = secrets.compare_digest(body.username, _admin_username())
    pass_ok = secrets.compare_digest(body.password, _admin_password())
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    return LoginResponse(token=_admin_token(), username=body.username)


def get_current_user(request: Request) -> dict:
    """Tiny dependency that gates protected routes.

    Replaceable: the signature returns a dict with at least ``username``.
    Future Clerk implementation returns the same shape plus tenant_id/user_id.
    """
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )
    token = header[7:].strip()
    if not secrets.compare_digest(token, _admin_token()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )
    return {
        "username": _admin_username(),
        "role": "admin",
        "user_id": DEFAULT_USER_ID,
        "tenant_id": DEFAULT_TENANT_ID,
        "default_watchlist_id": DEFAULT_WATCHLIST_ID,
    }


@router.get("/me")
def me(user: dict = Depends(get_current_user)) -> dict:  # noqa: B008 - FastAPI idiom
    """Echoes the current user. Handy for client-side session validation."""
    return user
