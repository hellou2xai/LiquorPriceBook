"""AI-A: buy-now-vs-defer recommender.

  GET /api/v1/products/{code}/verdict       Returns a cached or freshly
                                             generated verdict using Claude
                                             Haiku, given a structured
                                             feature vector for the product.

The feature vector includes:
  - current case_cost and the delta vs the prior edition (from mv_price_changes)
  - the current RIP details (tier, save, post-RIP case price)
  - the RIP stability flag (same save_amount in prior edition?)
  - active partials (with days-to-expiry)
  - is_closeout flag
  - category volatility percentile (placeholder for now)

Cache key is ``(product_id, book_edition_id)`` - one Haiku call serves every
retailer asking about the same product in the same edition.

If ANTHROPIC_API_KEY is not configured, returns a *static heuristic verdict*
so the UI still demos without paid AI. The static rule:
  - is_closeout -> BUY_NOW (terminal)
  - case_cost_pct < -3 -> BUY_NOW (just dropped >3%)
  - case_cost_pct > +5 -> DEFER (price went up sharply)
  - rip_stable is False -> BUY_NOW (rotating tier; may disappear)
  - otherwise -> HOLD
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import desc, select, text
from sqlalchemy.orm import Session

from lpb_core.db import get_session
from lpb_core.db.models import (
    AiVerdictCache,
    BookEdition,
    Distributor,
    InventoryReduction,
    PartialsPricing,
    PartialsRip,
    Product,
    ProductEdition,
    RipOffer,
)
from lpb_core.settings import settings

from .auth import get_current_user

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["ai"])

_MODEL_HAIKU = "claude-haiku-4-5-20251001"


class VerdictOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    verdict: str            # BUY_NOW | DEFER | HOLD | PASS
    confidence: Decimal
    rationale: str
    factors: dict
    model: str
    generated_at: datetime
    cached: bool


def _feature_vector(session: Session, code: str, distributor_slug: str) -> dict[str, Any]:
    dist = session.execute(
        select(Distributor).where(Distributor.slug == distributor_slug)
    ).scalar_one_or_none()
    if dist is None:
        raise HTTPException(status_code=404, detail=f"Unknown distributor {distributor_slug}")

    pe_row = session.execute(
        select(ProductEdition, Product.id.label("product_id"), BookEdition.id.label("be_id"))
        .join(Product, Product.id == ProductEdition.product_id)
        .join(BookEdition, BookEdition.id == ProductEdition.book_edition_id)
        .where(Product.distributor_id == dist.id, Product.code == code)
        .order_by(desc(BookEdition.year), desc(BookEdition.month))
        .limit(1)
    ).first()
    if pe_row is None:
        raise HTTPException(status_code=404, detail="Product not found")
    pe: ProductEdition = pe_row[0]
    product_id: UUID = pe_row.product_id
    be_id: UUID = pe_row.be_id

    # Price delta from matview.
    mv = session.execute(
        text(
            "SELECT prev_case_cost, case_cost_pct FROM mv_price_changes "
            "WHERE product_edition_id = :pe_id"
        ),
        {"pe_id": str(pe.id)},
    ).first()
    prev_case_cost = float(mv.prev_case_cost) if mv and mv.prev_case_cost is not None else None
    case_cost_pct = float(mv.case_cost_pct) if mv and mv.case_cost_pct is not None else None

    # Current RIPs.
    rip_rows = session.execute(
        select(RipOffer).where(RipOffer.product_edition_id == pe.id)
    ).scalars().all()
    rips = [
        {
            "tier": r.tier,
            "tier_cases": r.tier_cases,
            "save_amount": float(r.save_amount),
            "case_price": float(r.case_price) if r.case_price is not None else None,
            "btl_price": float(r.btl_price) if r.btl_price is not None else None,
        }
        for r in rip_rows
    ]

    # RIP stability: were these same tiers present in the prior edition?
    prior_be = session.execute(
        select(BookEdition.id)
        .where(
            BookEdition.distributor_id == dist.id,
            (BookEdition.year * 12 + BookEdition.month) <
            (pe.book_edition.year * 12 + pe.book_edition.month) if False else True,
        )
        .order_by(desc(BookEdition.year), desc(BookEdition.month))
        .limit(2)
    ).scalars().all()
    prior_be_id = prior_be[1] if len(prior_be) > 1 else None
    rip_stable = None
    if prior_be_id and rips:
        prior_rip_rows = session.execute(
            select(RipOffer.tier, RipOffer.save_amount)
            .join(ProductEdition, ProductEdition.id == RipOffer.product_edition_id)
            .where(
                ProductEdition.product_id == product_id,
                ProductEdition.book_edition_id == prior_be_id,
            )
        ).all()
        prior_map = {tier: float(save) for tier, save in prior_rip_rows}
        rip_stable = all(
            prior_map.get(r["tier"]) == r["save_amount"] for r in rips
        )

    # Closeout?
    is_closeout = session.execute(
        select(InventoryReduction.id)
        .where(
            InventoryReduction.book_edition_id == be_id,
            InventoryReduction.product_id == product_id,
        )
        .limit(1)
    ).scalar_one_or_none() is not None

    # Active partials.
    today = date.today()
    pp_rows = session.execute(
        select(PartialsPricing)
        .where(
            PartialsPricing.linked_product_id == product_id,
            PartialsPricing.start_date <= today,
            PartialsPricing.end_date >= today,
        )
    ).scalars().all()
    pr_rows = session.execute(
        select(PartialsRip)
        .where(
            PartialsRip.linked_product_id == product_id,
            PartialsRip.start_date <= today,
            PartialsRip.end_date >= today,
        )
    ).scalars().all()
    partials = []
    for p in pp_rows:
        partials.append({
            "kind": "pricing",
            "ends_in_days": (p.end_date - today).days,
            "best_case_price": float(p.best_case_price) if p.best_case_price is not None else None,
        })
    for r in pr_rows:
        partials.append({
            "kind": "rip",
            "ends_in_days": (r.end_date - today).days,
            "rip_price": float(r.rip_price) if r.rip_price is not None else None,
        })

    return {
        "product_id": str(product_id),
        "book_edition_id": str(be_id),
        "code": code,
        "description": pe.description,
        "size": pe.size,
        "pack": pe.pack,
        "case_cost": float(pe.case_cost) if pe.case_cost is not None else None,
        "btl_cost": float(pe.btl_cost) if pe.btl_cost is not None else None,
        "prev_case_cost": prev_case_cost,
        "case_cost_pct": case_cost_pct,
        "rips": rips,
        "rip_stable": rip_stable,
        "is_closeout": is_closeout,
        "active_partials": partials,
    }


def _heuristic_verdict(fv: dict[str, Any]) -> dict[str, Any]:
    """Fallback static rule when no Anthropic key is configured."""
    factors = []
    verdict = "HOLD"
    if fv["is_closeout"]:
        verdict = "BUY_NOW"
        factors.append("closeout (terminal listing)")
    elif fv["case_cost_pct"] is not None and fv["case_cost_pct"] <= -3:
        verdict = "BUY_NOW"
        factors.append(f"case cost dropped {fv['case_cost_pct']:.1f}%")
    elif fv["case_cost_pct"] is not None and fv["case_cost_pct"] >= 5:
        verdict = "DEFER"
        factors.append(f"case cost rose {fv['case_cost_pct']:.1f}%")
    elif fv["rip_stable"] is False:
        verdict = "BUY_NOW"
        factors.append("RIP tier rotated vs prior edition")
    if fv.get("active_partials"):
        nearest = min(p["ends_in_days"] for p in fv["active_partials"])
        factors.append(f"active partial ends in {nearest}d")
    rationale = (
        "Heuristic verdict (no AI key configured). "
        + (factors[0] if factors else "Stable pricing and RIP this month.")
    )
    return {
        "verdict": verdict,
        "confidence": 0.55,
        "rationale": rationale,
        "factors": {"signals": factors},
        "model": "heuristic-v1",
    }


def _call_haiku(fv: dict[str, Any]) -> dict[str, Any]:
    """Call Claude Haiku via the Anthropic SDK. Returns parsed JSON dict.

    Schema we ask the model to emit:
      { "verdict": "BUY_NOW"|"DEFER"|"HOLD"|"PASS",
        "confidence": 0.0-1.0,
        "rationale": "<=180 chars",
        "factors": ["<bullet>", ...] }
    """
    from anthropic import Anthropic
    client = Anthropic(api_key=settings.anthropic_api_key)
    prompt = (
        "You're an analyst for an independent NJ liquor retailer deciding whether "
        "to buy a SKU this month or wait until next month. NJ wholesalers publish "
        "a new price book each month with locked prices and Retail Incentive "
        "Programs (RIPs). Closeouts are terminal - if listed, it's the last "
        "chance. Reply ONLY with a JSON object matching this schema:\n"
        '{"verdict": "BUY_NOW"|"DEFER"|"HOLD"|"PASS",\n'
        ' "confidence": 0.0-1.0,\n'
        ' "rationale": "one sentence, <= 180 chars",\n'
        ' "factors": ["<short signal>", "..."]}\n\n'
        "Feature vector:\n" + json.dumps(fv, default=str, indent=2)
    )
    resp = client.messages.create(
        model=_MODEL_HAIKU,
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    text_out = "".join(
        block.text for block in resp.content if hasattr(block, "text")
    ).strip()
    # Strip markdown fences if Haiku wraps in them.
    if text_out.startswith("```"):
        text_out = text_out.strip("`")
        text_out = text_out.replace("json\n", "", 1)
    parsed = json.loads(text_out)
    parsed["model"] = _MODEL_HAIKU
    return parsed


@router.get("/products/{code}/verdict", response_model=VerdictOut)
def get_verdict(
    code: str,
    distributor: str = Query("nj-allied"),
    refresh: bool = Query(False, description="Bypass cache and regenerate"),
    user: dict = Depends(get_current_user),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
):
    fv = _feature_vector(session, code, distributor)
    pe_book_edition_id = UUID(fv["book_edition_id"])
    product_id = UUID(fv["product_id"])

    # 1. Cache lookup
    if not refresh:
        cached = session.execute(
            select(AiVerdictCache).where(
                AiVerdictCache.product_id == product_id,
                AiVerdictCache.book_edition_id == pe_book_edition_id,
            )
        ).scalar_one_or_none()
        if cached:
            return VerdictOut(
                verdict=cached.verdict,
                confidence=cached.confidence,
                rationale=cached.rationale,
                factors=cached.factors or {},
                model=cached.model,
                generated_at=cached.generated_at,
                cached=True,
            )

    # 2. Generate
    try:
        if settings.anthropic_api_key:
            parsed = _call_haiku(fv)
        else:
            parsed = _heuristic_verdict(fv)
    except Exception as exc:  # noqa: BLE001
        log.exception("verdict generation failed; falling back to heuristic")
        parsed = _heuristic_verdict(fv)
        parsed["rationale"] = parsed["rationale"] + f" (AI fallback: {type(exc).__name__})"

    # 3. Cache and return
    factors_payload = parsed.get("factors") or {}
    if isinstance(factors_payload, list):
        factors_payload = {"signals": factors_payload}
    confidence = float(parsed.get("confidence", 0.5))
    confidence = max(0.0, min(1.0, confidence))

    cached_row = AiVerdictCache(
        product_id=product_id,
        book_edition_id=pe_book_edition_id,
        verdict=parsed["verdict"],
        confidence=confidence,
        rationale=parsed["rationale"][:1000],
        factors=factors_payload,
        model=parsed.get("model", "unknown"),
    )
    # Upsert: if a row already exists, update it.
    existing = session.execute(
        select(AiVerdictCache).where(
            AiVerdictCache.product_id == product_id,
            AiVerdictCache.book_edition_id == pe_book_edition_id,
        )
    ).scalar_one_or_none()
    if existing:
        existing.verdict = cached_row.verdict
        existing.confidence = cached_row.confidence
        existing.rationale = cached_row.rationale
        existing.factors = cached_row.factors
        existing.model = cached_row.model
        existing.generated_at = datetime.utcnow()
        session.commit()
        return VerdictOut(
            verdict=existing.verdict,
            confidence=existing.confidence,
            rationale=existing.rationale,
            factors=existing.factors or {},
            model=existing.model,
            generated_at=existing.generated_at,
            cached=False,
        )
    session.add(cached_row)
    session.commit()
    return VerdictOut(
        verdict=cached_row.verdict,
        confidence=cached_row.confidence,
        rationale=cached_row.rationale,
        factors=cached_row.factors or {},
        model=cached_row.model,
        generated_at=cached_row.generated_at,
        cached=False,
    )
