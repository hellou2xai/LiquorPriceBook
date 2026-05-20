"""Sales rep CRUD + order email generation.

  GET    /api/v1/sales-reps          — list reps for tenant
  POST   /api/v1/sales-reps          — create rep
  PATCH  /api/v1/sales-reps/{id}     — update rep
  DELETE /api/v1/sales-reps/{id}     — delete rep
  POST   /api/v1/orders/{id}/email   — generate mailto link data
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from lpb_core.db import get_session
from lpb_core.db.models import (
    Product,
    ProductEdition,
    SalesRep,
    Watchlist,
    WatchlistItem,
)

from .auth import get_current_user

router = APIRouter(prefix="/api/v1", tags=["sales-reps"])


# ── Schemas ──────────────────────────────────────────────────────────────

class SalesRepIn(BaseModel):
    name: str
    email: str
    phone: str | None = None
    division: str | None = None
    notes: str | None = None


class SalesRepOut(BaseModel):
    id: str
    name: str
    email: str
    phone: str | None
    division: str | None
    notes: str | None
    created_at: str
    updated_at: str


class SalesRepUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    division: str | None = None
    notes: str | None = None


class EmailData(BaseModel):
    to: str
    subject: str
    body: str


# ── Helpers ──────────────────────────────────────────────────────────────

def _rep_out(rep: SalesRep) -> SalesRepOut:
    return SalesRepOut(
        id=str(rep.id),
        name=rep.name,
        email=rep.email,
        phone=rep.phone,
        division=rep.division,
        notes=rep.notes,
        created_at=rep.created_at.isoformat(),
        updated_at=rep.updated_at.isoformat(),
    )


# ── CRUD ────────────────────────────────────────────────────────────────

@router.get("/sales-reps", response_model=list[SalesRepOut])
def list_reps(
    division: str | None = Query(None),
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    stmt = (
        select(SalesRep)
        .where(SalesRep.tenant_id == user["tenant_id"])
        .order_by(SalesRep.name)
    )
    if division:
        stmt = stmt.where(SalesRep.division == division)
    reps = session.execute(stmt).scalars().all()
    return [_rep_out(r) for r in reps]


@router.post("/sales-reps", response_model=SalesRepOut, status_code=201)
def create_rep(
    body: SalesRepIn,
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    rep = SalesRep(
        tenant_id=user["tenant_id"],
        name=body.name,
        email=body.email,
        phone=body.phone,
        division=body.division,
        notes=body.notes,
    )
    session.add(rep)
    session.commit()
    session.refresh(rep)
    return _rep_out(rep)


@router.patch("/sales-reps/{rep_id}", response_model=SalesRepOut)
def update_rep(
    rep_id: UUID,
    body: SalesRepUpdate,
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    rep = session.execute(
        select(SalesRep).where(
            SalesRep.id == rep_id,
            SalesRep.tenant_id == user["tenant_id"],
        )
    ).scalar_one_or_none()
    if not rep:
        raise HTTPException(status_code=404, detail="Sales rep not found")

    for field in ("name", "email", "phone", "division", "notes"):
        val = getattr(body, field)
        if val is not None:
            setattr(rep, field, val)
    session.commit()
    session.refresh(rep)
    return _rep_out(rep)


@router.delete("/sales-reps/{rep_id}", status_code=204)
def delete_rep(
    rep_id: UUID,
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    rep = session.execute(
        select(SalesRep).where(
            SalesRep.id == rep_id,
            SalesRep.tenant_id == user["tenant_id"],
        )
    ).scalar_one_or_none()
    if not rep:
        raise HTTPException(status_code=404, detail="Sales rep not found")
    session.delete(rep)
    session.commit()


# ── Email generation ────────────────────────────────────────────────────

@router.post(
    "/orders/{order_id}/email",
    response_model=EmailData,
)
def generate_order_email(
    order_id: UUID,
    rep_id: UUID | None = Query(None),
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Generate email data (to, subject, body) for an order.

    If rep_id is provided, uses that rep's email. Otherwise
    returns empty 'to' for the client to fill in.
    """
    order = session.execute(
        select(Watchlist).where(
            Watchlist.id == order_id,
            Watchlist.tenant_id == user["tenant_id"],
            Watchlist.is_default.is_(False),
        )
    ).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    to_email = ""
    rep_name = ""
    if rep_id:
        rep = session.execute(
            select(SalesRep).where(
                SalesRep.id == rep_id,
                SalesRep.tenant_id == user["tenant_id"],
            )
        ).scalar_one_or_none()
        if rep:
            to_email = rep.email
            rep_name = rep.name

    # Get order items with product info
    items = session.execute(
        select(WatchlistItem)
        .where(WatchlistItem.watchlist_id == order_id)
    ).scalars().all()

    # Build product details
    lines = []
    total_cases = 0
    for item in items:
        pe = session.execute(
            select(
                Product.code,
                ProductEdition.description,
                ProductEdition.size,
                ProductEdition.case_cost,
            )
            .select_from(ProductEdition)
            .join(Product, Product.id == ProductEdition.product_id)
            .where(ProductEdition.product_id == item.product_id)
            .order_by(ProductEdition.id.desc())
            .limit(1)
        ).first()
        if not pe:
            continue
        qty = item.qty_cases or 0
        total_cases += qty
        cost_str = f"${pe.case_cost}" if pe.case_cost else "N/A"
        line_total = (
            f" = ${float(pe.case_cost) * qty:.2f}"
            if pe.case_cost and qty
            else ""
        )
        lines.append(
            f"  {pe.code}  {pe.description or ''}  "
            f"{pe.size or ''}  x{qty} cases  "
            f"@ {cost_str}{line_total}"
        )

    div_str = f" ({order.division})" if order.division else ""
    subject = f"Order: {order.name}{div_str}"

    body_parts = []
    if rep_name:
        body_parts.append(f"Hi {rep_name},\n")
    body_parts.append(
        f"Please find the order details below for "
        f"\"{order.name}\"{div_str}:\n"
    )
    body_parts.append(f"Items ({len(lines)} products, {total_cases} cases):")
    body_parts.append("─" * 60)
    body_parts.extend(lines)
    body_parts.append("─" * 60)

    if order.order_notes:
        body_parts.append(f"\nNotes: {order.order_notes}")

    body_parts.append("\nThank you.")

    return EmailData(
        to=to_email,
        subject=subject,
        body="\n".join(body_parts),
    )
