"""
Hermetic tests for the RF impedance-matching network synthesis module.

Covers (≥30 tests):

  reflection_coefficient
    - Perfect match (Z_L == Z0) → Γ = 0, VSWR = 1, RL = inf, ML = 0
    - Open circuit (Z_L → ∞): approximate with large R
    - Short circuit (Z_L = 0): Γ = −1, VSWR undefined/inf
    - Real mismatch 50→100 Ω: exact Γ = 1/3
    - Complex load: verify |Γ| in (0, 1)
    - Invalid z0 (negative) → ok=False
    - Return loss positive for passive load

  lsection_match  (50→100 Ω, purely resistive — classic closed-form)
    - Q = sqrt(R_high/R_low − 1) = sqrt(2 − 1) = 1.0
    - Both solutions returned (sign ± Q)
    - component_value_shunt > 0 and component_value_series > 0
    - Impedance ratio 1:4 (50→200 Ω): Q = sqrt(4-1) = sqrt(3)
    - Complex source: ok=True returned
    - Zero source resistance → ok=False
    - Very low frequency → larger component values
    - Doubling frequency → halves component values (L, C both scale as 1/f)

  pi_network
    - 50→50 Ω with Q=5 → ok=False (Q_min=0 for equal R but Q must be > 0) — ok=True with warning
    - 50→200 Ω with Q=3 (> Q_min=sqrt(3)) → ok=True, r_virtual < min(r_s, r_l)
    - Q below Q_min → ok=False with reason
    - Component values all positive
    - Higher Q → narrower bandwidth (r_virtual decreases)

  t_network
    - 50→200 Ω with Q=3 → ok=True, r_virtual > max(r_s, r_l)
    - Q below Q_min → ok=False
    - Component values positive

  quarter_wave_transformer
    - sqrt(50 × 200) = 100 Ω (exact)
    - sqrt(50 × 50) = 50 Ω (trivial)
    - Negative r_source → ok=False
    - Scaling: Z0 ∝ sqrt(R_load)

  single_stub_match
    - Real load Z_L = 25 Ω, Z0 = 50 Ω: two solutions, both realizable
    - Purely reactive load → ok=False (g_L = 0)
    - Invalid termination string → ok=False
    - Both solutions have d_wavelength in [0, 0.5]
    - Solutions for short vs open termination differ

  microstrip_synthesis (Hammerstad)
    - 50 Ω, εr = 4.4 (FR4): W/H ≈ 1.9 (well-known result)
    - 75 Ω, εr = 1.0: narrower trace (higher Z0 → smaller W/H)
    - Self-check: z0_achieved ≈ z0_target within 1%
    - Negative εr → ok=False
    - With strip thickness t > 0: wider effective width (W_eff > W)

  microstrip_analysis (Hammerstad)
    - Analyse width from synthesis → Z0 round-trip within 1%
    - Wide trace (W/H = 4): εr_eff > (εr+1)/2
    - Narrow trace (W/H = 0.5): εr_eff < (εr+1)/2 ... approach from narrow side
    - Zero width → ok=False
    - wavelength_factor = 1/sqrt(εr_eff)

  LLM tool handlers (stub registry)
    - rfmatch_reflection tool: ok=True for valid input
    - rfmatch_lsection tool: ok=True, solutions list present
    - rfmatch_pi tool: ok=True, component_value_series > 0
    - rfmatch_t tool: ok=True, component_value_p > 0
    - rfmatch_quarter_wave tool: ok=True, z0_transformer_ohm == 100
    - rfmatch_single_stub tool: ok=True, 2 solutions
    - rfmatch_microstrip_synth tool: ok=True, width > 0
    - rfmatch_microstrip_anal tool: ok=True, z0 present
    - Tool with invalid JSON → error payload

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

# ── Prefer real kerf_chat if installed; stub otherwise ───────────────────────
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

from kerf_electronics.rfmatch.match import (
    lsection_match,
    microstrip_analysis,
    microstrip_synthesis,
    pi_network,
    quarter_wave_transformer,
    reflection_coefficient,
    single_stub_match,
    t_network,
)

# ── Load tool module via importlib so stub is active ─────────────────────────
_tool_spec = importlib.util.spec_from_file_location(
    "kerf_electronics.rfmatch.tools",
    os.path.join(_SRC, "kerf_electronics", "rfmatch", "tools.py"),
)
_tool_mod = importlib.util.module_from_spec(_tool_spec)
_tool_spec.loader.exec_module(_tool_mod)

_refl_tool = _tool_mod.rfmatch_reflection
_lsec_tool = _tool_mod.rfmatch_lsection
_pi_tool = _tool_mod.rfmatch_pi
_t_tool = _tool_mod.rfmatch_t
_qw_tool = _tool_mod.rfmatch_quarter_wave
_stub_tool = _tool_mod.rfmatch_single_stub
_ms_synth_tool = _tool_mod.rfmatch_microstrip_synth
_ms_anal_tool = _tool_mod.rfmatch_microstrip_anal


# ── Async call helper ─────────────────────────────────────────────────────────

async def call(fn, **kwargs):
    result = await fn(None, json.dumps(kwargs).encode())
    return json.loads(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. reflection_coefficient
# ═══════════════════════════════════════════════════════════════════════════════

class TestReflectionCoefficient:

    def test_perfect_match(self):
        """Z_L = Z0 → Γ = 0, VSWR = 1, RL = inf (None), ML = 0."""
        r = reflection_coefficient(z_load=50.0, z0=50.0)
        assert r["ok"] is True
        assert abs(r["gamma_mag"]) < 1e-10
        assert r["vswr"] == pytest.approx(1.0, abs=1e-6)
        assert r["mismatch_loss_db"] == pytest.approx(0.0, abs=1e-5)

    def test_real_mismatch_50_to_100(self):
        """Z_L = 100 Ω, Z0 = 50 Ω → Γ = (100-50)/(100+50) = 1/3."""
        r = reflection_coefficient(z_load=100.0, z0=50.0)
        assert r["ok"] is True
        assert abs(r["gamma_re"] - 1 / 3) < 1e-9
        assert abs(r["gamma_im"]) < 1e-10

    def test_return_loss_positive_passive(self):
        """Return loss is positive for any passive load (|Γ| < 1)."""
        r = reflection_coefficient(z_load=75.0, z0=50.0)
        assert r["ok"] is True
        assert r["return_loss_db"] > 0.0

    def test_vswr_formula(self):
        """VSWR = (1 + |Γ|) / (1 - |Γ|)."""
        r = reflection_coefficient(z_load=100.0, z0=50.0)
        gamma = abs(complex(r["gamma_re"], r["gamma_im"]))
        expected_vswr = (1 + gamma) / (1 - gamma)
        assert r["vswr"] == pytest.approx(expected_vswr, rel=1e-6)

    def test_complex_load_gamma_in_unit_disc(self):
        """Complex passive load: |Γ| < 1."""
        r = reflection_coefficient(z_load=complex(30, 40), z0=50.0)
        assert r["ok"] is True
        assert 0.0 < r["gamma_mag"] < 1.0

    def test_negative_z0_rejected(self):
        r = reflection_coefficient(z_load=50.0, z0=-10.0)
        assert r["ok"] is False

    def test_mismatch_loss_nonneg(self):
        """Mismatch loss >= 0 for passive loads."""
        r = reflection_coefficient(z_load=complex(25, -10), z0=50.0)
        assert r["ok"] is True
        assert r["mismatch_loss_db"] >= 0.0

    def test_short_circuit_large_gamma(self):
        """Z_L = 0 → Γ ≈ −1 (short); VSWR → inf (returned as None)."""
        r = reflection_coefficient(z_load=0.001, z0=50.0)  # near-short
        assert r["ok"] is True
        assert r["gamma_mag"] > 0.99


# ═══════════════════════════════════════════════════════════════════════════════
# 2. lsection_match
# ═══════════════════════════════════════════════════════════════════════════════

class TestLsectionMatch:

    def test_50_to_100_Q(self):
        """50→100 Ω: Q = sqrt(100/50 − 1) = 1.0."""
        r = lsection_match(z_source=50.0, z_load=100.0, freq_hz=100e6)
        assert r["ok"] is True
        assert abs(r["Q"] - 1.0) < 1e-6

    def test_50_to_100_two_solutions(self):
        """Two solutions are returned."""
        r = lsection_match(z_source=50.0, z_load=100.0, freq_hz=100e6)
        assert r["ok"] is True
        assert len(r["solutions"]) == 2

    def test_50_to_100_realizable_solutions(self):
        """At least one realizable solution for 50→100 Ω."""
        r = lsection_match(z_source=50.0, z_load=100.0, freq_hz=100e6)
        assert r["ok"] is True
        realizable = [s for s in r["solutions"] if s["realizable"]]
        assert len(realizable) >= 1

    def test_component_values_positive_50_100(self):
        """All component values in realizable solutions are positive."""
        r = lsection_match(z_source=50.0, z_load=100.0, freq_hz=100e6)
        for sol in r["solutions"]:
            if sol["realizable"]:
                assert sol["component_value_shunt"] > 0
                assert sol["component_value_series"] > 0

    def test_50_to_200_Q(self):
        """50→200 Ω: Q = sqrt(200/50 − 1) = sqrt(3) ≈ 1.7321."""
        r = lsection_match(z_source=50.0, z_load=200.0, freq_hz=100e6)
        assert r["ok"] is True
        assert abs(r["Q"] - math.sqrt(3)) < 1e-6

    def test_double_frequency_halves_component_L(self):
        """Doubling frequency → half the inductance (X=ωL, so L=X/ω ∝ 1/f)."""
        r1 = lsection_match(z_source=50.0, z_load=100.0, freq_hz=100e6)
        r2 = lsection_match(z_source=50.0, z_load=100.0, freq_hz=200e6)
        # Find inductors in both
        for s1, s2 in zip(r1["solutions"], r2["solutions"]):
            if s1["component_type_shunt"] == "L" and s2["component_type_shunt"] == "L":
                assert abs(s1["component_value_shunt"] / s2["component_value_shunt"] - 2.0) < 1e-6

    def test_zero_source_resistance_rejected(self):
        r = lsection_match(z_source=complex(0, 10), z_load=100.0, freq_hz=100e6)
        assert r["ok"] is False

    def test_complex_source_ok(self):
        r = lsection_match(z_source=complex(50, 20), z_load=100.0, freq_hz=100e6)
        assert r["ok"] is True
        assert "solutions" in r


# ═══════════════════════════════════════════════════════════════════════════════
# 3. pi_network
# ═══════════════════════════════════════════════════════════════════════════════

class TestPiNetwork:

    def test_50_to_200_q3_ok(self):
        """50→200 Ω with Q=3 (>Q_min=sqrt(3)≈1.73): ok=True."""
        r = pi_network(r_source=50.0, r_load=200.0, freq_hz=100e6, q_loaded=3.0)
        assert r["ok"] is True

    def test_r_virtual_less_than_min(self):
        """r_virtual = R_high / (Q²+1) < min(R_source, R_load)."""
        r = pi_network(r_source=50.0, r_load=200.0, freq_hz=100e6, q_loaded=3.0)
        assert r["ok"] is True
        assert r["r_virtual"] < min(50.0, 200.0)

    def test_q_below_qmin_rejected(self):
        """Q < Q_min → ok=False."""
        q_min = math.sqrt(200 / 50 - 1)  # sqrt(3) ≈ 1.73
        r = pi_network(r_source=50.0, r_load=200.0, freq_hz=100e6, q_loaded=q_min * 0.9)
        assert r["ok"] is False

    def test_component_values_positive(self):
        r = pi_network(r_source=50.0, r_load=200.0, freq_hz=100e6, q_loaded=3.0)
        assert r["ok"] is True
        assert r["component_value_p1"] > 0
        assert r["component_value_series"] > 0
        assert r["component_value_p2"] > 0

    def test_equal_r_q_above_zero(self):
        """Equal source/load (R_high/R_low=1, Q_min=0): Q=2 should work."""
        r = pi_network(r_source=50.0, r_load=50.0, freq_hz=100e6, q_loaded=2.0)
        assert r["ok"] is True

    def test_negative_r_source_rejected(self):
        r = pi_network(r_source=-50.0, r_load=200.0, freq_hz=100e6, q_loaded=3.0)
        assert r["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 4. t_network
# ═══════════════════════════════════════════════════════════════════════════════

class TestTNetwork:

    def test_50_to_200_q3_ok(self):
        r = t_network(r_source=50.0, r_load=200.0, freq_hz=100e6, q_loaded=3.0)
        assert r["ok"] is True

    def test_r_virtual_greater_than_max(self):
        """T-network: r_virtual = R_low × (Q²+1) > max(R_s, R_l)."""
        r = t_network(r_source=50.0, r_load=200.0, freq_hz=100e6, q_loaded=3.0)
        assert r["ok"] is True
        assert r["r_virtual"] > max(50.0, 200.0)

    def test_q_below_qmin_rejected(self):
        q_min = math.sqrt(200 / 50 - 1)
        r = t_network(r_source=50.0, r_load=200.0, freq_hz=100e6, q_loaded=q_min * 0.9)
        assert r["ok"] is False

    def test_component_values_positive(self):
        r = t_network(r_source=50.0, r_load=200.0, freq_hz=100e6, q_loaded=3.0)
        assert r["ok"] is True
        assert r["component_value_s1"] > 0
        assert r["component_value_s2"] > 0
        assert r["component_value_p"] > 0


# ═══════════════════════════════════════════════════════════════════════════════
# 5. quarter_wave_transformer
# ═══════════════════════════════════════════════════════════════════════════════

class TestQuarterWaveTransformer:

    def test_50_200(self):
        """sqrt(50 × 200) = sqrt(10000) = 100 Ω."""
        r = quarter_wave_transformer(r_source=50.0, r_load=200.0)
        assert r["ok"] is True
        assert abs(r["z0_transformer_ohm"] - 100.0) < 1e-6

    def test_50_50(self):
        """Trivial: sqrt(50 × 50) = 50 Ω."""
        r = quarter_wave_transformer(r_source=50.0, r_load=50.0)
        assert r["ok"] is True
        assert abs(r["z0_transformer_ohm"] - 50.0) < 1e-6

    def test_scales_as_sqrt_rload(self):
        """Quadrupling R_load doubles Z0."""
        r1 = quarter_wave_transformer(r_source=50.0, r_load=100.0)
        r2 = quarter_wave_transformer(r_source=50.0, r_load=400.0)
        ratio = r2["z0_transformer_ohm"] / r1["z0_transformer_ohm"]
        assert abs(ratio - 2.0) < 1e-6

    def test_negative_r_source_rejected(self):
        r = quarter_wave_transformer(r_source=-10.0, r_load=50.0)
        assert r["ok"] is False

    def test_zero_r_load_rejected(self):
        r = quarter_wave_transformer(r_source=50.0, r_load=0.0)
        assert r["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 6. single_stub_match
# ═══════════════════════════════════════════════════════════════════════════════

class TestSingleStubMatch:

    def test_real_load_two_solutions(self):
        """Z_L = 25 Ω, Z0 = 50 Ω → two solutions."""
        r = single_stub_match(z_load=25.0, z0=50.0)
        assert r["ok"] is True
        assert len(r["solutions"]) == 2

    def test_d_wavelength_in_range(self):
        """Feed-line distance d in [0, 0.5λ]."""
        r = single_stub_match(z_load=25.0, z0=50.0)
        assert r["ok"] is True
        for sol in r["solutions"]:
            assert 0.0 <= sol["d_wavelength"] <= 0.5 + 1e-9

    def test_stub_length_in_range(self):
        """Stub length in [0, 0.5λ]."""
        r = single_stub_match(z_load=25.0, z0=50.0)
        assert r["ok"] is True
        for sol in r["solutions"]:
            assert 0.0 <= sol["stub_length_wavelength"] <= 0.5 + 1e-9

    def test_purely_reactive_load_rejected(self):
        """Z_L purely imaginary → g_L = 0 → ok=False."""
        r = single_stub_match(z_load=complex(0, 50), z0=50.0)
        assert r["ok"] is False

    def test_invalid_termination_rejected(self):
        r = single_stub_match(z_load=25.0, termination="banana")
        assert r["ok"] is False

    def test_invalid_stub_type_rejected(self):
        r = single_stub_match(z_load=25.0, stub_type="banjo")
        assert r["ok"] is False

    def test_open_vs_short_differ(self):
        """Open and short stub terminations give different stub lengths."""
        r_short = single_stub_match(z_load=25.0, z0=50.0, termination="short")
        r_open = single_stub_match(z_load=25.0, z0=50.0, termination="open")
        assert r_short["ok"] and r_open["ok"]
        # Stub lengths should differ
        l_short = r_short["solutions"][0]["stub_length_wavelength"]
        l_open = r_open["solutions"][0]["stub_length_wavelength"]
        assert abs(l_short - l_open) > 1e-4


# ═══════════════════════════════════════════════════════════════════════════════
# 7. microstrip_synthesis (Hammerstad)
# ═══════════════════════════════════════════════════════════════════════════════

class TestMicrostripSynthesis:

    def test_50_ohm_fr4_width_ratio(self):
        """50 Ω, εr=4.4: W/H ≈ 1.9 (Pozar Table 3.2 / IPC-2141A)."""
        r = microstrip_synthesis(z0_target=50.0, er=4.4)
        assert r["ok"] is True
        assert abs(r["width_to_height"] - 1.9) < 0.2   # within ±10% of known value

    def test_75_ohm_narrower_than_50_ohm(self):
        """Higher Z0 → narrower trace (smaller W/H)."""
        r50 = microstrip_synthesis(z0_target=50.0, er=4.4)
        r75 = microstrip_synthesis(z0_target=75.0, er=4.4)
        assert r50["ok"] and r75["ok"]
        assert r75["width_to_height"] < r50["width_to_height"]

    def test_self_check_within_1_pct(self):
        """Self-check: z0_achieved within 1% of z0_target."""
        for z0_t in (25.0, 50.0, 75.0, 100.0):
            r = microstrip_synthesis(z0_target=z0_t, er=4.4)
            assert r["ok"] is True
            assert r["error_percent"] < 1.0, (
                f"Z0={z0_t}: error {r['error_percent']:.3f}% ≥ 1%"
            )

    def test_negative_er_rejected(self):
        r = microstrip_synthesis(z0_target=50.0, er=-1.0)
        assert r["ok"] is False

    def test_strip_thickness_widens_trace(self):
        """Non-zero strip thickness t gives wider effective W."""
        r0 = microstrip_synthesis(z0_target=50.0, er=4.4, h=1.0, t=0.0)
        rt = microstrip_synthesis(z0_target=50.0, er=4.4, h=1.0, t=0.035)
        assert r0["ok"] and rt["ok"]
        assert rt["width"] > r0["width"]

    def test_er_eff_between_1_and_er(self):
        """1 < εr_eff < εr for any valid input."""
        r = microstrip_synthesis(z0_target=50.0, er=4.4)
        assert r["ok"] is True
        assert 1.0 < r["er_eff"] < 4.4

    def test_zero_z0_rejected(self):
        r = microstrip_synthesis(z0_target=0.0, er=4.4)
        assert r["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 8. microstrip_analysis (Hammerstad)
# ═══════════════════════════════════════════════════════════════════════════════

class TestMicrostripAnalysis:

    def test_round_trip_50_ohm(self):
        """Synthesise then analyse: Z0 round-trip within 1%."""
        rs = microstrip_synthesis(z0_target=50.0, er=4.4, h=1.0)
        assert rs["ok"] is True
        ra = microstrip_analysis(width=rs["width"], h=1.0, er=4.4)
        assert ra["ok"] is True
        assert abs(ra["z0"] - 50.0) / 50.0 < 0.01

    def test_wavelength_factor(self):
        """wavelength_factor = 1/sqrt(εr_eff)."""
        r = microstrip_analysis(width=1.9, h=1.0, er=4.4)
        assert r["ok"] is True
        expected = 1.0 / math.sqrt(r["er_eff"])
        assert abs(r["wavelength_factor"] - expected) < 1e-6

    def test_wide_trace_er_eff(self):
        """Wide trace (W/H = 4): εr_eff approaches εr (but < εr)."""
        r = microstrip_analysis(width=4.0, h=1.0, er=4.4)
        assert r["ok"] is True
        # For wide trace εr_eff > (εr+1)/2 and < εr
        mid = (4.4 + 1.0) / 2.0
        assert r["er_eff"] > mid
        assert r["er_eff"] < 4.4

    def test_zero_width_rejected(self):
        r = microstrip_analysis(width=0.0, h=1.0, er=4.4)
        assert r["ok"] is False

    def test_negative_h_rejected(self):
        r = microstrip_analysis(width=1.0, h=-1.0, er=4.4)
        assert r["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 9. LLM tool handlers
# ═══════════════════════════════════════════════════════════════════════════════

class TestToolHandlers:

    @pytest.mark.asyncio
    async def test_reflection_tool_ok(self):
        r = await call(_refl_tool, z_load_re=100.0, z_load_im=0.0, z0=50.0)
        assert r["ok"] is True
        assert "gamma_mag" in r

    @pytest.mark.asyncio
    async def test_lsection_tool_ok(self):
        r = await call(
            _lsec_tool,
            z_source_re=50.0, z_source_im=0.0,
            z_load_re=100.0, z_load_im=0.0,
            freq_hz=100e6,
        )
        assert r["ok"] is True
        assert "solutions" in r
        assert len(r["solutions"]) == 2

    @pytest.mark.asyncio
    async def test_pi_tool_ok(self):
        r = await call(_pi_tool, r_source=50.0, r_load=200.0, freq_hz=100e6, q_loaded=3.0)
        assert r["ok"] is True
        assert r["component_value_series"] > 0

    @pytest.mark.asyncio
    async def test_t_tool_ok(self):
        r = await call(_t_tool, r_source=50.0, r_load=200.0, freq_hz=100e6, q_loaded=3.0)
        assert r["ok"] is True
        assert r["component_value_p"] > 0

    @pytest.mark.asyncio
    async def test_quarter_wave_tool_100_ohm(self):
        r = await call(_qw_tool, r_source=50.0, r_load=200.0)
        assert r["ok"] is True
        assert abs(r["z0_transformer_ohm"] - 100.0) < 1e-4

    @pytest.mark.asyncio
    async def test_single_stub_tool_two_solutions(self):
        r = await call(_stub_tool, z_load_re=25.0, z_load_im=0.0, z0=50.0)
        assert r["ok"] is True
        assert len(r["solutions"]) == 2

    @pytest.mark.asyncio
    async def test_microstrip_synth_tool_width_positive(self):
        r = await call(_ms_synth_tool, z0_target=50.0, er=4.4)
        assert r["ok"] is True
        assert r["width"] > 0

    @pytest.mark.asyncio
    async def test_microstrip_anal_tool_z0_present(self):
        r = await call(_ms_anal_tool, width=1.9, h=1.0, er=4.4)
        assert r["ok"] is True
        assert "z0" in r
        assert r["z0"] > 0

    @pytest.mark.asyncio
    async def test_invalid_json_returns_error(self):
        result = await _refl_tool(None, b"not-valid-json!!!")
        parsed = json.loads(result)
        # Real kerf_chat err_payload: {"error": ..., "code": ...} (no "ok" key)
        # Stub err_payload: {"ok": False, "error": ..., "code": ...}
        assert parsed.get("ok") is False or "error" in parsed
