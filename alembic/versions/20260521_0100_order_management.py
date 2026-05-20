"""Add order management columns to watchlists and watchlist_items.

Extends watchlists for named orders with division assignment and status.
Extends watchlist_items with quantity tracking and RIP tier selection.

Revision ID: 0007_order_management
Revises: 0006_add_divisions
Create Date: 2026-05-21
"""
from alembic import op

revision = "0007_order_management"
down_revision = "0006_add_divisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- watchlists: order metadata --
    op.execute(
        "ALTER TABLE watchlists "
        "ADD COLUMN IF NOT EXISTS division VARCHAR(16)"
    )
    op.execute(
        "ALTER TABLE watchlists "
        "ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT 'draft'"
    )
    op.execute(
        "ALTER TABLE watchlists "
        "ADD COLUMN IF NOT EXISTS order_notes TEXT"
    )
    op.execute(
        "ALTER TABLE watchlists "
        "ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMPTZ"
    )

    # -- watchlist_items: quantity tracking --
    op.execute(
        "ALTER TABLE watchlist_items "
        "ADD COLUMN IF NOT EXISTS qty_cases INTEGER NOT NULL DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE watchlist_items "
        "ADD COLUMN IF NOT EXISTS qty_bottles INTEGER NOT NULL DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE watchlist_items "
        "ADD COLUMN IF NOT EXISTS selected_rip_tier VARCHAR(16)"
    )

    # Indexes
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_watchlists_tenant_status "
        "ON watchlists (tenant_id, status)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_watchlists_tenant_status")
    op.execute("ALTER TABLE watchlist_items DROP COLUMN IF EXISTS selected_rip_tier")
    op.execute("ALTER TABLE watchlist_items DROP COLUMN IF EXISTS qty_bottles")
    op.execute("ALTER TABLE watchlist_items DROP COLUMN IF EXISTS qty_cases")
    op.execute("ALTER TABLE watchlists DROP COLUMN IF EXISTS submitted_at")
    op.execute("ALTER TABLE watchlists DROP COLUMN IF EXISTS order_notes")
    op.execute("ALTER TABLE watchlists DROP COLUMN IF EXISTS status")
    op.execute("ALTER TABLE watchlists DROP COLUMN IF EXISTS division")
