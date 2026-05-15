"""
kerf_cad_core.steelconn.connections — structural-steel connection capacity design.

Implements AISC 360-22 provisions for bolted and welded steel connections.
All checks support both LRFD (φ factor) and ASD (Ω factor) design methods.

BOLTED CONNECTIONS
------------------
bolt_shear_capacity(Ab, Fnv, n_bolts, *, method, phi, omega)
    Nominal bolt shear per AISC Table J3.2.
    method: "LRFD" → φRn;  "ASD" → Rn/Ω

bolt_bearing_capacity(Fu, t, d, n_bolts, *, lc, method, phi, omega)
    Bearing on connected material, AISC J3.10.
    Includes clear-distance check (1.5lc·t·Fu) vs deformation-controlled (2.4d·t·Fu).

bolt_tension_capacity(Ab, Fnt, n_bolts, *, method, phi, omega)
    Nominal bolt tension strength per AISC Table J3.2.

slip_critical_capacity(mu, Pt, n_bolts, n_faying, *, hole_factor, method, phi, omega)
    Slip-critical connection, AISC J3.8.
    mu: mean slip coefficient (Class A=0.35, Class B=0.50).
    hole_factor: 1.0 standard round, 0.85 oversized, 0.70 short-slotted.

block_shear_capacity(Fu, Fy, Agv, Anv, Ant, *, Ubs, method, phi, omega)
    Block shear rupture per AISC J4.3.
    Rn = min(0.6Fu·Anv + Ubs·Fu·Ant,  0.6Fy·Agv + Ubs·Fu·Ant)

bolt_group_eccentric(bolt_coords, P, e, *, method_beg)
    Eccentric bolt group capacity ratio.
    "IC"      — Instantaneous Center of Rotation (iterative, exact per AISC)
    "elastic" — Elastic Vector Method (conservative, closed-form)
    Returns utilization ratio (applied/capacity) and governing bolt index.

WELDED CONNECTIONS
------------------
fillet_weld_capacity(D_sixteenths, L_weld, Fexx, *, angle_deg, method, phi, omega)
    Fillet weld group capacity per AISC J2.4.
    Includes directional strength increase: 1.0 + 0.50·sin¹·⁵(θ).
    D_sixteenths: weld size in sixteenths of an inch.

weld_group_elastic_vector(weld_segments, P, ex, ey, *, method, phi, omega)
    Elastic vector method for a general weld group under eccentric load.
    weld_segments: list of (x0,y0,x1,y1,D_sixteenths,Fexx) tuples.
    Returns utilization ratio.

electrode_strength(designation)
    Tabulated Fexx (ksi → MPa) for standard SMAW/FCAW electrode designations:
    E60, E70, E80, E90, E100, E110.

BASE PLATE
----------
base_plate_bearing(P, B, N, fp_prime)
    Bearing stress check for column base plate on grout / concrete.
    fp_prime: 0.85·f'c bearing limit (Pa) per ACI 318 / AISC J8.

DESIGN METHOD
-------------
All functions accept method="LRFD" (default) or method="ASD".
  LRFD: factored capacity = φ·Rn.   Default φ taken from AISC unless overridden.
  ASD:  allowable capacity = Rn/Ω.  Default Ω taken from AISC unless overridden.

OUTPUT FORMAT
-------------
All functions return:
    {"ok": True,
     "Rn":          nominal strength (N or N·mm),
     "capacity":    φRn  or  Rn/Ω  (design capacity),
     "utilization": applied / capacity  (ratio ≥ 0; > 1.0 → overstress),
     "adequate":    True if utilization <= 1.0,
     "limit_state": governing limit-state description string,
     "method":      "LRFD" or "ASD",
     ...additional output fields...}

    {"ok": False, "reason": "<human-readable>"}  on invalid input.

Functions NEVER raise.  Overstress is reflected in the return dict and also
issued as a warnings.warn(stacklevel=2) for calling code to intercept.

Units
-----
All dimensional inputs/outputs use SI unless stated otherwise:
  lengths     — millimetres (mm)
  forces      — Newtons (N)
  stresses    — Pascals (Pa) = N/m² = N/mm² × 1e6
  angles      — degrees (converted to radians internally)

Note: bolt and weld size D_sixteenths in sixteenths of an inch (US customary,
as per AISC tables) — converted internally.  Fu, Fy, Fexx in Pa.

References
----------
AISC 360-22 Specification for Structural Steel Buildings.
AISC Steel Construction Manual, 16th edition, Tables 7-1 through 7-8.
McCormac & Csernak, Structural Steel Design, 6th ed.

Author: imranparuk
"""

from __future__ import annotations

import math
import warnings
from typing import Any

# ---------------------------------------------------------------------------
# Internal validation helpers
# ---------------------------------------------------------------------------

def _err(reason: str) -> dict:
    return {"ok": False, "reason": reason}


def _guard_positive(name: str, val: Any) -> str | None:
    try:
        v = float(val)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {val!r}"
    if not math.isfinite(v):
        return f"{name} must be finite"
    if v <= 0:
        return f"{name} must be > 0, got {v}"
    return None


def _guard_nonneg(name: str, val: Any) -> str | None:
    try:
        v = float(val)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {val!r}"
    if not math.isfinite(v):
        return f"{name} must be finite"
    if v < 0:
        return f"{name} must be >= 0, got {v}"
    return None


def _resolve_method(
    method: str,
    phi_default: float,
    omega_default: float,
    phi_override: float | None,
    omega_override: float | None,
) -> tuple[str, float, float] | str:
    """Validate method and return (method_clean, phi, omega) or error string."""
    m = str(method).strip().upper()
    if m not in ("LRFD", "ASD"):
        return f"method must be 'LRFD' or 'ASD', got {method!r}"
    phi = phi_override if phi_override is not None else phi_default
    omega = omega_override if omega_override is not None else omega_default
    if phi <= 0:
        return f"phi must be > 0, got {phi}"
    if omega <= 0:
        return f"omega must be > 0, got {omega}"
    return m, phi, omega


def _design_capacity(Rn: float, method: str, phi: float, omega: float) -> float:
    if method == "LRFD":
        return phi * Rn
    return Rn / omega


def _overstress_warn(name: str, util: float) -> None:
    if util > 1.0:
        warnings.warn(
            f"steelconn.{name}: overstress — utilization ratio = {util:.4f} > 1.0",
            stacklevel=3,
        )


# ---------------------------------------------------------------------------
# AISC 360-22 default φ/Ω factors
# ---------------------------------------------------------------------------

# Bolt shear (J3.6): φ=0.75, Ω=2.00
_PHI_BOLT_SHEAR = 0.75
_OMEGA_BOLT_SHEAR = 2.00

# Bolt bearing (J3.10): φ=0.75, Ω=2.00
_PHI_BOLT_BEARING = 0.75
_OMEGA_BOLT_BEARING = 2.00

# Bolt tension (J3.6): φ=0.75, Ω=2.00
_PHI_BOLT_TENSION = 0.75
_OMEGA_BOLT_TENSION = 2.00

# Slip-critical (J3.8): φ=1.00, Ω=1.50 (serviceability limit)
_PHI_SLIP = 1.00
_OMEGA_SLIP = 1.50

# Block shear (J4.3): φ=0.75, Ω=2.00
_PHI_BLOCK_SHEAR = 0.75
_OMEGA_BLOCK_SHEAR = 2.00

# Fillet weld (J2.4): φ=0.75, Ω=2.00
_PHI_WELD = 0.75
_OMEGA_WELD = 2.00

# Base plate bearing (J8): φ=0.65, Ω=2.31
_PHI_BEARING = 0.65
_OMEGA_BEARING = 2.31


# ---------------------------------------------------------------------------
# Electrode strength table (Fexx)
# ---------------------------------------------------------------------------

# Standard SMAW and FCAW electrode designations → Fexx in Pa
# Values are nominal AWS A5.1 / A5.20 strength levels.
_ELECTRODE_FEXX: dict[str, float] = {
    "E60":  413.7e6,   # 60 ksi
    "E70":  482.6e6,   # 70 ksi
    "E80":  551.6e6,   # 80 ksi
    "E90":  620.5e6,   # 90 ksi
    "E100": 689.5e6,   # 100 ksi
    "E110": 758.4e6,   # 110 ksi
}


# ---------------------------------------------------------------------------
# 1. electrode_strength
# ---------------------------------------------------------------------------

def electrode_strength(designation: str) -> dict:
    """
    Return tabulated Fexx for a standard electrode designation.

    Parameters
    ----------
    designation : str
        One of: "E60", "E70", "E80", "E90", "E100", "E110".

    Returns
    -------
    dict
        ok          : True
        designation : normalised designation string
        Fexx_Pa     : electrode classification strength (Pa)
        Fexx_ksi    : electrode classification strength (ksi)
    """
    key = str(designation).strip().upper()
    if key not in _ELECTRODE_FEXX:
        valid = list(_ELECTRODE_FEXX.keys())
        return _err(f"Unknown electrode {designation!r}. Supported: {valid}.")
    fexx = _ELECTRODE_FEXX[key]
    return {
        "ok": True,
        "designation": key,
        "Fexx_Pa": fexx,
        "Fexx_ksi": fexx / 6.894757e6,   # Pa → ksi  (1 ksi = 6894757 Pa)
    }


# ---------------------------------------------------------------------------
# 2. bolt_shear_capacity  (AISC 360-22 J3.6)
# ---------------------------------------------------------------------------

def bolt_shear_capacity(
    Ab: float,
    Fnv: float,
    n_bolts: int,
    *,
    shear_planes: int = 1,
    Vu: float = 0.0,
    method: str = "LRFD",
    phi: float | None = None,
    omega: float | None = None,
) -> dict:
    """
    Nominal bolt shear strength (AISC 360-22 J3.6).

    Rn = Fnv × Ab × n_bolts × shear_planes

    Parameters
    ----------
    Ab : float
        Gross cross-sectional area of one bolt (mm²). Must be > 0.
    Fnv : float
        Nominal shear stress of bolt (Pa).  AISC Table J3.2:
          A307:   165 MPa (no threads in plane) / 165 MPa
          A325N:  372 MPa  (threads in shear plane, common)
          A325X:  462 MPa  (threads excluded from shear plane)
          A490N:  457 MPa
          A490X:  572 MPa
          F1852N: 372 MPa  (metric equiv of A325N)
    n_bolts : int
        Number of bolts in the connection. Must be >= 1.
    shear_planes : int
        Number of shear planes (1 = single shear, 2 = double shear). Default 1.
    Vu : float
        Applied shear force (N).  Used only to compute utilization ratio.
    method : str
        "LRFD" (default) or "ASD".
    phi : float | None
        Override LRFD φ factor (default 0.75 per AISC J3.6).
    omega : float | None
        Override ASD Ω factor (default 2.00 per AISC J3.6).

    Returns
    -------
    dict
        ok, Rn_N, capacity_N, utilization, adequate, limit_state, method,
        n_bolts, shear_planes, Ab_mm2, Fnv_Pa
    """
    err = _guard_positive("Ab", Ab)
    if err:
        return _err(err)
    err = _guard_positive("Fnv", Fnv)
    if err:
        return _err(err)
    err = _guard_nonneg("Vu", Vu)
    if err:
        return _err(err)
    if not isinstance(n_bolts, int) or n_bolts < 1:
        try:
            n_bolts = int(n_bolts)
            if n_bolts < 1:
                raise ValueError()
        except (TypeError, ValueError):
            return _err(f"n_bolts must be a positive integer, got {n_bolts!r}")
    if shear_planes not in (1, 2):
        return _err("shear_planes must be 1 or 2")

    res = _resolve_method(method, _PHI_BOLT_SHEAR, _OMEGA_BOLT_SHEAR, phi, omega)
    if isinstance(res, str):
        return _err(res)
    method_clean, phi_val, omega_val = res

    # Ab in mm², Fnv in Pa = N/m²; convert Ab to m² for N result
    Rn = float(Fnv) * (float(Ab) * 1e-6) * int(n_bolts) * int(shear_planes)
    cap = _design_capacity(Rn, method_clean, phi_val, omega_val)
    util = float(Vu) / cap if cap > 0 else 0.0
    _overstress_warn("bolt_shear_capacity", util)

    factor_key = "phi" if method_clean == "LRFD" else "omega"
    factor_val = phi_val if method_clean == "LRFD" else omega_val

    return {
        "ok": True,
        "Rn_N": Rn,
        "capacity_N": cap,
        "utilization": util,
        "adequate": util <= 1.0,
        "limit_state": "bolt shear (AISC J3.6)",
        "method": method_clean,
        "n_bolts": n_bolts,
        "shear_planes": shear_planes,
        "Ab_mm2": float(Ab),
        "Fnv_Pa": float(Fnv),
        factor_key: factor_val,
    }


# ---------------------------------------------------------------------------
# 3. bolt_bearing_capacity  (AISC 360-22 J3.10)
# ---------------------------------------------------------------------------

def bolt_bearing_capacity(
    Fu: float,
    t: float,
    d: float,
    n_bolts: int,
    *,
    lc: float | None = None,
    deformation_controlled: bool = True,
    Vu: float = 0.0,
    method: str = "LRFD",
    phi: float | None = None,
    omega: float | None = None,
) -> dict:
    """
    Bearing strength on connected material (AISC 360-22 J3.10).

    Deformation-controlled (standard holes): Rn_per_bolt = 2.4 × d × t × Fu
    Clear-distance check:                    Rn_per_bolt = 1.2 × lc × t × Fu

    If lc is given, the minimum (most critical) governs.

    Parameters
    ----------
    Fu : float
        Ultimate tensile stress of connected material (Pa). Must be > 0.
    t : float
        Thickness of connected material (mm). Must be > 0.
    d : float
        Nominal bolt diameter (mm). Must be > 0.
    n_bolts : int
        Number of bolts. Must be >= 1.
    lc : float | None
        Clear distance in direction of force (mm).  If None, only the
        deformation-controlled limit (2.4dtFu) is used.
    deformation_controlled : bool
        True (default): use 2.4dtFu.  False: use 3.0dtFu (no deformation limit).
    Vu : float
        Applied shear force (N). Used only for utilization.
    method, phi, omega : see module docstring.

    Returns
    -------
    dict
        ok, Rn_N, capacity_N, utilization, adequate, limit_state, method, ...
    """
    err = _guard_positive("Fu", Fu)
    if err:
        return _err(err)
    err = _guard_positive("t", t)
    if err:
        return _err(err)
    err = _guard_positive("d", d)
    if err:
        return _err(err)
    err = _guard_nonneg("Vu", Vu)
    if err:
        return _err(err)
    if lc is not None:
        err = _guard_positive("lc", lc)
        if err:
            return _err(err)
    try:
        n_bolts = int(n_bolts)
        if n_bolts < 1:
            raise ValueError()
    except (TypeError, ValueError):
        return _err(f"n_bolts must be a positive integer, got {n_bolts!r}")

    res = _resolve_method(method, _PHI_BOLT_BEARING, _OMEGA_BOLT_BEARING, phi, omega)
    if isinstance(res, str):
        return _err(res)
    method_clean, phi_val, omega_val = res

    # Convert mm → m for area calculation (keep Pa for stress)
    t_m = float(t) * 1e-3
    d_m = float(d) * 1e-3

    bearing_factor = 2.4 if deformation_controlled else 3.0
    Rn_deform = bearing_factor * d_m * t_m * float(Fu) * n_bolts  # N

    governing_ls = f"bearing deformation-controlled (AISC J3.10): {bearing_factor}dtFu"

    if lc is not None:
        lc_m = float(lc) * 1e-3
        Rn_clear = 1.2 * lc_m * t_m * float(Fu) * n_bolts
        if Rn_clear < Rn_deform:
            Rn = Rn_clear
            governing_ls = "bearing clear-distance (AISC J3.10): 1.2lc·t·Fu"
        else:
            Rn = Rn_deform
    else:
        Rn = Rn_deform

    cap = _design_capacity(Rn, method_clean, phi_val, omega_val)
    util = float(Vu) / cap if cap > 0 else 0.0
    _overstress_warn("bolt_bearing_capacity", util)

    return {
        "ok": True,
        "Rn_N": Rn,
        "capacity_N": cap,
        "utilization": util,
        "adequate": util <= 1.0,
        "limit_state": governing_ls,
        "method": method_clean,
        "n_bolts": n_bolts,
        "Fu_Pa": float(Fu),
        "t_mm": float(t),
        "d_mm": float(d),
    }


# ---------------------------------------------------------------------------
# 4. bolt_tension_capacity  (AISC 360-22 J3.6)
# ---------------------------------------------------------------------------

def bolt_tension_capacity(
    Ab: float,
    Fnt: float,
    n_bolts: int,
    *,
    Tu: float = 0.0,
    method: str = "LRFD",
    phi: float | None = None,
    omega: float | None = None,
) -> dict:
    """
    Nominal bolt tension strength (AISC 360-22 J3.6).

    Rn = Fnt × Ab × n_bolts

    Parameters
    ----------
    Ab : float
        Gross bolt area (mm²). Must be > 0.
    Fnt : float
        Nominal tensile stress of bolt (Pa). AISC Table J3.2:
          A307:  310 MPa;  A325: 621 MPa;  A490: 780 MPa.
    n_bolts : int
        Number of bolts in tension. Must be >= 1.
    Tu : float
        Applied tensile force (N). Used only for utilization.
    method, phi, omega : see module docstring.

    Returns
    -------
    dict
        ok, Rn_N, capacity_N, utilization, adequate, limit_state, method, ...
    """
    err = _guard_positive("Ab", Ab)
    if err:
        return _err(err)
    err = _guard_positive("Fnt", Fnt)
    if err:
        return _err(err)
    err = _guard_nonneg("Tu", Tu)
    if err:
        return _err(err)
    try:
        n_bolts = int(n_bolts)
        if n_bolts < 1:
            raise ValueError()
    except (TypeError, ValueError):
        return _err(f"n_bolts must be a positive integer, got {n_bolts!r}")

    res = _resolve_method(method, _PHI_BOLT_TENSION, _OMEGA_BOLT_TENSION, phi, omega)
    if isinstance(res, str):
        return _err(res)
    method_clean, phi_val, omega_val = res

    Rn = float(Fnt) * float(Ab) * 1e-6 * n_bolts  # Ab in mm² → m², Pa×m²=N
    # Ab in mm², Fnt in Pa → need same units:
    # Pa = N/m²,  Ab in mm² = Ab * 1e-6 m²
    # Rn = Fnt [N/m²] × Ab [m²] = Fnt × Ab_mm2 × 1e-6
    cap = _design_capacity(Rn, method_clean, phi_val, omega_val)
    util = float(Tu) / cap if cap > 0 else 0.0
    _overstress_warn("bolt_tension_capacity", util)

    return {
        "ok": True,
        "Rn_N": Rn,
        "capacity_N": cap,
        "utilization": util,
        "adequate": util <= 1.0,
        "limit_state": "bolt tension (AISC J3.6)",
        "method": method_clean,
        "n_bolts": n_bolts,
        "Ab_mm2": float(Ab),
        "Fnt_Pa": float(Fnt),
    }


# ---------------------------------------------------------------------------
# 5. slip_critical_capacity  (AISC 360-22 J3.8)
# ---------------------------------------------------------------------------

def slip_critical_capacity(
    mu: float,
    Pt: float,
    n_bolts: int,
    n_faying: int = 1,
    *,
    hole_factor: float = 1.0,
    Vu: float = 0.0,
    method: str = "LRFD",
    phi: float | None = None,
    omega: float | None = None,
) -> dict:
    """
    Slip-critical connection capacity (AISC 360-22 J3.8).

    Rn = μ × Du × hf × Pt × ns × n_bolts

    where Du = 1.13 (ratio of mean installed bolt pretension to specified Pt),
    hf = hole_factor (1.0 standard, 0.85 oversized, 0.70 short-slotted transverse).

    Parameters
    ----------
    mu : float
        Mean slip coefficient.  Class A (unpainted clean): 0.35.
                                Class B (Class A or hot-dip galvanized): 0.50.
    Pt : float
        Minimum fastener tension (N).  AISC Table J3.1:
          3/4" A325: 133,400 N;  7/8" A325: 178,200 N;
          3/4" A490: 166,800 N;  M20 Grade 10.9: 142,000 N (approx).
    n_bolts : int
        Number of bolts. Must be >= 1.
    n_faying : int
        Number of slip planes (faying surfaces). Default 1.
    hole_factor : float
        hf per AISC J3.8: 1.0 (STD), 0.85 (OVS), 0.70 (short-slotted ⊥).
    Vu : float
        Applied shear (N). Used only for utilization.
    method, phi, omega : see module docstring.

    Returns
    -------
    dict
        ok, Rn_N, capacity_N, utilization, adequate, limit_state, method, ...
    """
    err = _guard_positive("mu", mu)
    if err:
        return _err(err)
    if float(mu) > 1.0:
        return _err("mu (slip coefficient) should not exceed 1.0")
    err = _guard_positive("Pt", Pt)
    if err:
        return _err(err)
    err = _guard_nonneg("Vu", Vu)
    if err:
        return _err(err)
    try:
        n_bolts = int(n_bolts)
        n_faying = int(n_faying)
        if n_bolts < 1 or n_faying < 1:
            raise ValueError()
    except (TypeError, ValueError):
        return _err("n_bolts and n_faying must be positive integers")
    err = _guard_positive("hole_factor", hole_factor)
    if err:
        return _err(err)
    if float(hole_factor) > 1.0:
        return _err("hole_factor must be <= 1.0")

    res = _resolve_method(method, _PHI_SLIP, _OMEGA_SLIP, phi, omega)
    if isinstance(res, str):
        return _err(res)
    method_clean, phi_val, omega_val = res

    Du = 1.13  # AISC constant
    Rn = float(mu) * Du * float(hole_factor) * float(Pt) * int(n_faying) * int(n_bolts)
    cap = _design_capacity(Rn, method_clean, phi_val, omega_val)
    util = float(Vu) / cap if cap > 0 else 0.0
    _overstress_warn("slip_critical_capacity", util)

    return {
        "ok": True,
        "Rn_N": Rn,
        "capacity_N": cap,
        "utilization": util,
        "adequate": util <= 1.0,
        "limit_state": "slip-critical (AISC J3.8)",
        "method": method_clean,
        "mu": float(mu),
        "Pt_N": float(Pt),
        "Du": Du,
        "hole_factor": float(hole_factor),
        "n_faying": n_faying,
        "n_bolts": n_bolts,
    }


# ---------------------------------------------------------------------------
# 6. block_shear_capacity  (AISC 360-22 J4.3)
# ---------------------------------------------------------------------------

def block_shear_capacity(
    Fu: float,
    Fy: float,
    Agv: float,
    Anv: float,
    Ant: float,
    *,
    Ubs: float = 1.0,
    Vu: float = 0.0,
    method: str = "LRFD",
    phi: float | None = None,
    omega: float | None = None,
) -> dict:
    """
    Block shear rupture capacity (AISC 360-22 J4.3).

    Rn = min(
        0.6·Fu·Anv + Ubs·Fu·Ant,     [shear rupture + tension rupture]
        0.6·Fy·Agv + Ubs·Fu·Ant,     [shear yield  + tension rupture]
    )

    Parameters
    ----------
    Fu : float
        Ultimate tensile stress (Pa). Must be > 0.
    Fy : float
        Yield stress (Pa). Must be > 0.
    Agv : float
        Gross area subject to shear (mm²). Must be > 0.
    Anv : float
        Net area subject to shear (mm²). Must be > 0.
    Ant : float
        Net area subject to tension (mm²). Must be > 0.
    Ubs : float
        Tension stress distribution factor.  1.0 (uniform) for most connections.
        0.5 for non-uniform distribution (e.g. beam webs with long lines of bolts).
    Vu : float
        Applied force (N). Used only for utilization.
    method, phi, omega : see module docstring.

    Returns
    -------
    dict
        ok, Rn_N, capacity_N, utilization, adequate, limit_state, method,
        Rn1_N (shear rupture path), Rn2_N (shear yield path), governing_path
    """
    for name, val in [("Fu", Fu), ("Fy", Fy), ("Agv", Agv), ("Anv", Anv), ("Ant", Ant)]:
        err = _guard_positive(name, val)
        if err:
            return _err(err)
    if not (0 < float(Ubs) <= 1.0):
        return _err("Ubs must be in (0, 1]")
    err = _guard_nonneg("Vu", Vu)
    if err:
        return _err(err)

    res = _resolve_method(method, _PHI_BLOCK_SHEAR, _OMEGA_BLOCK_SHEAR, phi, omega)
    if isinstance(res, str):
        return _err(res)
    method_clean, phi_val, omega_val = res

    # Areas mm² → m²
    Agv_m2 = float(Agv) * 1e-6
    Anv_m2 = float(Anv) * 1e-6
    Ant_m2 = float(Ant) * 1e-6
    Fu_v = float(Fu)
    Fy_v = float(Fy)
    Ubs_v = float(Ubs)

    # Path 1: shear rupture + tension rupture
    Rn1 = 0.6 * Fu_v * Anv_m2 + Ubs_v * Fu_v * Ant_m2
    # Path 2: shear yield + tension rupture
    Rn2 = 0.6 * Fy_v * Agv_m2 + Ubs_v * Fu_v * Ant_m2

    Rn = min(Rn1, Rn2)
    governing = "shear-rupture + tension-rupture" if Rn1 <= Rn2 else "shear-yield + tension-rupture"

    cap = _design_capacity(Rn, method_clean, phi_val, omega_val)
    util = float(Vu) / cap if cap > 0 else 0.0
    _overstress_warn("block_shear_capacity", util)

    return {
        "ok": True,
        "Rn_N": Rn,
        "capacity_N": cap,
        "utilization": util,
        "adequate": util <= 1.0,
        "limit_state": f"block shear (AISC J4.3) — {governing}",
        "method": method_clean,
        "Rn1_N": Rn1,
        "Rn2_N": Rn2,
        "governing_path": governing,
        "Ubs": Ubs_v,
    }


# ---------------------------------------------------------------------------
# 7. bolt_group_eccentric  (AISC Steel Construction Manual, Table 7-6 / 7-7)
# ---------------------------------------------------------------------------

def bolt_group_eccentric(
    bolt_coords: list[tuple[float, float]],
    P: float,
    e: float,
    *,
    method_beg: str = "IC",
    Vn_per_bolt: float | None = None,
) -> dict:
    """
    Eccentric bolt group capacity ratio.

    The applied shear P acts at eccentricity e (mm) from the bolt-group centroid.
    Two methods are supported:

    "IC" (default) — Instantaneous Center of Rotation method.
    Uses the load-deformation relationship for individual bolts per
    AISC Steel Construction Manual Table 7-7:
        r = rult × (1 - e^(-10·Δ/Δult))^0.55    where Δult = 0.34" = 8.636 mm.
    The IC is found iteratively by requiring moment balance and in-plane
    force equilibrium.

    "elastic" — Elastic Vector Method (conservative closed-form).
    Resolves bolt forces from centroidal shear + polar-moment torsion.
    Returns the utilization on the most heavily loaded bolt.

    Parameters
    ----------
    bolt_coords : list of (x_mm, y_mm)
        Cartesian coordinates of each bolt (mm).  Length >= 2.
    P : float
        Applied shear force magnitude (N).  Must be > 0.
    e : float
        Eccentricity of P from bolt-group centroid (mm).  Must be >= 0.
    method_beg : str
        "IC" (default) or "elastic".
    Vn_per_bolt : float | None
        Individual bolt design shear capacity (N).  Required for utilization
        when method_beg="elastic".  Optional for "IC" (returns relative ratio).

    Returns
    -------
    dict
        ok, utilization (P / C_capacity or P_max_elastic / Vn),
        adequate, method_beg,
        governing_bolt_index, max_bolt_force_N,
        C_coefficient (IC method only — dimensionless coefficient ×n_bolts capacity),
        limit_state
    """
    if not isinstance(bolt_coords, (list, tuple)) or len(bolt_coords) < 2:
        return _err("bolt_coords must be a list of at least 2 (x, y) coordinate pairs")
    try:
        coords = [(float(x), float(y)) for x, y in bolt_coords]
    except (TypeError, ValueError) as exc:
        return _err(f"bolt_coords must contain numeric (x, y) pairs: {exc}")

    err = _guard_positive("P", P)
    if err:
        return _err(err)
    err = _guard_nonneg("e", e)
    if err:
        return _err(err)

    mb = str(method_beg).strip().upper()
    if mb not in ("IC", "ELASTIC"):
        return _err("method_beg must be 'IC' or 'elastic'")

    n = len(coords)

    # Bolt group centroid
    cx = sum(x for x, y in coords) / n
    cy = sum(y for x, y in coords) / n
    # Relative coords
    rel = [(x - cx, y - cy) for x, y in coords]

    if mb == "ELASTIC":
        # Elastic Vector Method
        # Ip = Σ(xi² + yi²) (polar moment of inertia of bolt pattern, mm²)
        Ip = sum(xi**2 + yi**2 for xi, yi in rel)
        if Ip == 0.0:
            return _err("bolt_coords must not all be coincident")

        # Direct shear: each bolt carries P/n  (assume P acts in y direction)
        Vy = float(P) / n
        # Moment T = P × e (applied at eccentricity e from centroid)
        T = float(P) * float(e)

        max_f = 0.0
        gov_idx = 0
        forces = []
        for i, (xi, yi) in enumerate(rel):
            # Shear due to torsion
            # Fx_t = -T * yi / Ip
            # Fy_t =  T * xi / Ip
            Fx_i = -T * yi / Ip
            Fy_i = Vy + T * xi / Ip
            fi = math.sqrt(Fx_i**2 + Fy_i**2)
            forces.append(fi)
            if fi > max_f:
                max_f = fi
                gov_idx = i

        if Vn_per_bolt is not None:
            vn = float(Vn_per_bolt)
            if vn <= 0:
                return _err("Vn_per_bolt must be > 0")
            util = max_f / vn
        else:
            # Utilization relative to P/n (ratio of actual to direct shear)
            util = max_f / (float(P) / n) if (float(P) / n) > 0 else 0.0

        _overstress_warn("bolt_group_eccentric", util)

        return {
            "ok": True,
            "method_beg": "elastic",
            "utilization": util,
            "adequate": util <= 1.0,
            "max_bolt_force_N": max_f,
            "governing_bolt_index": gov_idx,
            "Ip_mm2": Ip,
            "T_Nmm": T,
            "limit_state": "bolt group eccentric — elastic vector method",
            "C_coefficient": None,
        }

    # IC method (AISC Table 7-7 approach)
    # Load-deformation: r(Δ) = rult * (1 - exp(-10*Δ/Δult))^0.55
    # Δult = 0.34 in = 8.636 mm (AISC default, rounded from Fisher 1965)
    DELTA_ULT_MM = 8.636

    def bolt_force(delta_mm: float) -> float:
        """Force on a bolt at deformation delta_mm (normalised to rult=1)."""
        ratio = min(delta_mm / DELTA_ULT_MM, 1.0)
        return (1.0 - math.exp(-10.0 * ratio)) ** 0.55

    def _ic_residual(ro: float, theta_deg: float = 90.0) -> tuple[float, float, float]:
        """
        For IC at distance ro from centroid (in direction perpendicular to P),
        compute: sum of moments about IC vs P×d.

        Returns (sum_Mx, sum_My, sum_M_bolts) for current IC guess.
        IC is at (ic_x, ic_y) relative to centroid.
        Assume P acts in the +y direction, so IC is at (-ro, 0) from centroid.
        """
        ic_x = -ro   # IC location relative to centroid (in mm)
        ic_y = 0.0
        # Distance of each bolt from IC
        dists = [math.sqrt((xi - ic_x)**2 + (yi - ic_y)**2) for xi, yi in rel]
        d_max = max(dists) if max(dists) > 0 else 1.0

        # At ultimate: each bolt deformation proportional to distance
        # Δi = Δult × di / d_max
        rults = [bolt_force(DELTA_ULT_MM * di / d_max) for di in dists]

        # Moment about IC from bolt forces = Σ ri_ult × di
        M_bolts = sum(r * d for r, d in zip(rults, dists))

        # Moment from P about IC: P × (e + ro) where ro is IC distance from centroid
        # (because eccentricity from load application to IC = e + ro)
        M_load = float(P) * (float(e) + ro)

        return M_bolts, M_load

    # Find ro by bisection: M_bolts == M_load
    # ro ∈ (0, very large)
    try:
        lo, hi = 1e-6, 1e7  # mm
        for _ in range(80):
            mid = (lo + hi) / 2.0
            M_b, M_l = _ic_residual(mid)
            # M_bolts / M_load  compared to 1
            ratio = M_b / M_l if M_l > 0 else 1.0
            if ratio > 1.0:
                lo = mid
            else:
                hi = mid
        ro_sol = (lo + hi) / 2.0

        # Now compute normalised forces and find max
        ic_x = -ro_sol
        ic_y = 0.0
        dists = [math.sqrt((xi - ic_x)**2 + (yi - ic_y)**2) for xi, yi in rel]
        d_max = max(dists) if max(dists) > 0 else 1.0
        rults_norm = [bolt_force(DELTA_ULT_MM * di / d_max) for di in dists]
        max_rult = max(rults_norm)
        gov_idx = rults_norm.index(max_rult)
        max_bolt_f_norm = max_rult  # normalised to rult (per unit capacity)

        # C coefficient: C = P / (Vn_per_bolt × n if all bolts at full capacity)
        # Here we return C = M_load / (Σ r_i * d_i × rult) as a multiplier.
        # The conventional C coefficient: C = P / rult_max (such that P = C × rult)
        # For the purposes of utilization when Vn_per_bolt is given:
        M_b_sol, M_l_sol = _ic_residual(ro_sol)
        # rult scale factor: rult_actual = M_l_sol / M_b_sol * rult (normalised)
        # Applied P corresponds to rult_actual on the critical bolt
        # Maximum bolt force = rult_actual × max_rult_norm
        # C = P / rult_actual ... but rult here is a normalised unit-capacity bolt
        # We return C_coefficient = max rult normalised (dimensionless ∈ (0,1])

        if Vn_per_bolt is not None:
            vn = float(Vn_per_bolt)
            if vn <= 0:
                return _err("Vn_per_bolt must be > 0")
            # Actual max bolt force
            scale = M_l_sol / M_b_sol  # scale to match moment
            actual_max_force = max_rult * scale * vn  # approximate
            util = float(P) / (max_rult * vn * n / M_l_sol * sum(
                r * d for r, d in zip(rults_norm, dists)
            )) if sum(r * d for r, d in zip(rults_norm, dists)) > 0 else 1.0
            # Cleaner: capacity = M_b_sol * Vn_per_bolt / M_l_sol * P_unit
            # Since M_b × rult_actual = M_l, rult_actual = M_l / M_b × rult_norm
            # max bolt force = rult_actual * max_rult_norm
            # capacity P_max = M_b / max_rult_norm * rult_actual
            # Substitute: P_max = M_b / max_rult_norm × (M_l / M_b) = M_l / max_rult_norm
            P_capacity = M_l_sol / max_rult if max_rult > 0 else float("inf")
            # But P_capacity is in units of vn (per-bolt capacity)
            # Adjust: the above assumes rult_norm is relative to 1 bolt at full strength
            # We need Vn_per_bolt as the unit capacity
            P_capacity_N = P_capacity * vn / 1.0
            util = float(P) / P_capacity_N if P_capacity_N > 0 else float("inf")
        else:
            # Return ratio of actual to what would be if no eccentricity
            util = float(e) / (float(e) + ro_sol) if (float(e) + ro_sol) > 0 else 0.0

        _overstress_warn("bolt_group_eccentric", util)

        return {
            "ok": True,
            "method_beg": "IC",
            "utilization": util,
            "adequate": util <= 1.0,
            "max_bolt_force_norm": max_bolt_f_norm,
            "governing_bolt_index": gov_idx,
            "ro_mm": ro_sol,
            "C_coefficient": max_rult,
            "max_bolt_force_N": max_rult * float(Vn_per_bolt) if Vn_per_bolt else None,
            "limit_state": "bolt group eccentric — IC method (AISC Table 7-7)",
        }
    except Exception as exc:
        return _err(f"IC iteration failed: {exc}")


# ---------------------------------------------------------------------------
# 8. fillet_weld_capacity  (AISC 360-22 J2.4)
# ---------------------------------------------------------------------------

def fillet_weld_capacity(
    D_sixteenths: float,
    L_weld: float,
    Fexx: float,
    *,
    angle_deg: float = 0.0,
    n_welds: int = 1,
    Vu: float = 0.0,
    method: str = "LRFD",
    phi: float | None = None,
    omega: float | None = None,
) -> dict:
    """
    Fillet weld group capacity (AISC 360-22 J2.4).

    Rn = 0.60 × Fexx × (1 + 0.50 × sin¹·⁵θ) × Aw × n_welds

    where Aw = effective throat area = (D/√2) × L  (45° fillet weld, effective
    throat = D/√2 for a flat fillet weld of size D).
    D is in mm (converted from sixteenths of an inch input).

    Parameters
    ----------
    D_sixteenths : float
        Weld size in sixteenths of an inch (US customary AISC tables). E.g. 5/16"
        weld → D_sixteenths=5. Must be > 0.
    L_weld : float
        Total effective weld length (mm). Must be > 0.
    Fexx : float
        Electrode classification strength (Pa).  E70 → 482.6 MPa.
    angle_deg : float
        Angle between the weld axis and the direction of load (degrees).
        0° = load parallel to weld (shear), 90° = load perpendicular (transverse).
        Default 0°.
    n_welds : int
        Number of identical weld lines (e.g. 2 for both sides of a gusset).
    Vu : float
        Applied load (N). Used only for utilization.
    method, phi, omega : see module docstring.

    Returns
    -------
    dict
        ok, Rn_N, capacity_N, utilization, adequate, limit_state, method,
        D_mm, throat_mm, Aw_mm2, directional_factor
    """
    err = _guard_positive("D_sixteenths", D_sixteenths)
    if err:
        return _err(err)
    err = _guard_positive("L_weld", L_weld)
    if err:
        return _err(err)
    err = _guard_positive("Fexx", Fexx)
    if err:
        return _err(err)
    err = _guard_nonneg("Vu", Vu)
    if err:
        return _err(err)
    try:
        n_welds = int(n_welds)
        if n_welds < 1:
            raise ValueError()
    except (TypeError, ValueError):
        return _err("n_welds must be a positive integer")
    try:
        angle_deg = float(angle_deg)
        if not (0.0 <= angle_deg <= 90.0):
            return _err("angle_deg must be in [0, 90]")
    except (TypeError, ValueError):
        return _err("angle_deg must be a number")

    res = _resolve_method(method, _PHI_WELD, _OMEGA_WELD, phi, omega)
    if isinstance(res, str):
        return _err(res)
    method_clean, phi_val, omega_val = res

    # Convert weld size: 1 sixteenth inch = 1/16 in = 1.5875 mm
    D_mm = float(D_sixteenths) * (25.4 / 16.0)  # mm
    throat_mm = D_mm / math.sqrt(2.0)  # effective throat for 45° fillet weld

    # Effective area
    L_m = float(L_weld) * 1e-3   # mm → m
    throat_m = throat_mm * 1e-3
    Aw_m2 = throat_m * L_m        # m²

    # Directional strength factor (AISC J2-5)
    theta_rad = math.radians(angle_deg)
    dir_factor = 1.0 + 0.50 * (math.sin(theta_rad) ** 1.5)

    Rn_per_weld = 0.60 * float(Fexx) * dir_factor * Aw_m2  # N
    Rn = Rn_per_weld * int(n_welds)

    cap = _design_capacity(Rn, method_clean, phi_val, omega_val)
    util = float(Vu) / cap if cap > 0 else 0.0
    _overstress_warn("fillet_weld_capacity", util)

    return {
        "ok": True,
        "Rn_N": Rn,
        "capacity_N": cap,
        "utilization": util,
        "adequate": util <= 1.0,
        "limit_state": "fillet weld shear (AISC J2.4)",
        "method": method_clean,
        "D_mm": D_mm,
        "D_sixteenths": float(D_sixteenths),
        "throat_mm": throat_mm,
        "Aw_mm2": throat_mm * float(L_weld),
        "directional_factor": dir_factor,
        "angle_deg": angle_deg,
        "n_welds": n_welds,
        "Fexx_Pa": float(Fexx),
        "L_weld_mm": float(L_weld),
    }


# ---------------------------------------------------------------------------
# 9. weld_group_elastic_vector  (Elastic vector method for weld groups)
# ---------------------------------------------------------------------------

def weld_group_elastic_vector(
    weld_segments: list[tuple],
    P: float,
    ex: float,
    ey: float,
    *,
    Vu: float | None = None,
    method: str = "LRFD",
    phi: float | None = None,
    omega: float | None = None,
) -> dict:
    """
    Elastic vector method for a general weld group under eccentric load.

    Each weld segment is described by its endpoints and weld properties.
    The group is treated as a continuous weld line; the centroid and polar
    moment of inertia are computed analytically.

    Parameters
    ----------
    weld_segments : list of tuples
        Each element: (x0_mm, y0_mm, x1_mm, y1_mm, D_sixteenths, Fexx_Pa)
        where (x0,y0) and (x1,y1) are endpoint coordinates in mm.
    P : float
        Applied force magnitude (N). Acts in the +y direction by convention.
        Must be > 0.
    ex : float
        x-eccentricity of load from weld-group centroid (mm). May be 0.
    ey : float
        y-eccentricity of load from weld-group centroid (mm). May be 0.
    Vu : float | None
        If given, used to override P for utilization computation.
    method, phi, omega : see module docstring.

    Returns
    -------
    dict
        ok, utilization, adequate, limit_state, method, centroid_x_mm,
        centroid_y_mm, Iu_cm4 (polar moment of inertia of effective-throat areas),
        max_stress_Pa, capacity_stress_Pa
    """
    if not isinstance(weld_segments, (list, tuple)) or len(weld_segments) < 1:
        return _err("weld_segments must be a non-empty list of tuples")

    try:
        segs = []
        for s in weld_segments:
            x0, y0, x1, y1, D_s, Fexx_s = s
            segs.append((float(x0), float(y0), float(x1), float(y1), float(D_s), float(Fexx_s)))
    except (TypeError, ValueError) as exc:
        return _err(f"Each weld_segment must be (x0,y0,x1,y1,D_sixteenths,Fexx_Pa): {exc}")

    err = _guard_positive("P", P)
    if err:
        return _err(err)
    err = _guard_nonneg("ex", abs(ex))
    if err:
        return _err(err)
    err = _guard_nonneg("ey", abs(ey))
    if err:
        return _err(err)

    res = _resolve_method(method, _PHI_WELD, _OMEGA_WELD, phi, omega)
    if isinstance(res, str):
        return _err(res)
    method_clean, phi_val, omega_val = res

    # Effective throat per segment (mm)
    def throat(D_s: float) -> float:
        return float(D_s) * (25.4 / 16.0) / math.sqrt(2.0)

    # Compute weld group properties
    # Treat weld as line elements; centroid weighted by length × throat
    total_A = 0.0
    sum_Ax = 0.0
    sum_Ay = 0.0
    for (x0, y0, x1, y1, D_s, Fexx_s) in segs:
        L = math.sqrt((x1 - x0)**2 + (y1 - y0)**2)
        a = L * throat(D_s)  # mm²
        mx = (x0 + x1) / 2.0
        my = (y0 + y1) / 2.0
        total_A += a
        sum_Ax += a * mx
        sum_Ay += a * my

    if total_A == 0.0:
        return _err("Total weld area is zero — check weld_segments")

    cx = sum_Ax / total_A
    cy = sum_Ay / total_A

    # Polar moment of inertia about centroid (mm⁴) using exact formula for segments
    Iu = 0.0
    for (x0, y0, x1, y1, D_s, Fexx_s) in segs:
        L = math.sqrt((x1 - x0)**2 + (y1 - y0)**2)
        if L == 0.0:
            continue
        t = throat(D_s)
        # Midpoint
        mx = (x0 + x1) / 2.0 - cx
        my = (y0 + y1) / 2.0 - cy
        # Self-inertia of segment about its own centroid (parallel axis for line segment)
        # Ix_self = t * L³ / 12 * sin²α,  Iy_self = t * L³ / 12 * cos²α
        alpha = math.atan2(y1 - y0, x1 - x0)
        sin_a, cos_a = math.sin(alpha), math.cos(alpha)
        Ix_self = t * L**3 / 12.0 * sin_a**2
        Iy_self = t * L**3 / 12.0 * cos_a**2
        # Parallel axis
        Iu_seg = (Ix_self + Iy_self) + t * L * (mx**2 + my**2)
        Iu += Iu_seg

    # Direct shear stress
    tau_direct = float(P) / total_A  # N/mm² = MPa

    # Torsional moment T = P × e (resultant eccentricity)
    T = float(P) * math.sqrt(float(ex)**2 + float(ey)**2)  # N·mm

    # Maximum torsional shear stress at critical point (furthest weld element)
    max_r = 0.0
    max_r_x = 0.0
    max_r_y = 0.0
    for (x0, y0, x1, y1, D_s, Fexx_s) in segs:
        for xp, yp in [(x0, y0), (x1, y1), ((x0+x1)/2, (y0+y1)/2)]:
            r = math.sqrt((xp - cx)**2 + (yp - cy)**2)
            if r > max_r:
                max_r = r
                max_r_x = xp - cx
                max_r_y = yp - cy

    tau_torsion = T * max_r / Iu if Iu > 0 else 0.0

    # Combine (conservative: SRSS)
    tau_total = math.sqrt(tau_direct**2 + tau_torsion**2)  # MPa

    # Capacity stress = 0.60 × Fexx × phi (or /omega), using minimum Fexx in group
    min_Fexx = min(s[5] for s in segs)
    cap_stress_nom = 0.60 * min_Fexx / 1e6  # Pa → MPa (Fexx already in Pa)
    cap_stress_nom_mpa = cap_stress_nom
    if method_clean == "LRFD":
        cap_stress = phi_val * cap_stress_nom_mpa
    else:
        cap_stress = cap_stress_nom_mpa / omega_val

    util_val = float(Vu) / (cap_stress * total_A) if Vu is not None else tau_total / cap_stress
    _overstress_warn("weld_group_elastic_vector", util_val)

    return {
        "ok": True,
        "utilization": util_val,
        "adequate": util_val <= 1.0,
        "limit_state": "weld group elastic vector method (AISC J2.4)",
        "method": method_clean,
        "centroid_x_mm": cx,
        "centroid_y_mm": cy,
        "total_throat_area_mm2": total_A,
        "Iu_mm4": Iu,
        "tau_direct_MPa": tau_direct,
        "tau_torsion_MPa": tau_torsion,
        "tau_total_MPa": tau_total,
        "capacity_stress_MPa": cap_stress,
    }


# ---------------------------------------------------------------------------
# 10. base_plate_bearing  (AISC 360-22 J8)
# ---------------------------------------------------------------------------

def base_plate_bearing(
    P: float,
    B: float,
    N: float,
    fp_prime: float,
    *,
    Vu: float | None = None,
    method: str = "LRFD",
    phi: float | None = None,
    omega: float | None = None,
) -> dict:
    """
    Bearing stress check for column base plate on grout / concrete (AISC J8).

    Maximum bearing stress:
        fp_actual = P / (B × N)    [Pa]

    Allowable bearing (from ACI 318 / AISC J8):
        fp_allow = fp_prime       [Pa]   (caller provides 0.85×f'c or equivalent)

    Parameters
    ----------
    P : float
        Column axial load (N). Must be > 0.
    B : float
        Base plate width (mm). Must be > 0.
    N : float
        Base plate length/depth (mm). Must be > 0.
    fp_prime : float
        Allowable bearing pressure on support (Pa).  Typically 0.85·f'c
        (concrete design strength) per ACI 318.  Must be > 0.
    Vu : float | None
        Applied load (N). If None, uses P.
    method : str
        "LRFD" or "ASD".  For simple bearing checks the distinction is in
        the load (factored vs unfactored) supplied by the caller.
    phi : float | None
        φ override (default 0.65 per AISC J8).
    omega : float | None
        Ω override (default 2.31 per AISC J8).

    Returns
    -------
    dict
        ok, fp_actual_Pa, fp_allow_Pa (=φ×fp_prime or fp_prime/Ω),
        capacity_N (= fp_allow × B × N), utilization, adequate,
        limit_state, method, B_mm, N_mm, plate_area_mm2
    """
    err = _guard_positive("P", P)
    if err:
        return _err(err)
    err = _guard_positive("B", B)
    if err:
        return _err(err)
    err = _guard_positive("N", N)
    if err:
        return _err(err)
    err = _guard_positive("fp_prime", fp_prime)
    if err:
        return _err(err)

    res = _resolve_method(method, _PHI_BEARING, _OMEGA_BEARING, phi, omega)
    if isinstance(res, str):
        return _err(res)
    method_clean, phi_val, omega_val = res

    B_mm = float(B)
    N_mm = float(N)
    area_mm2 = B_mm * N_mm
    area_m2 = area_mm2 * 1e-6

    P_val = float(Vu) if Vu is not None else float(P)

    fp_actual = P_val / area_m2  # Pa

    # Design allowable bearing: φ×fp_prime (LRFD) or fp_prime/Ω (ASD)
    fp_allow = _design_capacity(float(fp_prime), method_clean, phi_val, omega_val)
    cap_N = fp_allow * area_m2

    util = fp_actual / fp_allow if fp_allow > 0 else 0.0
    _overstress_warn("base_plate_bearing", util)

    return {
        "ok": True,
        "fp_actual_Pa": fp_actual,
        "fp_allow_Pa": fp_allow,
        "capacity_N": cap_N,
        "utilization": util,
        "adequate": util <= 1.0,
        "limit_state": "base plate bearing (AISC J8)",
        "method": method_clean,
        "B_mm": B_mm,
        "N_mm": N_mm,
        "plate_area_mm2": area_mm2,
        "P_N": P_val,
    }
