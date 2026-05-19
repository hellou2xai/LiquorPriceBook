"""add pdf_bytes column to book_editions

PDFs live in Postgres for MVP (no object storage dependency). The column is
deferred at the ORM layer so list queries don't pull megabytes.

Idempotency note
----------------
The 0001 initial migration uses ``Base.metadata.create_all()`` against the
*live* model, so any column we add to the ORM also gets picked up by 0001
on fresh databases. That means by the time this migration runs against a
brand-new Postgres, ``pdf_bytes`` is already there. We therefore use
``ADD COLUMN IF NOT EXISTS`` so the migration is idempotent: it adds the
column on existing DBs that pre-date the change, and is a no-op on fresh DBs
where 0001 created it already.

The same pattern (IF NOT EXISTS / IF EXISTS) should apply to every future
schema change until / unless we refactor 0001 to use explicit op.create_table
calls.

Revision ID: 0003_pdf_bytes
Revises: 0002_seed
Create Date: 2026-05-19 13:00:00
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0003_pdf_bytes"
down_revision: Union[str, None] = "0002_seed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE book_editions ADD COLUMN IF NOT EXISTS pdf_bytes BYTEA"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE book_editions DROP COLUMN IF EXISTS pdf_bytes"
    )
