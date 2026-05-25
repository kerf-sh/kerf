"""
Random-vibration response to broadband input acceleration PSD via modal method.

Theory
------
For a structure with modal frequencies f_i, damping ζ_i, and modal
participation factors Γ_i, the mean-square response in mode i to a flat
(constant-level) input PSD  S_0  [g²/Hz or (m/s²)²/Hz] is:

    σ²_i = Γ_i² · S_0 · (π / 2) · f_i / (2 ζ_i) · (1 / ω_i²)²

For a general (frequency-dependent) PSD the integral over the positive
half-spectrum is evaluated numerically using the trapezoidal rule over the
provided PSD table.

Miles' equation (single-DOF flat PSD)
--------------------------------------
For a constant PSD level S_0 [(m/s²)²/Hz or g²/Hz] applied to the base:

    GRMS  = √( (π/2) · f_n · Q · S_0 )

where Q = 1 / (2 ζ) is the quality factor, f_n the natural frequency.

Reference: Miles, J.W. (1954), "On the structural fatigue under random
loading," J. Aeronautical Sciences 21, 753-762.

For a multi-mode structure under a shaped PSD:

    σ²_total = Σ_i [ Γ_i · φ_i(DOF) ]² · ∫ H_i(f)² · S(f) df

where H_i(f) = 1 / √((1-(f/f_i)²)² + (2ζ_i·f/f_i)²) / (2πf_i)².

Cross-modal correlation is neglected (white-noise or well-separated modes
assumption).

References
----------
* Random Vibration in Mechanical Systems — Crandall & Mark, 1963.
* Steinberg, "Vibration Analysis for Electronic Equipment", 3rd ed., §4.
* MIL-STD-810, Annex A (PSD test levels).
* Lalanne, "Mechanical Vibration and Shock Analysis", Vol. 3, §4.3.

Public entry-points
-------------------
    miles_equation(fn, Q, S0)
        -> dict { ok, GRMS, sigma_1, sigma_3 }

    random_vibration_psd(modes, modal_damping, modal_participation,
                         psd_table, *, dof_index=0, n_sigma=3)
        -> dict { ok, rms_response, sigma_1, sigma_3, modal_rms,
                  miles_approx (if single-mode) }

All routines are pure Python (no numpy / scipy) and never raise; errors
return {"ok": False, "reason": "..."}.
"""

from __future__ import annotations

import math
from typing import Any


# ---------------------------------------------------------------------------
# Miles' equation
# ---------------------------------------------------------------------------

def miles_equation(
    fn: float,
    Q: float,
    S0: float,
) -> dict[str, Any]:
    """
    Miles' equation for SDOF base-excitation RMS response.

        GRMS = √( (π/2) · f_n · Q · S_0 )

    Parameters
    ----------
    fn : natural frequency [Hz]
    Q  : quality factor  = 1 / (2 ζ)
    S0 : flat (constant) PSD level [(m/s²)²/Hz  or  g²/Hz]

    Returns
    -------
    { ok, GRMS [same unit as √S0·Hz], sigma_1, sigma_3, zeta }
    """
    if fn <= 0:
        return {"ok": False, "reason": "fn must be positive"}
    if Q <= 0:
        return {"ok": False, "reason": "Q must be positive"}
    if S0 < 0:
        return {"ok": False, "reason": "S0 must be non-negative"}

    zeta = 1.0 / (2.0 * Q)
    grms = math.sqrt(math.pi / 2.0 * fn * Q * S0)
    return {
        "ok": True,
        "GRMS": grms,
        "sigma_1": grms,       # 1-sigma (68.3% probability)
        "sigma_3": 3.0 * grms, # 3-sigma (99.7% probability)
        "zeta": zeta,
    }


# ---------------------------------------------------------------------------
# PSD table interpolation helpers
# ---------------------------------------------------------------------------

def _interp_psd(
    psd_table: list[tuple[float, float]],
    f: float,
) -> float:
    """
    Linear interpolation (in linear–linear space) of a (freq, psd) table.
    Returns 0 outside the table range.
    """
    if not psd_table or f < psd_table[0][0] or f > psd_table[-1][0]:
        return 0.0
    for i in range(len(psd_table) - 1):
        f0, s0 = psd_table[i]
        f1, s1 = psd_table[i + 1]
        if f0 <= f <= f1:
            if abs(f1 - f0) < 1e-30:
                return s0
            t = (f - f0) / (f1 - f0)
            return s0 + t * (s1 - s0)
    return psd_table[-1][1]


def _integrate_psd_trapz(
    psd_table: list[tuple[float, float]],
) -> float:
    """
    Trapezoidal integration of PSD table → mean-square (variance) value.
    Assumes psd_table is sorted by frequency.
    """
    if len(psd_table) < 2:
        return 0.0
    total = 0.0
    for i in range(len(psd_table) - 1):
        f0, s0 = psd_table[i]
        f1, s1 = psd_table[i + 1]
        total += 0.5 * (s0 + s1) * (f1 - f0)
    return total


def _modal_mean_square(
    fn: float,
    zeta: float,
    gamma: float,
    phi_dof: float,
    psd_table: list[tuple[float, float]],
    *,
    n_pts: int = 500,
) -> float:
    """
    Numerically integrate modal contribution to mean-square response:

        σ²_i = (Γ_i · φ_i)² · ∫_0^∞  H_i(f)² · S(f)  df

    where  H_i(f) = 1 / ( (2πf_i)² · √((1-(f/f_i)²)² + (2ζf/f_i)²) )
    is the single-DOF displacement FRF (acceleration input → displacement out).

    Integration range: f_psd_min to f_psd_max (outside the table S(f)=0).
    Dense grid near resonance (±5× half-power bandwidth) for accuracy.
    """
    if not psd_table or fn <= 0 or zeta <= 0:
        return 0.0

    f_low = psd_table[0][0]
    f_high = psd_table[-1][0]

    if f_high <= f_low:
        return 0.0

    # Scale factor for displacement FRF from acceleration PSD:
    #   |H(f)|² = 1 / ( ωn^4 · ((1-r²)² + (2ζr)²) )
    #   where ωn = 2πfn
    wn = 2.0 * math.pi * fn
    wn4 = wn ** 4

    # Build integration grid
    df_coarse = (f_high - f_low) / n_pts

    # Sample points: uniform + dense cluster around resonance
    pts = set()
    # Coarse uniform grid
    f = f_low
    while f <= f_high + 1e-12:
        pts.add(f)
        f += df_coarse

    # Dense grid near resonance: ±10 half-power bandwidths
    bw = 2.0 * zeta * fn
    f_near_low = max(f_low, fn - 10.0 * bw)
    f_near_high = min(f_high, fn + 10.0 * bw)
    n_dense = max(200, int((f_near_high - f_near_low) / (bw / 20.0)))
    if f_near_high > f_near_low:
        df_dense = (f_near_high - f_near_low) / n_dense
        f = f_near_low
        while f <= f_near_high + 1e-12:
            pts.add(f)
            f += df_dense

    pts_sorted = sorted(pts)

    # Trapezoidal integration
    def integrand(fq: float) -> float:
        s = _interp_psd(psd_table, fq)
        if s <= 0.0:
            return 0.0
        r = fq / fn
        den = (1.0 - r * r) ** 2 + (2.0 * zeta * r) ** 2
        if den < 1e-300:
            return 0.0
        h2 = 1.0 / (wn4 * den)
        return h2 * s

    integral = 0.0
    prev_f = pts_sorted[0]
    prev_g = integrand(prev_f)
    for cur_f in pts_sorted[1:]:
        cur_g = integrand(cur_f)
        integral += 0.5 * (prev_g + cur_g) * (cur_f - prev_f)
        prev_f = cur_f
        prev_g = cur_g

    # Mode contribution: (Γ_i · φ_i)²  × integral
    coeff = (gamma * phi_dof) ** 2
    return coeff * integral


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def random_vibration_psd(
    modes: dict[str, Any],
    modal_damping: float | list[float],
    modal_participation: list[float],
    psd_table: list[list[float]],
    *,
    dof_index: int = 0,
    n_sigma: int = 3,
) -> dict[str, Any]:
    """
    Random-vibration response to a shaped input acceleration PSD.

    Parameters
    ----------
    modes : dict with keys:
        "omega"       : list[float]  — natural circular frequencies [rad/s]
        "mode_shapes" : list[list]   — mode shapes (each length >= dof_index+1)

    modal_damping : float or list[float]
        Viscous damping ratio(s) ζ (scalar → all same, list → per-mode).

    modal_participation : list[float]
        Modal participation factors Γ_i (base-excitation direction).
        Length must equal number of modes.

    psd_table : list[[f_Hz, S_value]]
        Input acceleration PSD as list of [frequency_Hz, PSD_value] pairs.
        Sorted by frequency ascending.  Units: (m/s²)²/Hz or g²/Hz.

    dof_index : int
        Index of the response DOF to evaluate (default 0).

    n_sigma : int
        Number of sigma for peak response estimate (default 3).

    Returns
    -------
    {
      ok              : bool,
      rms_response    : float   — σ_total (RMS displacement response),
      sigma_1         : float   — 1-sigma (= rms_response),
      sigma_3         : float   — n_sigma × rms_response,
      modal_rms       : list    — per-mode RMS contribution,
      input_grms      : float   — RMS of input (√∫ PSD df),
      miles_approx    : dict    — Miles' equation for first mode (validation),
    }
    """
    # --- Validate inputs ---
    if not isinstance(modes, dict):
        return {"ok": False, "reason": "modes must be a dict with 'omega' and 'mode_shapes'"}

    omega_n = modes.get("omega", [])
    mode_shapes = modes.get("mode_shapes", [])

    if not omega_n:
        return {"ok": False, "reason": "modes['omega'] must be non-empty"}
    if not mode_shapes:
        return {"ok": False, "reason": "modes['mode_shapes'] must be non-empty"}
    if len(omega_n) != len(mode_shapes):
        return {"ok": False, "reason": "omega and mode_shapes must have equal length"}

    n_modes = len(omega_n)

    if not modal_participation or len(modal_participation) != n_modes:
        return {"ok": False, "reason": "modal_participation must match number of modes"}

    # Normalise damping
    if isinstance(modal_damping, (int, float)):
        zeta = [float(modal_damping)] * n_modes
    else:
        zeta = [float(z) for z in modal_damping]
        if len(zeta) != n_modes:
            return {"ok": False, "reason": "modal_damping list length must match n_modes"}

    for z in zeta:
        if z <= 0.0:
            return {"ok": False, "reason": "damping ratios must be positive for random vibration"}

    # Convert psd_table to sorted list of tuples
    try:
        psd_pairs = [(float(row[0]), float(row[1])) for row in psd_table]
    except (TypeError, IndexError, ValueError) as e:
        return {"ok": False, "reason": f"psd_table format error: {e}"}

    if len(psd_pairs) < 2:
        return {"ok": False, "reason": "psd_table must have at least 2 points"}

    psd_pairs.sort(key=lambda x: x[0])

    for f, s in psd_pairs:
        if f < 0:
            return {"ok": False, "reason": "PSD frequencies must be non-negative"}
        if s < 0:
            return {"ok": False, "reason": "PSD values must be non-negative"}

    # Validate dof_index
    for ms in mode_shapes:
        if len(ms) <= dof_index:
            return {"ok": False, "reason": f"mode_shape shorter than dof_index+1={dof_index+1}"}

    # --- Compute input GRMS ---
    input_ms = _integrate_psd_trapz(psd_pairs)
    input_grms = math.sqrt(max(input_ms, 0.0))

    # --- Modal mean-square contributions (SRSS — uncorrelated modes) ---
    modal_ms_list = []
    fn_list = [wn / (2.0 * math.pi) for wn in omega_n]

    for i in range(n_modes):
        fn_i = fn_list[i]
        zeta_i = zeta[i]
        gamma_i = float(modal_participation[i])
        phi_ij = float(mode_shapes[i][dof_index])

        ms_i = _modal_mean_square(
            fn_i, zeta_i, gamma_i, phi_ij, psd_pairs
        )
        modal_ms_list.append(ms_i)

    # SRSS total
    total_ms = sum(modal_ms_list)
    rms_total = math.sqrt(max(total_ms, 0.0))
    modal_rms = [math.sqrt(max(m, 0.0)) for m in modal_ms_list]

    # Miles' approximation for first mode (flat PSD at first natural frequency)
    fn0 = fn_list[0]
    zeta0 = zeta[0]
    Q0 = 1.0 / (2.0 * zeta0)
    S0_at_fn = _interp_psd(psd_pairs, fn0)
    miles_result = miles_equation(fn0, Q0, S0_at_fn)

    return {
        "ok": True,
        "rms_response": rms_total,
        "sigma_1": rms_total,
        "sigma_3": n_sigma * rms_total,
        "modal_rms": modal_rms,
        "input_grms": input_grms,
        "miles_approx": miles_result,
    }


def miles_sdof_response(
    fn: float,
    zeta: float,
    S0: float,
    *,
    n_sigma: int = 3,
) -> dict[str, Any]:
    """
    Convenience wrapper: SDOF Miles response with both Miles closed-form and
    numerical modal-method result for cross-validation.

    The modal method treats the SDOF as a 1-DOF structure with:
        ω = 2π·fn,  Γ = 1,  φ = 1/(2π·fn)²  (displacement per (m/s²) base)

    Parameters
    ----------
    fn    : natural frequency [Hz]
    zeta  : damping ratio
    S0    : flat PSD level [(m/s²)²/Hz]
    n_sigma : sigma multiplier (default 3)

    Returns
    -------
    { ok, miles_GRMS, modal_rms, relative_error_pct }
    """
    if fn <= 0:
        return {"ok": False, "reason": "fn must be positive"}
    if zeta <= 0:
        return {"ok": False, "reason": "zeta must be positive"}
    if S0 < 0:
        return {"ok": False, "reason": "S0 must be non-negative"}

    # Miles closed-form
    Q = 1.0 / (2.0 * zeta)
    miles_grms = math.sqrt(math.pi / 2.0 * fn * Q * S0)

    # For base-excited SDOF: displacement response PSD is
    #   Sd(f) = S0 / ((2πfn)^4 · ((1-r²)² + (2ζr)²))
    # The modal participation Γ=1 and φ=1 for base accel → accel response.
    # Here we compute displacement RMS directly via Miles' σ_x:
    #   σ_x = σ_a / ωn²   (flat PSD approximation)
    wn = 2.0 * math.pi * fn
    # Flat PSD over full frequency range centred on fn
    f_low = max(1e-3, fn * 0.01)
    f_high = fn * 100.0
    n_pts = 2000
    psd_pairs = [[f_low + k * (f_high - f_low) / (n_pts - 1), S0] for k in range(n_pts)]

    modes = {
        "omega": [wn],
        "mode_shapes": [[1.0]],  # unit displacement shape
    }
    result = random_vibration_psd(
        modes,
        [zeta],
        [1.0],       # unit participation factor (for displacement)
        psd_pairs,
        dof_index=0,
    )

    if not result["ok"]:
        return {"ok": False, "reason": result.get("reason", "modal method failed")}

    modal_rms = result["rms_response"]

    # Miles gives acceleration GRMS; modal_rms here is displacement RMS
    # For SDOF: σ_x ≈ σ_a / ωn² (white noise approximation)
    miles_disp = miles_grms / (wn ** 2)
    rel_err = abs(modal_rms - miles_disp) / max(miles_disp, 1e-300) * 100.0

    return {
        "ok": True,
        "miles_GRMS": miles_grms,
        "miles_displacement_rms": miles_disp,
        "modal_displacement_rms": modal_rms,
        "relative_error_pct": rel_err,
        "n_sigma": n_sigma,
        "sigma_3": n_sigma * modal_rms,
    }
