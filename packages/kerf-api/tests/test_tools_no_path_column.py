"""Regression: tool implementations must NOT query the non-existent
`path` column on `files`.

The `files` table stores rows tree-shaped (parent_id + name); there is
no `path` column. Four tool modules (file_ops, material, object_ops,
revisions, scaffold) used to each carry a duplicate copy of a broken
`SELECT … WHERE path = $2` query, so every read_file / write_file /
edit_file / scaffold tool call 500'd with:

    asyncpg.exceptions.UndefinedColumnError: column "path" does not exist

surfacing to the user as:
  - The assistant hallucinating "temporary backend issue preventing file writes"
  - Tool-result chips showing ⚠ ERROR on every call
  - `main.jscad` never being updated despite the assistant saying it did

Fix: tree-walking resolve_path in file_ops; all four other modules
re-export it.
"""
from __future__ import annotations

import pathlib
import re


_ROOT = pathlib.Path(__file__).resolve().parents[3]
_TOOL_DIRS = [
    _ROOT / "packages/kerf-api/src/kerf_api/tools",
    _ROOT / "packages/kerf-chat/src/kerf_chat/tools",
    _ROOT / "packages/kerf-cloud/src/kerf_cloud",
]

# Lines like:    SELECT ... FROM files ... WHERE ... path = $...
# (case-insensitive). Excludes the literal "name" column.
_FORBIDDEN = re.compile(
    r"FROM\s+files[\s\S]{0,200}?\bpath\s*=\s*\$\d+",
    re.IGNORECASE,
)


def test_no_files_path_column_query_in_tool_modules():
    offenders: list[str] = []
    for d in _TOOL_DIRS:
        if not d.is_dir():
            continue
        for py in d.rglob("*.py"):
            text = py.read_text()
            # Strip comments first so commentary explaining the OLD bug
            # (e.g. "this used to say WHERE path = $2") doesn't trip the guard.
            stripped = "\n".join(
                line for line in text.splitlines()
                if not line.lstrip().startswith("#")
            )
            if _FORBIDDEN.search(stripped):
                offenders.append(str(py.relative_to(_ROOT)))
    assert not offenders, (
        f"these files query the non-existent `files.path` column:\n"
        + "\n".join(f"  {o}" for o in offenders)
        + "\nUse the tree-walking resolve_path helper from "
        + "kerf_api.tools.file_ops instead."
    )


def test_resolve_path_is_centralised_in_file_ops():
    """The other tool modules should re-export resolve_path from file_ops,
    not declare their own copy."""
    file_ops = (_ROOT / "packages/kerf-api/src/kerf_api/tools/file_ops.py").read_text()
    assert "async def resolve_path(" in file_ops, (
        "file_ops.resolve_path is the canonical implementation"
    )

    for sibling in ("material.py", "object_ops.py", "revisions.py", "scaffold.py"):
        text = (_ROOT / "packages/kerf-api/src/kerf_api/tools" / sibling).read_text()
        # Re-export form is `from kerf_api.tools.file_ops import resolve_path`.
        # Forbid a fresh `async def resolve_path(` declaration in these files.
        assert "async def resolve_path(" not in text, (
            f"{sibling} must NOT redeclare resolve_path — import it from file_ops"
        )
        assert "from kerf_api.tools.file_ops import" in text, (
            f"{sibling} must import resolve_path (and possibly ensure_folders) "
            f"from kerf_api.tools.file_ops"
        )
