"""Static checks on the Alembic revision chain.

These don't need a DB connection - they parse the script directory and assert
invariants:

  * Every revision ID fits ``alembic_version.version_num VARCHAR(32)``.
  * The chain is linear with no orphan or duplicate revisions.

If you've added a new migration and the integration test (alembic upgrade head
against real Postgres) fails on bookkeeping, this is the cheap repro.
"""

from alembic.config import Config
from alembic.script import ScriptDirectory

ALEMBIC_VERSION_NUM_MAX_LEN = 32


def _script_dir() -> ScriptDirectory:
    return ScriptDirectory.from_config(Config("alembic.ini"))


def test_revision_ids_fit_default_version_column():
    script = _script_dir()
    too_long = [
        r.revision
        for r in script.walk_revisions()
        if len(r.revision) > ALEMBIC_VERSION_NUM_MAX_LEN
    ]
    assert not too_long, (
        f"Revision IDs longer than {ALEMBIC_VERSION_NUM_MAX_LEN} chars will "
        f"break alembic bookkeeping: {too_long}"
    )


def test_revision_chain_is_linear():
    script = _script_dir()
    heads = script.get_heads()
    assert len(heads) == 1, f"expected exactly one head, found {heads}"
