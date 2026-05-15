"""Scaffold adapters (bolts, freecad_library): the registry interface is
implemented and discovery works on a fake tree. Conversion is a documented
TODO and returns []. Hermetic.
"""
from pathlib import Path

from kerf_parts.adapters import adapter_keys, get_adapter
from kerf_parts.adapters.bolts import adapt as bolts_adapt
from kerf_parts.adapters.bolts import discover_collections
from kerf_parts.adapters.freecad_library import adapt as fc_adapt
from kerf_parts.adapters.freecad_library import discover_part_files
from kerf_parts.manifest import Source

BOLTS = Source("bolts", "https://github.com/boltsparts/BOLTS.git", "v0.4.1",
                "LGPL-2.1-or-later", "bolts-blt", "bolts")
FC = Source("freecad-library", "https://github.com/FreeCAD/FreeCAD-library.git",
            "master", "mixed", "freecad-fcstd-step", "freecad_library")


def test_all_manifest_adapters_are_registered():
    keys = set(adapter_keys())
    assert {"kicad", "kicad3d", "bolts", "freecad_library"} <= keys
    for k in keys:
        assert callable(get_adapter(k))


def test_bolts_scaffold_returns_empty_but_callable(tmp_path):
    assert bolts_adapt(BOLTS, tmp_path) == []


def test_bolts_discovers_collection_files(tmp_path):
    d = tmp_path / "data" / "fasteners"
    d.mkdir(parents=True)
    (d / "hexbolt.blt").write_text("collection", encoding="utf-8")
    (d / "nuts.yaml").write_text("a: 1", encoding="utf-8")
    found = {p.name for p in discover_collections(tmp_path)}
    assert {"hexbolt.blt", "nuts.yaml"} <= found


def test_freecad_scaffold_returns_empty_but_callable(tmp_path):
    assert fc_adapt(FC, tmp_path) == []


def test_freecad_discovers_part_files(tmp_path):
    (tmp_path / "Mechanical").mkdir()
    (tmp_path / "Mechanical" / "bracket.FCStd").write_bytes(b"\0")
    (tmp_path / "Mechanical" / "gear.step").write_text("ISO-10303", encoding="utf-8")
    (tmp_path / "README.md").write_text("ignore me", encoding="utf-8")
    found = {p.name for p in discover_part_files(tmp_path)}
    assert found == {"bracket.FCStd", "gear.step"}
