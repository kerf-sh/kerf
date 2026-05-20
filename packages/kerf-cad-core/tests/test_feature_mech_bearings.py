"""
Feature tests: T-26 Mech — bearings catalog to housing fit.

Coverage (>=25 bearing codes):
  - Standard catalog codes across all four series (6000, 6200, 6300, NU200)
  - ISO 286-1 fits: H7/g6, H7/k6, H7/m6, H7/n6, H7/p6, N7/h6, K7/h6, etc.
  - Housing bore generation (bearing_housing_fit)
  - Shaft shoulder and housing lip geometry (bearing_shoulder_geometry)
  - Boundary / malformed input rejection
  - Idempotency -- calling functions twice with the same inputs gives identical results
  - Life and static-safety flow per catalog entry

All tests are pure-Python and hermetic: no OCC, no DB, no network.

References
----------
ISO 286-1:2010 -- Geometrical product specifications -- Limits and fits
ISO 281:2007   -- Rolling bearings -- Dynamic load ratings and rating life
SKF Bearing Catalogue, 2018 edition, sections 7, 12
"""
from __future__ import annotations

import math

import pytest

from kerf_cad_core.bearings.select import (
    bearing_adjusted_life,
    bearing_equivalent_load,
    bearing_rating_life,
    bearing_select,
    bearing_static_safety,
    bearing_limiting_speed,
    _SERIES_TABLE,
)
from kerf_cad_core.bearings.housing import (
    bearing_housing_fit,
    bearing_shoulder_geometry,
    _it_width,
)

REL = 1e-5


# ---------------------------------------------------------------------------
# Catalog fixtures -- one entry per built-in bearing code
# ---------------------------------------------------------------------------

# Extract all 40 built-in catalog entries as (series, bore, OD, B, C_N, C0_N, dm_mm)
_CATALOG_ENTRIES: list[tuple[str, float, float, float, float, float, float]] = [
    (series, bore, OD, B, C_N, C0_N, dm)
    for series, rows in _SERIES_TABLE.items()
    for bore, OD, B, C_N, C0_N, dm in rows
]

assert len(_CATALOG_ENTRIES) >= 25, (
    f"Expected at least 25 catalog entries for T-26, found {len(_CATALOG_ENTRIES)}"
)


# ===========================================================================
# 1. Standard catalog -- 25+ bearing codes validated
# ===========================================================================


class TestCatalogCodes:
    """Verify all 40 catalog entries have physically sane dimensions and ratings."""

    @pytest.mark.parametrize("series,bore,OD,B,C_N,C0_N,dm", _CATALOG_ENTRIES)
    def test_catalog_dimensions_sane(self, series, bore, OD, B, C_N, C0_N, dm):
        """Bearing dimensions are physically consistent."""
        assert bore > 0
        assert OD > bore, f"{series} bore={bore} OD={OD}: OD must exceed bore"
        assert B > 0
        assert C_N > 0
        assert C0_N > 0
        # dm must be inside the ring cross-section
        assert bore < dm < OD, f"{series} bore={bore} dm={dm} OD={OD}"

    @pytest.mark.parametrize("series,bore,OD,B,C_N,C0_N,dm", _CATALOG_ENTRIES)
    def test_catalog_rating_life_positive(self, series, bore, OD, B, C_N, C0_N, dm):
        """L10 life for a moderate load (30% of C_N) is finite and positive."""
        bt = "roller" if series == "NU200" else "ball"
        P = 0.3 * C_N
        res = bearing_rating_life(C=C_N, P=P, bearing_type=bt)
        assert res["ok"] is True
        assert res["L10_rev"] > 0
        assert math.isfinite(res["L10_rev"])

    @pytest.mark.parametrize("series,bore,OD,B,C_N,C0_N,dm", _CATALOG_ENTRIES)
    def test_catalog_static_safety_at_half_C0(self, series, bore, OD, B, C_N, C0_N, dm):
        """Static safety factor == 2 when P0 = 0.5 * C0."""
        res = bearing_static_safety(C0=C0_N, P0=0.5 * C0_N)
        assert res["ok"] is True
        assert res["s0"] == pytest.approx(2.0, rel=REL)

    @pytest.mark.parametrize("series,bore,OD,B,C_N,C0_N,dm", _CATALOG_ENTRIES)
    def test_catalog_limiting_speed_below_limit(self, series, bore, OD, B, C_N, C0_N, dm):
        """At 500 rpm all bearings are well within speed limits."""
        bt = "roller" if series == "NU200" else "ball"
        res = bearing_limiting_speed(dm_mm=dm, n_rpm=500.0, bearing_type=bt)
        assert res["ok"] is True
        assert res["utilisation"] < 1.0

    @pytest.mark.parametrize("series,bore,OD,B,C_N,C0_N,dm", _CATALOG_ENTRIES)
    def test_catalog_shoulder_geometry_ok(self, series, bore, OD, B, C_N, C0_N, dm):
        """Shoulder geometry succeeds for every catalog entry."""
        bt = "roller" if series == "NU200" else "ball"
        res = bearing_shoulder_geometry(bore_mm=bore, OD_mm=OD, B_mm=B, bearing_type=bt)
        assert res["ok"] is True
        assert res["shaft_shoulder_OD_mm"] > bore
        assert res["housing_lip_ID_mm"] < OD
        assert res["r_min_inner_mm"] > 0
        assert res["r_min_outer_mm"] > 0

    @pytest.mark.parametrize("series,bore,OD,B,C_N,C0_N,dm", _CATALOG_ENTRIES)
    def test_catalog_housing_fit_H7k6(self, series, bore, OD, B, C_N, C0_N, dm):
        """H7/k6 fit computes non-trivially for every catalog bore/OD."""
        res = bearing_housing_fit(bore_mm=bore, OD_mm=OD, shaft_fit="k6", housing_fit="H7")
        assert res["ok"] is True
        assert res["shaft_IT_um"] > 0
        assert res["housing_IT_um"] > 0
        # H7 housing: EI = 0, ES > 0 --> clearance
        assert res["housing_EI_um"] == pytest.approx(0.0)
        assert res["housing_ES_um"] > 0
        assert res["fit_type_housing"] == "clearance"
        # k6 shaft: transition fit
        assert res["fit_type_shaft"] in ("transition", "interference")


# ===========================================================================
# 2. ISO 286 fit correctness -- specific tolerance zone checks
# ===========================================================================


class TestISO286Fits:
    """Verify specific fit deviations against ISO 286-1:2010 reference values."""

    # Reference: bore=30 mm (>18, <=30 range), shaft k6 -> IT6=13 um, es=+2 um, ei=-11 um
    def test_k6_at_30mm_deviations(self):
        res = bearing_housing_fit(30, 62, shaft_fit="k6", housing_fit="H7")
        assert res["ok"] is True
        # IT6 for 18<d<=30 = 13 um
        assert res["shaft_IT_um"] == pytest.approx(13.0, abs=0.01)
        # k fundamental deviation at 30 mm -> es = +2 um
        assert res["shaft_es_um"] == pytest.approx(2.0, abs=0.01)
        # ei = es - IT = 2 - 13 = -11 um
        assert res["shaft_ei_um"] == pytest.approx(-11.0, abs=0.01)
        assert res["fit_type_shaft"] == "transition"

    # H7 housing at OD=62 mm (50<D<=80): IT7=30 um, EI=0, ES=+30
    def test_H7_at_62mm_deviations(self):
        res = bearing_housing_fit(30, 62, shaft_fit="h6", housing_fit="H7")
        assert res["ok"] is True
        assert res["housing_EI_um"] == pytest.approx(0.0, abs=0.01)
        assert res["housing_IT_um"] == pytest.approx(30.0, abs=0.01)
        assert res["housing_ES_um"] == pytest.approx(30.0, abs=0.01)
        assert res["fit_type_housing"] == "clearance"

    # h6 shaft = clearance fit (es=0, ei=-IT)
    def test_h6_shaft_is_clearance(self):
        res = bearing_housing_fit(25, 52, shaft_fit="h6", housing_fit="H7")
        assert res["ok"] is True
        # h: es = 0 (zero-line shaft), ei = -IT -- clearance by ISO convention
        assert res["shaft_es_um"] == pytest.approx(0.0, abs=0.01)
        assert res["shaft_ei_um"] < 0
        # h is always clearance (shaft below zero line for all fits)
        assert res["fit_type_shaft"] == "clearance"

    # n6 shaft -> interference for most sizes
    def test_n6_shaft_at_50mm(self):
        res = bearing_housing_fit(50, 90, shaft_fit="n6", housing_fit="H7")
        assert res["ok"] is True
        # n at 30<d<=50: es=17 um, IT6=16 um -> ei=1 um > 0 -> interference
        assert res["shaft_es_um"] == pytest.approx(17.0, abs=0.01)
        assert res["shaft_ei_um"] == pytest.approx(1.0, abs=0.01)
        assert res["fit_type_shaft"] == "interference"

    # p6 shaft -> interference
    def test_p6_shaft_interference(self):
        res = bearing_housing_fit(40, 80, shaft_fit="p6", housing_fit="H7")
        assert res["ok"] is True
        assert res["fit_type_shaft"] == "interference"
        assert res["shaft_ei_um"] > 0

    # g6 shaft -> clearance (es < 0)
    def test_g6_shaft_clearance(self):
        res = bearing_housing_fit(35, 72, shaft_fit="g6", housing_fit="H7")
        assert res["ok"] is True
        assert res["shaft_es_um"] < 0
        assert res["fit_type_shaft"] == "clearance"

    # N7 housing -> transition/interference (EI < 0)
    def test_N7_housing_negative_EI(self):
        res = bearing_housing_fit(30, 62, shaft_fit="k6", housing_fit="N7")
        assert res["ok"] is True
        assert res["housing_EI_um"] < 0
        assert res["fit_type_housing"] in ("transition", "interference")

    # K7 housing -> transition fit
    def test_K7_housing_transition(self):
        res = bearing_housing_fit(20, 47, shaft_fit="k6", housing_fit="K7")
        assert res["ok"] is True
        assert res["housing_EI_um"] < 0
        # K7 at 18<D<=30: EI=-2 um, IT7=21 um -> ES=+19 um -> transition
        assert res["fit_type_housing"] == "transition"

    # js5 shaft -> symmetric tolerance
    def test_js5_shaft_symmetric(self):
        res = bearing_housing_fit(20, 47, shaft_fit="js5", housing_fit="H7")
        assert res["ok"] is True
        # js: es = +IT/2, ei = -IT/2
        assert res["shaft_es_um"] == pytest.approx(-res["shaft_ei_um"], abs=0.01)
        assert res["fit_type_shaft"] == "transition"

    # f7 shaft -> clearance (negative es)
    def test_f7_shaft_clearance(self):
        res = bearing_housing_fit(17, 40, shaft_fit="f7", housing_fit="H7")
        assert res["ok"] is True
        assert res["shaft_es_um"] < 0
        assert res["fit_type_shaft"] == "clearance"

    # m6 shaft at bore=50 -> transition (es > 0 but ei < 0)
    def test_m6_shaft_at_50mm(self):
        res = bearing_housing_fit(50, 90, shaft_fit="m6", housing_fit="H7")
        assert res["ok"] is True
        # m at 30<d<=50: es=9 um, IT6=16 um -> ei=9-16=-7 um -> transition
        assert res["shaft_es_um"] == pytest.approx(9.0, abs=0.01)
        assert res["shaft_ei_um"] == pytest.approx(-7.0, abs=0.01)
        assert res["fit_type_shaft"] == "transition"

    # P7 housing at large OD -> interference or transition
    def test_P7_housing_large_OD(self):
        res = bearing_housing_fit(35, 80, shaft_fit="k6", housing_fit="P7")
        assert res["ok"] is True
        assert res["housing_EI_um"] < 0
        assert res["fit_type_housing"] in ("transition", "interference")


# ===========================================================================
# 3. Shoulder geometry -- lip and shoulder dimensions
# ===========================================================================


class TestShoulderGeometry:

    def test_shaft_shoulder_above_bore(self):
        """Shaft shoulder OD must be strictly greater than bore."""
        res = bearing_shoulder_geometry(20, 47, 14, "ball")
        assert res["ok"] is True
        assert res["shaft_shoulder_OD_mm"] > 20.0

    def test_housing_lip_below_OD(self):
        """Housing lip ID must be strictly less than OD."""
        res = bearing_shoulder_geometry(20, 47, 14, "ball")
        assert res["ok"] is True
        assert res["housing_lip_ID_mm"] < 47.0

    def test_shoulder_height_scaled_with_bore(self):
        """Larger bore -> larger shoulder height."""
        r_small = bearing_shoulder_geometry(10, 26, 8, "ball")
        r_large = bearing_shoulder_geometry(50, 110, 27, "ball")
        assert r_small["ok"] and r_large["ok"]
        assert r_large["shaft_shoulder_h_mm"] > r_small["shaft_shoulder_h_mm"]

    def test_roller_bearing_shoulder_larger_than_ball(self):
        """Roller bearings use 0.25*d vs 0.2*d, giving larger shoulders."""
        r_ball = bearing_shoulder_geometry(30, 62, 16, "ball")
        r_roller = bearing_shoulder_geometry(30, 62, 16, "roller")
        assert r_ball["ok"] and r_roller["ok"]
        assert r_roller["shaft_shoulder_h_mm"] >= r_ball["shaft_shoulder_h_mm"]

    def test_fillet_radius_increases_with_size(self):
        """Chamfer/fillet radius grows with bore size."""
        r_small = bearing_shoulder_geometry(10, 26, 8)
        r_large = bearing_shoulder_geometry(120, 215, 40)
        assert r_large["r_min_inner_mm"] >= r_small["r_min_inner_mm"]

    def test_small_bearing_chamfer(self):
        """Very small bearing (bore=10) uses r_min_inner=0.3 mm."""
        res = bearing_shoulder_geometry(10, 26, 8)
        assert res["ok"] is True
        assert res["r_min_inner_mm"] == pytest.approx(0.3, abs=0.01)

    def test_shoulder_height_gte_chamfer_plus_half(self):
        """Shoulder height must be >= r_min_inner + 0.5 mm (clears chamfer)."""
        res = bearing_shoulder_geometry(30, 62, 16, bearing_type="ball")
        assert res["ok"] is True
        assert res["shaft_shoulder_h_mm"] >= res["r_min_inner_mm"] + 0.5

    def test_housing_lip_height_gte_chamfer_plus_half(self):
        """Lip height must be >= r_min_outer + 0.5 mm."""
        res = bearing_shoulder_geometry(bore_mm=10, OD_mm=35, B_mm=11, bearing_type="ball")
        assert res["ok"] is True
        assert res["housing_lip_h_mm"] >= res["r_min_outer_mm"] + 0.5

    @pytest.mark.parametrize("series,bore,OD,B,C_N,C0_N,dm", _CATALOG_ENTRIES[:10])
    def test_shoulder_lip_geometry_for_10_entries(self, series, bore, OD, B, C_N, C0_N, dm):
        """First 10 catalog entries all produce valid shoulder geometry."""
        bt = "roller" if series == "NU200" else "ball"
        res = bearing_shoulder_geometry(bore_mm=bore, OD_mm=OD, B_mm=B, bearing_type=bt)
        assert res["ok"] is True
        assert res["shaft_shoulder_OD_mm"] > bore
        assert res["housing_lip_ID_mm"] < OD
        assert res["shaft_shoulder_h_mm"] > 0
        assert res["housing_lip_h_mm"] > 0


# ===========================================================================
# 4. Integration: catalog -> fit -> geometry pipeline
# ===========================================================================


class TestCatalogFitGeometryPipeline:
    """End-to-end: select bearing from catalog, compute fits and geometry."""

    def test_6200_30mm_full_pipeline(self):
        """6200/30 bearing: selection -> housing fit -> shoulder geometry."""
        sel = bearing_select(
            series="6200",
            Fr=2000.0,
            Fa=0.0,
            n_rpm=1000.0,
            Lh_min=5000.0,
            bearing_type="ball",
        )
        assert sel["ok"] is True
        assert sel["selected"] is not None
        b = sel["selected"]

        fit = bearing_housing_fit(
            bore_mm=b["bore_mm"],
            OD_mm=b["OD_mm"],
            shaft_fit="k6",
            housing_fit="H7",
        )
        assert fit["ok"] is True

        geo = bearing_shoulder_geometry(
            bore_mm=b["bore_mm"],
            OD_mm=b["OD_mm"],
            B_mm=b["B_mm"],
            bearing_type="ball",
        )
        assert geo["ok"] is True
        assert geo["shaft_shoulder_OD_mm"] > b["bore_mm"]
        assert geo["housing_lip_ID_mm"] < b["OD_mm"]

    def test_NU200_roller_full_pipeline(self):
        """NU200 cylindrical roller: life -> fit -> geometry."""
        # NU200/30: bore=30, OD=62, B=16, C=29600, C0=24000
        bore, OD, B = 30.0, 62.0, 16.0
        C_N, C0_N = 29600.0, 24000.0

        # Use P = 10% of C_N so life >> 1000 h
        life = bearing_adjusted_life(
            C=C_N,
            P=C_N * 0.10,
            n_rpm=800.0,
            bearing_type="roller",
            a1=1.0,
            a23=1.0,
        )
        assert life["ok"] is True
        assert life["Lna_hours"] > 5000.0

        fit = bearing_housing_fit(bore_mm=bore, OD_mm=OD, shaft_fit="h6", housing_fit="N7")
        assert fit["ok"] is True

        geo = bearing_shoulder_geometry(bore_mm=bore, OD_mm=OD, B_mm=B, bearing_type="roller")
        assert geo["ok"] is True
        assert geo["shaft_shoulder_h_mm"] >= geo["r_min_inner_mm"]

    def test_6300_series_high_load_pipeline(self):
        """6300 series: select bearing under heavy load, verify fit is computable.

        Use a moderate load and life target that the catalog can satisfy.
        The 6300/50 has C=61800 N; Fr=8000 N at 500 rpm gives plenty of life.
        """
        sel = bearing_select(
            series="6300",
            Fr=8000.0,
            Fa=1000.0,
            n_rpm=500.0,
            Lh_min=5000.0,
        )
        assert sel["ok"] is True
        assert sel["selected"] is not None
        b = sel["selected"]

        fit = bearing_housing_fit(
            bore_mm=b["bore_mm"],
            OD_mm=b["OD_mm"],
            shaft_fit="m6",
            housing_fit="H7",
        )
        assert fit["ok"] is True

    def test_6000_series_small_bearing_H7k6(self):
        """6000/10 (smallest catalog bearing): H7/k6 fit values are sensible."""
        res = bearing_housing_fit(bore_mm=10, OD_mm=26, shaft_fit="k6", housing_fit="H7")
        assert res["ok"] is True
        # IT6 at 6<d<=10 = 9 um; k at 6<d<=10 -> es=1 um, ei=1-9=-8 um
        assert res["shaft_IT_um"] == pytest.approx(9.0, abs=0.01)
        assert res["shaft_es_um"] == pytest.approx(1.0, abs=0.01)
        assert res["shaft_ei_um"] == pytest.approx(-8.0, abs=0.01)


# ===========================================================================
# 5. Boundary conditions
# ===========================================================================


class TestBoundaryConditions:

    # --- bearing_housing_fit boundaries ---

    def test_housing_fit_bore_zero_rejected(self):
        res = bearing_housing_fit(0, 62, "k6", "H7")
        assert res["ok"] is False

    def test_housing_fit_negative_bore_rejected(self):
        res = bearing_housing_fit(-10, 62, "k6", "H7")
        assert res["ok"] is False

    def test_housing_fit_OD_less_than_bore_rejected(self):
        res = bearing_housing_fit(62, 30, "k6", "H7")
        assert res["ok"] is False

    def test_housing_fit_OD_equal_bore_rejected(self):
        res = bearing_housing_fit(30, 30, "k6", "H7")
        assert res["ok"] is False

    def test_housing_fit_over_500mm_rejected(self):
        res = bearing_housing_fit(300, 600, "k6", "H7")
        assert res["ok"] is False

    def test_housing_fit_bad_shaft_designator_rejected(self):
        res = bearing_housing_fit(30, 62, "z9", "H7")
        assert res["ok"] is False

    def test_housing_fit_bad_housing_designator_rejected(self):
        res = bearing_housing_fit(30, 62, "k6", "Z7")
        assert res["ok"] is False

    def test_housing_fit_malformed_shaft_str_rejected(self):
        """Non-parseable shaft fit string (no grade number) must return ok=False."""
        res = bearing_housing_fit(30, 62, "k", "H7")
        assert res["ok"] is False

    def test_housing_fit_malformed_housing_str_rejected(self):
        res = bearing_housing_fit(30, 62, "k6", "H")
        assert res["ok"] is False

    def test_housing_fit_it_grade_too_high_rejected(self):
        """IT12 is beyond supported range (IT3-IT11) -> error."""
        res = bearing_housing_fit(30, 62, "k12", "H7")
        assert res["ok"] is False

    def test_housing_fit_it_grade_zero_rejected(self):
        res = bearing_housing_fit(30, 62, "k0", "H7")
        assert res["ok"] is False

    # --- bearing_shoulder_geometry boundaries ---

    def test_shoulder_bore_zero_rejected(self):
        res = bearing_shoulder_geometry(0, 62, 16)
        assert res["ok"] is False

    def test_shoulder_OD_le_bore_rejected(self):
        res = bearing_shoulder_geometry(62, 30, 16)
        assert res["ok"] is False

    def test_shoulder_width_zero_rejected(self):
        res = bearing_shoulder_geometry(30, 62, 0)
        assert res["ok"] is False

    def test_shoulder_negative_OD_rejected(self):
        res = bearing_shoulder_geometry(30, -62, 16)
        assert res["ok"] is False

    def test_shoulder_unknown_bearing_type_warns(self):
        """Unknown bearing_type returns ok=True but with a warning."""
        res = bearing_shoulder_geometry(30, 62, 16, bearing_type="needle")
        assert res["ok"] is True
        assert any("not recognized" in w for w in res["warnings"])

    # --- Smallest/largest catalog bearings ---

    def test_housing_fit_smallest_bore_10mm(self):
        """10mm bore (6000/10): H7/k6 fit is valid."""
        res = bearing_housing_fit(10, 26, "k6", "H7")
        assert res["ok"] is True
        assert res["shaft_IT_um"] > 0

    def test_housing_fit_largest_bore_70mm(self):
        """70mm bore (NU200/70): H7/k6 fit is valid."""
        res = bearing_housing_fit(70, 125, "k6", "H7")
        assert res["ok"] is True
        assert res["housing_IT_um"] > 0


# ===========================================================================
# 6. Malformed / invalid inputs
# ===========================================================================


class TestMalformedInputs:

    def test_housing_fit_none_bore_rejected(self):
        """None bore_mm must return ok=False."""
        try:
            res = bearing_housing_fit(None, 62, "k6", "H7")
            assert res["ok"] is False
        except (TypeError, ValueError):
            pass  # also acceptable

    def test_housing_fit_string_bore_rejected(self):
        try:
            res = bearing_housing_fit("thirty", 62, "k6", "H7")
            assert res["ok"] is False
        except (TypeError, ValueError):
            pass

    def test_housing_fit_inf_OD_rejected(self):
        res = bearing_housing_fit(30, float("inf"), "k6", "H7")
        assert res["ok"] is False

    def test_housing_fit_nan_bore_rejected(self):
        res = bearing_housing_fit(float("nan"), 62, "k6", "H7")
        assert res["ok"] is False

    def test_shoulder_geometry_inf_bore(self):
        res = bearing_shoulder_geometry(float("inf"), 62, 16)
        assert res["ok"] is False

    def test_shoulder_geometry_nan_width(self):
        res = bearing_shoulder_geometry(30, 62, float("nan"))
        assert res["ok"] is False

    def test_housing_fit_empty_string_shaft(self):
        res = bearing_housing_fit(30, 62, "", "H7")
        assert res["ok"] is False

    def test_housing_fit_empty_string_housing(self):
        res = bearing_housing_fit(30, 62, "k6", "")
        assert res["ok"] is False

    def test_housing_fit_numeric_grade_only(self):
        """Pure numeric string has no designator -> rejected."""
        res = bearing_housing_fit(30, 62, "6", "H7")
        assert res["ok"] is False

    def test_housing_fit_negative_OD_rejected(self):
        res = bearing_housing_fit(30, -62, "k6", "H7")
        assert res["ok"] is False

    def test_shoulder_geometry_negative_bore(self):
        res = bearing_shoulder_geometry(-30, 62, 16)
        assert res["ok"] is False


# ===========================================================================
# 7. Idempotency -- same inputs produce identical outputs
# ===========================================================================


class TestIdempotency:

    def test_housing_fit_idempotent(self):
        """Calling bearing_housing_fit twice returns identical dicts."""
        args = dict(bore_mm=40, OD_mm=80, shaft_fit="k6", housing_fit="H7")
        r1 = bearing_housing_fit(**args)
        r2 = bearing_housing_fit(**args)
        assert r1 == r2

    def test_shoulder_geometry_idempotent(self):
        args = dict(bore_mm=40, OD_mm=80, B_mm=18, bearing_type="ball")
        r1 = bearing_shoulder_geometry(**args)
        r2 = bearing_shoulder_geometry(**args)
        assert r1 == r2

    def test_housing_fit_idempotent_all_series(self):
        """Housing fit is idempotent for every catalog entry."""
        for series, bore, OD, B, C_N, C0_N, dm in _CATALOG_ENTRIES:
            r1 = bearing_housing_fit(bore, OD, "k6", "H7")
            r2 = bearing_housing_fit(bore, OD, "k6", "H7")
            assert r1 == r2, f"Not idempotent for {series} bore={bore}"

    def test_shoulder_geometry_idempotent_all_series(self):
        for series, bore, OD, B, C_N, C0_N, dm in _CATALOG_ENTRIES:
            bt = "roller" if series == "NU200" else "ball"
            r1 = bearing_shoulder_geometry(bore, OD, B, bt)
            r2 = bearing_shoulder_geometry(bore, OD, B, bt)
            assert r1 == r2, f"Not idempotent for {series} bore={bore}"

    def test_bearing_select_idempotent(self):
        """bearing_select is deterministic for same inputs."""
        args = dict(
            series="6200",
            Fr=3000.0,
            Fa=500.0,
            n_rpm=1500.0,
            Lh_min=10000.0,
            bearing_type="ball",
        )
        r1 = bearing_select(**args)
        r2 = bearing_select(**args)
        assert r1 == r2


# ===========================================================================
# 8. IT grade widths -- spot checks against ISO 286-1 Table 1
# ===========================================================================


class TestITGradeWidths:
    """Verify IT grade tolerance widths match ISO 286-1 reference values."""

    # (nominal_mm, grade, expected_um)
    @pytest.mark.parametrize(
        "nominal,grade,expected_um",
        [
            (5,   7,  12),   # 3<d<=6, IT7
            (8,   6,   9),   # 6<d<=10, IT6
            (15,  7,  18),   # 10<d<=18, IT7
            (25,  6,  13),   # 18<d<=30, IT6
            (25,  7,  21),   # 18<d<=30, IT7
            (40,  6,  16),   # 30<d<=50, IT6
            (40,  7,  25),   # 30<d<=50, IT7
            (65,  7,  30),   # 50<d<=80, IT7
            (100, 7,  35),   # 80<d<=120, IT7
            (150, 7,  40),   # 120<d<=180, IT7
            (220, 7,  46),   # 180<d<=250, IT7
            (280, 7,  52),   # 250<d<=315, IT7
        ],
    )
    def test_it_width(self, nominal, grade, expected_um):
        got = _it_width(nominal, grade)
        assert got == pytest.approx(float(expected_um), abs=0.01), (
            f"IT{grade} at nominal={nominal}mm: expected {expected_um}um, got {got}um"
        )

    def test_it_grade_out_of_range_returns_none(self):
        assert _it_width(30, 12) is None  # IT12 not in table
        assert _it_width(30, 1) is None   # IT1 not in table

    def test_it_width_size_out_of_range_returns_none(self):
        # 0 mm is not valid (bands are >over, so 0 mm falls outside)
        assert _it_width(0, 7) is None


# ===========================================================================
# 9. Fit classification correctness
# ===========================================================================


class TestFitClassification:
    """Systematic fit-type classification for common bearing fits."""

    @pytest.mark.parametrize(
        "shaft_fit,expected_type",
        [
            ("g6",  "clearance"),    # negative es -> clearance
            ("h6",  "clearance"),    # es=0 (zero-line shaft) -> clearance
            ("h5",  "clearance"),    # es=0 -> clearance
            ("js6", "transition"),   # symmetric: es=+IT/2, ei=-IT/2 -> transition
            ("k6",  "transition"),   # es=+2, ei=2-16=-14 -> transition
            ("n6",  "interference"), # es=+17, IT6=16, ei=+1 > 0 -> interference
            ("p6",  "interference"), # es=+26, IT6=16, ei=+10 > 0 -> interference
        ],
    )
    def test_shaft_fit_type_at_50mm(self, shaft_fit, expected_type):
        res = bearing_housing_fit(50, 90, shaft_fit=shaft_fit, housing_fit="H7")
        assert res["ok"] is True, f"Failed for shaft_fit={shaft_fit}: {res}"
        assert res["fit_type_shaft"] == expected_type, (
            f"shaft_fit={shaft_fit} at 50mm: expected {expected_type}, "
            f"got {res['fit_type_shaft']} "
            f"(es={res['shaft_es_um']}, ei={res['shaft_ei_um']})"
        )

    @pytest.mark.parametrize(
        "housing_fit,expected_type",
        [
            ("H7", "clearance"),    # EI=0, ES>0
            ("G7", "clearance"),    # EI>0, clearly clearance
            ("K7", "transition"),   # EI<0, ES>0
        ],
    )
    def test_housing_fit_type_at_OD47mm(self, housing_fit, expected_type):
        # OD=47mm (30<D<=50)
        res = bearing_housing_fit(20, 47, shaft_fit="k6", housing_fit=housing_fit)
        assert res["ok"] is True, f"Failed for housing_fit={housing_fit}: {res}"
        assert res["fit_type_housing"] == expected_type, (
            f"housing_fit={housing_fit} at OD=47mm: expected {expected_type}, "
            f"got {res['fit_type_housing']} "
            f"(EI={res['housing_EI_um']}, ES={res['housing_ES_um']})"
        )
