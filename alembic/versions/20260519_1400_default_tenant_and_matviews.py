"""seed default tenant + create price-changes materialised view

Until Clerk auth lands, every retailer signs in with the same admin/admin
credentials. We need *something* to anchor watchlists and notes on, so we
seed a single ``internal`` tenant and a single ``admin`` user with fixed
UUIDs. The static-auth dependency returns these IDs verbatim.

Also creates ``mv_price_changes``, the materialised view that powers the
"what moved this month" dashboard. Computed via window function over
product_editions ordered by (year, month) per product. Refreshed at the end
of every successful ingest by the worker / API.

Revision ID: 0004_default_tenant
Revises: 0003_pdf_bytes
Create Date: 2026-05-19 14:00:00
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = "0004_default_tenant"
down_revision: Union[str, None] = "0003_pdf_bytes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Fixed UUIDs so the static-auth dependency can return them without a DB roundtrip.
DEFAULT_TENANT_ID = "00000000-0000-0000-0000-00000000a001"
DEFAULT_USER_ID = "00000000-0000-0000-0000-00000000a002"
DEFAULT_WATCHLIST_ID = "00000000-0000-0000-0000-00000000a003"


def upgrade() -> None:
    conn = op.get_bind()

    # ---- default tenant ----
    conn.execute(
        text(
            "INSERT INTO tenants (id, slug, display_name, plan) "
            "VALUES (:id, 'internal', 'Internal (shared admin)', 'beta') "
            "ON CONFLICT (slug) DO NOTHING"
        ),
        {"id": DEFAULT_TENANT_ID},
    )

    # ---- default user ----
    conn.execute(
        text(
            "INSERT INTO users (id, tenant_id, clerk_user_id, email, "
            "display_name, role) "
            "VALUES (:id, :tenant_id, 'static-admin', 'admin@local', "
            "'Admin (static)', 'owner') "
            "ON CONFLICT (clerk_user_id) DO NOTHING"
        ),
        {"id": DEFAULT_USER_ID, "tenant_id": DEFAULT_TENANT_ID},
    )

    # ---- default watchlist ----
    conn.execute(
        text(
            "INSERT INTO watchlists (id, tenant_id, name, is_default) "
            "VALUES (:id, :tenant_id, 'My watchlist', TRUE) "
            "ON CONFLICT DO NOTHING"
        ),
        {"id": DEFAULT_WATCHLIST_ID, "tenant_id": DEFAULT_TENANT_ID},
    )

    # ---- mv_price_changes ----
    # One row per (product_id, book_edition_id), with the prior edition's
    # case_cost joined in via LAG. Excludes the very first edition for each
    # product (no comparison possible).
    op.execute("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS mv_price_changes AS
        WITH ordered AS (
            SELECT
                pe.id                                            AS product_edition_id,
                pe.product_id,
                pe.book_edition_id,
                pe.case_cost,
                pe.btl_cost,
                pe.category_id,
                pe.brand_id,
                be.year                                          AS year,
                be.month                                         AS month,
                be.distributor_id                                AS distributor_id,
                LAG(pe.case_cost) OVER w                         AS prev_case_cost,
                LAG(pe.btl_cost) OVER w                          AS prev_btl_cost,
                LAG(pe.book_edition_id) OVER w                   AS prev_book_edition_id
            FROM product_editions pe
            JOIN book_editions be ON be.id = pe.book_edition_id
            WINDOW w AS (
                PARTITION BY pe.product_id
                ORDER BY be.year, be.month, be.created_at
            )
        )
        SELECT
            product_edition_id,
            product_id,
            book_edition_id,
            distributor_id,
            year,
            month,
            category_id,
            brand_id,
            case_cost,
            prev_case_cost,
            (case_cost - prev_case_cost)                         AS case_cost_delta,
            CASE
                WHEN prev_case_cost IS NULL OR prev_case_cost = 0 THEN NULL
                ELSE ROUND(
                    (case_cost - prev_case_cost) / prev_case_cost * 100,
                    2
                )
            END                                                  AS case_cost_pct,
            btl_cost,
            prev_btl_cost,
            (btl_cost - prev_btl_cost)                           AS btl_cost_delta,
            prev_book_edition_id
        FROM ordered
        WHERE prev_case_cost IS NOT NULL;
    """)
    # Unique index lets us REFRESH MATERIALIZED VIEW CONCURRENTLY (we don't
    # actually use CONCURRENTLY in MVP since refresh is fast, but it's free).
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_mv_price_changes_pe "
        "ON mv_price_changes (product_edition_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_mv_price_changes_movers "
        "ON mv_price_changes (book_edition_id, case_cost_pct)"
    )


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_price_changes CASCADE")
    conn = op.get_bind()
    conn.execute(text("DELETE FROM watchlists WHERE id = :id"),
                 {"id": DEFAULT_WATCHLIST_ID})
    conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": DEFAULT_USER_ID})
    conn.execute(text("DELETE FROM tenants WHERE id = :id"), {"id": DEFAULT_TENANT_ID})
