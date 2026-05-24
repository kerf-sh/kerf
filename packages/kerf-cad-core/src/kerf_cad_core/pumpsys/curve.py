"""
kerf_cad_core.pumpsys.curve — centrifugal-pump & system-curve engineering.

Distinct from:
  civil/hydraulics  — pipe-network pressure solver (multi-branch, loops)
  fluidpower/       — hydraulic actuator / circuit sizing

This module covers pump *selection* and *operating-point* analysis:
  system_curve              — H = H_static + K·Q²
  pump_curve_from_points    — quadratic fit from ≥ 3 catalogue (Q, H) points
  operating_point           — intersection of pump & system curves
  hydraulic_power           — useful fluid power, brake power, efficiency
  npsh_available            — NPSHa = (P_atm − P_vapor)/ρg − z_s − h_fs
  npsh_check                — cavitation margin: NPSHa vs NPSHr
  affinity_speed            — pump affinity laws: speed change scaling
  affinity_trim             — pump affinity laws: impeller trim scaling
  pumps_in_series           — combined head-flow curve
  pumps_in_parallel         — combined head-flow curve
  specific_speed            — dimensionless Ns, impeller-type guidance
  minimum_flow_note         — warn if operating Q < 25% of BEP flow

All functions return plain dicts:
    success → {"ok": True, ..., "warnings": [...]}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise; exceedance / off-design conditions add entries to
the "warnings" list but still return ok=True.

Units (SI throughout)
---------------------
  Q             — m³/s    (volume flow rate)
  H             — m       (head in metres of fluid)
  P             — Pa      (pressure, where relevant)
  power         — W       (Watts)
  speed         — rpm     (rotational speed)
  density       — kg/m³
  g             — 9.81 m/s²
  NPSH          — m
  D_impeller    — m

References
----------
Kaplan, I. et al., "Pump Handbook", 4th ed., McGraw-Hill (2010).
White, F.M., "Fluid Mechanics", 8th ed., McGraw-Hill (2016).
Cengel & Cimbala, "Fluid Mechanics: Fundamentals and Applications", 3rd ed.
HI (Hydraulic Institute) Standards.

Author: imranparuk
"""

from __future__ import annotations

import math
from typing import Any
from kerf_cad_core._guards import _err, _guard_nonneg, _guard_positive

_G = 9.81  # m/s²


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ok(**kwargs) -> dict:
    d = {"ok": True, "warnings": []}
    d.update(kwargs)
    return d


# ---------------------------------------------------------------------------
# 1. system_curve
# ---------------------------------------------------------------------------

def system_curve(
    H_static: float,
    K: float,
    Q: float,
) -> dict:
    """
    Compute system head at a given flow rate.

    The system-curve model is:

        H_sys = H_static + K · Q²

    where K lumps all pipe-friction (Darcy-Weisbach) and fitting losses:

        K = Σ [f·L/D + Σ K_fitting] / (2g·A²)

    or equivalently supplied from a pipe-friction calculation.

    Parameters
    ----------
    H_static : float
        Static head (m). Sum of elevation difference + static pressure difference
        converted to metres. May be 0 (all-friction system). Must be >= 0.
    K : float
        System resistance coefficient (m·s²/m⁶ = s²/m⁵). Must be >= 0.
    Q : float
        Volume flow rate (m³/s). Must be >= 0.

    Returns
    -------
    dict
        ok          : True
        H_system_m  : system head at Q (m)
        H_static_m  : static head used (m)
        K           : resistance coefficient used
        Q_m3s       : flow rate used (m³/s)
        warnings    : []
    """
    e = _guard_nonneg("H_static", H_static)
    if e:
        return _err(e)
    e = _guard_nonneg("K", K)
    if e:
        return _err(e)
    e = _guard_nonneg("Q", Q)
    if e:
        return _err(e)

    H_sys = float(H_static) + float(K) * float(Q) ** 2
    return _ok(H_system_m=H_sys, H_static_m=float(H_static), K=float(K), Q_m3s=float(Q))


# ---------------------------------------------------------------------------
# 2. system_K_from_pipe
# ---------------------------------------------------------------------------

def system_K_from_pipe(
    f: float,
    L: float,
    D: float,
    A: float,
    *,
    K_fittings: float = 0.0,
) -> dict:
    """
    Compute system resistance coefficient K from Darcy-Weisbach pipe friction.

    K = (f·L/D + K_fittings) / (2·g·A²)

    Parameters
    ----------
    f : float
        Darcy friction factor (dimensionless). Must be > 0.
    L : float
        Pipe length (m). Must be > 0.
    D : float
        Internal pipe diameter (m). Must be > 0.
    A : float
        Pipe cross-sectional area (m²). Must be > 0.
        For a circular pipe: A = π·D²/4.
    K_fittings : float
        Sum of minor-loss coefficients for fittings (dimensionless, default 0).
        Must be >= 0.

    Returns
    -------
    dict
        ok       : True
        K        : system resistance coefficient (s²/m⁵)
        f_L_D    : friction term f·L/D
        warnings : []
    """
    for name, val in [("f", f), ("L", L), ("D", D), ("A", A)]:
        e = _guard_positive(name, val)
        if e:
            return _err(e)
    e = _guard_nonneg("K_fittings", K_fittings)
    if e:
        return _err(e)

    f_L_D = float(f) * float(L) / float(D)
    K = (f_L_D + float(K_fittings)) / (2.0 * _G * float(A) ** 2)
    return _ok(K=K, f_L_D=f_L_D)


# ---------------------------------------------------------------------------
# 3. pump_curve_from_points
# ---------------------------------------------------------------------------

def pump_curve_from_points(
    points: list[tuple[float, float]],
) -> dict:
    """
    Fit a quadratic pump curve H = a·Q² + b·Q + c from ≥ 3 catalogue points.

    The quadratic form is a least-squares fit through the supplied (Q, H)
    pairs.  For exactly 3 points a unique quadratic passes through all three.
    For > 3 points the fit is least-squares.

    Parameters
    ----------
    points : list of (Q, H) tuples
        At least 3 (flow m³/s, head m) catalogue pairs from the pump datasheet.
        Q values must be distinct.  H values must be > 0.

    Returns
    -------
    dict
        ok      : True
        a, b, c : quadratic coefficients  H = a·Q² + b·Q + c
        H_shutoff : head at Q=0 (= c)
        Q_max     : largest Q supplied (m³/s)
        warnings  : [] (warns if curve is non-monotone-decreasing)
    """
    if not isinstance(points, (list, tuple)) or len(points) < 3:
        return _err("points must contain at least 3 (Q, H) pairs")

    Qs, Hs = [], []
    for i, pt in enumerate(points):
        try:
            q, h = float(pt[0]), float(pt[1])
        except (TypeError, ValueError, IndexError):
            return _err(f"points[{i}] must be a (Q, H) pair of numbers")
        if q < 0:
            return _err(f"points[{i}]: Q={q} must be >= 0")
        if h < 0:
            return _err(f"points[{i}]: H={h} must be >= 0")
        Qs.append(q)
        Hs.append(h)

    # Check distinct Q values
    if len(set(Qs)) < len(Qs):
        return _err("All Q values in points must be distinct")

    # Least-squares quadratic fit via normal equations (pure Python, no numpy)
    # Design matrix columns: Q², Q, 1
    n = len(Qs)
    # Build sums for normal equations [A^T A] x = A^T b
    s00 = s01 = s02 = s03 = s04 = 0.0
    r0 = r1 = r2 = 0.0
    for q, h in zip(Qs, Hs):
        q2 = q * q
        q3 = q2 * q
        q4 = q3 * q
        s00 += q4
        s01 += q3
        s02 += q2
        s03 += q
        s04 += 1.0
        r0 += q2 * h
        r1 += q * h
        r2 += h

    # 3×3 symmetric system for [a, b, c]:
    # | s00 s01 s02 | |a|   |r0|
    # | s01 s02 s03 | |b| = |r1|
    # | s02 s03 s04 | |c|   |r2|
    A00, A01, A02 = s00, s01, s02
    A10, A11, A12 = s01, s02, s03
    A20, A21, A22 = s02, s03, s04

    # Gaussian elimination (3×3)
    mat = [
        [A00, A01, A02, r0],
        [A10, A11, A12, r1],
        [A20, A21, A22, r2],
    ]

    for col in range(3):
        # Find pivot
        pivot_row = max(range(col, 3), key=lambda r: abs(mat[r][col]))
        mat[col], mat[pivot_row] = mat[pivot_row], mat[col]
        piv = mat[col][col]
        if abs(piv) < 1e-30:
            return _err("Degenerate system: pump curve points are collinear or nearly so")
        for row in range(col + 1, 3):
            factor = mat[row][col] / piv
            for k in range(col, 4):
                mat[row][k] -= factor * mat[col][k]

    # Back-substitution
    coeffs = [0.0, 0.0, 0.0]
    for i in range(2, -1, -1):
        coeffs[i] = mat[i][3]
        for j in range(i + 1, 3):
            coeffs[i] -= mat[i][j] * coeffs[j]
        coeffs[i] /= mat[i][i]

    a, b, c = coeffs[0], coeffs[1], coeffs[2]
    H_shutoff = c  # H at Q = 0
    Q_max = max(Qs)

    warnings: list[str] = []
    # Check monotone: dH/dQ = 2a·Q + b should be <= 0 for all Q in [0, Q_max]
    # For a valid pump curve, head decreases with flow.
    # dH/dQ at Q=0 is b; at Q=Q_max is 2a*Q_max + b
    dH_at_zero = b
    dH_at_max = 2.0 * a * Q_max + b
    if dH_at_zero > 1e-9:
        warnings.append(
            "Pump curve slope is positive at Q=0: curve may not represent "
            "a typical centrifugal pump"
        )
    if H_shutoff < 0:
        warnings.append(
            f"Shut-off head H(Q=0) = {H_shutoff:.4f} m is negative; "
            "check catalogue points"
        )

    res = _ok(a=a, b=b, c=c, H_shutoff=H_shutoff, Q_max=Q_max)
    res["warnings"] = warnings
    return res


# ---------------------------------------------------------------------------
# 4. operating_point
# ---------------------------------------------------------------------------

def operating_point(
    a: float,
    b: float,
    c: float,
    H_static: float,
    K: float,
) -> dict:
    """
    Find the pump operating point: intersection of pump & system curves.

    Pump curve:   H_pump  = a·Q² + b·Q + c
    System curve: H_sys   = H_static + K·Q²

    Setting equal:

        a·Q² + b·Q + c = H_static + K·Q²
        (a − K)·Q² + b·Q + (c − H_static) = 0

    Solved as quadratic; the positive real root is the operating point.

    Parameters
    ----------
    a, b, c : float
        Quadratic pump-curve coefficients from pump_curve_from_points.
    H_static : float
        Static system head (m). Must be >= 0.
    K : float
        System resistance coefficient (s²/m⁵). Must be >= 0.

    Returns
    -------
    dict
        ok         : True
        Q_op_m3s   : operating flow (m³/s)
        H_op_m     : operating head (m)
        warnings   : [] (warns on negative flow, off-BEP, imaginary root)
    """
    e = _guard_nonneg("H_static", H_static)
    if e:
        return _err(e)
    e = _guard_nonneg("K", K)
    if e:
        return _err(e)

    A_coef = float(a) - float(K)
    B_coef = float(b)
    C_coef = float(c) - float(H_static)

    warnings: list[str] = []

    if abs(A_coef) < 1e-30:
        # Linear case: b·Q + (c - H_static) = 0
        if abs(B_coef) < 1e-30:
            return _err(
                "Degenerate operating-point: pump and system curves are parallel "
                "(no unique intersection)"
            )
        Q_op = -C_coef / B_coef
    else:
        discriminant = B_coef ** 2 - 4.0 * A_coef * C_coef
        if discriminant < 0:
            return _err(
                f"No real operating point: discriminant = {discriminant:.6g} < 0. "
                "System head may always exceed pump head."
            )
        sqrt_disc = math.sqrt(discriminant)
        Q1 = (-B_coef + sqrt_disc) / (2.0 * A_coef)
        Q2 = (-B_coef - sqrt_disc) / (2.0 * A_coef)

        # Prefer the positive root closest to zero (physical solution)
        candidates = [q for q in (Q1, Q2) if q >= -1e-12]
        if not candidates:
            warnings.append(
                "Both operating-point roots are negative — pump cannot meet "
                "system demand. Q_op set to 0."
            )
            Q_op = 0.0
        else:
            Q_op = min(candidates)

    if Q_op < -1e-12:
        warnings.append(
            f"Operating flow Q = {Q_op:.6g} m³/s is negative; "
            "system head exceeds pump shut-off head"
        )
        Q_op = max(Q_op, 0.0)

    H_op = float(a) * Q_op ** 2 + float(b) * Q_op + float(c)

    if H_op < 0:
        warnings.append(
            f"Operating head H = {H_op:.4f} m is negative; check inputs"
        )

    res = _ok(Q_op_m3s=Q_op, H_op_m=H_op)
    res["warnings"] = warnings
    return res


# ---------------------------------------------------------------------------
# 5. hydraulic_power
# ---------------------------------------------------------------------------

def hydraulic_power(
    Q: float,
    H: float,
    rho: float,
    *,
    eta: float | None = None,
    P_shaft_W: float | None = None,
) -> dict:
    """
    Compute hydraulic power, brake power, and overall efficiency.

    P_hydraulic = ρ · g · Q · H          (useful fluid power, W)
    P_brake     = P_hydraulic / η         (shaft input power, W)
    η           = P_hydraulic / P_brake   (overall pump efficiency)

    Provide either eta OR P_shaft_W; the other is computed.  If neither is
    provided, only P_hydraulic is returned.

    Parameters
    ----------
    Q : float
        Volume flow rate (m³/s). Must be > 0.
    H : float
        Total dynamic head (m). Must be > 0.
    rho : float
        Fluid density (kg/m³). Must be > 0. Water ≈ 1000 kg/m³.
    eta : float, optional
        Overall pump efficiency (0 < η ≤ 1).
    P_shaft_W : float, optional
        Brake (shaft) power input (W). Must be > 0.

    Returns
    -------
    dict
        ok             : True
        P_hydraulic_W  : useful fluid power (W)
        P_brake_W      : shaft input power (W) — if determinable
        eta            : overall efficiency — if determinable
        warnings       : [] (warns if eta < 0.3 or > 0.95)
    """
    e = _guard_positive("Q", Q)
    if e:
        return _err(e)
    e = _guard_positive("H", H)
    if e:
        return _err(e)
    e = _guard_positive("rho", rho)
    if e:
        return _err(e)

    P_hyd = float(rho) * _G * float(Q) * float(H)
    warnings: list[str] = []

    res = _ok(P_hydraulic_W=P_hyd)

    if eta is not None and P_shaft_W is not None:
        return _err("Provide either eta or P_shaft_W, not both")

    if eta is not None:
        e = _guard_positive("eta", eta)
        if e:
            return _err(e)
        eta_val = float(eta)
        if eta_val > 1.0:
            return _err(f"eta={eta_val} must be <= 1.0")
        P_brake = P_hyd / eta_val
        res["P_brake_W"] = P_brake
        res["eta"] = eta_val
        if eta_val < 0.3:
            warnings.append(
                f"Pump efficiency eta={eta_val:.2%} is very low (< 30%); "
                "check operating point"
            )
        elif eta_val > 0.95:
            warnings.append(
                f"Pump efficiency eta={eta_val:.2%} is unusually high (> 95%); "
                "verify inputs"
            )
    elif P_shaft_W is not None:
        e = _guard_positive("P_shaft_W", P_shaft_W)
        if e:
            return _err(e)
        P_br = float(P_shaft_W)
        if P_br < P_hyd * 0.9999:
            return _err(
                f"P_shaft_W={P_br:.2f} W < P_hydraulic={P_hyd:.2f} W; "
                "shaft power must be >= hydraulic power (energy cannot be created)"
            )
        eta_val = P_hyd / P_br
        res["P_brake_W"] = P_br
        res["eta"] = eta_val
        if eta_val < 0.3:
            warnings.append(
                f"Pump efficiency eta={eta_val:.2%} is very low (< 30%); "
                "check operating point"
            )

    res["warnings"] = warnings
    return res


# ---------------------------------------------------------------------------
# 6. npsh_available
# ---------------------------------------------------------------------------

def npsh_available(
    P_atm_Pa: float,
    P_vapor_Pa: float,
    rho: float,
    z_suction_m: float,
    h_friction_m: float,
) -> dict:
    """
    Compute Net Positive Suction Head Available (NPSHa).

    NPSHa = (P_atm − P_vapor) / (ρ·g) − z_suction − h_friction

    where:
      P_atm       — absolute atmospheric (or inlet tank) pressure (Pa)
      P_vapor     — fluid vapour pressure at operating temperature (Pa)
      z_suction   — vertical distance from suction surface to pump centreline
                    (positive upwards, i.e. suction lift; negative for flooded
                    suction / pump below liquid level)
      h_friction  — friction head loss in suction piping (m); must be >= 0

    Parameters
    ----------
    P_atm_Pa : float
        Absolute pressure at suction source (Pa). Must be > 0.
        Standard atmospheric ≈ 101325 Pa.
    P_vapor_Pa : float
        Vapour pressure of the liquid at operating temperature (Pa). Must be >= 0.
        Water at 20°C ≈ 2338 Pa.
    rho : float
        Fluid density (kg/m³). Must be > 0.
    z_suction_m : float
        Suction lift (m). Positive = pump above liquid surface (suction lift).
        Negative = pump below liquid surface (flooded suction / positive head).
    h_friction_m : float
        Friction head loss in suction line (m). Must be >= 0.

    Returns
    -------
    dict
        ok          : True
        NPSHa_m     : net positive suction head available (m)
        P_margin_m  : (P_atm − P_vapor) / (ρ·g)  (absolute suction head, m)
        warnings    : [] (warns if NPSHa <= 0)
    """
    e = _guard_positive("P_atm_Pa", P_atm_Pa)
    if e:
        return _err(e)
    e = _guard_nonneg("P_vapor_Pa", P_vapor_Pa)
    if e:
        return _err(e)
    e = _guard_positive("rho", rho)
    if e:
        return _err(e)
    e = _guard_nonneg("h_friction_m", h_friction_m)
    if e:
        return _err(e)

    if float(P_vapor_Pa) >= float(P_atm_Pa):
        return _err(
            f"P_vapor_Pa={P_vapor_Pa} Pa must be < P_atm_Pa={P_atm_Pa} Pa"
        )

    P_margin = (float(P_atm_Pa) - float(P_vapor_Pa)) / (float(rho) * _G)
    NPSHa = P_margin - float(z_suction_m) - float(h_friction_m)

    warnings: list[str] = []
    if NPSHa <= 0:
        warnings.append(
            f"NPSHa = {NPSHa:.3f} m <= 0: cavitation is certain; "
            "reduce suction lift or friction losses"
        )

    res = _ok(NPSHa_m=NPSHa, P_margin_m=P_margin)
    res["warnings"] = warnings
    return res


# ---------------------------------------------------------------------------
# 7. npsh_check
# ---------------------------------------------------------------------------

def npsh_check(
    NPSHa_m: float,
    NPSHr_m: float,
    *,
    margin_m: float = 0.5,
) -> dict:
    """
    Check NPSHa against NPSHr with a safety margin.

    Cavitation is flagged (in warnings) when:

        NPSHa < NPSHr + margin_m

    Parameters
    ----------
    NPSHa_m : float
        NPSH available (m), from npsh_available().
    NPSHr_m : float
        NPSH required by the pump (m), from manufacturer data. Must be > 0.
    margin_m : float
        Cavitation safety margin (m). Default 0.5 m per HI standard.
        Must be >= 0.

    Returns
    -------
    dict
        ok                  : True
        cavitation_risk     : True if NPSHa < NPSHr + margin_m
        NPSHa_m             : as supplied
        NPSHr_m             : as supplied
        margin_m            : safety margin used
        NPSHa_minus_NPSHr   : NPSHa − NPSHr (m)
        warnings            : [] (warns if cavitation_risk)
    """
    e = _guard_positive("NPSHr_m", NPSHr_m)
    if e:
        return _err(e)
    e = _guard_nonneg("margin_m", margin_m)
    if e:
        return _err(e)

    NPSHa = float(NPSHa_m)
    NPSHr = float(NPSHr_m)
    margin = float(margin_m)

    cavitation_risk = NPSHa < NPSHr + margin
    diff = NPSHa - NPSHr

    warnings: list[str] = []
    if cavitation_risk:
        warnings.append(
            f"CAVITATION RISK: NPSHa={NPSHa:.3f} m < NPSHr+margin="
            f"{NPSHr + margin:.3f} m (margin={margin:.2f} m). "
            "Reduce suction lift, suction losses, or select a pump with "
            "lower NPSHr."
        )

    res = _ok(
        cavitation_risk=cavitation_risk,
        NPSHa_m=NPSHa,
        NPSHr_m=NPSHr,
        margin_m=margin,
        NPSHa_minus_NPSHr=diff,
    )
    res["warnings"] = warnings
    return res


# ---------------------------------------------------------------------------
# 8. affinity_speed
# ---------------------------------------------------------------------------

def affinity_speed(
    Q1: float,
    H1: float,
    P1: float,
    n1: float,
    n2: float,
) -> dict:
    """
    Apply pump affinity laws for a speed change (constant impeller diameter).

    Affinity laws (Fan/Pump Laws):
        Q₂ = Q₁ · (n₂/n₁)
        H₂ = H₁ · (n₂/n₁)²
        P₂ = P₁ · (n₂/n₁)³

    Parameters
    ----------
    Q1, H1, P1 : float
        Original operating point: flow (m³/s), head (m), power (W).
        All must be > 0.
    n1 : float
        Original speed (rpm). Must be > 0.
    n2 : float
        New speed (rpm). Must be > 0.

    Returns
    -------
    dict
        ok     : True
        Q2     : scaled flow (m³/s)
        H2     : scaled head (m)
        P2     : scaled power (W)
        ratio  : speed ratio n2/n1
        warnings: []
    """
    for name, val in [("Q1", Q1), ("H1", H1), ("P1", P1), ("n1", n1), ("n2", n2)]:
        e = _guard_positive(name, val)
        if e:
            return _err(e)

    ratio = float(n2) / float(n1)
    Q2 = float(Q1) * ratio
    H2 = float(H1) * ratio ** 2
    P2 = float(P1) * ratio ** 3

    warnings: list[str] = []
    if ratio < 0.5 or ratio > 2.0:
        warnings.append(
            f"Speed ratio n2/n1 = {ratio:.3f} is outside the typical "
            "affinity-law valid range (0.5–2.0); accuracy may degrade"
        )

    res = _ok(Q2=Q2, H2=H2, P2=P2, ratio=ratio)
    res["warnings"] = warnings
    return res


# ---------------------------------------------------------------------------
# 9. affinity_trim
# ---------------------------------------------------------------------------

def affinity_trim(
    Q1: float,
    H1: float,
    P1: float,
    D1: float,
    D2: float,
) -> dict:
    """
    Apply pump affinity laws for an impeller-trim (diameter) change.

    Trim affinity laws:
        Q₂ = Q₁ · (D₂/D₁)
        H₂ = H₁ · (D₂/D₁)²
        P₂ = P₁ · (D₂/D₁)³

    Parameters
    ----------
    Q1, H1, P1 : float
        Original operating point: flow (m³/s), head (m), power (W).
        All must be > 0.
    D1 : float
        Original impeller diameter (m). Must be > 0.
    D2 : float
        Trimmed impeller diameter (m). Must be > 0 and <= D1.

    Returns
    -------
    dict
        ok     : True
        Q2     : scaled flow (m³/s)
        H2     : scaled head (m)
        P2     : scaled power (W)
        ratio  : diameter ratio D2/D1
        warnings: []
    """
    for name, val in [("Q1", Q1), ("H1", H1), ("P1", P1), ("D1", D1), ("D2", D2)]:
        e = _guard_positive(name, val)
        if e:
            return _err(e)

    ratio = float(D2) / float(D1)
    warnings: list[str] = []

    if ratio > 1.0 + 1e-9:
        warnings.append(
            f"D2/D1 = {ratio:.4f} > 1.0; trimming increases diameter which "
            "is not physically possible. Results are extrapolated."
        )
    if ratio < 0.7:
        warnings.append(
            f"Trim ratio D2/D1 = {ratio:.3f} < 0.7; affinity-law accuracy "
            "degrades below ~70% trim (use manufacturer trim curves)"
        )

    Q2 = float(Q1) * ratio
    H2 = float(H1) * ratio ** 2
    P2 = float(P1) * ratio ** 3

    res = _ok(Q2=Q2, H2=H2, P2=P2, ratio=ratio)
    res["warnings"] = warnings
    return res


# ---------------------------------------------------------------------------
# 10. pumps_in_series
# ---------------------------------------------------------------------------

def pumps_in_series(
    curves: list[tuple[float, float, float]],
    Q_eval: float,
) -> dict:
    """
    Compute combined head of pumps in series at a given flow rate.

    For pumps in series, the combined head at any Q is the sum of individual
    pump heads at that Q:

        H_combined(Q) = Σ H_i(Q)   where H_i(Q) = a_i·Q² + b_i·Q + c_i

    Parameters
    ----------
    curves : list of (a, b, c) tuples
        Quadratic coefficients for each pump (from pump_curve_from_points).
        At least 1 pump required.
    Q_eval : float
        Flow rate at which to evaluate the combined head (m³/s). Must be >= 0.

    Returns
    -------
    dict
        ok               : True
        H_combined_m     : combined head at Q_eval (m)
        H_individual_m   : list of individual pump heads at Q_eval (m)
        n_pumps          : number of pumps
        Q_eval_m3s       : flow evaluated at (m³/s)
        warnings         : [] (warns if any individual pump head < 0)
    """
    if not isinstance(curves, (list, tuple)) or len(curves) < 1:
        return _err("curves must contain at least 1 (a, b, c) pump-curve triple")

    e = _guard_nonneg("Q_eval", Q_eval)
    if e:
        return _err(e)

    Q = float(Q_eval)
    warnings: list[str] = []
    H_individual: list[float] = []

    for i, curve in enumerate(curves):
        try:
            a, b, c = float(curve[0]), float(curve[1]), float(curve[2])
        except (TypeError, ValueError, IndexError):
            return _err(f"curves[{i}] must be a (a, b, c) triple of numbers")
        h = a * Q ** 2 + b * Q + c
        if h < 0:
            warnings.append(
                f"Pump {i+1} head H={h:.3f} m at Q={Q:.6g} m³/s is negative; "
                "may be beyond pump's operating range"
            )
        H_individual.append(h)

    H_combined = sum(H_individual)

    res = _ok(
        H_combined_m=H_combined,
        H_individual_m=H_individual,
        n_pumps=len(curves),
        Q_eval_m3s=Q,
    )
    res["warnings"] = warnings
    return res


# ---------------------------------------------------------------------------
# 11. pumps_in_parallel
# ---------------------------------------------------------------------------

def pumps_in_parallel(
    curves: list[tuple[float, float, float]],
    H_eval: float,
) -> dict:
    """
    Compute combined flow of pumps in parallel at a given head.

    For pumps in parallel, each pump operates at the same head H.  The combined
    flow is the sum of individual pump flows at that head.

    For each pump, solve a·Q² + b·Q + (c − H) = 0 for Q (positive root).

    Parameters
    ----------
    curves : list of (a, b, c) tuples
        Quadratic coefficients for each pump. At least 1 pump required.
    H_eval : float
        Common head at which to evaluate individual flows (m). Must be >= 0.

    Returns
    -------
    dict
        ok               : True
        Q_combined_m3s   : combined flow at H_eval (m³/s)
        Q_individual_m3s : list of individual pump flows at H_eval (m³/s)
        n_pumps          : number of pumps
        H_eval_m         : head evaluated at (m)
        warnings         : []
    """
    if not isinstance(curves, (list, tuple)) or len(curves) < 1:
        return _err("curves must contain at least 1 (a, b, c) pump-curve triple")

    e = _guard_nonneg("H_eval", H_eval)
    if e:
        return _err(e)

    H = float(H_eval)
    warnings: list[str] = []
    Q_individual: list[float] = []

    for i, curve in enumerate(curves):
        try:
            a, b, c = float(curve[0]), float(curve[1]), float(curve[2])
        except (TypeError, ValueError, IndexError):
            return _err(f"curves[{i}] must be a (a, b, c) triple of numbers")

        # Solve a·Q² + b·Q + (c − H) = 0
        C_coef = c - H
        if abs(a) < 1e-30:
            # Linear: b·Q + C_coef = 0
            if abs(b) < 1e-30:
                warnings.append(
                    f"Pump {i+1}: degenerate curve (a=b=0); using Q=0"
                )
                Q_individual.append(0.0)
                continue
            Q_i = -C_coef / b
        else:
            disc = b ** 2 - 4.0 * a * C_coef
            if disc < 0:
                warnings.append(
                    f"Pump {i+1} cannot deliver H={H:.2f} m "
                    f"(max head = {c:.2f} m at Q=0); using Q=0"
                )
                Q_individual.append(0.0)
                continue
            sqrt_disc = math.sqrt(disc)
            Q_pos = (-b + sqrt_disc) / (2.0 * a)
            Q_neg = (-b - sqrt_disc) / (2.0 * a)
            candidates = [q for q in (Q_pos, Q_neg) if q >= -1e-12]
            Q_i = min(candidates) if candidates else 0.0

        if Q_i < 0:
            warnings.append(
                f"Pump {i+1}: computed flow Q={Q_i:.6g} m³/s is negative; "
                "using 0"
            )
            Q_i = 0.0

        Q_individual.append(Q_i)

    Q_combined = sum(Q_individual)

    res = _ok(
        Q_combined_m3s=Q_combined,
        Q_individual_m3s=Q_individual,
        n_pumps=len(curves),
        H_eval_m=H,
    )
    res["warnings"] = warnings
    return res


# ---------------------------------------------------------------------------
# 12. specific_speed
# ---------------------------------------------------------------------------

# Dimensionless specific-speed bands per White, "Fluid Mechanics", 8th ed.,
# §11.4 / Fig. 11.20 (Ns* = ω·√Q / (g·H)^(3/4), SI, dimensionless):
#   Ns* ≲ 0.75   radial / centrifugal
#   0.75–1.5     mixed-flow (Francis)
#   ≳ 1.5        axial-flow / propeller (efficient axial pumps Ns* ≈ 2.2–5)
_IMPELLER_GUIDANCE: list[tuple[tuple[float, float], str, str]] = [
    # (Ns_min, Ns_max), impeller_type, guidance
    ((0.0,    0.20),  "radial (low-Ns)",
     "High head, low flow. Radial/centrifugal impeller. Risk of instability "
     "and poor efficiency at very low Ns (<0.2). Consider positive-"
     "displacement pump."),
    ((0.20,   0.75),  "radial",
     "Standard centrifugal radial impeller. Best efficiency range for "
     "most industrial applications (White Fig. 11.20)."),
    ((0.75,   1.5),   "mixed-flow",
     "Mixed-flow (Francis) impeller. Moderate head, moderate-to-high flow."),
    ((1.5,  100.0),   "axial-flow",
     "Low head, very high flow. Axial or propeller impeller (fan-like). "
     "Use propeller pump / axial-flow pump."),
]


def specific_speed(
    Q: float,
    H: float,
    n: float,
) -> dict:
    """
    Compute the dimensionless specific speed Ns and recommend impeller type.

    True dimensionless specific speed (shape factor), White "Fluid
    Mechanics", 8th ed., Eq. 11.30b:

        Ns* = ω · √Q / (g · H)^(3/4)

    where ω (rad/s), Q (m³/s), H (m), g = 9.81 m/s².  This quantity is
    genuinely dimensionless (the (g·H)^(3/4) group has units of velocity
    to the 3/2 power, cancelling ω·√Q).  An earlier implementation omitted
    the g term, producing a *dimensional* number ~5.7× larger that did not
    match White's standard impeller bands — that defect is corrected here.

    Note: many references quote n in rpm; this function accepts rpm and
    converts internally:  ω = n_rpm × 2π/60.

    Impeller-type guidance — White Fig. 11.20 dimensionless Ns* bands:
      0.0  – 0.20  radial (low-Ns centrifugal; poor efficiency)
      0.20 – 0.75  radial (standard centrifugal)
      0.75 – 1.5   mixed-flow (Francis)
      1.5+         axial-flow / propeller

    For convenience the dimensional form n_rpm·√Q / H^(3/4) (rad-based, no g)
    is also returned as ``Ns_dimensional`` and the US customary form
    (gpm, ft, rpm) as ``Nss_us_customary``.

    Parameters
    ----------
    Q : float
        Best-efficiency-point (BEP) flow rate (m³/s). Must be > 0.
    H : float
        BEP head (m). Must be > 0.
    n : float
        Rotational speed (rpm). Must be > 0.

    Returns
    -------
    dict
        ok             : True
        Ns             : dimensionless specific speed
        impeller_type  : recommended impeller type string
        guidance       : design guidance note
        n_rpm          : speed used (rpm)
        n_rad_s        : speed used (rad/s)
        warnings       : []
    """
    e = _guard_positive("Q", Q)
    if e:
        return _err(e)
    e = _guard_positive("H", H)
    if e:
        return _err(e)
    e = _guard_positive("n", n)
    if e:
        return _err(e)

    omega = float(n) * 2.0 * math.pi / 60.0  # rad/s
    Qf = float(Q)
    Hf = float(H)

    # True dimensionless specific speed (White Eq. 11.30b): Ns* = ω√Q/(gH)^¾
    Ns = omega * math.sqrt(Qf) / (_G * Hf) ** 0.75
    # Legacy dimensional form retained for transparency / back-compat.
    Ns_dimensional = omega * math.sqrt(Qf) / Hf ** 0.75
    # US customary specific speed Nss = n(rpm)·√(Q[gpm]) / H[ft]^¾
    Q_gpm = Qf * 15850.323
    H_ft = Hf / 0.3048
    Nss_us = float(n) * math.sqrt(Q_gpm) / H_ft ** 0.75

    impeller_type = "unknown"
    guidance = ""
    for (ns_min, ns_max), imp_type, guide in _IMPELLER_GUIDANCE:
        if Ns <= ns_max:
            impeller_type = imp_type
            guidance = guide
            break

    warnings: list[str] = []
    if Ns < 0.20:
        warnings.append(
            f"Ns* = {Ns:.4f} is very low; a positive-displacement pump may be "
            "more appropriate than a centrifugal pump (White §11.4)"
        )

    res = _ok(
        Ns=Ns,
        Ns_dimensional=Ns_dimensional,
        Nss_us_customary=Nss_us,
        impeller_type=impeller_type,
        guidance=guidance,
        n_rpm=float(n),
        n_rad_s=omega,
    )
    res["warnings"] = warnings
    return res


# ---------------------------------------------------------------------------
# 13. minimum_flow_note
# ---------------------------------------------------------------------------

def minimum_flow_note(
    Q_op: float,
    Q_bep: float,
    *,
    min_fraction: float = 0.25,
) -> dict:
    """
    Check whether the operating flow is above the minimum continuous stable flow.

    The typical minimum continuous stable flow (MCSF) for a centrifugal pump
    is approximately 25% of the BEP flow (Kaplan §2.4, HI 9.6.4).

    Parameters
    ----------
    Q_op : float
        Operating flow rate (m³/s). Must be >= 0.
    Q_bep : float
        Best efficiency point (BEP) flow rate (m³/s). Must be > 0.
    min_fraction : float
        Minimum-flow fraction of Q_bep (default 0.25 = 25%).
        Must be in (0, 1).

    Returns
    -------
    dict
        ok               : True
        Q_op_m3s         : operating flow (m³/s)
        Q_bep_m3s        : BEP flow (m³/s)
        Q_min_m3s        : minimum recommended flow (m³/s)
        Q_fraction       : Q_op / Q_bep
        below_min_flow   : True if Q_op < Q_min
        warnings         : [] (warns if below_min_flow)
    """
    e = _guard_nonneg("Q_op", Q_op)
    if e:
        return _err(e)
    e = _guard_positive("Q_bep", Q_bep)
    if e:
        return _err(e)

    if not (0 < float(min_fraction) < 1):
        return _err(f"min_fraction={min_fraction} must be in (0, 1)")

    Q_min = float(Q_bep) * float(min_fraction)
    Q_frac = float(Q_op) / float(Q_bep)
    below_min = float(Q_op) < Q_min

    warnings: list[str] = []
    if below_min:
        warnings.append(
            f"Operating flow Q={Q_op:.6g} m³/s is below the minimum "
            f"recommended flow Q_min={Q_min:.6g} m³/s "
            f"({min_fraction:.0%} of BEP={Q_bep:.6g} m³/s). "
            "Risk of recirculation, vibration, and reduced bearing life. "
            "Install a bypass or recirculation line."
        )
    elif Q_frac > 1.2:
        warnings.append(
            f"Operating flow Q={Q_op:.6g} m³/s is above 120% of BEP "
            f"({Q_bep:.6g} m³/s). Pump may be operating beyond its curve; "
            "risk of cavitation and overloading motor."
        )

    res = _ok(
        Q_op_m3s=float(Q_op),
        Q_bep_m3s=float(Q_bep),
        Q_min_m3s=Q_min,
        Q_fraction=Q_frac,
        below_min_flow=below_min,
    )
    res["warnings"] = warnings
    return res
