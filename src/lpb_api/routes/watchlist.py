"""Watchlist + notes endpoints (tenant-scoped, audit-logged).

  GET    /api/v1/watchlist                       list items in the default watchlist
  POST   /api/v1/watchlist/items                 add a product to the watchlist
  PATCH  /api/v1/watchlist/items/{product_code}  update target prices
  DELETE /api/v1/watchlist/items/{product_code}  remove from watchlist

  GET    /api/v1/products/{code}/notes           list non-deleted notes for product
  POST   /api/v1/products/{code}/notes           add a note
  PATCH  /api/v1/notes/{id}                      update note body
  DELETE /api/v1/notes/{id}                      soft-delete

Every write logs to ``audit_log``.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from lpb_core.db import get_session
from lpb_core.db.models import (
    AuditLog,
    Distributor,
    Note,
    Product,
    Watchlist,
    WatchlistItem,
)

from .auth import get_current_user

router = APIRouter(tags=["watchlist"])


# ---------------- watchlist ----------------

class WatchlistItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    product_code: str
    product_description: str | None = None
    target_case_price: Decimal | None
    target_btl_price: Decimal | None
    notes: str | None
    created_at: datetime


class WatchlistAddIn(BaseModel):
    code: str
    distributor: str = "nj-allied"
    target_case_price: Decimal | None = None
    target_btl_price: Decimal | None = None
    notes: str | None = None


class WatchlistUpdateIn(BaseModel):
    target_case_price: Decimal | None = None
    target_btl_price: Decimal | None = None
    notes: str | None = None


def _audit(
    session: Session,
    *,
    tenant_id: UUID,
    user_id: UUID,
    entity_table: str,
    entity_id: UUID,
    action: str,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            entity_table=entity_table,
            entity_id=entity_id,
            action=action,
            before=before,
            after=after,
        )
    )


def _resolve_product(session: Session, distributor: str, code: str) -> Product:
    p = session.execute(
        select(Product)
        .join(Distributor, Distributor.id == Product.distributor_id)
        .where(Distributor.slug == distributor, Product.code == code)
    ).scalar_one_or_none()
    if p is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product {distributor}/{code} not found",
        )
    return p


@router.get("/api/v1/watchlist", response_model=list[WatchlistItemOut])
def list_watchlist(
    user: dict = Depends(get_current_user),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
):
    rows = session.execute(
        select(
            WatchlistItem,
            Product.code,
        )
        .join(Product, Product.id == WatchlistItem.product_id)
        .join(Watchlist, Watchlist.id == WatchlistItem.watchlist_id)
        .where(Watchlist.tenant_id == user["tenant_id"])
        .order_by(desc(WatchlistItem.created_at))
    ).all()
    return [
        WatchlistItemOut(
            product_code=code,
            target_case_price=wi.target_case_price,
            target_btl_price=wi.target_btl_price,
            notes=wi.notes,
            created_at=wi.created_at,
        )
        for wi, code in rows
    ]


@router.post(
    "/api/v1/watchlist/items",
    response_model=WatchlistItemOut,
    status_code=status.HTTP_201_CREATED,
)
def add_watchlist_item(
    body: WatchlistAddIn,
    user: dict = Depends(get_current_user),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
):
    product = _resolve_product(session, body.distributor, body.code)
    # Pick the user's default watchlist.
    wl = session.get(Watchlist, user["default_watchlist_id"])
    if wl is None:
        raise HTTPException(status_code=500, detail="Default watchlist missing")

    # Idempotent: if it's already there, update target prices and return.
    existing = session.execute(
        select(WatchlistItem).where(
            WatchlistItem.watchlist_id == wl.id,
            WatchlistItem.product_id == product.id,
        )
    ).scalar_one_or_none()
    def _money(v):
        return str(v) if v is not None else None

    if existing:
        before = {
            "target_case_price": _money(existing.target_case_price),
            "target_btl_price": _money(existing.target_btl_price),
            "notes": existing.notes,
        }
        existing.target_case_price = body.target_case_price
        existing.target_btl_price = body.target_btl_price
        existing.notes = body.notes
        _audit(
            session,
            tenant_id=user["tenant_id"],
            user_id=user["user_id"],
            entity_table="watchlist_items",
            entity_id=existing.id,
            action="update",
            before=before,
            after={"product_code": body.code},
        )
        session.commit()
        return WatchlistItemOut(
            product_code=product.code,
            target_case_price=existing.target_case_price,
            target_btl_price=existing.target_btl_price,
            notes=existing.notes,
            created_at=existing.created_at,
        )

    item = WatchlistItem(
        watchlist_id=wl.id,
        product_id=product.id,
        target_case_price=body.target_case_price,
        target_btl_price=body.target_btl_price,
        notes=body.notes,
    )
    session.add(item)
    session.flush()
    _audit(
        session,
        tenant_id=user["tenant_id"],
        user_id=user["user_id"],
        entity_table="watchlist_items",
        entity_id=item.id,
        action="insert",
        after={"product_code": body.code},
    )
    session.commit()
    return WatchlistItemOut(
        product_code=product.code,
        target_case_price=item.target_case_price,
        target_btl_price=item.target_btl_price,
        notes=item.notes,
        created_at=item.created_at,
    )


@router.patch(
    "/api/v1/watchlist/items/{code}",
    response_model=WatchlistItemOut,
)
def update_watchlist_item(
    code: str,
    body: WatchlistUpdateIn,
    distributor: str = "nj-allied",
    user: dict = Depends(get_current_user),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
):
    product = _resolve_product(session, distributor, code)
    item = session.execute(
        select(WatchlistItem)
        .join(Watchlist, Watchlist.id == WatchlistItem.watchlist_id)
        .where(
            Watchlist.tenant_id == user["tenant_id"],
            WatchlistItem.product_id == product.id,
        )
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Watchlist item not found")

    def _money(v):
        return str(v) if v is not None else None

    before = {
        "target_case_price": _money(item.target_case_price),
        "target_btl_price": _money(item.target_btl_price),
        "notes": item.notes,
    }
    if body.target_case_price is not None:
        item.target_case_price = body.target_case_price
    if body.target_btl_price is not None:
        item.target_btl_price = body.target_btl_price
    if body.notes is not None:
        item.notes = body.notes
    _audit(
        session,
        tenant_id=user["tenant_id"],
        user_id=user["user_id"],
        entity_table="watchlist_items",
        entity_id=item.id,
        action="update",
        before=before,
    )
    session.commit()
    return WatchlistItemOut(
        product_code=product.code,
        target_case_price=item.target_case_price,
        target_btl_price=item.target_btl_price,
        notes=item.notes,
        created_at=item.created_at,
    )


@router.delete(
    "/api/v1/watchlist/items/{code}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_watchlist_item(
    code: str,
    distributor: str = "nj-allied",
    user: dict = Depends(get_current_user),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
):
    product = _resolve_product(session, distributor, code)
    item = session.execute(
        select(WatchlistItem)
        .join(Watchlist, Watchlist.id == WatchlistItem.watchlist_id)
        .where(
            Watchlist.tenant_id == user["tenant_id"],
            WatchlistItem.product_id == product.id,
        )
    ).scalar_one_or_none()
    if item is None:
        return
    _audit(
        session,
        tenant_id=user["tenant_id"],
        user_id=user["user_id"],
        entity_table="watchlist_items",
        entity_id=item.id,
        action="delete",
    )
    session.delete(item)
    session.commit()
    return


# ---------------- notes ----------------

class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    product_code: str
    body: str
    created_at: datetime
    updated_at: datetime


class NoteBody(BaseModel):
    body: str


@router.get("/api/v1/products/{code}/notes", response_model=list[NoteOut])
def list_notes(
    code: str,
    distributor: str = "nj-allied",
    user: dict = Depends(get_current_user),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
):
    product = _resolve_product(session, distributor, code)
    rows = session.execute(
        select(Note)
        .where(
            Note.product_id == product.id,
            Note.tenant_id == user["tenant_id"],
            Note.deleted_at.is_(None),
        )
        .order_by(desc(Note.created_at))
    ).scalars().all()
    return [
        NoteOut(
            id=n.id, product_code=code, body=n.body,
            created_at=n.created_at, updated_at=n.updated_at,
        )
        for n in rows
    ]


@router.post(
    "/api/v1/products/{code}/notes",
    response_model=NoteOut,
    status_code=status.HTTP_201_CREATED,
)
def add_note(
    code: str,
    body: NoteBody,
    distributor: str = "nj-allied",
    user: dict = Depends(get_current_user),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
):
    product = _resolve_product(session, distributor, code)
    if not body.body.strip():
        raise HTTPException(status_code=400, detail="Empty note body")
    note = Note(
        tenant_id=user["tenant_id"],
        product_id=product.id,
        author_user_id=user["user_id"],
        body=body.body,
    )
    session.add(note)
    session.flush()
    _audit(
        session,
        tenant_id=user["tenant_id"],
        user_id=user["user_id"],
        entity_table="notes",
        entity_id=note.id,
        action="insert",
        after={"product_code": code, "body_preview": body.body[:64]},
    )
    session.commit()
    return NoteOut(
        id=note.id, product_code=code, body=note.body,
        created_at=note.created_at, updated_at=note.updated_at,
    )


@router.patch("/api/v1/notes/{note_id}", response_model=NoteOut)
def update_note(
    note_id: UUID,
    body: NoteBody,
    user: dict = Depends(get_current_user),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
):
    note = session.execute(
        select(Note).where(
            Note.id == note_id,
            Note.tenant_id == user["tenant_id"],
            Note.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    before = {"body": note.body}
    note.body = body.body
    _audit(
        session,
        tenant_id=user["tenant_id"],
        user_id=user["user_id"],
        entity_table="notes",
        entity_id=note.id,
        action="update",
        before=before,
    )
    session.commit()
    product_code = session.execute(
        select(Product.code).where(Product.id == note.product_id)
    ).scalar_one()
    return NoteOut(
        id=note.id, product_code=product_code, body=note.body,
        created_at=note.created_at, updated_at=note.updated_at,
    )


@router.delete(
    "/api/v1/notes/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_note(
    note_id: UUID,
    user: dict = Depends(get_current_user),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
):
    note = session.execute(
        select(Note).where(
            Note.id == note_id,
            Note.tenant_id == user["tenant_id"],
            Note.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if note is None:
        return
    note.deleted_at = datetime.utcnow()
    _audit(
        session,
        tenant_id=user["tenant_id"],
        user_id=user["user_id"],
        entity_table="notes",
        entity_id=note.id,
        action="soft_delete",
    )
    session.commit()
    return
