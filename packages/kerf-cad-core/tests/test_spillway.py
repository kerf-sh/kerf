"""
Hermetic tests for kerf_cad_core.spillway — dam & spillway hydraulics.

All tests are pure-Python, deterministic, and independent of OCC / DB / network.
Numeric results are verified against USBR hand-calculations or direct
algebraic derivations.

Sections covered
----------------
  design.ogee_discharge          — WES discharge formula & corrections
  design.ogee_crest_profile      — coordinate table shape & apex
  design.orifice_discharge       — free-flow and submerged gate
  design.chute_velocity          — normal depth & terminal velocity
  design.stilling_basin          — Bélanger sequent depth, basin type
  design.energy_dissipation      — toe energy, apron length
  design.scour_depth             — Lacey and Mason methods
  design.flood_routing_puls      — modified-Puls level-pool routing
  design.dam_freeboard           — wave height & freeboard
  design.gravity_dam_stability   — overturning / sliding / middle-third
  plugin._TOOL_MODULES           — registration check

References
----------
USBR (1977) Design of Small Dams, 3rd ed.
Chaudhry, M.H. (2008) Open-Channel Hydraulics, 2nd ed.
Lacey, G. (1930) Stable Channels in Alluvium.  Proc. ICE.

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math

import pytest

from kerf_cad_core.spillway.design import (
    _G,
    ogee_discharge,
    ogee_crest_profile,
    orifice_discharge,
    chute_velocity,
    stilling_basin,
    energy_dissipation,
    scour_depth,
    flood_routing_puls,
    dam_freeboard,
    gravity_dam_stability,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _ctx():
    class _Ctx:
        project_id = "test"
    return _Ctx()


def _args(**kwargs) -> bytes:
    return json.dumps(kwargs).encode()


# ===========================================================================
# ogee_discharge
# ===========================================================================

class TestOgeeDischarge:
    def test_basic_design_head(self):
        """At design head, C = C0 (k_h = 1), no contractions or submergence."""
        r = ogee_discharge(design_head_m=2.0, actual_head_m=2.0, crest_length_m=10.0)
        assert r["ok"]
        # Q = 2.21 * 10 * 2.0^1.5 = 2.21 * 10 * 2.828... ≈ 62.51
        Q_expected = 2.21 * 10.0 * 2.0 ** 1.5
        assert abs(r["discharge_m3s"] - Q_expected) < 0.1

    def test_ovehead_cavitation_warning(self):
        """He/Hd > 1.33 should trigger cavitation warning."""
        r = ogee_discharge(design_head_m=1.0, actual_head_m=1.5, crest_length_m=5.0)
        assert r["ok"]
        assert any("cavitation" in w for w in r["warnings"])

    def test_underhead_low_pressure_warning(self):
        """He/Hd < 0.5 should trigger sub-atmospheric warning."""
        r = ogee_discharge(design_head_m=2.0, actual_head_m=0.5, crest_length_m=5.0)
        assert r["ok"]
        assert any("sub-atmospheric" in w.lower() or "below atmospheric" in w.lower()
                   for w in r["warnings"])

    def test_end_contractions_reduce_length(self):
        """Two end contractions should reduce effective length."""
        r_no = ogee_discharge(
            design_head_m=2.0, actual_head_m=2.0, crest_length_m=10.0,
            num_end_contractions=0,
        )
        r_two = ogee_discharge(
            design_head_m=2.0, actual_head_m=2.0, crest_length_m=10.0,
            num_end_contractions=2,
        )
        assert r_two["L_eff_m"] < r_no["L_eff_m"]
        assert r_two["discharge_m3s"] < r_no["discharge_m3s"]

    def test_submergence_reduces_discharge(self):
        """Positive tailwater should reduce discharge via Villemonte."""
        r_free = ogee_discharge(
            design_head_m=2.0, actual_head_m=2.0, crest_length_m=10.0, tailwater_m=0.0
        )
        r_sub = ogee_discharge(
            design_head_m=2.0, actual_head_m=2.0, crest_length_m=10.0, tailwater_m=1.0
        )
        assert r_sub["discharge_m3s"] < r_free["discharge_m3s"]
        assert r_sub["submergence_factor"] < 1.0

    def test_invalid_design_head(self):
        r = ogee_discharge(design_head_m=-1.0, actual_head_m=2.0, crest_length_m=5.0)
        assert not r["ok"]

    def test_invalid_contractions(self):
        r = ogee_discharge(
            design_head_m=2.0, actual_head_m=2.0, crest_length_m=5.0,
            num_end_contractions=3,
        )
        assert not r["ok"]

    def test_approach_velocity_increases_he(self):
        """Shallow approach increases He via velocity head."""
        r_deep = ogee_discharge(
            design_head_m=2.0, actual_head_m=2.0, crest_length_m=10.0,
            approach_depth_m=20.0,
        )
        r_shallow = ogee_discharge(
            design_head_m=2.0, actual_head_m=2.0, crest_length_m=10.0,
            approach_depth_m=0.5,
        )
        # Shallow approach has higher approach velocity → higher He_total
        assert r_shallow["He_m"] >= r_deep["He_m"]


# ===========================================================================
# ogee_crest_profile
# ===========================================================================

class TestOgeeCrestProfile:
    def test_apex_at_origin(self):
        """Profile must contain the apex at (0, 0)."""
        r = ogee_crest_profile(design_head_m=3.0)
        assert r["ok"]
        apex = next((p for p in r["profile"] if p["x_m"] == 0.0 and p["y_m"] == 0.0), None)
        assert apex is not None

    def test_downstream_y_negative(self):
        """Downstream points (x > 0) must have y <= 0."""
        r = ogee_crest_profile(design_head_m=2.0)
        assert r["ok"]
        for p in r["profile"]:
            if p["x_m"] > 0:
                assert p["y_m"] <= 0.0

    def test_downstream_power_law(self):
        """y/Hd = -0.5*(x/Hd)^1.85 for downstream quadrant."""
        Hd = 2.0
        r = ogee_crest_profile(design_head_m=Hd, n_downstream=10)
        assert r["ok"]
        # Check the last point
        last = [p for p in r["profile"] if p["x_m"] > 0][-1]
        x = last["x_m"]
        y_expected = -0.5 * Hd * (x / Hd) ** 1.85
        assert abs(last["y_m"] - y_expected) < 1e-3

    def test_profile_point_count(self):
        """Profile should have approximately n_upstream + 1 + n_downstream points."""
        r = ogee_crest_profile(design_head_m=1.5, n_upstream=8, n_downstream=20)
        assert r["ok"]
        assert len(r["profile"]) == 8 + 1 + 20


# ===========================================================================
# orifice_discharge
# ===========================================================================

class TestOrificeDischarge:
    def test_free_flow(self):
        """Free-flow orifice: Q = Cd*A*sqrt(2g*(Hu - a/2))."""
        a, W, Hu = 1.0, 3.0, 5.0
        Cd = 0.61
        A = a * W
        h_eff = Hu - a / 2.0
        Q_exp = Cd * A * math.sqrt(2 * _G * h_eff)
        r = orifice_discharge(gate_opening_m=a, gate_width_m=W, head_upstream_m=Hu, Cd=Cd)
        assert r["ok"]
        assert r["flow_condition"] == "free"
        assert abs(r["discharge_m3s"] - Q_exp) < 0.01

    def test_submerged_flow(self):
        """When tailwater > gate opening, switches to submerged flow."""
        r = orifice_discharge(
            gate_opening_m=0.5, gate_width_m=2.0, head_upstream_m=4.0,
            head_downstream_m=2.0,  # tailwater > gate opening
        )
        assert r["ok"]
        assert r["flow_condition"] == "submerged"
        # Q = 0.61 * 0.5*2 * sqrt(2*9.81*(4-2))
        Q_exp = 0.61 * 1.0 * math.sqrt(2 * _G * 2.0)
        assert abs(r["discharge_m3s"] - Q_exp) < 0.01

    def test_reverse_flow(self):
        """Upstream head < downstream head → reverse flow warning, Q=0."""
        r = orifice_discharge(
            gate_opening_m=1.0, gate_width_m=2.0, head_upstream_m=1.5,
            head_downstream_m=3.0,
        )
        assert r["ok"]
        assert r["discharge_m3s"] == 0.0
        assert r["flow_condition"] == "reverse"

    def test_invalid_inputs(self):
        r = orifice_discharge(gate_opening_m=-1.0, gate_width_m=2.0, head_upstream_m=3.0)
        assert not r["ok"]

    def test_invalid_cd(self):
        r = orifice_discharge(gate_opening_m=1.0, gate_width_m=2.0,
                              head_upstream_m=3.0, Cd=0.0)
        assert not r["ok"]


# ===========================================================================
# chute_velocity
# ===========================================================================

class TestChuteVelocity:
    def test_manning_consistency(self):
        """Check that V_n * A_n ≈ Q (Manning consistency)."""
        Q, W, S, n = 20.0, 4.0, 0.1, 0.013
        r = chute_velocity(flow_m3s=Q, chute_width_m=W, chute_slope=S, manning_n=n)
        assert r["ok"]
        # V * A should equal Q
        V = r["terminal_velocity_m_s"]
        A = r["flow_area_m2"]
        assert abs(V * A - Q) < 0.05

    def test_steep_slope_warning(self):
        """Slope > 0.3 should trigger structural warning."""
        r = chute_velocity(flow_m3s=5.0, chute_width_m=2.0, chute_slope=0.4, manning_n=0.013)
        assert r["ok"]
        assert any("slope" in w.lower() for w in r["warnings"])

    def test_downstream_velocity_greater(self):
        """Downstream velocity after drop should exceed terminal velocity."""
        r = chute_velocity(
            flow_m3s=10.0, chute_width_m=3.0, chute_slope=0.05, manning_n=0.015,
            chute_length_m=50.0,
        )
        assert r["ok"]
        assert r["downstream_velocity_m_s"] > r["terminal_velocity_m_s"]

    def test_froude_supercritical_chute(self):
        """Steep chute should yield Fr > 1."""
        r = chute_velocity(flow_m3s=15.0, chute_width_m=3.0, chute_slope=0.1, manning_n=0.013)
        assert r["ok"]
        assert r["froude_number"] > 1.0

    def test_invalid_slope(self):
        r = chute_velocity(flow_m3s=10.0, chute_width_m=3.0, chute_slope=-0.01, manning_n=0.013)
        assert not r["ok"]


# ===========================================================================
# stilling_basin
# ===========================================================================

class TestStillingBasin:
    def test_belanger_sequent_depth(self):
        """Verify Bélanger equation: y2 = (y1/2)*(sqrt(1+8*Fr1²)-1)."""
        y1, Q, W = 0.4, 20.0, 5.0
        V1 = Q / (y1 * W)
        Fr1 = V1 / math.sqrt(_G * y1)
        y2_expected = (y1 / 2.0) * (math.sqrt(1.0 + 8.0 * Fr1 ** 2) - 1.0)
        r = stilling_basin(
            upstream_depth_m=y1, flow_m3s=Q, chute_width_m=W, tailwater_depth_m=y2_expected
        )
        assert r["ok"]
        assert abs(r["depth2_m"] - y2_expected) < 0.01

    def test_type_iii_basin(self):
        """Fr1 > 4.5 should select Type III basin."""
        # Fr1 = V1/sqrt(g*y1); set V1 high
        y1 = 0.3
        Q = 0.3 * 5.0 * math.sqrt(_G * y1) * 6.0  # Fr1 ≈ 6
        W = 5.0
        r = stilling_basin(
            upstream_depth_m=y1, flow_m3s=Q, chute_width_m=W,
            tailwater_depth_m=0.0,
        )
        assert r["ok"]
        assert r["basin_type"] == "III"

    def test_type_ii_basin(self):
        """Fr1 ≈ 3.5 should select Type II basin."""
        y1 = 0.5
        Q = 0.5 * 4.0 * math.sqrt(_G * y1) * 3.5  # Fr1 ≈ 3.5
        W = 4.0
        r = stilling_basin(
            upstream_depth_m=y1, flow_m3s=Q, chute_width_m=W,
            tailwater_depth_m=0.0,
        )
        assert r["ok"]
        assert r["basin_type"] == "II"

    def test_sweepout_warning(self):
        """TW < y2 should produce sweepout warning."""
        y1 = 0.3
        W = 5.0
        Q = 25.0
        r = stilling_basin(
            upstream_depth_m=y1, flow_m3s=Q, chute_width_m=W,
            tailwater_depth_m=0.01,  # far below y2
        )
        assert r["ok"]
        assert any("sweep" in w.lower() or "floor must be depressed" in w.lower()
                   for w in r["warnings"])

    def test_undular_low_fr(self):
        """Fr1 < 1.7 should give undular basin type."""
        y1 = 2.0
        W = 5.0
        Q = W * y1 * 1.3 * math.sqrt(_G * y1)  # Fr1 ≈ 1.3
        r = stilling_basin(
            upstream_depth_m=y1, flow_m3s=Q, chute_width_m=W,
            tailwater_depth_m=y1,
        )
        assert r["ok"]
        assert r["basin_type"] == "undular"

    def test_energy_loss_positive(self):
        """Energy loss across jump must be positive."""
        r = stilling_basin(
            upstream_depth_m=0.4, flow_m3s=20.0, chute_width_m=5.0,
            tailwater_depth_m=2.0,
        )
        assert r["ok"]
        assert r["energy_loss_m"] > 0

    def test_invalid_inputs(self):
        r = stilling_basin(
            upstream_depth_m=-0.1, flow_m3s=10.0, chute_width_m=3.0,
            tailwater_depth_m=1.0,
        )
        assert not r["ok"]


# ===========================================================================
# energy_dissipation
# ===========================================================================

class TestEnergyDissipation:
    def test_energy_at_toe_formula(self):
        """E_toe = y_ds + V_toe²/(2g)."""
        H_up = 15.0
        y_ds = 1.0
        Q = 30.0
        W = 5.0
        r = energy_dissipation(
            upstream_head_m=H_up, downstream_depth_m=y_ds,
            flow_m3s=Q, basin_width_m=W,
        )
        assert r["ok"]
        V_toe = math.sqrt(2 * _G * (H_up - y_ds))
        E_toe_expected = y_ds + V_toe ** 2 / (2 * _G)
        assert abs(r["energy_at_toe_m"] - E_toe_expected) < 0.01

    def test_apron_length_positive(self):
        """Apron length must be positive."""
        r = energy_dissipation(
            upstream_head_m=10.0, downstream_depth_m=0.5,
            flow_m3s=20.0, basin_width_m=4.0,
        )
        assert r["ok"]
        assert r["apron_length_m"] > 0

    def test_basin_plus_protection(self):
        """Total apron = basin_length + downstream_protection."""
        r = energy_dissipation(
            upstream_head_m=8.0, downstream_depth_m=0.8,
            flow_m3s=15.0, basin_width_m=3.0,
        )
        assert r["ok"]
        assert abs(
            r["apron_length_m"] - r["basin_length_m"] - r["downstream_protection_length_m"]
        ) < 1e-6


# ===========================================================================
# scour_depth
# ===========================================================================

class TestScourDepth:
    def test_lacey_formula(self):
        """Lacey: d = 0.47*(Q/f)^(1/3), f = 1.76*sqrt(d50)."""
        Q, W, d50 = 50.0, 10.0, 1.0
        f = 1.76 * math.sqrt(d50)
        d_expected = 0.47 * (Q / f) ** (1 / 3)
        r = scour_depth(flow_m3s=Q, channel_width_m=W, d50_mm=d50, method="lacey")
        assert r["ok"]
        assert abs(r["scour_depth_m"] - d_expected) < 0.01

    def test_mason_method(self):
        """Mason method should return positive scour > 0."""
        r = scour_depth(
            flow_m3s=100.0, channel_width_m=15.0, d50_mm=0.5,
            method="mason", head_drop_m=20.0,
        )
        assert r["ok"]
        assert r["scour_depth_m"] > 0
        assert r["method"] == "mason"

    def test_lacey_silt_factor_returned(self):
        """Lacey method should return lacey_silt_factor."""
        r = scour_depth(flow_m3s=20.0, channel_width_m=5.0, d50_mm=2.0, method="lacey")
        assert r["ok"]
        assert "lacey_silt_factor" in r

    def test_invalid_method(self):
        r = scour_depth(flow_m3s=20.0, channel_width_m=5.0, d50_mm=2.0, method="unknown")
        assert not r["ok"]

    def test_mason_requires_head(self):
        """Mason method requires head_drop_m."""
        r = scour_depth(flow_m3s=20.0, channel_width_m=5.0, d50_mm=1.0, method="mason")
        assert not r["ok"]


# ===========================================================================
# flood_routing_puls
# ===========================================================================

class TestFloodRoutingPuls:
    def _simple_hydrograph(self):
        """Triangular inflow hydrograph, dt = 3600 s."""
        times = [0, 3600, 7200, 10800, 14400, 18000]
        flows = [0, 50, 100, 80, 40, 0]
        return list(zip(times, flows))

    def _simple_sd(self):
        """Simple linear storage-discharge: Q = S / 18000."""
        pairs = []
        for S in range(0, 2_000_001, 100_000):
            Q = S / 18000.0
            pairs.append((float(S), round(Q, 4)))
        return pairs

    def test_basic_routing(self):
        """Basic routing: outflow hydrograph should have same length as routing steps."""
        r = flood_routing_puls(
            inflow_hydrograph=self._simple_hydrograph(),
            storage_discharge_pairs=self._simple_sd(),
            dt_s=3600.0,
        )
        assert r["ok"]
        assert len(r["outflow_hydrograph"]) >= 2

    def test_peak_attenuation(self):
        """Peak outflow must be <= peak inflow (reservoir attenuates)."""
        r = flood_routing_puls(
            inflow_hydrograph=self._simple_hydrograph(),
            storage_discharge_pairs=self._simple_sd(),
            dt_s=3600.0,
        )
        assert r["ok"]
        assert r["peak_outflow_m3s"] <= 100.0

    def test_initial_storage(self):
        """Non-zero initial storage should shift the initial outflow up."""
        r0 = flood_routing_puls(
            inflow_hydrograph=self._simple_hydrograph(),
            storage_discharge_pairs=self._simple_sd(),
            dt_s=3600.0,
            initial_storage_m3=0.0,
        )
        r1 = flood_routing_puls(
            inflow_hydrograph=self._simple_hydrograph(),
            storage_discharge_pairs=self._simple_sd(),
            dt_s=3600.0,
            initial_storage_m3=360000.0,  # 20 m³/s equivalent
        )
        assert r0["ok"] and r1["ok"]
        assert r1["outflow_hydrograph"][0]["outflow_m3s"] > r0["outflow_hydrograph"][0]["outflow_m3s"]

    def test_invalid_hydrograph(self):
        """Hydrograph with non-increasing time must fail."""
        bad = [(0, 10), (7200, 50), (3600, 30)]  # not monotone
        r = flood_routing_puls(
            inflow_hydrograph=bad,
            storage_discharge_pairs=self._simple_sd(),
            dt_s=3600.0,
        )
        assert not r["ok"]

    def test_short_hydrograph(self):
        """Hydrograph with < 2 points must fail."""
        r = flood_routing_puls(
            inflow_hydrograph=[(0, 10)],
            storage_discharge_pairs=self._simple_sd(),
            dt_s=3600.0,
        )
        assert not r["ok"]

    def test_peak_outflow_keys_present(self):
        """Check that all expected keys are present in result."""
        r = flood_routing_puls(
            inflow_hydrograph=self._simple_hydrograph(),
            storage_discharge_pairs=self._simple_sd(),
            dt_s=3600.0,
        )
        assert r["ok"]
        for key in ("peak_outflow_m3s", "peak_outflow_time_s", "peak_storage_m3", "attenuation_m3s"):
            assert key in r


# ===========================================================================
# dam_freeboard
# ===========================================================================

class TestDamFreeboard:
    def test_wave_height_formula(self):
        """Hs = 0.0248 * U^2 * F^0.5 (limited by 0.7*depth)."""
        F, U, d = 5.0, 25.0, 15.0
        Hs_calc = min(0.0248 * U ** 2 * F ** 0.5, 0.7 * d)
        r = dam_freeboard(
            reservoir_fetch_km=F, wind_speed_m_s=U, dam_height_m=20.0,
            reservoir_depth_m=d,
        )
        assert r["ok"]
        assert abs(r["significant_wave_height_m"] - Hs_calc) < 0.01

    def test_freeboard_positive(self):
        """Required freeboard should always be positive."""
        r = dam_freeboard(
            reservoir_fetch_km=3.0, wind_speed_m_s=20.0, dam_height_m=15.0
        )
        assert r["ok"]
        assert r["required_freeboard_m"] > 0

    def test_freeboard_components(self):
        """Freeboard = wind_setup + wave_runup + safety_margin."""
        r = dam_freeboard(
            reservoir_fetch_km=4.0, wind_speed_m_s=22.0, dam_height_m=18.0,
            freeboard_safety_m=0.6,
        )
        assert r["ok"]
        expected = r["wind_setup_m"] + r["wave_runup_m"] + 0.6
        assert abs(r["required_freeboard_m"] - expected) < 1e-4

    def test_high_wind_warning(self):
        """Wind speed > 35 m/s should trigger warning."""
        r = dam_freeboard(
            reservoir_fetch_km=5.0, wind_speed_m_s=40.0, dam_height_m=20.0
        )
        assert r["ok"]
        assert any("wind" in w.lower() for w in r["warnings"])

    def test_invalid_fetch(self):
        r = dam_freeboard(reservoir_fetch_km=0.0, wind_speed_m_s=20.0, dam_height_m=10.0)
        assert not r["ok"]


# ===========================================================================
# gravity_dam_stability
# ===========================================================================

class TestGravityDamStability:
    def test_stable_dam(self):
        """A wide-base dam should be stable with adequate FOS."""
        r = gravity_dam_stability(
            dam_height_m=20.0,
            dam_base_width_m=16.0,  # wide base
            upstream_water_depth_m=18.0,
            uplift_fraction=0.667,
            friction_coefficient=0.75,
        )
        assert r["ok"]
        assert r["FOS_overturning"] > 1.5
        assert r["FOS_sliding"] > 1.0

    def test_narrow_base_unstable(self):
        """Very narrow base dam should fail middle-third or overturning."""
        r = gravity_dam_stability(
            dam_height_m=20.0,
            dam_base_width_m=5.0,  # much too narrow
            upstream_water_depth_m=18.0,
            uplift_fraction=1.0,  # no drainage (worst case)
            friction_coefficient=0.75,
        )
        assert r["ok"]
        # Should flag instability
        assert not r["stable"] or len(r["warnings"]) > 0

    def test_weight_calculation(self):
        """Weight ≈ γ_c * B * H for rectangular section (crest ≈ base)."""
        H, B = 10.0, 8.0
        rho_c = 2400.0
        gamma_c = rho_c * 9.81 / 1000.0  # kN/m³
        W_expected = gamma_c * B * H  # rectangular approx
        r = gravity_dam_stability(
            dam_height_m=H,
            dam_base_width_m=B,
            upstream_water_depth_m=8.0,
            concrete_density_kg_m3=rho_c,
            crest_width_m=B,  # force rectangular
        )
        assert r["ok"]
        assert abs(r["weight_kN"] - W_expected) < 1.0

    def test_uplift_with_no_drainage(self):
        """With no drainage (alpha=1), uplift > with drainage."""
        kwargs = dict(
            dam_height_m=15.0, dam_base_width_m=12.0,
            upstream_water_depth_m=13.0,
        )
        r_drain = gravity_dam_stability(**kwargs, uplift_fraction=0.667)
        r_nodrain = gravity_dam_stability(**kwargs, uplift_fraction=1.0)
        assert r_drain["ok"] and r_nodrain["ok"]
        assert r_nodrain["uplift_kN"] > r_drain["uplift_kN"]

    def test_overtopping_warning(self):
        """Upstream water > dam height should warn overtopping."""
        r = gravity_dam_stability(
            dam_height_m=10.0, dam_base_width_m=8.0,
            upstream_water_depth_m=12.0,  # > dam height
        )
        assert r["ok"]
        assert any("overtopping" in w.lower() for w in r["warnings"])

    def test_middle_third_keys_present(self):
        r = gravity_dam_stability(
            dam_height_m=15.0, dam_base_width_m=10.0,
            upstream_water_depth_m=12.0,
        )
        assert r["ok"]
        for key in ("eccentricity_m", "middle_third_ok", "FOS_overturning",
                    "FOS_sliding", "stable"):
            assert key in r

    def test_invalid_dam_height(self):
        r = gravity_dam_stability(
            dam_height_m=0.0, dam_base_width_m=8.0,
            upstream_water_depth_m=5.0,
        )
        assert not r["ok"]


# ===========================================================================
# plugin registration check
# ===========================================================================

class TestPluginRegistration:
    def test_spillway_tools_registered(self):
        """kerf_cad_core.spillway.tools must appear in _TOOL_MODULES."""
        from kerf_cad_core.plugin import _TOOL_MODULES
        assert "kerf_cad_core.spillway.tools" in _TOOL_MODULES

    def test_tools_importable(self):
        """spillway.tools module must be importable without errors."""
        import importlib
        mod = importlib.import_module("kerf_cad_core.spillway.tools")
        assert mod is not None


# ===========================================================================
# Authoritative external-reference cases (citable, numeric answers)
# ===========================================================================

class TestAuthoritativeReferences:
    """Cross-checks vs published worked results with known numeric answers.

    Sources: USBR (1977) Design of Small Dams 3rd ed.; Chow (1959)
    Open-Channel Hydraulics (Bélanger jump); Henderson (1966); Lacey
    (1930); Bretschneider/SMB (Linsley & Franzini)."""

    def test_usbr_ogee_design_head_discharge(self):
        # USBR SI ogee at design head: Q = C0·L·He^1.5, C0 = 2.21,
        # He = Hd = 2 m, L = 10 m → Q = 62.51 m³/s.
        r = ogee_discharge(design_head_m=2.0, actual_head_m=2.0,
                           crest_length_m=10.0)
        assert r["ok"]
        assert abs(r["discharge_m3s"] - 62.51) < 0.5

    def test_belanger_sequent_depth_fr5(self):
        # Chow (1959) Bélanger: Fr1=5, y1=0.4 m → y2 = 2.635 m.
        r = stilling_basin(upstream_depth_m=0.4,
                           flow_m3s=0.4 * 1.0 * (5.0 * math.sqrt(_G * 0.4)),
                           chute_width_m=1.0, tailwater_depth_m=2.7)
        assert r["ok"]
        assert abs(r["froude1"] - 5.0) < 0.02
        assert abs(r["depth2_m"] - 2.635) < 0.01

    def test_jump_energy_loss_closed_form(self):
        # Classic hydraulic-jump head loss: ΔE = (y2-y1)³/(4·y1·y2)
        # (Chow 1959). Fr1=5, y1=0.4 → y2=2.635 → ΔE ≈ 2.649 m.
        y1 = 0.4
        Q = y1 * 1.0 * (5.0 * math.sqrt(_G * y1))
        r = stilling_basin(upstream_depth_m=y1, flow_m3s=Q,
                           chute_width_m=1.0, tailwater_depth_m=2.7)
        y2 = r["depth2_m"]
        dE_expected = (y2 - y1) ** 3 / (4.0 * y1 * y2)
        assert abs(r["energy_loss_m"] - dE_expected) < 1e-2

    def test_usbr_basin_type_high_froude(self):
        # USBR (1977 p.213): Fr1 ≥ 4.5 → Type III stilling basin.
        y1 = 0.3
        Q = y1 * 2.0 * (6.0 * math.sqrt(_G * y1))
        r = stilling_basin(upstream_depth_m=y1, flow_m3s=Q,
                           chute_width_m=2.0, tailwater_depth_m=3.0)
        assert r["ok"]
        assert r["froude1"] >= 4.5
        assert r["basin_type"] == "III"

    def test_orifice_gate_free_flow(self):
        # Sharp orifice gate Cd=0.61, a=1 m, W=3 m, Hu=5 m (free flow):
        # Q = Cd·A·√(2g·(Hu−a/2)) = 0.61·3·√(2·9.81·4.5) ≈ 17.20 m³/s.
        r = orifice_discharge(gate_opening_m=1.0, gate_width_m=3.0,
                              head_upstream_m=5.0, Cd=0.61)
        assert r["ok"]
        assert abs(r["discharge_m3s"] - 17.20) < 0.1

    def test_lacey_regime_scour(self):
        # Lacey (1930): f = 1.76·√d50, d_scour = 0.47·(Q/f)^(1/3).
        # d50 = 2 mm → f = 2.489, Q = 300 m³/s → 0.47·(300/2.489)^⅓ ≈ 2.32 m.
        r = scour_depth(flow_m3s=300.0, channel_width_m=20.0,
                        d50_mm=2.0, method="lacey")
        assert r["ok"]
        assert abs(r["scour_depth_m"] - 2.32) < 0.05
        assert abs(r["lacey_silt_factor"] - 1.76 * math.sqrt(2.0)) < 1e-3

    def test_gravity_dam_hydrostatic_force(self):
        # Hydrostatic thrust per unit length Ph = ½·γ_w·Hw² (γ_w=9.81 kN/m³).
        # Hw = 20 m → Ph = 0.5·9.81·400 = 1962 kN/m.
        r = gravity_dam_stability(dam_height_m=25.0, dam_base_width_m=18.0,
                                  upstream_water_depth_m=20.0)
        assert r["ok"]
        assert abs(r["horizontal_hydrostatic_kN"] - 1962.0) < 1.0

    def test_bretschneider_significant_wave_height(self):
        # Linsley & Franzini Bretschneider/SMB: H_s = 0.0248·U²·√F.
        # U = 20 m/s, F = 2 km, deep water → H_s ≈ 14.0 m (depth-capped if
        # reservoir shallow; use deep reservoir to test the SMB form).
        r = dam_freeboard(reservoir_fetch_km=2.0, wind_speed_m_s=20.0,
                          dam_height_m=40.0, reservoir_depth_m=30.0)
        assert r["ok"]
        assert abs(r["significant_wave_height_m"] - 14.03) < 0.2

    def test_chute_manning_normal_depth(self):
        # Manning rectangular chute: Q=20 m³/s, W=5 m, S=0.1, n=0.015
        # → normal depth ≈ 0.391 m, V ≈ 10.23 m/s, Fr ≈ 5.22 (supercritical).
        r = chute_velocity(flow_m3s=20.0, chute_width_m=5.0,
                           chute_slope=0.1, manning_n=0.015)
        assert r["ok"]
        assert abs(r["normal_depth_m"] - 0.391) < 5e-3
        assert abs(r["terminal_velocity_m_s"] - 10.23) < 0.1
        assert r["froude_number"] > 1.0
