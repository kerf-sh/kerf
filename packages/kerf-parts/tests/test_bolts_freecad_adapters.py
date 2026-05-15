"""Hermetic tests for the BOLTS and FreeCAD-library scaffold adapters.

All fixtures are created programmatically inside tmp_path — NO upstream
third-party data is committed.  No network access.  PyYAML is required for
the BOLTS parsing tests; tests that depend on it are skipped if it is absent.

Coverage goals (≥25 tests):
 BOLTS adapter
   - missing source returns []
   - source_present() reflects directory state
   - empty data/ dir returns []
   - single-class single-table enumerates correct part count
   - multi-row table → one part per row
   - multi-class collection → parts from all classes
   - multi-collection (two files) → parts from both
   - part name includes standard prefix and size key
   - category derived from collection/class content
   - provenance fields populated on every part
   - attribution block non-empty, has required keys
   - attribution_text non-empty
   - rel_path stable, ends with .part, no empty segments
   - content hash deterministic across two adapt() calls
   - idempotent re-run: same parts
   - malformed YAML file skipped, others still processed
   - class with no table → single placeholder part emitted
   - emit_part() returns a KerfPart with provenance
   - to_part_doc() matches canonical schema
 FreeCAD-library adapter
   - missing source returns []
   - source_present() reflects directory state
   - enumerates .FCStd files
   - enumerates .step / .stp / .brep files
   - ignores non-part files (.py, .md, .txt)
   - category derived from parent folder name
   - name derived from file stem
   - provenance fields on every part
   - attribution block non-empty
   - rel_path includes source name and folder structure
   - content hash deterministic
   - idempotent re-run
   - emit_part() returns KerfPart with provenance
   - multi-level folder structure → correct category + rel_path
   - hidden files / __MACOSX entries skipped
"""
from __future__ import annotations

from pathlib import Path

import pytest

from kerf_parts.adapters.bolts import (
    adapt as bolts_adapt,
    discover_collections,
    emit_part as bolts_emit_part,
    source_present as bolts_source_present,
)
from kerf_parts.adapters.freecad_library import (
    adapt as fc_adapt,
    discover_part_files,
    emit_part as fc_emit_part,
    source_present as fc_source_present,
)
from kerf_parts.manifest import Source

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

BOLTS_SRC = Source(
    "bolts",
    "https://github.com/boltsparts/BOLTS.git",
    "v0.4.1",
    "LGPL-2.1-or-later",
    "bolts-blt",
    "bolts",
)

FC_SRC = Source(
    "freecad-library",
    "https://github.com/FreeCAD/FreeCAD-library.git",
    "master",
    "CC0-1.0",
    "freecad-fcstd-step",
    "freecad_library",
)

# Minimal valid BOLTS .blt (YAML) collection fixture.
_BOLTS_BLT_SIMPLE = """\
collection:
  name: Test Hex Bolts
  description: Synthetic hex bolt collection for testing
  id: testhexbolts

classes:
  - id: TESTISO4014
    standard:
      - TEST ISO 4014
    description: Synthetic hex bolt full thread
    parameters:
      free: [d, l]
      types:
        d: Length
        l: Length
        k: Length
        s: Length
      defaults:
        d: M3
        l: 20
      tables:
        - index: d
          columns: [k, s]
          data:
            M3: [2.0, 5.5]
            M4: [2.8, 7.0]
            M5: [3.5, 8.0]
            M6: [4.0, 10.0]
"""

_BOLTS_BLT_NUTS = """\
collection:
  name: Test Hex Nuts
  description: Synthetic hex nut collection for testing
  id: testhexnuts

classes:
  - id: TESTDIN934
    standard:
      - TEST DIN 934
    description: Synthetic hex nut
    parameters:
      free: [d]
      types:
        d: Length
        m: Length
        s: Length
      defaults:
        d: M3
      tables:
        - index: d
          columns: [m, s]
          data:
            M3: [2.4, 5.5]
            M4: [3.2, 7.0]
"""

_BOLTS_BLT_NO_TABLE = """\
collection:
  name: Test Custom Parts
  description: Parts without parameter tables
  id: testcustom

classes:
  - id: TESTCUSTOM01
    description: A part with no table entries
    parameters:
      free: [x]
      types:
        x: Length
      defaults:
        x: 10
"""

_BOLTS_BLT_MULTI_CLASS = """\
collection:
  name: Test Fasteners Mix
  description: Multiple classes in one file
  id: testmix

classes:
  - id: TESTBOLT_A
    standard: [TEST-A]
    description: Class A bolt
    parameters:
      free: [d]
      types:
        d: Length
      defaults:
        d: M3
      tables:
        - index: d
          columns: [k]
          data:
            M3: [2.0]
            M5: [3.5]

  - id: TESTBOLT_B
    standard: [TEST-B]
    description: Class B bolt
    parameters:
      free: [d]
      types:
        d: Length
      defaults:
        d: M4
      tables:
        - index: d
          columns: [k]
          data:
            M4: [2.8]
            M6: [4.0]
"""


def _make_bolts_fixture(tmp_path: Path, content: str, filename: str = "hexbolts.blt") -> Path:
    """Create a minimal BOLTS-style data/ tree with one collection file."""
    data_dir = tmp_path / "data" / "fasteners"
    data_dir.mkdir(parents=True)
    col_file = data_dir / filename
    col_file.write_text(content, encoding="utf-8")
    return tmp_path


def _make_fc_fixture(tmp_path: Path) -> Path:
    """Create a minimal FreeCAD-library-style tree with mixed part files."""
    mech = tmp_path / "Mechanical"
    mech.mkdir()
    (mech / "Bracket_L50.FCStd").write_bytes(b"\x50\x4b\x03\x04")  # ZIP magic (FCStd)
    (mech / "Shaft_D10.step").write_text("ISO-10303-21;", encoding="utf-8")

    fasteners = tmp_path / "Fasteners" / "Bolts"
    fasteners.mkdir(parents=True)
    (fasteners / "HexBolt_M6x20.FCStd").write_bytes(b"\x50\x4b\x03\x04")
    (fasteners / "HexBolt_M8x30.stp").write_text("ISO-10303-21;", encoding="utf-8")

    (tmp_path / "README.md").write_text("# FreeCAD Library", encoding="utf-8")
    (tmp_path / "LICENSE").write_text("CC0", encoding="utf-8")
    return tmp_path


# ===========================================================================
# BOLTS adapter tests
# ===========================================================================

def test_bolts_missing_source_returns_empty():
    """adapt() on a non-existent directory returns [] without raising."""
    result = bolts_adapt(BOLTS_SRC, "/nonexistent/path/that/does/not/exist")
    assert result == []


def test_bolts_source_present_false_for_missing_dir(tmp_path):
    assert not bolts_source_present(tmp_path / "gone")


def test_bolts_source_present_false_for_empty_dir(tmp_path):
    """An existing but empty directory has no collections, so source_present=False."""
    assert not bolts_source_present(tmp_path)


def test_bolts_source_present_true_when_collection_exists(tmp_path):
    _make_bolts_fixture(tmp_path, _BOLTS_BLT_SIMPLE)
    assert bolts_source_present(tmp_path)


def test_bolts_empty_data_dir_returns_empty(tmp_path):
    """data/ dir exists but has no .blt/.yaml files → adapt returns []."""
    (tmp_path / "data" / "fasteners").mkdir(parents=True)
    result = bolts_adapt(BOLTS_SRC, tmp_path)
    assert result == []


def test_bolts_single_table_enumerates_all_rows(tmp_path):
    """One class with 4 rows yields exactly 4 parts."""
    _make_bolts_fixture(tmp_path, _BOLTS_BLT_SIMPLE)
    parts = bolts_adapt(BOLTS_SRC, tmp_path)
    assert len(parts) == 4, f"expected 4, got {len(parts)}: {[p.name for p in parts]}"


def test_bolts_part_names_include_size_key(tmp_path):
    """Part names embed the row key (M3, M4, M5, M6)."""
    _make_bolts_fixture(tmp_path, _BOLTS_BLT_SIMPLE)
    parts = bolts_adapt(BOLTS_SRC, tmp_path)
    names = {p.name for p in parts}
    for size in ("M3", "M4", "M5", "M6"):
        assert any(size in n for n in names), f"{size} not found in names {names}"


def test_bolts_part_names_include_standard_prefix(tmp_path):
    """Part names include the standard number as a prefix."""
    _make_bolts_fixture(tmp_path, _BOLTS_BLT_SIMPLE)
    parts = bolts_adapt(BOLTS_SRC, tmp_path)
    assert all("TEST ISO 4014" in p.name for p in parts), (
        f"standard not in name: {[p.name for p in parts]}"
    )


def test_bolts_multi_class_collection_covers_all_classes(tmp_path):
    """A collection file with two classes yields parts from both."""
    _make_bolts_fixture(tmp_path, _BOLTS_BLT_MULTI_CLASS, "mix.blt")
    parts = bolts_adapt(BOLTS_SRC, tmp_path)
    class_ids = {p.metadata.get("bolts_class_id") for p in parts}
    assert "TESTBOLT_A" in class_ids
    assert "TESTBOLT_B" in class_ids
    assert len(parts) == 4  # 2 + 2


def test_bolts_multi_collection_files_yields_parts_from_all(tmp_path):
    """Two collection files → parts from both."""
    data = tmp_path / "data" / "fasteners"
    data.mkdir(parents=True)
    (data / "bolts.blt").write_text(_BOLTS_BLT_SIMPLE, encoding="utf-8")
    (data / "nuts.blt").write_text(_BOLTS_BLT_NUTS, encoding="utf-8")
    parts = bolts_adapt(BOLTS_SRC, tmp_path)
    # 4 bolts + 2 nuts
    assert len(parts) == 6


def test_bolts_category_for_bolt_collection(tmp_path):
    """Parts from a bolt collection have a 'fastener' category."""
    _make_bolts_fixture(tmp_path, _BOLTS_BLT_SIMPLE)
    parts = bolts_adapt(BOLTS_SRC, tmp_path)
    for p in parts:
        assert "fastener" in p.category.lower() or p.category == "mechanical", p.category


def test_bolts_category_for_nut_collection(tmp_path):
    _make_bolts_fixture(tmp_path, _BOLTS_BLT_NUTS)
    parts = bolts_adapt(BOLTS_SRC, tmp_path)
    for p in parts:
        assert "fastener" in p.category.lower() or p.category == "mechanical", p.category


def test_bolts_provenance_metadata_populated(tmp_path):
    """Every part has source / upstream_url / upstream_ref in metadata."""
    _make_bolts_fixture(tmp_path, _BOLTS_BLT_SIMPLE)
    parts = bolts_adapt(BOLTS_SRC, tmp_path)
    assert parts
    for p in parts:
        assert p.metadata.get("source") == "bolts", p.metadata
        assert p.metadata.get("upstream_url") == BOLTS_SRC.git_url, p.metadata
        assert p.metadata.get("upstream_ref") == BOLTS_SRC.ref, p.metadata


def test_bolts_attribution_block_has_required_keys(tmp_path):
    """The embedded attribution block carries the canonical required keys."""
    _make_bolts_fixture(tmp_path, _BOLTS_BLT_SIMPLE)
    parts = bolts_adapt(BOLTS_SRC, tmp_path)
    required = {
        "source_project", "source_url", "license",
        "original_author", "retrieved_at",
    }
    for p in parts:
        a = p.metadata.get("attribution")
        assert a, f"{p.name}: missing attribution"
        missing = required - set(a)
        assert not missing, f"{p.name}: attribution missing {missing}"
        assert a["original_author"], f"{p.name}: blank original_author"
        assert a["source_project"] == "bolts", p.name


def test_bolts_attribution_text_non_empty(tmp_path):
    """Every part carries a human-readable attribution_text."""
    _make_bolts_fixture(tmp_path, _BOLTS_BLT_SIMPLE)
    parts = bolts_adapt(BOLTS_SRC, tmp_path)
    for p in parts:
        assert p.metadata.get("attribution_text"), f"{p.name}: no attribution_text"


def test_bolts_rel_path_stable_and_valid(tmp_path):
    """rel_path ends with .part, no empty path segments, includes source name."""
    _make_bolts_fixture(tmp_path, _BOLTS_BLT_SIMPLE)
    parts = bolts_adapt(BOLTS_SRC, tmp_path)
    for p in parts:
        assert p.rel_path.endswith(".part"), f"no .part: {p.rel_path}"
        segs = p.rel_path.split("/")
        assert all(segs), f"empty segment in {p.rel_path}"
        assert p.rel_path.startswith("bolts/"), p.rel_path


def test_bolts_content_hash_deterministic(tmp_path):
    """Two adapt() calls on the same fixture produce the same sorted hash list."""
    _make_bolts_fixture(tmp_path, _BOLTS_BLT_SIMPLE)
    h1 = sorted(p.ensure_hash() for p in bolts_adapt(BOLTS_SRC, tmp_path))
    h2 = sorted(p.ensure_hash() for p in bolts_adapt(BOLTS_SRC, tmp_path))
    assert h1 == h2
    assert all(h for h in h1), "hash must not be empty"


def test_bolts_idempotent_rerun(tmp_path):
    """Running adapt() twice returns identical part sets."""
    _make_bolts_fixture(tmp_path, _BOLTS_BLT_SIMPLE)
    run1 = bolts_adapt(BOLTS_SRC, tmp_path)
    run2 = bolts_adapt(BOLTS_SRC, tmp_path)
    assert len(run1) == len(run2)
    hashes1 = sorted(p.ensure_hash() for p in run1)
    hashes2 = sorted(p.ensure_hash() for p in run2)
    assert hashes1 == hashes2


def test_bolts_malformed_yaml_skipped_others_processed(tmp_path):
    """A malformed YAML file is skipped; other files in the tree still convert."""
    data = tmp_path / "data" / "fasteners"
    data.mkdir(parents=True)
    (data / "good.blt").write_text(_BOLTS_BLT_SIMPLE, encoding="utf-8")
    (data / "bad.blt").write_text("{ unclosed: [bracket", encoding="utf-8")
    parts = bolts_adapt(BOLTS_SRC, tmp_path)
    # The good file has 4 rows; the bad one is skipped.
    assert len(parts) == 4


def test_bolts_class_with_no_table_emits_placeholder(tmp_path):
    """A class that has no tables still produces exactly one placeholder part."""
    _make_bolts_fixture(tmp_path, _BOLTS_BLT_NO_TABLE)
    parts = bolts_adapt(BOLTS_SRC, tmp_path)
    assert len(parts) == 1
    assert parts[0].metadata.get("bolts_class_id") == "TESTCUSTOM01"


def test_bolts_emit_part_returns_kerfpart_with_provenance(tmp_path):
    """emit_part() is callable directly and returns an attributed KerfPart."""
    _make_bolts_fixture(tmp_path, _BOLTS_BLT_SIMPLE)
    part = bolts_emit_part(
        BOLTS_SRC, tmp_path,
        name="TEST ISO 4014 M6",
        category="fastener/bolt",
        collection_file="data/fasteners/hexbolts.blt",
    )
    assert part.name == "TEST ISO 4014 M6"
    assert part.content_hash
    assert part.metadata.get("attribution")
    assert part.metadata["attribution"]["original_author"]


def test_bolts_to_part_doc_matches_canonical_schema(tmp_path):
    """to_part_doc() returns all required keys of the canonical .part JSON."""
    _make_bolts_fixture(tmp_path, _BOLTS_BLT_SIMPLE)
    parts = bolts_adapt(BOLTS_SRC, tmp_path)
    assert parts
    doc = parts[0].to_part_doc()
    for key in ("version", "name", "description", "category", "manufacturer",
                "mpn", "value", "datasheet_url", "distributors", "metadata"):
        assert key in doc, f"missing canonical key: {key}"
    assert doc["version"] == 1
    assert doc["metadata"]["attribution"]


def test_bolts_discovers_yaml_extension_too(tmp_path):
    """discover_collections() also picks up .yaml files (not just .blt)."""
    data = tmp_path / "data" / "profiles"
    data.mkdir(parents=True)
    (data / "angle.yaml").write_text(_BOLTS_BLT_SIMPLE, encoding="utf-8")
    cols = discover_collections(tmp_path)
    assert any(p.suffix == ".yaml" for p in cols)


def test_bolts_rel_paths_unique_across_sizes(tmp_path):
    """Each concrete size gets a distinct rel_path (no collisions)."""
    _make_bolts_fixture(tmp_path, _BOLTS_BLT_SIMPLE)
    parts = bolts_adapt(BOLTS_SRC, tmp_path)
    paths = [p.rel_path for p in parts]
    assert len(paths) == len(set(paths)), f"duplicate rel_paths: {paths}"


# ===========================================================================
# FreeCAD-library adapter tests
# ===========================================================================

def test_fc_missing_source_returns_empty():
    result = fc_adapt(FC_SRC, "/nonexistent/freecad/checkout")
    assert result == []


def test_fc_source_present_false_for_missing(tmp_path):
    assert not fc_source_present(tmp_path / "gone")


def test_fc_source_present_false_for_empty(tmp_path):
    assert not fc_source_present(tmp_path)


def test_fc_source_present_true_when_parts_exist(tmp_path):
    _make_fc_fixture(tmp_path)
    assert fc_source_present(tmp_path)


def test_fc_enumerates_fcstd_files(tmp_path):
    """discover_part_files finds .FCStd files."""
    (tmp_path / "Part.FCStd").write_bytes(b"\x50\x4b\x03\x04")
    found = discover_part_files(tmp_path)
    assert any(p.suffix.lower() == ".fcstd" for p in found)


def test_fc_enumerates_step_stp_brep(tmp_path):
    """discover_part_files finds .step, .stp, and .brep files."""
    (tmp_path / "a.step").write_text("ISO", encoding="utf-8")
    (tmp_path / "b.stp").write_text("ISO", encoding="utf-8")
    (tmp_path / "c.brep").write_text("BRep", encoding="utf-8")
    found = {p.name for p in discover_part_files(tmp_path)}
    assert found == {"a.step", "b.stp", "c.brep"}


def test_fc_ignores_non_part_files(tmp_path):
    """Python scripts, markdown, text files are not enumerated as parts."""
    (tmp_path / "script.py").write_text("pass", encoding="utf-8")
    (tmp_path / "README.md").write_text("# hi", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("note", encoding="utf-8")
    (tmp_path / "Part.step").write_text("ISO", encoding="utf-8")
    found = discover_part_files(tmp_path)
    names = {p.name for p in found}
    assert names == {"Part.step"}


def test_fc_adapt_part_count_matches_file_count(tmp_path):
    """adapt() returns exactly one part per importable file."""
    _make_fc_fixture(tmp_path)
    files = discover_part_files(tmp_path)
    parts = fc_adapt(FC_SRC, tmp_path)
    assert len(parts) == len(files), (
        f"parts={len(parts)}, files={len(files)}: "
        f"files={[f.name for f in files]}, parts={[p.name for p in parts]}"
    )


def test_fc_name_derived_from_stem(tmp_path):
    """Part name uses the file stem (spaces replacing _ and -)."""
    (tmp_path / "Hex_Bolt_M6.step").write_text("ISO", encoding="utf-8")
    parts = fc_adapt(FC_SRC, tmp_path)
    assert parts
    assert any(
        w in parts[0].name for w in ("Hex", "Bolt", "M6")
    ), f"unexpected name: {parts[0].name}"


def test_fc_category_from_parent_folder(tmp_path):
    """Category reflects the parent folder name."""
    fasteners = tmp_path / "Fasteners"
    fasteners.mkdir()
    (fasteners / "bolt.step").write_text("ISO", encoding="utf-8")
    parts = fc_adapt(FC_SRC, tmp_path)
    assert parts
    assert "fastener" in parts[0].category.lower(), parts[0].category


def test_fc_category_fallback_mechanical(tmp_path):
    """Files in an unknown folder default to 'mechanical'."""
    misc = tmp_path / "Miscellaneous"
    misc.mkdir()
    (misc / "widget.FCStd").write_bytes(b"\x50\x4b\x03\x04")
    parts = fc_adapt(FC_SRC, tmp_path)
    assert parts[0].category == "mechanical"


def test_fc_provenance_metadata_populated(tmp_path):
    _make_fc_fixture(tmp_path)
    parts = fc_adapt(FC_SRC, tmp_path)
    assert parts
    for p in parts:
        assert p.metadata.get("source") == "freecad-library", p.metadata
        assert p.metadata.get("upstream_url") == FC_SRC.git_url
        assert p.metadata.get("upstream_ref") == FC_SRC.ref


def test_fc_attribution_block_non_empty(tmp_path):
    _make_fc_fixture(tmp_path)
    parts = fc_adapt(FC_SRC, tmp_path)
    required = {"source_project", "source_url", "license", "original_author", "retrieved_at"}
    for p in parts:
        a = p.metadata.get("attribution")
        assert a, f"{p.name}: missing attribution"
        missing = required - set(a)
        assert not missing, f"{p.name}: attribution missing {missing}"
        assert a["original_author"]


def test_fc_rel_path_includes_source_and_ends_with_part(tmp_path):
    _make_fc_fixture(tmp_path)
    parts = fc_adapt(FC_SRC, tmp_path)
    for p in parts:
        assert p.rel_path.startswith("freecad-library/"), p.rel_path
        assert p.rel_path.endswith(".part"), p.rel_path
        segs = p.rel_path.split("/")
        assert all(segs), f"empty segment in {p.rel_path}"


def test_fc_content_hash_deterministic(tmp_path):
    _make_fc_fixture(tmp_path)
    h1 = sorted(p.ensure_hash() for p in fc_adapt(FC_SRC, tmp_path))
    h2 = sorted(p.ensure_hash() for p in fc_adapt(FC_SRC, tmp_path))
    assert h1 == h2
    assert all(h for h in h1)


def test_fc_idempotent_rerun(tmp_path):
    _make_fc_fixture(tmp_path)
    run1 = fc_adapt(FC_SRC, tmp_path)
    run2 = fc_adapt(FC_SRC, tmp_path)
    assert len(run1) == len(run2)
    hashes1 = sorted(p.ensure_hash() for p in run1)
    hashes2 = sorted(p.ensure_hash() for p in run2)
    assert hashes1 == hashes2


def test_fc_emit_part_returns_attributed_kerfpart(tmp_path):
    _make_fc_fixture(tmp_path)
    part = fc_emit_part(
        FC_SRC, tmp_path,
        name="Bracket",
        category="mechanical",
        part_file="Mechanical/Bracket_L50.FCStd",
    )
    assert part.name == "Bracket"
    assert part.content_hash
    assert part.metadata.get("attribution")


def test_fc_multilevel_folder_category_and_relpath(tmp_path):
    """Files nested in Fasteners/Bolts get the bolt category, relpath preserves structure."""
    fasteners = tmp_path / "Fasteners" / "Bolts"
    fasteners.mkdir(parents=True)
    (fasteners / "HexM8x30.step").write_text("ISO", encoding="utf-8")
    parts = fc_adapt(FC_SRC, tmp_path)
    assert parts
    p = parts[0]
    assert "bolt" in p.category.lower() or "fastener" in p.category.lower(), p.category
    assert "Fasteners" in p.rel_path or "Bolts" in p.rel_path, p.rel_path


def test_fc_hidden_files_skipped(tmp_path):
    """Files inside hidden directories are not enumerated."""
    hidden = tmp_path / ".hidden"
    hidden.mkdir()
    (hidden / "part.step").write_text("ISO", encoding="utf-8")
    visible = tmp_path / "Visible"
    visible.mkdir()
    (visible / "part.step").write_text("ISO", encoding="utf-8")
    parts = fc_adapt(FC_SRC, tmp_path)
    assert len(parts) == 1
    assert "Visible" in parts[0].rel_path


def test_fc_macosx_entries_skipped(tmp_path):
    """__MACOSX archive artifacts are not enumerated."""
    mac = tmp_path / "__MACOSX"
    mac.mkdir()
    (mac / "part.step").write_text("ISO", encoding="utf-8")
    real = tmp_path / "Mechanical"
    real.mkdir()
    (real / "gear.step").write_text("ISO", encoding="utf-8")
    parts = fc_adapt(FC_SRC, tmp_path)
    assert len(parts) == 1
    assert "gear" in parts[0].rel_path.lower()


def test_fc_freecad_file_metadata_key(tmp_path):
    """Each part's metadata carries freecad_file pointing at the relative path."""
    mech = tmp_path / "Mechanical"
    mech.mkdir()
    (mech / "shaft.step").write_text("ISO", encoding="utf-8")
    parts = fc_adapt(FC_SRC, tmp_path)
    assert parts
    p = parts[0]
    assert p.metadata.get("freecad_file") == "Mechanical/shaft.step"
    assert p.metadata.get("freecad_format") == "step"


def test_fc_to_part_doc_matches_canonical_schema(tmp_path):
    mech = tmp_path / "Mechanical"
    mech.mkdir()
    (mech / "bracket.FCStd").write_bytes(b"\x50\x4b\x03\x04")
    parts = fc_adapt(FC_SRC, tmp_path)
    assert parts
    doc = parts[0].to_part_doc()
    for key in ("version", "name", "description", "category", "manufacturer",
                "mpn", "value", "datasheet_url", "distributors", "metadata"):
        assert key in doc, f"missing canonical key: {key}"
    assert doc["version"] == 1
    assert doc["metadata"]["attribution"]
