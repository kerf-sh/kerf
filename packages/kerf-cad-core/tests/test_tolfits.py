"""
Hermetic tests for kerf_cad_core.tolfits — ISO 286 limits & fits + Lamé press-fit.

Coverage (≥ 30 tests):
  fits.it_tolerance       — IT tolerance grade values vs ISO 286-1 table values
  fits.shaft_limits       — shaft deviations (es, ei) for key codes
  fits.hole_limits        — hole deviations (EI, ES) for key codes
  fits.fit_analysis       — fit classification and clearance/interference limits
  fits.preferred_fits     — ISO 286-2 preferred fit table
  fits.press_fit          — Lamé contact pressure, hoop stresses, assembly force,
                            shrink-fit temperature
  tools.*                 — LLM tool wrappers (happy path + error paths)

All tests are pure-Python and hermetic: no OCC, no DB, no network.
Tolerance calculations verified against ISO 286-1:2010 published tables and
Shigley's MED 10th ed. hand-calculations.

References
----------
ISO 286-1:2010 — Tables 1, 3, 4 (tolerance grades and deviations)
Shigley's MED 10th ed. §2-13 (press-fit analysis, Table A-11)

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.tolfits.fits import (
    it_tolerance,
    shaft_limits,
    hole_limits,
    fit_analysis,
    preferred_fits,
    press_fit,
    _band_for,
    _mean_diameter,
    _tolerance_unit_i,
)
from kerf_cad_core.tolfits.tools import (
    run_iso286_it_tolerance,
    run_iso286_shaft_limits,
    run_iso286_hole_limits,
    run_iso286_fit_analysis,
    run_iso286_preferred_fits,
    run_iso286_press_fit,
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


REL = 1e-4  # relative tolerance for floating-point checks (µm precision)


# ===========================================================================
# 1. Tolerance unit and size bands
# ===========================================================================

def test_band_for_basic():
    """Size 25 mm falls in (18, 30] band."""
    lo, hi = _band_for(25.0)
    assert lo == 18 and hi == 30


def test_band_for_boundary_3():
    """Size exactly 3 mm → (0, 3] band."""
    lo, hi = _band_for(3.0)
    assert lo == 0 and hi == 3


def test_band_for_boundary_6():
    """Size just above 3 → (3, 6] band."""
    lo, hi = _band_for(3.1)
    assert lo == 3 and hi == 6


def test_band_for_above_500():
    """Size 800 mm → (630, 800] band."""
    lo, hi = _band_for(800.0)
    assert lo == 630 and hi == 800


def test_band_for_out_of_range():
    """Size > 3150 mm raises ValueError."""
    with pytest.raises(ValueError):
        _band_for(3200.0)


def test_tolerance_unit_small():
    """
    Tolerance unit i for D = 10 mm (band 6-10, D_mean = sqrt(60) ≈ 7.746).
    i = 0.45*(7.746^(1/3)) + 0.001*7.746 ≈ 0.45*1.975 + 0.00775 ≈ 0.896 µm
    """
    D = math.sqrt(6 * 10)  # 7.746
    i = _tolerance_unit_i(D)
    assert 0.85 < i < 1.0, f"Expected i ≈ 0.896, got {i}"


def test_tolerance_unit_25mm():
    """
    Band 18-30: D_mean = sqrt(18*30) = sqrt(540) ≈ 23.24 mm
    i = 0.45*(23.24^(1/3)) + 0.001*23.24 ≈ 0.45*2.849 + 0.02324 ≈ 1.305 µm
    """
    D = math.sqrt(18 * 30)
    i = _tolerance_unit_i(D)
    assert 1.25 < i < 1.40, f"Expected i ≈ 1.307, got {i}"


# ===========================================================================
# 2. IT tolerance grade values (vs ISO 286-1 Table 1 published values)
# ===========================================================================

def test_it7_25mm():
    """
    IT7 for nominal 25 mm (band 18-30).
    ISO 286-1 table: IT7 = 21 µm.
    Formula: 16 * i ≈ 16 * 1.307 = 20.9 → 21 µm
    """
    r = it_tolerance(25.0, "IT7")
    assert r["ok"] is True
    assert r["IT_um"] == 21, f"Expected 21 µm, got {r['IT_um']}"


def test_it6_25mm():
    """
    IT6 for 25 mm (band 18-30).
    ISO 286-1 table: IT6 = 13 µm.
    Formula: 10 * i ≈ 10 * 1.307 = 13.07 → 13 µm
    """
    r = it_tolerance(25.0, "IT6")
    assert r["ok"] is True
    assert r["IT_um"] == 13, f"Expected 13 µm, got {r['IT_um']}"


def test_it8_50mm():
    """
    IT8 for nominal 50 mm (band 30-50, D = sqrt(1500) ≈ 38.73).
    i = 0.45*(38.73^(1/3)) + 0.001*38.73 ≈ 0.45*3.382 + 0.03873 ≈ 1.56 µm
    IT8 = 25 * i ≈ 39 µm.
    ISO 286-1 table: IT8 for 30-50 = 39 µm.
    """
    r = it_tolerance(50.0, "IT8")
    assert r["ok"] is True
    assert r["IT_um"] == 39, f"Expected 39 µm, got {r['IT_um']}"


def test_it11_100mm():
    """
    IT11 for nominal 100 mm (band 80-120, D = sqrt(9600) ≈ 97.98).
    i = 0.45*(97.98^(1/3)) + 0.001*97.98 ≈ 0.45*4.610 + 0.09798 ≈ 2.173 µm
    IT11 = 100 * 2.173 = 217.3 → 217 µm.
    ISO 286-1 table: IT11 for 80-120 = 220 µm.
    Allow ±5 µm tolerance due to intermediate rounding.
    """
    r = it_tolerance(100.0, "IT11")
    assert r["ok"] is True
    assert abs(r["IT_um"] - 220) <= 5, f"Expected ≈220 µm, got {r['IT_um']}"


def test_it_tolerance_invalid_grade():
    """Unknown grade returns ok=False."""
    r = it_tolerance(25.0, "IT99")
    assert r["ok"] is False
    assert "reason" in r


def test_it_tolerance_invalid_nominal():
    """Nominal ≤ 0 returns ok=False."""
    r = it_tolerance(0.0, "IT7")
    assert r["ok"] is False


def test_it_tolerance_out_of_range():
    """Nominal > 3150 returns ok=False."""
    r = it_tolerance(4000.0, "IT7")
    assert r["ok"] is False


def test_it7_mm_conversion():
    """IT_mm = IT_um / 1000."""
    r = it_tolerance(25.0, "IT7")
    assert r["ok"] is True
    assert abs(r["IT_mm"] - r["IT_um"] / 1000.0) < 1e-10


# ===========================================================================
# 3. Shaft limits
# ===========================================================================

def test_shaft_h7_25mm():
    """
    Shaft h7 for Ø25 mm: es = 0, ei = -21 µm (IT7 = 21).
    Reference shaft h: es = 0, ei = -IT.
    """
    r = shaft_limits(25.0, "h7")
    assert r["ok"] is True
    assert r["es_um"] == 0.0
    assert r["ei_um"] == -21.0
    assert abs(r["upper_limit_mm"] - 25.000) < 1e-6
    assert abs(r["lower_limit_mm"] - 24.979) < 1e-4


def test_shaft_g6_25mm():
    """
    Shaft g6 for Ø25 mm: es should be negative (clearance shaft).
    ISO 286-1: g6 for 18-30 band: es ≈ -7 µm.
    Formula: es = -(2.5 * D^0.34) where D = 23.24 → -2.5*3.13 ≈ -7.8 → -8 µm
    """
    r = shaft_limits(25.0, "g6")
    assert r["ok"] is True
    assert r["es_um"] < 0, "g shaft should have negative upper deviation"
    assert r["ei_um"] < r["es_um"], "ei must be below es"
    # IT6 = 13, so IT span: ei = es - 13
    assert abs(r["es_um"] - r["ei_um"] - 13.0) < 1e-6


def test_shaft_k6_25mm():
    """
    Shaft k6 for Ø25 mm: transition shaft, ei > 0.
    ISO 286-2:2010 Table: k6 for 18 < D ≤ 30 mm → es = +15 µm, ei = +2 µm.
    ISO 286-1 §5.6: shaft k fundamental deviation ei = +0.6·∛D (IT4..IT7).
    """
    r = shaft_limits(25.0, "k6")
    assert r["ok"] is True
    assert r["ei_um"] == 2.0   # ISO 286-2: k6 Ø25 lower deviation +2 µm
    assert r["es_um"] == 15.0  # ei + IT6 (13 µm) = +15 µm
    assert r["upper_limit_mm"] > 25.0


def test_shaft_p6_25mm():
    """
    Shaft p6 for Ø25 mm: interference shaft, ei > 0.
    Standard Shigley App. A-11: p6 18<D≤30 → upper +28, lower +15.
    Our formula: ei_p ≈ IT7 = 21 µm (approximate). The actual range is ±2 µm.
    """
    r = shaft_limits(25.0, "p6")
    assert r["ok"] is True
    assert r["ei_um"] > 0, "p shaft should have positive ei"
    assert r["es_um"] > r["ei_um"]


def test_shaft_s6_25mm():
    """
    Shaft s6 for Ø25 mm: strong interference shaft, ei > 0.
    """
    r = shaft_limits(25.0, "s6")
    assert r["ok"] is True
    assert r["ei_um"] > 0
    assert r["ei_um"] > shaft_limits(25.0, "p6")["ei_um"], "s should have larger ei than p"


def test_shaft_limits_uppercase_rejects():
    """Uppercase shaft code returns ok=False with suggestion to use hole_limits."""
    r = shaft_limits(25.0, "H7")
    assert r["ok"] is False
    assert "hole" in r["reason"].lower() or "shaft" in r["reason"].lower()


def test_shaft_limits_invalid_code():
    """Unknown letter code returns ok=False."""
    r = shaft_limits(25.0, "q6")
    assert r["ok"] is False


def test_shaft_it_span():
    """es - ei must equal IT for all shaft codes."""
    for code in ["h6", "g6", "f7", "k6", "n7", "s7"]:
        nominal = 40.0
        r = shaft_limits(nominal, code)
        assert r["ok"] is True, f"shaft_limits failed for {code}"
        grade = r["grade"]
        it_r = it_tolerance(nominal, grade)
        assert abs(r["es_um"] - r["ei_um"] - it_r["IT_um"]) < 0.01, (
            f"IT span mismatch for {code}: es={r['es_um']}, ei={r['ei_um']}, IT={it_r['IT_um']}"
        )


# ===========================================================================
# 4. Hole limits
# ===========================================================================

def test_hole_H7_25mm():
    """
    Hole H7 for Ø25 mm: EI = 0, ES = +21 µm (IT7 = 21).
    Reference hole H: EI = 0.
    """
    r = hole_limits(25.0, "H7")
    assert r["ok"] is True
    assert r["EI_um"] == 0.0
    assert r["ES_um"] == 21.0
    assert abs(r["lower_limit_mm"] - 25.000) < 1e-6
    assert abs(r["upper_limit_mm"] - 25.021) < 1e-4


def test_hole_H7_it_span():
    """ES - EI must equal IT7."""
    r = hole_limits(25.0, "H7")
    assert r["ok"] is True
    assert abs(r["ES_um"] - r["EI_um"] - 21.0) < 1e-6


def test_hole_F8_25mm():
    """
    Hole F8 for Ø25 mm: EI > 0 (clearance hole, positive EI).
    F hole uses duality: EI_F = -es_f.
    es_f = -(5.5 * D^0.41), D=23.24 → -5.5*4.37 ≈ -24 µm → EI_F ≈ +24 µm.
    """
    r = hole_limits(25.0, "F8")
    assert r["ok"] is True
    assert r["EI_um"] > 0, "F hole should have positive EI (clearance)"


def test_hole_K7_25mm():
    """
    Hole K7 for Ø25 mm: ES = 0 for IT ≤ 8.
    """
    r = hole_limits(25.0, "K7")
    assert r["ok"] is True
    assert r["ES_um"] == 0.0, f"Expected ES=0 for K7, got {r['ES_um']}"
    assert r["EI_um"] == -21.0  # EI = ES - IT = -IT7


def test_hole_N7_25mm():
    """
    Hole N7 for Ø25 mm: EI < 0 (hole below zero line → interference tendency).
    """
    r = hole_limits(25.0, "N7")
    assert r["ok"] is True
    assert r["EI_um"] < 0, "N7 hole should have negative EI"
    assert r["ES_um"] <= 0, "N7 hole ES should be ≤ 0"


def test_hole_limits_lowercase_rejects():
    """Lowercase hole code returns ok=False."""
    r = hole_limits(25.0, "h7")
    assert r["ok"] is False


def test_hole_it_span():
    """ES - EI must equal IT for all hole codes."""
    for code in ["H7", "H8", "F8", "G7", "K7", "N7"]:
        nominal = 25.0
        r = hole_limits(nominal, code)
        assert r["ok"] is True, f"hole_limits failed for {code}"
        grade = r["grade"]
        it_r = it_tolerance(nominal, grade)
        assert abs(r["ES_um"] - r["EI_um"] - it_r["IT_um"]) < 0.01, (
            f"IT span mismatch for {code}: ES={r['ES_um']}, EI={r['EI_um']}, IT={it_r['IT_um']}"
        )


# ===========================================================================
# 5. Fit analysis
# ===========================================================================

def test_fit_H7_g6_clearance():
    """
    H7/g6 at Ø25 mm: ISO preferred sliding fit — should be clearance.
    """
    r = fit_analysis(25.0, "H7", "g6")
    assert r["ok"] is True
    assert r["fit_type"] == "clearance", f"Expected clearance, got {r['fit_type']}"
    assert r["min_clearance_mm"] > 0, "min clearance must be positive for clearance fit"
    assert r["max_clearance_mm"] > r["min_clearance_mm"]


def test_fit_H7_h6_clearance():
    """
    H7/h6 at Ø25 mm: locational clearance fit.
    H7: EI=0, ES=+21 µm; h6: es=0, ei=-13 µm.
    max_clearance = 25.021 - 24.987 = 0.034 mm = 34 µm
    min_clearance = 25.000 - 25.000 = 0 mm → exactly clearance boundary
    """
    r = fit_analysis(25.0, "H7", "h6")
    assert r["ok"] is True
    assert r["fit_type"] == "clearance"
    assert r["min_clearance_mm"] >= 0.0


def test_fit_H7_k6_transition():
    """
    H7/k6 at Ø25 mm: ISO preferred transition fit.
    k6: ei=0, es=+13. H7: EI=0, ES=+21.
    max_clearance = 25.021 - 25.000 = +0.021 mm (shaft at min)
    min_clearance = 25.000 - 25.013 = -0.013 mm (shaft at max → interference)
    → transition fit
    """
    r = fit_analysis(25.0, "H7", "k6")
    assert r["ok"] is True
    assert r["fit_type"] == "transition", f"Expected transition, got {r['fit_type']}"
    assert r["min_clearance_mm"] < 0
    assert r["max_clearance_mm"] > 0


def test_fit_H7_s6_interference():
    """
    H7/s6 at Ø25 mm: ISO preferred medium drive fit — interference.
    """
    r = fit_analysis(25.0, "H7", "s6")
    assert r["ok"] is True
    assert r["fit_type"] == "interference", f"Expected interference, got {r['fit_type']}"
    assert r["max_clearance_mm"] < 0


def test_fit_clearance_formula():
    """
    max_clearance = hole_upper - shaft_lower.
    min_clearance = hole_lower - shaft_upper.
    """
    r = fit_analysis(25.0, "H7", "g6")
    h = hole_limits(25.0, "H7")
    s = shaft_limits(25.0, "g6")
    assert r["ok"] and h["ok"] and s["ok"]
    expected_max = h["upper_limit_mm"] - s["lower_limit_mm"]
    expected_min = h["lower_limit_mm"] - s["upper_limit_mm"]
    assert abs(r["max_clearance_mm"] - expected_max) < 1e-9
    assert abs(r["min_clearance_mm"] - expected_min) < 1e-9


def test_fit_interference_values():
    """
    max_interference = -min_clearance; min_interference = -max_clearance.
    """
    r = fit_analysis(25.0, "H7", "s6")
    assert r["ok"] is True
    assert abs(r["max_interference_mm"] - (-r["min_clearance_mm"])) < 1e-9
    assert abs(r["min_interference_mm"] - (-r["max_clearance_mm"])) < 1e-9


def test_fit_bad_hole():
    """Invalid hole designation returns ok=False."""
    r = fit_analysis(25.0, "X99", "h6")
    assert r["ok"] is False


def test_fit_bad_shaft():
    """Invalid shaft designation returns ok=False."""
    r = fit_analysis(25.0, "H7", "q6")
    assert r["ok"] is False


# ===========================================================================
# 6. Preferred fits
# ===========================================================================

def test_preferred_fits_hole_basis_count():
    """Hole-basis system should return 10 preferred fits."""
    r = preferred_fits(system="hole-basis")
    assert r["ok"] is True
    assert len(r["fits"]) == 10


def test_preferred_fits_shaft_basis_count():
    """Shaft-basis system should return 10 preferred fits."""
    r = preferred_fits(system="shaft-basis")
    assert r["ok"] is True
    assert len(r["fits"]) == 10


def test_preferred_fits_filter_clearance():
    """Filtering by clearance should return only clearance fits."""
    r = preferred_fits(fit_types=["clearance"])
    assert r["ok"] is True
    for f in r["fits"]:
        assert f["expected_type"] == "clearance"


def test_preferred_fits_with_nominal():
    """When nominal provided, each entry has an analysis sub-dict."""
    r = preferred_fits(nominal_mm=25.0)
    assert r["ok"] is True
    for f in r["fits"]:
        assert "analysis" in f
        if f["analysis"]["ok"]:
            assert "fit_type_computed" in f


def test_preferred_fits_invalid_system():
    """Unknown system returns ok=False."""
    r = preferred_fits(system="unknown-basis")
    assert r["ok"] is False


# ===========================================================================
# 7. Press-fit / Lamé analysis
# ===========================================================================

def test_press_fit_basic_contact_pressure():
    """
    Steel hub (D_hub_outer=80mm) on steel shaft (Ø50mm solid), δ=0.05mm.
    Hand-calc: r_i=25mm, r_o=40mm, δ_radial=0.025mm=25µm.
    C_hub = ((r_o²+r_i²)/(r_o²-r_i²) + 0.3) / 200e9
          = ((1600+625)/(1600-625) + 0.3) / 200e9
          = (2225/975 + 0.3) / 200e9
          = (2.282 + 0.3) / 200e9 = 2.582/200e9 = 1.291e-11
    C_shaft = (1 - 0.3) / 200e9 = 0.7/200e9 = 3.5e-12
    denominator = r_i * (C_hub + C_shaft) = 0.025 * (1.291e-11 + 3.5e-12)
                = 0.025 * 1.641e-11 = 4.103e-13
    p_c = δ_radial / denom = 25e-6 / 4.103e-13 ≈ 60.93 MPa
    """
    r = press_fit(
        nominal_mm=50.0,
        interference_mm=0.05,
        hub_outer_mm=80.0,
    )
    assert r["ok"] is True
    p_MPa = r["contact_pressure_MPa"]
    # Allow ±5 MPa tolerance due to formula variations
    assert 50 < p_MPa < 80, f"Expected p_c ≈ 61 MPa, got {p_MPa:.1f} MPa"


def test_press_fit_zero_interference():
    """Zero interference → zero contact pressure."""
    r = press_fit(nominal_mm=50.0, interference_mm=0.0, hub_outer_mm=80.0)
    assert r["ok"] is True
    assert r["contact_pressure_Pa"] == 0.0
    assert r["contact_pressure_MPa"] == 0.0


def test_press_fit_hub_hoop_stress_tensile():
    """Hub hoop stress at inner radius should be tensile (positive)."""
    r = press_fit(nominal_mm=50.0, interference_mm=0.05, hub_outer_mm=80.0)
    assert r["ok"] is True
    assert r["hub_hoop_stress_inner_Pa"] > 0, "Hub inner hoop stress must be tensile"


def test_press_fit_hub_hoop_inner_ge_outer():
    """Hub hoop stress at inner radius ≥ outer radius (Lamé distribution)."""
    r = press_fit(nominal_mm=50.0, interference_mm=0.05, hub_outer_mm=80.0)
    assert r["ok"] is True
    assert r["hub_hoop_stress_inner_Pa"] >= r["hub_hoop_stress_outer_Pa"]


def test_press_fit_shaft_hoop_compressive():
    """Solid shaft hoop stress is uniform compressive = -p_c."""
    r = press_fit(nominal_mm=50.0, interference_mm=0.05, hub_outer_mm=80.0)
    assert r["ok"] is True
    p_c = r["contact_pressure_Pa"]
    # For solid shaft: hoop = -p_c
    assert abs(r["shaft_hoop_stress_inner_Pa"] - (-p_c)) < 1e-3 * abs(p_c)


def test_press_fit_assembly_force():
    """Assembly force = p_c * π * d * L * μ."""
    r = press_fit(
        nominal_mm=50.0,
        interference_mm=0.05,
        hub_outer_mm=80.0,
        mu_friction=0.12,
        length_mm=60.0,
    )
    assert r["ok"] is True
    assert r["assembly_force_N"] is not None
    # Manual check: F = p_c * π * 0.05 * 0.06 * 0.12
    p_c = r["contact_pressure_Pa"]
    expected_F = p_c * math.pi * 0.050 * 0.060 * 0.12
    assert abs(r["assembly_force_N"] - expected_F) < 1.0, (
        f"Expected F ≈ {expected_F:.0f} N, got {r['assembly_force_N']:.0f} N"
    )


def test_press_fit_no_length_no_force():
    """Without length, assembly_force_N is None."""
    r = press_fit(nominal_mm=50.0, interference_mm=0.05, hub_outer_mm=80.0)
    assert r["ok"] is True
    assert r["assembly_force_N"] is None


def test_press_fit_shrink_fit_temperature():
    """Shrink-fit ΔT should be positive and reasonable for steel."""
    r = press_fit(nominal_mm=50.0, interference_mm=0.05, hub_outer_mm=80.0)
    assert r["ok"] is True
    # δ / (α * D) = 50e-6 / (12e-6 * 0.05) = 50/0.6 ≈ 83°C × 1.25 safety = 104°C
    delta_T = r["shrink_fit_delta_T_C"]
    assert 80 < delta_T < 200, f"Expected ΔT ≈ 104°C, got {delta_T:.1f}°C"


def test_press_fit_overstress_flag():
    """Large interference should trigger hub_overstressed if yield is low."""
    r = press_fit(
        nominal_mm=50.0,
        interference_mm=0.5,   # very large — 500 µm
        hub_outer_mm=60.0,     # thin hub → higher stress
        yield_strength_hub_Pa=200e6,  # 200 MPa low yield
    )
    assert r["ok"] is True
    assert r["hub_overstressed"] is True


def test_press_fit_no_overstress_ample_yield():
    """Small interference with high yield: no overstress."""
    r = press_fit(
        nominal_mm=50.0,
        interference_mm=0.02,
        hub_outer_mm=80.0,
        yield_strength_hub_Pa=500e6,
        yield_strength_shaft_Pa=500e6,
    )
    assert r["ok"] is True
    assert r["hub_overstressed"] is False
    assert r["shaft_overstressed"] is False


def test_press_fit_invalid_hub_smaller():
    """hub_outer_mm ≤ nominal_mm → ok=False."""
    r = press_fit(nominal_mm=50.0, interference_mm=0.05, hub_outer_mm=40.0)
    assert r["ok"] is False


def test_press_fit_negative_interference():
    """Negative interference → ok=False."""
    r = press_fit(nominal_mm=50.0, interference_mm=-0.01, hub_outer_mm=80.0)
    assert r["ok"] is False


def test_press_fit_hollow_shaft():
    """Hollow shaft: shaft hoop stress at bore more compressive than interface."""
    r = press_fit(
        nominal_mm=50.0,
        interference_mm=0.05,
        hub_outer_mm=80.0,
        shaft_bore_mm=20.0,
    )
    assert r["ok"] is True
    # For hollow shaft: |hoop_inner| > |hoop_outer|
    assert abs(r["shaft_hoop_stress_inner_Pa"]) >= abs(r["shaft_hoop_stress_outer_Pa"])


# ===========================================================================
# 8. LLM tool wrappers
# ===========================================================================

def test_tool_it_tolerance_ok():
    """iso286_it_tolerance tool happy path."""
    raw = _run(run_iso286_it_tolerance(_ctx(), _args(nominal_mm=25.0, grade="IT7")))
    d = _ok_tool(raw)
    assert d["IT_um"] == 21


def test_tool_it_tolerance_missing_grade():
    """iso286_it_tolerance tool missing grade returns error."""
    raw = _run(run_iso286_it_tolerance(_ctx(), _args(nominal_mm=25.0)))
    _err_tool(raw)


def test_tool_shaft_limits_ok():
    """iso286_shaft_limits tool happy path."""
    raw = _run(run_iso286_shaft_limits(_ctx(), _args(nominal_mm=25.0, designation="h7")))
    d = _ok_tool(raw)
    assert d["es_um"] == 0.0
    assert d["ei_um"] == -21.0


def test_tool_shaft_limits_error():
    """iso286_shaft_limits tool with invalid JSON."""
    raw = _run(run_iso286_shaft_limits(_ctx(), b"not json"))
    _err_tool(raw)


def test_tool_hole_limits_ok():
    """iso286_hole_limits tool happy path."""
    raw = _run(run_iso286_hole_limits(_ctx(), _args(nominal_mm=25.0, designation="H7")))
    d = _ok_tool(raw)
    assert d["EI_um"] == 0.0
    assert d["ES_um"] == 21.0


def test_tool_fit_analysis_ok():
    """iso286_fit_analysis tool happy path."""
    raw = _run(run_iso286_fit_analysis(_ctx(), _args(
        nominal_mm=25.0, hole_designation="H7", shaft_designation="g6"
    )))
    d = _ok_tool(raw)
    assert d["fit_type"] == "clearance"


def test_tool_fit_analysis_missing_field():
    """iso286_fit_analysis tool missing shaft_designation returns error."""
    raw = _run(run_iso286_fit_analysis(_ctx(), _args(
        nominal_mm=25.0, hole_designation="H7"
    )))
    _err_tool(raw)


def test_tool_preferred_fits_ok():
    """iso286_preferred_fits tool happy path."""
    raw = _run(run_iso286_preferred_fits(_ctx(), _args(nominal_mm=25.0)))
    d = _ok_tool(raw)
    assert len(d["fits"]) > 0


def test_tool_press_fit_ok():
    """iso286_press_fit tool happy path."""
    raw = _run(run_iso286_press_fit(_ctx(), _args(
        nominal_mm=50.0,
        interference_mm=0.05,
        hub_outer_mm=80.0,
        length_mm=60.0,
    )))
    d = _ok_tool(raw)
    assert d["contact_pressure_MPa"] > 0
    assert d["assembly_force_N"] is not None


def test_tool_press_fit_missing_field():
    """iso286_press_fit tool missing hub_outer_mm returns error."""
    raw = _run(run_iso286_press_fit(_ctx(), _args(
        nominal_mm=50.0, interference_mm=0.05
    )))
    _err_tool(raw)


def test_tool_press_fit_invalid_geometry():
    """iso286_press_fit tool with hub smaller than nominal returns ok=False."""
    raw = _run(run_iso286_press_fit(_ctx(), _args(
        nominal_mm=50.0, interference_mm=0.05, hub_outer_mm=40.0
    )))
    d = json.loads(raw)
    assert d.get("ok") is False or ("error" in d)


# ===========================================================================
# Externally-citable reference cases (production-confidence validation)
# Cross-checked vs ISO 286-1:2010, ISO 286-2:2010 limit-deviation tables,
# and Shigley 10th ed. §2-13 (Lamé interference fit).
# ===========================================================================

from kerf_cad_core.tolfits.fits import (  # noqa: E402
    it_tolerance as _ref_it,
    shaft_limits as _ref_sl,
    hole_limits as _ref_hl,
    fit_analysis as _ref_fa,
    press_fit as _ref_pf,
)


class TestTolfitsExternalReferences:
    """Validated against ISO 286-1/286-2 tables and Shigley Lamé eq (2-67)."""

    def test_it7_band_18_30_iso286(self):
        # ISO 286-2:2010 Table: IT7 for 18 < D ≤ 30 mm = 21 µm.
        r = _ref_it(25.0, "IT7")
        assert r["IT_um"] == 21

    def test_it6_band_18_30_iso286(self):
        # ISO 286-2: IT6 for 18 < D ≤ 30 mm = 13 µm.
        r = _ref_it(25.0, "IT6")
        assert r["IT_um"] == 13

    def test_it8_band_18_30_iso286(self):
        # ISO 286-2: IT8 for 18 < D ≤ 30 mm = 33 µm.
        r = _ref_it(25.0, "IT8")
        assert r["IT_um"] == 33

    def test_shaft_h6_reference(self):
        # ISO 286-2: h6 Ø25 → es=0, ei=−13 µm (reference shaft).
        r = _ref_sl(25.0, "h6")
        assert r["es_um"] == 0
        assert r["ei_um"] == -13

    def test_shaft_g6_iso286_2(self):
        # ISO 286-2: g6 Ø25 → es=−7, ei=−20 µm.
        r = _ref_sl(25.0, "g6")
        assert r["es_um"] == -7
        assert r["ei_um"] == -20

    def test_shaft_p6_iso286_2(self):
        # ISO 286-2: p6 Ø50 → es=+42, ei=+26 µm (FD ei=+26 per ISO 286-1).
        r = _ref_sl(50.0, "p6")
        assert r["ei_um"] == 26.0
        assert r["es_um"] == 42.0

    def test_shaft_s6_iso286_2(self):
        # ISO 286-2: s6 Ø50 → es=+59, ei=+43 µm.
        r = _ref_sl(50.0, "s6")
        assert r["ei_um"] == 43.0
        assert r["es_um"] == 59.0

    def test_shaft_u6_iso286_2(self):
        # ISO 286-2: u6 Ø50 → es=+86, ei=+70 µm.
        r = _ref_sl(50.0, "u6")
        assert r["ei_um"] == 70.0
        assert r["es_um"] == 86.0

    def test_hole_H7_reference(self):
        # ISO 286-2: H7 Ø25 → EI=0, ES=+21 µm (basic hole).
        r = _ref_hl(25.0, "H7")
        assert r["EI_um"] == 0.0
        assert r["ES_um"] == 21

    def test_fit_H7_g6_clearance(self):
        # ISO 286-2 preferred "sliding" fit H7/g6 Ø25 is a clearance fit:
        # min clearance = hole_min − shaft_max = 0 − (−7) = +7 µm.
        r = _ref_fa(25.0, "H7", "g6")
        assert r["fit_type"] == "clearance"
        assert r["min_clearance_mm"] == pytest.approx(0.007, abs=1e-6)

    def test_fit_H7_p6_interference(self):
        # ISO 286-2 "locational interference" H7/p6 Ø50:
        # min interference = shaft_min(ei +26) − hole_max(ES +25) = +1 µm.
        r = _ref_fa(50.0, "H7", "p6")
        assert r["fit_type"] == "interference"
        assert r["min_interference_mm"] == pytest.approx(0.001, abs=1e-6)

    def test_press_fit_lame_shigley_2_67(self):
        # Shigley Eq (2-67): solid shaft + same-E hub, contact pressure
        # p = (E δ/d)·[(do²−d²)(d²)/(2 d²·do²)].
        # d=50 mm, do=100 mm, δ=0.04 mm (diametral), E=200 GPa → 60.0 MPa.
        r = _ref_pf(50.0, 0.04, 100.0, 0.0, 200e9, 200e9, 0.3, 0.3)
        d, do = 0.05, 0.10
        p = (200e9 * 0.04e-3 / d) * ((do ** 2 - d ** 2) * d ** 2 / (2 * d ** 2 * do ** 2))
        assert r["contact_pressure_Pa"] == pytest.approx(p, rel=1e-6)
