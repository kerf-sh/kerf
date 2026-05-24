"""Balance wheel and hairspring physics.

The balance + hairspring is the timekeeping oscillator of a mechanical watch.
It is equivalent to a torsional simple harmonic oscillator:

    T = 2π · √(I / k)

where:
    I  = moment of inertia of the balance wheel (kg·m², or g·mm² internally)
    k  = torsional stiffness of the hairspring (N·m/rad, or N·mm/rad)

Public API
----------
balance_period(I_balance_gmm2, k_hairspring_Nmmrad)
    → oscillation period T in seconds.

beats_per_hour(period_seconds)
    → beat rate as a float; recognises standard calibre values.

isochronism_check(I_balance_gmm2, k_hairspring_Nmmrad, amplitude_range_deg)
    → IsochronismResult describing period sensitivity to amplitude.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Tuple


# ---------------------------------------------------------------------------
# Period and beat rate
# ---------------------------------------------------------------------------

def balance_period(
    I_balance_gmm2: float,
    k_hairspring_Nmmrad: float,
) -> float:
    """Return the oscillation period of the balance-hairspring oscillator (seconds).

    Uses the ideal SHO formula:

        T = 2π · √(I / k)

    Parameters
    ----------
    I_balance_gmm2 : float
        Moment of inertia of the balance wheel in g·mm².
        Typical wristwatch balance: 5–25 g·mm².
        Conversion: 1 g·mm² = 1e-9 kg·m².
    k_hairspring_Nmmrad : float
        Torsional stiffness of the hairspring in N·mm/rad.
        Typical wristwatch hairspring: 0.05–0.50 N·mm/rad.

    Returns
    -------
    float
        Oscillation period T in seconds.

    Raises
    ------
    ValueError
        If either parameter is non-positive.

    Notes
    -----
    Unit consistency: I in g·mm², k in N·mm/rad.
        [T] = √([g·mm²] / [N·mm/rad])
            = √([g·mm²·rad] / [N·mm])
            = √([g·mm·rad] / [N])
            = √([g·mm·rad] / [g·mm/s²])
            = √([s²·rad])
        Since rad is dimensionless: [T] = s  ✓
    """
    if I_balance_gmm2 <= 0:
        raise ValueError(
            f"I_balance_gmm2 must be positive, got {I_balance_gmm2}"
        )
    if k_hairspring_Nmmrad <= 0:
        raise ValueError(
            f"k_hairspring_Nmmrad must be positive, got {k_hairspring_Nmmrad}"
        )
    return 2.0 * math.pi * math.sqrt(I_balance_gmm2 / k_hairspring_Nmmrad)


def beats_per_hour(period_seconds: float) -> float:
    """Return the beat rate in beats per hour (bph) for a given period.

    One full oscillation = 2 beats (one tick + one tock).

        bph = 3600 / (period / 2) = 7200 / period

    Parameters
    ----------
    period_seconds : float
        Full oscillation period T in seconds.

    Returns
    -------
    float
        Beat rate in beats per hour.

    Notes
    -----
    Standard beat rates and their corresponding periods:

    +---------+-------------------+------------------------+
    | bph     | period (s)        | calibre examples       |
    +=========+===================+========================+
    | 18 000  | 0.4000  s         | vintage pocket watches |
    | 21 600  | 0.3333  s         | ETA 2472, 2783         |
    | 28 800  | 0.2500  s         | ETA 2824-2, Rolex 3135 |
    | 36 000  | 0.2000  s         | Zenith El Primero      |
    +---------+-------------------+------------------------+

    Raises
    ------
    ValueError
        If period_seconds ≤ 0.
    """
    if period_seconds <= 0:
        raise ValueError(
            f"period_seconds must be positive, got {period_seconds}"
        )
    return 7200.0 / period_seconds


def period_from_bph(bph: float) -> float:
    """Return the oscillation period (seconds) for a given beat rate.

    Inverse of beats_per_hour:  T = 7200 / bph.

    Parameters
    ----------
    bph : float
        Beat rate in beats per hour.

    Returns
    -------
    float
        Period in seconds.
    """
    if bph <= 0:
        raise ValueError(f"bph must be positive, got {bph}")
    return 7200.0 / bph


# ---------------------------------------------------------------------------
# Isochronism
# ---------------------------------------------------------------------------

@dataclass
class IsochronismResult:
    """Result of the isochronism sensitivity analysis.

    Attributes
    ----------
    I_balance_gmm2 : float
        Moment of inertia of the balance (g·mm²).
    k_hairspring_Nmmrad : float
        Hairspring stiffness (N·mm/rad).
    amplitude_range_deg : tuple[float, float]
        (min_amplitude, max_amplitude) in degrees.
    period_at_min_amp : float
        Period at the minimum amplitude (s).  For an ideal SHO this equals
        period_at_max_amp.
    period_at_max_amp : float
        Period at the maximum amplitude (s).
    delta_period_ms : float
        |period_at_max_amp − period_at_min_amp| × 1000  (milliseconds).
        An ideal SHO gives 0 ms.
    rate_sensitivity_spd : float
        Approximate rate change in seconds-per-day (s/d) over the amplitude
        range, extrapolated to 24 h.
    is_isochronous : bool
        True when delta_period_ms < threshold (0.5 ms by default).
    notes : list[str]
        Human-readable notes about the analysis.
    """
    I_balance_gmm2: float
    k_hairspring_Nmmrad: float
    amplitude_range_deg: Tuple[float, float]
    period_at_min_amp: float
    period_at_max_amp: float
    delta_period_ms: float
    rate_sensitivity_spd: float
    is_isochronous: bool
    notes: List[str] = field(default_factory=list)


def isochronism_check(
    I_balance_gmm2: float,
    k_hairspring_Nmmrad: float,
    amplitude_range_deg: Tuple[float, float] = (180.0, 300.0),
    isochronism_threshold_ms: float = 0.5,
) -> IsochronismResult:
    """Check how well the balance-hairspring maintains a constant period.

    For an ideal SHO the period is independent of amplitude.  In practice:

    * At high amplitudes, the end coils of a flat Archimedean hairspring
      stiffen (positive Breguet effect) or soften depending on collet position.
    * At low amplitudes, coil adhesion can cause period variation.

    This function models the *ideal* SHO case (period is perfectly constant
    with amplitude) and computes the theoretical sensitivity.  A real
    hairspring will deviate; the 'notes' field records what to watch for.

    Parameters
    ----------
    I_balance_gmm2 : float
        Moment of inertia of the balance (g·mm²).
    k_hairspring_Nmmrad : float
        Hairspring stiffness (N·mm/rad).
    amplitude_range_deg : tuple[float, float]
        (min_amplitude_deg, max_amplitude_deg) — the expected operating range
        of the balance wheel swing.  Typical watch: (180°, 310°).
    isochronism_threshold_ms : float
        Period variation threshold (ms) below which the system is declared
        isochronous.  Default 0.5 ms (≈ 43 s/day — generous for watchmaking;
        a fine movement targets < 0.01 ms).

    Returns
    -------
    IsochronismResult

    Notes
    -----
    For an ideal linear spring the period equals T = 2π√(I/k) regardless of
    amplitude.  The sensitivity reported here is therefore 0 for the ideal
    case.  This function serves as the *baseline*; subtracting real-world
    measurements from the ideal identifies the hairspring's anisochronism.
    """
    if I_balance_gmm2 <= 0:
        raise ValueError(f"I_balance_gmm2 must be positive, got {I_balance_gmm2}")
    if k_hairspring_Nmmrad <= 0:
        raise ValueError(
            f"k_hairspring_Nmmrad must be positive, got {k_hairspring_Nmmrad}"
        )
    amp_min, amp_max = amplitude_range_deg
    if amp_min <= 0 or amp_max <= 0:
        raise ValueError("amplitude_range_deg values must be positive")
    if amp_min >= amp_max:
        raise ValueError(
            "amplitude_range_deg[0] must be less than amplitude_range_deg[1]"
        )

    # Ideal SHO: period is amplitude-independent
    T_ideal = balance_period(I_balance_gmm2, k_hairspring_Nmmrad)

    # For a real pendulum (circular error analogy) the period correction is:
    #   T_real ≈ T_ideal × (1 + θ²/16 + ...)
    # where θ is the amplitude in radians.
    # Hairspring is torsional, not gravitational, so circular-error correction
    # is not applicable — the leading-order correction is truly 0.
    # We compute the ideal answer (delta = 0) and add a note.
    T_min = T_ideal  # period is independent of amplitude for ideal SHO
    T_max = T_ideal

    delta_ms = abs(T_max - T_min) * 1000.0
    # Rate sensitivity: extrapolate delta to 24 hours
    # Beats per day = 86400 / (T_ideal / 2)
    # If each beat is ΔT/2 shorter/longer, rate shift = (ΔT / T_ideal) × 86400
    rate_spd = (delta_ms / 1000.0 / T_ideal) * 86400.0

    notes = [
        "Ideal SHO model: period is independent of amplitude — delta = 0.",
        "Real hairsprings show anisochronism due to coil geometry; "
        "use an overcoil (Breguet) or free-sprung balance to minimise it.",
        f"Operating amplitude range: {amp_min:.0f}°–{amp_max:.0f}°.",
    ]

    return IsochronismResult(
        I_balance_gmm2=I_balance_gmm2,
        k_hairspring_Nmmrad=k_hairspring_Nmmrad,
        amplitude_range_deg=(amp_min, amp_max),
        period_at_min_amp=T_min,
        period_at_max_amp=T_max,
        delta_period_ms=delta_ms,
        rate_sensitivity_spd=rate_spd,
        is_isochronous=delta_ms < isochronism_threshold_ms,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Convenience: solve for hairspring stiffness from known bph + balance inertia
# ---------------------------------------------------------------------------

def hairspring_stiffness(
    bph: float,
    I_balance_gmm2: float,
) -> float:
    """Return the hairspring stiffness k (N·mm/rad) needed for a target beat rate.

    Inverts  T = 2π√(I/k)  →  k = I × (2π/T)² = I × (bph/7200 × π)².

    Parameters
    ----------
    bph : float
        Target beat rate in beats per hour.
    I_balance_gmm2 : float
        Moment of inertia of the balance wheel (g·mm²).

    Returns
    -------
    float
        Required hairspring torsional stiffness in N·mm/rad.
    """
    if bph <= 0:
        raise ValueError(f"bph must be positive, got {bph}")
    if I_balance_gmm2 <= 0:
        raise ValueError(f"I_balance_gmm2 must be positive, got {I_balance_gmm2}")
    T = period_from_bph(bph)
    omega = 2.0 * math.pi / T  # angular frequency rad/s
    return I_balance_gmm2 * omega ** 2
