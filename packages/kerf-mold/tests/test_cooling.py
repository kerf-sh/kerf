"""
Tests for kerf_mold.cooling — injection-mold cooling channel thermal analysis.

DoD coverage:
  1. channel_flow returns Re, Nu, htc for a turbulent channel.
  2. Flow regime correctly classified (laminar / turbulent).
  3. Re = rho * v * D / mu (oracle check).
  4. Dittus-Boelter Nu formula verified.
  5. circuit_analysis returns ChannelFlowResult for each channel.
  6. cooling_time Janeschitz-Kriegl oracle verified.
  7. cooling_time warns for unknown polymer.
  8. CoolingCircuit validates layout.
"""

from __future__ import annotations

import math
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from kerf_mold.cooling import (
    CoolantProperties,
    CoolingChannel,
    CoolingCircuit,
    channel_flow,
    circuit_analysis,
    cooling_time,
    POLYMER_THERMAL_DIFFUSIVITY,
    _WATER_DENSITY,
    _WATER_VISCOSITY,
    _WATER_THERMAL_COND,
    _WATER_SPECIFIC_HEAT,
)


# ===========================================================================
# CoolantProperties
# ===========================================================================

class TestCoolantProperties:
    def test_prandtl_water(self):
        """Prandtl of water at 25°C ≈ 6."""
        water = CoolantProperties()
        Pr = water.prandtl
        assert 5.5 < Pr < 7.5, f"Pr = {Pr} (expected ~6.1)"

    def test_kinematic_viscosity(self):
        water = CoolantProperties()
        nu = water.kinematic_viscosity_m2_s
        # At 25°C: ν ≈ 8.9e-7 m²/s
        assert 7e-7 < nu < 1.1e-6


# ===========================================================================
# channel_flow — Reynolds number oracle
# ===========================================================================

class TestChannelFlow:
    def _turbulent_channel(self) -> CoolingChannel:
        """DN10 channel, 200 mm long, well into turbulent flow."""
        return CoolingChannel(diameter_mm=10.0, length_mm=200.0, label="test_ch")

    def _turbulent_flow_rate(self, ch: CoolingChannel) -> float:
        """Flow rate giving Re ≈ 20 000 (turbulent)."""
        water = CoolantProperties()
        A = ch.cross_section_area_m2
        D = ch.hydraulic_diameter_m
        Re_target = 20000.0
        v = Re_target * water.dynamic_viscosity_Pa_s / (water.density_kg_m3 * D)
        return v * A

    def test_reynolds_oracle(self):
        """Re = rho * v * D / mu — analytic oracle."""
        water = CoolantProperties()
        ch = self._turbulent_channel()
        Q = self._turbulent_flow_rate(ch)
        A = ch.cross_section_area_m2
        D = ch.hydraulic_diameter_m
        v = Q / A
        Re_expected = water.density_kg_m3 * v * D / water.dynamic_viscosity_Pa_s

        result = channel_flow(ch, Q, water)
        assert result.reynolds == pytest.approx(Re_expected, rel=1e-6)

    def test_turbulent_regime(self):
        """High Re → 'turbulent' regime."""
        ch = self._turbulent_channel()
        Q = self._turbulent_flow_rate(ch)
        result = channel_flow(ch, Q)
        assert result.flow_regime == "turbulent"

    def test_laminar_regime(self):
        """Very low flow rate → 'laminar' regime."""
        water = CoolantProperties()
        ch = CoolingChannel(diameter_mm=10.0, length_mm=200.0)
        # Low Re → laminar: Re < 2300
        # v = Re * mu / (rho * D) with Re = 1000
        D = ch.hydraulic_diameter_m
        v = 1000.0 * water.dynamic_viscosity_Pa_s / (water.density_kg_m3 * D)
        Q = v * ch.cross_section_area_m2
        result = channel_flow(ch, Q, water)
        assert result.flow_regime == "laminar"
        assert result.reynolds < 2300.0

    def test_nusselt_turbulent_dittus_boelter(self):
        """
        Turbulent Nu oracle: Nu = 0.023 * Re^0.8 * Pr^0.4 (Dittus-Boelter).
        """
        water = CoolantProperties()
        ch = self._turbulent_channel()
        Q = self._turbulent_flow_rate(ch)
        result = channel_flow(ch, Q, water)

        Re = result.reynolds
        Pr = water.prandtl
        Nu_expected = 0.023 * (Re ** 0.8) * (Pr ** 0.4)

        # Re > 10000, so full turbulent formula applies
        assert result.reynolds > 10000.0
        assert result.nusselt == pytest.approx(Nu_expected, rel=0.01)

    def test_htc_positive(self):
        ch = self._turbulent_channel()
        Q = self._turbulent_flow_rate(ch)
        result = channel_flow(ch, Q)
        assert result.htc_W_m2K > 0.0

    def test_pressure_drop_positive(self):
        ch = self._turbulent_channel()
        Q = self._turbulent_flow_rate(ch)
        result = channel_flow(ch, Q)
        assert result.pressure_drop_pa > 0.0

    def test_htc_from_nu(self):
        """HTC = Nu * k / D (oracle)."""
        water = CoolantProperties()
        ch = self._turbulent_channel()
        Q = self._turbulent_flow_rate(ch)
        result = channel_flow(ch, Q, water)

        htc_expected = result.nusselt * water.thermal_conductivity_W_mK / ch.hydraulic_diameter_m
        assert result.htc_W_m2K == pytest.approx(htc_expected, rel=1e-9)

    def test_zero_flow_raises(self):
        ch = self._turbulent_channel()
        with pytest.raises(ValueError, match="flow_rate"):
            channel_flow(ch, 0.0)

    def test_velocity_oracle(self):
        """velocity = Q / A_cross."""
        ch = self._turbulent_channel()
        Q = self._turbulent_flow_rate(ch)
        result = channel_flow(ch, Q)
        v_expected = Q / ch.cross_section_area_m2
        assert result.velocity_m_s == pytest.approx(v_expected, rel=1e-6)


# ===========================================================================
# circuit_analysis
# ===========================================================================

class TestCircuitAnalysis:
    def _make_series_circuit(self) -> CoolingCircuit:
        channels = [
            CoolingChannel(diameter_mm=10.0, length_mm=200.0, label=f"C{i}")
            for i in range(3)
        ]
        return CoolingCircuit(
            channels=channels,
            layout="series",
            flow_rate_lpm=5.0,
            coolant_inlet_temp_c=20.0,
        )

    def _make_parallel_circuit(self) -> CoolingCircuit:
        channels = [
            CoolingChannel(diameter_mm=8.0, length_mm=150.0, label=f"P{i}")
            for i in range(4)
        ]
        return CoolingCircuit(
            channels=channels,
            layout="parallel",
            flow_rate_lpm=8.0,
            coolant_inlet_temp_c=18.0,
        )

    def test_series_circuit_returns_all_channels(self):
        circ = self._make_series_circuit()
        result = circuit_analysis(circ, mould_surface_temp_c=60.0)
        assert len(result.channels) == 3

    def test_parallel_circuit_returns_all_channels(self):
        circ = self._make_parallel_circuit()
        result = circuit_analysis(circ, mould_surface_temp_c=60.0)
        assert len(result.channels) == 4

    def test_effective_htc_positive(self):
        circ = self._make_series_circuit()
        result = circuit_analysis(circ, mould_surface_temp_c=60.0)
        assert result.total_htc_W_m2K > 0.0

    def test_total_area_positive(self):
        circ = self._make_series_circuit()
        result = circuit_analysis(circ, mould_surface_temp_c=60.0)
        assert result.total_heat_area_m2 > 0.0

    def test_heat_area_oracle(self):
        """Total heat-transfer area = π*D*L * n_channels for series."""
        circ = self._make_series_circuit()
        result = circuit_analysis(circ, mould_surface_temp_c=60.0)
        D = circ.channels[0].diameter_m
        L = circ.channels[0].length_m
        n = len(circ.channels)
        expected_area = math.pi * D * L * n
        assert result.total_heat_area_m2 == pytest.approx(expected_area, rel=1e-6)

    def test_pressure_drop_series_sum(self):
        """Series total dP ≈ sum of channel dPs."""
        circ = self._make_series_circuit()
        result = circuit_analysis(circ, mould_surface_temp_c=60.0)
        # All channels identical in a series circuit
        # ChannelFlowResult stores pressure_drop_pa; circuit result is in kPa
        single_dp_pa = result.channels[0].pressure_drop_pa
        expected_total_kPa = single_dp_pa * len(circ.channels) / 1000.0
        assert result.total_pressure_drop_kPa == pytest.approx(expected_total_kPa, rel=0.01)

    def test_result_as_dict_structure(self):
        circ = self._make_series_circuit()
        result = circuit_analysis(circ, mould_surface_temp_c=60.0)
        d = result.as_dict()
        for key in ["layout", "total_flow_lpm", "channels",
                    "effective_htc_W_m2K", "total_area_m2",
                    "total_pressure_drop_kPa"]:
            assert key in d, f"Missing key: {key}"

    def test_laminar_channel_warns(self):
        """Very low flow rate → laminar flow → warning in result."""
        channels = [CoolingChannel(diameter_mm=10.0, length_mm=100.0, label="slow")]
        circ = CoolingCircuit(
            channels=channels,
            layout="series",
            flow_rate_lpm=0.05,   # very low → laminar
        )
        result = circuit_analysis(circ, mould_surface_temp_c=60.0)
        # Should warn about laminar flow
        assert any("laminar" in w.lower() for w in result.warnings)

    def test_invalid_layout_raises(self):
        with pytest.raises(ValueError, match="layout"):
            CoolingCircuit(
                channels=[CoolingChannel()],
                layout="diagonal",
            )


# ===========================================================================
# cooling_time — Janeschitz-Kriegl oracle
# ===========================================================================

class TestCoolingTime:
    def test_cooling_time_positive(self):
        """Positive cooling time for typical PP part."""
        result = cooling_time(
            wall_thickness_mm=3.0,
            melt_temp_c=220.0,
            mould_temp_c=30.0,
            ejection_temp_c=80.0,
            polymer="PP",
        )
        assert result.cooling_time_s > 0.0

    def test_janeschitz_kriegl_oracle(self):
        """
        Analytic oracle:
          t = (s² / (π² · a)) · ln(4/π · ΔT_melt / ΔT_eject)
        s = 3mm/2 = 1.5e-3 m (two-sided cooling, half-thickness)
        ΔT_melt = 220 - 30 = 190 °C
        ΔT_eject = 80 - 30 = 50 °C
        a = 8.6e-8 m²/s (PP)
        """
        wall_mm = 3.0
        T_melt, T_mould, T_eject = 220.0, 30.0, 80.0
        a = POLYMER_THERMAL_DIFFUSIVITY["PP"]
        s = (wall_mm * 1e-3) / 2.0
        ratio = (4.0 / math.pi) * (T_melt - T_mould) / (T_eject - T_mould)
        t_expected = (s ** 2 / (math.pi ** 2 * a)) * math.log(ratio)

        result = cooling_time(wall_mm, T_melt, T_mould, T_eject, "PP")
        assert result.cooling_time_s == pytest.approx(t_expected, rel=1e-10)

    def test_thicker_wall_longer_cooling(self):
        """Doubling wall thickness → 4× cooling time (s² dependence)."""
        kwargs = dict(melt_temp_c=220.0, mould_temp_c=30.0, ejection_temp_c=80.0, polymer="PP")
        r1 = cooling_time(2.0, **kwargs)
        r2 = cooling_time(4.0, **kwargs)
        ratio = r2.cooling_time_s / r1.cooling_time_s
        # t ∝ s², s = wall/2, so ratio should be (4/2)² = 4.0
        assert ratio == pytest.approx(4.0, rel=0.01)

    def test_unknown_polymer_warns_and_defaults_pp(self):
        result = cooling_time(3.0, 220.0, 30.0, 80.0, polymer="UNOBTAINIUM")
        assert any("PP" in w or "polymer" in w.lower() for w in result.warnings)
        assert result.cooling_time_s > 0.0

    def test_negative_delta_T_returns_zero(self):
        """T_melt <= T_mould → cooling_time = 0."""
        result = cooling_time(3.0, 25.0, 30.0, 80.0)  # melt < mould
        assert result.cooling_time_s == pytest.approx(0.0)
        assert len(result.warnings) > 0

    def test_all_polymers_give_positive_times(self):
        """All polymers in the library give a positive cooling time."""
        for poly in POLYMER_THERMAL_DIFFUSIVITY:
            result = cooling_time(2.5, 200.0, 25.0, 70.0, polymer=poly)
            assert result.cooling_time_s > 0.0, f"Zero cooling time for {poly}"

    def test_result_as_dict_keys(self):
        result = cooling_time(3.0, 220.0, 30.0, 80.0)
        d = result.as_dict()
        for key in ["cooling_time_s", "wall_thickness_mm", "polymer",
                    "melt_temp_c", "mould_temp_c", "ejection_temp_c",
                    "thermal_diffusivity_m2_s"]:
            assert key in d, f"Missing key: {key}"

    def test_thermal_diffusivity_in_result(self):
        result = cooling_time(3.0, 220.0, 30.0, 80.0, polymer="ABS")
        assert result.thermal_diffusivity_m2_s == pytest.approx(
            POLYMER_THERMAL_DIFFUSIVITY["ABS"], rel=1e-10
        )

    def test_override_thermal_diffusivity(self):
        """User can override thermal diffusivity."""
        a_custom = 1.5e-7   # custom value
        result = cooling_time(3.0, 220.0, 30.0, 80.0, thermal_diffusivity_m2_s=a_custom)
        assert result.thermal_diffusivity_m2_s == pytest.approx(a_custom, rel=1e-10)


# ===========================================================================
# Module smoke tests
# ===========================================================================

class TestModuleImport:
    def test_import_cooling(self):
        import kerf_mold.cooling  # noqa

    def test_pycompile(self):
        import py_compile
        path = os.path.join(_SRC, "kerf_mold", "cooling.py")
        py_compile.compile(path, doraise=True)
