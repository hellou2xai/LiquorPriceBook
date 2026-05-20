"""Add hidden_at column to watchlists for hiding orders.

Retailers can hide completed/old orders without deleting them.

Revision ID: 0008_order_hidden_at
Revises: 0007_order_management
Create Date: 2026-05-22
"""
from alembic import op

revision = "0008_order_hidden_at"
down_revision = "0007_order_management"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE watchlists "
        "ADD COLUMN IF NOT EXISTS hidden_at TIMESTAMPTZ"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE watchlists DROP COLUMN IF EXISTS hidden_at")
