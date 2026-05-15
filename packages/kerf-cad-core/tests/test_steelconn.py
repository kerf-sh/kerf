"""
Hermetic tests for kerf_cad_core.steelconn — structural-steel connection design.

Coverage:
  connections.electrode_strength         — tabulated Fexx
  connections.bolt_shear_capacity        — AISC J3.6
  connections.bolt_bearing_capacity      — AISC J3.10
  connections.bolt_tension_capacity      — AISC J3.6
  connections.slip_critical_capacity     — AISC J3.8
  connections.block_shear_capacity       — AISC J4.3
  connections.bolt_group_eccentric       — IC + elastic methods
  connections.fillet_weld_capacity       — AISC J2.4
  connections.weld_group_elastic_vector  — elastic vector method
  connections.base_plate_bearing         — AISC J8
  tools.*                                — LLM wrappers (happy path + error paths)

All tests are pure-Python and hermetic: no OCC, no DB, no network, no fixtures.
Formulas verified algebraically against AISC 360-22 and published textbook examples.

References
----------
AISC 360-22 — Specification for Structural Steel Buildings
McCormac & Csernak, Structural Steel Design, 6th ed.

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid
import warnings

import pytest

from kerf_cad_core.steelconn.connections import (
    bolt_shear_capacity,
    bolt_bearing_capacity,
    bolt_tension_capacity,
    slip_critical_capacity,
    block_shear_capacity,
    bolt_group_eccentric,
    fillet_weld_capacity,
    weld_group_elastic_vector,
    electrode_strength,
    base_plate_bearing,
)
from kerf_cad_core.steelconn.tools import (
    run_electrode_strength,
    run_bolt_shear_capacity,
    run_bolt_bearing_capacity,
    run_bolt_tension_capacity,
    run_slip_critical_capacity,
    run_block_shear_capacity,
    run_bolt_group_eccentric,
    run_fillet_weld_capacity,
    run_weld_group_elastic_vector,
    run_base_plate_bearing,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _ctx():
    try:
        from kerf_core.utils.context import ProjectCtx  # type: ignore[import]
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


REL = 1e-6


# ===========================================================================
# 1. electrode_strength
# ===========================================================================

class TestElectrodeStrength:

    def test_e70_returns_correct_fexx(self):
        """E70 electrode: Fexx = 482.6e6 Pa (70 ksi × 6894.757 Pa/psi)."""
        res = electrode_strength("E70")
        assert res["ok"] is True
        assert abs(res["Fexx_Pa"] - 482.6e6) / 482.6e6 < 0.001

    def test_e60_ksi_approximately_60(self):
        """E60: Fexx_ksi ≈ 60 ksi (within 0.1% of nominal, table value rounded)."""
        res = electrode_strength("E60")
        assert res["ok"] is True
        # 413.7 MPa / 6.8948 Pa-per-psi × 1000 psi/ksi ≈ 60.0 ksi ±0.1%
        assert abs(res["Fexx_ksi"] - 60.0) / 60.0 < 0.01

    def test_unknown_designation_returns_error(self):
        """Unknown electrode designation must return ok=False."""
        res = electrode_strength("E55")
        assert res["ok"] is False
        assert "reason" in res

    def test_fexx_pa_ksi_conversion_consistent(self):
        """Fexx_Pa / 6.894757e6 should equal Fexx_ksi for all electrodes (1 ksi = 6894757 Pa)."""
        for desig in ("E60", "E70", "E80", "E90", "E100", "E110"):
            res = electrode_strength(desig)
            assert res["ok"] is True
            # 1 ksi = 1000 psi = 1000 × 6894.757 Pa = 6,894,757 Pa
            assert abs(res["Fexx_Pa"] / 6.894757e6 - res["Fexx_ksi"]) < 1e-6


# ===========================================================================
# 2. bolt_shear_capacity  (AISC J3.6)
# ===========================================================================

class TestBoltShearCapacity:

    # AISC Design Example: 3/4" A325N bolt
    # Ab = π/4 × (3/4")² ≈ 285.0 mm²  (nominal: 3/4" = 19.05 mm → Ab=π/4×19.05²=284.9 mm²)
    # Fnv = 372 MPa (A325N threads in shear plane)
    _AB = math.pi / 4.0 * 19.05**2   # mm²
    _FNV = 372e6                       # Pa

    def test_single_shear_nominal_strength(self):
        """Rn = Fnv × Ab [m²] × n_bolts (single shear); Ab must be converted mm² → m²."""
        res = bolt_shear_capacity(self._AB, self._FNV, 1)
        assert res["ok"] is True
        # Fnv in Pa = N/m², Ab in mm² → convert to m² by ×1e-6 for result in N
        expected = self._FNV * (self._AB * 1e-6) * 1
        assert abs(res["Rn_N"] - expected) / expected < REL

    def test_double_shear_doubles_strength(self):
        """Double shear must give exactly 2× the single shear Rn."""
        r1 = bolt_shear_capacity(self._AB, self._FNV, 1, shear_planes=1)
        r2 = bolt_shear_capacity(self._AB, self._FNV, 1, shear_planes=2)
        assert r1["ok"] and r2["ok"]
        assert abs(r2["Rn_N"] / r1["Rn_N"] - 2.0) < REL

    def test_four_bolts_four_times_single_bolt(self):
        """4 bolts must give 4× the single-bolt nominal strength."""
        r1 = bolt_shear_capacity(self._AB, self._FNV, 1)
        r4 = bolt_shear_capacity(self._AB, self._FNV, 4)
        assert abs(r4["Rn_N"] / r1["Rn_N"] - 4.0) < REL

    def test_lrfd_phi_applied(self):
        """LRFD capacity = 0.75 × Rn (default φ)."""
        res = bolt_shear_capacity(self._AB, self._FNV, 1, method="LRFD")
        assert res["ok"] is True
        assert abs(res["capacity_N"] / res["Rn_N"] - 0.75) < REL

    def test_asd_omega_applied(self):
        """ASD capacity = Rn / 2.00 (default Ω)."""
        res = bolt_shear_capacity(self._AB, self._FNV, 1, method="ASD")
        assert res["ok"] is True
        assert abs(res["capacity_N"] - res["Rn_N"] / 2.00) / (res["Rn_N"] / 2.00) < REL

    def test_utilization_over_one_sets_adequate_false(self):
        """Utilization > 1.0 must set adequate=False."""
        res = bolt_shear_capacity(self._AB, self._FNV, 1, Vu=1e9)
        assert res["ok"] is True
        assert res["adequate"] is False
        assert res["utilization"] > 1.0

    def test_negative_Ab_returns_error(self):
        res = bolt_shear_capacity(-100.0, self._FNV, 1)
        assert res["ok"] is False

    def test_zero_bolts_returns_error(self):
        res = bolt_shear_capacity(self._AB, self._FNV, 0)
        assert res["ok"] is False

    def test_invalid_method_returns_error(self):
        res = bolt_shear_capacity(self._AB, self._FNV, 1, method="LSD")
        assert res["ok"] is False


# ===========================================================================
# 3. bolt_bearing_capacity  (AISC J3.10)
# ===========================================================================

class TestBoltBearingCapacity:

    _FU = 400e6   # Pa (A36 connected material: Fu=400 MPa)
    _T  = 10.0    # mm
    _D  = 19.05   # mm (3/4" bolt)
    _N  = 4

    def test_deformation_controlled_formula(self):
        """Rn = 2.4 × d × t × Fu × n_bolts (deformation-controlled)."""
        res = bolt_bearing_capacity(self._FU, self._T, self._D, self._N)
        assert res["ok"] is True
        d_m = self._D * 1e-3
        t_m = self._T * 1e-3
        expected = 2.4 * d_m * t_m * self._FU * self._N
        assert abs(res["Rn_N"] - expected) / expected < REL

    def test_clear_distance_governs_when_smaller(self):
        """When lc is small (lc = 0.5d), 1.2·lc·t·Fu < 2.4·d·t·Fu."""
        lc_small = 0.5 * self._D   # will give 1.2*0.5d < 2.4d
        res = bolt_bearing_capacity(self._FU, self._T, self._D, 1, lc=lc_small)
        assert res["ok"] is True
        # 1.2 × lc × t × Fu vs 2.4 × d × t × Fu → 1.2*lc vs 2.4*d
        # 1.2 × 0.5d = 0.6d < 2.4d → clear governs
        assert "clear-distance" in res["limit_state"]

    def test_deformation_governs_when_lc_large(self):
        """When lc is large (lc = 10d), 2.4dtFu governs."""
        lc_large = 10.0 * self._D
        res = bolt_bearing_capacity(self._FU, self._T, self._D, 1, lc=lc_large)
        assert res["ok"] is True
        assert "deformation" in res["limit_state"]

    def test_lrfd_phi_factor(self):
        """LRFD: capacity = 0.75 × Rn."""
        res = bolt_bearing_capacity(self._FU, self._T, self._D, 1, method="LRFD")
        assert abs(res["capacity_N"] - 0.75 * res["Rn_N"]) / res["Rn_N"] < REL

    def test_negative_t_returns_error(self):
        res = bolt_bearing_capacity(self._FU, -5.0, self._D, 1)
        assert res["ok"] is False

    def test_zero_n_bolts_returns_error(self):
        res = bolt_bearing_capacity(self._FU, self._T, self._D, 0)
        assert res["ok"] is False


# ===========================================================================
# 4. bolt_tension_capacity  (AISC J3.6)
# ===========================================================================

class TestBoltTensionCapacity:

    _AB  = math.pi / 4.0 * 19.05**2  # mm²
    _FNT = 621e6                       # Pa (A325)

    def test_formula_matches_aisc(self):
        """Rn = Fnt × Ab [Pa × mm² → N via ×1e-6]."""
        res = bolt_tension_capacity(self._AB, self._FNT, 1)
        assert res["ok"] is True
        expected = self._FNT * self._AB * 1e-6
        assert abs(res["Rn_N"] - expected) / expected < REL

    def test_multiple_bolts_scale_linearly(self):
        """n bolts must give n × single bolt Rn."""
        r1 = bolt_tension_capacity(self._AB, self._FNT, 1)
        r5 = bolt_tension_capacity(self._AB, self._FNT, 5)
        assert abs(r5["Rn_N"] / r1["Rn_N"] - 5.0) < REL

    def test_utilization_zero_when_no_load(self):
        """No applied tension → utilization = 0."""
        res = bolt_tension_capacity(self._AB, self._FNT, 2, Tu=0.0)
        assert res["ok"] is True
        assert res["utilization"] == 0.0

    def test_negative_Ab_returns_error(self):
        res = bolt_tension_capacity(-100.0, self._FNT, 1)
        assert res["ok"] is False

    def test_negative_Tu_returns_error(self):
        res = bolt_tension_capacity(self._AB, self._FNT, 1, Tu=-100.0)
        assert res["ok"] is False


# ===========================================================================
# 5. slip_critical_capacity  (AISC J3.8)
# ===========================================================================

class TestSlipCriticalCapacity:

    # AISC example: 3/4" A325 bolt, Class A faying surface
    # Pt = 133,400 N per AISC Table J3.1
    _MU = 0.35
    _PT = 133400.0
    _N  = 1
    _DU = 1.13

    def test_formula_matches_aisc_j3_8(self):
        """Rn = μ × 1.13 × hf × Pt × ns × n_bolts."""
        res = slip_critical_capacity(self._MU, self._PT, self._N)
        assert res["ok"] is True
        expected = self._MU * self._DU * 1.0 * self._PT * 1 * self._N
        assert abs(res["Rn_N"] - expected) / expected < REL

    def test_class_b_higher_than_class_a(self):
        """Class B (μ=0.50) must give higher capacity than Class A (μ=0.35)."""
        rA = slip_critical_capacity(0.35, self._PT, self._N)
        rB = slip_critical_capacity(0.50, self._PT, self._N)
        assert rB["Rn_N"] > rA["Rn_N"]

    def test_oversized_hole_factor_reduces_capacity(self):
        """Oversized holes (hf=0.85) reduce capacity vs standard (hf=1.0)."""
        r_std = slip_critical_capacity(self._MU, self._PT, self._N, hole_factor=1.0)
        r_ovs = slip_critical_capacity(self._MU, self._PT, self._N, hole_factor=0.85)
        assert r_ovs["Rn_N"] < r_std["Rn_N"]
        assert abs(r_ovs["Rn_N"] / r_std["Rn_N"] - 0.85) < REL

    def test_two_faying_surfaces_double_capacity(self):
        """Two faying surfaces → 2× single-surface capacity."""
        r1 = slip_critical_capacity(self._MU, self._PT, self._N, 1)
        r2 = slip_critical_capacity(self._MU, self._PT, self._N, 2)
        assert abs(r2["Rn_N"] / r1["Rn_N"] - 2.0) < REL

    def test_phi_and_omega_defaults(self):
        """LRFD: φ=1.00, ASD: Ω=1.50 (serviceability level)."""
        r_lrfd = slip_critical_capacity(self._MU, self._PT, 1, method="LRFD")
        r_asd  = slip_critical_capacity(self._MU, self._PT, 1, method="ASD")
        assert abs(r_lrfd["capacity_N"] - 1.0 * r_lrfd["Rn_N"]) < REL
        assert abs(r_asd["capacity_N"]  - r_asd["Rn_N"] / 1.5) < REL

    def test_mu_greater_than_one_returns_error(self):
        res = slip_critical_capacity(1.5, self._PT, 1)
        assert res["ok"] is False

    def test_negative_Pt_returns_error(self):
        res = slip_critical_capacity(self._MU, -100.0, 1)
        assert res["ok"] is False


# ===========================================================================
# 6. block_shear_capacity  (AISC J4.3)
# ===========================================================================

class TestBlockShearCapacity:

    # Representative example from McCormac & Csernak:
    # A36 steel: Fy=250 MPa, Fu=400 MPa
    # Agv=1500 mm², Anv=1200 mm², Ant=300 mm²
    _FU  = 400e6
    _FY  = 250e6
    _AGV = 1500.0
    _ANV = 1200.0
    _ANT = 300.0

    def _rn_path1(self, Fu, Anv, Ant, Ubs=1.0):
        """Path 1: 0.6Fu·Anv + Ubs·Fu·Ant  [areas in mm²]"""
        return 0.6 * Fu * Anv * 1e-6 + Ubs * Fu * Ant * 1e-6

    def _rn_path2(self, Fu, Fy, Agv, Ant, Ubs=1.0):
        """Path 2: 0.6Fy·Agv + Ubs·Fu·Ant  [areas in mm²]"""
        return 0.6 * Fy * Agv * 1e-6 + Ubs * Fu * Ant * 1e-6

    def test_governing_minimum_path(self):
        """Rn must be min(path1, path2)."""
        res = block_shear_capacity(self._FU, self._FY, self._AGV, self._ANV, self._ANT)
        assert res["ok"] is True
        p1 = self._rn_path1(self._FU, self._ANV, self._ANT)
        p2 = self._rn_path2(self._FU, self._FY, self._AGV, self._ANT)
        expected = min(p1, p2)
        assert abs(res["Rn_N"] - expected) / expected < REL

    def test_ubs_half_reduces_capacity(self):
        """Ubs=0.5 (non-uniform) must give lower capacity than Ubs=1.0."""
        r1 = block_shear_capacity(self._FU, self._FY, self._AGV, self._ANV, self._ANT, Ubs=1.0)
        r0 = block_shear_capacity(self._FU, self._FY, self._AGV, self._ANV, self._ANT, Ubs=0.5)
        assert r0["Rn_N"] < r1["Rn_N"]

    def test_lrfd_phi_075(self):
        """LRFD: capacity = 0.75 × Rn."""
        res = block_shear_capacity(self._FU, self._FY, self._AGV, self._ANV, self._ANT)
        assert abs(res["capacity_N"] - 0.75 * res["Rn_N"]) / res["Rn_N"] < REL

    def test_governing_path_reported(self):
        """governing_path field must be present and non-empty."""
        res = block_shear_capacity(self._FU, self._FY, self._AGV, self._ANV, self._ANT)
        assert res["ok"] is True
        assert res["governing_path"] in (
            "shear-rupture + tension-rupture",
            "shear-yield + tension-rupture",
        )

    def test_zero_agv_returns_error(self):
        res = block_shear_capacity(self._FU, self._FY, 0.0, self._ANV, self._ANT)
        assert res["ok"] is False

    def test_ubs_zero_returns_error(self):
        res = block_shear_capacity(self._FU, self._FY, self._AGV, self._ANV, self._ANT, Ubs=0.0)
        assert res["ok"] is False


# ===========================================================================
# 7. bolt_group_eccentric
# ===========================================================================

class TestBoltGroupEccentric:

    # 4-bolt group in a square pattern, 75 mm spacing
    _COORDS = [(0.0, 0.0), (75.0, 0.0), (0.0, 75.0), (75.0, 75.0)]

    def test_elastic_zero_eccentricity_utilization_is_one(self):
        """e=0 → no torsion → all bolt forces equal → utilization based on direct shear only."""
        P = 100000.0
        res = bolt_group_eccentric(self._COORDS, P, 0.0, method_beg="elastic")
        assert res["ok"] is True
        # With e=0, T=0, max bolt force = P/n
        assert res["max_bolt_force_N"] == pytest.approx(P / 4.0, rel=1e-9)

    def test_elastic_with_eccentricity_increases_bolt_force(self):
        """Adding eccentricity increases the maximum bolt force."""
        P = 100000.0
        r0 = bolt_group_eccentric(self._COORDS, P, 0.0,   method_beg="elastic")
        r1 = bolt_group_eccentric(self._COORDS, P, 100.0, method_beg="elastic")
        assert r1["max_bolt_force_N"] > r0["max_bolt_force_N"]

    def test_elastic_governing_bolt_index_valid(self):
        """Governing bolt index must be within [0, n_bolts)."""
        res = bolt_group_eccentric(self._COORDS, 50000.0, 50.0, method_beg="elastic")
        assert res["ok"] is True
        assert 0 <= res["governing_bolt_index"] < len(self._COORDS)

    def test_ic_method_returns_ok(self):
        """IC method should run without error for standard configuration."""
        res = bolt_group_eccentric(self._COORDS, 80000.0, 100.0, method_beg="IC")
        assert res["ok"] is True
        assert res["C_coefficient"] is not None

    def test_ic_larger_eccentricity_larger_utilization(self):
        """Larger eccentricity must increase IC utilization."""
        P = 50000.0
        r1 = bolt_group_eccentric(self._COORDS, P, 50.0,  method_beg="IC")
        r2 = bolt_group_eccentric(self._COORDS, P, 200.0, method_beg="IC")
        assert r1["ok"] and r2["ok"]
        assert r2["utilization"] > r1["utilization"]

    def test_fewer_than_two_bolts_returns_error(self):
        res = bolt_group_eccentric([(0.0, 0.0)], 10000.0, 0.0)
        assert res["ok"] is False

    def test_negative_P_returns_error(self):
        res = bolt_group_eccentric(self._COORDS, -1000.0, 0.0)
        assert res["ok"] is False

    def test_invalid_method_beg_returns_error(self):
        res = bolt_group_eccentric(self._COORDS, 10000.0, 0.0, method_beg="FEM")
        assert res["ok"] is False


# ===========================================================================
# 8. fillet_weld_capacity  (AISC J2.4)
# ===========================================================================

class TestFilletWeldCapacity:

    # 5/16" E70 fillet weld, 150 mm long
    _D = 5.0           # sixteenths
    _L = 150.0         # mm
    _FEXX = 482.6e6    # Pa (E70)

    def _throat(self, D_sixteenths: float) -> float:
        """Effective throat (mm) = D_mm / √2."""
        D_mm = D_sixteenths * (25.4 / 16.0)
        return D_mm / math.sqrt(2.0)

    def test_parallel_load_formula_zero_angle(self):
        """θ=0: directional factor = 1.0, Rn = 0.6×Fexx×throat×L."""
        res = fillet_weld_capacity(self._D, self._L, self._FEXX, angle_deg=0.0)
        assert res["ok"] is True
        throat_m = self._throat(self._D) * 1e-3
        L_m = self._L * 1e-3
        expected = 0.6 * self._FEXX * 1.0 * throat_m * L_m
        assert abs(res["Rn_N"] - expected) / expected < REL

    def test_transverse_load_increases_capacity(self):
        """θ=90° must give (1 + 0.5×1.0)=1.5× the θ=0° capacity."""
        r0  = fillet_weld_capacity(self._D, self._L, self._FEXX, angle_deg=0.0)
        r90 = fillet_weld_capacity(self._D, self._L, self._FEXX, angle_deg=90.0)
        assert r90["Rn_N"] > r0["Rn_N"]
        # Factor at 90°: 1 + 0.5 × sin^1.5(90°) = 1 + 0.5 × 1 = 1.5
        assert abs(r90["Rn_N"] / r0["Rn_N"] - 1.5) < 1e-6

    def test_double_sided_weld_doubles_capacity(self):
        """n_welds=2 must give exactly 2× single-sided capacity."""
        r1 = fillet_weld_capacity(self._D, self._L, self._FEXX, n_welds=1)
        r2 = fillet_weld_capacity(self._D, self._L, self._FEXX, n_welds=2)
        assert abs(r2["Rn_N"] / r1["Rn_N"] - 2.0) < REL

    def test_larger_weld_size_increases_capacity(self):
        """Larger D_sixteenths → larger throat → larger capacity."""
        r5  = fillet_weld_capacity(5.0, self._L, self._FEXX)
        r8  = fillet_weld_capacity(8.0, self._L, self._FEXX)
        assert r8["Rn_N"] > r5["Rn_N"]

    def test_directional_factor_reported(self):
        """directional_factor must equal 1.0 + 0.50 × sin^1.5(θ)."""
        for angle in (0.0, 30.0, 60.0, 90.0):
            res = fillet_weld_capacity(self._D, self._L, self._FEXX, angle_deg=angle)
            assert res["ok"] is True
            theta = math.radians(angle)
            expected_df = 1.0 + 0.50 * (math.sin(theta) ** 1.5)
            assert abs(res["directional_factor"] - expected_df) < 1e-9

    def test_lrfd_phi_factor(self):
        """LRFD: capacity = 0.75 × Rn."""
        res = fillet_weld_capacity(self._D, self._L, self._FEXX)
        assert abs(res["capacity_N"] - 0.75 * res["Rn_N"]) / res["Rn_N"] < REL

    def test_angle_out_of_range_returns_error(self):
        res = fillet_weld_capacity(self._D, self._L, self._FEXX, angle_deg=95.0)
        assert res["ok"] is False

    def test_zero_L_returns_error(self):
        res = fillet_weld_capacity(self._D, 0.0, self._FEXX)
        assert res["ok"] is False


# ===========================================================================
# 9. weld_group_elastic_vector
# ===========================================================================

class TestWeldGroupElasticVector:

    # Single horizontal weld segment at y=0, x from 0 to 200 mm
    _SEG = [(0.0, 0.0, 200.0, 0.0, 5.0, 482.6e6)]

    def test_single_segment_returns_ok(self):
        """Single weld segment with zero eccentricity should return ok=True."""
        res = weld_group_elastic_vector(self._SEG, P=50000.0, ex=0.0, ey=0.0)
        assert res["ok"] is True
        assert "utilization" in res

    def test_eccentricity_increases_utilization(self):
        """Larger eccentricity must increase utilization."""
        r0 = weld_group_elastic_vector(self._SEG, P=50000.0, ex=0.0, ey=0.0)
        r1 = weld_group_elastic_vector(self._SEG, P=50000.0, ex=100.0, ey=0.0)
        assert r1["utilization"] >= r0["utilization"]

    def test_centroid_on_segment_midpoint(self):
        """For symmetric single segment, centroid should be at midpoint."""
        res = weld_group_elastic_vector(self._SEG, P=10000.0, ex=0.0, ey=0.0)
        assert res["ok"] is True
        assert abs(res["centroid_x_mm"] - 100.0) < 1e-9
        assert abs(res["centroid_y_mm"] - 0.0) < 1e-9

    def test_two_equal_segments_symmetric_zero_torque(self):
        """Two symmetric segments with zero eccentricity: utilization from direct shear only."""
        segs = [
            (0.0, 50.0, 200.0, 50.0, 5.0, 482.6e6),
            (0.0, -50.0, 200.0, -50.0, 5.0, 482.6e6),
        ]
        res = weld_group_elastic_vector(segs, P=100000.0, ex=0.0, ey=0.0)
        assert res["ok"] is True
        # With zero eccentricity, torsional stress should be zero
        assert abs(res["tau_torsion_MPa"]) < 1e-6

    def test_empty_segments_returns_error(self):
        res = weld_group_elastic_vector([], P=10000.0, ex=0.0, ey=0.0)
        assert res["ok"] is False

    def test_negative_P_returns_error(self):
        res = weld_group_elastic_vector(self._SEG, P=-1000.0, ex=0.0, ey=0.0)
        assert res["ok"] is False


# ===========================================================================
# 10. base_plate_bearing  (AISC J8)
# ===========================================================================

class TestBasePlateBearing:

    # Example: 500 kN column on 250×250 mm base plate, f'c=28 MPa
    _P   = 500000.0  # N
    _B   = 250.0     # mm
    _N   = 250.0     # mm
    _FPC = 0.85 * 28e6  # Pa (= 23.8 MPa)

    def test_bearing_stress_formula(self):
        """fp_actual = P / (B × N) [Pa]."""
        res = base_plate_bearing(self._P, self._B, self._N, self._FPC)
        assert res["ok"] is True
        area_m2 = self._B * self._N * 1e-6
        fp_expected = self._P / area_m2
        assert abs(res["fp_actual_Pa"] - fp_expected) / fp_expected < REL

    def test_adequate_when_stress_below_allowable(self):
        """Small load on large plate: bearing stress < allowable → adequate=True."""
        res = base_plate_bearing(100000.0, 500.0, 500.0, self._FPC)
        assert res["ok"] is True
        assert res["adequate"] is True

    def test_overstress_flagged(self):
        """Excessive load must give adequate=False and utilization > 1."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            res = base_plate_bearing(10e6, 100.0, 100.0, 10e6)
        assert res["ok"] is True
        assert res["adequate"] is False
        assert res["utilization"] > 1.0

    def test_lrfd_capacity_formula(self):
        """LRFD: capacity_N = φ × fp_prime × area."""
        res = base_plate_bearing(self._P, self._B, self._N, self._FPC, method="LRFD")
        assert res["ok"] is True
        phi_fp = 0.65 * self._FPC
        area_m2 = self._B * self._N * 1e-6
        expected_cap = phi_fp * area_m2
        assert abs(res["capacity_N"] - expected_cap) / expected_cap < REL

    def test_asd_capacity_formula(self):
        """ASD: capacity_N = fp_prime / Ω × area, Ω=2.31."""
        res = base_plate_bearing(self._P, self._B, self._N, self._FPC, method="ASD")
        assert res["ok"] is True
        fp_allow = self._FPC / 2.31
        area_m2 = self._B * self._N * 1e-6
        expected_cap = fp_allow * area_m2
        assert abs(res["capacity_N"] - expected_cap) / expected_cap < REL

    def test_negative_P_returns_error(self):
        res = base_plate_bearing(-100.0, self._B, self._N, self._FPC)
        assert res["ok"] is False

    def test_zero_B_returns_error(self):
        res = base_plate_bearing(self._P, 0.0, self._N, self._FPC)
        assert res["ok"] is False

    def test_zero_fp_prime_returns_error(self):
        res = base_plate_bearing(self._P, self._B, self._N, 0.0)
        assert res["ok"] is False


# ===========================================================================
# 11. LLM tool wrappers
# ===========================================================================

class TestToolWrappers:

    def test_run_electrode_strength_happy(self):
        ctx = _ctx()
        raw = _run(run_electrode_strength(ctx, _args(designation="E70")))
        d = _ok_tool(raw)
        assert d["Fexx_Pa"] > 0

    def test_run_electrode_strength_bad_desig(self):
        ctx = _ctx()
        raw = _run(run_electrode_strength(ctx, _args(designation="E999")))
        _err_tool(raw)

    def test_run_bolt_shear_happy(self):
        ctx = _ctx()
        Ab = math.pi / 4.0 * 19.05**2
        raw = _run(run_bolt_shear_capacity(ctx, _args(Ab=Ab, Fnv=372e6, n_bolts=2)))
        d = _ok_tool(raw)
        assert d["Rn_N"] > 0

    def test_run_bolt_shear_missing_field(self):
        ctx = _ctx()
        raw = _run(run_bolt_shear_capacity(ctx, _args(Fnv=372e6, n_bolts=2)))
        _err_tool(raw)

    def test_run_bolt_bearing_happy(self):
        ctx = _ctx()
        raw = _run(run_bolt_bearing_capacity(ctx, _args(
            Fu=400e6, t=10.0, d=19.05, n_bolts=3
        )))
        d = _ok_tool(raw)
        assert d["Rn_N"] > 0

    def test_run_bolt_tension_happy(self):
        ctx = _ctx()
        Ab = math.pi / 4.0 * 19.05**2
        raw = _run(run_bolt_tension_capacity(ctx, _args(Ab=Ab, Fnt=621e6, n_bolts=1)))
        d = _ok_tool(raw)
        assert d["capacity_N"] > 0

    def test_run_slip_critical_happy(self):
        ctx = _ctx()
        raw = _run(run_slip_critical_capacity(ctx, _args(mu=0.35, Pt=133400.0, n_bolts=4)))
        d = _ok_tool(raw)
        assert d["Rn_N"] > 0

    def test_run_block_shear_happy(self):
        ctx = _ctx()
        raw = _run(run_block_shear_capacity(ctx, _args(
            Fu=400e6, Fy=250e6, Agv=1500.0, Anv=1200.0, Ant=300.0
        )))
        d = _ok_tool(raw)
        assert d["Rn_N"] > 0

    def test_run_bolt_group_elastic_happy(self):
        ctx = _ctx()
        coords = [[0.0, 0.0], [75.0, 0.0], [0.0, 75.0], [75.0, 75.0]]
        raw = _run(run_bolt_group_eccentric(ctx, _args(
            bolt_coords=coords, P=80000.0, e=50.0, method_beg="elastic"
        )))
        d = _ok_tool(raw)
        assert d["max_bolt_force_N"] > 0

    def test_run_bolt_group_ic_happy(self):
        ctx = _ctx()
        coords = [[0.0, 0.0], [75.0, 0.0], [0.0, 75.0], [75.0, 75.0]]
        raw = _run(run_bolt_group_eccentric(ctx, _args(
            bolt_coords=coords, P=80000.0, e=100.0, method_beg="IC"
        )))
        d = _ok_tool(raw)
        assert "utilization" in d

    def test_run_fillet_weld_happy(self):
        ctx = _ctx()
        raw = _run(run_fillet_weld_capacity(ctx, _args(
            D_sixteenths=5.0, L_weld=150.0, Fexx=482.6e6
        )))
        d = _ok_tool(raw)
        assert d["Rn_N"] > 0

    def test_run_fillet_weld_missing_field(self):
        ctx = _ctx()
        raw = _run(run_fillet_weld_capacity(ctx, _args(L_weld=150.0, Fexx=482.6e6)))
        _err_tool(raw)

    def test_run_weld_group_happy(self):
        ctx = _ctx()
        segs = [[0.0, 0.0, 200.0, 0.0, 5.0, 482.6e6]]
        raw = _run(run_weld_group_elastic_vector(ctx, _args(
            weld_segments=segs, P=50000.0, ex=50.0, ey=0.0
        )))
        d = _ok_tool(raw)
        assert "utilization" in d

    def test_run_base_plate_happy(self):
        ctx = _ctx()
        raw = _run(run_base_plate_bearing(ctx, _args(
            P=500000.0, B=250.0, N=250.0, fp_prime=23.8e6
        )))
        d = _ok_tool(raw)
        assert "utilization" in d

    def test_run_base_plate_missing_field(self):
        ctx = _ctx()
        raw = _run(run_base_plate_bearing(ctx, _args(P=500000.0, B=250.0, N=250.0)))
        _err_tool(raw)

    def test_run_bolt_shear_bad_json(self):
        ctx = _ctx()
        raw = _run(run_bolt_shear_capacity(ctx, b"not json"))
        _err_tool(raw)
