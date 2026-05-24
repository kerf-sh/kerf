"""
kerf_cad_core.packaging.design — pure-Python protective-packaging & shipping design.

Distinct from nesting/ (2D cut nesting) and costing/.

Public API
----------

CORRUGATED BOX
  box_compression_strength(ECT, C_f, Z, *, safety_factor, humidity_factor,
                           time_factor, stack_load_N)
      McKee formula: BCT = C_f * ECT * Z^0.5 * t^0.5; safety factor vs
      warehouse stack load; humidity & time derate.

PALLET PATTERN
  pallet_pattern(case_L, case_W, case_H, pallet_L, pallet_W, max_height,
                 *, pattern)
      Column-stack vs interlocked brick-pattern optimisation.  Returns
      cases per layer, layers, cases per pallet, cube utilisation,
      area utilisation.

DIMENSIONAL / VOLUMETRIC WEIGHT & FREIGHT CLASS
  shipping_weight(length_mm, width_mm, height_mm, actual_kg, *,
                  carrier, freight_class_override)
      Dimensional weight (DIM factor 5000 cm³/kg domestic / 6000 int'l),
      chargeable weight, NMFC freight class lookup from density (lb/ft³).

CUSHION DESIGN
  cushion_design(product_weight_kg, drop_height_m, fragility_G,
                 foam_static_stress_kPa, foam_cushion_curve_G,
                 *, bearing_area_cm2, safety_factor)
      Drop height → required velocity change, cushion static stress, cushion
      curve G vs static loading chart → thickness via energy method.
      Flags under-cushioned / fragile-exceeded.

SHOCK & VIBRATION TRANSMISSIBILITY
  shock_transmissibility(fn_Hz, damping_ratio, input_freq_Hz)
      Single-DOF transmissibility T = sqrt((1+(2ζr)²)/((1-r²)²+(2ζr)²)).
      Flags resonance (r ≈ 1).

CONTAINER / ISO-UNIT FILL OPTIMISATION
  container_fill(case_L, case_W, case_H, container_type, *,
                 orientation_permutations)
      TEU / FEU / 20HC internal dims; try all 6 box orientations; return
      best layer × row × column arrangement, utilisation.

STRETCH-WRAP CONTAINMENT
  stretch_wrap(pallet_weight_kg, film_gauge_um, *, revolutions,
               overlap_fraction, pre_stretch_pct)
      Containment force (N) per layer, total for rev count; flag if below
      EUMOS 40509 / ASTM D4169 recommended minimums.

All functions:
  - Return {"ok": True, ...} on success, {"ok": False, "reason": ...} on error.
  - Append human-readable warnings (list[str]) for flagged conditions.
  - NEVER raise.

Units (SI unless noted)
-----------------------
  lengths   — mm (box dims), m (drop height)
  forces    — N
  mass      — kg
  stress    — kPa (cushion), N/m (ECT)
  area      — cm²
  frequency — Hz

References
----------
McKee, R.C. (1963) — Box Compression: A Simple Formula.
TAPPI T804 — Compression Test of Fiberboard Shipping Containers.
ASTM D1596 — Shock-Absorbing Packaging Material; Cushion Curves.
ISTA 2A/2B — Packaged-Product Performance Testing.
EUMOS 40509 — Test Method for Unitised Loads; Containment Force.
NMFC Item 360 — Freight Classification by Density.
ISO 668:2020 — Series 1 Freight Containers — Classification.

Author: imranparuk
"""

from __future__ import annotations

import math
from typing import Any
from kerf_cad_core._guards import _err, _guard_nonneg, _guard_positive


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_FLUTE: dict[str, tuple[float, float]] = {
    "A": (4.8, 1.56),
    "B": (3.0, 1.32),
    "C": (3.6, 1.45),
    "E": (1.6, 1.27),
    "F": (0.8, 1.25),
    "BC": (6.6, 1.45),  # double-wall B+C (approx)
    "EB": (4.6, 1.30),  # double-wall E+B (approx)
}

# NMFC freight density → class table  (density lb/ft³, class)
# Classes defined in 18 tiers; we use the published density thresholds.
_NMFC_DENSITY_CLASS: list[tuple[float, float]] = [
    # (lower density bound lb/ft³, freight class)
    (50.0, 50),
    (35.0, 55),
    (30.0, 60),
    (22.5, 65),
    (15.0, 70),
    (13.5, 77.5),
    (12.0, 85),
    (10.5, 92.5),
    (9.0, 100),
    (8.0, 110),
    (7.0, 125),
    (6.0, 150),
    (5.0, 175),
    (4.0, 200),
    (3.0, 250),
    (2.0, 300),
    (1.0, 400),
    (0.0, 500),
]

# ISO container internal dimensions  (L_mm, W_mm, H_mm, max_payload_kg)
_CONTAINER: dict[str, tuple[float, float, float, float]] = {
    "20GP": (5898.0, 2352.0, 2393.0, 28_180.0),
    "40GP": (12_025.0, 2352.0, 2393.0, 26_680.0),
    "40HC": (12_025.0, 2352.0, 2698.0, 26_330.0),
    "45HC": (13_556.0, 2352.0, 2698.0, 27_600.0),
}


# ---------------------------------------------------------------------------
# 1. Box compression strength — McKee formula
# ---------------------------------------------------------------------------

def box_compression_strength(
    ECT: float,
    C_f: float,
    Z: float,
    *,
    safety_factor: float = 1.0,
    humidity_factor: float = 1.0,
    time_factor: float = 1.0,
    stack_load_N: float | None = None,
    flute: str = "C",
) -> dict:
    """
    McKee formula for corrugated-box compression strength.

    BCT = C_f * ECT * Z^0.5 * t^0.5

    where:
      ECT  — edge-crush test value (N/m; typical C-flute single-wall 3500–7000 N/m)
      C_f  — McKee constant (dimensionless; typically 5.874 for SI, some sources
             use 5.87 imperial — pass the value already in consistent units)
      Z    — box perimeter  (mm → converted internally to m)
      t    — combined board thickness (mm from flute table → m)
      safety_factor       — divide BCT by this to get allowable load (>= 1.0)
      humidity_factor     — fraction ≤ 1.0; 0.60–0.80 typical for high-humidity
                            warehouse (default 1.0 = dry storage)
      time_factor         — fraction ≤ 1.0; long-term stack creep: 0.50 for 30-day
                            typical (default 1.0 = short-term test)
      stack_load_N        — actual warehouse stack load (N); if provided, checks
                            safe BCT >= stack_load_N
      flute               — single-letter flute code for thickness lookup
                            (A / B / C / E / F / BC / EB); default 'C'

    Returns
    -------
    dict
      ok              : True
      BCT_N           : raw McKee BCT (N)
      BCT_derated_N   : BCT after humidity & time derating (N)
      allowable_N     : BCT_derated / safety_factor (N)
      board_thickness_mm : flute thickness (mm)
      safety_factor   : as provided
      stack_overload  : True if allowable_N < stack_load_N (only when stack_load_N given)
      warnings        : list[str]
    """
    err = _guard_positive("ECT", ECT)
    if err:
        return _err(err)
    err = _guard_positive("C_f", C_f)
    if err:
        return _err(err)
    err = _guard_positive("Z", Z)
    if err:
        return _err(err)
    err = _guard_positive("safety_factor", safety_factor)
    if err:
        return _err(err)
    err = _guard_positive("humidity_factor", humidity_factor)
    if err:
        return _err(err)
    err = _guard_positive("time_factor", time_factor)
    if err:
        return _err(err)

    flute_key = str(flute).upper()
    if flute_key not in _FLUTE:
        return _err(
            f"Unknown flute '{flute}'. Supported: {sorted(_FLUTE.keys())}."
        )

    warnings: list[str] = []

    t_mm, _ = _FLUTE[flute_key]
    t_m = t_mm / 1000.0
    Z_m = float(Z) / 1000.0  # perimeter mm → m

    ECT_f = float(ECT)
    C_f_f = float(C_f)

    # McKee formula: BCT = C_f * ECT * (Z * t)^0.5
    BCT = C_f_f * ECT_f * math.sqrt(Z_m * t_m)

    # Derate for humidity and time
    BCT_derated = BCT * float(humidity_factor) * float(time_factor)

    allowable = BCT_derated / float(safety_factor)

    stack_overload = False
    if stack_load_N is not None:
        err2 = _guard_nonneg("stack_load_N", stack_load_N)
        if err2:
            return _err(err2)
        stack_load = float(stack_load_N)
        if allowable < stack_load:
            stack_overload = True
            warnings.append(
                f"STACK-OVERLOAD: allowable BCT {allowable:.1f} N < stack load "
                f"{stack_load:.1f} N — upgrade box spec or reduce stack height."
            )

    if float(humidity_factor) < 0.70:
        warnings.append(
            f"WARNING: humidity_factor={float(humidity_factor):.2f} < 0.70 — "
            "severe moisture environment; consider moisture barrier or waterproof adhesive."
        )
    if float(time_factor) < 0.50:
        warnings.append(
            f"WARNING: time_factor={float(time_factor):.2f} < 0.50 — "
            "very long storage duration; creep may dominate over static strength."
        )
    if float(safety_factor) < 1.5:
        warnings.append(
            f"INFO: safety_factor={float(safety_factor):.2f} < 1.50 — "
            "TAPPI recommends SF ≥ 1.5 for warehouse stacking."
        )

    result: dict = {
        "ok": True,
        "BCT_N": BCT,
        "BCT_derated_N": BCT_derated,
        "allowable_N": allowable,
        "board_thickness_mm": t_mm,
        "safety_factor": float(safety_factor),
        "warnings": warnings,
    }
    if stack_load_N is not None:
        result["stack_overload"] = stack_overload
    return result


# ---------------------------------------------------------------------------
# 2. Pallet pattern optimisation
# ---------------------------------------------------------------------------

def pallet_pattern(
    case_L: float,
    case_W: float,
    case_H: float,
    pallet_L: float,
    pallet_W: float,
    max_height: float,
    *,
    pattern: str = "auto",
    case_weight_kg: float = 0.0,
    max_pallet_kg: float | None = None,
) -> dict:
    """
    Optimise pallet loading for column-stack or interlocked (brick) patterns.

    Parameters
    ----------
    case_L, case_W, case_H : float
        Case outer dimensions (mm).  All must be > 0.
    pallet_L, pallet_W : float
        Pallet deck dimensions (mm).  Both must be > 0.
    max_height : float
        Maximum loaded pallet height including pallet deck (mm).  Must be > 0.
    pattern : str
        'column', 'interlock', or 'auto' (default: tries both, returns best).
    case_weight_kg : float
        Gross case weight (kg).  Used for pallet weight calc (default 0 → skip).
    max_pallet_kg : float | None
        Maximum gross pallet weight (kg).  If given, layers are capped to avoid
        overweight.

    Returns
    -------
    dict
      ok              : True
      pattern_used    : 'column' or 'interlock'
      cases_per_layer : int
      layers          : int
      cases_per_pallet: int
      pallet_weight_kg: float (only if case_weight_kg > 0)
      area_utilisation: float  [0–1]
      cube_utilisation: float  [0–1]
      warnings        : list[str]

    Notes
    -----
    Column pattern: each layer identical orientation (L × W on pallet face).
    Interlock (brick): odd layers rotated 90° for stability.
    Best is the arrangement with the highest cases_per_pallet.
    """
    for name, val in (
        ("case_L", case_L), ("case_W", case_W), ("case_H", case_H),
        ("pallet_L", pallet_L), ("pallet_W", pallet_W), ("max_height", max_height),
    ):
        err = _guard_positive(name, val)
        if err:
            return _err(err)

    pattern_lower = str(pattern).lower().strip()
    if pattern_lower not in ("column", "interlock", "auto"):
        return _err(f"pattern must be 'column', 'interlock', or 'auto'; got {pattern!r}")

    warnings: list[str] = []

    cL = float(case_L)
    cW = float(case_W)
    cH = float(case_H)
    pL = float(pallet_L)
    pW = float(pallet_W)
    mH = float(max_height)

    def _cases_layer(oL: float, oW: float) -> int:
        """Cases per layer for orientation oL × oW on pallet pL × pW."""
        n_a = int(pL / oL)
        n_b = int(pW / oW)
        return n_a * n_b

    def _column_result() -> dict:
        """Column pattern: identical orientation every layer."""
        # Try both orientations; pick the one that gives more cases per layer
        c1 = _cases_layer(cL, cW)
        c2 = _cases_layer(cW, cL)
        cpl = max(c1, c2)
        if cpl == 0:
            return {"cases_per_layer": 0, "layers": 0, "cases": 0, "area": 0.0}
        layers = int(mH / cH)
        if max_pallet_kg and case_weight_kg > 0:
            max_layers_by_weight = int(max_pallet_kg / (cpl * case_weight_kg))
            layers = min(layers, max_layers_by_weight)
        layers = max(layers, 0)
        case_footprint = cL * cW if c1 >= c2 else cW * cL
        orient_L = cL if c1 >= c2 else cW
        orient_W = cW if c1 >= c2 else cL
        area_used = cpl * case_footprint
        area_total = pL * pW
        area_util = area_used / area_total if area_total > 0 else 0.0
        cube_util = (cpl * cH * layers) / (pL * pW * mH) if (pL * pW * mH) > 0 else 0.0
        return {
            "cases_per_layer": cpl,
            "layers": layers,
            "cases": cpl * layers,
            "area": area_util,
            "cube": cube_util,
            "orient_L": orient_L,
            "orient_W": orient_W,
        }

    def _interlock_result() -> dict:
        """Interlock: odd layers 0°, even layers 90°."""
        c_odd = _cases_layer(cL, cW)
        c_even = _cases_layer(cW, cL)  # rotated 90°
        if c_odd == 0 and c_even == 0:
            return {"cases_per_layer": 0, "layers": 0, "cases": 0, "area": 0.0}
        if c_even == 0:
            # 90° doesn't fit at all — fallback to column
            return _column_result()
        total_layers = int(mH / cH)
        if max_pallet_kg and case_weight_kg > 0:
            avg_cpl = (c_odd + c_even) / 2.0
            max_layers_by_weight = int(max_pallet_kg / (avg_cpl * case_weight_kg))
            total_layers = min(total_layers, max_layers_by_weight)
        total_layers = max(total_layers, 0)
        n_odd = math.ceil(total_layers / 2)
        n_even = total_layers - n_odd
        total_cases = n_odd * c_odd + n_even * c_even
        avg_cpl = total_cases / total_layers if total_layers > 0 else 0.0
        area_used = (c_odd * cL * cW + c_even * cW * cL) / 2.0
        area_util = area_used / (pL * pW) if (pL * pW) > 0 else 0.0
        cube_util = (total_cases * cH) / (pL * pW * mH) if (pL * pW * mH) > 0 else 0.0
        return {
            "cases_per_layer": int(round(avg_cpl)),
            "layers": total_layers,
            "cases": total_cases,
            "area": area_util,
            "cube": cube_util,
        }

    if pattern_lower == "column":
        r = _column_result()
        chosen = "column"
    elif pattern_lower == "interlock":
        r = _interlock_result()
        chosen = "interlock"
    else:
        rc = _column_result()
        ri = _interlock_result()
        if ri["cases"] >= rc["cases"]:
            r = ri
            chosen = "interlock"
        else:
            r = rc
            chosen = "column"

    if r.get("cases", 0) == 0:
        warnings.append("WARNING: no cases fit on pallet — check dimensions.")

    pallet_weight = 0.0
    include_weight = False
    if case_weight_kg > 0 and r.get("cases", 0) > 0:
        pallet_weight = float(case_weight_kg) * r["cases"]
        include_weight = True
        if max_pallet_kg and pallet_weight > float(max_pallet_kg):
            warnings.append(
                f"WARNING: pallet weight {pallet_weight:.1f} kg exceeds "
                f"max_pallet_kg={float(max_pallet_kg):.1f} kg — reduce layers."
            )

    if float(r.get("cube", 0.0)) < 0.60:
        warnings.append(
            f"INFO: cube utilisation {float(r.get('cube', 0)):.1%} < 60% — "
            "consider different case or pallet dimensions."
        )

    out: dict = {
        "ok": True,
        "pattern_used": chosen,
        "cases_per_layer": int(r.get("cases_per_layer", 0)),
        "layers": int(r.get("layers", 0)),
        "cases_per_pallet": int(r.get("cases", 0)),
        "area_utilisation": float(r.get("area", 0.0)),
        "cube_utilisation": float(r.get("cube", 0.0)),
        "warnings": warnings,
    }
    if include_weight:
        out["pallet_weight_kg"] = pallet_weight
    return out


# ---------------------------------------------------------------------------
# 3. Dimensional / volumetric weight & freight class
# ---------------------------------------------------------------------------

def shipping_weight(
    length_mm: float,
    width_mm: float,
    height_mm: float,
    actual_kg: float,
    *,
    carrier: str = "domestic",
    freight_class_override: float | None = None,
) -> dict:
    """
    Dimensional (volumetric) weight and chargeable weight; NMFC freight class.

    DIM weight:
      volume_cm3 = (L_mm/10) * (W_mm/10) * (H_mm/10)
      DIM weight = volume_cm3 / DIM_factor
      DIM_factor = 5000 cm³/kg for domestic courier; 6000 for international.

    Chargeable weight = max(actual_kg, DIM weight).

    NMFC freight class from density (lb/ft³):
      density = actual_lb / volume_ft³
      → class from _NMFC_DENSITY_CLASS table.

    Parameters
    ----------
    length_mm, width_mm, height_mm : float
        Outer carton dimensions (mm).  All must be > 0.
    actual_kg : float
        Actual gross weight (kg).  Must be > 0.
    carrier : str
        'domestic' (DIM factor 5000) or 'international' (DIM factor 6000).
    freight_class_override : float | None
        If given, overrides the NMFC class lookup.

    Returns
    -------
    dict
      ok                  : True
      volume_cm3          : float
      dim_weight_kg       : float
      chargeable_weight_kg: float
      dim_factor          : int (5000 or 6000)
      density_lb_ft3      : float
      freight_class       : float (NMFC class)
      warnings            : list[str]
    """
    for name, val in (
        ("length_mm", length_mm), ("width_mm", width_mm),
        ("height_mm", height_mm), ("actual_kg", actual_kg),
    ):
        err = _guard_positive(name, val)
        if err:
            return _err(err)

    carrier_lower = str(carrier).lower().strip()
    if carrier_lower not in ("domestic", "international"):
        return _err(f"carrier must be 'domestic' or 'international'; got {carrier!r}")

    warnings: list[str] = []

    L_cm = float(length_mm) / 10.0
    W_cm = float(width_mm) / 10.0
    H_cm = float(height_mm) / 10.0
    volume_cm3 = L_cm * W_cm * H_cm

    dim_factor = 5000 if carrier_lower == "domestic" else 6000
    dim_weight_kg = volume_cm3 / dim_factor

    actual = float(actual_kg)
    chargeable = max(actual, dim_weight_kg)

    # Density for NMFC
    volume_ft3 = volume_cm3 / 28_316.85  # cm³ → ft³
    actual_lb = actual * 2.20462
    density_lb_ft3 = actual_lb / volume_ft3 if volume_ft3 > 0 else 0.0

    if freight_class_override is not None:
        freight_class = float(freight_class_override)
    else:
        freight_class = 500.0  # default highest class
        for lower_bound, cls in _NMFC_DENSITY_CLASS:
            if density_lb_ft3 >= lower_bound:
                freight_class = float(cls)
                break

    if dim_weight_kg > actual:
        warnings.append(
            f"INFO: DIM weight {dim_weight_kg:.2f} kg > actual {actual:.2f} kg — "
            "chargeable weight is DIM weight."
        )
    if freight_class >= 250:
        warnings.append(
            f"WARNING: freight class {freight_class} is high — very low-density "
            "shipment; consider denser packing or padded mailer."
        )

    return {
        "ok": True,
        "volume_cm3": volume_cm3,
        "dim_weight_kg": dim_weight_kg,
        "chargeable_weight_kg": chargeable,
        "dim_factor": dim_factor,
        "density_lb_ft3": density_lb_ft3,
        "freight_class": freight_class,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 4. Cushion design
# ---------------------------------------------------------------------------

def cushion_design(
    product_weight_kg: float,
    drop_height_m: float,
    fragility_G: float,
    foam_static_stress_kPa: float,
    foam_cushion_curve_G: float,
    *,
    bearing_area_cm2: float = 100.0,
    safety_factor: float = 1.5,
) -> dict:
    """
    Cushion design from drop height, fragility, and foam cushion-curve data.

    Method (ASTM D1596 / ISTA):
    1. Required velocity change:  ΔV = sqrt(2 g h)  [m/s]
    2. Static stress on foam:
          σ_s = (product_weight_kg * 9.81) / (bearing_area_cm2 * 1e-4)  [Pa → kPa]
    3. Cushion efficiency factor η:
          G_transmitted / G_applied ≈ foam_cushion_curve_G / G_applied
          (user provides G value read off foam cushion curve at σ_s)
    4. Required cushion thickness:
          t = ΔV² / (2 * g * (fragility_G / safety_factor - 1) * g)
          Simplified energy method:
          t = ΔV² / (2 * g * (G_allow - 1))
          where G_allow = fragility_G / safety_factor
    5. Flag if foam_cushion_curve_G > fragility_G (under-cushioned).
       Flag if static stress outside typical foam operating window
       (σ_s < 1 kPa → too soft to transmit; σ_s > 200 kPa → foam bottoms out).

    Parameters
    ----------
    product_weight_kg : float
        Product gross weight (kg).  Must be > 0.
    drop_height_m : float
        Drop height (m) per ISTA test procedure.  Must be > 0.
    fragility_G : float
        Product fragility level (peak G the product can tolerate).  Must be > 1.
    foam_static_stress_kPa : float
        Static stress on foam face at bearing_area_cm2 (kPa).
        May also be computed internally — used if provided directly.
        Must be > 0.
    foam_cushion_curve_G : float
        G value read from foam's cushion curve at the operating static stress
        and the required thickness.  Must be > 0.
    bearing_area_cm2 : float
        Foam bearing area (cm²).  Default 100 cm².  Must be > 0.
    safety_factor : float
        Applied to fragility_G: G_allow = fragility_G / safety_factor.
        Must be >= 1.0.

    Returns
    -------
    dict
      ok                    : True
      delta_V_m_s           : velocity change (m/s)
      static_stress_kPa     : static stress on foam (kPa) — computed from weight/area
      required_thickness_mm : minimum cushion thickness (mm)
      G_allow               : fragility_G / safety_factor
      under_cushioned       : True if foam_cushion_curve_G > fragility_G
      fragile_exceeded      : True if foam_cushion_curve_G > G_allow
      warnings              : list[str]
    """
    err = _guard_positive("product_weight_kg", product_weight_kg)
    if err:
        return _err(err)
    err = _guard_positive("drop_height_m", drop_height_m)
    if err:
        return _err(err)
    err = _guard_positive("fragility_G", fragility_G)
    if err:
        return _err(err)
    if float(fragility_G) <= 1.0:
        return _err(f"fragility_G must be > 1.0 (physical minimum); got {fragility_G}")
    err = _guard_positive("foam_static_stress_kPa", foam_static_stress_kPa)
    if err:
        return _err(err)
    err = _guard_positive("foam_cushion_curve_G", foam_cushion_curve_G)
    if err:
        return _err(err)
    err = _guard_positive("bearing_area_cm2", bearing_area_cm2)
    if err:
        return _err(err)
    err = _guard_positive("safety_factor", safety_factor)
    if err:
        return _err(err)
    if float(safety_factor) < 1.0:
        return _err(f"safety_factor must be >= 1.0; got {safety_factor}")

    warnings: list[str] = []
    g = 9.81  # m/s²

    h = float(drop_height_m)
    m = float(product_weight_kg)
    G_frag = float(fragility_G)
    G_curve = float(foam_cushion_curve_G)
    A_m2 = float(bearing_area_cm2) * 1e-4  # cm² → m²
    SF = float(safety_factor)

    # Velocity change
    delta_V = math.sqrt(2.0 * g * h)

    # Static stress (compute from weight/area; cross-check with provided value)
    sigma_s_Pa = (m * g) / A_m2  # Pa
    sigma_s_kPa = sigma_s_Pa / 1000.0

    # Allowable G
    G_allow = G_frag / SF
    if G_allow <= 1.0:
        warnings.append(
            f"WARNING: G_allow = fragility_G/SF = {G_frag}/{SF:.2f} = {G_allow:.2f} "
            "<= 1.0 — cushion equation degenerate; increase fragility_G or reduce SF."
        )
        G_allow = max(G_allow, 1.01)

    # Required cushion thickness (energy method):
    # KE = 0.5 m ΔV² = F × t_cushion
    # F_decel = m × G_allow × g
    # t = KE / F_decel = (0.5 m ΔV²) / (m × G_allow × g) = ΔV² / (2 × G_allow × g)
    t_m = delta_V**2 / (2.0 * G_allow * g)
    t_mm = t_m * 1000.0

    under_cushioned = G_curve > G_frag
    fragile_exceeded = G_curve > G_allow

    if under_cushioned:
        warnings.append(
            f"UNDER-CUSHIONED: foam cushion-curve G ({G_curve:.1f}G) > "
            f"product fragility ({G_frag:.1f}G) — the foam will transmit shocks "
            "above the product's tolerable limit. Use lower-density foam or "
            "increase bearing area."
        )
    elif fragile_exceeded:
        warnings.append(
            f"FRAGILE-EXCEEDED: foam cushion-curve G ({G_curve:.1f}G) > "
            f"G_allow ({G_allow:.1f}G = fragility/SF) — insufficient safety margin. "
            "Increase safety factor or select better foam."
        )

    if sigma_s_kPa < 1.0:
        warnings.append(
            f"INFO: static stress {sigma_s_kPa:.3f} kPa < 1 kPa — foam may be too soft "
            "for this load; risk of foam bottoming out under repeated drops."
        )
    if sigma_s_kPa > 200.0:
        warnings.append(
            f"WARNING: static stress {sigma_s_kPa:.1f} kPa > 200 kPa — foam likely to "
            "bottom out; increase bearing area or use higher-density foam."
        )

    return {
        "ok": True,
        "delta_V_m_s": delta_V,
        "static_stress_kPa": sigma_s_kPa,
        "required_thickness_mm": t_mm,
        "G_allow": G_allow,
        "under_cushioned": under_cushioned,
        "fragile_exceeded": fragile_exceeded,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 5. Shock & vibration transmissibility through cushion
# ---------------------------------------------------------------------------

def shock_transmissibility(
    fn_Hz: float,
    damping_ratio: float,
    input_freq_Hz: float,
) -> dict:
    """
    Single-DOF shock & vibration transmissibility through packaging cushion.

    Transmissibility (force or displacement):
        T = sqrt( (1 + (2ζr)²) / ((1 - r²)² + (2ζr)²) )
    where r = input_freq / fn (frequency ratio).

    A cushion acts as a low-pass filter for r >> 1 (> sqrt(2));
    for r < 1 the cushion amplifies vibration (up to 1/2ζ at resonance).

    Parameters
    ----------
    fn_Hz : float
        Natural frequency of packaged product on cushion (Hz).  Must be > 0.
    damping_ratio : float
        Damping ratio ζ.  0 < ζ < 1 for underdamped system.  Must be > 0.
    input_freq_Hz : float
        Excitation / input frequency (Hz).  Must be > 0.

    Returns
    -------
    dict
      ok                : True
      frequency_ratio   : r = input_freq_Hz / fn_Hz
      transmissibility  : T (dimensionless)
      attenuation_dB    : -20 log10(T) [positive dB = attenuation]
      isolation_pct     : (1 - T) * 100  [%] (negative if amplifying)
      resonance_warning : True if |r - 1| < 0.05  (within 5% of resonance)
      warnings          : list[str]
    """
    err = _guard_positive("fn_Hz", fn_Hz)
    if err:
        return _err(err)
    err = _guard_positive("damping_ratio", damping_ratio)
    if err:
        return _err(err)
    err = _guard_positive("input_freq_Hz", input_freq_Hz)
    if err:
        return _err(err)

    if float(damping_ratio) >= 1.0:
        return _err(
            f"damping_ratio must be < 1.0 for underdamped system; got {damping_ratio}"
        )

    warnings: list[str] = []

    fn = float(fn_Hz)
    zeta = float(damping_ratio)
    f_in = float(input_freq_Hz)
    r = f_in / fn

    numerator = 1.0 + (2.0 * zeta * r) ** 2
    denominator = (1.0 - r**2) ** 2 + (2.0 * zeta * r) ** 2
    if denominator < 1e-15:
        return _err("Degenerate denominator at perfect resonance with zero damping.")

    T = math.sqrt(numerator / denominator)
    attenuation_dB = -20.0 * math.log10(T) if T > 1e-15 else float("inf")
    isolation_pct = (1.0 - T) * 100.0

    resonance_warning = abs(r - 1.0) < 0.05
    if resonance_warning:
        warnings.append(
            f"RESONANCE: frequency ratio r={r:.3f} is within 5% of resonance — "
            f"transmissibility T={T:.2f}; use higher damping or detune cushion fn."
        )
    if T > 1.0 and not resonance_warning:
        warnings.append(
            f"INFO: T={T:.3f} > 1.0 — cushion is amplifying at this frequency "
            "(r < √2); consider stiffening cushion to move fn above input frequency."
        )

    return {
        "ok": True,
        "frequency_ratio": r,
        "transmissibility": T,
        "attenuation_dB": attenuation_dB,
        "isolation_pct": isolation_pct,
        "resonance_warning": resonance_warning,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 6. Container / ISO-unit fill optimisation
# ---------------------------------------------------------------------------

def container_fill(
    case_L: float,
    case_W: float,
    case_H: float,
    container_type: str = "40GP",
    *,
    orientation_permutations: bool = True,
) -> dict:
    """
    Optimise case-count in an ISO shipping container.

    Tries up to 6 box orientations (all permutations of L/W/H) and returns
    the arrangement with the highest utilisation.

    Parameters
    ----------
    case_L, case_W, case_H : float
        Case outer dimensions (mm).  All must be > 0.
    container_type : str
        One of '20GP', '40GP', '40HC', '45HC' (default '40GP').
    orientation_permutations : bool
        If True (default), try all 6 orientations.  If False, use input order only.

    Returns
    -------
    dict
      ok               : True
      container_type   : str
      internal_L_mm    : float
      internal_W_mm    : float
      internal_H_mm    : float
      orientation_used : tuple (oL, oW, oH) in mm
      cases_per_row    : int  (along container length)
      cases_per_col    : int  (across container width)
      layers           : int  (vertical)
      total_cases      : int
      volume_utilisation: float  [0–1]
      warnings         : list[str]
    """
    for name, val in (("case_L", case_L), ("case_W", case_W), ("case_H", case_H)):
        err = _guard_positive(name, val)
        if err:
            return _err(err)

    ctype = str(container_type).upper().strip()
    if ctype not in _CONTAINER:
        return _err(
            f"Unknown container_type '{container_type}'. "
            f"Supported: {sorted(_CONTAINER.keys())}."
        )

    warnings: list[str] = []
    cL = float(case_L)
    cW = float(case_W)
    cH = float(case_H)
    con_L, con_W, con_H, _ = _CONTAINER[ctype]

    # Generate orientations
    dims = (cL, cW, cH)
    if orientation_permutations:
        from itertools import permutations as _perms
        orientations = list(set(_perms(dims)))
    else:
        orientations = [(cL, cW, cH)]

    best: dict = {"total": 0}
    for oL, oW, oH in orientations:
        n_row = int(con_L / oL)
        n_col = int(con_W / oW)
        n_lay = int(con_H / oH)
        total = n_row * n_col * n_lay
        if total > best.get("total", 0):
            best = {
                "total": total,
                "oL": oL, "oW": oW, "oH": oH,
                "n_row": n_row, "n_col": n_col, "n_lay": n_lay,
            }

    total = int(best.get("total", 0))
    case_vol = cL * cW * cH
    container_vol = con_L * con_W * con_H
    vol_util = (total * case_vol / container_vol) if container_vol > 0 else 0.0

    if total == 0:
        warnings.append("WARNING: no cases fit in container — check dimensions.")
    if vol_util < 0.50:
        warnings.append(
            f"INFO: volume utilisation {vol_util:.1%} < 50% — consider consolidation "
            "or a smaller container type."
        )

    return {
        "ok": True,
        "container_type": ctype,
        "internal_L_mm": con_L,
        "internal_W_mm": con_W,
        "internal_H_mm": con_H,
        "orientation_used": (best.get("oL", cL), best.get("oW", cW), best.get("oH", cH)),
        "cases_per_row": int(best.get("n_row", 0)),
        "cases_per_col": int(best.get("n_col", 0)),
        "layers": int(best.get("n_lay", 0)),
        "total_cases": total,
        "volume_utilisation": vol_util,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 7. Stretch-wrap containment force
# ---------------------------------------------------------------------------

def stretch_wrap(
    pallet_weight_kg: float,
    film_gauge_um: float,
    *,
    revolutions: int = 3,
    overlap_fraction: float = 0.50,
    pre_stretch_pct: float = 200.0,
) -> dict:
    """
    Stretch-wrap containment force & revolution count per EUMOS 40509 / ASTM D4169.

    Containment force model (linear):
      F_per_layer (N) = k_film × gauge_um × pre_stretch_factor × pallet_perimeter_estimate
      where k_film ≈ 0.18 N/(μm·m)  (empirical constant for typical LLDPE stretch film)
      pre_stretch_factor = (pre_stretch_pct / 100) * overlap_fraction * 2 layers/revolution

    EUMOS 40509 minimum containment force (rough guidance):
      F_min = 0.4 × pallet_weight_kg × 9.81  (N)  for class 1 transport

    Parameters
    ----------
    pallet_weight_kg : float
        Gross pallet weight (product + pallet deck) (kg).  Must be > 0.
    film_gauge_um : float
        Film gauge / thickness (μm).  Typical 17–30 μm.  Must be > 0.
    revolutions : int
        Number of wrap revolutions.  Must be >= 1.
    overlap_fraction : float
        Fraction of film width overlapping on each revolution (0–1).  Default 0.50.
    pre_stretch_pct : float
        Pre-stretch percentage applied by wrap machine.  Typical 150–300%.
        Default 200%.

    Returns
    -------
    dict
      ok                      : True
      F_per_revolution_N      : containment force per revolution (N)
      F_total_N               : total containment force for all revolutions (N)
      F_min_required_N        : EUMOS 40509 minimum (N)
      eumos_compliant         : True if F_total_N >= F_min_required_N
      revolutions_for_minimum : int — minimum revolutions needed to meet EUMOS
      warnings                : list[str]
    """
    err = _guard_positive("pallet_weight_kg", pallet_weight_kg)
    if err:
        return _err(err)
    err = _guard_positive("film_gauge_um", film_gauge_um)
    if err:
        return _err(err)
    err = _guard_positive("pre_stretch_pct", pre_stretch_pct)
    if err:
        return _err(err)

    try:
        rev_i = int(revolutions)
    except (TypeError, ValueError):
        return _err(f"revolutions must be an integer; got {revolutions!r}")
    if rev_i < 1:
        return _err(f"revolutions must be >= 1; got {rev_i}")

    if not (0.0 < float(overlap_fraction) <= 1.0):
        return _err(
            f"overlap_fraction must be in (0, 1]; got {overlap_fraction}"
        )

    warnings: list[str] = []

    gauge = float(film_gauge_um)
    pre_s = float(pre_stretch_pct) / 100.0  # ratio
    overlap = float(overlap_fraction)
    W = float(pallet_weight_kg)

    # Empirical LLDPE stretch-film constant
    k_film = 0.18  # N / (μm · m)

    # Approximate standard euro-pallet half-perimeter (1200 mm × 800 mm)
    # We don't know actual pallet dims here, so use a generic estimate.
    # In real use, pass actual pallet perimeter.
    pallet_perimeter_m = 4.0  # m  (standard euro-pallet 1200+800 mm × 2 sides ≈ 4 m)

    # Force per revolution (2 film layers per revolution × overlap × pre-stretch)
    F_per_rev = k_film * gauge * pre_s * overlap * 2.0 * pallet_perimeter_m

    F_total = F_per_rev * rev_i

    # EUMOS 40509 class 1 minimum
    F_min = 0.4 * W * 9.81

    eumos_ok = F_total >= F_min

    # Minimum revolutions to meet EUMOS
    if F_per_rev > 0:
        rev_min = math.ceil(F_min / F_per_rev)
    else:
        rev_min = 9999

    if not eumos_ok:
        warnings.append(
            f"EUMOS-INSUFFICIENT: total containment force {F_total:.1f} N < "
            f"required {F_min:.1f} N — increase revolutions to at least {rev_min}."
        )
    if gauge < 17.0:
        warnings.append(
            f"INFO: film gauge {gauge:.1f} μm < 17 μm — thin film may be prone to "
            "tearing on pallet corners; consider edge protectors."
        )
    if pre_s > 3.5:
        warnings.append(
            f"WARNING: pre_stretch {float(pre_stretch_pct):.0f}% > 350% — "
            "risk of film neck-down and reduced containment force."
        )

    return {
        "ok": True,
        "F_per_revolution_N": F_per_rev,
        "F_total_N": F_total,
        "F_min_required_N": F_min,
        "eumos_compliant": eumos_ok,
        "revolutions_for_minimum": int(rev_min),
        "warnings": warnings,
    }
