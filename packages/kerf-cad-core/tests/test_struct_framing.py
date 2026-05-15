"""
Tests for the structural grid + levels + framing layer.

Covers:
  - Grid: construction, label resolution, coordinate math
  - Level: construction, validation
  - Column: length from levels, mass calculation
  - Beam: length from grid points, mass calculation, zero-length error
  - Section catalog: lookup by name (exact + case variants)
  - framing_summary: tonnage rollup by section + grand total
  - Invalid grid label error paths (never raises)
  - Tool runner smoke tests (dict-in / dict-out via asyncio.run)

Pure-Python; hermetic; no OCC; no DB; no network.
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.struct.grid import StructGrid, Level, GridPoint, _label_to_x_index, _y_label_to_index
from kerf_cad_core.struct.framing import (
    Column,
    Beam,
    SECTION_CATALOG,
    SteelSection,
    get_section,
)
from kerf_cad_core.struct.tools import (
    _build_grid,
    _build_level,
    _resolve_column,
    _resolve_beam,
    framing_summary,
    run_struct_grid,
    run_struct_level,
    run_struct_column,
    run_struct_beam,
    run_struct_framing_summary,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx():
    """Minimal fake ProjectCtx for tool runner tests."""
    class _FakeCtx:
        pass
    return _FakeCtx()


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _call(runner, **kwargs) -> dict:
    raw = _run(runner(_ctx(), json.dumps(kwargs).encode()))
    return json.loads(raw)


# Canonical test grid: 3 X bays, 2 Y bays
# axes A,B,C,D at x=0,6000,14000,20000 (spacings 6000,8000,6000)
# axes 1,2,3   at y=0,5000,10000       (spacings 5000,5000)
GRID_SX = [6000.0, 8000.0, 6000.0]
GRID_SY = [5000.0, 5000.0]

# Levels
LEVEL_G   = Level("Ground",    0.0)
LEVEL_L1  = Level("L1",     4000.0)
LEVEL_L2  = Level("L2",     8000.0)
LEVEL_ROOF = Level("Roof", 12000.0)

LEVELS_DICT = {
    "Ground": {"name": "Ground",    "elevation_mm": 0.0},
    "L1":     {"name": "L1",        "elevation_mm": 4000.0},
    "L2":     {"name": "L2",        "elevation_mm": 8000.0},
    "Roof":   {"name": "Roof",      "elevation_mm": 12000.0},
}


def _make_grid():
    return StructGrid(spacing_x=GRID_SX, spacing_y=GRID_SY)


def _grid_dict():
    return _make_grid().to_dict()


# ===========================================================================
# 1. Grid label → index helpers
# ===========================================================================

def test_label_to_x_index_a():
    assert _label_to_x_index("A") == 0

def test_label_to_x_index_d():
    assert _label_to_x_index("D") == 3

def test_label_to_x_index_case_insensitive():
    assert _label_to_x_index("c") == 2

def test_label_to_x_index_invalid():
    assert _label_to_x_index("1") is None

def test_y_label_to_index_one():
    assert _y_label_to_index("1") == 0

def test_y_label_to_index_three():
    assert _y_label_to_index("3") == 2

def test_y_label_to_index_invalid():
    assert _y_label_to_index("X") is None


# ===========================================================================
# 2. StructGrid — construction + axis labels
# ===========================================================================

def test_grid_x_axis_labels():
    g = _make_grid()
    assert g.x_axis_labels == ["A", "B", "C", "D"]

def test_grid_y_axis_labels():
    g = _make_grid()
    assert g.y_axis_labels == ["1", "2", "3"]

def test_grid_x_coords_cumulative():
    g = _make_grid()
    assert g._x_coords == [0.0, 6000.0, 14000.0, 20000.0]

def test_grid_y_coords_cumulative():
    g = _make_grid()
    assert g._y_coords == [0.0, 5000.0, 10000.0]

def test_grid_to_dict_keys():
    d = _make_grid().to_dict()
    assert "spacing_x" in d and "spacing_y" in d
    assert "x_axes" in d and "y_axes" in d
    assert "x_coords_mm" in d and "y_coords_mm" in d

def test_grid_invalid_empty_spacing_x():
    with pytest.raises(ValueError, match="spacing_x"):
        StructGrid(spacing_x=[], spacing_y=[5000.0])

def test_grid_invalid_zero_spacing():
    with pytest.raises(ValueError):
        StructGrid(spacing_x=[0.0], spacing_y=[5000.0])

def test_grid_invalid_negative_spacing():
    with pytest.raises(ValueError):
        StructGrid(spacing_x=[-1000.0], spacing_y=[5000.0])


# ===========================================================================
# 3. Grid label → coordinate resolution
# ===========================================================================

def test_resolve_a1_is_origin():
    g = _make_grid()
    ok, pt, err = g.resolve("A/1")
    assert ok
    assert pt.x_mm == 0.0 and pt.y_mm == 0.0
    assert err is None

def test_resolve_b3():
    g = _make_grid()
    ok, pt, err = g.resolve("B/3")
    assert ok
    assert pt.x_mm == 6000.0
    assert pt.y_mm == 10000.0

def test_resolve_d2():
    g = _make_grid()
    ok, pt, err = g.resolve("D/2")
    assert ok
    assert pt.x_mm == 20000.0
    assert pt.y_mm == 5000.0

def test_resolve_case_insensitive():
    g = _make_grid()
    ok, pt, _ = g.resolve("b/2")
    assert ok
    assert pt.label == "B/2"

def test_resolve_canonical_label():
    g = _make_grid()
    _, pt, _ = g.resolve("c/1")
    assert pt.label == "C/1"

def test_resolve_invalid_format_returns_false():
    g = _make_grid()
    ok, pt, err = g.resolve("B3")   # missing slash
    assert not ok
    assert pt is None
    assert "Invalid grid label" in err

def test_resolve_out_of_range_x():
    g = _make_grid()
    ok, pt, err = g.resolve("E/1")   # only A–D defined
    assert not ok
    assert "out of range" in err.lower()

def test_resolve_out_of_range_y():
    g = _make_grid()
    ok, pt, err = g.resolve("A/4")   # only 1–3 defined
    assert not ok
    assert "out of range" in err.lower()

def test_resolve_all_intersections_count():
    g = _make_grid()
    pts = g.all_intersections()
    assert len(pts) == 4 * 3   # 4 X axes × 3 Y axes


# ===========================================================================
# 4. Level — construction + validation
# ===========================================================================

def test_level_ground():
    lev = Level("Ground", 0.0)
    assert lev.elevation_mm == 0.0

def test_level_negative_elevation():
    lev = Level("B1", -3500.0)
    assert lev.elevation_mm == -3500.0

def test_level_empty_name_raises():
    with pytest.raises(ValueError):
        Level("", 0.0)

def test_level_to_dict():
    lev = Level("L1", 4000.0)
    d = lev.to_dict()
    assert d == {"name": "L1", "elevation_mm": 4000.0}


# ===========================================================================
# 5. Section catalog
# ===========================================================================

def test_catalog_has_12_sections():
    assert len(SECTION_CATALOG) == 12

def test_get_section_ipe200():
    sec = get_section("IPE200")
    assert sec is not None
    assert sec.family == "IPE"
    assert sec.mass_kg_m == 22.4

def test_get_section_hea300():
    sec = get_section("HEA300")
    assert sec is not None
    assert sec.A_mm2 == 11250.0

def test_get_section_ub_356():
    sec = get_section("UB356x171x51")
    assert sec is not None
    assert sec.family == "UB"

def test_get_section_w14x68():
    sec = get_section("W14x68")
    assert sec is not None
    assert sec.Ix_mm4 == pytest.approx(576.5e6)

def test_get_section_unknown_returns_none():
    assert get_section("INVALID_SECTION") is None

def test_section_to_dict_keys():
    sec = get_section("IPE160")
    d = sec.to_dict()
    for key in ("name", "family", "A_mm2", "Ix_mm4", "Iy_mm4", "mass_kg_m"):
        assert key in d


# ===========================================================================
# 6. Column — length and mass
# ===========================================================================

def test_column_length_simple():
    g = _make_grid()
    _, pt, _ = g.resolve("B/2")
    sec = get_section("HEA200")
    col = Column("C1", "B/2", pt, sec, LEVEL_G, LEVEL_L1)
    assert col.length_mm == pytest.approx(4000.0)

def test_column_mass():
    g = _make_grid()
    _, pt, _ = g.resolve("A/1")
    sec = get_section("HEA200")   # 42.3 kg/m
    col = Column("C2", "A/1", pt, sec, LEVEL_G, LEVEL_L1)
    # length = 4000 mm = 4 m; mass = 4 × 42.3 = 169.2 kg
    assert col.mass_kg == pytest.approx(4.0 * 42.3, rel=1e-6)

def test_column_length_from_negative_base():
    g = _make_grid()
    _, pt, _ = g.resolve("A/1")
    sec = get_section("IPE200")
    base = Level("B1", -3000.0)
    top  = Level("G",    0.0)
    col = Column("C3", "A/1", pt, sec, base, top)
    assert col.length_mm == pytest.approx(3000.0)

def test_column_to_dict_type():
    g = _make_grid()
    _, pt, _ = g.resolve("C/2")
    sec = get_section("IPE360")
    col = Column("C4", "C/2", pt, sec, LEVEL_G, LEVEL_L1)
    d = col.to_dict()
    assert d["type"] == "column"
    assert d["length_mm"] == pytest.approx(4000.0)


# ===========================================================================
# 7. Beam — length and mass
# ===========================================================================

def test_beam_length_along_x():
    g = _make_grid()
    _, pt_a, _ = g.resolve("A/1")
    _, pt_b, _ = g.resolve("B/1")  # x: 0 → 6000, y same
    sec = get_section("IPE270")
    beam = Beam("BM1", "A/1", "B/1", pt_a, pt_b, sec, LEVEL_L1)
    assert beam.length_mm == pytest.approx(6000.0)

def test_beam_length_along_y():
    g = _make_grid()
    _, pt1, _ = g.resolve("A/1")
    _, pt2, _ = g.resolve("A/3")   # y: 0 → 10000
    sec = get_section("IPE270")
    beam = Beam("BM2", "A/1", "A/3", pt1, pt2, sec, LEVEL_L1)
    assert beam.length_mm == pytest.approx(10000.0)

def test_beam_length_diagonal():
    g = _make_grid()
    _, pt_a1, _ = g.resolve("A/1")  # (0, 0)
    _, pt_b2, _ = g.resolve("B/2")  # (6000, 5000)
    sec = get_section("IPE200")
    beam = Beam("BM3", "A/1", "B/2", pt_a1, pt_b2, sec, LEVEL_L1)
    expected = math.sqrt(6000**2 + 5000**2)
    assert beam.length_mm == pytest.approx(expected, rel=1e-6)

def test_beam_mass():
    g = _make_grid()
    _, pt_a, _ = g.resolve("A/2")
    _, pt_c, _ = g.resolve("C/2")   # x: 0 → 14000, y same
    sec = get_section("IPE270")    # 36.1 kg/m
    beam = Beam("BM4", "A/2", "C/2", pt_a, pt_c, sec, LEVEL_L1)
    expected_mass = (14000.0 / 1000.0) * 36.1
    assert beam.mass_kg == pytest.approx(expected_mass, rel=1e-6)

def test_beam_to_dict_type():
    g = _make_grid()
    _, pt_a, _ = g.resolve("A/1")
    _, pt_d, _ = g.resolve("D/1")
    sec = get_section("UB356x171x51")
    beam = Beam("BM5", "A/1", "D/1", pt_a, pt_d, sec, LEVEL_ROOF)
    d = beam.to_dict()
    assert d["type"] == "beam"
    assert d["level"] == "Roof"


# ===========================================================================
# 8. _build_grid / _build_level helpers
# ===========================================================================

def test_build_grid_ok():
    ok, grid, errors = _build_grid([6000], [5000])
    assert ok
    assert errors == []
    assert grid._x_coords == [0.0, 6000.0]

def test_build_grid_bad_type():
    ok, grid, errors = _build_grid(["notanumber"], [5000])
    assert not ok
    assert errors

def test_build_level_ok():
    ok, lev, errors = _build_level("L1", 4000.0)
    assert ok
    assert lev.elevation_mm == 4000.0

def test_build_level_empty_name():
    ok, lev, errors = _build_level("", 0.0)
    assert not ok
    assert errors

def test_build_level_bad_elev():
    ok, lev, errors = _build_level("L1", "bad")
    assert not ok


# ===========================================================================
# 9. framing_summary — tonnage rollup
# ===========================================================================

def _make_members():
    """Return two columns (HEA200) + two beams (IPE270) for summary tests."""
    g = _make_grid()
    sec_col = get_section("HEA200")
    sec_bm  = get_section("IPE270")

    _, p1, _ = g.resolve("A/1")
    _, p2, _ = g.resolve("B/1")
    _, p3, _ = g.resolve("A/2")
    _, p4, _ = g.resolve("B/2")

    col1 = Column("C1", "A/1", p1, sec_col, LEVEL_G, LEVEL_L1)
    col2 = Column("C2", "B/1", p2, sec_col, LEVEL_G, LEVEL_L1)
    bm1  = Beam("BM1", "A/1", "B/1", p1, p2, sec_bm, LEVEL_L1)
    bm2  = Beam("BM2", "A/2", "B/2", p3, p4, sec_bm, LEVEL_L1)

    return [col1.to_dict(), col2.to_dict(), bm1.to_dict(), bm2.to_dict()]


def test_summary_total_members():
    members = _make_members()
    s = framing_summary(members)
    assert s["total_members"] == 4

def test_summary_column_count():
    members = _make_members()
    s = framing_summary(members)
    assert s["by_type"]["columns"]["count"] == 2

def test_summary_beam_count():
    members = _make_members()
    s = framing_summary(members)
    assert s["by_type"]["beams"]["count"] == 2

def test_summary_by_section_keys():
    members = _make_members()
    s = framing_summary(members)
    section_names = {r["section"] for r in s["by_section"]}
    assert "HEA200" in section_names
    assert "IPE270" in section_names

def test_summary_hea200_count():
    members = _make_members()
    s = framing_summary(members)
    hea = next(r for r in s["by_section"] if r["section"] == "HEA200")
    assert hea["count"] == 2

def test_summary_total_mass_kg():
    members = _make_members()
    s = framing_summary(members)
    # 2 columns: 4 m × 42.3 kg/m × 2 = 338.4 kg
    # 2 beams:   6 m × 36.1 kg/m × 2 = 433.2 kg
    expected = 2 * 4.0 * 42.3 + 2 * 6.0 * 36.1
    assert s["total_mass_kg"] == pytest.approx(expected, rel=1e-4)

def test_summary_total_mass_t():
    members = _make_members()
    s = framing_summary(members)
    assert s["total_mass_t"] == pytest.approx(s["total_mass_kg"] / 1000.0, rel=1e-6)

def test_summary_empty():
    s = framing_summary([])
    assert s["total_members"] == 0
    assert s["total_mass_kg"] == 0.0
    assert s["by_section"] == []


# ===========================================================================
# 10. Tool runners — struct_grid
# ===========================================================================

def test_tool_grid_ok():
    r = _call(run_struct_grid, spacing_x=[6000, 8000], spacing_y=[5000])
    assert r["ok"] is True
    assert r["grid"]["x_axes"] == ["A", "B", "C"]
    assert r["grid"]["y_axes"] == ["1", "2"]

def test_tool_grid_invalid_spacing():
    r = _call(run_struct_grid, spacing_x=[-100], spacing_y=[5000])
    assert r["ok"] is False
    assert r["errors"]

def test_tool_grid_missing_spacing_y():
    r = _call(run_struct_grid, spacing_x=[6000])
    assert r["ok"] is False


# ===========================================================================
# 11. Tool runners — struct_level
# ===========================================================================

def test_tool_level_ok():
    r = _call(run_struct_level, name="L1", elevation_mm=4000)
    assert r["ok"] is True
    assert r["level"]["elevation_mm"] == 4000.0

def test_tool_level_empty_name():
    r = _call(run_struct_level, name="", elevation_mm=0)
    assert r["ok"] is False

def test_tool_level_negative_elevation():
    r = _call(run_struct_level, name="Basement", elevation_mm=-3500)
    assert r["ok"] is True
    assert r["level"]["elevation_mm"] == -3500.0


# ===========================================================================
# 12. Tool runners — struct_column
# ===========================================================================

def test_tool_column_ok():
    r = _call(
        run_struct_column,
        id="C-B2", grid_label="B/2", section="HEA200",
        base_level="Ground", top_level="L1",
        grid=_grid_dict(), levels=LEVELS_DICT,
    )
    assert r["ok"] is True
    col = r["column"]
    assert col["grid_label"] == "B/2"
    assert col["length_mm"] == pytest.approx(4000.0)
    assert col["mass_kg"] == pytest.approx(4.0 * 42.3)

def test_tool_column_invalid_grid_label():
    r = _call(
        run_struct_column,
        id="C-Z9", grid_label="Z/9", section="HEA200",
        base_level="Ground", top_level="L1",
        grid=_grid_dict(), levels=LEVELS_DICT,
    )
    assert r["ok"] is False
    assert r["errors"]

def test_tool_column_unknown_section():
    r = _call(
        run_struct_column,
        id="C-A1", grid_label="A/1", section="BOGUS_SECTION",
        base_level="Ground", top_level="L1",
        grid=_grid_dict(), levels=LEVELS_DICT,
    )
    assert r["ok"] is False
    assert any("section" in e.lower() or "BOGUS" in e for e in r["errors"])

def test_tool_column_same_level_error():
    r = _call(
        run_struct_column,
        id="C-A1-same", grid_label="A/1", section="HEA200",
        base_level="Ground", top_level="Ground",
        grid=_grid_dict(), levels=LEVELS_DICT,
    )
    assert r["ok"] is False

def test_tool_column_missing_level():
    r = _call(
        run_struct_column,
        id="C-A1", grid_label="A/1", section="HEA200",
        base_level="Ground", top_level="NonExistentLevel",
        grid=_grid_dict(), levels=LEVELS_DICT,
    )
    assert r["ok"] is False


# ===========================================================================
# 13. Tool runners — struct_beam
# ===========================================================================

def test_tool_beam_ok():
    r = _call(
        run_struct_beam,
        id="BM-A1-B1", start="A/1", end="B/1", section="IPE270",
        level="L1", grid=_grid_dict(), levels=LEVELS_DICT,
    )
    assert r["ok"] is True
    bm = r["beam"]
    assert bm["length_mm"] == pytest.approx(6000.0)
    assert bm["mass_kg"] == pytest.approx(6.0 * 36.1)

def test_tool_beam_zero_length_error():
    r = _call(
        run_struct_beam,
        id="BM-same", start="A/1", end="A/1", section="IPE270",
        level="L1", grid=_grid_dict(), levels=LEVELS_DICT,
    )
    assert r["ok"] is False
    assert any("zero" in e.lower() or "same" in e.lower() for e in r["errors"])

def test_tool_beam_invalid_start_label():
    r = _call(
        run_struct_beam,
        id="BM-bad", start="Z/9", end="A/1", section="IPE270",
        level="L1", grid=_grid_dict(), levels=LEVELS_DICT,
    )
    assert r["ok"] is False

def test_tool_beam_missing_level():
    r = _call(
        run_struct_beam,
        id="BM-a", start="A/1", end="B/1", section="IPE270",
        level="MissingLevel", grid=_grid_dict(), levels=LEVELS_DICT,
    )
    assert r["ok"] is False


# ===========================================================================
# 14. Tool runners — struct_framing_summary
# ===========================================================================

def test_tool_summary_ok():
    members = _make_members()
    r = _call(run_struct_framing_summary, members=members)
    assert r["ok"] is True
    assert r["total_members"] == 4
    assert r["total_mass_t"] > 0

def test_tool_summary_empty():
    r = _call(run_struct_framing_summary, members=[])
    assert r["ok"] is True
    assert r["total_members"] == 0
    assert r["total_mass_kg"] == 0.0

def test_tool_summary_missing_members():
    r = _call(run_struct_framing_summary)
    # missing required arg — should return error payload
    data = r
    assert "error" in data or data.get("ok") is False
