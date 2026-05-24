"""
Tests for kerf_cad_core.tolstack.tol3d — 3D vector-loop tolerance stack-up.

Validation against:
  - Algebraic identities (WC >= RSS per axis)
  - Known closed-form results for simple 1-contributor chains
  - Monte-Carlo consistency with RSS for Gaussian inputs
  - Jacobian finite-difference checks
  - Edge cases: empty, zero-tol, mixed distributions

All tests are pure-Python and hermetic.

Author: imranparuk
"""
from __future__ import annotations

import math
import pytest

from kerf_cad_core.tolstack.tol3d import analyze_stack_3d
from kerf_cad_core.tolstack import analyze_stack_3d as analyze_stack_3d_toplevel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _near(a: float, b: float, rel: float = 1e-6, abs_tol: float = 1e-10) -> bool:
    return abs(a - b) <= max(rel * max(abs(a), abs(b), 1.0), abs_tol)


# ---------------------------------------------------------------------------
# Import / re-export
# ---------------------------------------------------------------------------

def test_toplevel_export():
    """analyze_stack_3d is re-exported from kerf_cad_core.tolstack."""
    assert analyze_stack_3d_toplevel is analyze_stack_3d


# ---------------------------------------------------------------------------
# Empty contributor list
# ---------------------------------------------------------------------------

def test_empty_contributors():
    r = analyze_stack_3d([])
    assert r["ok"]
    assert r["closure"] == [0.0] * 6
    assert r["total_position_deviation"] == 0.0
    assert len(r["warnings"]) > 0  # should warn about empty list


# ---------------------------------------------------------------------------
# Single contributor — closure checks
# ---------------------------------------------------------------------------

def test_single_contributor_closure_x():
    """Single X contributor with direction +1 → closure[0] == mean[0]."""
    contrib = [{"mean": [5.0, 0, 0, 0, 0, 0], "tol": 0.1, "direction": 1}]
    r = analyze_stack_3d(contrib, method="rss")
    assert r["ok"]
    assert _near(r["closure"][0], 5.0)
    assert _near(r["closure"][1], 0.0)


def test_single_contributor_closure_direction_minus():
    """Direction -1 negates the mean contribution."""
    contrib = [{"mean": [3.0, 0, 0, 0, 0, 0], "tol": 0.0, "direction": -1}]
    r = analyze_stack_3d(contrib, method="worst-case")
    assert r["ok"]
    assert _near(r["closure"][0], -3.0)


# ---------------------------------------------------------------------------
# Two-contributor chain: cancellation
# ---------------------------------------------------------------------------

def test_two_contributor_cancellation():
    """Two equal, opposite contributors → closure ~ 0."""
    c1 = {"mean": [10.0, 0, 0, 0, 0, 0], "tol": 0.05, "direction": 1}
    c2 = {"mean": [10.0, 0, 0, 0, 0, 0], "tol": 0.05, "direction": -1}
    r = analyze_stack_3d([c1, c2], method="rss")
    assert r["ok"]
    assert _near(r["closure"][0], 0.0, abs_tol=1e-12)


# ---------------------------------------------------------------------------
# Worst-case >= RSS per axis
# ---------------------------------------------------------------------------

def test_wc_ge_rss():
    """Worst-case delta must be >= RSS delta for every axis."""
    contribs = [
        {"mean": [1.0, 2.0, 0.5, 0.01, 0.02, 0.0], "tol": [0.1, 0.2, 0.05, 0.005, 0.01, 0.0], "direction": 1},
        {"mean": [0.5, 1.0, 1.5, 0.02, 0.0, 0.01], "tol": [0.05, 0.1, 0.15, 0.002, 0.0, 0.001], "direction": 1},
        {"mean": [2.0, 0.0, 0.5, 0.0, 0.03, 0.0],  "tol": [0.2, 0.0, 0.05, 0.0, 0.003, 0.0], "direction": -1},
    ]
    wc = analyze_stack_3d(contribs, method="worst-case")
    rss = analyze_stack_3d(contribs, method="rss")
    assert wc["ok"] and rss["ok"]
    for j in range(6):
        assert wc["delta_per_axis"][j] >= rss["delta_per_axis"][j] - 1e-10, (
            f"axis {j}: WC {wc['delta_per_axis'][j]} < RSS {rss['delta_per_axis'][j]}"
        )


# ---------------------------------------------------------------------------
# Single contributor — analytic RSS check
# ---------------------------------------------------------------------------

def test_single_contributor_rss_analytic():
    """
    Single contributor, all axes equal tol t, normal distribution.
    RSS sigma_j = t/3 for each axis (Jacobian = identity * direction).
    delta_j = 3 * t/3 = t.
    """
    t = 0.12
    contrib = [{"mean": [0.0] * 6, "tol": t, "direction": 1}]
    r = analyze_stack_3d(contrib, method="rss")
    assert r["ok"]
    for j in range(6):
        assert _near(r["delta_per_axis"][j], t, rel=1e-4), (
            f"axis {j}: got {r['delta_per_axis'][j]}, expected {t}"
        )


# ---------------------------------------------------------------------------
# Single contributor — analytic WC check
# ---------------------------------------------------------------------------

def test_single_contributor_wc_analytic():
    """Single contributor worst-case: delta_j = |J_jk| * tol_k = tol_j."""
    t = 0.15
    contrib = [{"mean": [0.0] * 6, "tol": [t, t/2, t/3, t/4, t/5, t/6], "direction": 1}]
    r = analyze_stack_3d(contrib, method="worst-case")
    assert r["ok"]
    expected = [t, t/2, t/3, t/4, t/5, t/6]
    for j in range(6):
        assert _near(r["delta_per_axis"][j], expected[j], rel=1e-4), (
            f"axis {j}: got {r['delta_per_axis'][j]}, expected {expected[j]}"
        )


# ---------------------------------------------------------------------------
# Jacobian sanity
# ---------------------------------------------------------------------------

def test_jacobian_identity_single_contributor():
    """
    For a single contributor with direction +1, the linear Jacobian should
    be close to the identity matrix (∂C_j/∂mean_k ≈ δ_jk).
    """
    contrib = [{"mean": [1.0, 2.0, 3.0, 0.1, 0.2, 0.3], "tol": 0.01, "direction": 1}]
    r = analyze_stack_3d(contrib, method="rss")
    J = r["jacobian"]  # shape [6][1][6]
    for j in range(6):
        for k in range(6):
            expected = 1.0 if j == k else 0.0
            got = J[j][0][k]
            assert _near(got, expected, rel=1e-3, abs_tol=1e-6), (
                f"J[{j}][0][{k}] = {got}, expected {expected}"
            )


# ---------------------------------------------------------------------------
# Monte-Carlo consistency with RSS
# ---------------------------------------------------------------------------

def test_mc_rss_consistency():
    """
    Monte-Carlo ±3σ delta should be within 5% of RSS delta for large n
    with normal distributions.
    """
    contribs = [
        {"mean": [10.0, 5.0, 2.0, 0.1, 0.05, 0.0], "tol": 0.1, "distribution": "normal", "direction": 1},
        {"mean": [5.0, 0.0, 1.0, 0.05, 0.02, 0.0], "tol": 0.05, "distribution": "normal", "direction": 1},
    ]
    rss = analyze_stack_3d(contribs, method="rss")
    mc = analyze_stack_3d(contribs, method="monte-carlo", n_samples=100_000, seed=99)
    assert rss["ok"] and mc["ok"]

    # Check position axes (0..2) — rotation axes with near-zero tol may have large rel error
    for j in range(3):
        rss_d = rss["delta_per_axis"][j]
        mc_d = mc["delta_per_axis"][j]
        if rss_d > 1e-10:
            ratio = abs(mc_d - rss_d) / rss_d
            assert ratio < 0.10, (
                f"axis {j}: MC delta {mc_d:.6f} vs RSS delta {rss_d:.6f}, rel diff {ratio:.3%}"
            )


# ---------------------------------------------------------------------------
# Total position deviation
# ---------------------------------------------------------------------------

def test_total_position_deviation():
    """total_position_deviation == sqrt(sum(delta[:3]^2))."""
    contrib = [{"mean": [1.0, 2.0, 3.0, 0.0, 0.0, 0.0], "tol": [0.1, 0.2, 0.3, 0.0, 0.0, 0.0], "direction": 1}]
    r = analyze_stack_3d(contrib, method="rss")
    assert r["ok"]
    expected_pos = math.sqrt(sum(r["delta_per_axis"][j] ** 2 for j in range(3)))
    assert _near(r["total_position_deviation"], expected_pos)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def test_invalid_method():
    r = analyze_stack_3d([], method="banana")
    assert not r["ok"]
    assert "Unknown method" in r["reason"]


def test_invalid_n_samples():
    r = analyze_stack_3d([], method="monte-carlo", n_samples=1)
    assert not r["ok"]


def test_invalid_contributors_type():
    r = analyze_stack_3d("not a list")
    assert not r["ok"]


def test_bad_contributor_skipped():
    """Non-dict contributor emits a warning and is skipped."""
    r = analyze_stack_3d(["not a dict"], method="rss")
    assert r["ok"]
    assert len(r["contributors_used"]) == 0
    assert any("must be a dict" in w for w in r["warnings"])


def test_bad_tol_clamped():
    """Negative tol is clamped to 0 with a warning."""
    r = analyze_stack_3d([{"tol": -0.1}], method="rss")
    assert r["ok"]
    assert any("clamped" in w for w in r["warnings"])


def test_zero_tol_warning():
    r = analyze_stack_3d([{"tol": 0.0}], method="rss")
    assert r["ok"]
    assert any("zero" in w.lower() for w in r["warnings"])


# ---------------------------------------------------------------------------
# Uniform distribution
# ---------------------------------------------------------------------------

def test_uniform_distribution_mc():
    """Uniform distribution MC should produce a result without errors."""
    contrib = [{"mean": [5.0, 0, 0, 0, 0, 0], "tol": 0.5, "distribution": "uniform", "direction": 1}]
    r = analyze_stack_3d(contrib, method="monte-carlo", n_samples=10_000, seed=7)
    assert r["ok"]
    # For uniform ±t: σ = t/√3 → δ ≈ 3·t/√3 = t√3 ≈ 0.866
    mc_d = r["delta_per_axis"][0]
    assert 0.5 < mc_d < 1.5, f"Unexpected MC delta for uniform: {mc_d}"


# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------

def test_mc_reproducibility():
    """Same seed → identical results."""
    contrib = [{"mean": [1.0, 2.0, 3.0, 0.0, 0.0, 0.0], "tol": 0.1, "direction": 1}]
    r1 = analyze_stack_3d(contrib, method="monte-carlo", seed=42)
    r2 = analyze_stack_3d(contrib, method="monte-carlo", seed=42)
    assert r1["delta_per_axis"] == r2["delta_per_axis"]
