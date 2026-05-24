"""GK-P17 tests — hem_sheet / jog_sheet / multi_flange.

Each function must emit a valid unfoldable body (carries __sheet_metal__
metadata with a sensible flat_length or total_flat_length).

Oracle contract
---------------
* hem_sheet:  total_flat_length > flat_length of the base bent body.
* jog_sheet:  total_flat_length > existing_flat by exactly 2*BA + step_length.
* multi_flange: operations list length == len(bend_specs); total_flat_length
  is the developed length after all bends.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from kerf_cad_core.geom.sheet_metal import (
    K_FACTOR_TABLE,
    bend_allowance,
    bend_sheet,
    unfold_sheet,
    hem_sheet,
    jog_sheet,
    multi_flange,
)
from kerf_cad_core.geom.brep import Body, Shell, Face, Loop, Coedge, Edge, Line3, Vertex, Plane, _unit


# ---------------------------------------------------------------------------
# Fixture: a simple planar sheet body (flat, lies in XY, thickness = 2 mm)
# ---------------------------------------------------------------------------

def _make_flat_sheet(length: float = 100.0, width: float = 50.0, thickness: float = 2.0) -> Body:
    """Return a minimal flat-sheet Body that bend_sheet can consume."""
    from kerf_cad_core.geom.brep import (
        Body, Shell, Face, Loop, Coedge, Edge, Line3, Vertex, Plane, _unit
    )
    import numpy as np
    corners = [
        np.array([0.0, 0.0, 0.0]),
        np.array([length, 0.0, 0.0]),
        np.array([length, width, 0.0]),
        np.array([0.0, width, 0.0]),
    ]
    # Top face (z = thickness)
    top = [c + np.array([0, 0, thickness]) for c in corners]
    p0, p1, p2, p3 = corners
    t0, t1, t2, t3 = top

    tol = 1e-7
    v0, v1, v2, v3 = Vertex(p0, tol), Vertex(p1, tol), Vertex(p2, tol), Vertex(p3, tol)
    e01 = Edge(Line3(p0, p1), 0.0, 1.0, v0, v1, tol)
    e12 = Edge(Line3(p1, p2), 0.0, 1.0, v1, v2, tol)
    e23 = Edge(Line3(p2, p3), 0.0, 1.0, v2, v3, tol)
    e30 = Edge(Line3(p3, p0), 0.0, 1.0, v3, v0, tol)
    coedges = [Coedge(e01, True), Coedge(e12, True), Coedge(e23, True), Coedge(e30, True)]
    loop = Loop(coedges, is_outer=True)
    plane = Plane(origin=p0, x_axis=_unit(p1 - p0), y_axis=_unit(p3 - p0))
    face = Face(plane, [loop], orientation=True, tol=tol)
    # Add a top face to give the body z-extent so thickness > 0
    vt0, vt1, vt2, vt3 = Vertex(t0, tol), Vertex(t1, tol), Vertex(t2, tol), Vertex(t3, tol)
    te01 = Edge(Line3(t0, t1), 0.0, 1.0, vt0, vt1, tol)
    te12 = Edge(Line3(t1, t2), 0.0, 1.0, vt1, vt2, tol)
    te23 = Edge(Line3(t2, t3), 0.0, 1.0, vt2, vt3, tol)
    te30 = Edge(Line3(t3, t0), 0.0, 1.0, vt3, vt0, tol)
    tcoedges = [Coedge(te01, True), Coedge(te12, True), Coedge(te23, True), Coedge(te30, True)]
    tloop = Loop(tcoedges, is_outer=True)
    tplane = Plane(origin=t0, x_axis=_unit(t1 - t0), y_axis=_unit(t3 - t0))
    tface = Face(tplane, [tloop], orientation=True, tol=tol)
    shell = Shell([face, tface], is_closed=False)
    return Body(shells=[shell])


def _make_bent(
    length: float = 100.0,
    width: float = 50.0,
    thickness: float = 2.0,
    bend_line: float = 60.0,
    angle_deg: float = 90.0,
    radius: float = 3.0,
    k_factor: float = 0.44,
) -> Body:
    """Make a bent body using bend_sheet."""
    flat = _make_flat_sheet(length, width, thickness)
    return bend_sheet(flat, bend_line, math.radians(angle_deg), radius, k_factor=k_factor)


# ===========================================================================
# Tests: hem_sheet
# ===========================================================================

class TestHemSheet:
    def _bent(self):
        return _make_bent()

    def test_returns_body(self):
        b = hem_sheet(self._bent())
        assert isinstance(b, Body)

    def test_metadata_type_hemmed(self):
        b = hem_sheet(self._bent())
        meta = b.__sheet_metal__
        assert meta["type"] == "hemmed"

    def test_total_flat_longer_than_base(self):
        """total_flat_length must exceed the base bent flat length."""
        bent = self._bent()
        base_meta = bent.__sheet_metal__
        base_flat = (
            base_meta["flange1_length"]
            + base_meta["bend_allowance"]
            + base_meta["flange2_length"]
        )
        hemmed = hem_sheet(bent)
        assert hemmed.__sheet_metal__["total_flat_length"] > base_flat

    def test_hem_flat_length_positive(self):
        b = hem_sheet(self._bent())
        assert b.__sheet_metal__["hem_flat_length"] > 0

    # --- closed hem ---
    def test_closed_hem_gap_zero(self):
        b = hem_sheet(self._bent(), style="closed", gap=5.0)  # gap forced to 0
        assert b.__sheet_metal__["hem_gap"] == 0.0

    def test_closed_style_stored(self):
        b = hem_sheet(self._bent(), style="closed")
        assert b.__sheet_metal__["hem_style"] == "closed"

    # --- open hem ---
    def test_open_hem_gap_preserved(self):
        b = hem_sheet(self._bent(), style="open", gap=2.0)
        assert b.__sheet_metal__["hem_gap"] == 2.0

    def test_open_hem_total_flat_larger_than_closed(self):
        bent = self._bent()
        closed = hem_sheet(bent, style="closed")
        open_ = hem_sheet(bent, style="open", gap=3.0)
        assert open_.__sheet_metal__["total_flat_length"] > closed.__sheet_metal__["total_flat_length"]

    # --- teardrop hem ---
    def test_teardrop_default_gap_equals_thickness(self):
        thickness = 2.0
        bent = _make_bent(thickness=thickness)
        b = hem_sheet(bent, style="teardrop")
        assert abs(b.__sheet_metal__["hem_gap"] - thickness) < 1e-9

    def test_teardrop_style_stored(self):
        b = hem_sheet(self._bent(), style="teardrop")
        assert b.__sheet_metal__["hem_style"] == "teardrop"

    # --- oracle: 180° BA ---
    def test_hem_ba_equals_pi_times_neutral_radius(self):
        """hem BA = π * (radius + k_factor * thickness)."""
        thickness = 2.0
        radius = thickness / 2.0
        kf = 0.44
        bent = _make_bent(thickness=thickness)
        b = hem_sheet(bent, radius=radius, k_factor=kf)
        expected_ba = math.pi * (radius + kf * thickness)
        stored_hem_flat = b.__sheet_metal__["hem_flat_length"]
        # hem_flat_length = hem_ba + hem_return; at closed style hem_return = thickness
        hem_ba_recovered = stored_hem_flat - (b.__sheet_metal__["hem_gap"] + thickness)
        assert abs(hem_ba_recovered - expected_ba) < 1e-6

    # --- invalid inputs ---
    def test_invalid_style_raises(self):
        with pytest.raises(ValueError, match="style"):
            hem_sheet(self._bent(), style="hammered")

    def test_negative_gap_raises(self):
        with pytest.raises(ValueError, match="gap"):
            hem_sheet(self._bent(), style="open", gap=-1.0)

    def test_non_bent_body_raises(self):
        flat = _make_flat_sheet()
        flat.__sheet_metal__ = {"type": "flat", "thickness": 2.0, "width": 50.0}
        with pytest.raises(ValueError, match="bent"):
            hem_sheet(flat)

    def test_no_metadata_raises(self):
        flat = _make_flat_sheet()
        with pytest.raises(ValueError):
            hem_sheet(flat)

    def test_zero_radius_raises(self):
        with pytest.raises(ValueError, match="radius"):
            hem_sheet(self._bent(), radius=0.0)


# ===========================================================================
# Tests: jog_sheet
# ===========================================================================

class TestJogSheet:
    def _base(self):
        flat = _make_flat_sheet(100.0, 50.0, 2.0)
        flat.__sheet_metal__ = {
            "type": "flat",
            "thickness": 2.0,
            "width": 50.0,
            "flat_length": 100.0,
            "flange1_length": 0.0,
            "bend_allowance": 0.0,
            "flange2_length": 100.0,
        }
        return flat

    def test_returns_body(self):
        b = jog_sheet(self._base(), offset=5.0, radius=2.0)
        assert isinstance(b, Body)

    def test_metadata_type_jogged(self):
        b = jog_sheet(self._base(), offset=5.0, radius=2.0)
        assert b.__sheet_metal__["type"] == "jogged"

    def test_offset_stored(self):
        b = jog_sheet(self._base(), offset=7.5, radius=2.0)
        assert abs(b.__sheet_metal__["offset"] - 7.5) < 1e-9

    def test_total_flat_longer_than_base(self):
        base = self._base()
        b = jog_sheet(base, offset=5.0, radius=2.0)
        assert b.__sheet_metal__["total_flat_length"] > 100.0

    def test_jog_ba_positive(self):
        b = jog_sheet(self._base(), offset=5.0, radius=2.0)
        assert b.__sheet_metal__["jog_ba"] > 0

    def test_oracle_flat_length(self):
        """Oracle: total_flat = base_flat + 2*jog_ba + step_length."""
        offset = 5.0
        radius = 2.0
        kf = 0.44
        thickness = 2.0
        jog_angle = math.pi / 2
        expected_ba = bend_allowance(jog_angle, radius, thickness, kf)
        step_length = offset / math.sin(jog_angle)
        expected_total = 100.0 + 2 * expected_ba + step_length
        b = jog_sheet(self._base(), offset=offset, jog_angle_rad=jog_angle, radius=radius, k_factor=kf)
        assert abs(b.__sheet_metal__["total_flat_length"] - expected_total) < 1e-6

    def test_step_length_30deg(self):
        """step_length = offset / sin(angle)."""
        offset = 10.0
        angle = math.radians(30)
        expected_step = offset / math.sin(angle)
        b = jog_sheet(self._base(), offset=offset, jog_angle_rad=angle, radius=2.0)
        assert abs(b.__sheet_metal__["step_length"] - expected_step) < 1e-6

    def test_negative_offset_ok(self):
        b = jog_sheet(self._base(), offset=-5.0, radius=2.0)
        assert b.__sheet_metal__["offset"] == -5.0
        assert b.__sheet_metal__["total_flat_length"] > 100.0

    # --- invalid inputs ---
    def test_zero_offset_raises(self):
        with pytest.raises(ValueError, match="offset"):
            jog_sheet(self._base(), offset=0.0, radius=2.0)

    def test_angle_too_large_raises(self):
        with pytest.raises(ValueError, match="jog_angle_rad"):
            jog_sheet(self._base(), offset=5.0, jog_angle_rad=2.0, radius=2.0)

    def test_zero_radius_raises(self):
        with pytest.raises(ValueError, match="radius"):
            jog_sheet(self._base(), offset=5.0, radius=0.0)

    def test_no_metadata_raises(self):
        flat = _make_flat_sheet()
        with pytest.raises(ValueError):
            jog_sheet(flat, offset=5.0, radius=2.0)


# ===========================================================================
# Tests: multi_flange
# ===========================================================================

class TestMultiFlange:
    def _flat(self, length: float = 200.0, width: float = 50.0, thickness: float = 2.0):
        flat = _make_flat_sheet(length, width, thickness)
        return flat

    def test_returns_body(self):
        flat = self._flat()
        b = multi_flange(flat, [
            {"bend_line": 80.0, "angle_rad": math.pi / 2, "radius": 3.0},
        ])
        assert isinstance(b, Body)

    def test_metadata_type_multi_flange(self):
        flat = self._flat()
        b = multi_flange(flat, [
            {"bend_line": 80.0, "angle_rad": math.pi / 2, "radius": 3.0},
        ])
        assert b.__sheet_metal__["type"] == "multi_flange"

    def test_operations_length_matches_specs(self):
        flat = self._flat()
        specs = [
            {"bend_line": 60.0, "angle_rad": math.pi / 2, "radius": 3.0},
            {"bend_line": 40.0, "angle_rad": math.pi / 4, "radius": 3.0},
            {"bend_line": 30.0, "angle_rad": math.pi / 6, "radius": 3.0},
        ]
        b = multi_flange(flat, specs)
        assert b.__sheet_metal__["num_bends"] == 3
        assert len(b.__sheet_metal__["operations"]) == 3

    def test_single_bend_flat_length_matches_bend_sheet(self):
        """1-spec multi_flange must give same total_flat_length as bend_sheet."""
        length, width, thickness = 200.0, 50.0, 2.0
        bl, ar, r, kf = 80.0, math.pi / 2, 3.0, 0.44

        flat_for_multi = self._flat(length, width, thickness)
        flat_for_single = self._flat(length, width, thickness)

        b_multi = multi_flange(flat_for_multi, [
            {"bend_line": bl, "angle_rad": ar, "radius": r, "k_factor": kf},
        ])
        b_single = bend_sheet(flat_for_single, bl, ar, r, k_factor=kf)
        single_meta = b_single.__sheet_metal__
        single_flat = (
            single_meta["flange1_length"]
            + single_meta["bend_allowance"]
            + single_meta["flange2_length"]
        )
        assert abs(b_multi.__sheet_metal__["total_flat_length"] - single_flat) < 1e-6

    def test_operations_have_required_keys(self):
        flat = self._flat()
        b = multi_flange(flat, [
            {"bend_line": 80.0, "angle_rad": math.pi / 2, "radius": 3.0},
        ])
        op = b.__sheet_metal__["operations"][0]
        for key in ("index", "bend_line", "angle_rad", "radius", "k_factor",
                    "bend_allowance", "cumulative_flat_length"):
            assert key in op, f"Key '{key}' missing from operation dict"

    def test_bend_allowances_positive(self):
        flat = self._flat()
        b = multi_flange(flat, [
            {"bend_line": 80.0, "angle_rad": math.pi / 3, "radius": 2.0},
            {"bend_line": 50.0, "angle_rad": math.pi / 4, "radius": 2.0},
        ])
        for op in b.__sheet_metal__["operations"]:
            assert op["bend_allowance"] > 0

    def test_k_factor_default(self):
        flat = self._flat()
        b = multi_flange(flat, [
            {"bend_line": 80.0, "angle_rad": math.pi / 2, "radius": 3.0},
        ])
        op = b.__sheet_metal__["operations"][0]
        assert op["k_factor"] == 0.4

    def test_empty_specs_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            multi_flange(self._flat(), [])

    def test_missing_required_key_raises(self):
        # Use a flat with metadata so validation reaches the spec-key check
        flat = self._flat()
        with pytest.raises(ValueError, match="bend_line|missing"):
            multi_flange(flat, [{"angle_rad": math.pi / 2, "radius": 3.0}])

    def test_non_dict_spec_raises(self):
        with pytest.raises(ValueError):
            multi_flange(self._flat(), ["not_a_dict"])

    def test_no_metadata_raises(self):
        # A body without __sheet_metal__ should fail
        from kerf_cad_core.geom.brep import Body, Shell
        empty_body = Body(shells=[])
        with pytest.raises(ValueError, match="__sheet_metal__"):
            multi_flange(empty_body, [
                {"bend_line": 20.0, "angle_rad": math.pi / 2, "radius": 2.0}
            ])

    def test_two_bends_flat_positive(self):
        flat = self._flat(length=200.0)
        b = multi_flange(flat, [
            {"bend_line": 80.0, "angle_rad": math.pi / 2, "radius": 3.0},
            {"bend_line": 40.0, "angle_rad": math.pi / 2, "radius": 3.0},
        ])
        assert b.__sheet_metal__["total_flat_length"] > 0
