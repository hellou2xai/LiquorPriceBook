"""Add rip_ratings table for retailer thumbs-up/down on RIP offers.

Revision ID: 0011_rip_ratings
Revises: 0010_product_links
Create Date: 2026-05-24
"""
from alembic import op

revision = "0011_rip_ratings"
down_revision = "0010_product_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS rip_ratings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
            edition_label VARCHAR(8) NOT NULL,
            rating SMALLINT NOT NULL CHECK (rating IN (-1, 1)),
            comment TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (user_id, product_id, edition_label)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_rip_ratings_product "
        "ON rip_ratings (product_id, edition_label)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_rip_ratings_tenant "
        "ON rip_ratings (tenant_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS rip_ratings")
