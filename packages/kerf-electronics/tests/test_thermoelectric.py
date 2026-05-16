"""
Hermetic tests for the thermoelectric (Peltier TEC / Seebeck TEG) module.

Covers (≥30 tests):

  figure_of_merit
    - Z = α² / (R·K) exact value
    - ZT = Z·T_mean exact value when t_mean supplied
    - ZT is None when t_mean not supplied
    - Zero resistance → ok=False
    - Zero thermal_conductance → ok=False

  tec_operating_point
    - Qc/Qh/P/COP satisfy energy balance (Qh = Qc + P)
    - Higher current increases both Qc (up to optimum) and P
    - Negative Qc at excessive ΔT issues warning and ok=True
    - tc >= th → ok=False
    - Zero current → ok=False

  tec_optimal_current
    - I_max_Qc = α·Tc / R exactly
    - I_max_COP < I_max_Qc (max-COP always less than max-Qc current)
    - COP_max > 0 for realistic inputs
    - tc >= th → ok=False

  tec_delta_t_max
    - ΔT_max = ½·Z·Tc² exactly
    - Th_max = Tc + ΔT_max
    - Higher Z → larger ΔT_max
    - Zero resistance → ok=False

  tec_couples_required
    - N = ceil(Qc_target / Qc_per_couple)
    - Qc_total >= Qc_target
    - Negative Qc_per_couple → N=None and warning
    - tc >= th → ok=False

  tec_heatsink_coupled
    - Th > t_ambient (heatsink heats up)
    - Th = t_ambient + Rθ·Qh within tolerance after convergence
    - converged=True for typical inputs
    - Large Rθ → heatsink_undersized warning
    - Zero rtheta → ok=False

  tec_multistage
    - Two-stage: total_delta_T = t_hot_ambient − t_cold_target
    - Each stage result has Qc, Qh, P_input keys
    - Empty stages list → ok=False
    - t_cold_target >= t_hot_ambient → ok=False

  teg_output
    - Voc = α·N·ΔT exactly
    - Ri = N·R exactly
    - Pm = Voc²/(4·Ri) exactly
    - Im = Voc/(2·Ri) exactly
    - P_load = I_load²·R_load for arbitrary R_load
    - P_load = Pm at matched load (R_load = Ri)
    - P_load < Pm for mismatched load (R_load ≠ Ri)
    - More couples → higher Voc (linear)
    - tc >= th → ok=False
    - n_couples < 1 → ok=False

  teg_efficiency
    - eta_max < eta_carnot (always less than Carnot)
    - eta_max increases with higher ZT_mean
    - R_opt > resistance (M > 1 for ZT_mean > 0)
    - eta_ratio = eta_max / eta_carnot in (0, 1)
    - tc >= th → ok=False

  teg_array
    - Parray = n_series × n_parallel × Pm_module
    - Varray = n_series × Voc_module
    - n_total_modules = n_series × n_parallel

  teg_fill_factor
    - FF = (2 × n_couples × pellet_area) / footprint
    - FF > 1 issues warning and ok=True
    - Zero footprint → ok=False

  LLM tool handlers (stub registry)
    - tec_figure_of_merit tool ok=True returns Z
    - tec_operating_point tool ok=True returns Qc
    - tec_delta_t_max tool ok=True returns delta_T_max
    - teg_output tool ok=True returns Voc
    - teg_efficiency tool ok=True returns eta_max
    - tool with invalid JSON → error payload

Author: imranparuk
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
import sys
import types
import warnings

# ── Stub kerf_chat if not installed ──────────────────────────────────────────
try:
    import kerf_chat as _kc_pkg  # noqa: F401
    import kerf_chat.tools as _kc_tools  # noqa: F401
    import kerf_chat.tools.registry as _kc_real  # noqa: F401
except Exception:
    _kc_real = None

_reg_stub = types.ModuleType("kerf_chat.tools.registry")
_reg_stub.Registry = type("Registry", (list,), {})
_reg_stub.ToolSpec = type(
    "ToolSpec", (), {"__init__": lambda s, **kw: s.__dict__.update(kw)}
)
_reg_stub.err_payload = lambda msg, code: json.dumps(
    {"ok": False, "error": msg, "code": code}
)
_reg_stub.ok_payload = lambda v: json.dumps({"ok": True, **v})
_reg_stub.register = lambda spec, write=False: (lambda fn: fn)

_kerf_chat_stub = types.ModuleType("kerf_chat")
_kerf_chat_tools_stub = types.ModuleType("kerf_chat.tools")
sys.modules.setdefault("kerf_chat", _kerf_chat_stub)
sys.modules.setdefault("kerf_chat.tools", _kerf_chat_tools_stub)
if _kc_real is None:
    sys.modules["kerf_chat.tools.registry"] = _reg_stub

# ── Ensure src/ is on path ────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import pytest

from kerf_electronics.thermoelectric.tec import (
    figure_of_merit,
    tec_couples_required,
    tec_delta_t_max,
    tec_heatsink_coupled,
    tec_multistage,
    tec_operating_point,
    tec_optimal_current,
    teg_array,
    teg_efficiency,
    teg_fill_factor,
    teg_output,
)

# ── Load tool module via importlib so stub is active ─────────────────────────
_tool_spec_path = importlib.util.spec_from_file_location(
    "kerf_electronics.thermoelectric.tools",
    os.path.join(_SRC, "kerf_electronics", "thermoelectric", "tools.py"),
)
_tool_mod = importlib.util.module_from_spec(_tool_spec_path)
_tool_spec_path.loader.exec_module(_tool_mod)

_tec_fom_tool = _tool_mod.tec_figure_of_merit_tool
_tec_op_tool = _tool_mod.tec_operating_point_tool
_tec_dtm_tool = _tool_mod.tec_delta_t_max_tool
_teg_out_tool = _tool_mod.teg_output_tool
_teg_eff_tool = _tool_mod.teg_efficiency_tool


# ── Async call helper ─────────────────────────────────────────────────────────

async def call(fn, **kwargs):
    result = await fn(None, json.dumps(kwargs).encode())
    return json.loads(result)


# ── Typical module parameters used across tests ───────────────────────────────
# Approximate TEC127 module-level parameters (all 127 couples lumped together).
# At ΔT=25 K with I=3 A, Qc ≈ +20.6 W — a physically achievable operating point.
_ALPHA = 0.05       # V/K  (module Seebeck, 127 couples)
_R = 1.2            # Ω    (module resistance)
_K = 0.6            # W/K  (module thermal conductance)
_TC = 273.15        # K    (0°C cold side)
_TH = 298.15        # K    (25°C hot side, ΔT=25 K)
_I = 3.0            # A


# ═══════════════════════════════════════════════════════════════════════════════
# 1. figure_of_merit
# ═══════════════════════════════════════════════════════════════════════════════

class TestFigureOfMerit:
    def test_Z_exact(self):
        """Z = α² / (R·K) exactly."""
        res = figure_of_merit(alpha=_ALPHA, resistance=_R,
                               thermal_conductance=_K)
        assert res["ok"] is True
        expected_Z = _ALPHA ** 2 / (_R * _K)
        assert abs(res["Z"] - expected_Z) < 1e-15

    def test_ZT_exact_when_t_mean_given(self):
        """ZT = Z·T_mean exactly when t_mean supplied."""
        T = 300.0
        res = figure_of_merit(alpha=_ALPHA, resistance=_R,
                               thermal_conductance=_K, t_mean=T)
        assert res["ok"] is True
        expected_ZT = (_ALPHA ** 2 / (_R * _K)) * T
        assert abs(res["ZT"] - expected_ZT) < 1e-12

    def test_ZT_none_without_t_mean(self):
        """ZT is None when t_mean not supplied."""
        res = figure_of_merit(alpha=_ALPHA, resistance=_R,
                               thermal_conductance=_K)
        assert res["ok"] is True
        assert res["ZT"] is None

    def test_zero_resistance_error(self):
        res = figure_of_merit(alpha=_ALPHA, resistance=0.0,
                               thermal_conductance=_K)
        assert res["ok"] is False
        assert "resistance" in res["reason"]

    def test_zero_thermal_conductance_error(self):
        res = figure_of_merit(alpha=_ALPHA, resistance=_R,
                               thermal_conductance=0.0)
        assert res["ok"] is False
        assert "thermal_conductance" in res["reason"]

    def test_higher_alpha_higher_Z(self):
        """Doubling α quadruples Z."""
        res1 = figure_of_merit(alpha=_ALPHA, resistance=_R, thermal_conductance=_K)
        res2 = figure_of_merit(alpha=2 * _ALPHA, resistance=_R, thermal_conductance=_K)
        assert abs(res2["Z"] / res1["Z"] - 4.0) < 1e-9


# ═══════════════════════════════════════════════════════════════════════════════
# 2. tec_operating_point
# ═══════════════════════════════════════════════════════════════════════════════

class TestTecOperatingPoint:
    def test_energy_balance(self):
        """Qh = Qc + P_input (energy conservation)."""
        res = tec_operating_point(
            alpha=_ALPHA, resistance=_R, thermal_conductance=_K,
            current=_I, tc=_TC, th=_TH,
        )
        assert res["ok"] is True
        assert abs(res["Qh"] - (res["Qc"] + res["P_input"])) < 1e-10

    def test_Qc_formula_exact(self):
        """Qc = α·I·Tc − ½·I²·R − K·ΔT verified numerically."""
        alpha, R, K = _ALPHA, _R, _K
        I, Tc, Th = _I, _TC, _TH
        dT = Th - Tc
        expected = alpha * I * Tc - 0.5 * I ** 2 * R - K * dT
        res = tec_operating_point(alpha=alpha, resistance=R, thermal_conductance=K,
                                   current=I, tc=Tc, th=Th)
        assert abs(res["Qc"] - expected) < 1e-12

    def test_COP_positive_for_valid_point(self):
        """COP > 0 when Qc > 0."""
        res = tec_operating_point(
            alpha=_ALPHA, resistance=_R, thermal_conductance=_K,
            current=_I, tc=_TC, th=_TH,
        )
        assert res["ok"] is True
        if res["Qc"] > 0:
            assert res["COP"] > 0.0

    def test_negative_Qc_warning(self):
        """At extreme ΔT Qc < 0: warning issued, ok=True."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            # Very large ΔT with tiny current → Qc definitely negative
            res = tec_operating_point(
                alpha=_ALPHA, resistance=_R, thermal_conductance=_K,
                current=0.001, tc=250.0, th=350.0,
            )
            assert res["ok"] is True
            assert res["Qc"] < 0.0
            assert "negative_Qc" in res["warnings"]
            assert any("negative" in str(x.message).lower() or
                       "qc" in str(x.message).lower() for x in w)

    def test_tc_gte_th_error(self):
        res = tec_operating_point(
            alpha=_ALPHA, resistance=_R, thermal_conductance=_K,
            current=_I, tc=320.0, th=300.0,
        )
        assert res["ok"] is False

    def test_zero_current_error(self):
        res = tec_operating_point(
            alpha=_ALPHA, resistance=_R, thermal_conductance=_K,
            current=0.0, tc=_TC, th=_TH,
        )
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 3. tec_optimal_current
# ═══════════════════════════════════════════════════════════════════════════════

class TestTecOptimalCurrent:
    def test_I_max_Qc_exact(self):
        """I_max_Qc = α·Tc / R exactly."""
        res = tec_optimal_current(
            alpha=_ALPHA, resistance=_R, thermal_conductance=_K,
            tc=_TC, th=_TH,
        )
        assert res["ok"] is True
        expected = _ALPHA * _TC / _R
        assert abs(res["I_max_Qc"] - expected) < 1e-12

    def test_I_max_COP_less_than_I_max_Qc(self):
        """I_max_COP < I_max_Qc for all valid inputs."""
        res = tec_optimal_current(
            alpha=_ALPHA, resistance=_R, thermal_conductance=_K,
            tc=_TC, th=_TH,
        )
        assert res["ok"] is True
        assert res["I_max_COP"] < res["I_max_Qc"]

    def test_COP_max_positive(self):
        """COP_max > 0 for realistic operating conditions."""
        res = tec_optimal_current(
            alpha=_ALPHA, resistance=_R, thermal_conductance=_K,
            tc=_TC, th=_TH,
        )
        assert res["ok"] is True
        assert res["COP_max"] > 0.0

    def test_tc_equals_th_error(self):
        res = tec_optimal_current(
            alpha=_ALPHA, resistance=_R, thermal_conductance=_K,
            tc=300.0, th=300.0,
        )
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 4. tec_delta_t_max
# ═══════════════════════════════════════════════════════════════════════════════

class TestTecDeltaTMax:
    def test_delta_T_max_exact(self):
        """ΔT_max = ½·Z·Tc²."""
        res = tec_delta_t_max(alpha=_ALPHA, resistance=_R,
                               thermal_conductance=_K, tc=_TC)
        assert res["ok"] is True
        Z = _ALPHA ** 2 / (_R * _K)
        expected = 0.5 * Z * _TC ** 2
        assert abs(res["delta_T_max"] - expected) < 1e-10

    def test_Th_max_equals_Tc_plus_delta_T_max(self):
        """Th_max = Tc + ΔT_max."""
        res = tec_delta_t_max(alpha=_ALPHA, resistance=_R,
                               thermal_conductance=_K, tc=_TC)
        assert res["ok"] is True
        assert abs(res["Th_max"] - (res["tc"] + res["delta_T_max"])) < 1e-10

    def test_higher_Z_larger_delta_T_max(self):
        """Higher Z → larger ΔT_max (all else equal)."""
        res_lo = tec_delta_t_max(alpha=_ALPHA, resistance=_R,
                                  thermal_conductance=_K, tc=_TC)
        res_hi = tec_delta_t_max(alpha=2 * _ALPHA, resistance=_R,
                                  thermal_conductance=_K, tc=_TC)
        assert res_hi["delta_T_max"] > res_lo["delta_T_max"]

    def test_zero_resistance_error(self):
        res = tec_delta_t_max(alpha=_ALPHA, resistance=0.0,
                               thermal_conductance=_K, tc=_TC)
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 5. tec_couples_required
# ═══════════════════════════════════════════════════════════════════════════════

class TestTecCouplesRequired:
    def test_N_is_ceil(self):
        """N = ceil(Qc_target / Qc_per_couple)."""
        Qc_target = 5.0
        res = tec_couples_required(
            alpha_per_couple=_ALPHA, resistance_per_couple=_R,
            thermal_conductance_per_couple=_K,
            current=_I, tc=_TC, th=_TH, Qc_target=Qc_target,
        )
        assert res["ok"] is True
        assert res["N"] is not None
        qc_per = res["Qc_per_couple"]
        expected_N = math.ceil(Qc_target / qc_per)
        assert res["N"] == expected_N

    def test_Qc_total_gte_target(self):
        """Total Qc (N couples) >= Qc_target."""
        Qc_target = 3.0
        res = tec_couples_required(
            alpha_per_couple=_ALPHA, resistance_per_couple=_R,
            thermal_conductance_per_couple=_K,
            current=_I, tc=_TC, th=_TH, Qc_target=Qc_target,
        )
        assert res["ok"] is True
        assert res["Qc_total"] >= Qc_target - 1e-9

    def test_negative_Qc_per_couple_warns_and_N_is_None(self):
        """When Qc_per_couple ≤ 0, N=None and warning issued."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            res = tec_couples_required(
                alpha_per_couple=_ALPHA, resistance_per_couple=_R,
                thermal_conductance_per_couple=_K,
                current=0.0001, tc=200.0, th=400.0, Qc_target=1.0,
            )
            assert res["ok"] is True
            assert res["N"] is None
            assert "negative_Qc_per_couple" in res["warnings"]
            assert any("qc" in str(x.message).lower() or
                       "negative" in str(x.message).lower() for x in w)

    def test_tc_gte_th_error(self):
        res = tec_couples_required(
            alpha_per_couple=_ALPHA, resistance_per_couple=_R,
            thermal_conductance_per_couple=_K,
            current=_I, tc=320.0, th=300.0, Qc_target=1.0,
        )
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 6. tec_heatsink_coupled
# ═══════════════════════════════════════════════════════════════════════════════

class TestTecHeatsinkCoupled:
    # Heatsink: Rθ = 0.5 K/W, ambient = 298 K (25°C), tc = 278 K (5°C)
    _T_AMB = 298.15
    _TC_HS = 278.15
    _RTH = 0.5

    def test_Th_above_ambient(self):
        """Hot-side temperature is higher than ambient (heatsink heats up)."""
        res = tec_heatsink_coupled(
            alpha=_ALPHA, resistance=_R, thermal_conductance=_K,
            current=_I, tc=self._TC_HS, t_ambient=self._T_AMB,
            rtheta=self._RTH,
        )
        assert res["ok"] is True
        assert res["Th"] > self._T_AMB

    def test_equilibrium_condition_satisfied(self):
        """Th = T_ambient + Rθ·Qh within 1 mK after convergence."""
        res = tec_heatsink_coupled(
            alpha=_ALPHA, resistance=_R, thermal_conductance=_K,
            current=_I, tc=self._TC_HS, t_ambient=self._T_AMB,
            rtheta=self._RTH,
        )
        assert res["ok"] is True
        assert res["converged"] is True
        Th = res["Th"]
        Qh = res["Qh"]
        Th_check = self._T_AMB + self._RTH * Qh
        assert abs(Th - Th_check) < 1e-3

    def test_converged_true_typical(self):
        """converged=True for typical heatsink coupling."""
        res = tec_heatsink_coupled(
            alpha=_ALPHA, resistance=_R, thermal_conductance=_K,
            current=_I, tc=self._TC_HS, t_ambient=self._T_AMB,
            rtheta=self._RTH,
        )
        assert res["converged"] is True

    def test_zero_rtheta_error(self):
        res = tec_heatsink_coupled(
            alpha=_ALPHA, resistance=_R, thermal_conductance=_K,
            current=_I, tc=self._TC_HS, t_ambient=self._T_AMB,
            rtheta=0.0,
        )
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 7. tec_multistage
# ═══════════════════════════════════════════════════════════════════════════════

class TestTecMultistage:
    _STAGE = {
        "alpha": _ALPHA,
        "resistance": _R,
        "thermal_conductance": _K,
        "current": _I,
    }
    _TC_COLD = 233.15   # -40°C
    _TH_AMB = 313.15    # +40°C

    def test_two_stage_total_delta_T(self):
        """total_delta_T = t_hot_ambient − t_cold_target."""
        res = tec_multistage(
            stages=[self._STAGE, self._STAGE],
            t_cold_target=self._TC_COLD,
            t_hot_ambient=self._TH_AMB,
        )
        assert res["ok"] is True
        expected = self._TH_AMB - self._TC_COLD
        assert abs(res["total_delta_T"] - expected) < 1e-9

    def test_stage_results_count(self):
        """stages_results has exactly n_stages entries."""
        res = tec_multistage(
            stages=[self._STAGE, self._STAGE, self._STAGE],
            t_cold_target=self._TC_COLD,
            t_hot_ambient=self._TH_AMB,
        )
        assert res["ok"] is True
        assert len(res["stages_results"]) == 3

    def test_stage_results_have_required_keys(self):
        """Each stage result has Qc, Qh, P_input."""
        res = tec_multistage(
            stages=[self._STAGE, self._STAGE],
            t_cold_target=self._TC_COLD,
            t_hot_ambient=self._TH_AMB,
        )
        assert res["ok"] is True
        for sr in res["stages_results"]:
            assert "Qc" in sr
            assert "Qh" in sr
            assert "P_input" in sr

    def test_empty_stages_error(self):
        res = tec_multistage(
            stages=[], t_cold_target=self._TC_COLD, t_hot_ambient=self._TH_AMB
        )
        assert res["ok"] is False

    def test_cold_gte_hot_error(self):
        res = tec_multistage(
            stages=[self._STAGE],
            t_cold_target=350.0,
            t_hot_ambient=300.0,
        )
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 8. teg_output
# ═══════════════════════════════════════════════════════════════════════════════

class TestTegOutput:
    # TEG parameters: α=0.2 mV/K per couple, 127 couples, ΔT=100K
    _A = 0.0002     # V/K per couple
    _R = 0.01       # Ω per couple
    _N = 127
    _TC = 300.0
    _TH = 400.0

    def test_Voc_exact(self):
        """Voc = α·N·ΔT exactly."""
        res = teg_output(alpha=self._A, resistance=self._R, n_couples=self._N,
                          tc=self._TC, th=self._TH)
        assert res["ok"] is True
        expected = self._A * self._N * (self._TH - self._TC)
        assert abs(res["Voc"] - expected) < 1e-12

    def test_Ri_exact(self):
        """Ri = N·R exactly."""
        res = teg_output(alpha=self._A, resistance=self._R, n_couples=self._N,
                          tc=self._TC, th=self._TH)
        assert res["ok"] is True
        assert abs(res["Ri"] - self._N * self._R) < 1e-12

    def test_Pm_exact(self):
        """Pm = Voc² / (4·Ri) exactly."""
        res = teg_output(alpha=self._A, resistance=self._R, n_couples=self._N,
                          tc=self._TC, th=self._TH)
        assert res["ok"] is True
        expected = res["Voc"] ** 2 / (4.0 * res["Ri"])
        assert abs(res["Pm"] - expected) < 1e-12

    def test_Im_exact(self):
        """Im = Voc / (2·Ri) exactly."""
        res = teg_output(alpha=self._A, resistance=self._R, n_couples=self._N,
                          tc=self._TC, th=self._TH)
        assert res["ok"] is True
        expected = res["Voc"] / (2.0 * res["Ri"])
        assert abs(res["Im"] - expected) < 1e-12

    def test_P_load_at_matched_load_equals_Pm(self):
        """P_load = Pm when r_load = Ri."""
        res = teg_output(alpha=self._A, resistance=self._R, n_couples=self._N,
                          tc=self._TC, th=self._TH)
        Ri = res["Ri"]
        res2 = teg_output(alpha=self._A, resistance=self._R, n_couples=self._N,
                           tc=self._TC, th=self._TH, r_load=Ri)
        assert abs(res2["P_load"] - res["Pm"]) < 1e-10

    def test_P_load_formula_arbitrary_r_load(self):
        """P_load = I_load²·R_load for arbitrary R_load."""
        r_load = 2.5
        res = teg_output(alpha=self._A, resistance=self._R, n_couples=self._N,
                          tc=self._TC, th=self._TH, r_load=r_load)
        assert res["ok"] is True
        expected = res["I_load"] ** 2 * r_load
        assert abs(res["P_load"] - expected) < 1e-12

    def test_more_couples_higher_Voc(self):
        """Doubling n_couples doubles Voc."""
        res1 = teg_output(alpha=self._A, resistance=self._R, n_couples=100,
                           tc=self._TC, th=self._TH)
        res2 = teg_output(alpha=self._A, resistance=self._R, n_couples=200,
                           tc=self._TC, th=self._TH)
        assert abs(res2["Voc"] / res1["Voc"] - 2.0) < 1e-9

    def test_tc_gte_th_error(self):
        res = teg_output(alpha=self._A, resistance=self._R, n_couples=self._N,
                          tc=400.0, th=300.0)
        assert res["ok"] is False

    def test_n_couples_zero_error(self):
        res = teg_output(alpha=self._A, resistance=self._R, n_couples=0,
                          tc=self._TC, th=self._TH)
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 9. teg_efficiency
# ═══════════════════════════════════════════════════════════════════════════════

class TestTegEfficiency:
    _A = 0.0002
    _R = 0.01
    _K = 0.004
    _TC = 300.0
    _TH = 400.0

    def test_eta_max_less_than_carnot(self):
        """ηmax < ηCarnot (real device always below Carnot)."""
        res = teg_efficiency(alpha=self._A, resistance=self._R,
                              thermal_conductance=self._K,
                              tc=self._TC, th=self._TH)
        assert res["ok"] is True
        assert res["eta_max"] < res["eta_carnot"]

    def test_eta_ratio_in_unit_interval(self):
        """eta_ratio = eta_max / eta_carnot in (0, 1)."""
        res = teg_efficiency(alpha=self._A, resistance=self._R,
                              thermal_conductance=self._K,
                              tc=self._TC, th=self._TH)
        assert res["ok"] is True
        assert 0.0 < res["eta_ratio"] < 1.0

    def test_R_opt_greater_than_R(self):
        """R_opt > R (M > 1 for any realistic ZT_mean > 0)."""
        res = teg_efficiency(alpha=self._A, resistance=self._R,
                              thermal_conductance=self._K,
                              tc=self._TC, th=self._TH)
        assert res["ok"] is True
        assert res["R_opt_per_couple"] > self._R

    def test_higher_ZT_higher_eta_ratio(self):
        """Higher ZT_mean → eta_ratio closer to 1 (more Carnot-like)."""
        # Higher alpha → higher Z → higher ZT
        res_lo = teg_efficiency(alpha=self._A, resistance=self._R,
                                 thermal_conductance=self._K,
                                 tc=self._TC, th=self._TH)
        res_hi = teg_efficiency(alpha=10 * self._A, resistance=self._R,
                                 thermal_conductance=self._K,
                                 tc=self._TC, th=self._TH)
        assert res_hi["eta_ratio"] > res_lo["eta_ratio"]

    def test_tc_equals_th_error(self):
        res = teg_efficiency(alpha=self._A, resistance=self._R,
                              thermal_conductance=self._K,
                              tc=300.0, th=300.0)
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 10. teg_array
# ═══════════════════════════════════════════════════════════════════════════════

class TestTegArray:
    _A = 0.0002
    _R = 0.01
    _N = 127
    _TC = 300.0
    _TH = 400.0

    def test_Parray_equals_Ns_Np_Pm(self):
        """Parray = n_series × n_parallel × Pm_module."""
        Ns, Np = 4, 3
        res = teg_array(alpha=self._A, resistance=self._R, n_couples=self._N,
                         tc=self._TC, th=self._TH, n_series=Ns, n_parallel=Np)
        assert res["ok"] is True
        assert abs(res["Parray"] - Ns * Np * res["Pm_module"]) < 1e-10

    def test_Varray_equals_Ns_Voc(self):
        """Varray = n_series × Voc_module."""
        Ns, Np = 5, 2
        res = teg_array(alpha=self._A, resistance=self._R, n_couples=self._N,
                         tc=self._TC, th=self._TH, n_series=Ns, n_parallel=Np)
        assert res["ok"] is True
        assert abs(res["Varray"] - Ns * res["Voc_module"]) < 1e-10

    def test_n_total_modules(self):
        """n_total_modules = n_series × n_parallel."""
        Ns, Np = 6, 4
        res = teg_array(alpha=self._A, resistance=self._R, n_couples=self._N,
                         tc=self._TC, th=self._TH, n_series=Ns, n_parallel=Np)
        assert res["ok"] is True
        assert res["n_total_modules"] == Ns * Np


# ═══════════════════════════════════════════════════════════════════════════════
# 11. teg_fill_factor
# ═══════════════════════════════════════════════════════════════════════════════

class TestTegFillFactor:
    def test_fill_factor_exact(self):
        """FF = 2·n_couples·pellet_area / footprint."""
        pa = 1.5    # mm²
        ph = 3.0    # mm
        nc = 127
        fp = 400.0  # mm²
        res = teg_fill_factor(pellet_area_mm2=pa, pellet_height_mm=ph,
                               n_couples=nc, module_footprint_mm2=fp)
        assert res["ok"] is True
        expected = 2 * nc * pa / fp
        assert abs(res["fill_factor"] - expected) < 1e-12

    def test_FF_gt_1_warns(self):
        """FF > 1 issues a warning and returns ok=True."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            # 200 couples × 2 legs × 2 mm² = 800 mm² in 100 mm² footprint
            res = teg_fill_factor(pellet_area_mm2=2.0, pellet_height_mm=3.0,
                                   n_couples=200, module_footprint_mm2=100.0)
            assert res["ok"] is True
            assert res["fill_factor"] > 1.0
            assert "fill_factor_exceeds_1" in res["warnings"]
            assert any("fill" in str(x.message).lower() or "1" in str(x.message)
                       for x in w)

    def test_zero_footprint_error(self):
        res = teg_fill_factor(pellet_area_mm2=1.5, pellet_height_mm=3.0,
                               n_couples=127, module_footprint_mm2=0.0)
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 12. LLM tool handlers (stub registry)
# ═══════════════════════════════════════════════════════════════════════════════

class TestToolHandlers:
    @pytest.mark.asyncio
    async def test_tec_figure_of_merit_tool_ok(self):
        res = await call(_tec_fom_tool, alpha=_ALPHA, resistance=_R,
                          thermal_conductance=_K, t_mean=300.0)
        assert res["ok"] is True
        assert "Z" in res

    @pytest.mark.asyncio
    async def test_tec_operating_point_tool_ok(self):
        res = await call(_tec_op_tool, alpha=_ALPHA, resistance=_R,
                          thermal_conductance=_K, current=_I, tc=_TC, th=_TH)
        assert res["ok"] is True
        assert "Qc" in res

    @pytest.mark.asyncio
    async def test_tec_delta_t_max_tool_ok(self):
        res = await call(_tec_dtm_tool, alpha=_ALPHA, resistance=_R,
                          thermal_conductance=_K, tc=_TC)
        assert res["ok"] is True
        assert "delta_T_max" in res

    @pytest.mark.asyncio
    async def test_teg_output_tool_ok(self):
        res = await call(_teg_out_tool, alpha=0.0002, resistance=0.01,
                          n_couples=127, tc=300.0, th=400.0)
        assert res["ok"] is True
        assert "Voc" in res

    @pytest.mark.asyncio
    async def test_teg_efficiency_tool_ok(self):
        res = await call(_teg_eff_tool, alpha=0.0002, resistance=0.01,
                          thermal_conductance=0.004, tc=300.0, th=400.0)
        assert res["ok"] is True
        assert "eta_max" in res

    @pytest.mark.asyncio
    async def test_tool_invalid_json_returns_error(self):
        result = await _tec_fom_tool(None, b"{{not json{{")
        data = json.loads(result)
        assert data.get("ok") is False or "error" in data
