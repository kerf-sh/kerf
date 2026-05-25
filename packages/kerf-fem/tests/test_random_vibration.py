"""
Tests for kerf_fem.random_vibration — random-vibration response to PSD.

Validation targets
------------------
1. Miles' equation closed-form: GRMS = √((π/2)·fn·Q·S0)
2. Miles' equation consistency: GRMS = 1/(2ζ) × something Q-independent
3. PSD table integration: ∫S df = S0 × BW for flat PSD
4. Modal method SDOF displacement RMS matches Miles (within ~5% for broad flat PSD)
5. Higher Q (lower ζ) → higher GRMS (Miles)
6. Tool handler valid/bad JSON
"""

from __future__ import annotations

import json
import math
import asyncio
import pytest

from kerf_fem.random_vibration import (
    miles_equation,
    random_vibration_psd,
    miles_sdof_response,
    _integrate_psd_trapz,
    _interp_psd,
)


# ---------------------------------------------------------------------------
# §1  Miles' equation closed-form validation
# ---------------------------------------------------------------------------

class TestMilesEquation:

    def test_closed_form_direct(self):
        """GRMS = √((π/2) × fn × Q × S0) matches stdlib sqrt."""
        fn, Q, S0 = 100.0, 10.0, 0.04  # (m/s²)²/Hz
        res = miles_equation(fn, Q, S0)
        assert res["ok"]
        expected = math.sqrt(math.pi / 2.0 * fn * Q * S0)
        rel_err = abs(res["GRMS"] - expected) / expected
        assert rel_err < 1e-12, (
            f"Miles GRMS={res['GRMS']:.6e}, expected={expected:.6e}"
        )

    def test_sigma_1_equals_grms(self):
        """sigma_1 must equal GRMS."""
        res = miles_equation(50.0, 20.0, 0.01)
        assert res["ok"]
        assert abs(res["sigma_1"] - res["GRMS"]) < 1e-30

    def test_sigma_3_is_3x_grms(self):
        """sigma_3 = 3 × GRMS."""
        res = miles_equation(100.0, 10.0, 0.04)
        assert res["ok"]
        assert abs(res["sigma_3"] - 3.0 * res["GRMS"]) < 1e-30

    def test_zeta_roundtrip(self):
        """Q = 1/(2ζ) → returned zeta should match."""
        for zeta in [0.01, 0.05, 0.1, 0.2]:
            Q = 1.0 / (2.0 * zeta)
            res = miles_equation(100.0, Q, 0.01)
            assert res["ok"]
            assert abs(res["zeta"] - zeta) < 1e-12

    def test_grms_scales_with_sqrt_S0(self):
        """GRMS ∝ √S0: doubling S0 → GRMS × √2."""
        fn, Q = 100.0, 10.0
        res1 = miles_equation(fn, Q, 0.01)
        res2 = miles_equation(fn, Q, 0.02)
        ratio = res2["GRMS"] / res1["GRMS"]
        assert abs(ratio - math.sqrt(2.0)) < 1e-12

    def test_grms_scales_with_sqrt_fn(self):
        """GRMS ∝ √fn: quadrupling fn → GRMS × 2."""
        Q, S0 = 10.0, 0.01
        res1 = miles_equation(100.0, Q, S0)
        res4 = miles_equation(400.0, Q, S0)
        ratio = res4["GRMS"] / res1["GRMS"]
        assert abs(ratio - 2.0) < 1e-12

    def test_higher_Q_higher_grms(self):
        """Higher Q (lower damping) → higher GRMS."""
        fn, S0 = 100.0, 0.01
        res_low_Q = miles_equation(fn, 5.0, S0)
        res_high_Q = miles_equation(fn, 20.0, S0)
        assert res_high_Q["GRMS"] > res_low_Q["GRMS"]

    def test_zero_psd_zero_grms(self):
        """S0=0 → GRMS=0."""
        res = miles_equation(100.0, 10.0, 0.0)
        assert res["ok"]
        assert res["GRMS"] == 0.0

    def test_invalid_fn(self):
        res = miles_equation(0.0, 10.0, 0.01)
        assert not res["ok"]

    def test_invalid_Q(self):
        res = miles_equation(100.0, -1.0, 0.01)
        assert not res["ok"]

    def test_invalid_S0(self):
        res = miles_equation(100.0, 10.0, -0.01)
        assert not res["ok"]


# ---------------------------------------------------------------------------
# §2  PSD integration helper
# ---------------------------------------------------------------------------

class TestPSDIntegration:

    def test_flat_psd_integral(self):
        """∫_f1^f2 S0 df = S0 × (f2 - f1)."""
        f1, f2, S0 = 10.0, 1000.0, 0.04
        n = 500
        df = (f2 - f1) / (n - 1)
        table = [(f1 + k * df, S0) for k in range(n)]
        integral = _integrate_psd_trapz(table)
        expected = S0 * (f2 - f1)
        rel_err = abs(integral - expected) / expected
        assert rel_err < 1e-4, (
            f"Flat PSD integral {integral:.6e}, expected {expected:.6e}"
        )

    def test_single_point_returns_zero(self):
        assert _integrate_psd_trapz([(100.0, 0.04)]) == 0.0

    def test_empty_returns_zero(self):
        assert _integrate_psd_trapz([]) == 0.0

    def test_interpolation_inside_range(self):
        table = [(10.0, 1.0), (20.0, 2.0)]
        v = _interp_psd(table, 15.0)
        assert abs(v - 1.5) < 1e-12

    def test_interpolation_at_boundary(self):
        table = [(10.0, 1.0), (20.0, 2.0)]
        assert abs(_interp_psd(table, 10.0) - 1.0) < 1e-12
        assert abs(_interp_psd(table, 20.0) - 2.0) < 1e-12

    def test_interpolation_outside_range_is_zero(self):
        table = [(10.0, 1.0), (20.0, 2.0)]
        assert _interp_psd(table, 5.0) == 0.0
        assert _interp_psd(table, 25.0) == 0.0


# ---------------------------------------------------------------------------
# §3  Modal random-vibration — SDOF vs Miles
# ---------------------------------------------------------------------------

class TestRandomVibrationSDOF:
    """
    SDOF base-excited system:
        fn = 100 Hz, ζ = 0.05, flat PSD S0 = 0.04 (m/s²)²/Hz

    Miles GRMS = √(π/2 × 100 × 10 × 0.04) = √(62.83...) ≈ 7.927 m/s²

    The modal method computes displacement RMS.
    For SDOF: σ_x ≈ σ_a / ωn² (from Miles acceleration RMS).
    """

    FN = 100.0       # Hz
    ZETA = 0.05
    S0 = 0.04        # (m/s²)²/Hz

    def _flat_psd(self, f_low=1.0, f_high=2000.0, n=300):
        df = (f_high - f_low) / (n - 1)
        return [[f_low + k * df, self.S0] for k in range(n)]

    def test_miles_displacement_vs_modal(self):
        """
        Modal method displacement RMS should match Miles displacement estimate
        σ_x = GRMS/ωn² within 5% (flat white noise approximation error).
        """
        res = miles_sdof_response(self.FN, self.ZETA, self.S0)
        assert res["ok"], res.get("reason")
        rel_err = res["relative_error_pct"]
        # Wide PSD (1–200×fn) so white-noise approximation holds well
        assert rel_err < 5.0, (
            f"Miles vs modal displacement RMS: {rel_err:.2f}% (tolerance 5%)"
        )

    def test_random_vibration_psd_runs_ok(self):
        """random_vibration_psd returns ok=True for valid SDOF setup."""
        wn = 2.0 * math.pi * self.FN
        modes = {"omega": [wn], "mode_shapes": [[1.0]]}
        psd = self._flat_psd()
        res = random_vibration_psd(
            modes=modes,
            modal_damping=self.ZETA,
            modal_participation=[1.0],
            psd_table=psd,
        )
        assert res["ok"], res.get("reason")
        assert res["rms_response"] > 0.0
        assert res["sigma_1"] == res["rms_response"]
        assert abs(res["sigma_3"] - 3.0 * res["rms_response"]) < 1e-30

    def test_miles_approx_returned(self):
        """miles_approx dict must be present in result."""
        wn = 2.0 * math.pi * self.FN
        modes = {"omega": [wn], "mode_shapes": [[1.0]]}
        psd = self._flat_psd()
        res = random_vibration_psd(
            modes=modes,
            modal_damping=self.ZETA,
            modal_participation=[1.0],
            psd_table=psd,
        )
        assert res["ok"]
        assert "miles_approx" in res
        assert res["miles_approx"]["ok"]

    def test_modal_rms_length(self):
        """modal_rms must have one entry per mode."""
        wn = 2.0 * math.pi * self.FN
        modes = {"omega": [wn, wn * 3.0], "mode_shapes": [[1.0, 0.0], [0.0, 1.0]]}
        psd = self._flat_psd()
        res = random_vibration_psd(
            modes=modes,
            modal_damping=0.05,
            modal_participation=[1.0, 0.5],
            psd_table=psd,
        )
        assert res["ok"]
        assert len(res["modal_rms"]) == 2

    def test_higher_damping_lower_rms(self):
        """Higher damping → lower RMS response (same PSD level)."""
        wn = 2.0 * math.pi * self.FN
        modes = {"omega": [wn], "mode_shapes": [[1.0]]}
        psd = self._flat_psd()
        res_low = random_vibration_psd(modes, 0.01, [1.0], psd)
        res_high = random_vibration_psd(modes, 0.2, [1.0], psd)
        assert res_low["ok"] and res_high["ok"]
        assert res_low["rms_response"] > res_high["rms_response"]

    def test_input_grms(self):
        """input_grms = √∫S df ≈ √(S0 × BW) for flat PSD."""
        f_low, f_high, n = 1.0, 2000.0, 500
        bw = f_high - f_low
        psd = self._flat_psd(f_low=f_low, f_high=f_high, n=n)
        wn = 2.0 * math.pi * self.FN
        modes = {"omega": [wn], "mode_shapes": [[1.0]]}
        res = random_vibration_psd(modes, self.ZETA, [1.0], psd)
        assert res["ok"]
        expected_grms = math.sqrt(self.S0 * bw)
        rel_err = abs(res["input_grms"] - expected_grms) / expected_grms
        assert rel_err < 0.01, (
            f"input_grms={res['input_grms']:.4e}, expected={expected_grms:.4e}"
        )


# ---------------------------------------------------------------------------
# §4  Input validation
# ---------------------------------------------------------------------------

class TestRandomVibrationInputValidation:

    def _base(self):
        wn = 2.0 * math.pi * 100.0
        return {
            "modes": {"omega": [wn], "mode_shapes": [[1.0]]},
            "modal_damping": 0.05,
            "modal_participation": [1.0],
            "psd_table": [[1.0, 0.04], [1000.0, 0.04]],
        }

    def test_missing_modes(self):
        """Passing None for modes should return ok=False."""
        a = self._base()
        # Pass None explicitly — triggers the isinstance(modes, dict) guard
        res = random_vibration_psd(
            None,  # modes=None
            a["modal_damping"],
            a["modal_participation"],
            a["psd_table"],
        )
        assert not res["ok"]

    def test_negative_damping(self):
        a = self._base()
        res = random_vibration_psd(
            a["modes"], -0.05, a["modal_participation"], a["psd_table"]
        )
        assert not res["ok"]

    def test_psd_too_short(self):
        a = self._base()
        res = random_vibration_psd(
            a["modes"], 0.05, [1.0], [[100.0, 0.04]]
        )
        assert not res["ok"]

    def test_participation_wrong_length(self):
        wn = 2.0 * math.pi * 100.0
        modes = {"omega": [wn, wn * 2], "mode_shapes": [[1.0, 0.0], [0.0, 1.0]]}
        res = random_vibration_psd(
            modes, 0.05, [1.0],  # only 1 factor for 2 modes
            [[1.0, 0.04], [1000.0, 0.04]]
        )
        assert not res["ok"]

    def test_negative_psd_value(self):
        a = self._base()
        res = random_vibration_psd(
            a["modes"], 0.05, [1.0], [[1.0, -0.04], [1000.0, 0.04]]
        )
        assert not res["ok"]


# ---------------------------------------------------------------------------
# §5  Tool handler
# ---------------------------------------------------------------------------

class TestRandomVibrationToolHandler:

    def _payload(self):
        wn = 2.0 * math.pi * 100.0
        return {
            "modes": {"omega": [wn], "mode_shapes": [[1.0]]},
            "modal_damping": 0.05,
            "modal_participation": [1.0],
            "psd_table": [[1.0, 0.04], [500.0, 0.04], [2000.0, 0.04]],
        }

    def test_valid_payload(self):
        from kerf_fem.tools import run_fem_random_vibration_psd
        raw = asyncio.run(
            run_fem_random_vibration_psd(None, json.dumps(self._payload()).encode())
        )
        result = json.loads(raw)
        assert result.get("ok") is True
        assert "rms_response" in result

    def test_bad_json(self):
        from kerf_fem.tools import run_fem_random_vibration_psd
        raw = asyncio.run(run_fem_random_vibration_psd(None, b"bad json {{{"))
        result = json.loads(raw)
        assert "error" in result

    def test_missing_required(self):
        from kerf_fem.tools import run_fem_random_vibration_psd
        payload = {"modes": {"omega": [628.0], "mode_shapes": [[1.0]]}}
        raw = asyncio.run(run_fem_random_vibration_psd(None, json.dumps(payload).encode()))
        result = json.loads(raw)
        assert "error" in result

    def test_tool_spec_name(self):
        from kerf_fem.tools import fem_random_vibration_psd_spec
        assert fem_random_vibration_psd_spec.name == "fem_random_vibration_psd"

    def test_n_sigma_parameter(self):
        """n_sigma parameter changes sigma_3 output."""
        from kerf_fem.tools import run_fem_random_vibration_psd
        p = self._payload()
        p["n_sigma"] = 2
        raw = asyncio.run(run_fem_random_vibration_psd(None, json.dumps(p).encode()))
        result = json.loads(raw)
        assert result.get("ok") is True
        assert abs(result["sigma_3"] - 2.0 * result["rms_response"]) < 1e-10
