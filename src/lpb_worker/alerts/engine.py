"""Per-ingest alert evaluation.

After every successful ingest, we run a deterministic rules pass over the new
edition and emit candidate alerts. Optionally, we batch-score them via Claude
Haiku for importance, take the top N per tenant, write ``alert_events`` rows,
and ship an email digest via Resend.

Rules implemented:
  * price_drop_pct       - case_cost dropped >= threshold% from prior edition
  * price_rise_pct       - case_cost rose >= threshold% from prior edition
  * new_rip              - first-time RIP for a product
  * rip_rotated          - RIP tier or save_amount changed vs prior edition
  * partial_expiring_soon- active partial ends within N days
  * new_closeout         - product entered the IR list this edition
  * watchlist_target_hit - product price <= watchlist target

The engine is intentionally a single module so it's trivial to debug.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import desc, select, text
from sqlalchemy.orm import Session

from lpb_core.db.models import (
    AlertEvent,
    BookEdition,
    InventoryReduction,
    PartialsPricing,
    PartialsRip,
    Product,
    ProductEdition,
    RipOffer,
    Tenant,
    Watchlist,
    WatchlistItem,
)

log = logging.getLogger(__name__)

# Default rule thresholds. We'll make these per-tenant configurable later.
PRICE_PCT_THRESHOLD = 5.0
PARTIAL_EXPIRY_DAYS = 2
MAX_ALERTS_PER_TENANT = 20


def evaluate_alerts(session: Session, book_edition_id: UUID) -> int:
    """Evaluate alerts for one freshly ingested edition. Returns number of
    AlertEvents written."""
    edition = session.get(BookEdition, book_edition_id)
    if edition is None:
        log.warning("evaluate_alerts: edition %s not found", book_edition_id)
        return 0
    log.info("evaluating alerts for edition %s (%d-%02d)",
             edition.id, edition.year, edition.month)

    prior_edition_id = session.execute(
        select(BookEdition.id)
        .where(
            BookEdition.distributor_id == edition.distributor_id,
            (BookEdition.year * 12 + BookEdition.month) <
            (edition.year * 12 + edition.month),
        )
        .order_by(desc(BookEdition.year), desc(BookEdition.month))
        .limit(1)
    ).scalar_one_or_none()

    candidates: list[dict[str, Any]] = []
    candidates += _rule_price_moves(session, edition.id)
    candidates += _rule_rip_changes(session, edition.id, prior_edition_id)
    candidates += _rule_new_closeouts(session, edition.id, prior_edition_id)
    candidates += _rule_partials_expiring(session, edition.id)

    log.info("alert candidates: %d", len(candidates))

    # Fan out per tenant. For now everyone shares one tenant; later we'll
    # filter by tenant watchlist / subscription rules.
    tenant_ids = [t.id for t in session.execute(select(Tenant)).scalars().all()]
    if not tenant_ids:
        return 0

    fired = 0
    for tenant_id in tenant_ids:
        # Per-tenant: also include watchlist-target-hit candidates.
        per_tenant = list(candidates) + _rule_watchlist_targets(
            session, tenant_id=tenant_id, book_edition_id=edition.id,
        )
        if not per_tenant:
            continue
        # Trim to top N by deterministic ranking (no Haiku in MVP - cheap and
        # deterministic is good enough; AI scoring can be layered later).
        ranked = sorted(
            per_tenant,
            key=lambda c: _candidate_priority(c),
            reverse=True,
        )[:MAX_ALERTS_PER_TENANT]
        for c in ranked:
            session.add(
                AlertEvent(
                    tenant_id=tenant_id,
                    product_id=c.get("product_id"),
                    book_edition_id=edition.id,
                    rule_type=c["rule_type"],
                    score=c.get("score"),
                    payload=c.get("payload", {}),
                )
            )
            fired += 1
    session.flush()
    log.info("alert_events written: %d across %d tenants", fired, len(tenant_ids))
    return fired


def _candidate_priority(c: dict[str, Any]) -> float:
    """Heuristic ranker. Closeouts beat watchlist hits beat RIPs beat moves."""
    base = {
        "new_closeout": 1.0,
        "watchlist_target_hit": 0.95,
        "rip_rotated": 0.85,
        "new_rip": 0.8,
        "price_drop_pct": 0.7,
        "price_rise_pct": 0.6,
        "partial_expiring_soon": 0.5,
    }.get(c["rule_type"], 0.3)
    extra = abs(float(c.get("score") or 0)) * 0.01
    return base + extra


# --------------------- rules ---------------------

def _rule_price_moves(session: Session, edition_id: UUID) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            "SELECT mpc.product_id, p.code, pe.description, "
            "       mpc.case_cost_pct AS pct, mpc.case_cost, mpc.prev_case_cost "
            "FROM mv_price_changes mpc "
            "JOIN product_editions pe ON pe.id = mpc.product_edition_id "
            "JOIN products p ON p.id = pe.product_id "
            "WHERE mpc.book_edition_id = :eid "
            "  AND mpc.case_cost_pct IS NOT NULL "
            "  AND ABS(mpc.case_cost_pct) >= :thresh"
        ),
        {"eid": str(edition_id), "thresh": PRICE_PCT_THRESHOLD},
    ).all()
    out: list[dict[str, Any]] = []
    for r in rows:
        rule = "price_drop_pct" if r.pct < 0 else "price_rise_pct"
        out.append({
            "rule_type": rule,
            "product_id": r.product_id,
            "score": float(abs(r.pct)),
            "payload": {
                "code": r.code,
                "description": r.description,
                "pct": float(r.pct),
                "case_cost": float(r.case_cost) if r.case_cost is not None else None,
                "prev_case_cost": float(r.prev_case_cost) if r.prev_case_cost is not None else None,
            },
        })
    return out


def _rule_rip_changes(
    session: Session, edition_id: UUID, prior_edition_id: UUID | None,
) -> list[dict[str, Any]]:
    if prior_edition_id is None:
        return []
    # All RIPs in current edition (joined to product).
    current = session.execute(
        select(
            Product.id.label("product_id"),
            Product.code,
            ProductEdition.description,
            RipOffer.tier,
            RipOffer.save_amount,
        )
        .join(ProductEdition, ProductEdition.product_id == Product.id)
        .join(RipOffer, RipOffer.product_edition_id == ProductEdition.id)
        .where(ProductEdition.book_edition_id == edition_id)
    ).all()
    prior = session.execute(
        select(
            ProductEdition.product_id,
            RipOffer.tier,
            RipOffer.save_amount,
        )
        .join(RipOffer, RipOffer.product_edition_id == ProductEdition.id)
        .where(ProductEdition.book_edition_id == prior_edition_id)
    ).all()
    prior_keys = {(p.product_id, p.tier): p.save_amount for p in prior}
    prior_product_ids = {p.product_id for p in prior}

    out: list[dict[str, Any]] = []
    for r in current:
        key = (r.product_id, r.tier)
        if key not in prior_keys:
            rule = "new_rip" if r.product_id not in prior_product_ids else "rip_rotated"
            out.append({
                "rule_type": rule,
                "product_id": r.product_id,
                "score": float(r.save_amount),
                "payload": {
                    "code": r.code,
                    "description": r.description,
                    "tier": r.tier,
                    "save_amount": float(r.save_amount),
                },
            })
        elif prior_keys[key] != r.save_amount:
            out.append({
                "rule_type": "rip_rotated",
                "product_id": r.product_id,
                "score": float(abs(r.save_amount - prior_keys[key])),
                "payload": {
                    "code": r.code,
                    "description": r.description,
                    "tier": r.tier,
                    "save_amount": float(r.save_amount),
                    "prior_save_amount": float(prior_keys[key]),
                },
            })
    return out


def _rule_new_closeouts(
    session: Session, edition_id: UUID, prior_edition_id: UUID | None,
) -> list[dict[str, Any]]:
    rows = session.execute(
        select(
            InventoryReduction.product_id,
            Product.code,
            InventoryReduction.description,
            InventoryReduction.case_save,
            InventoryReduction.original_case,
        )
        .join(Product, Product.id == InventoryReduction.product_id)
        .where(InventoryReduction.book_edition_id == edition_id)
    ).all()
    if not rows:
        return []
    prior_product_ids: set[UUID] = set()
    if prior_edition_id is not None:
        prior_product_ids = {
            r.product_id
            for r in session.execute(
                select(InventoryReduction.product_id)
                .where(InventoryReduction.book_edition_id == prior_edition_id)
            ).all()
        }
    out: list[dict[str, Any]] = []
    for r in rows:
        if r.product_id in prior_product_ids:
            continue
        pct = (
            (float(r.case_save) / float(r.original_case) * 100)
            if r.case_save and r.original_case else None
        )
        out.append({
            "rule_type": "new_closeout",
            "product_id": r.product_id,
            "score": pct,
            "payload": {
                "code": r.code,
                "description": r.description,
                "case_save": float(r.case_save) if r.case_save is not None else None,
                "pct_off": pct,
            },
        })
    return out


def _rule_partials_expiring(
    session: Session, edition_id: UUID,
) -> list[dict[str, Any]]:
    today = date.today()
    out: list[dict[str, Any]] = []
    pp_rows = session.execute(
        select(PartialsPricing, Product.code)
        .outerjoin(Product, Product.id == PartialsPricing.linked_product_id)
        .where(
            PartialsPricing.book_edition_id == edition_id,
            PartialsPricing.end_date >= today,
            PartialsPricing.end_date <=
            text(f"CURRENT_DATE + INTERVAL '{PARTIAL_EXPIRY_DAYS} days'"),
        )
    ).all()
    for p, code in pp_rows:
        out.append({
            "rule_type": "partial_expiring_soon",
            "product_id": p.linked_product_id,
            "score": (p.end_date - today).days,
            "payload": {
                "code": code,
                "description": p.description,
                "ends_in_days": (p.end_date - today).days,
                "best_case_price": (
                    float(p.best_case_price)
                    if p.best_case_price is not None else None
                ),
            },
        })
    pr_rows = session.execute(
        select(PartialsRip, Product.code)
        .outerjoin(Product, Product.id == PartialsRip.linked_product_id)
        .where(
            PartialsRip.book_edition_id == edition_id,
            PartialsRip.end_date >= today,
            PartialsRip.end_date <=
            text(f"CURRENT_DATE + INTERVAL '{PARTIAL_EXPIRY_DAYS} days'"),
        )
    ).all()
    for p, code in pr_rows:
        out.append({
            "rule_type": "partial_expiring_soon",
            "product_id": p.linked_product_id,
            "score": (p.end_date - today).days,
            "payload": {
                "code": code,
                "description": p.description,
                "ends_in_days": (p.end_date - today).days,
                "tier": p.tier,
                "rip_price": float(p.rip_price) if p.rip_price is not None else None,
            },
        })
    return out


def _rule_watchlist_targets(
    session: Session, *, tenant_id: UUID, book_edition_id: UUID,
) -> list[dict[str, Any]]:
    rows = session.execute(
        select(
            WatchlistItem.product_id,
            Product.code,
            ProductEdition.description,
            ProductEdition.case_cost,
            WatchlistItem.target_case_price,
        )
        .join(Watchlist, Watchlist.id == WatchlistItem.watchlist_id)
        .join(Product, Product.id == WatchlistItem.product_id)
        .join(
            ProductEdition,
            (ProductEdition.product_id == Product.id) &
            (ProductEdition.book_edition_id == book_edition_id),
        )
        .where(
            Watchlist.tenant_id == tenant_id,
            WatchlistItem.target_case_price.is_not(None),
            ProductEdition.case_cost <= WatchlistItem.target_case_price,
        )
    ).all()
    return [
        {
            "rule_type": "watchlist_target_hit",
            "product_id": r.product_id,
            "score": float(r.target_case_price - r.case_cost) if r.case_cost is not None else None,
            "payload": {
                "code": r.code,
                "description": r.description,
                "case_cost": float(r.case_cost) if r.case_cost is not None else None,
                "target_case_price": float(r.target_case_price),
            },
        }
        for r in rows
    ]
