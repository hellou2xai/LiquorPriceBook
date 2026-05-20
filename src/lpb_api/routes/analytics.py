"""Pricing analytics endpoints for cross-edition comparison.

  GET /api/v1/analytics?view=<view>&limit=N&distributor=<slug|all>

Views (single distributor):
  price_drops       -- products with biggest case cost decreases
  price_increases   -- products with biggest case cost increases
  new_rips          -- RIP offers added this edition (not in previous)
  lost_rips         -- RIP offers removed (were in previous, gone now)
  best_value        -- lowest effective cost (case_cost - RIP save)
  closeout_rip      -- closeout items that ALSO have RIP offers
  category_trends   -- average price change per category
  new_products      -- products in current edition but not previous
  discontinued      -- products in previous edition but not current
  watchlist_movers  -- price changes on user's tracked products

Cross-distributor views (distributor=all or specific):
  cross_category_compare  -- avg price per category per distributor
  cross_rip_coverage      -- RIP stats per category per distributor
  cross_brand_availability-- brand presence comparison
  cross_price_compare     -- matched product prices (via product_links)
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, asc, case, desc, func, or_, select
from sqlalchemy.orm import Session, aliased

from lpb_core.db import get_session
from lpb_core.db.models import (
    BookEdition,
    Brand,
    Category,
    Distributor,
    InventoryReduction,
    Product,
    ProductEdition,
    ProductLink,
    RipOffer,
    Watchlist,
    WatchlistItem,
)

from .auth import get_current_user

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])

SINGLE_VIEWS = {
    "price_drops", "price_increases", "new_rips", "lost_rips",
    "best_value", "closeout_rip", "category_trends",
    "new_products", "discontinued", "watchlist_movers",
}

CROSS_VIEWS = {
    "cross_category_compare", "cross_rip_coverage",
    "cross_brand_availability", "cross_price_compare",
}

VALID_VIEWS = SINGLE_VIEWS | CROSS_VIEWS


# -- Schemas ------------------------------------------------------------------

class AnalyticsRow(BaseModel):
    code: str
    description: str | None = None
    size: str | None = None
    brand: str | None = None
    category: str | None = None
    divisions: str | None = None
    case_cost: str | None = None
    prev_case_cost: str | None = None
    pct_change: float | None = None
    rip_save: str | None = None
    effective_cost: str | None = None
    rip_tier: str | None = None
    is_closeout: bool = False
    closeout_pct_off: float | None = None
    tag: str | None = None
    distributor_slug: str | None = None
    distributor_name: str | None = None


class CategoryTrendRow(BaseModel):
    category: str
    product_count: int
    avg_case_cost: str
    prev_avg_case_cost: str
    avg_change: str
    avg_pct_change: float
    drops: int
    increases: int
    distributor_slug: str | None = None
    distributor_name: str | None = None


class CrossCategoryRow(BaseModel):
    category: str
    product_count_a: int = 0
    product_count_b: int = 0
    avg_cost_a: str | None = None
    avg_cost_b: str | None = None
    diff: str | None = None
    pct_diff: float | None = None
    cheaper: str | None = None  # distributor slug that's cheaper
    distributor_a_slug: str = ""
    distributor_a_name: str = ""
    distributor_b_slug: str = ""
    distributor_b_name: str = ""


class CrossRipRow(BaseModel):
    category: str
    rip_count_a: int = 0
    rip_count_b: int = 0
    avg_save_a: str | None = None
    avg_save_b: str | None = None
    coverage_pct_a: float | None = None
    coverage_pct_b: float | None = None
    distributor_a_slug: str = ""
    distributor_a_name: str = ""
    distributor_b_slug: str = ""
    distributor_b_name: str = ""


class CrossBrandRow(BaseModel):
    brand: str
    count_a: int = 0
    count_b: int = 0
    exclusive_to: str | None = None  # distributor slug or None if shared
    distributor_a_slug: str = ""
    distributor_a_name: str = ""
    distributor_b_slug: str = ""
    distributor_b_name: str = ""


class CrossPriceRow(BaseModel):
    """Matched products across distributors via product_links."""
    link_id: str
    canonical_description: str | None = None
    size: str | None = None
    brand: str | None = None
    category: str | None = None
    code_a: str | None = None
    code_b: str | None = None
    case_cost_a: str | None = None
    case_cost_b: str | None = None
    diff: str | None = None
    pct_diff: float | None = None
    cheaper: str | None = None
    rip_save_a: str | None = None
    rip_save_b: str | None = None
    effective_a: str | None = None
    effective_b: str | None = None
    distributor_a_slug: str = ""
    distributor_a_name: str = ""
    distributor_b_slug: str = ""
    distributor_b_name: str = ""


class AnalyticsResponse(BaseModel):
    view: str
    edition_current: str
    edition_previous: str | None = None
    total: int
    rows: list[AnalyticsRow] = []
    category_rows: list[CategoryTrendRow] = []
    cross_category_rows: list[CrossCategoryRow] = []
    cross_rip_rows: list[CrossRipRow] = []
    cross_brand_rows: list[CrossBrandRow] = []
    cross_price_rows: list[CrossPriceRow] = []
    distributors: list[str] = []  # slugs involved


# -- Helpers ------------------------------------------------------------------

def _money(v) -> str | None:
    if v is None:
        return None
    return str(round(float(v), 2))


def _not_future_filter():
    """SQLAlchemy filter: edition (year, month) <= today."""
    today = date.today()
    return or_(
        BookEdition.year < today.year,
        and_(BookEdition.year == today.year,
             BookEdition.month <= today.month),
    )


def _get_editions(session: Session, slug: str = "nj-allied"):
    """Return (current, previous) BookEdition or raise.

    Current = latest non-future edition; previous = the one before it.
    """
    editions = session.execute(
        select(BookEdition)
        .join(Distributor, Distributor.id == BookEdition.distributor_id)
        .where(Distributor.slug == slug, _not_future_filter())
        .order_by(desc(BookEdition.year), desc(BookEdition.month),
                  desc(BookEdition.created_at))
        .limit(2)
    ).scalars().all()
    if not editions:
        raise HTTPException(status_code=404, detail="No editions found")
    current = editions[0]
    previous = editions[1] if len(editions) > 1 else None
    return current, previous


def _get_all_editions(session: Session):
    """Return dict[slug -> (current, previous, Distributor)] for all distributors."""
    rows = session.execute(
        select(BookEdition, Distributor)
        .join(Distributor, Distributor.id == BookEdition.distributor_id)
        .where(_not_future_filter())
        .order_by(Distributor.slug, desc(BookEdition.year),
                  desc(BookEdition.month), desc(BookEdition.created_at))
    ).all()
    if not rows:
        raise HTTPException(status_code=404, detail="No editions found")

    by_slug: dict[str, list[tuple]] = {}
    for ed, dist in rows:
        by_slug.setdefault(dist.slug, []).append((ed, dist))

    result: dict[str, tuple] = {}
    for slug, pairs in by_slug.items():
        cur = pairs[0][0]
        prev = pairs[1][0] if len(pairs) > 1 else None
        dist = pairs[0][1]
        result[slug] = (cur, prev, dist)
    return result


def _label(ed: BookEdition) -> str:
    return f"{ed.year:04d}-{ed.month:02d}"


def _dist_info(session: Session, edition: BookEdition) -> tuple[str, str]:
    """Return (slug, name) for a BookEdition's distributor."""
    row = session.execute(
        select(Distributor.slug, Distributor.name)
        .where(Distributor.id == edition.distributor_id)
    ).first()
    return (row.slug, row.name) if row else ("unknown", "Unknown")


# -- Main endpoint ------------------------------------------------------------

@router.get("", response_model=AnalyticsResponse)
def get_analytics(
    view: str = Query(..., description="Analysis view"),
    limit: int = Query(100, ge=1, le=500),
    distributor: str = Query("nj-allied"),
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if view not in VALID_VIEWS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid view. Valid: {', '.join(sorted(VALID_VIEWS))}",
        )

    # Cross-distributor views
    if view in CROSS_VIEWS:
        return _CROSS_HANDLERS[view](session, limit, user)

    # Single-distributor views with distributor=all support
    if distributor == "all":
        return _handle_all_distributors(view, session, limit, user)

    current, previous = _get_editions(session, slug=distributor)
    dslug, dname = _dist_info(session, current)
    handler = _SINGLE_HANDLERS[view]
    resp = handler(session, current, previous, limit, user)
    # Stamp distributor info on rows
    for r in resp.rows:
        r.distributor_slug = dslug
        r.distributor_name = dname
    for r in resp.category_rows:
        r.distributor_slug = dslug
        r.distributor_name = dname
    resp.distributors = [dslug]
    return resp


def _handle_all_distributors(view, session, limit, user):
    """Run a single-distributor view across all distributors and merge."""
    all_eds = _get_all_editions(session)
    handler = _SINGLE_HANDLERS[view]

    merged_rows: list[AnalyticsRow] = []
    merged_cat_rows: list[CategoryTrendRow] = []
    dist_slugs = []
    edition_labels = []

    for slug, (cur, prev, dist) in sorted(all_eds.items()):
        resp = handler(session, cur, prev, limit, user)
        for r in resp.rows:
            r.distributor_slug = dist.slug
            r.distributor_name = dist.name
            merged_rows.append(r)
        for r in resp.category_rows:
            r.distributor_slug = dist.slug
            r.distributor_name = dist.name
            merged_cat_rows.append(r)
        dist_slugs.append(slug)
        edition_labels.append(resp.edition_current)

    # Sort merged rows by absolute pct_change
    if view in ("price_drops", "price_increases", "watchlist_movers", "best_value"):
        merged_rows.sort(key=lambda r: abs(r.pct_change or 0), reverse=True)
    merged_rows = merged_rows[:limit]
    merged_cat_rows = merged_cat_rows[:limit]

    return AnalyticsResponse(
        view=view,
        edition_current=" / ".join(edition_labels) if edition_labels else "",
        total=len(merged_rows) or len(merged_cat_rows),
        rows=merged_rows,
        category_rows=merged_cat_rows,
        distributors=dist_slugs,
    )


# -- Single-distributor view handlers ----------------------------------------

def _price_changes(session, current, previous, limit, user, *, direction: str):
    if previous is None:
        return AnalyticsResponse(
            view=f"price_{direction}s",
            edition_current=_label(current),
            total=0,
        )

    CurPE = ProductEdition
    PrevPE = aliased(ProductEdition, name="prev_pe")

    stmt = (
        select(
            Product.code,
            CurPE.description,
            CurPE.size,
            CurPE.divisions,
            CurPE.case_cost.label("cur_cost"),
            PrevPE.case_cost.label("prev_cost"),
            Category.display_name.label("category"),
            Brand.display_name.label("brand"),
        )
        .select_from(CurPE)
        .join(Product, Product.id == CurPE.product_id)
        .join(PrevPE, and_(
            PrevPE.product_id == CurPE.product_id,
            PrevPE.book_edition_id == previous.id,
        ))
        .outerjoin(Category, Category.id == CurPE.category_id)
        .outerjoin(Brand, Brand.id == CurPE.brand_id)
        .where(
            CurPE.book_edition_id == current.id,
            CurPE.case_cost.is_not(None),
            PrevPE.case_cost.is_not(None),
            CurPE.case_cost != PrevPE.case_cost,
        )
    )

    if direction == "drop":
        stmt = stmt.where(CurPE.case_cost < PrevPE.case_cost)
        stmt = stmt.order_by(asc(
            (CurPE.case_cost - PrevPE.case_cost) / PrevPE.case_cost
        ))
    else:
        stmt = stmt.where(CurPE.case_cost > PrevPE.case_cost)
        stmt = stmt.order_by(desc(
            (CurPE.case_cost - PrevPE.case_cost) / PrevPE.case_cost
        ))

    stmt = stmt.limit(limit)
    rows = session.execute(stmt).all()

    result_rows = []
    for r in rows:
        change = float(r.cur_cost - r.prev_cost)
        pct = round(change / float(r.prev_cost) * 100, 1) if r.prev_cost else None
        result_rows.append(AnalyticsRow(
            code=r.code,
            description=r.description,
            size=r.size,
            brand=r.brand,
            category=r.category,
            divisions=r.divisions,
            case_cost=_money(r.cur_cost),
            prev_case_cost=_money(r.prev_cost),
            pct_change=pct,
            tag=f"{'↓' if change < 0 else '↑'} ${abs(change):.2f}",
        ))

    return AnalyticsResponse(
        view=f"price_{direction}s" if direction == "drop" else "price_increases",
        edition_current=_label(current),
        edition_previous=_label(previous),
        total=len(result_rows),
        rows=result_rows,
    )


def _price_drops(session, current, previous, limit, user):
    return _price_changes(session, current, previous, limit, user, direction="drop")


def _price_increases(session, current, previous, limit, user):
    return _price_changes(session, current, previous, limit, user, direction="increase")


def _new_rips(session, current, previous, limit, user):
    if previous is None:
        return AnalyticsResponse(view="new_rips", edition_current=_label(current), total=0)

    prev_rip_pids = (
        select(Product.id)
        .join(ProductEdition, ProductEdition.product_id == Product.id)
        .join(RipOffer, RipOffer.product_edition_id == ProductEdition.id)
        .where(ProductEdition.book_edition_id == previous.id)
    ).scalar_subquery()

    stmt = (
        select(
            Product.code,
            ProductEdition.description,
            ProductEdition.size,
            ProductEdition.case_cost,
            ProductEdition.divisions,
            Category.display_name.label("category"),
            Brand.display_name.label("brand"),
            func.max(RipOffer.save_amount).label("best_save"),
            func.min(RipOffer.tier_cases).label("min_tier"),
        )
        .select_from(RipOffer)
        .join(ProductEdition, ProductEdition.id == RipOffer.product_edition_id)
        .join(Product, Product.id == ProductEdition.product_id)
        .outerjoin(Category, Category.id == ProductEdition.category_id)
        .outerjoin(Brand, Brand.id == ProductEdition.brand_id)
        .where(
            ProductEdition.book_edition_id == current.id,
            Product.id.not_in(prev_rip_pids),
        )
        .group_by(
            Product.code, ProductEdition.description, ProductEdition.size,
            ProductEdition.case_cost, ProductEdition.divisions,
            Category.display_name, Brand.display_name,
        )
        .order_by(desc(func.max(RipOffer.save_amount)))
        .limit(limit)
    )

    rows = session.execute(stmt).all()
    result = [
        AnalyticsRow(
            code=r.code, description=r.description, size=r.size,
            brand=r.brand, category=r.category, divisions=r.divisions,
            case_cost=_money(r.case_cost),
            rip_save=_money(r.best_save),
            effective_cost=(
                _money(max(0, float(r.case_cost) - float(r.best_save)))
                if r.case_cost and r.best_save else None
            ),
            rip_tier=f"{r.min_tier}CS",
            tag="New RIP",
        )
        for r in rows
    ]

    return AnalyticsResponse(
        view="new_rips", edition_current=_label(current),
        edition_previous=_label(previous), total=len(result), rows=result,
    )


def _lost_rips(session, current, previous, limit, user):
    if previous is None:
        return AnalyticsResponse(view="lost_rips", edition_current=_label(current), total=0)

    cur_rip_pids = (
        select(Product.id)
        .join(ProductEdition, ProductEdition.product_id == Product.id)
        .join(RipOffer, RipOffer.product_edition_id == ProductEdition.id)
        .where(ProductEdition.book_edition_id == current.id)
    ).scalar_subquery()

    stmt = (
        select(
            Product.code,
            ProductEdition.description,
            ProductEdition.size,
            ProductEdition.case_cost,
            ProductEdition.divisions,
            Category.display_name.label("category"),
            Brand.display_name.label("brand"),
            func.max(RipOffer.save_amount).label("best_save"),
        )
        .select_from(RipOffer)
        .join(ProductEdition, ProductEdition.id == RipOffer.product_edition_id)
        .join(Product, Product.id == ProductEdition.product_id)
        .outerjoin(Category, Category.id == ProductEdition.category_id)
        .outerjoin(Brand, Brand.id == ProductEdition.brand_id)
        .where(
            ProductEdition.book_edition_id == previous.id,
            Product.id.not_in(cur_rip_pids),
        )
        .group_by(
            Product.code, ProductEdition.description, ProductEdition.size,
            ProductEdition.case_cost, ProductEdition.divisions,
            Category.display_name, Brand.display_name,
        )
        .order_by(desc(func.max(RipOffer.save_amount)))
        .limit(limit)
    )

    rows = session.execute(stmt).all()
    result = [
        AnalyticsRow(
            code=r.code, description=r.description, size=r.size,
            brand=r.brand, category=r.category, divisions=r.divisions,
            case_cost=_money(r.case_cost),
            rip_save=_money(r.best_save),
            tag="RIP Removed",
        )
        for r in rows
    ]

    return AnalyticsResponse(
        view="lost_rips", edition_current=_label(current),
        edition_previous=_label(previous), total=len(result), rows=result,
    )


def _best_value(session, current, previous, limit, user):
    PrevPE = aliased(ProductEdition, name="prev_pe")

    stmt = (
        select(
            Product.code,
            ProductEdition.description,
            ProductEdition.size,
            ProductEdition.case_cost,
            ProductEdition.divisions,
            Category.display_name.label("category"),
            Brand.display_name.label("brand"),
            func.max(RipOffer.save_amount).label("best_save"),
            PrevPE.case_cost.label("prev_cost"),
        )
        .select_from(ProductEdition)
        .join(Product, Product.id == ProductEdition.product_id)
        .join(RipOffer, RipOffer.product_edition_id == ProductEdition.id)
        .outerjoin(Category, Category.id == ProductEdition.category_id)
        .outerjoin(Brand, Brand.id == ProductEdition.brand_id)
        .outerjoin(PrevPE, and_(
            PrevPE.product_id == ProductEdition.product_id,
            PrevPE.book_edition_id == (previous.id if previous else None),
        ))
        .where(
            ProductEdition.book_edition_id == current.id,
            ProductEdition.case_cost.is_not(None),
        )
        .group_by(
            Product.code, ProductEdition.description, ProductEdition.size,
            ProductEdition.case_cost, ProductEdition.divisions,
            Category.display_name, Brand.display_name,
            PrevPE.case_cost,
        )
        .order_by(asc(ProductEdition.case_cost - func.max(RipOffer.save_amount)))
        .limit(limit)
    )

    rows = session.execute(stmt).all()
    result = []
    for r in rows:
        eff = max(0, float(r.case_cost) - float(r.best_save)) if r.best_save else None
        pct = None
        if r.prev_cost and r.case_cost:
            change = float(r.case_cost) - float(r.prev_cost)
            pct = round(change / float(r.prev_cost) * 100, 1)
        save_pct = (
            round(float(r.best_save) / float(r.case_cost) * 100, 1)
            if r.case_cost and r.best_save else None
        )
        result.append(AnalyticsRow(
            code=r.code, description=r.description, size=r.size,
            brand=r.brand, category=r.category, divisions=r.divisions,
            case_cost=_money(r.case_cost),
            prev_case_cost=_money(r.prev_cost),
            rip_save=_money(r.best_save),
            effective_cost=_money(eff) if eff is not None else None,
            pct_change=pct,
            tag=f"Save {save_pct}%" if save_pct else None,
        ))

    return AnalyticsResponse(
        view="best_value", edition_current=_label(current),
        edition_previous=_label(previous) if previous else None,
        total=len(result), rows=result,
    )


def _closeout_rip(session, current, _previous, limit, user):
    stmt = (
        select(
            Product.code,
            ProductEdition.description,
            ProductEdition.size,
            ProductEdition.case_cost,
            ProductEdition.divisions,
            Category.display_name.label("category"),
            Brand.display_name.label("brand"),
            func.max(RipOffer.save_amount).label("best_save"),
            InventoryReduction.best_case.label("closeout_case"),
            InventoryReduction.original_case.label("original_case"),
        )
        .select_from(InventoryReduction)
        .join(Product, Product.id == InventoryReduction.product_id)
        .join(ProductEdition, and_(
            ProductEdition.product_id == Product.id,
            ProductEdition.book_edition_id == current.id,
        ))
        .join(RipOffer, RipOffer.product_edition_id == ProductEdition.id)
        .outerjoin(Category, Category.id == ProductEdition.category_id)
        .outerjoin(Brand, Brand.id == ProductEdition.brand_id)
        .where(InventoryReduction.book_edition_id == current.id)
        .group_by(
            Product.code, ProductEdition.description, ProductEdition.size,
            ProductEdition.case_cost, ProductEdition.divisions,
            Category.display_name, Brand.display_name,
            InventoryReduction.best_case, InventoryReduction.original_case,
        )
        .order_by(desc(func.max(RipOffer.save_amount)))
        .limit(limit)
    )

    rows = session.execute(stmt).all()
    result = []
    for r in rows:
        co_pct = None
        if r.original_case and r.closeout_case:
            co_pct = round((1 - float(r.closeout_case) / float(r.original_case)) * 100, 1)
        result.append(AnalyticsRow(
            code=r.code, description=r.description, size=r.size,
            brand=r.brand, category=r.category, divisions=r.divisions,
            case_cost=_money(r.closeout_case or r.case_cost),
            prev_case_cost=_money(r.original_case),
            rip_save=_money(r.best_save),
            effective_cost=_money(max(
                0,
                float(r.closeout_case or r.case_cost or 0)
                - float(r.best_save or 0),
            )),
            is_closeout=True,
            closeout_pct_off=co_pct,
            tag="Closeout + RIP",
        ))

    return AnalyticsResponse(
        view="closeout_rip", edition_current=_label(current),
        total=len(result), rows=result,
    )


def _category_trends(session, current, previous, limit, user):
    if previous is None:
        return AnalyticsResponse(
            view="category_trends", edition_current=_label(current), total=0,
        )

    PrevPE = aliased(ProductEdition, name="prev_pe")

    stmt = (
        select(
            Category.display_name.label("category"),
            func.count().label("cnt"),
            func.avg(ProductEdition.case_cost).label("avg_cur"),
            func.avg(PrevPE.case_cost).label("avg_prev"),
            func.avg(ProductEdition.case_cost - PrevPE.case_cost).label("avg_change"),
            func.sum(case(
                (ProductEdition.case_cost < PrevPE.case_cost, 1),
                else_=0,
            )).label("drops"),
            func.sum(case(
                (ProductEdition.case_cost > PrevPE.case_cost, 1),
                else_=0,
            )).label("increases"),
        )
        .select_from(ProductEdition)
        .join(PrevPE, and_(
            PrevPE.product_id == ProductEdition.product_id,
            PrevPE.book_edition_id == previous.id,
        ))
        .join(Category, Category.id == ProductEdition.category_id)
        .where(
            ProductEdition.book_edition_id == current.id,
            ProductEdition.case_cost.is_not(None),
            PrevPE.case_cost.is_not(None),
        )
        .group_by(Category.display_name)
        .having(func.count() >= 3)
        .order_by(asc(func.avg(ProductEdition.case_cost - PrevPE.case_cost)))
        .limit(limit)
    )

    rows = session.execute(stmt).all()
    cat_rows = []
    for r in rows:
        avg_pct = 0.0
        if r.avg_prev and float(r.avg_prev) > 0:
            avg_pct = round(float(r.avg_change) / float(r.avg_prev) * 100, 2)
        cat_rows.append(CategoryTrendRow(
            category=r.category,
            product_count=r.cnt,
            avg_case_cost=_money(r.avg_cur),
            prev_avg_case_cost=_money(r.avg_prev),
            avg_change=_money(r.avg_change),
            avg_pct_change=avg_pct,
            drops=int(r.drops or 0),
            increases=int(r.increases or 0),
        ))

    return AnalyticsResponse(
        view="category_trends", edition_current=_label(current),
        edition_previous=_label(previous), total=len(cat_rows),
        category_rows=cat_rows,
    )


def _new_products(session, current, previous, limit, user):
    if previous is None:
        return AnalyticsResponse(view="new_products", edition_current=_label(current), total=0)

    prev_pids = (
        select(ProductEdition.product_id)
        .where(ProductEdition.book_edition_id == previous.id)
    ).scalar_subquery()

    stmt = (
        select(
            Product.code,
            ProductEdition.description,
            ProductEdition.size,
            ProductEdition.case_cost,
            ProductEdition.divisions,
            Category.display_name.label("category"),
            Brand.display_name.label("brand"),
        )
        .select_from(ProductEdition)
        .join(Product, Product.id == ProductEdition.product_id)
        .outerjoin(Category, Category.id == ProductEdition.category_id)
        .outerjoin(Brand, Brand.id == ProductEdition.brand_id)
        .where(
            ProductEdition.book_edition_id == current.id,
            ProductEdition.product_id.not_in(prev_pids),
        )
        .order_by(asc(ProductEdition.description))
        .limit(limit)
    )

    rows = session.execute(stmt).all()
    result = [
        AnalyticsRow(
            code=r.code, description=r.description, size=r.size,
            brand=r.brand, category=r.category, divisions=r.divisions,
            case_cost=_money(r.case_cost),
            tag="New",
        )
        for r in rows
    ]

    return AnalyticsResponse(
        view="new_products", edition_current=_label(current),
        edition_previous=_label(previous), total=len(result), rows=result,
    )


def _discontinued(session, current, previous, limit, user):
    if previous is None:
        return AnalyticsResponse(view="discontinued", edition_current=_label(current), total=0)

    cur_pids = (
        select(ProductEdition.product_id)
        .where(ProductEdition.book_edition_id == current.id)
    ).scalar_subquery()

    stmt = (
        select(
            Product.code,
            ProductEdition.description,
            ProductEdition.size,
            ProductEdition.case_cost,
            ProductEdition.divisions,
            Category.display_name.label("category"),
            Brand.display_name.label("brand"),
        )
        .select_from(ProductEdition)
        .join(Product, Product.id == ProductEdition.product_id)
        .outerjoin(Category, Category.id == ProductEdition.category_id)
        .outerjoin(Brand, Brand.id == ProductEdition.brand_id)
        .where(
            ProductEdition.book_edition_id == previous.id,
            ProductEdition.product_id.not_in(cur_pids),
        )
        .order_by(asc(ProductEdition.description))
        .limit(limit)
    )

    rows = session.execute(stmt).all()
    result = [
        AnalyticsRow(
            code=r.code, description=r.description, size=r.size,
            brand=r.brand, category=r.category, divisions=r.divisions,
            case_cost=_money(r.case_cost),
            tag="Discontinued",
        )
        for r in rows
    ]

    return AnalyticsResponse(
        view="discontinued", edition_current=_label(current),
        edition_previous=_label(previous), total=len(result), rows=result,
    )


def _watchlist_movers(session, current, previous, limit, user):
    if previous is None:
        return AnalyticsResponse(view="watchlist_movers", edition_current=_label(current), total=0)

    default_wl = session.execute(
        select(Watchlist).where(
            Watchlist.tenant_id == user["tenant_id"],
            Watchlist.is_default == True,  # noqa: E712
        )
    ).scalar_one_or_none()

    if default_wl is None:
        return AnalyticsResponse(view="watchlist_movers", edition_current=_label(current), total=0)

    wl_product_ids = (
        select(WatchlistItem.product_id)
        .where(WatchlistItem.watchlist_id == default_wl.id)
    ).scalar_subquery()

    PrevPE = aliased(ProductEdition, name="prev_pe")

    stmt = (
        select(
            Product.code,
            ProductEdition.description,
            ProductEdition.size,
            ProductEdition.case_cost.label("cur_cost"),
            PrevPE.case_cost.label("prev_cost"),
            ProductEdition.divisions,
            Category.display_name.label("category"),
            Brand.display_name.label("brand"),
        )
        .select_from(ProductEdition)
        .join(Product, Product.id == ProductEdition.product_id)
        .join(PrevPE, and_(
            PrevPE.product_id == ProductEdition.product_id,
            PrevPE.book_edition_id == previous.id,
        ))
        .outerjoin(Category, Category.id == ProductEdition.category_id)
        .outerjoin(Brand, Brand.id == ProductEdition.brand_id)
        .where(
            ProductEdition.book_edition_id == current.id,
            ProductEdition.product_id.in_(wl_product_ids),
            ProductEdition.case_cost.is_not(None),
            PrevPE.case_cost.is_not(None),
            ProductEdition.case_cost != PrevPE.case_cost,
        )
        .order_by(asc(
            (ProductEdition.case_cost - PrevPE.case_cost) / PrevPE.case_cost
        ))
        .limit(limit)
    )

    rows = session.execute(stmt).all()
    result = []
    for r in rows:
        change = float(r.cur_cost - r.prev_cost)
        pct = round(change / float(r.prev_cost) * 100, 1) if r.prev_cost else None
        result.append(AnalyticsRow(
            code=r.code, description=r.description, size=r.size,
            brand=r.brand, category=r.category, divisions=r.divisions,
            case_cost=_money(r.cur_cost),
            prev_case_cost=_money(r.prev_cost),
            pct_change=pct,
            tag="Tracked",
        ))

    return AnalyticsResponse(
        view="watchlist_movers", edition_current=_label(current),
        edition_previous=_label(previous), total=len(result), rows=result,
    )


# -- Cross-distributor view handlers -----------------------------------------

def _cross_category_compare(session: Session, limit: int, user: dict):
    """Average case cost per category per distributor — side by side."""
    all_eds = _get_all_editions(session)
    slugs = sorted(all_eds.keys())
    if len(slugs) < 2:
        return AnalyticsResponse(view="cross_category_compare", edition_current="", total=0)

    slug_a, slug_b = slugs[0], slugs[1]
    ed_a, _, dist_a = all_eds[slug_a]
    ed_b, _, dist_b = all_eds[slug_b]

    # Get avg case cost per category for each distributor
    def _cat_stats(eid):
        return dict(session.execute(
            select(
                Category.display_name,
                func.count(ProductEdition.id).label("cnt"),
                func.avg(ProductEdition.case_cost).label("avg_cost"),
            )
            .join(Category, Category.id == ProductEdition.category_id)
            .where(
                ProductEdition.book_edition_id == eid,
                ProductEdition.case_cost.is_not(None),
            )
            .group_by(Category.display_name)
            .having(func.count() >= 3)
        ).all(), key=lambda r: r[0])  # type: ignore

    # Collect raw data
    rows_a = session.execute(
        select(
            Category.display_name.label("cat"),
            func.count(ProductEdition.id).label("cnt"),
            func.avg(ProductEdition.case_cost).label("avg_cost"),
        )
        .join(Category, Category.id == ProductEdition.category_id)
        .where(ProductEdition.book_edition_id == ed_a.id, ProductEdition.case_cost.is_not(None))
        .group_by(Category.display_name)
        .having(func.count() >= 3)
    ).all()

    rows_b = session.execute(
        select(
            Category.display_name.label("cat"),
            func.count(ProductEdition.id).label("cnt"),
            func.avg(ProductEdition.case_cost).label("avg_cost"),
        )
        .join(Category, Category.id == ProductEdition.category_id)
        .where(ProductEdition.book_edition_id == ed_b.id, ProductEdition.case_cost.is_not(None))
        .group_by(Category.display_name)
        .having(func.count() >= 3)
    ).all()

    stats_a = {r.cat: (r.cnt, float(r.avg_cost)) for r in rows_a}
    stats_b = {r.cat: (r.cnt, float(r.avg_cost)) for r in rows_b}

    all_cats = sorted(set(stats_a.keys()) | set(stats_b.keys()))
    result = []
    for cat in all_cats:
        cnt_a, avg_a = stats_a.get(cat, (0, None))
        cnt_b, avg_b = stats_b.get(cat, (0, None))
        diff = None
        pct_diff = None
        cheaper = None
        if avg_a is not None and avg_b is not None:
            diff = round(avg_a - avg_b, 2)
            if avg_b > 0:
                pct_diff = round(diff / avg_b * 100, 1)
            cheaper = slug_a if avg_a < avg_b else slug_b if avg_b < avg_a else None
        result.append(CrossCategoryRow(
            category=cat,
            product_count_a=cnt_a,
            product_count_b=cnt_b,
            avg_cost_a=_money(avg_a),
            avg_cost_b=_money(avg_b),
            diff=_money(diff),
            pct_diff=pct_diff,
            cheaper=cheaper,
            distributor_a_slug=dist_a.slug,
            distributor_a_name=dist_a.name,
            distributor_b_slug=dist_b.slug,
            distributor_b_name=dist_b.name,
        ))

    # Sort by absolute difference
    result.sort(key=lambda r: abs(r.pct_diff or 0), reverse=True)
    result = result[:limit]

    return AnalyticsResponse(
        view="cross_category_compare",
        edition_current=f"{_label(ed_a)} / {_label(ed_b)}",
        total=len(result),
        cross_category_rows=result,
        distributors=[slug_a, slug_b],
    )


def _cross_rip_coverage(session: Session, limit: int, user: dict):
    """RIP offer coverage and avg savings per category per distributor."""
    all_eds = _get_all_editions(session)
    slugs = sorted(all_eds.keys())
    if len(slugs) < 2:
        return AnalyticsResponse(view="cross_rip_coverage", edition_current="", total=0)

    slug_a, slug_b = slugs[0], slugs[1]
    ed_a, _, dist_a = all_eds[slug_a]
    ed_b, _, dist_b = all_eds[slug_b]

    def _rip_stats(eid):
        rows = session.execute(
            select(
                Category.display_name.label("cat"),
                func.count(func.distinct(ProductEdition.id)).label("total"),
                func.count(func.distinct(RipOffer.product_edition_id)).label("rip_count"),
                func.avg(RipOffer.save_amount).label("avg_save"),
            )
            .select_from(ProductEdition)
            .join(Category, Category.id == ProductEdition.category_id)
            .outerjoin(RipOffer, RipOffer.product_edition_id == ProductEdition.id)
            .where(ProductEdition.book_edition_id == eid)
            .group_by(Category.display_name)
            .having(func.count(func.distinct(ProductEdition.id)) >= 3)
        ).all()
        return {
            r.cat: (r.total, r.rip_count, float(r.avg_save) if r.avg_save else None)
            for r in rows
        }

    stats_a = _rip_stats(ed_a.id)
    stats_b = _rip_stats(ed_b.id)

    all_cats = sorted(set(stats_a.keys()) | set(stats_b.keys()))
    result = []
    for cat in all_cats:
        total_a, rip_a, avg_save_a = stats_a.get(cat, (0, 0, None))
        total_b, rip_b, avg_save_b = stats_b.get(cat, (0, 0, None))
        cov_a = round(rip_a / total_a * 100, 1) if total_a > 0 else None
        cov_b = round(rip_b / total_b * 100, 1) if total_b > 0 else None
        result.append(CrossRipRow(
            category=cat,
            rip_count_a=rip_a,
            rip_count_b=rip_b,
            avg_save_a=_money(avg_save_a),
            avg_save_b=_money(avg_save_b),
            coverage_pct_a=cov_a,
            coverage_pct_b=cov_b,
            distributor_a_slug=dist_a.slug,
            distributor_a_name=dist_a.name,
            distributor_b_slug=dist_b.slug,
            distributor_b_name=dist_b.name,
        ))

    # Sort by difference in coverage
    result.sort(key=lambda r: abs((r.coverage_pct_a or 0) - (r.coverage_pct_b or 0)), reverse=True)
    result = result[:limit]

    return AnalyticsResponse(
        view="cross_rip_coverage",
        edition_current=f"{_label(ed_a)} / {_label(ed_b)}",
        total=len(result),
        cross_rip_rows=result,
        distributors=[slug_a, slug_b],
    )


def _cross_brand_availability(session: Session, limit: int, user: dict):
    """Brand presence comparison across distributors."""
    all_eds = _get_all_editions(session)
    slugs = sorted(all_eds.keys())
    if len(slugs) < 2:
        return AnalyticsResponse(view="cross_brand_availability", edition_current="", total=0)

    slug_a, slug_b = slugs[0], slugs[1]
    ed_a, _, dist_a = all_eds[slug_a]
    ed_b, _, dist_b = all_eds[slug_b]

    def _brand_counts(eid):
        rows = session.execute(
            select(
                Brand.display_name.label("brand"),
                func.count(ProductEdition.id).label("cnt"),
            )
            .join(Brand, Brand.id == ProductEdition.brand_id)
            .where(ProductEdition.book_edition_id == eid)
            .group_by(Brand.display_name)
        ).all()
        return {r.brand: r.cnt for r in rows}

    counts_a = _brand_counts(ed_a.id)
    counts_b = _brand_counts(ed_b.id)

    all_brands = sorted(set(counts_a.keys()) | set(counts_b.keys()))
    result = []
    for brand in all_brands:
        ca = counts_a.get(brand, 0)
        cb = counts_b.get(brand, 0)
        exclusive = None
        if ca > 0 and cb == 0:
            exclusive = slug_a
        elif cb > 0 and ca == 0:
            exclusive = slug_b
        result.append(CrossBrandRow(
            brand=brand,
            count_a=ca,
            count_b=cb,
            exclusive_to=exclusive,
            distributor_a_slug=dist_a.slug,
            distributor_a_name=dist_a.name,
            distributor_b_slug=dist_b.slug,
            distributor_b_name=dist_b.name,
        ))

    # Sort: exclusives first, then by total count descending
    result.sort(key=lambda r: (r.exclusive_to is None, -(r.count_a + r.count_b)))
    result = result[:limit]

    return AnalyticsResponse(
        view="cross_brand_availability",
        edition_current=f"{_label(ed_a)} / {_label(ed_b)}",
        total=len(result),
        cross_brand_rows=result,
        distributors=[slug_a, slug_b],
    )


def _cross_price_compare(session: Session, limit: int, user: dict):
    """Compare prices for linked products across distributors (V2)."""
    all_eds = _get_all_editions(session)
    slugs = sorted(all_eds.keys())
    if len(slugs) < 2:
        return AnalyticsResponse(view="cross_price_compare", edition_current="", total=0)

    slug_a, slug_b = slugs[0], slugs[1]
    ed_a, _, dist_a = all_eds[slug_a]
    ed_b, _, dist_b = all_eds[slug_b]

    # Find products with link_id set, get their current edition data
    ProdA = aliased(Product, name="prod_a")
    ProdB = aliased(Product, name="prod_b")
    PeA = aliased(ProductEdition, name="pe_a")
    PeB = aliased(ProductEdition, name="pe_b")
    RipA = aliased(RipOffer, name="rip_a")
    RipB = aliased(RipOffer, name="rip_b")

    # Subqueries for best RIP per product_edition
    best_rip_a = (
        select(func.max(RipA.save_amount))
        .where(RipA.product_edition_id == PeA.id)
        .correlate(PeA)
        .scalar_subquery()
    )
    best_rip_b = (
        select(func.max(RipB.save_amount))
        .where(RipB.product_edition_id == PeB.id)
        .correlate(PeB)
        .scalar_subquery()
    )

    stmt = (
        select(
            ProductLink.id.label("link_id"),
            ProductLink.canonical_description,
            ProductLink.size,
            Brand.display_name.label("brand"),
            Category.display_name.label("category"),
            ProdA.code.label("code_a"),
            ProdB.code.label("code_b"),
            PeA.case_cost.label("cost_a"),
            PeB.case_cost.label("cost_b"),
            best_rip_a.label("rip_a"),
            best_rip_b.label("rip_b"),
        )
        .select_from(ProductLink)
        .join(ProdA, and_(ProdA.link_id == ProductLink.id, ProdA.distributor_id == dist_a.id))
        .join(ProdB, and_(ProdB.link_id == ProductLink.id, ProdB.distributor_id == dist_b.id))
        .join(PeA, and_(PeA.product_id == ProdA.id, PeA.book_edition_id == ed_a.id))
        .join(PeB, and_(PeB.product_id == ProdB.id, PeB.book_edition_id == ed_b.id))
        .outerjoin(Brand, Brand.id == ProductLink.brand_id)
        .outerjoin(Category, Category.id == ProductLink.category_id)
        .where(
            PeA.case_cost.is_not(None),
            PeB.case_cost.is_not(None),
        )
        .order_by(desc(func.abs(PeA.case_cost - PeB.case_cost)))
        .limit(limit)
    )

    rows = session.execute(stmt).all()
    result = []
    for r in rows:
        cost_a = float(r.cost_a) if r.cost_a else None
        cost_b = float(r.cost_b) if r.cost_b else None
        diff = None
        pct_diff = None
        cheaper = None
        if cost_a is not None and cost_b is not None:
            diff = round(cost_a - cost_b, 2)
            avg_cost = (cost_a + cost_b) / 2
            pct_diff = round(diff / avg_cost * 100, 1) if avg_cost > 0 else None
            cheaper = slug_a if cost_a < cost_b else slug_b if cost_b < cost_a else None

        rip_a = float(r.rip_a) if r.rip_a else None
        rip_b = float(r.rip_b) if r.rip_b else None
        eff_a = _money(max(0, cost_a - rip_a)) if cost_a and rip_a else _money(cost_a)
        eff_b = _money(max(0, cost_b - rip_b)) if cost_b and rip_b else _money(cost_b)

        result.append(CrossPriceRow(
            link_id=str(r.link_id),
            canonical_description=r.canonical_description,
            size=r.size,
            brand=r.brand,
            category=r.category,
            code_a=r.code_a,
            code_b=r.code_b,
            case_cost_a=_money(cost_a),
            case_cost_b=_money(cost_b),
            diff=_money(diff),
            pct_diff=pct_diff,
            cheaper=cheaper,
            rip_save_a=_money(rip_a),
            rip_save_b=_money(rip_b),
            effective_a=eff_a,
            effective_b=eff_b,
            distributor_a_slug=dist_a.slug,
            distributor_a_name=dist_a.name,
            distributor_b_slug=dist_b.slug,
            distributor_b_name=dist_b.name,
        ))

    return AnalyticsResponse(
        view="cross_price_compare",
        edition_current=f"{_label(ed_a)} / {_label(ed_b)}",
        total=len(result),
        cross_price_rows=result,
        distributors=[slug_a, slug_b],
    )


# -- Handler registries -------------------------------------------------------

_SINGLE_HANDLERS = {
    "price_drops": _price_drops,
    "price_increases": _price_increases,
    "new_rips": _new_rips,
    "lost_rips": _lost_rips,
    "best_value": _best_value,
    "closeout_rip": _closeout_rip,
    "category_trends": _category_trends,
    "new_products": _new_products,
    "discontinued": _discontinued,
    "watchlist_movers": _watchlist_movers,
}

_CROSS_HANDLERS = {
    "cross_category_compare": _cross_category_compare,
    "cross_rip_coverage": _cross_rip_coverage,
    "cross_brand_availability": _cross_brand_availability,
    "cross_price_compare": _cross_price_compare,
}

# Keep legacy name for backwards compat
_HANDLERS = {**_SINGLE_HANDLERS, **_CROSS_HANDLERS}
