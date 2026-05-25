"""
Tests for kerf_fem.harmonic — steady-state harmonic response (mode superposition).

Validation targets
------------------
1. SDOF DAF = 1/√((1-r²)²+(2ζr)²) — exact closed form
2. SDOF resonance at r=1 gives DAF = 1/(2ζ) — exact
3. Static limit (r→0): DAF → 1.0
4. Mode superposition on SDOF matches closed-form within 0.1%
5. Resonant peak frequency matches natural frequency within df tolerance
6. Phase at resonance is 90° (for small damping)
7. Tool handler valid/bad JSON
"""

from __future__ import annotations

import json
import math
import asyncio
import pytest

from kerf_fem.harmonic import (
    sdof_daf,
    sdof_phase_deg,
    harmonic_response,
    sdof_harmonic_response,
)


# ---------------------------------------------------------------------------
# §1  SDOF DAF closed-form
# ---------------------------------------------------------------------------

class TestSDOF_DAF:

    def test_resonance_daf(self):
        """At r=1 (resonance), DAF = 1/(2ζ) exactly."""
        for zeta in [0.01, 0.05, 0.1, 0.2]:
            daf = sdof_daf(1.0, zeta)
            expected = 1.0 / (2.0 * zeta)
            rel_err = abs(daf - expected) / expected
            assert rel_err < 1e-12, (
                f"DAF at resonance ζ={zeta}: got {daf:.6f}, expected {expected:.6f}"
            )

    def test_static_limit(self):
        """At r→0, DAF → 1.0 (static response)."""
        for zeta in [0.01, 0.05, 0.1]:
            daf = sdof_daf(0.0, zeta)
            assert abs(daf - 1.0) < 1e-12, f"Static DAF should be 1.0, got {daf}"

    def test_daf_formula_arbitrary_r(self):
        """DAF agrees with closed form at arbitrary r."""
        r, zeta = 0.7, 0.05
        daf = sdof_daf(r, zeta)
        expected = 1.0 / math.sqrt((1 - r**2)**2 + (2*zeta*r)**2)
        assert abs(daf - expected) / expected < 1e-12

    def test_daf_decreases_beyond_resonance(self):
        """For small ζ, DAF decreases for r > 1."""
        zeta = 0.05
        daf_at_1 = sdof_daf(1.0, zeta)
        daf_at_2 = sdof_daf(2.0, zeta)
        assert daf_at_2 < daf_at_1, "DAF should decrease beyond resonance"

    def test_higher_damping_lower_peak(self):
        """Higher damping → lower peak DAF."""
        daf_low = sdof_daf(1.0, 0.02)
        daf_high = sdof_daf(1.0, 0.1)
        assert daf_high < daf_low

    def test_daf_always_positive(self):
        """DAF must always be positive."""
        for r in [0.0, 0.5, 1.0, 1.5, 2.0, 3.0]:
            for zeta in [0.01, 0.05, 0.2]:
                daf = sdof_daf(r, zeta)
                assert daf > 0


# ---------------------------------------------------------------------------
# §2  SDOF phase angle
# ---------------------------------------------------------------------------

class TestSDOF_Phase:

    def test_phase_at_resonance(self):
        """At resonance (r=1), phase should be ±90°."""
        for zeta in [0.01, 0.05, 0.1]:
            phase = sdof_phase_deg(1.0, zeta)
            assert abs(abs(phase) - 90.0) < 1e-10, (
                f"Phase at resonance ζ={zeta}: got {phase:.4f}°, expected ±90°"
            )

    def test_phase_below_resonance(self):
        """Below resonance (r < 1), phase between 0° and 90°."""
        phase = sdof_phase_deg(0.5, 0.05)
        assert 0.0 <= phase <= 90.0, f"Phase below resonance: {phase}"

    def test_phase_above_resonance(self):
        """Above resonance (r > 1), phase between 90° and 180°."""
        phase = sdof_phase_deg(1.5, 0.05)
        assert 90.0 <= phase <= 180.0, f"Phase above resonance: {phase}"


# ---------------------------------------------------------------------------
# §3  Mode superposition harmonic_response — SDOF validation
# ---------------------------------------------------------------------------

class TestHarmonicResponseSDOF:
    """
    Treat a single-DOF system with:
        ω_n = 2π × 10 Hz,  ζ = 0.05,  F = 1 N,  k = ω_n²·m = ω_n² (m=1 kg)
    Mode shape φ = [1/ω_n²] (unit displacement per unit force, for m-normalised mode).
    Modal force = φ^T · F = 1/ω_n².
    Response at DOF 0: |U(ω)| = |H_0(ω)|.

    For mass-normalised mode shape φ_i s.t. φ_i^T M φ_i = 1 with m=1:
        φ_i = 1,  modal force Γ = F_0 = 1
    Then physical response:
        U = φ / (ω_n² - ω² + 2iζω_nω) × Γ = 1/(ω_n² - ω² + 2iζω_nω)
    Static response U_static = 1/ω_n².
    DAF = |U| × ω_n² = 1/√((1-r²)²+(2ζr)²).
    """

    FN = 10.0           # Hz
    ZETA = 0.05
    WN = 2.0 * math.pi * FN
    F0 = 1.0            # N
    TOL = 0.001         # 0.1 %

    @property
    def modes(self):
        return {
            "omega": [self.WN],
            "mode_shapes": [[1.0]],   # mass-normalised, m=1 kg
        }

    @property
    def force(self):
        return [self.F0]

    def test_resonant_peak_frequency(self):
        """Peak amplitude should occur at approximately fn (within df resolution)."""
        freq_range = {"f_min": 1.0, "f_max": 20.0, "n_pts": 500}
        res = harmonic_response(
            self.modes, self.ZETA, self.force, freq_range, dof_index=0
        )
        assert res["ok"], res.get("reason")
        # Allow ±2 df tolerance for peak location
        df = (20.0 - 1.0) / 499
        assert abs(res["resonant_peak_hz"] - self.FN) < 2.0 * df, (
            f"Resonant peak at {res['resonant_peak_hz']:.3f} Hz, expected {self.FN} Hz"
        )

    def test_daf_matches_closed_form_at_resonance(self):
        """
        At r=1, FEM DAF = 1/(2ζ).
        |U(ω_n)| · ω_n² should match DAF = 1/(2ζ) to within TOL.
        """
        # Run at exactly fn
        freq_range = {"f_min": self.FN * 0.9999, "f_max": self.FN * 1.0001, "n_pts": 3}
        res = harmonic_response(
            self.modes, self.ZETA, self.force, freq_range, dof_index=0
        )
        assert res["ok"]
        # amplitude at index 1 (closest to fn)
        amp = res["amplitude"][1]
        daf_fem = amp * self.WN**2
        daf_exact = 1.0 / (2.0 * self.ZETA)
        rel_err = abs(daf_fem - daf_exact) / daf_exact
        assert rel_err < self.TOL, (
            f"DAF at resonance: FEM={daf_fem:.4f}, exact={daf_exact:.4f}, err={rel_err*100:.3f}%"
        )

    def test_static_response(self):
        """
        At very low frequency (r≈0), amplitude ≈ F0/ωn² = 1/ωn².
        """
        freq_range = {"f_min": 0.001, "f_max": 0.01, "n_pts": 5}
        res = harmonic_response(
            self.modes, self.ZETA, self.force, freq_range, dof_index=0
        )
        assert res["ok"]
        amp = res["amplitude"][0]
        expected = self.F0 / self.WN**2
        rel_err = abs(amp - expected) / expected
        assert rel_err < self.TOL, (
            f"Static amplitude: FEM={amp:.6e}, expected={expected:.6e}, err={rel_err*100:.3f}%"
        )

    def test_daf_vs_analytical_sweep(self):
        """
        Over a full sweep 1–20 Hz, DAF_numerical / DAF_analytical should
        be < 0.1% everywhere (validates DAF_analytical output field).
        """
        freq_range = {"f_min": 0.5, "f_max": 20.0, "n_pts": 100}
        res = harmonic_response(
            self.modes, self.ZETA, self.force, freq_range, dof_index=0
        )
        assert res["ok"]

        max_err = 0.0
        for i, f in enumerate(res["frequencies_hz"]):
            amp = res["amplitude"][i]
            daf_fem = amp * self.WN**2
            r = f / self.FN
            daf_exact = sdof_daf(r, self.ZETA)
            if daf_exact > 1e-10:
                err = abs(daf_fem - daf_exact) / daf_exact
                max_err = max(max_err, err)

        assert max_err < 0.001, (
            f"Max DAF error over sweep: {max_err*100:.3f}% (tolerance 0.1%)"
        )

    def test_amplitude_list_length(self):
        n_pts = 150
        freq_range = {"f_min": 1.0, "f_max": 20.0, "n_pts": n_pts}
        res = harmonic_response(self.modes, self.ZETA, self.force, freq_range)
        assert res["ok"]
        assert len(res["amplitude"]) == n_pts
        assert len(res["frequencies_hz"]) == n_pts
        assert len(res["phase_deg"]) == n_pts

    def test_phase_at_resonance_near_90deg(self):
        """Phase at resonance should be near ±90° for small ζ."""
        freq_range = {"f_min": self.FN * 0.9999, "f_max": self.FN * 1.0001, "n_pts": 3}
        res = harmonic_response(
            self.modes, self.ZETA, self.force, freq_range, dof_index=0
        )
        assert res["ok"]
        phase = res["phase_deg"][1]
        assert abs(abs(phase) - 90.0) < 1.0, (
            f"Phase at resonance: {phase:.2f}°, expected ±90°"
        )


# ---------------------------------------------------------------------------
# §4  Multi-mode response
# ---------------------------------------------------------------------------

class TestHarmonicResponseMultiMode:

    def test_two_modes_run(self):
        """Two-mode harmonic response returns ok=True."""
        modes = {
            "omega": [2 * math.pi * 10.0, 2 * math.pi * 40.0],
            "mode_shapes": [[1.0, 0.0], [0.0, 1.0]],
        }
        freq_range = {"f_min": 1.0, "f_max": 50.0, "n_pts": 200}
        res = harmonic_response(modes, 0.05, [1.0, 1.0], freq_range, dof_index=0)
        assert res["ok"]
        assert len(res["amplitude"]) == 200

    def test_per_mode_damping_list(self):
        """Per-mode damping list accepted."""
        modes = {
            "omega": [2 * math.pi * 10.0, 2 * math.pi * 40.0],
            "mode_shapes": [[1.0, 0.0], [0.0, 1.0]],
        }
        res = harmonic_response(
            modes, [0.02, 0.1], [1.0, 0.0],
            {"f_min": 1.0, "f_max": 50.0, "n_pts": 100}
        )
        assert res["ok"]


# ---------------------------------------------------------------------------
# §5  Input validation
# ---------------------------------------------------------------------------

class TestHarmonicInputValidation:

    def test_empty_omega(self):
        modes = {"omega": [], "mode_shapes": []}
        res = harmonic_response(modes, 0.05, [1.0], {"f_min": 1.0, "f_max": 10.0, "n_pts": 10})
        assert not res["ok"]

    def test_mismatched_mode_count(self):
        modes = {
            "omega": [100.0, 200.0],
            "mode_shapes": [[1.0]],  # only 1 shape for 2 omegas
        }
        res = harmonic_response(modes, 0.05, [1.0], {"f_min": 1.0, "f_max": 10.0, "n_pts": 10})
        assert not res["ok"]

    def test_fmax_less_than_fmin(self):
        modes = {"omega": [100.0], "mode_shapes": [[1.0]]}
        res = harmonic_response(modes, 0.05, [1.0], {"f_min": 10.0, "f_max": 5.0, "n_pts": 10})
        assert not res["ok"]

    def test_negative_damping(self):
        modes = {"omega": [100.0], "mode_shapes": [[1.0]]}
        res = harmonic_response(modes, -0.05, [1.0], {"f_min": 1.0, "f_max": 10.0, "n_pts": 10})
        assert not res["ok"]


# ---------------------------------------------------------------------------
# §6  Tool handler
# ---------------------------------------------------------------------------

class TestHarmonicToolHandler:

    def test_valid_payload(self):
        from kerf_fem.tools import run_fem_harmonic_response
        wn = 2.0 * math.pi * 10.0
        payload = {
            "modes": {"omega": [wn], "mode_shapes": [[1.0]]},
            "modal_damping": 0.05,
            "force_vector": [1.0],
            "freq_range": {"f_min": 1.0, "f_max": 20.0, "n_pts": 50},
        }
        raw = asyncio.run(run_fem_harmonic_response(None, json.dumps(payload).encode()))
        result = json.loads(raw)
        assert result.get("ok") is True
        assert "amplitude" in result

    def test_bad_json(self):
        from kerf_fem.tools import run_fem_harmonic_response
        raw = asyncio.run(run_fem_harmonic_response(None, b"invalid json {{{"))
        result = json.loads(raw)
        assert "error" in result

    def test_missing_field(self):
        from kerf_fem.tools import run_fem_harmonic_response
        payload = {"modes": {"omega": [100.0], "mode_shapes": [[1.0]]}}
        raw = asyncio.run(run_fem_harmonic_response(None, json.dumps(payload).encode()))
        result = json.loads(raw)
        assert "error" in result

    def test_tool_spec_name(self):
        from kerf_fem.tools import fem_harmonic_response_spec
        assert fem_harmonic_response_spec.name == "fem_harmonic_response"


# ---------------------------------------------------------------------------
# §7  SDOF harmonic response helper
# ---------------------------------------------------------------------------

class TestSDOFHarmonicResponseHelper:

    def test_sdof_harmonic_static(self):
        """At very low f, amplitude ≈ F0/k."""
        fn, zeta, F0, k = 10.0, 0.05, 100.0, 50000.0
        res = sdof_harmonic_response(fn, zeta, F0, k, {"f_min": 0.001, "f_max": 0.01, "n_pts": 5})
        assert res["ok"]
        amp = res["amplitude"][0]
        expected = F0 / k
        assert abs(amp - expected) / expected < 0.001

    def test_sdof_harmonic_resonance(self):
        """Peak amplitude ≈ F0/(k × 2ζ).  Dense grid near resonance."""
        fn, zeta, F0, k = 10.0, 0.05, 100.0, 50000.0
        wn = 2.0 * math.pi * fn
        # Very dense sweep centred on fn to capture the resonant peak accurately
        res = sdof_harmonic_response(
            fn, zeta, F0, k,
            {"f_min": fn * 0.999, "f_max": fn * 1.001, "n_pts": 2000},
        )
        assert res["ok"]
        peak = max(res["amplitude"])
        expected = (F0 / k) / (2.0 * zeta)
        rel_err = abs(peak - expected) / expected
        assert rel_err < 0.001, (
            f"Resonance peak {peak:.6e} vs exact {expected:.6e}, err={rel_err*100:.3f}%"
        )
