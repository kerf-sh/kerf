"""Regression: migration runner must skip comments-only "tombstone" files.

T-307 folded every alter/drop shim back into the originating CREATE TABLE,
which left three migrations (0003_revisions_prefs.sql,
0007_step_tess_revision_finalize.sql, 0009_workshop_gallery.sql) as pure
comments — no SQL statements at all.

asyncpg's simple-query response parser crashes with
`AttributeError: 'NoneType' object has no attribute 'decode'` when the
server returns an EmptyQueryResponse (no command tag) — exactly what
happens for a comments-only file. The Fly `release_command` deploy
aborted because of this on 2026-05-19.

The runner now strips line comments + blank lines to decide whether a
file has any executable content; tombstones are stamped in the ledger
and skipped.
"""
from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path


def _load_runner():
    """Import the runner module without it executing as __main__."""
    runner_path = Path(__file__).resolve().parents[1] / "src/kerf_core/db/migrations/runner.py"
    spec = runner_path.read_text()
    mod = types.ModuleType("runner_under_test")
    # The runner uses `Path(__file__).parent` to locate the migrations
    # dir; provide a __file__ so it works when exec'd from this test.
    mod.__file__ = str(runner_path)
    exec(compile(spec, str(runner_path), "exec"), mod.__dict__)
    return mod


def test_runner_detects_tombstone_pattern():
    """Tombstone-detection is the comment-stripping helper at the heart
    of the fix. Verify the detection logic itself before testing the
    full async flow."""
    body = "-- comment 1\n  -- comment 2\n\n   -- comment 3   \n"
    stripped = "\n".join(
        line for line in body.splitlines()
        if line.strip() and not line.strip().startswith("--")
    ).strip()
    assert stripped == "", "all-comment body should strip to empty"

    body_with_stmt = "-- header\nselect 1;\n-- footer\n"
    stripped = "\n".join(
        line for line in body_with_stmt.splitlines()
        if line.strip() and not line.strip().startswith("--")
    ).strip()
    assert stripped == "select 1;"


def test_baseline_has_three_tombstone_files():
    """Pin the actual tombstone files so a refactor can't silently delete
    them (which would change migration numbering) or accidentally add
    executable SQL into them (which would re-introduce the asyncpg crash)."""
    migrations = Path(__file__).resolve().parents[1] / "src/kerf_core/db/migrations"
    tombstones = []
    for sql_file in sorted(migrations.glob("*.sql")):
        text = sql_file.read_text()
        stripped = "\n".join(
            line for line in text.splitlines()
            if line.strip() and not line.strip().startswith("--")
        ).strip()
        if not stripped:
            tombstones.append(sql_file.name)

    expected = {
        "0003_revisions_prefs.sql",
        "0007_step_tess_revision_finalize.sql",
        "0009_workshop_gallery.sql",
    }
    assert set(tombstones) == expected, (
        f"expected tombstones {expected}; found {set(tombstones)}. "
        f"If you renamed/removed a fold target, update this test."
    )


def test_runner_module_imports_without_running():
    """The runner is importable as a library (not just as __main__).
    This is what the test loader does, and what supports the
    auto-discovery of `run_migrations` for other tests."""
    runner = _load_runner()
    assert hasattr(runner, "run_migrations")
    assert hasattr(runner, "_LEDGER")
    assert runner._LEDGER == "kerf_migrations_ledger"


def test_runner_tombstone_skips_execute(monkeypatch):
    """Behavioural: run_migrations against a fake connection that records
    every execute() call. Assert the tombstone files reach the ledger
    INSERT path but NOT the body-execute path."""
    runner = _load_runner()

    executed_bodies: list[str] = []
    ledger_inserts: list[str] = []

    class FakeTransaction:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *exc):
            return False

    class FakeConn:
        def __init__(self):
            self._closed = False
        async def execute(self, sql, *args):
            # Migration-body execute: positional 0 is the file body.
            # Ledger insert: positional 0 is a parameterised insert SQL.
            if "INSERT INTO kerf_migrations_ledger" in sql:
                ledger_inserts.append(args[0] if args else "")
            elif "CREATE TABLE IF NOT EXISTS kerf_migrations_ledger" in sql:
                # ledger DDL — neither a migration body nor a stamp
                pass
            else:
                executed_bodies.append(sql[:80])
            return "OK"
        async def fetch(self, sql, *args):
            return []
        def transaction(self):
            return FakeTransaction()
        async def close(self):
            self._closed = True

    fake = FakeConn()

    async def fake_connect(dsn):
        return fake

    monkeypatch.setattr(runner, "asyncpg",
                        types.SimpleNamespace(
                            connect=fake_connect,
                            PostgresError=Exception,
                        ))

    asyncio.run(runner.run_migrations("postgres://test"))

    # Every migration file must have its name in the ledger.
    migrations_dir = Path(__file__).resolve().parents[1] / "src/kerf_core/db/migrations"
    expected_files = {p.name for p in migrations_dir.glob("*.sql")}
    assert set(ledger_inserts) == expected_files

    # Tombstones MUST NOT be in executed_bodies. Compute their substring
    # markers — each tombstone starts with a comment header — and assert
    # none of those headers appear in executed_bodies.
    tombstone_names = {
        "0003_revisions_prefs.sql",
        "0007_step_tess_revision_finalize.sql",
        "0009_workshop_gallery.sql",
    }
    for ts in tombstone_names:
        ts_text = (migrations_dir / ts).read_text()
        first_chars = ts_text[:80].strip().splitlines()[0] if ts_text else ""
        for body in executed_bodies:
            assert first_chars not in body or first_chars == "", (
                f"tombstone {ts} body reached execute(): {body!r}"
            )
