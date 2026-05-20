"""Price history trend endpoint.

  GET /api/v1/catalog/{code}/price-history

Returns a product's case cost, bottle cost, best RIP save, and closeout status
across every book edition it has appeared in, ordered chronologically.  Also
returns pre-computed summary statistics and a simple price-trend label.
"""

from __future__ import annotations

import calendar
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import and_, asc, func, select
from sqlalchemy.orm import Session

from lpb_core.db import get_session
from lpb_core.db.models import (
    BookEdition,
    Brand,
    Distributor,
    InventoryReduction,
    Product,
    ProductEdition,
    RipOffer,
)

from .auth import get_current_user

router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])


# ---------------------------------------------------------------------------
# Response shapes
# ---------------------------------------------------------------------------

class PriceDataPoint(BaseModel):
    edition_label: str
    year: int
    month: int
    case_cost: Decimal | None
    btl_cost: Decimal | None
    best_rip_save: Decimal | None
    effective_cost: Decimal | None
    has_rip: bool
    has_closeout: bool


class PriceHistorySummary(BaseModel):
    min_case_cost: Decimal | None
    max_case_cost: Decimal | None
    avg_case_cost: Decimal | None
    current_case_cost: Decimal | None
    total_editions: int
    price_trend: str  # "rising" | "falling" | "stable"


class PriceHistoryResponse(BaseModel):
    code: str
    description: str | None
    brand: str | None
    data_points: list[PriceDataPoint]
    summary: PriceHistorySummary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _edition_label(year: int, month: int) -> str:
    """Human-readable label like 'Apr 2026'."""
    return f"{calendar.month_abbr[month]} {year}"


def _price_trend(data_points: list[PriceDataPoint]) -> str:
    """Derive a trend label from the chronologically ordered data points.

    Only points that have a non-null case_cost participate.  If fewer than
    two such points exist the result is 'stable'.  A change of less than 1 %
    over the entire window is also 'stable'.
    """
    costs = [dp.case_cost for dp in data_points if dp.case_cost is not None]
    if len(costs) < 2:
        return "stable"
    first, last = costs[0], costs[-1]
    if first == 0:
        return "stable"
    pct_change = (last - first) / first * 100
    if pct_change > Decimal("1"):
        return "rising"
    if pct_change < Decimal("-1"):
        return "falling"
    return "stable"


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.get("/{code}/price-history", response_model=PriceHistoryResponse)
def get_price_history(
    code: str,
    distributor: str = Query("nj-allied"),
    user: dict = Depends(get_current_user),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
):
    # 1. Resolve distributor and product.
    dist = session.execute(
        select(Distributor).where(Distributor.slug == distributor)
    ).scalar_one_or_none()
    if dist is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown distributor '{distributor}'",
        )

    product = session.execute(
        select(Product).where(
            Product.distributor_id == dist.id,
            Product.code == code,
        )
    ).scalar_one_or_none()
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product '{code}' not found",
        )

    # 2. Subquery: best (max) RIP save_amount per product_edition.
    best_rip_sq = (
        select(
            RipOffer.product_edition_id,
            func.max(RipOffer.save_amount).label("max_save"),
        )
        .group_by(RipOffer.product_edition_id)
        .subquery()
    )

    # 3. Subquery: closeout flag per (product, book_edition).
    closeout_sq = (
        select(
            InventoryReduction.book_edition_id,
        )
        .where(InventoryReduction.product_id == product.id)
        .subquery()
    )

    # 4. Main query: one row per edition the product appeared in.
    rows = session.execute(
        select(
            BookEdition.year,
            BookEdition.month,
            ProductEdition.description,
            ProductEdition.case_cost,
            ProductEdition.btl_cost,
            Brand.display_name.label("brand_display"),
            best_rip_sq.c.max_save.label("best_rip_save"),
            closeout_sq.c.book_edition_id.isnot(None).label("has_closeout"),
        )
        .select_from(ProductEdition)
        .join(BookEdition, BookEdition.id == ProductEdition.book_edition_id)
        .outerjoin(Brand, Brand.id == ProductEdition.brand_id)
        .outerjoin(
            best_rip_sq,
            best_rip_sq.c.product_edition_id == ProductEdition.id,
        )
        .outerjoin(
            closeout_sq,
            closeout_sq.c.book_edition_id == ProductEdition.book_edition_id,
        )
        .where(ProductEdition.product_id == product.id)
        .order_by(asc(BookEdition.year), asc(BookEdition.month))
    ).all()

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No edition data found for product '{code}'",
        )

    # 5. Build data points.
    data_points: list[PriceDataPoint] = []
    description: str | None = None
    brand: str | None = None

    for row in rows:
        # Use the most-recent non-null values for description / brand.
        if row.description:
            description = row.description
        if row.brand_display:
            brand = row.brand_display

        has_rip = row.best_rip_save is not None
        # has_closeout comes from the outer-join: the column is None when
        # there is no matching closeout row, not a boolean False.
        has_closeout = row.has_closeout if row.has_closeout is not None else False

        effective_cost: Decimal | None = None
        if row.case_cost is not None and row.best_rip_save is not None:
            effective_cost = row.case_cost - row.best_rip_save
        elif row.case_cost is not None:
            effective_cost = row.case_cost

        data_points.append(
            PriceDataPoint(
                edition_label=_edition_label(row.year, row.month),
                year=row.year,
                month=row.month,
                case_cost=row.case_cost,
                btl_cost=row.btl_cost,
                best_rip_save=row.best_rip_save,
                effective_cost=effective_cost,
                has_rip=has_rip,
                has_closeout=bool(has_closeout),
            )
        )

    # 6. Compute summary stats.
    costs_with_values = [dp.case_cost for dp in data_points if dp.case_cost is not None]
    min_case_cost: Decimal | None = min(costs_with_values) if costs_with_values else None
    max_case_cost: Decimal | None = max(costs_with_values) if costs_with_values else None
    avg_case_cost: Decimal | None = (
        sum(costs_with_values) / len(costs_with_values) if costs_with_values else None
    )
    current_case_cost: Decimal | None = (
        data_points[-1].case_cost if data_points else None
    )

    summary = PriceHistorySummary(
        min_case_cost=min_case_cost,
        max_case_cost=max_case_cost,
        avg_case_cost=(
            Decimal(str(round(float(avg_case_cost), 2))) if avg_case_cost is not None else None
        ),
        current_case_cost=current_case_cost,
        total_editions=len(data_points),
        price_trend=_price_trend(data_points),
    )

    return PriceHistoryResponse(
        code=code,
        description=description,
        brand=brand,
        data_points=data_points,
        summary=summary,
    )
