"""
kerf_cad_core.fasteners.joint — bolted-joint analysis (VDI 2230 / Shigley style).

Public functions
----------------
  preload_from_torque(T, d, K)
      Clamp preload from tightening torque.  T = K · F · d  →  F = T / (K · d)

  bolt_stiffness(d_shank, length_shank, d_thread_minor, length_thread, E_bolt)
      Bolt axial stiffness: springs-in-series (shank region + threaded region).
      Uses minor (stress-area) diameter for threaded segment.

  clamped_stiffness(grip_length, E_clamp, d_bolt, *, half_angle_deg, n_frustums)
      Clamped-member stiffness via the conical-frustum (VDI 2230) method.
      Frustum half-angle α = 30° (default, per VDI recommendation).

  joint_load_factor(k_bolt, k_clamp)
      Load factor Φ = k_bolt / (k_bolt + k_clamp).
      Fraction of the external working load carried by the bolt.

  bolt_working_stress(F_preload, F_external, Phi, A_stress, *, Kb, torque_Nm, d_m)
      Total bolt tensile stress from preload + Φ-fraction of working load,
      plus torsional stress from residual wrench torque (if supplied).

  separation_safety(F_preload, F_external, Phi)
      Joint separation safety factor  n_sep = F_preload / (F_external · (1 − Φ)).
      Warns when n_sep < 1 (joint opens).

  slip_safety(F_preload, F_shear, mu, n_bolts)
      Friction-grip slip safety factor  n_slip = mu · F_preload · n_bolts / F_shear.
      Warns when n_slip < 1.25 (common structural minimum).

  fatigue_check(sigma_a, Se, sigma_m, Sut, *, Kf)
      Modified-Goodman fatigue check for the bolt:
          sigma_a / (Se / Kf) + sigma_m / Sut ≤ 1
      Returns Goodman ratio and pass/fail.

  strip_length(F_preload, F_external, Phi, d_nom, thread_pitch,
               Ssy_bolt, Ssy_nut, *, safety_factor)
      Minimum thread-engagement length to prevent stripping (bolt and nut/tapped-hole).
      Uses shear-area approach (Shigley §8-7).

ISO_THREAD : dict
      ISO metric thread geometry table keyed by nominal diameter (mm):
      M1.6 … M64. Each entry: {pitch_mm, d_minor_mm, d_pitch_mm, stress_area_mm2}.

Units
-----
  lengths  — metres (m)     (thread table entries in mm — clearly labelled)
  forces   — Newtons (N)
  torque   — Newton-metres (N·m)
  stress   — Pascals (Pa)
  moduli   — Pascals (Pa)

All functions return {"ok": True/False, ...}.  Never raise.

References
----------
VDI 2230-1:2015 — Systematic calculation of highly stressed bolted joints
Shigley's Mechanical Engineering Design, 10th ed., §§ 8-1 to 8-9
ISO 68-1:1998   — ISO general-purpose metric screw threads (M-series)

Author: imranparuk
"""

from __future__ import annotations

import math
import warnings as _warnings_mod
from typing import Any


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _guard_positive(name: str, value: Any) -> str | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {value!r}"
    if not math.isfinite(v):
        return f"{name} must be finite, got {v}"
    if v <= 0:
        return f"{name} must be > 0, got {v}"
    return None


def _guard_nonneg(name: str, value: Any) -> str | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {value!r}"
    if not math.isfinite(v):
        return f"{name} must be finite, got {v}"
    if v < 0:
        return f"{name} must be >= 0, got {v}"
    return None


def _err(reason: str) -> dict:
    return {"ok": False, "reason": reason}


# ---------------------------------------------------------------------------
# ISO metric thread geometry table
# Source: ISO 68-1, ISO 724, and Shigley Table 8-1 (10th ed.)
# Keys: nominal_diameter_mm (int or float where needed)
# Values: pitch_mm, minor_diameter_mm (d_minor), pitch_diameter_mm (d_pitch),
#         stress_area_mm2 (At) — tensile stress area per ISO 898
#
# stress_area formula:  At = π/4 × ((d_pitch + d_minor)/2)²  ← ISO 898-1 Annex B
# For consistency the table uses published At values from Shigley Table 8-1.
# ---------------------------------------------------------------------------

ISO_THREAD: dict[float, dict] = {
    1.6:  {"pitch_mm": 0.35,  "d_minor_mm": 1.171,  "d_pitch_mm": 1.373,  "stress_area_mm2": 1.27},
    2.0:  {"pitch_mm": 0.40,  "d_minor_mm": 1.509,  "d_pitch_mm": 1.740,  "stress_area_mm2": 2.07},
    2.5:  {"pitch_mm": 0.45,  "d_minor_mm": 1.948,  "d_pitch_mm": 2.208,  "stress_area_mm2": 3.39},
    3.0:  {"pitch_mm": 0.50,  "d_minor_mm": 2.387,  "d_pitch_mm": 2.675,  "stress_area_mm2": 5.03},
    4.0:  {"pitch_mm": 0.70,  "d_minor_mm": 3.141,  "d_pitch_mm": 3.545,  "stress_area_mm2": 8.78},
    5.0:  {"pitch_mm": 0.80,  "d_minor_mm": 4.019,  "d_pitch_mm": 4.480,  "stress_area_mm2": 14.2},
    6.0:  {"pitch_mm": 1.00,  "d_minor_mm": 4.773,  "d_pitch_mm": 5.350,  "stress_area_mm2": 20.1},
    8.0:  {"pitch_mm": 1.25,  "d_minor_mm": 6.466,  "d_pitch_mm": 7.188,  "stress_area_mm2": 36.6},
    10.0: {"pitch_mm": 1.50,  "d_minor_mm": 8.160,  "d_pitch_mm": 9.026,  "stress_area_mm2": 58.0},
    12.0: {"pitch_mm": 1.75,  "d_minor_mm": 9.853,  "d_pitch_mm": 10.863, "stress_area_mm2": 84.3},
    14.0: {"pitch_mm": 2.00,  "d_minor_mm": 11.546, "d_pitch_mm": 12.701, "stress_area_mm2": 115.0},
    16.0: {"pitch_mm": 2.00,  "d_minor_mm": 13.546, "d_pitch_mm": 14.701, "stress_area_mm2": 157.0},
    18.0: {"pitch_mm": 2.50,  "d_minor_mm": 14.933, "d_pitch_mm": 16.376, "stress_area_mm2": 192.0},
    20.0: {"pitch_mm": 2.50,  "d_minor_mm": 16.933, "d_pitch_mm": 18.376, "stress_area_mm2": 245.0},
    22.0: {"pitch_mm": 2.50,  "d_minor_mm": 18.933, "d_pitch_mm": 20.376, "stress_area_mm2": 303.0},
    24.0: {"pitch_mm": 3.00,  "d_minor_mm": 20.320, "d_pitch_mm": 22.051, "stress_area_mm2": 353.0},
    27.0: {"pitch_mm": 3.00,  "d_minor_mm": 23.320, "d_pitch_mm": 25.051, "stress_area_mm2": 459.0},
    30.0: {"pitch_mm": 3.50,  "d_minor_mm": 25.706, "d_pitch_mm": 27.727, "stress_area_mm2": 561.0},
    33.0: {"pitch_mm": 3.50,  "d_minor_mm": 28.706, "d_pitch_mm": 30.727, "stress_area_mm2": 694.0},
    36.0: {"pitch_mm": 4.00,  "d_minor_mm": 31.093, "d_pitch_mm": 33.402, "stress_area_mm2": 817.0},
    39.0: {"pitch_mm": 4.00,  "d_minor_mm": 34.093, "d_pitch_mm": 36.402, "stress_area_mm2": 976.0},
    42.0: {"pitch_mm": 4.50,  "d_minor_mm": 36.479, "d_pitch_mm": 39.077, "stress_area_mm2": 1120.0},
    45.0: {"pitch_mm": 4.50,  "d_minor_mm": 39.479, "d_pitch_mm": 42.077, "stress_area_mm2": 1300.0},
    48.0: {"pitch_mm": 5.00,  "d_minor_mm": 41.866, "d_pitch_mm": 44.752, "stress_area_mm2": 1470.0},
    52.0: {"pitch_mm": 5.00,  "d_minor_mm": 45.866, "d_pitch_mm": 48.752, "stress_area_mm2": 1760.0},
    56.0: {"pitch_mm": 5.50,  "d_minor_mm": 49.252, "d_pitch_mm": 53.402, "stress_area_mm2": 2030.0},
    60.0: {"pitch_mm": 5.50,  "d_minor_mm": 53.252, "d_pitch_mm": 57.402, "stress_area_mm2": 2360.0},
    64.0: {"pitch_mm": 6.00,  "d_minor_mm": 56.639, "d_pitch_mm": 61.052, "stress_area_mm2": 2680.0},
}


def lookup_thread(d_nom_mm: float) -> dict | None:
    """Return thread data for nearest nominal diameter, or None if not found."""
    key = float(d_nom_mm)
    if key in ISO_THREAD:
        return ISO_THREAD[key]
    # nearest match within 0.1 mm
    best = min(ISO_THREAD.keys(), key=lambda k: abs(k - key))
    if abs(best - key) <= 0.2:
        return ISO_THREAD[best]
    return None


# ---------------------------------------------------------------------------
# 1. preload_from_torque
# ---------------------------------------------------------------------------

def preload_from_torque(
    T: float,
    d: float,
    K: float = 0.20,
) -> dict:
    """
    Clamp preload force from tightening torque.

    Parameters
    ----------
    T : float
        Tightening torque (N·m).  Must be > 0.
    d : float
        Nominal bolt diameter (m).  Must be > 0.
    K : float
        Nut factor / torque coefficient (dimensionless).  Default 0.20
        (dry-contact steel).  Typical range: 0.10 (lubricated) to 0.25 (rough).

    Returns
    -------
    dict
        ok          : True
        F_preload_N : clamp preload force (N)
        T_Nm        : tightening torque used (N·m)
        d_m         : bolt diameter used (m)
        K           : nut factor used
        warnings    : []

    Formula
    -------
    T = K · F · d  →  F = T / (K · d)

    References
    ----------
    Shigley §8-8; VDI 2230 §5.4.2
    """
    err = _guard_positive("T", T)
    if err:
        return _err(err)
    err = _guard_positive("d", d)
    if err:
        return _err(err)
    err = _guard_positive("K", K)
    if err:
        return _err(err)

    T = float(T)
    d = float(d)
    K = float(K)

    warnings: list[str] = []

    if K < 0.10 or K > 0.35:
        warnings.append(
            f"Nut factor K={K:.3f} is outside typical range [0.10, 0.35]; "
            "verify lubrication condition."
        )

    F = T / (K * d)

    return {
        "ok": True,
        "F_preload_N": F,
        "T_Nm": T,
        "d_m": d,
        "K": K,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 2. bolt_stiffness
# ---------------------------------------------------------------------------

def bolt_stiffness(
    d_shank: float,
    length_shank: float,
    d_thread_minor: float,
    length_thread: float,
    E_bolt: float = 200e9,
) -> dict:
    """
    Axial bolt stiffness: shank + threaded segment in series.

    Models the bolt as two concentric cylinders in series:
      - Unthreaded shank: diameter d_shank, length length_shank
      - Threaded section: effective diameter d_thread_minor (minor/stress-area diam.),
        length length_thread

    Parameters
    ----------
    d_shank : float
        Shank (unthreaded) diameter (m).  Must be > 0.
    length_shank : float
        Length of unthreaded shank within grip (m).  Must be >= 0.
        Pass 0 if fully threaded bolt.
    d_thread_minor : float
        Minor / stress-area diameter of threaded section (m).  Must be > 0.
        For ISO metric: d_minor from ISO_THREAD table.
    length_thread : float
        Length of threaded section within grip (m).  Must be > 0.
    E_bolt : float
        Young's modulus of bolt material (Pa).  Default 200e9 (steel).

    Returns
    -------
    dict
        ok          : True
        k_bolt_N_per_m : bolt axial stiffness (N/m)
        k_shank     : shank stiffness component (N/m)   (inf if length_shank=0)
        k_thread    : thread stiffness component (N/m)
        A_shank_m2  : shank cross-section area (m²)
        A_thread_m2 : thread stress-section area (m²)
        E_Pa        : Young's modulus used (Pa)
        warnings    : []

    Formula
    -------
    k_i = E · A_i / L_i
    1/k_bolt = 1/k_shank + 1/k_thread  (series springs)

    References
    ----------
    Shigley §8-3; VDI 2230 §5.3
    """
    err = _guard_positive("d_shank", d_shank)
    if err:
        return _err(err)
    err = _guard_nonneg("length_shank", length_shank)
    if err:
        return _err(err)
    err = _guard_positive("d_thread_minor", d_thread_minor)
    if err:
        return _err(err)
    err = _guard_positive("length_thread", length_thread)
    if err:
        return _err(err)
    err = _guard_positive("E_bolt", E_bolt)
    if err:
        return _err(err)

    d_s = float(d_shank)
    L_s = float(length_shank)
    d_t = float(d_thread_minor)
    L_t = float(length_thread)
    E = float(E_bolt)

    warnings: list[str] = []

    A_s = math.pi / 4.0 * d_s ** 2
    A_t = math.pi / 4.0 * d_t ** 2

    k_t = E * A_t / L_t

    if L_s > 0:
        k_s = E * A_s / L_s
        k_bolt = 1.0 / (1.0 / k_s + 1.0 / k_t)
    else:
        # Fully threaded — shank term drops out
        k_s = float("inf")
        k_bolt = k_t
        warnings.append("length_shank=0: fully threaded bolt (no unthreaded shank segment).")

    if d_t > d_s:
        warnings.append(
            f"d_thread_minor ({d_t*1e3:.2f} mm) > d_shank ({d_s*1e3:.2f} mm); "
            "check diameters — minor should be < nominal shank diameter."
        )

    return {
        "ok": True,
        "k_bolt_N_per_m": k_bolt,
        "k_shank": k_s,
        "k_thread": k_t,
        "A_shank_m2": A_s,
        "A_thread_m2": A_t,
        "E_Pa": E,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 3. clamped_stiffness (frustum method)
# ---------------------------------------------------------------------------

def clamped_stiffness(
    grip_length: float,
    E_clamp: float,
    d_bolt: float,
    *,
    half_angle_deg: float = 30.0,
    n_frustums: int = 2,
) -> dict:
    """
    Clamped-member stiffness via conical-frustum model (VDI 2230).

    The frustum model treats the compressed zone beneath the bolt head (and nut)
    as a pair of back-to-back truncated cones.  Each cone has a half-angle α
    (default 30° per VDI 2230 Sect. 3.3).

    Parameters
    ----------
    grip_length : float
        Total clamped-member grip length l_K (m).  Must be > 0.
    E_clamp : float
        Effective Young's modulus of clamped members (Pa).  Must be > 0.
        For a stack of different materials use 1/E_eff = Σ(L_i / (E_i L_total)).
    d_bolt : float
        Nominal bolt diameter (m).  Must be > 0.
        The frustum outer diameter at mid-grip is d_bolt + 2·(l_K/2)·tan(α).
    half_angle_deg : float
        Frustum half-angle α (degrees).  Default 30° (VDI 2230).
    n_frustums : int
        Number of frustum pairs (default 2 for through-bolt with head + nut).

    Returns
    -------
    dict
        ok               : True
        k_clamp_N_per_m  : clamped-member axial stiffness (N/m)
        grip_length_m    : grip length used (m)
        E_Pa             : Young's modulus used (Pa)
        d_bolt_m         : bolt diameter used (m)
        half_angle_deg   : frustum half-angle used (degrees)
        d_w_m            : washer-face outer diameter = 1.5 × d_bolt (m)
        warnings         : []

    Formula (VDI 2230 eq. A.7 / Shigley eq. 8-23)
    ------
    For a single frustum cone (half of the grip):

        k_cone = π E d_bolt tan(α) /
                 ln[ (2t·tan(α) + d_w − d_bolt)(d_w + d_bolt) /
                     ((2t·tan(α) + d_w + d_bolt)(d_w − d_bolt)) ]

    where:
        t     = grip_length / 2  (half-grip for one frustum)
        d_w   = bearing face/washer diameter = 1.5 × d_bolt  (VDI default)
        α     = half_angle_deg

    Two back-to-back frustums in series → k_clamp = k_cone / 2.

    References
    ----------
    VDI 2230-1:2015, Annex A (frustum stiffness)
    Shigley 10th ed., §8-3, eq. 8-23
    """
    err = _guard_positive("grip_length", grip_length)
    if err:
        return _err(err)
    err = _guard_positive("E_clamp", E_clamp)
    if err:
        return _err(err)
    err = _guard_positive("d_bolt", d_bolt)
    if err:
        return _err(err)

    try:
        alpha_deg = float(half_angle_deg)
    except (TypeError, ValueError):
        return _err(f"half_angle_deg must be a number, got {half_angle_deg!r}")
    if not (5.0 <= alpha_deg <= 75.0):
        return _err(f"half_angle_deg must be in [5, 75], got {alpha_deg}")

    warnings: list[str] = []

    L = float(grip_length)
    E = float(E_clamp)
    d = float(d_bolt)
    alpha_rad = math.radians(alpha_deg)
    tan_a = math.tan(alpha_rad)

    # Washer-face (bearing face) diameter — VDI default: d_w = 1.5 d_bolt
    d_w = 1.5 * d

    # Half-grip for one frustum cone
    t = L / 2.0

    # Shigley eq. 8-23 / VDI frustum stiffness for ONE cone:
    #   numerator   = (2t tan α + d_w − d)(d_w + d)
    #   denominator = (2t tan α + d_w + d)(d_w − d)
    A_num = (2.0 * t * tan_a + d_w - d) * (d_w + d)
    A_den = (2.0 * t * tan_a + d_w + d) * (d_w - d)

    if A_den <= 0 or A_num <= 0:
        warnings.append(
            "Frustum geometry degenerate (d_w <= d_bolt or extreme tan α); "
            "result may be unreliable."
        )
        # Fallback: simple cylinder
        A_cyl = math.pi / 4.0 * ((d_w ** 2) - d ** 2) if d_w > d else math.pi / 4.0 * d_w ** 2
        k_cone = E * A_cyl / t if t > 0 else float("inf")
    else:
        log_ratio = math.log(A_num / A_den)
        if abs(log_ratio) < 1e-15:
            return _err("Frustum stiffness denominator is zero (geometry invalid).")
        k_cone = math.pi * E * d * tan_a / log_ratio

    # Two back-to-back frustums in series: 1/k_clamp = 2 / k_cone
    k_clamp = k_cone / n_frustums

    if k_clamp <= 0:
        warnings.append("Computed k_clamp <= 0; check geometry inputs.")

    return {
        "ok": True,
        "k_clamp_N_per_m": k_clamp,
        "grip_length_m": L,
        "E_Pa": E,
        "d_bolt_m": d,
        "half_angle_deg": alpha_deg,
        "d_w_m": d_w,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 4. joint_load_factor
# ---------------------------------------------------------------------------

def joint_load_factor(
    k_bolt: float,
    k_clamp: float,
) -> dict:
    """
    Joint load factor Φ (phi).

    Φ is the fraction of an external separating load that is borne by the bolt;
    (1 − Φ) is the fraction relieving the clamp preload.

    Parameters
    ----------
    k_bolt : float
        Bolt axial stiffness (N/m).  Must be > 0.
    k_clamp : float
        Clamped-member stiffness (N/m).  Must be > 0.

    Returns
    -------
    dict
        ok       : True
        Phi      : joint load factor (dimensionless, 0 < Φ < 1)
        k_bolt   : bolt stiffness used (N/m)
        k_clamp  : clamped-member stiffness used (N/m)
        stiffness_ratio : k_clamp / k_bolt
        warnings : []

    Formula
    -------
    Φ = k_bolt / (k_bolt + k_clamp)

    Typical values: Φ ≈ 0.05–0.25 for joints in compression (stiff members),
    Φ ≈ 0.4–0.8 for gaskets or soft clamped material.

    References
    ----------
    Shigley §8-5; VDI 2230 §5.3.2
    """
    err = _guard_positive("k_bolt", k_bolt)
    if err:
        return _err(err)
    err = _guard_positive("k_clamp", k_clamp)
    if err:
        return _err(err)

    k_b = float(k_bolt)
    k_c = float(k_clamp)

    Phi = k_b / (k_b + k_c)
    ratio = k_c / k_b

    warnings: list[str] = []
    if Phi > 0.5:
        warnings.append(
            f"Phi={Phi:.3f} > 0.5: bolt carries >50% of external load; "
            "joint compliance is high (gasket or thin clamped members)."
        )

    return {
        "ok": True,
        "Phi": Phi,
        "k_bolt": k_b,
        "k_clamp": k_c,
        "stiffness_ratio": ratio,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 5. bolt_working_stress
# ---------------------------------------------------------------------------

def bolt_working_stress(
    F_preload: float,
    F_external: float,
    Phi: float,
    A_stress: float,
    *,
    Kb: float = 1.0,
    torque_Nm: float = 0.0,
    d_m: float = 0.0,
) -> dict:
    """
    Total bolt tensile (and combined) stress under working load.

    Parameters
    ----------
    F_preload : float
        Assembly preload (N).  Must be > 0.
    F_external : float
        External separating load per bolt (N).  Must be >= 0.
    Phi : float
        Joint load factor (0 < Φ ≤ 1).  Must be in (0, 1].
    A_stress : float
        Bolt tensile stress area (m²).  Must be > 0.
        Use the ISO stress area from ISO_THREAD (convert mm² → m²).
    Kb : float
        Optional bending stress concentration factor for threads (default 1.0).
    torque_Nm : float
        Residual wrench torque on bolt body (N·m).  If > 0 and d_m > 0,
        torsional stress is also computed.
    d_m : float
        Mean (pitch) diameter of bolt thread (m).  Required if torque_Nm > 0.

    Returns
    -------
    dict
        ok                  : True
        sigma_total_Pa      : total tensile stress (preload + working load) (Pa)
        sigma_preload_Pa    : tensile stress from preload alone (Pa)
        sigma_working_Pa    : additional tensile stress from working load (Pa)
        F_bolt_total_N      : total bolt force = F_preload + Phi * F_external (N)
        tau_torsion_Pa      : torsional stress from residual torque (Pa) — 0 if not given
        sigma_von_mises_Pa  : Von Mises equivalent (tensile + torsion) (Pa)
        A_stress_m2         : stress area used (m²)
        Phi                 : load factor used
        warnings            : []

    Formula
    -------
    F_bolt = F_preload + Φ · F_external
    σ_total = Kb · F_bolt / A_stress

    Torsion from residual torque (if provided):
        τ = 16 T_resid / (π d_m³)  [on mean pitch cylinder]
    σ_VM = √(σ² + 3τ²)

    References
    ----------
    Shigley §8-5, 8-7; VDI 2230 §5.5
    """
    err = _guard_positive("F_preload", F_preload)
    if err:
        return _err(err)
    err = _guard_nonneg("F_external", F_external)
    if err:
        return _err(err)
    err = _guard_positive("A_stress", A_stress)
    if err:
        return _err(err)
    err = _guard_positive("Kb", Kb)
    if err:
        return _err(err)

    try:
        Phi_f = float(Phi)
    except (TypeError, ValueError):
        return _err(f"Phi must be a number, got {Phi!r}")
    if not (0.0 < Phi_f <= 1.0):
        return _err(f"Phi must be in (0, 1], got {Phi_f}")

    F_p = float(F_preload)
    F_e = float(F_external)
    A = float(A_stress)
    Kb_f = float(Kb)

    warnings: list[str] = []

    sigma_pre = F_p / A
    F_bolt = F_p + Phi_f * F_e
    sigma_total = Kb_f * F_bolt / A
    sigma_working = Kb_f * Phi_f * F_e / A

    tau = 0.0
    if float(torque_Nm) > 0 and float(d_m) > 0:
        T_r = float(torque_Nm)
        dm = float(d_m)
        # τ = 16 T / (π d³)  — torsion on mean diameter cylinder
        tau = 16.0 * T_r / (math.pi * dm ** 3)

    sigma_vm = math.sqrt(sigma_total ** 2 + 3.0 * tau ** 2)

    return {
        "ok": True,
        "sigma_total_Pa": sigma_total,
        "sigma_preload_Pa": sigma_pre,
        "sigma_working_Pa": sigma_working,
        "F_bolt_total_N": F_bolt,
        "tau_torsion_Pa": tau,
        "sigma_von_mises_Pa": sigma_vm,
        "A_stress_m2": A,
        "Phi": Phi_f,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 6. separation_safety
# ---------------------------------------------------------------------------

def separation_safety(
    F_preload: float,
    F_external: float,
    Phi: float,
) -> dict:
    """
    Joint separation (opening) safety factor.

    The joint separates when the external load completely unloads the clamp.
    The safety factor is:

        n_sep = F_preload / [F_external · (1 − Φ)]

    Parameters
    ----------
    F_preload : float
        Assembly preload (N).  Must be > 0.
    F_external : float
        External separating load per bolt (N).  Must be > 0.
    Phi : float
        Joint load factor (0 < Φ < 1).

    Returns
    -------
    dict
        ok             : True
        n_sep          : separation safety factor
        separated      : True if n_sep < 1 (joint opens — warns)
        F_preload_N    : preload used (N)
        F_external_N   : external load used (N)
        Phi            : load factor used
        warnings       : list (non-empty if n_sep < 1 or < 1.2)

    References
    ----------
    Shigley §8-6; VDI 2230 §5.5.3
    """
    err = _guard_positive("F_preload", F_preload)
    if err:
        return _err(err)
    err = _guard_positive("F_external", F_external)
    if err:
        return _err(err)

    try:
        Phi_f = float(Phi)
    except (TypeError, ValueError):
        return _err(f"Phi must be a number, got {Phi!r}")
    if not (0.0 <= Phi_f < 1.0):
        return _err(f"Phi must be in [0, 1), got {Phi_f}")

    F_p = float(F_preload)
    F_e = float(F_external)

    warnings: list[str] = []

    clamp_relief = F_e * (1.0 - Phi_f)
    n_sep = F_p / clamp_relief if clamp_relief > 0 else float("inf")

    separated = n_sep < 1.0
    if separated:
        warnings.append(
            f"SEPARATION FAILURE: n_sep={n_sep:.3f} < 1.0 — joint opens under load. "
            "Increase preload or reduce external force."
        )
        _warnings_mod.warn(
            f"fasteners.separation_safety: joint separates (n_sep={n_sep:.3f})",
            stacklevel=2,
        )
    elif n_sep < 1.2:
        warnings.append(
            f"n_sep={n_sep:.3f} < 1.2: marginal separation safety; "
            "consider higher preload."
        )

    return {
        "ok": True,
        "n_sep": n_sep,
        "separated": separated,
        "F_preload_N": F_p,
        "F_external_N": F_e,
        "Phi": Phi_f,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 7. slip_safety
# ---------------------------------------------------------------------------

def slip_safety(
    F_preload: float,
    F_shear: float,
    mu: float,
    n_bolts: int = 1,
) -> dict:
    """
    Friction-grip slip safety factor for a bolted joint in shear.

    Parameters
    ----------
    F_preload : float
        Assembly preload per bolt (N).  Must be > 0.
    F_shear : float
        Total applied shear force on the joint (N).  Must be > 0.
    mu : float
        Coefficient of friction between faying surfaces.  Must be > 0.
        Typical: 0.35 (steel on steel, clean); 0.50 (slip-critical, shot-blasted).
    n_bolts : int
        Number of bolts in the joint.  Must be >= 1.

    Returns
    -------
    dict
        ok             : True
        n_slip         : slip safety factor
        slips          : True if n_slip < 1 (joint slips — warns)
        F_friction_N   : total friction capacity (mu × F_preload × n_bolts) (N)
        F_shear_N      : applied shear used (N)
        mu             : friction coefficient used
        n_bolts        : number of bolts used
        warnings       : list

    Formula
    -------
    F_friction = μ · F_preload · n_bolts
    n_slip = F_friction / F_shear

    References
    ----------
    Shigley §8-9; AISC Design Guide (friction-critical joints)
    """
    err = _guard_positive("F_preload", F_preload)
    if err:
        return _err(err)
    err = _guard_positive("F_shear", F_shear)
    if err:
        return _err(err)
    err = _guard_positive("mu", mu)
    if err:
        return _err(err)

    try:
        n_b = int(n_bolts)
    except (TypeError, ValueError):
        return _err(f"n_bolts must be an integer, got {n_bolts!r}")
    if n_b < 1:
        return _err(f"n_bolts must be >= 1, got {n_b}")

    F_p = float(F_preload)
    F_s = float(F_shear)
    mu_f = float(mu)

    warnings: list[str] = []

    F_friction = mu_f * F_p * n_b
    n_slip = F_friction / F_s

    slips = n_slip < 1.0
    if slips:
        warnings.append(
            f"SLIP FAILURE: n_slip={n_slip:.3f} < 1.0 — joint slips under shear load. "
            "Increase preload, friction, or bolt count."
        )
        _warnings_mod.warn(
            f"fasteners.slip_safety: joint slips (n_slip={n_slip:.3f})",
            stacklevel=2,
        )
    elif n_slip < 1.25:
        warnings.append(
            f"n_slip={n_slip:.3f} < 1.25: below recommended structural minimum; "
            "consider increasing preload or mu."
        )

    return {
        "ok": True,
        "n_slip": n_slip,
        "slips": slips,
        "F_friction_N": F_friction,
        "F_shear_N": F_s,
        "mu": mu_f,
        "n_bolts": n_b,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 8. fatigue_check (modified Goodman for bolt)
# ---------------------------------------------------------------------------

def fatigue_check(
    sigma_a: float,
    Se: float,
    sigma_m: float,
    Sut: float,
    *,
    Kf: float = 1.0,
) -> dict:
    """
    Modified-Goodman fatigue check for a bolt.

    Parameters
    ----------
    sigma_a : float
        Alternating (amplitude) bolt stress (Pa).  Must be >= 0.
        σ_a = Φ · F_external / (2 · A_stress)  for pulsating external load.
    Se : float
        Bolt endurance limit (Pa).  Must be > 0.
    sigma_m : float
        Mean bolt stress (Pa).  Must be >= 0.
        σ_m = (F_preload + Φ · F_external / 2) / A_stress
    Sut : float
        Bolt ultimate tensile strength (Pa).  Must be > 0.
    Kf : float
        Fatigue stress concentration factor for thread root (default 1.0).
        Typical bolt thread: Kf ≈ 2.2–3.8 (depends on thread form and surface).

    Returns
    -------
    dict
        ok               : True
        goodman_ratio    : (Kf·σ_a/Se) + (σ_m/Sut)  — must be ≤ 1 for infinite life
        fatigue_ok       : True if goodman_ratio ≤ 1.0
        n_goodman        : Goodman safety factor = 1 / goodman_ratio
        sigma_a_Pa       : alternating stress used (Pa)
        sigma_m_Pa       : mean stress used (Pa)
        Se_Pa            : endurance limit used (Pa)
        Sut_Pa           : ultimate strength used (Pa)
        Kf               : stress concentration factor used
        warnings         : list

    Formula
    -------
    Goodman: Kf · σ_a / Se + σ_m / Sut = 1  (fatigue boundary)

    References
    ----------
    Shigley §8-7 (bolt fatigue); §6-14 (Goodman)
    """
    err = _guard_nonneg("sigma_a", sigma_a)
    if err:
        return _err(err)
    err = _guard_positive("Se", Se)
    if err:
        return _err(err)
    err = _guard_nonneg("sigma_m", sigma_m)
    if err:
        return _err(err)
    err = _guard_positive("Sut", Sut)
    if err:
        return _err(err)
    err = _guard_positive("Kf", Kf)
    if err:
        return _err(err)

    sa = float(sigma_a)
    Se_v = float(Se)
    sm = float(sigma_m)
    Sut_v = float(Sut)
    Kf_v = float(Kf)

    warnings: list[str] = []

    goodman_ratio = Kf_v * sa / Se_v + sm / Sut_v
    fatigue_ok = goodman_ratio <= 1.0
    n_goodman = 1.0 / goodman_ratio if goodman_ratio > 0 else float("inf")

    if not fatigue_ok:
        warnings.append(
            f"FATIGUE FAILURE: Goodman ratio={goodman_ratio:.4f} > 1.0 — "
            "bolt will fail in fatigue. Increase preload or reduce alternating load."
        )
        _warnings_mod.warn(
            f"fasteners.fatigue_check: fatigue failure (ratio={goodman_ratio:.4f})",
            stacklevel=2,
        )
    elif goodman_ratio > 0.8:
        warnings.append(
            f"Goodman ratio={goodman_ratio:.4f} > 0.8: limited fatigue margin."
        )

    return {
        "ok": True,
        "goodman_ratio": goodman_ratio,
        "fatigue_ok": fatigue_ok,
        "n_goodman": n_goodman,
        "sigma_a_Pa": sa,
        "sigma_m_Pa": sm,
        "Se_Pa": Se_v,
        "Sut_Pa": Sut_v,
        "Kf": Kf_v,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 9. strip_length (thread pull-out / stripping)
# ---------------------------------------------------------------------------

def strip_length(
    F_preload: float,
    F_external: float,
    Phi: float,
    d_nom: float,
    thread_pitch: float,
    Ssy_bolt: float,
    Ssy_nut: float,
    *,
    safety_factor: float = 2.0,
) -> dict:
    """
    Minimum thread engagement length to prevent thread stripping.

    Uses the shear-area approach: the stripping load for the bolt external thread
    equals the shear stress area (per engaged length) times the shear strength.
    The nut/tapped-hole internal thread is checked separately.

    Parameters
    ----------
    F_preload : float
        Assembly preload (N).  Must be > 0.
    F_external : float
        External working load (N).  Must be >= 0.
    Phi : float
        Joint load factor (0 < Φ ≤ 1).
    d_nom : float
        Nominal bolt diameter (m).  Must be > 0.
    thread_pitch : float
        Thread pitch (m).  Must be > 0.
        E.g., M16 pitch = 2.0 mm → 0.002 m.
    Ssy_bolt : float
        Shear yield strength of bolt (Pa).  Must be > 0.
        Typically ≈ 0.577 Sy for ductile material (von Mises).
    Ssy_nut : float
        Shear yield strength of nut / tapped material (Pa).  Must be > 0.
    safety_factor : float
        Safety factor on engagement length (default 2.0).

    Returns
    -------
    dict
        ok                     : True
        L_e_bolt_m             : min engagement length to avoid bolt stripping (m)
        L_e_nut_m              : min engagement length to avoid nut stripping (m)
        L_e_required_m         : max(L_e_bolt, L_e_nut) × safety_factor (m)
        F_total_N              : total bolt force = F_preload + Phi·F_external (N)
        shear_area_per_m_bolt  : bolt thread shear area per metre engagement (m²/m)
        shear_area_per_m_nut   : nut thread shear area per metre engagement (m²/m)
        warnings               : []

    Formula (Shigley §8-7)
    ----------------------
    Shear area per unit length for bolt external thread:
        A_s_bolt/L = π d_nom / (2 pitch)  × 0.75  (75% thread engagement height)
        (simplified: per-pitch shear area = π × d × 0.75 × pitch / 2, so per metre
         = π × d_nom × 0.75 / 2 per pitch height)

    More precisely (Shigley eq. 8-24, stress area at minor diameter):
        A_strip_bolt / turn = π × d_minor × 0.75 × pitch   [m² per pitch length]
        → per metre: A_s_bolt = π × d_minor × 0.75

    For nut (internal thread, shear at pitch diameter):
        A_s_nut = π × d_nom × 0.75

    Required engagement length:
        L_e = F_total / (Ssy × A_s)   then multiply by safety_factor

    References
    ----------
    Shigley 10th ed., §8-7 (thread stripping)
    """
    err = _guard_positive("F_preload", F_preload)
    if err:
        return _err(err)
    err = _guard_nonneg("F_external", F_external)
    if err:
        return _err(err)
    err = _guard_positive("d_nom", d_nom)
    if err:
        return _err(err)
    err = _guard_positive("thread_pitch", thread_pitch)
    if err:
        return _err(err)
    err = _guard_positive("Ssy_bolt", Ssy_bolt)
    if err:
        return _err(err)
    err = _guard_positive("Ssy_nut", Ssy_nut)
    if err:
        return _err(err)
    err = _guard_positive("safety_factor", safety_factor)
    if err:
        return _err(err)

    try:
        Phi_f = float(Phi)
    except (TypeError, ValueError):
        return _err(f"Phi must be a number, got {Phi!r}")
    if not (0.0 < Phi_f <= 1.0):
        return _err(f"Phi must be in (0, 1], got {Phi_f}")

    F_p = float(F_preload)
    F_e = float(F_external)
    d = float(d_nom)
    p = float(thread_pitch)
    Ssy_b = float(Ssy_bolt)
    Ssy_n = float(Ssy_nut)
    sf = float(safety_factor)

    warnings: list[str] = []

    F_total = F_p + Phi_f * F_e

    # Shear area per unit length (per metre of engagement)
    # bolt external thread: shear at minor diameter ≈ d - 1.08 × pitch (ISO 68-1 approx)
    d_minor_approx = d - 1.0825 * p
    if d_minor_approx <= 0:
        d_minor_approx = d * 0.8
        warnings.append(
            "Computed minor diameter is <= 0; using 0.8 × d_nom as approximation."
        )

    # Shear area per metre of engagement:
    A_s_bolt_per_m = math.pi * d_minor_approx * 0.75    # m²/m
    A_s_nut_per_m = math.pi * d * 0.75                  # m²/m

    # Required engagement length (before safety factor)
    L_e_bolt = F_total / (Ssy_b * A_s_bolt_per_m) if A_s_bolt_per_m > 0 else float("inf")
    L_e_nut = F_total / (Ssy_n * A_s_nut_per_m) if A_s_nut_per_m > 0 else float("inf")
    L_e_req = max(L_e_bolt, L_e_nut) * sf

    if L_e_req > 5.0 * d:
        warnings.append(
            f"Required engagement length L_e={L_e_req*1e3:.1f} mm > 5×d_nom="
            f"{5*d*1e3:.1f} mm; consider stronger nut/tapped material or larger bolt."
        )

    return {
        "ok": True,
        "L_e_bolt_m": L_e_bolt,
        "L_e_nut_m": L_e_nut,
        "L_e_required_m": L_e_req,
        "F_total_N": F_total,
        "shear_area_per_m_bolt": A_s_bolt_per_m,
        "shear_area_per_m_nut": A_s_nut_per_m,
        "d_minor_approx_m": d_minor_approx,
        "warnings": warnings,
    }
