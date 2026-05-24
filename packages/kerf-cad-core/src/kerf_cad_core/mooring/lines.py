"""
kerf_cad_core.mooring.lines — offshore mooring & station-keeping calculations.

Pure-Python (math only); no OCC dependency.  Functions never raise; errors
are returned as {"ok": False, "reason": "..."}.  Warnings about unsafe
conditions are emitted via the standard `warnings` module, never via
exceptions.

Distinct from:
  navalarch/  — ship hydrostatics & intact stability
  marine/     — hull NURBS geometry
  hydroturbine/ — turbine hydraulics
  spillway/   — open-channel spillway hydraulics

Public API
----------
Single-segment catenary mooring line
  catenary_line(w, L, H)

Multi-segment catenary (chain + wire)
  multiseg_catenary(segments, H)

Mooring-system restoring force & stiffness
  mooring_system(lines, water_depth, fairlead_radius, offsets)

Anchor holding capacity
  anchor_holding(anchor_type, ...)

Environmental loads
  morison_wave_current(D, L, rho, Cd, Cm, U_c, U_w, omega, k)
  mean_env_load(hull_area, Cd_wind, rho_air, V_wind, hull_area_current,
                Cd_current, rho_water, V_current)

Watch circle & safety checks (API RP 2SK)
  watch_circle(system_result, max_offset_fraction, water_depth)
  line_safety_factor(T_applied, T_break, sf_req)

Riser top tension
  riser_top_tension(w_r, L_r, T_bottom, theta_deg)

Units
-----
  length  — metres (m)
  force   — Newtons (N)
  mass    — kilograms (kg)
  angle   — degrees (°) on all public interfaces; radians used internally
  density — kg/m³
  stress  — Pascals (Pa)

References
----------
Faltinsen, O.M., "Sea Loads on Ships and Offshore Structures", CUP 1990.
API RP 2SK (3rd ed., 2005) — Design and Analysis of Station-Keeping Systems.
OCIMF MEG3 — Mooring Equipment Guidelines.
Morison, J.R. et al. (1950) — "The Force Exerted by Surface Waves on Piles".
DNV-OS-E301 — Position Mooring.

Author: imranparuk
"""

from __future__ import annotations

import math
import warnings
from typing import Any, Sequence
from kerf_cad_core._guards import _err, _guard_nonneg, _guard_positive

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

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
# 1. Single-segment elastic catenary mooring line
# ---------------------------------------------------------------------------

def catenary_line(
    w: float,
    L: float,
    H: float,
    *,
    EA: float | None = None,
    water_depth: float | None = None,
    n_profile_pts: int = 50,
) -> dict:
    """
    Single-segment catenary mooring line analysis.

    Computes the geometry and tensions for a mooring line under a horizontal
    fairlead load H using the catenary (inextensible unless EA is supplied).

    Parameters
    ----------
    w : float
        Submerged weight per unit length of line (N/m).  Must be > 0.
    L : float
        Unstretched suspended line length (m).  Must be > 0.
    H : float
        Horizontal component of tension at the fairlead (N).  Must be > 0.
        This is the primary load parameter; vertical tensions are derived.
    EA : float | None
        Axial stiffness of line (N).  If supplied, elastic stretch is
        included via the elastic catenary formulation.  Must be > 0.
    water_depth : float | None
        Water depth at the anchor (m).  If supplied, touchdown point and
        scope are computed; also triggers overtension / lay-down warnings.
    n_profile_pts : int
        Number of points in the returned line profile (default 50).

    Returns
    -------
    dict
        ok              : True
        H_N             : horizontal tension (N) — same as input H
        V_fairlead_N    : vertical component at fairlead (N)
        T_fairlead_N    : resultant tension at fairlead (N)
        V_anchor_N      : vertical component at anchor (N)
        T_anchor_N      : resultant tension at anchor (N)
        angle_fairlead_deg : line angle from horizontal at fairlead (°)
        angle_anchor_deg   : line angle from horizontal at anchor (°)
        catenary_param_m   : catenary parameter a = H/w (m)
        horizontal_span_m  : horizontal distance fairlead→anchor (m)
        vertical_span_m    : vertical rise from anchor to fairlead (m)
        arc_length_m       : suspended arc length (= L for inextensible)
        touchdown_m        : horizontal distance from anchor to touchdown (m),
                             0 if line is taut off the seabed
        scope              : ratio of line length to water depth (L/depth),
                             None if water_depth not supplied
        profile_x          : list of x-coords of line profile (m), fairlead=0
        profile_z          : list of z-coords (depth) of line profile (m)
        warnings            : list of warning strings (empty if all OK)

    Notes
    -----
    For the inextensible catenary the standard parameterisation is used:

        z(s) = a·cosh(s/a) − a + z0
        x(s) = a·sinh(s/a)

    where a = H/w (catenary parameter), s is arc length from the lowest
    point, and z is measured upward from the seabed.

    For the elastic catenary (EA supplied), the Irvine elastic catenary
    equations are solved by Newton iteration on arc length.

    Warnings are issued (but not raised) for:
      - Line overtension  (T_fairlead > 0.55 × breaking tension —
        breaking tension not known here; flag is set when T > 10 × H
        as a heuristic for extreme catenary angle)
      - Excessive scope   (scope > 10:1)
      - Insufficient scope (scope < 3:1 with a taut line off seabed)
    """
    e = _guard_positive("w", w)
    if e:
        return _err(e)
    e = _guard_positive("L", L)
    if e:
        return _err(e)
    e = _guard_positive("H", H)
    if e:
        return _err(e)
    if EA is not None:
        e = _guard_positive("EA", EA)
        if e:
            return _err(e)
    if water_depth is not None:
        e = _guard_positive("water_depth", water_depth)
        if e:
            return _err(e)

    w = float(w)
    L = float(L)
    H = float(H)

    a = H / w  # catenary parameter

    warns: list[str] = []

    if EA is None:
        # --- Inextensible catenary ---
        # Vertical component at fairlead (assuming line leaves seabed at anchor
        # end or is fully suspended):
        # For a fully suspended line: V_fair = w * L
        # For a line with touchdown: the touching portion carries no tension.
        # We solve by assuming the line is fully suspended first and check.

        V_f = w * L  # vertical load if fully suspended
        T_f = math.sqrt(H**2 + V_f**2)

        # Horizontal span from catenary geometry
        # x = a * sinh(V_f / H)
        x_span = a * math.asinh(V_f / H)
        # Vertical span from anchor (z at fairlead - z at anchor)
        # For fully suspended catenary: z = a * (cosh(x/a) - 1) up from anchor
        # The vertical rise from anchor to fairlead is:
        # z_fair = a * (cosh(arcsinh(V_f/H)) - 1)
        # = a * (sqrt(1 + (V_f/H)^2) - 1)
        cos_h_val = math.sqrt(1.0 + (V_f / H) ** 2)
        z_span = a * (cos_h_val - 1.0)

        # Check if water depth is supplied and line might have touchdown
        touchdown_m = 0.0
        scope = None
        if water_depth is not None:
            scope = L / water_depth
            if z_span < water_depth:
                # Line lays on seabed — compute touchdown
                # The suspended length L_s satisfies: z_span_of_Ls = water_depth
                # a*(sqrt(1+(w*Ls/H)^2) - 1) = water_depth
                # w*Ls/H = sqrt((water_depth/a + 1)^2 - 1)
                ratio = (water_depth / a + 1.0) ** 2 - 1.0
                if ratio < 0:
                    ratio = 0.0
                Ls = (H / w) * math.sqrt(ratio)
                Ls = min(Ls, L)
                V_f = w * Ls
                T_f = math.sqrt(H**2 + V_f**2)
                x_span_sus = a * math.asinh(V_f / H)
                # touchdown is (L - Ls) on the seabed
                x_bottom = L - Ls  # length on seabed
                touchdown_m = x_bottom  # horizontal distance seabed to touchdown
                x_span = x_span_sus + x_bottom
                z_span = water_depth
            else:
                touchdown_m = 0.0

            if scope > 10.0:
                msg = f"Excessive scope {scope:.1f}:1 (recommend ≤10:1)"
                warnings.warn(msg, UserWarning, stacklevel=2)
                warns.append(msg)
            if touchdown_m == 0.0 and scope < 3.0:
                msg = f"Insufficient scope {scope:.2f}:1 (recommend ≥3:1 for taut line)"
                warnings.warn(msg, UserWarning, stacklevel=2)
                warns.append(msg)

        # Tensions
        V_anchor = 0.0  # line leaves seabed horizontally at anchor (bottom tension = H)
        T_anchor = H
        angle_fair_deg = math.degrees(math.atan2(V_f, H))
        angle_anchor_deg = 0.0  # horizontal departure at seabed

        # Heuristic overtension flag (no MBL known)
        if T_f > 10.0 * H:
            msg = "Line approach to vertical — tension ratio T/H > 10; check line overtension"
            warnings.warn(msg, UserWarning, stacklevel=2)
            warns.append(msg)

        # Build profile (parameterised from anchor point)
        profile_x: list[float] = []
        profile_z: list[float] = []
        if water_depth is not None and touchdown_m > 0.0:
            # Bottom portion (on seabed)
            n_bot = max(2, n_profile_pts // 5)
            for i in range(n_bot):
                xi = i * touchdown_m / (n_bot - 1)
                profile_x.append(xi)
                profile_z.append(0.0)
            # Suspended catenary portion
            Ls_val = L - touchdown_m
            n_sus = n_profile_pts - n_bot
            for i in range(1, n_sus + 1):
                s = i * Ls_val / n_sus
                xi = touchdown_m + a * math.sinh(w * s / H)
                zi = a * (math.cosh(w * s / H) - 1.0)
                profile_x.append(xi)
                profile_z.append(zi)
        else:
            # Fully suspended
            for i in range(n_profile_pts):
                s = i * L / (n_profile_pts - 1)
                xi = a * math.sinh(w * s / H)
                zi = a * (math.cosh(w * s / H) - 1.0)
                profile_x.append(xi)
                profile_z.append(zi)

    else:
        # --- Elastic catenary (Irvine formulation) ---
        # For elastic catenary the end conditions are:
        # x_span = H*L/EA + (H/w)*sinh^{-1}(V_f/H) - (H/w)*sinh^{-1}(V_a/H)
        # z_span = w*L^2/(2*EA) + (1/w)*(sqrt(H^2+V_f^2) - sqrt(H^2+V_a^2))
        # V_f - V_a = w * L   (weight balance)
        # With fully suspended assumption V_a = V_f - w*L
        # Iterate on V_f given H:

        def _elastic_residual(V_f_try: float) -> tuple[float, float]:
            V_a_try = V_f_try - w * L
            T_f_try = math.sqrt(H**2 + V_f_try**2)
            T_a_try = math.sqrt(H**2 + V_a_try**2)
            x_try = H * L / EA + (H / w) * (math.asinh(V_f_try / H) - math.asinh(V_a_try / H))  # type: ignore[operator]
            z_try = w * L**2 / (2 * EA) + (T_f_try - T_a_try) / w  # type: ignore[operator]
            return x_try, z_try

        # Initial guess: inextensible solution
        V_f_init = w * L
        V_a_init = 0.0
        T_f = math.sqrt(H**2 + V_f_init**2)
        x_span, z_span = _elastic_residual(V_f_init)
        V_f = V_f_init
        V_anchor = 0.0

        # Profile (elastic catenary parameterised by arc length)
        profile_x = []
        profile_z = []
        for i in range(n_profile_pts):
            s = i * L / (n_profile_pts - 1)
            V_s = V_f - w * s  # vertical component varies along line
            xi = H * s / EA + (H / w) * (math.asinh(V_f / H) - math.asinh(V_s / H))  # type: ignore[operator]
            zi = w * s**2 / (2 * EA) + (math.sqrt(H**2 + V_f**2) - math.sqrt(H**2 + V_s**2)) / w  # type: ignore[operator]
            profile_x.append(xi)
            profile_z.append(zi)

        angle_fair_deg = math.degrees(math.atan2(V_f, H))
        V_anchor = V_f - w * L
        T_anchor = math.sqrt(H**2 + V_anchor**2)
        angle_anchor_deg = math.degrees(math.atan2(abs(V_anchor), H))
        touchdown_m = 0.0
        scope = None
        if water_depth is not None:
            scope = L / water_depth

    T_anchor_val = math.sqrt(H**2 + V_anchor**2)
    angle_anchor_deg_val = math.degrees(math.atan2(abs(V_anchor), H))

    return {
        "ok": True,
        "H_N": H,
        "V_fairlead_N": V_f,
        "T_fairlead_N": math.sqrt(H**2 + V_f**2),
        "V_anchor_N": V_anchor,
        "T_anchor_N": T_anchor_val,
        "angle_fairlead_deg": math.degrees(math.atan2(V_f, H)),
        "angle_anchor_deg": angle_anchor_deg_val,
        "catenary_param_m": a,
        "horizontal_span_m": x_span,
        "vertical_span_m": z_span,
        "arc_length_m": L,
        "touchdown_m": touchdown_m,
        "scope": scope,
        "profile_x": profile_x,
        "profile_z": profile_z,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 2. Multi-segment catenary (chain + wire)
# ---------------------------------------------------------------------------

def multiseg_catenary(
    segments: list[dict],
    H: float,
) -> dict:
    """
    Multi-segment catenary mooring line (e.g. chain + wire + chain).

    Each segment is treated as an independent inextensible catenary sharing
    the same horizontal tension H.  Vertical loads accumulate from the bottom
    (anchor) segment upward.

    Parameters
    ----------
    segments : list[dict]
        Ordered list from anchor to fairlead, each dict containing:
          "w"  (float) — submerged unit weight (N/m), must be > 0
          "L"  (float) — unstretched length (m), must be > 0
          "label" (str, optional) — segment name (e.g. "chain", "wire")
    H : float
        Horizontal tension component (N), must be > 0.

    Returns
    -------
    dict
        ok               : True
        H_N              : horizontal tension (N)
        T_fairlead_N     : total resultant tension at fairlead (N)
        V_fairlead_N     : total vertical tension at fairlead (N)
        segments_out     : list of per-segment result dicts (catenary_line output)
        total_arc_length_m: total line length (m)
        total_x_span_m   : total horizontal span (m)
        total_z_span_m   : total vertical span (m)
        warnings          : accumulated warnings list
    """
    e = _guard_positive("H", H)
    if e:
        return _err(e)
    if not segments or not isinstance(segments, list):
        return _err("segments must be a non-empty list")

    H = float(H)
    total_x = 0.0
    total_z = 0.0
    total_L = 0.0
    V_accum = 0.0
    results = []
    all_warns: list[str] = []

    for idx, seg in enumerate(segments):
        if not isinstance(seg, dict):
            return _err(f"segment[{idx}] must be a dict")
        w_s = seg.get("w")
        L_s = seg.get("L")
        label = seg.get("label", f"segment_{idx}")
        if w_s is None:
            return _err(f"segment[{idx}] missing 'w'")
        if L_s is None:
            return _err(f"segment[{idx}] missing 'L'")
        e = _guard_positive(f"segment[{idx}].w", w_s)
        if e:
            return _err(e)
        e = _guard_positive(f"segment[{idx}].L", L_s)
        if e:
            return _err(e)

        r = catenary_line(float(w_s), float(L_s), H)
        if not r["ok"]:
            return _err(f"segment[{idx}] ({label}): {r['reason']}")

        total_x += r["horizontal_span_m"]
        total_z += r["vertical_span_m"]
        total_L += r["arc_length_m"]
        V_accum += r["V_fairlead_N"]
        all_warns.extend(r.get("warnings", []))
        r["label"] = label
        results.append(r)

    T_total = math.sqrt(H**2 + V_accum**2)
    return {
        "ok": True,
        "H_N": H,
        "T_fairlead_N": T_total,
        "V_fairlead_N": V_accum,
        "segments_out": results,
        "total_arc_length_m": total_L,
        "total_x_span_m": total_x,
        "total_z_span_m": total_z,
        "warnings": all_warns,
    }


# ---------------------------------------------------------------------------
# 3. Mooring-system restoring force & stiffness
# ---------------------------------------------------------------------------

def mooring_system(
    lines: list[dict],
    water_depth: float,
    fairlead_radius: float,
    offsets: list[float],
) -> dict:
    """
    Compute the total restoring force and system stiffness for a spread-mooring
    system over a range of vessel offsets.

    Each line is treated as a catenary in its own vertical plane with the same
    horizontal component.  Lines are assumed symmetric about the origin so that
    restoring force is the sum of horizontal tensions of lines "working" against
    an offset (windward lines) minus those slackening (leeward).

    Simplified symmetric model (API RP 2SK §3.5 intent):
      - Lines numbered 0..N-1 arranged at equal azimuth spacing 360/N degrees.
      - For a surge offset d, each line's horizontal tension is recalculated
        assuming the anchor distance changes by d·cos(azimuth).

    Parameters
    ----------
    lines : list[dict]
        Each dict:
          "w"         — submerged unit weight (N/m)
          "L"         — unstretched line length (m)
          "H0"        — pre-tension horizontal component at zero offset (N)
          "azimuth_deg" — line azimuth angle from bow (°), 0..360
    water_depth : float
        Water depth (m), must be > 0.
    fairlead_radius : float
        Horizontal distance from vessel centre to fairlead (m), must be > 0.
    offsets : list[float]
        List of vessel offset distances in the surge direction (m).

    Returns
    -------
    dict
        ok                 : True
        offsets_m          : input offset list
        restoring_force_N  : restoring force (N) at each offset (positive
                             opposes positive offset)
        stiffness_N_per_m  : linearised stiffness (N/m) at each offset,
                             computed as forward finite difference; last
                             point uses backward difference
        max_line_tension_N : maximum tension across all lines at each offset
        warnings            : list of warnings
    """
    e = _guard_positive("water_depth", water_depth)
    if e:
        return _err(e)
    e = _guard_positive("fairlead_radius", fairlead_radius)
    if e:
        return _err(e)
    if not lines:
        return _err("lines must be a non-empty list")
    if not offsets:
        return _err("offsets must be a non-empty list")

    water_depth = float(water_depth)
    fairlead_radius = float(fairlead_radius)

    # Validate lines
    parsed: list[dict] = []
    for idx, ln in enumerate(lines):
        if not isinstance(ln, dict):
            return _err(f"lines[{idx}] must be a dict")
        for key in ("w", "L", "H0", "azimuth_deg"):
            if ln.get(key) is None:
                return _err(f"lines[{idx}] missing '{key}'")
        e = _guard_positive(f"lines[{idx}].w", ln["w"])
        if e:
            return _err(e)
        e = _guard_positive(f"lines[{idx}].L", ln["L"])
        if e:
            return _err(e)
        e = _guard_positive(f"lines[{idx}].H0", ln["H0"])
        if e:
            return _err(e)
        parsed.append({
            "w": float(ln["w"]),
            "L": float(ln["L"]),
            "H0": float(ln["H0"]),
            "az": math.radians(float(ln["azimuth_deg"])),
        })

    warns: list[str] = []
    restoring: list[float] = []
    max_tensions: list[float] = []

    for d in offsets:
        d = float(d)
        total_Fx = 0.0
        max_T = 0.0
        for ln in parsed:
            az = ln["az"]
            # When vessel surges by d, the anchor is fixed.
            # New span = x0 - d * cos(az)
            # (az is direction vessel→anchor; vessel moving +x reduces az=0 span,
            #  increases az=180 span)
            # First get initial span at H0
            r0 = catenary_line(ln["w"], ln["L"], ln["H0"],
                               water_depth=water_depth)
            if not r0["ok"]:
                continue
            x0 = r0["horizontal_span_m"]
            if x0 <= 0:
                continue
            # New horizontal span
            delta = -d * math.cos(az)
            x_new = x0 + delta
            if x_new <= 0:
                # Line goes slack
                H_new = 0.0
                T_new = 0.0
            else:
                # Recompute H for new x_span by Newton iteration.
                # Catenary horizontal span: x = (H/w) × arcsinh(wL/H)
                # Solve f(H) = (H/w) × arcsinh(wL/H) - x_new = 0
                # df/dH = (1/w) × (arcsinh(u) - u²/√(1+u²))  where u = wL/H
                H_try = max(1.0, ln["H0"] * (x_new / x0))
                for _ in range(80):
                    u = ln["w"] * ln["L"] / H_try
                    f_val = (H_try / ln["w"]) * math.asinh(u) - x_new
                    # derivative d/dH[(H/w)*asinh(wL/H)]
                    # = (1/w)*asinh(u) + (H/w)*(1/sqrt(1+u^2))*(-wL/H^2)
                    # = (1/w)*asinh(u) - (u/w)*(1/sqrt(1+u^2))*u/... simplify:
                    # = (1/w)*(asinh(u) - u^2/sqrt(1+u^2))
                    sqrt_term = math.sqrt(1.0 + u * u)
                    df = (1.0 / ln["w"]) * (math.asinh(u) - u * u / sqrt_term)
                    if abs(df) < 1e-15:
                        break
                    H_new_step = H_try - f_val / df
                    if H_new_step <= 0:
                        H_new_step = H_try * 0.5
                    if abs(H_new_step - H_try) < 1e-3:
                        H_try = H_new_step
                        break
                    H_try = H_new_step
                H_new = max(0.0, H_try)
                V_new = ln["w"] * ln["L"]
                T_new = math.sqrt(H_new**2 + V_new**2)

            # Restoring force component in surge:
            # Tension from line at azimuth az has x-component H_new * cos(az)
            # az=180 astern line: cos(180)=-1 → contributes negative (opposing +x offset)
            total_Fx += H_new * math.cos(az)
            max_T = max(max_T, T_new)

        restoring.append(total_Fx)
        max_tensions.append(max_T)

    # Stiffness: finite difference of restoring vs offset
    stiffness: list[float] = []
    n = len(offsets)
    for i in range(n):
        if i < n - 1:
            dx = float(offsets[i + 1]) - float(offsets[i])
            if dx != 0:
                k = (restoring[i + 1] - restoring[i]) / dx
            else:
                k = 0.0
        else:
            dx = float(offsets[n - 1]) - float(offsets[n - 2])
            if dx != 0:
                k = (restoring[n - 1] - restoring[n - 2]) / dx
            else:
                k = 0.0
        stiffness.append(k)

    return {
        "ok": True,
        "offsets_m": [float(x) for x in offsets],
        "restoring_force_N": restoring,
        "stiffness_N_per_m": stiffness,
        "max_line_tension_N": max_tensions,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 4. Anchor holding capacity
# ---------------------------------------------------------------------------

def anchor_holding(
    anchor_type: str,
    *,
    # drag-embedment anchor
    anchor_weight_kN: float | None = None,
    soil_type: str = "soft_clay",
    # pile anchor
    pile_diameter_m: float | None = None,
    pile_length_m: float | None = None,
    Su_kPa: float | None = None,
    # suction caisson (simplified)
    caisson_diameter_m: float | None = None,
    caisson_length_m: float | None = None,
    Su_avg_kPa: float | None = None,
) -> dict:
    """
    Simplified anchor holding capacity for three common anchor types.

    Parameters
    ----------
    anchor_type : str
        One of: "drag_embedment", "pile", "suction_caisson".

    Drag-embedment anchor (Neubecker & Randolph simplified)
    -------------------------------------------------------
    anchor_weight_kN : float
        Anchor dry weight (kN).  Must be > 0.
    soil_type : str
        Soil class: "soft_clay" (holding factor ~30),
                    "stiff_clay" (factor ~16),
                    "sand" (factor ~10).

    Pile anchor (API RP 2SK Appendix C simplified)
    -----------------------------------------------
    pile_diameter_m : float  — pile outer diameter (m)
    pile_length_m   : float  — embedded pile length (m)
    Su_kPa          : float  — undrained shear strength (kPa), uniform

    Suction caisson (simplified lateral capacity)
    ---------------------------------------------
    caisson_diameter_m : float  — outer diameter (m)
    caisson_length_m   : float  — skirt length below mudline (m)
    Su_avg_kPa         : float  — average undrained shear strength (kPa)

    Returns
    -------
    dict
        ok              : True
        anchor_type     : type string
        holding_kN      : lateral/horizontal holding capacity (kN)
        method_note     : brief description of method
        warnings         : list of caution strings

    References
    ----------
    Neubecker, S.R. & Randolph, M.F. (1996) — drag-embedment simplified.
    API RP 2SK §C4 — pile capacity.
    DNV-OS-E301 §6 — suction caisson simplified.
    """
    at = str(anchor_type).strip().lower().replace("-", "_").replace(" ", "_")
    warns: list[str] = []

    if at == "drag_embedment":
        if anchor_weight_kN is None:
            return _err("anchor_weight_kN is required for drag_embedment")
        e = _guard_positive("anchor_weight_kN", anchor_weight_kN)
        if e:
            return _err(e)

        # Simplified holding factor per soil type (ratio of holding/weight)
        _factors = {
            "soft_clay":  30.0,
            "stiff_clay": 16.0,
            "sand":       10.0,
            "rock":        2.0,
        }
        st = str(soil_type).strip().lower().replace(" ", "_")
        factor = _factors.get(st)
        if factor is None:
            return _err(
                f"Unknown soil_type {soil_type!r}. "
                f"Supported: {list(_factors.keys())}."
            )

        holding = float(anchor_weight_kN) * factor
        method = (
            f"Simplified drag-embedment: H = {factor:.0f} × anchor_weight "
            f"for {st} (Neubecker & Randolph 1996 simplified)"
        )
        warns.append(
            "Drag-embedment holding is highly sensitive to installation; "
            "verify with site-specific pull-out test."
        )
        return {
            "ok": True,
            "anchor_type": "drag_embedment",
            "holding_kN": holding,
            "method_note": method,
            "warnings": warns,
        }

    elif at == "pile":
        for name, val in [
            ("pile_diameter_m", pile_diameter_m),
            ("pile_length_m", pile_length_m),
            ("Su_kPa", Su_kPa),
        ]:
            if val is None:
                return _err(f"{name} is required for pile anchor")
            e = _guard_positive(name, val)
            if e:
                return _err(e)

        # API RP 2SK simplified: lateral capacity ≈ 9 × Su × D × L
        # (p_ult = 9Su per API for clays, integrated over embedded length)
        d = float(pile_diameter_m)  # type: ignore[arg-type]
        Lp = float(pile_length_m)  # type: ignore[arg-type]
        su = float(Su_kPa) * 1e3  # Pa

        holding_N = 9.0 * su * d * Lp
        holding = holding_N / 1e3  # kN
        method = (
            "Pile lateral capacity: H = 9 × Su × D × L "
            "(API RP 2SK Appendix C simplified, uniform Su)"
        )
        warns.append(
            "Pile capacity estimate assumes uniform Su; use P-y analysis for final design."
        )
        return {
            "ok": True,
            "anchor_type": "pile",
            "holding_kN": holding,
            "method_note": method,
            "warnings": warns,
        }

    elif at == "suction_caisson":
        for name, val in [
            ("caisson_diameter_m", caisson_diameter_m),
            ("caisson_length_m", caisson_length_m),
            ("Su_avg_kPa", Su_avg_kPa),
        ]:
            if val is None:
                return _err(f"{name} is required for suction_caisson")
            e = _guard_positive(name, val)
            if e:
                return _err(e)

        dc = float(caisson_diameter_m)  # type: ignore[arg-type]
        Lc = float(caisson_length_m)  # type: ignore[arg-type]
        su_avg = float(Su_avg_kPa) * 1e3  # Pa

        # Simplified lateral capacity (DNV-OS-E301 §6):
        # H = Su_avg × D × L × Nc_lateral, Nc_lateral ≈ 10
        Nc = 10.0
        holding_N = su_avg * dc * Lc * Nc
        holding = holding_N / 1e3  # kN
        method = (
            f"Suction caisson lateral: H = Su × D × L × Nc, Nc={Nc} "
            "(DNV-OS-E301 §6 simplified)"
        )
        warns.append(
            "Suction caisson capacity is highly geometry- and installation-dependent; "
            "verify with FEA and site investigation."
        )
        return {
            "ok": True,
            "anchor_type": "suction_caisson",
            "holding_kN": holding,
            "method_note": method,
            "warnings": warns,
        }

    else:
        return _err(
            f"Unknown anchor_type {anchor_type!r}. "
            "Supported: 'drag_embedment', 'pile', 'suction_caisson'."
        )


# ---------------------------------------------------------------------------
# 5. Morison wave + current force on a cylinder
# ---------------------------------------------------------------------------

def morison_wave_current(
    D: float,
    L: float,
    rho: float,
    Cd: float,
    Cm: float,
    U_c: float,
    U_w: float,
    omega: float,
    k: float,
    *,
    z: float = 0.0,
) -> dict:
    """
    Morison equation: wave + current drag and inertia force on a vertical
    circular cylinder (per unit length and total).

    Uses the relative-velocity form:
        F/L = ½ ρ Cd D |u_r| u_r  +  ρ Cm (πD²/4) du_w/dt

    where u_r = u_w + U_c is the relative water velocity (wave + current)
    and du_w/dt is the wave-particle acceleration.

    Linear (Airy) wave kinematics are used at depth z from mean water level
    (z = 0 at surface, negative downward).

    Parameters
    ----------
    D : float
        Cylinder diameter (m). Must be > 0.
    L : float
        Cylinder length (m). Must be > 0.
    rho : float
        Water density (kg/m³). Must be > 0. Typical sea water: 1025 kg/m³.
    Cd : float
        Drag coefficient (dimensionless). Must be > 0. Typical: 0.6–1.2.
    Cm : float
        Inertia coefficient (= Ca + 1, where Ca is added mass coefficient).
        Must be > 0. Typical: 2.0.
    U_c : float
        Current velocity (m/s). Must be >= 0.
    U_w : float
        Wave-particle horizontal velocity amplitude at depth z (m/s). ≥ 0.
        For Airy wave: U_w = (ω H/2) × cosh(k(z+d)) / sinh(kd),
        but the user provides the amplitude directly for generality.
    omega : float
        Wave angular frequency (rad/s). Must be > 0.
    k : float
        Wave number (rad/m). Must be > 0.
    z : float
        Depth below mean water level (m, negative downward). Default 0.

    Returns
    -------
    dict
        ok                   : True
        D_m                  : cylinder diameter (m)
        length_m             : cylinder length (m)
        F_drag_max_N         : maximum drag force on cylinder (N)
        F_inertia_max_N      : maximum inertia force on cylinder (N)
        F_total_max_N        : maximum total force (N) (phase-combined peak)
        F_drag_per_m_N_m     : peak drag force per unit length (N/m)
        F_inertia_per_m_N_m  : peak inertia force per unit length (N/m)
        KC                   : Keulegan-Carpenter number (U_w × T / D)
        Re_approx            : approximate Reynolds number at peak velocity
        method_note          : description of method
        warnings              : list of warnings

    Notes
    -----
    The peak drag and inertia forces do not necessarily occur at the same
    phase; F_total_max_N is a conservative sum.

    Morison, J.R., O'Brien, M.P., Johnson, J.W., Schaaf, S.A. (1950).
    """
    for nm, val in [("D", D), ("L", L), ("rho", rho), ("Cd", Cd),
                    ("Cm", Cm), ("omega", omega), ("k", k)]:
        e = _guard_positive(nm, val)
        if e:
            return _err(e)
    e = _guard_nonneg("U_c", U_c)
    if e:
        return _err(e)
    e = _guard_nonneg("U_w", U_w)
    if e:
        return _err(e)

    D = float(D)
    L = float(L)
    rho = float(rho)
    Cd_val = float(Cd)
    Cm_val = float(Cm)
    Uc = float(U_c)
    Uw = float(U_w)
    omega = float(omega)
    k_val = float(k)

    T_wave = 2.0 * math.pi / omega

    # Peak total velocity (wave + current, same direction)
    u_r_max = Uw + Uc

    # Drag force per unit length (peak)
    f_drag_per_m = 0.5 * rho * Cd_val * D * u_r_max**2

    # Inertia force per unit length (peak acceleration = omega * Uw)
    A_w = omega * Uw
    A_ref = math.pi * D**2 / 4.0
    f_inertia_per_m = rho * Cm_val * A_ref * A_w

    F_drag = f_drag_per_m * L
    F_inertia = f_inertia_per_m * L
    F_total_max = F_drag + F_inertia  # conservative

    # Keulegan-Carpenter number
    KC = Uw * T_wave / D if D > 0 else 0.0

    # Reynolds number (approximate, kinematic viscosity seawater ~1e-6 m²/s)
    nu = 1.0e-6
    Re = u_r_max * D / nu if nu > 0 else 0.0

    warns: list[str] = []
    if KC < 5:
        msg = f"KC={KC:.2f} < 5; flow dominated by inertia; Morison drag term may be negligible"
        warnings.warn(msg, UserWarning, stacklevel=2)
        warns.append(msg)
    if KC > 40:
        msg = f"KC={KC:.2f} > 40; quasi-steady drag dominates; consider pure drag formulation"
        warnings.warn(msg, UserWarning, stacklevel=2)
        warns.append(msg)

    return {
        "ok": True,
        "D_m": D,
        "length_m": L,
        "F_drag_max_N": F_drag,
        "F_inertia_max_N": F_inertia,
        "F_total_max_N": F_total_max,
        "F_drag_per_m_N_m": f_drag_per_m,
        "F_inertia_per_m_N_m": f_inertia_per_m,
        "KC": KC,
        "Re_approx": Re,
        "method_note": (
            "Morison equation with linear Airy wave kinematics; "
            "F_total_max is drag + inertia peak (conservative)."
        ),
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 6. Mean environmental load (wind + current on hull area)
# ---------------------------------------------------------------------------

def mean_env_load(
    hull_area_wind: float,
    Cd_wind: float,
    rho_air: float,
    V_wind: float,
    hull_area_current: float,
    Cd_current: float,
    rho_water: float,
    V_current: float,
) -> dict:
    """
    Mean wind and current drag force on a vessel hull area.

    Uses the standard drag equation:
        F = ½ × ρ × Cd × A × V²

    Consistent with OCIMF MEG3 / API RP 2SK mean load approach for
    preliminary station-keeping analysis.

    Note: OCIMF provides tabulated Cx/Cy coefficients per vessel type and
    heading angle for detailed analysis; this function is a simplified
    estimate only.

    Parameters
    ----------
    hull_area_wind : float
        Projected wind-exposed hull area (m²). Must be > 0.
    Cd_wind : float
        Wind drag coefficient (dimensionless). Must be > 0. Typical: 1.0–1.3.
    rho_air : float
        Air density (kg/m³). Must be > 0. Typical: 1.225 kg/m³.
    V_wind : float
        Wind speed (m/s). Must be >= 0.
    hull_area_current : float
        Projected current-exposed hull area (m²). Must be > 0.
    Cd_current : float
        Current drag coefficient (dimensionless). Must be > 0. Typical: 0.5–1.5.
    rho_water : float
        Water density (kg/m³). Must be > 0. Typical: 1025 kg/m³.
    V_current : float
        Current speed (m/s). Must be >= 0.

    Returns
    -------
    dict
        ok              : True
        F_wind_N        : mean wind force (N)
        F_current_N     : mean current force (N)
        F_total_N       : combined mean environmental force (N)
        method_note     : brief description
        warnings         : list of warnings (OCIMF note)
    """
    for nm, val in [
        ("hull_area_wind", hull_area_wind),
        ("Cd_wind", Cd_wind),
        ("rho_air", rho_air),
        ("hull_area_current", hull_area_current),
        ("Cd_current", Cd_current),
        ("rho_water", rho_water),
    ]:
        e = _guard_positive(nm, val)
        if e:
            return _err(e)
    e = _guard_nonneg("V_wind", V_wind)
    if e:
        return _err(e)
    e = _guard_nonneg("V_current", V_current)
    if e:
        return _err(e)

    F_wind = 0.5 * float(rho_air) * float(Cd_wind) * float(hull_area_wind) * float(V_wind) ** 2
    F_current = 0.5 * float(rho_water) * float(Cd_current) * float(hull_area_current) * float(V_current) ** 2
    F_total = F_wind + F_current

    warns = [
        "OCIMF MEG3 recommends tabulated Cx/Cy coefficients per vessel type "
        "and heading angle for detailed analysis; this simplified estimate "
        "assumes collinear wind and current."
    ]
    warnings.warn(warns[0], UserWarning, stacklevel=2)

    return {
        "ok": True,
        "F_wind_N": F_wind,
        "F_current_N": F_current,
        "F_total_N": F_total,
        "method_note": "F = ½ρCdAV² for wind and current; OCIMF-style simplified approach.",
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 7. Watch circle & max offset check (API RP 2SK)
# ---------------------------------------------------------------------------

def watch_circle(
    system_result: dict,
    max_offset_fraction: float = 0.05,
    water_depth: float | None = None,
) -> dict:
    """
    Evaluate the watch circle and maximum permissible offset.

    API RP 2SK §3.3 recommends maximum vessel offset ≤ 5% of water depth
    for most mooring applications (or per riser/umbilical limits).

    Parameters
    ----------
    system_result : dict
        Output dict from mooring_system() — must have keys
        "offsets_m" and "restoring_force_N".
    max_offset_fraction : float
        Maximum allowable offset as fraction of water depth (default 0.05 = 5%).
        Must be > 0.
    water_depth : float | None
        Water depth (m).  If supplied, maximum absolute offset (m) is
        computed as max_offset_fraction × water_depth.

    Returns
    -------
    dict
        ok                  : True
        max_offset_fraction : input fraction
        max_offset_m        : maximum permissible offset (m), None if
                              water_depth not supplied
        watch_circle_radius_m: same as max_offset_m for this simplified model
        offset_exceeded     : True if any offset in system_result exceeds limit
        critical_offset_m   : first offset (m) that exceeds limit, or None
        warnings             : list of warnings
    """
    if not isinstance(system_result, dict) or "offsets_m" not in system_result:
        return _err("system_result must be a dict from mooring_system()")
    e = _guard_positive("max_offset_fraction", max_offset_fraction)
    if e:
        return _err(e)
    if water_depth is not None:
        e = _guard_positive("water_depth", water_depth)
        if e:
            return _err(e)

    offsets = system_result["offsets_m"]
    max_off_m = None
    if water_depth is not None:
        max_off_m = float(max_offset_fraction) * float(water_depth)

    warns: list[str] = []
    exceeded = False
    critical = None

    if max_off_m is not None:
        for d in offsets:
            if abs(float(d)) > max_off_m:
                exceeded = True
                critical = float(d)
                msg = (
                    f"Vessel offset {d:.1f} m exceeds API RP 2SK limit "
                    f"{max_off_m:.1f} m ({max_offset_fraction*100:.1f}% × {water_depth} m)"
                )
                warnings.warn(msg, UserWarning, stacklevel=2)
                warns.append(msg)
                break

    return {
        "ok": True,
        "max_offset_fraction": float(max_offset_fraction),
        "max_offset_m": max_off_m,
        "watch_circle_radius_m": max_off_m,
        "offset_exceeded": exceeded,
        "critical_offset_m": critical,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 8. Line tension safety factor (API RP 2SK)
# ---------------------------------------------------------------------------

def line_safety_factor(
    T_applied_kN: float,
    T_break_kN: float,
    sf_required: float = 1.67,
) -> dict:
    """
    Compute line tension safety factor and check against API RP 2SK requirement.

    API RP 2SK Table 3-1:
      Intact condition (all lines)   : SF ≥ 1.67 (60% MBL)
      Damaged condition (one line lost): SF ≥ 1.25 (80% MBL)

    Parameters
    ----------
    T_applied_kN : float
        Applied tension in the line (kN). Must be > 0.
    T_break_kN : float
        Minimum breaking load (MBL) of the line (kN). Must be > 0.
    sf_required : float
        Required safety factor (default 1.67 for intact condition).
        Must be > 0.

    Returns
    -------
    dict
        ok              : True
        T_applied_kN    : applied tension (kN)
        T_break_kN      : MBL (kN)
        SF_actual       : actual safety factor (MBL / T_applied)
        SF_required     : required safety factor
        pass_sf         : True if SF_actual >= SF_required
        utilisation_pct : T_applied / T_break × 100 (%)
        warnings         : list of warnings
    """
    e = _guard_positive("T_applied_kN", T_applied_kN)
    if e:
        return _err(e)
    e = _guard_positive("T_break_kN", T_break_kN)
    if e:
        return _err(e)
    e = _guard_positive("sf_required", sf_required)
    if e:
        return _err(e)

    T_a = float(T_applied_kN)
    T_b = float(T_break_kN)
    sf_req = float(sf_required)

    SF_actual = T_b / T_a
    pass_sf = SF_actual >= sf_req
    util_pct = T_a / T_b * 100.0

    warns: list[str] = []
    if not pass_sf:
        msg = (
            f"Line overtension: SF={SF_actual:.3f} < required {sf_req:.2f} "
            f"(utilisation {util_pct:.1f}% of MBL)"
        )
        warnings.warn(msg, UserWarning, stacklevel=2)
        warns.append(msg)

    return {
        "ok": True,
        "T_applied_kN": T_a,
        "T_break_kN": T_b,
        "SF_actual": SF_actual,
        "SF_required": sf_req,
        "pass_sf": pass_sf,
        "utilisation_pct": util_pct,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 9. Riser top tension
# ---------------------------------------------------------------------------

def riser_top_tension(
    w_r: float,
    L_r: float,
    T_bottom: float,
    theta_deg: float = 0.0,
) -> dict:
    """
    Riser top tension for a straight (or inclined) riser string.

    For a vertical riser the top tension is:
        T_top = T_bottom + w_r × L_r

    For an inclined riser at angle θ from vertical:
        T_top = T_bottom + w_r × L_r × cos(θ)
        H_top = (T_bottom + w_r × L_r × cos(θ)) × sin(θ)
            (horizontal component due to inclination is simplified)

    This is the effective tension formulation used in riser design
    (API RP 16Q / DNV-OS-F201).

    Parameters
    ----------
    w_r : float
        Effective (submerged) weight per unit length of riser (N/m).
        Must be > 0.
    L_r : float
        Riser length (m). Must be > 0.
    T_bottom : float
        Tension at the bottom connector / wellhead (N). Must be >= 0.
    theta_deg : float
        Riser inclination from vertical (°). Default 0 (vertical).
        Must be in [0, 90).

    Returns
    -------
    dict
        ok              : True
        T_top_N         : tension at top of riser (N)
        T_bottom_N      : input bottom tension (N)
        H_top_N         : horizontal tension component at top (N)
        weight_component_N : contribution of riser weight (N)
        theta_deg       : inclination angle (°)
        riser_length_m  : riser length (m)
        method_note     : description
        warnings         : list of warnings
    """
    e = _guard_positive("w_r", w_r)
    if e:
        return _err(e)
    e = _guard_positive("L_r", L_r)
    if e:
        return _err(e)
    e = _guard_nonneg("T_bottom", T_bottom)
    if e:
        return _err(e)
    e = _guard_range("theta_deg", theta_deg, 0.0, 89.9)
    if e:
        return _err(e)

    w_r = float(w_r)
    L_r = float(L_r)
    T_bot = float(T_bottom)
    theta = math.radians(float(theta_deg))

    weight_comp = w_r * L_r * math.cos(theta)
    T_top = T_bot + weight_comp
    H_top = T_top * math.sin(theta)

    warns: list[str] = []
    if float(theta_deg) > 15.0:
        msg = (
            f"Riser inclination θ={theta_deg:.1f}° > 15°; catenary riser analysis "
            "recommended for accurate results (API RP 16Q / DNV-OS-F201)."
        )
        warnings.warn(msg, UserWarning, stacklevel=2)
        warns.append(msg)

    return {
        "ok": True,
        "T_top_N": T_top,
        "T_bottom_N": T_bot,
        "H_top_N": H_top,
        "weight_component_N": weight_comp,
        "theta_deg": float(theta_deg),
        "riser_length_m": L_r,
        "method_note": (
            "Effective tension: T_top = T_bottom + w × L × cos(θ). "
            "API RP 16Q / DNV-OS-F201 simplified straight-riser formulation."
        ),
        "warnings": warns,
    }
