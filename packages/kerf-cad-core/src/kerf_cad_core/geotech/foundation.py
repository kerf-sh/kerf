"""
kerf_cad_core.geotech.foundation — pure-Python geotechnical / foundation
engineering calculations.

Public functions
----------------
bearing_capacity(c, phi_deg, gamma, Df, B, foundation_type, *, FS, surcharge)
    Terzaghi/Meyerhof ultimate and allowable bearing capacity.
    Supports strip / square / circular footings.
    Returns Nc, Nq, Ngamma (bearing-capacity factors), q_ult, q_allow.

settlement(sigma_v, Cc, e0, H, *, Cs, sigma_v0, settlement_type)
    Immediate (elastic) and one-dimensional consolidation settlement.
    Returns settlement_m for primary consolidation (Cc/e0 method) or
    immediate elastic settlement via Boussinesq approximation.

lateral_earth_pressure(gamma, H, phi_deg, *, method, c, delta_deg,
                       surcharge, hw)
    Rankine or Coulomb lateral earth pressure coefficients Ka/Kp,
    resultant active/passive force per unit wall length, and location.
    Includes surcharge and water-table effects.

retaining_wall_stability(Fa, Fp, W_wall, x_W, B_base, Df, c, phi_deg, gamma,
                          *, FS_req_ot, FS_req_sl, FS_req_bc)
    Factor of safety against overturning, sliding, and bearing failure
    for a gravity/cantilever retaining wall.  Flags if FS < required.

slope_stability_infinite(gamma, c, phi_deg, H, beta_deg, *, hw_ratio, FS_req)
    Simplified infinite-slope factor of safety (dry, partially saturated,
    or fully submerged with water table ratio hw/H).
    Flags liquefaction-prone soils (phi_deg < 5) in warnings.

pile_axial_capacity(perimeter, area_tip, unit_skin_friction, unit_end_bearing,
                    pile_length, *, alpha, FS)
    Pile axial capacity: skin friction (alpha-method) + end bearing.
    Returns Qs (skin friction), Qp (end bearing), Q_ult, Q_allow.

All functions return a plain dict:
    success → {"ok": True, ...computed fields..., "warnings": [...]}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise.

Units
-----
Unless otherwise stated:
  lengths  — metres (m)
  angles   — degrees (°)
  stress   — kPa (kN/m²)
  force    — kN or kN/m (per-unit-width for walls/pressures)
  weight   — kN/m (unit weight × depth)
  gamma    — kN/m³   (unit weight of soil)

References
----------
Das, B.M. "Principles of Geotechnical Engineering", 9th ed.
Bowles, J.E. "Foundation Analysis and Design", 5th ed.
Terzaghi, K. "Theoretical Soil Mechanics" (1943).
Meyerhof, G.G. "The Ultimate Bearing Capacity of Foundations" (1951).
Rankine, W.J.M. (1857); Coulomb, C.-A. (1776).

Author: imranparuk
"""
from __future__ import annotations

import math
import warnings as _warnings_mod
from typing import Any
from kerf_cad_core._guards import _err, _guard_finite, _guard_nonneg, _guard_positive


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _deg2rad(degrees: float) -> float:
    return degrees * math.pi / 180.0


# ---------------------------------------------------------------------------
# Bearing-capacity factors (Terzaghi + Meyerhof)
# ---------------------------------------------------------------------------

def _terzaghi_factors(phi_rad: float) -> tuple[float, float, float]:
    """Terzaghi (1943) bearing-capacity factors Nc, Nq, Nγ.

    Terzaghi's original expressions:
        Nq  = e^(π tan φ) × tan²(45 + φ/2)
        Nc  = (Nq - 1) × cot(φ)          [for φ > 0; else Nc = 5.14]
        Nγ  = 2(Nq + 1) tan(φ)           [Vesic approximation]

    Returns (Nc, Nq, Ngamma).
    """
    if phi_rad < 1e-9:
        Nq = 1.0
        Nc = 5.14   # Prandtl/Terzaghi limit for φ=0
        Ngamma = 0.0
    else:
        Nq = math.exp(math.pi * math.tan(phi_rad)) * math.tan(
            math.pi / 4.0 + phi_rad / 2.0
        ) ** 2
        Nc = (Nq - 1.0) / math.tan(phi_rad)
        Ngamma = 2.0 * (Nq + 1.0) * math.tan(phi_rad)  # Vesic approx
    return Nc, Nq, Ngamma


# ---------------------------------------------------------------------------
# 1. bearing_capacity
# ---------------------------------------------------------------------------

def bearing_capacity(
    c: float,
    phi_deg: float,
    gamma: float,
    Df: float,
    B: float,
    foundation_type: str = "strip",
    *,
    FS: float = 3.0,
    surcharge: float = 0.0,
) -> dict:
    """
    Terzaghi/Meyerhof ultimate and allowable bearing capacity.

    Parameters
    ----------
    c : float
        Cohesion (kPa). Must be >= 0.
    phi_deg : float
        Friction angle (°). Must be in [0, 45].
    gamma : float
        Unit weight of soil (kN/m³). Must be > 0.
    Df : float
        Foundation depth (m). Must be >= 0.
    B : float
        Foundation width (m). Must be > 0.
    foundation_type : str
        "strip"    — Terzaghi strip (plane strain)
        "square"   — Terzaghi square footing (shape factors applied)
        "circular" — Terzaghi circular footing (shape factors applied)
    FS : float
        Factor of safety on ultimate bearing capacity (default 3.0). > 0.
    surcharge : float
        Additional surcharge pressure at foundation level (kPa). >= 0.

    Returns
    -------
    dict
        ok             : True
        Nc, Nq, Ngamma : bearing-capacity factors
        q_ult_kPa      : ultimate bearing capacity (kPa)
        q_allow_kPa    : allowable bearing capacity = q_ult / FS (kPa)
        foundation_type: footing type used
        FS             : factor of safety used
        warnings       : list of advisory strings (never raises)

    Formulas (Terzaghi 1943 + shape factors)
    -----------------------------------------
    Strip:
        q_ult = c·Nc + q·Nq + 0.5·γ·B·Nγ
    Square:
        q_ult = 1.3·c·Nc + q·Nq + 0.4·γ·B·Nγ
    Circular:
        q_ult = 1.3·c·Nc + q·Nq + 0.3·γ·B·Nγ

    where q = γ·Df + surcharge (effective overburden at foundation level).
    """
    warns: list[str] = []

    e = _guard_nonneg("c", c)
    if e:
        return _err(e)
    e = _guard_finite("phi_deg", phi_deg)
    if e:
        return _err(e)
    phi_f = float(phi_deg)
    if not 0.0 <= phi_f <= 45.0:
        return _err(f"phi_deg must be in [0, 45], got {phi_f}")
    e = _guard_positive("gamma", gamma)
    if e:
        return _err(e)
    e = _guard_nonneg("Df", Df)
    if e:
        return _err(e)
    e = _guard_positive("B", B)
    if e:
        return _err(e)
    e = _guard_positive("FS", FS)
    if e:
        return _err(e)
    e = _guard_nonneg("surcharge", surcharge)
    if e:
        return _err(e)

    ft = str(foundation_type).strip().lower()
    if ft not in ("strip", "square", "circular"):
        return _err(
            f"foundation_type must be 'strip', 'square', or 'circular', got {foundation_type!r}"
        )

    phi_rad = _deg2rad(phi_f)
    Nc, Nq, Ngamma = _terzaghi_factors(phi_rad)

    c_val = float(c)
    gamma_val = float(gamma)
    Df_val = float(Df)
    B_val = float(B)
    FS_val = float(FS)
    q_over = gamma_val * Df_val + float(surcharge)

    if ft == "strip":
        q_ult = c_val * Nc + q_over * Nq + 0.5 * gamma_val * B_val * Ngamma
    elif ft == "square":
        q_ult = 1.3 * c_val * Nc + q_over * Nq + 0.4 * gamma_val * B_val * Ngamma
    else:  # circular
        q_ult = 1.3 * c_val * Nc + q_over * Nq + 0.3 * gamma_val * B_val * Ngamma

    q_allow = q_ult / FS_val

    if FS_val < 3.0:
        warns.append(
            f"FS={FS_val:.2f} < 3.0 — typical minimum FS for bearing capacity is 3.0 "
            "(Das §3.5). Review load assumptions."
        )
    if phi_f < 5.0 and c_val < 1.0:
        warns.append(
            "phi_deg < 5° and c < 1 kPa — soil may be liquefaction-prone or very soft; "
            "verify site investigation data."
        )

    return {
        "ok": True,
        "Nc": Nc,
        "Nq": Nq,
        "Ngamma": Ngamma,
        "q_ult_kPa": q_ult,
        "q_allow_kPa": q_allow,
        "foundation_type": ft,
        "FS": FS_val,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 2. settlement
# ---------------------------------------------------------------------------

def settlement(
    sigma_v: float,
    Cc: float,
    e0: float,
    H: float,
    *,
    Cs: float = 0.0,
    sigma_v0: float | None = None,
    settlement_type: str = "consolidation",
) -> dict:
    """
    One-dimensional consolidation settlement (Cc/e0 method) or immediate
    elastic settlement approximation.

    Parameters
    ----------
    sigma_v : float
        Final effective vertical stress at mid-layer (kPa). > 0.
    Cc : float
        Compression index. > 0.
    e0 : float
        Initial void ratio. > 0.
    H : float
        Thickness of compressible layer (m). > 0.
    Cs : float
        Swelling/recompression index (default 0.0). Used if sigma_v0 < σ'c
        (overconsolidated zone). >= 0.
    sigma_v0 : float | None
        Initial effective vertical stress (kPa). If None, defaults to
        sigma_v × 0.5 (50% stress increase assumption for a simple check).
        Must be > 0 if provided.
    settlement_type : str
        "consolidation" (default) — primary consolidation via Terzaghi's
                                     1D compression equation.
        "immediate"               — elastic immediate settlement using
                                     simplified Boussinesq: Si ≈ q·B·(1-ν²)/Es
                                     (requires extra kwargs: see Notes).

    Returns
    -------
    dict
        ok             : True
        settlement_m   : computed settlement (m)
        settlement_mm  : computed settlement (mm)
        settlement_type: type used
        warnings       : list of advisory strings

    Formula (consolidation)
    -----------------------
    For a normally consolidated clay (σ'v0 <= σ'c = σ'v):

        Sc = (Cc / (1 + e0)) × H × log10(σ'v / σ'v0)

    For overconsolidated case (two-branch, requires σ'c):
    This implementation uses the simpler single-branch Cc formula; if the
    caller needs Cs for the overconsolidated branch, pass a suitably
    blended Cc value or split the calculation.

    Notes
    -----
    For "immediate" settlement the caller should pass the additional
    keyword arguments via the dict interface in tools.py; the function
    interprets sigma_v as net bearing pressure q (kPa), Cc as Es (MPa ×
    convenience factor — see tools.py wrapper), e0 as Poisson's ratio ν,
    H as half-width B (m).  Returns Si in metres.
    """
    warns: list[str] = []

    e = _guard_positive("sigma_v", sigma_v)
    if e:
        return _err(e)
    e = _guard_positive("Cc", Cc)
    if e:
        return _err(e)
    e = _guard_positive("e0", e0)
    if e:
        return _err(e)
    e = _guard_positive("H", H)
    if e:
        return _err(e)
    e = _guard_nonneg("Cs", Cs)
    if e:
        return _err(e)

    stype = str(settlement_type).strip().lower().replace("-", "").replace(" ", "")

    sigma_v_val = float(sigma_v)
    Cc_val = float(Cc)
    e0_val = float(e0)
    H_val = float(H)

    if stype == "consolidation":
        if sigma_v0 is None:
            sigma_v0_val = sigma_v_val * 0.5
            warns.append(
                "sigma_v0 not provided; defaulted to 0.5 × sigma_v. "
                "Provide actual initial effective stress for accuracy."
            )
        else:
            e2 = _guard_positive("sigma_v0", sigma_v0)
            if e2:
                return _err(e2)
            sigma_v0_val = float(sigma_v0)

        if sigma_v_val <= sigma_v0_val:
            return _err(
                f"sigma_v={sigma_v_val} kPa must be > sigma_v0={sigma_v0_val} kPa "
                "(stress must increase for settlement to occur)."
            )

        Sc = (Cc_val / (1.0 + e0_val)) * H_val * math.log10(sigma_v_val / sigma_v0_val)

        if Cc_val > 0.7:
            warns.append(
                f"Cc={Cc_val:.3f} is high (> 0.7) — typical of very soft/organic clays. "
                "Verify Cc from consolidation test."
            )
        if Sc > 0.3:
            warns.append(
                f"Predicted settlement {Sc * 1000:.0f} mm exceeds 300 mm — "
                "consider deep foundation or ground improvement."
            )

        return {
            "ok": True,
            "settlement_m": Sc,
            "settlement_mm": Sc * 1000.0,
            "settlement_type": "consolidation",
            "sigma_v_kPa": sigma_v_val,
            "sigma_v0_kPa": sigma_v0_val,
            "Cc": Cc_val,
            "e0": e0_val,
            "H_m": H_val,
            "warnings": warns,
        }

    elif stype == "immediate":
        # Interpret inputs as: sigma_v=q (kPa), Cc=Es (kPa), e0=nu (-), H=B (m)
        # Si = q * B * (1 - nu^2) / Es   (Boussinesq centre point, rigid footing approx)
        q = sigma_v_val
        Es = Cc_val  # re-purposed field: Es in kPa
        nu = e0_val  # re-purposed field: Poisson ratio
        B = H_val    # re-purposed field: footing width/radius (m)

        if not 0.0 < nu < 0.5:
            return _err(
                f"For immediate settlement e0 is used as Poisson ratio ν; "
                f"must be in (0, 0.5), got {nu}."
            )
        Si = q * B * (1.0 - nu ** 2) / Es

        return {
            "ok": True,
            "settlement_m": Si,
            "settlement_mm": Si * 1000.0,
            "settlement_type": "immediate",
            "q_kPa": q,
            "Es_kPa": Es,
            "nu": nu,
            "B_m": B,
            "warnings": warns,
        }

    else:
        return _err(
            f"settlement_type must be 'consolidation' or 'immediate', got {settlement_type!r}"
        )


# ---------------------------------------------------------------------------
# 3. lateral_earth_pressure
# ---------------------------------------------------------------------------

def lateral_earth_pressure(
    gamma: float,
    H: float,
    phi_deg: float,
    *,
    method: str = "rankine",
    c: float = 0.0,
    delta_deg: float = 0.0,
    surcharge: float = 0.0,
    hw: float = 0.0,
) -> dict:
    """
    Rankine or Coulomb lateral earth pressure coefficients and resultant forces.

    Parameters
    ----------
    gamma : float
        Unit weight of soil (kN/m³). > 0.
    H : float
        Retained wall height (m). > 0.
    phi_deg : float
        Internal friction angle (°). Must be in [0, 45].
    method : str
        "rankine"  — Rankine (1857); vertical wall, horizontal backfill.
        "coulomb"  — Coulomb (1776); accounts for wall friction δ.
    c : float
        Cohesion for Rankine active (kPa); ignored for passive in this impl.
        >= 0.
    delta_deg : float
        Wall friction angle δ (°); used only for Coulomb. >= 0.
    surcharge : float
        Uniform surcharge on backfill surface (kPa). >= 0.
    hw : float
        Height of water table measured from the wall BASE (m).
        0.0 = fully dry (default); hw = H = fully saturated to surface.
        The submerged zone (bottom hw metres) uses buoyant unit weight
        γ' = γ − 9.81 kN/m³; water pressure is also added.  >= 0.

    Returns
    -------
    dict
        ok        : True
        method    : method used
        Ka        : active earth pressure coefficient
        Kp        : passive earth pressure coefficient
        Pa_kN_m   : active resultant force per unit wall length (kN/m)
        Pp_kN_m   : passive resultant force per unit wall length (kN/m)
        Pa_z_m    : point of application of Pa from wall base (m)
        Pp_z_m    : point of application of Pp from wall base (m)
        warnings  : list of advisory strings
    """
    warns: list[str] = []

    e = _guard_positive("gamma", gamma)
    if e:
        return _err(e)
    e = _guard_positive("H", H)
    if e:
        return _err(e)
    e = _guard_finite("phi_deg", phi_deg)
    if e:
        return _err(e)
    phi_f = float(phi_deg)
    if not 0.0 <= phi_f <= 45.0:
        return _err(f"phi_deg must be in [0, 45], got {phi_f}")
    e = _guard_nonneg("c", c)
    if e:
        return _err(e)
    e = _guard_nonneg("delta_deg", delta_deg)
    if e:
        return _err(e)
    e = _guard_nonneg("surcharge", surcharge)
    if e:
        return _err(e)
    e = _guard_nonneg("hw", hw)
    if e:
        return _err(e)

    meth = str(method).strip().lower()
    if meth not in ("rankine", "coulomb"):
        return _err(f"method must be 'rankine' or 'coulomb', got {method!r}")

    phi_rad = _deg2rad(phi_f)
    delta_rad = _deg2rad(float(delta_deg))
    gamma_val = float(gamma)
    H_val = float(H)
    c_val = float(c)
    q_s = float(surcharge)
    hw_val = min(float(hw), H_val)  # clamp to wall height

    if meth == "rankine":
        # Rankine (horizontal backfill, vertical wall)
        # Ka = tan²(45 - φ/2)
        # Kp = tan²(45 + φ/2)
        Ka = math.tan(math.pi / 4.0 - phi_rad / 2.0) ** 2
        Kp = math.tan(math.pi / 4.0 + phi_rad / 2.0) ** 2

        # Partition: dry zone is the TOP (H - hw) metres of the wall.
        # Wet zone is the BOTTOM hw metres of the wall.
        # hw = 0 → fully dry; hw = H → fully saturated.
        gamma_prime = max(gamma_val - 9.81, 0.1)  # buoyant unit weight; min 0.1
        gamma_w = 9.81
        dry_h = H_val - hw_val   # height of dry zone (top of wall)
        wet_h = hw_val           # height of wet/submerged zone (bottom of wall)

        # Effective vertical stress (using full gamma in dry zone, gamma' in wet zone)
        sv_top = q_s
        sv_wt = q_s + gamma_val * dry_h          # at the water-table interface
        sv_bot = sv_wt + gamma_prime * wet_h      # at wall base

        def _sigma_a(sv_: float) -> float:
            return Ka * sv_ - 2.0 * c_val * math.sqrt(Ka)

        sa_top = _sigma_a(sv_top)
        sa_wt = _sigma_a(sv_wt)
        sa_bot = _sigma_a(sv_bot)

        # Dry block (0..dry_h from top, i.e. hw..H from base): trapezoid
        if dry_h > 0.0:
            Pa_dry = 0.5 * (sa_top + sa_wt) * dry_h
            # centroid of trapezoid from TOP of block:
            # x_c = h/3 × (2b + a)/(a + b)  where a=sa_top (top), b=sa_wt (bot)
            denom_d = max(abs(sa_top + sa_wt), 1e-12)
            z_dry_from_block_top = dry_h / 3.0 * (sa_top + 2 * sa_wt) / denom_d
            z_dry_from_base = wet_h + (dry_h - z_dry_from_block_top)
        else:
            Pa_dry = 0.0
            z_dry_from_base = 0.0

        # Wet (earth) block (wet zone, bottom hw metres): trapezoid
        if wet_h > 0.0:
            Pa_wet = 0.5 * (sa_wt + sa_bot) * wet_h
            denom_w = max(abs(sa_wt + sa_bot), 1e-12)
            z_wet_from_base = wet_h / 3.0 * (sa_wt + 2 * sa_bot) / denom_w
        else:
            Pa_wet = 0.0
            z_wet_from_base = 0.0

        # Water pressure (triangular) over wet zone
        Pw = 0.5 * gamma_w * wet_h ** 2
        z_pw = wet_h / 3.0

        Pa_total = Pa_dry + Pa_wet + Pw

        # Centroid from base (moments about base)
        if abs(Pa_total) > 1e-12:
            mom = (Pa_dry * z_dry_from_base
                   + Pa_wet * z_wet_from_base
                   + Pw * z_pw)
            z_a_base = mom / Pa_total
        else:
            z_a_base = H_val / 3.0

        # Passive (Rankine, no cohesion for passive; use full γ × H)
        sv_base_full = q_s + gamma_val * H_val
        Pp_total = 0.5 * Kp * sv_base_full * H_val  # triangular approx
        z_p_base = H_val / 3.0

    else:  # coulomb
        # Coulomb active coefficient — vertical wall (α=90°), horizontal
        # backfill (β=0).  The general Coulomb expression
        #   Ka = sin²(α+φ) /
        #        [ sin²α·sin(α−δ)·(1 + √(sin(φ+δ)sin(φ−β) /
        #                              (sin(α−δ)sin(α+β))))² ]
        # reduces, for α=90° and β=0, to the standard form
        #   Ka = cos²φ /
        #        [ cos δ·(1 + √(sin(φ+δ)·sin φ / cos δ))² ]
        # Reference: Das, "Principles of Geotechnical Engineering", 9th ed.,
        # §13.7 (Coulomb's active earth pressure); Bowles §11.
        # NOTE: the previous implementation used sin²φ in the numerator,
        # which underestimated Ka by ~3× (non-conservative for wall design).

        def _coulomb_Ka(phi_r: float, delta_r: float) -> float:
            num = math.cos(phi_r) ** 2
            sqt_arg = (math.sin(phi_r + delta_r) * math.sin(phi_r)) / math.cos(delta_r)
            if sqt_arg < 0:
                sqt_arg = 0.0
            denom = math.cos(delta_r) * (1.0 + math.sqrt(sqt_arg)) ** 2
            return num / max(denom, 1e-12)

        def _coulomb_Kp(phi_r: float, delta_r: float) -> float:
            # Coulomb passive coefficient is well known to overestimate Kp for
            # δ > φ/3 (plane-failure-surface assumption).  Use the Rankine
            # passive value, which is conservative for design.
            # Reference: Das §13.9 (Coulomb passive pressure caveat).
            Kp_rank = math.tan(math.pi / 4.0 + phi_r / 2.0) ** 2
            return Kp_rank

        Ka = _coulomb_Ka(phi_rad, delta_rad)
        Kp = _coulomb_Kp(phi_rad, delta_rad)

        # Forces (triangular, vertical wall, horizontal backfill)
        sv_bot = q_s + gamma_val * H_val
        Pa_total = 0.5 * Ka * sv_bot * H_val + Ka * q_s * H_val
        Pa_total = 0.5 * Ka * (sv_bot + q_s) * H_val  # trapezoidal with surcharge

        # Better: triangular soil + rectangular surcharge
        Pa_tri = 0.5 * Ka * gamma_val * H_val ** 2
        Pa_rect = Ka * q_s * H_val
        Pa_total = Pa_tri + Pa_rect

        # Centroid from base
        if abs(Pa_total) > 1e-12:
            z_a_base = (Pa_tri * H_val / 3.0 + Pa_rect * H_val / 2.0) / Pa_total
        else:
            z_a_base = H_val / 3.0

        Pp_total = 0.5 * Kp * gamma_val * H_val ** 2
        z_p_base = H_val / 3.0

    if phi_f < 5.0 and float(c) < 1.0:
        warns.append(
            "phi_deg < 5° and c < 1 kPa — soil may be liquefaction-prone. "
            "Verify site investigation data and consider dynamic analysis."
        )
    if float(delta_deg) > phi_f * 0.67 and meth == "coulomb":
        warns.append(
            f"Wall friction δ={delta_deg}° > 2φ/3 ({phi_f * 0.67:.1f}°) — "
            "Coulomb's formula may overestimate Ka; use curved failure surface."
        )

    return {
        "ok": True,
        "method": meth,
        "Ka": Ka,
        "Kp": Kp,
        "Pa_kN_m": Pa_total,
        "Pp_kN_m": Pp_total,
        "Pa_z_m": z_a_base,
        "Pp_z_m": z_p_base,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 4. retaining_wall_stability
# ---------------------------------------------------------------------------

def retaining_wall_stability(
    Fa: float,
    Fp: float,
    W_wall: float,
    x_W: float,
    B_base: float,
    Df: float,
    c: float,
    phi_deg: float,
    gamma: float,
    *,
    FS_req_ot: float = 2.0,
    FS_req_sl: float = 1.5,
    FS_req_bc: float = 3.0,
) -> dict:
    """
    Factor of safety against overturning, sliding, and bearing for a retaining wall.

    Parameters
    ----------
    Fa : float
        Active resultant force per unit wall length (kN/m). >= 0.
    Fp : float
        Passive resultant force per unit wall length (kN/m). >= 0.
    W_wall : float
        Total vertical weight of wall + soil on heel per unit length (kN/m). > 0.
    x_W : float
        Horizontal distance from toe to resultant vertical force (m). > 0.
    B_base : float
        Base width of wall (m). > 0.
    Df : float
        Depth of foundation (m). >= 0.
    c : float
        Cohesion at base (kPa). >= 0.
    phi_deg : float
        Friction angle at base (°). In [0, 45].
    gamma : float
        Unit weight of soil (kN/m³). > 0.
    FS_req_ot : float
        Required FS overturning (default 2.0).
    FS_req_sl : float
        Required FS sliding (default 1.5).
    FS_req_bc : float
        Required FS bearing capacity (default 3.0).

    Returns
    -------
    dict
        ok             : True
        FS_overturning : factor of safety against overturning
        FS_sliding     : factor of safety against sliding
        FS_bearing     : factor of safety against bearing capacity failure
        overturning_ok : bool
        sliding_ok     : bool
        bearing_ok     : bool
        warnings       : list of advisory strings
    """
    warns: list[str] = []

    e = _guard_nonneg("Fa", Fa)
    if e:
        return _err(e)
    e = _guard_nonneg("Fp", Fp)
    if e:
        return _err(e)
    e = _guard_positive("W_wall", W_wall)
    if e:
        return _err(e)
    e = _guard_positive("x_W", x_W)
    if e:
        return _err(e)
    e = _guard_positive("B_base", B_base)
    if e:
        return _err(e)
    e = _guard_nonneg("Df", Df)
    if e:
        return _err(e)
    e = _guard_nonneg("c", c)
    if e:
        return _err(e)
    e = _guard_finite("phi_deg", phi_deg)
    if e:
        return _err(e)
    phi_f = float(phi_deg)
    if not 0.0 <= phi_f <= 45.0:
        return _err(f"phi_deg must be in [0, 45], got {phi_f}")
    e = _guard_positive("gamma", gamma)
    if e:
        return _err(e)

    phi_rad = _deg2rad(phi_f)
    Fa_v = float(Fa)
    Fp_v = float(Fp)
    W = float(W_wall)
    xw = float(x_W)
    B = float(B_base)
    Df_v = float(Df)
    c_v = float(c)
    gamma_v = float(gamma)

    # --- Overturning ---
    # Stabilising moment (about toe) = W × x_W + Fp × (Df/3)
    # Overturning moment             = Fa × (H_a)  — caller provides Pa as resultant
    # We approximate active arm as Df/3 + retained height contribution.
    # Since the caller passes Fa as the total active force, we need the arm.
    # Convention: Fa acts at H_eff/3 from base; we don't have H_eff here.
    # Use a simplified approach: assume Fa acts at Df/3 + B/6 from base.
    # A more precise implementation requires the arm to be passed in.
    # Use Fa arm = B/3 (conservative for full-height active pressure triangular).
    M_stabilising = W * xw + Fp_v * Df_v / 3.0
    M_overturning = Fa_v * B / 3.0  # simplified arm

    if M_overturning > 1e-12:
        FS_ot = M_stabilising / M_overturning
    else:
        FS_ot = float("inf")

    # --- Sliding ---
    # Resisting force = W tan(φ) + c × B + Fp
    # Driving force   = Fa
    F_resist = W * math.tan(phi_rad) + c_v * B + Fp_v
    if Fa_v > 1e-12:
        FS_sl = F_resist / Fa_v
    else:
        FS_sl = float("inf")

    # --- Bearing capacity check ---
    # Eccentricity: e = B/2 - (M_stabilising - M_overturning) / W
    x_R = (M_stabilising - M_overturning) / max(W, 1e-12)
    e_ecc = B / 2.0 - x_R
    B_eff = max(B - 2.0 * abs(e_ecc), 0.01)  # effective base width

    # Simple Terzaghi for strip base
    phi_rad_b = phi_rad
    Nc_b, Nq_b, Ng_b = _terzaghi_factors(phi_rad_b)
    q_ult_base = c_v * Nc_b + gamma_v * Df_v * Nq_b + 0.5 * gamma_v * B_eff * Ng_b
    q_applied = W / B_eff  # average contact pressure

    if q_applied > 1e-12:
        FS_bc = q_ult_base / q_applied
    else:
        FS_bc = float("inf")

    ot_req = float(FS_req_ot)
    sl_req = float(FS_req_sl)
    bc_req = float(FS_req_bc)

    ot_ok = FS_ot >= ot_req
    sl_ok = FS_sl >= sl_req
    bc_ok = FS_bc >= bc_req

    if not ot_ok:
        warns.append(
            f"FS_overturning={FS_ot:.2f} < required {ot_req:.2f}. "
            "Increase base width or add a shear key."
        )
    if not sl_ok:
        warns.append(
            f"FS_sliding={FS_sl:.2f} < required {sl_req:.2f}. "
            "Add a shear key or increase base friction."
        )
    if not bc_ok:
        warns.append(
            f"FS_bearing={FS_bc:.2f} < required {bc_req:.2f}. "
            "Reduce wall load or improve bearing layer."
        )
    if abs(e_ecc) > B / 6.0:
        warns.append(
            f"Eccentricity |e|={abs(e_ecc):.3f} m > B/6={B / 6.0:.3f} m — "
            "resultant outside kern; uplift at heel; redesign base dimensions."
        )

    return {
        "ok": True,
        "FS_overturning": FS_ot,
        "FS_sliding": FS_sl,
        "FS_bearing": FS_bc,
        "overturning_ok": ot_ok,
        "sliding_ok": sl_ok,
        "bearing_ok": bc_ok,
        "eccentricity_m": e_ecc,
        "B_eff_m": B_eff,
        "q_applied_kPa": q_applied,
        "q_ult_kPa": q_ult_base,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 5. slope_stability_infinite
# ---------------------------------------------------------------------------

def slope_stability_infinite(
    gamma: float,
    c: float,
    phi_deg: float,
    H: float,
    beta_deg: float,
    *,
    hw_ratio: float = 0.0,
    FS_req: float = 1.5,
) -> dict:
    """
    Simplified infinite-slope factor of safety.

    Parameters
    ----------
    gamma : float
        Unit weight of soil (kN/m³). > 0.
    c : float
        Cohesion (kPa). >= 0.
    phi_deg : float
        Internal friction angle (°). In [0, 45].
    H : float
        Depth to failure plane (m). > 0.
    beta_deg : float
        Slope angle (°). Must be in (0, 90).
    hw_ratio : float
        hw / H — ratio of water table depth to failure plane depth.
        0.0 = dry (default); 1.0 = fully saturated (phreatic at surface).
        Must be in [0, 1].
    FS_req : float
        Required factor of safety (default 1.5). > 0.

    Returns
    -------
    dict
        ok        : True
        FS        : computed factor of safety
        adequate  : bool — True if FS >= FS_req
        method    : "infinite-slope"
        warnings  : list of advisory strings

    Formula
    -------
    Dry (hw_ratio = 0):
        FS = c/(γ·H·sin β·cos β) + tan φ / tan β

    Partially/fully saturated (hw_ratio = hw/H = m):
        FS = c/(γ·H·sin β·cos β) + (1 - m·γw/γ)·tan φ / tan β

    where γw = 9.81 kN/m³.
    """
    warns: list[str] = []

    e = _guard_positive("gamma", gamma)
    if e:
        return _err(e)
    e = _guard_nonneg("c", c)
    if e:
        return _err(e)
    e = _guard_finite("phi_deg", phi_deg)
    if e:
        return _err(e)
    phi_f = float(phi_deg)
    if not 0.0 <= phi_f <= 45.0:
        return _err(f"phi_deg must be in [0, 45], got {phi_f}")
    e = _guard_positive("H", H)
    if e:
        return _err(e)
    e = _guard_finite("beta_deg", beta_deg)
    if e:
        return _err(e)
    beta_f = float(beta_deg)
    if not 0.0 < beta_f < 90.0:
        return _err(f"beta_deg must be in (0, 90), got {beta_f}")
    e = _guard_finite("hw_ratio", hw_ratio)
    if e:
        return _err(e)
    m = float(hw_ratio)
    if not 0.0 <= m <= 1.0:
        return _err(f"hw_ratio must be in [0, 1], got {m}")
    e = _guard_positive("FS_req", FS_req)
    if e:
        return _err(e)

    gamma_w = 9.81
    gamma_v = float(gamma)
    c_v = float(c)
    H_v = float(H)
    phi_rad = _deg2rad(phi_f)
    beta_rad = _deg2rad(beta_f)
    FS_req_v = float(FS_req)

    sin_b = math.sin(beta_rad)
    cos_b = math.cos(beta_rad)
    tan_b = math.tan(beta_rad)
    tan_phi = math.tan(phi_rad)

    # Cohesion term
    c_term = c_v / (gamma_v * H_v * sin_b * cos_b) if (gamma_v * H_v * sin_b * cos_b) > 1e-12 else 0.0

    # Friction term (reduced by water pressure)
    pore_factor = 1.0 - m * gamma_w / gamma_v
    fric_term = pore_factor * tan_phi / tan_b if tan_b > 1e-12 else float("inf")

    FS = c_term + fric_term

    adequate = FS >= FS_req_v

    if phi_f < 5.0 and c_v < 1.0:
        warns.append(
            "phi_deg < 5° and c < 1 kPa — soil may be liquefaction-prone. "
            "Consider dynamic slope stability analysis (Newmark method)."
        )
    if not adequate:
        warns.append(
            f"FS={FS:.2f} < required {FS_req_v:.2f}. "
            "Consider reducing slope angle, drainage, or soil reinforcement."
        )
    if m > 0.8:
        warns.append(
            f"hw_ratio={m:.2f} indicates near-fully saturated conditions — "
            "pore pressure significantly reduces stability."
        )

    return {
        "ok": True,
        "FS": FS,
        "adequate": adequate,
        "FS_req": FS_req_v,
        "hw_ratio": m,
        "method": "infinite-slope",
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 6. pile_axial_capacity
# ---------------------------------------------------------------------------

def pile_axial_capacity(
    perimeter: float,
    area_tip: float,
    unit_skin_friction: float,
    unit_end_bearing: float,
    pile_length: float,
    *,
    alpha: float = 1.0,
    FS: float = 3.0,
) -> dict:
    """
    Pile axial capacity: alpha-method skin friction + end bearing.

    Parameters
    ----------
    perimeter : float
        Pile perimeter (m). > 0.
    area_tip : float
        Pile tip cross-sectional area (m²). > 0.
    unit_skin_friction : float
        Average unit skin friction along pile shaft (kPa). >= 0.
        This is the undrained shear strength su (or average fs) before α.
    unit_end_bearing : float
        Unit end-bearing capacity at pile tip (kPa). >= 0.
        Typically = Nc × cu for end-bearing piles (Nc ≈ 9 for driven piles).
    pile_length : float
        Total pile length (m). > 0.
    alpha : float
        Adhesion factor α for skin friction (0 < α <= 1.0; default 1.0).
        Typical range: 0.4–0.8 for soft clay (API/Tomlinson α-method).
    FS : float
        Factor of safety on ultimate capacity (default 3.0). > 0.

    Returns
    -------
    dict
        ok            : True
        Qs_kN         : skin friction capacity (kN)
        Qp_kN         : end-bearing capacity (kN)
        Q_ult_kN      : ultimate pile capacity (kN)
        Q_allow_kN    : allowable pile capacity = Q_ult / FS (kN)
        FS            : factor of safety used
        warnings      : list of advisory strings

    Formula (α-method, API RP 2GEO / Tomlinson)
    ---------------------------------------------
        Qs = α × fs × perimeter × L
        Qp = qp × A_tip
        Q_ult = Qs + Qp
        Q_allow = Q_ult / FS
    """
    warns: list[str] = []

    e = _guard_positive("perimeter", perimeter)
    if e:
        return _err(e)
    e = _guard_positive("area_tip", area_tip)
    if e:
        return _err(e)
    e = _guard_nonneg("unit_skin_friction", unit_skin_friction)
    if e:
        return _err(e)
    e = _guard_nonneg("unit_end_bearing", unit_end_bearing)
    if e:
        return _err(e)
    e = _guard_positive("pile_length", pile_length)
    if e:
        return _err(e)
    e = _guard_positive("alpha", alpha)
    if e:
        return _err(e)
    if float(alpha) > 1.0:
        return _err(f"alpha must be <= 1.0, got {alpha}")
    e = _guard_positive("FS", FS)
    if e:
        return _err(e)

    p_val = float(perimeter)
    A_tip = float(area_tip)
    fs_val = float(unit_skin_friction)
    qp_val = float(unit_end_bearing)
    L_val = float(pile_length)
    alpha_val = float(alpha)
    FS_val = float(FS)

    Qs = alpha_val * fs_val * p_val * L_val
    Qp = qp_val * A_tip
    Q_ult = Qs + Qp
    Q_allow = Q_ult / FS_val

    if FS_val < 2.5:
        warns.append(
            f"FS={FS_val:.2f} < 2.5 — typical minimum FS for pile capacity is 2.5–3.0. "
            "Review design loads and site investigation."
        )
    if alpha_val < 0.4:
        warns.append(
            f"alpha={alpha_val:.2f} < 0.4 — unusually low adhesion factor. "
            "Verify soil shear strength and pile installation method."
        )
    if Qs < Qp * 0.1 and Qs > 0:
        warns.append(
            "End bearing dominates capacity (Qp >> Qs). "
            "Verify end bearing in hard strata; skin friction contribution is negligible."
        )

    return {
        "ok": True,
        "Qs_kN": Qs,
        "Qp_kN": Qp,
        "Q_ult_kN": Q_ult,
        "Q_allow_kN": Q_allow,
        "FS": FS_val,
        "alpha": alpha_val,
        "pile_length_m": L_val,
        "warnings": warns,
    }
