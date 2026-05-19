"""initial schema

Creates all 24 tables for the LiquorPriceBook MVP. Materialised views are
created in a follow-up migration once we have first-edition data to back them.

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-19 12:00:00
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

from lpb_core.db import Base
import lpb_core.db.models  # noqa: F401 - ensure models register on Base.metadata


# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Required extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # Create every table declared on Base.metadata in dependency order.
    Base.metadata.create_all(bind=op.get_bind())

    # Helpful trigram indexes for free-text search (week 5-6 catalog browse).
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_product_editions_description_trgm "
        "ON product_editions USING gin (description gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_combos_contains_trgm "
        "ON combos USING gin (contains gin_trgm_ops)"
    )


def downgrade() -> None:
    # Drop everything in reverse dependency order.
    op.execute("DROP INDEX IF EXISTS ix_combos_contains_trgm")
    op.execute("DROP INDEX IF EXISTS ix_product_editions_description_trgm")
    Base.metadata.drop_all(bind=op.get_bind())
