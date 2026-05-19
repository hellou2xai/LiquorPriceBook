"""The ingest pipeline.

Given an ``ingest_run_id``:

  1. Load the associated ``book_edition`` (including the deferred PDF bytes).
  2. Run the vendor scraper (currently only NjAllied) on those bytes.
  3. Normalise: category resolver + brand deriver + duplicate-code reconciler.
  4. Upsert products and product_editions.
  5. Insert dependent rows: rip_offers, partials_pricing, partials_rips,
     inventory_reduction, combos, combo_components, keg_list. Fuzzy-link
     anything that lacks a hard product code, dump <0.85 confidence rows
     into ``low_confidence_matches``.
  6. Update the ingest_run with rows_by_section and mark it completed.

Idempotency: every upsert keys on a natural unique constraint
(``(distributor_id, code)`` for products; ``(product_id, book_edition_id)``
for product_editions; ``(book_edition_id, sku)`` for combos; etc.) and uses
``ON CONFLICT DO NOTHING / DO UPDATE``. Re-running the pipeline against the
same edition is safe.
"""

from __future__ import annotations

import hashlib
import logging
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from lpb_core.db.models import (
    BookEdition,
    Category,
    Combo,
    IngestRun,
    InventoryReduction,
    KegListEntry,
    LowConfidenceMatch,
    PartialsPricing,
    PartialsRip,
    Product,
    ProductEdition,
    RipOffer,
)

from .matchers import FuzzyProductMatcher
from .normalisers import BrandDeriver, CategoryResolver, resolve_duplicate_code_categories

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _tier_to_cases(tier: str | None) -> int | None:
    """`1CS` -> 1, `5CS` -> 5, `1CASE` -> 1, etc."""
    if not tier:
        return None
    digits = "".join(ch for ch in tier if ch.isdigit())
    return int(digits) if digits else None


def compute_content_hash(pdf_bytes: bytes) -> str:
    return hashlib.sha256(pdf_bytes).hexdigest()


# ---------------------------------------------------------------------------
# main entry point
# ---------------------------------------------------------------------------

def run_ingest(session: Session, ingest_run_id: UUID) -> dict[str, int]:
    """Execute the full pipeline for a single IngestRun. Commits at the end.

    Returns the rows_by_section dict (also persisted on the IngestRun row).
    """
    run: IngestRun = session.get(IngestRun, ingest_run_id)  # type: ignore[assignment]
    if run is None:
        raise RuntimeError(f"IngestRun {ingest_run_id} not found")
    edition: BookEdition = session.execute(
        select(BookEdition).where(BookEdition.id == run.book_edition_id)
    ).scalar_one()

    if not edition.pdf_bytes:
        raise RuntimeError(
            f"BookEdition {edition.id} has no pdf_bytes; cannot scrape"
        )

    log.info("ingest_run=%s book_edition=%s starting", run.id, edition.id)
    pdf_bytes: bytes = edition.pdf_bytes

    # 1. Scrape to a temp file (pdfplumber wants a path).
    sections = _scrape_pdf_bytes(pdf_bytes, edition.source_filename)
    log.info("scraped sections: %s", {k: len(v) for k, v in sections.items()})

    # 2. Build cleaning helpers and run the normalisation passes.
    cat_resolver = CategoryResolver(session)
    brand_deriver = BrandDeriver(session)
    sort_order_by_cat = dict(
        session.execute(select(Category.id, Category.sort_order)).all()
    )

    # Resolve category_id for every main-catalog row, dedupe by code,
    # then upsert products + product_editions.
    main_rows: list[dict[str, Any]] = []
    for raw in sections.get("main_catalog", []):
        cat_id = cat_resolver.resolve(raw.get("category"))
        brand_id = brand_deriver.ensure(
            description=raw.get("brand_header"),
            brand_header=raw.get("brand_header"),
        )
        main_rows.append({**raw, "category_id": cat_id, "brand_id": brand_id})

    code_to_winning_cat = resolve_duplicate_code_categories(
        [{"code": r["code"], "category_id": r["category_id"]} for r in main_rows],
        sort_order_by_category_id=sort_order_by_cat,
    )

    products_inserted = _upsert_products_and_editions(
        session=session,
        distributor_id=edition.distributor_id,
        book_edition_id=edition.id,
        main_rows=main_rows,
        winning_category_by_code=code_to_winning_cat,
    )

    # 3. RIP offers (1:N from product_editions).
    rip_inserted = _insert_rip_offers(session, edition.id, main_rows)

    # 4. Build the matcher index now that products exist for this edition.
    product_index = _build_product_index(session, edition.distributor_id)
    matcher = FuzzyProductMatcher(product_index)

    # 5. Insert dependent sections.
    pp_inserted, pp_lc = _insert_partials_pricing(
        session, edition.id, sections.get("partials_pricing", []), matcher
    )
    pr_inserted, pr_lc = _insert_partials_rips(
        session, edition.id, sections.get("partials_rips", []), matcher
    )
    ir_inserted = _insert_inventory_reduction(
        session, edition.id, sections.get("inventory_reduction", []), matcher
    )
    combos_inserted = _insert_combos(
        session, edition.id, sections.get("combos", [])
    )
    keg_inserted = _insert_kegs(
        session, edition.id, sections.get("keg_list", []), matcher
    )

    rows_by_section = {
        "main_catalog": products_inserted,
        "rip_offers": rip_inserted,
        "partials_pricing": pp_inserted,
        "partials_rips": pr_inserted,
        "inventory_reduction": ir_inserted,
        "combos": combos_inserted,
        "keg_list": keg_inserted,
        "low_confidence_matches": pp_lc + pr_lc,
        "unknown_categories": len(cat_resolver.unknown),
    }
    if cat_resolver.unknown:
        log.warning(
            "unknown category strings (first 5): %s",
            list(cat_resolver.unknown.items())[:5],
        )

    # 6. Stamp the edition + ingest run as done.
    session.execute(
        update(BookEdition)
        .where(BookEdition.id == edition.id)
        .values(scraped_at=datetime.now(UTC))
    )
    session.execute(
        update(IngestRun)
        .where(IngestRun.id == run.id)
        .values(
            status="completed",
            finished_at=datetime.now(UTC),
            rows_by_section=rows_by_section,
        )
    )
    session.commit()
    log.info("ingest_run=%s completed rows=%s", run.id, rows_by_section)
    return rows_by_section


# ---------------------------------------------------------------------------
# scraper bridge
# ---------------------------------------------------------------------------

def _scrape_pdf_bytes(pdf_bytes: bytes, source_filename: str) -> dict[str, list[dict]]:
    """Write bytes to a temp file and call the NjAllied scraper."""
    from templates.NjAllied import scrape_pdf

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = Path(tmp.name)
    try:
        results, _diag = scrape_pdf(tmp_path, source_name=source_filename)
        return results
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# upserts
# ---------------------------------------------------------------------------

def _upsert_products_and_editions(
    *,
    session: Session,
    distributor_id: UUID,
    book_edition_id: UUID,
    main_rows: list[dict[str, Any]],
    winning_category_by_code: dict[str, UUID | None],
) -> int:
    """Upsert products by (distributor_id, code), then product_editions by
    (product_id, book_edition_id). Returns count of product_editions inserted."""
    if not main_rows:
        return 0

    # Unique product (code -> first-seen row) for the products table.
    by_code: dict[str, dict[str, Any]] = {}
    for r in main_rows:
        code = r.get("code")
        if not code:
            continue
        by_code.setdefault(code, r)

    if not by_code:
        return 0

    # Upsert products in bulk.
    product_payload = [
        {
            "distributor_id": distributor_id,
            "code": code,
            "first_seen_in_edition_id": book_edition_id,
            "last_seen_in_edition_id": book_edition_id,
        }
        for code in by_code
    ]
    stmt = (
        pg_insert(Product)
        .values(product_payload)
        .on_conflict_do_update(
            index_elements=["distributor_id", "code"],
            set_={"last_seen_in_edition_id": book_edition_id},
        )
    )
    session.execute(stmt)
    session.flush()

    # Map code -> product_id for the editions insert.
    code_to_pid = dict(
        session.execute(
            select(Product.code, Product.id).where(
                Product.distributor_id == distributor_id,
                Product.code.in_(list(by_code.keys())),
            )
        ).all()
    )

    edition_payload: list[dict[str, Any]] = []
    for code, r in by_code.items():
        pid = code_to_pid.get(code)
        if pid is None:
            continue
        edition_payload.append(
            {
                "product_id": pid,
                "book_edition_id": book_edition_id,
                "category_id": winning_category_by_code.get(code),
                "brand_id": r.get("brand_id"),
                "raw_category": r.get("category"),
                "raw_brand_header": r.get("brand_header"),
                "description": r.get("brand_header"),  # main catalog has no separate desc
                "size": r.get("size"),
                "pack": r.get("pack"),
                "po_cost": _to_decimal(r.get("po_cost")),
                "case_cost": _to_decimal(r.get("case_cost")),
                "btl_cost": _to_decimal(r.get("btl_cost")),
                "best_buy_raw": r.get("best_buy"),
                "best_rip_raw": r.get("best_rip"),
                "page": r.get("page"),
                "lane": r.get("lane"),
            }
        )

    if not edition_payload:
        return 0

    # Replace any existing edition rows for this (book_edition_id) so re-runs
    # don't accumulate stale state. Easier than ON CONFLICT for this volume.
    session.execute(
        delete(ProductEdition).where(
            ProductEdition.book_edition_id == book_edition_id
        )
    )
    session.execute(pg_insert(ProductEdition).values(edition_payload))
    session.flush()
    return len(edition_payload)


def _insert_rip_offers(
    session: Session,
    book_edition_id: UUID,
    main_rows: list[dict[str, Any]],
) -> int:
    """Insert one rip_offers row per product_edition that carries RIP data."""
    # Look up product_edition_id for every (code) in this edition.
    ed_lookup = dict(
        session.execute(
            select(Product.code, ProductEdition.id)
            .join(Product, Product.id == ProductEdition.product_id)
            .where(ProductEdition.book_edition_id == book_edition_id)
        ).all()
    )

    payload: list[dict[str, Any]] = []
    seen_pe_ids: set[UUID] = set()
    for r in main_rows:
        save = _to_decimal(r.get("rip_save_amount"))
        tier = r.get("rip_tier")
        if save is None or tier is None:
            continue
        pe_id = ed_lookup.get(r.get("code"))
        if pe_id is None or pe_id in seen_pe_ids:
            continue
        tier_cases = _tier_to_cases(tier) or 1
        payload.append(
            {
                "product_edition_id": pe_id,
                "tier": tier,
                "tier_cases": tier_cases,
                "save_amount": save,
                "case_price": _to_decimal(r.get("rip_case_price")),
                "btl_price": _to_decimal(r.get("rip_btl_price")),
            }
        )
        seen_pe_ids.add(pe_id)
    if not payload:
        return 0
    session.execute(
        delete(RipOffer).where(RipOffer.product_edition_id.in_(seen_pe_ids))
    )
    session.execute(pg_insert(RipOffer).values(payload))
    return len(payload)


def _build_product_index(
    session: Session,
    distributor_id: UUID,
) -> list[tuple[UUID, str, str | None, str | None]]:
    """Pull (product_id, code, latest description, latest size) for fuzzy matching."""
    rows = session.execute(
        select(
            Product.id,
            Product.code,
            ProductEdition.description,
            ProductEdition.size,
        )
        .join(ProductEdition, ProductEdition.product_id == Product.id)
        .where(Product.distributor_id == distributor_id)
    ).all()
    # Dedupe to latest description per product (any order is fine for matching).
    by_pid: dict[UUID, tuple[UUID, str, str | None, str | None]] = {}
    for pid, code, desc, size in rows:
        by_pid[pid] = (pid, code, desc, size)
    return list(by_pid.values())


def _insert_partials_pricing(
    session: Session,
    book_edition_id: UUID,
    rows: list[dict[str, Any]],
    matcher: FuzzyProductMatcher,
) -> tuple[int, int]:
    session.execute(
        delete(PartialsPricing).where(PartialsPricing.book_edition_id == book_edition_id)
    )
    payload: list[dict[str, Any]] = []
    lc_count = 0
    for r in rows:
        match = matcher.match(
            description=r.get("description"),
            candidate_code=r.get("product_number"),
        )
        payload.append(
            {
                "book_edition_id": book_edition_id,
                "description": r.get("description"),
                "product_number": r.get("product_number"),
                "start_date": r.get("start_date"),
                "end_date": r.get("end_date"),
                "best_case_price": _to_decimal(r.get("best_case_price")),
                "best_case_tier": r.get("best_case_tier"),
                "best_btl_price": _to_decimal(r.get("best_bottle_price")),
                "linked_product_id": match.product_id,
                "match_confidence": match.confidence,
            }
        )
        if match.product_id is not None and not match.is_confident:
            lc_count += 1
    if payload:
        session.execute(pg_insert(PartialsPricing).values(payload))
    if lc_count:
        _record_low_confidence(
            session, book_edition_id, "partials_pricing", payload, matcher.min_confidence
        )
    return len(payload), lc_count


def _insert_partials_rips(
    session: Session,
    book_edition_id: UUID,
    rows: list[dict[str, Any]],
    matcher: FuzzyProductMatcher,
) -> tuple[int, int]:
    session.execute(
        delete(PartialsRip).where(PartialsRip.book_edition_id == book_edition_id)
    )
    payload: list[dict[str, Any]] = []
    lc_count = 0
    for r in rows:
        match = matcher.match(
            description=r.get("description"),
            size=r.get("size"),
        )
        payload.append(
            {
                "book_edition_id": book_edition_id,
                "description": r.get("description"),
                "size": r.get("size"),
                "start_date": r.get("start_date"),
                "end_date": r.get("end_date"),
                "tier": r.get("tier"),
                "rip_price": _to_decimal(r.get("rip_price")),
                "rip_raw": r.get("rip_raw"),
                "linked_product_id": match.product_id,
                "match_confidence": match.confidence,
            }
        )
        if match.product_id is not None and not match.is_confident:
            lc_count += 1
    if payload:
        session.execute(pg_insert(PartialsRip).values(payload))
    if lc_count:
        _record_low_confidence(
            session, book_edition_id, "partials_rips", payload, matcher.min_confidence
        )
    return len(payload), lc_count


def _insert_inventory_reduction(
    session: Session,
    book_edition_id: UUID,
    rows: list[dict[str, Any]],
    matcher: FuzzyProductMatcher,
) -> int:
    session.execute(
        delete(InventoryReduction).where(
            InventoryReduction.book_edition_id == book_edition_id
        )
    )
    payload: list[dict[str, Any]] = []
    for r in rows:
        match = matcher.match(
            description=r.get("description"),
            size=r.get("size"),
            candidate_code=r.get("product_code"),
        )
        if match.product_id is None:
            continue
        payload.append(
            {
                "book_edition_id": book_edition_id,
                "product_id": match.product_id,
                "subcategory": r.get("subcategory"),
                "description": r.get("description"),
                "size": r.get("size"),
                "pack": r.get("pack"),
                "original_case": _to_decimal(r.get("original_case")),
                "original_bottle": _to_decimal(r.get("original_bottle")),
                "best_case": _to_decimal(r.get("best_case")),
                "best_bottle": _to_decimal(r.get("best_bottle")),
                "case_save": _to_decimal(r.get("case_save")),
                "bottle_save": _to_decimal(r.get("bottle_save")),
            }
        )
    if payload:
        # Deduplicate within payload by (book_edition_id, product_id) so the
        # uq_inventory_reduction_edition_product constraint isn't violated by
        # the rare same-code-twice-in-the-IR-section case.
        seen: set[UUID] = set()
        deduped = []
        for p in payload:
            if p["product_id"] in seen:
                continue
            seen.add(p["product_id"])
            deduped.append(p)
        session.execute(pg_insert(InventoryReduction).values(deduped))
        return len(deduped)
    return 0


def _insert_combos(
    session: Session,
    book_edition_id: UUID,
    rows: list[dict[str, Any]],
) -> int:
    session.execute(
        delete(Combo).where(Combo.book_edition_id == book_edition_id)
    )
    payload: list[dict[str, Any]] = []
    seen_skus: set[str] = set()
    for r in rows:
        sku = r.get("sku")
        if not sku or sku in seen_skus:
            continue
        seen_skus.add(sku)
        payload.append(
            {
                "book_edition_id": book_edition_id,
                "sku": sku,
                "subcategory": r.get("subcategory"),
                "item_code": r.get("item_code"),
                "contains": r.get("contains"),
                "front_line_price": _to_decimal(r.get("front_line_price")),
            }
        )
    if payload:
        session.execute(pg_insert(Combo).values(payload))
    return len(payload)


def _insert_kegs(
    session: Session,
    book_edition_id: UUID,
    rows: list[dict[str, Any]],
    matcher: FuzzyProductMatcher,
) -> int:
    session.execute(
        delete(KegListEntry).where(KegListEntry.book_edition_id == book_edition_id)
    )
    payload: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    for r in rows:
        abg_code = r.get("abg_code")
        if not abg_code or abg_code in seen_codes:
            continue
        seen_codes.add(abg_code)
        match = matcher.match(description=r.get("description"), size=r.get("size"))
        payload.append(
            {
                "book_edition_id": book_edition_id,
                "type": r.get("type"),
                "abg_code": abg_code,
                "description": r.get("description"),
                "size": r.get("size"),
                "best_keg_price": _to_decimal(r.get("best_keg_price")),
                "value_per_750ml": _to_decimal(r.get("value_per_750ml")),
                "best_btl_reg": _to_decimal(r.get("best_btl_reg")),
                "per_ounce_estimate": _to_decimal(r.get("per_ounce_estimate")),
                "in_stock": bool(r.get("in_stock", False)),
                "linked_product_id": match.product_id if match.is_confident else None,
            }
        )
    if payload:
        session.execute(pg_insert(KegListEntry).values(payload))
    return len(payload)


def _record_low_confidence(
    session: Session,
    book_edition_id: UUID,
    source_table: str,
    payload: list[dict[str, Any]],
    threshold: float,
) -> None:
    """Snapshot low-confidence fuzzy hits into the review queue."""
    lc_rows: list[dict[str, Any]] = []
    for p in payload:
        conf = p.get("match_confidence")
        pid = p.get("linked_product_id")
        if pid is None or conf is None or conf >= threshold:
            continue
        lc_rows.append(
            {
                "book_edition_id": book_edition_id,
                "source_table": source_table,
                "source_id": p.get("source_id") or pid,  # placeholder
                "candidate_product_id": pid,
                "confidence": conf,
                "payload": {k: str(v) for k, v in p.items()
                            if k in ("description", "size", "product_number")},
            }
        )
    if lc_rows:
        session.execute(pg_insert(LowConfidenceMatch).values(lc_rows))


def _to_decimal(v):
    """Convert scraper string/float to Decimal-safe value; let SQLAlchemy cast."""
    if v is None or v == "":
        return None
    if isinstance(v, str):
        # Strip stray spaces or trailing $ symbols.
        v = v.strip().lstrip("$").replace(",", "")
        try:
            return float(v)
        except ValueError:
            return None
    return v
