"""
Hermetic tests for kerf_cad_core.acoustics — engineering/architectural acoustics.

All tests are pure-Python and hermetic: no OCC, no DB, no network, no fixtures.
Formulas are verified against published hand-calculations.

References
----------
ISO 9613-1:1993  — Attenuation of sound during propagation outdoors
ISO 140-3:1995   — Measurement of airborne sound insulation
ASHRAE HVAC Applications 2019, Chapter 48
Sabine (1900), Eyring (1930)
Beranek "Acoustics" (1954/1986)
IEC 61672-1:2013 — Electroacoustics: Sound level meters

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.acoustics.sound import (
    spl_sum,
    spl_subtract,
    spl_average,
    point_source_attenuation,
    line_source_attenuation,
    inverse_square_delta,
    sabine_rt60,
    eyring_rt60,
    room_constant,
    reverberant_spl,
    mass_law_tl,
    composite_tl,
    spl_transmitted,
    a_weighting_offset,
    c_weighting_offset,
    apply_weighting,
    octave_band_combine,
    nc_rating,
    nr_rating,
    duct_attenuation,
    duct_breakout_spl,
    duct_regen_spl,
    lw_from_lp,
    lp_from_lw,
)
from kerf_cad_core.acoustics.tools import (
    run_acoustics_spl_sum,
    run_acoustics_spl_subtract,
    run_acoustics_point_source,
    run_acoustics_sabine_rt60,
    run_acoustics_mass_law_tl,
    run_acoustics_nc_rating,
    run_acoustics_duct_attenuation,
    run_acoustics_lw_from_lp,
    run_acoustics_lp_from_lw,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _ctx():
    try:
        from kerf_core.utils.context import ProjectCtx  # type: ignore[import]
        return ProjectCtx(
            pool=None, storage=None,
            project_id=uuid.uuid4(), user_id=uuid.uuid4(),
            role="owner", http_client=None,
        )
    except Exception:
        return None


def _args(**kwargs) -> bytes:
    return json.dumps(kwargs).encode()


def _ok_tool(raw: str) -> dict:
    d = json.loads(raw)
    assert d.get("ok") is True, f"Expected ok=True, got: {d}"
    return d


def _err_tool(raw: str) -> dict:
    d = json.loads(raw)
    is_ok_false = d.get("ok") is False
    is_err_payload = "error" in d and "code" in d
    assert is_ok_false or is_err_payload, f"Expected error response, got: {d}"
    return d


REL = 1e-6


# ===========================================================================
# 1. spl_sum
# ===========================================================================

class TestSplSum:

    def test_two_identical_sources_adds_3db(self):
        """Two identical 70 dB sources → 10·log10(2·10^7) ≈ 73.01 dB."""
        res = spl_sum([70.0, 70.0])
        assert res["ok"] is True
        assert abs(res["spl_db"] - (70.0 + 10.0 * math.log10(2.0))) < 1e-9

    def test_single_value_returns_same(self):
        """Single-element list returns the same value."""
        res = spl_sum([85.0])
        assert res["ok"] is True
        assert abs(res["spl_db"] - 85.0) < 1e-9

    def test_three_sources_hand_calc(self):
        """80 + 80 + 80 = 10·log10(3·10^8) ≈ 84.77 dB."""
        expected = 10.0 * math.log10(3.0 * 10.0 ** (80.0 / 10.0))
        res = spl_sum([80.0, 80.0, 80.0])
        assert res["ok"] is True
        assert abs(res["spl_db"] - expected) < REL

    def test_empty_list_returns_error(self):
        res = spl_sum([])
        assert res["ok"] is False

    def test_n_count_correct(self):
        res = spl_sum([60.0, 65.0, 70.0])
        assert res["ok"] is True
        assert res["n"] == 3

    def test_tool_happy_path(self):
        raw = _run(run_acoustics_spl_sum(_ctx(), _args(levels_db=[70.0, 70.0])))
        d = _ok_tool(raw)
        assert abs(d["spl_db"] - (70.0 + 10.0 * math.log10(2.0))) < 1e-9

    def test_tool_missing_arg(self):
        raw = _run(run_acoustics_spl_sum(_ctx(), _args()))
        _err_tool(raw)


# ===========================================================================
# 2. spl_subtract
# ===========================================================================

class TestSplSubtract:

    def test_subtract_removes_background(self):
        """Combining 70 dB source + 65 dB background = combined.
        Subtracting background recovers source."""
        source = 70.0
        bg = 65.0
        combined_lin = 10.0 ** (source / 10.0) + 10.0 ** (bg / 10.0)
        combined = 10.0 * math.log10(combined_lin)
        res = spl_subtract(combined, bg)
        assert res["ok"] is True
        assert abs(res["spl_source"] - source) < 0.01  # within 0.01 dB

    def test_bg_equal_total_returns_error(self):
        res = spl_subtract(70.0, 70.0)
        assert res["ok"] is False

    def test_bg_greater_than_total_returns_error(self):
        res = spl_subtract(65.0, 70.0)
        assert res["ok"] is False

    def test_delta_db_correct(self):
        res = spl_subtract(80.0, 70.0)
        assert res["ok"] is True
        assert abs(res["delta_db"] - 10.0) < REL


# ===========================================================================
# 3. spl_average
# ===========================================================================

class TestSplAverage:

    def test_identical_values_returns_same(self):
        """Average of N identical values equals that value."""
        res = spl_average([75.0, 75.0, 75.0])
        assert res["ok"] is True
        assert abs(res["spl_db"] - 75.0) < 1e-9

    def test_two_different_values_hand_calc(self):
        """Average of 70 and 80: 10·log10(0.5·(10^7 + 10^8))."""
        expected = 10.0 * math.log10(0.5 * (10.0 ** 7 + 10.0 ** 8))
        res = spl_average([70.0, 80.0])
        assert res["ok"] is True
        assert abs(res["spl_db"] - expected) < REL

    def test_empty_returns_error(self):
        res = spl_average([])
        assert res["ok"] is False


# ===========================================================================
# 4. point_source_attenuation
# ===========================================================================

class TestPointSourceAttenuation:

    def test_lw_100_at_1m_free_field(self):
        """Lp = Lw + 10·log10(1/(4π)) = 100 − 10·log10(4π) ≈ 100 − 11.0 = 88.99 dB."""
        res = point_source_attenuation(100.0, 1.0, Q=1.0)
        assert res["ok"] is True
        expected = 100.0 + 10.0 * math.log10(1.0 / (4.0 * math.pi))
        assert abs(res["lp_db"] - expected) < REL

    def test_Q2_hemispherical_3db_higher_than_Q1(self):
        """Q=2 (hemisphere) gives 3 dB more than Q=1 at same distance."""
        r1 = point_source_attenuation(90.0, 5.0, Q=1.0)
        r2 = point_source_attenuation(90.0, 5.0, Q=2.0)
        assert r1["ok"] and r2["ok"]
        assert abs((r2["lp_db"] - r1["lp_db"]) - 10.0 * math.log10(2.0)) < REL

    def test_doubling_distance_drops_6db(self):
        """Doubling distance should drop SPL by 20·log10(2) ≈ 6.02 dB."""
        r1 = point_source_attenuation(100.0, 5.0)
        r2 = point_source_attenuation(100.0, 10.0)
        assert r1["ok"] and r2["ok"]
        delta = r1["lp_db"] - r2["lp_db"]
        assert abs(delta - 20.0 * math.log10(2.0)) < REL

    def test_negative_r_returns_error(self):
        res = point_source_attenuation(90.0, -1.0)
        assert res["ok"] is False

    def test_tool_happy_path(self):
        raw = _run(run_acoustics_point_source(_ctx(), _args(Lw=100.0, r=1.0, Q=1.0)))
        d = _ok_tool(raw)
        expected = 100.0 + 10.0 * math.log10(1.0 / (4.0 * math.pi))
        assert abs(d["lp_db"] - expected) < REL


# ===========================================================================
# 5. line_source_attenuation
# ===========================================================================

class TestLineSourceAttenuation:

    def test_hand_calc_at_10m(self):
        """Lp = 80 − 10·log10(2π × 10) = 80 − 10·log10(62.83)."""
        Lw = 80.0
        r = 10.0
        expected = Lw - 10.0 * math.log10(2.0 * math.pi * r)
        res = line_source_attenuation(Lw, r)
        assert res["ok"] is True
        assert abs(res["lp_db"] - expected) < REL

    def test_doubling_distance_drops_3db(self):
        """Line source: doubling distance → -10·log10(2) ≈ -3.01 dB."""
        r1 = line_source_attenuation(80.0, 5.0)
        r2 = line_source_attenuation(80.0, 10.0)
        assert r1["ok"] and r2["ok"]
        delta = r1["lp_db"] - r2["lp_db"]
        assert abs(delta - 10.0 * math.log10(2.0)) < REL

    def test_zero_r_returns_error(self):
        res = line_source_attenuation(80.0, 0.0)
        assert res["ok"] is False


# ===========================================================================
# 6. inverse_square_delta
# ===========================================================================

class TestInverseSquareDelta:

    def test_doubling_distance_minus_6db(self):
        res = inverse_square_delta(5.0, 10.0)
        assert res["ok"] is True
        assert abs(res["delta_db"] - (-6.0206)) < 0.001

    def test_halving_distance_plus_6db(self):
        res = inverse_square_delta(10.0, 5.0)
        assert res["ok"] is True
        assert abs(res["delta_db"] - 6.0206) < 0.001

    def test_same_distance_zero(self):
        res = inverse_square_delta(3.0, 3.0)
        assert res["ok"] is True
        assert abs(res["delta_db"]) < REL


# ===========================================================================
# 7. sabine_rt60
# ===========================================================================

class TestSabineRt60:

    def test_hand_calc(self):
        """RT60 = 0.161 × 200 / 40 = 0.805 s."""
        res = sabine_rt60(200.0, 40.0)
        assert res["ok"] is True
        assert abs(res["rt60_s"] - 0.805) < 1e-9

    def test_large_absorption_short_rt60(self):
        """More absorption → shorter RT60."""
        r1 = sabine_rt60(500.0, 50.0)
        r2 = sabine_rt60(500.0, 200.0)
        assert r1["ok"] and r2["ok"]
        assert r1["rt60_s"] > r2["rt60_s"]

    def test_zero_volume_returns_error(self):
        res = sabine_rt60(0.0, 40.0)
        assert res["ok"] is False

    def test_tool_happy_path(self):
        raw = _run(run_acoustics_sabine_rt60(_ctx(), _args(volume_m3=200.0, total_absorption_m2=40.0)))
        d = _ok_tool(raw)
        assert abs(d["rt60_s"] - 0.805) < 1e-9


# ===========================================================================
# 8. eyring_rt60
# ===========================================================================

class TestEyringRt60:

    def test_low_alpha_matches_sabine_approx(self):
        """For small α, Eyring ≈ Sabine (within ~10% for α=0.1)."""
        V = 300.0
        S = 250.0
        alpha = 0.1
        # Sabine: A = S × α = 25 m², RT60_sabine = 0.161 × 300 / 25 = 1.932 s
        sabine = sabine_rt60(V, S * alpha)
        eyring_res = eyring_rt60(V, S, alpha)
        assert eyring_res["ok"] and sabine["ok"]
        # Both should be in the same ballpark (within 15%)
        assert abs(eyring_res["rt60_s"] - sabine["rt60_s"]) / sabine["rt60_s"] < 0.15

    def test_alpha_boundary_returns_error(self):
        res = eyring_rt60(300.0, 250.0, 1.0)
        assert res["ok"] is False

    def test_alpha_zero_returns_error(self):
        res = eyring_rt60(300.0, 250.0, 0.0)
        assert res["ok"] is False

    def test_hand_calc(self):
        """V=100, S=100, α=0.5: RT60 = 0.161×100/(−100×ln(0.5)) = 16.1/(69.315) ≈ 0.2323 s."""
        V = 100.0
        S = 100.0
        alpha = 0.5
        expected = 0.161 * V / (-S * math.log(1.0 - alpha))
        res = eyring_rt60(V, S, alpha)
        assert res["ok"] is True
        assert abs(res["rt60_s"] - expected) < REL


# ===========================================================================
# 9. room_constant
# ===========================================================================

class TestRoomConstant:

    def test_hand_calc(self):
        """R = 200 × 0.2 / (1 − 0.2) = 40 / 0.8 = 50 m²."""
        res = room_constant(200.0, 0.2)
        assert res["ok"] is True
        assert abs(res["R_m2"] - 50.0) < REL

    def test_alpha_one_returns_error(self):
        res = room_constant(200.0, 1.0)
        assert res["ok"] is False

    def test_alpha_zero_returns_error(self):
        res = room_constant(200.0, 0.0)
        assert res["ok"] is False


# ===========================================================================
# 10. reverberant_spl
# ===========================================================================

class TestReverberantSpl:

    def test_hand_calc(self):
        """Lp_rev = 90 + 10·log10(4/50) = 90 + 10·log10(0.08) = 90 − 10.97 ≈ 79.03 dB."""
        Lw = 90.0
        R = 50.0
        expected = Lw + 10.0 * math.log10(4.0 / R)
        res = reverberant_spl(Lw, R)
        assert res["ok"] is True
        assert abs(res["lp_db"] - expected) < REL

    def test_larger_R_lower_spl(self):
        """More absorption (larger R) → quieter reverberant field."""
        r1 = reverberant_spl(90.0, 50.0)
        r2 = reverberant_spl(90.0, 200.0)
        assert r1["ok"] and r2["ok"]
        assert r1["lp_db"] > r2["lp_db"]

    def test_zero_R_returns_error(self):
        res = reverberant_spl(90.0, 0.0)
        assert res["ok"] is False


# ===========================================================================
# 11. mass_law_tl
# ===========================================================================

class TestMassLawTL:

    def test_hand_calc_100kg_500hz(self):
        """TL = 20·log10(100 × 500) − 47 = 20·log10(50000) − 47 = 93.98 − 47 = 46.98 dB."""
        m = 100.0
        f = 500.0
        expected = 20.0 * math.log10(m * f) - 47.0
        res = mass_law_tl(m, f)
        assert res["ok"] is True
        assert abs(res["tl_db"] - expected) < REL

    def test_doubling_mass_adds_6db(self):
        """Doubling surface density adds 20·log10(2) ≈ 6.02 dB to TL."""
        r1 = mass_law_tl(50.0, 1000.0)
        r2 = mass_law_tl(100.0, 1000.0)
        assert r1["ok"] and r2["ok"]
        delta = r2["tl_db"] - r1["tl_db"]
        assert abs(delta - 20.0 * math.log10(2.0)) < REL

    def test_octave_up_adds_6db(self):
        """Doubling frequency adds 20·log10(2) ≈ 6.02 dB to TL."""
        r1 = mass_law_tl(50.0, 500.0)
        r2 = mass_law_tl(50.0, 1000.0)
        assert r1["ok"] and r2["ok"]
        delta = r2["tl_db"] - r1["tl_db"]
        assert abs(delta - 20.0 * math.log10(2.0)) < REL

    def test_zero_mass_returns_error(self):
        res = mass_law_tl(0.0, 500.0)
        assert res["ok"] is False

    def test_tool_happy_path(self):
        raw = _run(run_acoustics_mass_law_tl(
            _ctx(), _args(surface_density_kg_m2=100.0, freq_hz=500.0)
        ))
        d = _ok_tool(raw)
        expected = 20.0 * math.log10(100.0 * 500.0) - 47.0
        assert abs(d["tl_db"] - expected) < REL


# ===========================================================================
# 12. composite_tl
# ===========================================================================

class TestCompositeTL:

    def test_uniform_wall_equals_element_tl(self):
        """Partition with identical elements returns that same TL."""
        elements = [
            {"area_m2": 5.0, "tl_db": 40.0},
            {"area_m2": 5.0, "tl_db": 40.0},
        ]
        res = composite_tl(elements)
        assert res["ok"] is True
        assert abs(res["tl_composite_db"] - 40.0) < REL

    def test_weak_element_dominates(self):
        """A 10 dB window in a 50 dB wall should significantly reduce composite TL."""
        elements = [
            {"area_m2": 9.0, "tl_db": 50.0},
            {"area_m2": 1.0, "tl_db": 10.0},
        ]
        res = composite_tl(elements)
        assert res["ok"] is True
        assert res["tl_composite_db"] < 30.0  # severely degraded

    def test_empty_elements_returns_error(self):
        res = composite_tl([])
        assert res["ok"] is False

    def test_total_area_correct(self):
        elements = [
            {"area_m2": 3.0, "tl_db": 35.0},
            {"area_m2": 2.0, "tl_db": 30.0},
        ]
        res = composite_tl(elements)
        assert res["ok"] is True
        assert abs(res["total_area_m2"] - 5.0) < REL


# ===========================================================================
# 13. spl_transmitted
# ===========================================================================

class TestSplTransmitted:

    def test_hand_calc(self):
        res = spl_transmitted(75.0, 30.0)
        assert res["ok"] is True
        assert abs(res["lp_transmitted"] - 45.0) < REL

    def test_zero_tl_unchanged(self):
        res = spl_transmitted(80.0, 0.0)
        assert res["ok"] is True
        assert abs(res["lp_transmitted"] - 80.0) < REL


# ===========================================================================
# 14. a_weighting_offset
# ===========================================================================

class TestAWeightingOffset:

    def test_1000hz_is_zero(self):
        """By definition, A-weighting correction at 1000 Hz = 0 dB."""
        res = a_weighting_offset(1000.0)
        assert res["ok"] is True
        assert abs(res["offset_db"]) < 0.05  # within 0.05 dB of 0

    def test_63hz_is_negative(self):
        """At 63 Hz, hearing sensitivity is low → large negative correction."""
        res = a_weighting_offset(63.0)
        assert res["ok"] is True
        assert res["offset_db"] < -20.0  # should be around -26 dB

    def test_4000hz_is_positive(self):
        """At 4 kHz, A-weighting correction is slightly positive (~+1 dB)."""
        res = a_weighting_offset(4000.0)
        assert res["ok"] is True
        assert 0.0 < res["offset_db"] < 2.0


# ===========================================================================
# 15. c_weighting_offset
# ===========================================================================

class TestCWeightingOffset:

    def test_1000hz_approx_zero(self):
        """C-weighting at 1000 Hz ≈ 0 dB."""
        res = c_weighting_offset(1000.0)
        assert res["ok"] is True
        assert abs(res["offset_db"]) < 0.1

    def test_63hz_small_negative(self):
        """C-weighting at 63 Hz is only slightly negative (~-0.8 dB)."""
        res = c_weighting_offset(63.0)
        assert res["ok"] is True
        assert -2.0 < res["offset_db"] < 0.0


# ===========================================================================
# 16. apply_weighting + octave_band_combine
# ===========================================================================

class TestWeightingAndCombine:

    def test_a_weighting_1khz_band_unchanged(self):
        """A-weighting adds 0 dB at 1 kHz (within tolerance)."""
        res = apply_weighting({1000: 70.0}, weighting="A")
        assert res["ok"] is True
        assert abs(res["weighted_bands"][1000] - 70.0) < 0.1

    def test_a_weighting_attenuation_at_low_freq(self):
        """At 63 Hz, A-weighted SPL is significantly lower than unweighted."""
        res = apply_weighting({63: 70.0}, weighting="A")
        assert res["ok"] is True
        assert res["weighted_bands"][63] < 50.0

    def test_unknown_weighting_returns_error(self):
        res = apply_weighting({1000: 70.0}, weighting="Z")
        assert res["ok"] is False

    def test_unknown_frequency_returns_error(self):
        res = apply_weighting({999: 70.0}, weighting="A")
        assert res["ok"] is False

    def test_octave_combine_single_band(self):
        """Single band: combined = that band's level."""
        res = octave_band_combine({1000: 75.0})
        assert res["ok"] is True
        assert abs(res["combined_db"] - 75.0) < REL

    def test_octave_combine_two_equal_bands(self):
        """Two equal bands → combined = band + 10·log10(2)."""
        res = octave_band_combine({500: 70.0, 1000: 70.0})
        assert res["ok"] is True
        expected = 70.0 + 10.0 * math.log10(2.0)
        assert abs(res["combined_db"] - expected) < REL

    def test_full_pipeline_a_weight_and_combine(self):
        """Flat 70 dB spectrum across 250–4000 Hz → combined dB(A) around 70 dB."""
        bands = {250: 70.0, 500: 70.0, 1000: 70.0, 2000: 70.0, 4000: 70.0}
        w = apply_weighting(bands, weighting="A")
        assert w["ok"] is True
        c = octave_band_combine(w["weighted_bands"])
        assert c["ok"] is True
        # Combined dB(A) should be > 70 (1 kHz band has 0 offset, 2 kHz +1.2, 4 kHz +1.0)
        assert c["combined_db"] > 70.0


# ===========================================================================
# 17. nc_rating
# ===========================================================================

class TestNcRating:

    def test_all_bands_below_nc15_returns_nc15(self):
        """A spectrum well below NC-15 limits should get NC-15 rating."""
        spectrum = {63: 40, 125: 30, 250: 25, 500: 20, 1000: 15, 2000: 12, 4000: 10, 8000: 9}
        res = nc_rating(spectrum)
        assert res["ok"] is True
        assert res["nc_rating"] == 15

    def test_spectrum_at_nc40_limits_returns_nc40(self):
        """Spectrum exactly matching NC-40 limits should get NC-40 rating."""
        nc40 = {63: 64, 125: 56, 250: 50, 500: 45, 1000: 41, 2000: 39, 4000: 38, 8000: 37}
        res = nc_rating(nc40)
        assert res["ok"] is True
        assert res["nc_rating"] == 40

    def test_exceeds_nc70_flagged(self):
        """Spectrum above NC-70 limits should flag exceeds_nc70."""
        loud = {63: 90, 125: 90, 250: 90, 500: 90, 1000: 90, 2000: 90, 4000: 90, 8000: 90}
        res = nc_rating(loud)
        assert res["ok"] is True
        assert res["exceeds_nc70"] is True

    def test_tool_happy_path(self):
        spectrum = {63: 55, 125: 44, 250: 35, 500: 29, 1000: 25, 2000: 22, 4000: 21, 8000: 20}
        raw = _run(run_acoustics_nc_rating(_ctx(), _args(octave_band_spls=spectrum)))
        d = _ok_tool(raw)
        assert d["nc_rating"] is not None


# ===========================================================================
# 18. nr_rating
# ===========================================================================

class TestNrRating:

    def test_quiet_spectrum_nr0(self):
        """Very quiet spectrum → NR-0."""
        quiet = {63: 40, 125: 30, 250: 25, 500: 20, 1000: 18, 2000: 16, 4000: 15, 8000: 14}
        res = nr_rating(quiet)
        assert res["ok"] is True
        assert res["nr_rating"] == 0

    def test_spectrum_at_nr30_limits(self):
        """Spectrum exactly at NR-30 limits → NR-30."""
        nr30 = {63: 73, 125: 62, 250: 53, 500: 47, 1000: 43, 2000: 40, 4000: 39, 8000: 38}
        res = nr_rating(nr30)
        assert res["ok"] is True
        assert res["nr_rating"] == 30

    def test_exceeds_nr75_flagged(self):
        loud = {63: 110, 125: 100, 250: 100, 500: 100, 1000: 100, 2000: 100, 4000: 100, 8000: 100}
        res = nr_rating(loud)
        assert res["ok"] is True
        assert res["exceeds_nr75"] is True


# ===========================================================================
# 19. duct_attenuation
# ===========================================================================

class TestDuctAttenuation:

    def test_lined_higher_than_unlined(self):
        """Lined duct has higher insertion loss than unlined at all bands."""
        r_lined = duct_attenuation(5.0, 0.3, lining="lined")
        r_unlined = duct_attenuation(5.0, 0.3, lining="unlined")
        assert r_lined["ok"] and r_unlined["ok"]
        for freq in (63, 125, 250, 500, 1000):
            assert r_lined["il_by_band_db"][freq] > r_unlined["il_by_band_db"][freq]

    def test_length_scales_linearly(self):
        """IL at 1 m doubled for 2 m duct."""
        r1 = duct_attenuation(1.0, 0.2, lining="lined")
        r2 = duct_attenuation(2.0, 0.2, lining="lined")
        assert r1["ok"] and r2["ok"]
        for freq in (125, 500, 1000):
            assert abs(r2["il_by_band_db"][freq] - 2.0 * r1["il_by_band_db"][freq]) < REL

    def test_invalid_lining_returns_error(self):
        res = duct_attenuation(5.0, 0.3, lining="foam")
        assert res["ok"] is False

    def test_tool_happy_path(self):
        raw = _run(run_acoustics_duct_attenuation(
            _ctx(), _args(length_m=5.0, diam_m=0.3, lining="lined")
        ))
        d = _ok_tool(raw)
        # JSON serialization converts int keys to strings
        keys = {int(k) for k in d["il_by_band_db"]}
        assert 1000 in keys


# ===========================================================================
# 20. duct_breakout_spl
# ===========================================================================

class TestDuctBreakoutSpl:

    def test_hand_calc(self):
        """Lw_in=80, length=2m, perimeter=0.8m, TL=20 dB:
        area = 2×0.8 = 1.6 m²
        Lp = 80 − 20 + 10·log10(1.6) ≈ 80 − 20 + 2.04 = 62.04 dB."""
        res = duct_breakout_spl(80.0, 2.0, 0.8, 20.0)
        assert res["ok"] is True
        expected = 80.0 - 20.0 + 10.0 * math.log10(2.0 * 0.8)
        assert abs(res["lp_breakout"] - expected) < REL

    def test_higher_tl_lower_breakout(self):
        r1 = duct_breakout_spl(80.0, 2.0, 0.8, 20.0)
        r2 = duct_breakout_spl(80.0, 2.0, 0.8, 30.0)
        assert r1["ok"] and r2["ok"]
        assert r2["lp_breakout"] < r1["lp_breakout"]


# ===========================================================================
# 21. duct_regen_spl
# ===========================================================================

class TestDuctRegenSpl:

    def test_elbow_90_higher_than_elbow_45(self):
        """90° elbow generates more noise than 45° at same velocity."""
        r90 = duct_regen_spl(5.0, 0.3, "elbow_90")
        r45 = duct_regen_spl(5.0, 0.3, "elbow_45")
        assert r90["ok"] and r45["ok"]
        assert r90["Lw_regen_db"] > r45["Lw_regen_db"]

    def test_higher_velocity_more_noise(self):
        """Higher velocity → higher regenerated Lw."""
        r_low = duct_regen_spl(3.0, 0.3)
        r_high = duct_regen_spl(8.0, 0.3)
        assert r_low["ok"] and r_high["ok"]
        assert r_high["Lw_regen_db"] > r_low["Lw_regen_db"]

    def test_unknown_fitting_returns_error(self):
        res = duct_regen_spl(5.0, 0.3, "magic_fitting")
        assert res["ok"] is False


# ===========================================================================
# 22. lw_from_lp and lp_from_lw (roundtrip)
# ===========================================================================

class TestLwLpRoundtrip:

    def test_roundtrip_free_field(self):
        """lw_from_lp(lp_from_lw(Lw, r), r) == Lw."""
        Lw = 95.0
        r = 3.0
        lp_res = lp_from_lw(Lw, r, Q=1.0)
        assert lp_res["ok"] is True
        lw_res = lw_from_lp(lp_res["lp_db"], r, Q=1.0)
        assert lw_res["ok"] is True
        assert abs(lw_res["Lw_db"] - Lw) < REL

    def test_lw_from_lp_hand_calc(self):
        """Lw = Lp + 10·log10(4π r²) for Q=1.
        At r=1m: Lw = Lp + 10·log10(4π) ≈ Lp + 11.0 dB."""
        lp = 80.0
        r = 1.0
        expected_lw = lp + 10.0 * math.log10(4.0 * math.pi * r ** 2)
        res = lw_from_lp(lp, r, Q=1.0)
        assert res["ok"] is True
        assert abs(res["Lw_db"] - expected_lw) < REL

    def test_tool_lp_from_lw(self):
        raw = _run(run_acoustics_lp_from_lw(_ctx(), _args(lw_db=100.0, r_m=1.0)))
        d = _ok_tool(raw)
        expected = 100.0 + 10.0 * math.log10(1.0 / (4.0 * math.pi))
        assert abs(d["lp_db"] - expected) < REL

    def test_tool_lw_from_lp(self):
        raw = _run(run_acoustics_lw_from_lp(_ctx(), _args(lp_db=89.0, r_m=1.0, Q=1.0)))
        d = _ok_tool(raw)
        expected = 89.0 + 10.0 * math.log10(4.0 * math.pi)
        assert abs(d["Lw_db"] - expected) < REL

    def test_Q2_hemisphere_roundtrip(self):
        """Roundtrip with Q=2 (hemispherical field)."""
        Lw = 88.0
        r = 5.0
        lp_res = lp_from_lw(Lw, r, Q=2.0)
        lw_res = lw_from_lp(lp_res["lp_db"], r, Q=2.0)
        assert lw_res["ok"] is True
        assert abs(lw_res["Lw_db"] - Lw) < REL


# ===========================================================================
# 23. Error path coverage
# ===========================================================================

class TestErrorPaths:

    def test_point_source_zero_r(self):
        assert point_source_attenuation(90.0, 0.0)["ok"] is False

    def test_point_source_zero_Q(self):
        assert point_source_attenuation(90.0, 1.0, Q=0.0)["ok"] is False

    def test_sabine_zero_absorption(self):
        assert sabine_rt60(100.0, 0.0)["ok"] is False

    def test_mass_law_zero_freq(self):
        assert mass_law_tl(50.0, 0.0)["ok"] is False

    def test_composite_tl_missing_area(self):
        assert composite_tl([{"tl_db": 30.0}])["ok"] is False

    def test_composite_tl_missing_tl(self):
        assert composite_tl([{"area_m2": 5.0}])["ok"] is False

    def test_duct_regen_zero_velocity(self):
        assert duct_regen_spl(0.0, 0.3)["ok"] is False

    def test_apply_weighting_empty(self):
        assert apply_weighting({})["ok"] is False

    def test_octave_combine_empty(self):
        assert octave_band_combine({})["ok"] is False

    def test_nc_rating_empty(self):
        assert nc_rating({})["ok"] is False

    def test_nr_rating_empty(self):
        assert nr_rating({})["ok"] is False


# ===========================================================================
# AUTHORITATIVE EXTERNAL REFERENCE CASES
# ---------------------------------------------------------------------------
# Cross-checked against Beranek "Acoustics", Kinsler & Frey "Fundamentals of
# Acoustics", IEC 61672-1 (weighting), ISO 140-3 (mass law).
# ===========================================================================

class TestAcousticsAuthoritativeReferences:
    def test_sabine_beranek(self):
        # Sabine RT60 = 0.161 V/A (SI, c=343 m/s). Beranek: V=1000 m3,
        # A=200 sabins -> 0.805 s.
        r = sabine_rt60(1000.0, 200.0)
        assert r["rt60_s"] == pytest.approx(0.805, abs=1e-3)

    def test_sabine_constant_value(self):
        # Sabine constant 24 ln(10)/c = 0.1611 (c=343). Check via V=A.
        r = sabine_rt60(100.0, 100.0)
        assert r["rt60_s"] == pytest.approx(0.161, abs=1e-3)

    def test_eyring_approaches_sabine_low_alpha(self):
        # Eyring -> Sabine for small alpha (Kinsler & Frey).
        rs = sabine_rt60(500.0, 0.05 * 400.0)
        re = eyring_rt60(500.0, 400.0, 0.05)
        assert re["rt60_s"] == pytest.approx(rs["rt60_s"], rel=0.05)

    def test_two_equal_sources_3db(self):
        # Doubling acoustic energy adds 10 log10(2) = 3.0103 dB.
        r = spl_sum([80.0, 80.0])
        assert r["spl_db"] == pytest.approx(83.0103, abs=1e-3)

    def test_ten_equal_sources_10db(self):
        # 10 equal sources add 10 dB.
        r = spl_sum([70.0] * 10)
        assert r["spl_db"] == pytest.approx(80.0, abs=1e-6)

    def test_mass_law_iso140(self):
        # Field-incidence mass law TL = 20 log10(m f) - 47 (ISO 140-3).
        # m=10 kg/m2, f=500 Hz -> 26.98 dB.
        r = mass_law_tl(10.0, 500.0)
        assert r["tl_db"] == pytest.approx(26.979, abs=1e-2)

    def test_mass_law_doubling_mass_6db(self):
        # Doubling mass (or freq) -> +6.02 dB (20 log10 2).
        a = mass_law_tl(10.0, 500.0)["tl_db"]
        b = mass_law_tl(20.0, 500.0)["tl_db"]
        assert (b - a) == pytest.approx(6.0206, abs=1e-3)

    def test_a_weighting_1khz_zero(self):
        # IEC 61672-1: A-weighting is 0 dB at 1 kHz by definition.
        r = a_weighting_offset(1000.0)
        assert r["offset_db"] == pytest.approx(0.0, abs=0.05)

    def test_a_weighting_table_values_iec(self):
        # IEC 61672-1 Table: A(100 Hz) ~ -19.1 dB, A(10 kHz) ~ -2.5 dB.
        assert a_weighting_offset(100.0)["offset_db"] == pytest.approx(-19.1, abs=0.2)
        assert a_weighting_offset(10000.0)["offset_db"] == pytest.approx(-2.5, abs=0.2)

    def test_inverse_square_6db_per_doubling(self):
        # Point source free field: -6.02 dB per distance doubling.
        r = inverse_square_delta(1.0, 2.0)
        assert r["delta_db"] == pytest.approx(-6.0206, abs=1e-3)
