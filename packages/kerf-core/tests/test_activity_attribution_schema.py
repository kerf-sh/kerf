"""Regression: activity-feed attribution columns are folded into baseline.

Every chat event in the activity panel used to render as "Unknown
asked …" / "Unknown created the project" because:
  - `chat_messages` had no `user_id` column
  - `chat_threads` had no `created_by` column
  - `projects` had no `created_by` column

These were folded into the consolidated baseline migration
(0001_core_identity.sql) per the "clean baseline migrations" rule —
NOT introduced via an `alter table … add column` shim, since DBs are
reset on deploy.

This test pins the DDL so a refactor can't silently strip the columns
again (the activity SQL joins through them and the route would 500 if
they're missing).
"""
import pathlib
import re

_BASELINE = (
    pathlib.Path(__file__).resolve().parents[1]
    / "src/kerf_core/db/migrations/0001_core_identity.sql"
).read_text()


def _table_block(table: str) -> str:
    """Extract the CREATE TABLE …(...) block for a given table name."""
    m = re.search(
        rf"create table if not exists {re.escape(table)} \((.+?)\);",
        _BASELINE, re.S | re.I,
    )
    assert m, f"{table} CREATE TABLE not found in baseline"
    return m.group(1)


def test_chat_messages_has_user_id_column():
    body = _table_block("chat_messages")
    # user_id references users(id) — soft FK so deleting a user
    # anonymises their messages rather than cascading.
    assert re.search(r"user_id\s+uuid\s+references\s+users\(id\)", body, re.I), (
        "chat_messages.user_id must be present and reference users(id)"
    )
    assert "on delete set null" in body.lower()


def test_chat_threads_has_created_by_column():
    body = _table_block("chat_threads")
    assert re.search(r"created_by\s+uuid\s+references\s+users\(id\)", body, re.I), (
        "chat_threads.created_by must be present and reference users(id)"
    )


def test_projects_has_created_by_column():
    body = _table_block("projects")
    assert re.search(r"created_by\s+uuid\s+references\s+users\(id\)", body, re.I), (
        "projects.created_by must be present and reference users(id)"
    )


def test_attribution_columns_have_indexes():
    # Activity feed orders by created_at DESC and joins users; the per-user
    # filter benefits from indexes on the FK columns.
    assert "chat_messages_user_id_idx" in _BASELINE
    assert "chat_threads_created_by_idx" in _BASELINE
    assert "projects_created_by_idx" in _BASELINE


def test_no_alter_table_add_column_shims_for_attribution():
    """Per CLAUDE.md / memory: NEVER add the columns via `alter table add
    column`. They must be folded into the CREATE TABLE literal. This guard
    catches the easy mistake of slipping in a follow-on migration."""
    # The columns are added; the bug we're guarding against is doing it
    # via alter-table elsewhere instead of folding here.
    forbidden_pat = re.compile(
        r"alter\s+table\s+(chat_messages|chat_threads|projects)\s+add\s+column"
        r".*?(user_id|created_by)",
        re.I | re.S,
    )
    migrations_dir = pathlib.Path(__file__).resolve().parents[1] / "src/kerf_core/db/migrations"
    for sql_file in sorted(migrations_dir.glob("*.sql")):
        text = sql_file.read_text()
        match = forbidden_pat.search(text)
        assert match is None, (
            f"{sql_file.name} contains an ALTER TABLE …ADD COLUMN for an "
            f"attribution column ({match.group(0) if match else ''}). "
            f"Fold the column into the consolidated CREATE TABLE in "
            f"0001_core_identity.sql instead."
        )
