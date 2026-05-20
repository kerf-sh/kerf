"""Tests for IGES 144 (Trimmed Parametric Surface) reader/writer — GK-49.

Oracle: round-trip a trimmed plane: write a TrimmedSurface to IGES, read it
back, and verify that the boundary loop Hausdorff distance ≤ 1e-6.

All tests are pure-Python and hermetic (no OCCT, no external files).
"""

from __future__ import annotations

import math
import pathlib
import tempfile

import numpy as np
import pytest

from kerf_cad_core.geom.nurbs import NurbsCurve, NurbsSurface
from kerf_cad_core.geom.io.iges import (
    IgesReadError,
    IgesWriteError,
    TrimmedSurface,
    read_iges,
    write_iges,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clamped_knots(n_cp: int, degree: int) -> np.ndarray:
    """Build a clamped uniform knot vector for *n_cp* control points of given degree."""
    n_internal = n_cp - degree - 1
    internal = np.linspace(0.0, 1.0, n_internal + 2)[1:-1] if n_internal > 0 else []
    knots = (
        [0.0] * (degree + 1)
        + list(internal)
        + [1.0] * (degree + 1)
    )
    return np.array(knots, dtype=float)


def _make_planar_nurbs_surface() -> NurbsSurface:
    """Unit planar surface in XY: S(u,v) = (u, v, 0), u∈[0,1], v∈[0,1]."""
    # Bilinear (degree 1 × 1) plane: 2×2 control points
    cp = np.array([
        [[0.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        [[1.0, 0.0, 0.0], [1.0, 1.0, 0.0]],
    ], dtype=float)
    knots = np.array([0.0, 0.0, 1.0, 1.0])
    return NurbsSurface(
        degree_u=1,
        degree_v=1,
        control_points=cp,
        knots_u=knots,
        knots_v=knots,
    )


def _make_rectangular_boundary(u0: float, u1: float, v0: float, v1: float) -> NurbsCurve:
    """Rectangular UV boundary loop as a degree-1 closed polyline NurbsCurve.

    The control points walk CCW: (u0,v0) → (u1,v0) → (u1,v1) → (u0,v1) → (u0,v0).
    """
    # 5 control points (last = first for closure), degree 1
    cp = np.array([
        [u0, v0],
        [u1, v0],
        [u1, v1],
        [u0, v1],
        [u0, v0],
    ], dtype=float)
    # Clamped knot vector for 5 control points, degree 1
    knots = np.array([0.0, 0.0, 0.25, 0.5, 0.75, 1.0, 1.0], dtype=float)
    return NurbsCurve(degree=1, control_points=cp, knots=knots)


def _make_unit_square_trimmed_surface() -> TrimmedSurface:
    """A unit-square trimmed surface: plane trimmed by its full boundary."""
    surf = _make_planar_nurbs_surface()
    boundary = _make_rectangular_boundary(0.0, 1.0, 0.0, 1.0)
    return TrimmedSurface(surface=surf, outer_boundary=[boundary])


def _sample_nurbs_curve_2d(crv: NurbsCurve, n: int = 64) -> np.ndarray:
    """Sample a 2-D NurbsCurve at *n* uniformly-spaced parameter values."""
    t0 = float(crv.knots[0])
    t1 = float(crv.knots[-1])
    ts = np.linspace(t0, t1, n)
    pts = np.array([crv.evaluate(t) for t in ts])
    # Ensure 2D
    if pts.shape[1] > 2:
        pts = pts[:, :2]
    return pts


def _hausdorff_2d(pts_a: np.ndarray, pts_b: np.ndarray) -> float:
    """Directed Hausdorff distance from pts_a to pts_b (one-sided), then symmetric."""
    from scipy.spatial.distance import directed_hausdorff
    d_ab = directed_hausdorff(pts_a, pts_b)[0]
    d_ba = directed_hausdorff(pts_b, pts_a)[0]
    return max(d_ab, d_ba)


def _hausdorff_2d_pure(pts_a: np.ndarray, pts_b: np.ndarray) -> float:
    """Pure-numpy Hausdorff (no scipy dependency)."""
    # Directed: for each point in a, find min dist to any point in b
    def _directed(x: np.ndarray, y: np.ndarray) -> float:
        # x: (n,2), y: (m,2)
        max_min = 0.0
        for pt in x:
            dists = np.linalg.norm(y - pt, axis=1)
            max_min = max(max_min, float(np.min(dists)))
        return max_min

    return max(_directed(pts_a, pts_b), _directed(pts_b, pts_a))


# ---------------------------------------------------------------------------
# Unit-level entity tests
# ---------------------------------------------------------------------------

class TestWriteIgesBasic:
    def test_write_creates_file(self, tmp_path):
        ts = _make_unit_square_trimmed_surface()
        out = str(tmp_path / "test.igs")
        write_iges(ts, out)
        assert pathlib.Path(out).exists()
        assert pathlib.Path(out).stat().st_size > 0

    def test_write_produces_section_markers(self, tmp_path):
        ts = _make_unit_square_trimmed_surface()
        out = str(tmp_path / "test.igs")
        write_iges(ts, out)
        text = pathlib.Path(out).read_text()
        lines = text.splitlines()
        sections = {line[72] for line in lines if len(line) >= 73}
        assert "S" in sections
        assert "G" in sections
        assert "D" in sections
        assert "P" in sections
        assert "T" in sections

    def test_write_80_column_lines(self, tmp_path):
        ts = _make_unit_square_trimmed_surface()
        out = str(tmp_path / "test.igs")
        write_iges(ts, out)
        for line in pathlib.Path(out).read_text().splitlines():
            assert len(line) == 80, f"Line not 80 chars: {len(line)!r} → {line!r}"

    def test_write_entity_144_present(self, tmp_path):
        """Written IGES must contain at least one entity-144 DE entry."""
        ts = _make_unit_square_trimmed_surface()
        out = str(tmp_path / "test.igs")
        write_iges(ts, out)
        text = pathlib.Path(out).read_text()
        # Look for '     144' in DE section lines (entity type in cols 1-8)
        d_lines = [l for l in text.splitlines() if len(l) >= 73 and l[72] == "D"]
        entity_types = {int(l[0:8].strip()) for l in d_lines if l[0:8].strip()}
        assert 144 in entity_types, f"Entity 144 not found; types present: {entity_types}"

    def test_write_entity_128_present(self, tmp_path):
        ts = _make_unit_square_trimmed_surface()
        out = str(tmp_path / "test.igs")
        write_iges(ts, out)
        text = pathlib.Path(out).read_text()
        d_lines = [l for l in text.splitlines() if len(l) >= 73 and l[72] == "D"]
        entity_types = {int(l[0:8].strip()) for l in d_lines if l[0:8].strip()}
        assert 128 in entity_types

    def test_write_entity_126_present(self, tmp_path):
        ts = _make_unit_square_trimmed_surface()
        out = str(tmp_path / "test.igs")
        write_iges(ts, out)
        text = pathlib.Path(out).read_text()
        d_lines = [l for l in text.splitlines() if len(l) >= 73 and l[72] == "D"]
        entity_types = {int(l[0:8].strip()) for l in d_lines if l[0:8].strip()}
        assert 126 in entity_types

    def test_write_entity_142_present(self, tmp_path):
        ts = _make_unit_square_trimmed_surface()
        out = str(tmp_path / "test.igs")
        write_iges(ts, out)
        text = pathlib.Path(out).read_text()
        d_lines = [l for l in text.splitlines() if len(l) >= 73 and l[72] == "D"]
        entity_types = {int(l[0:8].strip()) for l in d_lines if l[0:8].strip()}
        assert 142 in entity_types

    def test_write_raises_on_empty_boundary(self, tmp_path):
        surf = _make_planar_nurbs_surface()
        ts = TrimmedSurface(surface=surf, outer_boundary=[])
        with pytest.raises(IgesWriteError):
            write_iges(ts, str(tmp_path / "bad.igs"))

    def test_write_raises_on_wrong_type(self, tmp_path):
        with pytest.raises(IgesWriteError):
            write_iges("not_a_trimmed_surface", str(tmp_path / "bad.igs"))  # type: ignore


class TestReadIgesBasic:
    def test_read_returns_list(self, tmp_path):
        ts = _make_unit_square_trimmed_surface()
        out = str(tmp_path / "test.igs")
        write_iges(ts, out)
        result = read_iges(out)
        assert isinstance(result, list)

    def test_read_one_trimmed_surface(self, tmp_path):
        ts = _make_unit_square_trimmed_surface()
        out = str(tmp_path / "test.igs")
        write_iges(ts, out)
        result = read_iges(out)
        assert len(result) == 1

    def test_read_surface_is_nurbs(self, tmp_path):
        ts = _make_unit_square_trimmed_surface()
        out = str(tmp_path / "test.igs")
        write_iges(ts, out)
        result = read_iges(out)
        assert isinstance(result[0].surface, NurbsSurface)

    def test_read_outer_boundary_nonempty(self, tmp_path):
        ts = _make_unit_square_trimmed_surface()
        out = str(tmp_path / "test.igs")
        write_iges(ts, out)
        result = read_iges(out)
        assert len(result[0].outer_boundary) >= 1

    def test_read_outer_boundary_is_nurbs_curve(self, tmp_path):
        ts = _make_unit_square_trimmed_surface()
        out = str(tmp_path / "test.igs")
        write_iges(ts, out)
        result = read_iges(out)
        for crv in result[0].outer_boundary:
            assert isinstance(crv, NurbsCurve)

    def test_read_missing_file_raises(self):
        with pytest.raises(IgesReadError):
            read_iges("/nonexistent/path/file.igs")


# ---------------------------------------------------------------------------
# ORACLE: Round-trip — boundary loop Hausdorff ≤ 1e-6
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_round_trip_unit_square_boundary_hausdorff(self, tmp_path):
        """Oracle: write→read a trimmed unit-square plane; boundary Hausdorff ≤ 1e-6."""
        ts_orig = _make_unit_square_trimmed_surface()
        out = str(tmp_path / "rt_unit_square.igs")
        write_iges(ts_orig, out)
        ts_rt = read_iges(out)[0]

        # Sample the original outer boundary
        orig_crv = ts_orig.outer_boundary[0]
        rt_crv = ts_rt.outer_boundary[0]

        pts_orig = _sample_nurbs_curve_2d(orig_crv, n=128)
        pts_rt = _sample_nurbs_curve_2d(rt_crv, n=128)

        h = _hausdorff_2d_pure(pts_orig, pts_rt)
        assert h <= 1e-6, f"Boundary Hausdorff {h:.3e} exceeds 1e-6"

    def test_round_trip_surface_control_points_close(self, tmp_path):
        """Surface control points survive round-trip within 1e-9."""
        ts_orig = _make_unit_square_trimmed_surface()
        out = str(tmp_path / "rt_surf_cp.igs")
        write_iges(ts_orig, out)
        ts_rt = read_iges(out)[0]

        cp_orig = ts_orig.surface.control_points
        cp_rt = ts_rt.surface.control_points

        assert cp_orig.shape == cp_rt.shape, (
            f"CP shape mismatch: {cp_orig.shape} vs {cp_rt.shape}"
        )
        max_err = float(np.max(np.abs(cp_orig - cp_rt)))
        assert max_err <= 1e-9, f"Max CP error {max_err:.3e} exceeds 1e-9"

    def test_round_trip_knot_vectors_close(self, tmp_path):
        """Knot vectors survive round-trip within 1e-9."""
        ts_orig = _make_unit_square_trimmed_surface()
        out = str(tmp_path / "rt_knots.igs")
        write_iges(ts_orig, out)
        ts_rt = read_iges(out)[0]

        ku_orig = ts_orig.surface.knots_u
        ku_rt = ts_rt.surface.knots_u
        kv_orig = ts_orig.surface.knots_v
        kv_rt = ts_rt.surface.knots_v

        np.testing.assert_allclose(ku_orig, ku_rt, atol=1e-9, err_msg="knots_u mismatch")
        np.testing.assert_allclose(kv_orig, kv_rt, atol=1e-9, err_msg="knots_v mismatch")

    def test_round_trip_surface_degree(self, tmp_path):
        """Surface degrees are preserved exactly."""
        ts_orig = _make_unit_square_trimmed_surface()
        out = str(tmp_path / "rt_degree.igs")
        write_iges(ts_orig, out)
        ts_rt = read_iges(out)[0]
        assert ts_rt.surface.degree_u == ts_orig.surface.degree_u
        assert ts_rt.surface.degree_v == ts_orig.surface.degree_v

    def test_round_trip_surface_evaluates_consistently(self, tmp_path):
        """Surface evaluations at grid points match within 1e-9 after round-trip."""
        ts_orig = _make_unit_square_trimmed_surface()
        out = str(tmp_path / "rt_eval.igs")
        write_iges(ts_orig, out)
        ts_rt = read_iges(out)[0]

        surf_orig = ts_orig.surface
        surf_rt = ts_rt.surface
        for u in np.linspace(0.0, 1.0, 5):
            for v in np.linspace(0.0, 1.0, 5):
                pt_orig = surf_orig.evaluate(float(u), float(v))
                pt_rt = surf_rt.evaluate(float(u), float(v))
                err = float(np.linalg.norm(pt_orig - pt_rt))
                assert err <= 1e-9, (
                    f"Surface eval mismatch at u={u:.2f},v={v:.2f}: {err:.3e}"
                )

    def test_round_trip_boundary_curve_degree(self, tmp_path):
        """Boundary curve degree is preserved."""
        ts_orig = _make_unit_square_trimmed_surface()
        out = str(tmp_path / "rt_crv_deg.igs")
        write_iges(ts_orig, out)
        ts_rt = read_iges(out)[0]
        assert ts_rt.outer_boundary[0].degree == ts_orig.outer_boundary[0].degree

    def test_round_trip_boundary_control_points_close(self, tmp_path):
        """Boundary curve control points survive round-trip within 1e-9."""
        ts_orig = _make_unit_square_trimmed_surface()
        out = str(tmp_path / "rt_bnd_cp.igs")
        write_iges(ts_orig, out)
        ts_rt = read_iges(out)[0]

        cp_orig = ts_orig.outer_boundary[0].control_points
        cp_rt = ts_rt.outer_boundary[0].control_points[:, :cp_orig.shape[1]]

        assert cp_orig.shape == cp_rt.shape, (
            f"Boundary CP shape mismatch: {cp_orig.shape} vs {cp_rt.shape}"
        )
        max_err = float(np.max(np.abs(cp_orig - cp_rt)))
        assert max_err <= 1e-9, f"Max boundary CP error {max_err:.3e}"

    def test_round_trip_inner_boundaries_empty(self, tmp_path):
        """No inner boundaries expected for the unit-square test case."""
        ts_orig = _make_unit_square_trimmed_surface()
        out = str(tmp_path / "rt_inner.igs")
        write_iges(ts_orig, out)
        ts_rt = read_iges(out)[0]
        assert ts_rt.inner_boundaries == []

    def test_round_trip_cubic_surface_hausdorff(self, tmp_path):
        """Round-trip a degree-3 NURBS surface trimmed to a sub-rectangle."""
        # Build a simple degree-3 surface (bicubic flat patch with extra CPs)
        # S(u,v) = (u, v, 0) parametrised via 4x4 control points
        n = 4  # 4 control points per direction
        u_pts = np.linspace(0.0, 1.0, n)
        v_pts = np.linspace(0.0, 1.0, n)
        cp = np.zeros((n, n, 3))
        for i, u in enumerate(u_pts):
            for j, v in enumerate(v_pts):
                cp[i, j] = [u, v, 0.0]

        knots = _clamped_knots(n, degree=3)
        surf = NurbsSurface(
            degree_u=3,
            degree_v=3,
            control_points=cp,
            knots_u=knots,
            knots_v=knots,
        )
        # Trim to a sub-rectangle [0.1, 0.9] x [0.1, 0.9]
        boundary = _make_rectangular_boundary(0.1, 0.9, 0.1, 0.9)
        ts_orig = TrimmedSurface(surface=surf, outer_boundary=[boundary])

        out = str(tmp_path / "rt_cubic.igs")
        write_iges(ts_orig, out)
        ts_rt = read_iges(out)[0]

        orig_crv = ts_orig.outer_boundary[0]
        rt_crv = ts_rt.outer_boundary[0]

        pts_orig = _sample_nurbs_curve_2d(orig_crv, n=128)
        pts_rt = _sample_nurbs_curve_2d(rt_crv, n=128)

        h = _hausdorff_2d_pure(pts_orig, pts_rt)
        assert h <= 1e-6, f"Cubic surface round-trip Hausdorff {h:.3e} exceeds 1e-6"


# ---------------------------------------------------------------------------
# Additional structural / robustness tests
# ---------------------------------------------------------------------------

class TestStructural:
    def test_de_sequence_numbers_are_odd(self, tmp_path):
        """All DE line 1 sequence numbers are odd (IGES convention)."""
        ts = _make_unit_square_trimmed_surface()
        out = str(tmp_path / "de_seq.igs")
        write_iges(ts, out)
        text = pathlib.Path(out).read_text()
        d_lines = [l for l in text.splitlines() if len(l) >= 80 and l[72] == "D"]
        # Every other D line should have odd seq num (DE line 1)
        for i, line in enumerate(d_lines):
            seq = int(line[73:80])
            if i % 2 == 0:  # DE line 1
                assert seq % 2 == 1, f"DE line 1 has even seq {seq}"
            else:            # DE line 2
                assert seq % 2 == 0, f"DE line 2 has odd seq {seq}"

    def test_pd_back_pointers_are_odd(self, tmp_path):
        """PD back-pointers (cols 65-72) must be odd (they point to DE line 1)."""
        ts = _make_unit_square_trimmed_surface()
        out = str(tmp_path / "pd_back.igs")
        write_iges(ts, out)
        text = pathlib.Path(out).read_text()
        p_lines = [l for l in text.splitlines() if len(l) >= 80 and l[72] == "P"]
        for line in p_lines:
            back_ptr = int(line[64:72].strip())
            assert back_ptr % 2 == 1, f"PD back-pointer {back_ptr} is not odd"

    def test_multiple_trimmed_surfaces_roundtrip(self, tmp_path):
        """Write two surfaces to separate files and read each back correctly."""
        surf1 = _make_planar_nurbs_surface()
        bnd1 = _make_rectangular_boundary(0.0, 0.5, 0.0, 1.0)
        ts1 = TrimmedSurface(surface=surf1, outer_boundary=[bnd1])

        surf2 = _make_planar_nurbs_surface()
        bnd2 = _make_rectangular_boundary(0.2, 0.8, 0.2, 0.8)
        ts2 = TrimmedSurface(surface=surf2, outer_boundary=[bnd2])

        for i, ts in enumerate([ts1, ts2]):
            out = str(tmp_path / f"multi_{i}.igs")
            write_iges(ts, out)
            result = read_iges(out)
            assert len(result) == 1
            crv_orig = ts.outer_boundary[0]
            crv_rt = result[0].outer_boundary[0]
            pts_o = _sample_nurbs_curve_2d(crv_orig, 64)
            pts_r = _sample_nurbs_curve_2d(crv_rt, 64)
            h = _hausdorff_2d_pure(pts_o, pts_r)
            assert h <= 1e-6, f"Surface {i} Hausdorff {h:.3e} exceeds 1e-6"

    def test_rational_surface_roundtrip(self, tmp_path):
        """A rational NURBS surface (non-unit weights) survives round-trip."""
        cp = np.array([
            [[0.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
            [[1.0, 0.0, 0.0], [1.0, 1.0, 0.0]],
        ], dtype=float)
        knots = np.array([0.0, 0.0, 1.0, 1.0])
        # Non-unit weights (makes it rational)
        weights = np.array([[1.0, 0.9], [0.9, 1.0]])
        surf = NurbsSurface(
            degree_u=1, degree_v=1,
            control_points=cp, knots_u=knots, knots_v=knots,
            weights=weights,
        )
        bnd = _make_rectangular_boundary(0.0, 1.0, 0.0, 1.0)
        ts = TrimmedSurface(surface=surf, outer_boundary=[bnd])

        out = str(tmp_path / "rational.igs")
        write_iges(ts, out)
        ts_rt = read_iges(out)[0]

        # Weights must be preserved
        w_orig = ts.surface.weights
        w_rt = ts_rt.surface.weights
        assert w_rt is not None, "Weights lost after round-trip"
        np.testing.assert_allclose(w_orig, w_rt, atol=1e-9)
