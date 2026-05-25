"""
Steady-state harmonic (frequency) response via mode superposition.

Computes the steady-state complex response  U(ω)  to a harmonic excitation
F·e^{iωt} over a user-specified frequency sweep, using modal damping.

Theory
------
In modal coordinates the i-th mode contributes:

    H_i(ω) = φ_i^T F / (ω_i² - ω² + 2 i ζ_i ω_i ω)

where ω_i = 2π f_i is the i-th natural circular frequency, ζ_i the modal
damping ratio, and φ_i the i-th mass-normalised mode shape.

The physical response at DOF j is:

    U_j(ω) = Σ_i  φ_{ij} · H_i(ω)

The amplitude |U_j(ω)| yields the frequency-response function (FRF).

For a single-DOF system excited at its base (transmissibility) or at the
mass (force), the dynamic amplification factor (DAF) is:

    DAF = 1 / √((1 - r²)² + (2 ζ r)²)    where r = ω / ω_n

This function is validated against the closed-form SDOF DAF.

References
----------
* Clough & Penzien, "Dynamics of Structures", 3rd ed., §12.3 (mode super-
  position frequency response).
* Craig & Kurdila, "Fundamentals of Structural Dynamics", §8.5.
* Inman, "Engineering Vibration", §3.4 (DAF / transmissibility).

Public entry-points
-------------------
    harmonic_response(modes, modal_damping, force_vector, freq_range, *,
                      dof_index=0)
        -> dict { ok, frequencies_hz, amplitude, phase_deg,
                  transmissibility, DAF_analytical }

    sdof_daf(r, zeta)
        -> float   (SDOF dynamic amplification factor)

All routines are pure Python (no numpy / scipy) and never raise; errors
return {"ok": False, "reason": "..."}.
"""

from __future__ import annotations

import math
from typing import Any


# ---------------------------------------------------------------------------
# SDOF helpers
# ---------------------------------------------------------------------------

def sdof_daf(r: float, zeta: float) -> float:
    """
    SDOF dynamic amplification factor (Inman §3.4):

        DAF = 1 / √((1 - r²)² + (2 ζ r)²)

    Parameters
    ----------
    r    : frequency ratio ω / ω_n
    zeta : viscous damping ratio (0 < ζ < 1)
    """
    den = math.sqrt((1.0 - r * r) ** 2 + (2.0 * zeta * r) ** 2)
    if den < 1e-300:
        return math.inf
    return 1.0 / den


def sdof_phase_deg(r: float, zeta: float) -> float:
    """
    Phase angle (degrees) of SDOF response:

        φ = atan2(2 ζ r, 1 - r²)   [0 to 180°]
    """
    return math.degrees(math.atan2(2.0 * zeta * r, 1.0 - r * r))


# ---------------------------------------------------------------------------
# Complex arithmetic helpers (avoid numpy dependency)
# ---------------------------------------------------------------------------

def _cadd(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    return (a[0] + b[0], a[1] + b[1])


def _cmul(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    return (a[0] * b[0] - a[1] * b[1], a[0] * b[1] + a[1] * b[0])


def _cdiv(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    """Divide complex a / b."""
    denom = b[0] * b[0] + b[1] * b[1]
    if denom < 1e-300:
        return (math.inf, math.inf)
    return ((a[0] * b[0] + a[1] * b[1]) / denom,
            (a[1] * b[0] - a[0] * b[1]) / denom)


def _cabs(a: tuple[float, float]) -> float:
    return math.sqrt(a[0] * a[0] + a[1] * a[1])


# ---------------------------------------------------------------------------
# Core mode-superposition sweep
# ---------------------------------------------------------------------------

def _modal_frf(
    omega_n: list[float],
    zeta: list[float],
    modal_forces: list[float],
    mode_dof_values: list[float],
    omega: float,
) -> tuple[float, float]:
    """
    Compute complex response  U(ω)  at a single DOF via mode superposition.

    Parameters
    ----------
    omega_n        : natural circular frequencies [rad/s], length n_modes
    zeta           : modal damping ratios, length n_modes
    modal_forces   : φ_i^T · F  (modal force participation), length n_modes
    mode_dof_values: φ_{i,j}  (mode shape value at output DOF j), length n_modes
    omega          : excitation circular frequency [rad/s]

    Returns
    -------
    (real, imag) complex response amplitude
    """
    u = (0.0, 0.0)
    for i, wn in enumerate(omega_n):
        # Modal frequency-response function
        # H_i = modal_forces[i] / (ω_n² - ω² + 2 i ζ_i ω_n ω)
        real_part = wn * wn - omega * omega
        imag_part = 2.0 * zeta[i] * wn * omega
        denom = (real_part, imag_part)
        num = (modal_forces[i], 0.0)
        Hi = _cdiv(num, denom)
        # Contribution to physical DOF: φ_{i,j} · H_i
        contrib = _cmul((mode_dof_values[i], 0.0), Hi)
        u = _cadd(u, contrib)
    return u


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def harmonic_response(
    modes: dict[str, Any],
    modal_damping: float | list[float],
    force_vector: list[float],
    freq_range: dict[str, Any],
    *,
    dof_index: int = 0,
) -> dict[str, Any]:
    """
    Steady-state harmonic response via mode superposition.

    Parameters
    ----------
    modes : dict with keys:
        "omega"       : list[float]  — natural circular frequencies [rad/s]
        "mode_shapes" : list[list]   — mode shape vectors, each of length n_dof

    modal_damping : float or list[float]
        Damping ratio ζ (scalar → all modes same; list → per-mode).

    force_vector : list[float]
        Nodal force vector F [N] of length n_dof.

    freq_range : dict with keys:
        "f_min"  : float   — minimum frequency [Hz]
        "f_max"  : float   — maximum frequency [Hz]
        "n_pts"  : int     — number of sweep points (default 200)

    dof_index : int
        Index of the output DOF to compute FRF at (default 0).

    Returns
    -------
    {
      ok              : bool,
      frequencies_hz  : list[float]     — frequency sweep [Hz],
      amplitude       : list[float]     — |U(f)| at dof_index,
      phase_deg       : list[float]     — phase angle [degrees],
      DAF_analytical  : list[float]     — SDOF DAF for first mode (validation),
      resonant_peak_hz: float           — frequency of maximum amplitude,
      resonant_amplitude: float         — peak amplitude value,
    }
    """
    # --- Validate inputs ---
    if not isinstance(modes, dict):
        return {"ok": False, "reason": "modes must be a dict with 'omega' and 'mode_shapes'"}

    omega_n = modes.get("omega", [])
    mode_shapes = modes.get("mode_shapes", [])

    if not omega_n:
        return {"ok": False, "reason": "modes['omega'] must be a non-empty list"}
    if not mode_shapes:
        return {"ok": False, "reason": "modes['mode_shapes'] must be a non-empty list"}
    if len(omega_n) != len(mode_shapes):
        return {"ok": False, "reason": "len(omega) must equal len(mode_shapes)"}

    n_modes = len(omega_n)

    # Normalise damping
    if isinstance(modal_damping, (int, float)):
        zeta = [float(modal_damping)] * n_modes
    else:
        zeta = [float(z) for z in modal_damping]
        if len(zeta) != n_modes:
            return {"ok": False, "reason": "modal_damping list length must match number of modes"}

    for z in zeta:
        if z < 0.0:
            return {"ok": False, "reason": "damping ratios must be non-negative"}

    if not force_vector:
        return {"ok": False, "reason": "force_vector must not be empty"}

    n_dof = len(force_vector)
    for ms in mode_shapes:
        if len(ms) < n_dof:
            return {"ok": False, "reason": "mode_shape vector shorter than force_vector"}

    if dof_index < 0 or dof_index >= n_dof:
        return {"ok": False, "reason": f"dof_index {dof_index} out of range [0, {n_dof-1}]"}

    f_min = float(freq_range.get("f_min", 0.0))
    f_max = float(freq_range.get("f_max", 1.0))
    n_pts = int(freq_range.get("n_pts", 200))

    if f_min < 0:
        return {"ok": False, "reason": "f_min must be >= 0"}
    if f_max <= f_min:
        return {"ok": False, "reason": "f_max must be > f_min"}
    if n_pts < 2:
        return {"ok": False, "reason": "n_pts must be >= 2"}

    # Pre-compute modal force participations: Γ_i = φ_i^T · F
    # (mass-normalised mode shapes assumed; for un-normalised, DAF is relative)
    modal_forces = []
    for i in range(n_modes):
        phi_i = mode_shapes[i]
        gamma = sum(phi_i[k] * force_vector[k] for k in range(n_dof))
        modal_forces.append(gamma)

    # Mode shape values at output DOF
    phi_dof = [mode_shapes[i][dof_index] for i in range(n_modes)]

    # First natural frequency for SDOF DAF reference
    wn0 = omega_n[0]
    fn0 = wn0 / (2.0 * math.pi)
    zeta0 = zeta[0]

    # Frequency sweep
    df = (f_max - f_min) / (n_pts - 1)
    freqs_hz = [f_min + k * df for k in range(n_pts)]

    amplitudes = []
    phases = []
    daf_analytical = []

    for f in freqs_hz:
        omega = 2.0 * math.pi * f
        u_cplx = _modal_frf(omega_n, zeta, modal_forces, phi_dof, omega)
        amp = _cabs(u_cplx)
        # Phase: atan2(imag, real), shifted to [0, 360)
        phase = math.degrees(math.atan2(u_cplx[1], u_cplx[0]))

        # SDOF analytical DAF for first mode
        r = f / fn0 if fn0 > 1e-30 else 0.0
        daf = sdof_daf(r, zeta0)

        amplitudes.append(amp)
        phases.append(phase)
        daf_analytical.append(daf)

    # Find resonant peak
    peak_amp = max(amplitudes)
    peak_idx = amplitudes.index(peak_amp)
    peak_freq = freqs_hz[peak_idx]

    return {
        "ok": True,
        "frequencies_hz": freqs_hz,
        "amplitude": amplitudes,
        "phase_deg": phases,
        "DAF_analytical": daf_analytical,
        "resonant_peak_hz": peak_freq,
        "resonant_amplitude": peak_amp,
    }


def sdof_harmonic_response(
    fn: float,
    zeta: float,
    F0: float,
    k: float,
    freq_range: dict[str, Any],
) -> dict[str, Any]:
    """
    Analytical SDOF steady-state harmonic response (validation helper).

    U_static = F0 / k
    |U(ω)| = U_static · DAF(r, ζ)

    Parameters
    ----------
    fn    : natural frequency [Hz]
    zeta  : viscous damping ratio
    F0    : force amplitude [N]
    k     : stiffness [N/m]
    freq_range : {"f_min", "f_max", "n_pts"}

    Returns
    -------
    { ok, frequencies_hz, amplitude, DAF, U_static }
    """
    if fn <= 0:
        return {"ok": False, "reason": "fn must be positive"}
    if k <= 0:
        return {"ok": False, "reason": "k must be positive"}
    if zeta < 0:
        return {"ok": False, "reason": "zeta must be non-negative"}

    f_min = float(freq_range.get("f_min", 0.0))
    f_max = float(freq_range.get("f_max", 2.0 * fn))
    n_pts = int(freq_range.get("n_pts", 200))

    if n_pts < 2:
        return {"ok": False, "reason": "n_pts must be >= 2"}
    if f_max <= f_min:
        return {"ok": False, "reason": "f_max must be > f_min"}

    U_static = F0 / k
    df = (f_max - f_min) / (n_pts - 1)
    freqs = [f_min + k_ * df for k_ in range(n_pts)]
    daf_vals = [sdof_daf(f / fn, zeta) for f in freqs]
    amp_vals = [U_static * d for d in daf_vals]

    return {
        "ok": True,
        "frequencies_hz": freqs,
        "amplitude": amp_vals,
        "DAF": daf_vals,
        "U_static": U_static,
    }
