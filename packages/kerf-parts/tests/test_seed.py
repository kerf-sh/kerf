"""Seed module — the network/DB-free pieces: NOTICE emission into the
gitignored generated dir, and convert_sources orchestration. The DB write
path (seed_into_db) needs Postgres + kerf_core and is exercised by Kerf's
integration suite, not here.
"""
from pathlib import Path

import pytest

from kerf_parts.manifest import Source
from kerf_parts.seed import (
    GENERATED_DIRNAME,
    NOTICE_FILENAME,
    convert_sources,
    write_notice,
)

SRCS = [
    Source("kicad-symbols", "https://gitlab.com/kicad/libraries/kicad-symbols.git",
           "9.0.9", "CC-BY-SA-4.0 WITH KiCad-Library-Exception", "kicad-sym",
           "kicad"),
    Source("bolts", "https://github.com/boltsparts/BOLTS.git", "v0.4.1",
           "LGPL-2.1-or-later", "bolts-blt", "bolts"),
]


def test_write_notice_into_gitignored_generated_dir(tmp_path):
    generated = tmp_path / GENERATED_DIRNAME
    out = write_notice(generated, SRCS)
    assert out.name == NOTICE_FILENAME
    assert out.parent == generated
    text = out.read_text(encoding="utf-8")
    # Attribution content + the explicit "not redistributed" statement.
    assert "NOT redistributed by Kerf" in text
    assert "kicad-symbols" in text
    assert "CC-BY-SA-4.0" in text
    assert "KiCad Library Exception" in text
    assert "v0.4.1" in text


def test_convert_sources_skips_missing_cache(tmp_path):
    logs = []
    parts = convert_sources(SRCS, tmp_path, log=logs.append)
    # No cache dirs exist -> nothing converted, clear message, no crash.
    assert parts == []
    assert any("cache missing" in m for m in logs)


def test_convert_sources_runs_scaffold_adapter(tmp_path):
    # bolts cache present but empty -> scaffold adapter returns [] cleanly.
    (tmp_path / "bolts").mkdir()
    logs = []
    parts = convert_sources(
        [SRCS[1]], tmp_path, log=logs.append
    )
    assert parts == []
    assert any("0 part(s) converted" in m for m in logs)
