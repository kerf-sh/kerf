"""
Hermetic tests for kerf_cad_core.tolstack — 1D tolerance stack-up analysis.

Coverage:
  stack.analyze_stack   — worst-case, rss, mrss, monte-carlo methods
  stack._parse_contributors — asymmetric tolerances, degenerate inputs
  Algebraic consistency: WC >= RSS >= MRSS spread relationships
  MC seeded reproducibility
  tools.run_tolstack_analyze / run_tolstack_methods — LLM tool wrappers

All tests are pure-Python and hermetic: no OCC, no DB, no network.
Formulas verified against published expressions.

References
----------
Drake, 1999 — Dimensioning and Tolerancing Handbook (McGraw-Hill)
Bender, SAE 680490, 1968.

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.tolstack.stack import (
    analyze_stack,
    _wc_gap,
    _rss_analysis,
    _mrss_analysis,
    _mc_analysis,
    _parse_contributors,
    _normal_cdf,
    _lcg_uniform,
)
from kerf_cad_core.tolstack.tools import (
    run_tolstack_analyze,
    run_tolstack_methods,
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


REL = 1e-6  # relative tolerance for floating-point checks


# ---------------------------------------------------------------------------
# Simple contributor fixtures
# ---------------------------------------------------------------------------

def _simple_contributors(n=3):
    """Three equal ±0.1 contributors, all +1 direction, symmetric."""
    return [
        {"nominal": 10.0, "plus_tol": 0.1, "minus_tol": 0.1, "direction": 1}
        for _ in range(n)
    ]


def _mixed_contributors():
    """Mixed +/-1 directions: shaft-in-bore style."""
    return [
        {"nominal": 50.0, "plus_tol": 0.05, "minus_tol": 0.05, "direction": 1},  # bore
        {"nominal": 49.9, "plus_tol": 0.03, "minus_tol": 0.03, "direction": -1},  # shaft
    ]


# ===========================================================================
# 1. Worst-case method
# ===========================================================================

class TestWorstCase:

    def test_basic_gap_nominal(self):
        """gap_nominal = sum(direction × nominal)."""
        cs = _simple_contributors(3)
        res = analyze_stack(cs, method="worst-case")
        assert res["ok"] is True
        assert abs(res["gap_nominal"] - 30.0) < 1e-12

    def test_wc_gap_min_max_formula(self):
        """gap_min = nominal - Σtol, gap_max = nominal + Σtol."""
        cs = _simple_contributors(3)
        res = analyze_stack(cs, method="worst-case")
        assert abs(res["gap_min_wc"] - (30.0 - 0.3)) < 1e-12
        assert abs(res["gap_max_wc"] - (30.0 + 0.3)) < 1e-12

    def test_wc_gap_min_equals_gap_min_field(self):
        """For worst-case, gap_min == gap_min_wc."""
        cs = _simple_contributors(3)
        res = analyze_stack(cs, method="worst-case")
        assert res["gap_min"] == res["gap_min_wc"]
        assert res["gap_max"] == res["gap_max_wc"]

    def test_wc_no_sigma(self):
        """Worst-case returns sigma_gap=None, cp=None, cpk=None."""
        res = analyze_stack(_simple_contributors(2), method="worst-case")
        assert res["sigma_gap"] is None
        assert res["cp"] is None
        assert res["cpk"] is None

    def test_wc_mixed_directions(self):
        """Mixed directions: gap_nominal = bore - shaft."""
        cs = _mixed_contributors()
        res = analyze_stack(cs, method="worst-case")
        assert abs(res["gap_nominal"] - (50.0 - 49.9)) < 1e-12

    def test_wc_single_contributor(self):
        """Single contributor: gap = direction × nominal."""
        cs = [{"nominal": 5.0, "plus_tol": 0.02, "minus_tol": 0.02, "direction": -1}]
        res = analyze_stack(cs, method="worst-case")
        assert res["ok"] is True
        assert abs(res["gap_nominal"] - (-5.0)) < 1e-12

    def test_wc_warnings_list_present(self):
        """Result always includes a warnings list."""
        res = analyze_stack(_simple_contributors(1), method="worst-case")
        assert isinstance(res["warnings"], list)

    def test_wc_contributors_used_present(self):
        """Result includes contributors_used list."""
        res = analyze_stack(_simple_contributors(2), method="worst-case")
        assert isinstance(res["contributors_used"], list)
        assert len(res["contributors_used"]) == 2


# ===========================================================================
# 2. RSS method
# ===========================================================================

class TestRSS:

    def test_rss_sigma_formula(self):
        """sigma_gap = √Σ(tol_i/3)² for identical contributors."""
        cs = _simple_contributors(4)  # each tol=0.1
        res = analyze_stack(cs, method="rss")
        tol = 0.1
        sigma_expected = math.sqrt(4 * (tol / 3.0) ** 2)
        assert abs(res["sigma_gap"] - sigma_expected) / sigma_expected < REL

    def test_rss_gap_limits_3sigma(self):
        """gap_min/max == gap_nominal ± 3σ."""
        cs = _simple_contributors(4)
        res = analyze_stack(cs, method="rss")
        assert abs(res["gap_min"] - (res["gap_nominal"] - 3.0 * res["sigma_gap"])) < 1e-10
        assert abs(res["gap_max"] - (res["gap_nominal"] + 3.0 * res["sigma_gap"])) < 1e-10

    def test_rss_gap_narrower_than_wc(self):
        """RSS gap range must be narrower than worst-case range."""
        cs = _simple_contributors(5)
        rss = analyze_stack(cs, method="rss")
        wc = analyze_stack(cs, method="worst-case")
        assert rss["gap_min"] > wc["gap_min"]
        assert rss["gap_max"] < wc["gap_max"]

    def test_rss_cp_positive(self):
        """Cp must be > 0 for finite tolerances."""
        cs = _simple_contributors(3)
        res = analyze_stack(cs, method="rss")
        assert res["cp"] is not None
        assert res["cp"] > 0

    def test_rss_defect_ppm_non_negative(self):
        """defect_ppm must be >= 0."""
        res = analyze_stack(_simple_contributors(3), method="rss")
        assert res["defect_ppm"] >= 0

    def test_rss_yield_between_0_100(self):
        """yield_pct in [0, 100]."""
        res = analyze_stack(_simple_contributors(3), method="rss")
        assert 0.0 <= res["yield_pct"] <= 100.0

    def test_rss_yield_plus_defect_consistent(self):
        """yield_pct + defect_ppm/10000 ≈ 100 (within floating-point noise)."""
        res = analyze_stack(_simple_contributors(3), method="rss")
        # yield_pct = (1 - defect_ppm/1e6) × 100
        expected_yield = (1.0 - res["defect_ppm"] / 1e6) * 100.0
        assert abs(res["yield_pct"] - expected_yield) < 1e-6

    def test_rss_more_contributors_wider_sigma(self):
        """More contributors → larger sigma_gap."""
        cs3 = _simple_contributors(3)
        cs6 = _simple_contributors(6)
        sigma3 = analyze_stack(cs3, method="rss")["sigma_gap"]
        sigma6 = analyze_stack(cs6, method="rss")["sigma_gap"]
        assert sigma6 > sigma3


# ===========================================================================
# 3. Modified RSS / Benderized
# ===========================================================================

class TestMRSS:

    def test_mrss_gap_tol_formula(self):
        """gap_tol = Cf × √Σtol_i² with default Cf=1.5."""
        cs = _simple_contributors(3)  # each tol=0.1
        res = analyze_stack(cs, method="mrss")
        cf = 1.5
        gap_tol_expected = cf * math.sqrt(3 * 0.1 ** 2)
        gap_range = res["gap_max"] - res["gap_min"]
        assert abs(gap_range / 2.0 - gap_tol_expected) / gap_tol_expected < REL

    def test_mrss_cf_in_result(self):
        """bender_cf must be echoed in result."""
        res = analyze_stack(_simple_contributors(2), method="mrss", bender_cf=1.8)
        assert abs(res.get("bender_cf", 0) - 1.8) < 1e-12

    def test_mrss_wider_than_rss(self):
        """MRSS spread (Cf=1.5) must be wider than pure RSS (Cf≈1)."""
        cs = _simple_contributors(5)
        rss_range = analyze_stack(cs, method="rss")["gap_max"] - analyze_stack(cs, method="rss")["gap_min"]
        mrss_range = analyze_stack(cs, method="mrss")["gap_max"] - analyze_stack(cs, method="mrss")["gap_min"]
        assert mrss_range > rss_range

    def test_mrss_narrower_than_wc(self):
        """MRSS range must be narrower than worst-case."""
        cs = _simple_contributors(5)
        wc_range = analyze_stack(cs, method="worst-case")["gap_max"] - analyze_stack(cs, method="worst-case")["gap_min"]
        mrss_range = analyze_stack(cs, method="mrss")["gap_max"] - analyze_stack(cs, method="mrss")["gap_min"]
        assert mrss_range < wc_range

    def test_mrss_custom_cf(self):
        """Custom bender_cf=2.0 produces wider gap than cf=1.5."""
        cs = _simple_contributors(3)
        range15 = analyze_stack(cs, method="mrss", bender_cf=1.5)["gap_max"] - analyze_stack(cs, method="mrss", bender_cf=1.5)["gap_min"]
        range20 = analyze_stack(cs, method="mrss", bender_cf=2.0)["gap_max"] - analyze_stack(cs, method="mrss", bender_cf=2.0)["gap_min"]
        assert range20 > range15


# ===========================================================================
# 4. Monte-Carlo
# ===========================================================================

class TestMonteCarlo:

    def test_mc_seeded_reproducible(self):
        """Same seed + same inputs → identical gap_nominal and sigma_gap."""
        cs = _simple_contributors(3)
        r1 = analyze_stack(cs, method="monte-carlo", seed=99, n_samples=5000)
        r2 = analyze_stack(cs, method="monte-carlo", seed=99, n_samples=5000)
        assert r1["sigma_gap"] == r2["sigma_gap"]
        assert r1["mean_gap"] == r2["mean_gap"]
        assert r1["defect_ppm"] == r2["defect_ppm"]

    def test_mc_different_seed_different_result(self):
        """Different seeds → different sigma_gap (extremely high probability)."""
        cs = _simple_contributors(3)
        r1 = analyze_stack(cs, method="monte-carlo", seed=1, n_samples=2000)
        r2 = analyze_stack(cs, method="monte-carlo", seed=9999, n_samples=2000)
        # sigma_gap should differ (not deterministically equal)
        assert r1["sigma_gap"] != r2["sigma_gap"]

    def test_mc_mean_gap_close_to_nominal(self):
        """MC mean_gap should be close to gap_nominal for large n."""
        cs = _simple_contributors(4)
        res = analyze_stack(cs, method="monte-carlo", seed=42, n_samples=50000)
        assert abs(res["mean_gap"] - res["gap_nominal"]) < 0.01

    def test_mc_sigma_gap_close_to_rss(self):
        """MC sigma for normal contributors should be close to RSS sigma."""
        cs = _simple_contributors(4)
        rss = analyze_stack(cs, method="rss")
        mc = analyze_stack(cs, method="monte-carlo", seed=42, n_samples=100_000)
        rel_err = abs(mc["sigma_gap"] - rss["sigma_gap"]) / rss["sigma_gap"]
        assert rel_err < 0.05  # within 5%

    def test_mc_n_samples_in_result(self):
        """n_samples and seed echoed in result."""
        res = analyze_stack(_simple_contributors(2), method="monte-carlo", seed=7, n_samples=500)
        assert res["n_samples"] == 500
        assert res["seed"] == 7

    def test_mc_yield_between_0_100(self):
        """yield_pct in [0, 100]."""
        res = analyze_stack(_simple_contributors(3), method="monte-carlo", seed=42, n_samples=1000)
        assert 0.0 <= res["yield_pct"] <= 100.0

    def test_mc_uniform_distribution(self):
        """Uniform distribution contributors produce finite valid results."""
        cs = [
            {"nominal": 10.0, "plus_tol": 0.1, "minus_tol": 0.1,
             "direction": 1, "distribution": "uniform"},
            {"nominal": 5.0, "plus_tol": 0.05, "minus_tol": 0.05,
             "direction": 1, "distribution": "uniform"},
        ]
        res = analyze_stack(cs, method="monte-carlo", seed=42, n_samples=2000)
        assert res["ok"] is True
        assert math.isfinite(res["sigma_gap"])

    def test_mc_mixed_distributions(self):
        """Mixed normal + uniform contributors produce valid results."""
        cs = [
            {"nominal": 20.0, "plus_tol": 0.1, "minus_tol": 0.1,
             "direction": 1, "distribution": "normal"},
            {"nominal": 15.0, "plus_tol": 0.08, "minus_tol": 0.08,
             "direction": -1, "distribution": "uniform"},
        ]
        res = analyze_stack(cs, method="monte-carlo", seed=42, n_samples=3000)
        assert res["ok"] is True
        assert math.isfinite(res["sigma_gap"])

    def test_mc_cp_positive(self):
        """Cp must be > 0."""
        res = analyze_stack(_simple_contributors(3), method="monte-carlo", seed=42, n_samples=5000)
        assert res["cp"] > 0


# ===========================================================================
# 5. Cross-method consistency
# ===========================================================================

class TestCrossMethod:

    def test_wc_bounds_rss_range(self):
        """WC bounds must contain the RSS ±3σ range OR be equal for tight stacks."""
        cs = _simple_contributors(3)
        wc = analyze_stack(cs, method="worst-case")
        rss = analyze_stack(cs, method="rss")
        # RSS gap limits are tighter than WC; WC must bound them
        assert rss["gap_min"] >= wc["gap_min"]
        assert rss["gap_max"] <= wc["gap_max"]

    def test_wc_bounds_mrss_range(self):
        """WC bounds must contain the MRSS range."""
        cs = _simple_contributors(4)
        wc = analyze_stack(cs, method="worst-case")
        mrss = analyze_stack(cs, method="mrss")
        assert mrss["gap_min"] >= wc["gap_min"]
        assert mrss["gap_max"] <= wc["gap_max"]

    def test_gap_nominal_consistent_across_methods(self):
        """gap_nominal must be identical for all methods (pure arithmetic)."""
        cs = _mixed_contributors()
        gap_noms = [
            analyze_stack(cs, method=m)["gap_nominal"]
            for m in ("worst-case", "rss", "mrss", "monte-carlo")
        ]
        for v in gap_noms:
            assert abs(v - gap_noms[0]) < 1e-12

    def test_wc_range_monotone_in_n(self):
        """Adding more same-tolerance contributors widens WC range."""
        cs2 = _simple_contributors(2)
        cs4 = _simple_contributors(4)
        range2 = analyze_stack(cs2, method="worst-case")["gap_max_wc"] - analyze_stack(cs2, method="worst-case")["gap_min_wc"]
        range4 = analyze_stack(cs4, method="worst-case")["gap_max_wc"] - analyze_stack(cs4, method="worst-case")["gap_min_wc"]
        assert range4 > range2


# ===========================================================================
# 6. Degenerate and edge case inputs
# ===========================================================================

class TestEdgeCases:

    def test_empty_contributors(self):
        """Empty contributors list returns ok=True with zero gap."""
        res = analyze_stack([], method="worst-case")
        assert res["ok"] is True
        assert res["gap_nominal"] == 0.0
        assert len(res["warnings"]) > 0  # should warn about empty

    def test_zero_tolerance_contributors(self):
        """Zero-tolerance contributors produce warnings, not errors."""
        cs = [{"nominal": 10.0, "plus_tol": 0.0, "minus_tol": 0.0, "direction": 1}]
        res = analyze_stack(cs, method="rss")
        assert res["ok"] is True
        assert any("zero" in w.lower() or "0" in w for w in res["warnings"])

    def test_asymmetric_tolerance_warning(self):
        """Asymmetric tolerances produce a warning."""
        cs = [{"nominal": 10.0, "plus_tol": 0.2, "minus_tol": 0.05, "direction": 1}]
        res = analyze_stack(cs, method="rss")
        assert res["ok"] is True
        assert any("asymmetric" in w.lower() for w in res["warnings"])

    def test_asymmetric_tolerance_shifts_nominal(self):
        """Asymmetric tol: symmetrised nominal = original + (plus-minus)/2."""
        cs = [{"nominal": 10.0, "plus_tol": 0.3, "minus_tol": 0.1, "direction": 1}]
        res = analyze_stack(cs, method="worst-case")
        # bias = (0.3 - 0.1)/2 = 0.1 → adjusted nominal = 10.1
        assert abs(res["contributors_used"][0]["nominal"] - 10.1) < 1e-12

    def test_unknown_distribution_falls_back(self):
        """Unknown distribution string → warning, falls back to normal."""
        cs = [{"nominal": 5.0, "plus_tol": 0.1, "minus_tol": 0.1,
               "direction": 1, "distribution": "cauchy"}]
        res = analyze_stack(cs, method="rss")
        assert res["ok"] is True
        assert any("distribution" in w.lower() for w in res["warnings"])

    def test_invalid_direction_falls_back(self):
        """Invalid direction → warning, falls back to +1."""
        cs = [{"nominal": 5.0, "plus_tol": 0.1, "minus_tol": 0.1, "direction": 0}]
        res = analyze_stack(cs, method="rss")
        assert res["ok"] is True
        assert any("direction" in w.lower() for w in res["warnings"])

    def test_unknown_method_returns_error(self):
        """Unknown method string returns ok=False."""
        res = analyze_stack(_simple_contributors(2), method="super-rss")
        assert res["ok"] is False
        assert "reason" in res

    def test_invalid_n_samples_returns_error(self):
        """n_samples < 2 returns ok=False."""
        res = analyze_stack(_simple_contributors(2), method="monte-carlo", n_samples=1)
        assert res["ok"] is False

    def test_invalid_bender_cf_returns_error(self):
        """bender_cf <= 0 returns ok=False."""
        res = analyze_stack(_simple_contributors(2), method="mrss", bender_cf=-0.5)
        assert res["ok"] is False

    def test_contributors_not_list_returns_error(self):
        """contributors must be a list."""
        res = analyze_stack("not a list")  # type: ignore[arg-type]
        assert res["ok"] is False


# ===========================================================================
# 7. LCG and statistics primitives
# ===========================================================================

class TestPrimitives:

    def test_lcg_uniform_length(self):
        """LCG must produce exactly n samples."""
        samples = _lcg_uniform(42, 1000)
        assert len(samples) == 1000

    def test_lcg_uniform_range(self):
        """LCG samples must be in [0, 1)."""
        samples = _lcg_uniform(0, 500)
        assert all(0.0 <= s < 1.0 for s in samples)

    def test_lcg_deterministic(self):
        """Same seed always produces same sequence."""
        s1 = _lcg_uniform(7, 50)
        s2 = _lcg_uniform(7, 50)
        assert s1 == s2

    def test_normal_cdf_midpoint(self):
        """Normal CDF at 0 == 0.5."""
        assert abs(_normal_cdf(0.0) - 0.5) < 1e-12

    def test_normal_cdf_3sigma(self):
        """Normal CDF at ±3σ: P(|Z| < 3) ≈ 0.9973."""
        p_inside = _normal_cdf(3.0) - _normal_cdf(-3.0)
        assert abs(p_inside - 0.9973002) < 1e-5

    def test_parse_contributors_valid(self):
        """_parse_contributors returns correct length for valid inputs."""
        warnings = []
        parsed = _parse_contributors(
            [{"nominal": 1.0, "plus_tol": 0.1, "minus_tol": 0.1, "direction": 1}],
            warnings,
        )
        assert parsed is not None
        assert len(parsed) == 1
        assert abs(parsed[0]["tol"] - 0.1) < 1e-12


# ===========================================================================
# 8. LLM tool wrappers
# ===========================================================================

class TestToolWrappers:

    def test_run_tolstack_analyze_rss_happy_path(self):
        ctx = _ctx()
        cs = _simple_contributors(3)
        raw = _run(run_tolstack_analyze(ctx, _args(contributors=cs, method="rss")))
        d = _ok_tool(raw)
        assert d["sigma_gap"] > 0

    def test_run_tolstack_analyze_wc_happy_path(self):
        ctx = _ctx()
        cs = _simple_contributors(2)
        raw = _run(run_tolstack_analyze(ctx, _args(contributors=cs, method="worst-case")))
        d = _ok_tool(raw)
        assert d["gap_min"] < d["gap_max"]

    def test_run_tolstack_analyze_mrss_happy_path(self):
        ctx = _ctx()
        cs = _simple_contributors(3)
        raw = _run(run_tolstack_analyze(ctx, _args(contributors=cs, method="mrss")))
        d = _ok_tool(raw)
        assert d["ok"] is True
        assert d.get("bender_cf") is not None

    def test_run_tolstack_analyze_mc_happy_path(self):
        ctx = _ctx()
        cs = _simple_contributors(3)
        raw = _run(run_tolstack_analyze(
            ctx, _args(contributors=cs, method="monte-carlo", seed=42, n_samples=1000)
        ))
        d = _ok_tool(raw)
        assert d["n_samples"] == 1000

    def test_run_tolstack_analyze_missing_contributors(self):
        ctx = _ctx()
        raw = _run(run_tolstack_analyze(ctx, _args(method="rss")))
        _err_tool(raw)

    def test_run_tolstack_analyze_bad_json(self):
        ctx = _ctx()
        raw = _run(run_tolstack_analyze(ctx, b"not json {{{"))
        _err_tool(raw)

    def test_run_tolstack_analyze_bad_method(self):
        ctx = _ctx()
        cs = _simple_contributors(2)
        raw = _run(run_tolstack_analyze(ctx, _args(contributors=cs, method="garbage")))
        d = json.loads(raw)
        assert d.get("ok") is False or ("error" in d)

    def test_run_tolstack_methods_returns_all_methods(self):
        ctx = _ctx()
        raw = _run(run_tolstack_methods(ctx, _args()))
        d = json.loads(raw)
        # ok_payload may or may not inject ok=True; check the data is present
        assert d.get("ok") is not False, f"Unexpected error: {d}"
        # methods may be top-level or nested under 'methods' key
        methods = d.get("methods", d)
        assert "worst-case" in methods
        assert "rss" in methods
        assert "mrss" in methods
        assert "monte-carlo" in methods

    def test_run_tolstack_analyze_mc_seeded_via_tool(self):
        """Tool layer: same seed produces identical sigma_gap."""
        ctx = _ctx()
        cs = _simple_contributors(4)
        raw1 = _run(run_tolstack_analyze(ctx, _args(
            contributors=cs, method="monte-carlo", seed=123, n_samples=2000
        )))
        raw2 = _run(run_tolstack_analyze(ctx, _args(
            contributors=cs, method="monte-carlo", seed=123, n_samples=2000
        )))
        d1 = _ok_tool(raw1)
        d2 = _ok_tool(raw2)
        assert d1["sigma_gap"] == d2["sigma_gap"]
        assert d1["defect_ppm"] == d2["defect_ppm"]
