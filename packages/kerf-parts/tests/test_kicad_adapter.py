"""KiCad adapter conversion against the existing kerf-imports fixtures
(copied into this package's tests/fixtures/). Asserts symbols + footprints
convert into Kerf-native part docs. Hermetic — no network.
"""
from pathlib import Path

import pytest

from kerf_parts.adapters import get_adapter
from kerf_parts.adapters.kicad import KiCadUnavailable, adapt, adapt_packages3d
from kerf_parts.manifest import Source

FIXTURES = Path(__file__).parent / "fixtures"

SRC = Source(
    "kicad-symbols",
    "https://gitlab.com/kicad/libraries/kicad-symbols.git",
    "9.0.9",
    "CC-BY-SA-4.0 WITH KiCad-Library-Exception",
    "kicad-sym",
    "kicad",
)


@pytest.fixture(scope="module")
def kiutils_available():
    try:
        import kiutils  # noqa: F401

        return True
    except ImportError:
        return False


def _require(kiutils_available):
    if not kiutils_available:
        pytest.skip("kiutils not installed")


def test_registry_maps_keys():
    assert get_adapter("kicad") is adapt
    assert get_adapter("kicad3d") is adapt_packages3d
    with pytest.raises(KeyError):
        get_adapter("does-not-exist")


def test_symbol_and_footprint_convert(kiutils_available):
    _require(kiutils_available)
    parts = adapt(SRC, FIXTURES)
    assert parts, "expected converted parts from the fixtures dir"

    # The resistor symbol "R"
    syms = [p for p in parts if p.schematic_symbol is not None]
    r = next(
        (p for p in syms if p.schematic_symbol["entry_name"] == "R"), None
    )
    assert r is not None
    assert r.category == "electronic"
    assert r.schematic_symbol["pin_count"] >= 2
    assert r.content_hash, "content hash must be set for incremental seeding"
    # provenance metadata threaded through from the manifest source
    assert r.metadata["source"] == "kicad-symbols"
    assert r.metadata["upstream_ref"] == "9.0.9"
    # in-library path is stable + .part
    assert r.rel_path.startswith("kicad-symbols/Symbols/Device/")
    assert r.rel_path.endswith(".part")

    # The 0805 footprint
    fps = [p for p in parts if p.pcb_footprint is not None]
    fp = next(
        (p for p in fps if p.pcb_footprint["entry_name"] == "R_0805_2012Metric"),
        None,
    )
    assert fp is not None
    assert fp.pcb_footprint["pad_count"] == 2
    assert fp.model_3d_paths, "footprint should carry its 3D model reference"
    assert fp.rel_path.startswith("kicad-symbols/Footprints/Resistor_SMD/")


def test_to_part_doc_is_native_part_json(kiutils_available):
    _require(kiutils_available)
    parts = adapt(SRC, FIXTURES)
    r = next(p for p in parts if (p.schematic_symbol or {}).get("entry_name") == "R")
    doc = r.to_part_doc()
    # Matches the canonical .part shape written by kerf_api scaffold.run_create_part
    for key in (
        "version", "name", "description", "category", "manufacturer",
        "mpn", "value", "datasheet_url", "distributors", "metadata",
    ):
        assert key in doc, f"missing canonical .part key: {key}"
    assert doc["version"] == 1
    # plus the electronic sub-objects kerf_imports.kicad_library emits
    assert doc["schematic_symbol"]["entry_name"] == "R"


def test_conversion_is_deterministic(kiutils_available):
    _require(kiutils_available)
    h1 = sorted(p.ensure_hash() for p in adapt(SRC, FIXTURES))
    h2 = sorted(p.ensure_hash() for p in adapt(SRC, FIXTURES))
    assert h1 == h2


def test_packages3d_adapter_is_noop():
    src3d = Source("kicad-packages3D", "https://e/p.git", "9.0.9", "CC",
                    "step-wrl", "kicad3d", heavy=True)
    assert adapt_packages3d(src3d, FIXTURES) == []


def test_kicad_unavailable_is_typed(monkeypatch):
    # Simulate kiutils missing -> adapter raises a clear typed error.
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "kiutils":
            raise ImportError("No module named 'kiutils'")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(KiCadUnavailable):
        adapt(SRC, FIXTURES)
