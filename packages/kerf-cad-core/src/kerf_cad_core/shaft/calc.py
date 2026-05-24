"""
kerf_cad_core.shaft.calc — pure-Python shaft & bearing sizing formulas.

Implements four public functions:

  shaft_diameter(M, T, sigma_allow, *, method, Kf, Kfs, safety_factor)
      Required shaft diameter from combined bending + torsion loads.
      Supports:
        "DE-Goodman"   — Distortion-Energy / Goodman (ASME B106 approach)
        "max-shear"    — Maximum-Shear-Stress (Tresca) combined criterion

  shaft_critical_speed(length_m, mass_per_m, E, I, *, supports)
      First whirl (lateral) critical speed for a uniform shaft.
      Supports: "simply-supported" (default) or "fixed-fixed".

  bearing_l10(C, P, n_rpm, bearing_type)
      ISO 281 L10 basic rating life.
        ball   → exponent p = 3.0
        roller → exponent p = 10/3

  key_size(shaft_d_mm, torque_Nm, material)
      Square/rectangular key sizing from standard shaft-diameter tables
      (ANSI B17.1 / DIN 6885) plus shear and bearing stress checks.

All functions return a plain dict:
    success → {"ok": True, ...computed fields...}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise.

Units
-----
Unless otherwise stated:
  lengths  — metres (m)          shaft_diameter / shaft_critical_speed inputs
  lengths  — millimetres (mm)    key_size shaft diameter input
  forces   — Newtons (N)
  moments  — Newton-metres (N·m)
  stress   — Pascals (Pa)
  load     — Newtons (N)         bearing dynamic-load rating C, equivalent load P
  speed    — rpm                 bearing life calculations
  life     — 10^6 revolutions    bearing L10 output

References
----------
ASME B106.1M-1985 — Design of Transmission Shafting
ISO 281:2007 — Rolling bearings — Dynamic load ratings and rating life
Shigley's Mechanical Engineering Design, 10th ed., §§ 6-14, 11-9, 8-9
ANSI B17.1-1967 — Keys and Keyseats

Author: imranparuk
"""

from __future__ import annotations

import math
from typing import Any
from kerf_cad_core._guards import _err, _guard_nonneg, _guard_positive


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_KEY_TABLE: list[tuple[tuple[float, float], tuple[float, float]]] = [
    ((6,    8),    (2,   2)),
    ((8,    10),   (3,   3)),
    ((10,   12),   (4,   4)),
    ((12,   17),   (5,   5)),
    ((17,   22),   (6,   6)),
    ((22,   30),   (8,   7)),
    ((30,   38),   (10,  8)),
    ((38,   44),   (12,  8)),
    ((44,   50),   (14,  9)),
    ((50,   58),   (16,  10)),
    ((58,   65),   (18,  11)),
    ((65,   75),   (20,  12)),
    ((75,   85),   (22,  14)),
    ((85,   95),   (25,  14)),
    ((95,   110),  (28,  16)),
    ((110,  130),  (32,  18)),
    ((130,  150),  (36,  20)),
    ((150,  170),  (40,  22)),
    ((170,  200),  (45,  25)),
    ((200,  230),  (50,  28)),
]

# Key-length default: standard practice uses L = 1.5 × shaft_d unless provided
_KEY_L_FACTOR = 1.5

# Material allowable stresses (Pa) — conservative published values
_KEY_MATERIALS: dict[str, dict[str, float]] = {
    "steel_1045":   {"tau_allow": 170e6, "sigma_c_allow": 340e6},
    "steel_1020":   {"tau_allow": 120e6, "sigma_c_allow": 240e6},
    "stainless_304":{"tau_allow": 115e6, "sigma_c_allow": 230e6},
    "cast_iron":    {"tau_allow":  55e6, "sigma_c_allow": 110e6},
}

_DEFAULT_KEY_MATERIAL = "steel_1045"


def _lookup_key(shaft_d_mm: float) -> tuple[float, float] | None:
    """Return (width_mm, height_mm) for shaft_d_mm, or None if out of range."""
    for (d_min, d_max), (w, h) in _KEY_TABLE:
        if d_min <= shaft_d_mm <= d_max:
            return (w, h)
    return None


# ---------------------------------------------------------------------------
# 1. shaft_diameter
# ---------------------------------------------------------------------------

def shaft_diameter(
    M: float,
    T: float,
    sigma_allow: float,
    *,
    method: str = "DE-Goodman",
    Kf: float = 1.0,
    Kfs: float = 1.0,
    safety_factor: float = 1.0,
) -> dict:
    """
    Required solid circular shaft diameter from combined bending and torsion.

    Parameters
    ----------
    M : float
        Bending moment (N·m). Must be >= 0.
    T : float
        Torsional moment / torque (N·m). Must be >= 0.
    sigma_allow : float
        Allowable normal stress (Pa). For DE-Goodman this is the endurance
        limit Se (or Se' divided by safety factor externally); for max-shear
        this is the allowable bending stress. Must be > 0.
    method : str
        "DE-Goodman"  — Distortion-Energy / Goodman combined criterion
                        (ASME B106, Shigley §6-14).  Uses Von Mises equivalent
                        stresses; the required diameter satisfies:

                            d³ = (32/π·Se) × √[(Kf·M)² + ¾(Kfs·T)²]

                        This matches the DE-Goodman endurance criterion when the
                        mean torque is treated as a steady load (infinite life).

        "max-shear"   — Maximum-Shear-Stress (Tresca) criterion.  The required
                        diameter satisfies:

                            d³ = (16/π·τ_allow) × √[M² + T²]

                        where τ_allow = sigma_allow / 2.
    Kf : float
        Fatigue stress concentration factor for bending (default 1.0 — no notch).
    Kfs : float
        Fatigue stress concentration factor for torsion (default 1.0 — no notch).
    safety_factor : float
        Additional safety factor multiplied on the right-hand side before
        solving for d (default 1.0 — safety already embedded in sigma_allow).

    Returns
    -------
    dict
        ok        : True
        diameter_m: required shaft diameter (m)
        method    : method used
        M_Nm      : bending moment used (N·m)
        T_Nm      : torque used (N·m)
        sigma_allow_Pa: allowable stress used (Pa)

    Notes
    -----
    Both M and T may be zero simultaneously (trivial zero-diameter degenerate
    case) — in that situation the function returns diameter_m = 0.0.
    At least one of Kf, Kfs must be >= 1.
    """
    # --- Validate ---
    err = _guard_nonneg("M", M)
    if err:
        return _err(err)
    err = _guard_nonneg("T", T)
    if err:
        return _err(err)
    err = _guard_positive("sigma_allow", sigma_allow)
    if err:
        return _err(err)
    err = _guard_positive("Kf", Kf)
    if err:
        return _err(err)
    err = _guard_positive("Kfs", Kfs)
    if err:
        return _err(err)
    err = _guard_positive("safety_factor", safety_factor)
    if err:
        return _err(err)

    method_clean = str(method).strip().lower().replace("-", "").replace("_", "")

    M = float(M)
    T = float(T)
    Se = float(sigma_allow)
    kf = float(Kf)
    kfs = float(Kfs)
    sf = float(safety_factor)

    if method_clean == "degoodman":
        # DE-Goodman (ASME B106 / Shigley §6-14)
        # d³ = (32 × sf / (π × Se)) × √[(Kf·M)² + ¾(Kfs·T)²]
        radicand = (kf * M) ** 2 + 0.75 * (kfs * T) ** 2
        rhs = (32.0 * sf / (math.pi * Se)) * math.sqrt(radicand)
        d = rhs ** (1.0 / 3.0) if rhs > 0 else 0.0
        return {
            "ok": True,
            "diameter_m": d,
            "method": "DE-Goodman",
            "M_Nm": M,
            "T_Nm": T,
            "sigma_allow_Pa": Se,
            "Kf": kf,
            "Kfs": kfs,
            "safety_factor": sf,
        }

    elif method_clean == "maxshear":
        # Tresca / max-shear criterion
        # τ_allow = Se / 2
        # d³ = (16 × sf / (π × τ_allow)) × √[M² + T²]
        #      = (32 × sf / (π × Se)) × √[M² + T²]
        radicand = M ** 2 + T ** 2
        rhs = (32.0 * sf / (math.pi * Se)) * math.sqrt(radicand)
        d = rhs ** (1.0 / 3.0) if rhs > 0 else 0.0
        return {
            "ok": True,
            "diameter_m": d,
            "method": "max-shear",
            "M_Nm": M,
            "T_Nm": T,
            "sigma_allow_Pa": Se,
            "Kf": kf,
            "Kfs": kfs,
            "safety_factor": sf,
        }

    else:
        return _err(
            f"Unknown method {method!r}. Supported: 'DE-Goodman', 'max-shear'."
        )


# ---------------------------------------------------------------------------
# 2. shaft_critical_speed
# ---------------------------------------------------------------------------

def shaft_critical_speed(
    length_m: float,
    mass_per_m: float,
    E: float,
    I: float,
    *,
    supports: str = "simply-supported",
) -> dict:
    """
    First lateral (whirl) critical speed for a uniform shaft.

    Uses the Euler-Bernoulli beam equation exact natural frequency solution
    for a uniform cross-section.  The first mode shape coefficient β·L
    depends on the boundary conditions (supports).

    Parameters
    ----------
    length_m : float
        Shaft length (m).  Must be > 0.
    mass_per_m : float
        Mass per unit length (kg/m).  Must be > 0.
        For a solid steel shaft: mass_per_m = ρ × π/4 × d²
        (ρ ≈ 7850 kg/m³ for steel).
    E : float
        Young's modulus (Pa).  Must be > 0.  Steel ≈ 200e9 Pa.
    I : float
        Second moment of area of the cross-section (m⁴).  Must be > 0.
        For a solid circular shaft of diameter d: I = π·d⁴/64.
    supports : str
        Boundary condition:
          "simply-supported" (default) — pinned-pinned; β₁·L = π
          "fixed-fixed"                — clamped-clamped; β₁·L = 4.730

    Returns
    -------
    dict
        ok            : True
        omega_rad_s   : first critical angular speed (rad/s)
        n_rpm         : first critical speed (rpm)
        beta_L        : β₁·L coefficient used
        supports      : boundary condition string
        length_m      : shaft length (m)
        EI_Nm2        : flexural rigidity E·I (N·m²)
        mass_per_m    : mass per unit length (kg/m)

    Formula
    -------
    For a uniform Euler-Bernoulli beam the natural frequency of the i-th mode
    is given by:

        ω_i = (β_i · L)² × √(EI / (ρA · L⁴))

    where β_i·L is the i-th eigenvalue of the characteristic equation.

    For i=1:
        simply-supported : β₁·L = π      ≈ 3.14159
        fixed-fixed      : β₁·L = 4.73004

    References
    ----------
    Rao, S.S. "Mechanical Vibrations", 5th ed., §8-6.
    """
    err = _guard_positive("length_m", length_m)
    if err:
        return _err(err)
    err = _guard_positive("mass_per_m", mass_per_m)
    if err:
        return _err(err)
    err = _guard_positive("E", E)
    if err:
        return _err(err)
    err = _guard_positive("I", I)
    if err:
        return _err(err)

    L = float(length_m)
    m = float(mass_per_m)
    E_val = float(E)
    I_val = float(I)

    sup = str(supports).strip().lower().replace("-", "").replace(" ", "").replace("_", "")

    if sup in ("simplysupported", "pinned", "pinnedpinned", "ss"):
        beta_L = math.pi  # π for simply-supported first mode
        sup_label = "simply-supported"
    elif sup in ("fixedfixed", "clamped", "clampedclamped", "ff"):
        beta_L = 4.73004074  # exact first eigenvalue for fixed-fixed
        sup_label = "fixed-fixed"
    else:
        return _err(
            f"Unknown supports {supports!r}. Supported: 'simply-supported', 'fixed-fixed'."
        )

    EI = E_val * I_val
    # ω = (β₁L)² / L² × √(EI / m)
    # equivalently: ω = (β₁L/L)² × L^0 × ... let's write it cleanly:
    # ω = (β₁L)² × √(EI / (m × L⁴))
    omega = (beta_L ** 2) * math.sqrt(EI / (m * L ** 4))
    n_rpm = omega * 60.0 / (2.0 * math.pi)

    return {
        "ok": True,
        "omega_rad_s": omega,
        "n_rpm": n_rpm,
        "beta_L": beta_L,
        "supports": sup_label,
        "length_m": L,
        "EI_Nm2": EI,
        "mass_per_m": m,
    }


# ---------------------------------------------------------------------------
# 3. bearing_l10
# ---------------------------------------------------------------------------

# ISO 281 life exponent per bearing type
_BEARING_EXPONENTS: dict[str, float] = {
    "ball":   3.0,
    "roller": 10.0 / 3.0,
}


def bearing_l10(
    C: float,
    P: float,
    n_rpm: float,
    bearing_type: str = "ball",
) -> dict:
    """
    ISO 281 basic rating life L10.

    Parameters
    ----------
    C : float
        Basic dynamic load rating (N).  Must be > 0.
    P : float
        Equivalent dynamic bearing load (N).  Must be > 0.
    n_rpm : float
        Rotational speed (rpm).  Must be > 0.
    bearing_type : str
        "ball"   — point-contact bearing; p = 3     (ISO 281 §5.1)
        "roller" — line-contact bearing; p = 10/3   (ISO 281 §5.1)

    Returns
    -------
    dict
        ok           : True
        L10_rev      : basic rating life in 10^6 revolutions
        L10_hours    : basic rating life in operating hours at n_rpm
        C_over_P     : load ratio C/P
        p            : life exponent used
        bearing_type : bearing type string
        C_N          : dynamic load rating used (N)
        P_N          : equivalent load used (N)
        n_rpm        : rotational speed used (rpm)

    Formula
    -------
    ISO 281:

        L10 = (C / P)^p    [units: 10^6 revolutions]

        L10_hours = L10 × 10^6 / (60 × n)

    where p = 3 for ball bearings, p = 10/3 for roller bearings.
    """
    err = _guard_positive("C", C)
    if err:
        return _err(err)
    err = _guard_positive("P", P)
    if err:
        return _err(err)
    err = _guard_positive("n_rpm", n_rpm)
    if err:
        return _err(err)

    bt = str(bearing_type).strip().lower()
    if bt not in _BEARING_EXPONENTS:
        valid = list(_BEARING_EXPONENTS.keys())
        return _err(
            f"Unknown bearing_type {bearing_type!r}. Supported: {valid}."
        )

    p = _BEARING_EXPONENTS[bt]
    C_val = float(C)
    P_val = float(P)
    n = float(n_rpm)

    ratio = C_val / P_val
    L10_rev = ratio ** p  # in millions of revolutions
    L10_hours = L10_rev * 1e6 / (60.0 * n)

    return {
        "ok": True,
        "L10_rev": L10_rev,
        "L10_hours": L10_hours,
        "C_over_P": ratio,
        "p": p,
        "bearing_type": bt,
        "C_N": C_val,
        "P_N": P_val,
        "n_rpm": n,
    }


# ---------------------------------------------------------------------------
# 4. key_size
# ---------------------------------------------------------------------------

def key_size(
    shaft_d_mm: float,
    torque_Nm: float,
    material: str = _DEFAULT_KEY_MATERIAL,
    *,
    key_length_mm: float | None = None,
) -> dict:
    """
    Square/rectangular key sizing per ANSI B17.1 / DIN 6885.

    Selects the standard key cross-section for the given shaft diameter, then
    checks both the shear stress (on the key width × length area) and the
    bearing/compressive stress (on the half key height × length area).

    Parameters
    ----------
    shaft_d_mm : float
        Shaft diameter (mm).  Must be in the standard range [6, 230] mm.
    torque_Nm : float
        Transmitted torque (N·m).  Must be >= 0.
    material : str
        Key material from built-in catalog:
          "steel_1045" (default)  — τ_allow=170 MPa, σ_c=340 MPa
          "steel_1020"            — τ_allow=120 MPa, σ_c=240 MPa
          "stainless_304"         — τ_allow=115 MPa, σ_c=230 MPa
          "cast_iron"             — τ_allow= 55 MPa, σ_c=110 MPa
    key_length_mm : float | None
        Key length (mm).  If None (default), uses L = 1.5 × shaft_d_mm.
        Must be > 0 if provided.

    Returns
    -------
    dict
        ok                  : True
        shaft_d_mm          : shaft diameter (mm)
        key_width_mm        : key width w (mm)
        key_height_mm       : key height h (mm)
        key_length_mm       : key length L (mm) used
        material            : material name
        tau_allow_Pa        : allowable shear stress (Pa)
        sigma_c_allow_Pa    : allowable compressive stress (Pa)
        shear_stress_Pa     : computed shear stress on key (Pa)
        bearing_stress_Pa   : computed compressive/bearing stress on key (Pa)
        shear_ok            : True if shear_stress <= tau_allow
        bearing_ok          : True if bearing_stress <= sigma_c_allow
        shear_safety_factor : tau_allow / shear_stress (inf if torque=0)
        bearing_safety_factor: sigma_c_allow / bearing_stress (inf if torque=0)

    Formulas (Shigley §8-9)
    -----------------------
    Tangential force at shaft surface:
        F = 2T / d      (d in metres)

    Shear stress on key:
        τ = F / (w × L)     (area = w × L in metres²)

    Bearing (compressive) stress on key:
        σ_c = F / (h/2 × L)    (area = h/2 × L in metres²)
    """
    err = _guard_positive("shaft_d_mm", shaft_d_mm)
    if err:
        return _err(err)
    err = _guard_nonneg("torque_Nm", torque_Nm)
    if err:
        return _err(err)

    d_mm = float(shaft_d_mm)
    T = float(torque_Nm)

    mat = str(material).strip().lower()
    if mat not in _KEY_MATERIALS:
        valid = list(_KEY_MATERIALS.keys())
        return _err(f"Unknown material {material!r}. Supported: {valid}.")

    key_dims = _lookup_key(d_mm)
    if key_dims is None:
        return _err(
            f"shaft_d_mm={d_mm} is outside the standard key table range "
            f"[{_KEY_TABLE[0][0][0]}, {_KEY_TABLE[-1][0][1]}] mm."
        )

    w_mm, h_mm = key_dims

    if key_length_mm is not None:
        err = _guard_positive("key_length_mm", key_length_mm)
        if err:
            return _err(err)
        L_mm = float(key_length_mm)
    else:
        L_mm = _KEY_L_FACTOR * d_mm

    tau_allow = _KEY_MATERIALS[mat]["tau_allow"]
    sigma_c_allow = _KEY_MATERIALS[mat]["sigma_c_allow"]

    # Convert to metres for SI stress calculation
    d_m = d_mm * 1e-3
    w_m = w_mm * 1e-3
    h_m = h_mm * 1e-3
    L_m = L_mm * 1e-3

    # Tangential force
    F = 2.0 * T / d_m if d_m > 0 else 0.0

    # Shear stress: τ = F / (w × L)
    shear_area = w_m * L_m
    tau = F / shear_area if shear_area > 0 else 0.0

    # Bearing stress: σ_c = F / (h/2 × L)
    bearing_area = (h_m / 2.0) * L_m
    sigma_c = F / bearing_area if bearing_area > 0 else 0.0

    shear_ok = tau <= tau_allow
    bearing_ok = sigma_c <= sigma_c_allow

    shear_sf = tau_allow / tau if tau > 0 else float("inf")
    bearing_sf = sigma_c_allow / sigma_c if sigma_c > 0 else float("inf")

    return {
        "ok": True,
        "shaft_d_mm": d_mm,
        "key_width_mm": w_mm,
        "key_height_mm": h_mm,
        "key_length_mm": L_mm,
        "material": mat,
        "tau_allow_Pa": tau_allow,
        "sigma_c_allow_Pa": sigma_c_allow,
        "shear_stress_Pa": tau,
        "bearing_stress_Pa": sigma_c,
        "shear_ok": shear_ok,
        "bearing_ok": bearing_ok,
        "shear_safety_factor": shear_sf,
        "bearing_safety_factor": bearing_sf,
    }
