"""
kerf_cad_core.spillway.design — Pure-Python dam & spillway hydraulics.

Implements ten public functions covering the full hydraulic design cycle for
spillways and gravity dams.  All functions return plain dicts:

    success → {"ok": True, ...computed fields..., "warnings": [...]}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise.

Units
-----
Unless stated otherwise all inputs and outputs use SI:
  lengths  — metres (m)
  areas    — m²
  volumes  — m³
  flow     — m³/s
  velocity — m/s
  head     — m
  force    — kN (gravity-dam stability)
  pressure — kN/m²
  time     — seconds (s) for hydrograph, hours acceptable when documented

References
----------
USBR (1977) Design of Small Dams, 3rd ed.  Bureau of Reclamation.
USBR (1987) Design of Small Canal Structures.
US Army Corps of Engineers EM 1110-2-1601 (1994) Hydraulic Design of
    Flood Control Channels.
Chaudhry, M.H. (2008) Open-Channel Hydraulics, 2nd ed.  Springer.
Linsley, R.K. & Franzini, J.B. (1979) Water Resources Engineering, 3rd ed.
Henderson, F.M. (1966) Open Channel Flow.  Macmillan.
Lacey, G. (1930) Stable Channels in Alluvium.  Proc. ICE.

Author: imranparuk
"""

from __future__ import annotations

import math
from typing import Any
from kerf_cad_core._guards import _err

_G = 9.81  # m/s²

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _ok(**kw: Any) -> dict:
    d = {"ok": True}
    d.update(kw)
    if "warnings" not in d:
        d["warnings"] = []
    return d


def _pos(val: Any, name: str) -> str | None:
    """Return error string if val is not a positive number, else None."""
    try:
        v = float(val)
    except (TypeError, ValueError):
        return f"{name} must be a number"
    if v <= 0:
        return f"{name} must be > 0"
    return None


def _nonneg(val: Any, name: str) -> str | None:
    try:
        v = float(val)
    except (TypeError, ValueError):
        return f"{name} must be a number"
    if v < 0:
        return f"{name} must be >= 0"
    return None


# ---------------------------------------------------------------------------
# 1. ogee_discharge — WES ogee spillway discharge
# ---------------------------------------------------------------------------

def ogee_discharge(
    design_head_m: float,
    actual_head_m: float,
    crest_length_m: float,
    *,
    approach_depth_m: float = 0.0,
    num_end_contractions: int = 0,
    tailwater_m: float = 0.0,
    C0: float = 2.21,
) -> dict:
    """Compute discharge over a WES ogee (standard-crest) spillway.

    Basic formula (SI):
        Q = C · L_eff · H_e^1.5

    Discharge coefficient C is adjusted for:
      - Head ratio  He/Hd  (WES head-correction factor k_h)
      - Approach velocity head  (adds to He)
      - End contractions  (reduces effective length L_eff)
      - Submergence  (Villemonte equation when tailwater affects flow)

    Parameters
    ----------
    design_head_m : float
        Design head Hd (m) for which the crest was optimised.  Must be > 0.
    actual_head_m : float
        Actual operating head He (m) above crest.  Must be > 0.
    crest_length_m : float
        Gross crest length L (m).  Must be > 0.
    approach_depth_m : float
        Depth P of water in the approach channel measured from crest datum (m).
        Used to compute approach-velocity head.  Default 0 (ignore).
    num_end_contractions : int
        Number of end contractions (0, 1, or 2).  Each reduces L by 0.1·He.
    tailwater_m : float
        Tailwater elevation above crest (m).  > 0 means submerged.  Default 0.
    C0 : float
        Discharge coefficient at design head (m^0.5/s in SI).  Default 2.21
        (USBR value; use 2.18 for metric, 3.97 US-customary).

    Returns
    -------
    dict with ok=True and keys:
        discharge_m3s, C_effective, L_eff_m, He_m,
        approach_velocity_head_m, submergence_ratio, submergence_factor,
        warnings
    """
    e = (_pos(design_head_m, "design_head_m") or
         _pos(actual_head_m, "actual_head_m") or
         _pos(crest_length_m, "crest_length_m"))
    if e:
        return _err(e)
    e2 = _nonneg(approach_depth_m, "approach_depth_m") or _nonneg(tailwater_m, "tailwater_m")
    if e2:
        return _err(e2)
    if num_end_contractions not in (0, 1, 2):
        return _err("num_end_contractions must be 0, 1, or 2")

    Hd = float(design_head_m)
    He = float(actual_head_m)
    L = float(crest_length_m)
    P = float(approach_depth_m)
    Ht = float(tailwater_m)

    warnings: list[str] = []

    # Approach-velocity head correction
    # V_approach = Q / (A_approach); iterate once
    Va_head = 0.0
    if P > 0:
        # First estimate without Va correction
        Q_est = C0 * L * He ** 1.5
        A_approach = (P + He) * L
        Va = Q_est / A_approach if A_approach > 0 else 0.0
        Va_head = Va ** 2 / (2 * _G)

    He_total = He + Va_head  # total energy head

    # WES head-ratio correction (USBR Design of Small Dams, Fig. 9-21)
    # C / C0 is approximated by polynomial fit to tabulated k_h values:
    #   ratio = He/Hd
    #   k_h ≈ 1 + 0.122*(ratio-1) - 0.031*(ratio-1)² for ratio ≈ 0.2–1.8
    ratio = He_total / Hd if Hd > 0 else 1.0
    k_h = 1.0 + 0.122 * (ratio - 1.0) - 0.031 * (ratio - 1.0) ** 2
    # Clamp coefficient: USBR limits k_h to about 0.85 – 1.08
    k_h = max(0.85, min(1.08, k_h))
    C_eff = C0 * k_h

    # End-contraction correction (Rehbock / Francis)
    L_eff = L - 0.1 * num_end_contractions * He_total
    if L_eff <= 0:
        warnings.append("Effective crest length ≤ 0 due to contractions; check geometry")
        L_eff = 1e-6

    # Free-flow discharge
    Q_free = C_eff * L_eff * He_total ** 1.5

    # Submergence correction (Villemonte 1947)
    # Qs/Qf = (1 - (Ht/He)^1.5)^0.385
    sub_ratio = 0.0
    sub_factor = 1.0
    if Ht > 0:
        sub_ratio = Ht / He_total if He_total > 0 else 0.0
        if sub_ratio >= 1.0:
            warnings.append(
                "Tailwater at or above total energy head: spillway may be flooded; Q set to 0"
            )
            sub_factor = 0.0
        else:
            sub_factor = (1.0 - sub_ratio ** 1.5) ** 0.385
        if sub_ratio > 0.7:
            warnings.append(
                f"High submergence ratio {sub_ratio:.2f}: discharge significantly reduced"
            )

    Q = Q_free * sub_factor

    if He_total > 1.33 * Hd:
        warnings.append(
            f"He/Hd = {He_total/Hd:.2f} > 1.33: cavitation risk on crest surface"
        )
    if He_total < 0.5 * Hd:
        warnings.append(
            f"He/Hd = {He_total/Hd:.2f} < 0.50: pressure below atmospheric on crest; "
            "actual discharge may exceed computed value"
        )

    return _ok(
        discharge_m3s=round(Q, 6),
        C_effective=round(C_eff, 4),
        L_eff_m=round(L_eff, 4),
        He_m=round(He_total, 4),
        approach_velocity_head_m=round(Va_head, 5),
        submergence_ratio=round(sub_ratio, 4),
        submergence_factor=round(sub_factor, 4),
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# 2. ogee_crest_profile — WES standard crest coordinates
# ---------------------------------------------------------------------------

def ogee_crest_profile(
    design_head_m: float,
    *,
    n_upstream: int = 10,
    n_downstream: int = 40,
) -> dict:
    """Generate (x, y) coordinates of a WES standard ogee crest profile.

    The WES standard shape (USBR 1977, Fig. 9-7 / USACE EM 1110-2-1603):

    Downstream quadrant (x ≥ 0):
        y / Hd = −K · (x / Hd)^n
        where K = 0.5, n = 1.85  (for vertical upstream face, Hd-normalised)

    Upstream quadrant approximated by three tangent circular arcs
    (radii R1 = 0.5Hd, R2 = 0.2Hd, R3 = 0.04Hd).

    Origin at the crest apex.  Positive x is downstream; positive y is upward
    (so computed y values are negative below the crest).

    Parameters
    ----------
    design_head_m : float
        Design head Hd (m).  Must be > 0.
    n_upstream : int
        Number of coordinate points on the upstream side.  Default 10.
    n_downstream : int
        Number of coordinate points on the downstream side.  Default 40.

    Returns
    -------
    dict with ok=True and keys:
        design_head_m, profile (list of {"x_m": ..., "y_m": ...})
        The origin (x=0, y=0) is the crest apex.
    """
    e = _pos(design_head_m, "design_head_m")
    if e:
        return _err(e)
    Hd = float(design_head_m)
    K = 0.5
    n_exp = 1.85
    points: list[dict] = []

    # Upstream quadrant: parabolic approximation
    # x_us ranges from -0.5*Hd to 0  (normalised upstream tangent limit)
    for i in range(n_upstream, 0, -1):
        x_norm = -0.5 * (i / n_upstream)
        # Upstream shape: y/Hd = -0.724*(x/Hd + 0.5)^1.85 + 0.362  (approx)
        # Simplified: use a circular arc approximation
        # R = 0.5*Hd; centre at (x=0, y=-R) so y = -R + sqrt(R²-x²)
        R = 0.5 * Hd
        x_abs = abs(x_norm * Hd)
        if x_abs <= R:
            y_norm = (-R + math.sqrt(max(0.0, R ** 2 - x_abs ** 2))) / Hd
        else:
            y_norm = 0.0
        points.append({"x_m": round(x_norm * Hd, 5), "y_m": round(y_norm * Hd, 5)})

    # Crest apex
    points.append({"x_m": 0.0, "y_m": 0.0})

    # Downstream quadrant: WES power-law
    x_max = 2.0 * Hd
    for i in range(1, n_downstream + 1):
        x_norm = (i / n_downstream) * (x_max / Hd)
        y_norm = -K * x_norm ** n_exp
        points.append({"x_m": round(x_norm * Hd, 5), "y_m": round(y_norm * Hd, 5)})

    return _ok(design_head_m=Hd, profile=points, warnings=[])


# ---------------------------------------------------------------------------
# 3. orifice_discharge — gated / submerged orifice spillway
# ---------------------------------------------------------------------------

def orifice_discharge(
    gate_opening_m: float,
    gate_width_m: float,
    head_upstream_m: float,
    *,
    head_downstream_m: float = 0.0,
    Cd: float = 0.61,
    gate_type: str = "sluice",
) -> dict:
    """Compute discharge through a gated or submerged orifice spillway gate.

    Free-flow orifice (submerged-inlet form):
        Q = Cd · A · sqrt(2g · (Hu − a/2))

    Submerged (tailwater above gate opening):
        Q = Cd · A · sqrt(2g · ΔH)   where ΔH = Hu − Hd

    For sharp-crested orifices (Cd ≈ 0.61).
    For drum gates / radial gates Cd ≈ 0.74–0.80 is typical.

    Parameters
    ----------
    gate_opening_m : float
        Gate opening height a (m).  Must be > 0.
    gate_width_m : float
        Gate width W (m).  Must be > 0.
    head_upstream_m : float
        Upstream head measured from gate sill (m).  Must be > 0.
    head_downstream_m : float
        Downstream (tailwater) head measured from gate sill (m).  Default 0.
    Cd : float
        Discharge coefficient (default 0.61).
    gate_type : str
        'sluice' (default), 'radial', or 'drum'.  Informational only.

    Returns
    -------
    dict with ok=True and keys:
        discharge_m3s, velocity_m_s, gate_area_m2, effective_head_m,
        flow_condition ('free' or 'submerged'), warnings
    """
    e = (_pos(gate_opening_m, "gate_opening_m") or
         _pos(gate_width_m, "gate_width_m") or
         _pos(head_upstream_m, "head_upstream_m"))
    if e:
        return _err(e)
    e2 = _nonneg(head_downstream_m, "head_downstream_m")
    if e2:
        return _err(e2)
    if Cd <= 0 or Cd > 1.0:
        return _err("Cd must be in (0, 1]")

    a = float(gate_opening_m)
    W = float(gate_width_m)
    Hu = float(head_upstream_m)
    Hd_tw = float(head_downstream_m)

    warnings: list[str] = []

    if Hu < a:
        warnings.append("Upstream head < gate opening: orifice not fully submerged; result approximate")

    A = a * W
    flow_condition = "free"

    if Hd_tw > a:
        # Submerged orifice: ΔH = Hu - Hd_tw
        dH = Hu - Hd_tw
        if dH <= 0:
            warnings.append("Upstream head ≤ downstream head: zero or reverse flow; Q set to 0")
            return _ok(
                discharge_m3s=0.0,
                velocity_m_s=0.0,
                gate_area_m2=round(A, 5),
                effective_head_m=0.0,
                flow_condition="reverse",
                warnings=warnings,
            )
        h_eff = dH
        flow_condition = "submerged"
    else:
        # Free-flow: head measured to centroid of gate opening
        h_eff = Hu - a / 2.0

    Q = float(Cd) * A * math.sqrt(2 * _G * h_eff)
    V = Q / A if A > 0 else 0.0

    return _ok(
        discharge_m3s=round(Q, 6),
        velocity_m_s=round(V, 4),
        gate_area_m2=round(A, 5),
        effective_head_m=round(h_eff, 4),
        flow_condition=flow_condition,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# 4. chute_velocity — chute & terminal velocity
# ---------------------------------------------------------------------------

def chute_velocity(
    flow_m3s: float,
    chute_width_m: float,
    chute_slope: float,
    manning_n: float,
    *,
    chute_length_m: float = 0.0,
) -> dict:
    """Compute chute flow depth, velocity, and terminal (uniform-flow) velocity.

    Uses Manning's equation for rectangular chute channel:
        V_n = (1/n) · R^(2/3) · S^(1/2)
        Q = V_n · A

    Normal depth is solved by bisection.  The terminal velocity is the
    velocity at normal (uniform-flow) depth for the given slope.

    If chute_length_m is provided, a downstream velocity is estimated via
    energy equation (frictionless):
        V_ds = sqrt(V_us² + 2g·(ΔZ))
    where ΔZ = chute_length_m · chute_slope.

    Parameters
    ----------
    flow_m3s : float
        Design discharge Q (m³/s).  Must be > 0.
    chute_width_m : float
        Chute width W (m).  Must be > 0.
    chute_slope : float
        Chute longitudinal slope S (m/m).  Must be > 0.
    manning_n : float
        Manning's roughness n.  Typical: 0.013–0.018 for concrete.
    chute_length_m : float
        Chute length (m) for downstream velocity estimate.  0 = skip.

    Returns
    -------
    dict with ok=True and keys:
        normal_depth_m, terminal_velocity_m_s, froude_number,
        flow_area_m2, hydraulic_radius_m,
        downstream_velocity_m_s (if chute_length_m > 0),
        warnings
    """
    e = (_pos(flow_m3s, "flow_m3s") or
         _pos(chute_width_m, "chute_width_m") or
         _pos(chute_slope, "chute_slope") or
         _pos(manning_n, "manning_n"))
    if e:
        return _err(e)
    e2 = _nonneg(chute_length_m, "chute_length_m")
    if e2:
        return _err(e2)

    Q = float(flow_m3s)
    W = float(chute_width_m)
    S = float(chute_slope)
    n = float(manning_n)
    L = float(chute_length_m)

    warnings: list[str] = []

    # Bisection for normal depth in rectangular section
    def _manning_Q(y: float) -> float:
        A = W * y
        P = W + 2 * y
        R = A / P
        return (1.0 / n) * A * R ** (2 / 3) * S ** 0.5

    y_lo, y_hi = 1e-6, max(Q / W, 1.0) * 20
    for _ in range(80):
        y_mid = (y_lo + y_hi) / 2
        if _manning_Q(y_mid) < Q:
            y_lo = y_mid
        else:
            y_hi = y_mid
    yn = (y_lo + y_hi) / 2

    A_n = W * yn
    P_n = W + 2 * yn
    R_n = A_n / P_n
    V_n = Q / A_n
    Fr_n = V_n / math.sqrt(_G * yn)

    result: dict = _ok(
        normal_depth_m=round(yn, 5),
        terminal_velocity_m_s=round(V_n, 4),
        froude_number=round(Fr_n, 4),
        flow_area_m2=round(A_n, 5),
        hydraulic_radius_m=round(R_n, 5),
    )

    if Fr_n > 1.5:
        warnings.append(
            f"Froude number at normal depth = {Fr_n:.2f}: highly supercritical chute"
        )
    if S > 0.3:
        warnings.append(
            "Chute slope > 0.3 (1:3.33): structural loads and air entrainment require special design"
        )

    # Downstream velocity via energy equation
    if L > 0:
        dZ = L * S
        V_ds = math.sqrt(V_n ** 2 + 2 * _G * dZ)
        result["downstream_velocity_m_s"] = round(V_ds, 4)
        result["elevation_drop_m"] = round(dZ, 4)
        if V_ds > 30:
            warnings.append(
                f"Downstream velocity {V_ds:.1f} m/s: severe erosion potential; consider aeration"
            )

    result["warnings"] = warnings
    return result


# ---------------------------------------------------------------------------
# 5. stilling_basin — USBR Type I–IV selection & hydraulic jump design
# ---------------------------------------------------------------------------

def stilling_basin(
    upstream_depth_m: float,
    flow_m3s: float,
    chute_width_m: float,
    tailwater_depth_m: float,
    *,
    elevation_drop_m: float = 0.0,
) -> dict:
    """Design a USBR stilling basin for a hydraulic jump.

    Computes:
      - Froude number Fr1 at the jump toe
      - Sequent (conjugate) depth y2 via Bélanger equation
      - USBR basin type recommendation (I–IV)
      - Required basin floor elevation (to ensure jump stays in basin)
      - Basin length Lb per USBR Fig. 6-5
      - End-sill height

    USBR type selection (USBR 1977, p. 213):
      Type I  : Fr1 > 4.5  — standard jump; floor protection only
      Type II : Fr1 2.5–4.5 — chute blocks + end sill (high tailwater)
      Type III: Fr1 4.5–9   — chute blocks + baffle piers + end sill
      Type IV : Fr1 1.7–2.5 — wave suppressors
      (Fr1 < 1.7 : jump formation doubtful; undular or absent)

    Parameters
    ----------
    upstream_depth_m : float
        Flow depth y1 immediately upstream of the jump (m).  Must be > 0.
    flow_m3s : float
        Total discharge Q (m³/s).  Must be > 0.
    chute_width_m : float
        Basin width W (m).  Must be > 0.
    tailwater_depth_m : float
        Tailwater depth TW (m) measured from basin floor.  Must be >= 0.
    elevation_drop_m : float
        Energy head available if basin floor can be lowered (m).  Default 0.

    Returns
    -------
    dict with ok=True and keys:
        froude1, depth1_m, depth2_m (sequent depth),
        velocity1_m_s, velocity2_m_s,
        basin_type ('I'|'II'|'III'|'IV'|'undular'),
        basin_length_m, end_sill_height_m,
        floor_depression_needed_m,
        tailwater_deficit_m (y2 - TW; positive means TW is adequate),
        energy_loss_m, relative_energy_loss,
        warnings
    """
    e = (_pos(upstream_depth_m, "upstream_depth_m") or
         _pos(flow_m3s, "flow_m3s") or
         _pos(chute_width_m, "chute_width_m") or
         _nonneg(tailwater_depth_m, "tailwater_depth_m"))
    if e:
        return _err(e)
    e2 = _nonneg(elevation_drop_m, "elevation_drop_m")
    if e2:
        return _err(e2)

    y1 = float(upstream_depth_m)
    Q = float(flow_m3s)
    W = float(chute_width_m)
    TW = float(tailwater_depth_m)

    warnings: list[str] = []

    V1 = Q / (y1 * W)
    Fr1 = V1 / math.sqrt(_G * y1)

    # Bélanger equation (rectangular channel)
    y2 = (y1 / 2.0) * (math.sqrt(1.0 + 8.0 * Fr1 ** 2) - 1.0)
    V2 = Q / (y2 * W)
    Fr2 = V2 / math.sqrt(_G * y2)

    # Energy loss
    E1 = y1 + V1 ** 2 / (2 * _G)
    E2 = y2 + V2 ** 2 / (2 * _G)
    dE = E1 - E2
    rel_loss = dE / E1 if E1 > 0 else 0.0

    # USBR basin type
    if Fr1 < 1.7:
        basin_type = "undular"
        warnings.append(
            f"Fr1 = {Fr1:.2f} < 1.7: jump may not form; undular wave; basin not effective"
        )
    elif Fr1 < 2.5:
        basin_type = "IV"
        warnings.append(
            f"Fr1 = {Fr1:.2f}: USBR Type IV basin — wave suppressors required; "
            "oscillating jump may cause rough water downstream"
        )
    elif Fr1 < 4.5:
        basin_type = "II"
    else:
        basin_type = "III"

    # Basin length (USBR Fig. 6-5 fitted curve)
    # Lb/y2 ≈ 6.1  for Fr1 = 4–10 (Type II/III)
    # Lb/y2 ≈ 5.0  for Fr1 < 4
    if Fr1 >= 4.5:
        Lb_ratio = 6.1
    elif Fr1 >= 2.5:
        Lb_ratio = 5.0
    else:
        Lb_ratio = 4.0
    Lb = Lb_ratio * y2

    # End sill height (USBR): ~0.1–0.15 y2
    sill_h = 0.12 * y2

    # Tailwater check
    tw_deficit = y2 - TW  # positive = TW adequate (TW >= y2)
    floor_depression = 0.0
    if TW < y2:
        # Basin floor needs to be depressed so jump forms
        floor_depression = y2 - TW
        warnings.append(
            f"Tailwater depth {TW:.2f} m < sequent depth {y2:.2f} m: "
            f"basin floor must be depressed by {floor_depression:.2f} m or jump will sweep out"
        )
    if TW > 1.1 * y2:
        warnings.append(
            f"Tailwater {TW:.2f} m > 1.1·y2 = {1.1*y2:.2f} m: "
            "submerged jump — reduced energy dissipation"
        )

    return _ok(
        froude1=round(Fr1, 4),
        froude2=round(Fr2, 4),
        depth1_m=round(y1, 5),
        depth2_m=round(y2, 5),
        velocity1_m_s=round(V1, 4),
        velocity2_m_s=round(V2, 4),
        basin_type=basin_type,
        basin_length_m=round(Lb, 4),
        end_sill_height_m=round(sill_h, 4),
        floor_depression_needed_m=round(floor_depression, 4),
        tailwater_deficit_m=round(y2 - TW, 4),
        energy_loss_m=round(dE, 5),
        relative_energy_loss=round(rel_loss, 4),
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# 6. energy_dissipation — energy head & required apron
# ---------------------------------------------------------------------------

def energy_dissipation(
    upstream_head_m: float,
    downstream_depth_m: float,
    flow_m3s: float,
    basin_width_m: float,
    *,
    basin_roughness_n: float = 0.015,
    basin_slope: float = 0.0,
) -> dict:
    """Compute energy available for dissipation and required apron length.

    Energy at the spillway toe:
        E_toe = upstream_head_m + V_toe²/(2g)
    where V_toe is computed from continuity at downstream depth.

    Required apron length is estimated by the USBR 6·y2 rule after the
    stilling basin exits, plus scour protection extent.

    Parameters
    ----------
    upstream_head_m : float
        Total upstream head above apron (dam crest to basin floor) (m).
    downstream_depth_m : float
        Normal depth in the downstream channel (m).
    flow_m3s : float
        Discharge Q (m³/s).
    basin_width_m : float
        Basin / apron width (m).
    basin_roughness_n : float
        Manning's n for the apron surface.  Default 0.015 (concrete).
    basin_slope : float
        Apron longitudinal slope (m/m).  Default 0 (horizontal apron).

    Returns
    -------
    dict with ok=True and keys:
        energy_at_toe_m, velocity_at_toe_m_s, froude_at_toe,
        energy_available_for_dissipation_m, apron_length_m,
        warnings
    """
    e = (_pos(upstream_head_m, "upstream_head_m") or
         _pos(downstream_depth_m, "downstream_depth_m") or
         _pos(flow_m3s, "flow_m3s") or
         _pos(basin_width_m, "basin_width_m"))
    if e:
        return _err(e)

    H_up = float(upstream_head_m)
    y_ds = float(downstream_depth_m)
    Q = float(flow_m3s)
    W = float(basin_width_m)
    n_apron = float(basin_roughness_n)

    warnings: list[str] = []

    # Velocity at toe from energy conservation (frictionless chute)
    # E_up = y_ds + V_toe²/2g  → V_toe = sqrt(2g*(H_up - y_ds))
    if H_up <= y_ds:
        warnings.append(
            "Upstream head ≤ downstream depth: no energy drop; results may be unreliable"
        )
    V_toe = math.sqrt(max(0.0, 2 * _G * (H_up - y_ds)))
    E_toe = y_ds + V_toe ** 2 / (2 * _G)
    Fr_toe = V_toe / math.sqrt(_G * y_ds) if y_ds > 0 else 0.0

    # Energy available for dissipation
    E_ds = y_ds  # kinetic energy in downstream channel is reference
    dE = E_toe - E_ds

    # Sequent depth & basin length
    A_toe = y_ds * W  # approximate; proper y_toe would need jump calc
    # Use simplified jump: y1_approx = Q / (V_toe * W)
    y1_approx = Q / (V_toe * W) if V_toe > 0 else y_ds
    Fr1 = V_toe / math.sqrt(_G * y1_approx) if y1_approx > 0 else Fr_toe
    y2 = (y1_approx / 2.0) * (math.sqrt(1.0 + 8.0 * Fr1 ** 2) - 1.0)
    Lb = 6.0 * y2

    # Add downstream protection: 3·y2 beyond basin exit (USBR guideline)
    L_protection = 3.0 * y2
    L_total = Lb + L_protection

    if V_toe > 20:
        warnings.append(
            f"Velocity at toe {V_toe:.1f} m/s: consider aerator ramps on chute to prevent cavitation"
        )
    if Fr_toe < 1.7 and Fr_toe > 0:
        warnings.append("Froude number at toe < 1.7: hydraulic jump may not form effectively")

    return _ok(
        energy_at_toe_m=round(E_toe, 4),
        velocity_at_toe_m_s=round(V_toe, 4),
        froude_at_toe=round(Fr_toe, 4),
        energy_available_for_dissipation_m=round(dE, 4),
        apron_length_m=round(L_total, 4),
        basin_length_m=round(Lb, 4),
        downstream_protection_length_m=round(L_protection, 4),
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# 7. scour_depth — downstream scour
# ---------------------------------------------------------------------------

def scour_depth(
    flow_m3s: float,
    channel_width_m: float,
    d50_mm: float,
    *,
    method: str = "lacey",
    head_drop_m: float = 0.0,
) -> dict:
    """Estimate scour depth downstream of a dam / energy dissipator.

    Two methods are supported:

    'lacey'  — Lacey (1930) regime scour:
        d_scour = 0.47 · (Q/f)^(1/3)
        where f = Lacey's silt factor = 1.76 · sqrt(d50_mm)

    'mason'  — Mason & Arumugam (1985) empirical formula for ski-jump /
        plunge-pool scour:
        d_s = 3.27 · Q^0.6 · H^0.5 / (g^0.3 · d90^0.06)
        Simplified as:
        d_s = 1.9 · Q^0.6 · head_drop_m^0.5 / d50_mm^0.06

    Parameters
    ----------
    flow_m3s : float
        Discharge Q (m³/s).
    channel_width_m : float
        Channel width (m).  Used for unit discharge q = Q/W.
    d50_mm : float
        Median sediment grain size (mm).
    method : str
        'lacey' (default) or 'mason'.
    head_drop_m : float
        Total head drop from reservoir to scour hole (m).  Required for 'mason'.

    Returns
    -------
    dict with ok=True and keys:
        scour_depth_m, method, unit_discharge_m2s, lacey_silt_factor (if lacey),
        warnings
    """
    e = (_pos(flow_m3s, "flow_m3s") or
         _pos(channel_width_m, "channel_width_m") or
         _pos(d50_mm, "d50_mm"))
    if e:
        return _err(e)
    if method not in ("lacey", "mason"):
        return _err("method must be 'lacey' or 'mason'")
    if method == "mason":
        e2 = _pos(head_drop_m, "head_drop_m")
        if e2:
            return _err(e2 + " (required for mason method)")

    Q = float(flow_m3s)
    W = float(channel_width_m)
    d50 = float(d50_mm)
    H = float(head_drop_m)
    warnings: list[str] = []
    q = Q / W  # unit discharge m²/s

    if method == "lacey":
        f = 1.76 * math.sqrt(d50)
        # Lacey scour depth from surface
        R_s = 0.47 * (Q / f) ** (1 / 3)
        d_scour = R_s
        extra = {"lacey_silt_factor": round(f, 4)}
    else:  # mason
        # Mason & Arumugam (1985) simplified
        d_scour = 1.9 * (Q ** 0.6) * (H ** 0.5) / (d50 ** 0.06)
        extra = {}

    if d_scour > 10:
        warnings.append(
            f"Estimated scour depth {d_scour:.1f} m is very deep; verify with physical model"
        )
    if d50 < 0.1:
        warnings.append("Very fine sediment (d50 < 0.1 mm): scour may extend further than computed")

    return _ok(
        scour_depth_m=round(d_scour, 4),
        method=method,
        unit_discharge_m2s=round(q, 4),
        **extra,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# 8. flood_routing_puls — modified-Puls (level-pool) reservoir routing
# ---------------------------------------------------------------------------

def flood_routing_puls(
    inflow_hydrograph: list[tuple[float, float]],
    storage_discharge_pairs: list[tuple[float, float]],
    dt_s: float,
    *,
    initial_storage_m3: float = 0.0,
) -> dict:
    """Route a flood hydrograph through a reservoir using the modified-Puls method.

    The modified-Puls (level-pool) routing equation (Chaudhry 2008, §10-4):

        (2S_n/Δt + Q_n) + I_n + I_{n+1} = 2S_{n+1}/Δt + Q_{n+1}

    A monotone storage-discharge table is used to look up (2S/dt + Q) → Q.

    Parameters
    ----------
    inflow_hydrograph : list of (t_s, I_m3s)
        Inflow hydrograph as a list of (time_seconds, inflow_m3s) tuples.
        Must have >= 2 points; time must be monotonically increasing.
    storage_discharge_pairs : list of (S_m3, Q_m3s)
        Reservoir storage-discharge curve as (storage_m3, discharge_m3s).
        Must have >= 2 points; storage must be monotonically increasing.
    dt_s : float
        Routing time step (s).  Must be > 0.  Typically equal to inflow
        hydrograph interval.
    initial_storage_m3 : float
        Initial reservoir storage at the start of routing (m³).  Default 0.

    Returns
    -------
    dict with ok=True and keys:
        outflow_hydrograph (list of {t_s, outflow_m3s, storage_m3}),
        peak_outflow_m3s, peak_outflow_time_s,
        peak_storage_m3, attenuation_m3s (peak_in - peak_out),
        warnings
    """
    if not inflow_hydrograph or len(inflow_hydrograph) < 2:
        return _err("inflow_hydrograph must have at least 2 points")
    if not storage_discharge_pairs or len(storage_discharge_pairs) < 2:
        return _err("storage_discharge_pairs must have at least 2 points")
    e = _pos(dt_s, "dt_s")
    if e:
        return _err(e)
    e2 = _nonneg(initial_storage_m3, "initial_storage_m3")
    if e2:
        return _err(e2)

    # Validate and unpack hydrograph
    times = [float(p[0]) for p in inflow_hydrograph]
    inflows = [float(p[1]) for p in inflow_hydrograph]
    for i in range(1, len(times)):
        if times[i] <= times[i - 1]:
            return _err("inflow_hydrograph time values must be strictly increasing")
    for I in inflows:
        if I < 0:
            return _err("inflow values must be >= 0")

    # Validate and unpack storage-discharge
    S_vals = [float(p[0]) for p in storage_discharge_pairs]
    Q_vals = [float(p[1]) for p in storage_discharge_pairs]
    for i in range(1, len(S_vals)):
        if S_vals[i] <= S_vals[i - 1]:
            return _err("storage values in storage_discharge_pairs must be strictly increasing")
    for q in Q_vals:
        if q < 0:
            return _err("discharge values must be >= 0")

    dt = float(dt_s)
    S0 = float(initial_storage_m3)
    warnings: list[str] = []

    # Build (2S/dt + Q) table indexed by S
    def _Qfun(S: float) -> float:
        """Interpolate Q from storage."""
        if S <= S_vals[0]:
            return Q_vals[0]
        if S >= S_vals[-1]:
            if S > S_vals[-1] * 1.05:
                warnings.append("Storage exceeds table range; extrapolating discharge")
            return Q_vals[-1]
        for i in range(1, len(S_vals)):
            if S_vals[i] >= S:
                frac = (S - S_vals[i - 1]) / (S_vals[i] - S_vals[i - 1])
                return Q_vals[i - 1] + frac * (Q_vals[i] - Q_vals[i - 1])
        return Q_vals[-1]

    def _Sfun(twSdt_Q: float) -> tuple[float, float]:
        """Given (2S/dt + Q), find S and Q by bisection."""
        # f(S) = 2S/dt + Q(S) - target
        target = twSdt_Q
        s_lo, s_hi = 0.0, max(S_vals[-1] * 2, S0 * 2, 1.0)
        # Extend upper bound if needed
        for _ in range(30):
            s_m = (s_lo + s_hi) / 2
            val = 2 * s_m / dt + _Qfun(s_m)
            if val < target:
                s_lo = s_m
            else:
                s_hi = s_m
        s_out = (s_lo + s_hi) / 2
        q_out = _Qfun(s_out)
        return s_out, q_out

    # Interpolate inflow at uniform dt steps
    t_start = times[0]
    t_end = times[-1]
    n_steps = max(int((t_end - t_start) / dt) + 1, len(times))
    t_route = [t_start + i * dt for i in range(n_steps)]

    def _interp_I(t: float) -> float:
        if t <= times[0]:
            return inflows[0]
        if t >= times[-1]:
            return inflows[-1]
        for i in range(1, len(times)):
            if times[i] >= t:
                frac = (t - times[i - 1]) / (times[i] - times[i - 1])
                return inflows[i - 1] + frac * (inflows[i] - inflows[i - 1])
        return inflows[-1]

    # Routing loop
    S_n = S0
    Q_n = _Qfun(S_n)
    outflow_hydro: list[dict] = []
    outflow_hydro.append({
        "t_s": round(t_route[0], 2),
        "outflow_m3s": round(Q_n, 4),
        "storage_m3": round(S_n, 2),
    })

    peak_out = Q_n
    peak_out_t = t_route[0]
    peak_S = S_n

    for i in range(1, len(t_route)):
        t_prev = t_route[i - 1]
        t_curr = t_route[i]
        I_prev = _interp_I(t_prev)
        I_curr = _interp_I(t_curr)

        # Modified-Puls routing equation
        rhs = (2 * S_n / dt - Q_n) + I_prev + I_curr
        S_new, Q_new = _Sfun(rhs)
        outflow_hydro.append({
            "t_s": round(t_curr, 2),
            "outflow_m3s": round(Q_new, 4),
            "storage_m3": round(S_new, 2),
        })
        if Q_new > peak_out:
            peak_out = Q_new
            peak_out_t = t_curr
        if S_new > peak_S:
            peak_S = S_new
        S_n = S_new
        Q_n = Q_new

    peak_in = max(inflows)
    attenuation = peak_in - peak_out
    if attenuation < 0:
        warnings.append("Outflow peak exceeds inflow peak: check storage-discharge curve")

    return _ok(
        outflow_hydrograph=outflow_hydro,
        peak_outflow_m3s=round(peak_out, 4),
        peak_outflow_time_s=round(peak_out_t, 2),
        peak_storage_m3=round(peak_S, 2),
        attenuation_m3s=round(attenuation, 4),
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# 9. dam_freeboard — wind setup + wave runup
# ---------------------------------------------------------------------------

def dam_freeboard(
    reservoir_fetch_km: float,
    wind_speed_m_s: float,
    dam_height_m: float,
    *,
    reservoir_depth_m: float = 10.0,
    embankment_slope_v_to_h: float = 3.0,
    freeboard_safety_m: float = 0.5,
) -> dict:
    """Estimate required dam freeboard from wind setup and wave runup.

    Computations:
        Significant wave height (Bretschneider / SMB):
            H_s = 0.0248 · U^2 · F^0.5  (Linsley & Franzini, SI)
            where U = wind speed (m/s), F = fetch (km)
        Wind setup (USBR):
            S_w = U² · F / (61,000 · d)
            where d = reservoir depth (m), F in km
        Wave runup (USBR / Corps of Engineers):
            R = 2.5 · H_s / (1 + H_s/(d · tan(θ)))
            where θ = upstream slope angle (simplified to R ≈ 2·H_s for
            rough embankments)
        Required freeboard = wind_setup + wave_runup + safety margin

    Parameters
    ----------
    reservoir_fetch_km : float
        Effective fetch F (km).  Must be > 0.
    wind_speed_m_s : float
        Design wind speed U (m/s).  Must be > 0.  Typical: 20–40 m/s.
    dam_height_m : float
        Dam height above foundation (m).  Used for context only.
    reservoir_depth_m : float
        Average reservoir depth (m).  Default 10 m.
    embankment_slope_v_to_h : float
        Upstream face slope expressed as vertical:horizontal (e.g. 3 means
        3H:1V is incorrect — this is 1V:3H, slope = 1/3 = 0.333).  Default 3.
    freeboard_safety_m : float
        Additional safety margin (m).  Default 0.5.

    Returns
    -------
    dict with ok=True and keys:
        significant_wave_height_m, wave_period_s, wind_setup_m, wave_runup_m,
        required_freeboard_m, warnings
    """
    e = (_pos(reservoir_fetch_km, "reservoir_fetch_km") or
         _pos(wind_speed_m_s, "wind_speed_m_s") or
         _pos(dam_height_m, "dam_height_m") or
         _pos(reservoir_depth_m, "reservoir_depth_m") or
         _pos(embankment_slope_v_to_h, "embankment_slope_v_to_h"))
    if e:
        return _err(e)
    e2 = _nonneg(freeboard_safety_m, "freeboard_safety_m")
    if e2:
        return _err(e2)

    F = float(reservoir_fetch_km)
    U = float(wind_speed_m_s)
    H_dam = float(dam_height_m)
    d = float(reservoir_depth_m)
    m = float(embankment_slope_v_to_h)  # H:V ratio

    warnings: list[str] = []

    # Significant wave height (Linsley & Franzini approximation)
    Hs = 0.0248 * U ** 2 * F ** 0.5
    # Clamp: maximum wave height limited by depth (breaking)
    Hs = min(Hs, 0.7 * d)

    # Wave period (SMB: T_s ≈ 0.4·sqrt(F_m) where F_m in metres)
    F_m = F * 1000
    T_s = 0.4 * math.sqrt(F_m)  # approximate

    # Wind setup
    # S_w = U² · F / (61000 · d)  (F in km, d in m, U in m/s)
    Sw = U ** 2 * F / (61000.0 * d)

    # Wave runup (simplified for rough concrete / rip-rap)
    # R_u / H_s ≈ 2.0 for rough embankments (USBR guide)
    # Slope effect: multiply by (1/m)^0.5 correction factor
    slope_factor = 1.0 / math.sqrt(m)
    Ru = 2.0 * Hs * slope_factor
    Ru = max(Ru, Hs)  # minimum = wave height

    freeboard = Sw + Ru + float(freeboard_safety_m)

    if wind_speed_m_s > 35:
        warnings.append(f"Wind speed {U} m/s is very high: verify regional design wind speed")
    if Hs > 1.5:
        warnings.append(
            f"Significant wave height {Hs:.2f} m: consider armoured riprap or concrete facing"
        )
    if freeboard < 0.5:
        warnings.append("Required freeboard < 0.5 m: inadequate; minimum 0.5 m recommended")
    if freeboard < 1.0:
        warnings.append("Freeboard < 1.0 m: review against applicable dam safety regulation")

    return _ok(
        significant_wave_height_m=round(Hs, 4),
        wave_period_s=round(T_s, 4),
        wind_setup_m=round(Sw, 5),
        wave_runup_m=round(Ru, 4),
        required_freeboard_m=round(freeboard, 4),
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# 10. gravity_dam_stability — overturning / sliding / uplift quick-check
# ---------------------------------------------------------------------------

def gravity_dam_stability(
    dam_height_m: float,
    dam_base_width_m: float,
    upstream_water_depth_m: float,
    *,
    concrete_density_kg_m3: float = 2400.0,
    downstream_water_depth_m: float = 0.0,
    uplift_fraction: float = 0.667,
    friction_coefficient: float = 0.75,
    unit_length_m: float = 1.0,
    crest_width_m: float = 0.0,
) -> dict:
    """Gravity-dam stability quick-check per USBR / ICOLD criteria.

    Checks per unit length of dam (default 1 m):

    1. Overturning stability:
         OTM = ½ · γ_w · H_w² · B   (horizontal hydrostatic)
         Resisting moment RM = W · d_W (weight × centroid arm from toe)
         FOS_overturning = RM / OTM  ≥ 1.5 recommended

    2. Uplift force:
         U = α · γ_w · (H_u + H_d)/2 · B
         α = uplift_fraction (0.667 full base drains, 1.0 no drains)

    3. Sliding stability:
         FOS_sliding = (μ · (W - U)) / H_hydrostatic  ≥ 1.0 (min)
         Recommended FOS ≥ 1.5 with passive resistance

    4. Resultant location (middle-third rule):
         e = B/2 - x_R  where x_R = (RM - OTM) / W_eff
         Resultant in middle third:  e ≤ B/6

    Simplified rectangular cross-section.  Inclined upstream / downstream
    faces, silt pressure, seismic loads, and tension crack not included.

    Parameters
    ----------
    dam_height_m : float
        Dam height H (m).  Must be > 0.
    dam_base_width_m : float
        Base width B (m).  Must be > 0.
    upstream_water_depth_m : float
        Upstream water depth above foundation (m).  Must be > 0.
    concrete_density_kg_m3 : float
        Unit weight of concrete (kg/m³).  Default 2400.
    downstream_water_depth_m : float
        Downstream tailwater depth (m).  Default 0.
    uplift_fraction : float
        α = uplift intensity factor (0–1).  0.667 = drains at 1/3 base.
        1.0 = no drainage (conservative).
    friction_coefficient : float
        μ = base friction coefficient.  0.75 typical for concrete-on-rock.
    unit_length_m : float
        Dam length (m) per unit being analysed.  Default 1.
    crest_width_m : float
        Crest width (m).  If 0, approximated as 0.15·dam_height_m.

    Returns
    -------
    dict with ok=True and keys:
        weight_kN, uplift_kN, net_vertical_kN,
        horizontal_hydrostatic_kN, overturning_moment_kNm,
        resisting_moment_kNm, FOS_overturning, FOS_sliding,
        eccentricity_m, base_width_m, middle_third_ok,
        stable, warnings
    """
    e = (_pos(dam_height_m, "dam_height_m") or
         _pos(dam_base_width_m, "dam_base_width_m") or
         _pos(upstream_water_depth_m, "upstream_water_depth_m") or
         _pos(concrete_density_kg_m3, "concrete_density_kg_m3") or
         _pos(friction_coefficient, "friction_coefficient"))
    if e:
        return _err(e)
    e2 = _nonneg(downstream_water_depth_m, "downstream_water_depth_m") or \
         _nonneg(uplift_fraction, "uplift_fraction")
    if e2:
        return _err(e2)
    if uplift_fraction > 1.0:
        return _err("uplift_fraction must be <= 1.0")

    H = float(dam_height_m)
    B = float(dam_base_width_m)
    Hw = float(upstream_water_depth_m)
    Hd_tw = float(downstream_water_depth_m)
    rho_c = float(concrete_density_kg_m3)
    alpha = float(uplift_fraction)
    mu = float(friction_coefficient)
    Lw = float(unit_length_m)
    Bw = float(crest_width_m) if crest_width_m > 0 else max(0.15 * H, B * 0.1)

    warnings: list[str] = []

    gamma_w = 9.81  # kN/m³ (water unit weight)
    gamma_c = rho_c * 9.81 / 1000.0  # kN/m³

    # Dam weight (trapezoidal simplification; use base as average)
    # For rectangular section: W = γ_c · B · H · Lw
    W = gamma_c * (B + Bw) / 2.0 * H * Lw  # trapezoidal (kN)
    # Centroid of trapezoidal from toe: x_W ≈ B/3 * (1 + Bw/B)/(1+Bw/B) — approximate
    # Simplified: take weight centroid = B * (B+2*Bw) / (3*(B+Bw))  from downstream toe
    x_W = B * (B + 2 * Bw) / (3.0 * (B + Bw)) if (B + Bw) > 0 else B / 2.0

    # Uplift force (linear distribution from Hu at heel to Hd at toe)
    U = alpha * gamma_w * (Hw + Hd_tw) / 2.0 * B * Lw  # kN
    # Uplift centroid: for linear distribution from Hw (heel) to Hd (toe):
    # x_U = B * (2*Hd_tw + Hw) / (3*(Hw + Hd_tw))  from toe
    if (Hw + Hd_tw) > 0:
        x_U = B * (2.0 * Hd_tw + Hw) / (3.0 * (Hw + Hd_tw))
    else:
        x_U = B / 2.0

    # Horizontal hydrostatic force (upstream)
    Ph = 0.5 * gamma_w * Hw ** 2 * Lw  # kN
    # Point of application: H_w/3 from base
    y_Ph = Hw / 3.0

    # Downstream hydrostatic (resisting)
    Ph_ds = 0.5 * gamma_w * Hd_tw ** 2 * Lw  # kN
    y_Ph_ds = Hd_tw / 3.0

    # ---- Moments about toe (downstream face at base) ----
    # Overturning moments (anticlockwise, about toe)
    OTM = Ph * y_Ph - Ph_ds * y_Ph_ds  # net horizontal moment
    OTM += U * x_U  # uplift also overturning

    # Resisting moments
    RM = W * x_W

    # FOS overturning
    FOS_ot = RM / OTM if OTM > 0 else float("inf")

    # Net vertical force
    V_net = W - U + Ph_ds * 0  # Ph_ds is horizontal, ignored for vertical sum
    # (downstream hydrostatic is horizontal in simplified calc)

    # Sliding
    FOS_sl = (mu * (W - U) + Ph_ds) / Ph if Ph > 0 else float("inf")

    # Resultant location from toe
    M_net = RM - OTM  # net moment about toe
    x_R = M_net / V_net if V_net > 0 else B / 2.0
    e_eccen = B / 2.0 - x_R  # eccentricity from centre
    middle_third = abs(e_eccen) <= B / 6.0

    stable = (FOS_ot >= 1.5) and (FOS_sl >= 1.0) and middle_third

    if FOS_ot < 1.5:
        warnings.append(
            f"FOS overturning = {FOS_ot:.2f} < 1.5: dam may overturn; increase base width or add drainage"
        )
    if FOS_sl < 1.5:
        warnings.append(
            f"FOS sliding = {FOS_sl:.2f} < 1.5: check shear key or increase friction"
        )
    if FOS_sl < 1.0:
        warnings.append(
            f"FOS sliding = {FOS_sl:.2f} < 1.0: CRITICAL — dam will slide"
        )
    if not middle_third:
        warnings.append(
            f"Resultant eccentricity e = {e_eccen:.3f} m > B/6 = {B/6:.3f} m: "
            "tension at heel; resultant outside middle third"
        )
    if Hw > H:
        warnings.append("Upstream water depth > dam height: overtopping condition")

    return _ok(
        weight_kN=round(W, 2),
        uplift_kN=round(U, 2),
        net_vertical_kN=round(V_net, 2),
        horizontal_hydrostatic_kN=round(Ph, 2),
        overturning_moment_kNm=round(OTM, 2),
        resisting_moment_kNm=round(RM, 2),
        FOS_overturning=round(FOS_ot, 3),
        FOS_sliding=round(FOS_sl, 3),
        eccentricity_m=round(e_eccen, 4),
        base_width_m=round(B, 4),
        middle_third_ok=middle_third,
        stable=stable,
        warnings=warnings,
    )
