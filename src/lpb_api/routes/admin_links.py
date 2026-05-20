"""Admin endpoint for cross-distributor product linking.

  POST /api/v1/admin/link-products    accept fuzzy-match results and create
                                      product_links rows + set link_id on
                                      both Product records.

Called by ``scripts/link_products.py`` after it computes fuzzy matches
locally from the catalog API.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from lpb_core.db import get_session
from lpb_core.db.models import Brand, Category, Distributor, Product, ProductLink

from .auth import get_current_user

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


# ---------- request / response shapes ------------------------------------

class LinkItem(BaseModel):
    allied_code: str
    fedway_code: str
    confidence: float
    canonical_description: str | None = None
    size: str | None = None
    pack: int | None = None
    brand_slug: str | None = None
    category_slug: str | None = None


class LinkRequest(BaseModel):
    links: list[LinkItem]


class LinkResponse(BaseModel):
    created: int
    updated: int
    skipped: int
    errors: list[str]


# ---------- helpers -------------------------------------------------------

def _lookup_distributor(session: Session, slug: str) -> UUID:
    dist = session.execute(
        select(Distributor.id).where(Distributor.slug == slug)
    ).scalar_one_or_none()
    if dist is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Distributor '{slug}' not found",
        )
    return dist


def _find_product(session: Session, distributor_id: UUID, code: str) -> Product | None:
    return session.execute(
        select(Product).where(
            Product.distributor_id == distributor_id,
            Product.code == code,
        )
    ).scalar_one_or_none()


# ---------- route ---------------------------------------------------------

@router.post("/link-products", response_model=LinkResponse)
def create_product_links(
    body: LinkRequest,
    user: dict = Depends(get_current_user),  # noqa: B008
    session: Session = Depends(get_session),  # noqa: B008
):
    """Accept fuzzy-match results and create/update product_links.

    For each link in the request:
    1. Look up the Allied and Fedway Product rows by (distributor, code).
    2. Resolve brand_slug / category_slug to IDs.
    3. If both products already share the same link_id, skip.
    4. Otherwise create a ProductLink and set link_id on both products.
    """
    allied_dist_id = _lookup_distributor(session, "nj-allied")
    fedway_dist_id = _lookup_distributor(session, "nj-fedway")

    # Pre-load brand and category lookups
    brand_cache: dict[str, UUID] = {}
    category_cache: dict[str, UUID] = {}

    def _brand_id(slug: str | None) -> UUID | None:
        if not slug:
            return None
        if slug not in brand_cache:
            bid = session.execute(
                select(Brand.id).where(Brand.slug == slug)
            ).scalar_one_or_none()
            brand_cache[slug] = bid  # type: ignore[assignment]
        return brand_cache.get(slug)

    def _category_id(slug: str | None) -> UUID | None:
        if not slug:
            return None
        if slug not in category_cache:
            cid = session.execute(
                select(Category.id).where(Category.slug == slug)
            ).scalar_one_or_none()
            category_cache[slug] = cid  # type: ignore[assignment]
        return category_cache.get(slug)

    created = 0
    updated = 0
    skipped = 0
    errors: list[str] = []

    for item in body.links:
        allied_product = _find_product(session, allied_dist_id, item.allied_code)
        fedway_product = _find_product(session, fedway_dist_id, item.fedway_code)

        if allied_product is None:
            errors.append(f"Allied product {item.allied_code} not found")
            continue
        if fedway_product is None:
            errors.append(f"Fedway product {item.fedway_code} not found")
            continue

        # If both already share the same non-null link_id, skip
        if (
            allied_product.link_id is not None
            and allied_product.link_id == fedway_product.link_id
        ):
            skipped += 1
            continue

        # If one already has a link_id, reuse that link and attach the other
        existing_link_id = allied_product.link_id or fedway_product.link_id

        if existing_link_id is not None:
            # Update the existing link's metadata
            existing_link = session.get(ProductLink, existing_link_id)
            if existing_link:
                existing_link.canonical_description = item.canonical_description
                existing_link.match_method = "auto"
            allied_product.link_id = existing_link_id
            fedway_product.link_id = existing_link_id
            updated += 1
        else:
            # Create a new ProductLink
            brand_id = _brand_id(item.brand_slug)
            cat_id = _category_id(item.category_slug)

            link = ProductLink(
                canonical_description=item.canonical_description,
                size=item.size,
                pack=item.pack,
                brand_id=brand_id,
                category_id=cat_id,
                match_method="auto",
            )
            session.add(link)
            session.flush()  # get the generated id

            allied_product.link_id = link.id
            fedway_product.link_id = link.id
            created += 1

    session.commit()

    log.info(
        "link-products: created=%d updated=%d skipped=%d errors=%d",
        created, updated, skipped, len(errors),
    )
    if errors:
        log.warning("link-products errors (first 10): %s", errors[:10])

    return LinkResponse(
        created=created,
        updated=updated,
        skipped=skipped,
        errors=errors[:50],  # cap error list size
    )
