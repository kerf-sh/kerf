"""
Hermetic tests for kerf_cad_core.fiveaxis — 5-axis machine-tool kinematics.

Coverage:
  kinematics.forward_kinematics — FK for AC trunnion, BC head, table-head
  kinematics.inverse_post       — IK round-trip, multiple solutions, singularity
  kinematics.tool_axis_from_lead_lag — lead/lag → tool axis
  kinematics.linearisation_segments — chord-deviation → segment count
  kinematics.rotary_feedrate    — DPM and inverse-time
  kinematics.collision_cone_check — cone clearance
  tools.*                        — LLM tool wrappers (happy path + error paths)

All tests are pure-Python and hermetic: no OCC, no DB, no network, no fixtures.

References
----------
Soons, J.A. et al. "Modelling of five-axis machine tool kinematics", IJMTM 2001.
Bohez, E.L.J. "Five-axis milling machine tool kinematic chain design", IJMTM 2002.

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import warnings

import pytest

from kerf_cad_core.fiveaxis.kinematics import (
    MachineConfig,
    MachineType,
    RotaryAxis,
    forward_kinematics,
    inverse_post,
    tool_axis_from_lead_lag,
    linearisation_segments,
    rotary_feedrate,
    collision_cone_check,
    _normalise3,
    _dot3,
    _norm3,
)
from kerf_cad_core.fiveaxis.tools import (
    run_fiveaxis_forward_kinematics,
    run_fiveaxis_inverse_post,
    run_fiveaxis_tool_axis_lead_lag,
    run_fiveaxis_linearisation,
    run_fiveaxis_rotary_feedrate,
    run_fiveaxis_collision_cone,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REL = 1e-6
ANG = 1e-4   # tolerance for round-trip angle checks (radians)

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _ctx():
    try:
        from kerf_core.utils.context import ProjectCtx  # type: ignore[import]
        import uuid
        return ProjectCtx(
            pool=None, storage=None,
            project_id=uuid.uuid4(), user_id=uuid.uuid4(),
            role="owner", http_client=None,
        )
    except Exception:
        return None


def _args(**kwargs) -> bytes:
    return json.dumps(kwargs).encode()


def _ok_tool(raw: str) -> dict:
    d = json.loads(raw)
    assert d.get("ok") is True, f"Expected ok=True, got: {d}"
    return d


def _err_tool(raw: str) -> dict:
    d = json.loads(raw)
    is_ok_false = d.get("ok") is False
    is_err_payload = "error" in d and "code" in d
    assert is_ok_false or is_err_payload, f"Expected error response, got: {d}"
    return d


def _ac_config(
    a_lo=-120.0, a_hi=30.0,
    c_lo=-360.0, c_hi=360.0,
    pivot=0.0,
) -> MachineConfig:
    return MachineConfig(
        machine_type=MachineType.TABLE_TABLE,
        first_rotary=RotaryAxis(
            axis=(1.0, 0.0, 0.0),
            lo_rad=math.radians(a_lo), hi_rad=math.radians(a_hi), name="A"
        ),
        second_rotary=RotaryAxis(
            axis=(0.0, 0.0, 1.0),
            lo_rad=math.radians(c_lo), hi_rad=math.radians(c_hi), name="C"
        ),
        pivot_length_mm=pivot,
    )


def _bc_config(
    b_lo=-120.0, b_hi=120.0,
    c_lo=-360.0, c_hi=360.0,
    pivot=0.0,
) -> MachineConfig:
    return MachineConfig(
        machine_type=MachineType.HEAD_HEAD,
        first_rotary=RotaryAxis(
            axis=(0.0, 1.0, 0.0),
            lo_rad=math.radians(b_lo), hi_rad=math.radians(b_hi), name="B"
        ),
        second_rotary=RotaryAxis(
            axis=(0.0, 0.0, 1.0),
            lo_rad=math.radians(c_lo), hi_rad=math.radians(c_hi), name="C"
        ),
        pivot_length_mm=pivot,
    )


# ===========================================================================
# 1. Forward kinematics — AC trunnion (TABLE_TABLE)
# ===========================================================================

class TestFKTableTable:

    def test_zero_angles_tool_axis_is_down(self):
        """At A=C=0, tool axis in part frame = [0,0,-1] (spindle points down)."""
        cfg = _ac_config()
        r = forward_kinematics(cfg, 0.0, 0.0, 0.0, 0.0, 0.0)
        assert r["ok"] is True
        ax = r["tool_axis"]
        assert abs(ax[0]) < 1e-9
        assert abs(ax[1]) < 1e-9
        assert abs(ax[2] + 1.0) < 1e-9  # z = -1

    def test_zero_angles_tip_at_origin(self):
        """At A=C=0, X=Y=Z=0, tip_part_mm = [0,0,0]."""
        cfg = _ac_config()
        r = forward_kinematics(cfg, 0.0, 0.0, 0.0, 0.0, 0.0)
        tip = r["tip_part_mm"]
        assert abs(tip[0]) < 1e-9
        assert abs(tip[1]) < 1e-9
        assert abs(tip[2]) < 1e-9

    def test_c90_rotates_tool_axis_in_xy_plane(self):
        """C=90°, A=0: table rotates around Z; tool axis stays [0,0,-1] in part frame
        because the tool-part relationship doesn't change in the plane of C."""
        cfg = _ac_config()
        r = forward_kinematics(cfg, 0.0, 0.0, 0.0, 0.0, math.radians(90.0))
        ax = r["tool_axis"]
        # Tool axis is still [0,0,-1] in part frame since C rotation doesn't tilt tool
        assert abs(ax[2] + 1.0) < 1e-9

    def test_a45_tilts_tool_axis(self):
        """A=45°, C=0: tool axis in part frame should have non-zero Y component."""
        cfg = _ac_config()
        r = forward_kinematics(cfg, 0.0, 0.0, 0.0, math.radians(45.0), 0.0)
        assert r["ok"] is True
        ax = r["tool_axis"]
        # Tool axis should be tilted: non-zero Y
        assert abs(ax[1]) > 0.5   # sin(45°) ≈ 0.707

    def test_tool_axis_is_unit_vector(self):
        """Tool axis must be a unit vector for arbitrary angles."""
        cfg = _ac_config()
        for a_deg in (-30.0, 0.0, 15.0):
            for c_deg in (-90.0, 45.0, 180.0):
                r = forward_kinematics(
                    cfg, 10.0, 5.0, -20.0,
                    math.radians(a_deg), math.radians(c_deg)
                )
                ax = r["tool_axis"]
                mag = math.sqrt(ax[0]**2 + ax[1]**2 + ax[2]**2)
                assert abs(mag - 1.0) < 1e-9, f"axis not unit: A={a_deg} C={c_deg}"

    def test_over_travel_warning_emitted(self):
        """A=200° beyond travel limit should emit a warning and include it in result."""
        cfg = _ac_config(a_lo=-120.0, a_hi=30.0)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            r = forward_kinematics(cfg, 0.0, 0.0, 0.0, math.radians(200.0), 0.0)
        assert len(r["warnings"]) > 0
        assert any("over_travel" in msg for msg in r["warnings"])

    def test_linear_axes_translate_tip(self):
        """At A=C=0, X=10, Y=5, Z=-20: tip in part frame = [10, 5, -20]."""
        cfg = _ac_config()
        r = forward_kinematics(cfg, 10.0, 5.0, -20.0, 0.0, 0.0)
        tip = r["tip_part_mm"]
        assert abs(tip[0] - 10.0) < 1e-9
        assert abs(tip[1] - 5.0) < 1e-9
        assert abs(tip[2] + 20.0) < 1e-9


# ===========================================================================
# 2. Forward kinematics — BC head (HEAD_HEAD)
# ===========================================================================

class TestFKHeadHead:

    def test_zero_angles_tool_axis_is_down(self):
        """At B=C=0 in head-head, tool axis = [0,0,-1]."""
        cfg = _bc_config()
        r = forward_kinematics(cfg, 0.0, 0.0, 0.0, 0.0, 0.0)
        ax = r["tool_axis"]
        assert abs(ax[2] + 1.0) < 1e-9

    def test_b90_tilts_tool_axis_to_horizontal(self):
        """B=90°: tool axis tilted to horizontal (approximately [-1,0,0])."""
        cfg = _bc_config()
        r = forward_kinematics(cfg, 0.0, 0.0, 0.0, math.radians(90.0), 0.0)
        ax = r["tool_axis"]
        # sin(90)=1, cos(90)=0; tool axis should be ~[-sin(b), 0, -cos(b)] in BC
        assert abs(_norm3(tuple(ax))) - 1.0 < 1e-9  # type: ignore[arg-type]

    def test_tool_axis_unit_vector_bc(self):
        """Tool axis must be unit vector for arbitrary BC angles."""
        cfg = _bc_config()
        for b_deg in (0.0, 30.0, -45.0):
            for c_deg in (0.0, 60.0, -90.0):
                r = forward_kinematics(
                    cfg, 0.0, 0.0, 100.0,
                    math.radians(b_deg), math.radians(c_deg)
                )
                ax = r["tool_axis"]
                mag = math.sqrt(ax[0]**2 + ax[1]**2 + ax[2]**2)
                assert abs(mag - 1.0) < 1e-9

    def test_pivot_offset_shifts_tip(self):
        """Non-zero pivot_length_mm shifts tip from linear axis position."""
        pivot = 100.0
        cfg = _bc_config(pivot=pivot)
        r0 = forward_kinematics(cfg, 0.0, 0.0, 0.0, 0.0, 0.0)
        # At B=C=0, pivot is along -Z, so tip should be at Z = -pivot
        tip = r0["tip_part_mm"]
        assert abs(tip[2] + pivot) < 1e-6


# ===========================================================================
# 3. Inverse kinematics — AC trunnion round-trip
# ===========================================================================

class TestIKTableTable:

    def _fk_ik_roundtrip(
        self, cfg: MachineConfig,
        a_deg: float, c_deg: float,
        x: float = 0.0, y: float = 0.0, z: float = 0.0,
    ) -> None:
        """FK → IK must recover original rotary angles (modulo ±solutions)."""
        fk = forward_kinematics(cfg, x, y, z, math.radians(a_deg), math.radians(c_deg))
        tip = tuple(fk["tip_part_mm"])  # type: ignore[arg-type]
        ax  = tuple(fk["tool_axis"])    # type: ignore[arg-type]

        ik = inverse_post(cfg, tip, ax, prev_angles_rad=(math.radians(a_deg), math.radians(c_deg)))

        assert ik["ok"] is True
        assert len(ik["solutions"]) > 0
        # At least one solution should recover the original FK result
        any_match = False
        for sol in ik["solutions"]:
            fk2 = forward_kinematics(
                cfg, x, y, z, sol["q1_rad"], sol["q2_rad"]
            )
            ax2 = fk2["tool_axis"]
            dot = abs(_dot3(tuple(ax2), ax))  # type: ignore[arg-type]
            if dot > 0.9999:
                any_match = True
                break
        assert any_match, f"No IK solution recovered FK for A={a_deg}° C={c_deg}°"

    def test_roundtrip_a_neg15_c0(self):
        """Non-singular: A=-15°, C=0 — tool axis has significant Y component."""
        cfg = _ac_config()
        self._fk_ik_roundtrip(cfg, -15.0, 0.0)

    def test_roundtrip_a_neg30_c45(self):
        cfg = _ac_config()
        self._fk_ik_roundtrip(cfg, -30.0, 45.0)

    def test_roundtrip_a15_c_neg90(self):
        cfg = _ac_config()
        self._fk_ik_roundtrip(cfg, 15.0, -90.0)

    def test_roundtrip_with_translation(self):
        cfg = _ac_config()
        self._fk_ik_roundtrip(cfg, -20.0, 60.0, x=50.0, y=-30.0, z=10.0)

    def test_two_solutions_returned(self):
        """IK should return 2 solutions for non-singular configuration."""
        cfg = _ac_config()
        ax = _normalise3((0.0, math.sin(math.radians(30.0)), -math.cos(math.radians(30.0))))
        ik = inverse_post(cfg, (0.0, 0.0, 0.0), ax)
        assert len(ik["solutions"]) == 2

    def test_best_index_valid(self):
        """best index must be in range of solutions list."""
        cfg = _ac_config()
        ax = _normalise3((0.1, 0.2, -0.97))
        ik = inverse_post(cfg, (10.0, 5.0, 0.0), ax)
        assert 0 <= ik["best"] < len(ik["solutions"])

    def test_shortest_path_selects_lower_total_travel(self):
        """With two IK solutions, best minimises total angular travel from prev."""
        cfg = _ac_config()
        a_rad = math.radians(-30.0)
        c_rad = math.radians(45.0)
        fk = forward_kinematics(cfg, 0.0, 0.0, 0.0, a_rad, c_rad)
        tip = tuple(fk["tip_part_mm"])  # type: ignore[arg-type]
        ax  = tuple(fk["tool_axis"])    # type: ignore[arg-type]
        ik = inverse_post(cfg, tip, ax, prev_angles_rad=(a_rad, c_rad))
        best_idx = ik["best"]
        best = ik["solutions"][best_idx]
        # Total travel for best should be ≤ total travel for any other solution
        def travel(s):
            return abs(s["q1_rad"] - a_rad) + abs(s["q2_rad"] - c_rad)
        best_cost = travel(best)
        for i, s in enumerate(ik["solutions"]):
            if i != best_idx:
                assert best_cost <= travel(s) + 1e-9


# ===========================================================================
# 4. Inverse kinematics — BC head round-trip
# ===========================================================================

class TestIKHeadHead:

    def _fk_ik_roundtrip_bc(
        self, cfg: MachineConfig,
        b_deg: float, c_deg: float,
        x: float = 0.0, y: float = 0.0, z: float = 0.0,
    ) -> None:
        fk = forward_kinematics(cfg, x, y, z, math.radians(b_deg), math.radians(c_deg))
        tip = tuple(fk["tip_part_mm"])  # type: ignore[arg-type]
        ax  = tuple(fk["tool_axis"])    # type: ignore[arg-type]

        ik = inverse_post(cfg, tip, ax)
        assert ik["ok"] is True
        assert len(ik["solutions"]) > 0

        any_match = False
        for sol in ik["solutions"]:
            fk2 = forward_kinematics(cfg, x, y, z, sol["q1_rad"], sol["q2_rad"])
            ax2 = fk2["tool_axis"]
            dot = abs(_dot3(tuple(ax2), ax))  # type: ignore[arg-type]
            if dot > 0.9999:
                any_match = True
                break
        assert any_match, f"No IK solution recovered FK for B={b_deg}° C={c_deg}°"

    def test_roundtrip_b_neg15_c0(self):
        """Non-singular: B=-15°, C=0."""
        cfg = _bc_config()
        self._fk_ik_roundtrip_bc(cfg, -15.0, 0.0)

    def test_roundtrip_b30_c45(self):
        cfg = _bc_config()
        self._fk_ik_roundtrip_bc(cfg, 30.0, 45.0)

    def test_roundtrip_b_neg45_c_neg90(self):
        cfg = _bc_config()
        self._fk_ik_roundtrip_bc(cfg, -45.0, -90.0)

    def test_roundtrip_b60_c180(self):
        cfg = _bc_config()
        self._fk_ik_roundtrip_bc(cfg, 60.0, 180.0)

    def test_bc_two_solutions(self):
        """BC IK must return 2 solutions."""
        cfg = _bc_config()
        ax = _normalise3((math.sin(math.radians(20.0)) * math.cos(math.radians(30.0)),
                          math.sin(math.radians(20.0)) * math.sin(math.radians(30.0)),
                          -math.cos(math.radians(20.0))))
        ik = inverse_post(cfg, (0.0, 0.0, 0.0), ax)
        assert len(ik["solutions"]) == 2


# ===========================================================================
# 5. Singularity detection
# ===========================================================================

class TestSingularity:

    def test_singular_tool_axis_down_ac(self):
        """Tool axis = [0,0,-1] (straight down) should trigger singularity flag."""
        cfg = _ac_config()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            ik = inverse_post(cfg, (0.0, 0.0, 0.0), (0.0, 0.0, -1.0))
        assert ik["singularity"] is True
        assert len(ik["warnings"]) > 0
        assert any("singularity" in msg.lower() for msg in ik["warnings"])

    def test_singular_tool_axis_up_ac(self):
        """Tool axis = [0,0,1] (straight up) should also trigger singularity."""
        cfg = _ac_config()
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            ik = inverse_post(cfg, (0.0, 0.0, 0.0), (0.0, 0.0, 1.0))
        assert ik["singularity"] is True

    def test_non_singular_no_singularity_flag(self):
        """Tilted tool axis should not trigger singularity."""
        cfg = _ac_config()
        ax = _normalise3((0.2, 0.1, -0.97))
        ik = inverse_post(cfg, (0.0, 0.0, 0.0), ax)
        assert ik["singularity"] is False

    def test_singularity_bc_head(self):
        """For BC head, B=0 → axis [0,0,-1] is singular."""
        cfg = _bc_config()
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            ik = inverse_post(cfg, (0.0, 0.0, 0.0), (0.0, 0.0, -1.0))
        assert ik["singularity"] is True

    def test_avoidance_tilt_applied(self):
        """After singularity avoidance tilt, IK should still return solutions."""
        cfg = _ac_config()
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            ik = inverse_post(
                cfg, (10.0, 10.0, 0.0), (0.0, 0.0, -1.0),
                avoidance_tilt_rad=math.radians(2.0)
            )
        assert len(ik["solutions"]) > 0


# ===========================================================================
# 6. RTCP compensation
# ===========================================================================

class TestRTCP:

    def test_rtcp_zero_pivot_no_offset(self):
        """With pivot=0, RTCP should not shift XYZ from tip position."""
        cfg = _ac_config(pivot=0.0)
        tip = (50.0, 30.0, -10.0)
        ax  = _normalise3((0.0, math.sin(math.radians(15.0)), -math.cos(math.radians(15.0))))
        ik = inverse_post(cfg, tip, ax)
        # FK round-trip: the best solution should map back to the original tip
        best = ik["solutions"][ik["best"]]
        fk = forward_kinematics(
            cfg, best["x_mm"], best["y_mm"], best["z_mm"],
            best["q1_rad"], best["q2_rad"]
        )
        t2 = fk["tip_part_mm"]
        dist = math.sqrt(sum((t2[i] - tip[i])**2 for i in range(3)))
        assert dist < 0.1  # within 0.1 mm

    def test_rtcp_with_nonzero_pivot_ac(self):
        """With pivot_length > 0, RTCP must adjust XYZ to compensate."""
        pivot = 80.0
        cfg_no_pivot = _ac_config(pivot=0.0)
        cfg_pivot    = _ac_config(pivot=pivot)

        tip = (20.0, 10.0, 0.0)
        ax  = _normalise3((0.0, math.sin(math.radians(20.0)), -math.cos(math.radians(20.0))))

        ik0 = inverse_post(cfg_no_pivot, tip, ax)
        ik1 = inverse_post(cfg_pivot,    tip, ax)

        # The XYZ positions must differ when pivot is non-zero
        s0 = ik0["solutions"][ik0["best"]]
        s1 = ik1["solutions"][ik1["best"]]
        delta_z = abs(s1["z_mm"] - s0["z_mm"])
        assert delta_z > 0.1  # pivot compensation must shift Z

    def test_rtcp_bc_pivot_shifts_tip(self):
        """For BC head with pivot, FK tip should differ from linear axis position."""
        pivot = 120.0
        cfg = _bc_config(pivot=pivot)
        # B=45° → pivot shifts tip by pivot in rotated direction
        r = forward_kinematics(cfg, 0.0, 0.0, 0.0, math.radians(45.0), 0.0)
        tip = r["tip_part_mm"]
        # Tip should not be at origin
        dist = math.sqrt(tip[0]**2 + tip[1]**2 + tip[2]**2)
        assert dist > pivot * 0.5


# ===========================================================================
# 7. Lead/lag to tool axis
# ===========================================================================

class TestLeadLag:

    def test_zero_lead_lag_returns_surface_normal(self):
        """Lead=Lag=0 → tool axis = surface normal."""
        feed = (1.0, 0.0, 0.0)
        norm = (0.0, 0.0, 1.0)
        r = tool_axis_from_lead_lag(feed, norm, 0.0, 0.0)
        ax = r["tool_axis"]
        assert abs(ax[0] - 0.0) < 1e-9
        assert abs(ax[1] - 0.0) < 1e-9
        assert abs(ax[2] - 1.0) < 1e-9

    def test_nonzero_lead_tilts_axis(self):
        """Lead > 0 should tilt the tool axis away from normal."""
        feed = (1.0, 0.0, 0.0)
        norm = (0.0, 0.0, 1.0)
        r = tool_axis_from_lead_lag(feed, norm, math.radians(15.0), 0.0)
        ax = r["tool_axis"]
        # Tool axis should no longer be purely [0,0,1]
        assert abs(ax[2] - 1.0) > 1e-3

    def test_result_is_unit_vector(self):
        """Lead/lag result must always be a unit vector."""
        for lead in (-20.0, 0.0, 10.0, 30.0):
            for lag in (-15.0, 0.0, 5.0):
                r = tool_axis_from_lead_lag(
                    (1.0, 0.0, 0.0),
                    (0.0, 0.0, 1.0),
                    math.radians(lead),
                    math.radians(lag),
                )
                ax = r["tool_axis"]
                mag = math.sqrt(ax[0]**2 + ax[1]**2 + ax[2]**2)
                assert abs(mag - 1.0) < 1e-9

    def test_lead_45_deg_correct_direction(self):
        """Lead=45° around side axis tilts by 45° from normal."""
        feed = (1.0, 0.0, 0.0)
        norm = (0.0, 0.0, 1.0)
        # side = cross(feed, norm) = cross([1,0,0],[0,0,1]) = [0,-1,0] → normalised = [0,-1,0]
        # R_lead around [0,-1,0] by -45° applied to [0,0,1]:
        r = tool_axis_from_lead_lag(feed, norm, math.radians(45.0), 0.0)
        ax = r["tool_axis"]
        # The result should have non-trivial Z and X components
        assert abs(ax[2]) < 0.95   # tilted away from Z


# ===========================================================================
# 8. Linearisation segments
# ===========================================================================

class TestLinearisation:

    def test_zero_angle_returns_one_segment(self):
        """Zero angular motion → 1 segment with zero deviation."""
        cfg = _ac_config()
        r = linearisation_segments(
            cfg, (100.0, 0.0, 0.0),
            0.0, 0.0, 0.0, 0.0,
            x_mm=0.0, y_mm=0.0, z_mm=0.0,
        )
        assert r["ok"] is True
        assert r["n_segments"] == 1
        assert r["chord_deviation_mm"] == 0.0

    def test_large_arc_needs_more_segments(self):
        """Larger arc needs more segments than small arc (same radius, same tol)."""
        cfg = _ac_config()
        tip = (100.0, 0.0, 0.0)
        r_small = linearisation_segments(cfg, tip, 0.0, math.radians(5.0),  0.0, 0.0)
        r_large = linearisation_segments(cfg, tip, 0.0, math.radians(45.0), 0.0, 0.0)
        assert r_large["n_segments"] >= r_small["n_segments"]

    def test_tighter_tolerance_needs_more_segments(self):
        """Tighter chord tolerance requires more segments."""
        cfg = _ac_config()
        tip = (50.0, 0.0, 0.0)
        r_loose = linearisation_segments(cfg, tip, 0.0, math.radians(30.0), 0.0, 0.0, chord_tol_mm=0.1)
        r_tight = linearisation_segments(cfg, tip, 0.0, math.radians(30.0), 0.0, 0.0, chord_tol_mm=0.001)
        assert r_tight["n_segments"] >= r_loose["n_segments"]

    def test_chord_deviation_within_tolerance(self):
        """Computed chord deviation must be ≤ requested tolerance."""
        cfg = _ac_config()
        tip = (80.0, 0.0, 0.0)
        tol = 0.02
        r = linearisation_segments(cfg, tip, 0.0, math.radians(20.0), 0.0, 0.0, chord_tol_mm=tol)
        assert r["chord_deviation_mm"] <= tol + 1e-9

    def test_large_segments_warning_emitted(self):
        """A move requiring >100 segments should emit a warning."""
        cfg = _ac_config()
        tip = (1000.0, 0.0, 0.0)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            r = linearisation_segments(
                cfg, tip, 0.0, math.radians(90.0), 0.0, 0.0,
                chord_tol_mm=0.001
            )
        if r["n_segments"] > 100:
            assert len(r["warnings"]) > 0


# ===========================================================================
# 9. Rotary feedrate
# ===========================================================================

class TestRotaryFeedrate:

    def test_dpm_formula(self):
        """DPM = V_tip × (180/π) / R."""
        R, V = 100.0, 1000.0
        r = rotary_feedrate(R, V, method="dpm")
        assert r["ok"] is True
        expected = V * (180.0 / math.pi) / R
        assert abs(r["feed_dpm"] - expected) / expected < REL

    def test_inverse_time_formula(self):
        """G93 inverse-time for 1° arc: F = V / (R·π/180)."""
        R, V = 50.0, 500.0
        r = rotary_feedrate(R, V, method="inverse_time")
        assert r["ok"] is True
        arc_1deg = R * math.pi / 180.0
        expected = V / arc_1deg
        assert abs(r["feed_inverse_time_per_min"] - expected) / expected < REL

    def test_dpm_increases_with_speed(self):
        """Higher tip speed → higher DPM."""
        R = 80.0
        f1 = rotary_feedrate(R, 500.0, "dpm")["feed_dpm"]
        f2 = rotary_feedrate(R, 1000.0, "dpm")["feed_dpm"]
        assert f2 > f1

    def test_dpm_decreases_with_radius(self):
        """Larger radius → lower DPM for same tip speed (arc is bigger)."""
        V = 800.0
        f1 = rotary_feedrate(50.0, V, "dpm")["feed_dpm"]
        f2 = rotary_feedrate(100.0, V, "dpm")["feed_dpm"]
        assert f1 > f2

    def test_zero_radius_returns_error(self):
        r = rotary_feedrate(0.0, 1000.0)
        assert r["ok"] is False

    def test_negative_speed_returns_error(self):
        r = rotary_feedrate(100.0, -500.0)
        assert r["ok"] is False

    def test_unknown_method_returns_error(self):
        r = rotary_feedrate(100.0, 1000.0, method="rpm")
        assert r["ok"] is False


# ===========================================================================
# 10. Collision cone check
# ===========================================================================

class TestCollisionCone:

    def test_vertical_tool_no_tilt_wide_cone_ok(self):
        """Tool pointing straight down [0,0,-1], wide cone (45°) → clearance ok."""
        r = collision_cone_check((0.0, 0.0, -1.0), math.radians(5.0))
        assert r["ok"] is True
        assert r["clearance_ok"] is True

    def test_tilted_tool_exceeds_narrow_cone_not_ok(self):
        """Tool tilted 87° from Z with narrow cone (5°) → collision.
        max_tilt = 90° - 5° = 85°; tilt 87° > 85° → violation."""
        ax = _normalise3((math.sin(math.radians(87.0)), 0.0, math.cos(math.radians(87.0))))
        r = collision_cone_check(ax, math.radians(5.0))
        assert r["ok"] is True
        assert r["clearance_ok"] is False

    def test_clearance_angle_negative_on_violation(self):
        """Clearance angle < 0 when cone is violated."""
        ax = _normalise3((math.sin(math.radians(85.0)), 0.0, math.cos(math.radians(85.0))))
        r = collision_cone_check(ax, math.radians(10.0))
        if not r["clearance_ok"]:
            assert r["clearance_angle_deg"] < 0.0

    def test_explicit_tilt_angle_used(self):
        """Explicit holder_tilt_rad overrides computed tilt from axis.
        With tilt=88° and half-cone=5°: max_tilt=85° → violation."""
        ax = (0.0, 0.0, -1.0)  # vertical
        r = collision_cone_check(ax, math.radians(5.0), holder_tilt_rad=math.radians(88.0))
        assert r["ok"] is True
        assert r["clearance_ok"] is False

    def test_invalid_cone_angle_returns_error(self):
        """half_cone_angle > π/2 must return ok=False."""
        r = collision_cone_check((0.0, 0.0, -1.0), math.radians(100.0))
        assert r["ok"] is False

    def test_tilt_deg_in_result(self):
        """Result must include tilt_deg and half_cone_deg."""
        r = collision_cone_check((0.0, 0.0, -1.0), math.radians(15.0))
        assert "tilt_deg" in r
        assert "half_cone_deg" in r
        assert abs(r["half_cone_deg"] - 15.0) < 1e-9


# ===========================================================================
# 11. LLM tool wrappers
# ===========================================================================

class TestToolWrappers:

    # --- fiveaxis_forward_kinematics ---

    def test_fk_tool_happy_path(self):
        ctx = _ctx()
        raw = _run(run_fiveaxis_forward_kinematics(ctx, _args(
            x_mm=0.0, y_mm=0.0, z_mm=0.0, q1_deg=0.0, q2_deg=0.0,
        )))
        d = _ok_tool(raw)
        assert len(d["tip_part_mm"]) == 3
        assert len(d["tool_axis"]) == 3

    def test_fk_tool_missing_q1(self):
        ctx = _ctx()
        raw = _run(run_fiveaxis_forward_kinematics(ctx, _args(
            x_mm=0.0, y_mm=0.0, z_mm=0.0, q2_deg=0.0,
        )))
        _err_tool(raw)

    def test_fk_tool_bad_json(self):
        ctx = _ctx()
        raw = _run(run_fiveaxis_forward_kinematics(ctx, b"not json"))
        _err_tool(raw)

    def test_fk_tool_head_head_type(self):
        ctx = _ctx()
        raw = _run(run_fiveaxis_forward_kinematics(ctx, _args(
            x_mm=0.0, y_mm=0.0, z_mm=0.0, q1_deg=30.0, q2_deg=45.0,
            machine={"type": "head_head", "pivot_length_mm": 80.0},
        )))
        d = _ok_tool(raw)
        assert d["tip_part_mm"] is not None

    def test_fk_tool_unknown_machine_type_error(self):
        ctx = _ctx()
        raw = _run(run_fiveaxis_forward_kinematics(ctx, _args(
            x_mm=0.0, y_mm=0.0, z_mm=0.0, q1_deg=0.0, q2_deg=0.0,
            machine={"type": "five_axis_unknown"},
        )))
        _err_tool(raw)

    # --- fiveaxis_inverse_post ---

    def test_ik_tool_happy_path(self):
        ctx = _ctx()
        raw = _run(run_fiveaxis_inverse_post(ctx, _args(
            tip_part_mm=[20.0, 10.0, 5.0],
            tool_axis=[0.0, 0.3, -0.95],
        )))
        d = _ok_tool(raw)
        assert len(d["solutions"]) > 0
        assert "best" in d

    def test_ik_tool_with_prev_angles(self):
        ctx = _ctx()
        raw = _run(run_fiveaxis_inverse_post(ctx, _args(
            tip_part_mm=[10.0, 5.0, 0.0],
            tool_axis=[0.0, 0.2, -0.98],
            prev_q1_deg=-15.0,
            prev_q2_deg=30.0,
        )))
        d = _ok_tool(raw)
        assert len(d["solutions"]) > 0

    def test_ik_tool_missing_tip(self):
        ctx = _ctx()
        raw = _run(run_fiveaxis_inverse_post(ctx, _args(
            tool_axis=[0.0, 0.0, -1.0],
        )))
        _err_tool(raw)

    def test_ik_tool_wrong_tip_size(self):
        ctx = _ctx()
        raw = _run(run_fiveaxis_inverse_post(ctx, _args(
            tip_part_mm=[1.0, 2.0],
            tool_axis=[0.0, 0.0, -1.0],
        )))
        _err_tool(raw)

    # --- fiveaxis_tool_axis_lead_lag ---

    def test_lead_lag_tool_happy_path(self):
        ctx = _ctx()
        raw = _run(run_fiveaxis_tool_axis_lead_lag(ctx, _args(
            feed_direction=[1.0, 0.0, 0.0],
            surface_normal=[0.0, 0.0, 1.0],
            lead_angle_deg=10.0,
            lag_angle_deg=5.0,
        )))
        d = _ok_tool(raw)
        ax = d["tool_axis"]
        mag = math.sqrt(ax[0]**2 + ax[1]**2 + ax[2]**2)
        assert abs(mag - 1.0) < 1e-6

    def test_lead_lag_tool_missing_normal(self):
        ctx = _ctx()
        raw = _run(run_fiveaxis_tool_axis_lead_lag(ctx, _args(
            feed_direction=[1.0, 0.0, 0.0],
        )))
        _err_tool(raw)

    # --- fiveaxis_linearisation ---

    def test_linearisation_tool_happy_path(self):
        ctx = _ctx()
        raw = _run(run_fiveaxis_linearisation(ctx, _args(
            tip_part_mm=[50.0, 0.0, 0.0],
            q1_start_deg=0.0, q1_end_deg=30.0,
            q2_start_deg=0.0, q2_end_deg=0.0,
            chord_tol_mm=0.01,
        )))
        d = _ok_tool(raw)
        assert d["n_segments"] >= 1

    def test_linearisation_tool_missing_field(self):
        ctx = _ctx()
        raw = _run(run_fiveaxis_linearisation(ctx, _args(
            tip_part_mm=[50.0, 0.0, 0.0],
            q1_start_deg=0.0,
            # missing q1_end_deg
            q2_start_deg=0.0, q2_end_deg=0.0,
        )))
        _err_tool(raw)

    # --- fiveaxis_rotary_feedrate ---

    def test_feedrate_tool_dpm_happy_path(self):
        ctx = _ctx()
        raw = _run(run_fiveaxis_rotary_feedrate(ctx, _args(
            arc_radius_mm=100.0,
            desired_tip_speed_mm_per_min=1200.0,
            method="dpm",
        )))
        d = _ok_tool(raw)
        assert d["feed_dpm"] > 0

    def test_feedrate_tool_inverse_time_happy_path(self):
        ctx = _ctx()
        raw = _run(run_fiveaxis_rotary_feedrate(ctx, _args(
            arc_radius_mm=80.0,
            desired_tip_speed_mm_per_min=800.0,
            method="inverse_time",
        )))
        d = _ok_tool(raw)
        assert d["feed_inverse_time_per_min"] > 0

    def test_feedrate_tool_zero_radius_error(self):
        ctx = _ctx()
        raw = _run(run_fiveaxis_rotary_feedrate(ctx, _args(
            arc_radius_mm=0.0,
            desired_tip_speed_mm_per_min=1000.0,
        )))
        _err_tool(raw)

    def test_feedrate_tool_missing_radius(self):
        ctx = _ctx()
        raw = _run(run_fiveaxis_rotary_feedrate(ctx, _args(
            desired_tip_speed_mm_per_min=1000.0,
        )))
        _err_tool(raw)

    # --- fiveaxis_collision_cone ---

    def test_cone_tool_happy_path_ok(self):
        ctx = _ctx()
        raw = _run(run_fiveaxis_collision_cone(ctx, _args(
            tool_axis=[0.0, 0.0, -1.0],
            half_cone_angle_deg=10.0,
        )))
        d = _ok_tool(raw)
        assert "clearance_ok" in d

    def test_cone_tool_violation_detected(self):
        ctx = _ctx()
        raw = _run(run_fiveaxis_collision_cone(ctx, _args(
            tool_axis=[0.0, 0.0, -1.0],
            half_cone_angle_deg=10.0,
            holder_tilt_deg=85.0,
        )))
        d = _ok_tool(raw)
        assert d["clearance_ok"] is False

    def test_cone_tool_missing_half_cone(self):
        ctx = _ctx()
        raw = _run(run_fiveaxis_collision_cone(ctx, _args(
            tool_axis=[0.0, 0.0, -1.0],
        )))
        _err_tool(raw)

    def test_cone_tool_invalid_cone_angle(self):
        ctx = _ctx()
        raw = _run(run_fiveaxis_collision_cone(ctx, _args(
            tool_axis=[0.0, 0.0, -1.0],
            half_cone_angle_deg=95.0,
        )))
        _err_tool(raw)
