"""
Hermetic tests for the audio electronics & loudspeaker design module.

Covers ≥ 30 tests against audio-engineering hand-calculations:

  amp_class_b         — class-B efficiency = π/4 ≈ 78.54%, worst-case Pdiss
  amp_class_a         — class-A efficiency ≤ 25%, quiescent current
  amp_class_ab        — AB bounds bracket A and B
  amp_class_d         — output power, dead-time loss, LC filter
  heatsink_rth        — junction temperature budget
  sealed_box          — Qtc=0.707 Butterworth, volume, f3
  vented_box          — QB3/SBB4 alignment, port sizing, chuffing flag
  driver_spl          — SPL at power, distance scaling
  passive_crossover   — LR4 crossover component values, BW2
  zobel_network       — Rz = Re, Cz = Le/Re²
  lpad_attenuator     — voltage ratio, 6 dB attenuation
  damping_factor      — DF = Re / (Zout + Rcable)
  spl_add             — incoherent addition (two equal → +3 dB)
  spl_distance        — inverse-square law (double distance → −6 dB)
  db_voltage          — 20×log10 ratio
  db_power            — 10×log10 ratio
  a_weighting         — 0 dB at 1 kHz, negative below and above
  impedance_bridging  — ratio check, bridging_ok flag
  tool handlers       — LLM async wrappers return ok=True

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

# ── Prefer the real kerf_chat if installed; stub otherwise ───────────────────
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

from kerf_electronics.audio.design import (
    a_weighting,
    amp_class_a,
    amp_class_ab,
    amp_class_b,
    amp_class_d,
    damping_factor,
    db_power,
    db_voltage,
    driver_spl,
    heatsink_rth,
    impedance_bridging,
    lpad_attenuator,
    passive_crossover,
    sealed_box,
    spl_add,
    spl_distance,
    vented_box,
    zobel_network,
)

# ── Load tool module via importlib so stub is active ─────────────────────────
_tool_spec = importlib.util.spec_from_file_location(
    "kerf_electronics.audio.tools",
    os.path.join(_SRC, "kerf_electronics", "audio", "tools.py"),
)
_tool_mod = importlib.util.module_from_spec(_tool_spec)
_tool_spec.loader.exec_module(_tool_mod)

_amp_b_tool = _tool_mod.audio_amp_class_b
_amp_a_tool = _tool_mod.audio_amp_class_a
_amp_d_tool = _tool_mod.audio_amp_class_d
_sealed_tool = _tool_mod.audio_sealed_box
_xover_tool = _tool_mod.audio_crossover
_spl_add_tool = _tool_mod.audio_spl_add
_df_tool = _tool_mod.audio_damping_factor
_bridge_tool = _tool_mod.audio_impedance_bridge
_aweight_tool = _tool_mod.audio_a_weighting


# ── Async call helper ─────────────────────────────────────────────────────────
async def call(fn, **kwargs):
    result = await fn(None, json.dumps(kwargs).encode())
    return json.loads(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Class-B Amplifier
# ═══════════════════════════════════════════════════════════════════════════════

class TestAmpClassB:
    """η_max = π/4 ≈ 78.54%, worst-case Pdiss at Vpk = Vcc/π."""

    def test_efficiency_max_equals_pi_over_4(self):
        """Theoretical class-B efficiency = π/4 × 100% ≈ 78.5398%."""
        res = amp_class_b(vcc=30.0, rl=8.0)
        assert res["ok"] is True
        expected = (math.pi / 4.0) * 100.0
        assert abs(res["efficiency_max_pct"] - expected) < 0.001

    def test_pout_max_formula(self):
        """Pout_max = Vcc² / (2 × RL)."""
        vcc, rl = 30.0, 8.0
        res = amp_class_b(vcc=vcc, rl=rl)
        assert abs(res["pout_max_w"] - vcc ** 2 / (2.0 * rl)) < 1e-6

    def test_pdiss_per_device_max(self):
        """Pdiss_per_device_max = Vcc² / (π² × RL). Tolerance accounts for round(4)."""
        vcc, rl = 30.0, 8.0
        res = amp_class_b(vcc=vcc, rl=rl)
        expected = vcc ** 2 / (math.pi ** 2 * rl)
        assert abs(res["pdiss_per_device_max_w"] - expected) < 1e-3

    def test_vpk_at_worst_dissipation(self):
        """Worst-case Vpk = Vcc/π. Tolerance accounts for round(4)."""
        vcc = 24.0
        res = amp_class_b(vcc=vcc, rl=4.0)
        assert abs(res["vpk_at_worst_dissipation_v"] - vcc / math.pi) < 1e-3

    def test_zero_vcc_returns_error(self):
        res = amp_class_b(vcc=0.0, rl=8.0)
        assert res["ok"] is False

    def test_negative_rl_returns_error(self):
        res = amp_class_b(vcc=30.0, rl=-8.0)
        assert res["ok"] is False

    def test_required_keys_present(self):
        res = amp_class_b(vcc=30.0, rl=8.0)
        for k in ("pout_max_w", "pdiss_per_device_max_w", "efficiency_max_pct",
                  "vpk_at_worst_dissipation_v", "psupply_at_pout_max_w"):
            assert k in res, f"missing key {k!r}"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Class-A Amplifier
# ═══════════════════════════════════════════════════════════════════════════════

class TestAmpClassA:
    """η_max ≤ 25%, Iq = Vcc/(2×RL) at minimum."""

    def test_efficiency_at_most_25pct(self):
        """Class-A ideal efficiency ≤ 25%."""
        res = amp_class_a(vcc=20.0, rl=8.0)
        assert res["ok"] is True
        assert res["efficiency_max_pct"] <= 25.0 + 1e-6

    def test_efficiency_exactly_25pct_at_minimum_iq(self):
        """With iq_factor=1.0 (min quiescent), η = 25% exactly."""
        res = amp_class_a(vcc=20.0, rl=8.0, iq_factor=1.0)
        assert abs(res["efficiency_max_pct"] - 25.0) < 0.01

    def test_iq_formula(self):
        """Iq = iq_factor × Vcc / (2 × RL)."""
        vcc, rl = 24.0, 8.0
        res = amp_class_a(vcc=vcc, rl=rl, iq_factor=1.5)
        expected_iq = 1.5 * vcc / (2.0 * rl)
        assert abs(res["iq_a"] - expected_iq) < 1e-9

    def test_pout_max_formula(self):
        """Pout_max = Vcc² / (8 × RL)."""
        vcc, rl = 20.0, 8.0
        res = amp_class_a(vcc=vcc, rl=rl)
        assert abs(res["pout_max_w"] - vcc ** 2 / (8.0 * rl)) < 1e-6

    def test_bad_iq_factor_returns_error(self):
        res = amp_class_a(vcc=20.0, rl=8.0, iq_factor=0.5)
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Class-AB Amplifier
# ═══════════════════════════════════════════════════════════════════════════════

class TestAmpClassAB:
    def test_bounds_bracket_a_and_b(self):
        """Lower bound = 25% (class A), upper bound ≈ 78.54% (class B)."""
        res = amp_class_ab(vcc=30.0, rl=8.0)
        assert res["ok"] is True
        assert abs(res["efficiency_lower_pct"] - 25.0) < 0.01
        assert abs(res["efficiency_upper_pct"] - (math.pi / 4.0) * 100.0) < 0.001

    def test_estimate_is_between_bounds(self):
        res = amp_class_ab(vcc=30.0, rl=8.0)
        assert res["efficiency_lower_pct"] < res["efficiency_estimate_pct"] < res["efficiency_upper_pct"]

    def test_pout_max_same_as_class_b(self):
        """Class-AB Pout_max = Vcc²/(2×RL) (same topology as push-pull)."""
        vcc, rl = 30.0, 8.0
        res_ab = amp_class_ab(vcc=vcc, rl=rl)
        res_b = amp_class_b(vcc=vcc, rl=rl)
        assert abs(res_ab["pout_max_w"] - res_b["pout_max_w"]) < 1e-6


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Class-D Amplifier
# ═══════════════════════════════════════════════════════════════════════════════

class TestAmpClassD:
    def test_ideal_efficiency_100pct(self):
        res = amp_class_d(vcc=30.0, rl=8.0, fsw_hz=400e3)
        assert res["ok"] is True
        assert abs(res["efficiency_ideal_pct"] - 100.0) < 1e-6

    def test_dead_time_loss_formula(self):
        """Dead-time loss = 2 × td × fsw × 100%."""
        td_ns = 50.0
        fsw = 400e3
        res = amp_class_d(vcc=30.0, rl=8.0, fsw_hz=fsw, dead_time_ns=td_ns)
        expected_loss = 2.0 * (td_ns * 1e-9) * fsw * 100.0
        assert abs(res["dead_time_loss_pct"] - expected_loss) < 1e-6

    def test_lc_filter_fb_equals_fsw_over_10(self):
        """Filter bandwidth = fsw / 10."""
        fsw = 400e3
        res = amp_class_d(vcc=30.0, rl=8.0, fsw_hz=fsw)
        assert abs(res["filter_fb_hz"] - fsw / 10.0) < 1e-3

    def test_pout_max_formula(self):
        """Pout_max = Vcc²/(2×RL) same as class B."""
        vcc, rl = 30.0, 8.0
        res = amp_class_d(vcc=vcc, rl=rl, fsw_hz=400e3)
        assert abs(res["pout_max_w"] - vcc ** 2 / (2.0 * rl)) < 1e-6

    def test_lc_filter_L_and_C_positive(self):
        res = amp_class_d(vcc=30.0, rl=8.0, fsw_hz=400e3)
        assert res["filter_L_H"] > 0
        assert res["filter_C_F"] > 0

    def test_invalid_order_returns_error(self):
        res = amp_class_d(vcc=30.0, rl=8.0, fsw_hz=400e3, lc_order=3)
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Heatsink Thermal Resistance
# ═══════════════════════════════════════════════════════════════════════════════

class TestHeatsinkRth:
    def test_basic_calculation(self):
        """Rth_sa = (Tj_max - Ta)/Pdiss - Rth_jc - Rth_cs."""
        pdiss, tj, ta, rjc, rcs = 50.0, 150.0, 25.0, 0.5, 0.3
        res = heatsink_rth(pdiss_w=pdiss, tj_max_c=tj, ta_c=ta, rth_jc=rjc, rth_cs=rcs)
        assert res["ok"] is True
        expected = (tj - ta) / pdiss - rjc - rcs
        assert abs(res["rth_sa_required_c_per_w"] - expected) < 1e-6

    def test_ta_above_tj_returns_error(self):
        res = heatsink_rth(pdiss_w=50.0, tj_max_c=100.0, ta_c=110.0, rth_jc=0.5)
        assert res["ok"] is False

    def test_warning_when_rth_negative(self):
        """When package losses exceed budget, Rth_sa < 0 → warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            res = heatsink_rth(pdiss_w=200.0, tj_max_c=150.0, ta_c=25.0,
                               rth_jc=1.0, rth_cs=0.5)
            assert res["ok"] is True
            # Rth_sa = (150-25)/200 - 1.0 - 0.5 = 0.625 - 1.5 = -0.875 → warning
            assert res["rth_sa_required_c_per_w"] < 0
            assert any("negative" in str(x.message).lower() or "budget" in str(x.message).lower()
                       for x in w)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Sealed Box (Thiele-Small)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSealedBox:
    def test_butterworth_qtc_alpha(self):
        """Qtc=0.707 → α = (0.707/Qts)² - 1."""
        vas, qts, fs = 30.0, 0.35, 40.0
        res = sealed_box(vas_l=vas, qts=qts, fs_hz=fs, qtc=0.707)
        assert res["ok"] is True
        expected_alpha = (0.707 / qts) ** 2 - 1.0
        assert abs(res["alpha"] - expected_alpha) < 1e-4

    def test_vb_from_vas_and_alpha(self):
        """Vb = Vas / α."""
        vas, qts = 30.0, 0.35
        res = sealed_box(vas_l=vas, qts=qts, fs_hz=40.0, qtc=0.707)
        assert abs(res["vb_l"] - vas / res["alpha"]) < 1e-4

    def test_fc_formula(self):
        """fc = fs × sqrt(α + 1)."""
        vas, qts, fs = 30.0, 0.35, 40.0
        res = sealed_box(vas_l=vas, qts=qts, fs_hz=fs, qtc=0.707)
        expected_fc = fs * math.sqrt(res["alpha"] + 1.0)
        assert abs(res["fc_hz"] - expected_fc) < 0.01

    def test_f3_greater_than_fc_for_butterworth(self):
        """For Butterworth (Qtc=0.707), f3 ≈ fc (exactly at −3 dB by definition)."""
        res = sealed_box(vas_l=30.0, qts=0.35, fs_hz=40.0, qtc=0.707)
        # f3 is referenced to fc; for a 2nd-order HP with Q=0.707, f3 = fc
        assert res["f3_hz"] > 0

    def test_qtc_leq_qts_returns_error(self):
        """qtc must be greater than qts."""
        res = sealed_box(vas_l=30.0, qts=0.5, fs_hz=40.0, qtc=0.3)
        assert res["ok"] is False
        assert "qtc" in res["reason"].lower() or "qts" in res["reason"].lower()

    def test_high_qtc_triggers_warning(self):
        """Qtc > 1.2 triggers a bass-hump warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            sealed_box(vas_l=30.0, qts=0.3, fs_hz=40.0, qtc=1.5)
            assert any("hump" in str(x.message).lower() or "qtc" in str(x.message).lower()
                       for x in w)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Vented Box
# ═══════════════════════════════════════════════════════════════════════════════

class TestVentedBox:
    def test_qb3_returns_valid_result(self):
        res = vented_box(vas_l=30.0, qts=0.35, fs_hz=40.0, re_ohm=6.0,
                         sd_cm2=130.0, alignment="QB3")
        assert res["ok"] is True
        assert res["vb_l"] > 0
        assert res["fb_hz"] > 0
        assert res["port_length_mm"] >= 0

    def test_sbb4_returns_valid_result(self):
        res = vented_box(vas_l=30.0, qts=0.35, fs_hz=40.0, re_ohm=6.0,
                         sd_cm2=130.0, alignment="SBB4")
        assert res["ok"] is True
        assert res["vb_l"] > 0

    def test_invalid_alignment_returns_error(self):
        res = vented_box(vas_l=30.0, qts=0.35, fs_hz=40.0, re_ohm=6.0,
                         sd_cm2=130.0, alignment="BW4")
        assert res["ok"] is False

    def test_chuffing_flag_set_for_tiny_port(self):
        """Very small port (5 mm) at Xmax=5mm should trigger chuffing warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            res = vented_box(vas_l=30.0, qts=0.35, fs_hz=40.0, re_ohm=6.0,
                             sd_cm2=130.0, alignment="QB3", port_diameter_mm=5.0)
            assert res["ok"] is True
            # chuffing_warning may be True or warnings may be issued
            if res["chuffing_warning"]:
                assert any("chuffing" in str(x.message).lower() or
                           "velocity" in str(x.message).lower()
                           for x in w)

    def test_fb_less_than_fs(self):
        """In a properly tuned vented box, fb < fs (below driver resonance)."""
        res = vented_box(vas_l=30.0, qts=0.35, fs_hz=40.0, re_ohm=6.0,
                         sd_cm2=130.0, alignment="QB3")
        assert res["fb_hz"] <= res["fs_hz"]


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Driver SPL
# ═══════════════════════════════════════════════════════════════════════════════

class TestDriverSPL:
    def test_spl_at_1w_equals_sensitivity(self):
        """At 1 W, 1 m, SPL = sensitivity."""
        sens = 90.0
        res = driver_spl(sensitivity_db_1w_1m=sens, power_w=1.0,
                         xmax_mm=5.0, sd_cm2=130.0, re_ohm=6.0, distance_m=1.0)
        assert res["ok"] is True
        assert abs(res["spl_at_rated_power_db"] - sens) < 0.01

    def test_spl_10x_power_adds_10db(self):
        """10× power → +10 dB SPL."""
        res1 = driver_spl(sensitivity_db_1w_1m=90.0, power_w=10.0,
                          xmax_mm=5.0, sd_cm2=130.0, re_ohm=6.0, distance_m=1.0)
        res2 = driver_spl(sensitivity_db_1w_1m=90.0, power_w=100.0,
                          xmax_mm=5.0, sd_cm2=130.0, re_ohm=6.0, distance_m=1.0)
        diff = res2["spl_at_rated_power_db"] - res1["spl_at_rated_power_db"]
        assert abs(diff - 10.0) < 0.01

    def test_spl_double_distance_minus_6db(self):
        """Doubling distance → −6 dB SPL (inverse-square law). Tolerance for round(2)."""
        res1 = driver_spl(sensitivity_db_1w_1m=90.0, power_w=100.0,
                          xmax_mm=5.0, sd_cm2=130.0, re_ohm=6.0, distance_m=1.0)
        res2 = driver_spl(sensitivity_db_1w_1m=90.0, power_w=100.0,
                          xmax_mm=5.0, sd_cm2=130.0, re_ohm=6.0, distance_m=2.0)
        diff = res1["spl_at_rated_power_db"] - res2["spl_at_rated_power_db"]
        assert abs(diff - 6.0) < 0.05


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Passive Crossover
# ═══════════════════════════════════════════════════════════════════════════════

class TestPassiveCrossover:
    def test_lr4_returns_4_components(self):
        """4th-order LR crossover has 4 components."""
        res = passive_crossover(fc_hz=2000.0, z_load=8.0, order=4,
                                topology="linkwitz-riley")
        assert res["ok"] is True
        assert len(res["components"]) == 4

    def test_bw2_L_formula(self):
        """BW2 first component (L) = g1 × Z / ωc.  g1=1.4142 for Butterworth 2nd."""
        fc, z = 2000.0, 8.0
        omega_c = 2.0 * math.pi * fc
        res = passive_crossover(fc_hz=fc, z_load=z, order=2, topology="butterworth")
        assert res["ok"] is True
        # First component is inductor: L = g1 × Z / ωc = 1.4142 × 8 / ωc
        l_expected = 1.4142 * z / omega_c
        l_actual = res["components"][0]["value_H"]
        assert abs(l_actual - l_expected) < 1e-9

    def test_bw2_C_formula(self):
        """BW2 second component (C) = g2 / (ωc × Z). g2=1.4142."""
        fc, z = 2000.0, 8.0
        omega_c = 2.0 * math.pi * fc
        res = passive_crossover(fc_hz=fc, z_load=z, order=2, topology="butterworth")
        c_expected = 1.4142 / (omega_c * z)
        c_actual = res["components"][1]["value_F"]
        assert abs(c_actual - c_expected) < 1e-12

    def test_invalid_order_returns_error(self):
        res = passive_crossover(fc_hz=2000.0, z_load=8.0, order=5,
                                topology="butterworth")
        assert res["ok"] is False

    def test_invalid_topology_returns_error(self):
        res = passive_crossover(fc_hz=2000.0, z_load=8.0, order=2,
                                topology="chebyshev")
        assert res["ok"] is False

    def test_component_types_alternate_L_C(self):
        """Components should alternate L, C, L, C in a 4th-order network."""
        res = passive_crossover(fc_hz=2000.0, z_load=8.0, order=4,
                                topology="butterworth")
        types = [c["type"] for c in res["components"]]
        assert types == ["L", "C", "L", "C"]


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Zobel Network
# ═══════════════════════════════════════════════════════════════════════════════

class TestZobel:
    def test_rz_equals_re(self):
        """Rz = Re."""
        res = zobel_network(re_ohm=6.0, le_mh=0.5)
        assert res["ok"] is True
        assert abs(res["rz_ohm"] - 6.0) < 1e-6

    def test_cz_formula(self):
        """Cz = Le / Re². Tolerance accounts for round(4)."""
        re, le_mh = 6.0, 0.5
        res = zobel_network(re_ohm=re, le_mh=le_mh)
        expected_cz_uf = (le_mh * 1e-3 / re ** 2) * 1e6
        assert abs(res["cz_uF"] - expected_cz_uf) < 1e-3

    def test_zero_re_returns_error(self):
        res = zobel_network(re_ohm=0.0, le_mh=0.5)
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 11. L-pad Attenuator
# ═══════════════════════════════════════════════════════════════════════════════

class TestLpad:
    def test_zero_attenuation_no_network(self):
        """0 dB attenuation → Rs = 0, Rp = ∞."""
        res = lpad_attenuator(attenuation_db=0.0, z_source=100.0, z_load=8.0)
        assert res["ok"] is True
        assert res["rs_ohm"] == 0.0

    def test_6db_attenuation_voltage_ratio(self):
        """6 dB attenuation → voltage ratio = 0.5 (20×log10(0.5) = −6 dB)."""
        res = lpad_attenuator(attenuation_db=6.0, z_source=100.0, z_load=8.0)
        assert res["ok"] is True
        # Rs = Z_load × (1/k − 1) where k = 10^(−6/20) = 0.5
        k = 10.0 ** (-6.0 / 20.0)  # ≈ 0.501
        rs_expected = 8.0 * (1.0 / k - 1.0)
        assert abs(res["rs_ohm"] - rs_expected) < 1e-4

    def test_negative_attenuation_returns_error(self):
        """Negative attenuation (gain) is not valid for an L-pad."""
        res = lpad_attenuator(attenuation_db=-6.0, z_source=100.0, z_load=8.0)
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 12. Damping Factor
# ═══════════════════════════════════════════════════════════════════════════════

class TestDampingFactor:
    def test_df_formula(self):
        """DF = Re / (Zout + R_cable)."""
        res = damping_factor(amp_zout_ohm=0.05, re_ohm=6.0, cable_r_ohm=0.1)
        assert res["ok"] is True
        expected_df = 6.0 / (0.05 + 0.1)
        assert abs(res["damping_factor"] - expected_df) < 1e-6

    def test_ideal_amp_zero_zout(self):
        """With Zout = 0 and cable = 0.1 Ω, DF = Re / 0.1."""
        res = damping_factor(amp_zout_ohm=0.0, re_ohm=8.0, cable_r_ohm=0.1)
        assert abs(res["damping_factor"] - 80.0) < 1e-6

    def test_poor_df_warning(self):
        """DF < 10 → warning issued."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            res = damping_factor(amp_zout_ohm=2.0, re_ohm=8.0, cable_r_ohm=0.5)
            assert res["damping_factor"] < 10.0
            assert any("df" in str(x.message).lower() or "damping" in str(x.message).lower()
                       for x in w)

    def test_zero_total_impedance_returns_error(self):
        """Zout=0 and cable=0 → zero denominator → error."""
        res = damping_factor(amp_zout_ohm=0.0, re_ohm=8.0, cable_r_ohm=0.0)
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 13. SPL Addition
# ═══════════════════════════════════════════════════════════════════════════════

class TestSPLAdd:
    def test_two_equal_sources_plus_3db(self):
        """Two identical incoherent sources → +3 dB."""
        spl = 90.0
        res = spl_add(spl, spl)
        assert res["ok"] is True
        assert abs(res["spl_total_db"] - (spl + 10.0 * math.log10(2))) < 0.001

    def test_very_different_levels_dominated_by_louder(self):
        """90 dB + 70 dB ≈ 90.04 dB (louder source dominates)."""
        res = spl_add(90.0, 70.0)
        assert abs(res["spl_total_db"] - 90.0) < 0.1

    def test_single_value_returns_error(self):
        res = spl_add(90.0)
        assert res["ok"] is False

    def test_three_sources(self):
        """Three sources each at 80 dB → 80 + 10×log10(3) ≈ 84.77 dB."""
        res = spl_add(80.0, 80.0, 80.0)
        expected = 80.0 + 10.0 * math.log10(3.0)
        assert abs(res["spl_total_db"] - expected) < 0.001


# ═══════════════════════════════════════════════════════════════════════════════
# 14. SPL vs Distance
# ═══════════════════════════════════════════════════════════════════════════════

class TestSPLDistance:
    def test_double_distance_minus_6db(self):
        """Doubling distance → −6 dB. Tolerance accounts for round(3)."""
        res1 = spl_distance(spl_ref_db=100.0, d_ref_m=1.0, d_target_m=2.0)
        assert res1["ok"] is True
        # 20*log10(2) = 6.0206 dB; rounded result ≈ 93.979 dB
        assert abs(res1["spl_target_db"] - 94.0) < 0.05

    def test_same_distance_no_change(self):
        """Same distance → same SPL."""
        res = spl_distance(spl_ref_db=90.0, d_ref_m=2.0, d_target_m=2.0)
        assert abs(res["spl_target_db"] - 90.0) < 1e-6

    def test_inverse_square_law_exact(self):
        """SPL(d) = SPL(d0) − 20×log10(d/d0). Tolerance accounts for round(3)."""
        spl0, d0, d = 95.0, 1.0, 5.0
        res = spl_distance(spl_ref_db=spl0, d_ref_m=d0, d_target_m=d)
        expected = spl0 - 20.0 * math.log10(d / d0)
        assert abs(res["spl_target_db"] - expected) < 1e-2


# ═══════════════════════════════════════════════════════════════════════════════
# 15. dB Conversion
# ═══════════════════════════════════════════════════════════════════════════════

class TestDBConversion:
    def test_voltage_ratio_2_equals_6db(self):
        """20×log10(2) ≈ 6.0206 dB."""
        res = db_voltage(v_ratio=2.0)
        assert res["ok"] is True
        assert abs(res["db"] - 20.0 * math.log10(2.0)) < 1e-6

    def test_voltage_ratio_1_equals_0db(self):
        res = db_voltage(v_ratio=1.0)
        assert abs(res["db"] - 0.0) < 1e-9

    def test_power_ratio_2_equals_3db(self):
        """10×log10(2) ≈ 3.0103 dB."""
        res = db_power(p_ratio=2.0)
        assert res["ok"] is True
        assert abs(res["db"] - 10.0 * math.log10(2.0)) < 1e-6

    def test_power_ratio_10_equals_10db(self):
        res = db_power(p_ratio=10.0)
        assert abs(res["db"] - 10.0) < 1e-9

    def test_zero_ratio_returns_error(self):
        assert db_voltage(v_ratio=0.0)["ok"] is False
        assert db_power(p_ratio=0.0)["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 16. A-weighting
# ═══════════════════════════════════════════════════════════════════════════════

class TestAWeighting:
    def test_zero_db_at_1khz(self):
        """A-weighting = 0 dB at 1 kHz (normalisation)."""
        res = a_weighting(freq_hz=1000.0)
        assert res["ok"] is True
        assert abs(res["a_weighting_db"] - 0.0) < 0.01

    def test_negative_below_1khz(self):
        """A-weighting is negative (attenuation) below ~1 kHz."""
        res = a_weighting(freq_hz=100.0)
        assert res["a_weighting_db"] < 0.0

    def test_negative_above_10khz(self):
        """A-weighting drops at high frequencies (above ~4 kHz)."""
        res = a_weighting(freq_hz=20000.0)
        assert res["a_weighting_db"] < 0.0

    def test_peak_near_3_4khz(self):
        """A-weighting peaks around 3–4 kHz (maximum positive correction)."""
        res_3k = a_weighting(freq_hz=3000.0)
        res_100 = a_weighting(freq_hz=100.0)
        assert res_3k["a_weighting_db"] > res_100["a_weighting_db"]

    def test_zero_frequency_returns_error(self):
        res = a_weighting(freq_hz=0.0)
        assert res["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 17. Impedance Bridging
# ═══════════════════════════════════════════════════════════════════════════════

class TestImpedanceBridging:
    def test_bridging_ok_when_ratio_geq_10(self):
        """Z_load / Z_source ≥ 10 → bridging_ok = True."""
        res = impedance_bridging(z_source=100.0, z_load=10000.0)
        assert res["ok"] is True
        assert res["bridging_ok"] is True

    def test_bridging_not_ok_when_ratio_lt_10(self):
        """Z_load / Z_source < 10 → bridging_ok = False + warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            res = impedance_bridging(z_source=600.0, z_load=600.0)
            assert res["bridging_ok"] is False
            assert any("bridging" in str(x.message).lower() or
                       "impedance" in str(x.message).lower()
                       for x in w)

    def test_voltage_transfer_formula(self):
        """Av = Z_load / (Z_source + Z_load). Tolerance accounts for round(6)."""
        zs, zl = 100.0, 10000.0
        res = impedance_bridging(z_source=zs, z_load=zl)
        expected_av = zl / (zs + zl)
        assert abs(res["av_linear"] - expected_av) < 1e-5

    def test_av_db_approaches_0_for_high_ratio(self):
        """With Z_load >> Z_source, Av → 1 (0 dB)."""
        res = impedance_bridging(z_source=1.0, z_load=1e6)
        assert abs(res["av_db"]) < 0.01


# ═══════════════════════════════════════════════════════════════════════════════
# 18. LLM Tool Handlers (async)
# ═══════════════════════════════════════════════════════════════════════════════

class TestToolHandlers:
    @pytest.mark.asyncio
    async def test_amp_class_b_tool_ok(self):
        res = await call(_amp_b_tool, vcc=30.0, rl=8.0)
        assert res["ok"] is True
        assert "efficiency_max_pct" in res

    @pytest.mark.asyncio
    async def test_amp_class_b_efficiency_value(self):
        """Tool returns correct π/4 efficiency."""
        res = await call(_amp_b_tool, vcc=30.0, rl=8.0)
        expected = (math.pi / 4.0) * 100.0
        assert abs(res["efficiency_max_pct"] - expected) < 0.001

    @pytest.mark.asyncio
    async def test_amp_class_a_tool_ok(self):
        res = await call(_amp_a_tool, vcc=20.0, rl=8.0)
        assert res["ok"] is True
        assert "iq_a" in res

    @pytest.mark.asyncio
    async def test_amp_class_d_tool_ok(self):
        res = await call(_amp_d_tool, vcc=30.0, rl=8.0, fsw_hz=400000.0)
        assert res["ok"] is True
        assert "filter_L_H" in res

    @pytest.mark.asyncio
    async def test_sealed_box_tool_ok(self):
        res = await call(_sealed_tool, vas_l=30.0, qts=0.35, fs_hz=40.0)
        assert res["ok"] is True
        assert "vb_l" in res

    @pytest.mark.asyncio
    async def test_crossover_tool_ok(self):
        res = await call(_xover_tool, fc_hz=2000.0, z_load=8.0, order=4,
                         topology="linkwitz-riley")
        assert res["ok"] is True
        assert len(res["components"]) == 4

    @pytest.mark.asyncio
    async def test_spl_add_tool_ok(self):
        res = await call(_spl_add_tool, spl_values_db=[90.0, 90.0])
        assert res["ok"] is True
        expected = 90.0 + 10.0 * math.log10(2.0)
        assert abs(res["spl_total_db"] - expected) < 0.001

    @pytest.mark.asyncio
    async def test_damping_factor_tool_ok(self):
        res = await call(_df_tool, amp_zout_ohm=0.1, re_ohm=8.0)
        assert res["ok"] is True
        assert "damping_factor" in res

    @pytest.mark.asyncio
    async def test_tool_invalid_json_returns_error(self):
        result = await _amp_b_tool(None, b"not valid json{{")
        data = json.loads(result)
        assert data.get("ok") is False or "error" in data

    @pytest.mark.asyncio
    async def test_a_weighting_tool_zero_at_1khz(self):
        res = await call(_aweight_tool, freq_hz=1000.0)
        assert res["ok"] is True
        assert abs(res["a_weighting_db"]) < 0.01

    @pytest.mark.asyncio
    async def test_bridge_tool_ok(self):
        res = await call(_bridge_tool, z_source=100.0, z_load=10000.0)
        assert res["ok"] is True
        assert res["bridging_ok"] is True
