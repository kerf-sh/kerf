"""
EMC/EMI pre-compliance estimator — closed-form antenna and coupling models.

This module is distinct from:
  • kerf_electronics.si   — signal integrity (Z0, propagation, crosstalk)
  • kerf_electronics.pdn  — power-delivery network (IR-drop, decap)

All functions are pure Python (math module only) and follow the kerf
never-raise contract: validation errors are returned as dicts with
{ok: False, reason: str}; warnings are issued via the standard warnings
module for limit exceedances; exceptions are never raised to callers.

Formulas and references
------------------------
Differential-mode (DM) radiated emission from a current loop
    (Ott, "Electromagnetic Compatibility Engineering", Wiley 2009, §6.2):

    E [V/m] = (263e-16 * f^2 * A * I) / r

    where f = frequency [Hz], A = loop area [m²], I = loop current [A],
    r = measurement distance [m].  Valid for r > λ/(2π) (far field).

Common-mode (CM) radiated emission from a cable of length L carrying
    common-mode current I_cm (Ott §6.3 / Paul "Introduction to EMC" §10.5):

    E [V/m] = (4π × 10⁻⁷ × f × I_cm × L) / r
            ≈ (1.257e-6 × f × I_cm × L) / r

    This is the long-wire antenna approximation; it gives a conservative
    (worst-case) estimate for electrically short cables (L < λ/4).

FCC Part 15 Class A / Class B radiated emission limits at 10 m (§15.109):
    Class A limits (dBμV/m at 10 m):
        30–88 MHz   : 39.5 dBμV/m
        88–216 MHz  : 43.5 dBμV/m
        216–960 MHz : 46.4 dBμV/m
        >960 MHz    : 49.5 dBμV/m
    Class B limits (dBμV/m at 10 m):
        30–88 MHz   : 29.5 dBμV/m
        88–216 MHz  : 33.5 dBμV/m
        216–960 MHz : 35.5 dBμV/m
        >960 MHz    : 43.5 dBμV/m

    Note: FCC §15.109 specifies measurements at 10 m for Class A and
    3 m for Class B.  These limits are scaled here to a common reference
    using the 1/r free-space field relationship so both classes can be
    evaluated at arbitrary distances.

CISPR 22 / CISPR 32 Class A / Class B radiated emission limits at 10 m
    (CISPR 32:2015 Annex B Table B.4 for 10-m, which matches CISPR 22):
    Class A (dBμV/m at 10 m):
        30–230 MHz  : 40.0 dBμV/m
        230 MHz–1 GHz: 47.0 dBμV/m
    Class B (dBμV/m at 10 m):
        30–230 MHz  : 30.0 dBμV/m
        230 MHz–1 GHz: 37.0 dBμV/m
    Above 1 GHz: only CISPR 32 Class B 47.0 / Class A 54.0 (quasi-peak)

Near-field capacitive + inductive crosstalk between two parallel traces
    (Paul §6.3, first-order lumped model):

    Capacitive coupling coefficient:
        Kc = Cm / C0
           ≈ (2πε₀εᵣ * d * length) / (C0 * dist)  [simplified proximity]
       For the simplified model: Kc ≈ 1 / (1 + (dist/d)²)
       where dist = centre-to-centre trace spacing, d = trace width.

    Inductive coupling coefficient:
        Kl = Lm / L0
           ≈ μ₀ / (2π) * ln((dist/h)²) / L0   [simplified]
       For the simplified model (equal traces over ground plane):
           Kl ≈ 1 / (1 + (2*dist/h)²)
       where h = trace height above ground.

    Combined coupling = sqrt(Kc² + Kl²) [worst-case]

    This first-order model is consistent with IPC-2141A §5 and gives
    the same qualitative monotonic decrease with separation that the
    SI crosstalk model produces.

Shielding effectiveness of a conductive enclosure (Schelkunoff theory,
    simplified per Ott §5.3 / IEC 62153-4-7):

    SE_total [dB] = SE_absorption + SE_reflection - SE_multiple

    SE_absorption = 131.4 * t * sqrt(f * μr * σr)
        where t = wall thickness [m], μr = relative permeability,
        σr = relative conductivity (copper = 1.0), f in Hz.
        At 1 MHz, 1 mm copper: ≈ 129 dB.

    SE_reflection = 168 + 10*log10(σr / (μr * f))   [plane wave, far field]

    SE_multiple ≈ 20*log10(1 - 10^(−SE_absorption/10))  [negligible when SEa>10dB]

    Aperture leakage (rectangular slot, length L_slot [m]):
        SE_aperture [dB] = 20*log10(λ / (2 * L_slot))
                         = 20*log10(c / (2 * f * L_slot))
    The effective SE is min(SE_total, SE_aperture) when an aperture is present.

All E-field results are in dBμV/m.  Positive margin means the emission is
below the limit; negative margin means exceedance.

Author: imranparuk
"""
from __future__ import annotations

import math
import warnings
from typing import Optional

# ── Physical constants ────────────────────────────────────────────────────────

_C = 2.998e8          # speed of light [m/s]
_MU0 = 4 * math.pi * 1e-7  # free-space permeability [H/m]
_EPS0 = 8.854e-12     # free-space permittivity [F/m]

# ── Helpers ───────────────────────────────────────────────────────────────────


def _vpm_to_dbuvm(e_vpm: float) -> float:
    """Convert E-field [V/m] to dBμV/m.  E=0 returns -inf (not raised)."""
    if e_vpm <= 0.0:
        return -math.inf
    return 20.0 * math.log10(e_vpm * 1e6)


def _dbuvm_to_vpm(e_dbuvm: float) -> float:
    """Convert dBμV/m to V/m."""
    return 10.0 ** (e_dbuvm / 20.0) * 1e-6


def _validate_positive(value, name: str) -> Optional[str]:
    """Return an error string if value is not a positive real number."""
    if not isinstance(value, (int, float)) or math.isnan(value) or value <= 0:
        return f"{name} must be a positive number, got {value!r}"
    return None


def _validate_nonneg(value, name: str) -> Optional[str]:
    """Return an error string if value is negative or not a real number."""
    if not isinstance(value, (int, float)) or math.isnan(value) or value < 0:
        return f"{name} must be >= 0, got {value!r}"
    return None


# ── FCC Part 15 limit lines ────────────────────────────────────────────────────

# Limits are stored at 10 m reference distance.  The breakpoints follow
# FCC §15.109 Table 1 (Class A) and Table 2 (Class B).

_FCC_CLASS_A_10M = [
    (30e6,   88e6,   39.5),
    (88e6,   216e6,  43.5),
    (216e6,  960e6,  46.4),
    (960e6,  1e12,   49.5),
]

_FCC_CLASS_B_10M = [
    (30e6,   88e6,   29.5),
    (88e6,   216e6,  33.5),
    (216e6,  960e6,  35.5),
    (960e6,  1e12,   43.5),
]

# ── CISPR 22 / CISPR 32 limit lines ──────────────────────────────────────────

_CISPR_CLASS_A_10M = [
    (30e6,   230e6,  40.0),
    (230e6,  1e9,    47.0),
    (1e9,    6e9,    54.0),
]

_CISPR_CLASS_B_10M = [
    (30e6,   230e6,  30.0),
    (230e6,  1e9,    37.0),
    (1e9,    6e9,    47.0),
]


def _lookup_limit(freq_hz: float, table: list) -> Optional[float]:
    """Return the limit in dBμV/m for freq_hz from a piecewise-constant table."""
    for f_lo, f_hi, limit in table:
        if f_lo <= freq_hz < f_hi:
            return limit
    # Above last breakpoint: return last limit
    if table and freq_hz >= table[-1][0]:
        return table[-1][2]
    return None


def fcc_limit_dbuvm(
    freq_hz: float,
    class_: str = "B",
    distance_m: float = 10.0,
) -> dict:
    """
    FCC Part 15 §15.109 radiated emission limit in dBμV/m.

    FCC §15.109 publishes Class A limits at 10 m and Class B limits at 3 m.
    Internally, both tables are stored as 10 m–equivalent values (the Class B
    3 m values have been scaled to 10 m via 20·log10(3/10) ≈ −10.46 dB so
    that a single reference-distance correction based on 10 m applies to both
    classes).  When distance_m differs from 10 m, the limit is adjusted using
    the 20·log10(10/distance_m) free-space correction.

    Parameters
    ----------
    freq_hz    : float — frequency [Hz], must be 30 MHz – 40 GHz
    class_     : str   — 'A' or 'B' (default 'B')
    distance_m : float — measurement distance [m] (default 10.0 m)

    Returns
    -------
    dict with keys: ok, limit_dbuvm, freq_hz, class_, distance_m
    """
    err = _validate_positive(freq_hz, "freq_hz")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(distance_m, "distance_m")
    if err:
        return {"ok": False, "reason": err}
    class_ = str(class_).upper().strip()
    if class_ not in ("A", "B"):
        return {"ok": False, "reason": "class_ must be 'A' or 'B'"}

    table = _FCC_CLASS_A_10M if class_ == "A" else _FCC_CLASS_B_10M
    limit_at_ref = _lookup_limit(freq_hz, table)
    if limit_at_ref is None:
        return {
            "ok": False,
            "reason": f"No FCC Class {class_} limit defined for {freq_hz/1e6:.1f} MHz",
        }

    # Both tables store 10 m–equivalent values (see _FCC_CLASS_A_10M / _FCC_CLASS_B_10M).
    # FCC §15.109 publishes Class B at 3 m and Class A at 10 m, but the stored limits are
    # already scaled to the 10 m reference distance so that a single distance correction
    #   20·log10(10 / distance_m)
    # produces the correct limit at any requested distance.
    # (Bug fix: previously ref_dist was set to 3 m for Class B, which applied the wrong
    # correction factor and returned limits 10.46 dB too low at every distance.)
    ref_dist = 10.0  # both tables use 10 m as the common reference
    # Adjust to requested distance using 1/r (free-space)
    correction_db = 20.0 * math.log10(ref_dist / distance_m)
    limit_adj = limit_at_ref + correction_db

    return {
        "ok": True,
        "freq_hz": freq_hz,
        "class_": class_,
        "distance_m": distance_m,
        "limit_dbuvm": round(limit_adj, 2),
        "standard": "FCC Part 15 §15.109",
    }


def cispr_limit_dbuvm(
    freq_hz: float,
    class_: str = "B",
    distance_m: float = 10.0,
) -> dict:
    """
    CISPR 22 / CISPR 32 radiated emission limit in dBμV/m.

    Reference distance is 10 m for both classes.  Adjustment to other
    distances via 20*log10(10/d).

    Parameters
    ----------
    freq_hz    : float — frequency [Hz], must be 30 MHz – 6 GHz
    class_     : str   — 'A' or 'B' (default 'B')
    distance_m : float — measurement distance [m] (default 10.0 m)

    Returns
    -------
    dict with keys: ok, limit_dbuvm, freq_hz, class_, distance_m
    """
    err = _validate_positive(freq_hz, "freq_hz")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(distance_m, "distance_m")
    if err:
        return {"ok": False, "reason": err}
    class_ = str(class_).upper().strip()
    if class_ not in ("A", "B"):
        return {"ok": False, "reason": "class_ must be 'A' or 'B'"}

    table = _CISPR_CLASS_A_10M if class_ == "A" else _CISPR_CLASS_B_10M
    limit_at_ref = _lookup_limit(freq_hz, table)
    if limit_at_ref is None:
        return {
            "ok": False,
            "reason": f"No CISPR Class {class_} limit defined for {freq_hz/1e6:.1f} MHz",
        }

    ref_dist = 10.0
    correction_db = 20.0 * math.log10(ref_dist / distance_m)
    limit_adj = limit_at_ref + correction_db

    return {
        "ok": True,
        "freq_hz": freq_hz,
        "class_": class_,
        "distance_m": distance_m,
        "limit_dbuvm": round(limit_adj, 2),
        "standard": "CISPR 32:2015 / CISPR 22",
    }


# ── Radiated emission — differential mode ─────────────────────────────────────


def radiated_emission_differential(
    freq_hz: float,
    loop_area_m2: float,
    current_a: float,
    distance_m: float = 3.0,
) -> dict:
    """
    Estimate far-field radiated E-field from a differential-mode current loop.

    Uses the small-loop (magnetic dipole) far-field approximation from
    Ott, "Electromagnetic Compatibility Engineering" (Wiley, 2009), §6.2:

        E [V/m] = (263e-16 × f² × A × I) / r

    Valid in the far field (r > λ/(2π)).  A warning is issued when the
    measurement distance is in the near field.

    Parameters
    ----------
    freq_hz      : float — fundamental frequency [Hz]
    loop_area_m2 : float — enclosed loop area [m²] (length × width of current path)
    current_a    : float — loop current amplitude [A] (peak or RMS — same formula)
    distance_m   : float — measurement distance [m] (default 3.0 m)

    Returns
    -------
    dict with keys:
        ok, freq_hz, loop_area_m2, current_a, distance_m,
        e_field_vpm, e_field_dbuvm,
        far_field (bool — True if r > λ/(2π))
    """
    err = _validate_positive(freq_hz, "freq_hz")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(loop_area_m2, "loop_area_m2")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(current_a, "current_a")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(distance_m, "distance_m")
    if err:
        return {"ok": False, "reason": err}

    wavelength = _C / freq_hz
    near_field_boundary = wavelength / (2.0 * math.pi)
    far_field = distance_m >= near_field_boundary

    if not far_field:
        warnings.warn(
            f"radiated_emission_differential: measurement distance {distance_m:.2f} m "
            f"is in the near field (λ/(2π) = {near_field_boundary:.2f} m at "
            f"{freq_hz/1e6:.1f} MHz).  Far-field formula may underestimate.",
            stacklevel=2,
        )

    # Ott §6.2: E = 263e-16 * f^2 * A * I / r
    e_vpm = (263e-16 * freq_hz**2 * loop_area_m2 * current_a) / distance_m
    e_dbuvm = _vpm_to_dbuvm(e_vpm)

    return {
        "ok": True,
        "freq_hz": freq_hz,
        "loop_area_m2": loop_area_m2,
        "current_a": current_a,
        "distance_m": distance_m,
        "e_field_vpm": e_vpm,
        "e_field_dbuvm": round(e_dbuvm, 2),
        "far_field": far_field,
        "formula": "Ott (2009) §6.2: E = 263e-16 × f² × A × I / r",
    }


# ── Radiated emission — common mode ──────────────────────────────────────────


def radiated_emission_common_mode(
    freq_hz: float,
    cable_length_m: float,
    current_a: float,
    distance_m: float = 3.0,
) -> dict:
    """
    Estimate far-field radiated E-field from common-mode cable current.

    Uses the long-wire (short monopole) antenna approximation from
    Ott §6.3 / Paul "Introduction to EMC" (2006) §10.5:

        E [V/m] = (4π × 10⁻⁷ × f × I_cm × L) / r

    Conservative (worst-case) for cables electrically short (L < λ/4).
    A warning is issued when the cable length exceeds λ/4.

    Parameters
    ----------
    freq_hz       : float — frequency [Hz]
    cable_length_m : float — cable length [m]
    current_a     : float — common-mode current amplitude [A]
    distance_m    : float — measurement distance [m] (default 3.0 m)

    Returns
    -------
    dict with keys:
        ok, freq_hz, cable_length_m, current_a, distance_m,
        e_field_vpm, e_field_dbuvm,
        electrically_short (bool — True if L < λ/4)
    """
    err = _validate_positive(freq_hz, "freq_hz")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(cable_length_m, "cable_length_m")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(current_a, "current_a")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(distance_m, "distance_m")
    if err:
        return {"ok": False, "reason": err}

    wavelength = _C / freq_hz
    electrically_short = cable_length_m < wavelength / 4.0

    if not electrically_short:
        warnings.warn(
            f"radiated_emission_common_mode: cable length {cable_length_m:.3f} m "
            f"exceeds λ/4 = {wavelength/4:.3f} m at {freq_hz/1e6:.1f} MHz.  "
            f"Short-antenna approximation may underestimate.",
            stacklevel=2,
        )

    # Ott §6.3 / Paul §10.5: E = μ₀ × f × I × L / r  (= 4π×10⁻⁷ × f × I × L / r)
    e_vpm = (_MU0 * freq_hz * current_a * cable_length_m) / distance_m
    e_dbuvm = _vpm_to_dbuvm(e_vpm)

    return {
        "ok": True,
        "freq_hz": freq_hz,
        "cable_length_m": cable_length_m,
        "current_a": current_a,
        "distance_m": distance_m,
        "e_field_vpm": e_vpm,
        "e_field_dbuvm": round(e_dbuvm, 2),
        "electrically_short": electrically_short,
        "formula": "Ott (2009) §6.3: E = μ₀ × f × I_cm × L / r",
    }


# ── Emission margin vs limit lines ────────────────────────────────────────────


def emission_margin_db(
    e_field_dbuvm: float,
    freq_hz: float,
    standard: str = "cispr",
    class_: str = "B",
    distance_m: float = 10.0,
) -> dict:
    """
    Compute the margin (dB) between a measured/estimated E-field and a
    regulatory limit line.  Positive margin = below limit (pass); negative = fail.

    Issues a warnings.warn for any exceedance.

    Parameters
    ----------
    e_field_dbuvm : float — estimated E-field [dBμV/m] at distance_m
    freq_hz       : float — frequency [Hz]
    standard      : str   — 'fcc' or 'cispr' (default 'cispr')
    class_        : str   — 'A' or 'B' (default 'B')
    distance_m    : float — measurement distance [m] (default 10.0 m)

    Returns
    -------
    dict with keys: ok, margin_db, passes, limit_dbuvm, e_field_dbuvm,
                    freq_hz, standard, class_, distance_m
    """
    err = _validate_positive(freq_hz, "freq_hz")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(distance_m, "distance_m")
    if err:
        return {"ok": False, "reason": err}
    if not isinstance(e_field_dbuvm, (int, float)) or math.isnan(e_field_dbuvm):
        return {"ok": False, "reason": "e_field_dbuvm must be a real number"}

    standard = str(standard).lower().strip()
    if standard not in ("fcc", "cispr"):
        return {"ok": False, "reason": "standard must be 'fcc' or 'cispr'"}

    if standard == "fcc":
        lim_result = fcc_limit_dbuvm(freq_hz, class_=class_, distance_m=distance_m)
    else:
        lim_result = cispr_limit_dbuvm(freq_hz, class_=class_, distance_m=distance_m)

    if not lim_result["ok"]:
        return {"ok": False, "reason": lim_result["reason"]}

    limit = lim_result["limit_dbuvm"]
    margin = limit - e_field_dbuvm
    passes = margin >= 0.0

    if not passes:
        warnings.warn(
            f"EMC EXCEEDANCE: {standard.upper()} Class {class_} limit exceeded by "
            f"{-margin:.1f} dB at {freq_hz/1e6:.1f} MHz "
            f"(emission={e_field_dbuvm:.1f} dBμV/m, limit={limit:.1f} dBμV/m, "
            f"distance={distance_m} m)",
            stacklevel=2,
        )

    return {
        "ok": True,
        "freq_hz": freq_hz,
        "standard": standard.upper(),
        "class_": class_.upper(),
        "distance_m": distance_m,
        "e_field_dbuvm": round(e_field_dbuvm, 2),
        "limit_dbuvm": round(limit, 2),
        "margin_db": round(margin, 2),
        "passes": passes,
    }


# ── Near-field crosstalk (capacitive + inductive) ────────────────────────────


def near_field_crosstalk(
    freq_hz: float,
    trace_width_mm: float,
    trace_spacing_mm: float,
    trace_height_mm: float,
    parallel_length_mm: float,
    er: float = 4.5,
) -> dict:
    """
    First-order capacitive + inductive coupling coefficient between two parallel
    PCB traces.

    Model (Paul "Introduction to EMC", 2006, §6.3 first-order proximity):

        Capacitive coupling:
            Kc ≈ 1 / (1 + (dist / w)²)
            where dist = centre-to-centre spacing = trace_width + trace_spacing,
                  w = trace_width.

        Inductive coupling:
            Kl ≈ 1 / (1 + (2 * dist / h)²)
            where h = trace height above ground plane.

        Combined (worst case):
            K_combined = sqrt(Kc² + Kl²)

        Length correction:
            K_effective = K_combined * tanh(parallel_length_mm / (100 * h))
            This saturates for long coupled sections, consistent with the
            coupled-line saturation behaviour in IPC-2141A §5.

    Parameters
    ----------
    freq_hz            : float — frequency [Hz] (for far-end phase check)
    trace_width_mm     : float — trace width [mm]
    trace_spacing_mm   : float — edge-to-edge spacing between traces [mm]
    trace_height_mm    : float — trace height above nearest ground plane [mm]
    parallel_length_mm : float — parallel run length [mm]
    er                 : float — relative permittivity (default 4.5 for FR4)

    Returns
    -------
    dict with keys:
        ok, Kc, Kl, K_combined, K_effective,
        freq_hz, trace_width_mm, trace_spacing_mm, trace_height_mm,
        parallel_length_mm, er
    """
    err = _validate_positive(freq_hz, "freq_hz")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(trace_width_mm, "trace_width_mm")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(trace_spacing_mm, "trace_spacing_mm")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(trace_height_mm, "trace_height_mm")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(parallel_length_mm, "parallel_length_mm")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(er, "er")
    if err:
        return {"ok": False, "reason": err}

    w = trace_width_mm
    s = trace_spacing_mm
    h = trace_height_mm
    L = parallel_length_mm

    # Centre-to-centre distance
    dist = w + s

    # Capacitive coupling (proximity, normalised)
    Kc = 1.0 / (1.0 + (dist / w) ** 2)

    # Inductive coupling (proximity, normalised)
    Kl = 1.0 / (1.0 + (2.0 * dist / h) ** 2)

    K_combined = math.sqrt(Kc ** 2 + Kl ** 2)

    # Length saturation factor using tanh (saturates toward 1 for long runs)
    saturation_arg = L / (100.0 * h)
    K_effective = K_combined * math.tanh(saturation_arg)

    return {
        "ok": True,
        "freq_hz": freq_hz,
        "trace_width_mm": w,
        "trace_spacing_mm": s,
        "trace_height_mm": h,
        "parallel_length_mm": L,
        "er": er,
        "Kc": round(Kc, 6),
        "Kl": round(Kl, 6),
        "K_combined": round(K_combined, 6),
        "K_effective": round(K_effective, 6),
        "note": (
            "First-order proximity model.  For accurate coupling use a full-wave "
            "field solver.  Consistent with IPC-2141A §5 qualitative bounds."
        ),
    }


# ── Shielding effectiveness ────────────────────────────────────────────────────


def shielding_effectiveness(
    freq_hz: float,
    thickness_m: float,
    conductivity_relative: float = 1.0,
    permeability_relative: float = 1.0,
    aperture_length_m: float = 0.0,
) -> dict:
    """
    Shielding effectiveness of a conductive enclosure (Schelkunoff theory).

    Computes absorption (SEa), reflection (SEr), and combined (SEtotal = SEa + SEr).
    When aperture_length_m > 0, the aperture leakage limit is also computed and
    the effective SE is min(SEtotal, SE_aperture).

    Formulas
    --------
    SEa [dB] = 131.4 × t × sqrt(f × μr × σr)      [Ott §5.3]
    SEr [dB] = 168 + 10×log10(σr / (μr × f))       [Ott §5.3, plane wave far field]
    SE_multiple ≈ -20×log10(1 − 10^(−SEa/10))      [negligible when SEa > 10 dB]
    SE_aperture [dB] = 20×log10(c / (2 × f × L_slot))  [single slot, Ott §5.4]

    Parameters
    ----------
    freq_hz               : float — frequency [Hz]
    thickness_m           : float — wall thickness [m]
    conductivity_relative : float — relative conductivity σr (copper=1.0, Al≈0.61)
    permeability_relative : float — relative permeability μr (steel≈1000)
    aperture_length_m     : float — longest aperture/slot dimension [m] (0 = no aperture)

    Returns
    -------
    dict with keys:
        ok, freq_hz, thickness_m, conductivity_relative, permeability_relative,
        se_absorption_db, se_reflection_db, se_multiple_db,
        se_total_db, se_aperture_db (None if no aperture),
        se_effective_db, aperture_limited (bool)
    """
    err = _validate_positive(freq_hz, "freq_hz")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(thickness_m, "thickness_m")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(conductivity_relative, "conductivity_relative")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(permeability_relative, "permeability_relative")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_nonneg(aperture_length_m, "aperture_length_m")
    if err:
        return {"ok": False, "reason": err}

    f = freq_hz
    t = thickness_m
    sigma_r = conductivity_relative
    mu_r = permeability_relative

    # Absorption loss
    se_a = 131.4 * t * math.sqrt(f * mu_r * sigma_r)

    # Reflection loss (plane wave far field)
    # Guard against log of zero
    if mu_r * f > 0:
        se_r = 168.0 + 10.0 * math.log10(sigma_r / (mu_r * f))
    else:
        se_r = 0.0

    # Multiple-reflection correction (only significant when SEa < 10 dB)
    if se_a >= 10.0:
        se_m = 0.0
    else:
        arg = 1.0 - 10.0 ** (-se_a / 10.0)
        if arg > 0:
            se_m = -20.0 * math.log10(arg)
        else:
            se_m = 0.0

    se_total = se_a + se_r - se_m

    # Aperture leakage
    se_aperture = None
    if aperture_length_m > 0.0:
        denom = 2.0 * f * aperture_length_m
        if denom > 0:
            se_aperture = 20.0 * math.log10(_C / denom)
        else:
            se_aperture = 0.0

    aperture_limited = False
    if se_aperture is not None:
        aperture_limited = se_aperture < se_total
        se_effective = min(se_total, se_aperture)
    else:
        se_effective = se_total

    return {
        "ok": True,
        "freq_hz": freq_hz,
        "thickness_m": thickness_m,
        "conductivity_relative": conductivity_relative,
        "permeability_relative": permeability_relative,
        "se_absorption_db": round(se_a, 2),
        "se_reflection_db": round(se_r, 2),
        "se_multiple_db": round(se_m, 2),
        "se_total_db": round(se_total, 2),
        "se_aperture_db": round(se_aperture, 2) if se_aperture is not None else None,
        "se_effective_db": round(se_effective, 2),
        "aperture_limited": aperture_limited,
        "formula": "Schelkunoff / Ott (2009) §5.3-5.4",
    }
