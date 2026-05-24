"""
kerf_cad_core.acoustics.sound — engineering/architectural acoustics (pure Python).

Implements the following public functions:

SPL Arithmetic
  spl_sum(levels_db)                  — logarithmic sum of SPL values
  spl_subtract(spl_total, spl_bg)     — background-noise subtraction
  spl_average(levels_db)              — energy-average (Leq style)

Distance Attenuation
  point_source_attenuation(Lw, r, Q)  — point source SPL at distance r
  line_source_attenuation(Lw, r)      — line source SPL per metre at distance r
  inverse_square_delta(r1, r2)        — ΔL for doubling/changing distance

Reverberation
  sabine_rt60(volume_m3, total_absorption_m2)       — Sabine RT60
  eyring_rt60(volume_m3, S_m2, alpha_avg)           — Eyring RT60
  room_constant(S_m2, alpha_avg)                    — room constant R
  reverberant_spl(Lw, R)                            — reverberant-field SPL

Transmission Loss
  mass_law_tl(surface_density_kg_m2, freq_hz)       — ISO mass-law TL
  composite_tl(elements)                             — composite partition TL
  spl_transmitted(spl_source, tl_db)                — SPL after barrier

Weighting
  a_weighting_offset(freq_hz)         — A-weighting correction (dB)
  c_weighting_offset(freq_hz)         — C-weighting correction (dB)
  apply_weighting(octave_band_spls, weighting)  — apply A or C weighting
  octave_band_combine(weighted_spls)  — combine octave-band levels to single dB(A/C)

Rating
  nc_rating(octave_band_spls)         — Noise Criteria (NC) rating
  nr_rating(octave_band_spls)         — Noise Rating (NR) curve rating

HVAC Duct Noise
  duct_attenuation(length_m, diam_m, lining)     — lined/unlined duct IL
  duct_breakout_spl(Lw_in, length_m, perimeter_m, tl_db)  — breakout noise
  duct_regen_spl(velocity_mps, diam_m, fitting_type)      — regenerated noise

Sound Power / Pressure Conversion
  lw_from_lp(lp_db, r_m, Q)          — Lw from measured Lp
  lp_from_lw(lw_db, r_m, Q)          — Lp from Lw (same as point_source helper)

All functions return plain dicts:
    success → {"ok": True, ...computed fields...}
    failure → {"ok": False, "reason": "<human-readable>"}

Invalid inputs are flagged via the warnings module; functions NEVER raise.

References
----------
ISO 9613-1:1993  — Acoustics: Attenuation of sound during propagation outdoors
ISO 140-3:1995   — Measurement of airborne sound insulation
ASHRAE Handbook: HVAC Applications 2019, Chapter 48 (Noise and Vibration)
Sabine, W.C. (1900) "Reverberation" — American Architect
Eyring, C.F. (1930) — Journal of the Acoustical Society of America
Beranek, L.L. "Acoustics" (1954/1986)
Harris, C.M. "Handbook of Acoustical Measurements and Noise Control" (1991)

Author: imranparuk
"""
from __future__ import annotations

import math
import warnings
from typing import Any
from kerf_cad_core._guards import _err, _guard_nonneg, _guard_positive


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _to_linear(spl_db: float) -> float:
    """Convert dB SPL to linear mean-square pressure ratio (p²/p₀²)."""
    return 10.0 ** (spl_db / 10.0)


def _to_db(linear: float) -> float:
    """Convert linear mean-square pressure ratio to dB SPL."""
    if linear <= 0.0:
        return -math.inf
    return 10.0 * math.log10(linear)


# ---------------------------------------------------------------------------
# 1. SPL Arithmetic
# ---------------------------------------------------------------------------

# Standard octave-band centre frequencies (Hz) — 63 Hz to 8 kHz
OCTAVE_BANDS_HZ = (63, 125, 250, 500, 1000, 2000, 4000, 8000)


def spl_sum(levels_db: list[float]) -> dict:
    """
    Logarithmic sum of multiple SPL values (energy addition).

    Formula: L_total = 10 × log₁₀(Σ 10^(Lᵢ/10))

    Parameters
    ----------
    levels_db : list[float]
        List of SPL values in dB.  Must contain at least one element.

    Returns
    -------
    dict
        ok       : True
        spl_db   : combined SPL (dB)
        n        : number of sources summed
    """
    if not isinstance(levels_db, (list, tuple)) or len(levels_db) == 0:
        return _err("levels_db must be a non-empty list of dB values")
    try:
        vals = [float(x) for x in levels_db]
    except (TypeError, ValueError) as exc:
        return _err(f"levels_db contains non-numeric value: {exc}")
    if not all(math.isfinite(v) for v in vals):
        return _err("levels_db contains non-finite value")

    total_linear = sum(_to_linear(v) for v in vals)
    return {"ok": True, "spl_db": _to_db(total_linear), "n": len(vals)}


def spl_subtract(spl_total: float, spl_bg: float) -> dict:
    """
    Subtract a background noise level from a combined measurement.

    Used to recover the source SPL when only a combined SPL (source + background)
    and the background SPL alone are known.

    Formula: L_source = 10 × log₁₀(10^(L_total/10) − 10^(L_bg/10))

    Parameters
    ----------
    spl_total : float
        Total measured SPL with source present (dB).
    spl_bg : float
        Background SPL measured without source (dB).

    Returns
    -------
    dict
        ok         : True
        spl_source : recovered source SPL (dB)
        delta_db   : difference spl_total − spl_bg (dB)
    """
    try:
        total = float(spl_total)
        bg = float(spl_bg)
    except (TypeError, ValueError) as exc:
        return _err(f"non-numeric input: {exc}")

    if not (math.isfinite(total) and math.isfinite(bg)):
        return _err("spl_total and spl_bg must be finite")

    delta = total - bg
    if delta <= 0:
        warnings.warn(
            f"spl_subtract: spl_bg ({bg} dB) >= spl_total ({total} dB); "
            "result is undefined. Returning ok=False.",
            stacklevel=2,
        )
        return _err(
            f"spl_bg ({bg} dB) must be strictly less than spl_total ({total} dB)"
        )
    if delta < 3.0:
        warnings.warn(
            f"spl_subtract: difference only {delta:.1f} dB; "
            "subtraction result has high uncertainty (< 3 dB margin).",
            stacklevel=2,
        )

    lin_source = _to_linear(total) - _to_linear(bg)
    return {
        "ok": True,
        "spl_source": _to_db(lin_source),
        "delta_db": delta,
    }


def spl_average(levels_db: list[float]) -> dict:
    """
    Energy-average (Leq) of multiple SPL values.

    Formula: L_avg = 10 × log₁₀((1/N) × Σ 10^(Lᵢ/10))

    Parameters
    ----------
    levels_db : list[float]
        List of SPL values in dB. Must contain at least one element.

    Returns
    -------
    dict
        ok      : True
        spl_db  : energy-average SPL (dB)
        n       : number of values
    """
    if not isinstance(levels_db, (list, tuple)) or len(levels_db) == 0:
        return _err("levels_db must be a non-empty list of dB values")
    try:
        vals = [float(x) for x in levels_db]
    except (TypeError, ValueError) as exc:
        return _err(f"levels_db contains non-numeric value: {exc}")
    if not all(math.isfinite(v) for v in vals):
        return _err("levels_db contains non-finite value")

    n = len(vals)
    avg_linear = sum(_to_linear(v) for v in vals) / n
    return {"ok": True, "spl_db": _to_db(avg_linear), "n": n}


# ---------------------------------------------------------------------------
# 2. Distance Attenuation
# ---------------------------------------------------------------------------

def point_source_attenuation(Lw: float, r: float, Q: float = 1.0) -> dict:
    """
    Free-field SPL at distance r from a point source with directivity Q.

    Formula (ISO 9613):
        Lp = Lw + 10·log₁₀(Q / (4π r²))

    Q = 1 → free field (spherical radiation)
    Q = 2 → hemispherical radiation (source on hard reflecting plane)
    Q = 4 → 90° corner (two reflecting surfaces)
    Q = 8 → 3-surface corner

    Parameters
    ----------
    Lw : float
        Sound power level (dB re 1 pW = 10⁻¹² W).
    r : float
        Distance from source to receiver (m). Must be > 0.
    Q : float
        Directivity factor (dimensionless, default 1.0). Must be > 0.

    Returns
    -------
    dict
        ok      : True
        lp_db   : SPL at distance r (dB)
        Lw_db   : sound power level used (dB)
        r_m     : distance used (m)
        Q       : directivity factor used
    """
    err = _guard_positive("r", r)
    if err:
        return _err(err)
    err = _guard_positive("Q", Q)
    if err:
        return _err(err)
    try:
        Lw_f = float(Lw)
    except (TypeError, ValueError):
        return _err(f"Lw must be a number, got {Lw!r}")
    if not math.isfinite(Lw_f):
        return _err(f"Lw must be finite, got {Lw_f}")

    r_f = float(r)
    Q_f = float(Q)
    lp = Lw_f + 10.0 * math.log10(Q_f / (4.0 * math.pi * r_f ** 2))
    return {"ok": True, "lp_db": lp, "Lw_db": Lw_f, "r_m": r_f, "Q": Q_f}


def line_source_attenuation(Lw_per_m: float, r: float) -> dict:
    """
    SPL at distance r from an infinite coherent line source.

    Formula: Lp = Lw/m − 10·log₁₀(2π r)

    Parameters
    ----------
    Lw_per_m : float
        Sound power level per metre of line source (dB re 1 pW/m).
    r : float
        Perpendicular distance from line to receiver (m). Must be > 0.

    Returns
    -------
    dict
        ok           : True
        lp_db        : SPL at distance r (dB)
        Lw_per_m_db  : sound power per metre used (dB)
        r_m          : distance used (m)
    """
    err = _guard_positive("r", r)
    if err:
        return _err(err)
    try:
        Lw_f = float(Lw_per_m)
    except (TypeError, ValueError):
        return _err(f"Lw_per_m must be a number, got {Lw_per_m!r}")
    if not math.isfinite(Lw_f):
        return _err(f"Lw_per_m must be finite")

    r_f = float(r)
    lp = Lw_f - 10.0 * math.log10(2.0 * math.pi * r_f)
    return {"ok": True, "lp_db": lp, "Lw_per_m_db": Lw_f, "r_m": r_f}


def inverse_square_delta(r1: float, r2: float) -> dict:
    """
    SPL change due to distance change for a point source (inverse-square law).

    Formula: ΔL = −20·log₁₀(r2 / r1)

    Positive ΔL → moving closer (r2 < r1) increases SPL.
    Negative ΔL → moving farther reduces SPL (6 dB per doubling).

    Parameters
    ----------
    r1 : float
        Reference distance (m). Must be > 0.
    r2 : float
        New distance (m). Must be > 0.

    Returns
    -------
    dict
        ok       : True
        delta_db : change in SPL (dB); negative means quieter at r2
        r1_m     : reference distance (m)
        r2_m     : new distance (m)
    """
    err = _guard_positive("r1", r1)
    if err:
        return _err(err)
    err = _guard_positive("r2", r2)
    if err:
        return _err(err)
    r1_f = float(r1)
    r2_f = float(r2)
    delta = -20.0 * math.log10(r2_f / r1_f)
    return {"ok": True, "delta_db": delta, "r1_m": r1_f, "r2_m": r2_f}


# ---------------------------------------------------------------------------
# 3. Reverberation
# ---------------------------------------------------------------------------

def sabine_rt60(volume_m3: float, total_absorption_m2: float) -> dict:
    """
    Sabine reverberation time RT60.

    Formula: RT60 = 0.161 × V / A    (s)
    where A = total absorption (m²  sabins) = Σ(Sᵢ × αᵢ)

    Valid for rooms with low average absorption (α_avg < ~0.2).

    Parameters
    ----------
    volume_m3 : float
        Room volume (m³). Must be > 0.
    total_absorption_m2 : float
        Total acoustic absorption (m²). Must be > 0.

    Returns
    -------
    dict
        ok          : True
        rt60_s      : reverberation time (s)
        volume_m3   : room volume used (m³)
        absorption_m2 : total absorption used (m²)
    """
    err = _guard_positive("volume_m3", volume_m3)
    if err:
        return _err(err)
    err = _guard_positive("total_absorption_m2", total_absorption_m2)
    if err:
        return _err(err)

    V = float(volume_m3)
    A = float(total_absorption_m2)
    rt60 = 0.161 * V / A
    return {"ok": True, "rt60_s": rt60, "volume_m3": V, "absorption_m2": A}


def eyring_rt60(volume_m3: float, S_m2: float, alpha_avg: float) -> dict:
    """
    Eyring reverberation time — more accurate for higher-absorption rooms.

    Formula: RT60 = 0.161 × V / (−S × ln(1 − α_avg))    (s)

    Parameters
    ----------
    volume_m3 : float
        Room volume (m³). Must be > 0.
    S_m2 : float
        Total room surface area (m²). Must be > 0.
    alpha_avg : float
        Average absorption coefficient (0 < α < 1).

    Returns
    -------
    dict
        ok              : True
        rt60_s          : reverberation time (s)
        volume_m3       : room volume (m³)
        surface_m2      : total surface area (m²)
        alpha_avg       : average absorption coefficient
    """
    err = _guard_positive("volume_m3", volume_m3)
    if err:
        return _err(err)
    err = _guard_positive("S_m2", S_m2)
    if err:
        return _err(err)
    try:
        alpha = float(alpha_avg)
    except (TypeError, ValueError):
        return _err(f"alpha_avg must be a number, got {alpha_avg!r}")
    if not (0.0 < alpha < 1.0):
        warnings.warn(
            f"eyring_rt60: alpha_avg={alpha} is outside (0, 1); result may be invalid.",
            stacklevel=2,
        )
        return _err("alpha_avg must be in the open interval (0, 1)")

    V = float(volume_m3)
    S = float(S_m2)
    rt60 = 0.161 * V / (-S * math.log(1.0 - alpha))
    return {
        "ok": True,
        "rt60_s": rt60,
        "volume_m3": V,
        "surface_m2": S,
        "alpha_avg": alpha,
    }


def room_constant(S_m2: float, alpha_avg: float) -> dict:
    """
    Room constant R.

    Formula: R = S × α / (1 − α)    (m²)

    Used in the combined direct + reverberant field SPL formula.

    Parameters
    ----------
    S_m2 : float
        Total room surface area (m²). Must be > 0.
    alpha_avg : float
        Average absorption coefficient (0 < α < 1).

    Returns
    -------
    dict
        ok         : True
        R_m2       : room constant (m²)
        S_m2       : surface area used (m²)
        alpha_avg  : absorption coefficient used
    """
    err = _guard_positive("S_m2", S_m2)
    if err:
        return _err(err)
    try:
        alpha = float(alpha_avg)
    except (TypeError, ValueError):
        return _err(f"alpha_avg must be a number, got {alpha_avg!r}")
    if not (0.0 < alpha < 1.0):
        return _err("alpha_avg must be in the open interval (0, 1)")

    S = float(S_m2)
    R = S * alpha / (1.0 - alpha)
    return {"ok": True, "R_m2": R, "S_m2": S, "alpha_avg": alpha}


def reverberant_spl(Lw: float, R: float) -> dict:
    """
    Reverberant-field contribution to SPL.

    Formula: Lp_rev = Lw + 10·log₁₀(4 / R)    (dB)

    Combined direct + reverberant:
        Lp_total = Lw + 10·log₁₀(Q/(4π r²) + 4/R)

    This function returns only the reverberant term.

    Parameters
    ----------
    Lw : float
        Sound power level (dB re 1 pW).
    R : float
        Room constant (m²). Must be > 0.

    Returns
    -------
    dict
        ok      : True
        lp_db   : reverberant field SPL contribution (dB)
        Lw_db   : sound power level used (dB)
        R_m2    : room constant used (m²)
    """
    err = _guard_positive("R", R)
    if err:
        return _err(err)
    try:
        Lw_f = float(Lw)
    except (TypeError, ValueError):
        return _err(f"Lw must be a number, got {Lw!r}")
    if not math.isfinite(Lw_f):
        return _err("Lw must be finite")

    R_f = float(R)
    lp = Lw_f + 10.0 * math.log10(4.0 / R_f)
    return {"ok": True, "lp_db": lp, "Lw_db": Lw_f, "R_m2": R_f}


# ---------------------------------------------------------------------------
# 4. Transmission Loss
# ---------------------------------------------------------------------------

def mass_law_tl(surface_density_kg_m2: float, freq_hz: float) -> dict:
    """
    Mass-law transmission loss for a single-leaf partition.

    Formula (field-incidence mass law, ISO 140-3):
        TL = 20·log₁₀(m × f) − 47    (dB)

    where m = surface density (kg/m²), f = frequency (Hz).

    Valid for limp panels below coincidence frequency.

    Parameters
    ----------
    surface_density_kg_m2 : float
        Surface density (kg/m²). Must be > 0.
    freq_hz : float
        Frequency (Hz). Must be > 0.

    Returns
    -------
    dict
        ok                     : True
        tl_db                  : transmission loss (dB)
        surface_density_kg_m2  : surface density used (kg/m²)
        freq_hz                : frequency used (Hz)
    """
    err = _guard_positive("surface_density_kg_m2", surface_density_kg_m2)
    if err:
        return _err(err)
    err = _guard_positive("freq_hz", freq_hz)
    if err:
        return _err(err)

    m = float(surface_density_kg_m2)
    f = float(freq_hz)
    tl_raw = 20.0 * math.log10(m * f) - 47.0

    # The field-incidence mass-law formula 20·log₁₀(m·f)−47 can yield negative
    # values at low surface-densities or low frequencies (m·f < 10^(47/20) ≈ 7.1).
    # Negative TL is physically meaningless — a wall cannot amplify sound — so
    # we clamp to zero and warn.  The formula remains valid only when m·f ≫ 1
    # (typically m·f ≥ 50 for ±1 dB accuracy).
    if tl_raw < 0.0:
        warnings.warn(
            f"mass_law_tl: computed TL={tl_raw:.1f} dB is negative "
            f"(m={m} kg/m², f={f} Hz); mass-law formula is not valid at this "
            "m·f product (need m·f ≥ ~7 for TL ≥ 0, ≥ ~50 for accuracy). "
            "Clamping to 0 dB.",
            stacklevel=2,
        )
    tl = max(0.0, tl_raw)
    return {"ok": True, "tl_db": tl, "surface_density_kg_m2": m, "freq_hz": f}


def composite_tl(elements: list[dict]) -> dict:
    """
    Composite partition transmission loss from multiple parallel elements.

    Each element dict: {"area_m2": float, "tl_db": float}

    Formula:
        τ_avg = Σ(Sᵢ × τᵢ) / Σ(Sᵢ)    where τᵢ = 10^(−TLᵢ/10)
        TL_composite = −10·log₁₀(τ_avg)

    Parameters
    ----------
    elements : list[dict]
        List of partition elements; each must contain 'area_m2' and 'tl_db'.

    Returns
    -------
    dict
        ok             : True
        tl_composite_db: composite TL (dB)
        total_area_m2  : total partition area (m²)
        n_elements     : number of elements
    """
    if not isinstance(elements, (list, tuple)) or len(elements) == 0:
        return _err("elements must be a non-empty list")

    total_area = 0.0
    weighted_tau = 0.0
    for i, el in enumerate(elements):
        if not isinstance(el, dict):
            return _err(f"element {i} must be a dict with 'area_m2' and 'tl_db'")
        area_val = el.get("area_m2")
        tl_val = el.get("tl_db")
        if area_val is None:
            return _err(f"element {i} missing 'area_m2'")
        if tl_val is None:
            return _err(f"element {i} missing 'tl_db'")
        e1 = _guard_positive(f"elements[{i}].area_m2", area_val)
        if e1:
            return _err(e1)
        try:
            tl_f = float(tl_val)
        except (TypeError, ValueError):
            return _err(f"elements[{i}].tl_db must be a number")
        if not math.isfinite(tl_f):
            return _err(f"elements[{i}].tl_db must be finite")

        area_f = float(area_val)
        tau_i = 10.0 ** (-tl_f / 10.0)
        total_area += area_f
        weighted_tau += area_f * tau_i

    tau_avg = weighted_tau / total_area
    tl_composite = -10.0 * math.log10(tau_avg)
    return {
        "ok": True,
        "tl_composite_db": tl_composite,
        "total_area_m2": total_area,
        "n_elements": len(elements),
    }


def spl_transmitted(spl_source: float, tl_db: float) -> dict:
    """
    SPL on the receiving side of a barrier given source-side SPL and TL.

    Formula: Lp_transmitted = Lp_source − TL

    Parameters
    ----------
    spl_source : float
        Source-side SPL (dB).
    tl_db : float
        Transmission loss of the barrier (dB). Should be >= 0.

    Returns
    -------
    dict
        ok              : True
        lp_transmitted  : receiving-side SPL (dB)
        spl_source_db   : source SPL used (dB)
        tl_db           : TL used (dB)
    """
    try:
        lp_s = float(spl_source)
        tl = float(tl_db)
    except (TypeError, ValueError) as exc:
        return _err(f"non-numeric input: {exc}")
    if not (math.isfinite(lp_s) and math.isfinite(tl)):
        return _err("spl_source and tl_db must be finite")
    if tl < 0:
        warnings.warn(
            f"spl_transmitted: tl_db={tl} dB is negative; "
            "typically TL should be >= 0 dB.",
            stacklevel=2,
        )
    return {
        "ok": True,
        "lp_transmitted": lp_s - tl,
        "spl_source_db": lp_s,
        "tl_db": tl,
    }


# ---------------------------------------------------------------------------
# 5. Frequency Weighting
# ---------------------------------------------------------------------------

# A-weighting table: octave-band centre frequencies → correction (dB)
# Values from IEC 61672-1:2013 Table 1.
_A_WEIGHT: dict[int, float] = {
    31:   -39.4,
    63:   -26.2,
    125:  -16.1,
    250:   -8.6,
    500:   -3.2,
    1000:   0.0,
    2000:  +1.2,
    4000:  +1.0,
    8000:  -1.1,
    16000: -6.6,
}

# C-weighting table (IEC 61672-1:2013)
_C_WEIGHT: dict[int, float] = {
    31:   -3.0,
    63:   -0.8,
    125:  -0.2,
    250:   0.0,
    500:   0.0,
    1000:  0.0,
    2000: -0.2,
    4000: -0.8,
    8000: -3.0,
    16000: -8.5,
}

# Analytical A-weighting (IEC 61672) for arbitrary frequency
def a_weighting_offset(freq_hz: float) -> dict:
    """
    A-weighting frequency correction at a given frequency.

    Uses the exact IEC 61672-1 formula:
        R_A(f) = (12194² × f⁴) /
                 [(f² + 20.6²)(√((f² + 107.7²)(f² + 737.9²)))(f² + 12194²)]
        A(f)   = 20·log₁₀(R_A(f)) + 2.00  (dB)

    Parameters
    ----------
    freq_hz : float
        Frequency (Hz). Must be > 0.

    Returns
    -------
    dict
        ok              : True
        offset_db       : A-weighting correction to add to unweighted SPL (dB)
        freq_hz         : frequency used (Hz)
    """
    err = _guard_positive("freq_hz", freq_hz)
    if err:
        return _err(err)
    f = float(freq_hz)

    f2 = f * f
    num = (12194.0 ** 2) * (f2 ** 2)
    den = (
        (f2 + 20.6 ** 2)
        * math.sqrt((f2 + 107.7 ** 2) * (f2 + 737.9 ** 2))
        * (f2 + 12194.0 ** 2)
    )
    if den == 0.0:
        return _err("A-weighting formula denominator is zero at this frequency")
    Ra = num / den
    offset = 20.0 * math.log10(Ra) + 2.00
    return {"ok": True, "offset_db": offset, "freq_hz": f}


def c_weighting_offset(freq_hz: float) -> dict:
    """
    C-weighting frequency correction at a given frequency.

    Uses the exact IEC 61672-1 formula:
        R_C(f) = (12194² × f²) / [(f² + 20.6²)(f² + 12194²)]
        C(f)   = 20·log₁₀(R_C(f)) + 0.06  (dB)

    Parameters
    ----------
    freq_hz : float
        Frequency (Hz). Must be > 0.

    Returns
    -------
    dict
        ok          : True
        offset_db   : C-weighting correction to add to unweighted SPL (dB)
        freq_hz     : frequency used (Hz)
    """
    err = _guard_positive("freq_hz", freq_hz)
    if err:
        return _err(err)
    f = float(freq_hz)

    f2 = f * f
    num = (12194.0 ** 2) * f2
    den = (f2 + 20.6 ** 2) * (f2 + 12194.0 ** 2)
    if den == 0.0:
        return _err("C-weighting formula denominator is zero")
    Rc = num / den
    offset = 20.0 * math.log10(Rc) + 0.06
    return {"ok": True, "offset_db": offset, "freq_hz": f}


def apply_weighting(
    octave_band_spls: dict[int, float],
    weighting: str = "A",
) -> dict:
    """
    Apply A or C weighting to octave-band SPL values.

    Parameters
    ----------
    octave_band_spls : dict[int, float]
        Mapping of {centre_freq_hz: spl_db}.
        Accepted frequencies: 31, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000.
    weighting : str
        'A' (default) or 'C'.

    Returns
    -------
    dict
        ok              : True
        weighted_bands  : dict of {freq_hz: weighted_spl_db}
        weighting       : weighting applied ('A' or 'C')
    """
    if not isinstance(octave_band_spls, dict) or len(octave_band_spls) == 0:
        return _err("octave_band_spls must be a non-empty dict {freq_hz: spl_db}")
    w = str(weighting).strip().upper()
    if w == "A":
        table = _A_WEIGHT
    elif w == "C":
        table = _C_WEIGHT
    else:
        return _err(f"weighting must be 'A' or 'C', got {weighting!r}")

    weighted: dict[int, float] = {}
    for freq, spl in octave_band_spls.items():
        try:
            f = int(freq)
            s = float(spl)
        except (TypeError, ValueError) as exc:
            return _err(f"invalid band entry ({freq}: {spl}): {exc}")
        if f not in table:
            return _err(
                f"frequency {f} Hz not in weighting table. "
                f"Supported: {sorted(table.keys())}"
            )
        if not math.isfinite(s):
            return _err(f"SPL at {f} Hz must be finite")
        weighted[f] = s + table[f]

    return {"ok": True, "weighted_bands": weighted, "weighting": w}


def octave_band_combine(weighted_spls: dict[int, float]) -> dict:
    """
    Combine weighted octave-band SPL values into a single overall level.

    Formula: L_total = 10·log₁₀(Σ 10^(Lᵢ/10))

    Parameters
    ----------
    weighted_spls : dict[int, float]
        Mapping of {centre_freq_hz: weighted_spl_db}.

    Returns
    -------
    dict
        ok           : True
        combined_db  : overall combined SPL (dB(A) or dB(C) depending on input)
        n_bands      : number of octave bands combined
    """
    if not isinstance(weighted_spls, dict) or len(weighted_spls) == 0:
        return _err("weighted_spls must be a non-empty dict {freq_hz: spl_db}")
    vals = []
    for freq, spl in weighted_spls.items():
        try:
            s = float(spl)
        except (TypeError, ValueError) as exc:
            return _err(f"invalid SPL at {freq} Hz: {exc}")
        if not math.isfinite(s):
            return _err(f"SPL at {freq} Hz must be finite")
        vals.append(s)

    total_linear = sum(_to_linear(v) for v in vals)
    return {"ok": True, "combined_db": _to_db(total_linear), "n_bands": len(vals)}


# ---------------------------------------------------------------------------
# 6. NC / NR Rating
# ---------------------------------------------------------------------------

# NC curve values at standard octave bands (63–8000 Hz)
# Source: Beranek 1989, ASHRAE 2019 Chapter 48
# _NC_CURVES[nc_value] = tuple of SPL limits at (63, 125, 250, 500, 1000, 2000, 4000, 8000)
_NC_BANDS = (63, 125, 250, 500, 1000, 2000, 4000, 8000)
_NC_CURVES: dict[int, tuple] = {
    15:  (47, 36, 29, 22, 17, 14, 12, 11),
    20:  (51, 40, 33, 26, 22, 19, 17, 16),
    25:  (54, 44, 37, 31, 27, 24, 22, 21),
    30:  (57, 48, 41, 35, 31, 29, 28, 27),
    35:  (60, 52, 45, 40, 36, 34, 33, 32),
    40:  (64, 56, 50, 45, 41, 39, 38, 37),
    45:  (67, 60, 54, 49, 46, 44, 43, 42),
    50:  (71, 64, 58, 54, 51, 49, 48, 47),
    55:  (74, 67, 62, 58, 56, 54, 53, 52),
    60:  (77, 71, 67, 63, 61, 59, 58, 57),
    65:  (80, 75, 71, 68, 66, 64, 63, 62),
    70:  (83, 79, 75, 72, 71, 70, 69, 68),
}


def nc_rating(octave_band_spls: dict) -> dict:
    """
    Noise Criteria (NC) rating for an octave-band SPL spectrum.

    The NC rating is the highest NC curve that is tangent to (not exceeded by)
    the measured spectrum across the standard bands 63–8000 Hz.

    Parameters
    ----------
    octave_band_spls : dict
        Mapping {freq_hz: spl_db} for the 8 standard bands
        (63, 125, 250, 500, 1000, 2000, 4000, 8000 Hz).
        Not all bands are required; only those present are rated.

    Returns
    -------
    dict
        ok              : True
        nc_rating       : integer NC curve level (e.g. 35); or None if above NC-70
        exceeds_nc70    : True if any band exceeds NC-70
        band_exceedance : dict {freq_hz: margin_db} — how much each band exceeds
                          its NC-limit at the rated NC level (negative = margin)
        octave_band_spls: echo of input
    """
    if not isinstance(octave_band_spls, dict) or len(octave_band_spls) == 0:
        return _err("octave_band_spls must be a non-empty dict")
    try:
        bands: dict[int, float] = {int(k): float(v) for k, v in octave_band_spls.items()}
    except (TypeError, ValueError) as exc:
        return _err(f"invalid band data: {exc}")

    exceeds_nc70 = False
    nc_top = _NC_CURVES[70]
    for freq, spl in bands.items():
        if freq in _NC_BANDS:
            idx = _NC_BANDS.index(freq)
            if spl > nc_top[idx]:
                exceeds_nc70 = True
                break

    if exceeds_nc70:
        warnings.warn(
            "nc_rating: spectrum exceeds NC-70 in at least one octave band.",
            stacklevel=2,
        )

    nc_result = None
    for nc_val in sorted(_NC_CURVES.keys()):
        curve = _NC_CURVES[nc_val]
        dominated = True
        for freq, spl in bands.items():
            if freq in _NC_BANDS:
                idx = _NC_BANDS.index(freq)
                if spl > curve[idx]:
                    dominated = False
                    break
        if dominated:
            nc_result = nc_val
            break

    if nc_result is None and not exceeds_nc70:
        nc_result = 70  # below all our defined curves

    # Compute band exceedance at rated NC (or NC-70 if none found)
    display_nc = nc_result if nc_result is not None else 70
    curve_for_display = _NC_CURVES.get(display_nc, _NC_CURVES[70])
    exceedance: dict[int, float] = {}
    for freq, spl in bands.items():
        if freq in _NC_BANDS:
            idx = _NC_BANDS.index(freq)
            exceedance[freq] = spl - curve_for_display[idx]

    return {
        "ok": True,
        "nc_rating": nc_result,
        "exceeds_nc70": exceeds_nc70,
        "band_exceedance": exceedance,
        "octave_band_spls": {k: float(v) for k, v in bands.items()},
    }


# NR curve values at octave bands 63–8000 Hz
# Source: ISO 1996-1:2016 / BS 8233:2014
_NR_BANDS = (63, 125, 250, 500, 1000, 2000, 4000, 8000)
_NR_CURVES: dict[int, tuple] = {
    0:  (55, 44, 35, 29, 25, 22, 21, 20),
    5:  (58, 47, 38, 32, 28, 25, 24, 23),
    10: (61, 50, 41, 35, 31, 28, 27, 26),
    15: (64, 53, 44, 38, 34, 31, 30, 29),
    20: (67, 56, 47, 41, 37, 34, 33, 32),
    25: (70, 59, 50, 44, 40, 37, 36, 35),
    30: (73, 62, 53, 47, 43, 40, 39, 38),
    35: (76, 65, 56, 50, 46, 43, 42, 41),
    40: (79, 68, 59, 53, 49, 46, 45, 44),
    45: (82, 71, 62, 56, 52, 49, 48, 47),
    50: (85, 74, 65, 59, 55, 52, 51, 50),
    55: (88, 77, 68, 62, 58, 55, 54, 53),
    60: (91, 80, 71, 65, 61, 58, 57, 56),
    65: (94, 83, 74, 68, 64, 61, 60, 59),
    70: (97, 86, 77, 71, 67, 64, 63, 62),
    75: (100, 89, 80, 74, 70, 67, 66, 65),
}


def nr_rating(octave_band_spls: dict) -> dict:
    """
    Noise Rating (NR) curve level for an octave-band SPL spectrum.

    The NR rating is the lowest NR curve that is at or above the measured
    spectrum in all octave bands (ISO 1996-1).

    Parameters
    ----------
    octave_band_spls : dict
        Mapping {freq_hz: spl_db} for the 8 standard bands
        (63, 125, 250, 500, 1000, 2000, 4000, 8000 Hz).

    Returns
    -------
    dict
        ok              : True
        nr_rating       : integer NR curve (e.g. 35); or None if above NR-75
        exceeds_nr75    : True if any band exceeds NR-75
        band_exceedance : dict {freq_hz: margin_db} at rated NR level
        octave_band_spls: echo of input
    """
    if not isinstance(octave_band_spls, dict) or len(octave_band_spls) == 0:
        return _err("octave_band_spls must be a non-empty dict")
    try:
        bands: dict[int, float] = {int(k): float(v) for k, v in octave_band_spls.items()}
    except (TypeError, ValueError) as exc:
        return _err(f"invalid band data: {exc}")

    exceeds_nr75 = False
    nr_top = _NR_CURVES[75]
    for freq, spl in bands.items():
        if freq in _NR_BANDS:
            idx = _NR_BANDS.index(freq)
            if spl > nr_top[idx]:
                exceeds_nr75 = True
                break

    if exceeds_nr75:
        warnings.warn(
            "nr_rating: spectrum exceeds NR-75 in at least one octave band.",
            stacklevel=2,
        )

    nr_result = None
    for nr_val in sorted(_NR_CURVES.keys()):
        curve = _NR_CURVES[nr_val]
        dominated = True
        for freq, spl in bands.items():
            if freq in _NR_BANDS:
                idx = _NR_BANDS.index(freq)
                if spl > curve[idx]:
                    dominated = False
                    break
        if dominated:
            nr_result = nr_val
            break

    display_nr = nr_result if nr_result is not None else 75
    curve_for_display = _NR_CURVES.get(display_nr, _NR_CURVES[75])
    exceedance: dict[int, float] = {}
    for freq, spl in bands.items():
        if freq in _NR_BANDS:
            idx = _NR_BANDS.index(freq)
            exceedance[freq] = spl - curve_for_display[idx]

    return {
        "ok": True,
        "nr_rating": nr_result,
        "exceeds_nr75": exceeds_nr75,
        "band_exceedance": exceedance,
        "octave_band_spls": {k: float(v) for k, v in bands.items()},
    }


# ---------------------------------------------------------------------------
# 7. HVAC Duct Noise
# ---------------------------------------------------------------------------

# Duct attenuation coefficients (dB/m) for lined rectangular ducts
# Approx. from ASHRAE HVAC Applications 2019, Chapter 48 Table 5
# Indexed by octave-band centre frequency (Hz)
_DUCT_LINED_ATTENUATION: dict[int, float] = {
    63:   0.66,
    125:  1.15,
    250:  1.97,
    500:  2.95,
    1000: 3.28,
    2000: 3.28,
    4000: 2.62,
    8000: 1.64,
}

# Unlined rectangular duct self-noise attenuation (dB/m)
_DUCT_UNLINED_ATTENUATION: dict[int, float] = {
    63:   0.16,
    125:  0.33,
    250:  0.49,
    500:  0.66,
    1000: 0.66,
    2000: 0.66,
    4000: 0.66,
    8000: 0.66,
}


def duct_attenuation(
    length_m: float,
    diam_m: float,
    lining: str = "unlined",
) -> dict:
    """
    Approximate insertion loss (IL) for a straight duct section.

    Uses simplified per-octave-band attenuation rates from ASHRAE 2019.

    Parameters
    ----------
    length_m : float
        Duct length (m). Must be > 0.
    diam_m : float
        Hydraulic diameter of duct (m). Must be > 0.
        For rectangular ducts: D_h = 2ab/(a+b).
    lining : str
        'lined' or 'unlined' (default 'unlined').

    Returns
    -------
    dict
        ok              : True
        il_by_band_db   : dict {freq_hz: insertion_loss_db} for 63–8000 Hz
        total_il_db     : dict {freq_hz: IL} (same as il_by_band_db, named for clarity)
        length_m        : duct length used (m)
        diam_m          : duct diameter used (m)
        lining          : lining type used
    """
    err = _guard_positive("length_m", length_m)
    if err:
        return _err(err)
    err = _guard_positive("diam_m", diam_m)
    if err:
        return _err(err)

    lin = str(lining).strip().lower()
    if lin == "lined":
        atten_table = _DUCT_LINED_ATTENUATION
    elif lin == "unlined":
        atten_table = _DUCT_UNLINED_ATTENUATION
    else:
        return _err(f"lining must be 'lined' or 'unlined', got {lining!r}")

    L = float(length_m)
    il: dict[int, float] = {freq: rate * L for freq, rate in atten_table.items()}
    return {
        "ok": True,
        "il_by_band_db": il,
        "total_il_db": il,
        "length_m": L,
        "diam_m": float(diam_m),
        "lining": lin,
    }


def duct_breakout_spl(
    Lw_in: float,
    length_m: float,
    perimeter_m: float,
    tl_db: float,
) -> dict:
    """
    Breakout noise SPL radiated through a duct wall.

    Formula (ASHRAE 2019, Ch. 48):
        Lp_out = Lw_in − TL + 10·log₁₀(perimeter × length / A_ref)
    where A_ref = 1 m² (reference area).

    Parameters
    ----------
    Lw_in : float
        Sound power level inside the duct (dB re 1 pW).
    length_m : float
        Duct section length (m). Must be > 0.
    perimeter_m : float
        Duct cross-section perimeter (m). Must be > 0.
    tl_db : float
        Transmission loss of the duct wall (dB).

    Returns
    -------
    dict
        ok            : True
        lp_breakout   : breakout SPL at reference distance (dB)
        Lw_in_db      : source Lw used (dB)
        length_m      : section length used (m)
        perimeter_m   : perimeter used (m)
        tl_db         : TL used (dB)
    """
    err = _guard_positive("length_m", length_m)
    if err:
        return _err(err)
    err = _guard_positive("perimeter_m", perimeter_m)
    if err:
        return _err(err)
    try:
        Lw_f = float(Lw_in)
        tl_f = float(tl_db)
    except (TypeError, ValueError) as exc:
        return _err(f"non-numeric input: {exc}")
    if not (math.isfinite(Lw_f) and math.isfinite(tl_f)):
        return _err("Lw_in and tl_db must be finite")

    L_f = float(length_m)
    p_f = float(perimeter_m)
    area = p_f * L_f
    lp_out = Lw_f - tl_f + 10.0 * math.log10(area / 1.0)
    return {
        "ok": True,
        "lp_breakout": lp_out,
        "Lw_in_db": Lw_f,
        "length_m": L_f,
        "perimeter_m": p_f,
        "tl_db": tl_f,
    }


# Regenerated noise Lw per fitting type (approximate dB, relative to velocity)
# Simplified model: Lw = A + B·log₁₀(V) where V = velocity (m/s)
# Source: ASHRAE 2019, Ch. 48
_REGEN_FITTING_COEFF: dict[str, tuple[float, float]] = {
    "elbow_90":    (30.0, 50.0),
    "elbow_45":    (26.0, 48.0),
    "tee_branch":  (28.0, 52.0),
    "tee_through": (22.0, 45.0),
    "reducer":     (18.0, 40.0),
    "diffuser":    (20.0, 42.0),
}


def duct_regen_spl(
    velocity_mps: float,
    diam_m: float,
    fitting_type: str = "elbow_90",
) -> dict:
    """
    Approximate regenerated (self-generated) noise Lw from a duct fitting.

    Uses a simplified power-law relationship: Lw = A + B·log₁₀(V/V_ref)
    where V_ref = 1 m/s.  Suitable for early design estimates only.

    Parameters
    ----------
    velocity_mps : float
        Duct air velocity upstream of fitting (m/s). Must be > 0.
    diam_m : float
        Duct hydraulic diameter (m). Must be > 0.
    fitting_type : str
        One of: 'elbow_90', 'elbow_45', 'tee_branch', 'tee_through',
        'reducer', 'diffuser' (default 'elbow_90').

    Returns
    -------
    dict
        ok           : True
        Lw_regen_db  : estimated regenerated Lw (dB re 1 pW)
        velocity_mps : velocity used (m/s)
        diam_m       : diameter used (m)
        fitting_type : fitting type used
    """
    err = _guard_positive("velocity_mps", velocity_mps)
    if err:
        return _err(err)
    err = _guard_positive("diam_m", diam_m)
    if err:
        return _err(err)

    ft = str(fitting_type).strip().lower()
    if ft not in _REGEN_FITTING_COEFF:
        valid = list(_REGEN_FITTING_COEFF.keys())
        return _err(f"fitting_type {fitting_type!r} not recognised. Supported: {valid}")

    V = float(velocity_mps)
    A, B = _REGEN_FITTING_COEFF[ft]
    Lw = A + B * math.log10(V)
    if V > 15.0:
        warnings.warn(
            f"duct_regen_spl: velocity {V} m/s exceeds typical duct design limit "
            "of ~15 m/s; regenerated noise estimate may be unreliable.",
            stacklevel=2,
        )
    return {
        "ok": True,
        "Lw_regen_db": Lw,
        "velocity_mps": V,
        "diam_m": float(diam_m),
        "fitting_type": ft,
    }


# ---------------------------------------------------------------------------
# 8. Sound Power ↔ Pressure conversion
# ---------------------------------------------------------------------------

def lw_from_lp(lp_db: float, r_m: float, Q: float = 1.0) -> dict:
    """
    Estimate sound power level Lw from a measured SPL Lp at distance r.

    Inverse of point_source_attenuation:
        Lw = Lp − 10·log₁₀(Q / (4π r²))
           = Lp + 10·log₁₀(4π r² / Q)

    Assumes free-field conditions (no room effect).

    Parameters
    ----------
    lp_db : float
        Measured SPL at distance r (dB).
    r_m : float
        Measurement distance from source (m). Must be > 0.
    Q : float
        Directivity factor (default 1.0). Must be > 0.

    Returns
    -------
    dict
        ok      : True
        Lw_db   : estimated sound power level (dB re 1 pW)
        lp_db   : SPL used (dB)
        r_m     : distance used (m)
        Q       : directivity used
    """
    err = _guard_positive("r_m", r_m)
    if err:
        return _err(err)
    err = _guard_positive("Q", Q)
    if err:
        return _err(err)
    try:
        lp_f = float(lp_db)
    except (TypeError, ValueError):
        return _err(f"lp_db must be a number, got {lp_db!r}")
    if not math.isfinite(lp_f):
        return _err("lp_db must be finite")

    r_f = float(r_m)
    Q_f = float(Q)
    Lw = lp_f + 10.0 * math.log10(4.0 * math.pi * r_f ** 2 / Q_f)
    return {"ok": True, "Lw_db": Lw, "lp_db": lp_f, "r_m": r_f, "Q": Q_f}


def lp_from_lw(lw_db: float, r_m: float, Q: float = 1.0) -> dict:
    """
    Calculate SPL at distance r from sound power level Lw.

    Alias for point_source_attenuation with clearer naming.

    Parameters
    ----------
    lw_db : float
        Sound power level (dB re 1 pW).
    r_m : float
        Distance from source (m). Must be > 0.
    Q : float
        Directivity factor (default 1.0). Must be > 0.

    Returns
    -------
    dict
        ok      : True
        lp_db   : SPL at distance r (dB)
        Lw_db   : sound power level used (dB)
        r_m     : distance used (m)
        Q       : directivity used
    """
    return point_source_attenuation(lw_db, r_m, Q)
