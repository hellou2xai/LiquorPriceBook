"""SQLAlchemy ORM models for LiquorPriceBook.

Schema overview
---------------
Dims:        distributors, categories, brands
Catalog:     book_editions, ingest_runs, products, product_editions, rip_offers,
             partials_pricing, partials_rips, inventory_reduction, combos,
             combo_components, keg_list
Tenancy:     tenants, users, watchlists, watchlist_items, notes
Alerts:      alert_configs, alert_events
Audit:       audit_log
AI cache:    ai_verdict_cache
Match queue: low_confidence_matches

Key conventions
---------------
- UUID primary keys throughout (Postgres ``gen_random_uuid()``).
- Tenant-scoped tables carry ``tenant_id`` with an index.
- Money is ``Numeric(12, 2)``: 10 digits + 2 decimals covers $9,999,999.99
  which is well clear of any case price.
- Soft delete (``deleted_at``) on notes; hard delete elsewhere.
- ``raw_*`` columns preserve the source-of-truth scraped string alongside any
  normalised dimension FK, so we can re-run the cleaning layer without
  re-scraping the PDF.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


# ---------------------------------------------------------------------------
# Mixins
# ---------------------------------------------------------------------------
def _uuid_pk():
    return mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )


def _now():
    return mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


def _updated():
    return mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


# ===========================================================================
# DIMENSIONS
# ===========================================================================

class Distributor(Base):
    """A wholesaler we ingest price books from (Allied, Fedway, Opici, RNDC)."""

    __tablename__ = "distributors"

    id: Mapped[UUID] = _uuid_pk()
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[str] = mapped_column(
        String(2), nullable=False, default="NJ", server_default=text("'NJ'")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime] = _now()


class Category(Base):
    """Normalised category taxonomy. Raw OCR-garbled strings live in ``raw_aliases``."""

    __tablename__ = "categories"

    id: Mapped[UUID] = _uuid_pk()
    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL")
    )
    raw_aliases: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    created_at: Mapped[datetime] = _now()


class Brand(Base):
    """Brand dimension, derived from product descriptions (not ``brand_header``)."""

    __tablename__ = "brands"

    id: Mapped[UUID] = _uuid_pk()
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_aliases: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = _now()


# ===========================================================================
# CATALOG FACTS
# ===========================================================================

class BookEdition(Base):
    """One monthly price book per distributor.

    ``content_hash`` makes re-uploads idempotent.
    ``supersedes_id`` lets a corrected re-parse replace its predecessor
    without orphaning downstream watchlists/notes (those FK to ``products``,
    not ``product_editions``).
    """

    __tablename__ = "book_editions"

    id: Mapped[UUID] = _uuid_pk()
    distributor_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("distributors.id", ondelete="RESTRICT"),
        nullable=False,
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    source_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_uri: Mapped[str | None] = mapped_column(String(1024))
    supersedes_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("book_editions.id", ondelete="SET NULL"),
    )
    scraped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime] = _now()

    __table_args__ = (
        UniqueConstraint("distributor_id", "content_hash",
                         name="uq_book_editions_distributor_content_hash"),
        Index("ix_book_editions_distributor_year_month",
              "distributor_id", "year", "month"),
        CheckConstraint("month BETWEEN 1 AND 12",
                        name="month_range"),
        CheckConstraint("year BETWEEN 2020 AND 2100",
                        name="year_range"),
    )


class IngestRun(Base):
    """Provenance + replay log for each ingestion attempt."""

    __tablename__ = "ingest_runs"

    id: Mapped[UUID] = _uuid_pk()
    book_edition_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("book_editions.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default=text("'pending'")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rows_by_section: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    error: Mapped[dict | None] = mapped_column(JSONB)
    triggered_by_user_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True))
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _updated()

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','completed','failed','superseded')",
            name="status_enum",
        ),
        Index("ix_ingest_runs_status", "status"),
    )


class Product(Base):
    """Canonical product, scoped per distributor.

    The same liquid SKU from different distributors carries different pricing,
    RIP eligibility, and ordering terms - they're not the same row. Cross-
    distributor links land in ``product_links`` (v2).
    """

    __tablename__ = "products"

    id: Mapped[UUID] = _uuid_pk()
    distributor_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("distributors.id", ondelete="RESTRICT"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    first_seen_in_edition_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("book_editions.id", ondelete="SET NULL")
    )
    last_seen_in_edition_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("book_editions.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _updated()

    __table_args__ = (
        UniqueConstraint("distributor_id", "code",
                         name="uq_products_distributor_code"),
    )


class ProductEdition(Base):
    """Per-book snapshot of a product. The time-series fact table.

    One row per (product, book_edition). Holds the SKU's pricing, size, pack,
    category and brand assignment for that edition, plus the raw values from
    the scraper for traceability.
    """

    __tablename__ = "product_editions"

    id: Mapped[UUID] = _uuid_pk()
    product_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    book_edition_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("book_editions.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Normalised dims (nullable for new variants until cleaning resolves them)
    category_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL")
    )
    brand_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("brands.id", ondelete="SET NULL")
    )
    # Source-of-truth raw values from scraper
    raw_category: Mapped[str | None] = mapped_column(String(255))
    raw_brand_header: Mapped[str | None] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text)
    size: Mapped[str | None] = mapped_column(String(32))
    pack: Mapped[int | None] = mapped_column(Integer)
    # Money columns
    po_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    case_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    btl_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    best_buy_raw: Mapped[str | None] = mapped_column(String(64))
    best_rip_raw: Mapped[str | None] = mapped_column(String(128))
    # Scraper provenance
    page: Mapped[int | None] = mapped_column(Integer)
    lane: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = _now()

    __table_args__ = (
        UniqueConstraint("product_id", "book_edition_id",
                         name="uq_product_editions_product_edition"),
        Index("ix_product_editions_book_edition_id", "book_edition_id"),
        Index("ix_product_editions_category_id", "category_id"),
        Index("ix_product_editions_brand_id", "brand_id"),
        Index("ix_product_editions_case_cost", "case_cost"),
    )


class RipOffer(Base):
    """A Retail Incentive Program tier attached to a product edition.

    Per NJ ABC rules:
    - Every RIP must have a paired small-quantity tier (<=5 cases, min 1 bottle).
    - Per-RIP cap: 50 cases OR $1,000.
    - Cash rebate by cheque, not netted against invoice.
    - Cheque must arrive 30+ days post-sale.

    save_amount is the cash rebate per tier. case_price and btl_price are the
    post-rebate effective prices the scraper extracts from the "$X.XX ON nCS" annotation.
    """

    __tablename__ = "rip_offers"

    id: Mapped[UUID] = _uuid_pk()
    product_edition_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("product_editions.id", ondelete="CASCADE"),
        nullable=False,
    )
    tier: Mapped[str] = mapped_column(String(16), nullable=False)  # e.g. "1CS", "5CS"
    tier_cases: Mapped[int] = mapped_column(Integer, nullable=False)
    save_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    case_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    btl_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    created_at: Mapped[datetime] = _now()

    __table_args__ = (
        UniqueConstraint("product_edition_id", "tier",
                         name="uq_rip_offers_edition_tier"),
        CheckConstraint("tier_cases > 0", name="tier_cases_positive"),
        CheckConstraint("tier_cases <= 50", name="nj_50_case_cap"),
        CheckConstraint("save_amount >= 0 AND save_amount <= 1000",
                        name="nj_1000_dollar_cap"),
        Index("ix_rip_offers_product_edition_id", "product_edition_id"),
    )


class PartialsPricing(Base):
    """Date-bounded Web Pricing partial (from Partials/Web PRICING section).

    Has its own product_number but partials often won't FK cleanly because
    the scraper has only ``(description, product_number)`` and the
    product_number is sometimes 6 digits where catalog codes are 7. Fuzzy
    matched to ``products`` with a confidence score; low confidence enters
    the manual review queue.
    """

    __tablename__ = "partials_pricing"

    id: Mapped[UUID] = _uuid_pk()
    book_edition_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("book_editions.id", ondelete="CASCADE"),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    product_number: Mapped[str | None] = mapped_column(String(32))
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    best_case_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    best_case_tier: Mapped[str | None] = mapped_column(String(16))
    best_btl_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    linked_product_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL")
    )
    match_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    created_at: Mapped[datetime] = _now()

    __table_args__ = (
        Index("ix_partials_pricing_dates", "start_date", "end_date"),
        Index("ix_partials_pricing_linked_product", "linked_product_id"),
    )


class PartialsRip(Base):
    """Date-bounded Web RIP partial (from Partials/Web RIPS section).

    Tier rows in the source PDF can be continuation lines (e.g. CSJ CHARD
    CARNR21 6P shows 1CASE=$36, then a child row 2CASES=$90). We collapse
    those into one row each with ``tier`` populated.
    """

    __tablename__ = "partials_rips"

    id: Mapped[UUID] = _uuid_pk()
    book_edition_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("book_editions.id", ondelete="CASCADE"),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    size: Mapped[str | None] = mapped_column(String(32))
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    tier: Mapped[str | None] = mapped_column(String(16))
    rip_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    rip_raw: Mapped[str | None] = mapped_column(String(128))
    linked_product_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL")
    )
    match_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    created_at: Mapped[datetime] = _now()

    __table_args__ = (
        Index("ix_partials_rips_dates", "start_date", "end_date"),
        Index("ix_partials_rips_linked_product", "linked_product_id"),
    )


class InventoryReduction(Base):
    """Closeout / Last-Call entries. These are terminal: a product appearing
    on the closeout list is being discontinued, not promoted. The "buy now
    vs defer" recommender refuses to recommend defer on these."""

    __tablename__ = "inventory_reduction"

    id: Mapped[UUID] = _uuid_pk()
    book_edition_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("book_editions.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    subcategory: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)
    size: Mapped[str | None] = mapped_column(String(32))
    pack: Mapped[int | None] = mapped_column(Integer)
    original_case: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    original_bottle: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    best_case: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    best_bottle: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    case_save: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    bottle_save: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    first_appeared_in_edition_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("book_editions.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = _now()

    __table_args__ = (
        UniqueConstraint("book_edition_id", "product_id",
                         name="uq_inventory_reduction_edition_product"),
        Index("ix_inventory_reduction_product", "product_id"),
    )


class Combo(Base):
    """A combo SKU (multi-bottle bundle) sold at a single front-line price."""

    __tablename__ = "combos"

    id: Mapped[UUID] = _uuid_pk()
    book_edition_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("book_editions.id", ondelete="CASCADE"),
        nullable=False,
    )
    sku: Mapped[str] = mapped_column(String(32), nullable=False)
    subcategory: Mapped[str | None] = mapped_column(String(64))
    item_code: Mapped[str | None] = mapped_column(String(255))
    contains: Mapped[str | None] = mapped_column(Text)
    front_line_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    created_at: Mapped[datetime] = _now()

    __table_args__ = (
        UniqueConstraint("book_edition_id", "sku",
                         name="uq_combos_edition_sku"),
        Index("ix_combos_sku", "sku"),
    )


class ComboComponent(Base):
    """A component product inside a combo, parsed out of ``Combo.contains``."""

    __tablename__ = "combo_components"

    id: Mapped[UUID] = _uuid_pk()
    combo_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("combos.id", ondelete="CASCADE"),
        nullable=False,
    )
    linked_product_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL")
    )
    qty_cases: Mapped[int | None] = mapped_column(Integer)
    qty_bottles: Mapped[int | None] = mapped_column(Integer)
    raw_token: Mapped[str] = mapped_column(Text, nullable=False)
    match_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    created_at: Mapped[datetime] = _now()

    __table_args__ = (
        Index("ix_combo_components_combo", "combo_id"),
    )


class KegListEntry(Base):
    """Kegs live in their own table - distinct unit economics (per-ounce vs
    750ml-equivalent comparison), Deposit-vs-Disposable type that does not exist
    elsewhere, no RIP structure. Forcing them into ``products`` would pollute
    aggregates."""

    __tablename__ = "keg_list"

    id: Mapped[UUID] = _uuid_pk()
    book_edition_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("book_editions.id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(String(16), nullable=False)  # Deposit | Disposable
    abg_code: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    size: Mapped[str | None] = mapped_column(String(32))
    best_keg_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    value_per_750ml: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    best_btl_reg: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    per_ounce_estimate: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    in_stock: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    linked_product_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = _now()

    __table_args__ = (
        UniqueConstraint("book_edition_id", "abg_code",
                         name="uq_keg_list_edition_code"),
        CheckConstraint(
            "type IN ('Deposit','Disposable')",
            name="type_enum",
        ),
    )


# ===========================================================================
# TENANCY
# ===========================================================================

class Tenant(Base):
    """A retailer organisation. One Clerk organisation maps to one tenant."""

    __tablename__ = "tenants"

    id: Mapped[UUID] = _uuid_pk()
    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    clerk_org_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    plan: Mapped[str] = mapped_column(
        String(32), nullable=False, default="beta", server_default=text("'beta'")
    )
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _updated()


class User(Base):
    """A user in a tenant. Auth is owned by Clerk; we mirror the minimum."""

    __tablename__ = "users"

    id: Mapped[UUID] = _uuid_pk()
    tenant_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    clerk_user_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(
        String(32), nullable=False, default="member", server_default=text("'member'")
    )
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _updated()

    __table_args__ = (
        Index("ix_users_tenant_id", "tenant_id"),
        CheckConstraint(
            "role IN ('owner','admin','member')",
            name="role_enum",
        ),
    )


class Watchlist(Base):
    __tablename__ = "watchlists"

    id: Mapped[UUID] = _uuid_pk()
    tenant_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _updated()

    __table_args__ = (
        Index("ix_watchlists_tenant_id", "tenant_id"),
    )


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    id: Mapped[UUID] = _uuid_pk()
    watchlist_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("watchlists.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_case_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    target_btl_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _now()

    __table_args__ = (
        UniqueConstraint("watchlist_id", "product_id",
                         name="uq_watchlist_items_watchlist_product"),
    )


class Note(Base):
    """Free-text per-tenant per-product notes. Soft-deleted."""

    __tablename__ = "notes"

    id: Mapped[UUID] = _uuid_pk()
    tenant_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    author_user_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _updated()

    __table_args__ = (
        Index("ix_notes_tenant_product", "tenant_id", "product_id"),
    )


# ===========================================================================
# ALERTS
# ===========================================================================

class AlertConfig(Base):
    """A subscription to one alert rule type for a tenant.

    ``rule_type`` examples:
        - price_drop_pct (params: threshold=5)
        - new_rip
        - rip_rotated (rip changed tier or save_amount)
        - partial_expiring_soon (params: days=2)
        - new_closeout
        - watchlist_target_hit
    """

    __tablename__ = "alert_configs"

    id: Mapped[UUID] = _uuid_pk()
    tenant_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    rule_type: Mapped[str] = mapped_column(String(64), nullable=False)
    params: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    channel: Mapped[str] = mapped_column(
        String(32), nullable=False, default="email", server_default=text("'email'")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _updated()

    __table_args__ = (
        Index("ix_alert_configs_tenant_id", "tenant_id"),
        CheckConstraint(
            "channel IN ('email','sms','inapp')",
            name="channel_enum",
        ),
    )


class AlertEvent(Base):
    """A fired alert. The bell-icon inbox in the UI pages from this table."""

    __tablename__ = "alert_events"

    id: Mapped[UUID] = _uuid_pk()
    tenant_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    alert_config_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("alert_configs.id", ondelete="SET NULL")
    )
    product_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL")
    )
    book_edition_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("book_editions.id", ondelete="SET NULL")
    )
    rule_type: Mapped[str] = mapped_column(String(64), nullable=False)
    score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    payload: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fired_at: Mapped[datetime] = _now()

    __table_args__ = (
        Index("ix_alert_events_tenant_fired_at", "tenant_id", "fired_at"),
    )


# ===========================================================================
# AUDIT
# ===========================================================================

class AuditLog(Base):
    """Append-only audit log. Every write to tenant-scoped tables logs here."""

    __tablename__ = "audit_log"

    id: Mapped[UUID] = _uuid_pk()
    tenant_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True))
    user_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True))
    entity_table: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    at: Mapped[datetime] = _now()

    __table_args__ = (
        Index("ix_audit_log_tenant_at", "tenant_id", "at"),
        Index("ix_audit_log_entity", "entity_table", "entity_id"),
        CheckConstraint(
            "action IN ('insert','update','delete','soft_delete','restore')",
            name="action_enum",
        ),
    )


# ===========================================================================
# AI CACHE + MATCH QUEUE
# ===========================================================================

class AiVerdictCache(Base):
    """Cached AI-A buy-now-vs-defer verdicts. Keyed on (product, edition) so
    one Haiku call serves every tenant viewing that SKU this month."""

    __tablename__ = "ai_verdict_cache"

    id: Mapped[UUID] = _uuid_pk()
    product_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    book_edition_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("book_editions.id", ondelete="CASCADE"),
        nullable=False,
    )
    verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    factors: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    generated_at: Mapped[datetime] = _now()

    __table_args__ = (
        UniqueConstraint("product_id", "book_edition_id",
                         name="uq_ai_verdict_product_edition"),
        CheckConstraint(
            "verdict IN ('BUY_NOW','DEFER','HOLD','PASS')",
            name="verdict_enum",
        ),
    )


class LowConfidenceMatch(Base):
    """Review queue for fuzzy matches with score < 0.85 during ingest."""

    __tablename__ = "low_confidence_matches"

    id: Mapped[UUID] = _uuid_pk()
    book_edition_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("book_editions.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_table: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    candidate_product_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL")
    )
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    payload: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_to_product_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL")
    )
    resolved_by_user_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = _now()

    __table_args__ = (
        Index("ix_low_confidence_matches_book_edition", "book_edition_id"),
        Index("ix_low_confidence_matches_unresolved",
              "book_edition_id",
              postgresql_where=text("resolved_at IS NULL")),
    )


__all__ = [
    # dims
    "Distributor", "Category", "Brand",
    # catalog facts
    "BookEdition", "IngestRun", "Product", "ProductEdition", "RipOffer",
    "PartialsPricing", "PartialsRip", "InventoryReduction",
    "Combo", "ComboComponent", "KegListEntry",
    # tenancy
    "Tenant", "User", "Watchlist", "WatchlistItem", "Note",
    # alerts
    "AlertConfig", "AlertEvent",
    # audit
    "AuditLog",
    # AI / matching
    "AiVerdictCache", "LowConfidenceMatch",
]
