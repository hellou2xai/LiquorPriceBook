"""Decision support endpoints: RIP ratings, missed opportunities, order scorecard.

  RIP Ratings:
    GET    /api/v1/rip-ratings?product_code=X     get user's rating + aggregates
    POST   /api/v1/rip-ratings                     rate a RIP (thumbs up/down)
    DELETE /api/v1/rip-ratings/{product_code}       remove rating

  Decision Intelligence:
    GET    /api/v1/decisions/missed-opportunities   deals you're not capturing
    GET    /api/v1/decisions/order-scorecard?order_id=X  grade a draft order
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import and_, asc, desc, func, or_, select
from sqlalchemy.orm import Session

from lpb_core.db import get_session
from lpb_core.db.models import (
    BookEdition,
    Brand,
    Category,
    Distributor,
    InventoryReduction,
    PartialsPricing,
    Product,
    ProductEdition,
    RipOffer,
    RipRating,
    Watchlist,
    WatchlistItem,
)

from .auth import get_current_user
from .catalog import _current_edition, _current_edition_ids

router = APIRouter(tags=["decisions"])


# -- Schemas ------------------------------------------------------------------

class RipRatingIn(BaseModel):
    product_code: str
    distributor: str = "nj-allied"
    rating: int  # 1 (thumbs up) or -1 (thumbs down)
    comment: str | None = None


class RipRatingOut(BaseModel):
    product_code: str
    my_rating: int | None = None  # 1, -1, or None
    my_comment: str | None = None
    thumbs_up: int = 0
    thumbs_down: int = 0
    score: float = 0.0  # net rating as %


class MissedOpportunityRow(BaseModel):
    code: str
    description: str | None = None
    size: str | None = None
    brand: str | None = None
    category: str | None = None
    case_cost: str | None = None
    opportunity_type: str  # rip_not_tracked, closeout_deal, partial_ending, high_rip_pct
    rip_save: str | None = None
    effective_cost: str | None = None
    rip_discount_pct: float | None = None
    closeout_pct_off: float | None = None
    days_remaining: int | None = None
    reason: str
    priority: int = 0  # lower = higher priority
    distributor_slug: str | None = None


class MissedOpportunitiesResponse(BaseModel):
    total: int
    rows: list[MissedOpportunityRow]
    summary: dict


class ScorecardMetric(BaseModel):
    label: str
    value: str
    max_value: str | None = None
    score: float  # 0-100
    color: str  # green, yellow, red


class OrderScorecardResponse(BaseModel):
    overall_grade: str  # A, B, C, D, F
    overall_score: float  # 0-100
    metrics: list[ScorecardMetric]
    recommendations: list[str]
    summary: dict


# -- Helpers ------------------------------------------------------------------

def _money(v) -> str | None:
    if v is None:
        return None
    return str(round(float(v), 2))


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


def _edition_label(ed: BookEdition) -> str:
    return f"{ed.year:04d}-{ed.month:02d}"


def _not_future_filter():
    today = date.today()
    return or_(
        BookEdition.year < today.year,
        and_(BookEdition.year == today.year,
             BookEdition.month <= today.month),
    )


# ============================================================================
# RIP RATINGS
# ============================================================================

@router.get("/api/v1/rip-ratings", response_model=RipRatingOut)
def get_rip_rating(
    product_code: str = Query(...),
    distributor: str = Query("nj-allied"),
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    product = _resolve_product(session, distributor, product_code)
    edition = _current_edition(session, distributor)
    label = _edition_label(edition)

    # User's own rating
    my = session.execute(
        select(RipRating).where(
            RipRating.user_id == user["user_id"],
            RipRating.product_id == product.id,
            RipRating.edition_label == label,
        )
    ).scalar_one_or_none()

    # Aggregates across all users
    agg = session.execute(
        select(
            func.count().filter(RipRating.rating == 1).label("up"),
            func.count().filter(RipRating.rating == -1).label("down"),
        )
        .where(
            RipRating.product_id == product.id,
            RipRating.edition_label == label,
        )
    ).first()

    up = agg.up if agg else 0
    down = agg.down if agg else 0
    total = up + down
    score = round(up / total * 100, 1) if total > 0 else 0.0

    return RipRatingOut(
        product_code=product_code,
        my_rating=my.rating if my else None,
        my_comment=my.comment if my else None,
        thumbs_up=up,
        thumbs_down=down,
        score=score,
    )


@router.get("/api/v1/rip-ratings/bulk", response_model=dict[str, RipRatingOut])
def get_rip_ratings_bulk(
    codes: str = Query(..., description="Comma-separated product codes"),
    distributor: str = Query("nj-allied"),
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Bulk fetch ratings for multiple products (used by list pages)."""
    code_list = [c.strip() for c in codes.split(",") if c.strip()][:200]
    if not code_list:
        return {}

    edition = _current_edition(session, distributor)
    label = _edition_label(edition)

    # Get product IDs
    products = session.execute(
        select(Product.id, Product.code)
        .join(Distributor, Distributor.id == Product.distributor_id)
        .where(Distributor.slug == distributor, Product.code.in_(code_list))
    ).all()
    pid_map = {p.id: p.code for p in products}
    code_pid = {p.code: p.id for p in products}

    if not pid_map:
        return {}

    # User's ratings
    my_ratings = session.execute(
        select(RipRating)
        .where(
            RipRating.user_id == user["user_id"],
            RipRating.product_id.in_(pid_map.keys()),
            RipRating.edition_label == label,
        )
    ).scalars().all()
    my_map = {r.product_id: r for r in my_ratings}

    # Aggregates
    agg_rows = session.execute(
        select(
            RipRating.product_id,
            func.count().filter(RipRating.rating == 1).label("up"),
            func.count().filter(RipRating.rating == -1).label("down"),
        )
        .where(
            RipRating.product_id.in_(pid_map.keys()),
            RipRating.edition_label == label,
        )
        .group_by(RipRating.product_id)
    ).all()
    agg_map = {r.product_id: (r.up, r.down) for r in agg_rows}

    result = {}
    for code in code_list:
        pid = code_pid.get(code)
        if not pid:
            continue
        my = my_map.get(pid)
        up, down = agg_map.get(pid, (0, 0))
        total = up + down
        result[code] = RipRatingOut(
            product_code=code,
            my_rating=my.rating if my else None,
            my_comment=my.comment if my else None,
            thumbs_up=up,
            thumbs_down=down,
            score=round(up / total * 100, 1) if total > 0 else 0.0,
        )
    return result


@router.post("/api/v1/rip-ratings", response_model=RipRatingOut,
             status_code=status.HTTP_201_CREATED)
def rate_rip(
    body: RipRatingIn,
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if body.rating not in (1, -1):
        raise HTTPException(400, "rating must be 1 (thumbs up) or -1 (thumbs down)")

    product = _resolve_product(session, body.distributor, body.product_code)
    edition = _current_edition(session, body.distributor)
    label = _edition_label(edition)

    # Check product actually has a RIP this edition
    has_rip = session.execute(
        select(RipOffer.id)
        .join(ProductEdition, ProductEdition.id == RipOffer.product_edition_id)
        .where(
            ProductEdition.book_edition_id == edition.id,
            ProductEdition.product_id == product.id,
        )
        .limit(1)
    ).scalar_one_or_none()
    if has_rip is None:
        raise HTTPException(400, "This product has no RIP offer this edition")

    # Upsert
    existing = session.execute(
        select(RipRating).where(
            RipRating.user_id == user["user_id"],
            RipRating.product_id == product.id,
            RipRating.edition_label == label,
        )
    ).scalar_one_or_none()

    if existing:
        existing.rating = body.rating
        existing.comment = body.comment
    else:
        session.add(RipRating(
            tenant_id=user["tenant_id"],
            user_id=user["user_id"],
            product_id=product.id,
            edition_label=label,
            rating=body.rating,
            comment=body.comment,
        ))
    session.commit()

    return get_rip_rating(
        product_code=body.product_code,
        distributor=body.distributor,
        user=user,
        session=session,
    )


@router.delete("/api/v1/rip-ratings/{product_code}",
               status_code=status.HTTP_204_NO_CONTENT)
def delete_rip_rating(
    product_code: str,
    distributor: str = Query("nj-allied"),
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    product = _resolve_product(session, distributor, product_code)
    edition = _current_edition(session, distributor)
    label = _edition_label(edition)

    existing = session.execute(
        select(RipRating).where(
            RipRating.user_id == user["user_id"],
            RipRating.product_id == product.id,
            RipRating.edition_label == label,
        )
    ).scalar_one_or_none()
    if existing:
        session.delete(existing)
        session.commit()


# ============================================================================
# MISSED OPPORTUNITIES
# ============================================================================

@router.get("/api/v1/decisions/missed-opportunities",
            response_model=MissedOpportunitiesResponse)
def missed_opportunities(
    distributor: str = Query("nj-allied"),
    limit: int = Query(100, ge=1, le=500),
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Surface deals the user isn't taking advantage of.

    Finds: high-value RIPs not on watchlist, active closeouts,
    expiring partials, and top discount-% RIPs they're ignoring.
    """
    today = date.today()
    try:
        edition = _current_edition(session, distributor)
    except HTTPException:
        return MissedOpportunitiesResponse(
            total=0, rows=[],
            summary={"by_type": {}, "total_rip_savings_missed": "0",
                     "closeout_count": 0, "expiring_partials": 0},
        )

    # Get tracked product IDs
    default_wl = session.execute(
        select(Watchlist).where(
            Watchlist.tenant_id == user["tenant_id"],
            Watchlist.is_default == True,  # noqa: E712
        )
    ).scalar_one_or_none()
    tracked_pids: set[UUID] = set()
    if default_wl:
        tracked_pids = set(session.execute(
            select(WatchlistItem.product_id)
            .where(WatchlistItem.watchlist_id == default_wl.id)
        ).scalars().all())

    dslug = distributor
    dist_row = session.execute(
        select(Distributor.slug, Distributor.name)
        .where(Distributor.id == edition.distributor_id)
    ).first()
    if dist_row:
        dslug = dist_row.slug

    results: list[MissedOpportunityRow] = []

    # 1. High-value RIPs not tracked
    rip_rows = session.execute(
        select(
            Product.code,
            Product.id.label("pid"),
            ProductEdition.description,
            ProductEdition.size,
            ProductEdition.case_cost,
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
            ProductEdition.book_edition_id == edition.id,
            ProductEdition.case_cost.is_not(None),
        )
        .group_by(
            Product.code, Product.id, ProductEdition.description,
            ProductEdition.size, ProductEdition.case_cost,
            Category.display_name, Brand.display_name,
        )
        .order_by(desc(func.max(RipOffer.save_amount)))
        .limit(300)
    ).all()

    for r in rip_rows:
        if r.pid in tracked_pids:
            continue
        if not r.case_cost or not r.best_save:
            continue
        pct = round(float(r.best_save) / float(r.case_cost) * 100, 1)
        if pct < 5:  # Skip trivial discounts
            continue
        eff = max(0, float(r.case_cost) - float(r.best_save))
        results.append(MissedOpportunityRow(
            code=r.code, description=r.description, size=r.size,
            brand=r.brand, category=r.category,
            case_cost=_money(r.case_cost),
            opportunity_type="rip_not_tracked",
            rip_save=_money(r.best_save),
            effective_cost=_money(eff),
            rip_discount_pct=pct,
            reason=f"RIP saves ${float(r.best_save):.2f}/case ({pct}%) — not on your list",
            priority=1,
            distributor_slug=dslug,
        ))

    # 2. Closeout deals not tracked
    co_rows = session.execute(
        select(
            Product.code,
            Product.id.label("pid"),
            ProductEdition.description,
            ProductEdition.size,
            Category.display_name.label("category"),
            Brand.display_name.label("brand"),
            InventoryReduction.best_case,
            InventoryReduction.original_case,
        )
        .select_from(InventoryReduction)
        .join(Product, Product.id == InventoryReduction.product_id)
        .outerjoin(ProductEdition, and_(
            ProductEdition.product_id == Product.id,
            ProductEdition.book_edition_id == edition.id,
        ))
        .outerjoin(Category, Category.id == ProductEdition.category_id)
        .outerjoin(Brand, Brand.id == ProductEdition.brand_id)
        .where(InventoryReduction.book_edition_id == edition.id)
        .order_by(desc(InventoryReduction.original_case - InventoryReduction.best_case))
        .limit(100)
    ).all()

    for r in co_rows:
        if r.pid in tracked_pids:
            continue
        pct_off = None
        if r.original_case and r.best_case:
            pct_off = round((1 - float(r.best_case) / float(r.original_case)) * 100, 1)
        results.append(MissedOpportunityRow(
            code=r.code, description=r.description, size=r.size,
            brand=r.brand, category=r.category,
            case_cost=_money(r.best_case),
            opportunity_type="closeout_deal",
            closeout_pct_off=pct_off,
            reason=(f"Closeout: {pct_off}% off — being discontinued"
                    if pct_off else "Closeout — being discontinued"),
            priority=0,  # Highest priority — time-sensitive
            distributor_slug=dslug,
        ))

    # 3. Partials ending soon (within 14 days)
    partials = session.execute(
        select(
            PartialsPricing.description,
            PartialsPricing.best_case_price,
            PartialsPricing.end_date,
            PartialsPricing.linked_product_id,
            Product.code,
        )
        .outerjoin(Product, Product.id == PartialsPricing.linked_product_id)
        .where(
            PartialsPricing.book_edition_id == edition.id,
            PartialsPricing.start_date <= today,
            PartialsPricing.end_date >= today,
            PartialsPricing.end_date <= func.current_date() + 14,
        )
        .order_by(asc(PartialsPricing.end_date))
        .limit(50)
    ).all()

    for p in partials:
        if p.linked_product_id and p.linked_product_id in tracked_pids:
            continue
        days_left = (p.end_date - today).days
        results.append(MissedOpportunityRow(
            code=p.code or "—",
            description=p.description,
            case_cost=_money(p.best_case_price),
            opportunity_type="partial_ending",
            days_remaining=days_left,
            reason=f"Special pricing ends in {days_left} day{'s' if days_left != 1 else ''}",
            priority=2,
            distributor_slug=dslug,
        ))

    # Sort by priority then discount
    results.sort(key=lambda r: (
        r.priority,
        -(r.rip_discount_pct or 0),
        -(r.closeout_pct_off or 0),
    ))
    results = results[:limit]

    # Summary counts
    type_counts = {}
    for r in results:
        type_counts[r.opportunity_type] = type_counts.get(r.opportunity_type, 0) + 1

    total_rip_missed = sum(
        float(r.rip_save or 0)
        for r in results if r.opportunity_type == "rip_not_tracked"
    )

    return MissedOpportunitiesResponse(
        total=len(results),
        rows=results,
        summary={
            "by_type": type_counts,
            "total_rip_savings_missed": _money(total_rip_missed),
            "closeout_count": type_counts.get("closeout_deal", 0),
            "expiring_partials": type_counts.get("partial_ending", 0),
        },
    )


# ============================================================================
# ORDER SCORECARD
# ============================================================================

@router.get("/api/v1/decisions/order-scorecard",
            response_model=OrderScorecardResponse)
def order_scorecard(
    distributor: str = Query("nj-allied"),
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Grade the user's tracked products as an order — how optimized is it?

    Scores: RIP capture rate, tier optimization, closeout awareness,
    category diversification, price-timing quality.
    """
    try:
        edition = _current_edition(session, distributor)
        edition_ids = _current_edition_ids(session, "all")
    except HTTPException:
        return OrderScorecardResponse(
            overall_grade="—", overall_score=0, metrics=[],
            recommendations=["No price book data available for this distributor yet."],
            summary={},
        )

    # Get tracked items
    default_wl = session.execute(
        select(Watchlist).where(
            Watchlist.tenant_id == user["tenant_id"],
            Watchlist.is_default == True,  # noqa: E712
        )
    ).scalar_one_or_none()

    if default_wl is None:
        return OrderScorecardResponse(
            overall_grade="—",
            overall_score=0,
            metrics=[],
            recommendations=["Start by adding products to your Order List."],
            summary={},
        )

    # Tracked products with current pricing
    tracked = session.execute(
        select(
            Product.code,
            Product.id.label("pid"),
            ProductEdition.case_cost,
            ProductEdition.btl_cost,
            Category.display_name.label("category"),
        )
        .select_from(WatchlistItem)
        .join(Watchlist, Watchlist.id == WatchlistItem.watchlist_id)
        .join(Product, Product.id == WatchlistItem.product_id)
        .outerjoin(ProductEdition, and_(
            ProductEdition.product_id == Product.id,
            ProductEdition.book_edition_id.in_(edition_ids),
        ))
        .outerjoin(Category, Category.id == ProductEdition.category_id)
        .where(Watchlist.id == default_wl.id)
    ).all()

    total_items = len(tracked)
    if total_items == 0:
        return OrderScorecardResponse(
            overall_grade="—",
            overall_score=0,
            metrics=[],
            recommendations=["Your Order List is empty. Add products to get a scorecard."],
            summary={},
        )

    tracked_pids = {r.pid for r in tracked if r.pid}
    total_cost = sum(float(r.case_cost or 0) for r in tracked)

    # --- Metric 1: RIP Capture Rate ---
    # How many of your tracked items have RIPs?
    total_rips_available = session.execute(
        select(func.count(func.distinct(ProductEdition.product_id)))
        .select_from(RipOffer)
        .join(ProductEdition, ProductEdition.id == RipOffer.product_edition_id)
        .where(
            ProductEdition.book_edition_id == edition.id,
            ProductEdition.product_id.in_(tracked_pids),
        )
    ).scalar() or 0

    rip_capture_pct = round(total_rips_available / total_items * 100, 1) if total_items else 0

    # --- Metric 2: Total RIP savings potential ---
    rip_savings = session.execute(
        select(func.sum(func.max(RipOffer.save_amount)))
        .select_from(RipOffer)
        .join(ProductEdition, ProductEdition.id == RipOffer.product_edition_id)
        .where(
            ProductEdition.book_edition_id == edition.id,
            ProductEdition.product_id.in_(tracked_pids),
        )
        .group_by(ProductEdition.product_id)
    ).scalars().all()
    total_rip_savings = sum(float(s) for s in rip_savings if s)
    savings_pct = round(total_rip_savings / total_cost * 100, 1) if total_cost > 0 else 0

    # --- Metric 3: Closeout awareness ---
    closeout_count = session.execute(
        select(func.count())
        .select_from(InventoryReduction)
        .where(
            InventoryReduction.book_edition_id == edition.id,
            InventoryReduction.product_id.in_(tracked_pids),
        )
    ).scalar() or 0

    # --- Metric 4: Category diversification ---
    categories = set(r.category for r in tracked if r.category)
    all_categories = session.execute(
        select(func.count(func.distinct(Category.id)))
        .select_from(ProductEdition)
        .join(Category, Category.id == ProductEdition.category_id)
        .where(ProductEdition.book_edition_id == edition.id)
    ).scalar() or 1
    diversity_pct = round(len(categories) / min(all_categories, 10) * 100, 1)
    diversity_pct = min(diversity_pct, 100)

    # --- Metric 5: Price timing ---
    # What % of tracked items are at/near 12-month low?
    hist_rows = session.execute(
        select(
            Product.code,
            ProductEdition.case_cost,
            BookEdition.year,
            BookEdition.month,
        )
        .select_from(ProductEdition)
        .join(Product, Product.id == ProductEdition.product_id)
        .join(BookEdition, BookEdition.id == ProductEdition.book_edition_id)
        .where(Product.id.in_(tracked_pids))
        .order_by(Product.code, asc(BookEdition.year), asc(BookEdition.month))
    ).all()

    from collections import defaultdict
    price_hist: dict[str, list[Decimal]] = defaultdict(list)
    for hr in hist_rows:
        if hr.case_cost is not None:
            price_hist[hr.code].append(hr.case_cost)

    at_low = 0
    at_high = 0
    for r in tracked:
        prices = price_hist.get(r.code, [])
        if len(prices) < 2 or r.case_cost is None:
            continue
        recent = prices[-12:]
        if r.case_cost <= min(recent):
            at_low += 1
        elif r.case_cost >= max(recent):
            at_high += 1

    timing_score = 0
    if total_items > 0:
        # Good timing = more items at low, fewer at high
        timing_score = min(100, round(
            (at_low / total_items * 80) + ((total_items - at_high) / total_items * 20)
        ) * 100 / 100)

    # --- Assemble metrics ---
    metrics = [
        ScorecardMetric(
            label="RIP Capture",
            value=f"{total_rips_available}/{total_items}",
            max_value=f"{total_items}",
            score=min(rip_capture_pct * 2, 100),  # 50% capture = perfect
            color=("green" if rip_capture_pct >= 30
                   else "yellow" if rip_capture_pct >= 15 else "red"),
        ),
        ScorecardMetric(
            label="RIP Savings",
            value=f"${total_rip_savings:.0f}",
            max_value=f"{savings_pct}% of order",
            score=min(savings_pct * 5, 100),  # 20% savings = perfect
            color="green" if savings_pct >= 10 else "yellow" if savings_pct >= 5 else "red",
        ),
        ScorecardMetric(
            label="Closeout Items",
            value=str(closeout_count),
            max_value=None,
            score=100 if closeout_count == 0 else max(0, 100 - closeout_count * 20),
            color="green" if closeout_count == 0 else "yellow" if closeout_count <= 2 else "red",
        ),
        ScorecardMetric(
            label="Category Mix",
            value=f"{len(categories)} categories",
            max_value=None,
            score=diversity_pct,
            color="green" if diversity_pct >= 50 else "yellow" if diversity_pct >= 25 else "red",
        ),
        ScorecardMetric(
            label="Price Timing",
            value=f"{at_low} at low / {at_high} at high",
            max_value=None,
            score=timing_score,
            color="green" if timing_score >= 60 else "yellow" if timing_score >= 30 else "red",
        ),
    ]

    overall = round(sum(m.score for m in metrics) / len(metrics), 1)
    grade = (
        "A" if overall >= 80 else
        "B" if overall >= 60 else
        "C" if overall >= 40 else
        "D" if overall >= 20 else "F"
    )

    # Recommendations
    recs = []
    if rip_capture_pct < 30:
        recs.append(f"Only {rip_capture_pct}% of your items have RIPs. "
                    f"Check the RIPs page for deals you may be missing.")
    if closeout_count > 0:
        recs.append(f"You have {closeout_count} closeout item(s) — these are "
                    "being discontinued. Buy now or remove from list.")
    if at_high > total_items * 0.3:
        recs.append(f"{at_high} items are at their 12-month high price. "
                    "Consider deferring or finding alternatives.")
    if at_low > 0:
        recs.append(f"{at_low} item(s) at 12-month low — good timing to buy.")
    if len(categories) < 3 and total_items > 5:
        recs.append("Your order is concentrated in few categories. "
                    "Consider diversifying for better shelf coverage.")
    if savings_pct >= 10:
        recs.append(f"Strong RIP savings potential at {savings_pct}% of order value.")
    if not recs:
        recs.append("Your order looks well-optimized. Review individual items for fine-tuning.")

    return OrderScorecardResponse(
        overall_grade=grade,
        overall_score=overall,
        metrics=metrics,
        recommendations=recs,
        summary={
            "total_items": total_items,
            "total_cost": _money(total_cost),
            "total_rip_savings": _money(total_rip_savings),
            "rip_capture_pct": rip_capture_pct,
            "closeout_count": closeout_count,
            "categories": len(categories),
            "at_12m_low": at_low,
            "at_12m_high": at_high,
        },
    )
