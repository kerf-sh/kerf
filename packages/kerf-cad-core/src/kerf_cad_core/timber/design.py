"""
kerf_cad_core.timber.design — NDS allowable-stress timber design (pure Python).

Distinct from:
  struct/    — general steel frame analysis (AISC)
  concrete/  — ACI 318 reinforced-concrete
  steelconn/ — bolted/welded steel connections
  beam/      — generic elastic beam deflection/moment/shear solver

Implements the full NDS 2018 Allowable Stress Design (ASD) methodology:

ADJUSTMENT FACTORS
------------------
  CD_load_duration(load_type)
      Load-duration factor CD per NDS Table 2.3.2.

  CM_wet(prop, species_type)
      Wet-service factor CM for sawn lumber or glulam.

  Ct_temp(prop, temp_F)
      Temperature factor Ct per NDS Table 2.3.4.

  CL_beam_stability(le_ft, b_in, d_in, E_prime_psi, Fb_prime_no_CL_psi)
      Beam stability factor CL via Ylinen equation (NDS §3.3.3).

  CF_size(prop, b_in, d_in)
      Size factor CF for visually graded sawn lumber (NDS Supplement Table 4A).
      Not applicable to glulam (returns 1.0).

  Cfu_flat_use(b_in, d_in)
      Flat-use factor Cfu for sawn lumber bending flat (NDS Supplement).

  Ci_incising(prop)
      Incising factor Ci per NDS 4.3.8 (for incised lumber for preservative treatment).

  Cr_repetitive(b_in, spacing_in)
      Repetitive-member factor Cr = 1.15 when b <= 2" nominal and
      spacing <= 24" and >= 3 parallel members (NDS §4.3.9).

  CP_column_stability(le_d, Fc_star_psi, FcE_psi)
      Column stability factor CP via Ylinen equation (NDS §3.7.1).

SECTION PROPERTIES
------------------
  sawn_section(b_nom_in, d_nom_in)
      Dressed dimensions and section properties for standard sawn lumber.
      Returns A, S, I (in², in³, in⁴) from dressed (S4S) dimensions.

  glulam_section(b_in, d_in)
      Section properties for a glulam (actual dimensions given directly).

ADJUSTED DESIGN VALUES
----------------------
  adjusted_Fb(Fb_ref, CD, CM, Ct, CL, CF, Cfu, Ci, Cr)
      Fb' = Fb × CD × CM × Ct × CL × CF × Cfu × Ci × Cr

  adjusted_Fv(Fv_ref, CD, CM, Ct, Ci)
      Fv' = Fv × CD × CM × Ct × Ci

  adjusted_Fc(Fc_ref, CD, CM, Ct, CF, Ci, CP)
      Fc' = Fc × CD × CM × Ct × CF × Ci × CP

  adjusted_Fc_perp(Fc_perp_ref, CM, Ct, Ci, Cb)
      Fc_perp' = Fc_perp × CM × Ct × Ci × Cb

  adjusted_E_prime(E_ref, CM, Ct, Ci)
      E' = E × CM × Ct × Ci

CHECKS
------
  check_bending(fb_psi, Fb_prime_psi)
      Bending check: fb <= Fb'. Returns utilization ratio.

  check_shear(fv_psi, Fv_prime_psi)
      Shear check: fv <= Fv'. Returns utilization ratio.

  check_deflection(delta_L_in, delta_TL_in, span_in, *, limit_L=360, limit_TL=240)
      Deflection limits: live-load L/360 (default), total-load L/240 (default).

  check_compression_column(fc_psi, Fc_prime_psi)
      Column compression check: fc <= Fc'. Returns utilization ratio.

  check_combined_bending_axial(fb_psi, Fb_prime_psi, fc_psi, Fc_star_psi, FcE_psi)
      NDS §3.9.2 combined interaction equation.

  check_bearing(fc_perp_psi, Fc_perp_prime_psi)
      Bearing (perpendicular-to-grain) check.

  FcE_critical(E_prime_psi, le_d)
      Euler critical buckling stress FcE = 0.822 E' / (le/d)².

FASTENERS
---------
  lateral_yield_bolt(D_in, tm_in, ts_in, Fyb_psi, Fe_m_psi, Fe_s_psi, theta_deg)
      Single-fastener lateral yield load (NDS Table I2.2 yield limit modes
      Im, Is, II, IIIm, IIIs, IV) for a single-shear bolt or lag screw.
      Returns governing mode and Z (lb).

  withdrawal_nail(D_in, L_pen_in, G)
      Nail withdrawal per NDS §12.2: W = 1380 × G^(5/2) × D^(3/2) [lb/in].
      Returns W_per_in and W_total for L_pen.

REFERENCE DESIGN VALUE TABLE
-----------------------------
  reference_design_values(species, grade)
      Look up tabulated Fb, Fv, Fc, Fc_perp, E (psi) for selected
      species/grade combinations from NDS Supplement Table 4A/4B.

Units
-----
  stress / pressure : psi (pounds per square inch)
  section dims      : inches
  moment            : lb·in
  force             : lb
  modulus           : psi

References
----------
NDS 2018 — National Design Specification for Wood Construction (AWC)
NDS Supplement 2018 — Design Values for Wood Construction
Breyer, D.E. et al. "Design of Wood Structures", 7th ed.
AFPA Technical Report No. 14 — Designing for Lateral-Torsional Buckling

Author: imranparuk
"""
from __future__ import annotations

import math
from typing import Any
from kerf_cad_core._guards import _err, _guard_nonneg, _guard_positive


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_CD_TABLE: dict[str, float] = {
    "permanent":       0.9,
    "ten_year":        1.0,
    "two_month":       1.15,
    "seven_day":       1.25,
    "ten_minute":      1.6,
    "impact":          2.0,
    # Common aliases
    "dead":            0.9,
    "live":            1.0,
    "floor_live":      1.0,
    "snow":            1.15,
    "roof_live":       1.25,
    "wind":            1.6,
    "seismic":         1.6,
    "construction":    1.25,
}


def CD_load_duration(load_type: str) -> dict:
    """Load duration factor CD (NDS Table 2.3.2).

    Parameters
    ----------
    load_type : str
        One of: permanent/dead (0.9), ten_year/live/floor_live (1.0),
        two_month/snow (1.15), seven_day/roof_live/construction (1.25),
        ten_minute/wind/seismic (1.6), impact (2.0).

    Returns
    -------
    dict  ok=True, CD (float), load_type
    """
    key = str(load_type).strip().lower().replace(" ", "_").replace("-", "_")
    if key not in _CD_TABLE:
        valid = sorted(set(_CD_TABLE.keys()))
        return _err(f"Unknown load_type {load_type!r}. Supported: {valid}.")
    return {"ok": True, "CD": _CD_TABLE[key], "load_type": key}


# ---------------------------------------------------------------------------
# CM — Wet-service factors (NDS §4.3.3 / §5.3.3)
# ---------------------------------------------------------------------------

# CM for sawn lumber (NDS Supplement Table 4A footnotes)
_CM_SAWN: dict[str, float] = {
    "Fb":      0.85,
    "Fv":      0.97,
    "Fc":      0.80,
    "Fc_perp": 0.67,
    "Ft":      1.00,
    "E":       0.90,
    "Emin":    0.90,
}

# CM for glulam (NDS Supplement Table 5A footnotes)
_CM_GLULAM: dict[str, float] = {
    "Fb":      0.80,
    "Fv":      0.875,
    "Fc":      0.73,
    "Fc_perp": 0.53,
    "Ft":      0.80,
    "E":       0.833,
    "Emin":    0.833,
}


def CM_wet(prop: str, species_type: str = "sawn") -> dict:
    """Wet-service factor CM.

    Parameters
    ----------
    prop : str
        Property key: Fb, Fv, Fc, Fc_perp, Ft, E, Emin.
    species_type : str
        "sawn" (default) or "glulam".

    Returns
    -------
    dict  ok=True, CM, prop, species_type
    """
    st = str(species_type).strip().lower()
    if st not in ("sawn", "glulam"):
        return _err(f"species_type must be 'sawn' or 'glulam', got {species_type!r}.")
    table = _CM_SAWN if st == "sawn" else _CM_GLULAM
    p = str(prop).strip()
    if p not in table:
        return _err(f"Unknown prop {prop!r}. Supported: {sorted(table.keys())}.")
    return {"ok": True, "CM": table[p], "prop": p, "species_type": st}


# ---------------------------------------------------------------------------
# Ct — Temperature factors (NDS Table 2.3.4)
# NDS defines Ct for T <= 100°F → 1.0; 100 < T <= 125°F → reduced;
# 125 < T <= 150°F → further reduced.  Above 150°F → not applicable.
# ---------------------------------------------------------------------------

def Ct_temp(prop: str, temp_F: float) -> dict:
    """Temperature factor Ct (NDS 2018 Table 2.3.3).

    Parameters
    ----------
    prop : str
        Property: Fb, Fv, Fc, Fc_perp, Ft, E, Emin.
    temp_F : float
        In-service temperature (°F).  Must be <= 150 for NDS applicability.

    Returns
    -------
    dict  ok=True, Ct, prop, temp_F
    """
    props_fb_fv_fc_ft = {"Fb", "Fv", "Fc", "Ft"}
    props_fc_perp = {"Fc_perp"}
    props_E = {"E", "Emin"}
    all_props = props_fb_fv_fc_ft | props_fc_perp | props_E
    p = str(prop).strip()
    if p not in all_props:
        return _err(f"Unknown prop {prop!r}. Supported: {sorted(all_props)}.")
    if not math.isfinite(float(temp_F)):
        return _err(f"temp_F must be finite, got {temp_F}.")
    T = float(temp_F)
    if T > 150.0:
        return _err(f"temp_F={T} exceeds NDS limit of 150°F for Ct applicability.")

    # NDS 2018 Table 2.3.3 (dry / in-service moisture content ≤ 19%):
    #   T ≤ 100°F                  : Ct = 1.0 (all)
    #   100°F < T ≤ 125°F          : Fb,Fv,Fc,Fc⊥,Ft = 0.8 ; E,Emin = 0.9
    #   125°F < T ≤ 150°F          : Fb,Fv,Fc,Fc⊥,Ft = 0.7 ; E,Emin = 0.9
    # Fc⊥ takes the SAME factor as Fb/Fv/Fc/Ft (it is not given a separate
    # reduced value in NDS Table 2.3.3 for the dry condition).
    if T <= 100.0:
        Ct = 1.0
    elif T <= 125.0:
        if p in props_E:
            Ct = 0.9
        else:  # Fb, Fv, Fc, Ft, Fc_perp
            Ct = 0.8
    else:  # 125 < T <= 150
        if p in props_E:
            Ct = 0.9
        else:  # Fb, Fv, Fc, Ft, Fc_perp
            Ct = 0.7

    return {"ok": True, "Ct": Ct, "prop": p, "temp_F": T}


# ---------------------------------------------------------------------------
# CL — Beam Stability Factor (NDS §3.3.3 Ylinen equation)
# ---------------------------------------------------------------------------

def CL_beam_stability(
    le_ft: float,
    b_in: float,
    d_in: float,
    E_prime_psi: float,
    Fb_prime_no_CL_psi: float,
) -> dict:
    """Beam stability factor CL (NDS §3.3.3).

    CL is computed via the Ylinen (Appendix H) equation:

        RB = sqrt(le·d / b²)         (slenderness ratio for bending)
        FbE = 1.20·E'_min / RB²      (critical buckling stress)
        *  Note: NDS uses E'_min (min modulus). Here we accept E' directly.
           Caller should pass E'_min × 0.85 (or appropriate E'_min).
        Fb* = Fb × all factors except CL
        alpha = FbE / Fb*
        CL = (1 + alpha)/(1.9) − sqrt(((1+alpha)/1.9)² − alpha/0.95)

    Parameters
    ----------
    le_ft : float
        Effective unbraced length (ft) of the compression edge.
    b_in : float
        Breadth (narrow face) of beam (in). Must be > 0.
    d_in : float
        Depth of beam (in). Must be > 0.
    E_prime_psi : float
        Adjusted modulus of elasticity E'_min (psi). Must be > 0.
    Fb_prime_no_CL_psi : float
        Adjusted Fb* (psi) with all factors applied except CL. Must be > 0.

    Returns
    -------
    dict  ok=True, CL, RB, FbE_psi, alpha, warnings (list)
    """
    for name, val in [
        ("le_ft", le_ft), ("b_in", b_in), ("d_in", d_in),
        ("E_prime_psi", E_prime_psi), ("Fb_prime_no_CL_psi", Fb_prime_no_CL_psi),
    ]:
        e = _guard_positive(name, val)
        if e:
            return _err(e)

    le_in = float(le_ft) * 12.0
    b = float(b_in)
    d = float(d_in)
    E_min = float(E_prime_psi)
    Fb_star = float(Fb_prime_no_CL_psi)

    warnings: list[str] = []

    # RB — slenderness ratio for bending (NDS §3.3.3.2)
    RB_sq = (le_in * d) / (b * b)
    RB = math.sqrt(RB_sq)

    if RB > 50.0:
        warnings.append(f"Beam slenderness RB={RB:.2f} > 50; exceeds NDS limit.")

    # FbE (NDS Eq. 3.3-6)
    FbE = 1.20 * E_min / RB_sq

    alpha = FbE / Fb_star
    A = (1.0 + alpha) / 1.9
    CL = A - math.sqrt(A * A - alpha / 0.95)
    CL = max(0.0, min(CL, 1.0))

    return {
        "ok": True,
        "CL": CL,
        "RB": RB,
        "FbE_psi": FbE,
        "alpha": alpha,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# CF — Size factor for visually graded sawn lumber (NDS Supplement Table 4A)
# ---------------------------------------------------------------------------

def CF_size(prop: str, b_in: float, d_in: float) -> dict:
    """Size factor CF for visually graded sawn lumber (NDS Supplement §4.3.6).

    Applies to Fb, Ft, Fc for members with d > 12 in (or width <= 4 in).
    Returns CF = (12/d)^(1/9) for Fb when d > 12.
    For Fc: CF = (12/d)^(1/9) when d > 12.
    For Ft: same as Fb.
    Not applicable to glulam — returns 1.0 for glulam.

    Parameters
    ----------
    prop : str
        "Fb", "Ft", "Fc", or "other" (returns 1.0).
    b_in : float
        Dressed breadth (in).
    d_in : float
        Dressed depth (in).

    Returns
    -------
    dict  ok=True, CF, prop, b_in, d_in
    """
    for name, val in [("b_in", b_in), ("d_in", d_in)]:
        e = _guard_positive(name, val)
        if e:
            return _err(e)

    p = str(prop).strip()
    b = float(b_in)
    d = float(d_in)

    # NDS size factor exponent  = 1/9
    if p in ("Fb", "Ft"):
        if d <= 12.0:
            CF = 1.0
        else:
            CF = (12.0 / d) ** (1.0 / 9.0)
        # Additional CF for Fb when b <= 3 in (NDS Supplement footnote)
        if b <= 3.0 and d > 8.0:
            CF = min(CF, (12.0 / d) ** (1.0 / 9.0))
    elif p == "Fc":
        if d <= 12.0:
            CF = 1.0
        else:
            CF = (12.0 / d) ** (1.0 / 9.0)
    else:
        CF = 1.0

    return {"ok": True, "CF": CF, "prop": p, "b_in": b, "d_in": d}


# ---------------------------------------------------------------------------
# Cfu — Flat-use factor (NDS §4.3.7)
# ---------------------------------------------------------------------------

# NDS Supplement Table 4A Cfu for sawn lumber loaded on edge vs flat
# Simplified: Cfu = (b/d)^(1/9) when b > d (loaded flat, "weak-axis bending")
def Cfu_flat_use(b_in: float, d_in: float) -> dict:
    """Flat-use factor Cfu (NDS §4.3.7).

    When a member is loaded about its strong axis (d > b), Cfu = 1.0.
    When loaded about its weak axis / flat (b >= d), NDS permits
    Cfu = (b/d)^(1/9) >= 1.0 (increases allowable stress slightly).

    Parameters
    ----------
    b_in : float
        Dressed breadth/width (in).
    d_in : float
        Dressed depth (in).

    Returns
    -------
    dict  ok=True, Cfu, b_in, d_in, flat_use (bool)
    """
    for name, val in [("b_in", b_in), ("d_in", d_in)]:
        e = _guard_positive(name, val)
        if e:
            return _err(e)

    b = float(b_in)
    d = float(d_in)

    if b >= d:
        # flat use — bending about weak axis
        Cfu = (b / d) ** (1.0 / 9.0)
        flat_use = True
    else:
        Cfu = 1.0
        flat_use = False

    return {"ok": True, "Cfu": Cfu, "b_in": b, "d_in": d, "flat_use": flat_use}


# ---------------------------------------------------------------------------
# Ci — Incising factor (NDS §4.3.8)
# ---------------------------------------------------------------------------

_CI_TABLE: dict[str, float] = {
    "Fb": 0.80,
    "Ft": 0.80,
    "Fv": 0.875,
    "Fc": 0.80,
    "Fc_perp": 1.00,
    "E": 0.95,
    "Emin": 0.95,
}


def Ci_incising(prop: str) -> dict:
    """Incising factor Ci for pressure-treated incised lumber (NDS §4.3.8).

    Parameters
    ----------
    prop : str
        Property key: Fb, Ft, Fv, Fc, Fc_perp, E, Emin.

    Returns
    -------
    dict  ok=True, Ci, prop
    """
    p = str(prop).strip()
    if p not in _CI_TABLE:
        return _err(f"Unknown prop {prop!r}. Supported: {sorted(_CI_TABLE.keys())}.")
    return {"ok": True, "Ci": _CI_TABLE[p], "prop": p}


# ---------------------------------------------------------------------------
# Cr — Repetitive member factor (NDS §4.3.9)
# ---------------------------------------------------------------------------

def Cr_repetitive(b_in: float, spacing_in: float) -> dict:
    """Repetitive-member factor Cr (NDS §4.3.9).

    Cr = 1.15 when:
      - member is 2" to 4" thick (b <= 4 in nominal, dressed b <= 3.5 in)
      - spacing <= 24 in on-center
      - >= 3 parallel members (always assumed here; caller confirms)
      - members are connected by a structural panel or sheathing

    Parameters
    ----------
    b_in : float
        Dressed breadth (in).
    spacing_in : float
        On-center spacing (in).

    Returns
    -------
    dict  ok=True, Cr, repetitive (bool), b_in, spacing_in
    """
    for name, val in [("b_in", b_in), ("spacing_in", spacing_in)]:
        e = _guard_positive(name, val)
        if e:
            return _err(e)

    b = float(b_in)
    sp = float(spacing_in)

    # Repetitive applies to 2x, 3x, 4x lumber (dressed b <= 3.5 in) at <= 24" oc
    repetitive = (b <= 3.5) and (sp <= 24.0)
    Cr = 1.15 if repetitive else 1.0

    return {"ok": True, "Cr": Cr, "repetitive": repetitive, "b_in": b, "spacing_in": sp}


# ---------------------------------------------------------------------------
# FcE — Euler critical buckling stress for columns (NDS §3.7.1)
# ---------------------------------------------------------------------------

def FcE_critical(E_prime_psi: float, le_d: float) -> dict:
    """Euler critical buckling stress for a column (NDS §3.7.1).

    FcE = 0.822 × E'_min / (le/d)²

    Parameters
    ----------
    E_prime_psi : float
        Adjusted modulus of elasticity E'_min (psi). Must be > 0.
    le_d : float
        Slenderness ratio le/d (effective length / least dimension). Must be > 0.

    Returns
    -------
    dict  ok=True, FcE_psi, E_prime_psi, le_d, warnings (list)
    """
    for name, val in [("E_prime_psi", E_prime_psi), ("le_d", le_d)]:
        e = _guard_positive(name, val)
        if e:
            return _err(e)

    E_min = float(E_prime_psi)
    le_d_val = float(le_d)

    warnings: list[str] = []
    if le_d_val > 50.0:
        warnings.append(
            f"Slenderness le/d={le_d_val:.2f} > 50; exceeds NDS maximum per §3.7.1.3."
        )

    FcE = 0.822 * E_min / (le_d_val ** 2)

    return {"ok": True, "FcE_psi": FcE, "E_prime_psi": E_min, "le_d": le_d_val, "warnings": warnings}


# ---------------------------------------------------------------------------
# CP — Column stability factor (NDS §3.7.1 Ylinen equation)
# ---------------------------------------------------------------------------

def CP_column_stability(le_d: float, Fc_star_psi: float, FcE_psi: float) -> dict:
    """Column stability factor CP via Ylinen equation (NDS §3.7.1).

    CP = (1 + alpha)/(2c) − sqrt(((1+alpha)/(2c))² − alpha/c)

    where alpha = FcE / Fc*  and  c = 0.8 for sawn lumber, 0.9 for glulam.
    (NDS uses c=0.8 for sawn and c=0.9 for glulam.)
    Here c=0.8 (conservative default, appropriate for sawn lumber).

    Parameters
    ----------
    le_d : float
        Slenderness ratio le/d.
    Fc_star_psi : float
        Fc* = Fc × all factors except CP (psi).
    FcE_psi : float
        Euler critical buckling stress = 0.822·E'_min / (le/d)² (psi).

    Returns
    -------
    dict  ok=True, CP, alpha, le_d, Fc_star_psi, FcE_psi, warnings (list)
    """
    for name, val in [("le_d", le_d), ("Fc_star_psi", Fc_star_psi), ("FcE_psi", FcE_psi)]:
        e = _guard_positive(name, val)
        if e:
            return _err(e)

    le_d_val = float(le_d)
    Fc_star = float(Fc_star_psi)
    FcE = float(FcE_psi)

    warnings: list[str] = []
    if le_d_val > 50.0:
        warnings.append(
            f"Slenderness le/d={le_d_val:.2f} > 50; exceeds NDS limit per §3.7.1.3."
        )

    c = 0.8  # sawn lumber
    alpha = FcE / Fc_star
    two_c = 2.0 * c
    A = (1.0 + alpha) / two_c
    CP = A - math.sqrt(A * A - alpha / c)
    CP = max(0.0, min(CP, 1.0))

    return {
        "ok": True,
        "CP": CP,
        "alpha": alpha,
        "c": c,
        "le_d": le_d_val,
        "Fc_star_psi": Fc_star,
        "FcE_psi": FcE,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Section properties — sawn lumber (dressed S4S dimensions)
# ---------------------------------------------------------------------------

# NDS Supplement Table 1B — Dressed (S4S) dimensions for standard lumber
# Format: nominal (b_nom, d_nom) → dressed (b_act, d_act) in inches
_SAWN_DRESSED: dict[tuple[int, int], tuple[float, float]] = {
    (2, 4):  (1.5,  3.5),
    (2, 6):  (1.5,  5.5),
    (2, 8):  (1.5,  7.25),
    (2, 10): (1.5,  9.25),
    (2, 12): (1.5, 11.25),
    (2, 14): (1.5, 13.25),
    (3, 4):  (2.5,  3.5),
    (3, 6):  (2.5,  5.5),
    (3, 8):  (2.5,  7.25),
    (3, 10): (2.5,  9.25),
    (3, 12): (2.5, 11.25),
    (4, 4):  (3.5,  3.5),
    (4, 6):  (3.5,  5.5),
    (4, 8):  (3.5,  7.25),
    (4, 10): (3.5,  9.25),
    (4, 12): (3.5, 11.25),
    (6, 6):  (5.5,  5.5),
    (6, 8):  (5.5,  7.5),
    (6, 10): (5.5,  9.5),
    (6, 12): (5.5, 11.5),
    (8, 8):  (7.5,  7.5),
    (8, 10): (7.5,  9.5),
    (8, 12): (7.5, 11.5),
    (10, 10): (9.5, 9.5),
    (10, 12): (9.5, 11.5),
    (12, 12): (11.5, 11.5),
}


def sawn_section(b_nom_in: int, d_nom_in: int) -> dict:
    """Section properties for standard dressed (S4S) sawn lumber.

    Parameters
    ----------
    b_nom_in : int
        Nominal breadth (in), e.g. 2, 3, 4, 6, 8, 10, 12.
    d_nom_in : int
        Nominal depth (in), e.g. 4, 6, 8, 10, 12, 14.

    Returns
    -------
    dict  ok=True, b_nom, d_nom, b_actual_in, d_actual_in,
          A_in2, S_in3, I_in4
    """
    key = (int(b_nom_in), int(d_nom_in))
    if key not in _SAWN_DRESSED:
        # Try also with d > b convention
        key_alt = (int(d_nom_in), int(b_nom_in))
        if key_alt in _SAWN_DRESSED:
            key = key_alt
        else:
            available = sorted(_SAWN_DRESSED.keys())
            return _err(
                f"Nominal size {b_nom_in}x{d_nom_in} not in dressed-dimension table. "
                f"Available: {available}."
            )

    b_act, d_act = _SAWN_DRESSED[key]
    A = b_act * d_act
    S = b_act * d_act ** 2 / 6.0
    I = b_act * d_act ** 3 / 12.0

    return {
        "ok": True,
        "b_nom_in": key[0],
        "d_nom_in": key[1],
        "b_actual_in": b_act,
        "d_actual_in": d_act,
        "A_in2": A,
        "S_in3": S,
        "I_in4": I,
    }


def glulam_section(b_in: float, d_in: float) -> dict:
    """Section properties for a glulam (actual dimensions given directly).

    Parameters
    ----------
    b_in : float
        Actual breadth (in). Must be > 0.
    d_in : float
        Actual depth (in). Must be > 0.

    Returns
    -------
    dict  ok=True, b_actual_in, d_actual_in, A_in2, S_in3, I_in4
    """
    for name, val in [("b_in", b_in), ("d_in", d_in)]:
        e = _guard_positive(name, val)
        if e:
            return _err(e)

    b = float(b_in)
    d = float(d_in)
    A = b * d
    S = b * d ** 2 / 6.0
    I = b * d ** 3 / 12.0

    return {
        "ok": True,
        "b_actual_in": b,
        "d_actual_in": d,
        "A_in2": A,
        "S_in3": S,
        "I_in4": I,
    }


# ---------------------------------------------------------------------------
# Adjusted design values
# ---------------------------------------------------------------------------

def adjusted_Fb(
    Fb_ref: float,
    CD: float = 1.0,
    CM: float = 1.0,
    Ct: float = 1.0,
    CL: float = 1.0,
    CF: float = 1.0,
    Cfu: float = 1.0,
    Ci: float = 1.0,
    Cr: float = 1.0,
) -> dict:
    """Adjusted allowable bending stress Fb' (NDS §2.3).

    Fb' = Fb × CD × CM × Ct × CL × CF × Cfu × Ci × Cr

    Returns
    -------
    dict  ok=True, Fb_prime_psi, factors (dict)
    """
    for name, val in [
        ("Fb_ref", Fb_ref), ("CD", CD), ("CM", CM), ("Ct", Ct),
        ("CL", CL), ("CF", CF), ("Cfu", Cfu), ("Ci", Ci), ("Cr", Cr),
    ]:
        e = _guard_positive(name, val)
        if e:
            return _err(e)

    Fb_prime = (float(Fb_ref) * float(CD) * float(CM) * float(Ct) *
                float(CL) * float(CF) * float(Cfu) * float(Ci) * float(Cr))

    return {
        "ok": True,
        "Fb_prime_psi": Fb_prime,
        "factors": {
            "Fb_ref": float(Fb_ref), "CD": float(CD), "CM": float(CM),
            "Ct": float(Ct), "CL": float(CL), "CF": float(CF),
            "Cfu": float(Cfu), "Ci": float(Ci), "Cr": float(Cr),
        },
    }


def adjusted_Fv(
    Fv_ref: float,
    CD: float = 1.0,
    CM: float = 1.0,
    Ct: float = 1.0,
    Ci: float = 1.0,
) -> dict:
    """Adjusted allowable shear stress Fv' = Fv × CD × CM × Ct × Ci."""
    for name, val in [("Fv_ref", Fv_ref), ("CD", CD), ("CM", CM), ("Ct", Ct), ("Ci", Ci)]:
        e = _guard_positive(name, val)
        if e:
            return _err(e)
    Fv_prime = float(Fv_ref) * float(CD) * float(CM) * float(Ct) * float(Ci)
    return {
        "ok": True,
        "Fv_prime_psi": Fv_prime,
        "factors": {
            "Fv_ref": float(Fv_ref), "CD": float(CD),
            "CM": float(CM), "Ct": float(Ct), "Ci": float(Ci),
        },
    }


def adjusted_Fc(
    Fc_ref: float,
    CD: float = 1.0,
    CM: float = 1.0,
    Ct: float = 1.0,
    CF: float = 1.0,
    Ci: float = 1.0,
    CP: float = 1.0,
) -> dict:
    """Adjusted allowable compression-parallel stress Fc' = Fc × CD × CM × Ct × CF × Ci × CP."""
    for name, val in [
        ("Fc_ref", Fc_ref), ("CD", CD), ("CM", CM), ("Ct", Ct),
        ("CF", CF), ("Ci", Ci), ("CP", CP),
    ]:
        e = _guard_positive(name, val)
        if e:
            return _err(e)
    Fc_prime = (float(Fc_ref) * float(CD) * float(CM) * float(Ct) *
                float(CF) * float(Ci) * float(CP))
    return {
        "ok": True,
        "Fc_prime_psi": Fc_prime,
        "factors": {
            "Fc_ref": float(Fc_ref), "CD": float(CD), "CM": float(CM),
            "Ct": float(Ct), "CF": float(CF), "Ci": float(Ci), "CP": float(CP),
        },
    }


def adjusted_Fc_perp(
    Fc_perp_ref: float,
    CM: float = 1.0,
    Ct: float = 1.0,
    Ci: float = 1.0,
    Cb: float = 1.0,
) -> dict:
    """Adjusted Fc_perp' = Fc_perp × CM × Ct × Ci × Cb.

    Cb is the bearing area factor (NDS §3.10.4).
    """
    for name, val in [("Fc_perp_ref", Fc_perp_ref), ("CM", CM), ("Ct", Ct), ("Ci", Ci), ("Cb", Cb)]:
        e = _guard_positive(name, val)
        if e:
            return _err(e)
    Fc_perp_prime = float(Fc_perp_ref) * float(CM) * float(Ct) * float(Ci) * float(Cb)
    return {
        "ok": True,
        "Fc_perp_prime_psi": Fc_perp_prime,
        "factors": {
            "Fc_perp_ref": float(Fc_perp_ref), "CM": float(CM),
            "Ct": float(Ct), "Ci": float(Ci), "Cb": float(Cb),
        },
    }


def adjusted_E_prime(
    E_ref: float,
    CM: float = 1.0,
    Ct: float = 1.0,
    Ci: float = 1.0,
) -> dict:
    """Adjusted modulus E' = E × CM × Ct × Ci."""
    for name, val in [("E_ref", E_ref), ("CM", CM), ("Ct", Ct), ("Ci", Ci)]:
        e = _guard_positive(name, val)
        if e:
            return _err(e)
    E_prime = float(E_ref) * float(CM) * float(Ct) * float(Ci)
    return {
        "ok": True,
        "E_prime_psi": E_prime,
        "factors": {"E_ref": float(E_ref), "CM": float(CM), "Ct": float(Ct), "Ci": float(Ci)},
    }


# ---------------------------------------------------------------------------
# Bearing area factor Cb (NDS §3.10.4)
# ---------------------------------------------------------------------------

def Cb_bearing_area(lb_in: float) -> dict:
    """Bearing area factor Cb (NDS §3.10.4).

    Cb = (lb + 0.375) / lb  for lb < 6 in (does not apply at ends of beams)
    Cb = 1.0 for lb >= 6 in or end bearings.

    Parameters
    ----------
    lb_in : float
        Bearing length (in).

    Returns
    -------
    dict  ok=True, Cb, lb_in
    """
    e = _guard_positive("lb_in", lb_in)
    if e:
        return _err(e)
    lb = float(lb_in)
    Cb = (lb + 0.375) / lb if lb < 6.0 else 1.0
    return {"ok": True, "Cb": Cb, "lb_in": lb}


# ---------------------------------------------------------------------------
# Stress calculations
# ---------------------------------------------------------------------------

def bending_stress(M_lbin: float, S_in3: float) -> dict:
    """Bending stress fb = M / S.

    Parameters
    ----------
    M_lbin : float
        Applied bending moment (lb·in). Must be >= 0.
    S_in3 : float
        Section modulus (in³). Must be > 0.

    Returns
    -------
    dict  ok=True, fb_psi
    """
    e = _guard_nonneg("M_lbin", M_lbin)
    if e:
        return _err(e)
    e = _guard_positive("S_in3", S_in3)
    if e:
        return _err(e)
    return {"ok": True, "fb_psi": float(M_lbin) / float(S_in3)}


def shear_stress(V_lb: float, A_in2: float) -> dict:
    """Maximum shear stress fv = 1.5 × V / A (rectangular section).

    Parameters
    ----------
    V_lb : float
        Shear force (lb). Must be >= 0.
    A_in2 : float
        Cross-sectional area (in²). Must be > 0.

    Returns
    -------
    dict  ok=True, fv_psi
    """
    e = _guard_nonneg("V_lb", V_lb)
    if e:
        return _err(e)
    e = _guard_positive("A_in2", A_in2)
    if e:
        return _err(e)
    return {"ok": True, "fv_psi": 1.5 * float(V_lb) / float(A_in2)}


# ---------------------------------------------------------------------------
# Design checks
# ---------------------------------------------------------------------------

def check_bending(fb_psi: float, Fb_prime_psi: float) -> dict:
    """Bending check: fb <= Fb' (NDS §3.3).

    Returns
    -------
    dict  ok=True, pass_ (bool), utilization (fb/Fb'), fb_psi, Fb_prime_psi,
          warnings (list)
    """
    for name, val in [("fb_psi", fb_psi), ("Fb_prime_psi", Fb_prime_psi)]:
        e = _guard_positive(name, val)
        if e:
            return _err(e)
    fb = float(fb_psi)
    Fb_p = float(Fb_prime_psi)
    util = fb / Fb_p
    warnings: list[str] = []
    if util > 1.0:
        warnings.append(f"Bending FAILS: fb={fb:.1f} > Fb'={Fb_p:.1f} psi (util={util:.3f}).")
    return {
        "ok": True,
        "pass_": util <= 1.0,
        "utilization": util,
        "fb_psi": fb,
        "Fb_prime_psi": Fb_p,
        "warnings": warnings,
    }


def check_shear(fv_psi: float, Fv_prime_psi: float) -> dict:
    """Shear check: fv <= Fv' (NDS §3.4).

    Returns
    -------
    dict  ok=True, pass_ (bool), utilization, fv_psi, Fv_prime_psi, warnings
    """
    for name, val in [("fv_psi", fv_psi), ("Fv_prime_psi", Fv_prime_psi)]:
        e = _guard_positive(name, val)
        if e:
            return _err(e)
    fv = float(fv_psi)
    Fv_p = float(Fv_prime_psi)
    util = fv / Fv_p
    warnings: list[str] = []
    if util > 1.0:
        warnings.append(f"Shear FAILS: fv={fv:.1f} > Fv'={Fv_p:.1f} psi (util={util:.3f}).")
    return {
        "ok": True,
        "pass_": util <= 1.0,
        "utilization": util,
        "fv_psi": fv,
        "Fv_prime_psi": Fv_p,
        "warnings": warnings,
    }


def check_deflection(
    delta_L_in: float,
    delta_TL_in: float,
    span_in: float,
    *,
    limit_L: float = 360.0,
    limit_TL: float = 240.0,
) -> dict:
    """Deflection check for live-load and total-load limits.

    Limits per NDS Table 3.5 (IBC / ASCE 7):
      Live load:  delta_L <= L / limit_L  (default L/360)
      Total load: delta_TL <= L / limit_TL (default L/240)

    Parameters
    ----------
    delta_L_in : float
        Live-load deflection (in). Must be >= 0.
    delta_TL_in : float
        Total-load deflection (in). Must be >= 0.
    span_in : float
        Clear span (in). Must be > 0.
    limit_L : float
        Live-load denominator (default 360).
    limit_TL : float
        Total-load denominator (default 240).

    Returns
    -------
    dict  ok=True, pass_ (bool), live_ok (bool), total_ok (bool),
          delta_L_in, delta_TL_in, span_in,
          limit_L_in (allowable live), limit_TL_in (allowable total),
          util_L, util_TL, warnings (list)
    """
    e = _guard_nonneg("delta_L_in", delta_L_in)
    if e:
        return _err(e)
    e = _guard_nonneg("delta_TL_in", delta_TL_in)
    if e:
        return _err(e)
    e = _guard_positive("span_in", span_in)
    if e:
        return _err(e)
    e = _guard_positive("limit_L", limit_L)
    if e:
        return _err(e)
    e = _guard_positive("limit_TL", limit_TL)
    if e:
        return _err(e)

    L = float(span_in)
    dL = float(delta_L_in)
    dTL = float(delta_TL_in)
    lim_L = float(limit_L)
    lim_TL = float(limit_TL)

    allow_L = L / lim_L
    allow_TL = L / lim_TL

    util_L = dL / allow_L if allow_L > 0 else float("inf")
    util_TL = dTL / allow_TL if allow_TL > 0 else float("inf")

    live_ok = util_L <= 1.0
    total_ok = util_TL <= 1.0
    pass_ = live_ok and total_ok

    warnings: list[str] = []
    if not live_ok:
        warnings.append(
            f"Live-load deflection FAILS: {dL:.4f}\" > L/{lim_L:.0f}={allow_L:.4f}\" "
            f"(util={util_L:.3f})."
        )
    if not total_ok:
        warnings.append(
            f"Total-load deflection FAILS: {dTL:.4f}\" > L/{lim_TL:.0f}={allow_TL:.4f}\" "
            f"(util={util_TL:.3f})."
        )

    return {
        "ok": True,
        "pass_": pass_,
        "live_ok": live_ok,
        "total_ok": total_ok,
        "delta_L_in": dL,
        "delta_TL_in": dTL,
        "span_in": L,
        "limit_L_in": allow_L,
        "limit_TL_in": allow_TL,
        "util_L": util_L,
        "util_TL": util_TL,
        "warnings": warnings,
    }


def check_compression_column(fc_psi: float, Fc_prime_psi: float) -> dict:
    """Column compression check: fc <= Fc' (NDS §3.7).

    Returns
    -------
    dict  ok=True, pass_ (bool), utilization, fc_psi, Fc_prime_psi, warnings
    """
    for name, val in [("fc_psi", fc_psi), ("Fc_prime_psi", Fc_prime_psi)]:
        e = _guard_positive(name, val)
        if e:
            return _err(e)
    fc = float(fc_psi)
    Fc_p = float(Fc_prime_psi)
    util = fc / Fc_p
    warnings: list[str] = []
    if util > 1.0:
        warnings.append(f"Column compression FAILS: fc={fc:.1f} > Fc'={Fc_p:.1f} psi (util={util:.3f}).")
    return {
        "ok": True,
        "pass_": util <= 1.0,
        "utilization": util,
        "fc_psi": fc,
        "Fc_prime_psi": Fc_p,
        "warnings": warnings,
    }


def check_combined_bending_axial(
    fb_psi: float,
    Fb_prime_psi: float,
    fc_psi: float,
    Fc_star_psi: float,
    FcE_psi: float,
    CP: float = 1.0,
) -> dict:
    """Combined bending + axial compression interaction (NDS §3.9.2).

    NDS 2018 Eq. (3.9-3) (single-axis bending):

        (fc / Fc')² + fb / (Fb' × [1 - fc/FcE]) <= 1.0

    where Fc' = Fc* × CP is the compression design value parallel to grain
    INCLUDING the column-stability factor CP (NDS §3.7.1).  The first
    (axial) term MUST use Fc' — using Fc* (without CP) understates the axial
    demand and is unconservative.  Pass the computed CP (from
    CP_column_stability); the function forms Fc' = Fc_star × CP internally.

    Parameters
    ----------
    fb_psi : float
        Actual bending stress (psi). Must be >= 0.
    Fb_prime_psi : float
        Adjusted allowable bending stress Fb' (psi).
    fc_psi : float
        Actual compression stress (psi). Must be >= 0.
    Fc_star_psi : float
        Fc* (Fc × all factors except CP) (psi).
    FcE_psi : float
        Euler critical buckling stress (psi).
    CP : float
        Column-stability factor (NDS §3.7.1), 0 < CP <= 1.  Default 1.0
        (back-compatible; only valid for a fully braced / stocky member).

    Returns
    -------
    dict  ok=True, pass_ (bool), interaction (float), warnings (list)
    """
    e = _guard_nonneg("fb_psi", fb_psi)
    if e:
        return _err(e)
    e = _guard_positive("Fb_prime_psi", Fb_prime_psi)
    if e:
        return _err(e)
    e = _guard_nonneg("fc_psi", fc_psi)
    if e:
        return _err(e)
    e = _guard_positive("Fc_star_psi", Fc_star_psi)
    if e:
        return _err(e)
    e = _guard_positive("FcE_psi", FcE_psi)
    if e:
        return _err(e)
    e = _guard_positive("CP", CP)
    if e:
        return _err(e)
    if float(CP) > 1.0:
        return _err(f"CP must be <= 1.0, got {CP}")

    fc = float(fc_psi)
    fb = float(fb_psi)
    Fb_p = float(Fb_prime_psi)
    Fc_star = float(Fc_star_psi)
    FcE = float(FcE_psi)
    # Fc' = Fc* × CP  (NDS §3.7.1 / Eq. 3.9-3 first term uses Fc', not Fc*)
    Fc_prime = Fc_star * float(CP)

    warnings: list[str] = []

    # Euler amplification denominator
    denom_euler = 1.0 - fc / FcE
    if denom_euler <= 0:
        warnings.append(
            f"fc={fc:.1f} >= FcE={FcE:.1f}; Euler amplification undefined (buckling imminent)."
        )
        interaction = float("inf")
        return {
            "ok": True,
            "pass_": False,
            "interaction": interaction,
            "warnings": warnings,
        }

    # NDS §3.9.2 interaction terms — axial term uses Fc' (= Fc* × CP)
    term1 = (fc / Fc_prime) ** 2
    term2 = fb / (Fb_p * denom_euler)
    interaction = term1 + term2

    if interaction > 1.0:
        warnings.append(
            f"Combined interaction FAILS: {interaction:.3f} > 1.0 "
            f"(term1={term1:.3f}, term2={term2:.3f})."
        )

    return {
        "ok": True,
        "pass_": interaction <= 1.0,
        "interaction": interaction,
        "term_axial": term1,
        "term_bending": term2,
        "fc_psi": fc,
        "fb_psi": fb,
        "Fc_star_psi": Fc_star,
        "Fc_prime_psi": Fc_prime,
        "CP": float(CP),
        "FcE_psi": FcE,
        "Fb_prime_psi": Fb_p,
        "warnings": warnings,
    }


def check_bearing(fc_perp_psi: float, Fc_perp_prime_psi: float) -> dict:
    """Bearing (perpendicular-to-grain) check: fc_perp <= Fc_perp' (NDS §3.10).

    Returns
    -------
    dict  ok=True, pass_ (bool), utilization, warnings
    """
    for name, val in [("fc_perp_psi", fc_perp_psi), ("Fc_perp_prime_psi", Fc_perp_prime_psi)]:
        e = _guard_positive(name, val)
        if e:
            return _err(e)
    fc_p = float(fc_perp_psi)
    Fc_pp = float(Fc_perp_prime_psi)
    util = fc_p / Fc_pp
    warnings: list[str] = []
    if util > 1.0:
        warnings.append(
            f"Bearing FAILS: fc_perp={fc_p:.1f} > Fc_perp'={Fc_pp:.1f} psi (util={util:.3f})."
        )
    return {
        "ok": True,
        "pass_": util <= 1.0,
        "utilization": util,
        "fc_perp_psi": fc_p,
        "Fc_perp_prime_psi": Fc_pp,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Fasteners — lateral yield (NDS yield-limit equations, single shear)
# ---------------------------------------------------------------------------

def lateral_yield_bolt(
    D_in: float,
    tm_in: float,
    ts_in: float,
    Fyb_psi: float,
    Fe_m_psi: float,
    Fe_s_psi: float,
    theta_deg: float = 0.0,
) -> dict:
    """Single-fastener lateral yield load Z (NDS Table I2.2, single shear).

    Implements NDS yield-limit equations for bolt/lag screw in single shear:
      Mode Im:  Z = D × tm × Fe_m / Rd
      Mode Is:  Z = D × ts × Fe_s / Rd
      Mode II:  Z = k1 × D × ts × Fe_s / Rd
      Mode IIIm: Z = k2 × D × tm × Fe_m / (1 + 2Re) / Rd
      Mode IIIs: Z = k3 × D × ts × Fe_s / (2 + Re) / Rd
      Mode IV:  Z = D² / Rd × sqrt(2Fe_m Fyb / (3(1+Re)))

    Rd is the reduction term per NDS Appendix I (Rd=4Kθ for modes Im/Is;
    Rd=3.6Kθ for mode II; Rd=3.2Kθ for modes IIIm/IIIs/IV).
    Kθ = 1 + θ/360 (theta_deg in degrees, 0 <= θ <= 90).

    Parameters
    ----------
    D_in : float
        Fastener diameter (in). Must be > 0.
    tm_in : float
        Main-member dowel bearing length (in). Must be > 0.
    ts_in : float
        Side-member dowel bearing length (in). Must be > 0.
    Fyb_psi : float
        Fastener bending yield strength (psi). Must be > 0.
    Fe_m_psi : float
        Dowel bearing strength of main member (psi). Must be > 0.
    Fe_s_psi : float
        Dowel bearing strength of side member (psi). Must be > 0.
    theta_deg : float
        Angle of load to grain (degrees, 0=parallel, 90=perp). Default 0.

    Returns
    -------
    dict  ok=True, Z_lb (governing), governing_mode (str),
          modes (dict of all mode Z values), warnings (list)
    """
    for name, val in [
        ("D_in", D_in), ("tm_in", tm_in), ("ts_in", ts_in),
        ("Fyb_psi", Fyb_psi), ("Fe_m_psi", Fe_m_psi), ("Fe_s_psi", Fe_s_psi),
    ]:
        e = _guard_positive(name, val)
        if e:
            return _err(e)
    e = _guard_nonneg("theta_deg", theta_deg)
    if e:
        return _err(e)

    D = float(D_in)
    tm = float(tm_in)
    ts = float(ts_in)
    Fyb = float(Fyb_psi)
    Fe_m = float(Fe_m_psi)
    Fe_s = float(Fe_s_psi)
    theta = float(theta_deg)

    warnings: list[str] = []

    # Kθ reduction factor
    K_theta = 1.0 + theta / 360.0

    # Rd values per NDS Appendix I Table I2.2
    Rd_Im = 4.0 * K_theta
    Rd_Is = 4.0 * K_theta
    Rd_II = 3.6 * K_theta
    Rd_III = 3.2 * K_theta
    Rd_IV = 3.2 * K_theta

    Re = Fe_m / Fe_s  # ratio of bearing strengths

    # k-coefficients (NDS App I Eq I-1, I-2, I-3)
    # k1 = sqrt(Re + 2Re²(1 + Rt + Rt²) + Rt²Re³) − Re(1+Rt) where Rt=tm/ts
    Rt = tm / ts

    k1_inner = (
        Re + 2.0 * Re ** 2 * (1.0 + Rt + Rt ** 2) + Rt ** 2 * Re ** 3
    )
    k1 = math.sqrt(max(k1_inner, 0.0)) - Re * (1.0 + Rt)

    k2 = -1.0 + math.sqrt(
        2.0 * (1.0 + Re) + (2.0 * Fyb * (1.0 + 2.0 * Re) * D ** 2) / (3.0 * Fe_m * tm ** 2)
    )

    k3 = -1.0 + math.sqrt(
        2.0 * (1.0 + Re) / Re + (2.0 * Fyb * (2.0 + Re) * D ** 2) / (3.0 * Fe_s * ts ** 2)
    )

    # Yield limit modes
    Z_Im = D * tm * Fe_m / Rd_Im
    Z_Is = D * ts * Fe_s / Rd_Is
    Z_II = k1 * D * ts * Fe_s / Rd_II
    Z_IIIm = k2 * D * tm * Fe_m / ((1.0 + 2.0 * Re) * Rd_III)
    Z_IIIs = k3 * D * ts * Fe_s / ((2.0 + Re) * Rd_III)
    Z_IV = (D ** 2 / Rd_IV) * math.sqrt(
        2.0 * Fe_m * Fyb / (3.0 * (1.0 + Re))
    )

    modes = {
        "Im": Z_Im,
        "Is": Z_Is,
        "II": Z_II,
        "IIIm": Z_IIIm,
        "IIIs": Z_IIIs,
        "IV": Z_IV,
    }

    # Governing = minimum positive mode
    positive_modes = {k: v for k, v in modes.items() if v > 0}
    if not positive_modes:
        return _err("All yield modes computed non-positive; check input values.")

    governing_mode = min(positive_modes, key=lambda k: positive_modes[k])
    Z = positive_modes[governing_mode]

    return {
        "ok": True,
        "Z_lb": Z,
        "governing_mode": governing_mode,
        "modes": modes,
        "D_in": D,
        "tm_in": tm,
        "ts_in": ts,
        "Fyb_psi": Fyb,
        "Fe_m_psi": Fe_m,
        "Fe_s_psi": Fe_s,
        "theta_deg": theta,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Fasteners — nail withdrawal (NDS §12.2)
# ---------------------------------------------------------------------------

def withdrawal_nail(D_in: float, L_pen_in: float, G: float) -> dict:
    """Nail withdrawal capacity (NDS §12.2).

    W = 1380 × G^(5/2) × D^(3/2)   [lb per inch of penetration]

    Parameters
    ----------
    D_in : float
        Nail shank diameter (in). Must be > 0.
    L_pen_in : float
        Penetration length into main member (in). Must be > 0.
    G : float
        Specific gravity of wood (oven-dry). Must be > 0.
        Typical: Douglas Fir-Larch 0.50, Southern Pine 0.55, Hem-Fir 0.43.

    Returns
    -------
    dict  ok=True, W_per_in_lb (lb/in), W_total_lb, D_in, L_pen_in, G, warnings
    """
    for name, val in [("D_in", D_in), ("L_pen_in", L_pen_in), ("G", G)]:
        e = _guard_positive(name, val)
        if e:
            return _err(e)

    D = float(D_in)
    L_pen = float(L_pen_in)
    Gv = float(G)

    warnings: list[str] = []
    if Gv > 1.0:
        warnings.append(f"G={Gv} > 1.0; check that this is specific gravity (oven-dry), not density.")

    W_per_in = 1380.0 * Gv ** 2.5 * D ** 1.5
    W_total = W_per_in * L_pen

    return {
        "ok": True,
        "W_per_in_lb": W_per_in,
        "W_total_lb": W_total,
        "D_in": D,
        "L_pen_in": L_pen,
        "G": Gv,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Reference design value table (NDS Supplement 2018 — selected values)
# ---------------------------------------------------------------------------

# Format: (species_group, grade) → {Fb, Fv, Fc, Fc_perp, Ft, E, Emin} psi
# Sources: NDS Supplement Table 4A (Visually Graded Dimension Lumber)
# Selected species-grade combinations only.
_REF_VALUES: dict[tuple[str, str], dict[str, float]] = {
    # Douglas Fir-Larch (NDS Supplement Table 4A)
    ("douglas_fir_larch", "select_structural"): {
        "Fb": 1500.0, "Fv": 180.0, "Fc": 1700.0, "Fc_perp": 625.0,
        "Ft": 1000.0, "E": 1_900_000.0, "Emin": 690_000.0,
    },
    ("douglas_fir_larch", "no_1"): {
        "Fb": 1000.0, "Fv": 180.0, "Fc": 1500.0, "Fc_perp": 625.0,
        "Ft": 675.0, "E": 1_700_000.0, "Emin": 620_000.0,
    },
    ("douglas_fir_larch", "no_2"): {
        "Fb": 900.0, "Fv": 180.0, "Fc": 1350.0, "Fc_perp": 625.0,
        "Ft": 575.0, "E": 1_600_000.0, "Emin": 580_000.0,
    },
    # Southern Pine (NDS Supplement Table 4B)
    ("southern_pine", "select_structural"): {
        "Fb": 1500.0, "Fv": 175.0, "Fc": 1800.0, "Fc_perp": 565.0,
        "Ft": 1000.0, "E": 1_800_000.0, "Emin": 660_000.0,
    },
    ("southern_pine", "no_1"): {
        "Fb": 1250.0, "Fv": 175.0, "Fc": 1550.0, "Fc_perp": 565.0,
        "Ft": 825.0, "E": 1_700_000.0, "Emin": 620_000.0,
    },
    ("southern_pine", "no_2"): {
        "Fb": 975.0, "Fv": 175.0, "Fc": 1250.0, "Fc_perp": 565.0,
        "Ft": 650.0, "E": 1_600_000.0, "Emin": 580_000.0,
    },
    # Hem-Fir (NDS Supplement Table 4A)
    ("hem_fir", "select_structural"): {
        "Fb": 1400.0, "Fv": 150.0, "Fc": 1500.0, "Fc_perp": 405.0,
        "Ft": 900.0, "E": 1_600_000.0, "Emin": 580_000.0,
    },
    ("hem_fir", "no_1"): {
        "Fb": 975.0, "Fv": 150.0, "Fc": 1350.0, "Fc_perp": 405.0,
        "Ft": 625.0, "E": 1_500_000.0, "Emin": 550_000.0,
    },
    ("hem_fir", "no_2"): {
        "Fb": 850.0, "Fv": 150.0, "Fc": 1300.0, "Fc_perp": 405.0,
        "Ft": 525.0, "E": 1_300_000.0, "Emin": 470_000.0,
    },
    # Spruce-Pine-Fir (NDS Supplement Table 4A)
    ("spruce_pine_fir", "select_structural"): {
        "Fb": 1250.0, "Fv": 135.0, "Fc": 1400.0, "Fc_perp": 425.0,
        "Ft": 700.0, "E": 1_500_000.0, "Emin": 550_000.0,
    },
    ("spruce_pine_fir", "no_1"): {
        "Fb": 875.0, "Fv": 135.0, "Fc": 1150.0, "Fc_perp": 425.0,
        "Ft": 450.0, "E": 1_400_000.0, "Emin": 510_000.0,
    },
    ("spruce_pine_fir", "no_2"): {
        "Fb": 875.0, "Fv": 135.0, "Fc": 1150.0, "Fc_perp": 425.0,
        "Ft": 450.0, "E": 1_400_000.0, "Emin": 510_000.0,
    },
}


def reference_design_values(species: str, grade: str) -> dict:
    """Tabulated NDS reference design values (NDS Supplement 2018, Table 4A/4B).

    Parameters
    ----------
    species : str
        Species group: douglas_fir_larch, southern_pine, hem_fir, spruce_pine_fir.
    grade : str
        Lumber grade: select_structural, no_1, no_2.

    Returns
    -------
    dict  ok=True, species, grade, Fb_psi, Fv_psi, Fc_psi, Fc_perp_psi,
          Ft_psi, E_psi, Emin_psi
    """
    sp = str(species).strip().lower().replace(" ", "_").replace("-", "_")
    gr = str(grade).strip().lower().replace(" ", "_").replace("-", "_")
    key = (sp, gr)
    if key not in _REF_VALUES:
        valid_species = sorted(set(k[0] for k in _REF_VALUES))
        valid_grades = sorted(set(k[1] for k in _REF_VALUES))
        return _err(
            f"No data for species={species!r} grade={grade!r}. "
            f"Species: {valid_species}. Grades: {valid_grades}."
        )
    v = _REF_VALUES[key]
    return {
        "ok": True,
        "species": sp,
        "grade": gr,
        "Fb_psi": v["Fb"],
        "Fv_psi": v["Fv"],
        "Fc_psi": v["Fc"],
        "Fc_perp_psi": v["Fc_perp"],
        "Ft_psi": v["Ft"],
        "E_psi": v["E"],
        "Emin_psi": v["Emin"],
    }
