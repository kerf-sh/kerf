"""
Tests for kerf_cad_core.gdt.it_grades — canonical ISO 286-1 IT-grade system.

Validates against published ISO 286-1:2010 Table 1 reference values and
checks that the two former call sites (gdt_callouts/propose.py and
kerf-mates/tolerance.py) now return consistent results.
"""
from __future__ import annotations

import math
import sys

import pytest

from kerf_cad_core.gdt.it_grades import (
    it_tolerance_mm,
    IT_GRADE_MULTIPLIERS,
    VALID_GRADES,
    _find_dim_range,
    _tolerance_unit_i,
    _geometric_mean_diameter,
)
from kerf_cad_core.gdt_callouts.propose import it_grade_tolerance


# ---------------------------------------------------------------------------
# 1. ISO 286-1 published reference values (Table 1 spot-checks)
# ---------------------------------------------------------------------------

class TestISO286PublishedValues:
    """
    Spot-check against ISO 286-1:2010 Table 1 tolerance values.
    Tolerance = k * i, i = 0.45*D^(1/3) + 0.001*D, D = geom-mean of band.
    50mm nominal falls in (30, 50] band: D = sqrt(30*50) ≈ 38.73 mm.
    10mm nominal falls in (6, 10] band: D = sqrt(6*10) ≈ 7.75 mm.

    Published ISO 286-1 values (µm):
        IT7 @ 50mm  = 25 µm  → 0.025 mm
        IT6 @ 50mm  = 16 µm  → 0.016 mm
        IT7 @ 10mm  = 15 µm  → 0.015 mm
        IT8 @ 50mm  = 39 µm  → 0.039 mm  (k=25)
        IT9 @ 50mm  = 62 µm  → 0.062 mm  (k=40)
    """

    def test_it7_at_50mm(self):
        tol = it_tolerance_mm("IT7", 50.0)
        # ISO 286-1 publishes 25 µm; formula gives ~24.98 µm
        assert abs(tol * 1000 - 25.0) <= 1.0, f"IT7@50mm = {tol*1000:.2f}µm, expected ≈25µm"

    def test_it6_at_50mm(self):
        tol = it_tolerance_mm("IT6", 50.0)
        # ISO 286-1 publishes 16 µm; formula gives ~15.6 µm
        assert abs(tol * 1000 - 16.0) <= 1.5, f"IT6@50mm = {tol*1000:.2f}µm, expected ≈16µm"

    def test_it7_at_10mm(self):
        tol = it_tolerance_mm("IT7", 10.0)
        # ISO 286-1 publishes 15 µm; formula gives ~14.4 µm
        assert abs(tol * 1000 - 15.0) <= 1.5, f"IT7@10mm = {tol*1000:.2f}µm, expected ≈15µm"

    def test_it8_at_50mm(self):
        tol = it_tolerance_mm("IT8", 50.0)
        # ISO 286-1 publishes 39 µm (k=25)
        assert abs(tol * 1000 - 39.0) <= 2.0, f"IT8@50mm = {tol*1000:.2f}µm, expected ≈39µm"

    def test_it9_at_50mm(self):
        tol = it_tolerance_mm("IT9", 50.0)
        # ISO 286-1 publishes 62 µm (k=40)
        assert abs(tol * 1000 - 62.0) <= 2.0, f"IT9@50mm = {tol*1000:.2f}µm, expected ≈62µm"

    def test_tolerance_unit_at_38mm(self):
        # D for (30, 50] band = sqrt(30*50) ≈ 38.73 mm
        D = math.sqrt(30.0 * 50.0)
        i = _tolerance_unit_i(D)
        # i ≈ 0.45*38.73^(1/3) + 0.001*38.73 ≈ 0.45*3.382 + 0.0387 ≈ 1.561 µm
        assert 1.4 < i < 1.7, f"i(38.73mm) = {i:.4f}µm"


# ---------------------------------------------------------------------------
# 2. Basic structural properties
# ---------------------------------------------------------------------------

class TestStructuralProperties:
    def test_all_grades_positive(self):
        for grade in IT_GRADE_MULTIPLIERS:
            tol = it_tolerance_mm(grade, 25.0)
            assert tol > 0, f"{grade} produced non-positive tolerance"

    def test_coarser_grade_larger_tolerance(self):
        for nom in [5.0, 25.0, 100.0]:
            t6 = it_tolerance_mm("IT6", nom)
            t7 = it_tolerance_mm("IT7", nom)
            t11 = it_tolerance_mm("IT11", nom)
            assert t6 < t7, f"IT6 should be finer than IT7 at {nom}mm"
            assert t7 < t11, f"IT7 should be finer than IT11 at {nom}mm"

    def test_larger_nominal_larger_tolerance(self):
        t_small = it_tolerance_mm("IT7", 3.0)
        t_large = it_tolerance_mm("IT7", 200.0)
        assert t_large > t_small

    def test_case_insensitive(self):
        assert it_tolerance_mm("IT7", 50.0) == it_tolerance_mm("it7", 50.0)

    def test_unknown_grade_raises(self):
        with pytest.raises(ValueError, match="Unknown IT grade"):
            it_tolerance_mm("IT99", 50.0)

    def test_zero_nominal_does_not_raise(self):
        tol = it_tolerance_mm("IT7", 0.0)
        assert tol > 0

    def test_large_nominal_extrapolates(self):
        tol = it_tolerance_mm("IT7", 600.0)
        assert tol > 0


# ---------------------------------------------------------------------------
# 3. Consistency between former call sites
# ---------------------------------------------------------------------------

class TestCallSiteConsistency:
    """
    Both gdt_callouts/propose.py (it_grade_tolerance) and kerf-mates
    (grade_to_tolerance when given a nominal) must return the same values
    now that both delegate to it_tolerance_mm.
    """

    def test_propose_wrapper_matches_canonical(self):
        """it_grade_tolerance(nominal, grade) == it_tolerance_mm(grade, nominal)."""
        for grade in ["IT5", "IT6", "IT7", "IT8", "IT9", "IT10"]:
            for nom in [10.0, 25.0, 50.0, 100.0]:
                canonical = it_tolerance_mm(grade, nom)
                via_propose = it_grade_tolerance(nom, grade)
                assert canonical == via_propose, (
                    f"{grade}@{nom}mm: canonical={canonical}, propose={via_propose}"
                )

    def test_mates_grade_to_tolerance_with_nominal(self):
        """grade_to_tolerance with explicit nominal matches canonical."""
        try:
            from kerf_mates.tolerance import grade_to_tolerance
        except ImportError:
            pytest.skip("kerf-mates not installed in this environment")

        for grade in ["IT6", "IT7", "IT8"]:
            for nom in [10.0, 50.0]:
                canonical = it_tolerance_mm(grade, nom)
                via_mates = grade_to_tolerance(grade, nom)
                assert canonical == via_mates, (
                    f"{grade}@{nom}mm: canonical={canonical}, mates={via_mates}"
                )

    def test_mates_grade_to_tolerance_default_25mm(self):
        """grade_to_tolerance() default (25mm) matches canonical at 25mm."""
        try:
            from kerf_mates.tolerance import grade_to_tolerance
        except ImportError:
            pytest.skip("kerf-mates not installed in this environment")

        canonical_it7 = it_tolerance_mm("IT7", 25.0)
        via_mates = grade_to_tolerance("IT7")
        assert canonical_it7 == via_mates, (
            f"IT7@25mm default: canonical={canonical_it7}, mates={via_mates}"
        )

    def test_mates_unknown_grade_returns_zero(self):
        """grade_to_tolerance with unknown grade returns 0.0."""
        try:
            from kerf_mates.tolerance import grade_to_tolerance
        except ImportError:
            pytest.skip("kerf-mates not installed in this environment")
        assert grade_to_tolerance("IT99") == 0.0

    def test_mates_it_grade_tolerances_table_uses_canonical(self):
        """IT_GRADE_TOLERANCES dict is now derived from the canonical formula."""
        try:
            from kerf_mates.tolerance import IT_GRADE_TOLERANCES
        except ImportError:
            pytest.skip("kerf-mates not installed in this environment")

        # At 25mm reference, IT7 canonical ≈ 0.021mm (21µm); old table was 5µm
        # Verify it's now formula-based (much larger than old 5µm entry)
        it7_um = IT_GRADE_TOLERANCES["IT7"]  # stored as µm in the dict
        assert it7_um > 10.0, (
            f"IT_GRADE_TOLERANCES['IT7'] = {it7_um}µm; expected >10µm (formula-based)"
        )


# ---------------------------------------------------------------------------
# 4. Size-band selection
# ---------------------------------------------------------------------------

class TestSizeBandSelection:
    def test_3mm_maps_to_0_3_band(self):
        lo, hi = _find_dim_range(3.0)
        assert lo == 0.0 and hi == 3.0

    def test_10mm_maps_to_6_10_band(self):
        lo, hi = _find_dim_range(10.0)
        assert lo == 6.0 and hi == 10.0

    def test_50mm_maps_to_30_50_band(self):
        lo, hi = _find_dim_range(50.0)
        assert lo == 30.0 and hi == 50.0

    def test_zero_maps_to_first_band(self):
        lo, hi = _find_dim_range(0.0)
        assert lo == 0.0 and hi == 3.0

    def test_above_500_maps_to_last_band(self):
        lo, hi = _find_dim_range(600.0)
        assert lo == 400.0 and hi == 500.0

    def test_first_band_uses_D_equals_1_5(self):
        D = _geometric_mean_diameter(0.0, 3.0)
        assert D == 1.5
