"""Add product_links table for cross-distributor product matching.

Products from different distributors that represent the same physical item
get a shared link_id. Enables cross-distributor price comparison, RIP
comparison, and unified analytics.

Revision ID: 0010_product_links
Revises: 0009_sales_reps
Create Date: 2026-05-23
"""
from alembic import op

revision = "0010_product_links"
down_revision = "0009_sales_reps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS product_links (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            canonical_description VARCHAR(512),
            size VARCHAR(32),
            pack INT,
            brand_id UUID REFERENCES brands(id) ON DELETE SET NULL,
            category_id UUID REFERENCES categories(id) ON DELETE SET NULL,
            match_method VARCHAR(32) NOT NULL DEFAULT 'auto',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_product_links_brand "
        "ON product_links (brand_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_product_links_category "
        "ON product_links (category_id)"
    )
    # Add link_id to products table
    op.execute(
        "ALTER TABLE products "
        "ADD COLUMN IF NOT EXISTS link_id UUID REFERENCES product_links(id) ON DELETE SET NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_products_link_id "
        "ON products (link_id) WHERE link_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE products DROP COLUMN IF EXISTS link_id")
    op.execute("DROP TABLE IF EXISTS product_links")
