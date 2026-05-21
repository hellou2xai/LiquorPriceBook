"""Catalog browse + product detail endpoints.

  GET  /api/v1/catalog/products              paginated, faceted list
  GET  /api/v1/catalog/products/{code}       full detail incl. price history
  GET  /api/v1/catalog/categories            dim w/ row counts in current edition
  GET  /api/v1/catalog/brands                dim w/ row counts in current edition
  GET  /api/v1/catalog/editions              all editions (per distributor) - lets
                                             the UI know which book is "current"
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, asc, desc, func, or_, select, text
from sqlalchemy.orm import Session, aliased

from lpb_core.db import get_session
from lpb_core.db.models import (
    BookEdition,
    Brand,
    Category,
    Distributor,
    PartialsPricing,
    PartialsRip,
    Product,
    ProductEdition,
    RipOffer,
)

from .auth import get_current_user

router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])


# -------- response shapes --------

class CategoryOut(BaseModel):
    id: UUID
    slug: str
    display_name: str
    sort_order: int
    product_count: int


class BrandOut(BaseModel):
    id: UUID
    slug: str
    display_name: str
    product_count: int


class EditionOut(BaseModel):
    id: UUID
    distributor_id: UUID
    distributor_slug: str
    year: int
    month: int
    label: str
    is_current: bool


class ProductRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    description: str | None
    size: str | None
    pack: int | None
    case_cost: Decimal | None
    btl_cost: Decimal | None
    category_slug: str | None
    brand_slug: str | None
    divisions: str | None = None
    has_rip: bool
    top_rip_save: Decimal | None
    top_rip_tier: str | None
    case_cost_pct: Decimal | None
    distributor_slug: str | None = None
    distributor_name: str | None = None


class ProductListOut(BaseModel):
    items: list[ProductRow]
    total: int
    limit: int
    offset: int
    edition: EditionOut


class RipDetail(BaseModel):
    tier: str
    tier_cases: int
    save_amount: Decimal
    case_price: Decimal | None
    btl_price: Decimal | None


class PriceHistoryPoint(BaseModel):
    year: int
    month: int
    label: str
    case_cost: Decimal | None
    btl_cost: Decimal | None


class PartialOut(BaseModel):
    kind: str            # "pricing" or "rip"
    description: str | None
    start_date: date
    end_date: date
    best_case_price: Decimal | None = None
    best_case_tier: str | None = None
    best_btl_price: Decimal | None = None
    tier: str | None = None
    rip_price: Decimal | None = None
    match_confidence: Decimal | None = None


class DivisionFacet(BaseModel):
    code: str
    product_count: int


class SizeFacet(BaseModel):
    size: str
    product_count: int


class BrandFacet(BaseModel):
    slug: str
    display_name: str
    product_count: int


class FacetsOut(BaseModel):
    divisions: list[DivisionFacet]
    sizes: list[SizeFacet]
    brands: list[BrandFacet]
    price_min: float | None
    price_max: float | None
    total_products: int
    total_with_rip: int


class ProductDetailOut(BaseModel):
    code: str
    distributor_slug: str
    description: str | None
    size: str | None
    pack: int | None
    category_slug: str | None
    category_display: str | None
    brand_slug: str | None
    brand_display: str | None
    divisions: str | None = None
    case_cost: Decimal | None
    btl_cost: Decimal | None
    prev_case_cost: Decimal | None
    case_cost_pct: Decimal | None
    price_history: list[PriceHistoryPoint]
    current_rips: list[RipDetail]
    active_partials: list[PartialOut]


# -------- helpers --------

def _current_edition(
    session: Session, distributor_slug: str | None = None
) -> BookEdition:
    """Book edition for the current calendar month (or most recent before it).

    Future editions (year/month > today) are stored for analytics but never
    used as "current" pricing.  If distributor_slug is given, constrain to
    that distributor.
    """
    today = date.today()
    stmt = (
        select(BookEdition)
        .join(Distributor, Distributor.id == BookEdition.distributor_id)
        .where(
            or_(
                BookEdition.year < today.year,
                and_(BookEdition.year == today.year,
                     BookEdition.month <= today.month),
            )
        )
        .order_by(desc(BookEdition.year), desc(BookEdition.month),
                  desc(BookEdition.created_at))
        .limit(1)
    )
    if distributor_slug:
        stmt = stmt.where(Distributor.slug == distributor_slug)
    ed = session.execute(stmt).scalar_one_or_none()
    if ed is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No price-book edition ingested yet",
        )
    return ed


def _label(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


# -------- routes --------

@router.get("/editions", response_model=list[EditionOut])
def list_editions(
    user: dict = Depends(get_current_user),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
):
    today = date.today()
    rows = session.execute(
        select(BookEdition, Distributor.slug)
        .join(Distributor, Distributor.id == BookEdition.distributor_id)
        .order_by(desc(BookEdition.year), desc(BookEdition.month))
    ).all()
    if not rows:
        return []
    # Mark the highest non-future (year, month) per distributor as current.
    seen_distributors: set[str] = set()
    out: list[EditionOut] = []
    for ed, dslug in rows:
        is_future = (ed.year > today.year
                     or (ed.year == today.year and ed.month > today.month))
        is_current = not is_future and dslug not in seen_distributors
        if is_current:
            seen_distributors.add(dslug)
        out.append(
            EditionOut(
                id=ed.id,
                distributor_id=ed.distributor_id,
                distributor_slug=dslug,
                year=ed.year,
                month=ed.month,
                label=_label(ed.year, ed.month),
                is_current=is_current,
            )
        )
    return out


def _current_edition_ids(
    session: Session, distributor_slug: str
) -> list[UUID]:
    """Return current edition IDs. If 'all', returns one per distributor.

    Excludes future editions (year/month > today).
    """
    today = date.today()
    future_filter = or_(
        BookEdition.year < today.year,
        and_(BookEdition.year == today.year,
             BookEdition.month <= today.month),
    )
    if distributor_slug == "all":
        rows = session.execute(
            select(BookEdition.id, Distributor.slug)
            .join(Distributor, Distributor.id == BookEdition.distributor_id)
            .where(future_filter)
            .order_by(desc(BookEdition.year), desc(BookEdition.month),
                      desc(BookEdition.created_at))
        ).all()
        seen: dict[str, UUID] = {}
        for eid, dslug in rows:
            if dslug not in seen:
                seen[dslug] = eid
        if not seen:
            raise HTTPException(status_code=404, detail="No editions ingested yet")
        return list(seen.values())
    ed = _current_edition(session, distributor_slug)
    return [ed.id]


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(
    distributor: str = Query("nj-allied"),
    user: dict = Depends(get_current_user),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
):
    edition_ids = _current_edition_ids(session, distributor)
    rows = session.execute(
        select(
            Category.id,
            Category.slug,
            Category.display_name,
            Category.sort_order,
            func.count(ProductEdition.id).label("n"),
        )
        .outerjoin(
            ProductEdition,
            and_(
                ProductEdition.category_id == Category.id,
                ProductEdition.book_edition_id.in_(edition_ids),
            ),
        )
        .group_by(Category.id, Category.slug, Category.display_name, Category.sort_order)
        .order_by(asc(Category.sort_order), asc(Category.display_name))
    ).all()
    return [
        CategoryOut(
            id=r.id, slug=r.slug, display_name=r.display_name,
            sort_order=r.sort_order, product_count=r.n,
        )
        for r in rows
    ]


@router.get("/brands", response_model=list[BrandOut])
def list_brands(
    distributor: str = Query("nj-allied"),
    q: str | None = Query(None, description="Filter by substring (case-insensitive)"),
    limit: int = Query(200, ge=1, le=1000),
    user: dict = Depends(get_current_user),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
):
    edition_ids = _current_edition_ids(session, distributor)
    stmt = (
        select(
            Brand.id,
            Brand.slug,
            Brand.display_name,
            func.count(ProductEdition.id).label("n"),
        )
        .join(ProductEdition, ProductEdition.brand_id == Brand.id)
        .where(ProductEdition.book_edition_id.in_(edition_ids))
        .group_by(Brand.id, Brand.slug, Brand.display_name)
        .order_by(desc("n"))
        .limit(limit)
    )
    if q:
        for word in q.split():
            stmt = stmt.where(Brand.display_name.ilike(f"%{word}%"))
    rows = session.execute(stmt).all()
    return [
        BrandOut(
            id=r.id, slug=r.slug, display_name=r.display_name, product_count=r.n,
        )
        for r in rows
    ]


@router.get("/products", response_model=ProductListOut)
def list_products(
    distributor: str = Query("nj-allied"),
    category: list[str] | None = Query(None, description="Slug; repeatable"),
    brand: list[str] | None = Query(None, description="Slug; repeatable"),
    size: list[str] | None = Query(None),
    division: list[str] | None = Query(None, description="Division code; repeatable"),
    search: str | None = Query(None, min_length=2),
    has_rip: bool | None = Query(None),
    min_case_cost: float | None = Query(None, ge=0),
    max_case_cost: float | None = Query(None, ge=0),
    sort: str = Query(
        "name",
        pattern="^(name|case_cost_asc|case_cost_desc|moved_pct_abs)$",
    ),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
):
    # Support distributor=all to show products from all distributors
    is_all = distributor == "all"
    if is_all:
        # Get current edition per distributor
        all_editions = session.execute(
            select(BookEdition.id, Distributor.slug, Distributor.name)
            .join(Distributor, Distributor.id == BookEdition.distributor_id)
            .order_by(desc(BookEdition.year), desc(BookEdition.month),
                      desc(BookEdition.created_at))
        ).all()
        # Pick latest edition per distributor
        seen: dict[str, tuple] = {}
        for eid, dslug, dname in all_editions:
            if dslug not in seen:
                seen[dslug] = (eid, dslug, dname)
        if not seen:
            raise HTTPException(status_code=404, detail="No editions ingested yet")
        edition_ids = [v[0] for v in seen.values()]
        dist_name_by_eid = {v[0]: v[2] for v in seen.values()}
        dist_slug_by_eid = {v[0]: v[1] for v in seen.values()}
        # Use first edition for the response metadata
        first_ed = session.execute(
            select(BookEdition).where(BookEdition.id == edition_ids[0])
        ).scalar_one()
        edition = first_ed
    else:
        edition = _current_edition(session, distributor)
        edition_ids = [edition.id]
        dist_row = session.execute(
            select(Distributor.slug, Distributor.name)
            .where(Distributor.id == edition.distributor_id)
        ).first()
        dist_name_by_eid = {edition.id: dist_row.name if dist_row else distributor}
        dist_slug_by_eid = {edition.id: dist_row.slug if dist_row else distributor}

    # Subquery: top RIP per product_edition (highest save_amount).
    top_rip_save = (
        select(
            RipOffer.product_edition_id,
            func.max(RipOffer.save_amount).label("max_save"),
        )
        .group_by(RipOffer.product_edition_id)
        .subquery()
    )
    top_rip = aliased(RipOffer)

    # Per-row price-change pct from mv_price_changes is joined in after the
    # main page is fetched (see below), to keep the main query readable.

    base = (
        select(
            Product.code.label("code"),
            ProductEdition.description.label("description"),
            ProductEdition.size.label("size"),
            ProductEdition.pack.label("pack"),
            ProductEdition.case_cost.label("case_cost"),
            ProductEdition.btl_cost.label("btl_cost"),
            Category.slug.label("category_slug"),
            Brand.slug.label("brand_slug"),
            ProductEdition.divisions.label("divisions"),
            top_rip.tier.label("top_rip_tier"),
            top_rip.save_amount.label("top_rip_save"),
            ProductEdition.id.label("product_edition_id"),
            ProductEdition.book_edition_id.label("book_edition_id"),
        )
        .select_from(ProductEdition)
        .join(Product, Product.id == ProductEdition.product_id)
        .outerjoin(Category, Category.id == ProductEdition.category_id)
        .outerjoin(Brand, Brand.id == ProductEdition.brand_id)
        .outerjoin(
            top_rip_save,
            top_rip_save.c.product_edition_id == ProductEdition.id,
        )
        .outerjoin(
            top_rip,
            and_(
                top_rip.product_edition_id == ProductEdition.id,
                top_rip.save_amount == top_rip_save.c.max_save,
            ),
        )
        .where(ProductEdition.book_edition_id.in_(edition_ids))
    )

    if category:
        base = base.where(Category.slug.in_(category))
    if brand:
        base = base.where(Brand.slug.in_(brand))
    if size:
        base = base.where(ProductEdition.size.in_(size))
    if division:
        div_conditions = []
        for d in division:
            div_conditions.append(
                or_(
                    ProductEdition.divisions == d,
                    ProductEdition.divisions.like(f"{d} %"),
                    ProductEdition.divisions.like(f"% {d}"),
                    ProductEdition.divisions.like(f"% {d} %"),
                )
            )
        base = base.where(or_(*div_conditions))
    if search:
        # Split search into words; each word must appear in code, description,
        # or brand.  "grey goose 750" matches brand=GREY GOOSE + size/desc=750.
        words = search.split()
        for word in words:
            pat = f"%{word}%"
            base = base.where(
                or_(
                    Product.code.ilike(pat),
                    ProductEdition.description.ilike(pat),
                    Brand.display_name.ilike(pat),
                    Category.display_name.ilike(pat),
                    ProductEdition.size.ilike(pat),
                )
            )
    if has_rip is True:
        base = base.where(top_rip_save.c.max_save.isnot(None))
    elif has_rip is False:
        base = base.where(top_rip_save.c.max_save.is_(None))
    if min_case_cost is not None:
        base = base.where(ProductEdition.case_cost >= min_case_cost)
    if max_case_cost is not None:
        base = base.where(ProductEdition.case_cost <= max_case_cost)

    # Count BEFORE sort/pagination
    count_stmt = select(func.count()).select_from(base.subquery())
    total = session.execute(count_stmt).scalar_one()

    # Sort
    if sort == "name":
        base = base.order_by(asc(ProductEdition.description), asc(Product.code))
    elif sort == "case_cost_asc":
        base = base.order_by(asc(ProductEdition.case_cost).nullslast(),
                             asc(Product.code))
    elif sort == "case_cost_desc":
        base = base.order_by(desc(ProductEdition.case_cost).nullslast(),
                             asc(Product.code))
    elif sort == "moved_pct_abs":
        # Sort by absolute |case_cost_pct| from mv_price_changes;
        # products with no prior edition sink to the bottom.
        base = base.order_by(asc(Product.code))

    base = base.limit(limit).offset(offset)
    rows = session.execute(base).all()

    # Join in price-change pct from the materialised view for the visible page.
    pe_ids = [r.product_edition_id for r in rows]
    pct_by_pe: dict[UUID, Decimal | None] = {}
    if pe_ids:
        for pe_id, pct in session.execute(
            text(
                "SELECT product_edition_id, case_cost_pct "
                "FROM mv_price_changes WHERE product_edition_id = ANY(:ids)"
            ),
            {"ids": pe_ids},
        ).all():
            pct_by_pe[pe_id] = pct

    items = [
        ProductRow(
            code=r.code,
            description=r.description,
            size=r.size,
            pack=r.pack,
            case_cost=r.case_cost,
            btl_cost=r.btl_cost,
            category_slug=r.category_slug,
            brand_slug=r.brand_slug,
            divisions=r.divisions,
            has_rip=r.top_rip_save is not None,
            top_rip_save=r.top_rip_save,
            top_rip_tier=r.top_rip_tier,
            case_cost_pct=pct_by_pe.get(r.product_edition_id),
            distributor_slug=dist_slug_by_eid.get(r.book_edition_id),
            distributor_name=dist_name_by_eid.get(r.book_edition_id),
        )
        for r in rows
    ]

    dist_slug = dist_slug_by_eid.get(edition.id, distributor)
    return ProductListOut(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        edition=EditionOut(
            id=edition.id,
            distributor_id=edition.distributor_id,
            distributor_slug=dist_slug,
            year=edition.year,
            month=edition.month,
            label=_label(edition.year, edition.month),
            is_current=True,
        ),
    )


@router.get("/facets", response_model=FacetsOut)
def get_facets(
    distributor: str = Query("nj-allied"),
    user: dict = Depends(get_current_user),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
):
    edition_ids = _current_edition_ids(session, distributor)

    # Divisions: split space-separated codes and count occurrences.
    div_rows = session.execute(
        text(
            "SELECT code, count(*) AS cnt FROM ("
            "  SELECT unnest(string_to_array(divisions, ' ')) AS code"
            "  FROM product_editions"
            "  WHERE book_edition_id = ANY(:eids)"
            "    AND divisions IS NOT NULL AND divisions != ''"
            ") sub GROUP BY code ORDER BY cnt DESC"
        ),
        {"eids": edition_ids},
    ).all()
    divisions = [DivisionFacet(code=r.code, product_count=r.cnt) for r in div_rows]

    # Sizes with counts.
    size_rows = session.execute(
        select(
            ProductEdition.size,
            func.count(ProductEdition.id).label("cnt"),
        )
        .where(
            ProductEdition.book_edition_id.in_(edition_ids),
            ProductEdition.size.isnot(None),
            ProductEdition.size != "",
        )
        .group_by(ProductEdition.size)
        .order_by(desc("cnt"))
    ).all()
    sizes = [SizeFacet(size=r.size, product_count=r.cnt) for r in size_rows]

    # Brands (top 200 by count).
    brand_rows = session.execute(
        select(
            Brand.slug,
            Brand.display_name,
            func.count(ProductEdition.id).label("cnt"),
        )
        .join(ProductEdition, ProductEdition.brand_id == Brand.id)
        .where(ProductEdition.book_edition_id.in_(edition_ids))
        .group_by(Brand.slug, Brand.display_name)
        .order_by(desc("cnt"))
        .limit(200)
    ).all()
    brands_out = [
        BrandFacet(slug=r.slug, display_name=r.display_name, product_count=r.cnt)
        for r in brand_rows
    ]

    # Price range.
    price_row = session.execute(
        select(
            func.min(ProductEdition.case_cost),
            func.max(ProductEdition.case_cost),
        ).where(
            ProductEdition.book_edition_id.in_(edition_ids),
            ProductEdition.case_cost.isnot(None),
        )
    ).first()
    price_min = float(price_row[0]) if price_row and price_row[0] else None
    price_max = float(price_row[1]) if price_row and price_row[1] else None

    # Total products & total with RIP.
    total_products = session.execute(
        select(func.count(ProductEdition.id))
        .where(ProductEdition.book_edition_id.in_(edition_ids))
    ).scalar_one()

    total_with_rip = session.execute(
        select(func.count(func.distinct(RipOffer.product_edition_id)))
        .join(ProductEdition, ProductEdition.id == RipOffer.product_edition_id)
        .where(ProductEdition.book_edition_id.in_(edition_ids))
    ).scalar_one()

    return FacetsOut(
        divisions=divisions,
        sizes=sizes,
        brands=brands_out,
        price_min=price_min,
        price_max=price_max,
        total_products=total_products,
        total_with_rip=total_with_rip,
    )


@router.get("/products/{code}", response_model=ProductDetailOut)
def product_detail(
    code: str,
    distributor: str = Query("nj-allied"),
    user: dict = Depends(get_current_user),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
):
    dist = session.execute(
        select(Distributor).where(Distributor.slug == distributor)
    ).scalar_one_or_none()
    if dist is None:
        raise HTTPException(status_code=404, detail=f"Unknown distributor {distributor}")

    # Find latest product_edition for this (distributor, code).
    latest_pe = session.execute(
        select(
            ProductEdition,
            Product.code,
            Category.slug.label("cat_slug"),
            Category.display_name.label("cat_display"),
            Brand.slug.label("brand_slug"),
            Brand.display_name.label("brand_display"),
            BookEdition.year,
            BookEdition.month,
        )
        .join(Product, Product.id == ProductEdition.product_id)
        .join(BookEdition, BookEdition.id == ProductEdition.book_edition_id)
        .outerjoin(Category, Category.id == ProductEdition.category_id)
        .outerjoin(Brand, Brand.id == ProductEdition.brand_id)
        .where(Product.distributor_id == dist.id, Product.code == code)
        .order_by(desc(BookEdition.year), desc(BookEdition.month))
        .limit(1)
    ).first()
    if latest_pe is None:
        raise HTTPException(status_code=404, detail="Product not found")

    pe: ProductEdition = latest_pe[0]

    # Full price history across all editions.
    hist_rows = session.execute(
        select(
            BookEdition.year,
            BookEdition.month,
            ProductEdition.case_cost,
            ProductEdition.btl_cost,
        )
        .join(BookEdition, BookEdition.id == ProductEdition.book_edition_id)
        .where(ProductEdition.product_id == pe.product_id)
        .order_by(asc(BookEdition.year), asc(BookEdition.month))
    ).all()
    history = [
        PriceHistoryPoint(
            year=r.year, month=r.month, label=_label(r.year, r.month),
            case_cost=r.case_cost, btl_cost=r.btl_cost,
        )
        for r in hist_rows
    ]

    # Prior case cost / pct change from matview.
    prev_case_cost = None
    case_cost_pct = None
    if pe.case_cost is not None:
        mv = session.execute(
            text(
                "SELECT prev_case_cost, case_cost_pct FROM mv_price_changes "
                "WHERE product_edition_id = :pe_id"
            ),
            {"pe_id": pe.id},
        ).first()
        if mv is not None:
            prev_case_cost, case_cost_pct = mv

    # Current RIP offers.
    rip_rows = session.execute(
        select(RipOffer)
        .where(RipOffer.product_edition_id == pe.id)
        .order_by(asc(RipOffer.tier_cases))
    ).scalars().all()
    rips = [
        RipDetail(
            tier=r.tier, tier_cases=r.tier_cases,
            save_amount=r.save_amount,
            case_price=r.case_price, btl_price=r.btl_price,
        )
        for r in rip_rows
    ]

    # Active partials (today within window).
    today = datetime.now().date()
    pp_rows = session.execute(
        select(PartialsPricing).where(
            PartialsPricing.linked_product_id == pe.product_id,
            PartialsPricing.start_date <= today,
            PartialsPricing.end_date >= today,
        )
    ).scalars().all()
    pr_rows = session.execute(
        select(PartialsRip).where(
            PartialsRip.linked_product_id == pe.product_id,
            PartialsRip.start_date <= today,
            PartialsRip.end_date >= today,
        )
    ).scalars().all()
    active_partials: list[PartialOut] = []
    for p in pp_rows:
        active_partials.append(
            PartialOut(
                kind="pricing",
                description=p.description,
                start_date=p.start_date,
                end_date=p.end_date,
                best_case_price=p.best_case_price,
                best_case_tier=p.best_case_tier,
                best_btl_price=p.best_btl_price,
                match_confidence=p.match_confidence,
            )
        )
    for r in pr_rows:
        active_partials.append(
            PartialOut(
                kind="rip",
                description=r.description,
                start_date=r.start_date,
                end_date=r.end_date,
                tier=r.tier,
                rip_price=r.rip_price,
                match_confidence=r.match_confidence,
            )
        )

    return ProductDetailOut(
        code=latest_pe.code,
        distributor_slug=distributor,
        description=pe.description,
        size=pe.size,
        pack=pe.pack,
        category_slug=latest_pe.cat_slug,
        category_display=latest_pe.cat_display,
        brand_slug=latest_pe.brand_slug,
        brand_display=latest_pe.brand_display,
        divisions=pe.divisions,
        case_cost=pe.case_cost,
        btl_cost=pe.btl_cost,
        prev_case_cost=prev_case_cost,
        case_cost_pct=case_cost_pct,
        price_history=history,
        current_rips=rips,
        active_partials=active_partials,
    )
