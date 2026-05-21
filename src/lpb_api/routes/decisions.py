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
from sqlalchemy import and_, asc, desc, func, or_, select, text
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


# ============================================================================
# BUY SHEET — Comprehensive Decision Support
# ============================================================================

class BuySheetItem(BaseModel):
    code: str
    description: str | None = None
    size: str | None = None
    pack: int | None = None
    brand: str | None = None
    category: str | None = None
    case_cost: str | None = None
    btl_cost: str | None = None
    divisions: str | None = None
    distributor_slug: str | None = None

    # Price intelligence
    prev_case_cost: str | None = None
    case_cost_pct: float | None = None
    price_trend: str | None = None
    at_12m_low: bool = False
    at_12m_high: bool = False
    months_of_history: int = 0
    avg_case_cost: str | None = None
    min_case_cost: str | None = None
    max_case_cost: str | None = None

    # RIP info
    has_rip: bool = False
    best_rip_save: str | None = None
    best_rip_tier: str | None = None
    best_rip_effective: str | None = None
    rip_discount_pct: float | None = None
    rip_stable: bool | None = None
    rip_tiers: list[dict] | None = None

    # Closeout info
    is_closeout: bool = False
    closeout_pct_off: float | None = None
    closeout_original_case: str | None = None

    # Specials (partials)
    has_active_special: bool = False
    special_end_date: str | None = None
    special_days_remaining: int | None = None
    special_description: str | None = None

    # Decision
    verdict: str
    verdict_reasons: list[str]
    urgency: int = 0
    section: str

    # Tracking
    is_tracked: bool = False


class BuySheetSection(BaseModel):
    key: str
    title: str
    subtitle: str
    count: int
    icon: str
    items: list[BuySheetItem]


class BuySheetSummary(BaseModel):
    total_items: int
    total_buy_now: int
    total_consider: int
    total_defer: int
    total_last_chance: int
    total_closeouts: int
    total_new_rips: int
    total_lost_rips: int
    potential_rip_savings: str
    market_direction: str
    avg_market_change_pct: float
    edition_label: str


class BuySheetResponse(BaseModel):
    sections: list[BuySheetSection]
    summary: BuySheetSummary


def _previous_edition(
    session: Session, distributor_id: UUID, current_year: int, current_month: int,
) -> BookEdition | None:
    """Find the edition immediately before the current one for the same distributor."""
    return session.execute(
        select(BookEdition)
        .where(
            BookEdition.distributor_id == distributor_id,
            BookEdition.is_active == True,  # noqa: E712
            or_(
                BookEdition.year < current_year,
                and_(BookEdition.year == current_year,
                     BookEdition.month < current_month),
            ),
        )
        .order_by(desc(BookEdition.year), desc(BookEdition.month))
        .limit(1)
    ).scalar_one_or_none()


def _compute_price_trend(prices: list[float]) -> str:
    """Determine price trend from a chronological list of prices."""
    if len(prices) < 2:
        return "new"
    recent = prices[-3:] if len(prices) >= 3 else prices
    increases = sum(1 for i in range(1, len(recent)) if recent[i] > recent[i - 1])
    decreases = sum(1 for i in range(1, len(recent)) if recent[i] < recent[i - 1])
    if increases > decreases:
        return "rising"
    if decreases > increases:
        return "falling"
    return "stable"


@router.get("/api/v1/decisions/buy-sheet", response_model=BuySheetResponse)
def buy_sheet(
    distributor: str = Query("nj-allied"),
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Comprehensive decision support: what to buy, how much, why, buy vs defer."""
    from collections import defaultdict

    today = date.today()

    try:
        edition = _current_edition(session, distributor)
    except HTTPException:
        empty_summary = BuySheetSummary(
            total_items=0, total_buy_now=0, total_consider=0, total_defer=0,
            total_last_chance=0, total_closeouts=0, total_new_rips=0,
            total_lost_rips=0, potential_rip_savings="0",
            market_direction="stable", avg_market_change_pct=0.0,
            edition_label="—",
        )
        return BuySheetResponse(sections=[], summary=empty_summary)

    dslug = distributor
    dist_row = session.execute(
        select(Distributor.slug).where(Distributor.id == edition.distributor_id)
    ).scalar_one_or_none()
    if dist_row:
        dslug = dist_row

    prev_edition = _previous_edition(
        session, edition.distributor_id, edition.year, edition.month,
    )

    # -- User's tracked product IDs ------------------------------------------
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

    # -- 1. All current products with pricing --------------------------------
    pe_rows = session.execute(
        select(
            Product.id.label("pid"),
            Product.code,
            ProductEdition.description,
            ProductEdition.size,
            ProductEdition.pack,
            ProductEdition.case_cost,
            ProductEdition.btl_cost,
            ProductEdition.divisions,
            Category.display_name.label("category"),
            Brand.display_name.label("brand"),
        )
        .select_from(ProductEdition)
        .join(Product, Product.id == ProductEdition.product_id)
        .outerjoin(Category, Category.id == ProductEdition.category_id)
        .outerjoin(Brand, Brand.id == ProductEdition.brand_id)
        .where(
            ProductEdition.book_edition_id == edition.id,
            ProductEdition.case_cost.is_not(None),
        )
    ).all()

    # Build a master dict keyed by product_id
    product_map: dict[UUID, dict] = {}
    for r in pe_rows:
        product_map[r.pid] = {
            "pid": r.pid,
            "code": r.code,
            "description": r.description,
            "size": r.size,
            "pack": r.pack,
            "case_cost": float(r.case_cost) if r.case_cost else None,
            "btl_cost": float(r.btl_cost) if r.btl_cost else None,
            "divisions": r.divisions,
            "category": r.category,
            "brand": r.brand,
        }

    all_pids = set(product_map.keys())
    if not all_pids:
        empty_summary = BuySheetSummary(
            total_items=0, total_buy_now=0, total_consider=0, total_defer=0,
            total_last_chance=0, total_closeouts=0, total_new_rips=0,
            total_lost_rips=0, potential_rip_savings="0",
            market_direction="stable", avg_market_change_pct=0.0,
            edition_label=_edition_label(edition),
        )
        return BuySheetResponse(sections=[], summary=empty_summary)

    # -- 2. Current RIP offers -----------------------------------------------
    rip_rows = session.execute(
        select(
            ProductEdition.product_id,
            RipOffer.tier,
            RipOffer.tier_cases,
            RipOffer.save_amount,
            RipOffer.case_price,
        )
        .select_from(RipOffer)
        .join(ProductEdition, ProductEdition.id == RipOffer.product_edition_id)
        .where(ProductEdition.book_edition_id == edition.id)
        .order_by(ProductEdition.product_id, desc(RipOffer.save_amount))
    ).all()

    curr_rip_map: dict[UUID, list[dict]] = defaultdict(list)
    for r in rip_rows:
        curr_rip_map[r.product_id].append({
            "tier": r.tier,
            "tier_cases": r.tier_cases,
            "save_amount": float(r.save_amount),
            "case_price": float(r.case_price) if r.case_price else None,
        })
    curr_rip_pids = set(curr_rip_map.keys())

    # -- 3. Previous edition RIP products (for lost/new detection) -----------
    prev_rip_pids: set[UUID] = set()
    prev_rip_save_map: dict[UUID, float] = {}
    if prev_edition:
        prev_rip_rows = session.execute(
            select(
                ProductEdition.product_id,
                func.max(RipOffer.save_amount).label("best_save"),
            )
            .select_from(RipOffer)
            .join(ProductEdition, ProductEdition.id == RipOffer.product_edition_id)
            .where(ProductEdition.book_edition_id == prev_edition.id)
            .group_by(ProductEdition.product_id)
        ).all()
        for r in prev_rip_rows:
            prev_rip_pids.add(r.product_id)
            prev_rip_save_map[r.product_id] = float(r.best_save)

    lost_rip_pids = prev_rip_pids - curr_rip_pids
    new_rip_pids = curr_rip_pids - prev_rip_pids

    # -- 4. Price changes from mv_price_changes ------------------------------
    price_change_map: dict[UUID, dict] = {}
    try:
        pc_rows = session.execute(text(
            "SELECT product_id, prev_case_cost, case_cost_pct "
            "FROM mv_price_changes WHERE book_edition_id = :eid"
        ), {"eid": str(edition.id)}).fetchall()
        for r in pc_rows:
            price_change_map[r.product_id] = {
                "prev_case_cost": float(r.prev_case_cost) if r.prev_case_cost is not None else None,
                "case_cost_pct": float(r.case_cost_pct) if r.case_cost_pct is not None else None,
            }
    except Exception:
        # mv_price_changes may not exist; fall through gracefully
        session.rollback()

    # -- 5. 12-month price history for highs/lows/trends ---------------------
    hist_rows = session.execute(
        select(
            ProductEdition.product_id,
            ProductEdition.case_cost,
            BookEdition.year,
            BookEdition.month,
        )
        .join(BookEdition, BookEdition.id == ProductEdition.book_edition_id)
        .where(
            ProductEdition.product_id.in_(all_pids),
            ProductEdition.case_cost.is_not(None),
            _not_future_filter(),
        )
        .order_by(ProductEdition.product_id, asc(BookEdition.year), asc(BookEdition.month))
    ).all()

    price_history: dict[UUID, list[float]] = defaultdict(list)
    for hr in hist_rows:
        price_history[hr.product_id].append(float(hr.case_cost))

    # -- 6. Closeout items ---------------------------------------------------
    co_rows = session.execute(
        select(
            InventoryReduction.product_id,
            InventoryReduction.original_case,
            InventoryReduction.best_case,
            InventoryReduction.description.label("co_desc"),
        )
        .where(InventoryReduction.book_edition_id == edition.id)
    ).all()

    closeout_map: dict[UUID, dict] = {}
    for r in co_rows:
        pct_off = None
        if r.original_case and r.best_case and float(r.original_case) > 0:
            pct_off = round((1 - float(r.best_case) / float(r.original_case)) * 100, 1)
        closeout_map[r.product_id] = {
            "pct_off": pct_off,
            "original_case": float(r.original_case) if r.original_case else None,
            "best_case": float(r.best_case) if r.best_case else None,
            "co_desc": r.co_desc,
        }

    # Previous edition closeouts (for detecting new closeouts)
    prev_closeout_pids: set[UUID] = set()
    if prev_edition:
        prev_closeout_pids = set(session.execute(
            select(InventoryReduction.product_id)
            .where(InventoryReduction.book_edition_id == prev_edition.id)
        ).scalars().all())

    closeout_pids = set(closeout_map.keys())
    new_closeout_pids = closeout_pids - prev_closeout_pids

    # -- 7. Active partials (web specials) -----------------------------------
    partial_rows = session.execute(
        select(
            PartialsPricing.linked_product_id,
            PartialsPricing.description,
            PartialsPricing.end_date,
            PartialsPricing.best_case_price,
        )
        .where(
            PartialsPricing.book_edition_id == edition.id,
            PartialsPricing.start_date <= today,
            PartialsPricing.end_date >= today,
            PartialsPricing.linked_product_id.is_not(None),
        )
        .order_by(asc(PartialsPricing.end_date))
    ).all()

    special_map: dict[UUID, dict] = {}
    for p in partial_rows:
        if p.linked_product_id and p.linked_product_id not in special_map:
            days_left = (p.end_date - today).days
            special_map[p.linked_product_id] = {
                "end_date": str(p.end_date),
                "days_remaining": days_left,
                "description": p.description,
                "best_case_price": float(p.best_case_price) if p.best_case_price else None,
            }

    # -- Build enriched product data -----------------------------------------
    def _build_item(pid: UUID, section: str, verdict: str,
                    reasons: list[str], urgency: int) -> BuySheetItem | None:
        pm = product_map.get(pid)
        if pm is None:
            return None

        cc = pm["case_cost"]
        prices = price_history.get(pid, [])
        recent_12 = prices[-12:] if prices else []

        # Price intelligence
        pc = price_change_map.get(pid, {})
        prev_cc = pc.get("prev_case_cost")
        cc_pct = pc.get("case_cost_pct")
        trend = _compute_price_trend(prices)
        is_at_low = cc is not None and len(recent_12) >= 2 and cc <= min(recent_12)
        is_at_high = cc is not None and len(recent_12) >= 2 and cc >= max(recent_12)
        avg_cc = round(sum(recent_12) / len(recent_12), 2) if recent_12 else None
        min_cc = min(recent_12) if recent_12 else None
        max_cc = max(recent_12) if recent_12 else None

        # RIP info
        rip_tiers_raw = curr_rip_map.get(pid, [])
        has_rip = len(rip_tiers_raw) > 0
        best_rip = rip_tiers_raw[0] if rip_tiers_raw else None
        best_save = best_rip["save_amount"] if best_rip else None
        best_tier = best_rip["tier"] if best_rip else None
        best_eff = round(cc - best_save, 2) if cc and best_save else None
        rip_disc_pct = round(best_save / cc * 100, 1) if cc and best_save and cc > 0 else None

        # RIP stability: same save_amount as previous edition?
        rip_stable = None
        if has_rip and pid in prev_rip_save_map:
            rip_stable = abs(prev_rip_save_map[pid] - best_save) < 0.01

        rip_tiers_out = [
            {"tier": t["tier"], "save_amount": _money(t["save_amount"]),
             "case_price": _money(t["case_price"])}
            for t in rip_tiers_raw
        ] if rip_tiers_raw else None

        # Closeout
        co = closeout_map.get(pid)
        is_closeout = co is not None
        co_pct_off = co["pct_off"] if co else None
        co_orig = co["original_case"] if co else None

        # Specials
        sp = special_map.get(pid)
        has_special = sp is not None

        return BuySheetItem(
            code=pm["code"],
            description=pm["description"],
            size=pm["size"],
            pack=pm["pack"],
            brand=pm["brand"],
            category=pm["category"],
            case_cost=_money(cc),
            btl_cost=_money(pm["btl_cost"]),
            divisions=pm["divisions"],
            distributor_slug=dslug,
            prev_case_cost=_money(prev_cc),
            case_cost_pct=round(cc_pct, 2) if cc_pct is not None else None,
            price_trend=trend,
            at_12m_low=is_at_low,
            at_12m_high=is_at_high,
            months_of_history=len(recent_12),
            avg_case_cost=_money(avg_cc),
            min_case_cost=_money(min_cc),
            max_case_cost=_money(max_cc),
            has_rip=has_rip,
            best_rip_save=_money(best_save),
            best_rip_tier=best_tier,
            best_rip_effective=_money(best_eff),
            rip_discount_pct=rip_disc_pct,
            rip_stable=rip_stable,
            rip_tiers=rip_tiers_out,
            is_closeout=is_closeout,
            closeout_pct_off=co_pct_off,
            closeout_original_case=_money(co_orig),
            has_active_special=has_special,
            special_end_date=sp["end_date"] if sp else None,
            special_days_remaining=sp["days_remaining"] if sp else None,
            special_description=sp["description"] if sp else None,
            verdict=verdict,
            verdict_reasons=reasons,
            urgency=urgency,
            section=section,
            is_tracked=pid in tracked_pids,
        )

    # -- Score and categorize every product ----------------------------------
    # Collect items per section; a product CAN appear in multiple sections
    section_items: dict[str, dict[UUID, BuySheetItem]] = {
        "last_chance": {},
        "strong_buy": {},
        "buy_now": {},
        "consider": {},
        "defer": {},
        "new_opportunities": {},
    }

    for pid, pm in product_map.items():
        cc = pm["case_cost"]
        if cc is None or cc <= 0:
            continue

        pc = price_change_map.get(pid, {})
        cc_pct = pc.get("case_cost_pct")
        prices = price_history.get(pid, [])
        recent_12 = prices[-12:] if prices else []
        is_at_low = cc is not None and len(recent_12) >= 2 and cc <= min(recent_12)
        is_at_high = cc is not None and len(recent_12) >= 2 and cc >= max(recent_12)
        near_low = (cc is not None and len(recent_12) >= 2
                    and min(recent_12) > 0
                    and (cc - min(recent_12)) / min(recent_12) <= 0.03)
        trend = _compute_price_trend(prices)

        rip_tiers = curr_rip_map.get(pid, [])
        has_rip = len(rip_tiers) > 0
        best_save = rip_tiers[0]["save_amount"] if rip_tiers else 0
        rip_disc = round(best_save / cc * 100, 1) if cc and best_save and cc > 0 else 0

        is_closeout = pid in closeout_map
        co = closeout_map.get(pid)
        co_pct = co["pct_off"] if co else None

        sp = special_map.get(pid)
        sp_days = sp["days_remaining"] if sp else None

        is_lost_rip = pid in lost_rip_pids
        is_new_rip = pid in new_rip_pids
        is_new_closeout = pid in new_closeout_pids
        price_dropped = cc_pct is not None and cc_pct < 0
        price_drop_pct = abs(cc_pct) if cc_pct and cc_pct < 0 else 0
        price_rise_pct = cc_pct if cc_pct and cc_pct > 0 else 0

        # ---- Section 1: LAST CHANCE ----------------------------------------
        last_reasons: list[str] = []
        last_urgency = 0

        if is_lost_rip and pid in product_map:
            prev_save = prev_rip_save_map.get(pid, 0)
            last_reasons.append(
                f"RIP of ${prev_save:.2f}/case expired — no longer available this month"
            )
            last_urgency = max(last_urgency, 95)

        if is_closeout:
            pct_str = f" ({co_pct}% off)" if co_pct else ""
            last_reasons.append(f"Closeout — being discontinued{pct_str}")
            last_urgency = max(last_urgency, 92)

        if sp and sp_days is not None and sp_days <= 3:
            last_reasons.append(
                f"Web special ends in {sp_days} day{'s' if sp_days != 1 else ''}"
            )
            last_urgency = max(last_urgency, 90)

        if last_reasons:
            item = _build_item(pid, "last_chance", "LAST_CHANCE", last_reasons, last_urgency)
            if item:
                section_items["last_chance"][pid] = item

        # ---- Section 2: STRONG BUY ----------------------------------------
        strong_reasons: list[str] = []
        strong_urgency = 0

        if price_dropped and has_rip:
            strong_reasons.append(
                f"Price dropped {price_drop_pct:.1f}% AND has RIP saving ${best_save:.2f}/case"
            )
            strong_urgency = max(strong_urgency, 85)

        if is_at_low and has_rip:
            strong_reasons.append(
                f"At 12-month low price AND has RIP ({rip_disc}% discount)"
            )
            strong_urgency = max(strong_urgency, 82)

        if is_new_rip and rip_disc > 10:
            strong_reasons.append(
                f"NEW RIP this month — {rip_disc}% discount (${best_save:.2f}/case)"
            )
            strong_urgency = max(strong_urgency, 80)

        if is_closeout and co_pct and co_pct > 20:
            strong_reasons.append(
                f"Closeout with {co_pct}% off — exceptional clearance deal"
            )
            strong_urgency = max(strong_urgency, 78)

        if strong_reasons:
            item = _build_item(pid, "strong_buy", "STRONG_BUY", strong_reasons, strong_urgency)
            if item:
                section_items["strong_buy"][pid] = item

        # ---- Section 3: BUY NOW -------------------------------------------
        buy_reasons: list[str] = []
        buy_urgency = 0

        if price_drop_pct > 2:
            buy_reasons.append(f"Price dropped {price_drop_pct:.1f}% this month")
            buy_urgency = max(buy_urgency, 65)

        if has_rip and rip_disc > 5:
            buy_reasons.append(f"RIP discount of {rip_disc}% (${best_save:.2f}/case)")
            buy_urgency = max(buy_urgency, 60)

        if is_at_low or near_low:
            if is_at_low:
                buy_reasons.append("At 12-month low price")
            else:
                buy_reasons.append("Within 3% of 12-month low price")
            buy_urgency = max(buy_urgency, 58)

        if sp and sp_days is not None and sp_days > 3:
            buy_reasons.append(
                f"Active web special — {sp_days} days remaining"
            )
            buy_urgency = max(buy_urgency, 55)

        if buy_reasons and pid not in section_items["strong_buy"]:
            item = _build_item(pid, "buy_now", "BUY_NOW", buy_reasons, buy_urgency)
            if item:
                section_items["buy_now"][pid] = item

        # ---- Section 4: CONSIDER ------------------------------------------
        consider_reasons: list[str] = []
        consider_urgency = 0

        has_small_rip = has_rip and 0 < rip_disc <= 5
        price_stable = cc_pct is not None and abs(cc_pct) <= 2

        if price_stable and has_small_rip:
            consider_reasons.append(
                f"Stable price with small RIP ({rip_disc}% discount)"
            )
            consider_urgency = max(consider_urgency, 35)

        if price_stable and not has_rip and len(recent_12) >= 2:
            avg_price = sum(recent_12) / len(recent_12)
            if avg_price > 0 and abs(cc - avg_price) / avg_price <= 0.05:
                consider_reasons.append("Price near 12-month average — normal pricing")
                consider_urgency = max(consider_urgency, 25)

        if has_rip and not price_dropped and not is_at_low and rip_disc <= 10:
            if not consider_reasons:
                consider_reasons.append(
                    f"Has RIP ({rip_disc}% off) but price not at a compelling level"
                )
                consider_urgency = max(consider_urgency, 30)

        if (consider_reasons
                and pid not in section_items["strong_buy"]
                and pid not in section_items["buy_now"]):
            item = _build_item(pid, "consider", "CONSIDER", consider_reasons, consider_urgency)
            if item:
                section_items["consider"][pid] = item

        # ---- Section 5: DEFER (never defer closeouts) ----------------------
        defer_reasons: list[str] = []
        defer_urgency = 0

        if not is_closeout:
            if price_rise_pct > 3:
                defer_reasons.append(
                    f"Price increased {price_rise_pct:.1f}% this month — wait for correction"
                )
                defer_urgency = max(defer_urgency, 15)

            if is_at_high:
                defer_reasons.append("At 12-month HIGH price — worst time to buy")
                defer_urgency = max(defer_urgency, 10)

            if trend == "rising" and len(prices) >= 3:
                recent_3 = prices[-3:]
                consecutive_up = all(
                    recent_3[i] > recent_3[i - 1] for i in range(1, len(recent_3))
                )
                if consecutive_up:
                    defer_reasons.append(
                        "3+ consecutive price increases — rising trend"
                    )
                    defer_urgency = max(defer_urgency, 12)

        if (defer_reasons
                and pid not in section_items["last_chance"]
                and pid not in section_items["strong_buy"]
                and pid not in section_items["buy_now"]):
            item = _build_item(pid, "defer", "DEFER", defer_reasons, defer_urgency)
            if item:
                section_items["defer"][pid] = item

        # ---- Section 6: NEW OPPORTUNITIES ----------------------------------
        new_reasons: list[str] = []
        new_urgency = 0

        if is_new_rip:
            new_reasons.append(
                f"NEW RIP this month — saving ${best_save:.2f}/case ({rip_disc}% off)"
            )
            new_urgency = max(new_urgency, 60)

        if is_new_closeout:
            pct_str = f" ({co_pct}% off)" if co_pct else ""
            new_reasons.append(f"Newly added to closeout list{pct_str}")
            new_urgency = max(new_urgency, 55)

        if sp and pid not in special_map:
            pass  # already handled; this branch is a no-op guard
        # Check for new specials by seeing if the partial just started recently
        if sp and sp_days is not None:
            total_duration = sp_days  # approximate; we only know days remaining
            if total_duration is not None:
                # Consider it "new" if end_date minus today > (end_date - start_date - 7)
                # Simpler: just flag all active specials in this section
                # as they are time-bounded opportunities
                pass

        if new_reasons:
            item = _build_item(
                pid, "new_opportunities", "BUY_NOW" if new_urgency >= 55 else "CONSIDER",
                new_reasons, new_urgency,
            )
            if item:
                section_items["new_opportunities"][pid] = item

    # -- Also add lost-RIP products that may not be in current product_map ---
    # Lost RIPs: products that HAD a RIP last month but are still in the catalog
    # without a RIP this month. Some might already be added; ensure no dupes.
    for pid in lost_rip_pids:
        if pid in section_items["last_chance"]:
            continue  # already added
        if pid not in product_map:
            continue  # product not in current edition at all
        prev_save = prev_rip_save_map.get(pid, 0)
        reasons = [f"RIP of ${prev_save:.2f}/case expired — no longer available this month"]
        item = _build_item(pid, "last_chance", "LAST_CHANCE", reasons, 95)
        if item:
            section_items["last_chance"][pid] = item

    # -- Sort each section by urgency desc, limit to 50 ----------------------
    SECTION_LIMIT = 50

    def _sorted_items(items_dict: dict[UUID, BuySheetItem]) -> list[BuySheetItem]:
        return sorted(items_dict.values(), key=lambda x: -x.urgency)[:SECTION_LIMIT]

    # -- Compute market direction --------------------------------------------
    all_pct_changes = [
        pc["case_cost_pct"]
        for pc in price_change_map.values()
        if pc.get("case_cost_pct") is not None
    ]
    avg_mkt_change = (
        round(sum(all_pct_changes) / len(all_pct_changes), 2)
        if all_pct_changes else 0.0
    )
    if avg_mkt_change > 1:
        market_dir = "prices_rising"
    elif avg_mkt_change < -1:
        market_dir = "prices_falling"
    else:
        market_dir = "stable"

    # -- Total potential RIP savings -----------------------------------------
    total_rip_savings = sum(
        curr_rip_map[pid][0]["save_amount"]
        for pid in curr_rip_pids
        if pid in curr_rip_map and curr_rip_map[pid]
    )

    # -- Assemble sections ---------------------------------------------------
    last_chance_items = _sorted_items(section_items["last_chance"])
    strong_buy_items = _sorted_items(section_items["strong_buy"])
    buy_now_items = _sorted_items(section_items["buy_now"])
    consider_items = _sorted_items(section_items["consider"])
    defer_items = _sorted_items(section_items["defer"])
    new_opp_items = _sorted_items(section_items["new_opportunities"])

    sections = [
        BuySheetSection(
            key="last_chance",
            title="LAST CHANCE",
            subtitle="Buy or lose — expiring RIPs, closeouts, ending specials",
            count=len(last_chance_items),
            icon="fire",
            items=last_chance_items,
        ),
        BuySheetSection(
            key="strong_buy",
            title="STRONG BUY",
            subtitle="Best deals this month — multiple signals align",
            count=len(strong_buy_items),
            icon="star",
            items=strong_buy_items,
        ),
        BuySheetSection(
            key="buy_now",
            title="BUY NOW",
            subtitle="Good timing — favorable price or discount",
            count=len(buy_now_items),
            icon="check",
            items=buy_now_items,
        ),
        BuySheetSection(
            key="consider",
            title="CONSIDER",
            subtitle="Decent but not urgent — stable pricing with small upside",
            count=len(consider_items),
            icon="think",
            items=consider_items,
        ),
        BuySheetSection(
            key="defer",
            title="DEFER",
            subtitle="Wait for better — prices rising or at highs",
            count=len(defer_items),
            icon="pause",
            items=defer_items,
        ),
        BuySheetSection(
            key="new_opportunities",
            title="NEW THIS MONTH",
            subtitle="New RIPs, new closeouts, fresh opportunities",
            count=len(new_opp_items),
            icon="sparkle",
            items=new_opp_items,
        ),
    ]

    # Remove empty sections
    sections = [s for s in sections if s.count > 0]

    # -- Summary -------------------------------------------------------------
    all_unique_pids: set[UUID] = set()
    for sec_dict in section_items.values():
        all_unique_pids.update(sec_dict.keys())

    summary = BuySheetSummary(
        total_items=len(all_unique_pids),
        total_buy_now=len(section_items["buy_now"]),
        total_consider=len(section_items["consider"]),
        total_defer=len(section_items["defer"]),
        total_last_chance=len(section_items["last_chance"]),
        total_closeouts=len(closeout_pids),
        total_new_rips=len(new_rip_pids),
        total_lost_rips=len(lost_rip_pids & all_pids),
        potential_rip_savings=_money(total_rip_savings) or "0",
        market_direction=market_dir,
        avg_market_change_pct=avg_mkt_change,
        edition_label=_edition_label(edition),
    )

    return BuySheetResponse(sections=sections, summary=summary)
