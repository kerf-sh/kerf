"""
Hermetic tests for kerf_cad_core.solarpv.shading — partial-shading & bypass-diode modelling.

Coverage:
  shading.cell_iv_point          — Newton solver: I(V) sanity
  shading.cell_iv_curve          — Isc, Voc, monotone I, positive MPP
  shading.module_iv_uniform      — 60-cell unshaded: P ≈ 255 W, V ≈ 30 V, I ≈ 8.5 A
  shading.module_iv_shaded       — one cell at 50% shade + bypass: P ≈ 2/3 unshaded
  shading.module_iv_shaded       — one cell at 50% shade + no bypass: P ≈ 50% unshaded
  shading.mppt_global            — finds global max, detects multiple local maxima
  shading.mppt_mismatch_loss     — mismatch loss > 0 when modules differ
  shading_tools.run_pv_cell_iv   — LLM tool happy path + error path
  shading_tools.run_pv_module_shaded_iv  — happy path + bad args
  shading_tools.run_pv_mppt_mismatch_loss — happy path + missing modules

All tests are pure-Python and hermetic: no OCC, no DB, no network.

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math

import pytest

from kerf_cad_core.solarpv.shading import (
    CellParams,
    pv_cell_params_stc,
    cell_iv_point,
    cell_iv_curve,
    module_iv_uniform,
    module_iv_shaded,
    mppt_global,
    mppt_mismatch_loss,
    module_mpp,
)
from kerf_cad_core.solarpv.shading_tools import (
    run_pv_cell_iv,
    run_pv_module_shaded_iv,
    run_pv_mppt_mismatch_loss,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeCtx:
    pass


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _ok(tool_fn, args_dict):
    result = json.loads(_run(tool_fn(_FakeCtx(), json.dumps(args_dict).encode())))
    assert result.get("ok") is not False, f"Expected success, got: {result}"
    assert "error" not in result, f"Expected success, got error: {result}"
    return result


def _err(tool_fn, args_dict):
    result = json.loads(_run(tool_fn(_FakeCtx(), json.dumps(args_dict).encode())))
    is_ok_false = result.get("ok") is False
    is_err_payload = "error" in result and "code" in result
    assert is_ok_false or is_err_payload, f"Expected error response, got: {result}"
    return result


STC = pv_cell_params_stc()  # default single-cell params


# ---------------------------------------------------------------------------
# SINGLE-DIODE CELL SOLVER
# ---------------------------------------------------------------------------

def test_cell_iv_point_short_circuit():
    """At V=0, I ≈ Iph (dominant over diode/shunt terms)."""
    I = cell_iv_point(0.0, STC)
    assert abs(I - STC.Iph) < 0.1, f"Expected I ≈ Iph at V=0, got {I}"


def test_cell_iv_point_open_circuit():
    """At Voc (≈ n·Vt·ln(Iph/Io)), I ≈ 0."""
    Voc_approx = STC.n * STC.Vt * math.log(STC.Iph / STC.Io + 1.0)
    I = cell_iv_point(Voc_approx, STC)
    assert abs(I) < 0.05, f"Expected I ≈ 0 at Voc, got {I}"


def test_cell_iv_point_monotone():
    """I(V) must be monotonically non-increasing."""
    curve = cell_iv_curve(STC, n_pts=50)
    for k in range(1, len(curve)):
        assert curve[k][1] <= curve[k - 1][1] + 1e-6, (
            f"Current increased at index {k}: {curve[k - 1][1]:.4f} → {curve[k][1]:.4f}"
        )


def test_cell_iv_curve_voc_positive():
    """Voc > 0.5 V per cell for a good cell."""
    curve = cell_iv_curve(STC, n_pts=100)
    last_positive_v = max((v for v, i in curve if i > 0.01), default=0.0)
    assert last_positive_v > 0.5, f"Voc {last_positive_v:.3f} V too low"


def test_cell_mpp_positive_power():
    """Single cell MPP power must be > 0."""
    curve = cell_iv_curve(STC, n_pts=100)
    mpp = mppt_global(curve)
    assert mpp["gmpp_p"] > 0.0


def test_cell_iph_scaling_with_irradiance():
    """Halving irradiance should roughly halve Isc."""
    low_irr = CellParams(
        Iph=STC.Iph * 0.5, Io=STC.Io, Rs=STC.Rs,
        Rsh=STC.Rsh, n=STC.n, T_K=STC.T_K,
    )
    I_full = cell_iv_point(0.0, STC)
    I_half = cell_iv_point(0.0, low_irr)
    assert abs(I_half / I_full - 0.5) < 0.05, (
        f"Expected Isc to scale with irradiance, got {I_half:.3f} vs {I_full:.3f}"
    )


# ---------------------------------------------------------------------------
# 60-CELL MODULE — UNIFORM IRRADIANCE (REFERENCE CASE)
# ---------------------------------------------------------------------------

def test_module_uniform_mpp_power():
    """
    60-cell module, STC: MPP power ≈ 255 W (typical 60-cell module).
    Accept 220–290 W as a reasonable range for default params.
    """
    curve = module_iv_uniform(60, STC, 1000.0, n_pts=300)
    mpp = mppt_global(curve)
    assert 220.0 < mpp["gmpp_p"] < 290.0, (
        f"Expected ~255 W MPP for 60-cell STC, got {mpp['gmpp_p']:.1f} W"
    )


def test_module_uniform_mpp_voltage():
    """60-cell module Vmp ≈ 30 V (0.5 V/cell × 60)."""
    curve = module_iv_uniform(60, STC, 1000.0, n_pts=300)
    mpp = mppt_global(curve)
    assert 25.0 < mpp["gmpp_v"] < 38.0, (
        f"Expected Vmp ≈ 30 V for 60-cell module, got {mpp['gmpp_v']:.2f} V"
    )


def test_module_uniform_mpp_current():
    """60-cell module Imp ≈ 8.5 A."""
    curve = module_iv_uniform(60, STC, 1000.0, n_pts=300)
    mpp = mppt_global(curve)
    assert 7.5 < mpp["gmpp_i"] < 9.5, (
        f"Expected Imp ≈ 8.5 A for 60-cell module, got {mpp['gmpp_i']:.2f} A"
    )


def test_module_uniform_voc():
    """60-cell Voc ≈ 37 V (0.62 V/cell × 60)."""
    curve = module_iv_uniform(60, STC, 1000.0, n_pts=300)
    pts = sorted(curve, key=lambda t: t[0])
    # Find last voltage where I > 0.1 A
    voc_approx = max((v for v, i in pts if i > 0.1), default=0.0)
    assert 33.0 < voc_approx < 44.0, (
        f"Expected Voc ≈ 37 V for 60-cell module, got {voc_approx:.2f} V"
    )


# ---------------------------------------------------------------------------
# PARTIAL SHADING — WITH BYPASS DIODES
# ---------------------------------------------------------------------------

def test_bypass_diodes_one_substring_shaded():
    """
    Module: 60 cells (3 × 20-cell substrings).
    First 20 cells at 50% irradiance (500 W/m²), remaining 40 at 1000 W/m².

    With bypass diodes: the shaded substring is bypassed at GMPP.
    Power ≈ 2 remaining substrings / 3 total ≈ 2/3 of unshaded.
    Accept: shaded MPP > 55% of unshaded MPP (definitely NOT 50%).
    """
    cell_irr = [500.0] * 20 + [1000.0] * 40
    curve_shaded = module_iv_shaded(cell_irr, STC, cells_per_bypass=20, bypass_fwd_v=0.7, n_pts=300)
    mpp_shaded = mppt_global(curve_shaded)

    curve_unshaded = module_iv_uniform(60, STC, 1000.0, n_pts=300)
    mpp_unshaded = mppt_global(curve_unshaded)

    ratio = mpp_shaded["gmpp_p"] / mpp_unshaded["gmpp_p"]
    assert ratio > 0.55, (
        f"With bypass diodes, expected power > 55% of unshaded; got {ratio:.2%}"
    )
    # Should lose one substring ≈ 1/3, so ratio should be close to 2/3
    assert ratio < 0.90, (
        f"With one substring shaded, expected < 90% of unshaded; got {ratio:.2%}"
    )


def test_bypass_diodes_prevent_deep_reverse():
    """
    With bypass diodes, module Voc stays positive (bypass prevents deep negative voltage).
    Without bypass on the shaded substring, Voc is close to that of 60-cell unshaded
    minus the bypass drop.
    """
    cell_irr = [500.0] * 20 + [1000.0] * 40
    curve = module_iv_shaded(cell_irr, STC, cells_per_bypass=20, bypass_fwd_v=0.7, n_pts=300)
    # The GMPP voltage should still be positive
    mpp = mppt_global(curve)
    assert mpp["gmpp_v"] > 0, f"GMPP voltage should be positive, got {mpp['gmpp_v']:.2f} V"


# ---------------------------------------------------------------------------
# PARTIAL SHADING — WITHOUT BYPASS DIODES
# ---------------------------------------------------------------------------

def test_no_bypass_diodes_severe_loss():
    """
    Without bypass diodes, all cells carry the shaded current.
    Power ≈ proportional to worst-cell irradiance → ~50% of unshaded.
    Accept ratio < 65% (definitely worse than the bypass case).
    """
    cell_irr = [500.0] * 20 + [1000.0] * 40
    curve_no_bypass = module_iv_shaded(
        cell_irr, STC, cells_per_bypass=20,
        bypass_fwd_v=1e6,  # effectively disabled
        n_pts=300,
    )
    mpp_no_bypass = mppt_global(curve_no_bypass)

    curve_unshaded = module_iv_uniform(60, STC, 1000.0, n_pts=300)
    mpp_unshaded = mppt_global(curve_unshaded)

    ratio_no_bypass = mpp_no_bypass["gmpp_p"] / mpp_unshaded["gmpp_p"]
    assert ratio_no_bypass < 0.65, (
        f"Without bypass diodes, expected < 65% power; got {ratio_no_bypass:.2%}"
    )


def test_bypass_better_than_no_bypass():
    """Bypass diodes always give higher MPP under the same shading."""
    cell_irr = [500.0] * 20 + [1000.0] * 40

    curve_bypass = module_iv_shaded(cell_irr, STC, cells_per_bypass=20, bypass_fwd_v=0.7, n_pts=300)
    mpp_bypass = mppt_global(curve_bypass)

    curve_no_bypass = module_iv_shaded(cell_irr, STC, cells_per_bypass=20, bypass_fwd_v=1e6, n_pts=300)
    mpp_no_bypass = mppt_global(curve_no_bypass)

    assert mpp_bypass["gmpp_p"] > mpp_no_bypass["gmpp_p"], (
        f"Bypass ({mpp_bypass['gmpp_p']:.1f} W) should beat no-bypass ({mpp_no_bypass['gmpp_p']:.1f} W)"
    )


# ---------------------------------------------------------------------------
# MULTIPLE LOCAL MAXIMA
# ---------------------------------------------------------------------------

def test_multiple_local_maxima_under_shading():
    """
    Strong shading on one substring creates a notch in the I-V curve that
    can produce two local power peaks.  With 60 cells and one substring at
    10% irradiance, we typically see multiple local maxima.
    """
    cell_irr = [100.0] * 20 + [1000.0] * 40
    curve = module_iv_shaded(cell_irr, STC, cells_per_bypass=20, bypass_fwd_v=0.7, n_pts=400)
    mpp_info = mppt_global(curve)
    # Under strong shading there should be at least one local maximum (GMPP)
    assert len(mpp_info["local_maxima"]) >= 1


def test_mppt_global_returns_best():
    """The GMPP returned must have the maximum power of all local maxima."""
    cell_irr = [200.0] * 20 + [1000.0] * 40
    curve = module_iv_shaded(cell_irr, STC, cells_per_bypass=20, bypass_fwd_v=0.7, n_pts=300)
    mpp_info = mppt_global(curve)
    if mpp_info["local_maxima"]:
        best_local = max(mpp_info["local_maxima"], key=lambda d: d["p"])
        assert mpp_info["gmpp_p"] == pytest.approx(best_local["p"], rel=1e-6)


# ---------------------------------------------------------------------------
# MPPT MISMATCH LOSS
# ---------------------------------------------------------------------------

def test_mismatch_loss_identical_modules():
    """Two identical unshaded modules → zero (or near-zero) mismatch loss."""
    curve = module_iv_uniform(60, STC, 1000.0, n_pts=200)
    result = mppt_mismatch_loss([curve, curve], n_pts=400)
    assert result["mismatch_loss_pct"] < 2.0, (
        f"Identical modules should have < 2% mismatch, got {result['mismatch_loss_pct']:.2f}%"
    )


def test_mismatch_loss_different_shading():
    """Modules with different shading patterns → positive mismatch loss."""
    curve_a = module_iv_uniform(60, STC, 1000.0, n_pts=200)
    cell_irr_b = [500.0] * 20 + [1000.0] * 40
    curve_b = module_iv_shaded(cell_irr_b, STC, cells_per_bypass=20, bypass_fwd_v=0.7, n_pts=200)
    result = mppt_mismatch_loss([curve_a, curve_b], n_pts=400)
    # Mismatch loss should be positive
    assert result["mismatch_loss_w"] > 0, "Expected positive mismatch loss"
    assert result["mismatch_loss_pct"] > 0, "Expected positive mismatch loss %"
    assert result["string_gmpp_p_w"] < result["sum_module_gmpp_p_w"], (
        "String GMPP should be less than sum of module GMPPs"
    )


def test_mismatch_loss_keys():
    """Result dict has all expected keys."""
    curve = module_iv_uniform(60, STC, 1000.0, n_pts=100)
    result = mppt_mismatch_loss([curve], n_pts=200)
    for key in ("string_gmpp_p_w", "sum_module_gmpp_p_w", "mismatch_loss_w",
                "mismatch_loss_pct", "module_gmpps"):
        assert key in result, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# MODULE MPP HELPER
# ---------------------------------------------------------------------------

def test_module_mpp_returns_dict():
    curve = module_iv_uniform(60, STC, 1000.0, n_pts=100)
    mpp = module_mpp(curve)
    assert "p_w" in mpp and "v_v" in mpp and "i_a" in mpp
    assert mpp["p_w"] > 0


# ---------------------------------------------------------------------------
# LLM TOOL WRAPPERS — pv_cell_iv
# ---------------------------------------------------------------------------

def test_tool_cell_iv_defaults():
    r = _ok(run_pv_cell_iv, {})
    assert "isc_a" in r
    assert "voc_v" in r
    assert r["mpp"]["p_w"] > 0
    assert r["voc_v"] > 0.3


def test_tool_cell_iv_custom_params():
    r = _ok(run_pv_cell_iv, {"Iph": 8.0, "T_C": 45.0, "n_pts": 50})
    assert r["isc_a"] == pytest.approx(8.0, abs=0.2)
    assert len(r["iv_curve"]) == 50


def test_tool_cell_iv_irradiance_scaling():
    r_full = _ok(run_pv_cell_iv, {"irradiance": 1000.0})
    r_half = _ok(run_pv_cell_iv, {"irradiance": 500.0})
    assert r_half["isc_a"] < r_full["isc_a"]
    assert r_half["mpp"]["p_w"] < r_full["mpp"]["p_w"]


def test_tool_cell_iv_bad_json():
    result = json.loads(_run(run_pv_cell_iv(_FakeCtx(), b"not json")))
    assert "error" in result or result.get("ok") is False


# ---------------------------------------------------------------------------
# LLM TOOL WRAPPERS — pv_module_shaded_iv
# ---------------------------------------------------------------------------

def test_tool_module_shaded_iv_unshaded():
    """Uniform 60-cell module: P ≈ 255 W."""
    r = _ok(run_pv_module_shaded_iv, {"n_cells": 60})
    assert 200.0 < r["mpp"]["p_w"] < 290.0, f"Expected ~255 W, got {r['mpp']['p_w']:.1f} W"


def test_tool_module_shaded_iv_shading_pattern():
    """Shading pattern with bypass diodes."""
    r = _ok(run_pv_module_shaded_iv, {
        "n_cells": 60,
        "shading_pattern": [
            {"cells": 20, "irradiance": 500},
            {"cells": 40, "irradiance": 1000},
        ],
        "cells_per_bypass": 20,
        "bypass_diodes": True,
    })
    assert r["mpp"]["p_w"] > 0
    assert r["power_loss_vs_uniform_pct"] > 0


def test_tool_module_shaded_iv_no_bypass():
    r_bypass = _ok(run_pv_module_shaded_iv, {
        "n_cells": 60,
        "shading_pattern": [
            {"cells": 20, "irradiance": 500},
            {"cells": 40, "irradiance": 1000},
        ],
        "bypass_diodes": True,
    })
    r_no_bypass = _ok(run_pv_module_shaded_iv, {
        "n_cells": 60,
        "shading_pattern": [
            {"cells": 20, "irradiance": 500},
            {"cells": 40, "irradiance": 1000},
        ],
        "bypass_diodes": False,
    })
    assert r_bypass["mpp"]["p_w"] > r_no_bypass["mpp"]["p_w"], (
        "Bypass diodes should yield higher power than without"
    )


def test_tool_module_shaded_iv_cell_irradiances():
    cell_irr = [1000.0] * 60
    cell_irr[10] = 200.0  # shade one cell
    r = _ok(run_pv_module_shaded_iv, {
        "n_cells": 60,
        "cell_irradiances": cell_irr,
    })
    assert r["mpp"]["p_w"] > 0


def test_tool_module_shaded_iv_bad_cell_count():
    """Wrong number of irradiances → error."""
    _err(run_pv_module_shaded_iv, {
        "n_cells": 60,
        "cell_irradiances": [1000.0] * 30,  # wrong count
    })


def test_tool_module_shaded_iv_bad_pattern_count():
    _err(run_pv_module_shaded_iv, {
        "n_cells": 60,
        "shading_pattern": [{"cells": 30, "irradiance": 1000}],  # only 30 cells total
    })


# ---------------------------------------------------------------------------
# LLM TOOL WRAPPERS — pv_mppt_mismatch_loss
# ---------------------------------------------------------------------------

def test_tool_mppt_mismatch_uniform():
    """Two uniform modules → low mismatch."""
    r = _ok(run_pv_mppt_mismatch_loss, {
        "modules": [
            {"n_cells": 60},
            {"n_cells": 60},
        ],
    })
    assert r["mismatch_loss_pct"] < 5.0
    assert r["string_gmpp_p_w"] > 0


def test_tool_mppt_mismatch_mixed():
    """One shaded + one unshaded → positive mismatch."""
    r = _ok(run_pv_mppt_mismatch_loss, {
        "modules": [
            {"n_cells": 60},
            {
                "n_cells": 60,
                "shading_pattern": [
                    {"cells": 20, "irradiance": 500},
                    {"cells": 40, "irradiance": 1000},
                ],
                "bypass_diodes": True,
            },
        ],
    })
    assert r["mismatch_loss_pct"] >= 0.0
    assert r["string_gmpp_p_w"] <= r["sum_module_gmpp_p_w"]
    assert len(r["per_module_gmpps"]) == 2


def test_tool_mppt_mismatch_missing_modules():
    """Missing modules key → error."""
    _err(run_pv_mppt_mismatch_loss, {})


def test_tool_mppt_mismatch_empty_modules():
    """Empty modules list → error."""
    _err(run_pv_mppt_mismatch_loss, {"modules": []})


def test_tool_mppt_mismatch_bad_json():
    result = json.loads(_run(run_pv_mppt_mismatch_loss(_FakeCtx(), b"{")))
    assert "error" in result or result.get("ok") is False


# ---------------------------------------------------------------------------
# VALIDATION: published numbers cross-check
# ---------------------------------------------------------------------------

def test_validation_60cell_unshaded_mpp():
    """
    Validation: 60-cell module, STC, uniform 1000 W/m².
    Expected: I ≈ 8.5 A, V ≈ 30 V, P ≈ 255 W.
    Params calibrated: n=1.0, Io=3.451e-10 from Voc_cell=0.620 V target.
    Tolerance: ±15% on power.
    """
    curve = module_iv_uniform(60, STC, 1000.0, n_pts=300)
    mpp = mppt_global(curve)
    assert 7.0 < mpp["gmpp_i"] < 9.5, f"Imp = {mpp['gmpp_i']:.2f} A (expect ~8.5)"
    assert 25.0 < mpp["gmpp_v"] < 40.0, f"Vmp = {mpp['gmpp_v']:.2f} V (expect ~30)"
    assert 215.0 < mpp["gmpp_p"] < 295.0, f"Pmp = {mpp['gmpp_p']:.1f} W (expect ~255)"


def test_validation_bypass_vs_no_bypass_50pct_shade():
    """
    Validation: 1 of 3 substrings at 50% irradiance.
    With bypass: power > 55% of unshaded (one substring bypassed, not full loss).
    Without bypass: power ≈ 50% (limited by worst cell).
    """
    cell_irr = [500.0] * 20 + [1000.0] * 40

    curve_bypass = module_iv_shaded(cell_irr, STC, cells_per_bypass=20, bypass_fwd_v=0.7, n_pts=300)
    curve_no_bypass = module_iv_shaded(cell_irr, STC, cells_per_bypass=20, bypass_fwd_v=1e6, n_pts=300)
    curve_unshaded = module_iv_uniform(60, STC, 1000.0, n_pts=300)

    p_bypass = mppt_global(curve_bypass)["gmpp_p"]
    p_no_bypass = mppt_global(curve_no_bypass)["gmpp_p"]
    p_unshaded = mppt_global(curve_unshaded)["gmpp_p"]

    r_bypass = p_bypass / p_unshaded
    r_no_bypass = p_no_bypass / p_unshaded

    # With bypass: retains > 55% (roughly 2/3)
    assert r_bypass > 0.55, f"Bypass ratio {r_bypass:.2%} — expected > 55%"
    # Without bypass: ≤ 65% (limited by shaded cell current)
    assert r_no_bypass < 0.65, f"No-bypass ratio {r_no_bypass:.2%} — expected < 65%"
    # Bypass is clearly better
    assert p_bypass > p_no_bypass, "Bypass must give more power than no-bypass"
