"""Add sales_reps table for distributor rep contacts.

Revision ID: 0009_sales_reps
Revises: 0008_order_hidden_at
Create Date: 2026-05-22
"""
from alembic import op

revision = "0009_sales_reps"
down_revision = "0008_order_hidden_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS sales_reps (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255) NOT NULL,
            phone VARCHAR(64),
            division VARCHAR(16),
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_sales_reps_tenant "
        "ON sales_reps (tenant_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sales_reps")
