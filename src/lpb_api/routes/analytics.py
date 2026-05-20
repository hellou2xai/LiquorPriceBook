"""Pricing analytics endpoints for cross-edition comparison.

  GET /api/v1/analytics?view=<view>&limit=N

Views:
  price_drops       — products with biggest case cost decreases
  price_increases   — products with biggest case cost increases
  new_rips          — RIP offers added this edition (not in previous)
  lost_rips         — RIP offers removed (were in previous, gone now)
  best_value        — lowest effective cost (case_cost - RIP save)
  closeout_rip      — closeout items that ALSO have RIP offers (double savings)
  category_trends   — average price change per category
  new_products      — products in current edition but not previous
  discontinued      — products in previous edition but not current
  watchlist_movers  — price changes on user's tracked products
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, asc, case, desc, func, select
from sqlalchemy.orm import Session

from lpb_core.db import get_session
from lpb_core.db.models import (
    BookEdition,
    Brand,
    Category,
    Distributor,
    InventoryReduction,
    Product,
    ProductEdition,
    RipOffer,
    Watchlist,
    WatchlistItem,
)

from .auth import get_current_user

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])

VALID_VIEWS = {
    "price_drops", "price_increases", "new_rips", "lost_rips",
    "best_value", "closeout_rip", "category_trends",
    "new_products", "discontinued", "watchlist_movers",
}


# ── Schemas ──────────────────────────────────────────────────────────────

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
    tag: str | None = None  # extra context per view


class CategoryTrendRow(BaseModel):
    category: str
    product_count: int
    avg_case_cost: str
    prev_avg_case_cost: str
    avg_change: str
    avg_pct_change: float
    drops: int
    increases: int


class AnalyticsResponse(BaseModel):
    view: str
    edition_current: str
    edition_previous: str | None = None
    total: int
    rows: list[AnalyticsRow] = []
    category_rows: list[CategoryTrendRow] = []


# ── Helpers ──────────────────────────────────────────────────────────────

def _money(v) -> str | None:
    if v is None:
        return None
    return str(round(float(v), 2))


def _get_editions(session: Session, slug: str = "nj-allied"):
    """Return (current, previous) BookEdition or raise."""
    editions = session.execute(
        select(BookEdition)
        .join(Distributor, Distributor.id == BookEdition.distributor_id)
        .where(Distributor.slug == slug)
        .order_by(desc(BookEdition.year), desc(BookEdition.month),
                  desc(BookEdition.created_at))
        .limit(2)
    ).scalars().all()
    if not editions:
        raise HTTPException(status_code=404, detail="No editions found")
    current = editions[0]
    previous = editions[1] if len(editions) > 1 else None
    return current, previous


def _label(ed: BookEdition) -> str:
    return f"{ed.year:04d}-{ed.month:02d}"


# ── Main endpoint ────────────────────────────────────────────────────────

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

    current, previous = _get_editions(session, slug=distributor)

    handler = _HANDLERS[view]
    return handler(session, current, previous, limit, user)


# ── View handlers ────────────────────────────────────────────────────────

def _price_changes(session, current, previous, limit, user, *, direction: str):
    """Shared logic for price_drops and price_increases."""
    if previous is None:
        return AnalyticsResponse(
            view=f"price_{direction}s",
            edition_current=_label(current),
            total=0,
        )

    # Join current and previous editions on product_id
    CurPE = ProductEdition
    from sqlalchemy.orm import aliased
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
    """RIP offers in current edition that don't exist in previous."""
    if previous is None:
        return AnalyticsResponse(view="new_rips", edition_current=_label(current), total=0)

    # Subquery: product IDs with RIPs in previous edition
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
    """RIP offers in previous edition that are gone in current."""
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
    """Products ranked by lowest effective cost (case_cost - best RIP save)."""
    from sqlalchemy.orm import aliased

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
    """Products that are BOTH closeout AND have RIP offers — double savings."""
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
    """Average price change per category between editions."""
    if previous is None:
        return AnalyticsResponse(
            view="category_trends", edition_current=_label(current), total=0,
        )

    from sqlalchemy.orm import aliased
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
    """Products in current edition that don't exist in previous."""
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
    """Products in previous edition that are gone in current."""
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
    """Price changes on user's tracked products."""
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

    from sqlalchemy.orm import aliased
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


_HANDLERS = {
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
