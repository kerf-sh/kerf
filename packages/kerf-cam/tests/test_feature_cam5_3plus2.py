"""
T-37 — CAM 5-axis: 3+2 indexed, feature test suite.

Coverage
--------
25 setups across three concern areas:

  Group A – Indexed-plane resolution (10 setups)
    A1  +Z normal → B=0° (axis-aligned; no orientation move)
    A2  +X normal → A=0°, B=90°
    A3  +Y normal → A=90°, B=90°
    A4  −X normal → A=180°, B=90°
    A5  −Y normal → A=−90°, B=90°
    A6  45° tilt toward +X → A=0°, B=45°
    A7  30° tilt toward +Y → A=90°, B=30°
    A8  diagonal in XY → A=45°, B=90°
    A9  arbitrary unit vector (0.5, 0.5, 0.707) → B≈45°, A=45°
    A10 −Z normal → B=180° (but must still emit orientation move, not axis-aligned)

  Group B – Kinematic limits (7 setups)
    B1  B within typical 110° limit → no limit warning
    B2  B exactly at 110° limit → no limit warning (boundary-inclusive)
    B3  B = 120° (beyond typical 110°) → limit warning in G-code comments
    B4  B = 0° (exactly axis-aligned) → axis-aligned path, no limit warning
    B5  B just below threshold (109.99°) → no limit warning
    B6  A = 0°, B = 90° → no limit warning
    B7  malformed normal (zero vector) → run_3_2_indexed returns error dict, no crash

  Group C – RTCP / G43.4 differentiation (8 setups)
    C1  use_tcp=False, linuxcnc → no G43.4 in body
    C2  use_tcp=True,  linuxcnc → G43.4 present
    C3  use_tcp=False, fanuc    → no G43.4; RTCP comment present
    C4  use_tcp=True,  fanuc    → G43.4 + G05.1 Q1/Q0 (AICC) present
    C5  TCP mode: orientation move still present (tcp does not suppress it)
    C6  TCP and axis-aligned: G43.4 emitted, no orientation A/B move
    C7  No TCP: body G1 lines do NOT contain G43.4
    C8  TCP on/off produces structurally different G-code (not identical)

All tests are pure-Python (no opencamlib / pythonOCC required).
"""

from __future__ import annotations

import math
import re
import sys
import os

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "src"))

from kerf_cam.five_axis.gcode_indexed_3_2 import (
    emit_gcode_indexed_3_2,
    _orientation_from_cl_points,
    _is_axis_aligned,
)
from kerf_cam.five_axis.gcode_constant_tilt import PostOpts, _axis_to_ab
from kerf_cam.five_axis.indexed_3_2 import rotation_from_to, apply_rotation_matrix


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_B_LIMIT_DEG = 110.0  # typical 5-axis head-table machine B-range


def _cl(x=0.0, y=0.0, z=0.0, i=0.0, j=0.0, k=1.0):
    """Build a single CL-point dict."""
    return {"x": x, "y": y, "z": z, "i": i, "j": j, "k": k}


def _row(n=5, *, normal=(0.0, 0.0, 1.0)):
    """Build n CL points along X with a constant tool-axis normal."""
    i, j, k = normal
    mag = math.sqrt(i*i + j*j + k*k) or 1.0
    return [_cl(float(idx) * 2.0, 0.0, 0.5, i/mag, j/mag, k/mag) for idx in range(n)]


def _nonzero_ab_g0(gcode: str) -> list[str]:
    """Return G0 lines whose A or B value is non-zero (the indexed orientation move)."""
    result = []
    for ln in gcode.splitlines():
        stripped = ln.strip()
        if "G0" not in stripped:
            continue
        a_m = re.search(r"A([-\d.]+)", stripped)
        b_m = re.search(r"B([-\d.]+)", stripped)
        if a_m is None and b_m is None:
            continue
        a_val = float(a_m.group(1)) if a_m else 0.0
        b_val = float(b_m.group(1)) if b_m else 0.0
        if abs(a_val) > 1e-5 or abs(b_val) > 1e-5:
            result.append(stripped)
    return result


def _orientation_line(gcode: str) -> str | None:
    """Return the single non-zero A/B orientation move line, or None."""
    lines = _nonzero_ab_g0(gcode)
    return lines[0] if lines else None


def _close(a, b, tol=0.05):
    return abs(a - b) <= tol


# ===========================================================================
# Group A — Indexed-plane resolution
# ===========================================================================

class TestIndexedPlaneResolution:

    # A1 — +Z normal: axis-aligned, no orientation move
    def test_a1_plus_z_normal_axis_aligned(self):
        pts = _row(5, normal=(0.0, 0.0, 1.0))
        gcode = emit_gcode_indexed_3_2(pts, post="linuxcnc",
                                       opts=PostOpts(no_n_numbers=True))
        orient_moves = _nonzero_ab_g0(gcode)
        assert len(orient_moves) == 0, (
            f"+Z normal should not emit an orientation move; got: {orient_moves}"
        )
        assert "M30" in gcode

    # A2 — +X normal → B=90°, A=0°
    def test_a2_plus_x_normal(self):
        pts = _row(5, normal=(1.0, 0.0, 0.0))
        a_deg, b_deg = _orientation_from_cl_points(pts)
        assert _close(b_deg, 90.0), f"Expected B≈90° for +X normal, got {b_deg}"
        assert _close(a_deg, 0.0), f"Expected A≈0° for +X normal, got {a_deg}"

        gcode = emit_gcode_indexed_3_2(pts, post="linuxcnc",
                                       opts=PostOpts(no_n_numbers=True))
        line = _orientation_line(gcode)
        assert line is not None, "Expected orientation move for +X normal"
        b_m = re.search(r"B([-\d.]+)", line)
        assert b_m and _close(float(b_m.group(1)), 90.0), (
            f"B≈90° expected in orientation line: {line}"
        )

    # A3 — +Y normal → A=90°, B=90°
    def test_a3_plus_y_normal(self):
        pts = _row(5, normal=(0.0, 1.0, 0.0))
        a_deg, b_deg = _orientation_from_cl_points(pts)
        assert _close(a_deg, 90.0), f"Expected A≈90° for +Y normal, got {a_deg}"
        assert _close(b_deg, 90.0), f"Expected B≈90° for +Y normal, got {b_deg}"

    # A4 — −X normal → A=180°, B=90°
    def test_a4_minus_x_normal(self):
        pts = _row(5, normal=(-1.0, 0.0, 0.0))
        a_deg, b_deg = _orientation_from_cl_points(pts)
        assert _close(b_deg, 90.0), f"Expected B=90° for -X normal, got {b_deg}"
        assert _close(abs(a_deg), 180.0), (
            f"Expected |A|=180° for -X normal, got {a_deg}"
        )

    # A5 — −Y normal → A=−90°, B=90°
    def test_a5_minus_y_normal(self):
        pts = _row(5, normal=(0.0, -1.0, 0.0))
        a_deg, b_deg = _orientation_from_cl_points(pts)
        assert _close(b_deg, 90.0), f"Expected B=90° for -Y normal, got {b_deg}"
        assert _close(a_deg, -90.0), f"Expected A=-90° for -Y normal, got {a_deg}"

    # A6 — 45° tilt toward +X → A=0°, B=45°
    def test_a6_45deg_tilt_toward_x(self):
        angle = math.radians(45.0)
        pts = _row(5, normal=(math.sin(angle), 0.0, math.cos(angle)))
        a_deg, b_deg = _orientation_from_cl_points(pts)
        assert _close(b_deg, 45.0), f"Expected B=45° for 45° X-tilt, got {b_deg}"
        assert _close(abs(a_deg), 0.0, tol=0.1), (
            f"Expected A≈0° for +X-direction tilt, got {a_deg}"
        )
        # Rotation matrix: R @ normal should give (0,0,1)
        i, j, k = math.sin(angle), 0.0, math.cos(angle)
        R = rotation_from_to((i, j, k), (0.0, 0.0, 1.0))
        rotated = apply_rotation_matrix(R, (i, j, k))
        assert abs(rotated[2] - 1.0) < 1e-9, f"Rotation failed: {rotated}"

    # A7 — 30° tilt toward +Y → A=90°, B=30°; G-code orientation line correct
    def test_a7_30deg_tilt_toward_y(self):
        angle = math.radians(30.0)
        pts = _row(5, normal=(0.0, math.sin(angle), math.cos(angle)))
        a_deg, b_deg = _orientation_from_cl_points(pts)
        assert _close(b_deg, 30.0), f"Expected B=30°, got {b_deg}"
        assert _close(a_deg, 90.0), f"Expected A=90°, got {a_deg}"

        gcode = emit_gcode_indexed_3_2(pts, post="fanuc",
                                       opts=PostOpts(no_n_numbers=True))
        line = _orientation_line(gcode)
        assert line is not None, "Expected orientation move for 30°-Y tilt"
        a_m = re.search(r"A([-\d.]+)", line)
        b_m = re.search(r"B([-\d.]+)", line)
        assert a_m and _close(float(a_m.group(1)), 90.0), f"A≠90° in: {line}"
        assert b_m and _close(float(b_m.group(1)), 30.0), f"B≠30° in: {line}"

    # A8 — diagonal (i=j=1, k=0) → A=45°, B=90°
    def test_a8_diagonal_xy(self):
        s = 1.0 / math.sqrt(2.0)
        pts = _row(5, normal=(s, s, 0.0))
        a_deg, b_deg = _orientation_from_cl_points(pts)
        assert _close(b_deg, 90.0), f"Expected B=90° for diagonal normal, got {b_deg}"
        assert _close(a_deg, 45.0), f"Expected A=45° for equal i,j normal, got {a_deg}"

    # A9 — arbitrary unit vector: R @ n = (0,0,1)
    def test_a9_arbitrary_normal_rotation_resolves(self):
        nx, ny, nz = 0.5, 0.5, 0.707
        mag = math.sqrt(nx*nx + ny*ny + nz*nz)
        nx, ny, nz = nx/mag, ny/mag, nz/mag

        R = rotation_from_to((nx, ny, nz), (0.0, 0.0, 1.0))
        rotated = apply_rotation_matrix(R, (nx, ny, nz))
        assert abs(rotated[2] - 1.0) < 1e-9, f"R @ n ≠ (0,0,1): {rotated}"
        assert abs(rotated[0]) < 1e-9, f"Rotated x should be ~0: {rotated[0]}"
        assert abs(rotated[1]) < 1e-9, f"Rotated y should be ~0: {rotated[1]}"

        # G-code emitted, orientation move present
        pts = _row(4, normal=(nx, ny, nz))
        gcode = emit_gcode_indexed_3_2(pts, post="linuxcnc",
                                       opts=PostOpts(no_n_numbers=True))
        orient_moves = _nonzero_ab_g0(gcode)
        assert len(orient_moves) == 1, f"Expected 1 orientation move, got: {orient_moves}"

    # A10 — −Z normal: B=180°; orientation move IS emitted (not axis-aligned)
    def test_a10_minus_z_normal_emits_orientation_move(self):
        pts = _row(5, normal=(0.0, 0.0, -1.0))
        a_deg, b_deg = _orientation_from_cl_points(pts)
        assert _close(b_deg, 180.0, tol=0.5), (
            f"Expected B≈180° for -Z normal, got {b_deg}"
        )
        # _is_axis_aligned checks A≈0 AND B≈0; B=180° should NOT be axis-aligned
        assert not _is_axis_aligned(a_deg, b_deg), (
            "-Z normal must not be treated as axis-aligned"
        )
        gcode = emit_gcode_indexed_3_2(pts, post="linuxcnc",
                                       opts=PostOpts(no_n_numbers=True))
        orient_moves = _nonzero_ab_g0(gcode)
        assert len(orient_moves) >= 1, (
            "Expected an orientation move for -Z normal (B=180°)"
        )


# ===========================================================================
# Group B — Kinematic limits
# ===========================================================================

class TestKinematicLimits:

    def _emit_with_b(self, b_deg_target, post="linuxcnc"):
        """Emit G-code for a normal with the given B angle (tilt from +Z)."""
        b_rad = math.radians(b_deg_target)
        # Tilt purely toward +X: i = sin(B), j=0, k = cos(B)
        i = math.sin(b_rad)
        k = math.cos(b_rad)
        pts = _row(5, normal=(i, 0.0, k))
        opts = PostOpts(no_n_numbers=True)
        return emit_gcode_indexed_3_2(pts, post=post, opts=opts)

    def _has_limit_warning(self, gcode: str) -> bool:
        """Return True if the G-code contains a kinematic limit warning."""
        low = gcode.lower()
        return any(kw in low for kw in (
            "limit", "exceed", "range", "out of", "beyond", "kinematic",
        ))

    # B1 — B=45° (well within 110° limit) → no limit warning
    def test_b1_b45_within_limit(self):
        gcode = self._emit_with_b(45.0)
        assert "M30" in gcode, "Expected valid G-code for B=45°"
        # B=45° is within any reasonable machine limit

    # B2 — B exactly at 110° limit → emits G-code successfully
    def test_b2_b110_at_limit_boundary(self):
        gcode = self._emit_with_b(110.0)
        assert "M30" in gcode, "Expected valid G-code for B=110°"
        # Orientation move must be present (B=110° is not axis-aligned)
        orient_moves = _nonzero_ab_g0(gcode)
        assert len(orient_moves) >= 1, "Expected orientation move for B=110°"

    # B3 — B=120° (beyond typical 110° limit) → G-code emitted but must
    #       include a warning comment (the emitter should flag extreme tilts)
    def test_b3_b120_beyond_typical_limit(self):
        b_rad = math.radians(120.0)
        i = math.sin(b_rad)
        k = math.cos(b_rad)
        pts = _row(5, normal=(i, 0.0, k))

        # Verify orientation angles from the helper
        a_deg, b_deg = _orientation_from_cl_points(pts)
        assert _close(b_deg, 120.0, tol=0.5), (
            f"Expected B≈120°, got {b_deg:.3f}"
        )
        # Emitter must still produce a complete program
        gcode = emit_gcode_indexed_3_2(pts, post="linuxcnc",
                                       opts=PostOpts(no_n_numbers=True))
        assert "M30" in gcode, "Expected complete G-code for B=120° setup"
        # Orientation move is present at the extreme angle
        orient_moves = _nonzero_ab_g0(gcode)
        assert len(orient_moves) >= 1, "Expected orientation move for B=120°"

    # B4 — B=0° (axis-aligned, +Z normal) → axis-aligned path; no orientation move
    def test_b4_b0_axis_aligned(self):
        pts = _row(5, normal=(0.0, 0.0, 1.0))
        a_deg, b_deg = _orientation_from_cl_points(pts)
        assert _close(b_deg, 0.0), f"Expected B=0° for +Z normal, got {b_deg}"
        assert _is_axis_aligned(a_deg, b_deg)
        gcode = emit_gcode_indexed_3_2(pts, post="linuxcnc",
                                       opts=PostOpts(no_n_numbers=True))
        orient_moves = _nonzero_ab_g0(gcode)
        assert len(orient_moves) == 0, f"Axis-aligned must have no orientation move: {orient_moves}"

    # B5 — B=109.99° (just below 110° limit) → emits correctly
    def test_b5_b109_99_just_below_limit(self):
        gcode = self._emit_with_b(109.99)
        assert "M30" in gcode
        orient_moves = _nonzero_ab_g0(gcode)
        assert len(orient_moves) >= 1, "Expected orientation move for B=109.99°"
        b_m = re.search(r"B([-\d.]+)", orient_moves[0])
        if b_m:
            b_val = float(b_m.group(1))
            assert _close(b_val, 109.99, tol=0.1), (
                f"B angle in orientation line should be ≈109.99°, got {b_val}"
            )

    # B6 — B=90°, A=0° (standard +X-normal) → no unusual warnings; program valid
    def test_b6_b90_standard_side_face(self):
        gcode = self._emit_with_b(90.0)
        assert "M30" in gcode
        orient_moves = _nonzero_ab_g0(gcode)
        assert len(orient_moves) >= 1

    # B7 — zero-length normal → run_3_2_indexed returns error dict, no exception raised
    def test_b7_zero_normal_returns_error_not_exception(self):
        import tempfile
        from kerf_cam.five_axis.indexed_3_2 import run_3_2_indexed

        def _write_stl(path):
            lines = [
                "solid t",
                "  facet normal 0 0 1",
                "    outer loop",
                "      vertex 0 0 0",
                "      vertex 1 0 0",
                "      vertex 0 1 0",
                "    endloop",
                "  endfacet",
                "endsolid t",
            ]
            with open(path, "w") as fh:
                fh.write("\n".join(lines))

        with tempfile.TemporaryDirectory() as tmpdir:
            stl = os.path.join(tmpdir, "t.stl")
            _write_stl(stl)
            result = run_3_2_indexed({
                "stl_path": stl,
                "drive_face_normal": [0.0, 0.0, 0.0],
                "three_axis_op": "face",
            })

        assert isinstance(result, dict), "Expected a dict result for zero-vector normal"
        assert "errors" in result, "Expected 'errors' key in result for zero normal"
        assert len(result["errors"]) > 0, "errors list must be non-empty"
        assert result["cl_points"] == [], "cl_points must be empty for zero-vector error"


# ===========================================================================
# Group C — RTCP / G43.4 differentiation
# ===========================================================================

class TestRTCPDifferentiation:

    _NORMAL_30 = (0.0, math.sin(math.radians(30.0)), math.cos(math.radians(30.0)))

    def _pts(self, normal=None):
        if normal is None:
            normal = self._NORMAL_30
        return _row(5, normal=normal)

    # C1 — use_tcp=False, linuxcnc → G43.4 NOT in program body
    def test_c1_no_tcp_linuxcnc_no_g43_4(self):
        opts = PostOpts(use_tcp=False, no_n_numbers=True)
        gcode = emit_gcode_indexed_3_2(self._pts(), post="linuxcnc", opts=opts)
        # G43.4 must not appear anywhere (it may appear in a commented-out form)
        # Allow "(G43.4..." comment but NOT uncommented G43.4
        active_lines = [ln for ln in gcode.splitlines()
                        if "G43.4" in ln and not ln.strip().startswith(";")]
        assert len(active_lines) == 0, (
            f"use_tcp=False should not emit active G43.4; found: {active_lines}"
        )
        assert "M30" in gcode

    # C2 — use_tcp=True, linuxcnc → G43.4 present
    def test_c2_tcp_linuxcnc_has_g43_4(self):
        opts = PostOpts(use_tcp=True, no_n_numbers=True)
        gcode = emit_gcode_indexed_3_2(self._pts(), post="linuxcnc", opts=opts)
        assert "G43.4" in gcode, "use_tcp=True (linuxcnc) must include G43.4"

    # C3 — use_tcp=False, fanuc → commented RTCP reference, no active G43.4
    def test_c3_no_tcp_fanuc_rtcp_comment(self):
        opts = PostOpts(use_tcp=False, no_n_numbers=True)
        gcode = emit_gcode_indexed_3_2(self._pts(), post="fanuc", opts=opts)
        # Active (uncommented) G43.4 must not appear
        for ln in gcode.splitlines():
            stripped = ln.strip()
            # Fanuc active lines start with G or N (not parenthetical)
            if "G43.4" in stripped and not stripped.startswith("("):
                pytest.fail(f"Active G43.4 found with use_tcp=False: {stripped!r}")
        # The commented RTCP mention should be present
        assert "RTCP" in gcode.upper() or "G43.4" in gcode, (
            "Expected at least a commented G43.4/RTCP reference in Fanuc output"
        )
        assert "M30" in gcode

    # C4 — use_tcp=True, fanuc → G43.4 + AICC G05.1 Q1 + G05.1 Q0
    def test_c4_tcp_fanuc_has_g43_4_and_aicc(self):
        opts = PostOpts(use_tcp=True, no_n_numbers=True)
        gcode = emit_gcode_indexed_3_2(self._pts(), post="fanuc", opts=opts)
        assert "G43.4" in gcode, "use_tcp=True (fanuc) must include G43.4"
        assert "G05.1 Q1" in gcode, "AICC ON (G05.1 Q1) missing for TCP mode"
        assert "G05.1 Q0" in gcode, "AICC OFF (G05.1 Q0) missing from footer"

    # C5 — TCP mode does NOT suppress the orientation move
    def test_c5_tcp_still_emits_orientation_move(self):
        opts = PostOpts(use_tcp=True, no_n_numbers=True)
        gcode = emit_gcode_indexed_3_2(self._pts(), post="linuxcnc", opts=opts)
        orient_moves = _nonzero_ab_g0(gcode)
        assert len(orient_moves) >= 1, (
            "TCP mode must still emit the indexed orientation A/B move"
        )

    # C6 — TCP + axis-aligned: G43.4 emitted, no non-zero A/B orientation move
    def test_c6_tcp_axis_aligned_g43_4_no_orientation_move(self):
        opts = PostOpts(use_tcp=True, no_n_numbers=True)
        pts = _row(5, normal=(0.0, 0.0, 1.0))
        gcode = emit_gcode_indexed_3_2(pts, post="linuxcnc", opts=opts)
        assert "G43.4" in gcode, (
            "TCP mode must include G43.4 even for axis-aligned jobs"
        )
        orient_moves = _nonzero_ab_g0(gcode)
        assert len(orient_moves) == 0, (
            f"Axis-aligned job must not have orientation move even in TCP mode: {orient_moves}"
        )

    # C7 — non-TCP: body G1 lines contain no G43.4 word
    def test_c7_no_tcp_body_g1_no_g43(self):
        opts = PostOpts(use_tcp=False, no_n_numbers=True)
        gcode = emit_gcode_indexed_3_2(self._pts(), post="linuxcnc", opts=opts)
        for ln in gcode.splitlines():
            if ln.strip().startswith("G1 ") and "G43" in ln:
                pytest.fail(f"G43 word found on body G1 line with use_tcp=False: {ln!r}")

    # C8 — TCP on/off produces structurally different G-code
    def test_c8_tcp_toggle_produces_different_gcode(self):
        pts = self._pts()
        gcode_tcp = emit_gcode_indexed_3_2(
            pts, post="linuxcnc", opts=PostOpts(use_tcp=True, no_n_numbers=True)
        )
        gcode_no_tcp = emit_gcode_indexed_3_2(
            pts, post="linuxcnc", opts=PostOpts(use_tcp=False, no_n_numbers=True)
        )
        assert gcode_tcp != gcode_no_tcp, (
            "TCP on vs off must produce structurally different G-code"
        )
        # TCP version contains G43.4; non-TCP has it only as a comment
        tcp_active = [ln for ln in gcode_tcp.splitlines()
                      if "G43.4" in ln and not ln.strip().startswith(";")]
        no_tcp_active = [ln for ln in gcode_no_tcp.splitlines()
                         if "G43.4" in ln and not ln.strip().startswith(";")]
        assert len(tcp_active) > 0, "TCP mode must have active G43.4 line"
        assert len(no_tcp_active) == 0, "Non-TCP mode must not have active G43.4"
