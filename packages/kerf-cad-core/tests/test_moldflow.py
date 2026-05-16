"""
Tests for kerf_cad_core.procsim.moldflow

Coverage (>=25 hermetic tests):
  1   ΔP ∝ L (linear in flow length) within 1% band
  2   ΔP ∝ 1/h³ for Newtonian (slot flow, n=1)
  3   ΔP ∝ 1/t_wall³ via h=t_wall/2 (Newtonian slot)
  4   Clamp tonnage = projected_area × cavity_pressure / (1000 g)
  5   Cooling time ∝ t_wall² (ratio test)
  6   Cooling time ∝ 1/α (ratio test via two materials)
  7   Cooling time contains ln(...) factor correctly
  8   Thinner wall → earlier freeze-off (shorter fill time before frozen)
  9   Very thin wall → short_shot flagged; thick wall → not flagged
  10  Two gates → one weld line at midpoint
  11  Three gates → two weld lines at expected positions
  12  Single hole → weld line just downstream of hole
  13  No holes, one gate → no weld lines
  14  Rib-to-wall > 0.6 → sink_mark_risk True
  15  Rib-to-wall ≤ 0.6 → sink_mark_risk False
  16  Rib-to-wall = 0 → sink_mark_risk False
  17  Balanced runner (n_cavities=4) → all cavity fill times equal
  18  Unbalanced runner (n_cavities=4) → fill times differ monotonically
  19  Shear rate over limit flagged for very high flow rate
  20  Normal shear rate not flagged
  21  Invalid flow_length_m ≤ 0 → ok=False, no raise
  22  Invalid t_wall_m ≤ 0 → ok=False, no raise
  23  Unknown material → ok=False, no raise
  24  n_gates < 1 → ok=False, no raise
  25  cooling_time() standalone: ΔP increases with longer flow at fixed geometry
  26  Pressure-drop scan ΔP list has correct length and is monotone in L
  27  Cooling time standalone bad temperature order → ok=False
  28  Gate diameter scales with sqrt of part area
  29  Runner diameter scales with cube-root of n_cavities
  30  ΔP is independent of width in a slot (only via shear-rate) — verify slot formula
"""
from __future__ import annotations

import math
import sys
import os

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "src"),
)

from kerf_cad_core.procsim.moldflow import (
    cooling_time,
    moldflow_fill,
    pressure_drop_scan,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fill(**kwargs):
    """Convenience wrapper: sensible defaults for a 200 mm × 100 mm × 3 mm cavity."""
    defaults = dict(
        flow_length_m=0.20,
        t_wall_m=0.003,
        width_m=0.10,
        flow_rate_m3s=1e-5,
        material="abs",
    )
    defaults.update(kwargs)
    return moldflow_fill(**defaults)


# ---------------------------------------------------------------------------
# 1. ΔP ∝ L (linear in flow length)
# ---------------------------------------------------------------------------

def test_pressure_drop_proportional_to_L():
    r1 = _fill(flow_length_m=0.10)
    r2 = _fill(flow_length_m=0.20)
    r3 = _fill(flow_length_m=0.40)
    assert r1["ok"] and r2["ok"] and r3["ok"]
    dp1, dp2, dp3 = r1["pressure_drop_Pa"], r2["pressure_drop_Pa"], r3["pressure_drop_Pa"]
    # ΔP ∝ L → ratio should be 2:1 and 4:1 within 1%
    assert abs(dp2 / dp1 - 2.0) < 0.02, f"ratio {dp2/dp1}"
    assert abs(dp3 / dp1 - 4.0) < 0.02, f"ratio {dp3/dp1}"


# ---------------------------------------------------------------------------
# 2. ΔP ∝ 1/h³ for Newtonian melt (n=1 via custom — use pp which is n≈0.38,
#    so we verify the inverse-power law approximately through the slot formula)
# ---------------------------------------------------------------------------

def test_pressure_drop_inverse_halfgap_cube():
    """For Newtonian (n=1) slot flow: ΔP ∝ h^{-(n+2)} = h^{-3}.
    We use the _slot_pressure_drop directly via two different wall thicknesses
    and check the ratio matches (h2/h1)^{-(n+2)}.
    """
    from kerf_cad_core.procsim.moldflow import _slot_pressure_drop
    K, n_val = 100.0, 1.0  # Newtonian
    L, W, Q = 0.2, 0.1, 1e-5
    h1 = 0.002
    h2 = 0.004  # double the half-gap
    dp1 = _slot_pressure_drop(L, W, h1, Q, K, n_val)
    dp2 = _slot_pressure_drop(L, W, h2, Q, K, n_val)
    # ΔP ∝ h^{-(n+2)} = h^{-3} → ratio = (h1/h2)^3 = (0.002/0.004)^3 = 0.125
    expected_ratio = (h1 / h2) ** (n_val + 2)
    actual_ratio = dp2 / dp1
    assert abs(actual_ratio - expected_ratio) < 1e-6, \
        f"Expected ratio {expected_ratio}, got {actual_ratio}"


# ---------------------------------------------------------------------------
# 3. ΔP ∝ 1/t_wall³ via slot formula (t_wall = 2h, Newtonian)
# ---------------------------------------------------------------------------

def test_pressure_drop_inverse_twall_cube():
    """Doubling t_wall (hence h) for Newtonian melt halves ΔP by 2^3=8."""
    from kerf_cad_core.procsim.moldflow import _slot_pressure_drop
    K, n_val = 100.0, 1.0
    L, W, Q = 0.2, 0.1, 1e-5
    t1, t2 = 0.002, 0.004  # t_wall values → h = t/2
    dp1 = _slot_pressure_drop(L, W, t1 / 2, Q, K, n_val)
    dp2 = _slot_pressure_drop(L, W, t2 / 2, Q, K, n_val)
    ratio = dp1 / dp2
    assert abs(ratio - 8.0) < 1e-4, f"Expected 8, got {ratio}"


# ---------------------------------------------------------------------------
# 4. Clamp tonnage = projected_area × cavity_pressure
# ---------------------------------------------------------------------------

def test_clamp_tonnage_formula():
    r = _fill(flow_length_m=0.20, width_m=0.10)
    assert r["ok"]
    projected_area = 0.20 * 0.10  # [m²]
    p_avg = r["pressure_drop_Pa"] / 2.0
    expected_N = projected_area * p_avg
    expected_t = expected_N / (1000.0 * 9.80665)
    assert abs(r["clamp_force_N"] - expected_N) < 1.0
    assert abs(r["clamp_tonnage_t"] - expected_t) < 1e-6


# ---------------------------------------------------------------------------
# 5. Cooling time ∝ t_wall²
# ---------------------------------------------------------------------------

def test_cooling_time_proportional_to_twall_squared():
    r1 = cooling_time(t_wall_m=0.002, material="abs")
    r2 = cooling_time(t_wall_m=0.004, material="abs")
    assert r1["ok"] and r2["ok"]
    tc1, tc2 = r1["cooling_time_s"], r2["cooling_time_s"]
    # Both use the same C_cool so: t_cool ∝ t_wall² → ratio = (0.004/0.002)² = 4
    assert abs(tc2 / tc1 - 4.0) < 0.01, f"ratio {tc2/tc1}"


# ---------------------------------------------------------------------------
# 6. Cooling time ∝ 1/α (ratio test: use two materials with different α)
# ---------------------------------------------------------------------------

def test_cooling_time_inversely_proportional_to_alpha():
    r_abs = cooling_time(t_wall_m=0.003, material="abs")
    r_pe = cooling_time(t_wall_m=0.003, material="pe")
    assert r_abs["ok"] and r_pe["ok"]
    alpha_abs = r_abs["thermal_diffusivity_m2s"]
    alpha_pe = r_pe["thermal_diffusivity_m2s"]
    tc_abs = r_abs["cooling_time_s"]
    tc_pe = r_pe["cooling_time_s"]
    # t_cool ∝ 1/α × ln(C) — C_cool differs between materials; check the
    # alpha-only contribution using the formula: t ∝ 1/α
    # We confirm the sign: larger α → shorter cooling time
    assert (alpha_pe > alpha_abs) == (tc_pe < tc_abs) or \
           (alpha_pe < alpha_abs) == (tc_pe > tc_abs)


# ---------------------------------------------------------------------------
# 7. Cooling time contains ln(C_cool) correctly
# ---------------------------------------------------------------------------

def test_cooling_time_ln_factor():
    r = cooling_time(t_wall_m=0.003, material="abs")
    assert r["ok"]
    C = r["C_cool"]
    alpha = r["thermal_diffusivity_m2s"]
    t_wall = 0.003
    expected = (t_wall ** 2 / (math.pi ** 2 * alpha)) * math.log(C)
    assert abs(r["cooling_time_s"] - expected) < 1e-12


# ---------------------------------------------------------------------------
# 8. Thinner wall → earlier freeze-off (shorter fill time before frozen)
# ---------------------------------------------------------------------------

def test_thinner_wall_earlier_freeze_off():
    r_thin = _fill(t_wall_m=0.001, flow_rate_m3s=1e-6)
    r_thick = _fill(t_wall_m=0.005, flow_rate_m3s=1e-6)
    assert r_thin["ok"] and r_thick["ok"]
    # Thinner wall has smaller half-gap → frozen layer is a larger fraction of h
    t_thin_h = 0.001 / 2.0
    t_thick_h = 0.005 / 2.0
    thin_ratio = r_thin["frozen_layer_m"] / t_thin_h
    thick_ratio = r_thick["frozen_layer_m"] / t_thick_h
    assert thin_ratio >= thick_ratio, \
        f"thin ratio {thin_ratio:.3f} should >= thick ratio {thick_ratio:.3f}"


# ---------------------------------------------------------------------------
# 9. Very thin wall → short_shot True; thick wall → not flagged
# ---------------------------------------------------------------------------

def test_short_shot_thin_wall():
    # Very thin wall, low flow rate → fill time long → frozen layer grows → short shot
    r_thin = _fill(t_wall_m=0.0005, flow_rate_m3s=1e-8)
    assert r_thin["ok"]
    assert r_thin["short_shot"] is True


def test_no_short_shot_thick_wall():
    # Thick wall, high flow rate → fill time short → no short shot
    r_thick = _fill(t_wall_m=0.010, flow_rate_m3s=1e-4)
    assert r_thick["ok"]
    assert r_thick["short_shot"] is False


# ---------------------------------------------------------------------------
# 10. Two gates → one weld line at midpoint
# ---------------------------------------------------------------------------

def test_two_gates_one_weld_line_at_midpoint():
    L = 0.20
    r = _fill(flow_length_m=L, n_gates=2)
    assert r["ok"]
    wls = r["weld_line_positions_m"]
    assert len(wls) == 1, f"Expected 1 weld line, got {len(wls)}"
    assert abs(wls[0] - L / 2.0) < 1e-9, f"Weld line at {wls[0]}, expected {L/2}"


# ---------------------------------------------------------------------------
# 11. Three gates → two weld lines at expected positions
# ---------------------------------------------------------------------------

def test_three_gates_two_weld_lines():
    L = 0.30
    r = _fill(flow_length_m=L, n_gates=3)
    assert r["ok"]
    wls = r["weld_line_positions_m"]
    # 3 gates at 0, L/2, L → weld lines at L/4 and 3L/4
    assert len(wls) == 2, f"Expected 2 weld lines, got {len(wls)}"
    assert abs(wls[0] - L / 4.0) < 1e-9
    assert abs(wls[1] - 3 * L / 4.0) < 1e-9


# ---------------------------------------------------------------------------
# 12. Single hole → weld line just downstream of hole
# ---------------------------------------------------------------------------

def test_hole_creates_weld_line():
    L = 0.20
    d_hole = 0.010  # 10 mm hole
    r = _fill(flow_length_m=L, n_holes=1, hole_diameter_m=d_hole)
    assert r["ok"]
    wls = r["weld_line_positions_m"]
    # Hole centre at L/2 = 0.10; weld line at 0.10 + 0.005 = 0.105
    expected_wl = L / 2.0 + d_hole / 2.0
    assert any(abs(w - expected_wl) < 1e-9 for w in wls), \
        f"Weld line at {expected_wl:.4f} not found in {wls}"


# ---------------------------------------------------------------------------
# 13. No holes, one gate → no weld lines
# ---------------------------------------------------------------------------

def test_single_gate_no_holes_no_weld_lines():
    r = _fill(n_gates=1, n_holes=0)
    assert r["ok"]
    assert r["weld_line_positions_m"] == []


# ---------------------------------------------------------------------------
# 14. Rib-to-wall > 0.6 → sink_mark_risk True
# ---------------------------------------------------------------------------

def test_sink_mark_risk_high_ratio():
    r = _fill(rib_wall_ratio=0.7)
    assert r["ok"]
    assert r["sink_mark_risk"] is True


# ---------------------------------------------------------------------------
# 15. Rib-to-wall ≤ 0.6 → sink_mark_risk False
# ---------------------------------------------------------------------------

def test_sink_mark_risk_safe_ratio():
    r = _fill(rib_wall_ratio=0.5)
    assert r["ok"]
    assert r["sink_mark_risk"] is False


def test_sink_mark_risk_exactly_at_limit():
    r = _fill(rib_wall_ratio=0.6)
    assert r["ok"]
    # 0.6 is the boundary — not strictly greater so False
    assert r["sink_mark_risk"] is False


# ---------------------------------------------------------------------------
# 16. Rib-to-wall = 0 → sink_mark_risk False
# ---------------------------------------------------------------------------

def test_sink_mark_risk_zero():
    r = _fill(rib_wall_ratio=0.0)
    assert r["ok"]
    assert r["sink_mark_risk"] is False


# ---------------------------------------------------------------------------
# 17. Balanced runner (n_cavities=4) → all cavity fill times equal
# ---------------------------------------------------------------------------

def test_balanced_runner_equal_fill_times():
    r = _fill(n_cavities=4, runner_balanced=True)
    assert r["ok"]
    times = r["cavity_fill_times_s"]
    assert len(times) == 4
    assert r["runner_balanced_equal"] is True
    assert all(abs(t - times[0]) < 1e-12 for t in times)


# ---------------------------------------------------------------------------
# 18. Unbalanced runner (n_cavities=4) → fill times differ monotonically
# ---------------------------------------------------------------------------

def test_unbalanced_runner_unequal_fill_times():
    r = _fill(n_cavities=4, runner_balanced=False)
    assert r["ok"]
    times = r["cavity_fill_times_s"]
    assert len(times) == 4
    assert r["runner_balanced_equal"] is False
    # Times should be strictly increasing
    for i in range(len(times) - 1):
        assert times[i] < times[i + 1], f"times not increasing: {times}"


# ---------------------------------------------------------------------------
# 19. Shear rate over limit flagged for very high flow rate
# ---------------------------------------------------------------------------

def test_shear_rate_over_limit_high_flow():
    # Very high flow rate → large shear rate
    r = _fill(flow_rate_m3s=0.01, t_wall_m=0.001)
    assert r["ok"]
    assert r["shear_rate_over_limit"] is True


# ---------------------------------------------------------------------------
# 20. Normal shear rate not flagged
# ---------------------------------------------------------------------------

def test_shear_rate_not_over_limit_normal():
    # Low flow rate, thick wall → low shear rate
    r = _fill(flow_rate_m3s=1e-7, t_wall_m=0.005)
    assert r["ok"]
    assert r["shear_rate_over_limit"] is False


# ---------------------------------------------------------------------------
# 21. Invalid flow_length_m ≤ 0 → ok=False, no raise
# ---------------------------------------------------------------------------

def test_invalid_flow_length_zero():
    r = moldflow_fill(flow_length_m=0.0, t_wall_m=0.003, width_m=0.1, flow_rate_m3s=1e-5)
    assert r["ok"] is False
    assert "reason" in r


def test_invalid_flow_length_negative():
    r = moldflow_fill(flow_length_m=-0.1, t_wall_m=0.003, width_m=0.1, flow_rate_m3s=1e-5)
    assert r["ok"] is False
    assert "reason" in r


# ---------------------------------------------------------------------------
# 22. Invalid t_wall_m ≤ 0 → ok=False, no raise
# ---------------------------------------------------------------------------

def test_invalid_twall_zero():
    r = moldflow_fill(flow_length_m=0.2, t_wall_m=0.0, width_m=0.1, flow_rate_m3s=1e-5)
    assert r["ok"] is False
    assert "reason" in r


# ---------------------------------------------------------------------------
# 23. Unknown material → ok=False, no raise
# ---------------------------------------------------------------------------

def test_unknown_material():
    r = moldflow_fill(
        flow_length_m=0.2, t_wall_m=0.003, width_m=0.1,
        flow_rate_m3s=1e-5, material="unobtainium"
    )
    assert r["ok"] is False
    assert "reason" in r


# ---------------------------------------------------------------------------
# 24. n_gates < 1 → ok=False, no raise
# ---------------------------------------------------------------------------

def test_invalid_n_gates():
    r = moldflow_fill(
        flow_length_m=0.2, t_wall_m=0.003, width_m=0.1,
        flow_rate_m3s=1e-5, n_gates=0
    )
    assert r["ok"] is False
    assert "reason" in r


# ---------------------------------------------------------------------------
# 25. Pressure-drop increases with longer flow at fixed geometry
# ---------------------------------------------------------------------------

def test_pressure_drop_increases_with_flow_length():
    r1 = _fill(flow_length_m=0.10)
    r2 = _fill(flow_length_m=0.30)
    assert r1["ok"] and r2["ok"]
    assert r2["pressure_drop_Pa"] > r1["pressure_drop_Pa"]


# ---------------------------------------------------------------------------
# 26. pressure_drop_scan list has correct length and is monotone in L
# ---------------------------------------------------------------------------

def test_pressure_drop_scan_monotone():
    Ls = [0.05, 0.10, 0.20, 0.40]
    r = pressure_drop_scan(
        flow_lengths_m=Ls,
        t_wall_m=0.003,
        width_m=0.10,
        flow_rate_m3s=1e-5,
        material="abs",
    )
    assert r["ok"]
    dps = r["pressure_drop_Pa"]
    assert len(dps) == len(Ls)
    for i in range(len(dps) - 1):
        assert dps[i] < dps[i + 1], f"Not monotone: {dps}"


# ---------------------------------------------------------------------------
# 27. Cooling time standalone bad temperature order → ok=False
# ---------------------------------------------------------------------------

def test_cooling_time_bad_temperature():
    # T_mould > T_melt — degenerate
    r = cooling_time(t_wall_m=0.003, material="abs", T_melt_C=50.0, T_mould_C=200.0)
    assert r["ok"] is False
    assert "reason" in r


def test_cooling_time_eject_equals_mould():
    # T_eject == T_mould — degenerate
    r = cooling_time(t_wall_m=0.003, material="abs", T_melt_C=230.0,
                     T_mould_C=80.0, T_eject_C=80.0)
    assert r["ok"] is False
    assert "reason" in r


# ---------------------------------------------------------------------------
# 28. Gate diameter scales with sqrt of part area
# ---------------------------------------------------------------------------

def test_gate_diameter_scales_with_sqrt_area():
    r1 = _fill(flow_length_m=0.10, width_m=0.10)
    r2 = _fill(flow_length_m=0.40, width_m=0.10)
    assert r1["ok"] and r2["ok"]
    # Area ratio = 4 → gate_d ratio = sqrt(4) = 2  (same t_wall)
    d1 = r1["gate_diameter_m"]
    d2 = r2["gate_diameter_m"]
    assert abs(d2 / d1 - 2.0) < 0.01, f"Gate d ratio {d2/d1}"


# ---------------------------------------------------------------------------
# 29. Runner diameter scales with cube-root of n_cavities
# ---------------------------------------------------------------------------

def test_runner_diameter_cube_root_cavities():
    r1 = _fill(n_cavities=1)
    r8 = _fill(n_cavities=8)
    assert r1["ok"] and r8["ok"]
    # runner_d ∝ n^(1/3) → ratio = 8^(1/3) = 2
    ratio = r8["runner_diameter_m"] / r1["runner_diameter_m"]
    assert abs(ratio - 2.0) < 1e-9, f"Runner d ratio {ratio}"


# ---------------------------------------------------------------------------
# 30. ΔP slot formula cross-check (ratio via _slot_pressure_drop directly)
# ---------------------------------------------------------------------------

def test_slot_pressure_drop_newtonian_cross_check():
    """For Newtonian (n=1) slit flow: ΔP = 6 η Q L / (W h³) × correction.
    Check that halving flow rate halves ΔP (linear in Q for n=1).
    """
    from kerf_cad_core.procsim.moldflow import _slot_pressure_drop
    K, n_val = 1000.0, 1.0
    L, W, h = 0.2, 0.1, 0.002
    Q1 = 1e-5
    Q2 = 2e-5
    dp1 = _slot_pressure_drop(L, W, h, Q1, K, n_val)
    dp2 = _slot_pressure_drop(L, W, h, Q2, K, n_val)
    assert abs(dp2 / dp1 - 2.0) < 1e-6, f"Ratio {dp2/dp1}, expected 2.0"
