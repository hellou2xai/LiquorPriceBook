"""Named order management endpoints.

Orders are non-default watchlists with division, status, qty tracking,
and payment analysis.

  GET    /api/v1/orders                         list orders
  POST   /api/v1/orders                         create order
  GET    /api/v1/orders/{id}                    order detail + analytics
  PATCH  /api/v1/orders/{id}                    update order
  DELETE /api/v1/orders/{id}                    delete draft order
  POST   /api/v1/orders/{id}/items              add item with qty
  PATCH  /api/v1/orders/{id}/items/{code}       update item qty/notes/tier
  DELETE /api/v1/orders/{id}/items/{code}       remove item
  POST   /api/v1/orders/{id}/copy-from-watchlist copy tracked products in
  POST   /api/v1/orders/{id}/submit             finalize order
  GET    /api/v1/orders/{id}/export             export xlsx
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, asc, desc, func, select
from sqlalchemy.orm import Session

from lpb_core.db import get_session
from lpb_core.db.models import (
    AuditLog,
    Brand,
    Category,
    Distributor,
    InventoryReduction,
    PartialsPricing,
    Product,
    ProductEdition,
    RipOffer,
    Watchlist,
    WatchlistItem,
)

from .auth import get_current_user
from .catalog import _current_edition

router = APIRouter(tags=["orders"])

VALID_DIVISIONS = {"L", "S", "D", "GS", "FB", "JD", "IV"}


# ── Schemas ──────────────────────────────────────────────────────────────

class OrderCreateIn(BaseModel):
    name: str
    division: str | None = None
    order_notes: str | None = None

class OrderUpdateIn(BaseModel):
    name: str | None = None
    division: str | None = None
    status: str | None = None
    order_notes: str | None = None

class OrderItemAddIn(BaseModel):
    code: str
    distributor: str = "nj-allied"
    qty_cases: int = 0
    qty_bottles: int = 0
    selected_rip_tier: str | None = None
    notes: str | None = None

class OrderItemUpdateIn(BaseModel):
    qty_cases: int | None = None
    qty_bottles: int | None = None
    selected_rip_tier: str | None = None
    notes: str | None = None

class OrderSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    division: str | None = None
    status: str
    order_notes: str | None = None
    item_count: int = 0
    total_cases: int = 0
    total_bottles: int = 0
    invoice_total: str | None = None
    rip_rebate_total: str | None = None
    effective_total: str | None = None
    created_at: str
    updated_at: str
    submitted_at: str | None = None
    hidden_at: str | None = None

class RipTierOut(BaseModel):
    tier: str
    tier_cases: int
    save_amount: str
    case_price: str | None = None
    btl_price: str | None = None

class RecommendationOut(BaseModel):
    type: str  # defer, closeout, rip_optimizer, special
    message: str
    priority: str = "info"  # info, warning, action

class OrderLineOut(BaseModel):
    product_code: str
    description: str | None = None
    size: str | None = None
    pack: int | None = None
    category_slug: str | None = None
    category_display: str | None = None
    brand_slug: str | None = None
    brand_display: str | None = None
    divisions: str | None = None
    case_cost: str | None = None
    btl_cost: str | None = None
    qty_cases: int = 0
    qty_bottles: int = 0
    selected_rip_tier: str | None = None
    notes: str | None = None
    # RIP info
    has_rip: bool = False
    rip_tiers: list[RipTierOut] = []
    best_rip_save: str | None = None
    # Payment breakdown per line
    line_invoice: str | None = None  # full case_cost * qty
    line_rip_rebate: str | None = None  # rebate cheque later
    line_effective: str | None = None  # invoice - rebate
    # Recommendations
    recommendations: list[RecommendationOut] = []
    is_closeout: bool = False

class PaymentCategoryBreakdown(BaseModel):
    category: str
    invoice: str
    rebate: str
    effective: str
    item_count: int

class PaymentAnalysisOut(BaseModel):
    invoice_total: str  # Payment Needed Now
    rip_rebate_total: str  # RIP Back Later
    effective_total: str  # Net effective cost
    rip_pct_of_order: str | None = None
    by_category: list[PaymentCategoryBreakdown] = []

class OrderDetailOut(BaseModel):
    id: str
    name: str
    division: str | None = None
    status: str
    order_notes: str | None = None
    created_at: str
    updated_at: str
    submitted_at: str | None = None
    items: list[OrderLineOut] = []
    payment: PaymentAnalysisOut
    recommendations: list[RecommendationOut] = []


# ── Helpers ──────────────────────────────────────────────────────────────

def _audit(
    session, *, tenant_id, user_id, entity_table,
    entity_id, action, before=None, after=None,
):
    session.add(AuditLog(
        tenant_id=tenant_id, user_id=user_id,
        entity_table=entity_table, entity_id=entity_id,
        action=action, before=before, after=after,
    ))


def _get_order(session: Session, order_id: UUID, tenant_id: UUID) -> Watchlist:
    wl = session.get(Watchlist, order_id)
    if wl is None or wl.tenant_id != tenant_id or wl.is_default:
        raise HTTPException(status_code=404, detail="Order not found")
    return wl


def _resolve_product(session: Session, distributor: str, code: str) -> Product:
    p = session.execute(
        select(Product)
        .join(Distributor, Distributor.id == Product.distributor_id)
        .where(Distributor.slug == distributor, Product.code == code)
    ).scalar_one_or_none()
    if p is None:
        raise HTTPException(status_code=404, detail=f"Product {distributor}/{code} not found")
    return p


def _money(v) -> str | None:
    if v is None:
        return None
    return str(round(float(v), 2))


# ── CRUD ─────────────────────────────────────────────────────────────────

@router.get("/api/v1/orders", response_model=list[OrderSummaryOut])
def list_orders(
    status_filter: str | None = Query(None, alias="status"),
    division: str | None = Query(None),
    include_hidden: bool = Query(False),
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    stmt = (
        select(Watchlist)
        .where(
            Watchlist.tenant_id == user["tenant_id"],
            Watchlist.is_default == False,  # noqa: E712
        )
        .order_by(desc(Watchlist.updated_at))
    )
    if not include_hidden:
        stmt = stmt.where(Watchlist.hidden_at == None)  # noqa: E711
    if status_filter:
        stmt = stmt.where(Watchlist.status == status_filter)
    if division:
        stmt = stmt.where(Watchlist.division == division)

    orders = session.execute(stmt).scalars().all()

    # Bulk-fetch item counts and qty totals
    order_ids = [o.id for o in orders]
    if not order_ids:
        return []

    item_stats = {}
    if order_ids:
        stats_rows = session.execute(
            select(
                WatchlistItem.watchlist_id,
                func.count().label("cnt"),
                func.coalesce(func.sum(WatchlistItem.qty_cases), 0).label("total_cases"),
                func.coalesce(func.sum(WatchlistItem.qty_bottles), 0).label("total_bottles"),
            )
            .where(WatchlistItem.watchlist_id.in_(order_ids))
            .group_by(WatchlistItem.watchlist_id)
        ).all()
        for r in stats_rows:
            item_stats[r.watchlist_id] = (r.cnt, r.total_cases, r.total_bottles)

    # Compute invoice totals per order (case_cost * qty_cases + btl_cost * qty_bottles)
    # Use the distributor from the product's distributor_id; default to nj-allied
    edition = _current_edition(session, "nj-allied")  # TODO: per-order distributor
    invoice_by_order: dict[UUID, Decimal] = defaultdict(lambda: Decimal("0"))
    rebate_by_order: dict[UUID, Decimal] = defaultdict(lambda: Decimal("0"))
    if order_ids:
        cost_rows = session.execute(
            select(
                WatchlistItem.watchlist_id,
                WatchlistItem.qty_cases,
                WatchlistItem.qty_bottles,
                ProductEdition.case_cost,
                ProductEdition.btl_cost,
                ProductEdition.id.label("pe_id"),
            )
            .select_from(WatchlistItem)
            .join(Product, Product.id == WatchlistItem.product_id)
            .outerjoin(ProductEdition, and_(
                ProductEdition.product_id == Product.id,
                ProductEdition.book_edition_id == edition.id,
            ))
            .where(WatchlistItem.watchlist_id.in_(order_ids))
        ).all()
        # Collect PE IDs for RIP lookup
        pe_ids = [r.pe_id for r in cost_rows if r.pe_id]
        rips_by_pe: dict[UUID, list] = defaultdict(list)
        if pe_ids:
            rip_rows = session.execute(
                select(RipOffer)
                .where(RipOffer.product_edition_id.in_(pe_ids))
                .order_by(asc(RipOffer.tier_cases))
            ).scalars().all()
            for rip in rip_rows:
                rips_by_pe[rip.product_edition_id].append(rip)
        for r in cost_rows:
            cc = r.case_cost or Decimal("0")
            bc = r.btl_cost or Decimal("0")
            inv = cc * r.qty_cases + bc * r.qty_bottles
            invoice_by_order[r.watchlist_id] += inv
            # RIP rebate on qualifying cases
            if r.pe_id and r.qty_cases > 0:
                rips = rips_by_pe.get(r.pe_id, [])
                qualifying = [
                    rip for rip in rips
                    if r.qty_cases >= rip.tier_cases
                ]
                if qualifying:
                    best = max(qualifying, key=lambda x: x.save_amount)
                    reb = min(
                        best.save_amount * r.qty_cases,
                        Decimal("1000"),
                    )
                    rebate_by_order[r.watchlist_id] += reb

    results = []
    for o in orders:
        cnt, cases, bottles = item_stats.get(o.id, (0, 0, 0))
        inv = invoice_by_order.get(o.id, Decimal("0"))
        reb = rebate_by_order.get(o.id, Decimal("0"))
        eff = inv - reb
        results.append(OrderSummaryOut(
            id=str(o.id),
            name=o.name,
            division=o.division,
            status=o.status,
            order_notes=o.order_notes,
            item_count=cnt,
            total_cases=cases,
            total_bottles=bottles,
            invoice_total=_money(inv),
            rip_rebate_total=_money(reb),
            effective_total=_money(eff),
            created_at=o.created_at.isoformat(),
            updated_at=o.updated_at.isoformat(),
            submitted_at=o.submitted_at.isoformat() if o.submitted_at else None,
            hidden_at=o.hidden_at.isoformat() if o.hidden_at else None,
        ))
    return results


@router.post("/api/v1/orders", response_model=OrderSummaryOut, status_code=201)
def create_order(
    body: OrderCreateIn,
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if body.division and body.division not in VALID_DIVISIONS:
        valid = ", ".join(sorted(VALID_DIVISIONS))
        raise HTTPException(
            status_code=400,
            detail=f"Invalid division. Valid: {valid}",
        )

    order = Watchlist(
        tenant_id=user["tenant_id"],
        name=body.name,
        is_default=False,
        division=body.division,
        status="draft",
        order_notes=body.order_notes,
    )
    session.add(order)
    session.flush()
    _audit(session, tenant_id=user["tenant_id"], user_id=user["user_id"],
           entity_table="watchlists", entity_id=order.id, action="insert",
           after={"name": body.name, "division": body.division})
    session.commit()
    return OrderSummaryOut(
        id=str(order.id), name=order.name, division=order.division,
        status=order.status, order_notes=order.order_notes,
        created_at=order.created_at.isoformat(),
        updated_at=order.updated_at.isoformat(),
    )


@router.patch("/api/v1/orders/{order_id}", response_model=OrderSummaryOut)
def update_order(
    order_id: UUID,
    body: OrderUpdateIn,
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    order = _get_order(session, order_id, user["tenant_id"])

    if body.division is not None and body.division != "" and body.division not in VALID_DIVISIONS:
        raise HTTPException(status_code=400, detail="Invalid division")

    before = {"name": order.name, "division": order.division, "status": order.status}
    if body.name is not None:
        order.name = body.name
    if body.division is not None:
        order.division = body.division or None
    if body.status is not None:
        order.status = body.status
    if body.order_notes is not None:
        order.order_notes = body.order_notes

    _audit(session, tenant_id=user["tenant_id"], user_id=user["user_id"],
           entity_table="watchlists", entity_id=order.id, action="update", before=before)
    session.commit()

    cnt_row = session.execute(
        select(
            func.count().label("cnt"),
            func.coalesce(func.sum(WatchlistItem.qty_cases), 0),
            func.coalesce(func.sum(WatchlistItem.qty_bottles), 0),
        ).where(WatchlistItem.watchlist_id == order.id)
    ).one()

    return OrderSummaryOut(
        id=str(order.id), name=order.name, division=order.division,
        status=order.status, order_notes=order.order_notes,
        item_count=cnt_row[0], total_cases=cnt_row[1], total_bottles=cnt_row[2],
        created_at=order.created_at.isoformat(),
        updated_at=order.updated_at.isoformat(),
        submitted_at=order.submitted_at.isoformat() if order.submitted_at else None,
    )


@router.delete("/api/v1/orders/{order_id}", status_code=204)
def delete_order(
    order_id: UUID,
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    order = _get_order(session, order_id, user["tenant_id"])
    _audit(session, tenant_id=user["tenant_id"], user_id=user["user_id"],
           entity_table="watchlists", entity_id=order.id, action="delete")
    session.delete(order)
    session.commit()


@router.post("/api/v1/orders/{order_id}/hide", response_model=OrderSummaryOut)
def hide_order(
    order_id: UUID,
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    order = _get_order(session, order_id, user["tenant_id"])
    order.hidden_at = datetime.now(UTC)
    _audit(session, tenant_id=user["tenant_id"], user_id=user["user_id"],
           entity_table="watchlists", entity_id=order.id, action="update",
           after={"hidden_at": order.hidden_at.isoformat()})
    session.commit()
    cnt_row = session.execute(
        select(
            func.count().label("cnt"),
            func.coalesce(func.sum(WatchlistItem.qty_cases), 0),
            func.coalesce(func.sum(WatchlistItem.qty_bottles), 0),
        ).where(WatchlistItem.watchlist_id == order.id)
    ).one()
    return OrderSummaryOut(
        id=str(order.id), name=order.name, division=order.division,
        status=order.status, order_notes=order.order_notes,
        item_count=cnt_row[0], total_cases=cnt_row[1], total_bottles=cnt_row[2],
        created_at=order.created_at.isoformat(),
        updated_at=order.updated_at.isoformat(),
        submitted_at=order.submitted_at.isoformat() if order.submitted_at else None,
        hidden_at=order.hidden_at.isoformat() if order.hidden_at else None,
    )


@router.post("/api/v1/orders/{order_id}/unhide", response_model=OrderSummaryOut)
def unhide_order(
    order_id: UUID,
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    order = _get_order(session, order_id, user["tenant_id"])
    order.hidden_at = None
    _audit(session, tenant_id=user["tenant_id"], user_id=user["user_id"],
           entity_table="watchlists", entity_id=order.id, action="update",
           after={"hidden_at": None})
    session.commit()
    cnt_row = session.execute(
        select(
            func.count().label("cnt"),
            func.coalesce(func.sum(WatchlistItem.qty_cases), 0),
            func.coalesce(func.sum(WatchlistItem.qty_bottles), 0),
        ).where(WatchlistItem.watchlist_id == order.id)
    ).one()
    return OrderSummaryOut(
        id=str(order.id), name=order.name, division=order.division,
        status=order.status, order_notes=order.order_notes,
        item_count=cnt_row[0], total_cases=cnt_row[1], total_bottles=cnt_row[2],
        created_at=order.created_at.isoformat(),
        updated_at=order.updated_at.isoformat(),
        submitted_at=order.submitted_at.isoformat() if order.submitted_at else None,
        hidden_at=order.hidden_at.isoformat() if order.hidden_at else None,
    )


# ── Items ────────────────────────────────────────────────────────────────

@router.post("/api/v1/orders/{order_id}/items", status_code=201)
def add_order_item(
    order_id: UUID,
    body: OrderItemAddIn,
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    order = _get_order(session, order_id, user["tenant_id"])
    product = _resolve_product(session, body.distributor, body.code)

    existing = session.execute(
        select(WatchlistItem).where(
            WatchlistItem.watchlist_id == order.id,
            WatchlistItem.product_id == product.id,
        )
    ).scalar_one_or_none()

    if existing:
        existing.qty_cases = body.qty_cases
        existing.qty_bottles = body.qty_bottles
        existing.selected_rip_tier = body.selected_rip_tier
        if body.notes is not None:
            existing.notes = body.notes
        session.commit()
        return {"status": "updated", "product_code": body.code}

    item = WatchlistItem(
        watchlist_id=order.id,
        product_id=product.id,
        qty_cases=body.qty_cases,
        qty_bottles=body.qty_bottles,
        selected_rip_tier=body.selected_rip_tier,
        notes=body.notes,
    )
    session.add(item)
    session.flush()
    _audit(session, tenant_id=user["tenant_id"], user_id=user["user_id"],
           entity_table="watchlist_items", entity_id=item.id, action="insert",
           after={"product_code": body.code, "qty_cases": body.qty_cases})
    session.commit()
    return {"status": "added", "product_code": body.code}


@router.patch("/api/v1/orders/{order_id}/items/{code}")
def update_order_item(
    order_id: UUID,
    code: str,
    body: OrderItemUpdateIn,
    distributor: str = "nj-allied",
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    order = _get_order(session, order_id, user["tenant_id"])
    product = _resolve_product(session, distributor, code)

    item = session.execute(
        select(WatchlistItem).where(
            WatchlistItem.watchlist_id == order.id,
            WatchlistItem.product_id == product.id,
        )
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not in this order")

    if body.qty_cases is not None:
        item.qty_cases = body.qty_cases
    if body.qty_bottles is not None:
        item.qty_bottles = body.qty_bottles
    if body.selected_rip_tier is not None:
        item.selected_rip_tier = body.selected_rip_tier
    if body.notes is not None:
        item.notes = body.notes

    session.commit()
    return {"status": "updated", "product_code": code}


@router.delete("/api/v1/orders/{order_id}/items/{code}", status_code=204)
def remove_order_item(
    order_id: UUID,
    code: str,
    distributor: str = "nj-allied",
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    order = _get_order(session, order_id, user["tenant_id"])
    product = _resolve_product(session, distributor, code)

    item = session.execute(
        select(WatchlistItem).where(
            WatchlistItem.watchlist_id == order.id,
            WatchlistItem.product_id == product.id,
        )
    ).scalar_one_or_none()
    if item is None:
        return
    session.delete(item)
    session.commit()


@router.post("/api/v1/orders/{order_id}/copy-from-watchlist")
def copy_from_watchlist(
    order_id: UUID,
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    order = _get_order(session, order_id, user["tenant_id"])

    default_wl = session.execute(
        select(Watchlist).where(
            Watchlist.tenant_id == user["tenant_id"],
            Watchlist.is_default == True,  # noqa: E712
        )
    ).scalar_one_or_none()
    if default_wl is None:
        raise HTTPException(status_code=404, detail="No default watchlist found")

    wl_items = session.execute(
        select(WatchlistItem).where(WatchlistItem.watchlist_id == default_wl.id)
    ).scalars().all()

    existing_product_ids = set(session.execute(
        select(WatchlistItem.product_id)
        .where(WatchlistItem.watchlist_id == order.id)
    ).scalars().all())

    added = 0
    for wi in wl_items:
        if wi.product_id in existing_product_ids:
            continue
        session.add(WatchlistItem(
            watchlist_id=order.id,
            product_id=wi.product_id,
            qty_cases=0,
            qty_bottles=0,
            notes=wi.notes,
        ))
        added += 1

    session.commit()
    return {"added": added, "total": len(wl_items)}


@router.post("/api/v1/orders/{order_id}/submit")
def submit_order(
    order_id: UUID,
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    order = _get_order(session, order_id, user["tenant_id"])
    if order.status != "draft":
        raise HTTPException(status_code=400, detail="Only draft orders can be submitted")

    order.status = "submitted"
    order.submitted_at = datetime.now(UTC)
    _audit(session, tenant_id=user["tenant_id"], user_id=user["user_id"],
           entity_table="watchlists", entity_id=order.id, action="update",
           after={"status": "submitted"})
    session.commit()
    return {"status": "submitted", "submitted_at": order.submitted_at.isoformat()}


@router.post("/api/v1/orders/{order_id}/clone", response_model=OrderSummaryOut, status_code=201)
def clone_order(
    order_id: UUID,
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    original = _get_order(session, order_id, user["tenant_id"])

    clone = Watchlist(
        tenant_id=user["tenant_id"],
        name=f"{original.name} (Copy)",
        is_default=False,
        division=original.division,
        status="draft",
    )
    session.add(clone)
    session.flush()

    # Copy all items from the original order
    orig_items = session.execute(
        select(WatchlistItem).where(WatchlistItem.watchlist_id == original.id)
    ).scalars().all()

    for wi in orig_items:
        session.add(WatchlistItem(
            watchlist_id=clone.id,
            product_id=wi.product_id,
            qty_cases=wi.qty_cases,
            qty_bottles=wi.qty_bottles,
            selected_rip_tier=wi.selected_rip_tier,
            notes=wi.notes,
        ))

    _audit(session, tenant_id=user["tenant_id"], user_id=user["user_id"],
           entity_table="watchlists", entity_id=clone.id, action="insert",
           after={"name": clone.name, "division": clone.division,
                  "cloned_from": str(original.id)})
    session.commit()

    cnt = len(orig_items)
    total_cases = sum(wi.qty_cases for wi in orig_items)
    total_bottles = sum(wi.qty_bottles for wi in orig_items)

    return OrderSummaryOut(
        id=str(clone.id), name=clone.name, division=clone.division,
        status=clone.status, order_notes=clone.order_notes,
        item_count=cnt, total_cases=total_cases, total_bottles=total_bottles,
        created_at=clone.created_at.isoformat(),
        updated_at=clone.updated_at.isoformat(),
    )


# ── Order Detail with Analytics ──────────────────────────────────────────

@router.get("/api/v1/orders/{order_id}", response_model=OrderDetailOut)
def get_order_detail(
    order_id: UUID,
    distributor: str = Query("nj-allied"),
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    order = _get_order(session, order_id, user["tenant_id"])
    edition = _current_edition(session, distributor)

    # Fetch all items with product+edition info
    stmt = (
        select(
            WatchlistItem,
            Product.code.label("product_code"),
            ProductEdition.description,
            ProductEdition.size,
            ProductEdition.pack,
            ProductEdition.case_cost,
            ProductEdition.btl_cost,
            ProductEdition.divisions,
            Category.slug.label("category_slug"),
            Category.display_name.label("category_display"),
            Brand.slug.label("brand_slug"),
            Brand.display_name.label("brand_display"),
            ProductEdition.id.label("pe_id"),
        )
        .select_from(WatchlistItem)
        .join(Product, Product.id == WatchlistItem.product_id)
        .outerjoin(ProductEdition, and_(
            ProductEdition.product_id == Product.id,
            ProductEdition.book_edition_id == edition.id,
        ))
        .outerjoin(Category, Category.id == ProductEdition.category_id)
        .outerjoin(Brand, Brand.id == ProductEdition.brand_id)
        .where(WatchlistItem.watchlist_id == order.id)
        .order_by(asc(ProductEdition.description))
    )
    rows = session.execute(stmt).all()

    if not rows:
        return OrderDetailOut(
            id=str(order.id), name=order.name, division=order.division,
            status=order.status, order_notes=order.order_notes,
            created_at=order.created_at.isoformat(),
            updated_at=order.updated_at.isoformat(),
            submitted_at=order.submitted_at.isoformat() if order.submitted_at else None,
            items=[], payment=PaymentAnalysisOut(
                invoice_total="0.00", rip_rebate_total="0.00", effective_total="0.00",
            ),
        )

    # Bulk fetch RIP tiers
    pe_ids = [r.pe_id for r in rows if r.pe_id]
    product_codes = [r.product_code for r in rows]
    rips_by_pe: dict[UUID, list] = defaultdict(list)
    if pe_ids:
        rip_rows = session.execute(
            select(RipOffer)
            .where(RipOffer.product_edition_id.in_(pe_ids))
            .order_by(asc(RipOffer.tier_cases))
        ).scalars().all()
        for rip in rip_rows:
            rips_by_pe[rip.product_edition_id].append(rip)

    # Bulk fetch closeout status
    closeout_product_ids = set()
    if product_codes:
        product_id_map = {r.product_code: r[0].product_id for r in rows}
        co_rows = session.execute(
            select(InventoryReduction.product_id)
            .where(
                InventoryReduction.book_edition_id == edition.id,
                InventoryReduction.product_id.in_([pid for pid in product_id_map.values()]),
            )
        ).scalars().all()
        closeout_product_ids = set(co_rows)

    # Bulk fetch active partials for defer recommendations
    from datetime import date as date_type
    today = date_type.today()
    upcoming_partials: dict[str, list] = defaultdict(list)
    if product_codes:
        pp_rows = session.execute(
            select(PartialsPricing.linked_product_id, PartialsPricing.start_date,
                   PartialsPricing.end_date, PartialsPricing.best_case_price)
            .where(
                PartialsPricing.start_date > today,
                PartialsPricing.linked_product_id.in_(
                    select(Product.id).where(Product.code.in_(product_codes))
                ),
            )
        ).all()
        code_by_pid = {}
        for r in rows:
            code_by_pid[r[0].product_id] = r.product_code
        for pp in pp_rows:
            c = code_by_pid.get(pp.linked_product_id)
            if c:
                upcoming_partials[c].append(pp)

    # Build line items with payment analysis
    lines: list[OrderLineOut] = []
    invoice_total = Decimal("0")
    rebate_total = Decimal("0")
    def _empty_cat():
        return {"invoice": Decimal("0"), "rebate": Decimal("0"), "count": 0}
    cat_breakdown: dict[str, dict] = defaultdict(_empty_cat)

    for r in rows:
        wi = r[0]  # WatchlistItem
        rips = rips_by_pe.get(r.pe_id, []) if r.pe_id else []
        rip_tiers = [
            RipTierOut(
                tier=rip.tier, tier_cases=rip.tier_cases,
                save_amount=str(rip.save_amount),
                case_price=_money(rip.case_price),
                btl_price=_money(rip.btl_price),
            ) for rip in rips
        ]
        best_rip = max(rips, key=lambda x: x.save_amount) if rips else None

        # Payment calc per line
        case_cost = r.case_cost or Decimal("0")
        btl_cost = r.btl_cost or Decimal("0")
        line_invoice = case_cost * wi.qty_cases + btl_cost * wi.qty_bottles

        # RIP rebate: only on cases, and only if qty meets tier minimum
        line_rebate = Decimal("0")
        if best_rip and wi.qty_cases >= best_rip.tier_cases:
            # Use the selected tier if specified, otherwise use best qualifying
            qualifying_rips = [rip for rip in rips if wi.qty_cases >= rip.tier_cases]
            if qualifying_rips:
                chosen = max(qualifying_rips, key=lambda x: x.save_amount)
                line_rebate = chosen.save_amount * wi.qty_cases
                # NJ ABC cap: 50 cases or $1,000 per RIP
                line_rebate = min(line_rebate, Decimal("1000"))

        line_effective = line_invoice - line_rebate
        invoice_total += line_invoice
        rebate_total += line_rebate

        cat = r.category_display or "Uncategorized"
        cat_breakdown[cat]["invoice"] += line_invoice
        cat_breakdown[cat]["rebate"] += line_rebate
        cat_breakdown[cat]["count"] += 1

        # Recommendations per line
        recs: list[RecommendationOut] = []
        is_closeout = wi.product_id in closeout_product_ids

        if is_closeout:
            recs.append(RecommendationOut(
                type="closeout", priority="action",
                message="Closeout item — being discontinued. Buy now if needed.",
            ))

        # Defer suggestion (only if not closeout)
        if not is_closeout and r.product_code in upcoming_partials:
            for pp in upcoming_partials[r.product_code]:
                if pp.best_case_price and r.case_cost and pp.best_case_price < r.case_cost:
                    savings = r.case_cost - pp.best_case_price
                    msg = (
                        f"Better price starting {pp.start_date}"
                        f": save {_money(savings)}/case"
                    )
                    recs.append(RecommendationOut(
                        type="defer", priority="warning",
                        message=msg,
                    ))

        # RIP tier optimizer
        if rips and wi.qty_cases > 0:
            for rip in rips:
                if wi.qty_cases < rip.tier_cases:
                    needed = rip.tier_cases - wi.qty_cases
                    cur_save = (
                        best_rip.save_amount
                        if best_rip and wi.qty_cases >= best_rip.tier_cases
                        else Decimal("0")
                    )
                    extra_save = rip.save_amount - cur_save
                    if extra_save > 0:
                        pl = "s" if needed > 1 else ""
                        msg = (
                            f"Add {needed} more case{pl} to reach"
                            f" {rip.tier} tier, save"
                            f" {_money(extra_save)} more/case"
                        )
                        recs.append(RecommendationOut(
                            type="rip_optimizer", priority="info",
                            message=msg,
                        ))
                    break  # only show next tier suggestion

        lines.append(OrderLineOut(
            product_code=r.product_code,
            description=r.description,
            size=r.size,
            pack=r.pack,
            category_slug=r.category_slug,
            category_display=r.category_display,
            brand_slug=r.brand_slug,
            brand_display=r.brand_display,
            divisions=r.divisions,
            case_cost=_money(r.case_cost),
            btl_cost=_money(r.btl_cost),
            qty_cases=wi.qty_cases,
            qty_bottles=wi.qty_bottles,
            selected_rip_tier=wi.selected_rip_tier,
            notes=wi.notes,
            has_rip=bool(rips),
            rip_tiers=rip_tiers,
            best_rip_save=_money(best_rip.save_amount) if best_rip else None,
            line_invoice=_money(line_invoice),
            line_rip_rebate=_money(line_rebate),
            line_effective=_money(line_effective),
            recommendations=recs,
            is_closeout=is_closeout,
        ))

    effective_total = invoice_total - rebate_total
    rip_pct = (
        str(round(float(rebate_total) / float(invoice_total) * 100, 1))
        if invoice_total > 0 else None
    )

    by_cat = [
        PaymentCategoryBreakdown(
            category=cat,
            invoice=_money(data["invoice"]),
            rebate=_money(data["rebate"]),
            effective=_money(data["invoice"] - data["rebate"]),
            item_count=data["count"],
        )
        for cat, data in sorted(cat_breakdown.items())
    ]

    # Order-level recommendations
    order_recs: list[RecommendationOut] = []
    closeout_count = sum(1 for line in lines if line.is_closeout)
    if closeout_count > 0:
        pl = "s" if closeout_count > 1 else ""
        order_recs.append(RecommendationOut(
            type="closeout", priority="action",
            message=f"{closeout_count} item{pl} being discontinued",
        ))
    defer_count = sum(
        1 for line in lines
        for r in line.recommendations if r.type == "defer"
    )
    if defer_count > 0:
        pl = "s" if defer_count > 1 else ""
        order_recs.append(RecommendationOut(
            type="defer", priority="warning",
            message=f"{defer_count} item{pl} may have better upcoming prices",
        ))

    return OrderDetailOut(
        id=str(order.id), name=order.name, division=order.division,
        status=order.status, order_notes=order.order_notes,
        created_at=order.created_at.isoformat(),
        updated_at=order.updated_at.isoformat(),
        submitted_at=order.submitted_at.isoformat() if order.submitted_at else None,
        items=lines,
        payment=PaymentAnalysisOut(
            invoice_total=_money(invoice_total),
            rip_rebate_total=_money(rebate_total),
            effective_total=_money(effective_total),
            rip_pct_of_order=rip_pct,
            by_category=by_cat,
        ),
        recommendations=order_recs,
    )


# ── Export ───────────────────────────────────────────────────────────────

@router.get("/api/v1/orders/{order_id}/export")
def export_order(
    order_id: UUID,
    format: str = Query("xlsx"),
    division: str | None = Query(None),
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if format not in ("xlsx",):
        raise HTTPException(status_code=400, detail="Only xlsx format supported")

    # Get the full order detail
    detail = get_order_detail(order_id, user=user, session=session)

    items = detail.items
    if division:
        items = [i for i in items if i.divisions and division in i.divisions]

    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill
    except ImportError as exc:
        raise HTTPException(
            status_code=500, detail="openpyxl not installed",
        ) from exc

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Order"

    # Header
    ws.append(["Order:", detail.name])
    ws.append(["Division:", detail.division or "All"])
    ws.append(["Status:", detail.status])
    ws.append([""])
    ws.append(["Payment Needed Now (Invoice):", detail.payment.invoice_total])
    ws.append(["RIP Rebate (cheque later):", detail.payment.rip_rebate_total])
    ws.append(["Effective Cost:", detail.payment.effective_total])
    ws.append([""])

    headers = [
        "Code", "Description", "Size", "Pack", "Category", "Brand",
        "Divisions", "Case Cost", "Btl Cost", "Qty Cases", "Qty Btls",
        "Has RIP", "Best RIP Save", "Line Invoice", "Line RIP Rebate",
        "Line Effective", "Notes",
    ]
    ws.append(headers)
    header_row = ws.max_row
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=header_row, column=col_idx)
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="F4F4F5", end_color="F4F4F5", fill_type="solid")

    for item in items:
        ws.append([
            item.product_code, item.description, item.size, item.pack,
            item.category_display, item.brand_display, item.divisions,
            item.case_cost, item.btl_cost, item.qty_cases, item.qty_bottles,
            "Yes" if item.has_rip else "", item.best_rip_save,
            item.line_invoice, item.line_rip_rebate, item.line_effective,
            item.notes,
        ])

    # Auto-width
    for col in ws.columns:
        max_len = 0
        col_letter = col[0].column_letter
        for cell in col:
            if cell.value:
                max_len = max(max_len, len(str(cell.value)))
        ws.column_dimensions[col_letter].width = min(max_len + 2, 40)

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"order-{detail.name.replace(' ', '_')}-{datetime.now(UTC).strftime('%Y%m%d')}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
