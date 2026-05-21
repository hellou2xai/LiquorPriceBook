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

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, asc, desc, func, select
from sqlalchemy.orm import Session, aliased

from lpb_core.db import get_session
from lpb_core.db.models import (
    AuditLog,
    BookEdition,
    Brand,
    Category,
    Distributor,
    Note,
    Product,
    ProductEdition,
    RipOffer,
    Watchlist,
    WatchlistItem,
)

from .auth import get_current_user
from .catalog import _current_edition_ids

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


class RipTierOut(BaseModel):
    tier: str
    tier_cases: int
    save_amount: Decimal
    case_price: Decimal | None = None
    btl_price: Decimal | None = None
    effective_case: Decimal | None = None
    effective_btl: Decimal | None = None
    discount_pct: Decimal | None = None


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    product_code: str
    description: str | None = None
    size: str | None = None
    pack: int | None = None
    category_slug: str | None = None
    category_display: str | None = None
    brand_slug: str | None = None
    brand_display: str | None = None
    divisions: str | None = None
    case_cost: Decimal | None = None
    btl_cost: Decimal | None = None
    has_rip: bool = False
    rip_tier: str | None = None
    rip_tier_cases: int | None = None
    rip_save_amount: Decimal | None = None
    rip_case_price: Decimal | None = None
    rip_btl_price: Decimal | None = None
    effective_case: Decimal | None = None
    effective_btl: Decimal | None = None
    rip_discount_pct: Decimal | None = None  # (save / case_cost) * 100
    all_rips: list[RipTierOut] = []  # all RIP tiers for comparison
    # Buy-timing intelligence
    prev_case_cost: Decimal | None = None
    price_pct_change: Decimal | None = None
    price_direction: str | None = None  # "up", "down", "flat", "new"
    low_12m: Decimal | None = None
    high_12m: Decimal | None = None
    avg_12m: Decimal | None = None
    months_at_price: int | None = None
    at_12m_low: bool = False
    at_12m_high: bool = False
    had_rip_prev: bool = False
    buy_signal: str = "HOLD"  # BUY_NOW, GOOD_BUY, HOLD, DEFER
    buy_reasons: list[str] = []
    # Distributor
    distributor_slug: str | None = None
    distributor_name: str | None = None
    # User fields
    target_case_price: Decimal | None = None
    target_btl_price: Decimal | None = None
    notes: str | None = None
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


@router.get("/api/v1/watchlist/order", response_model=list[OrderItemOut])
def watchlist_order(
    search: str | None = Query(None),  # noqa: B008
    category: str | None = Query(None),  # noqa: B008
    sort: str = Query("name", pattern="^(name|case_cost_asc|case_cost_desc|rip_save)$"),  # noqa: B008
    distributor: str = Query("nj-allied"),  # noqa: B008
    user: dict = Depends(get_current_user),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
):
    """Enriched watchlist with full product details and RIP info for the order page."""
    # Get current edition IDs for all distributors so tracked products from
    # any distributor resolve correctly (not just the sidebar-selected one).
    edition_ids = _current_edition_ids(session, "all")

    # Subquery: best (highest save_amount) RIP per product_edition
    top_rip_sub = (
        select(
            RipOffer.product_edition_id,
            func.max(RipOffer.save_amount).label("max_save"),
        )
        .group_by(RipOffer.product_edition_id)
        .subquery()
    )
    top_rip = aliased(RipOffer)

    stmt = (
        select(
            Product.code.label("product_code"),
            ProductEdition.description,
            ProductEdition.size,
            ProductEdition.pack,
            Category.slug.label("category_slug"),
            Category.display_name.label("category_display"),
            Brand.slug.label("brand_slug"),
            Brand.display_name.label("brand_display"),
            ProductEdition.divisions,
            ProductEdition.case_cost,
            ProductEdition.btl_cost,
            top_rip.tier.label("rip_tier"),
            top_rip.tier_cases.label("rip_tier_cases"),
            top_rip.save_amount.label("rip_save_amount"),
            top_rip.case_price.label("rip_case_price"),
            top_rip.btl_price.label("rip_btl_price"),
            Distributor.slug.label("distributor_slug"),
            Distributor.name.label("distributor_name"),
            WatchlistItem.target_case_price,
            WatchlistItem.target_btl_price,
            WatchlistItem.notes,
            WatchlistItem.created_at,
        )
        .select_from(WatchlistItem)
        .join(Watchlist, Watchlist.id == WatchlistItem.watchlist_id)
        .join(Product, Product.id == WatchlistItem.product_id)
        .join(Distributor, Distributor.id == Product.distributor_id)
        .outerjoin(
            ProductEdition,
            and_(
                ProductEdition.product_id == Product.id,
                ProductEdition.book_edition_id.in_(edition_ids),
            ),
        )
        .outerjoin(Category, Category.id == ProductEdition.category_id)
        .outerjoin(Brand, Brand.id == ProductEdition.brand_id)
        .outerjoin(
            top_rip_sub,
            top_rip_sub.c.product_edition_id == ProductEdition.id,
        )
        .outerjoin(
            top_rip,
            and_(
                top_rip.product_edition_id == ProductEdition.id,
                top_rip.save_amount == top_rip_sub.c.max_save,
            ),
        )
        .where(Watchlist.tenant_id == user["tenant_id"])
    )

    # Filters
    if search:
        pat = f"%{search}%"
        from sqlalchemy import or_
        stmt = stmt.where(
            or_(
                Product.code.ilike(pat),
                ProductEdition.description.ilike(pat),
            )
        )
    if category:
        stmt = stmt.where(Category.slug == category)

    # Sorting
    if sort == "name":
        stmt = stmt.order_by(asc(ProductEdition.description), asc(Product.code))
    elif sort == "case_cost_asc":
        stmt = stmt.order_by(asc(ProductEdition.case_cost).nullslast(), asc(Product.code))
    elif sort == "case_cost_desc":
        stmt = stmt.order_by(desc(ProductEdition.case_cost).nullslast(), asc(Product.code))
    elif sort == "rip_save":
        stmt = stmt.order_by(desc(top_rip.save_amount).nullslast(), asc(Product.code))

    raw_rows = session.execute(stmt).all()

    if not raw_rows:
        return []

    # Deduplicate: RIP join can produce multiple rows per product code.
    # Keep first occurrence (which has the best RIP due to the join logic).
    seen_codes: set[str] = set()
    rows: list = []
    for r in raw_rows:
        if r.product_code not in seen_codes:
            seen_codes.add(r.product_code)
            rows.append(r)

    # ── Bulk fetch ALL RIP tiers per product (not just best) ──
    product_codes_set = {r.product_code for r in rows}
    all_rips_stmt = (
        select(
            Product.code,
            RipOffer.tier,
            RipOffer.tier_cases,
            RipOffer.save_amount,
            RipOffer.case_price,
            RipOffer.btl_price,
        )
        .select_from(RipOffer)
        .join(ProductEdition, ProductEdition.id == RipOffer.product_edition_id)
        .join(Product, Product.id == ProductEdition.product_id)
        .where(
            ProductEdition.book_edition_id.in_(edition_ids),
            Product.code.in_(product_codes_set),
        )
        .order_by(Product.code, asc(RipOffer.tier_cases))
    )
    all_rips_rows = session.execute(all_rips_stmt).all()

    from collections import defaultdict
    rips_by_code: dict[str, list] = defaultdict(list)
    for rr in all_rips_rows:
        rips_by_code[rr.code].append(rr)

    # ── Bulk price history for buy-timing intelligence ──
    # Collect product_ids from main query to fetch history in one shot
    product_codes = [r.product_code for r in rows]
    hist_stmt = (
        select(
            Product.code,
            BookEdition.year,
            BookEdition.month,
            ProductEdition.case_cost,
        )
        .select_from(ProductEdition)
        .join(Product, Product.id == ProductEdition.product_id)
        .join(BookEdition, BookEdition.id == ProductEdition.book_edition_id)
        .where(Product.code.in_(product_codes))
        .order_by(Product.code, asc(BookEdition.year), asc(BookEdition.month))
    )
    hist_rows = session.execute(hist_stmt).all()

    # Build per-product price history
    history_map: dict[str, list[Decimal | None]] = defaultdict(list)
    for hr in hist_rows:
        history_map[hr.code].append(hr.case_cost)

    # Check which products had RIP in previous editions (across all distributors)
    prev_rip_codes: set[str] = set()
    all_editions = session.execute(
        select(BookEdition.id, Distributor.slug)
        .join(Distributor, Distributor.id == BookEdition.distributor_id)
        .order_by(Distributor.slug, desc(BookEdition.year), desc(BookEdition.month))
    ).all()
    # Find second-most-recent edition per distributor
    prev_edition_ids: list = []
    seen_dist: dict[str, int] = {}
    for eid, dslug in all_editions:
        seen_dist[dslug] = seen_dist.get(dslug, 0) + 1
        if seen_dist[dslug] == 2:  # second edition = previous
            prev_edition_ids.append(eid)
    if prev_edition_ids:
        prev_rip_rows = session.execute(
            select(Product.code)
            .select_from(RipOffer)
            .join(ProductEdition, ProductEdition.id == RipOffer.product_edition_id)
            .join(Product, Product.id == ProductEdition.product_id)
            .where(ProductEdition.book_edition_id.in_(prev_edition_ids))
            .distinct()
        ).scalars().all()
        prev_rip_codes = set(prev_rip_rows)

    results: list[OrderItemOut] = []
    for r in rows:
        has_rip = r.rip_save_amount is not None
        # Effective case: prefer rip_case_price, else case_cost - save_amount, else case_cost
        if has_rip and r.rip_case_price is not None:
            effective_case = r.rip_case_price
        elif has_rip and r.case_cost is not None and r.rip_save_amount is not None:
            effective_case = r.case_cost - r.rip_save_amount
        else:
            effective_case = r.case_cost
        # Effective btl: prefer rip_btl_price, else btl_cost
        if has_rip and r.rip_btl_price is not None:
            effective_btl = r.rip_btl_price
        else:
            effective_btl = r.btl_cost

        # ── Compute trend metrics ──
        prices = [p for p in history_map.get(r.product_code, []) if p is not None]
        prev_case_cost = None
        price_pct_change = None
        price_direction = "new"
        low_12m = None
        high_12m = None
        avg_12m = None
        months_at_price = None
        at_12m_low = False
        at_12m_high = False

        if len(prices) >= 1 and r.case_cost is not None:
            recent = prices[-12:]  # last 12 months
            low_12m = min(recent)
            high_12m = max(recent)
            avg_12m = Decimal(str(round(sum(recent) / len(recent), 2)))
            at_12m_low = r.case_cost <= low_12m
            at_12m_high = r.case_cost >= high_12m

            # Months at current price (consecutive from end)
            months_at_price = 0
            for p in reversed(prices):
                if p == r.case_cost:
                    months_at_price += 1
                else:
                    break

            if len(prices) >= 2:
                prev_case_cost = prices[-2]
                if prev_case_cost and prev_case_cost != 0:
                    change = r.case_cost - prev_case_cost
                    price_pct_change = Decimal(
                        str(round(float(change) / float(prev_case_cost) * 100, 1))
                    )
                    if change < 0:
                        price_direction = "down"
                    elif change > 0:
                        price_direction = "up"
                    else:
                        price_direction = "flat"

        had_rip_prev = r.product_code in prev_rip_codes

        # ── Buy signal ──
        signal = "HOLD"
        reasons: list[str] = []

        # Target price hit
        if r.target_case_price and effective_case and effective_case <= r.target_case_price:
            signal = "BUY_NOW"
            reasons.append("Hit your target price")

        # At 12-month low
        if at_12m_low and r.case_cost is not None:
            if signal != "BUY_NOW":
                signal = "BUY_NOW" if has_rip else "GOOD_BUY"
            reasons.append("At 12-month low")

        # New RIP appeared
        if has_rip and not had_rip_prev:
            if signal not in ("BUY_NOW",):
                signal = "BUY_NOW"
            reasons.append("New RIP just appeared")
        elif has_rip and had_rip_prev:
            if signal == "HOLD":
                signal = "GOOD_BUY"
            reasons.append("Active RIP")

        # Price dropped this month
        if price_direction == "down" and price_pct_change is not None:
            if abs(float(price_pct_change)) >= 5:
                if signal not in ("BUY_NOW",):
                    signal = "BUY_NOW" if has_rip else "GOOD_BUY"
                reasons.append(f"Price dropped {abs(float(price_pct_change)):.1f}%")
            elif signal == "HOLD":
                signal = "GOOD_BUY"
                reasons.append("Price dropped this month")

        # RIP just expired
        if had_rip_prev and not has_rip:
            if signal in ("HOLD",):
                signal = "DEFER"
            reasons.append("RIP expired — price may adjust")

        # At 12-month high
        if at_12m_high and not at_12m_low and r.case_cost is not None:
            if signal in ("HOLD",):
                signal = "DEFER"
            reasons.append("At 12-month high")

        # Price trending up
        if price_direction == "up" and not has_rip and signal in ("HOLD",):
            signal = "DEFER"
            reasons.append("Price trending up")

        # Stable price, no urgency
        if months_at_price and months_at_price >= 6 and signal == "HOLD":
            reasons.append(f"Price stable for {months_at_price} months")

        if not reasons:
            reasons.append("No strong signal — standard pricing")

        results.append(
            OrderItemOut(
                product_code=r.product_code,
                description=r.description,
                size=r.size,
                pack=r.pack,
                category_slug=r.category_slug,
                category_display=r.category_display,
                brand_slug=r.brand_slug,
                brand_display=r.brand_display,
                divisions=r.divisions,
                case_cost=r.case_cost,
                btl_cost=r.btl_cost,
                has_rip=has_rip,
                rip_tier=r.rip_tier,
                rip_tier_cases=r.rip_tier_cases,
                rip_save_amount=r.rip_save_amount,
                rip_case_price=r.rip_case_price,
                rip_btl_price=r.rip_btl_price,
                effective_case=effective_case,
                effective_btl=effective_btl,
                rip_discount_pct=(
                    Decimal(str(round(float(r.rip_save_amount) / float(r.case_cost) * 100, 1)))
                    if has_rip and r.rip_save_amount and r.case_cost and float(r.case_cost) > 0
                    else None
                ),
                all_rips=[
                    RipTierOut(
                        tier=rr.tier,
                        tier_cases=rr.tier_cases,
                        save_amount=rr.save_amount,
                        case_price=rr.case_price,
                        btl_price=rr.btl_price,
                        effective_case=(
                            rr.case_price if rr.case_price is not None
                            else (
                                r.case_cost - rr.save_amount
                                if r.case_cost and rr.save_amount
                                else None
                            )
                        ),
                        effective_btl=rr.btl_price if rr.btl_price is not None else r.btl_cost,
                        discount_pct=(
                            Decimal(str(round(float(rr.save_amount) / float(r.case_cost) * 100, 1)))
                            if rr.save_amount and r.case_cost and float(r.case_cost) > 0
                            else None
                        ),
                    )
                    for rr in rips_by_code.get(r.product_code, [])
                ],
                prev_case_cost=prev_case_cost,
                price_pct_change=price_pct_change,
                price_direction=price_direction,
                low_12m=low_12m,
                high_12m=high_12m,
                avg_12m=avg_12m,
                months_at_price=months_at_price,
                at_12m_low=at_12m_low,
                at_12m_high=at_12m_high,
                had_rip_prev=had_rip_prev,
                buy_signal=signal,
                buy_reasons=reasons,
                target_case_price=r.target_case_price,
                target_btl_price=r.target_btl_price,
                distributor_slug=r.distributor_slug,
                distributor_name=(r.distributor_name or "").split()[0] if r.distributor_name else None,
                notes=r.notes,
                created_at=r.created_at,
            )
        )
    return results


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
