"""
test_draft_rib_pipe.py
======================
GK-46: draft_body, rib_body, wirecut_body, pipe_body as Body-producing,
validated ops.

All tests are hermetic (pure-Python, no DB, no OCC required).
Analytic ground-truths:
  - pipe_body (straight, annular): volume = π(R_out² − R_in²) × L  ≤ 1e-6
  - rib_body cross-section:        A = ½(w_top + w_bottom) × h
  - draft_body prismatoid:         V = h/6*(A_bot + 4*A_mid + A_top)
  - wirecut_body depth:            max extent of bbox along direction
  - validate_body ok for each op's output
"""

from __future__ import annotations

import math

import pytest

from kerf_cad_core.geom.solid_features import (
    draft_body,
    pipe_body,
    rib_body,
    wirecut_body,
)
from kerf_cad_core.geom.brep import validate_body


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _approx(a: float, b: float, rel: float = 1e-6) -> None:
    """Assert |a−b| / max(|a|, |b|, 1) < rel."""
    denom = max(abs(a), abs(b), 1.0)
    assert abs(a - b) / denom < rel, f"{a!r} ≉ {b!r}  (rel tol {rel})"


def _body_valid(body) -> None:
    """Assert validate_body passes."""
    res = validate_body(body)
    assert res["ok"], f"validate_body failed: {res.get('errors')}"


# ===========================================================================
# 1. pipe_body — annular cylinder
#    ORACLE: volume = π(R_out² − R_in²) × L   ≤ 1e-6 relative
# ===========================================================================

class TestPipeBodyAnnularCylinder:
    """Straight-line path → exact annular cylinder."""

    def test_volume_exact_oracle_along_z(self):
        """π(R²−r²)×L  along Z axis."""
        R, r, L = 5.0, 2.0, 10.0
        res = pipe_body([[0, 0, 0], [0, 0, L]], R, r)
        assert res["ok"], res.get("reason")
        expected = math.pi * (R ** 2 - r ** 2) * L
        _approx(res["volume"], expected, rel=1e-6)

    def test_volume_exact_oracle_along_x(self):
        """Same oracle, extrusion along X."""
        R, r, L = 3.0, 1.0, 7.0
        res = pipe_body([[0, 0, 0], [L, 0, 0]], R, r)
        assert res["ok"], res.get("reason")
        expected = math.pi * (R ** 2 - r ** 2) * L
        _approx(res["volume"], expected, rel=1e-6)

    def test_volume_exact_oracle_along_y(self):
        """Oracle along Y."""
        R, r, L = 4.0, 1.5, 8.0
        res = pipe_body([[0, 0, 0], [0, L, 0]], R, r)
        assert res["ok"], res.get("reason")
        expected = math.pi * (R ** 2 - r ** 2) * L
        _approx(res["volume"], expected, rel=1e-6)

    def test_volume_diagonal_path(self):
        """Oracle for diagonal extrusion: only L matters."""
        R, r = 3.0, 1.0
        L = math.sqrt(3.0)
        res = pipe_body([[0, 0, 0], [1, 1, 1]], R, r)
        assert res["ok"], res.get("reason")
        expected = math.pi * (R ** 2 - r ** 2) * L
        _approx(res["volume"], expected, rel=1e-6)

    def test_validate_body_ok(self):
        """validate_body passes."""
        res = pipe_body([[0, 0, 0], [0, 0, 5.0]], 4.0, 2.0)
        assert res["ok"], res.get("reason")
        _body_valid(res["body"])

    def test_validate_body_ok_along_x(self):
        """validate_body passes for X-axis pipe."""
        res = pipe_body([[0, 0, 0], [6.0, 0, 0]], 3.0, 1.0)
        assert res["ok"], res.get("reason")
        _body_valid(res["body"])

    def test_length_reported_correctly(self):
        R, r, L = 2.0, 1.0, 9.0
        res = pipe_body([[0, 0, 0], [0, 0, L]], R, r)
        assert res["ok"]
        _approx(res["length"], L, rel=1e-9)

    def test_radii_reported(self):
        res = pipe_body([[0, 0, 0], [0, 0, 5.0]], 7.0, 3.0)
        assert res["ok"]
        assert res["outer_radius"] == 7.0
        assert res["inner_radius"] == 3.0

    def test_topology_counts(self):
        """Annular cylinder: V=4, E=6, F=4 (washer genus-1 topology)."""
        res = pipe_body([[0, 0, 0], [0, 0, 5.0]], 4.0, 2.0)
        assert res["ok"]
        # genus-1 body: V−E+F = V−E+F−2H = 0 with H = L−F = 2
        # V=4, E=6, F=4, L=6 (2 per cap + 1 outer cyl + 1 inner cyl)
        assert res["n_faces"] == 4
        assert res["n_edges"] == 6
        assert res["n_vertices"] == 4

    def test_thin_wall_oracle(self):
        """Oracle holds for thin-walled pipe."""
        R, r, L = 10.0, 9.9, 20.0
        res = pipe_body([[0, 0, 0], [0, 0, L]], R, r)
        assert res["ok"], res.get("reason")
        expected = math.pi * (R ** 2 - r ** 2) * L
        _approx(res["volume"], expected, rel=1e-6)

    def test_bad_inner_radius_equals_outer(self):
        res = pipe_body([[0, 0, 0], [0, 0, 5.0]], 3.0, 3.0)
        assert not res["ok"]

    def test_bad_inner_radius_exceeds_outer(self):
        res = pipe_body([[0, 0, 0], [0, 0, 5.0]], 2.0, 5.0)
        assert not res["ok"]

    def test_zero_length_path(self):
        res = pipe_body([[1, 1, 1], [1, 1, 1]], 2.0, 1.0)
        assert not res["ok"]

    def test_fewer_than_two_path_points(self):
        res = pipe_body([[0, 0, 0]], 2.0, 1.0)
        assert not res["ok"]

    def test_negative_outer_radius(self):
        res = pipe_body([[0, 0, 0], [0, 0, 5.0]], -1.0, -3.0)
        assert not res["ok"]


# ===========================================================================
# 2. rib_body — trapezoidal prism
#    ORACLE: volume = A_cross × L   where A = ½(w_top + w_bot) × H
# ===========================================================================

class TestRibBody:
    """Rib extruded trapezoidal prism."""

    def test_volume_no_draft(self):
        """No draft: rectangular prism, V = thickness × height × length."""
        L, t, H = 10.0, 2.0, 5.0
        res = rib_body(L, t, H, draft_angle_deg=0.0)
        assert res["ok"], res.get("reason")
        expected = t * H * L  # rect prism
        _approx(res["volume"], expected, rel=1e-6)

    def test_cross_section_no_draft(self):
        L, t, H = 8.0, 3.0, 4.0
        res = rib_body(L, t, H, draft_angle_deg=0.0)
        assert res["ok"]
        expected_area = t * H
        _approx(res["cross_section_area"], expected_area, rel=1e-6)

    def test_volume_with_draft(self):
        """Trapezoidal cross-section: A = ½(w_top + w_bot) × H."""
        L, t, H, angle = 5.0, 2.0, 4.0, 10.0
        angle_rad = math.radians(angle)
        taper = H * math.tan(angle_rad)
        w_top = t
        w_bottom = t + 2.0 * taper
        expected_area = 0.5 * (w_top + w_bottom) * H
        expected_vol = expected_area * L
        res = rib_body(L, t, H, draft_angle_deg=angle)
        assert res["ok"], res.get("reason")
        _approx(res["volume"], expected_vol, rel=1e-6)

    def test_cross_section_area_with_draft(self):
        L, t, H, angle = 6.0, 1.5, 3.0, 5.0
        angle_rad = math.radians(angle)
        taper = H * math.tan(angle_rad)
        w_top = t
        w_bottom = t + 2.0 * taper
        expected_area = 0.5 * (w_top + w_bottom) * H
        res = rib_body(L, t, H, draft_angle_deg=angle)
        assert res["ok"]
        _approx(res["cross_section_area"], expected_area, rel=1e-6)

    def test_validate_body_ok(self):
        """validate_body passes for rib with no draft."""
        res = rib_body(10.0, 2.0, 5.0)
        assert res["ok"], res.get("reason")
        _body_valid(res["body"])

    def test_validate_body_ok_with_draft(self):
        """validate_body passes for rib with draft."""
        res = rib_body(8.0, 2.0, 4.0, draft_angle_deg=5.0)
        assert res["ok"], res.get("reason")
        _body_valid(res["body"])

    def test_w_top_w_bottom_reported(self):
        L, t, H, angle = 5.0, 2.0, 3.0, 10.0
        angle_rad = math.radians(angle)
        taper = H * math.tan(angle_rad)
        res = rib_body(L, t, H, draft_angle_deg=angle)
        assert res["ok"]
        _approx(res["w_top"], t, rel=1e-9)
        _approx(res["w_bottom"], t + 2.0 * taper, rel=1e-9)

    def test_face_edge_vertex_count(self):
        """Prism has 6 faces, 12 edges, 8 vertices."""
        res = rib_body(5.0, 2.0, 3.0)
        assert res["ok"]
        assert res["n_faces"] == 6
        assert res["n_edges"] == 12
        assert res["n_vertices"] == 8

    def test_bad_profile_length(self):
        assert not rib_body(0.0, 2.0, 3.0)["ok"]
        assert not rib_body(-1.0, 2.0, 3.0)["ok"]

    def test_bad_rib_thickness(self):
        assert not rib_body(5.0, 0.0, 3.0)["ok"]

    def test_bad_rib_height(self):
        assert not rib_body(5.0, 2.0, 0.0)["ok"]

    def test_bad_draft_angle(self):
        assert not rib_body(5.0, 2.0, 3.0, draft_angle_deg=90.0)["ok"]
        assert not rib_body(5.0, 2.0, 3.0, draft_angle_deg=-1.0)["ok"]


# ===========================================================================
# 3. draft_body — tapered rectangular prism
#    ORACLE: prismatoid  V = h/6*(A_bot + 4*A_mid + A_top)
# ===========================================================================

class TestDraftBody:
    """Rectangular solid with draft angle → frustum prism."""

    def test_volume_zero_draft(self):
        """At zero draft (use tiny angle) body is essentially a rectangular prism."""
        W, D, H = 6.0, 4.0, 5.0
        # Use minimal draft angle and neutral=0 so taper_top ≈ 0
        # We test with no draft by using rib_body or by checking formula
        # draft_body requires angle in (0,90), so use very small angle
        angle = 0.01  # degrees
        res = draft_body(W, D, H, angle, neutral_plane_offset=0.0)
        assert res["ok"], res.get("reason")
        # For tiny angle body ≈ W × D × H
        _approx(res["volume"], W * D * H, rel=1e-3)

    def test_prismatoid_oracle(self):
        """Prismatoid formula: V = h/6*(A_bot + 4*A_mid + A_top)."""
        W, D, H = 10.0, 8.0, 6.0
        angle = 5.0
        angle_rad = math.radians(angle)
        # neutral_plane_offset=0: taper_bottom=0, taper_top = H*tan(angle)
        taper_top = H * math.tan(angle_rad)
        taper_bot = 0.0
        w_bot = W + 2 * taper_bot
        d_bot = D + 2 * taper_bot
        w_top = W - 2 * taper_top
        d_top = D - 2 * taper_top
        w_mid = (w_bot + w_top) / 2.0
        d_mid = (d_bot + d_top) / 2.0
        A_bot = w_bot * d_bot
        A_top = w_top * d_top
        A_mid = w_mid * d_mid
        expected = H / 6.0 * (A_bot + 4 * A_mid + A_top)
        res = draft_body(W, D, H, angle, neutral_plane_offset=0.0)
        assert res["ok"], res.get("reason")
        _approx(res["volume"], expected, rel=1e-6)

    def test_validate_body_ok(self):
        """validate_body passes."""
        res = draft_body(8.0, 6.0, 5.0, 3.0)
        assert res["ok"], res.get("reason")
        _body_valid(res["body"])

    def test_validate_body_ok_mid_neutral(self):
        """validate_body passes with neutral plane in the middle."""
        res = draft_body(8.0, 6.0, 6.0, 3.0, neutral_plane_offset=0.5)
        assert res["ok"], res.get("reason")
        _body_valid(res["body"])

    def test_taper_top_reported(self):
        W, D, H = 8.0, 6.0, 5.0
        angle = 4.0
        angle_rad = math.radians(angle)
        res = draft_body(W, D, H, angle, neutral_plane_offset=0.0)
        assert res["ok"]
        expected_taper_top = H * math.tan(angle_rad)
        _approx(res["taper_at_top"], expected_taper_top, rel=1e-6)

    def test_taper_bottom_zero_at_bottom_neutral(self):
        """With neutral_plane_offset=0, taper_at_bottom=0."""
        res = draft_body(6.0, 4.0, 5.0, 2.0, neutral_plane_offset=0.0)
        assert res["ok"]
        _approx(res["taper_at_bottom"], 0.0, rel=1e-6)

    def test_face_edge_vertex_count(self):
        """6 faces, 12 edges, 8 vertices."""
        res = draft_body(6.0, 4.0, 5.0, 2.0)
        assert res["ok"]
        assert res["n_faces"] == 6
        assert res["n_edges"] == 12
        assert res["n_vertices"] == 8

    def test_large_draft_angle_collapse_error(self):
        """Draft so large that top face collapses → ok=False."""
        # angle = 45°, H=5, taper_top = 5*tan(45)=5, W=4 → w_top=4-10=-6 ≤ 0
        res = draft_body(4.0, 4.0, 5.0, 45.0, neutral_plane_offset=0.0)
        assert not res["ok"]

    def test_bad_base_width(self):
        assert not draft_body(0.0, 4.0, 5.0, 2.0)["ok"]
        assert not draft_body(-1.0, 4.0, 5.0, 2.0)["ok"]

    def test_bad_draft_angle(self):
        assert not draft_body(6.0, 4.0, 5.0, 0.0)["ok"]
        assert not draft_body(6.0, 4.0, 5.0, 90.0)["ok"]

    def test_bad_neutral_offset(self):
        assert not draft_body(6.0, 4.0, 5.0, 2.0, neutral_plane_offset=-0.1)["ok"]
        assert not draft_body(6.0, 4.0, 5.0, 2.0, neutral_plane_offset=1.1)["ok"]


# ===========================================================================
# 4. wirecut_body — prismatic cutter body
#    ORACLE: cut_depth = max extent of bbox along direction
# ===========================================================================

class TestWirecutBody:
    """Cutter body for wirecut operation."""

    def test_ok_triangle_profile(self):
        """Triangle profile, Z-direction cut."""
        bbox = [10.0, 8.0, 6.0]
        profile = [[0.0, 0.0], [3.0, 0.0], [1.5, 3.0]]
        res = wirecut_body(bbox, profile, direction=(0.0, 0.0, 1.0))
        assert res["ok"], res.get("reason")

    def test_cut_depth_along_z(self):
        """cut_depth = bbox height along Z."""
        bbox = [10.0, 8.0, 6.0]
        profile = [[0.0, 0.0], [4.0, 0.0], [4.0, 3.0], [0.0, 3.0]]
        res = wirecut_body(bbox, profile, direction=(0.0, 0.0, 1.0))
        assert res["ok"], res.get("reason")
        _approx(res["cut_depth"], 6.0, rel=1e-9)

    def test_cut_depth_along_x(self):
        """cut_depth = bbox width along X."""
        bbox = [5.0, 8.0, 6.0]
        profile = [[0.0, 0.0], [3.0, 0.0], [3.0, 2.0], [0.0, 2.0]]
        res = wirecut_body(bbox, profile, direction=(1.0, 0.0, 0.0))
        assert res["ok"], res.get("reason")
        _approx(res["cut_depth"], 5.0, rel=1e-9)

    def test_cut_depth_along_y(self):
        """cut_depth = bbox depth along Y."""
        bbox = [10.0, 7.0, 6.0]
        profile = [[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0]]
        res = wirecut_body(bbox, profile, direction=(0.0, 1.0, 0.0))
        assert res["ok"], res.get("reason")
        _approx(res["cut_depth"], 7.0, rel=1e-9)

    def test_validate_body_ok(self):
        """validate_body passes for rectangular cutter."""
        bbox = [10.0, 8.0, 6.0]
        profile = [[0.0, 0.0], [4.0, 0.0], [4.0, 3.0], [0.0, 3.0]]
        res = wirecut_body(bbox, profile)
        assert res["ok"], res.get("reason")
        _body_valid(res["body"])

    def test_validate_body_ok_triangle(self):
        """validate_body passes for triangular cutter."""
        bbox = [8.0, 6.0, 5.0]
        profile = [[0.0, 0.0], [3.0, 0.0], [1.5, 2.0]]
        res = wirecut_body(bbox, profile)
        assert res["ok"], res.get("reason")
        _body_valid(res["body"])

    def test_face_count_rect_cutter(self):
        """Rectangle profile: 4+2=6 faces."""
        profile = [[0.0, 0.0], [3.0, 0.0], [3.0, 2.0], [0.0, 2.0]]
        res = wirecut_body([10.0, 8.0, 6.0], profile)
        assert res["ok"]
        assert res["n_faces"] == 6

    def test_face_count_triangle_cutter(self):
        """Triangle profile: 3+2=5 faces."""
        profile = [[0.0, 0.0], [3.0, 0.0], [1.5, 2.5]]
        res = wirecut_body([10.0, 8.0, 6.0], profile)
        assert res["ok"]
        assert res["n_faces"] == 5

    def test_path_length_perimeter(self):
        """path_length = 2D arc-length of the open profile chain (no closing segment)."""
        profile = [[0.0, 0.0], [3.0, 0.0], [3.0, 4.0], [0.0, 4.0]]
        res = wirecut_body([10.0, 8.0, 6.0], profile)
        assert res["ok"]
        # Open chain (n-1 segments): 0→1=3, 1→2=4, 2→3=3  → 10.0
        expected = 3.0 + 4.0 + 3.0
        _approx(res["path_length"], expected, rel=1e-9)

    def test_bad_solid_bbox_negative(self):
        profile = [[0.0, 0.0], [2.0, 0.0], [1.0, 1.0]]
        assert not wirecut_body([-1.0, 5.0, 5.0], profile)["ok"]

    def test_too_few_profile_points(self):
        """Fewer than 3 points can't form a closed polygon."""
        res = wirecut_body([10.0, 8.0, 6.0], [[0.0, 0.0], [2.0, 0.0]])
        assert not res["ok"]

    def test_zero_direction(self):
        profile = [[0.0, 0.0], [2.0, 0.0], [1.0, 1.0]]
        res = wirecut_body([10.0, 8.0, 6.0], profile, direction=(0.0, 0.0, 0.0))
        assert not res["ok"]
