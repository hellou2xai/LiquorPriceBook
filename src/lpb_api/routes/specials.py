"""Web Specials – active time-limited deals (partials).

  GET /api/v1/specials      all active partials with product info
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import asc, select
from sqlalchemy.orm import Session

from lpb_core.db import get_session
from lpb_core.db.models import (
    PartialsPricing,
    PartialsRip,
    Product,
    ProductEdition,
)

from .auth import get_current_user
from .catalog import _current_edition

router = APIRouter(tags=["specials"])


class WebSpecialOut(BaseModel):
    id: UUID
    kind: str  # "pricing" or "rip"
    description: str
    size: str | None = None
    start_date: date
    end_date: date
    days_remaining: int
    # Pricing partials
    best_case_price: Decimal | None = None
    best_case_tier: str | None = None
    best_btl_price: Decimal | None = None
    # RIP partials
    tier: str | None = None
    rip_price: Decimal | None = None
    rip_raw: str | None = None
    # Linked product info
    product_code: str | None = None
    product_description: str | None = None
    product_case_cost: Decimal | None = None
    product_btl_cost: Decimal | None = None
    match_confidence: Decimal | None = None


@router.get(
    "/api/v1/specials",
    response_model=list[WebSpecialOut],
)
def list_active_specials(
    distributor: str = Query("nj-allied"),
    user: dict = Depends(get_current_user),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
):
    edition = _current_edition(session, distributor)
    today = date.today()

    results: list[WebSpecialOut] = []

    # ── Partials Pricing ──
    pp_rows = (
        session.execute(
            select(PartialsPricing)
            .where(
                PartialsPricing.book_edition_id == edition.id,
                PartialsPricing.start_date <= today,
                PartialsPricing.end_date >= today,
            )
            .order_by(
                asc(PartialsPricing.end_date),
                asc(PartialsPricing.description),
            )
        )
        .scalars()
        .all()
    )

    # Bulk fetch linked product info
    pp_pids = [p.linked_product_id for p in pp_rows if p.linked_product_id]
    pp_product_info = _bulk_product_info(session, pp_pids, edition.id)

    for p in pp_rows:
        days_left = (p.end_date - today).days
        pinfo = pp_product_info.get(p.linked_product_id)
        results.append(
            WebSpecialOut(
                id=p.id,
                kind="pricing",
                description=p.description,
                size=None,
                start_date=p.start_date,
                end_date=p.end_date,
                days_remaining=max(days_left, 0),
                best_case_price=p.best_case_price,
                best_case_tier=p.best_case_tier,
                best_btl_price=p.best_btl_price,
                product_code=pinfo["code"] if pinfo else None,
                product_description=pinfo["desc"] if pinfo else None,
                product_case_cost=pinfo["case_cost"] if pinfo else None,
                product_btl_cost=pinfo["btl_cost"] if pinfo else None,
                match_confidence=p.match_confidence,
            )
        )

    # ── Partials RIPs ──
    pr_rows = (
        session.execute(
            select(PartialsRip)
            .where(
                PartialsRip.book_edition_id == edition.id,
                PartialsRip.start_date <= today,
                PartialsRip.end_date >= today,
            )
            .order_by(
                asc(PartialsRip.end_date),
                asc(PartialsRip.description),
            )
        )
        .scalars()
        .all()
    )

    pr_pids = [p.linked_product_id for p in pr_rows if p.linked_product_id]
    pr_product_info = _bulk_product_info(session, pr_pids, edition.id)

    for p in pr_rows:
        days_left = (p.end_date - today).days
        pinfo = pr_product_info.get(p.linked_product_id)
        results.append(
            WebSpecialOut(
                id=p.id,
                kind="rip",
                description=p.description,
                size=p.size,
                start_date=p.start_date,
                end_date=p.end_date,
                days_remaining=max(days_left, 0),
                tier=p.tier,
                rip_price=p.rip_price,
                rip_raw=p.rip_raw,
                product_code=pinfo["code"] if pinfo else None,
                product_description=pinfo["desc"] if pinfo else None,
                product_case_cost=pinfo["case_cost"] if pinfo else None,
                product_btl_cost=pinfo["btl_cost"] if pinfo else None,
                match_confidence=p.match_confidence,
            )
        )

    # Sort by days remaining (expiring soonest first)
    results.sort(key=lambda x: (x.days_remaining, x.description))
    return results


def _bulk_product_info(
    session: Session,
    product_ids: list[UUID],
    edition_id: UUID,
) -> dict[UUID, dict]:
    """Fetch product code + current edition info for a list of product IDs."""
    if not product_ids:
        return {}
    rows = session.execute(
        select(
            Product.id,
            Product.code,
            ProductEdition.description,
            ProductEdition.case_cost,
            ProductEdition.btl_cost,
        )
        .outerjoin(
            ProductEdition,
            (ProductEdition.product_id == Product.id)
            & (ProductEdition.book_edition_id == edition_id),
        )
        .where(Product.id.in_(product_ids))
    ).all()
    return {
        r.id: {
            "code": r.code,
            "desc": r.description,
            "case_cost": r.case_cost,
            "btl_cost": r.btl_cost,
        }
        for r in rows
    }
