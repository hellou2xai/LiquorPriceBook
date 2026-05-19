"""Analytics endpoints: RIP ranker, closeouts, combos, dashboard movers, alerts.

  GET /api/v1/rips                  RIP yield ranker
  GET /api/v1/closeouts             Inventory Reduction items + days-on-list
  GET /api/v1/combos                Combo bundles for the current edition
  GET /api/v1/dashboard/summary      aggregate analytics for the dashboard
  GET /api/v1/dashboard/movers      top price movers from mv_price_changes
  GET /api/v1/dashboard/watchlist-movers  movers intersected with user watchlist
  GET /api/v1/dashboard/alerts      recent AlertEvents for the tenant
"""

from __future__ import annotations

import calendar
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import desc, func, select, text
from sqlalchemy.orm import Session

from lpb_core.db import get_session
from lpb_core.db.models import (
    AlertEvent,
    BookEdition,
    Brand,
    Category,
    Combo,
    InventoryReduction,
    Product,
    ProductEdition,
    RipOffer,
    Watchlist,
    WatchlistItem,
)

from .auth import get_current_user
from .catalog import _current_edition

router = APIRouter(prefix="/api/v1", tags=["insights"])


# ----- RIP ranker -----

class RipRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    description: str | None
    size: str | None
    pack: int | None
    category_slug: str | None
    brand_slug: str | None
    case_cost: Decimal | None
    tier: str
    tier_cases: int
    save_amount: Decimal
    case_price: Decimal | None
    btl_price: Decimal | None
    effective_pct: float | None
    stable: bool | None


@router.get("/rips", response_model=list[RipRow])
def list_rips(
    distributor: str = Query("nj-allied"),
    category: list[str] | None = Query(None),
    min_pct: float = Query(0, ge=0, le=100),
    tier_cases_max: int | None = Query(None, ge=1, le=50),
    limit: int = Query(100, ge=1, le=500),
    user: dict = Depends(get_current_user),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
):
    edition = _current_edition(session, distributor)

    # Pull current RIPs.
    stmt = (
        select(
            Product.code,
            ProductEdition.description,
            ProductEdition.size,
            ProductEdition.pack,
            Category.slug.label("category_slug"),
            Brand.slug.label("brand_slug"),
            ProductEdition.case_cost,
            ProductEdition.id.label("pe_id"),
            ProductEdition.product_id.label("product_id"),
            RipOffer.tier,
            RipOffer.tier_cases,
            RipOffer.save_amount,
            RipOffer.case_price,
            RipOffer.btl_price,
        )
        .select_from(RipOffer)
        .join(ProductEdition, ProductEdition.id == RipOffer.product_edition_id)
        .join(Product, Product.id == ProductEdition.product_id)
        .outerjoin(Category, Category.id == ProductEdition.category_id)
        .outerjoin(Brand, Brand.id == ProductEdition.brand_id)
        .where(ProductEdition.book_edition_id == edition.id)
    )
    if category:
        stmt = stmt.where(Category.slug.in_(category))
    if tier_cases_max is not None:
        stmt = stmt.where(RipOffer.tier_cases <= tier_cases_max)
    stmt = stmt.order_by(desc(RipOffer.save_amount)).limit(limit * 3)
    raw = session.execute(stmt).all()
    if not raw:
        return []

    # Stability: did this same (product, tier) carry the same save_amount in
    # the immediately prior edition? Pull the comparison set in one query.
    product_ids = list({r.product_id for r in raw})

    prior_edition_id = session.execute(
        select(BookEdition.id)
        .where(
            BookEdition.distributor_id == edition.distributor_id,
            (BookEdition.year * 12 + BookEdition.month)
            < (edition.year * 12 + edition.month),
        )
        .order_by(desc(BookEdition.year), desc(BookEdition.month))
        .limit(1)
    ).scalar_one_or_none()

    prior_rip_by_key: dict[tuple[UUID, str], Decimal] = {}
    if prior_edition_id is not None and product_ids:
        prior_rows = session.execute(
            select(
                ProductEdition.product_id,
                RipOffer.tier,
                RipOffer.save_amount,
            )
            .join(RipOffer, RipOffer.product_edition_id == ProductEdition.id)
            .where(
                ProductEdition.book_edition_id == prior_edition_id,
                ProductEdition.product_id.in_(product_ids),
            )
        ).all()
        for prod_id, tier, save in prior_rows:
            prior_rip_by_key[(prod_id, tier)] = save

    out: list[RipRow] = []
    for r in raw:
        case_cost = float(r.case_cost) if r.case_cost is not None else None
        save = float(r.save_amount)
        effective_pct = (save / case_cost * 100) if case_cost else None
        if effective_pct is not None and effective_pct < min_pct:
            continue
        prior = prior_rip_by_key.get((r.product_id, r.tier))
        stable = None if prior is None else (prior == r.save_amount)
        out.append(
            RipRow(
                code=r.code,
                description=r.description,
                size=r.size,
                pack=r.pack,
                category_slug=r.category_slug,
                brand_slug=r.brand_slug,
                case_cost=r.case_cost,
                tier=r.tier,
                tier_cases=r.tier_cases,
                save_amount=r.save_amount,
                case_price=r.case_price,
                btl_price=r.btl_price,
                effective_pct=effective_pct,
                stable=stable,
            )
        )
        if len(out) >= limit:
            break
    return out


# ----- Closeouts -----

class CloseoutRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    description: str | None
    size: str | None
    pack: int | None
    original_case: Decimal | None
    best_case: Decimal | None
    case_save: Decimal | None
    pct_off: float | None
    days_on_list: int


@router.get("/closeouts", response_model=list[CloseoutRow])
def list_closeouts(
    distributor: str = Query("nj-allied"),
    min_pct: float = Query(0, ge=0, le=100),
    limit: int = Query(200, ge=1, le=1000),
    user: dict = Depends(get_current_user),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
):
    edition = _current_edition(session, distributor)

    # Subquery: first_seen_at per (product) on the closeout list
    # = MIN(created_at) of book_editions where this product had an IR row.
    first_seen = (
        select(
            InventoryReduction.product_id,
            func.min(BookEdition.year * 12 + BookEdition.month).label("first_ym"),
        )
        .join(BookEdition, BookEdition.id == InventoryReduction.book_edition_id)
        .where(BookEdition.distributor_id == edition.distributor_id)
        .group_by(InventoryReduction.product_id)
        .subquery()
    )

    rows = session.execute(
        select(
            Product.code,
            InventoryReduction.description,
            InventoryReduction.size,
            InventoryReduction.pack,
            InventoryReduction.original_case,
            InventoryReduction.best_case,
            InventoryReduction.case_save,
            first_seen.c.first_ym,
        )
        .join(Product, Product.id == InventoryReduction.product_id)
        .join(first_seen, first_seen.c.product_id == InventoryReduction.product_id)
        .where(InventoryReduction.book_edition_id == edition.id)
        .order_by(desc(InventoryReduction.case_save))
        .limit(limit)
    ).all()

    out: list[CloseoutRow] = []
    current_ym = edition.year * 12 + edition.month
    for r in rows:
        oc = float(r.original_case) if r.original_case is not None else None
        cs = float(r.case_save) if r.case_save is not None else None
        pct = (cs / oc * 100) if (oc and cs) else None
        if pct is not None and pct < min_pct:
            continue
        months_on_list = max(0, current_ym - int(r.first_ym))
        days_on_list = months_on_list * 30  # approximate
        out.append(
            CloseoutRow(
                code=r.code,
                description=r.description,
                size=r.size,
                pack=r.pack,
                original_case=r.original_case,
                best_case=r.best_case,
                case_save=r.case_save,
                pct_off=pct,
                days_on_list=days_on_list,
            )
        )
    return out


# ----- Combos -----

class ComboRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    sku: str
    subcategory: str | None
    item_code: str | None
    contains: str | None
    front_line_price: Decimal | None


@router.get("/combos", response_model=list[ComboRow])
def list_combos(
    distributor: str = Query("nj-allied"),
    subcategory: str | None = Query(None),
    search: str | None = Query(None),
    limit: int = Query(500, ge=1, le=1000),
    user: dict = Depends(get_current_user),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
):
    edition = _current_edition(session, distributor)
    stmt = (
        select(
            Combo.sku,
            Combo.subcategory,
            Combo.item_code,
            Combo.contains,
            Combo.front_line_price,
        )
        .where(Combo.book_edition_id == edition.id)
    )
    if subcategory:
        stmt = stmt.where(func.lower(Combo.subcategory) == subcategory.lower())
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            Combo.contains.ilike(pattern)
            | Combo.sku.ilike(pattern)
            | Combo.item_code.ilike(pattern)
        )
    stmt = stmt.order_by(Combo.subcategory, Combo.sku).limit(limit)
    rows = session.execute(stmt).all()
    return [
        ComboRow(
            sku=r.sku,
            subcategory=r.subcategory,
            item_code=r.item_code,
            contains=r.contains,
            front_line_price=r.front_line_price,
        )
        for r in rows
    ]


# ----- Dashboard Summary -----


class DashboardSummary(BaseModel):
    # Edition info
    edition_label: str
    edition_year: int
    edition_month: int
    # Counts
    total_products: int
    total_rips: int
    total_closeouts: int
    total_combos: int
    # Price movement
    products_price_down: int
    products_price_up: int
    products_price_flat: int
    avg_price_change_pct: float | None
    # RIP stats
    rip_total_potential_savings: float  # sum of all save_amounts
    rip_avg_discount_pct: float | None
    top_rip_categories: list[dict]  # [{category, count, avg_save}]
    # Watchlist
    watchlist_count: int
    watchlist_buy_now: int  # items with buy signal = BUY_NOW
    # Category breakdown
    category_product_counts: list[dict]  # [{category, count}]
    # Top drops
    top_price_drops: list[dict]  # [{code, description, case_cost, prev_case_cost, pct_change}]
    top_price_increases: list[dict]  # same structure


@router.get("/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary(
    distributor: str = Query("nj-allied"),
    user: dict = Depends(get_current_user),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
):
    edition = _current_edition(session, distributor)
    ed_id = edition.id
    tenant_id = user["tenant_id"]

    edition_label = f"{calendar.month_name[edition.month]} {edition.year}"

    # --- Counts ---
    total_products = session.execute(
        select(func.count()).select_from(ProductEdition).where(
            ProductEdition.book_edition_id == ed_id
        )
    ).scalar_one()

    total_rips = session.execute(
        select(func.count(func.distinct(RipOffer.product_edition_id))).where(
            RipOffer.product_edition_id.in_(
                select(ProductEdition.id).where(
                    ProductEdition.book_edition_id == ed_id
                )
            )
        )
    ).scalar_one()

    total_closeouts = session.execute(
        select(func.count()).select_from(InventoryReduction).where(
            InventoryReduction.book_edition_id == ed_id
        )
    ).scalar_one()

    total_combos = session.execute(
        select(func.count()).select_from(Combo).where(
            Combo.book_edition_id == ed_id
        )
    ).scalar_one()

    # --- Price movements from mv_price_changes ---
    price_stats = session.execute(
        text("""
            SELECT
                COUNT(*) FILTER (WHERE mpc.case_cost_pct < 0)  AS price_down,
                COUNT(*) FILTER (WHERE mpc.case_cost_pct > 0)  AS price_up,
                COUNT(*) FILTER (WHERE mpc.case_cost_pct = 0)  AS price_flat,
                AVG(mpc.case_cost_pct)                         AS avg_pct
            FROM mv_price_changes mpc
            WHERE mpc.book_edition_id = :ed_id
              AND mpc.case_cost_pct IS NOT NULL
        """),
        {"ed_id": str(ed_id)},
    ).one()

    products_price_down = price_stats.price_down or 0
    products_price_up = price_stats.price_up or 0
    products_price_flat = price_stats.price_flat or 0
    avg_price_change_pct = (
        float(price_stats.avg_pct) if price_stats.avg_pct is not None else None
    )

    # --- RIP stats ---
    rip_agg = session.execute(
        select(
            func.sum(RipOffer.save_amount),
            func.avg(
                RipOffer.save_amount * 100.0 / ProductEdition.case_cost
            ),
        )
        .join(ProductEdition, ProductEdition.id == RipOffer.product_edition_id)
        .where(ProductEdition.book_edition_id == ed_id)
        .where(ProductEdition.case_cost > 0)
    ).one()

    rip_total_potential_savings = float(rip_agg[0]) if rip_agg[0] is not None else 0.0
    rip_avg_discount_pct = float(rip_agg[1]) if rip_agg[1] is not None else None

    # Top RIP categories
    top_rip_cats_rows = session.execute(
        select(
            Category.slug,
            func.count(RipOffer.id).label("cnt"),
            func.avg(RipOffer.save_amount).label("avg_save"),
        )
        .join(ProductEdition, ProductEdition.id == RipOffer.product_edition_id)
        .join(Category, Category.id == ProductEdition.category_id)
        .where(ProductEdition.book_edition_id == ed_id)
        .group_by(Category.slug)
        .order_by(desc(func.count(RipOffer.id)))
        .limit(10)
    ).all()

    top_rip_categories = [
        {"category": r.slug, "count": r.cnt, "avg_save": float(r.avg_save)}
        for r in top_rip_cats_rows
    ]

    # --- Watchlist ---
    watchlist_count = session.execute(
        select(func.count()).select_from(WatchlistItem).join(
            Watchlist, Watchlist.id == WatchlistItem.watchlist_id
        ).where(Watchlist.tenant_id == tenant_id)
    ).scalar_one()

    # Buy-now count: watchlist items whose current price dropped vs previous
    watchlist_buy_now = session.execute(
        text("""
            SELECT COUNT(*)
            FROM watchlist_items wi
            JOIN watchlists w ON w.id = wi.watchlist_id
            JOIN mv_price_changes mpc ON mpc.product_id = wi.product_id
            WHERE w.tenant_id = :tid
              AND mpc.book_edition_id = :ed_id
              AND mpc.case_cost_pct < 0
        """),
        {"tid": str(tenant_id), "ed_id": str(ed_id)},
    ).scalar_one() or 0

    # --- Category breakdown ---
    cat_rows = session.execute(
        select(
            Category.slug,
            func.count(ProductEdition.id).label("cnt"),
        )
        .join(Category, Category.id == ProductEdition.category_id)
        .where(ProductEdition.book_edition_id == ed_id)
        .group_by(Category.slug)
        .order_by(desc(func.count(ProductEdition.id)))
    ).all()

    category_product_counts = [
        {"category": r.slug, "count": r.cnt} for r in cat_rows
    ]

    # --- Top price drops ---
    top_drops_rows = session.execute(
        text("""
            SELECT p.code,
                   pe.description,
                   mpc.case_cost,
                   mpc.prev_case_cost,
                   mpc.case_cost_pct
            FROM mv_price_changes mpc
            JOIN product_editions pe ON pe.id = mpc.product_edition_id
            JOIN products p ON p.id = pe.product_id
            WHERE mpc.book_edition_id = :ed_id
              AND mpc.case_cost_pct IS NOT NULL
              AND mpc.case_cost_pct < 0
            ORDER BY mpc.case_cost_pct ASC
            LIMIT 5
        """),
        {"ed_id": str(ed_id)},
    ).all()

    top_price_drops = [
        {
            "code": r.code,
            "description": r.description,
            "case_cost": str(r.case_cost) if r.case_cost is not None else None,
            "prev_case_cost": str(r.prev_case_cost) if r.prev_case_cost is not None else None,
            "pct_change": str(r.case_cost_pct) if r.case_cost_pct is not None else None,
        }
        for r in top_drops_rows
    ]

    # --- Top price increases ---
    top_inc_rows = session.execute(
        text("""
            SELECT p.code,
                   pe.description,
                   mpc.case_cost,
                   mpc.prev_case_cost,
                   mpc.case_cost_pct
            FROM mv_price_changes mpc
            JOIN product_editions pe ON pe.id = mpc.product_edition_id
            JOIN products p ON p.id = pe.product_id
            WHERE mpc.book_edition_id = :ed_id
              AND mpc.case_cost_pct IS NOT NULL
              AND mpc.case_cost_pct > 0
            ORDER BY mpc.case_cost_pct DESC
            LIMIT 5
        """),
        {"ed_id": str(ed_id)},
    ).all()

    top_price_increases = [
        {
            "code": r.code,
            "description": r.description,
            "case_cost": str(r.case_cost) if r.case_cost is not None else None,
            "prev_case_cost": str(r.prev_case_cost) if r.prev_case_cost is not None else None,
            "pct_change": str(r.case_cost_pct) if r.case_cost_pct is not None else None,
        }
        for r in top_inc_rows
    ]

    return DashboardSummary(
        edition_label=edition_label,
        edition_year=edition.year,
        edition_month=edition.month,
        total_products=total_products,
        total_rips=total_rips,
        total_closeouts=total_closeouts,
        total_combos=total_combos,
        products_price_down=products_price_down,
        products_price_up=products_price_up,
        products_price_flat=products_price_flat,
        avg_price_change_pct=avg_price_change_pct,
        rip_total_potential_savings=rip_total_potential_savings,
        rip_avg_discount_pct=rip_avg_discount_pct,
        top_rip_categories=top_rip_categories,
        watchlist_count=watchlist_count,
        watchlist_buy_now=watchlist_buy_now,
        category_product_counts=category_product_counts,
        top_price_drops=top_price_drops,
        top_price_increases=top_price_increases,
    )


# ----- Dashboard -----

class MoverRow(BaseModel):
    code: str
    description: str | None
    category_slug: str | None
    brand_slug: str | None
    case_cost: Decimal | None
    prev_case_cost: Decimal | None
    case_cost_pct: Decimal | None


@router.get("/dashboard/movers", response_model=list[MoverRow])
def movers(
    distributor: str = Query("nj-allied"),
    direction: str = Query("any", pattern="^(up|down|any)$"),
    limit: int = Query(25, ge=1, le=100),
    user: dict = Depends(get_current_user),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
):
    edition = _current_edition(session, distributor)
    direction_sql = ""
    if direction == "up":
        direction_sql = "AND mpc.case_cost_pct > 0"
    elif direction == "down":
        direction_sql = "AND mpc.case_cost_pct < 0"
    rows = session.execute(
        text(f"""
            SELECT p.code,
                   pe.description,
                   c.slug AS category_slug,
                   b.slug AS brand_slug,
                   mpc.case_cost,
                   mpc.prev_case_cost,
                   mpc.case_cost_pct
            FROM mv_price_changes mpc
            JOIN product_editions pe ON pe.id = mpc.product_edition_id
            JOIN products p ON p.id = pe.product_id
            LEFT JOIN categories c ON c.id = pe.category_id
            LEFT JOIN brands b ON b.id = pe.brand_id
            WHERE mpc.book_edition_id = :ed_id
              AND mpc.case_cost_pct IS NOT NULL
              {direction_sql}
            ORDER BY ABS(mpc.case_cost_pct) DESC
            LIMIT :lim
        """),
        {"ed_id": str(edition.id), "lim": limit},
    ).all()
    return [
        MoverRow(
            code=r.code, description=r.description,
            category_slug=r.category_slug, brand_slug=r.brand_slug,
            case_cost=r.case_cost, prev_case_cost=r.prev_case_cost,
            case_cost_pct=r.case_cost_pct,
        )
        for r in rows
    ]


@router.get("/dashboard/watchlist-movers", response_model=list[MoverRow])
def watchlist_movers(
    distributor: str = Query("nj-allied"),
    user: dict = Depends(get_current_user),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
):
    edition = _current_edition(session, distributor)
    rows = session.execute(
        text("""
            SELECT p.code,
                   pe.description,
                   c.slug AS category_slug,
                   b.slug AS brand_slug,
                   mpc.case_cost,
                   mpc.prev_case_cost,
                   mpc.case_cost_pct
            FROM watchlist_items wi
            JOIN watchlists w ON w.id = wi.watchlist_id
            JOIN mv_price_changes mpc ON mpc.product_id = wi.product_id
            JOIN product_editions pe ON pe.id = mpc.product_edition_id
            JOIN products p ON p.id = pe.product_id
            LEFT JOIN categories c ON c.id = pe.category_id
            LEFT JOIN brands b ON b.id = pe.brand_id
            WHERE w.tenant_id = :tid
              AND mpc.book_edition_id = :ed_id
            ORDER BY ABS(mpc.case_cost_pct) DESC NULLS LAST
        """),
        {"tid": str(user["tenant_id"]), "ed_id": str(edition.id)},
    ).all()
    return [
        MoverRow(
            code=r.code, description=r.description,
            category_slug=r.category_slug, brand_slug=r.brand_slug,
            case_cost=r.case_cost, prev_case_cost=r.prev_case_cost,
            case_cost_pct=r.case_cost_pct,
        )
        for r in rows
    ]


class AlertEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    rule_type: str
    score: Decimal | None
    payload: dict
    fired_at: datetime
    read_at: datetime | None
    product_code: str | None


@router.get("/dashboard/alerts", response_model=list[AlertEventOut])
def list_alerts(
    limit: int = Query(50, ge=1, le=200),
    unread_only: bool = Query(False),
    user: dict = Depends(get_current_user),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
):
    stmt = (
        select(AlertEvent, Product.code)
        .outerjoin(Product, Product.id == AlertEvent.product_id)
        .where(AlertEvent.tenant_id == user["tenant_id"])
        .order_by(desc(AlertEvent.fired_at))
        .limit(limit)
    )
    if unread_only:
        stmt = stmt.where(AlertEvent.read_at.is_(None))
    rows = session.execute(stmt).all()
    return [
        AlertEventOut(
            id=ae.id,
            rule_type=ae.rule_type,
            score=ae.score,
            payload=ae.payload or {},
            fired_at=ae.fired_at,
            read_at=ae.read_at,
            product_code=code,
        )
        for ae, code in rows
    ]
