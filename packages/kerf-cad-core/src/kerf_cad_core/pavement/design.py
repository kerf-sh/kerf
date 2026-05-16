"""
kerf_cad_core.pavement.design — highway & airfield pavement design formulas.

Implements pure-Python (math-only) pavement design calculations following:
  AASHTO Guide for Design of Pavement Structures, 1993 (AASHTO '93)
  PCA fatigue/erosion design concept (noted, not fully coded)
  Boussinesq (1885) vertical stress under circular load in elastic half-space
  Modified Berggren simplified frost-penetration depth

Scope
-----
This module covers PAVEMENT design only.  It is DISTINCT from:
  civil/alignment  — road horizontal/vertical geometry
  geotech/         — foundation bearing capacity, settlement, slope stability
  concrete/        — structural concrete beams, columns, slabs

Public functions
----------------
aashto93_flexible_sn(W18, ZR, S0, ΔPSI, MR)
    Required structural number SN for flexible (asphalt) pavement.

aashto93_flexible_layers(SN, layers)
    Required layer thicknesses from layer coefficients a_i & drainage m_i.

esals_design(ADT, truck_factor, lane_dist, dir_dist, design_years, growth_rate)
    Design-period ESALs from traffic inputs (growth-factor series).

esal_growth_factor(growth_rate, design_years)
    Geometric growth factor (compound) for ESAL accumulation.

load_equivalency_factor(axle_load_kN, axle_type)
    Load equivalency factor (LEF) via power-law (AASHTO '93).

cbr_to_mr(CBR)
    Subgrade resilient modulus MR (psi) from CBR (percent), AASHTO correlation.

cbr_to_k(CBR)
    Modulus of subgrade reaction k (pci) from CBR, AASHTO correlation.

boussinesq_stress(q, a, z)
    Vertical stress σ_z under centre of uniformly loaded circular area (Pa).

aashto93_rigid_thickness(W18, ZR, S0, ΔPSI, Sc, Cd, J, Ec, k)
    Rigid (PCC) slab thickness via iterative AASHTO '93 equation.

joint_spacing(h_slab_mm, coeff_thermal, delta_temp, allow_strain)
    Contraction joint spacing for rigid pavement slab.

dowel_bar_size(h_slab_mm)
    Recommended dowel bar diameter for rigid pavement joints (AASHTO/ACI).

frost_penetration_depth(freezing_index_degC_days, k_soil, L_soil)
    Frost penetration depth via modified Berggren simplified (Stefan) equation.

overlay_thickness_sn(SN_existing, SN_required, a_overlay)
    Overlay thickness from SN-deficiency method.

asphalt_quantity(length_m, width_m, thickness_m, density_kg_m3)
    Asphalt mix quantity (kg and tonnes) for a pavement layer.

Unit system
-----------
  SN, layer thicknesses   — inches (AASHTO '93 is in US customary throughout)
  ESALs                   — 18-kip (80-kN) equivalent single-axle loads
  MR                      — psi  (pounds per square inch)
  k                       — pci  (pounds per cubic inch) — modulus of subgrade reaction
  Sc                      — psi  — PCC modulus of rupture
  Ec                      — psi  — PCC elastic modulus
  Loads (Boussinesq)      — Pa, metres (SI)
  Frost depth             — metres (SI)
  Asphalt quantity        — SI (metres, kg)

All functions return a plain dict:
    success → {"ok": True, ..., "warnings": [...]}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise.

References
----------
AASHTO (1993). Guide for Design of Pavement Structures.
  American Association of State Highway and Transportation Officials.
Huang, Y.H. (2004). Pavement Analysis and Design, 2nd ed. Pearson.
Portland Cement Association (1966). Thickness Design for Concrete Highway
  and Street Pavements.
Boussinesq, J. (1885). Application des Potentiels. Gauthier-Villars, Paris.

Author: imranparuk
"""

from __future__ import annotations

import math
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


def _guard_range(name: str, value: Any, lo: float, hi: float) -> str | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {value!r}"
    if not math.isfinite(v):
        return f"{name} must be finite, got {v}"
    if v < lo or v > hi:
        return f"{name} must be in [{lo}, {hi}], got {v}"
    return None


def _err(reason: str) -> dict:
    return {"ok": False, "reason": reason}


# ---------------------------------------------------------------------------
# AASHTO '93 Flexible Pavement — Structural Number
# ---------------------------------------------------------------------------

# AASHTO '93 flexible pavement design equation (log10 form):
#
# log10(W18) = ZR·S0 + 9.36·log10(SN+1) - 0.20
#              + log10(ΔPSI / (4.2 - 1.5)) / (0.40 + 1094/(SN+1)^5.19)
#              + 2.32·log10(MR) - 8.07
#
# Rearranged to solve for SN iteratively (bisection on SN in [0, 50]).

# ΔPSI thresholds:
#   highway initial PSI = 4.2 (AASHTO default)
#   terminal PSI = 2.5 (major roads) or 2.0 (minor roads)
#   hence ΔPSI = 4.2 - terminal = 1.7 or 2.2 typically

_PSI_INITIAL = 4.2   # initial PSI (AASHTO standard highway)
_PSI_TERM_DEFAULT = 2.5  # terminal PSI default


def _aashto93_flex_lhs(SN: float, ZR: float, S0: float, DPSI: float, MR_psi: float) -> float:
    """Return predicted log10(W18) from AASHTO '93 flexible equation."""
    # Guard: SN must be >= 0
    if SN < 0:
        SN = 0.0
    log_w18 = (
        ZR * S0
        + 9.36 * math.log10(SN + 1.0)
        - 0.20
        + math.log10(DPSI / (4.2 - 1.5)) / (0.40 + 1094.0 / (SN + 1.0) ** 5.19)
        + 2.32 * math.log10(MR_psi)
        - 8.07
    )
    return log_w18


def aashto93_flexible_sn(
    W18: float,
    ZR: float,
    S0: float,
    DPSI: float,
    MR: float,
) -> dict:
    """
    Required structural number SN for flexible (asphalt) pavement — AASHTO '93.

    Parameters
    ----------
    W18 : float
        Design traffic in ESALs (18-kip equivalent single-axle loads).
        Must be > 0.
    ZR : float
        Standard normal deviate for reliability R.
        Typical values: R=50% → ZR=0.000; R=90% → ZR=-1.282;
        R=95% → ZR=-1.645; R=99% → ZR=-2.327.  Must be finite.
    S0 : float
        Overall standard deviation for flexible pavement. Typical: 0.45.
        Must be > 0.
    DPSI : float
        Design serviceability loss = PSI_initial - PSI_terminal.
        Typical: ΔPSI = 4.2 - 2.5 = 1.7 (major roads),
                 ΔPSI = 4.2 - 2.0 = 2.2 (minor roads).
        Must be in (0, 4.2).
    MR : float
        Effective subgrade resilient modulus (psi). Must be > 0.
        Typical range: 3 000–30 000 psi.
        Use cbr_to_mr() to convert from CBR %.

    Returns
    -------
    dict
        ok       : True
        SN       : required structural number (dimensionless, in.)
        W18      : design ESALs used
        ZR       : ZR used
        S0       : S0 used
        DPSI     : ΔPSI used
        MR_psi   : MR used (psi)
        warnings : list of warning strings (never raises)

    Notes
    -----
    Solved by bisection on SN ∈ [0, 50] matching log10(W18) within 1e-6.
    AASHTO '93, Part II, Chapter 3.

    Unit system: US customary throughout (SN dimensionless, MR in psi).
    """
    warnings: list[str] = []

    try:
        W18 = float(W18)
    except (TypeError, ValueError):
        return _err(f"W18 must be a number, got {W18!r}")
    if not math.isfinite(W18) or W18 <= 0:
        return _err(f"W18 must be > 0 and finite, got {W18}")

    try:
        ZR = float(ZR)
    except (TypeError, ValueError):
        return _err(f"ZR must be a number, got {ZR!r}")
    if not math.isfinite(ZR):
        return _err(f"ZR must be finite, got {ZR}")

    err = _guard_positive("S0", S0)
    if err:
        return _err(err)

    err = _guard_range("DPSI", DPSI, 0.01, 4.19)
    if err:
        return _err(err)

    err = _guard_positive("MR", MR)
    if err:
        return _err(err)

    S0 = float(S0)
    DPSI = float(DPSI)
    MR_psi = float(MR)

    target = math.log10(W18)

    # Bisection: find SN such that _aashto93_flex_lhs(SN, ...) == target
    lo, hi = 0.001, 50.0
    for _ in range(100):
        mid = (lo + hi) / 2.0
        val = _aashto93_flex_lhs(mid, ZR, S0, DPSI, MR_psi)
        if val < target:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-6:
            break

    SN_result = (lo + hi) / 2.0

    if SN_result < 1.0:
        warnings.append(
            f"SN={SN_result:.3f} < 1.0 in. — very low traffic or high subgrade strength; "
            "verify inputs."
        )
    if W18 > 1e8:
        warnings.append(
            f"W18={W18:.3e} is extremely high — verify ESAL accumulation."
        )

    return {
        "ok": True,
        "SN": SN_result,
        "W18": W18,
        "ZR": ZR,
        "S0": S0,
        "DPSI": DPSI,
        "MR_psi": MR_psi,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# AASHTO '93 Flexible Pavement — Layer Thicknesses
# ---------------------------------------------------------------------------

# Stage-solve: the thinnest layer satisfying SN contribution is chosen, then
# remaining SN is allocated to deeper layers.
#
# SN = a1·D1 + a2·m2·D2 + a3·m3·D3 + ...
#
# AASHTO '93 minimum layer thicknesses (in.):
_MIN_LAYER_THICKNESS_IN: dict[str, float] = {
    "asphalt":    1.0,   # HMA surface/binder — recommended min 1 in.
    "base":       4.0,   # granular base — recommended min 4 in.
    "subbase":    4.0,   # granular subbase — recommended min 4 in.
}


def aashto93_flexible_layers(
    SN: float,
    layers: list[dict],
) -> dict:
    """
    Required layer thicknesses from structural number and layer coefficients.

    Parameters
    ----------
    SN : float
        Required structural number (from aashto93_flexible_sn). Must be > 0.
    layers : list of dict
        Ordered list of layers from surface to bottom, each dict with:
          "a"   : layer coefficient a_i (1/in.)  — required, must be > 0
          "m"   : drainage coefficient m_i       — optional, default 1.0
          "name": label string                   — optional
          "type": "asphalt" | "base" | "subbase" | "other"
                  used for minimum-thickness lookup; default "other"

    Returns
    -------
    dict
        ok      : True
        layers  : list of dicts, each with:
                    name, type, a, m, D_in (required thickness in inches),
                    SN_contrib (SN contributed by this layer)
        SN_total: sum of SN contributions (≈ SN_required)
        SN_required: SN input
        warnings: list of warning strings

    Notes
    -----
    Uses stage-solve approach: each layer thickness is rounded up to the
    nearest 0.5 in., subject to the AASHTO minimum for its type.
    Remaining SN carried forward to next layer.  If SN_total > SN_required,
    the last layer was rounded up — normal practice.

    Unit system: US customary (SN, D in inches; a in 1/in.).
    """
    warnings: list[str] = []

    err = _guard_positive("SN", SN)
    if err:
        return _err(err)

    if not isinstance(layers, list) or len(layers) == 0:
        return _err("layers must be a non-empty list of dicts.")

    SN_remain = float(SN)
    result_layers = []

    for i, layer in enumerate(layers):
        if not isinstance(layer, dict):
            return _err(f"layers[{i}] must be a dict, got {type(layer).__name__}.")

        a = layer.get("a")
        if a is None:
            return _err(f"layers[{i}]: 'a' (layer coefficient) is required.")
        try:
            a = float(a)
        except (TypeError, ValueError):
            return _err(f"layers[{i}]['a'] must be a number, got {a!r}.")
        if not math.isfinite(a) or a <= 0:
            return _err(f"layers[{i}]['a'] must be > 0 and finite, got {a}.")

        m = float(layer.get("m", 1.0))
        if not math.isfinite(m) or m <= 0:
            return _err(f"layers[{i}]['m'] must be > 0 and finite, got {m}.")

        name = layer.get("name", f"Layer {i+1}")
        layer_type = str(layer.get("type", "other")).lower()

        # Minimum thickness from AASHTO table
        D_min = _MIN_LAYER_THICKNESS_IN.get(layer_type, 0.0)

        # Required D to carry remaining SN: D = SN_remain / (a * m)
        if SN_remain > 0:
            D_raw = SN_remain / (a * m)
            # Round up to nearest 0.5 in.
            D_rounded = math.ceil(D_raw / 0.5) * 0.5
            D_use = max(D_rounded, D_min)
        else:
            D_use = D_min if D_min > 0 else 0.0

        if D_use < D_min and D_min > 0:
            warnings.append(
                f"Layer '{name}' (type={layer_type}): computed D={D_use:.2f} in. "
                f"is below AASHTO minimum {D_min:.1f} in.; using minimum."
            )
            D_use = D_min

        SN_contrib = a * m * D_use
        SN_remain -= SN_contrib

        result_layers.append({
            "name": name,
            "type": layer_type,
            "a": a,
            "m": m,
            "D_in": D_use,
            "SN_contrib": SN_contrib,
        })

        if layer.get("type", "other") == "asphalt" and D_use < 1.5:
            warnings.append(
                f"Layer '{name}': D={D_use:.2f} in. < 1.5 in. — compaction "
                "of thin HMA lifts may be impractical in field conditions."
            )

    SN_total = sum(lyr["SN_contrib"] for lyr in result_layers)

    if SN_remain > 0.01:
        warnings.append(
            f"SN_total={SN_total:.3f} < SN_required={SN:.3f} — insufficient layers "
            "to carry required SN; add more layers or increase thickness."
        )

    return {
        "ok": True,
        "layers": result_layers,
        "SN_total": SN_total,
        "SN_required": float(SN),
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Traffic ESALs — design period accumulation
# ---------------------------------------------------------------------------

def esal_growth_factor(growth_rate: float, design_years: float) -> dict:
    """
    Geometric-series growth factor for ESAL accumulation over design period.

    For a compound (geometric) annual traffic growth rate r and design period
    n years, the growth factor G is:

        G = [(1 + r)^n - 1] / r          if r != 0
        G = n                             if r == 0

    Parameters
    ----------
    growth_rate : float
        Annual traffic growth rate as a decimal (e.g. 0.03 = 3%). >= 0.
    design_years : float
        Design period in years. Must be > 0.

    Returns
    -------
    dict
        ok           : True
        growth_factor: G (years)
        growth_rate  : r used
        design_years : n used

    Unit system: dimensionless (growth_factor multiplied against annual ESALs).
    """
    err = _guard_nonneg("growth_rate", growth_rate)
    if err:
        return _err(err)
    err = _guard_positive("design_years", design_years)
    if err:
        return _err(err)

    r = float(growth_rate)
    n = float(design_years)

    if abs(r) < 1e-10:
        G = n
    else:
        G = ((1.0 + r) ** n - 1.0) / r

    return {
        "ok": True,
        "growth_factor": G,
        "growth_rate": r,
        "design_years": n,
    }


def load_equivalency_factor(
    axle_load_kN: float,
    axle_type: str = "single",
) -> dict:
    """
    Load equivalency factor (LEF) for converting axle loads to 18-kip ESALs.

    Uses AASHTO '93 power-law approximation:
        LEF = (axle_load / standard_axle)^4.0   (simplified)

    Standard axle loads (reference):
        single axle: 80 kN  (17.99 kip ≈ 18 kip)
        tandem axle: 142 kN (AASHTO tandem standard)
        tridem axle: 178 kN (AASHTO tridem standard)

    Parameters
    ----------
    axle_load_kN : float
        Axle load in kN. Must be > 0.
    axle_type : str
        "single" (default), "tandem", or "tridem".

    Returns
    -------
    dict
        ok             : True
        LEF            : load equivalency factor
        axle_load_kN   : load used (kN)
        axle_type      : axle type string
        standard_axle_kN: reference standard axle (kN)
        warnings       : list

    Notes
    -----
    The simplified 4th-power law is used here (Liddle, 1962, as referenced in
    AASHTO '93).  For precise values from AASHTO pavement design charts use
    the tabulated LEF tables.

    Unit system: kN (axle loads).
    """
    warnings: list[str] = []

    err = _guard_positive("axle_load_kN", axle_load_kN)
    if err:
        return _err(err)

    _std_axle = {
        "single": 80.0,    # kN
        "tandem": 142.0,   # kN
        "tridem": 178.0,   # kN
    }

    at = str(axle_type).strip().lower()
    if at not in _std_axle:
        return _err(
            f"axle_type {axle_type!r} is not supported. "
            f"Use one of: {list(_std_axle.keys())}."
        )

    std = _std_axle[at]
    P = float(axle_load_kN)
    LEF = (P / std) ** 4.0

    if LEF > 5.0:
        warnings.append(
            f"LEF={LEF:.2f} > 5.0 — very high axle load relative to standard; "
            "verify axle load input."
        )

    return {
        "ok": True,
        "LEF": LEF,
        "axle_load_kN": P,
        "axle_type": at,
        "standard_axle_kN": std,
        "warnings": warnings,
    }


def esals_design(
    ADT: float,
    truck_factor: float,
    lane_dist: float,
    dir_dist: float,
    design_years: float,
    growth_rate: float,
) -> dict:
    """
    Design-period ESALs from traffic inputs.

    W18 = ADT × truck_factor × lane_dist × dir_dist × 365 × G

    where G is the geometric growth factor over the design period.

    Parameters
    ----------
    ADT : float
        Average Daily Traffic (vehicles/day, both directions). Must be > 0.
    truck_factor : float
        Truck ESAL factor — average ESALs per truck (from axle load spectra
        or AASHTO default tables).  Typical: 0.1–5.0. Must be > 0.
    lane_dist : float
        Lane distribution factor (fraction of ESALs in the design lane).
        Typical: 0.45–1.0. Must be in (0, 1].
    dir_dist : float
        Directional distribution factor (fraction in heavier direction).
        Typically 0.5 (equal split). Must be in (0, 1].
    design_years : float
        Design period (years). Must be > 0.
    growth_rate : float
        Annual traffic growth rate as decimal (e.g. 0.02 = 2%). >= 0.

    Returns
    -------
    dict
        ok          : True
        W18         : design-period ESALs
        annual_ESAL : first-year ESALs
        growth_factor: G used
        ADT         : ADT used
        truck_factor: truck_factor used
        lane_dist   : lane_dist used
        dir_dist    : dir_dist used
        design_years: design_years used
        growth_rate : growth_rate used
        warnings    : list

    Unit system: ESALs (18-kip ≡ 80-kN equivalent single axle loads).
    """
    warnings: list[str] = []

    err = _guard_positive("ADT", ADT)
    if err:
        return _err(err)
    err = _guard_positive("truck_factor", truck_factor)
    if err:
        return _err(err)
    err = _guard_range("lane_dist", lane_dist, 1e-3, 1.0)
    if err:
        return _err(err)
    err = _guard_range("dir_dist", dir_dist, 1e-3, 1.0)
    if err:
        return _err(err)
    err = _guard_positive("design_years", design_years)
    if err:
        return _err(err)
    err = _guard_nonneg("growth_rate", growth_rate)
    if err:
        return _err(err)

    r = float(growth_rate)
    n = float(design_years)

    if abs(r) < 1e-10:
        G = n
    else:
        G = ((1.0 + r) ** n - 1.0) / r

    annual_ESAL = float(ADT) * float(truck_factor) * float(lane_dist) * float(dir_dist) * 365.0
    W18 = annual_ESAL * G

    if W18 > 5e7:
        warnings.append(
            f"W18={W18:.2e} is very high (> 50 million ESALs) — "
            "verify inputs; may require staged design."
        )
    if W18 > 3e8:
        warnings.append(
            f"W18={W18:.2e} exceeds typical highway design range — "
            "check ADT and truck_factor."
        )

    return {
        "ok": True,
        "W18": W18,
        "annual_ESAL": annual_ESAL,
        "growth_factor": G,
        "ADT": float(ADT),
        "truck_factor": float(truck_factor),
        "lane_dist": float(lane_dist),
        "dir_dist": float(dir_dist),
        "design_years": n,
        "growth_rate": r,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Subgrade CBR correlations
# ---------------------------------------------------------------------------

def cbr_to_mr(CBR: float) -> dict:
    """
    Subgrade resilient modulus MR (psi) from CBR (%) — AASHTO '93 correlation.

    AASHTO '93 equation (Part II, Chapter 3):
        MR (psi) = 1500 × CBR

    Parameters
    ----------
    CBR : float
        California Bearing Ratio (percent). Must be in (0, 100].

    Returns
    -------
    dict
        ok    : True
        MR_psi: resilient modulus (psi)
        CBR   : CBR used (%)
        warnings: list

    Notes
    -----
    The 1500 × CBR approximation is the AASHTO '93 default correlation.
    Alternative correlations exist (e.g., Shell: MR = 10.3 × CBR^0.65 MPa).
    For fine-grained soils, direct laboratory MR testing is preferred.

    Unit system: MR in psi; CBR in percent.
    """
    warnings: list[str] = []

    err = _guard_range("CBR", CBR, 0.1, 100.0)
    if err:
        return _err(err)

    cbr = float(CBR)
    MR_psi = 1500.0 * cbr

    if cbr < 2.0:
        warnings.append(
            f"CBR={cbr}% is very low — subgrade may require stabilisation."
        )
    if cbr > 30.0:
        warnings.append(
            f"CBR={cbr}% is high — verify; the AASHTO 1500×CBR correlation "
            "may overestimate MR for CBR > 30%."
        )

    return {
        "ok": True,
        "MR_psi": MR_psi,
        "CBR": cbr,
        "warnings": warnings,
    }


def cbr_to_k(CBR: float) -> dict:
    """
    Modulus of subgrade reaction k (pci) from CBR (%) — AASHTO correlation.

    Approximate correlation used for rigid pavement design:
        k (pci) ≈ CBR / 3.33    (i.e., k ≈ 0.3 × CBR)

    More precisely, from AASHTO '93 nomograph interpolation (Huang 2004):
        k (pci) ≈ 26.3 × CBR^0.45

    This function uses the Huang power-law correlation for better accuracy
    over the typical CBR range.

    Parameters
    ----------
    CBR : float
        California Bearing Ratio (percent). Must be in (0, 100].

    Returns
    -------
    dict
        ok    : True
        k_pci : modulus of subgrade reaction (pci)
        CBR   : CBR used (%)
        warnings: list

    Unit system: k in pci (lb/in³); CBR in percent.
    """
    warnings: list[str] = []

    err = _guard_range("CBR", CBR, 0.1, 100.0)
    if err:
        return _err(err)

    cbr = float(CBR)
    k_pci = 26.3 * (cbr ** 0.45)

    if cbr < 3.0:
        warnings.append(
            f"CBR={cbr}% is low — consider subgrade improvement before pavement design."
        )

    return {
        "ok": True,
        "k_pci": k_pci,
        "CBR": cbr,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Boussinesq vertical stress under circular load
# ---------------------------------------------------------------------------

def boussinesq_stress(
    q: float,
    a: float,
    z: float,
) -> dict:
    """
    Vertical stress σ_z under the centre of a uniformly loaded circular area.

    Boussinesq (1885) elastic half-space solution for uniform circular load:

        σ_z = q × [1 - z³ / (a² + z²)^(3/2)]

    Parameters
    ----------
    q : float
        Contact pressure (Pa). Must be > 0.
    a : float
        Radius of loaded area (m). Must be > 0.
    z : float
        Depth below surface at which stress is evaluated (m). Must be > 0.

    Returns
    -------
    dict
        ok        : True
        sigma_z_Pa: vertical stress at depth z under centre (Pa)
        q_Pa      : contact pressure used (Pa)
        a_m       : radius used (m)
        z_m       : depth used (m)
        stress_ratio: σ_z / q (dimensionless)

    Notes
    -----
    Valid only under the centre of the loaded area.  At z=0 (surface)
    σ_z = q by definition (not computed here as division by zero; z must be > 0).
    The half-space assumption implies a semi-infinite homogeneous elastic medium.

    Unit system: SI (Pa, metres).
    """
    err = _guard_positive("q", q)
    if err:
        return _err(err)
    err = _guard_positive("a", a)
    if err:
        return _err(err)
    err = _guard_positive("z", z)
    if err:
        return _err(err)

    q_val = float(q)
    a_val = float(a)
    z_val = float(z)

    # Boussinesq formula under centre of circular load
    sigma_z = q_val * (1.0 - z_val ** 3 / (a_val ** 2 + z_val ** 2) ** 1.5)

    return {
        "ok": True,
        "sigma_z_Pa": sigma_z,
        "q_Pa": q_val,
        "a_m": a_val,
        "z_m": z_val,
        "stress_ratio": sigma_z / q_val,
    }


# ---------------------------------------------------------------------------
# AASHTO '93 Rigid Pavement — Slab Thickness
# ---------------------------------------------------------------------------

# AASHTO '93 rigid pavement design equation (log10 form):
#
# log10(W18) = ZR·S0 + 7.35·log10(D+1) - 0.06
#              + log10(ΔPSI / (4.5 - 1.5)) / (1 + 1.624×10^7 / (D+1)^8.46)
#              + (4.22 - 0.32·pt) × log10(
#                  Sc·Cd × (D^0.75 - 1.132) /
#                  (215.63·J × (D^0.75 - 18.42 / (Ec/k)^0.25))
#                )
#
# where:
#   D  = slab thickness (in.)
#   Sc = PCC modulus of rupture (psi)
#   Cd = drainage coefficient
#   J  = load transfer coefficient
#   Ec = PCC elastic modulus (psi)
#   k  = modulus of subgrade reaction (pci)
#   pt = terminal serviceability (default 2.5)

_PSI_INITIAL_RIGID = 4.5   # initial PSI for rigid pavement (AASHTO '93)


def _aashto93_rigid_lhs(
    D: float,
    ZR: float, S0: float, DPSI: float,
    Sc: float, Cd: float, J: float, Ec: float, k: float,
    pt: float = 2.5,
) -> float:
    """Return predicted log10(W18) from AASHTO '93 rigid pavement equation."""
    if D <= 0:
        return -999.0

    log_w18 = (
        ZR * S0
        + 7.35 * math.log10(D + 1.0)
        - 0.06
        + math.log10(DPSI / (_PSI_INITIAL_RIGID - 1.5))
        / (1.0 + 1.624e7 / (D + 1.0) ** 8.46)
    )

    # Structural term
    denom_inner = 215.63 * J * (D ** 0.75 - 18.42 / (Ec / k) ** 0.25)
    numer_inner = Sc * Cd * (D ** 0.75 - 1.132)

    if abs(denom_inner) < 1e-12 or numer_inner <= 0:
        return -999.0

    log_w18 += (4.22 - 0.32 * pt) * math.log10(numer_inner / denom_inner)

    return log_w18


def aashto93_rigid_thickness(
    W18: float,
    ZR: float,
    S0: float,
    DPSI: float,
    Sc: float,
    Cd: float,
    J: float,
    Ec: float,
    k: float,
    pt: float = 2.5,
) -> dict:
    """
    Rigid (PCC) slab thickness via iterative AASHTO '93 equation.

    Parameters
    ----------
    W18 : float
        Design ESALs. Must be > 0.
    ZR : float
        Standard normal deviate for reliability. Finite.
    S0 : float
        Overall standard deviation for rigid pavement. Typical: 0.35. > 0.
    DPSI : float
        Design serviceability loss = PSI_initial - PSI_terminal.
        For rigid pavement, PSI_initial = 4.5 (AASHTO).
        Typical: 4.5 - 2.5 = 2.0. Must be in (0, 4.5).
    Sc : float
        PCC modulus of rupture (psi). Typical: 600–700 psi. Must be > 0.
    Cd : float
        Drainage coefficient. Typical: 0.7–1.25. Must be > 0.
    J : float
        Load transfer coefficient. Typical: 3.2 (dowelled), 3.8–4.4 (undowelled).
        Must be > 0.
    Ec : float
        PCC elastic modulus (psi). Typical: 4e6 psi. Must be > 0.
    k : float
        Modulus of subgrade reaction (pci). Must be > 0.
        Use cbr_to_k() to convert from CBR %.
    pt : float
        Terminal serviceability index. Default 2.5. Must be in [1.5, 3.5].

    Returns
    -------
    dict
        ok      : True
        D_in    : required slab thickness (inches)
        W18     : design ESALs
        ZR, S0, DPSI, Sc, Cd, J, Ec, k, pt: inputs echoed
        warnings: list

    Notes
    -----
    Solved by bisection on D ∈ [2, 30] inches.
    AASHTO '93, Part III, Chapter 2.

    PCA fatigue/erosion criteria are not evaluated here — those require
    separate concrete fatigue tables.  See Huang (2004) §12-5.

    Unit system: US customary (D in inches, Sc/Ec in psi, k in pci).
    """
    warnings: list[str] = []

    try:
        W18 = float(W18)
    except (TypeError, ValueError):
        return _err(f"W18 must be a number, got {W18!r}")
    if not math.isfinite(W18) or W18 <= 0:
        return _err(f"W18 must be > 0 and finite, got {W18}")

    try:
        ZR = float(ZR)
    except (TypeError, ValueError):
        return _err(f"ZR must be a number, got {ZR!r}")
    if not math.isfinite(ZR):
        return _err(f"ZR must be finite, got {ZR}")

    for name, val in [("S0", S0), ("Sc", Sc), ("Cd", Cd), ("J", J), ("Ec", Ec), ("k", k)]:
        err = _guard_positive(name, val)
        if err:
            return _err(err)

    err = _guard_range("DPSI", DPSI, 0.01, 4.49)
    if err:
        return _err(err)

    err = _guard_range("pt", pt, 1.5, 3.5)
    if err:
        return _err(err)

    target = math.log10(float(W18))

    lo, hi = 2.0, 30.0
    # Check range feasibility
    if _aashto93_rigid_lhs(hi, ZR, float(S0), float(DPSI),
                            float(Sc), float(Cd), float(J), float(Ec), float(k), float(pt)) < target:
        warnings.append(
            "AASHTO '93 rigid equation cannot converge at D=30 in. — "
            "traffic or material inputs may be extreme."
        )
        return {
            "ok": True,
            "D_in": 30.0,
            "W18": float(W18),
            "ZR": float(ZR),
            "S0": float(S0),
            "DPSI": float(DPSI),
            "Sc": float(Sc),
            "Cd": float(Cd),
            "J": float(J),
            "Ec": float(Ec),
            "k": float(k),
            "pt": float(pt),
            "warnings": warnings,
        }

    for _ in range(120):
        mid = (lo + hi) / 2.0
        val = _aashto93_rigid_lhs(mid, ZR, float(S0), float(DPSI),
                                   float(Sc), float(Cd), float(J), float(Ec), float(k), float(pt))
        if val < target:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-5:
            break

    D_result = (lo + hi) / 2.0
    # Round up to nearest 0.5 in. (standard practice)
    D_rounded = math.ceil(D_result / 0.5) * 0.5

    if D_rounded < 6.0:
        warnings.append(
            f"D={D_rounded:.1f} in. is below the typical minimum slab "
            "thickness of 6 in. — verify inputs or consider light-traffic design."
        )
    if D_rounded > 24.0:
        warnings.append(
            f"D={D_rounded:.1f} in. is very thick — consider staged construction "
            "or reducing design period."
        )

    return {
        "ok": True,
        "D_in": D_rounded,
        "D_in_exact": D_result,
        "W18": float(W18),
        "ZR": float(ZR),
        "S0": float(S0),
        "DPSI": float(DPSI),
        "Sc": float(Sc),
        "Cd": float(Cd),
        "J": float(J),
        "Ec": float(Ec),
        "k": float(k),
        "pt": float(pt),
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Joint spacing & dowel bar size
# ---------------------------------------------------------------------------

def joint_spacing(
    h_slab_mm: float,
    coeff_thermal: float = 10e-6,
    delta_temp: float = 30.0,
    allow_strain: float = 2.0e-4,
) -> dict:
    """
    Contraction joint spacing for rigid pavement slab.

    Based on limiting curling/warping strain:

        L_joint = allow_strain / (coeff_thermal × delta_temp)

    Parameters
    ----------
    h_slab_mm : float
        Slab thickness (mm). Used to enforce L/h <= 20 practical limit. > 0.
    coeff_thermal : float
        Coefficient of thermal expansion of PCC (1/°C).
        Default: 10e-6 /°C (typical PCC).
    delta_temp : float
        Temperature differential (°C) — top to bottom of slab.
        Default: 30°C. Must be > 0.
    allow_strain : float
        Allowable joint opening strain for aggregate interlock.
        Default: 2.0e-4 (0.02%, conservative for joint sealant performance).
        Must be > 0.

    Returns
    -------
    dict
        ok            : True
        L_joint_m     : recommended joint spacing (m)
        L_joint_mm    : recommended joint spacing (mm)
        L_over_h_ratio: L/h ratio (should be <= 20–25 for crack control)
        h_slab_mm     : slab thickness used (mm)
        warnings      : list

    Unit system: SI (mm, m, °C).
    """
    warnings: list[str] = []

    err = _guard_positive("h_slab_mm", h_slab_mm)
    if err:
        return _err(err)
    err = _guard_positive("coeff_thermal", coeff_thermal)
    if err:
        return _err(err)
    err = _guard_positive("delta_temp", delta_temp)
    if err:
        return _err(err)
    err = _guard_positive("allow_strain", allow_strain)
    if err:
        return _err(err)

    ct = float(coeff_thermal)
    dT = float(delta_temp)
    eps = float(allow_strain)
    h = float(h_slab_mm)

    L_m = eps / (ct * dT)
    L_over_h = (L_m * 1000.0) / h

    if L_over_h > 25.0:
        warnings.append(
            f"L/h = {L_over_h:.1f} > 25 — increase temperature differential "
            "or reduce allowable strain to tighten joint spacing."
        )
    if L_m > 6.0:
        warnings.append(
            f"Joint spacing L={L_m:.2f} m > 6 m — transverse cracking risk "
            "increases; consider L <= 4.5–6 m for highway pavements."
        )

    return {
        "ok": True,
        "L_joint_m": L_m,
        "L_joint_mm": L_m * 1000.0,
        "L_over_h_ratio": L_over_h,
        "h_slab_mm": h,
        "warnings": warnings,
    }


def dowel_bar_size(h_slab_mm: float) -> dict:
    """
    Recommended dowel bar diameter for rigid pavement joints.

    AASHTO/ACI rule of thumb: dowel diameter ≈ slab_thickness / 8,
    rounded to the nearest standard bar size.

    Parameters
    ----------
    h_slab_mm : float
        Slab thickness (mm). Must be > 0.

    Returns
    -------
    dict
        ok               : True
        h_slab_mm        : slab thickness used (mm)
        dowel_diameter_mm: recommended dowel bar diameter (mm)
        dowel_spacing_mm : recommended dowel spacing (mm, typically 300 mm)
        dowel_length_mm  : recommended dowel bar length (mm)
        warnings         : list

    Notes
    -----
    Standard dowel bar diameters (mm): 19, 22, 25, 29, 32, 38, 44, 50.
    Spacing typically 300 mm (12 in.) c/c.
    Length typically 450–500 mm.

    Unit system: SI (mm).
    """
    warnings: list[str] = []

    err = _guard_positive("h_slab_mm", h_slab_mm)
    if err:
        return _err(err)

    h = float(h_slab_mm)
    d_raw = h / 8.0

    _std_dowels = [19.0, 22.0, 25.0, 29.0, 32.0, 38.0, 44.0, 50.0]
    # Select smallest standard size >= d_raw
    d_sel = _std_dowels[-1]
    for sd in _std_dowels:
        if sd >= d_raw:
            d_sel = sd
            break

    if h < 150.0:
        warnings.append(
            f"Slab thickness {h:.0f} mm < 150 mm — rigid pavement slabs are "
            "typically >= 150 mm for vehicular traffic."
        )

    return {
        "ok": True,
        "h_slab_mm": h,
        "dowel_diameter_mm": d_sel,
        "dowel_spacing_mm": 300.0,
        "dowel_length_mm": 450.0,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Frost penetration depth — modified Berggren / Stefan simplified
# ---------------------------------------------------------------------------

def frost_penetration_depth(
    freezing_index_degC_days: float,
    k_soil: float,
    L_soil: float,
) -> dict:
    """
    Frost penetration depth via modified Berggren simplified (Stefan) equation.

    Simplified Stefan equation:
        z_frost = sqrt(2 × k_soil × FI × 86400 / L_soil)

    where:
        k_soil  = thermal conductivity of frozen soil (W/m·K)
        FI      = freezing index (degree-days, °C·days)
        L_soil  = volumetric latent heat of soil (J/m³)
                = 334 000 J/kg × ρ_dry × w    (w = water content fraction)

    Parameters
    ----------
    freezing_index_degC_days : float
        Air freezing index (degree-days Celsius). Must be > 0.
        Typical: 100–3000 °C·days depending on climate.
    k_soil : float
        Thermal conductivity of frozen soil (W/m·K). Must be > 0.
        Typical: 0.5–2.5 W/m·K for moist soils.
    L_soil : float
        Volumetric latent heat of soil (J/m³). Must be > 0.
        Typical: 40–120 MJ/m³ (40e6–120e6 J/m³).

    Returns
    -------
    dict
        ok             : True
        z_frost_m      : frost penetration depth (m)
        FI             : freezing index used (°C·days)
        k_soil         : thermal conductivity used (W/m·K)
        L_soil         : latent heat used (J/m³)
        warnings       : list

    Notes
    -----
    The simplified Stefan equation ignores the sensible heat of the soil and
    surface temperature fluctuations.  The modified Berggren method applies
    a lambda correction factor (typically 0.5–1.0) for more accuracy.
    This function returns the unmodified Stefan result (lambda = 1.0).

    Unit system: SI (metres, W/m·K, J/m³, °C·days).
    """
    warnings: list[str] = []

    err = _guard_positive("freezing_index_degC_days", freezing_index_degC_days)
    if err:
        return _err(err)
    err = _guard_positive("k_soil", k_soil)
    if err:
        return _err(err)
    err = _guard_positive("L_soil", L_soil)
    if err:
        return _err(err)

    FI = float(freezing_index_degC_days)
    ks = float(k_soil)
    Ls = float(L_soil)

    # FI in °C·days × 86400 s/day = °C·s
    z_frost = math.sqrt(2.0 * ks * FI * 86400.0 / Ls)

    if z_frost > 3.0:
        warnings.append(
            f"z_frost={z_frost:.2f} m > 3 m — verify freezing index and soil "
            "properties; very deep frost penetration."
        )
    if FI > 2000:
        warnings.append(
            f"Freezing index FI={FI:.0f} °C·days is very high "
            "(subarctic/arctic conditions)."
        )

    return {
        "ok": True,
        "z_frost_m": z_frost,
        "FI": FI,
        "k_soil": ks,
        "L_soil": Ls,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Overlay thickness — SN-deficiency method
# ---------------------------------------------------------------------------

def overlay_thickness_sn(
    SN_existing: float,
    SN_required: float,
    a_overlay: float,
) -> dict:
    """
    Asphalt overlay thickness from SN-deficiency method (AASHTO '93).

    The required overlay thickness to bring a deteriorated pavement up to
    the required structural number:

        D_OL = (SN_required - SN_existing_eff) / a_OL

    where SN_existing_eff is the effective existing SN (may be less than
    as-built SN due to structural deterioration).

    Parameters
    ----------
    SN_existing : float
        Effective existing structural number (as-built × condition factor).
        Must be >= 0.
    SN_required : float
        Required structural number for remaining design period. Must be > 0.
    a_overlay : float
        Layer coefficient for overlay material.
        HMA: typically 0.42–0.44/in.  Must be > 0.

    Returns
    -------
    dict
        ok           : True
        D_overlay_in : required overlay thickness (inches)
        SN_deficiency: SN_required - SN_existing (deficit to cover)
        SN_existing  : SN_existing used
        SN_required  : SN_required used
        a_overlay    : a_overlay used
        warnings     : list

    Notes
    -----
    If SN_existing >= SN_required, overlay is not structurally needed
    (D_overlay = 0); a warning is issued.

    Unit system: US customary (SN and D in inches; a in 1/in.).
    """
    warnings: list[str] = []

    err = _guard_nonneg("SN_existing", SN_existing)
    if err:
        return _err(err)
    err = _guard_positive("SN_required", SN_required)
    if err:
        return _err(err)
    err = _guard_positive("a_overlay", a_overlay)
    if err:
        return _err(err)

    SN_e = float(SN_existing)
    SN_r = float(SN_required)
    a_ol = float(a_overlay)

    SN_def = SN_r - SN_e

    if SN_def <= 0:
        warnings.append(
            f"SN_existing={SN_e:.3f} >= SN_required={SN_r:.3f} — "
            "overlay is not structurally required; consider surface correction only."
        )
        D_ol = 0.0
    else:
        D_ol_raw = SN_def / a_ol
        # Round up to nearest 0.5 in.
        D_ol = math.ceil(D_ol_raw / 0.5) * 0.5
        if D_ol < 1.5:
            warnings.append(
                f"Overlay D={D_ol:.1f} in. < 1.5 in. — minimum HMA overlay "
                "thickness for adequate compaction is 1.5 in. (38 mm)."
            )

    return {
        "ok": True,
        "D_overlay_in": D_ol,
        "SN_deficiency": max(SN_def, 0.0),
        "SN_existing": SN_e,
        "SN_required": SN_r,
        "a_overlay": a_ol,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Asphalt quantity
# ---------------------------------------------------------------------------

def asphalt_quantity(
    length_m: float,
    width_m: float,
    thickness_m: float,
    density_kg_m3: float = 2350.0,
) -> dict:
    """
    Asphalt mix quantity for a pavement layer.

    Parameters
    ----------
    length_m : float
        Pavement length (m). Must be > 0.
    width_m : float
        Pavement width (m). Must be > 0.
    thickness_m : float
        Layer thickness (m). Must be > 0.
    density_kg_m3 : float
        Compacted HMA density (kg/m³). Default: 2350 kg/m³ (typical HMA).
        Must be > 0.

    Returns
    -------
    dict
        ok            : True
        volume_m3     : layer volume (m³)
        mass_kg       : mix mass (kg)
        mass_tonnes   : mix mass (tonnes)
        area_m2       : pavement area (m²)
        length_m      : length used (m)
        width_m       : width used (m)
        thickness_m   : thickness used (m)
        density_kg_m3 : density used (kg/m³)
        warnings      : list

    Notes
    -----
    Add 5–10% wastage to the computed mass for procurement.

    Unit system: SI (metres, kg, tonnes).
    """
    warnings: list[str] = []

    err = _guard_positive("length_m", length_m)
    if err:
        return _err(err)
    err = _guard_positive("width_m", width_m)
    if err:
        return _err(err)
    err = _guard_positive("thickness_m", thickness_m)
    if err:
        return _err(err)
    err = _guard_positive("density_kg_m3", density_kg_m3)
    if err:
        return _err(err)

    L = float(length_m)
    W = float(width_m)
    T = float(thickness_m)
    rho = float(density_kg_m3)

    area = L * W
    vol = area * T
    mass_kg = vol * rho
    mass_t = mass_kg / 1000.0

    if T < 0.025:
        warnings.append(
            f"thickness_m={T:.4f} m ({T*1000:.1f} mm) < 25 mm — "
            "very thin HMA lifts are impractical to compact uniformly."
        )
    if T > 0.30:
        warnings.append(
            f"thickness_m={T:.3f} m ({T*1000:.0f} mm) > 300 mm — "
            "a single HMA lift this thick is unusual; use multiple lifts."
        )

    return {
        "ok": True,
        "volume_m3": vol,
        "mass_kg": mass_kg,
        "mass_tonnes": mass_t,
        "area_m2": area,
        "length_m": L,
        "width_m": W,
        "thickness_m": T,
        "density_kg_m3": rho,
        "warnings": warnings,
    }
