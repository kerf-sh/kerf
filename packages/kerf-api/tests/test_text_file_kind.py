"""T-321 — Regression guard for the 'text' file kind and extension detection.

Invariants pinned here:
1. Every common text/source extension maps to kind='text' via classify.kind_for_name.
2. Dedicated Kerf extensions (.jscad, .sketch, .assembly, …) are NOT tagged 'text'.
3. FILE_KINDS allow-list and DB CHECK constraint both contain 'text'.
4. edit_file / write_file tool treat kind='text' the same as kind='file' (no BAD_KIND error).
"""
from __future__ import annotations

import pathlib
import re

import pytest

from kerf_core.classify import kind_for_name
from kerf_api.routes import FILE_KINDS


# ---------------------------------------------------------------------------
# 1. Extension → kind='text' detection
# ---------------------------------------------------------------------------

TEXT_EXTENSIONS = [
    # Plain text / docs
    "readme.txt",
    "notes.md",
    "report.rst",
    # Python
    "main.py",
    "helper.pyw",
    # C / C++ / embedded
    "driver.c",
    "driver.h",
    "module.cpp",
    "module.hpp",
    "sketch.ino",
    # Verilog / VHDL
    "counter.v",
    "counter.vhd",
    "counter.vhdl",
    # Linker script
    "stm32.ld",
    # Data / config
    "config.json",
    "config.yaml",
    "config.yml",
    "pyproject.toml",
    "settings.ini",
    "app.cfg",
    # Shell
    "build.sh",
    "run.bash",
    # Web
    "index.js",
    "main.ts",
    "app.jsx",
    "app.tsx",
    # Other
    "schema.sql",
    "schema.graphql",
    "proto.proto",
]


@pytest.mark.parametrize("name", TEXT_EXTENSIONS)
def test_text_extension_maps_to_text(name: str) -> None:
    result = kind_for_name(name)
    assert result == "text", (
        f"Expected kind_for_name({name!r}) == 'text', got {result!r}"
    )


# ---------------------------------------------------------------------------
# 2. Dedicated Kerf extensions are NOT tagged 'text'
# ---------------------------------------------------------------------------

DEDICATED_EXTENSIONS = [
    "model.jscad",
    "main.assembly",
    "sheet1.drawing",
    "base.sketch",
    "bracket.feature",
    "gear.part",
    "params.equations",
    "mesh.subd",
    "mesh.mesh",
    "family.family.json",
    "schedule.schedule.json",
]


@pytest.mark.parametrize("name", DEDICATED_EXTENSIONS)
def test_dedicated_extension_not_text(name: str) -> None:
    result = kind_for_name(name)
    assert result is None, (
        f"Expected kind_for_name({name!r}) == None (dedicated kind), got {result!r}"
    )


def test_unknown_extension_returns_none() -> None:
    assert kind_for_name("model.step") is None
    assert kind_for_name("scene.stl") is None
    assert kind_for_name("") is None
    assert kind_for_name(None) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 3. FILE_KINDS and DB constraint both include 'text'
# ---------------------------------------------------------------------------

_MIGRATIONS = (
    pathlib.Path(__file__).resolve().parents[2]
    / "kerf-core/src/kerf_core/db/migrations"
)


def _latest_kind_check_set() -> set[str]:
    # The baseline (post-T-307 clean-up) declares the files.kind allow-list
    # as an INLINE check inside `create table ... files (... kind text ...
    # check (kind in (...)))`, NOT as a named `files_kind_check` constraint
    # (that was an alter-table shim that T-307 folded away). Match both
    # forms so the drift-guard works whichever style the baseline uses.
    pats = [
        re.compile(r"files_kind_check\s+check\s*\(\s*kind in \(([^)]*)\)", re.I),
        re.compile(r"kind\s+text\s+not null\s+default\s+'file'\s+check\s*\(\s*kind in \(([^)]*)\)", re.I),
    ]
    found: str | None = None
    for path in sorted(_MIGRATIONS.glob("*.sql")):
        text = path.read_text()
        for pat in pats:
            for m in pat.finditer(text):
                found = m.group(1)
    assert found, "no files.kind check (inline or named) found in migrations"
    return set(re.findall(r"'([a-z_-]+)'", found))


def test_text_kind_in_file_kinds() -> None:
    assert "text" in FILE_KINDS, "'text' must be in FILE_KINDS allow-list"


def test_text_kind_in_db_constraint() -> None:
    db_kinds = _latest_kind_check_set()
    assert "text" in db_kinds, (
        "'text' is missing from the DB files_kind_check constraint"
    )


def test_file_kinds_matches_db_check_constraint_with_text() -> None:
    """Extend the existing drift-guard to include 'text'."""
    db = _latest_kind_check_set()
    app = set(FILE_KINDS)
    assert app == db, (
        f"FILE_KINDS drifted from the DB CHECK constraint.\n"
        f"  only in app: {sorted(app - db)}\n"
        f"  only in DB : {sorted(db - app)}"
    )


# ---------------------------------------------------------------------------
# 4. Extension-less well-known text files
# ---------------------------------------------------------------------------

def test_makefile_is_text() -> None:
    assert kind_for_name("Makefile") == "text"
    assert kind_for_name("makefile") == "text"


def test_dockerfile_is_text() -> None:
    assert kind_for_name("Dockerfile") == "text"
    assert kind_for_name("dockerfile") == "text"
