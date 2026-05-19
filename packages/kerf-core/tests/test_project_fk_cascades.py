"""
Audit every CREATE TABLE in the consolidated migrations and verify that every
FK referencing projects(id) or files(id) carries the correct ON DELETE action.

Rules enforced:
  - FK → projects(id)  must be  ON DELETE CASCADE
      EXCEPT projects.forked_from_project_id which is ON DELETE SET NULL
      (deleting a source project must not cascade-delete its forks).
  - FK → files(id)  must be  ON DELETE CASCADE
      EXCEPT chat_threads.file_id which is ON DELETE SET NULL
      (a thread survives if its anchoring file is deleted — it just loses
      the attachment).
  - FK → chat_threads(id)  must be  ON DELETE CASCADE
  - FK → chat_messages(id) must be  ON DELETE CASCADE  (future-proofing)

All other references (users, workspaces, blob_objects, …) are left to their
own correct semantics and not audited here — this test focuses solely on the
project-delete cascade path.
"""

from __future__ import annotations

import pathlib
import re
import sys

# ---------------------------------------------------------------------------
# Locate migrations directory relative to this test file.
# ---------------------------------------------------------------------------
_MIGRATIONS_DIR = (
    pathlib.Path(__file__).resolve().parents[1]
    / "src/kerf_core/db/migrations"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Matches a full column definition line that contains a REFERENCES clause.
# Group 1 = column name (or empty for table-level constraints)
# Group 2 = referenced table + column, e.g.  projects(id)
# Group 3 = the rest of the line (may contain ON DELETE …)
_FK_RE = re.compile(
    r"""
    ^\s*                                # leading whitespace
    (?P<col>\w+)?                       # optional column name
    [^(]*                               # skip to REFERENCES
    \breferences\s+                     # keyword
    (?P<ref_table>\w+)\((?P<ref_col>[^)]+)\)  # table(col)
    (?P<tail>.*)                        # rest of line
    """,
    re.IGNORECASE | re.VERBOSE,
)

_ON_DELETE_RE = re.compile(r"\bon\s+delete\s+(\w+)", re.IGNORECASE)


def _parse_fks(sql_file: pathlib.Path) -> list[dict]:
    """Return a list of FK descriptor dicts from *sql_file*."""
    fks = []
    text = sql_file.read_text()
    for lineno, line in enumerate(text.splitlines(), start=1):
        m = _FK_RE.match(line)
        if not m:
            continue
        ref_table = m.group("ref_table").lower()
        ref_col   = m.group("ref_col").lower().strip()
        tail      = m.group("tail") or ""
        col       = (m.group("col") or "").lower()

        # Extract the ON DELETE action if present.
        od = _ON_DELETE_RE.search(tail)
        on_delete = od.group(1).lower() if od else None  # e.g. "cascade", "set"

        # "set null" is two tokens; normalise.
        if on_delete == "set":
            on_delete = "set null" if "null" in tail.lower() else "set"

        fks.append({
            "file": sql_file.name,
            "lineno": lineno,
            "col": col,
            "ref_table": ref_table,
            "ref_col": ref_col,
            "on_delete": on_delete,
            "line": line.rstrip(),
        })
    return fks


# ---------------------------------------------------------------------------
# Whitelisted SET NULL exceptions
# ---------------------------------------------------------------------------

# (file_stem_pattern, column_name_pattern, ref_table)
# Using simple substring matching on file / column names.
_SET_NULL_OK = [
    # projects.forked_from_project_id → projects(id)
    # Deleting a source project must not delete its forks.
    ("0001_core_identity", "forked_from_project_id", "projects"),
    # chat_threads.file_id → files(id)
    # A thread survives after its anchoring file is deleted.
    ("0001_core_identity", "file_id", "files"),
    # usage_events.project_id → projects(id)
    # Billing audit records must survive project deletion — they are the
    # financial ledger.  The project_id is nulled rather than cascading so
    # COGS reconciliation can still tally total spend.
    ("0002_project_ingestion", "project_id", "projects"),
    # Various "created_by / user_id / reviewer_id" columns → users(id)
    # These are soft-references to the user who created something;
    # deleting the user sets them to null (anonymised history).
    # Auditing user-delete cascades is out of scope for T-313.
]


def _is_set_null_ok(fk: dict) -> bool:
    for file_pat, col_pat, ref_table in _SET_NULL_OK:
        if (
            file_pat in fk["file"]
            and col_pat in fk["col"]
            and ref_table == fk["ref_table"]
        ):
            return True
    return False


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

def test_project_fk_cascades():
    """Every FK → projects(id) or files(id) must be ON DELETE CASCADE."""
    violations: list[str] = []

    for sql_file in sorted(_MIGRATIONS_DIR.glob("*.sql")):
        for fk in _parse_fks(sql_file):
            ref_table = fk["ref_table"]

            if ref_table not in ("projects", "files", "chat_threads", "chat_messages"):
                continue

            on_delete = fk["on_delete"]

            if on_delete == "cascade":
                # Correct.
                continue

            if on_delete == "set null" and _is_set_null_ok(fk):
                # Whitelisted soft-reference.
                continue

            # Anything else (None, "restrict", unknown "set null") is a violation.
            violations.append(
                f"{fk['file']}:{fk['lineno']}: "
                f"col={fk['col'] or '<table-level>'} "
                f"references {fk['ref_table']}({fk['ref_col']}) "
                f"on_delete={on_delete!r}  — "
                f"expected CASCADE (or whitelisted SET NULL)\n"
                f"  {fk['line']}"
            )

    assert not violations, (
        "FK cascade audit failed — the following constraints reference "
        "projects(id) / files(id) without ON DELETE CASCADE:\n\n"
        + "\n\n".join(violations)
    )


def test_chat_thread_messages_cascade():
    """chat_messages.thread_id → chat_threads(id) must be ON DELETE CASCADE."""
    violations: list[str] = []
    for sql_file in sorted(_MIGRATIONS_DIR.glob("*.sql")):
        for fk in _parse_fks(sql_file):
            if fk["ref_table"] != "chat_threads":
                continue
            if fk["on_delete"] != "cascade":
                violations.append(
                    f"{fk['file']}:{fk['lineno']}: "
                    f"col={fk['col']} → chat_threads on_delete={fk['on_delete']!r}"
                )
    assert not violations, "\n".join(violations)
