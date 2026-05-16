"""
Hermetic tests for kerf_electronics.charger BMS design calculator.

Covers (≥30 tests):
  cc_cv_charge_profile:
    - Li-ion CC time = dod * Q / I_cc
    - CV time = -tau * ln(cv_cutoff)
    - total_time = t_cc + t_cv
    - total_time_min consistent with total_time_h
    - V_max_pack = V_max_cell * n_cells_series
    - LiFePO4 chemistry uses correct V_max (3.65 V)
    - NiMH chemistry uses correct default cc_fraction (0.3C)
    - Lead-acid temperature compensation reduces V_max at high temp
    - over-temp-charge warning when T > max_charge_temp
    - over-C-rate warning when cc_fraction > 2
    - invalid chemistry returns ok=False
    - zero capacity returns ok=False
    - dod > 1.0 returns ok=False

  charger_power:
    - P_out = V * I exactly
    - P_in = P_out / efficiency
    - P_loss = P_in - P_out
    - junction temperature computed from Rth
    - junction temp warning when T_j > 125°C
    - efficiency > 1 returns ok=False
    - zero voltage returns ok=False

  passive_balance:
    - zero imbalance → zero bleed and zero time
    - bleed current = V_high / R_bleed
    - balance power = V_high * I_bleed
    - imbalance warning when dV > 100 mV
    - v_high < v_low returns ok=False

  active_balance:
    - zero imbalance → zero transfer
    - transfer_time = dQ / I_xfer
    - energy_loss = V_hi * dQ * (1 - efficiency)

  coulomb_soc:
    - SOC_cc = SOC_init + charge_ah / capacity_ah
    - OCV blend: soc_blend = (1-alpha)*SOC_cc + alpha*OCV
    - drift_budget = drift_rate * elapsed_h
    - drift warning when > 5%
    - soc clamped to [0, 1]
    - soc_init > 1 returns ok=False

  state_of_health:
    - Q_now = Q_new * (1 - fade * n_cycles) exactly
    - R_now = R_new * (1 + growth * n_cycles) exactly
    - soh_pct = 100 * Q_now / Q_new
    - SoH < 80% triggers warning
    - cycles_to_80pct math
    - zero fade → infinite cycles_to_80pct (None)

  protection_thresholds:
    - ov_release_v = v_ov - hysteresis_v
    - uv_release_v = v_uv + hysteresis_v
    - ot_release_c = t_ot - hysteresis_t
    - flags evaluated when cell values given
    - short-circuit flag set above i_sc threshold
    - sc threshold <= oc threshold returns ok=False

  cell_matching_usable_capacity:
    - usable_fraction = 1 - tolerance_fraction exactly
    - q_cell_usable = q_nominal * (1 - tol)
    - tolerance > 5% triggers warning
    - tolerance >= 1.0 returns ok=False

  mppt_solar_charge:
    - p_mppt = V_mpp * I_mpp at STC (no derating)
    - temperature derating reduces I_mpp correctly
    - e_day = p_to_bat * peak_sun_hours
    - soc_end capped at 1.0
    - zero capacity returns ok=False

  LLM tool handlers (via registry stub):
    - charger_cc_cv_profile tool: happy path
    - charger_power tool: happy path
    - charger_passive_balance tool: happy path
    - charger_coulomb_soc tool: happy path
    - charger_protection tool: happy path
    - invalid JSON returns error

Author: imranparuk
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
import sys
import types

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
_KERF_CHAT_SAVED = {
    _n: sys.modules.get(_n)
    for _n in ("kerf_chat", "kerf_chat.tools", "kerf_chat.tools.registry")
}
if _kc_real is None:
    sys.modules["kerf_chat.tools.registry"] = _reg_stub

# ── Ensure src/ on path ───────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import pytest

from kerf_electronics.charger.bms import (
    active_balance,
    cc_cv_charge_profile,
    cell_matching_usable_capacity,
    charger_power,
    coulomb_soc,
    mppt_solar_charge,
    passive_balance,
    protection_thresholds,
    state_of_health,
)

# ── Load tool module via importlib so the stub is active ─────────────────────
_tool_spec = importlib.util.spec_from_file_location(
    "kerf_electronics.charger.tools",
    os.path.join(_SRC, "kerf_electronics", "charger", "tools.py"),
)
_tool_mod = importlib.util.module_from_spec(_tool_spec)
_tool_spec.loader.exec_module(_tool_mod)

cc_cv_profile_tool = _tool_mod.charger_cc_cv_profile
charger_power_tool = _tool_mod.charger_power_tool
passive_balance_tool = _tool_mod.charger_passive_balance
active_balance_tool = _tool_mod.charger_active_balance
coulomb_soc_tool = _tool_mod.charger_coulomb_soc
soh_tool = _tool_mod.charger_state_of_health
protection_tool = _tool_mod.charger_protection
cell_matching_tool = _tool_mod.charger_cell_matching
mppt_tool = _tool_mod.charger_mppt_solar


# ── Async call helper ─────────────────────────────────────────────────────────

async def call(fn, **kwargs):
    result = await fn(None, json.dumps(kwargs).encode())
    return json.loads(result)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. cc_cv_charge_profile
# ═══════════════════════════════════════════════════════════════════════════════

class TestCcCvChargeProfile:
    def test_cc_time_formula(self):
        """t_cc = dod * Q / I_cc = dod / cc_fraction (hours)."""
        r = cc_cv_charge_profile(
            capacity_ah=10.0,
            chemistry="li-ion",
            dod=0.8,
            cc_fraction=0.5,
        )
        assert r["ok"] is True
        # I_cc = 0.5 * 10 = 5 A; t_cc = 0.8 * 10 / 5 = 1.6 h
        assert abs(r["t_cc_h"] - 1.6) < 1e-6

    def test_cv_time_formula(self):
        """t_cv = -tau * ln(cv_cutoff_fraction), tau = Q / I_cc."""
        r = cc_cv_charge_profile(
            capacity_ah=10.0,
            chemistry="li-ion",
            dod=0.8,
            cc_fraction=0.5,
            cv_cutoff_fraction=0.05,
        )
        assert r["ok"] is True
        tau = 10.0 / 5.0  # Q / I_cc = 2 h
        t_cv_expected = -tau * math.log(0.05)
        # output is rounded to 4 dp, so tolerance is 5e-5
        assert abs(r["t_cv_h"] - t_cv_expected) < 1e-4

    def test_total_time_equals_cc_plus_cv(self):
        r = cc_cv_charge_profile(capacity_ah=5.0, chemistry="li-ion")
        assert r["ok"] is True
        assert abs(r["total_time_h"] - (r["t_cc_h"] + r["t_cv_h"])) < 1e-9

    def test_total_time_min_consistent(self):
        r = cc_cv_charge_profile(capacity_ah=5.0, chemistry="nimh")
        assert r["ok"] is True
        assert abs(r["total_time_min"] - r["total_time_h"] * 60.0) < 1e-6

    def test_v_max_pack_scales_with_n_series(self):
        r = cc_cv_charge_profile(
            capacity_ah=3.0, chemistry="li-ion", n_cells_series=4
        )
        assert r["ok"] is True
        # Li-ion V_max = 4.2; pack = 4 * 4.2 = 16.8 V
        assert abs(r["v_max_pack_v"] - 4 * r["v_max_cell_v"]) < 1e-9

    def test_lifepo4_v_max(self):
        """LiFePO4 per-cell V_max should be 3.65 V."""
        r = cc_cv_charge_profile(capacity_ah=10.0, chemistry="lifepo4")
        assert r["ok"] is True
        assert abs(r["v_max_cell_v"] - 3.65) < 1e-6

    def test_nimh_default_cc_fraction(self):
        """NiMH default cc_fraction is 0.3."""
        r = cc_cv_charge_profile(capacity_ah=2.0, chemistry="nimh")
        assert r["ok"] is True
        assert abs(r["cc_fraction"] - 0.3) < 1e-9

    def test_lead_acid_temp_comp_reduces_vmax(self):
        """At 35°C, lead-acid V_max per cell should be lower than at 25°C."""
        r25 = cc_cv_charge_profile(
            capacity_ah=10.0, chemistry="lead-acid", t_cell_c=25.0
        )
        r35 = cc_cv_charge_profile(
            capacity_ah=10.0, chemistry="lead-acid", t_cell_c=35.0
        )
        assert r25["ok"] and r35["ok"]
        assert r35["v_max_adjusted_v"] < r25["v_max_adjusted_v"]

    def test_over_temp_charge_warning(self):
        """Charging Li-ion above 45°C should generate a warning."""
        import warnings as _w
        with _w.catch_warnings(record=True):
            _w.simplefilter("always")
            r = cc_cv_charge_profile(
                capacity_ah=3.0, chemistry="li-ion", t_cell_c=50.0
            )
        assert r["ok"] is True
        assert any("over-temp" in w for w in r["warnings"])

    def test_over_c_rate_warning(self):
        """cc_fraction > 2 should trigger over-C-rate warning."""
        import warnings as _w
        with _w.catch_warnings(record=True):
            _w.simplefilter("always")
            r = cc_cv_charge_profile(
                capacity_ah=3.0, chemistry="li-ion", cc_fraction=3.0
            )
        assert r["ok"] is True
        assert any("over-C-rate" in w or "C-rate" in w for w in r["warnings"])

    def test_invalid_chemistry_error(self):
        r = cc_cv_charge_profile(capacity_ah=3.0, chemistry="unknown-chem")
        assert r["ok"] is False

    def test_zero_capacity_error(self):
        r = cc_cv_charge_profile(capacity_ah=0.0, chemistry="li-ion")
        assert r["ok"] is False

    def test_dod_over_one_error(self):
        r = cc_cv_charge_profile(capacity_ah=3.0, dod=1.5)
        assert r["ok"] is False

    def test_charge_accepted_equals_dod_times_capacity(self):
        r = cc_cv_charge_profile(capacity_ah=10.0, dod=0.7, chemistry="li-ion")
        assert r["ok"] is True
        assert abs(r["charge_accepted_ah"] - 0.7 * 10.0) < 1e-6


# ═══════════════════════════════════════════════════════════════════════════════
# 2. charger_power
# ═══════════════════════════════════════════════════════════════════════════════

class TestChargerPower:
    def test_p_out_formula(self):
        r = charger_power(v_bat_v=12.6, i_charge_a=5.0)
        assert r["ok"] is True
        assert abs(r["p_out_w"] - 12.6 * 5.0) < 1e-6

    def test_p_in_formula(self):
        r = charger_power(v_bat_v=12.0, i_charge_a=4.0, efficiency=0.85)
        assert r["ok"] is True
        # output rounded to 4 dp; tolerance 5e-5
        assert abs(r["p_in_w"] - (12.0 * 4.0 / 0.85)) < 1e-3

    def test_p_loss_equals_p_in_minus_p_out(self):
        r = charger_power(v_bat_v=12.0, i_charge_a=4.0, efficiency=0.90)
        assert r["ok"] is True
        assert abs(r["p_loss_w"] - (r["p_in_w"] - r["p_out_w"])) < 1e-6

    def test_junction_temp_formula(self):
        """T_j = T_amb + P_loss * Rth."""
        r = charger_power(
            v_bat_v=12.0, i_charge_a=4.0, efficiency=0.90,
            rth_c_a_k_per_w=5.0, t_ambient_c=25.0,
        )
        assert r["ok"] is True
        # p_loss_w is rounded to 4 dp before being stored; use stored value
        expected_tj = 25.0 + r["p_loss_w"] * 5.0
        # t_junction_c rounded to 2 dp, so tolerance is 0.01
        assert abs(r["t_junction_c"] - expected_tj) < 0.01

    def test_junction_temp_warning_over_125(self):
        """Very high loss with large Rth → T_j > 125°C → warning."""
        import warnings as _w
        with _w.catch_warnings(record=True):
            _w.simplefilter("always")
            r = charger_power(
                v_bat_v=12.0, i_charge_a=10.0, efficiency=0.50,
                rth_c_a_k_per_w=10.0, t_ambient_c=25.0,
            )
        assert r["ok"] is True
        assert r["t_junction_c"] > 125.0
        assert len(r["warnings"]) > 0

    def test_efficiency_over_one_error(self):
        r = charger_power(v_bat_v=12.0, i_charge_a=4.0, efficiency=1.1)
        assert r["ok"] is False

    def test_zero_voltage_error(self):
        r = charger_power(v_bat_v=0.0, i_charge_a=4.0)
        assert r["ok"] is False

    def test_no_rth_no_junction_key(self):
        """When rth_c_a_k_per_w is not given, t_junction_c should not be in result."""
        r = charger_power(v_bat_v=12.0, i_charge_a=2.0)
        assert r["ok"] is True
        assert "t_junction_c" not in r


# ═══════════════════════════════════════════════════════════════════════════════
# 3. passive_balance
# ═══════════════════════════════════════════════════════════════════════════════

class TestPassiveBalance:
    def test_zero_imbalance_returns_zero(self):
        r = passive_balance(4.1, 4.1, 3.0, 10.0)
        assert r["ok"] is True
        assert r["i_bleed_a"] == 0.0
        assert r["balance_time_h"] == 0.0

    def test_bleed_current_formula(self):
        """I_bleed = V_high / R_bleed."""
        r = passive_balance(4.2, 4.15, 3.0, 10.0)
        assert r["ok"] is True
        assert abs(r["i_bleed_a"] - 4.2 / 10.0) < 1e-6

    def test_bleed_power_formula(self):
        """P_bleed = V_high * I_bleed."""
        r = passive_balance(4.2, 4.0, 3.0, 10.0)
        assert r["ok"] is True
        assert abs(r["p_bleed_w"] - 4.2 * r["i_bleed_a"]) < 1e-6

    def test_imbalance_warning_over_100mv(self):
        """Voltage spread > 100 mV triggers imbalance warning."""
        import warnings as _w
        with _w.catch_warnings(record=True):
            _w.simplefilter("always")
            r = passive_balance(4.2, 4.05, 3.0, 10.0)
        assert r["ok"] is True
        assert any("imbalance" in w for w in r["warnings"])

    def test_v_high_less_than_v_low_error(self):
        r = passive_balance(4.0, 4.2, 3.0, 10.0)
        assert r["ok"] is False

    def test_balance_time_positive_for_imbalanced_cells(self):
        r = passive_balance(4.2, 4.1, 3.0, 100.0)
        assert r["ok"] is True
        assert r["balance_time_h"] > 0


# ═══════════════════════════════════════════════════════════════════════════════
# 4. active_balance
# ═══════════════════════════════════════════════════════════════════════════════

class TestActiveBalance:
    def test_zero_imbalance_returns_zero(self):
        r = active_balance(4.1, 4.1, 3.0, 0.5)
        assert r["ok"] is True
        assert r["dq_ah"] == 0.0
        assert r["transfer_time_h"] == 0.0
        assert r["energy_loss_wh"] == 0.0

    def test_transfer_time_formula(self):
        """t_xfer = dQ / I_xfer."""
        v_hi = 4.2
        v_lo = 4.1
        q = 3.0
        i_xfer = 0.5
        r = active_balance(v_hi, v_lo, q, i_xfer)
        assert r["ok"] is True
        dq_expected = (v_hi - v_lo) * (q / v_hi)
        t_expected = dq_expected / i_xfer
        # transfer_time_h rounded to 4 dp, so tolerance is 5e-5
        assert abs(r["transfer_time_h"] - t_expected) < 1e-4

    def test_energy_loss_formula(self):
        """energy_loss = V_hi * dQ * (1 - eff)."""
        v_hi = 4.2
        v_lo = 4.0
        q = 3.0
        eff = 0.85
        r = active_balance(v_hi, v_lo, q, 0.5, efficiency=eff)
        assert r["ok"] is True
        dq = (v_hi - v_lo) * (q / v_hi)
        expected_loss = v_hi * dq * (1.0 - eff)
        assert abs(r["energy_loss_wh"] - expected_loss) < 1e-6


# ═══════════════════════════════════════════════════════════════════════════════
# 5. coulomb_soc
# ═══════════════════════════════════════════════════════════════════════════════

class TestCoulombSOC:
    def test_soc_cc_formula(self):
        """SOC_cc = SOC_init + charge_ah / capacity_ah."""
        r = coulomb_soc(
            soc_init=0.5, charge_ah=1.0, capacity_ah=10.0,
            elapsed_h=1.0,
        )
        assert r["ok"] is True
        assert abs(r["soc_cc"] - 0.6) < 1e-6

    def test_ocv_blend_formula(self):
        """SOC_blend = (1 - alpha) * SOC_cc + alpha * OCV_SOC."""
        r = coulomb_soc(
            soc_init=0.5, charge_ah=0.0, capacity_ah=10.0,
            elapsed_h=0.0, ocv_soc=0.8, alpha_ocv=0.2,
        )
        assert r["ok"] is True
        expected = 0.8 * 0.5 + 0.2 * 0.8
        assert abs(r["soc_blend"] - expected) < 1e-6

    def test_drift_budget_formula(self):
        """drift_budget = drift_fraction_per_hour * elapsed_h."""
        r = coulomb_soc(
            soc_init=0.6, charge_ah=0.0, capacity_ah=10.0,
            elapsed_h=10.0, drift_fraction_per_hour=0.002,
        )
        assert r["ok"] is True
        assert abs(r["drift_budget"] - 0.02) < 1e-9

    def test_drift_warning_over_5pct(self):
        """drift > 5% triggers warning."""
        r = coulomb_soc(
            soc_init=0.5, charge_ah=0.0, capacity_ah=10.0,
            elapsed_h=100.0, drift_fraction_per_hour=0.001,
        )
        assert r["ok"] is True
        assert len(r["warnings"]) > 0

    def test_soc_clamped_at_one(self):
        """Over-charge: SOC_cc clamped to 1.0."""
        r = coulomb_soc(
            soc_init=0.9, charge_ah=5.0, capacity_ah=10.0, elapsed_h=0.0
        )
        assert r["ok"] is True
        assert r["soc_final"] <= 1.0

    def test_soc_clamped_at_zero(self):
        """Over-discharge: SOC_cc clamped to 0.0."""
        r = coulomb_soc(
            soc_init=0.1, charge_ah=-5.0, capacity_ah=10.0, elapsed_h=0.0
        )
        assert r["ok"] is True
        assert r["soc_final"] >= 0.0

    def test_soc_init_over_one_error(self):
        r = coulomb_soc(
            soc_init=1.5, charge_ah=0.0, capacity_ah=10.0, elapsed_h=0.0
        )
        assert r["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 6. state_of_health
# ═══════════════════════════════════════════════════════════════════════════════

class TestStateOfHealth:
    def test_q_now_formula(self):
        """Q_now = Q_new * (1 - fade * n_cycles)."""
        r = state_of_health(
            q_new_ah=3.0, r_new_ohm=0.05, n_cycles=1000,
            capacity_fade_per_cycle=0.0001,
        )
        assert r["ok"] is True
        expected_q = 3.0 * (1.0 - 0.0001 * 1000)
        assert abs(r["q_now_ah"] - expected_q) < 1e-6

    def test_r_now_formula(self):
        """R_now = R_new * (1 + growth * n_cycles)."""
        r = state_of_health(
            q_new_ah=3.0, r_new_ohm=0.05, n_cycles=500,
            resistance_growth_per_cycle=0.0002,
        )
        assert r["ok"] is True
        expected_r = 0.05 * (1.0 + 0.0002 * 500)
        assert abs(r["r_now_ohm"] - expected_r) < 1e-9

    def test_soh_pct_formula(self):
        """SoH% = 100 * Q_now / Q_new."""
        r = state_of_health(q_new_ah=3.0, r_new_ohm=0.05, n_cycles=0)
        assert r["ok"] is True
        assert abs(r["soh_pct"] - 100.0) < 1e-6

    def test_soh_below_80_warning(self):
        """SoH < 80% triggers warning."""
        import warnings as _w
        with _w.catch_warnings(record=True):
            _w.simplefilter("always")
            r = state_of_health(
                q_new_ah=3.0, r_new_ohm=0.05, n_cycles=5000,
                capacity_fade_per_cycle=0.00005,
            )
        assert r["ok"] is True
        assert any("80%" in w for w in r["warnings"])

    def test_cycles_to_80pct_formula(self):
        """cycles_to_80 = 0.20 / capacity_fade_per_cycle."""
        fade = 0.0001
        r = state_of_health(q_new_ah=3.0, r_new_ohm=0.05, n_cycles=0,
                             capacity_fade_per_cycle=fade)
        assert r["ok"] is True
        assert r["cycles_to_80pct"] == int(0.20 / fade)

    def test_zero_fade_infinite_cycles(self):
        """Zero fade → cycles_to_80pct = None (no EOL)."""
        r = state_of_health(
            q_new_ah=3.0, r_new_ohm=0.05, n_cycles=0,
            capacity_fade_per_cycle=0.0,
        )
        assert r["ok"] is True
        assert r["cycles_to_80pct"] is None


# ═══════════════════════════════════════════════════════════════════════════════
# 7. protection_thresholds
# ═══════════════════════════════════════════════════════════════════════════════

class TestProtectionThresholds:
    def _base(self, **kw):
        defaults = dict(
            v_ov_trip_v=4.25, v_uv_trip_v=2.5,
            i_oc_trip_a=30.0, t_ot_trip_c=60.0, i_sc_trip_a=100.0,
        )
        defaults.update(kw)
        return protection_thresholds(**defaults)

    def test_ov_release_formula(self):
        r = self._base(hysteresis_v=0.05)
        assert r["ok"] is True
        assert abs(r["ov_release_v"] - (4.25 - 0.05)) < 1e-6

    def test_uv_release_formula(self):
        r = self._base(hysteresis_v=0.05)
        assert r["ok"] is True
        assert abs(r["uv_release_v"] - (2.5 + 0.05)) < 1e-6

    def test_ot_release_formula(self):
        r = self._base(hysteresis_t_c=5.0)
        assert r["ok"] is True
        assert abs(r["ot_release_c"] - (60.0 - 5.0)) < 1e-6

    def test_ov_flag_when_v_above_trip(self):
        r = self._base(v_cell_v=4.30)
        assert r["ok"] is True
        assert r["flags"]["ov"] is True

    def test_ov_flag_clear_when_v_below_trip(self):
        r = self._base(v_cell_v=4.0)
        assert r["ok"] is True
        assert r["flags"]["ov"] is False

    def test_sc_flag_set_above_sc_threshold(self):
        r = self._base(i_cell_a=150.0)
        assert r["ok"] is True
        assert r["flags"]["short_circuit"] is True
        assert r["flags"]["oc"] is True

    def test_oc_flag_set_between_oc_and_sc(self):
        r = self._base(i_cell_a=50.0)
        assert r["ok"] is True
        assert r["flags"]["oc"] is True
        assert r["flags"]["short_circuit"] is False

    def test_sc_threshold_below_oc_error(self):
        r = protection_thresholds(
            v_ov_trip_v=4.25, v_uv_trip_v=2.5,
            i_oc_trip_a=100.0, t_ot_trip_c=60.0,
            i_sc_trip_a=50.0,  # sc < oc → error
        )
        assert r["ok"] is False

    def test_no_flags_when_no_cell_values(self):
        r = self._base()
        assert r["ok"] is True
        assert "flags" not in r


# ═══════════════════════════════════════════════════════════════════════════════
# 8. cell_matching_usable_capacity
# ═══════════════════════════════════════════════════════════════════════════════

class TestCellMatchingUsableCapacity:
    def test_usable_fraction_formula(self):
        r = cell_matching_usable_capacity(q_nominal_ah=10.0, tolerance_fraction=0.03)
        assert r["ok"] is True
        assert abs(r["usable_fraction"] - (1.0 - 0.03)) < 1e-9

    def test_q_cell_usable_formula(self):
        r = cell_matching_usable_capacity(q_nominal_ah=10.0, tolerance_fraction=0.02)
        assert r["ok"] is True
        assert abs(r["q_cell_usable_ah"] - 10.0 * 0.98) < 1e-6

    def test_q_pack_usable_scales_with_parallel(self):
        r = cell_matching_usable_capacity(
            q_nominal_ah=3.0, tolerance_fraction=0.02, n_parallel=4
        )
        assert r["ok"] is True
        assert abs(r["q_pack_usable_ah"] - 3.0 * 0.98 * 4) < 1e-6

    def test_warning_when_tolerance_over_5pct(self):
        import warnings as _w
        with _w.catch_warnings(record=True):
            _w.simplefilter("always")
            r = cell_matching_usable_capacity(
                q_nominal_ah=10.0, tolerance_fraction=0.06
            )
        assert r["ok"] is True
        assert len(r["warnings"]) > 0

    def test_tolerance_zero_gives_full_capacity(self):
        r = cell_matching_usable_capacity(q_nominal_ah=10.0, tolerance_fraction=0.0)
        assert r["ok"] is True
        assert abs(r["q_cell_usable_ah"] - 10.0) < 1e-9

    def test_tolerance_at_one_error(self):
        r = cell_matching_usable_capacity(q_nominal_ah=10.0, tolerance_fraction=1.0)
        assert r["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 9. mppt_solar_charge
# ═══════════════════════════════════════════════════════════════════════════════

class TestMpptSolarCharge:
    def test_p_mppt_at_stc(self):
        """At 25°C there is no derating; P_mppt = V_mpp * I_mpp."""
        r = mppt_solar_charge(
            v_mpp_v=18.0, i_mpp_a=5.0, peak_sun_hours=5.0,
            v_bat_v=12.0, capacity_ah=50.0, t_panel_c=25.0,
        )
        assert r["ok"] is True
        assert abs(r["p_mppt_w"] - 18.0 * 5.0) < 1e-6

    def test_temperature_derating_reduces_i_mpp(self):
        """At 45°C (Δ20°C), I_mpp should be slightly higher than STC
        for crystalline Si (positive isc_temp_coeff)."""
        r_25 = mppt_solar_charge(
            v_mpp_v=18.0, i_mpp_a=5.0, peak_sun_hours=5.0,
            v_bat_v=12.0, capacity_ah=50.0, t_panel_c=25.0,
        )
        r_45 = mppt_solar_charge(
            v_mpp_v=18.0, i_mpp_a=5.0, peak_sun_hours=5.0,
            v_bat_v=12.0, capacity_ah=50.0, t_panel_c=45.0,
            isc_temp_coeff_per_c=0.0004,
        )
        assert r_25["ok"] and r_45["ok"]
        assert r_45["i_mpp_derated_a"] > r_25["i_mpp_derated_a"]

    def test_e_day_formula(self):
        """e_day = P_mppt_to_bat * peak_sun_hours."""
        r = mppt_solar_charge(
            v_mpp_v=20.0, i_mpp_a=3.0, peak_sun_hours=4.0,
            v_bat_v=12.0, capacity_ah=100.0, t_panel_c=25.0,
            mppt_efficiency=1.0,
        )
        assert r["ok"] is True
        assert abs(r["e_day_wh"] - 20.0 * 3.0 * 4.0) < 1e-4

    def test_soc_end_capped_at_one(self):
        """Very large panel → soc_end capped at 1.0."""
        r = mppt_solar_charge(
            v_mpp_v=100.0, i_mpp_a=100.0, peak_sun_hours=12.0,
            v_bat_v=12.0, capacity_ah=1.0, soc_init=0.5,
        )
        assert r["ok"] is True
        assert r["soc_end"] <= 1.0

    def test_zero_capacity_error(self):
        r = mppt_solar_charge(
            v_mpp_v=18.0, i_mpp_a=5.0, peak_sun_hours=5.0,
            v_bat_v=12.0, capacity_ah=0.0,
        )
        assert r["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 10. LLM tool handlers
# ═══════════════════════════════════════════════════════════════════════════════

class TestToolCcCvProfile:
    @pytest.mark.asyncio
    async def test_happy_path(self):
        result = await call(
            cc_cv_profile_tool,
            capacity_ah=10.0,
            chemistry="li-ion",
            dod=0.8,
        )
        assert result["ok"] is True
        assert result["t_cc_h"] > 0
        assert result["t_cv_h"] > 0

    @pytest.mark.asyncio
    async def test_invalid_json_returns_error(self):
        res = json.loads(await cc_cv_profile_tool(None, b"not json"))
        assert "error" in res

    @pytest.mark.asyncio
    async def test_invalid_chemistry_returns_error(self):
        result = await call(cc_cv_profile_tool, capacity_ah=5.0, chemistry="banana")
        # err_payload returns {"ok": False, "error": ..., "code": ...}
        assert result.get("ok") is False or "error" in result


class TestToolChargerPower:
    @pytest.mark.asyncio
    async def test_happy_path(self):
        result = await call(
            charger_power_tool,
            v_bat_v=12.6, i_charge_a=2.0, efficiency=0.90,
        )
        assert result["ok"] is True
        assert result["p_out_w"] > 0

    @pytest.mark.asyncio
    async def test_with_thermal(self):
        result = await call(
            charger_power_tool,
            v_bat_v=12.0, i_charge_a=3.0, efficiency=0.85,
            rth_c_a_k_per_w=3.0, t_ambient_c=30.0,
        )
        assert result["ok"] is True
        assert "t_junction_c" in result


class TestToolPassiveBalance:
    @pytest.mark.asyncio
    async def test_happy_path(self):
        result = await call(
            passive_balance_tool,
            v_high_v=4.2, v_low_v=4.1,
            cell_capacity_ah=3.0, r_bleed_ohm=10.0,
        )
        assert result["ok"] is True
        assert result["i_bleed_a"] > 0


class TestToolCoulombSOC:
    @pytest.mark.asyncio
    async def test_happy_path(self):
        result = await call(
            coulomb_soc_tool,
            soc_init=0.5, charge_ah=1.0,
            capacity_ah=10.0, elapsed_h=2.0,
        )
        assert result["ok"] is True
        assert 0.0 <= result["soc_final"] <= 1.0

    @pytest.mark.asyncio
    async def test_with_ocv_blend(self):
        result = await call(
            coulomb_soc_tool,
            soc_init=0.5, charge_ah=0.0,
            capacity_ah=10.0, elapsed_h=0.0,
            ocv_soc=0.75, alpha_ocv=0.2,
        )
        assert result["ok"] is True
        # blend: 0.8*0.5 + 0.2*0.75 = 0.55
        assert abs(result["soc_blend"] - 0.55) < 1e-6


class TestToolProtection:
    @pytest.mark.asyncio
    async def test_happy_path_no_cell_values(self):
        result = await call(
            protection_tool,
            v_ov_trip_v=4.25, v_uv_trip_v=2.5,
            i_oc_trip_a=30.0, t_ot_trip_c=60.0, i_sc_trip_a=100.0,
        )
        assert result["ok"] is True
        assert "flags" not in result

    @pytest.mark.asyncio
    async def test_with_cell_values_flags_present(self):
        result = await call(
            protection_tool,
            v_ov_trip_v=4.25, v_uv_trip_v=2.5,
            i_oc_trip_a=30.0, t_ot_trip_c=60.0, i_sc_trip_a=100.0,
            v_cell_v=4.0, i_cell_a=10.0, t_cell_c=35.0,
        )
        assert result["ok"] is True
        assert "flags" in result

    @pytest.mark.asyncio
    async def test_invalid_json_returns_error(self):
        res = json.loads(await protection_tool(None, b"bad"))
        assert "error" in res


# ── Restore sys.modules so the kerf_chat stub does not leak ──────────────────
def teardown_module(module):  # noqa: D401
    import sys as _sys
    for _name, _orig in _KERF_CHAT_SAVED.items():
        if _orig is None:
            _sys.modules.pop(_name, None)
        else:
            _sys.modules[_name] = _orig
