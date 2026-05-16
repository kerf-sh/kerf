"""
Hermetic tests for kerf_cad_core.fasteners — bolted-joint analysis.

Coverage:
  joint.preload_from_torque   — nut-factor model T = K·F·d
  joint.bolt_stiffness        — series shank + thread springs
  joint.clamped_stiffness     — VDI 2230 frustum model
  joint.joint_load_factor     — Φ = k_bolt / (k_bolt + k_clamp)
  joint.bolt_working_stress   — combined tensile + torsional stress
  joint.separation_safety     — n_sep = F_i / (F_e · (1 − Φ))
  joint.slip_safety           — n_slip = μ·F_i·n / F_shear
  joint.fatigue_check         — modified Goodman for bolt
  joint.strip_length          — thread engagement / pullout length
  joint.ISO_THREAD            — thread geometry table
  tools.*                     — LLM tool wrappers (happy path + error paths)

All tests are pure-Python and hermetic: no OCC, no DB, no network, no fixtures.
Formulas verified algebraically against Shigley 10th ed. Chapter 8 hand-calcs.

References
----------
Shigley's Mechanical Engineering Design, 10th ed., Chapter 8
VDI 2230-1:2015

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid
import warnings

import pytest

from kerf_cad_core.fasteners.joint import (
    preload_from_torque,
    bolt_stiffness,
    clamped_stiffness,
    joint_load_factor,
    bolt_working_stress,
    separation_safety,
    slip_safety,
    fatigue_check,
    strip_length,
    ISO_THREAD,
)
from kerf_cad_core.fasteners.tools import (
    run_bolt_preload_from_torque,
    run_bolt_stiffness,
    run_clamped_member_stiffness,
    run_bolt_joint_load_factor,
    run_bolt_working_stress,
    run_bolt_separation_safety,
    run_bolt_slip_safety,
    run_bolt_fatigue_check,
    run_bolt_strip_length,
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
# 1. preload_from_torque
# ===========================================================================

class TestPreloadFromTorque:

    def test_formula_algebraic(self):
        """F = T / (K * d)  for standard inputs."""
        T, d, K = 100.0, 0.016, 0.20
        res = preload_from_torque(T=T, d=d, K=K)
        assert res["ok"] is True
        expected = T / (K * d)
        assert abs(res["F_preload_N"] - expected) / expected < REL

    def test_default_K_is_0_20(self):
        """Default K=0.20 matches explicit K=0.20."""
        T, d = 50.0, 0.012
        r1 = preload_from_torque(T=T, d=d)
        r2 = preload_from_torque(T=T, d=d, K=0.20)
        assert abs(r1["F_preload_N"] - r2["F_preload_N"]) < 1e-10

    def test_higher_torque_gives_higher_preload(self):
        """Doubling T must double F_preload."""
        d, K = 0.020, 0.20
        F1 = preload_from_torque(T=50.0, d=d, K=K)["F_preload_N"]
        F2 = preload_from_torque(T=100.0, d=d, K=K)["F_preload_N"]
        assert abs(F2 / F1 - 2.0) < REL

    def test_higher_K_gives_lower_preload(self):
        """Higher nut factor (more friction) means less clamp for same torque."""
        T, d = 100.0, 0.016
        F_low_K = preload_from_torque(T=T, d=d, K=0.10)["F_preload_N"]
        F_high_K = preload_from_torque(T=T, d=d, K=0.25)["F_preload_N"]
        assert F_low_K > F_high_K

    def test_m16_shigley_example(self):
        """Shigley Ex 8-5 (approx): M16 bolt, T=90 N·m, K=0.20.
        Expected F ≈ 90 / (0.20 × 0.016) = 28 125 N."""
        res = preload_from_torque(T=90.0, d=0.016, K=0.20)
        assert res["ok"] is True
        assert abs(res["F_preload_N"] - 28125.0) / 28125.0 < REL

    def test_negative_T_returns_error(self):
        res = preload_from_torque(T=-10.0, d=0.016)
        assert res["ok"] is False

    def test_zero_d_returns_error(self):
        res = preload_from_torque(T=50.0, d=0.0)
        assert res["ok"] is False

    def test_negative_K_returns_error(self):
        res = preload_from_torque(T=50.0, d=0.016, K=-0.1)
        assert res["ok"] is False

    def test_out_of_range_K_gets_warning(self):
        """K=0.05 is below typical range — should warn."""
        res = preload_from_torque(T=50.0, d=0.016, K=0.05)
        assert res["ok"] is True
        assert len(res["warnings"]) > 0


# ===========================================================================
# 2. bolt_stiffness
# ===========================================================================

class TestBoltStiffness:

    def test_fully_threaded_equals_thread_stiffness(self):
        """length_shank=0: k_bolt == k_thread (shank term absent)."""
        d_s, d_t, L_t, E = 0.016, 0.013_835, 0.020, 200e9
        res = bolt_stiffness(d_s, 0.0, d_t, L_t, E)
        assert res["ok"] is True
        A_t = math.pi / 4.0 * d_t ** 2
        k_thread_expected = E * A_t / L_t
        assert abs(res["k_bolt_N_per_m"] - k_thread_expected) / k_thread_expected < REL

    def test_series_spring_formula(self):
        """1/k_bolt = 1/k_shank + 1/k_thread for L_shank > 0."""
        d_s, L_s, d_t, L_t, E = 0.016, 0.025, 0.013_835, 0.015, 200e9
        res = bolt_stiffness(d_s, L_s, d_t, L_t, E)
        assert res["ok"] is True
        A_s = math.pi / 4.0 * d_s ** 2
        A_t = math.pi / 4.0 * d_t ** 2
        k_s = E * A_s / L_s
        k_t = E * A_t / L_t
        k_expected = 1.0 / (1.0 / k_s + 1.0 / k_t)
        assert abs(res["k_bolt_N_per_m"] - k_expected) / k_expected < REL

    def test_longer_bolt_is_softer(self):
        """Longer threaded section must reduce stiffness."""
        d_s, d_t, E = 0.016, 0.013_835, 200e9
        k1 = bolt_stiffness(d_s, 0.010, d_t, 0.015, E)["k_bolt_N_per_m"]
        k2 = bolt_stiffness(d_s, 0.010, d_t, 0.030, E)["k_bolt_N_per_m"]
        assert k1 > k2

    def test_negative_d_shank_returns_error(self):
        res = bolt_stiffness(-0.016, 0.02, 0.013, 0.015)
        assert res["ok"] is False

    def test_negative_d_thread_minor_returns_error(self):
        res = bolt_stiffness(0.016, 0.02, -0.013, 0.015)
        assert res["ok"] is False

    def test_zero_length_thread_returns_error(self):
        res = bolt_stiffness(0.016, 0.02, 0.013, 0.0)
        assert res["ok"] is False


# ===========================================================================
# 3. clamped_stiffness
# ===========================================================================

class TestClampedStiffness:

    def test_returns_positive_stiffness(self):
        """Basic call: grip=30 mm, steel, M16."""
        res = clamped_stiffness(
            grip_length=0.030, E_clamp=200e9, d_bolt=0.016,
        )
        assert res["ok"] is True
        assert res["k_clamp_N_per_m"] > 0

    def test_stiffer_material_gives_higher_k(self):
        """Steel (200 GPa) clamp must be stiffer than aluminium (70 GPa)."""
        k_steel = clamped_stiffness(0.030, 200e9, 0.016)["k_clamp_N_per_m"]
        k_al = clamped_stiffness(0.030, 70e9, 0.016)["k_clamp_N_per_m"]
        assert k_steel > k_al

    def test_longer_grip_gives_lower_k(self):
        """Longer grip reduces stiffness."""
        k1 = clamped_stiffness(0.020, 200e9, 0.016)["k_clamp_N_per_m"]
        k2 = clamped_stiffness(0.040, 200e9, 0.016)["k_clamp_N_per_m"]
        assert k1 > k2

    def test_k_proportional_to_E(self):
        """k_clamp scales linearly with E_clamp (frustum model)."""
        k1 = clamped_stiffness(0.030, 200e9, 0.016)["k_clamp_N_per_m"]
        k2 = clamped_stiffness(0.030, 400e9, 0.016)["k_clamp_N_per_m"]
        # Should be very close to 2× due to linear E scaling
        assert abs(k2 / k1 - 2.0) < 0.01

    def test_invalid_half_angle_returns_error(self):
        res = clamped_stiffness(0.030, 200e9, 0.016, half_angle_deg=90.0)
        assert res["ok"] is False

    def test_zero_grip_returns_error(self):
        res = clamped_stiffness(0.0, 200e9, 0.016)
        assert res["ok"] is False


# ===========================================================================
# 4. joint_load_factor
# ===========================================================================

class TestJointLoadFactor:

    def test_phi_formula(self):
        """Φ = k_bolt / (k_bolt + k_clamp) algebraically."""
        k_b, k_c = 100e6, 1000e6
        res = joint_load_factor(k_b, k_c)
        assert res["ok"] is True
        expected = k_b / (k_b + k_c)
        assert abs(res["Phi"] - expected) / expected < REL

    def test_phi_between_zero_and_one(self):
        """Φ must always be in (0, 1)."""
        for k_b, k_c in [(1e6, 1e9), (5e8, 5e8), (1e9, 1e6)]:
            res = joint_load_factor(k_b, k_c)
            assert 0 < res["Phi"] < 1

    def test_equal_stiffness_gives_phi_half(self):
        """k_bolt = k_clamp → Φ = 0.5."""
        k = 500e6
        res = joint_load_factor(k, k)
        assert abs(res["Phi"] - 0.5) < REL

    def test_very_stiff_clamp_gives_small_phi(self):
        """Very stiff clamp (k_clamp >> k_bolt) → Φ → 0."""
        res = joint_load_factor(1e6, 1e12)
        assert res["Phi"] < 0.01

    def test_zero_k_bolt_returns_error(self):
        res = joint_load_factor(0.0, 1e9)
        assert res["ok"] is False

    def test_zero_k_clamp_returns_error(self):
        res = joint_load_factor(1e9, 0.0)
        assert res["ok"] is False


# ===========================================================================
# 5. bolt_working_stress
# ===========================================================================

class TestBoltWorkingStress:

    def test_preload_only_no_external_load(self):
        """F_external=0: σ_total = F_preload / A_stress."""
        F_p = 20000.0
        A = 157e-6  # M16 stress area
        Phi = 0.10
        res = bolt_working_stress(F_p, 0.0, Phi, A)
        assert res["ok"] is True
        expected = F_p / A
        assert abs(res["sigma_total_Pa"] - expected) / expected < REL

    def test_total_force_formula(self):
        """F_bolt = F_preload + Phi × F_external."""
        F_p, F_e, Phi, A = 20000.0, 5000.0, 0.15, 157e-6
        res = bolt_working_stress(F_p, F_e, Phi, A)
        assert res["ok"] is True
        F_expected = F_p + Phi * F_e
        assert abs(res["F_bolt_total_N"] - F_expected) / F_expected < REL

    def test_von_mises_with_torsion(self):
        """Von Mises = √(σ² + 3τ²) when torque is supplied."""
        F_p, F_e, Phi, A = 15000.0, 2000.0, 0.12, 157e-6
        T_r, d_m = 20.0, 0.014701  # M16 pitch diameter
        res = bolt_working_stress(F_p, F_e, Phi, A, torque_Nm=T_r, d_m=d_m)
        assert res["ok"] is True
        tau = 16.0 * T_r / (math.pi * d_m ** 3)
        sigma = res["sigma_total_Pa"]
        vm_expected = math.sqrt(sigma ** 2 + 3.0 * tau ** 2)
        assert abs(res["sigma_von_mises_Pa"] - vm_expected) / vm_expected < REL

    def test_invalid_phi_returns_error(self):
        res = bolt_working_stress(10000.0, 0.0, 1.5, 157e-6)
        assert res["ok"] is False

    def test_negative_A_stress_returns_error(self):
        res = bolt_working_stress(10000.0, 0.0, 0.1, -100e-6)
        assert res["ok"] is False


# ===========================================================================
# 6. separation_safety
# ===========================================================================

class TestSeparationSafety:

    def test_formula_algebraic(self):
        """n_sep = F_preload / (F_external × (1 − Φ))."""
        F_p, F_e, Phi = 20000.0, 5000.0, 0.10
        res = separation_safety(F_p, F_e, Phi)
        assert res["ok"] is True
        expected = F_p / (F_e * (1.0 - Phi))
        assert abs(res["n_sep"] - expected) / expected < REL

    def test_no_separation_for_adequate_preload(self):
        """High preload relative to external load → no separation."""
        res = separation_safety(F_preload=50000.0, F_external=5000.0, Phi=0.10)
        assert res["ok"] is True
        assert res["separated"] is False
        assert res["n_sep"] > 1.0

    def test_separation_flagged_when_preload_too_low(self):
        """Low preload → n_sep < 1 → separated=True and warning issued."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            res = separation_safety(F_preload=100.0, F_external=50000.0, Phi=0.05)
        assert res["ok"] is True
        assert res["separated"] is True
        assert res["n_sep"] < 1.0
        assert len(res["warnings"]) > 0
        assert len(w) > 0  # Python warning also issued

    def test_phi_zero_gives_n_sep_equal_ratio(self):
        """Phi=0: n_sep = F_preload / F_external."""
        F_p, F_e = 30000.0, 10000.0
        res = separation_safety(F_p, F_e, Phi=0.0)
        assert res["ok"] is True
        assert abs(res["n_sep"] - 3.0) < REL

    def test_negative_F_preload_returns_error(self):
        res = separation_safety(-1000.0, 5000.0, 0.1)
        assert res["ok"] is False

    def test_phi_equal_one_returns_error(self):
        """Phi=1 → clamp relief = 0 → degenerate."""
        res = separation_safety(20000.0, 5000.0, Phi=1.0)
        assert res["ok"] is False


# ===========================================================================
# 7. slip_safety
# ===========================================================================

class TestSlipSafety:

    def test_formula_algebraic(self):
        """n_slip = mu × F_preload × n_bolts / F_shear."""
        F_p, F_s, mu, n = 20000.0, 10000.0, 0.35, 2
        res = slip_safety(F_p, F_s, mu, n)
        assert res["ok"] is True
        expected = mu * F_p * n / F_s
        assert abs(res["n_slip"] - expected) / expected < REL

    def test_more_bolts_prevents_slip(self):
        """More bolts linearly increase slip safety factor."""
        F_p, F_s, mu = 10000.0, 5000.0, 0.35
        n1 = slip_safety(F_p, F_s, mu, 1)["n_slip"]
        n3 = slip_safety(F_p, F_s, mu, 3)["n_slip"]
        assert abs(n3 / n1 - 3.0) < REL

    def test_slip_flagged_when_insufficient_friction(self):
        """Very low preload → slip."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            res = slip_safety(F_preload=100.0, F_shear=50000.0, mu=0.35, n_bolts=1)
        assert res["ok"] is True
        assert res["slips"] is True
        assert len(res["warnings"]) > 0
        assert len(w) > 0

    def test_no_slip_for_adequate_preload(self):
        res = slip_safety(F_preload=30000.0, F_shear=3000.0, mu=0.35, n_bolts=1)
        assert res["ok"] is True
        assert res["slips"] is False
        assert res["n_slip"] > 1.25

    def test_zero_mu_returns_error(self):
        res = slip_safety(20000.0, 5000.0, mu=0.0)
        assert res["ok"] is False

    def test_zero_n_bolts_returns_error(self):
        res = slip_safety(20000.0, 5000.0, mu=0.35, n_bolts=0)
        assert res["ok"] is False


# ===========================================================================
# 8. fatigue_check
# ===========================================================================

class TestFatigueCheck:

    def test_goodman_ratio_formula(self):
        """goodman_ratio = Kf·σ_a/Se + σ_m/Sut."""
        sa, Se, sm, Sut, Kf = 50e6, 300e6, 400e6, 800e6, 2.5
        res = fatigue_check(sa, Se, sm, Sut, Kf=Kf)
        assert res["ok"] is True
        expected = Kf * sa / Se + sm / Sut
        assert abs(res["goodman_ratio"] - expected) / expected < REL

    def test_safe_joint_returns_fatigue_ok(self):
        """Low alternating stress → good Goodman margin."""
        res = fatigue_check(sigma_a=10e6, Se=200e6, sigma_m=300e6, Sut=800e6, Kf=1.0)
        assert res["ok"] is True
        assert res["fatigue_ok"] is True
        assert res["n_goodman"] > 1.0

    def test_fatigue_failure_flagged(self):
        """High alternating stress → ratio > 1 → fatigue failure warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            res = fatigue_check(
                sigma_a=150e6, Se=100e6, sigma_m=600e6, Sut=700e6, Kf=3.0
            )
        assert res["ok"] is True
        assert res["fatigue_ok"] is False
        assert res["goodman_ratio"] > 1.0
        assert len(res["warnings"]) > 0
        assert len(w) > 0

    def test_n_goodman_equals_reciprocal_of_ratio(self):
        """n_goodman = 1 / goodman_ratio."""
        res = fatigue_check(20e6, 200e6, 300e6, 800e6)
        assert res["ok"] is True
        assert abs(res["n_goodman"] - 1.0 / res["goodman_ratio"]) < REL

    def test_zero_alternating_stress_gives_static_only(self):
        """σ_a=0: ratio = σ_m / Sut (static loading)."""
        sm, Sut = 400e6, 800e6
        res = fatigue_check(sigma_a=0.0, Se=200e6, sigma_m=sm, Sut=Sut)
        assert res["ok"] is True
        assert abs(res["goodman_ratio"] - sm / Sut) < REL

    def test_kf_increases_ratio(self):
        """Higher Kf must increase Goodman ratio."""
        r1 = fatigue_check(50e6, 200e6, 300e6, 800e6, Kf=1.0)["goodman_ratio"]
        r2 = fatigue_check(50e6, 200e6, 300e6, 800e6, Kf=3.0)["goodman_ratio"]
        assert r2 > r1

    def test_negative_Se_returns_error(self):
        res = fatigue_check(50e6, -200e6, 300e6, 800e6)
        assert res["ok"] is False

    def test_negative_Sut_returns_error(self):
        res = fatigue_check(50e6, 200e6, 300e6, -800e6)
        assert res["ok"] is False


# ===========================================================================
# 9. strip_length
# ===========================================================================

class TestStripLength:

    def test_returns_positive_engagement(self):
        """Basic call returns positive engagement lengths."""
        res = strip_length(
            F_preload=20000.0, F_external=5000.0, Phi=0.10,
            d_nom=0.016, thread_pitch=0.002,
            Ssy_bolt=480e6, Ssy_nut=280e6,
        )
        assert res["ok"] is True
        assert res["L_e_bolt_m"] > 0
        assert res["L_e_nut_m"] > 0
        assert res["L_e_required_m"] > 0

    def test_required_length_includes_safety_factor(self):
        """L_e_required = max(L_e_bolt, L_e_nut) × safety_factor."""
        res = strip_length(
            F_preload=20000.0, F_external=0.0, Phi=0.10,
            d_nom=0.016, thread_pitch=0.002,
            Ssy_bolt=480e6, Ssy_nut=280e6,
            safety_factor=3.0,
        )
        assert res["ok"] is True
        expected = max(res["L_e_bolt_m"], res["L_e_nut_m"]) * 3.0
        assert abs(res["L_e_required_m"] - expected) / expected < REL

    def test_stronger_bolt_material_reduces_engagement(self):
        """Stronger bolt (higher Ssy) needs shorter engagement."""
        base = dict(
            F_preload=30000.0, F_external=0.0, Phi=0.10,
            d_nom=0.016, thread_pitch=0.002, Ssy_nut=280e6,
        )
        L1 = strip_length(Ssy_bolt=400e6, **base)["L_e_bolt_m"]
        L2 = strip_length(Ssy_bolt=800e6, **base)["L_e_bolt_m"]
        assert L1 > L2

    def test_higher_external_load_increases_engagement(self):
        """Higher external load must increase required engagement."""
        base = dict(
            F_preload=20000.0, Phi=0.10, d_nom=0.016,
            thread_pitch=0.002, Ssy_bolt=480e6, Ssy_nut=280e6,
        )
        L1 = strip_length(F_external=0.0, **base)["L_e_required_m"]
        L2 = strip_length(F_external=20000.0, **base)["L_e_required_m"]
        assert L2 > L1

    def test_zero_d_nom_returns_error(self):
        res = strip_length(20000.0, 0.0, 0.1, 0.0, 0.002, 480e6, 280e6)
        assert res["ok"] is False

    def test_negative_pitch_returns_error(self):
        res = strip_length(20000.0, 0.0, 0.1, 0.016, -0.002, 480e6, 280e6)
        assert res["ok"] is False

    def test_negative_Ssy_bolt_returns_error(self):
        res = strip_length(20000.0, 0.0, 0.1, 0.016, 0.002, -480e6, 280e6)
        assert res["ok"] is False


# ===========================================================================
# 10. ISO_THREAD table
# ===========================================================================

class TestISOThread:

    def test_m16_entries(self):
        """M16 thread: pitch=2.0 mm, stress_area≈157 mm²."""
        t = ISO_THREAD[16.0]
        assert abs(t["pitch_mm"] - 2.0) < 1e-9
        assert abs(t["stress_area_mm2"] - 157.0) < 1.0

    def test_m8_entries(self):
        """M8: pitch=1.25 mm, At≈36.6 mm²."""
        t = ISO_THREAD[8.0]
        assert abs(t["pitch_mm"] - 1.25) < 1e-9
        assert abs(t["stress_area_mm2"] - 36.6) < 0.5

    def test_minor_diameter_less_than_nominal(self):
        """Minor diameter must always be < nominal diameter."""
        for nom, data in ISO_THREAD.items():
            assert data["d_minor_mm"] < nom, f"M{nom}: d_minor >= nom"

    def test_pitch_diameter_between_minor_and_nominal(self):
        """Pitch diameter must be between minor and nominal."""
        for nom, data in ISO_THREAD.items():
            assert data["d_minor_mm"] < data["d_pitch_mm"] < nom, f"M{nom}: pitch diam out of range"

    def test_stress_area_increases_with_diameter(self):
        """Larger bolt must have larger stress area."""
        sizes = sorted(ISO_THREAD.keys())
        for i in range(len(sizes) - 1):
            d1, d2 = sizes[i], sizes[i + 1]
            assert ISO_THREAD[d1]["stress_area_mm2"] < ISO_THREAD[d2]["stress_area_mm2"]


# ===========================================================================
# 10b. CITABLE REFERENCE CASES — known numeric answers
# ---------------------------------------------------------------------------
# Sources:
#   Shigley's Mechanical Engineering Design, 10th ed., Chapter 8
#     (Eq. 8-17 bolt stiffness, Eq. 8-20 frustum member stiffness,
#      Eq. 8-27 nut-factor torque, Eq. 8-29 separation, §8-11 Goodman).
#   ISO 898-1 / ISO 724 tensile stress area  At = π/4·((d2+d3)/2)².
#   VDI 2230-1:2015, Annex A (frustum stiffness, α = 30°).
# ===========================================================================

class TestCitableReferenceCases:

    def test_iso_stress_area_matches_iso898(self):
        """ISO 898-1 Annex defines At = π/4·((d_pitch + d_minor)/2)².
        Recomputing from the tabulated pitch/minor diameters must
        reproduce the published stress areas (Shigley Table 8-1):
        M16 → 156.7 mm², M10 → 58.0 mm², M8 → 36.6 mm²."""
        for nom, At_pub in ((16.0, 157.0), (10.0, 58.0), (8.0, 36.6),
                            (6.0, 20.1), (12.0, 84.3), (20.0, 245.0)):
            e = ISO_THREAD[nom]
            dp = e["d_pitch_mm"]
            dr = e["d_minor_mm"]
            At_calc = math.pi / 4.0 * ((dp + dr) / 2.0) ** 2
            assert abs(At_calc - At_pub) / At_pub < 0.01, (
                f"M{nom}: At_calc={At_calc:.2f} vs published {At_pub}"
            )
            assert abs(e["stress_area_mm2"] - At_pub) < max(0.6, 0.005 * At_pub)

    def test_preload_nut_factor_shigley_eq_8_27(self):
        """Shigley Eq. 8-27: T = K·Fi·d  →  Fi = T/(K·d).
        T=100 N·m, d=20 mm, K=0.20 → Fi = 100/(0.20·0.020) = 25 000 N."""
        res = preload_from_torque(T=100.0, d=0.020, K=0.20)
        assert res["ok"] is True
        assert abs(res["F_preload_N"] - 25000.0) / 25000.0 < REL

    def test_bolt_stiffness_shigley_eq_8_17_fully_threaded(self):
        """Shigley Eq. 8-17 (fully threaded within grip):
        kb = E·At/lt with At = π/4·d_minor².
        M16 minor d=13.546 mm, lt=30 mm, E=200 GPa →
        At = 1.4412e-4 m², kb = 200e9·1.4412e-4/0.030 = 9.6077e8 N/m."""
        d_t = 0.013546
        res = bolt_stiffness(0.016, 0.0, d_t, 0.030, 200e9)
        assert res["ok"] is True
        A_t = math.pi / 4.0 * d_t ** 2
        kb_exp = 200e9 * A_t / 0.030
        assert abs(res["k_bolt_N_per_m"] - kb_exp) / kb_exp < REL
        assert abs(res["k_bolt_N_per_m"] - 9.6077e8) / 9.6077e8 < 1e-3

    def test_member_stiffness_shigley_eq_8_20_frustum(self):
        """Shigley Eq. 8-20 / VDI 2230 frustum, α=30°, washer face
        d_w = 1.5·d.  Two back-to-back cones in series.
        Grip 30 mm, steel E=207 GPa, M16 →
        k_m = 3.7906e9 N/m (hand-evaluated from Eq. 8-20)."""
        res = clamped_stiffness(0.030, 207e9, 0.016)
        assert res["ok"] is True
        E, d, D, l = 207e9, 0.016, 1.5 * 0.016, 0.030
        t = l / 2.0
        tan30 = math.tan(math.radians(30.0))
        num = (2 * t * tan30 + D - d) * (D + d)
        den = (2 * t * tan30 + D + d) * (D - d)
        k_cone = math.pi * E * d * tan30 / math.log(num / den)
        k_m_exp = k_cone / 2.0
        assert abs(res["k_clamp_N_per_m"] - k_m_exp) / k_m_exp < 1e-9
        assert abs(res["k_clamp_N_per_m"] - 3.7906e9) / 3.7906e9 < 1e-3

    def test_stiffness_constant_C_shigley(self):
        """Shigley §8-6 joint stiffness constant C = kb/(kb+km) = Φ.
        For the M16/30 mm steel joint above: C ≈ 0.202."""
        kb = bolt_stiffness(0.016, 0.0, 0.013546, 0.030, 200e9)[
            "k_bolt_N_per_m"]
        km = clamped_stiffness(0.030, 207e9, 0.016)["k_clamp_N_per_m"]
        res = joint_load_factor(kb, km)
        assert res["ok"] is True
        assert abs(res["Phi"] - kb / (kb + km)) < 1e-12
        assert abs(res["Phi"] - 0.202) < 5e-3

    def test_separation_factor_shigley_eq_8_29(self):
        """Shigley Eq. 8-29: load factor against separation
        n0 = Fi / [P·(1 − C)].  Fi=20 000 N, P=10 000 N, C=0.20 →
        n0 = 20000 / (10000·0.8) = 2.5."""
        res = separation_safety(F_preload=20000.0, F_external=10000.0,
                                Phi=0.20)
        assert res["ok"] is True
        assert abs(res["n_sep"] - 2.5) / 2.5 < REL

    def test_working_stress_shigley_eq_8_25(self):
        """Shigley Eq. 8-25 bolt stress under load:
        σb = (Fi + C·P)/At.  Fi=20 kN, C=0.20, P=5 kN, At=157 mm² →
        σb = (20000 + 1000)/157e-6 = 133.758 MPa."""
        res = bolt_working_stress(20000.0, 5000.0, 0.20, 157e-6)
        assert res["ok"] is True
        sig_exp = (20000.0 + 0.20 * 5000.0) / 157e-6
        assert abs(res["sigma_total_Pa"] - sig_exp) / sig_exp < REL
        assert abs(res["sigma_total_Pa"] - 133.758e6) / 133.758e6 < 1e-3

    def test_modified_goodman_shigley_fatigue(self):
        """Shigley §6-12 / §8-11 modified-Goodman criterion:
        n = 1 / (σa/Se + σm/Sut) for Kf=1.
        σa=50 MPa, Se=200 MPa, σm=300 MPa, Sut=800 MPa →
        ratio = 0.25 + 0.375 = 0.625, n = 1.6."""
        res = fatigue_check(50e6, 200e6, 300e6, 800e6, Kf=1.0)
        assert res["ok"] is True
        assert abs(res["goodman_ratio"] - 0.625) / 0.625 < REL
        assert abs(res["n_goodman"] - 1.6) / 1.6 < REL

    def test_slip_critical_capacity_shigley_eq_8_30(self):
        """Friction-grip (slip-critical) capacity, Shigley §8-12 /
        RCSC: n_slip = μ·Fi·N / V.
        μ=0.35, Fi=20 kN, N=2 bolts, V=10 kN →
        n_slip = 0.35·20000·2/10000 = 1.4."""
        res = slip_safety(F_preload=20000.0, F_shear=10000.0,
                          mu=0.35, n_bolts=2)
        assert res["ok"] is True
        assert abs(res["n_slip"] - 1.4) / 1.4 < REL


# ===========================================================================
# 11. LLM tool wrappers
# ===========================================================================

class TestToolWrappers:

    def test_run_preload_happy_path(self):
        ctx = _ctx()
        raw = _run(run_bolt_preload_from_torque(ctx, _args(T=90.0, d=0.016, K=0.20)))
        d = _ok_tool(raw)
        assert abs(d["F_preload_N"] - 28125.0) / 28125.0 < REL

    def test_run_preload_missing_T(self):
        ctx = _ctx()
        raw = _run(run_bolt_preload_from_torque(ctx, _args(d=0.016)))
        _err_tool(raw)

    def test_run_preload_bad_json(self):
        ctx = _ctx()
        raw = _run(run_bolt_preload_from_torque(ctx, b"bad json"))
        _err_tool(raw)

    def test_run_bolt_stiffness_fully_threaded(self):
        ctx = _ctx()
        raw = _run(run_bolt_stiffness(ctx, _args(
            d_shank=0.016, length_shank=0.0,
            d_thread_minor=0.013835, length_thread=0.025,
        )))
        d = _ok_tool(raw)
        assert d["k_bolt_N_per_m"] > 0

    def test_run_bolt_stiffness_missing_field(self):
        ctx = _ctx()
        raw = _run(run_bolt_stiffness(ctx, _args(
            d_shank=0.016, d_thread_minor=0.013835, length_thread=0.025,
        )))
        _err_tool(raw)

    def test_run_clamped_member_stiffness_happy_path(self):
        ctx = _ctx()
        raw = _run(run_clamped_member_stiffness(ctx, _args(
            grip_length=0.030, E_clamp=200e9, d_bolt=0.016,
        )))
        d = _ok_tool(raw)
        assert d["k_clamp_N_per_m"] > 0

    def test_run_joint_load_factor_happy_path(self):
        ctx = _ctx()
        raw = _run(run_bolt_joint_load_factor(ctx, _args(
            k_bolt=100e6, k_clamp=1000e6,
        )))
        d = _ok_tool(raw)
        expected_phi = 100e6 / (100e6 + 1000e6)
        assert abs(d["Phi"] - expected_phi) / expected_phi < REL

    def test_run_joint_load_factor_missing_k_clamp(self):
        ctx = _ctx()
        raw = _run(run_bolt_joint_load_factor(ctx, _args(k_bolt=100e6)))
        _err_tool(raw)

    def test_run_working_stress_happy_path(self):
        ctx = _ctx()
        raw = _run(run_bolt_working_stress(ctx, _args(
            F_preload=20000.0, F_external=3000.0, Phi=0.12, A_stress=157e-6,
        )))
        d = _ok_tool(raw)
        assert d["sigma_total_Pa"] > 0
        assert d["sigma_von_mises_Pa"] >= d["sigma_total_Pa"]

    def test_run_separation_safety_happy_path(self):
        ctx = _ctx()
        raw = _run(run_bolt_separation_safety(ctx, _args(
            F_preload=30000.0, F_external=5000.0, Phi=0.10,
        )))
        d = _ok_tool(raw)
        assert d["n_sep"] > 1.0
        assert d["separated"] is False

    def test_run_separation_safety_missing_Phi(self):
        ctx = _ctx()
        raw = _run(run_bolt_separation_safety(ctx, _args(
            F_preload=30000.0, F_external=5000.0,
        )))
        _err_tool(raw)

    def test_run_slip_safety_happy_path(self):
        ctx = _ctx()
        raw = _run(run_bolt_slip_safety(ctx, _args(
            F_preload=20000.0, F_shear=4000.0, mu=0.35, n_bolts=2,
        )))
        d = _ok_tool(raw)
        assert d["n_slip"] > 1.0

    def test_run_fatigue_check_happy_path(self):
        ctx = _ctx()
        raw = _run(run_bolt_fatigue_check(ctx, _args(
            sigma_a=20e6, Se=200e6, sigma_m=300e6, Sut=800e6, Kf=2.5,
        )))
        d = _ok_tool(raw)
        assert d["fatigue_ok"] is True
        assert "goodman_ratio" in d

    def test_run_fatigue_check_missing_Sut(self):
        ctx = _ctx()
        raw = _run(run_bolt_fatigue_check(ctx, _args(
            sigma_a=20e6, Se=200e6, sigma_m=300e6,
        )))
        _err_tool(raw)

    def test_run_strip_length_happy_path(self):
        ctx = _ctx()
        raw = _run(run_bolt_strip_length(ctx, _args(
            F_preload=20000.0, F_external=5000.0, Phi=0.10,
            d_nom=0.016, thread_pitch=0.002,
            Ssy_bolt=480e6, Ssy_nut=280e6,
        )))
        d = _ok_tool(raw)
        assert d["L_e_required_m"] > 0

    def test_run_strip_length_missing_Ssy_nut(self):
        ctx = _ctx()
        raw = _run(run_bolt_strip_length(ctx, _args(
            F_preload=20000.0, F_external=5000.0, Phi=0.10,
            d_nom=0.016, thread_pitch=0.002, Ssy_bolt=480e6,
        )))
        _err_tool(raw)
