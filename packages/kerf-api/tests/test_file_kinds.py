"""Regression guard for the 'creating a file does nothing' bug.

The FileTree "+ New" menu offered kinds (section, cam_layered, tool,
plc_st, quadmesh, wiring) that the create_file endpoint's allow-list
rejected with 400 "invalid kind" — the store swallowed the error so the
UI silently did nothing. This pins three invariants:

1. Every kind the frontend menu offers is in the backend FILE_KINDS
   allow-list (so create_file accepts it).
2. FILE_KINDS exactly matches the DB CHECK constraint set in the latest
   files-kind migration (no app↔DB drift → no surprise 500s).
3. 'wiring' (a shipped, viewer-backed kind) is creatable.
"""
from __future__ import annotations

import pathlib
import re

from kerf_api.routes import FILE_KINDS

# The canonical FileTree "+ New" menu order (src/components/FileTree.jsx
# KIND_ORDER). Kept here as the cross-language contract.
MENU_KINDS = {
    "folder", "file", "sketch", "assembly", "drawing", "feature",
    "section", "cam_layered", "part", "circuit", "equations", "wiring",
    "tool", "plc_st", "quadmesh",
}

_MIGRATIONS = (
    pathlib.Path(__file__).resolve().parents[2]
    / "kerf-core/src/kerf_core/db/migrations"
)


def _latest_kind_check_set() -> set[str]:
    """Parse the final files_kind_check allowed-kind set.

    After the 66->10 migration fold the constraint lives in the
    consolidated baseline (0001_core_identity.sql). Scan every migration
    in filename order and use the LAST files_kind_check definition, so
    this keeps working wherever the constraint ends up.
    """
    pat = re.compile(
        r"files_kind_check\s+check\s*\(\s*kind in \(([^)]*)\)", re.I
    )
    found: str | None = None
    for path in sorted(_MIGRATIONS.glob("*.sql")):
        for m in pat.finditer(path.read_text()):
            found = m.group(1)
    assert found, "no files_kind_check definition found in migrations"
    return set(re.findall(r"'([a-z_-]+)'", found))


def test_every_menu_kind_is_accepted_by_create_file():
    missing = MENU_KINDS - set(FILE_KINDS)
    assert not missing, (
        f"FileTree menu offers kinds the API rejects with 400 "
        f"('nothing happens' bug): {sorted(missing)}"
    )


def test_wiring_kind_is_creatable():
    assert "wiring" in FILE_KINDS


def test_file_kinds_matches_db_check_constraint():
    db = _latest_kind_check_set()
    app = set(FILE_KINDS)
    assert app == db, (
        f"FILE_KINDS drifted from the DB CHECK constraint.\n"
        f"  only in app: {sorted(app - db)}\n"
        f"  only in DB : {sorted(db - app)}"
    )
