"""Add divisions column to product_editions.

Stores territory/division codes extracted from brand_header parentheses
(e.g. "L GS FB IV" from "OLD GRAND-DAD ( L GS FB IV )"). These codes
indicate delivery zones or ordering restrictions for each product.

Revision ID: 0006_add_divisions
Revises: 0005_widen_alert_score
Create Date: 2026-05-20
"""
from alembic import op

revision = "0006_add_divisions"
down_revision = "0005_widen_alert_score"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE product_editions "
        "ADD COLUMN IF NOT EXISTS divisions VARCHAR(255)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE product_editions "
        "DROP COLUMN IF EXISTS divisions"
    )
