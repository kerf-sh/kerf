"""
kerf_cad_core.solarpv.shading — partial-shading & bypass-diode modelling for PV modules.

Complements sizing.py (system-level design) with cell/substring-level physics for
non-uniform irradiance conditions: tree shadows, row shading, soiling, etc.

Implements
----------
SINGLE-DIODE MODEL (per cell)
  cell_iv_point(v, params)        — solve I at a given V using Newton iteration
  cell_iv_curve(params, *, n_pts) — I-V sweep for a single cell

MODULE UNDER PARTIAL SHADING
  module_iv_shaded(cell_irradiance_list, params, *, cells_per_bypass,
                   bypass_fwd_v, n_pts)
      Full I-V curve for a module whose cells see different irradiance levels.
      Handles bypass diodes: if a substring's max forward current < string current,
      the substring is bypassed at ~0.7 V drop.

MPPT MULTI-PEAK SEARCH
  mppt_global(iv_curve)          — find ALL local I-V power maxima; return GMPP
  mppt_mismatch_loss(module_iv_list, *, n_pts)
      Per-MPPT-input mismatch loss when multiple modules (possibly with
      different shading patterns) share one MPPT input in series.

PUBLIC HELPERS
  pv_cell_params_stc()           — default single-diode params for a typical
                                    60-cell module cell at STC

All functions are pure-Python (math + stdlib).  No OCC dependency.
Warnings issued via the standard ``warnings`` module where appropriate.
Functions never raise on domain errors.

Physical Model
--------------
Single-diode implicit equation (Shockley):
    I = Iph - Io·(exp((V + I·Rs)/(n·Vt)) - 1) - (V + I·Rs)/Rsh

where:
    Iph  — photo-generated (light) current (A)  ∝ irradiance
    Io   — dark saturation current (A)
    Rs   — series resistance (Ω)
    Rsh  — shunt resistance (Ω)
    n    — diode ideality factor
    Vt   — thermal voltage = k·T/q  (≈ 0.02585 V at 25 °C)

Bypass diodes (typically 1 per 20-cell substring in a 60-cell module) protect
shaded cells from reverse bias.  When a shaded substring cannot pass the string
current in the forward direction, the bypass diode conducts, clamping the
substring voltage to −Vbypass (≈ −0.7 V) rather than deeply negative.

References
----------
Duffie, J.A. & Beckman, W.A., "Solar Engineering of Thermal Processes", 4th ed.
De Soto, W., Klein, S.A., Beckman, W.A. (2006) — five-parameter single-diode model.
Villalva, M.G., Gazoli, J.R., Filho, E.R. (2009) — comprehensive single-diode model.
IEC 61215 — terrestrial PV module design qualification and type approval.

Author: imranparuk
"""
from __future__ import annotations

import math
import warnings
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_K = 1.380649e-23   # Boltzmann constant (J/K)
_Q = 1.602176634e-19  # electron charge (C)
_T_STC_K = 298.15  # STC temperature 25 °C in Kelvin


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class CellParams(NamedTuple):
    """Single-diode model parameters for one solar cell."""
    Iph: float   # Photo-current at STC (A) — proportional to irradiance
    Io: float    # Dark saturation current (A), typical ~1e-10 A
    Rs: float    # Series resistance (Ω), typical 0.005–0.02 Ω per cell
    Rsh: float   # Shunt resistance (Ω), typical 100–1000 Ω per cell
    n: float     # Diode ideality factor, typical 1.0–1.5
    T_K: float   # Cell temperature (K)

    @property
    def Vt(self) -> float:
        """Thermal voltage k·T/q (V)."""
        return _K * self.T_K / _Q


def pv_cell_params_stc(
    *,
    Iph: float = 9.0,
    Io: float = 3.451e-10,
    Rs: float = 0.005,
    Rsh: float = 400.0,
    n: float = 1.0,
    T_C: float = 25.0,
) -> CellParams:
    """
    Return CellParams at STC defaults for a typical 60-cell, 255 Wp module cell.

    Default single-cell parameters calibrated so that a 60-series-cell module
    produces: Voc ≈ 37 V, Vmp ≈ 30 V, Imp ≈ 8.5 A, Pmax ≈ 255 W.

    Calibration:  n=1.0, Io derived from Voc_cell=0.620 V at 1000 W/m², 25 °C.

    Parameters
    ----------
    Iph   : photo-current (A) at 1000 W/m² — scales with irradiance
    Io    : dark saturation current (A)
    Rs    : series resistance per cell (Ω)
    Rsh   : shunt resistance per cell (Ω)
    n     : diode ideality factor
    T_C   : cell temperature (°C)
    """
    return CellParams(
        Iph=Iph, Io=Io, Rs=Rs, Rsh=Rsh, n=n, T_K=T_C + 273.15
    )


# ---------------------------------------------------------------------------
# Single-cell I-V solver
# ---------------------------------------------------------------------------

def cell_iv_point(
    V: float,
    params: CellParams,
    *,
    max_iter: int = 50,
    tol: float = 1e-9,
) -> float:
    """
    Solve the single-diode implicit equation for current I at voltage V.

    Uses Newton–Raphson iteration on:
        f(I) = I - Iph + Io·(exp((V + I·Rs)/(n·Vt)) - 1) + (V + I·Rs)/Rsh

    Parameters
    ----------
    V       : terminal voltage (V), may be negative (bypass/reverse bias)
    params  : CellParams
    max_iter: Newton iteration limit
    tol     : convergence tolerance (A)

    Returns
    -------
    I : current (A) — positive = conventional current out of + terminal.
        Returns 0.0 on non-convergence (degenerate condition).
    """
    Iph, Io, Rs, Rsh, n = params.Iph, params.Io, params.Rs, params.Rsh, params.n
    Vt = params.Vt

    # Initial guess: short-circuit current less diode drop
    I = Iph

    nVt = n * Vt
    for _ in range(max_iter):
        arg = (V + I * Rs) / nVt
        # Clamp to avoid overflow in exp
        arg_clamped = min(arg, 700.0)
        exp_val = math.exp(arg_clamped)

        f = I - Iph + Io * (exp_val - 1.0) + (V + I * Rs) / Rsh
        df = 1.0 + Io * exp_val * Rs / nVt + Rs / Rsh

        delta = f / df
        I -= delta
        if abs(delta) < tol:
            return max(I, -Iph)  # physically bounded below

    return max(I, -Iph)


def cell_iv_curve(
    params: CellParams,
    *,
    n_pts: int = 200,
    v_min: float | None = None,
    v_max: float | None = None,
) -> list[tuple[float, float]]:
    """
    Compute the full I-V curve for a single cell.

    Sweeps voltage from 0 to Voc (or [v_min, v_max] if given).

    Returns
    -------
    List of (V, I) tuples, V increasing.
    """
    Vt = params.Vt
    # Estimate Voc: V where I ≈ 0
    # Voc ≈ n·Vt · ln(Iph/Io + 1)
    Voc_approx = params.n * Vt * math.log(max(params.Iph / params.Io + 1.0, 1.0))

    lo = v_min if v_min is not None else 0.0
    hi = v_max if v_max is not None else Voc_approx * 1.05

    curve: list[tuple[float, float]] = []
    for k in range(n_pts):
        V = lo + (hi - lo) * k / (n_pts - 1)
        I = cell_iv_point(V, params)
        curve.append((V, I))
    return curve


# ---------------------------------------------------------------------------
# Module IV under partial shading with bypass diodes
# ---------------------------------------------------------------------------

def _substring_voc(params: CellParams, iph_sub: float) -> float:
    """Open-circuit voltage of a substring with modified Iph."""
    p = CellParams(
        Iph=iph_sub, Io=params.Io, Rs=params.Rs,
        Rsh=params.Rsh, n=params.n, T_K=params.T_K,
    )
    Vt = p.Vt
    if iph_sub <= 0:
        return 0.0
    return p.n * Vt * math.log(max(iph_sub / p.Io + 1.0, 1.0))


def _substring_v_at_i(
    I_string: float,
    params: CellParams,
    iph_cells: list[float],
    bypass_fwd_v: float,
) -> float:
    """
    Voltage of one substring (N cells in series) at a given string current.

    If the worst-shaded cell's Isc < I_string, the substring is bypassed
    (voltage contribution = −bypass_fwd_v, typically −0.7 V).

    Parameters
    ----------
    I_string     : string current (A) — must be >= 0
    params       : base CellParams (cell-level parameters)
    iph_cells    : list of per-cell Iph values in this substring
    bypass_fwd_v : bypass diode forward voltage drop (V), positive value
    """
    # The limiting Isc of this substring is the minimum cell Isc
    # (without bypass, all cells carry the same current)
    min_iph = min(iph_cells)

    # Estimate max forward current of the worst-shaded cell
    # In the single-diode model, Isc ≈ Iph for small Rs/Rsh
    isc_min = cell_iv_point(0.0, CellParams(
        Iph=min_iph, Io=params.Io, Rs=params.Rs,
        Rsh=params.Rsh, n=params.n, T_K=params.T_K,
    ))

    if isc_min < I_string:
        # Bypass diode conducts — substring contributes −bypass_fwd_v
        return -bypass_fwd_v

    # Bypass not active — sum cell voltages at I_string
    V_sub = 0.0
    for iph in iph_cells:
        p = CellParams(
            Iph=iph, Io=params.Io, Rs=params.Rs,
            Rsh=params.Rsh, n=params.n, T_K=params.T_K,
        )
        # Solve V at fixed I: rearrange f(V) = I_string - cell_iv_point(V, p)
        # Binary search on V ∈ [−0.5, Voc+0.1]
        Voc = _substring_voc(p, iph)
        v_lo, v_hi = -0.5, Voc + 0.1
        for _ in range(60):
            v_mid = (v_lo + v_hi) / 2.0
            i_mid = cell_iv_point(v_mid, p)
            if i_mid > I_string:
                v_lo = v_mid
            else:
                v_hi = v_mid
        V_sub += (v_lo + v_hi) / 2.0
    return V_sub


def module_iv_shaded(
    cell_irradiance_list: list[float],
    params: CellParams,
    *,
    cells_per_bypass: int = 20,
    bypass_fwd_v: float = 0.7,
    n_pts: int = 200,
) -> list[tuple[float, float]]:
    """
    Compute the I-V curve of a module under non-uniform (partial) shading.

    The module consists of len(cell_irradiance_list) cells in series,
    grouped into substrings of `cells_per_bypass` cells each.  Each
    substring has one bypass diode in anti-parallel.

    Iph of each cell is linearly proportional to its irradiance:
        Iph_cell = params.Iph × (irradiance / 1000.0)

    Parameters
    ----------
    cell_irradiance_list : irradiance (W/m²) seen by each cell, len = N_cells
    params               : CellParams at reference (1000 W/m²) irradiance
    cells_per_bypass     : cells per bypass-diode substring (default 20)
    bypass_fwd_v         : bypass diode forward voltage (V), default 0.7
    n_pts                : number of I sweep points

    Returns
    -------
    List of (V_module, I_string) tuples.  I sweeps from Isc down to ~0.
    The curve may have multiple local power maxima under shading.
    """
    n_cells = len(cell_irradiance_list)
    if n_cells == 0:
        return []

    # Build per-cell Iph
    iph_cells = [params.Iph * (g / 1000.0) for g in cell_irradiance_list]

    # Group into substrings
    substrings: list[list[float]] = []
    for start in range(0, n_cells, cells_per_bypass):
        substrings.append(iph_cells[start : start + cells_per_bypass])

    # Determine sweep range: from 0 to max possible Isc
    I_max = max(
        cell_iv_point(0.0, CellParams(
            Iph=max(sub), Io=params.Io, Rs=params.Rs,
            Rsh=params.Rsh, n=params.n, T_K=params.T_K,
        ))
        for sub in substrings
    )

    curve: list[tuple[float, float]] = []
    for k in range(n_pts):
        # Sweep I from near-Isc down to 0
        I_str = I_max * (1.0 - k / (n_pts - 1))
        I_str = max(I_str, 0.0)

        V_total = sum(
            _substring_v_at_i(I_str, params, sub, bypass_fwd_v)
            for sub in substrings
        )
        curve.append((V_total, I_str))

    return curve


# ---------------------------------------------------------------------------
# Uniform-irradiance module IV (convenience wrapper)
# ---------------------------------------------------------------------------

def module_iv_uniform(
    n_cells: int,
    params: CellParams,
    irradiance: float = 1000.0,
    *,
    n_pts: int = 200,
) -> list[tuple[float, float]]:
    """
    I-V curve for a module with uniform irradiance (no shading).

    Equivalent to module_iv_shaded with all cells at the same irradiance.

    Parameters
    ----------
    n_cells    : number of cells in series
    params     : CellParams at 1000 W/m²
    irradiance : irradiance (W/m²), default 1000
    n_pts      : sweep points
    """
    return module_iv_shaded(
        [irradiance] * n_cells,
        params,
        n_pts=n_pts,
    )


# ---------------------------------------------------------------------------
# MPPT — global maximum power point search
# ---------------------------------------------------------------------------

def mppt_global(iv_curve: list[tuple[float, float]]) -> dict:
    """
    Locate the Global Maximum Power Point (GMPP) on an I-V curve.

    Also returns ALL local maxima (important under shading — the curve may
    have multiple bumps and a conventional hill-climbing MPPT can get stuck
    at a local maximum).

    Parameters
    ----------
    iv_curve : list of (V, I) tuples (any order; will be sorted by V)

    Returns
    -------
    dict with keys:
        gmpp_v   — voltage at global MPP (V)
        gmpp_i   — current at global MPP (A)
        gmpp_p   — power at global MPP (W)
        local_maxima — list of {"v", "i", "p"} for every local maximum
    """
    if not iv_curve:
        return {"gmpp_v": 0.0, "gmpp_i": 0.0, "gmpp_p": 0.0, "local_maxima": []}

    # Sort by voltage ascending
    pts = sorted(iv_curve, key=lambda t: t[0])
    powers = [v * i for v, i in pts]

    local_maxima: list[dict] = []
    n = len(pts)

    # Interior local maxima
    for k in range(1, n - 1):
        if powers[k] >= powers[k - 1] and powers[k] >= powers[k + 1]:
            # Check it's a genuine bump (not a flat plateau edge)
            if powers[k] > 0:
                local_maxima.append({
                    "v": pts[k][0],
                    "i": pts[k][1],
                    "p": powers[k],
                })

    # Edge cases: endpoints
    if n >= 2:
        if powers[0] >= powers[1] and powers[0] > 0:
            local_maxima.append({"v": pts[0][0], "i": pts[0][1], "p": powers[0]})
        if powers[-1] >= powers[-2] and powers[-1] > 0:
            local_maxima.append({"v": pts[-1][0], "i": pts[-1][1], "p": powers[-1]})

    if not local_maxima:
        # Fallback: global max of the power array
        k_max = max(range(n), key=lambda k: powers[k])
        local_maxima = [{"v": pts[k_max][0], "i": pts[k_max][1], "p": powers[k_max]}]

    gmpp = max(local_maxima, key=lambda d: d["p"])
    return {
        "gmpp_v": gmpp["v"],
        "gmpp_i": gmpp["i"],
        "gmpp_p": gmpp["p"],
        "local_maxima": sorted(local_maxima, key=lambda d: d["p"], reverse=True),
    }


# ---------------------------------------------------------------------------
# MPPT mismatch loss
# ---------------------------------------------------------------------------

def mppt_mismatch_loss(
    module_iv_list: list[list[tuple[float, float]]],
    *,
    n_pts: int = 400,
) -> dict:
    """
    Compute MPPT mismatch loss for a string of modules sharing one MPPT input.

    When modules with different shading patterns are connected in series on
    the same MPPT tracker, the tracker can only find one operating point for
    the whole string.  The sum of individual module MPPs is the theoretical
    upper bound; the actual string MPP is always <= that sum.

    Method
    ------
    1. For each module, determine its individual GMPP.
    2. Build the series string I-V curve: for each candidate string current,
       sum module voltages (using binary search on each module's I-V curve).
    3. Find the string GMPP.
    4. Mismatch loss = (sum of individual GMPPs − string GMPP) / sum of
       individual GMPPs, expressed as a fraction.

    Parameters
    ----------
    module_iv_list : list of per-module I-V curves (each: list of (V, I) tuples)
    n_pts          : sweep points for the string I-V curve

    Returns
    -------
    dict with keys:
        string_gmpp_p_w       — string GMPP power (W)
        sum_module_gmpp_p_w   — sum of individual module GMPPs (W)
        mismatch_loss_w       — absolute mismatch loss (W)
        mismatch_loss_pct     — relative mismatch loss (%)
        module_gmpps          — list of per-module GMPP dicts
        string_iv_curve       — the computed string I-V curve (V, I tuples)
    """
    if not module_iv_list:
        return {
            "string_gmpp_p_w": 0.0,
            "sum_module_gmpp_p_w": 0.0,
            "mismatch_loss_w": 0.0,
            "mismatch_loss_pct": 0.0,
            "module_gmpps": [],
            "string_iv_curve": [],
        }

    # Per-module GMPPs
    module_gmpps = [mppt_global(iv) for iv in module_iv_list]
    sum_individual = sum(g["gmpp_p"] for g in module_gmpps)

    # Determine sweep current range: intersection of all modules' Isc ranges
    # Max string current = min of all module Isc values
    def _isc(iv: list[tuple[float, float]]) -> float:
        """Approximate Isc: max I in the curve."""
        if not iv:
            return 0.0
        return max(i for _, i in iv)

    I_max = min(_isc(iv) for iv in module_iv_list)
    if I_max <= 0:
        return {
            "string_gmpp_p_w": 0.0,
            "sum_module_gmpp_p_w": sum_individual,
            "mismatch_loss_w": sum_individual,
            "mismatch_loss_pct": 100.0,
            "module_gmpps": module_gmpps,
            "string_iv_curve": [],
        }

    def _v_at_i(iv: list[tuple[float, float]], I_target: float) -> float:
        """Interpolate voltage at a given current from an IV curve (I decreasing)."""
        # Sort by I descending for binary search
        pts_by_i = sorted(iv, key=lambda t: t[1], reverse=True)
        if I_target >= pts_by_i[0][1]:
            return pts_by_i[0][0]
        if I_target <= pts_by_i[-1][1]:
            return pts_by_i[-1][0]
        # Linear interpolation
        for k in range(len(pts_by_i) - 1):
            i1, v1 = pts_by_i[k][1], pts_by_i[k][0]
            i2, v2 = pts_by_i[k + 1][1], pts_by_i[k + 1][0]
            if i2 <= I_target <= i1:
                if abs(i1 - i2) < 1e-12:
                    return v1
                t = (I_target - i1) / (i2 - i1)
                return v1 + t * (v2 - v1)
        return pts_by_i[-1][0]

    # Build string IV curve
    string_iv: list[tuple[float, float]] = []
    for k in range(n_pts):
        I_str = I_max * (1.0 - k / (n_pts - 1))
        I_str = max(I_str, 0.0)
        V_string = sum(_v_at_i(iv, I_str) for iv in module_iv_list)
        string_iv.append((V_string, I_str))

    string_gmpp = mppt_global(string_iv)
    string_p = string_gmpp["gmpp_p"]

    mismatch_w = max(sum_individual - string_p, 0.0)
    mismatch_pct = (mismatch_w / sum_individual * 100.0) if sum_individual > 0 else 0.0

    return {
        "string_gmpp_p_w": round(string_p, 3),
        "sum_module_gmpp_p_w": round(sum_individual, 3),
        "mismatch_loss_w": round(mismatch_w, 3),
        "mismatch_loss_pct": round(mismatch_pct, 4),
        "module_gmpps": module_gmpps,
        "string_iv_curve": string_iv,
    }


# ---------------------------------------------------------------------------
# Convenience: module MPP summary
# ---------------------------------------------------------------------------

def module_mpp(iv_curve: list[tuple[float, float]]) -> dict:
    """Return power, voltage, and current at the global MPP for a module IV curve."""
    g = mppt_global(iv_curve)
    return {"p_w": g["gmpp_p"], "v_v": g["gmpp_v"], "i_a": g["gmpp_i"]}
