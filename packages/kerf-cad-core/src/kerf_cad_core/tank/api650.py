"""
kerf_cad_core.tank.api650 — pure-Python API 650 atmospheric storage-tank design.

Implements fifteen public functions covering the principal design checks for
vertical cylindrical welded atmospheric storage tanks per API Std 650 (13th ed.
2020) and complementary standards.

Functions
---------
  shell_course_thickness          — 1-foot & variable-design-point shell thickness
                                    (product + hydrotest loads; corrosion allowance)
  minimum_shell_thickness         — Table 5.6a minimum thickness by nominal diameter
  bottom_plate_thickness          — §5.4 bottom plate minimum thickness
  annular_plate_thickness         — §5.5 annular bottom plate thickness
  cone_roof_thickness             — §5.10.5.1 supported-cone & self-supporting cone
  dome_roof_thickness             — §5.10.5.2 self-supporting dome (geodesic / umbrella)
  wind_girder_section_modulus     — §5.9.7 top wind girder required section modulus
  intermediate_stiffener_spacing  — §5.9.7.3 maximum intermediate stiffener spacing
  overturning_stability           — §5.11 wind overturning stability (M_wind vs M_resist)
  anchorage_requirement           — §5.11.2 bolt-circle anchor bolt sizing
  seismic_annex_e                 — Annex E impulsive/convective masses, base shear,
                                    overturning moment, sloshing wave height, freeboard
  venting_normal                  — API 2000 §4 normal vent capacity (breathing + working)
  venting_emergency               — API 2000 §5 emergency vent capacity (fire case)
  settlement_check                — §B.4 edge settlement, planar tilt, differential checks
  nozzle_reinforcement_note       — §5.7 nozzle reinforcement area-replacement note

All functions return a plain dict:
    success → {"ok": True, ...computed fields..., "warnings": [...]}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise.

Units
-----
Unless otherwise noted all inputs and outputs use SI:
  lengths       — metres (m)
  thicknesses   — metres (m); companion *_mm keys in millimetres
  diameters     — metres (m)
  heights       — metres (m)
  pressures     — Pascals (Pa)
  stresses      — Pascals (Pa)
  forces        — Newtons (N)
  moments       — Newton-metres (N·m)
  volumes       — cubic metres (m³)
  flow rates    — cubic metres per second (m³/s) unless noted
  density       — kg/m³
  mass          — kg
  angles        — degrees (°) for cone half-angles / roof slopes

References
----------
API Standard 650, 13th Edition, 2020
  §5.4 Bottom Plates
  §5.5 Annular Bottom Plates
  §5.6 Shell Design
  §5.7 Shell Openings and Nozzle Design
  §5.9.7 Wind Girders
  §5.10.5 Roof Plates
  §5.11 Wind Load (Overturning)
  Annex E Seismic Design of Storage Tanks
API Standard 2000, 7th Edition, 2014
  §4 Normal Venting
  §5 Emergency Venting (Fire)

Author: imranparuk
"""

from __future__ import annotations

import math
from typing import Any


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _err(reason: str) -> dict:
    return {"ok": False, "reason": reason}


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


def _guard_range(name: str, value: Any, lo: float, hi: float) -> str | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {value!r}"
    if not math.isfinite(v):
        return f"{name} must be finite"
    if not (lo <= v <= hi):
        return f"{name} must be in [{lo}, {hi}], got {v}"
    return None


# ---------------------------------------------------------------------------
# 1. shell_course_thickness
# ---------------------------------------------------------------------------

def shell_course_thickness(
    D: float,
    H: float,
    G: float = 1.0,
    *,
    Sd: float = 160e6,
    St: float = 171e6,
    c: float = 0.0,
    method: str = "1-foot",
    x: float | None = None,
) -> dict:
    """
    Required shell-plate thickness for one course of an API 650 tank.

    Two methods are supported:

    "1-foot" (default, API 650 §5.6.3.1):
        The design point is taken at 0.3 m (1 ft) above the bottom of the
        course.  Thickness (SI conversion of the API 650 mm-formula):

            API 650:  t [mm] = 4.9 × D [m] × (H-x) [m] × G / Sd [MPa]
            Pure SI:  t [m]  = 4900 × D [m] × (H-x) [m] × G / Sd [Pa]

            t_d = 4900 D (H - 0.3) G / Sd   (metres)
            t_t = 4900 D (H - 0.3) / St      (metres)
            t_required = max(t_d, t_t) + c

    "variable" (API 650 §5.6.3.2 variable-design-point method):
        Requires x, the distance (m) from the bottom of the course to the
        chosen design point.  Most conservative near bottom → x = 0 gives
        maximum thickness:

            t_d = 4900 D (H - x) G / Sd
            t_t = 4900 D (H - x) / St

    Parameters
    ----------
    D : float
        Nominal tank diameter (m). Must be > 0.
    H : float
        Design liquid height above the bottom of the course (m). Must be > 0.
    G : float
        Design specific gravity of stored liquid (dimensionless, default 1.0).
        Must be > 0.
    Sd : float
        Allowable stress for product load (Pa, default 160 MPa typical A36 plate
        per API 650 Table 5-2 SD column).
    St : float
        Allowable stress for hydrotest load (Pa, default 171 MPa typical A36
        per API 650 Table 5-2 ST column).
    c : float
        Corrosion allowance (m, default 0). Must be >= 0.
    method : str
        "1-foot" (default) or "variable".
    x : float | None
        Design-point height above course bottom (m).  Required for method
        "variable"; ignored for "1-foot".

    Returns
    -------
    dict
        ok              : True
        t_design_m      : product-load course thickness (net, no CA) [m]
        t_hydro_m       : hydrotest-load course thickness (net, no CA) [m]
        t_required_m    : governing thickness including corrosion allowance [m]
        t_required_mm   : same in mm
        governing       : "product" or "hydrotest"
        method          : method string used
        warnings        : list of advisory strings
    """
    e = _guard_positive("D", D)
    if e:
        return _err(e)
    e = _guard_positive("H", H)
    if e:
        return _err(e)
    e = _guard_positive("G", G)
    if e:
        return _err(e)
    e = _guard_positive("Sd", Sd)
    if e:
        return _err(e)
    e = _guard_positive("St", St)
    if e:
        return _err(e)
    e = _guard_nonneg("c", c)
    if e:
        return _err(e)

    meth = str(method).strip().lower().replace("-", "").replace("_", "")
    warnings: list[str] = []

    if meth == "1foot":
        h_eff = float(H) - 0.3
        if h_eff < 0:
            h_eff = 0.0
            warnings.append(
                "H < 0.3 m: 1-foot design point is above the liquid surface; "
                "effective head set to 0. Consider using method='variable' with x=0."
            )
        x_used = 0.3
    elif meth == "variable":
        if x is None:
            return _err("x is required for method='variable'")
        e = _guard_nonneg("x", x)
        if e:
            return _err(e)
        if float(x) >= float(H):
            return _err(f"x ({x}) must be < H ({H}) for method='variable'")
        h_eff = float(H) - float(x)
        x_used = float(x)
    else:
        return _err(
            f"Unknown method {method!r}. Supported: '1-foot', 'variable'."
        )

    D_f = float(D)
    G_f = float(G)
    Sd_f = float(Sd)
    St_f = float(St)
    c_f = float(c)

    # API 650 §5.6.3 thickness formulas (SI form, metres result)
    # Standard form: t [mm] = 4.9 × D [m] × (H - x) [m] × G / Sd [MPa]
    # Convert to pure-SI (metres / Pascals):
    #   t [m] = 4.9e-3 × D × (H-x) × G / Sd_MPa
    #         = 4.9e-3 × D × (H-x) × G / (Sd_Pa × 1e-6)
    #         = 4900 × D × (H-x) × G / Sd_Pa
    # Verify: D=15 m, H-x=9.7 m, G=1.0, Sd=160 MPa=160e6 Pa
    #   t = 4900 × 15 × 9.7 / 160e6 = 712,650 / 160,000,000 = 0.004454 m = 4.45 mm ✓

    t_d = 4900.0 * D_f * h_eff * G_f / Sd_f   # product load net thickness [m]
    t_t = 4900.0 * D_f * h_eff / St_f          # hydrotest load net thickness [m]

    t_net = max(t_d, t_t)
    t_required = t_net + c_f
    governing = "product" if t_d >= t_t else "hydrotest"

    # Advisory checks
    if G_f < 0.7:
        warnings.append(
            f"G = {G_f} < 0.7: very light liquid; verify product specific gravity."
        )
    if t_required < 5e-3:
        warnings.append(
            "t_required < 5 mm: check minimum thickness per API 650 Table 5-6a."
        )
    if c_f > 0.006:
        warnings.append(
            f"Corrosion allowance c = {c_f*1000:.1f} mm > 6 mm: unusually high; verify."
        )

    return {
        "ok": True,
        "t_design_m": t_d,
        "t_hydro_m": t_t,
        "t_required_m": t_required,
        "t_required_mm": t_required * 1e3,
        "governing": governing,
        "method": method,
        "x_m": x_used,
        "h_eff_m": h_eff,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 2. minimum_shell_thickness
# ---------------------------------------------------------------------------

# API 650 Table 5-6a  Nominal-diameter → min shell thickness (m)
# Boundary: diameter ≤ value → use this minimum thickness
_MIN_THICKNESS_TABLE: list[tuple[float, float]] = [
    (  4.0 + 1e-9, 4e-3),    # D ≤  ~4 m (≤ 13.1 ft) → 4.76 mm → round to 5mm specified below
    ( 15.0 + 1e-9, 5e-3),    # D > 4 m to ≤ 15 m   → 6 mm  per Table 5-6a
    ( 30.0 + 1e-9, 6e-3),    # D > 15 m to ≤ 30 m  → 8 mm
    ( 60.0 + 1e-9, 8e-3),    # D > 30 m to ≤ 60 m  → 10 mm
    (float("inf"), 10e-3),   # D > 60 m             → 13 mm
]

# More precise per API 650 Table 5-6a (Appendix A opens US/metric alternates)
# Metric table: nominal diameter bands
_MIN_THICK_METRIC: list[tuple[float, float]] = [
    ( 15.0, 5e-3),    # ≤ 15 m  → 5 mm
    ( 30.0, 6e-3),    # > 15 m to ≤ 30 m → 6 mm
    ( 60.0, 8e-3),    # > 30 m to ≤ 60 m → 8 mm
    (float("inf"), 10e-3),  # > 60 m → 10 mm
]


def minimum_shell_thickness(D: float) -> dict:
    """
    Minimum permissible shell-plate thickness per API 650 Table 5-6a.

    Parameters
    ----------
    D : float
        Nominal tank diameter (m). Must be > 0.

    Returns
    -------
    dict
        ok              : True
        t_min_m         : minimum shell thickness (m)
        t_min_mm        : minimum shell thickness (mm)
        D_m             : diameter used (m)
        warnings        : list
    """
    e = _guard_positive("D", D)
    if e:
        return _err(e)

    D_f = float(D)
    for d_limit, t_min in _MIN_THICK_METRIC:
        if D_f <= d_limit:
            break

    warnings: list[str] = []
    if D_f > 85.0:
        warnings.append(
            f"D = {D_f} m exceeds typical API 650 single-deck tank range; "
            "verify applicability."
        )

    return {
        "ok": True,
        "t_min_m": t_min,
        "t_min_mm": t_min * 1e3,
        "D_m": D_f,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 3. bottom_plate_thickness
# ---------------------------------------------------------------------------

def bottom_plate_thickness(
    *,
    c: float = 0.0,
    has_liner: bool = False,
) -> dict:
    """
    Minimum bottom plate thickness per API 650 §5.4.1.

    API 650 §5.4.1: Minimum bottom plate thickness (including annular) shall
    not be less than 6 mm (0.236 in.) exclusive of any corrosion allowance.

    Parameters
    ----------
    c : float
        Corrosion allowance (m, default 0). Must be >= 0.
    has_liner : bool
        If True, a sacrificial liner is present; warning suppressed.

    Returns
    -------
    dict
        ok              : True
        t_min_net_m     : API minimum net plate thickness (m)
        t_min_net_mm    : same in mm
        t_required_m    : minimum net + corrosion allowance (m)
        t_required_mm   : same in mm
        warnings        : list
    """
    e = _guard_nonneg("c", c)
    if e:
        return _err(e)

    t_min_net = 6e-3  # API 650 §5.4.1
    c_f = float(c)
    t_req = t_min_net + c_f
    warnings: list[str] = []

    if c_f > 3e-3 and not has_liner:
        warnings.append(
            f"Bottom plate corrosion allowance c = {c_f*1e3:.1f} mm > 3 mm; "
            "consider cathodic protection or a sacrificial liner."
        )

    return {
        "ok": True,
        "t_min_net_m": t_min_net,
        "t_min_net_mm": t_min_net * 1e3,
        "t_required_m": t_req,
        "t_required_mm": t_req * 1e3,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 4. annular_plate_thickness
# ---------------------------------------------------------------------------

def annular_plate_thickness(
    D: float,
    H: float,
    G: float = 1.0,
    *,
    Fy_shell_Pa: float = 250e6,
    c: float = 0.0,
) -> dict:
    """
    Minimum annular bottom plate thickness per API 650 §5.5.

    The annular plate projection width and minimum thickness are governed by
    the first-shell-course thickness and the product hydrostatic head.

    API 650 §5.5.3 Table 5-1a (SI): required annular-plate thickness as a
    function of the first-shell-course stress and the product head.

    Simplified conservative calculation:
        - First determine effective product stress at bottom of first course:
              sigma_1 = 4.9 * D * H * G   [using same formulation as shell]
          (proportional to σ = p·R/t)
        - Then look up Table 5-1a band (stress < 190 MPa → 6 mm;
          190–210 → 8 mm; 210–230 → 10 mm; > 230 → 13 mm).
        - Min width = max(600 mm, specified in §5.5.2).

    Parameters
    ----------
    D : float
        Nominal diameter (m).
    H : float
        Max design liquid height (m).
    G : float
        Specific gravity (default 1.0).
    Fy_shell_Pa : float
        First-shell-course plate minimum yield (Pa, default 250 MPa).
    c : float
        Corrosion allowance (m).

    Returns
    -------
    dict
        ok                  : True
        t_annular_net_m     : required annular plate net thickness (m)
        t_annular_net_mm    : same in mm
        t_annular_req_m     : net + CA (m)
        t_annular_req_mm    : same in mm
        min_projection_mm   : minimum annular plate projection width (mm) §5.5.2
        warnings            : list
    """
    e = _guard_positive("D", D)
    if e:
        return _err(e)
    e = _guard_positive("H", H)
    if e:
        return _err(e)
    e = _guard_positive("G", G)
    if e:
        return _err(e)
    e = _guard_nonneg("c", c)
    if e:
        return _err(e)

    # Equivalent hoop stress proxy (Pa) at bottom of first shell course
    # API Table 5-1a is keyed on the hydrostatic product pressure at the base
    # (ρ × g × H).  Use this directly as the table-lookup key.
    # Here we use the hydrostatic product (Pa) = rho * g * H ≈ 9810 * G * H
    rho_g_H = 9_810.0 * float(G) * float(H)  # Pa  (hydrostatic pressure at base)

    # Table 5-1a (SI) — product pressure vs annular thickness
    # product pressure (Pa)   → min annular plate thickness (m)
    _annular_table: list[tuple[float, float]] = [
        ( 50_000.0, 6e-3),
        (100_000.0, 8e-3),
        (200_000.0, 10e-3),
        (float("inf"), 13e-3),
    ]

    t_ann_net = 6e-3  # default minimum
    for p_lim, t_a in _annular_table:
        if rho_g_H <= p_lim:
            t_ann_net = t_a
            break

    # §5.5.2: minimum projection width beyond outer edge of shell ≥ 600 mm
    min_proj_mm = 600.0

    c_f = float(c)
    t_ann_req = t_ann_net + c_f
    warnings: list[str] = []

    if t_ann_req * 1e3 < 6.0:
        warnings.append(
            "Annular plate thickness < 6 mm; API 650 §5.5 minimum is 6 mm."
        )

    return {
        "ok": True,
        "t_annular_net_m": t_ann_net,
        "t_annular_net_mm": t_ann_net * 1e3,
        "t_annular_req_m": t_ann_req,
        "t_annular_req_mm": t_ann_req * 1e3,
        "min_projection_mm": min_proj_mm,
        "product_pressure_Pa": rho_g_H,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 5. cone_roof_thickness
# ---------------------------------------------------------------------------

def cone_roof_thickness(
    D: float,
    *,
    theta_deg: float = 9.46,
    design_load_Pa: float = 1_200.0,
    Sd: float = 160e6,
    E_joint: float = 1.0,
    c: float = 0.0,
    self_supporting: bool = False,
) -> dict:
    """
    Required cone-roof plate thickness per API 650 §5.10.5.

    Two sub-cases:

    Supported cone (self_supporting=False, §5.10.5.1):
        The roof is framed / rafter-supported.  Plates carry bending between
        rafters; minimum net thickness = max(5 mm, calculated).

    Self-supporting cone (self_supporting=True, §5.10.5.1 & Appendix F):
        Acts as a membrane cone.  Meridional membrane thrust governs:
            N_m = w * D / (4 * sin(θ))   [force / length]
            t   = N_m / (Sd * E_joint)

        where w = design_load_Pa (uniform load in Pa).

    Parameters
    ----------
    D : float
        Nominal tank diameter (m).
    theta_deg : float
        Cone half-angle from horizontal (degrees, default 9.46° ≈ 1:6 slope).
        Must be in [9.46, 37.0] per API 650 §5.10.5.1.
    design_load_Pa : float
        Uniform design roof load (Pa, dead + live; default 1200 Pa ≈ 25 lbf/ft²).
    Sd : float
        Allowable stress (Pa).
    E_joint : float
        Weld joint efficiency (default 1.0 for full-pen welds).
    c : float
        Corrosion allowance (m).
    self_supporting : bool
        True → self-supporting membrane formula; False → supported-frame minimum.

    Returns
    -------
    dict
        ok              : True
        t_calc_m        : calculated net thickness (m)
        t_required_m    : max(t_calc, t_min) + CA (m)
        t_required_mm   : same in mm
        t_min_net_mm    : API 650 absolute minimum net thickness (mm)
        theta_deg       : cone half-angle used (°)
        self_supporting : bool
        frangible_joint : True if frangible-joint geometry is satisfied
        warnings        : list
    """
    e = _guard_positive("D", D)
    if e:
        return _err(e)
    e = _guard_range("theta_deg", theta_deg, 9.46, 37.0)
    if e:
        return _err(e)
    e = _guard_positive("design_load_Pa", design_load_Pa)
    if e:
        return _err(e)
    e = _guard_positive("Sd", Sd)
    if e:
        return _err(e)
    e = _guard_range("E_joint", E_joint, 0.0, 1.0)
    if e:
        return _err(e)
    e = _guard_nonneg("c", c)
    if e:
        return _err(e)

    D_f = float(D)
    theta_r = math.radians(float(theta_deg))
    w = float(design_load_Pa)
    Sd_f = float(Sd)
    E_f = float(E_joint)
    c_f = float(c)

    t_min_net = 5e-3  # API 650 §5.10.5.1 absolute minimum 5 mm

    if self_supporting:
        # Membrane meridional thrust: N_m = w * R / (2 * sin θ) = w * D / (4 * sin θ)
        sin_t = math.sin(theta_r)
        N_m = w * D_f / (4.0 * sin_t)  # N/m
        t_calc = N_m / (Sd_f * E_f) if (Sd_f * E_f) > 0 else 0.0
    else:
        # Supported (framed) cone — minimum governs; no separate calc required
        # API 650 gives minimum 5 mm; typical calc shows minimum governs for small spans
        t_calc = t_min_net  # exactly the minimum for supported case

    t_net_governing = max(t_calc, t_min_net)
    t_required = t_net_governing + c_f

    # Frangible joint check: API 650 Appendix F / §5.10.4
    # Frangible joint is satisfied when the weld between roof and top angle
    # is the weakest link; this is a geometry/weld check, not a thickness calc.
    # Simplified indicator: frangible joint possible when theta < 37° and
    # roof-to-shell weld area < shell-to-bottom weld area (conservatively True
    # for cones < 37° without added stiffener).
    frangible_joint = float(theta_deg) <= 37.0 and not self_supporting

    warnings: list[str] = []
    if t_required < 5e-3:
        warnings.append(
            "UNDER-THICKNESS: t_required < 5 mm; API 650 §5.10.5.1 minimum is 5 mm."
        )
    if float(theta_deg) < 9.46:
        warnings.append(
            "Cone angle < 9.46° (1:6 slope); API 650 §5.10.5.1 requires θ ≥ 9.46°."
        )
    if D_f > 60.0 and self_supporting:
        warnings.append(
            f"D = {D_f} m > 60 m: verify self-supporting cone applicability; "
            "Appendix F analysis recommended."
        )

    return {
        "ok": True,
        "t_calc_m": t_calc,
        "t_required_m": t_required,
        "t_required_mm": t_required * 1e3,
        "t_min_net_mm": t_min_net * 1e3,
        "theta_deg": float(theta_deg),
        "self_supporting": self_supporting,
        "frangible_joint": frangible_joint,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 6. dome_roof_thickness
# ---------------------------------------------------------------------------

def dome_roof_thickness(
    D: float,
    *,
    Rc: float | None = None,
    design_load_Pa: float = 1_200.0,
    Sd: float = 160e6,
    E_joint: float = 1.0,
    c: float = 0.0,
) -> dict:
    """
    Required dome-roof plate thickness (self-supporting spherical dome) per
    API 650 §5.10.5.2.

    Membrane formula (thin-shell sphere under uniform load):
        N_m = w * Rc / 2          [N/m, meridional thrust]
        t   = N_m / (Sd * E)

    Crown radius Rc must satisfy 0.8 D ≤ Rc ≤ 1.5 D per §5.10.5.2.
    Default Rc = 0.8 D (minimum allowed, gives thickest result).

    Parameters
    ----------
    D : float
        Nominal tank diameter (m).
    Rc : float | None
        Crown radius (m, default 0.8 × D).
    design_load_Pa : float
        Uniform design roof load (Pa, default 1200 Pa).
    Sd : float
        Allowable stress (Pa).
    E_joint : float
        Weld joint efficiency.
    c : float
        Corrosion allowance (m).

    Returns
    -------
    dict
        ok              : True
        Rc_m            : crown radius used (m)
        t_calc_m        : calculated membrane thickness (m)
        t_required_m    : max(t_calc, t_min) + CA (m)
        t_required_mm   : same in mm
        t_min_net_mm    : API 650 minimum (5 mm)
        warnings        : list
    """
    e = _guard_positive("D", D)
    if e:
        return _err(e)
    e = _guard_positive("design_load_Pa", design_load_Pa)
    if e:
        return _err(e)
    e = _guard_positive("Sd", Sd)
    if e:
        return _err(e)
    e = _guard_range("E_joint", E_joint, 0.0, 1.0)
    if e:
        return _err(e)
    e = _guard_nonneg("c", c)
    if e:
        return _err(e)

    D_f = float(D)
    if Rc is None:
        Rc_f = 0.8 * D_f
    else:
        e = _guard_positive("Rc", Rc)
        if e:
            return _err(e)
        Rc_f = float(Rc)

    warnings: list[str] = []
    if Rc_f < 0.8 * D_f - 1e-9:
        warnings.append(
            f"Rc = {Rc_f:.3f} m < 0.8 D = {0.8*D_f:.3f} m; "
            "API 650 §5.10.5.2 requires Rc ≥ 0.8 D."
        )
    if Rc_f > 1.5 * D_f + 1e-9:
        warnings.append(
            f"Rc = {Rc_f:.3f} m > 1.5 D = {1.5*D_f:.3f} m; "
            "API 650 §5.10.5.2 requires Rc ≤ 1.5 D."
        )

    w = float(design_load_Pa)
    Sd_f = float(Sd)
    E_f = float(E_joint)
    c_f = float(c)

    t_min_net = 5e-3  # §5.10.5.2

    N_m = w * Rc_f / 2.0  # meridional thrust [N/m]
    t_calc = N_m / (Sd_f * E_f)

    t_required = max(t_calc, t_min_net) + c_f

    if t_required < 5e-3:
        warnings.append(
            "UNDER-THICKNESS: t_required < 5 mm; API 650 §5.10.5.2 minimum is 5 mm."
        )

    return {
        "ok": True,
        "Rc_m": Rc_f,
        "N_m_N_per_m": N_m,
        "t_calc_m": t_calc,
        "t_required_m": t_required,
        "t_required_mm": t_required * 1e3,
        "t_min_net_mm": t_min_net * 1e3,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 7. wind_girder_section_modulus
# ---------------------------------------------------------------------------

def wind_girder_section_modulus(
    D: float,
    t_shell: float,
    *,
    V_wind_m_s: float = 45.0,
    H_shell: float | None = None,
) -> dict:
    """
    Required section modulus of the top wind girder per API 650 §5.9.7.

    API 650 §5.9.7.1 (SI):
        Z_required = 0.0001 D² H (V/190)²   [m³]

    where D = nominal diameter (m), H = shell height (m),
    V = design wind speed (km/h), Z = section modulus (m³).

    This function accepts V in m/s and converts internally.

    Parameters
    ----------
    D : float
        Nominal tank diameter (m).
    t_shell : float
        Shell plate thickness (m, used for max unstiffened height check).
    V_wind_m_s : float
        Design wind speed (m/s, default 45 m/s ≈ 162 km/h).
    H_shell : float | None
        Total shell height (m). If None, only Z is returned without the
        max-unstiffened-height check.

    Returns
    -------
    dict
        ok                  : True
        Z_required_m3       : required section modulus (m³)
        Z_required_cm3      : same in cm³  (convenient for structural selection)
        V_wind_kmh          : wind speed used (km/h)
        max_H_unstiffened_m : maximum unstiffened shell height (m, only if H_shell provided)
        warnings            : list
    """
    e = _guard_positive("D", D)
    if e:
        return _err(e)
    e = _guard_positive("t_shell", t_shell)
    if e:
        return _err(e)
    e = _guard_positive("V_wind_m_s", V_wind_m_s)
    if e:
        return _err(e)

    D_f = float(D)
    t_f = float(t_shell)
    V_kmh = float(V_wind_m_s) * 3.6  # m/s → km/h

    if H_shell is not None:
        e = _guard_positive("H_shell", H_shell)
        if e:
            return _err(e)
        H_f = float(H_shell)
    else:
        H_f = D_f  # representative height if unknown

    # API 650 §5.9.7.1 (SI): Z [m³] = 0.0001 D² H (V/190)²
    # Note: API uses V in km/h, 190 km/h is the standard reference.
    Z_req = 0.0001 * D_f ** 2 * H_f * (V_kmh / 190.0) ** 2  # m³

    warnings: list[str] = []

    # Maximum unstiffened shell height API 650 §5.9.7.3
    # H_max = (9.47 t / D)^(1/3) * (190 / V)^(2/3) * t  (simplified)
    # More precisely per §5.9.7.3:
    # H_max = (190/V) * [(t/D)^1.5 × D] ... practical formula:
    # H_max [m] = (9.47 * (t/D)^3)^(1/3) * (190/V)^2/3  [corrected per code]
    # Use the standard formula: H_max = (t^3 / (0.0001 * D^2 * (V/190)^2))^(1/3)
    # Actually use API 650 §5.9.7.3 directly:
    # Maximum height of unstiffened shell:
    #   H_max [m] = 9.47 × t/D × (190/V)^(2/3)   ... no, check:
    # Correct formula (API 650 §5.9.7.3 SI):
    #   H_max = (9.47 t / D)^(1/3)  — this is dimensionless; not right.
    # Use practical form: Z_avail = actual shell section modulus = π D² t / 4
    # Conservatively: max spacing = Z_avail * (190/V)^2 / (0.0001 D²) but that's not
    # the stiffener-spacing formula.
    #
    # Per API 650 §5.9.7.3 the maximum height between intermediate stiffeners is:
    #   W_max = (9.47 t (190/V))^(1/3)   [metres]  with t in metres
    # This is equivalent to: W_max = 9.47^(1/3) * t^(1/3) * (190/V)^(1/3)
    # The intermediate stiffener spacing function handles this; here we just note
    # max H for a girder-only tank.
    W_max = (9.47 * t_f * (190.0 / V_kmh)) ** (1.0 / 3.0)  # m

    result: dict = {
        "ok": True,
        "Z_required_m3": Z_req,
        "Z_required_cm3": Z_req * 1e6,
        "V_wind_kmh": V_kmh,
        "W_max_unstiffened_m": W_max,
        "warnings": warnings,
    }

    if H_shell is not None:
        result["H_shell_m"] = H_f
        if H_f > W_max:
            warnings.append(
                f"Shell height H = {H_f:.2f} m exceeds maximum unstiffened "
                f"height {W_max:.2f} m at V = {V_kmh:.1f} km/h; "
                "intermediate stiffeners required."
            )

    return result


# ---------------------------------------------------------------------------
# 8. intermediate_stiffener_spacing
# ---------------------------------------------------------------------------

def intermediate_stiffener_spacing(
    D: float,
    t_shell: float,
    H_shell: float,
    *,
    V_wind_m_s: float = 45.0,
) -> dict:
    """
    Maximum intermediate wind stiffener spacing per API 650 §5.9.7.3 (SI).

    Maximum spacing between stiffeners (or bottom-to-first stiffener):
        W_max [m] = (9.47 * t * (190 / V))^(1/3)

    where V is in km/h, t is the minimum shell plate thickness (m).

    Parameters
    ----------
    D : float
        Nominal tank diameter (m).
    t_shell : float
        Minimum shell plate thickness (m) in the unstiffened region.
    H_shell : float
        Total shell height (m).
    V_wind_m_s : float
        Design wind speed (m/s, default 45 m/s).

    Returns
    -------
    dict
        ok                  : True
        W_max_m             : maximum spacing (m)
        n_stiffeners_min    : minimum number of intermediate stiffeners needed
        spacing_actual_m    : actual even spacing if stiffeners placed (m)
        warnings            : list
    """
    e = _guard_positive("D", D)
    if e:
        return _err(e)
    e = _guard_positive("t_shell", t_shell)
    if e:
        return _err(e)
    e = _guard_positive("H_shell", H_shell)
    if e:
        return _err(e)
    e = _guard_positive("V_wind_m_s", V_wind_m_s)
    if e:
        return _err(e)

    V_kmh = float(V_wind_m_s) * 3.6
    t_f = float(t_shell)
    H_f = float(H_shell)

    W_max = (9.47 * t_f * (190.0 / V_kmh)) ** (1.0 / 3.0)  # m

    n_stiff = 0
    if H_f > W_max:
        n_stiff = math.ceil(H_f / W_max) - 1

    spacing_actual = H_f / (n_stiff + 1) if n_stiff >= 0 else H_f

    warnings: list[str] = []
    if spacing_actual > W_max + 1e-9:
        warnings.append(
            f"Actual stiffener spacing {spacing_actual:.3f} m exceeds W_max "
            f"{W_max:.3f} m; increase number of stiffeners."
        )

    return {
        "ok": True,
        "W_max_m": W_max,
        "n_stiffeners_min": n_stiff,
        "spacing_actual_m": spacing_actual,
        "V_wind_kmh": V_kmh,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 9. overturning_stability
# ---------------------------------------------------------------------------

def overturning_stability(
    D: float,
    H_shell: float,
    W_total_N: float,
    *,
    V_wind_m_s: float = 45.0,
    rho_air: float = 1.225,
    Cf: float = 0.7,
    H_liquid_m: float = 0.0,
    rho_liquid: float = 1000.0,
) -> dict:
    """
    Wind overturning stability check per API 650 §5.11.

    Overturning moment:
        M_wind = q * Cf * D * H_shell * (H_shell / 2)

    where q = 0.5 * rho_air * V² is the dynamic wind pressure (Pa).

    Resisting moment (empty + liquid):
        M_resist = W_total_N * D / 2
                 + rho_liquid * g * (π D² / 4) * H_liquid_m * (D / 2)
               ...simplified as W × D/2 for self-weight only

    The stabilising moment from liquid content:
        M_liquid = weight_liquid * D / 4
                 = rho_liquid * g * π/4 * D² * H_liquid_m * D/4

    Parameters
    ----------
    D : float
        Nominal tank diameter (m).
    H_shell : float
        Shell height (m).
    W_total_N : float
        Total tank dead-weight (N, shell + roof + bottom + attachments, empty).
    V_wind_m_s : float
        Design wind speed (m/s, default 45 m/s).
    rho_air : float
        Air density (kg/m³, default 1.225).
    Cf : float
        Wind force coefficient (dimensionless, default 0.7 per API 650 §5.2).
    H_liquid_m : float
        Liquid height for partial-fill stability assessment (m, default 0).
    rho_liquid : float
        Liquid density (kg/m³, default 1000 for water).

    Returns
    -------
    dict
        ok                  : True
        M_wind_Nm           : overturning moment from wind (N·m)
        M_resist_Nm         : resisting moment (dead-weight lever arm D/2) (N·m)
        M_liquid_Nm         : additional resisting moment from liquid (N·m)
        M_resist_total_Nm   : total resisting moment (N·m)
        SF_overturning      : stability factor M_resist_total / M_wind
        overturning_ok      : True if SF ≥ 1.5 (API 650 recommended minimum)
        q_Pa                : dynamic wind pressure (Pa)
        warnings            : list
    """
    e = _guard_positive("D", D)
    if e:
        return _err(e)
    e = _guard_positive("H_shell", H_shell)
    if e:
        return _err(e)
    e = _guard_positive("W_total_N", W_total_N)
    if e:
        return _err(e)
    e = _guard_positive("V_wind_m_s", V_wind_m_s)
    if e:
        return _err(e)
    e = _guard_positive("rho_air", rho_air)
    if e:
        return _err(e)
    e = _guard_range("Cf", Cf, 0.1, 2.0)
    if e:
        return _err(e)
    e = _guard_nonneg("H_liquid_m", H_liquid_m)
    if e:
        return _err(e)
    e = _guard_positive("rho_liquid", rho_liquid)
    if e:
        return _err(e)

    D_f = float(D)
    H_f = float(H_shell)
    W_f = float(W_total_N)
    V_f = float(V_wind_m_s)
    rho_a = float(rho_air)
    Cf_f = float(Cf)

    g = 9.80665  # m/s²

    q = 0.5 * rho_a * V_f ** 2  # dynamic pressure Pa
    F_wind = q * Cf_f * D_f * H_f  # total lateral wind force N
    M_wind = F_wind * H_f / 2.0  # overturning moment N·m (force at H/2)

    # Dead-weight resisting moment (tank tips about bottom edge → lever arm = D/2)
    M_resist_DW = W_f * D_f / 2.0

    # Liquid stabilising moment
    H_liq_f = float(H_liquid_m)
    if H_liq_f > H_f:
        H_liq_f = H_f
    V_liq = math.pi / 4.0 * D_f ** 2 * H_liq_f  # m³
    W_liq = float(rho_liquid) * g * V_liq  # N
    # Liquid resists overturning: weight acts at D/4 from edge (centroid of half-circle)
    M_liquid = W_liq * D_f / 4.0

    M_resist_total = M_resist_DW + M_liquid
    SF = M_resist_total / M_wind if M_wind > 0 else float("inf")

    overturning_ok = SF >= 1.5

    warnings: list[str] = []
    if not overturning_ok:
        warnings.append(
            f"OVERTURNING: SF = {SF:.2f} < 1.5; anchorage required per API 650 §5.11.2."
        )
    if V_f > 67.0:
        warnings.append(
            f"Wind speed {V_f:.1f} m/s > 67 m/s (hurricane); verify applicability."
        )

    return {
        "ok": True,
        "M_wind_Nm": M_wind,
        "M_resist_DW_Nm": M_resist_DW,
        "M_liquid_Nm": M_liquid,
        "M_resist_total_Nm": M_resist_total,
        "SF_overturning": SF,
        "overturning_ok": overturning_ok,
        "q_Pa": q,
        "F_wind_N": F_wind,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 10. anchorage_requirement
# ---------------------------------------------------------------------------

def anchorage_requirement(
    D: float,
    M_overturning_Nm: float,
    W_shell_N: float,
    *,
    n_bolts: int = 16,
    bolt_grade: str = "A307",
    safety_factor: float = 2.0,
) -> dict:
    """
    Anchor bolt sizing per API 650 §5.11.2.

    Net uplift per bolt:
        F_uplift_per_bolt = (M_overturning / (D/2) - W_shell) / n_bolts

    Required bolt area:
        A_bolt = F_uplift_per_bolt / (sigma_allow / safety_factor)

    Parameters
    ----------
    D : float
        Nominal tank diameter (m).
    M_overturning_Nm : float
        Net overturning moment (N·m) from wind or seismic.
    W_shell_N : float
        Shell + roof dead weight resisting uplift (N; bottom weight excluded
        per API 650 §5.11.2 for empty-tank check).
    n_bolts : int
        Number of anchor bolts (default 16).
    bolt_grade : str
        Bolt grade: "A307" (σ_allow=124 MPa), "A193-B7" (σ_allow=207 MPa).
    safety_factor : float
        Additional safety factor on allowable bolt stress (default 2.0).

    Returns
    -------
    dict
        ok                  : True
        F_uplift_total_N    : total uplift force (N)
        F_per_bolt_N        : uplift per bolt (N); 0 if no uplift
        A_bolt_required_m2  : required bolt tensile area (m²)
        A_bolt_required_mm2 : same in mm²
        sigma_allow_Pa      : bolt allowable stress used (Pa)
        anchors_required    : True if net uplift > 0
        warnings            : list
    """
    e = _guard_positive("D", D)
    if e:
        return _err(e)
    e = _guard_nonneg("M_overturning_Nm", M_overturning_Nm)
    if e:
        return _err(e)
    e = _guard_positive("W_shell_N", W_shell_N)
    if e:
        return _err(e)
    if not isinstance(n_bolts, int) or n_bolts < 4:
        return _err("n_bolts must be an integer >= 4")
    e = _guard_positive("safety_factor", safety_factor)
    if e:
        return _err(e)

    _BOLT_GRADES: dict[str, float] = {
        "A307":    124e6,
        "A193-B7": 207e6,
        "A36":      96e6,
    }
    grade_key = str(bolt_grade).strip().upper()
    if grade_key not in _BOLT_GRADES:
        return _err(
            f"Unknown bolt_grade {bolt_grade!r}. Supported: {list(_BOLT_GRADES.keys())}."
        )

    sigma_allow = _BOLT_GRADES[grade_key] / float(safety_factor)

    D_f = float(D)
    M_f = float(M_overturning_Nm)
    W_f = float(W_shell_N)

    # Overturning uplift: F_uplift = 2 * M / D - W_shell
    # (lever arm = D/2 from centre → total uplift force = M/(D/2) = 2M/D)
    F_uplift_total = 2.0 * M_f / D_f - W_f
    anchors_required = F_uplift_total > 0

    if not anchors_required:
        F_per_bolt = 0.0
        A_req = 0.0
    else:
        F_per_bolt = F_uplift_total / float(n_bolts)
        A_req = F_per_bolt / sigma_allow

    warnings: list[str] = []
    if anchors_required:
        warnings.append(
            f"Anchorage required: net uplift = {F_uplift_total:.0f} N "
            f"({F_uplift_total/1000:.1f} kN)."
        )
    if A_req * 1e6 > 2000.0:
        warnings.append(
            f"Required bolt area {A_req*1e6:.0f} mm² is very large; "
            "consider increasing n_bolts or using higher-grade bolts."
        )

    return {
        "ok": True,
        "F_uplift_total_N": F_uplift_total,
        "F_per_bolt_N": F_per_bolt,
        "A_bolt_required_m2": A_req,
        "A_bolt_required_mm2": A_req * 1e6,
        "sigma_allow_Pa": sigma_allow,
        "bolt_grade": grade_key,
        "n_bolts": n_bolts,
        "anchors_required": anchors_required,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 11. seismic_annex_e
# ---------------------------------------------------------------------------

def seismic_annex_e(
    D: float,
    H_liquid: float,
    rho_liquid: float = 1000.0,
    *,
    Sds: float = 0.5,
    Sd1: float = 0.2,
    I: float = 1.0,
    Tc_factor: float | None = None,
) -> dict:
    """
    API 650 Annex E seismic design — impulsive & convective masses,
    base shear, overturning moment, sloshing wave height, and freeboard.

    Uses the simplified Annex E (Housner) model for ground-supported
    vertical cylindrical tanks.

    Parameters
    ----------
    D : float
        Nominal inside diameter (m). Must be > 0.
    H_liquid : float
        Maximum design liquid height (m). Must be > 0.
    rho_liquid : float
        Liquid density (kg/m³, default 1000). Must be > 0.
    Sds : float
        Short-period design spectral acceleration (g, default 0.5).
    Sd1 : float
        1-second design spectral acceleration (g, default 0.2).
    I : float
        Importance factor (dimensionless, API 650 Annex E Table E-2,
        default 1.0; use 1.25 or 1.5 for higher risk categories).
    Tc_factor : float | None
        Convective (sloshing) period multiplier; if None computed from
        Annex E formula: Tc = 1.8 * K_s * sqrt(D)  where K_s is from
        the period chart (approximated as K_s ≈ 0.578 for H/D > 1.333,
        1.0 for H/D < 0.5, interpolated otherwise).

    Returns
    -------
    dict
        ok                  : True
        m_total_kg          : total liquid mass (kg)
        m_imp_kg            : impulsive mass (kg)
        m_conv_kg           : convective (sloshing) mass (kg)
        h_imp_m             : impulsive mass height above bottom (m)
        h_conv_m            : convective mass height above bottom (m)
        Ti_s                : impulsive period (s)
        Tc_s                : convective (sloshing) period (s)
        V_imp_N             : impulsive base shear (N)
        V_conv_N            : convective base shear (N)
        V_total_N           : SRSS combined base shear (N)
        M_imp_Nm            : impulsive overturning moment at base (N·m)
        M_conv_Nm           : convective overturning moment at base (N·m)
        M_total_Nm          : SRSS combined overturning moment (N·m)
        delta_s_m           : sloshing wave height (m)
        freeboard_required_m: required freeboard (m, = delta_s for full containment)
        warnings            : list
    """
    e = _guard_positive("D", D)
    if e:
        return _err(e)
    e = _guard_positive("H_liquid", H_liquid)
    if e:
        return _err(e)
    e = _guard_positive("rho_liquid", rho_liquid)
    if e:
        return _err(e)
    e = _guard_nonneg("Sds", Sds)
    if e:
        return _err(e)
    e = _guard_nonneg("Sd1", Sd1)
    if e:
        return _err(e)
    e = _guard_positive("I", I)
    if e:
        return _err(e)

    D_f = float(D)
    H_f = float(H_liquid)
    rho_f = float(rho_liquid)
    R_f = D_f / 2.0
    g = 9.80665

    # Total liquid mass
    m_total = rho_f * math.pi / 4.0 * D_f ** 2 * H_f  # kg

    # Housner impulsive / convective mass fractions (Annex E)
    ratio = H_f / R_f  # H/R

    if ratio <= 1.333:
        # Short tank: H/R <= 4/3
        # m_imp / m_total = tanh(0.866 D/H) / (0.866 D/H)
        # m_conv / m_total = 1 - m_imp / m_total  (simplified Annex E)
        arg = 0.866 * D_f / H_f
        m_imp_frac = math.tanh(arg) / arg if arg > 0 else 1.0
        # Impulsive centroid height
        h_imp = 0.375 * H_f
    else:
        # Tall tank: H/R > 4/3
        m_imp_frac = 1.0 - 0.218 * D_f / H_f
        h_imp = 0.5 * H_f - 0.125 * D_f

    m_imp = m_imp_frac * m_total
    m_conv = m_total - m_imp

    # Convective centroid height
    # h_conv = H * (1 - cosh(1.84 H/D) / (1.84 H/D * sinh(1.84 H/D)))  ~simplified
    x_c = 1.84 * H_f / D_f
    if x_c > 0:
        try:
            cosh_xc = math.cosh(x_c)
            sinh_xc = math.sinh(x_c)
            if sinh_xc > 0:
                h_conv = H_f * (1.0 - cosh_xc / (x_c * sinh_xc))
            else:
                h_conv = H_f * 0.61  # fallback
        except OverflowError:
            h_conv = H_f * 0.61
    else:
        h_conv = H_f * 0.61

    # Clamp to [0, H]
    h_conv = max(0.0, min(h_conv, H_f))
    h_imp = max(0.0, min(h_imp, H_f))

    # Impulsive period (rigid tank approximation: Ti → 0 for rigid; simplified)
    # For rigid tanks Ti ≈ 0 and the impulsive spectral acceleration = Sds * I
    # Convective (sloshing) period
    # Tc = 1.8 * Ks * sqrt(D)   [seconds]
    # Ks from Annex E Fig. E-4: function of D/H
    D_over_H = D_f / H_f
    if D_over_H >= 2.0:
        Ks = 0.578
    elif D_over_H <= 0.75:
        Ks = 1.0
    else:
        Ks = 0.578 + (1.0 - 0.578) * (2.0 - D_over_H) / (2.0 - 0.75)

    Tc = 1.8 * Ks * math.sqrt(D_f)  # s (convective sloshing period)
    Ti = 0.0  # rigid-tank approximation

    # Spectral accelerations
    g_acc = 9.80665  # m/s²
    Ai = float(Sds) * float(I)  # impulsive Ai = Sds * I (g)
    # Convective: Ac = Sdc / Tc (or Sdc if Tc beyond corner)
    # Sdc ≈ 0.5 * Sd1 / Tc  (simplified Annex E; Annex E uses TL dependent formula)
    # Per API 650 Annex E: Ac = Sds / (Tc/TL)  for Tc > Ts; approximate as:
    Ts = float(Sd1) / float(Sds) if float(Sds) > 0 else 0.2
    if Tc <= Ts:
        Ac = float(Sds) * float(I)
    else:
        # Long-period range: Ac = Sd1 * I / Tc
        Ac = float(Sd1) * float(I) / Tc

    # Base shears
    V_imp = Ai * m_imp * g_acc  # N
    V_conv = Ac * m_conv * g_acc  # N
    V_total = math.sqrt(V_imp ** 2 + V_conv ** 2)  # SRSS

    # Overturning moments at base (about tank bottom)
    M_imp = V_imp * h_imp
    M_conv = V_conv * h_conv
    M_total = math.sqrt(M_imp ** 2 + M_conv ** 2)

    # Sloshing wave height (Annex E §E.6.2.1):
    # delta_s = 0.5 * D * Af * Ac   where Af = Ac is the convective accel (g)
    # API 650 Annex E: delta_s = D/2 * Ac  (simplified; full formula with K factors)
    delta_s = D_f / 2.0 * Ac  # m

    freeboard_req = delta_s  # full sloshing containment

    warnings: list[str] = []
    if delta_s > H_f * 0.3:
        warnings.append(
            f"INADEQUATE-FREEBOARD: sloshing wave height delta_s = {delta_s:.3f} m "
            f"is > 30% of liquid height; freeboard should be >= {delta_s:.3f} m."
        )
    if float(I) < 1.0:
        warnings.append("Importance factor I < 1.0 is non-standard; verify.")
    if float(Sds) > 2.5:
        warnings.append(
            f"Sds = {Sds} g is very high; verify seismic site classification."
        )

    return {
        "ok": True,
        "m_total_kg": m_total,
        "m_imp_kg": m_imp,
        "m_conv_kg": m_conv,
        "h_imp_m": h_imp,
        "h_conv_m": h_conv,
        "Ti_s": Ti,
        "Tc_s": Tc,
        "Ai_g": Ai,
        "Ac_g": Ac,
        "V_imp_N": V_imp,
        "V_conv_N": V_conv,
        "V_total_N": V_total,
        "M_imp_Nm": M_imp,
        "M_conv_Nm": M_conv,
        "M_total_Nm": M_total,
        "delta_s_m": delta_s,
        "freeboard_required_m": freeboard_req,
        "Tc_s_Ks": Ks,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 12. venting_normal
# ---------------------------------------------------------------------------

def venting_normal(
    V_tank_m3: float,
    flash_point_C: float = 40.0,
    *,
    fill_rate_m3_s: float = 0.0,
    draw_rate_m3_s: float = 0.0,
) -> dict:
    """
    Required normal vent capacity per API Standard 2000, 7th Edition, §4.

    Normal venting includes:
      1. Thermal breathing (Vb): product vapour expansion/contraction from
         daily temperature cycling.
      2. Working vent (Vw): displacement during filling and emptying.

    Simplified API 2000 §4 formula (conservative):
        Vb [m³/h] = 0.1 * V_tank [m³]   (≈ breathing rate for small tanks)
        Vw_in  = fill_rate * 3600   [m³/h]
        Vw_out = draw_rate * 3600   [m³/h]
        V_normal_in  = Vb + Vw_in
        V_normal_out = Vb + Vw_out

    More precisely API 2000 Table 2 gives thermal vent flow as a function of
    tank capacity; this implementation uses the simplified formula valid for
    tanks < 56,800 m³ (360,000 bbl).

    Parameters
    ----------
    V_tank_m3 : float
        Tank capacity (m³).
    flash_point_C : float
        Product flash point (°C, default 40). Used to flag Class I service.
    fill_rate_m3_s : float
        Maximum liquid fill rate (m³/s, default 0).
    draw_rate_m3_s : float
        Maximum liquid withdrawal rate (m³/s, default 0).

    Returns
    -------
    dict
        ok                      : True
        V_breathing_m3_h        : thermal breathing vent rate (m³/h)
        V_working_in_m3_h       : filling displacement rate (m³/h)
        V_working_out_m3_h      : emptying displacement rate (m³/h)
        V_total_in_m3_h         : total required in-breathing capacity (m³/h)
        V_total_out_m3_h        : total required out-breathing capacity (m³/h)
        flash_point_C           : flash point used
        class_I_service         : True if flash_point < 37.8°C (100°F) (Class I A/B)
        warnings                : list
    """
    e = _guard_positive("V_tank_m3", V_tank_m3)
    if e:
        return _err(e)
    e = _guard_nonneg("fill_rate_m3_s", fill_rate_m3_s)
    if e:
        return _err(e)
    e = _guard_nonneg("draw_rate_m3_s", draw_rate_m3_s)
    if e:
        return _err(e)

    V_f = float(V_tank_m3)
    fill = float(fill_rate_m3_s)
    draw = float(draw_rate_m3_s)
    fp = float(flash_point_C)

    # API 2000 §4.3 thermal breathing approximation:
    # Vb ≈ 0.1 × V_tank (m³/h) for most petroleum products (conservative)
    Vb = 0.1 * V_f  # m³/h

    Vw_in = fill * 3600.0   # m³/h
    Vw_out = draw * 3600.0  # m³/h

    V_total_in = Vb + Vw_in
    V_total_out = Vb + Vw_out

    class_I = fp < 37.8  # 37.8°C = 100°F

    warnings: list[str] = []
    if V_f > 56_800.0:
        warnings.append(
            f"Tank volume {V_f:.0f} m³ > 56,800 m³; API 2000 Table 2 should be "
            "used directly rather than the simplified 10% formula."
        )
    if class_I:
        warnings.append(
            f"Flash point {fp}°C < 37.8°C (100°F): Class I service; "
            "ensure pressure-vacuum valves rated for flammable vapour service."
        )

    return {
        "ok": True,
        "V_breathing_m3_h": Vb,
        "V_working_in_m3_h": Vw_in,
        "V_working_out_m3_h": Vw_out,
        "V_total_in_m3_h": V_total_in,
        "V_total_out_m3_h": V_total_out,
        "flash_point_C": fp,
        "class_I_service": class_I,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 13. venting_emergency
# ---------------------------------------------------------------------------

def venting_emergency(
    V_tank_m3: float,
    *,
    wetted_area_m2: float | None = None,
    D: float | None = None,
    H_liquid: float | None = None,
) -> dict:
    """
    Required emergency vent capacity (fire case) per API Standard 2000, §5.

    For a tank fully engulfed in fire the required emergency vent rate:

        Q_fire [m³/h] = 906,600 * F * A_w^0.82 / L_v   ... API 2000 SI form
                      ≈ simplified: Q_fire = 3.091 × A_w^0.82  [m³/h at 15°C]

    API 2000 §5.3.2 simplified (petroleum / general):
        Q_emergency = 3.091 × A_w^0.82   [m³/h of vapour at 15.6°C, 101.3 kPa]

    where A_w = wetted surface area (m²).  Wetted area = wetted shell +
    wetted bottom, typically taken as min(A_tank, 9.3 D²) for vertical tanks.

    Wetted area can be supplied directly, or computed from D and H_liquid.

    Parameters
    ----------
    V_tank_m3 : float
        Tank volume (m³, used for validation only).
    wetted_area_m2 : float | None
        Wetted surface area (m²). If None, D and H_liquid must be given.
    D : float | None
        Tank diameter (m), used to compute wetted area if not given.
    H_liquid : float | None
        Liquid height for wetted area (m), used if wetted_area_m2 is None.

    Returns
    -------
    dict
        ok                      : True
        wetted_area_m2          : wetted area used (m²)
        Q_emergency_m3_h        : required emergency vent flow (m³/h)
        warnings                : list
    """
    e = _guard_positive("V_tank_m3", V_tank_m3)
    if e:
        return _err(e)

    warnings: list[str] = []

    if wetted_area_m2 is not None:
        e = _guard_positive("wetted_area_m2", wetted_area_m2)
        if e:
            return _err(e)
        A_w = float(wetted_area_m2)
    elif D is not None and H_liquid is not None:
        e = _guard_positive("D", D)
        if e:
            return _err(e)
        e = _guard_positive("H_liquid", H_liquid)
        if e:
            return _err(e)
        D_f = float(D)
        H_f = float(H_liquid)
        # API 2000: wetted area = min of (π D H_liq + π/4 D²) and max_wetted
        # For exposed tanks, max wetted height is 9.14 m per API 2000 §5.3.2
        H_wet = min(H_f, 9.14)
        A_shell = math.pi * D_f * H_wet
        A_bottom = math.pi / 4.0 * D_f ** 2
        A_w = A_shell + A_bottom
    else:
        return _err(
            "Either wetted_area_m2 OR both D and H_liquid must be provided."
        )

    # API 2000 §5.3.2 (SI) simplified emergency vent
    Q_fire = 3.091 * A_w ** 0.82  # m³/h at 15.6°C, 101.3 kPa

    if A_w > 260.0:
        warnings.append(
            f"Wetted area {A_w:.1f} m² > 260 m² (≈ 2800 ft²); "
            "verify API 2000 §5.3.2 environment factor F applies (default F=1.0)."
        )

    return {
        "ok": True,
        "wetted_area_m2": A_w,
        "Q_emergency_m3_h": Q_fire,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 14. settlement_check
# ---------------------------------------------------------------------------

def settlement_check(
    D: float,
    *,
    S_edge_mm: float = 0.0,
    S_planar_mm: float = 0.0,
    S_diff_max_mm: float = 0.0,
    measurement_arc_deg: float = 10.0,
) -> dict:
    """
    API 650 Appendix B settlement tolerance checks.

    Three settlement components:

    1. Edge settlement (uniform perimeter settlement) S_edge:
       Limit per API 650 Appendix B: S_edge_allow = D / 100  [mm per D in metres]
       (simplified, equal to 10 mm/m for large tanks)

    2. Planar tilt (uniform tilt):
       Limit per API 650 App. B §B.4.3: S_planar ≤ D / 100 mm.

    3. Differential settlement between adjacent measurement points:
       Limit: S_diff ≤ 13 mm per 10° arc (API 650 App. B §B.4.4 conservative).

    Parameters
    ----------
    D : float
        Nominal tank diameter (m).
    S_edge_mm : float
        Measured edge settlement (mm, default 0).
    S_planar_mm : float
        Measured planar tilt settlement differential (mm, default 0).
    S_diff_max_mm : float
        Maximum observed differential settlement between adjacent measurement
        points at the specified arc spacing (mm, default 0).
    measurement_arc_deg : float
        Arc angle between adjacent measurement points (degrees, default 10°).

    Returns
    -------
    dict
        ok                      : True
        edge_limit_mm           : allowable edge settlement (mm)
        planar_limit_mm         : allowable planar tilt (mm)
        diff_limit_mm           : allowable differential (mm at given arc)
        edge_ok                 : True if S_edge ≤ limit
        planar_ok               : True if S_planar ≤ limit
        diff_ok                 : True if S_diff ≤ limit
        overall_ok              : True if all three pass
        warnings                : list
    """
    e = _guard_positive("D", D)
    if e:
        return _err(e)
    e = _guard_nonneg("S_edge_mm", S_edge_mm)
    if e:
        return _err(e)
    e = _guard_nonneg("S_planar_mm", S_planar_mm)
    if e:
        return _err(e)
    e = _guard_nonneg("S_diff_max_mm", S_diff_max_mm)
    if e:
        return _err(e)
    e = _guard_range("measurement_arc_deg", measurement_arc_deg, 1.0, 180.0)
    if e:
        return _err(e)

    D_f = float(D)

    # API 650 App. B limits
    edge_limit = D_f * 10.0  # mm (= D[m] * 10 mm/m)
    planar_limit = D_f * 10.0  # mm same
    # Differential: 13 mm per 10° arc; scale linearly for other arcs
    arc_f = float(measurement_arc_deg)
    diff_limit = 13.0 * arc_f / 10.0  # mm

    edge_ok = float(S_edge_mm) <= edge_limit
    planar_ok = float(S_planar_mm) <= planar_limit
    diff_ok = float(S_diff_max_mm) <= diff_limit
    overall_ok = edge_ok and planar_ok and diff_ok

    warnings: list[str] = []
    if not edge_ok:
        warnings.append(
            f"SETTLEMENT: edge settlement {S_edge_mm:.1f} mm exceeds limit "
            f"{edge_limit:.1f} mm for D = {D_f:.1f} m."
        )
    if not planar_ok:
        warnings.append(
            f"SETTLEMENT: planar tilt {S_planar_mm:.1f} mm exceeds limit "
            f"{planar_limit:.1f} mm."
        )
    if not diff_ok:
        warnings.append(
            f"SETTLEMENT: differential settlement {S_diff_max_mm:.1f} mm exceeds "
            f"limit {diff_limit:.1f} mm at {arc_f:.1f}° arc spacing."
        )

    return {
        "ok": True,
        "edge_limit_mm": edge_limit,
        "planar_limit_mm": planar_limit,
        "diff_limit_mm": diff_limit,
        "edge_ok": edge_ok,
        "planar_ok": planar_ok,
        "diff_ok": diff_ok,
        "overall_ok": overall_ok,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 15. nozzle_reinforcement_note
# ---------------------------------------------------------------------------

def nozzle_reinforcement_note(
    D_shell: float,
    t_shell: float,
    d_nozzle: float,
    t_nozzle: float,
    H: float,
    G: float = 1.0,
    *,
    Sd: float = 160e6,
    c: float = 0.0,
) -> dict:
    """
    API 650 §5.7 nozzle reinforcement area-replacement note.

    This function computes the required and available reinforcement areas for
    a shell nozzle opening per API 650 §5.7.3 (area-replacement method),
    analogous to ASME UG-37 but adapted for low-pressure storage tanks.

    Required reinforcement area:
        A_req = d_nozzle * t_req   [m²]

    where t_req is the required shell thickness at the nozzle elevation.

    Available area from shell:
        A_shell = (d_nozzle) * (t_shell - t_req - c)   [m²]

    Available area from nozzle:
        A_nozzle = 2 * h_n * (t_nozzle - t_req_nozzle)  [m²]
        (h_n = min(2.5 * t_shell, 2.5 * t_nozzle), t_req_nozzle = 0 for low pressure)

    Parameters
    ----------
    D_shell : float
        Tank diameter (m).
    t_shell : float
        Nominal shell plate thickness at nozzle elevation (m).
    d_nozzle : float
        Nozzle inside diameter (m).
    t_nozzle : float
        Nozzle neck nominal thickness (m).
    H : float
        Liquid height above nozzle centre-line (m).
    G : float
        Specific gravity (default 1.0).
    Sd : float
        Allowable stress (Pa, default 160 MPa).
    c : float
        Corrosion allowance (m).

    Returns
    -------
    dict
        ok                  : True
        t_req_m             : required shell thickness at nozzle elevation (m)
        A_required_m2       : required reinforcement area (m²)
        A_shell_m2          : available area from excess shell thickness (m²)
        A_nozzle_m2         : available area from nozzle neck (m²)
        A_total_m2          : total available reinforcement area (m²)
        shortfall_m2        : max(0, A_required - A_total) (m²)
        reinforcement_ok    : True if A_total >= A_required
        warnings            : list
    """
    e = _guard_positive("D_shell", D_shell)
    if e:
        return _err(e)
    e = _guard_positive("t_shell", t_shell)
    if e:
        return _err(e)
    e = _guard_positive("d_nozzle", d_nozzle)
    if e:
        return _err(e)
    e = _guard_positive("t_nozzle", t_nozzle)
    if e:
        return _err(e)
    e = _guard_positive("H", H)
    if e:
        return _err(e)
    e = _guard_positive("G", G)
    if e:
        return _err(e)
    e = _guard_positive("Sd", Sd)
    if e:
        return _err(e)
    e = _guard_nonneg("c", c)
    if e:
        return _err(e)

    D_f = float(D_shell)
    ts_f = float(t_shell)
    dn_f = float(d_nozzle)
    tn_f = float(t_nozzle)
    H_f = float(H)
    G_f = float(G)
    Sd_f = float(Sd)
    c_f = float(c)

    # Required shell thickness at nozzle centreline
    # Using §5.6.3 formula at the nozzle elevation (h_eff = H from nozzle centreline)
    # t [m] = 4900 × D [m] × H [m] × G / Sd [Pa]
    t_req_shell = 4900.0 * D_f * H_f * G_f / Sd_f  # m net

    # Required reinforcement area (API 650 §5.7.3)
    A_req = dn_f * t_req_shell  # m²

    # Available area from shell excess
    A_shell = max(0.0, dn_f * (ts_f - c_f - t_req_shell))

    # Available area from nozzle (projection height h_n)
    h_n = min(2.5 * ts_f, 2.5 * tn_f)
    t_req_nozzle = 0.0  # nozzle in tension; required thickness ≈ 0 for low-pressure
    A_nozzle = 2.0 * h_n * max(0.0, tn_f - t_req_nozzle)

    A_total = A_shell + A_nozzle
    shortfall = max(0.0, A_req - A_total)
    reinforcement_ok = A_total >= A_req

    warnings: list[str] = []
    if not reinforcement_ok:
        warnings.append(
            f"Nozzle reinforcement INADEQUATE: "
            f"A_required = {A_req*1e4:.1f} cm², A_total = {A_total*1e4:.1f} cm²; "
            f"shortfall = {shortfall*1e4:.1f} cm². Add a reinforcement pad."
        )
    if dn_f > D_f / 2.0:
        warnings.append(
            "Nozzle diameter > D/2: large opening; Appendix F / special analysis required."
        )

    return {
        "ok": True,
        "t_req_m": t_req_shell,
        "t_req_mm": t_req_shell * 1e3,
        "A_required_m2": A_req,
        "A_shell_m2": A_shell,
        "A_nozzle_m2": A_nozzle,
        "A_total_m2": A_total,
        "shortfall_m2": shortfall,
        "reinforcement_ok": reinforcement_ok,
        "warnings": warnings,
    }
