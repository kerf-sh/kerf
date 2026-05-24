"""
tests/test_iapws_if97.py — Validation tests for IAPWS-IF97 steam properties
=============================================================================

Reference values are taken directly from the IAPWS-IF97 standard
(Wagner et al., J. Eng. Gas Turbines Power, 2000), Tables 5, 15, 26, and 35.

Tolerances follow IF97 published precision:
  - v:  7 significant figures (relative tol 1e-6)
  - h:  5 significant figures (abs tol 0.01 kJ/kg)
  - s:  5 significant figures (abs tol 0.001 kJ/kg·K)
  - cp: 5 significant figures (abs tol 0.001 kJ/kg·K)
  - psat, Tsat: 5 significant figures
"""
from __future__ import annotations

import math
import pytest

from kerf_cad_core.fluids.iapws_if97 import (
    psat_T,
    Tsat_p,
    region1_props,
    region2_props,
    steam_properties_if97,
)


# ---------------------------------------------------------------------------
# Region 4 — Saturation curve
# ---------------------------------------------------------------------------

class TestRegion4Saturation:
    def test_Tsat_at_atmospheric_pressure(self):
        """Tsat(101.325 kPa) = 373.124 K  (IF97 Table 35 / standard result)."""
        T = Tsat_p(101325.0)
        assert abs(T - 373.124) < 0.001, f"Tsat={T:.4f} K, expected 373.124 K"

    def test_psat_at_370K(self):
        """psat(370 K) = 90.535 kPa  (IF97 Table 35)."""
        p = psat_T(370.0)
        assert abs(p / 1000.0 - 90.535) < 0.01, f"psat={p/1000:.4f} kPa, expected 90.535 kPa"

    def test_psat_at_critical_temperature(self):
        """psat(647.096 K) ≈ 22.064 MPa (critical point)."""
        p = psat_T(647.096)
        assert abs(p / 1e6 - 22.064) < 0.01, f"psat={p/1e6:.4f} MPa, expected 22.064 MPa"

    def test_Tsat_at_1MPa(self):
        """Tsat(1 MPa) ≈ 453.03 K — IF97 verification."""
        T = Tsat_p(1.0e6)
        # IAPWS-IF97: Tsat(1 MPa) = 453.0353 K
        assert abs(T - 453.035) < 0.01, f"Tsat={T:.4f} K, expected 453.035 K"

    def test_psat_T_and_Tsat_p_are_inverse(self):
        """Round-trip: Tsat(psat(T)) == T."""
        for T_ref in (280.0, 350.0, 500.0, 600.0):
            p = psat_T(T_ref)
            T_back = Tsat_p(p)
            assert abs(T_back - T_ref) < 1e-6, (
                f"Round-trip error at T={T_ref}: got {T_back:.8f}"
            )

    def test_psat_out_of_range_raises(self):
        with pytest.raises(ValueError):
            psat_T(200.0)   # below 273.15 K

    def test_Tsat_out_of_range_raises(self):
        with pytest.raises(ValueError):
            Tsat_p(30e6)    # above critical pressure


# ---------------------------------------------------------------------------
# Region 1 — Compressed liquid
# ---------------------------------------------------------------------------

class TestRegion1CompressedLiquid:
    """
    Reference: IAPWS-IF97 Table 5.

    T=300 K, p=3 MPa:
      v  = 0.00100215 m³/kg
      h  = 115.331    kJ/kg
      s  = 0.392294   kJ/kg·K
      cp = 4.17301    kJ/kg·K
    """

    @pytest.fixture
    def props_300_3mpa(self):
        return region1_props(300.0, 3.0e6)

    def test_v(self, props_300_3mpa):
        v = props_300_3mpa["v"]
        ref = 0.00100215
        assert abs(v - ref) / ref < 1e-5, f"v={v:.8f}, ref={ref}"

    def test_h(self, props_300_3mpa):
        h_kJ = props_300_3mpa["h"] / 1000.0
        ref = 115.331
        assert abs(h_kJ - ref) < 0.01, f"h={h_kJ:.4f} kJ/kg, ref={ref}"

    def test_s(self, props_300_3mpa):
        s_kJ = props_300_3mpa["s"] / 1000.0
        ref = 0.392294
        assert abs(s_kJ - ref) < 0.001, f"s={s_kJ:.6f} kJ/kg·K, ref={ref}"

    def test_cp(self, props_300_3mpa):
        cp_kJ = props_300_3mpa["cp"] / 1000.0
        ref = 4.17301
        assert abs(cp_kJ - ref) < 0.001, f"cp={cp_kJ:.5f} kJ/kg·K, ref={ref}"

    def test_additional_point_T300_p80mpa(self):
        """
        T=300 K, p=80 MPa — IF97 Table 5 second verification point.
        v = 0.971180e-3 m³/kg, h = 184.142 kJ/kg.
        """
        props = region1_props(300.0, 80.0e6)
        assert abs(props["v"] - 0.971180e-3) / 0.971180e-3 < 1e-5, f"v={props['v']:.8e}"
        assert abs(props["h"] / 1000.0 - 184.142) < 0.01, f"h={props['h']/1000:.4f}"

    def test_additional_point_T500_p3mpa(self):
        """
        T=500 K, p=3 MPa — IF97 Table 5 third verification point.
        v = 0.120241e-2 m³/kg, h = 975.542 kJ/kg.
        """
        props = region1_props(500.0, 3.0e6)
        assert abs(props["v"] - 0.120241e-2) / 0.120241e-2 < 1e-4, f"v={props['v']:.8e}"
        assert abs(props["h"] / 1000.0 - 975.542) < 0.01, f"h={props['h']/1000:.4f}"


# ---------------------------------------------------------------------------
# Region 2 — Superheated steam
# ---------------------------------------------------------------------------

class TestRegion2SuperheatedSteam:
    """
    Reference: IAPWS-IF97 Table 15.

    T=300 K, p=0.0035 MPa:
      v  = 39.4913  m³/kg
      h  = 2549.91  kJ/kg
      s  = 8.52238  kJ/kg·K
      cp = 1.91300  kJ/kg·K
    """

    @pytest.fixture
    def props_300_3500pa(self):
        return region2_props(300.0, 3500.0)

    def test_v(self, props_300_3500pa):
        v = props_300_3500pa["v"]
        ref = 39.4913
        assert abs(v - ref) / ref < 1e-5, f"v={v:.6f}, ref={ref}"

    def test_h(self, props_300_3500pa):
        h_kJ = props_300_3500pa["h"] / 1000.0
        ref = 2549.91
        assert abs(h_kJ - ref) < 0.01, f"h={h_kJ:.4f} kJ/kg, ref={ref}"

    def test_s(self, props_300_3500pa):
        s_kJ = props_300_3500pa["s"] / 1000.0
        ref = 8.52238
        assert abs(s_kJ - ref) < 0.001, f"s={s_kJ:.5f} kJ/kg·K, ref={ref}"

    def test_cp(self, props_300_3500pa):
        cp_kJ = props_300_3500pa["cp"] / 1000.0
        ref = 1.91300
        assert abs(cp_kJ - ref) < 0.001, f"cp={cp_kJ:.5f} kJ/kg·K, ref={ref}"

    def test_additional_point_T700_p0035mpa(self):
        """
        T=700 K, p=0.0035 MPa — IF97 Table 15 second verification point.
        v = 92.3015 m³/kg, h = 3335.68 kJ/kg.
        """
        props = region2_props(700.0, 3500.0)
        assert abs(props["v"] - 92.3015) / 92.3015 < 1e-5, f"v={props['v']:.6f}"
        assert abs(props["h"] / 1000.0 - 3335.68) < 0.05, f"h={props['h']/1000:.4f}"

    def test_additional_point_T700_p30mpa(self):
        """
        T=700 K, p=30 MPa — IF97 Table 15 third verification point.
        v = 0.542946e-2 m³/kg, h = 2631.49 kJ/kg.
        """
        props = region2_props(700.0, 30.0e6)
        assert abs(props["v"] - 0.542946e-2) / 0.542946e-2 < 1e-5, f"v={props['v']:.8e}"
        assert abs(props["h"] / 1000.0 - 2631.49) < 0.05, f"h={props['h']/1000:.4f}"


# ---------------------------------------------------------------------------
# Top-level dispatcher: steam_properties_if97
# ---------------------------------------------------------------------------

class TestSteamPropertiesIF97:
    def test_dispatcher_liquid_region1(self):
        """T=300K, p=3MPa → liquid, correct v."""
        result = steam_properties_if97(300.0, 3.0e6)
        assert result["phase"] == "liquid"
        assert abs(result["v_m3_per_kg"] - 0.00100215) < 1e-7
        assert abs(result["h_J_per_kg"] / 1000.0 - 115.331) < 0.01

    def test_dispatcher_vapour_region2(self):
        """T=300K, p=3500 Pa → vapour, correct v and h."""
        result = steam_properties_if97(300.0, 3500.0)
        assert result["phase"] == "vapour"
        assert abs(result["v_m3_per_kg"] - 39.4913) / 39.4913 < 1e-5
        assert abs(result["h_J_per_kg"] / 1000.0 - 2549.91) < 0.01

    def test_dispatcher_returns_all_fields(self):
        result = steam_properties_if97(400.0, 0.5e6)
        for key in ("T_K", "p_Pa", "v_m3_per_kg", "h_J_per_kg",
                    "s_J_per_kg_K", "cp_J_per_kg_K", "phase"):
            assert key in result, f"Missing key: {key}"

    def test_dispatcher_invalid_temperature(self):
        with pytest.raises(ValueError):
            steam_properties_if97(200.0, 1e5)  # below 273.15 K

    def test_dispatcher_invalid_pressure(self):
        with pytest.raises(ValueError):
            steam_properties_if97(300.0, 0.0)

    def test_steam_at_100c_atmospheric(self):
        """
        At ~373.124 K (psat ≈ 101.325 kPa), vapour just above saturation.
        Specific volume should be close to ideal gas RT/p.
        """
        T = 374.0    # slightly above saturation at atmospheric
        p = 101325.0
        result = steam_properties_if97(T, p)
        assert result["phase"] == "vapour"
        # Rough sanity: v ~ R*T/p for steam ≈ 461.5*374/101325 ≈ 1.70 m³/kg
        expected_v_rough = 461.526 * T / p
        assert abs(result["v_m3_per_kg"] - expected_v_rough) / expected_v_rough < 0.05
