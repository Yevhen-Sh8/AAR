"""The migration chain must resolve — offline, without a database.

CI caught `KeyError: '0011'` on a migration whose `down_revision` named a
revision that does not exist: the project's ids are `0011_flexible_participants`
style, and a new file used the bare number. The whole suite stayed green,
because tests build the schema with `create_all` and never touch alembic. So
the ONE thing the migrations are for — upgrading a database that already has
data — was the one thing nothing verified until a Postgres job ran.

`ScriptDirectory` walks the graph with no engine and no connection, so this
runs in the normal suite and fails in seconds instead of in CI.
"""
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

_API_ROOT = Path(__file__).resolve().parents[1]


def _scripts() -> ScriptDirectory:
    cfg = Config(str(_API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_API_ROOT / "alembic"))
    return ScriptDirectory.from_config(cfg)


def test_every_down_revision_points_at_a_real_revision() -> None:
    scripts = _scripts()
    known = {s.revision for s in scripts.walk_revisions()}
    for script in scripts.walk_revisions():
        for down in script._versioned_down_revisions:
            assert down in known, (
                f"{script.revision} declares down_revision={down!r}, which no "
                f"migration defines. Known: {sorted(known)}"
            )


def test_the_chain_is_linear_with_exactly_one_head() -> None:
    """Two heads mean two people added a migration on the same parent."""
    heads = _scripts().get_heads()
    assert len(heads) == 1, f"expected one head, got {heads}"


def test_walking_from_base_to_head_reaches_every_migration() -> None:
    """A revision nobody points at would never run on a fresh database."""
    scripts = _scripts()
    head = scripts.get_current_head()
    assert head is not None
    reachable = {s.revision for s in scripts.iterate_revisions(head, "base")}
    all_revisions = {s.revision for s in scripts.walk_revisions()}
    assert reachable == all_revisions, (
        f"unreachable from head: {sorted(all_revisions - reachable)}"
    )


def test_revision_ids_follow_the_project_convention() -> None:
    """`0012_decision_quality`, not `0012` — the bare number is what broke CI."""
    for script in _scripts().walk_revisions():
        assert script.revision[:4].isdigit(), script.revision
        assert "_" in script.revision, (
            f"{script.revision!r} is a bare number; use '<nnnn>_<name>' so a "
            f"down_revision written from memory cannot silently miss."
        )
