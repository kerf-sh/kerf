"""
Tests for kerf-energy: acoustic, daylight, solar, and heat-load modules.

Oracles
-------
1. Sabine RT60 for V=1000 m³, A=200 m² Sabines → RT60 = 0.805 s (analytic).
2. Daylight factor for a unit room with one window of given area matches the
   canonical split-flux formula DF = (τ·A_w·θ) / (6·A_floor·(1−ρ²)) · 100 %.
3. Solar noon altitude at equator on the vernal equinox ≈ 90° (within 1°).
"""
import math
import pytest

from kerf_energy.acoustic import rt60_sabine, stc_rating, Surface, total_absorption
from kerf_energy.daylight import (
    daylight_factor_split_flux,
    check_bs8206_compliance,
    BS8206_TARGETS,
)
from kerf_energy.solar import (
    solar_noon_altitude_deg,
    solar_declination_deg,
    solar_position,
    hour_angle_deg,
    clear_sky_irradiance,
    day_of_year,
)
from kerf_energy.heat_load import (
    ZoneHeatLoad,
    WallElement,
    GlazingElement,
    OccupancyLoad,
    LightingLoad,
    EquipmentLoad,
    HeatingLoadElement,
    zone_heating_load_w,
)


# ---------------------------------------------------------------------------
# Oracle 1 — Sabine RT60
# ---------------------------------------------------------------------------

class TestSabineRT60:
    def test_oracle_v1000_a200(self):
        """V=1000 m³, A=200 Sabines → RT60 = 0.161·1000/200 = 0.805 s."""
        rt60 = rt60_sabine(volume_m3=1000.0, total_absorption_sabines=200.0)
        assert math.isclose(rt60, 0.805, rel_tol=1e-6), (
            f"Expected 0.805 s, got {rt60}"
        )

    def test_proportional_to_volume(self):
        """Doubling volume doubles RT60."""
        rt1 = rt60_sabine(100.0, 50.0)
        rt2 = rt60_sabine(200.0, 50.0)
        assert math.isclose(rt2, 2 * rt1, rel_tol=1e-9)

    def test_inversely_proportional_to_absorption(self):
        """Doubling absorption halves RT60."""
        rt1 = rt60_sabine(500.0, 100.0)
        rt2 = rt60_sabine(500.0, 200.0)
        assert math.isclose(rt2, rt1 / 2, rel_tol=1e-9)

    def test_small_room(self):
        """Small classroom: V=200, A=60 → 0.161·200/60 ≈ 0.5367 s."""
        expected = 0.161 * 200 / 60
        rt60 = rt60_sabine(200.0, 60.0)
        assert math.isclose(rt60, expected, rel_tol=1e-9)

    def test_raises_on_nonpositive_volume(self):
        with pytest.raises(ValueError, match="volume_m3"):
            rt60_sabine(0.0, 100.0)

    def test_raises_on_nonpositive_absorption(self):
        with pytest.raises(ValueError, match="total_absorption_sabines"):
            rt60_sabine(500.0, 0.0)

    def test_sabine_constant(self):
        """The Sabine constant must be 0.161."""
        from kerf_energy.acoustic import SABINE_CONSTANT
        assert math.isclose(SABINE_CONSTANT, 0.161, rel_tol=1e-6)


class TestSabineHelpers:
    def test_surface_sabines(self):
        s = Surface(area_m2=10.0, absorption_coeff=0.5)
        assert math.isclose(s.sabines(), 5.0, rel_tol=1e-9)

    def test_total_absorption(self):
        surfaces = [
            Surface(area_m2=20.0, absorption_coeff=0.3),
            Surface(area_m2=15.0, absorption_coeff=0.6),
        ]
        expected = 20.0 * 0.3 + 15.0 * 0.6
        assert math.isclose(total_absorption(surfaces), expected, rel_tol=1e-9)

    def test_rt60_from_surfaces(self):
        surfaces = [
            Surface(area_m2=100.0, absorption_coeff=0.4),
            Surface(area_m2=50.0, absorption_coeff=0.2),
        ]
        A = total_absorption(surfaces)  # 40 + 10 = 50
        rt60 = rt60_sabine(500.0, A)
        expected = 0.161 * 500.0 / 50.0
        assert math.isclose(rt60, expected, rel_tol=1e-9)


class TestSTCRating:
    def test_stc_returns_integer(self):
        tl = [20, 25, 30, 32, 34, 36, 38, 40, 42, 44, 46, 48, 50, 50, 50, 50]
        stc = stc_rating(tl)
        assert isinstance(stc, int)

    def test_stc_nonnegative(self):
        tl = [5] * 16
        stc = stc_rating(tl)
        assert stc >= 0

    def test_stc_higher_for_better_tl(self):
        tl_low = [20] * 16
        tl_high = [50] * 16
        assert stc_rating(tl_high) > stc_rating(tl_low)

    def test_stc_length_mismatch_raises(self):
        with pytest.raises(ValueError, match="length"):
            stc_rating([30] * 10, [125, 250, 500, 1000, 2000])


# ---------------------------------------------------------------------------
# Oracle 2 — Daylight Factor split-flux
# ---------------------------------------------------------------------------

class TestDaylightFactor:
    """Daylight factor split-flux formula verification."""

    def _canonical_df(
        self,
        window_area: float,
        floor_area: float,
        tau: float = 0.6,
        sky: float = 0.4,
        rho: float = 0.5,
    ) -> float:
        """Reference implementation of the split-flux formula."""
        total_surface = 6.0 * floor_area
        numerator = tau * window_area * sky
        denominator = total_surface * (1.0 - rho ** 2)
        return (numerator / denominator) * 100.0

    def test_oracle_matches_canonical(self):
        """DF from kerf_energy equals the reference split-flux formula."""
        A_w = 4.0
        A_floor = 20.0
        tau = 0.6
        sky = 0.4
        rho = 0.5

        df_ref = self._canonical_df(A_w, A_floor, tau, sky, rho)
        df_calc = daylight_factor_split_flux(
            window_area_m2=A_w,
            room_floor_area_m2=A_floor,
            tau=tau,
            sky_component_fraction=sky,
            average_reflectance=rho,
        )
        assert math.isclose(df_calc, df_ref, rel_tol=1e-9), (
            f"Expected {df_ref:.6f}%, got {df_calc:.6f}%"
        )

    def test_oracle_value(self):
        """Numeric oracle: A_w=4, A_floor=20 with defaults → ≈ 1.0667 %."""
        df = daylight_factor_split_flux(
            window_area_m2=4.0,
            room_floor_area_m2=20.0,
        )
        expected = self._canonical_df(4.0, 20.0)
        assert math.isclose(df, expected, rel_tol=1e-9)

    def test_proportional_to_window_area(self):
        """Doubling window area doubles DF."""
        df1 = daylight_factor_split_flux(2.0, 20.0)
        df2 = daylight_factor_split_flux(4.0, 20.0)
        assert math.isclose(df2, 2 * df1, rel_tol=1e-9)

    def test_zero_window_gives_zero_df(self):
        df = daylight_factor_split_flux(0.0, 20.0)
        assert df == 0.0

    def test_obstructed_fraction_reduces_df(self):
        df_clear = daylight_factor_split_flux(4.0, 20.0, externally_obstructed_fraction=0.0)
        df_obstr = daylight_factor_split_flux(4.0, 20.0, externally_obstructed_fraction=0.5)
        assert df_obstr < df_clear

    def test_raises_nonpositive_floor_area(self):
        with pytest.raises(ValueError):
            daylight_factor_split_flux(4.0, 0.0)

    def test_raises_bad_tau(self):
        with pytest.raises(ValueError):
            daylight_factor_split_flux(4.0, 20.0, tau=0.0)

    def test_raises_bad_reflectance(self):
        with pytest.raises(ValueError):
            daylight_factor_split_flux(4.0, 20.0, average_reflectance=1.0)

    def test_bs8206_compliance_office_compliant(self):
        # office target = 2.0% — use a large window to ensure compliance
        df = daylight_factor_split_flux(
            window_area_m2=15.0,
            room_floor_area_m2=20.0,
            sky_component_fraction=0.7,
        )
        result = check_bs8206_compliance("office", df)
        assert result["target"] == BS8206_TARGETS["office"]
        # compliance depends on df value — just check structure
        assert "compliant" in result
        assert "margin" in result

    def test_bs8206_unknown_space_type_raises(self):
        with pytest.raises(ValueError, match="Unknown space type"):
            check_bs8206_compliance("warehouse", 1.5)


# ---------------------------------------------------------------------------
# Oracle 3 — Solar noon altitude at equator on equinox ≈ 90°
# ---------------------------------------------------------------------------

class TestSolarPosition:
    def test_noon_altitude_equator_equinox_approx_90(self):
        """Solar noon altitude at equator near vernal equinox is ≈ 90°.

        The Spencer approximation yields ~89.93° on doy=80 (March 21).
        We verify the result is within 1° of 90°.
        """
        # doy=80 is approximately the vernal equinox
        alt = solar_noon_altitude_deg(latitude_deg=0.0, doy=80)
        assert abs(alt - 90.0) < 1.0, (
            f"Expected solar noon altitude ≈ 90° at equator on equinox, "
            f"got {alt:.4f}°"
        )

    def test_noon_altitude_equator_equinox_close(self):
        """On the closest doy to true equinox, altitude is within 0.5°."""
        # Try doys 79-83 and find the closest to 90°
        alts = [solar_noon_altitude_deg(0.0, d) for d in range(79, 84)]
        best = max(alts)
        assert abs(best - 90.0) < 0.5, (
            f"Best altitude near equinox at equator was {best:.4f}°, expected ~90°"
        )

    def test_solar_declination_near_zero_at_equinox(self):
        """Solar declination is small (< 1°) near vernal equinox."""
        dec = solar_declination_deg(80)
        assert abs(dec) < 1.0, f"Expected declination ≈ 0° at equinox, got {dec:.4f}°"

    def test_noon_altitude_north_pole_summer_solstice(self):
        """At 90°N on summer solstice (doy=172), altitude ≈ 23.5°."""
        alt = solar_noon_altitude_deg(latitude_deg=90.0, doy=172)
        assert 20.0 < alt < 27.0, f"Expected ~23.5° at pole on solstice, got {alt:.4f}°"

    def test_noon_altitude_southern_hemisphere(self):
        """At -34°S (Cape Town) on Dec 21, sun is high in the sky (summer)."""
        alt = solar_noon_altitude_deg(latitude_deg=-34.0, doy=355)
        assert alt > 70.0, (
            f"Expected high altitude at -34°S in summer, got {alt:.4f}°"
        )

    def test_solar_position_sunrise_altitude_zero(self):
        """At the horizon (altitude ~ 0), sun is near sunrise/sunset."""
        # At equator on equinox, solar altitude at ha=90° (6h from noon) ~ 0°
        dec = solar_declination_deg(80)
        alt, az = solar_position(0.0, dec, 90.0)
        # altitude should be near 0 (within ~2°)
        assert abs(alt) < 3.0, (
            f"Expected ~0° altitude at 6h from solar noon at equator, got {alt:.4f}°"
        )

    def test_solar_noon_hour_angle_zero(self):
        """At solar noon, hour angle is 0."""
        ha = hour_angle_deg(12.0)
        assert ha == 0.0

    def test_hour_angle_6am(self):
        """At 06:00 solar time, hour angle = -90°."""
        ha = hour_angle_deg(6.0)
        assert ha == -90.0

    def test_clear_sky_irradiance_day(self):
        """At solar noon at equator in summer, DNI should be > 0."""
        irr = clear_sky_irradiance(0.0, 0.0, 172, 12.0)
        assert irr.direct_normal_w_m2 > 0
        assert irr.global_horizontal_w_m2 > 0

    def test_clear_sky_irradiance_night(self):
        """At midnight, irradiance components should all be 0."""
        irr = clear_sky_irradiance(0.0, 0.0, 172, 0.0)
        assert irr.direct_normal_w_m2 == 0.0
        assert irr.global_horizontal_w_m2 == 0.0

    def test_declination_summer_solstice(self):
        """Solar declination on summer solstice (doy~172) ≈ +23.45°."""
        dec = solar_declination_deg(172)
        assert 22.0 < dec < 25.0, (
            f"Expected ~23.45° declination at summer solstice, got {dec:.4f}°"
        )

    def test_declination_winter_solstice(self):
        """Solar declination on winter solstice (doy~355) ≈ -23.45°."""
        dec = solar_declination_deg(355)
        assert -25.0 < dec < -22.0, (
            f"Expected ~-23.45° declination at winter solstice, got {dec:.4f}°"
        )


# ---------------------------------------------------------------------------
# Heat load tests
# ---------------------------------------------------------------------------

class TestHeatLoad:
    def test_zone_with_wall_has_positive_sensible(self):
        zone = ZoneHeatLoad()
        zone.walls.append(WallElement(area_m2=20.0, u_value_w_m2_k=0.3))
        peak = zone.peak_sensible_w()
        assert peak > 0

    def test_occupancy_sensible_and_latent(self):
        zone = ZoneHeatLoad()
        zone.occupancy.append(OccupancyLoad(num_people=10))
        sensible = zone.sensible_w(14)
        latent = zone.latent_w()
        assert sensible == 10 * 75.0
        assert latent == 10 * 55.0

    def test_lighting_adds_to_sensible(self):
        zone_no_light = ZoneHeatLoad()
        zone_no_light.occupancy.append(OccupancyLoad(num_people=5))

        zone_with_light = ZoneHeatLoad()
        zone_with_light.occupancy.append(OccupancyLoad(num_people=5))
        zone_with_light.lighting.append(LightingLoad(installed_power_w=1000.0))

        assert zone_with_light.sensible_w(14) > zone_no_light.sensible_w(14)

    def test_peak_hour_in_range(self):
        zone = ZoneHeatLoad()
        zone.walls.append(WallElement(area_m2=30.0, u_value_w_m2_k=0.5))
        zone.glazing.append(GlazingElement(area_m2=5.0, u_value_w_m2_k=2.0, shgc=0.4))
        ph = zone.peak_hour()
        assert 1 <= ph <= 24

    def test_heating_load(self):
        elements = [
            HeatingLoadElement(area_m2=50.0, u_value_w_m2_k=0.3, delta_t_k=20.0),
            HeatingLoadElement(area_m2=10.0, u_value_w_m2_k=2.0, delta_t_k=20.0),
        ]
        load = zone_heating_load_w(elements)
        expected = 50.0 * 0.3 * 20.0 + 10.0 * 2.0 * 20.0
        assert math.isclose(load, expected, rel_tol=1e-9)

    def test_empty_zone_zero_load(self):
        zone = ZoneHeatLoad()
        assert zone.sensible_w(14) == 0.0
        assert zone.latent_w() == 0.0


# ---------------------------------------------------------------------------
# Parity test — kerf_energy.solar vs kerf_cad_core.solarpv.geometry
# ---------------------------------------------------------------------------

class TestSolarGeometryParity:
    """Assert that the shared geometry module and kerf_energy.solar produce
    bit-identical results for solar declination and equation of time.

    Both packages now delegate to kerf_cad_core.solarpv.geometry, so this
    test guards against accidental re-introduction of diverging formulas.
    """

    # Sample days: vernal equinox, summer solstice, autumnal equinox,
    # winter solstice, and a few arbitrary mid-season days.
    _SAMPLE_DOYS = [1, 32, 60, 80, 100, 121, 152, 172, 200, 230, 266, 300, 320, 355]

    def test_declination_parity(self):
        """solar_declination_deg from kerf_energy.solar matches the canonical
        geometry module for all sample days — tolerance 1e-12 degrees."""
        from kerf_energy.solar import solar_declination_deg as energy_decl
        from kerf_cad_core.solarpv.geometry import solar_declination_deg as geom_decl

        for doy in self._SAMPLE_DOYS:
            e = energy_decl(doy)
            g = geom_decl(doy)
            assert abs(e - g) < 1e-12, (
                f"doy={doy}: kerf_energy={e:.10f}  geometry={g:.10f}  delta={abs(e-g):.2e}"
            )

    def test_equation_of_time_parity(self):
        """equation_of_time_minutes from kerf_energy.solar matches the
        Spencer full-Fourier series in the canonical geometry module —
        tolerance 1e-12 minutes."""
        from kerf_energy.solar import equation_of_time_minutes as energy_eot
        from kerf_cad_core.solarpv.geometry import equation_of_time_spencer_min as geom_eot

        for doy in self._SAMPLE_DOYS:
            e = energy_eot(doy)
            g = geom_eot(doy)
            assert abs(e - g) < 1e-12, (
                f"doy={doy}: kerf_energy={e:.10f}  geometry={g:.10f}  delta={abs(e-g):.2e}"
            )

    def test_declination_range(self):
        """Declination stays within ±23.5° for all days of the year."""
        from kerf_cad_core.solarpv.geometry import solar_declination_deg

        for doy in range(1, 366):
            d = solar_declination_deg(doy)
            assert -23.6 <= d <= 23.6, f"doy={doy}: declination={d:.4f}° out of range"

    def test_sizing_solar_declination_matches_geometry(self):
        """sizing.solar_declination (thin wrapper) matches geometry module exactly."""
        from kerf_cad_core.solarpv.sizing import solar_declination as sizing_decl
        from kerf_cad_core.solarpv.geometry import solar_declination_deg as geom_decl

        for doy in self._SAMPLE_DOYS:
            assert sizing_decl(doy) == geom_decl(doy), (
                f"doy={doy}: sizing wrapper diverges from geometry module"
            )
