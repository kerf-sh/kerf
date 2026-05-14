"""
Tests for the KiCad Tier 2 library import (pyworker /import-kicad-library).

Fixtures:
  tests/fixtures/Device.kicad_sym          — one resistor symbol ("R")
  tests/fixtures/Resistor_SMD.pretty/
    R_0805_2012Metric.kicad_mod            — 0805 footprint with 2 pads + 1 STEP ref

Assertions:
  - Symbol "R" produces one Library Part with schematic_symbol.pins populated
  - Footprint "R_0805_2012Metric" produces one Library Part with
    pcb_footprint.pads populated and model_3d_paths non-empty
  - Idempotent re-run: content_hash identical on second call → no-op at Go layer
"""

import hashlib
import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def kiutils_available():
    try:
        import kiutils  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Import the route module directly (no HTTP server needed)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def import_kicad_library_module(kiutils_available):
    if not kiutils_available:
        pytest.skip("kiutils not installed")
    import importlib, sys
    # Ensure pyworker package root is on path
    import os
    from kerf_imports.kicad_library import (
        _parse_sym_files,
        _parse_mod_files,
    )
    return {"parse_sym": _parse_sym_files, "parse_mod": _parse_mod_files}


# ---------------------------------------------------------------------------
# Symbol library parsing
# ---------------------------------------------------------------------------

def test_symbol_produces_part(import_kicad_library_module):
    parse_sym = import_kicad_library_module["parse_sym"]
    parts = []
    warnings, errors = parse_sym(FIXTURES, parts)

    assert errors == [], f"unexpected errors: {errors}"

    sym_parts = [p for p in parts if p["schematic_symbol"] is not None]
    assert len(sym_parts) >= 1, "expected at least one symbol part"

    # Find the resistor "R"
    r_parts = [p for p in sym_parts if p["schematic_symbol"]["entry_name"] == "R"]
    assert len(r_parts) == 1, "expected exactly one 'R' symbol"
    r = r_parts[0]

    assert r["category"] == "electronic"
    assert r["content_hash"] != ""

    sym = r["schematic_symbol"]
    assert sym["library"] == "Device"
    assert sym["entry_name"] == "R"
    # The resistor has 2 pins (1 and 2)
    assert sym["pin_count"] >= 2, f"expected >=2 pins, got {sym['pin_count']}"
    pins = sym["pins"]
    pin_numbers = {p["number"] for p in pins}
    assert "1" in pin_numbers, "expected pin '1'"
    assert "2" in pin_numbers, "expected pin '2'"
    for pin in pins:
        assert pin["electrical_type"] != "", "pin electrical_type should not be empty"


def test_symbol_hash_deterministic(import_kicad_library_module):
    parse_sym = import_kicad_library_module["parse_sym"]
    parts1 = []
    parts2 = []
    parse_sym(FIXTURES, parts1)
    parse_sym(FIXTURES, parts2)

    hashes1 = {p["content_hash"] for p in parts1}
    hashes2 = {p["content_hash"] for p in parts2}
    assert hashes1 == hashes2, "content hashes must be deterministic across runs"


# ---------------------------------------------------------------------------
# Footprint library parsing
# ---------------------------------------------------------------------------

def test_footprint_produces_part(import_kicad_library_module):
    parse_mod = import_kicad_library_module["parse_mod"]
    parts = []
    warnings, errors = parse_mod(FIXTURES, parts)

    assert errors == [], f"unexpected errors: {errors}"

    fp_parts = [p for p in parts if p["pcb_footprint"] is not None]
    assert len(fp_parts) >= 1, "expected at least one footprint part"

    r0805 = next(
        (p for p in fp_parts if p["pcb_footprint"]["entry_name"] == "R_0805_2012Metric"),
        None,
    )
    assert r0805 is not None, "expected R_0805_2012Metric footprint part"

    assert r0805["category"] == "electronic"
    assert r0805["content_hash"] != ""

    fp = r0805["pcb_footprint"]
    # kiutils uses mod_file.parent.stem which strips the ".pretty" suffix.
    assert fp["library"] == "Resistor_SMD"
    assert fp["pad_count"] == 2
    assert len(fp["pads"]) == 2

    pad_numbers = {p["number"] for p in fp["pads"]}
    assert "1" in pad_numbers
    assert "2" in pad_numbers

    for pad in fp["pads"]:
        assert pad["type"] in ("smd", "thru_hole", "np_thru_hole", "connect")
        assert pad["shape"] != ""
        assert "x" in pad["position"]
        assert "x" in pad["size"]


def test_footprint_3d_model_path(import_kicad_library_module):
    parse_mod = import_kicad_library_module["parse_mod"]
    parts = []
    parse_mod(FIXTURES, parts)

    r0805 = next(
        (p for p in parts if p.get("pcb_footprint", {}).get("entry_name") == "R_0805_2012Metric"),
        None,
    )
    assert r0805 is not None
    paths = r0805["model_3d_paths"]
    assert len(paths) >= 1, "expected at least one 3D model path"
    assert any("R_0805_2012Metric" in p for p in paths), (
        f"expected R_0805_2012Metric in model paths, got {paths}"
    )


def test_footprint_hash_deterministic(import_kicad_library_module):
    parse_mod = import_kicad_library_module["parse_mod"]
    parts1 = []
    parts2 = []
    parse_mod(FIXTURES, parts1)
    parse_mod(FIXTURES, parts2)

    hashes1 = {p["content_hash"] for p in parts1}
    hashes2 = {p["content_hash"] for p in parts2}
    assert hashes1 == hashes2


# ---------------------------------------------------------------------------
# Idempotency: content_hash is stable — the Go layer deduplicates on it
# ---------------------------------------------------------------------------

def test_footprint_content_hash_matches_file(import_kicad_library_module):
    """
    The footprint content_hash must equal sha256 of the raw .kicad_mod text,
    which is what the Go import_kicad_library tool uses for dedup.
    """
    parse_mod = import_kicad_library_module["parse_mod"]
    parts = []
    parse_mod(FIXTURES, parts)

    r0805 = next(
        (p for p in parts if p.get("pcb_footprint", {}).get("entry_name") == "R_0805_2012Metric"),
        None,
    )
    assert r0805 is not None

    mod_file = FIXTURES / "Resistor_SMD.pretty" / "R_0805_2012Metric.kicad_mod"
    raw = mod_file.read_text(encoding="utf-8", errors="replace")
    expected_hash = hashlib.sha256(raw.encode()).hexdigest()
    assert r0805["content_hash"] == expected_hash, (
        f"footprint hash mismatch: got {r0805['content_hash']}, expected {expected_hash}"
    )
