"""Widen alert_events.score from NUMERIC(4,3) to NUMERIC(8,3).

The alert engine produces scores like 900.0 which overflow 4,3.

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_widen_alert_score"
down_revision = "0004_default_tenant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "alert_events",
        "score",
        type_=sa.Numeric(8, 3),
        existing_type=sa.Numeric(4, 3),
    )


def downgrade() -> None:
    op.alter_column(
        "alert_events",
        "score",
        type_=sa.Numeric(4, 3),
        existing_type=sa.Numeric(8, 3),
    )
