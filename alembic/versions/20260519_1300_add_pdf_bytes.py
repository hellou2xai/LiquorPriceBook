"""add pdf_bytes column to book_editions

PDFs live in Postgres for MVP (no object storage dependency). The column is
deferred at the ORM layer so list queries don't pull megabytes.

Revision ID: 0003_pdf_bytes
Revises: 0002_seed
Create Date: 2026-05-19 13:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0003_pdf_bytes"
down_revision: Union[str, None] = "0002_seed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "book_editions",
        sa.Column("pdf_bytes", sa.LargeBinary(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("book_editions", "pdf_bytes")
