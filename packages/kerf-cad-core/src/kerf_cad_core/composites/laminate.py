"""
kerf_cad_core.composites.laminate — Classical Lamination Theory (CLT).

Implements pure-Python (math only, no numpy) CLT analysis for composite
laminates.  All matrix operations use plain Python lists.

Public functions
----------------
reduced_stiffness(E1, E2, nu12, G12)
    Lamina reduced stiffness matrix Q (3×3, Voigt notation: 11, 22, 12).

transform_Q(Q, theta_deg)
    Transformed reduced stiffness Q̄(θ) for a ply at angle θ (degrees).

abd_matrix(plies)
    Assemble the 6×6 ABD matrix for a stacking sequence.
    plies: list of dicts with keys E1, E2, nu12, G12, thickness, angle_deg.

laminate_response(abd, N_M)
    Solve ABD × [ε0, κ] = [N, M] for mid-plane strains and curvatures
    using pure-Python Gaussian elimination (no numpy).

failure_indices(stress_global, stress_material, strengths, criteria)
    Per-ply failure indices for max-stress, max-strain, Tsai-Wu, Tsai-Hill.

laminate_engineering_moduli(abd, total_thickness)
    Effective laminate Ex, Ey, Gxy, nu_xy from the A matrix.

first_ply_failure_load(plies, N_M_unit, strengths_list, criteria)
    Scale factor λ for first-ply-failure under proportional loading.

Notes on CTE / hygroscopic effects
------------------------------------
This module does NOT compute thermally- or moisture-induced loads (N_T, N_H).
Those require α (CTE) and β (CME) fields per ply and a ΔT / ΔM input.
Add them externally: N_applied = N_mechanical - N_thermal - N_hygro, then
pass the combined load vector to laminate_response().

References
----------
Jones, R.M. "Mechanics of Composite Materials", 2nd ed. (1999)
Gibson, R.F. "Principles of Composite Material Mechanics", 4th ed. (2016)
Reddy, J.N. "Mechanics of Laminated Composite Plates", 2nd ed. (2004)

Units
-----
Stiffness / moduli : Pa (Pascals)
Thickness          : m  (metres)
Angles             : degrees
Forces per width   : N/m  (ABD N outputs)
Moments per width  : N·m/m = N (ABD M outputs)

Author: imranparuk
"""

from __future__ import annotations

import math
import warnings
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


# ---------------------------------------------------------------------------
# 3×3 matrix helpers (stored as flat list, row-major)
# M[i][j] = flat[i*3 + j]
# ---------------------------------------------------------------------------

def _mat3_zero() -> list[float]:
    return [0.0] * 9


def _mat3_add(A: list[float], B: list[float]) -> list[float]:
    return [a + b for a, b in zip(A, B)]


def _mat3_scale(A: list[float], s: float) -> list[float]:
    return [a * s for a in A]


def _mat3_get(A: list[float], i: int, j: int) -> float:
    return A[i * 3 + j]


def _mat3_set(A: list[float], i: int, j: int, v: float) -> None:
    A[i * 3 + j] = v


# ---------------------------------------------------------------------------
# 6×6 matrix helpers (stored as list[list[float]])
# ---------------------------------------------------------------------------

def _mat6_zero() -> list[list[float]]:
    return [[0.0] * 6 for _ in range(6)]


def _mat6_copy(A: list[list[float]]) -> list[list[float]]:
    return [[v for v in row] for row in A]


# ---------------------------------------------------------------------------
# 6×6 Gaussian elimination with partial pivoting
# Solves A x = b where A is 6×6, b is length-6 vector.
# Returns x as list[float], or raises ValueError if singular.
# ---------------------------------------------------------------------------

def _gauss_solve(A: list[list[float]], b: list[float]) -> list[float]:
    n = 6
    # Augmented matrix [A | b]
    aug = [A[i][:] + [b[i]] for i in range(n)]

    for col in range(n):
        # Partial pivot
        max_row = col
        max_val = abs(aug[col][col])
        for row in range(col + 1, n):
            if abs(aug[row][col]) > max_val:
                max_val = abs(aug[row][col])
                max_row = row
        if max_val < 1e-30:
            raise ValueError("ABD matrix is singular or near-singular")
        aug[col], aug[max_row] = aug[max_row], aug[col]

        pivot = aug[col][col]
        for row in range(col + 1, n):
            factor = aug[row][col] / pivot
            for k in range(col, n + 1):
                aug[row][k] -= factor * aug[col][k]

    # Back substitution
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = aug[i][n]
        for j in range(i + 1, n):
            x[i] -= aug[i][j] * x[j]
        x[i] /= aug[i][i]
    return x


# ---------------------------------------------------------------------------
# 1. reduced_stiffness
# ---------------------------------------------------------------------------

def reduced_stiffness(
    E1: float,
    E2: float,
    nu12: float,
    G12: float,
) -> dict:
    """
    Compute the lamina reduced stiffness matrix Q for a unidirectional ply.

    Classical Lamination Theory (Jones §2.4) uses the plane-stress reduced
    stiffness, which eliminates the out-of-plane normal stress σ3=0:

        Q11 = E1  / (1 - ν12·ν21)
        Q22 = E2  / (1 - ν12·ν21)
        Q12 = ν12·E2 / (1 - ν12·ν21)   [= ν21·E1 / denom]
        Q66 = G12

    where ν21 = ν12 · E2/E1  (reciprocal relation).

    Parameters
    ----------
    E1   : Young's modulus in fibre direction (Pa). Must be > 0.
    E2   : Young's modulus transverse to fibre (Pa). Must be > 0.
    nu12 : Major Poisson ratio. Must satisfy 0 < ν12 < sqrt(E1/E2).
    G12  : In-plane shear modulus (Pa). Must be > 0.

    Returns
    -------
    dict
        ok   : True
        Q    : 3×3 stiffness matrix as flat list (row-major), indices
               [Q11, Q12, 0, Q12, Q22, 0, 0, 0, Q66]
        Q11, Q12, Q22, Q66 : individual components (Pa)
        nu21 : minor Poisson ratio
    """
    for name, val in (("E1", E1), ("E2", E2), ("G12", G12)):
        err = _guard_positive(name, val)
        if err:
            return _err(err)

    err = _guard_positive("nu12", nu12)
    if err:
        return _err(err)

    E1_, E2_, nu12_, G12_ = float(E1), float(E2), float(nu12), float(G12)

    nu21 = nu12_ * E2_ / E1_
    denom = 1.0 - nu12_ * nu21

    if denom <= 0.0:
        return _err(
            f"nu12={nu12_} violates stability criterion; "
            f"need nu12 < sqrt(E1/E2)={math.sqrt(E1_/E2_):.4f}"
        )

    Q11 = E1_ / denom
    Q22 = E2_ / denom
    Q12 = nu12_ * E2_ / denom
    Q66 = G12_

    Q_flat = [
        Q11,  Q12,  0.0,
        Q12,  Q22,  0.0,
        0.0,  0.0,  Q66,
    ]

    return {
        "ok": True,
        "Q": Q_flat,
        "Q11": Q11,
        "Q12": Q12,
        "Q22": Q22,
        "Q66": Q66,
        "nu21": nu21,
        "denom": denom,
    }


# ---------------------------------------------------------------------------
# 2. transform_Q
# ---------------------------------------------------------------------------

def transform_Q(Q_or_result: Any, theta_deg: float) -> dict:
    """
    Transform the reduced stiffness Q to global coordinates for ply at angle θ.

    Uses the standard CLT transformation (Jones §2.8):

        Q̄ = T⁻¹ Q T⁻ᵀ

    where T is the stress transformation matrix.

    Parameters
    ----------
    Q_or_result : list[float] (3×3 flat) or dict returned by reduced_stiffness()
    theta_deg   : ply orientation in degrees (CCW from x-axis)

    Returns
    -------
    dict
        ok    : True
        Q_bar : 3×3 transformed stiffness as flat list
        Q_bar_11, Q_bar_12, Q_bar_16, Q_bar_22, Q_bar_26, Q_bar_66 : components
        theta_deg : angle used
    """
    if isinstance(Q_or_result, dict):
        if not Q_or_result.get("ok"):
            return _err("Q_or_result is an error dict")
        Q_flat = Q_or_result["Q"]
    elif isinstance(Q_or_result, list) and len(Q_or_result) == 9:
        Q_flat = [float(v) for v in Q_or_result]
    else:
        return _err("Q_or_result must be a 9-element flat list or a reduced_stiffness() dict")

    theta = math.radians(float(theta_deg))
    c = math.cos(theta)
    s = math.sin(theta)
    c2 = c * c
    s2 = s * s
    cs = c * s
    c4 = c2 * c2
    s4 = s2 * s2
    c2s2 = c2 * s2

    Q11 = Q_flat[0]
    Q12 = Q_flat[1]
    Q22 = Q_flat[4]
    Q66 = Q_flat[8]

    # Jones eq. 2.81 (plane-stress, no Q16/Q26 in principal axes)
    Qb11 = Q11 * c4 + 2.0 * (Q12 + 2.0 * Q66) * c2s2 + Q22 * s4
    Qb12 = (Q11 + Q22 - 4.0 * Q66) * c2s2 + Q12 * (c4 + s4)
    Qb22 = Q11 * s4 + 2.0 * (Q12 + 2.0 * Q66) * c2s2 + Q22 * c4
    Qb16 = (Q11 - Q12 - 2.0 * Q66) * c2 * cs - (Q22 - Q12 - 2.0 * Q66) * s2 * cs
    Qb26 = (Q11 - Q12 - 2.0 * Q66) * s2 * cs - (Q22 - Q12 - 2.0 * Q66) * c2 * cs
    Qb66 = (Q11 + Q22 - 2.0 * Q12 - 2.0 * Q66) * c2s2 + Q66 * (c4 + s4)

    Q_bar = [
        Qb11, Qb12, Qb16,
        Qb12, Qb22, Qb26,
        Qb16, Qb26, Qb66,
    ]

    return {
        "ok": True,
        "Q_bar": Q_bar,
        "Q_bar_11": Qb11,
        "Q_bar_12": Qb12,
        "Q_bar_16": Qb16,
        "Q_bar_22": Qb22,
        "Q_bar_26": Qb26,
        "Q_bar_66": Qb66,
        "theta_deg": float(theta_deg),
    }


# ---------------------------------------------------------------------------
# 3. abd_matrix
# ---------------------------------------------------------------------------

def abd_matrix(plies: list[dict]) -> dict:
    """
    Assemble the 6×6 ABD matrix for a composite laminate stacking sequence.

    The laminate is numbered from bottom (k=1) to top (k=N).
    The mid-plane is at z=0; z_k denotes the top surface of ply k.

    A_ij = Σ Q̄_ij^(k) (z_k  - z_{k-1})           [extensional stiffness]
    B_ij = Σ Q̄_ij^(k) (z_k² - z_{k-1}²) / 2      [coupling stiffness]
    D_ij = Σ Q̄_ij^(k) (z_k³ - z_{k-1}³) / 3      [bending stiffness]

    Parameters
    ----------
    plies : list of dicts, each with:
        E1          : float — fibre-direction modulus (Pa)
        E2          : float — transverse modulus (Pa)
        nu12        : float — major Poisson ratio
        G12         : float — shear modulus (Pa)
        thickness   : float — ply thickness (m), > 0
        angle_deg   : float — fibre angle (deg), positive CCW from x-axis

    Returns
    -------
    dict
        ok             : True
        A              : 3×3 extensional stiffness (flat list, Pa·m)
        B              : 3×3 coupling stiffness (flat list, Pa)
        D              : 3×3 bending stiffness (flat list, Pa·m³)
        ABD            : 6×6 full ABD matrix (list of 6 lists of 6 floats)
        z_coords       : list of ply interface z-coordinates (m)
        total_thickness: total laminate thickness (m)
        n_plies        : number of plies
        is_symmetric   : bool — B matrix all-zero within tolerance
        is_balanced    : bool — A16=A26≈0 within tolerance
    """
    if not plies:
        return _err("plies list is empty")

    required_keys = ("E1", "E2", "nu12", "G12", "thickness", "angle_deg")
    for k, ply in enumerate(plies):
        for key in required_keys:
            if key not in ply:
                return _err(f"ply[{k}] missing key '{key}'")

    # Compute z-coordinates (mid-plane at z=0)
    thicknesses = []
    for k, ply in enumerate(plies):
        err = _guard_positive("thickness", ply["thickness"])
        if err:
            return _err(f"ply[{k}]: {err}")
        thicknesses.append(float(ply["thickness"]))

    total_h = sum(thicknesses)
    z_bottom = -total_h / 2.0

    z_coords = [z_bottom]
    for t in thicknesses:
        z_coords.append(z_coords[-1] + t)

    # Initialise A, B, D as 3×3 flat lists
    A = _mat3_zero()
    B = _mat3_zero()
    D = _mat3_zero()

    for k, ply in enumerate(plies):
        # Compute reduced stiffness
        res_Q = reduced_stiffness(
            ply["E1"], ply["E2"], ply["nu12"], ply["G12"]
        )
        if not res_Q["ok"]:
            return _err(f"ply[{k}] reduced_stiffness error: {res_Q['reason']}")

        res_Qb = transform_Q(res_Q, ply["angle_deg"])
        if not res_Qb["ok"]:
            return _err(f"ply[{k}] transform_Q error: {res_Qb['reason']}")

        Qb = res_Qb["Q_bar"]  # flat 3×3

        z0 = z_coords[k]
        z1 = z_coords[k + 1]
        dz1 = z1 - z0
        dz2 = (z1 ** 2 - z0 ** 2) / 2.0
        dz3 = (z1 ** 3 - z0 ** 3) / 3.0

        for i in range(9):
            A[i] += Qb[i] * dz1
            B[i] += Qb[i] * dz2
            D[i] += Qb[i] * dz3

    # Assemble 6×6 ABD
    ABD = _mat6_zero()
    # Map 3×3 A, B, D indices into 6×6
    # ABD rows 0-2: [A | B], rows 3-5: [B | D]
    idx3 = [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2), (2, 0), (2, 1), (2, 2)]
    for flat_idx, (i, j) in enumerate(idx3):
        ABD[i][j] = A[flat_idx]
        ABD[i][j + 3] = B[flat_idx]
        ABD[i + 3][j] = B[flat_idx]
        ABD[i + 3][j + 3] = D[flat_idx]

    # Symmetric / balanced detection
    # Use the A-matrix scale as reference (B should be << A for symmetric laminates).
    tol_rel = 1e-6
    ref_A = max(abs(v) for v in A) or 1.0
    is_symmetric = all(abs(v) < tol_rel * ref_A * total_h for v in B)
    is_balanced = (
        abs(A[2]) < tol_rel * ref_A and   # A[0,2] = A16
        abs(A[5]) < tol_rel * ref_A       # A[1,2] = A26
    )

    if not is_symmetric:
        warnings.warn(
            "Laminate has non-zero B matrix (bending-extension coupling). "
            "B != 0 indicates a non-symmetric layup.",
            stacklevel=2,
        )

    return {
        "ok": True,
        "A": A,
        "B": B,
        "D": D,
        "ABD": ABD,
        "z_coords": z_coords,
        "total_thickness": total_h,
        "n_plies": len(plies),
        "is_symmetric": is_symmetric,
        "is_balanced": is_balanced,
    }


# ---------------------------------------------------------------------------
# 4. laminate_response
# ---------------------------------------------------------------------------

def laminate_response(
    abd_result: Any,
    N_M: list[float],
) -> dict:
    """
    Solve the 6×6 ABD system for mid-plane strains and curvatures.

    Given the resultant force and moment per unit width vector
    [Nx, Ny, Nxy, Mx, My, Mxy] (N/m and N, respectively), solve:

        [A B] [ε0]   [N]
        [B D] [κ ] = [M]

    using pure-Python Gaussian elimination with partial pivoting.

    Parameters
    ----------
    abd_result : dict returned by abd_matrix()
    N_M        : list of 6 floats [Nx, Ny, Nxy, Mx, My, Mxy]
                 Units: N/m for N components, N for M components (i.e. N·m/m)

    Returns
    -------
    dict
        ok              : True
        epsilon0        : mid-plane strains [eps_x, eps_y, gamma_xy] (dimensionless)
        kappa           : curvatures [kappa_x, kappa_y, kappa_xy] (1/m)
        response_vector : full 6-component solution [ε0, κ]
        N_M             : applied load/moment vector used
        ply_strains     : None (computed in laminate_stress if desired)
    """
    if not isinstance(abd_result, dict) or not abd_result.get("ok"):
        return _err("abd_result must be a successful abd_matrix() dict")

    if not isinstance(N_M, (list, tuple)) or len(N_M) != 6:
        return _err("N_M must be a list of 6 floats [Nx, Ny, Nxy, Mx, My, Mxy]")

    ABD = abd_result["ABD"]
    b = [float(v) for v in N_M]

    try:
        x = _gauss_solve(_mat6_copy(ABD), b)
    except ValueError as exc:
        return _err(f"ABD solve failed: {exc}")

    eps0 = x[:3]
    kappa = x[3:]

    return {
        "ok": True,
        "epsilon0": eps0,
        "kappa": kappa,
        "response_vector": x,
        "N_M": b,
    }


# ---------------------------------------------------------------------------
# 5. per-ply stress/strain in global and material axes
# ---------------------------------------------------------------------------

def _ply_strains_global(eps0: list[float], kappa: list[float], z_mid: float) -> list[float]:
    """Strain at the mid-plane of a ply at z_mid (global axes)."""
    return [
        eps0[0] + z_mid * kappa[0],
        eps0[1] + z_mid * kappa[1],
        eps0[2] + z_mid * kappa[2],
    ]


def _global_to_material_strain(eps_global: list[float], theta_deg: float) -> list[float]:
    """Transform global strain to material (1-2) axes."""
    theta = math.radians(theta_deg)
    c = math.cos(theta)
    s = math.sin(theta)
    c2, s2, cs = c * c, s * s, c * s
    ex, ey, gxy = eps_global
    # [e1, e2, g12] using standard strain transformation
    # Note: engineering shear strain γ = 2ε_12 convention used throughout
    e1  =  c2 * ex + s2 * ey + cs * gxy
    e2  =  s2 * ex + c2 * ey - cs * gxy
    g12 = -2.0 * cs * ex + 2.0 * cs * ey + (c2 - s2) * gxy
    return [e1, e2, g12]


def _material_strain_to_stress(eps_mat: list[float], Q_flat: list[float]) -> list[float]:
    """Compute material-axis stress from material-axis strain via Q."""
    e1, e2, g12 = eps_mat
    Q11, Q12 = Q_flat[0], Q_flat[1]
    Q22 = Q_flat[4]
    Q66 = Q_flat[8]
    s1  = Q11 * e1 + Q12 * e2
    s2  = Q12 * e1 + Q22 * e2
    s12 = Q66 * g12
    return [s1, s2, s12]


def _global_stress_from_material(stress_mat: list[float], theta_deg: float) -> list[float]:
    """Transform material-axis stress back to global (x-y) axes."""
    theta = math.radians(theta_deg)
    c = math.cos(theta)
    s = math.sin(theta)
    c2, s2, cs = c * c, s * s, c * s
    s1, s2_, s12 = stress_mat
    sx  =  c2 * s1 + s2 * s2_ - 2.0 * cs * s12
    sy  =  s2 * s1 + c2 * s2_ + 2.0 * cs * s12
    sxy =  cs * s1 - cs * s2_ + (c2 - s2) * s12
    return [sx, sy, sxy]


def ply_stresses_strains(
    abd_result: dict,
    response: dict,
    plies: list[dict],
) -> dict:
    """
    Compute per-ply stress and strain in both global and material axes.

    Parameters
    ----------
    abd_result : dict returned by abd_matrix()
    response   : dict returned by laminate_response()
    plies      : same ply list passed to abd_matrix()

    Returns
    -------
    dict
        ok   : True
        plies : list of dicts, one per ply:
            z_mid           : z-coordinate of ply midplane (m)
            strain_global   : [ex, ey, gxy] global
            strain_material : [e1, e2, g12] material
            stress_material : [s1, s2, s12] material (Pa)
            stress_global   : [sx, sy, sxy] global (Pa)
    """
    if not abd_result.get("ok"):
        return _err("abd_result must be ok")
    if not response.get("ok"):
        return _err("response must be ok")

    z_coords = abd_result["z_coords"]
    eps0 = response["epsilon0"]
    kappa = response["kappa"]

    result_plies = []
    for k, ply in enumerate(plies):
        z_mid = (z_coords[k] + z_coords[k + 1]) / 2.0

        # Reduced stiffness (material axes)
        res_Q = reduced_stiffness(ply["E1"], ply["E2"], ply["nu12"], ply["G12"])
        Q_flat = res_Q["Q"]  # already validated

        eps_g = _ply_strains_global(eps0, kappa, z_mid)
        eps_m = _global_to_material_strain(eps_g, ply["angle_deg"])
        sig_m = _material_strain_to_stress(eps_m, Q_flat)
        sig_g = _global_stress_from_material(sig_m, ply["angle_deg"])

        result_plies.append({
            "z_mid": z_mid,
            "strain_global": eps_g,
            "strain_material": eps_m,
            "stress_material": sig_m,
            "stress_global": sig_g,
        })

    return {"ok": True, "plies": result_plies}


# ---------------------------------------------------------------------------
# 6. failure_indices
# ---------------------------------------------------------------------------

def failure_indices(
    stress_material: list[float],
    strain_material: list[float],
    strengths: dict,
    criteria: list[str] | None = None,
) -> dict:
    """
    Compute failure indices for a single ply.

    Failure occurs when the failure index F.I. >= 1.

    Parameters
    ----------
    stress_material : [σ1, σ2, τ12] in material axes (Pa)
    strain_material : [ε1, ε2, γ12] in material axes
    strengths : dict with keys:
        F1t : tensile strength in fibre direction (Pa, > 0)
        F1c : compressive strength in fibre direction (Pa, > 0, magnitude)
        F2t : tensile strength transverse (Pa, > 0)
        F2c : compressive strength transverse (Pa, > 0, magnitude)
        F12 : shear strength (Pa, > 0)
        Optional for max-strain:
        e1t, e1c, e2t, e2c, g12_allow — allowable strains
    criteria : list of strings from {'max-stress', 'max-strain', 'tsai-wu', 'tsai-hill'}
               Defaults to all four if not specified.

    Returns
    -------
    dict
        ok         : True
        failed     : True if any criterion indicates failure (F.I. >= 1)
        max_stress : {fi, failed, margin} — max-stress failure index (max of ratios)
        max_strain : {fi, failed, margin} — max-strain failure index (if strains given)
        tsai_wu    : {fi, failed, margin} — Tsai-Wu failure index
        tsai_hill  : {fi, failed, margin} — Tsai-Hill failure index
        criteria_used : list of criteria evaluated

    Notes on criteria
    -----------------
    max-stress  : F.I. = max(|σ1|/F1, |σ2|/F2, |τ12|/F12)
    max-strain  : F.I. = max(|ε1|/e1allow, ...)
    Tsai-Hill   : F.I.² = (σ1/F1)² - σ1σ2/F1² + (σ2/F2)² + (τ12/F12)²
                  where F1=F1t if σ1>0 else F1c, F2=F2t if σ2>0 else F2c.
    Tsai-Wu     : F.I. = F1·σ1 + F2·σ2 + F11·σ1² + F22·σ2² + 2F12·σ1σ2 + F66·τ12²
                  interaction term: F12* = -0.5/sqrt(F1t·F1c·F2t·F2c) (Tsai 1968)
                  failure when F.I. >= 1.
    """
    if criteria is None:
        criteria = ["max-stress", "max-strain", "tsai-wu", "tsai-hill"]

    s1, s2, s12 = [float(v) for v in stress_material]
    e1, e2, g12 = [float(v) for v in strain_material]

    req = ("F1t", "F1c", "F2t", "F2c", "F12")
    for k in req:
        if k not in strengths:
            return _err(f"strengths missing key '{k}'")

    F1t = float(strengths["F1t"])
    F1c = float(strengths["F1c"])
    F2t = float(strengths["F2t"])
    F2c = float(strengths["F2c"])
    F12 = float(strengths["F12"])

    results: dict = {"ok": True, "criteria_used": list(criteria)}
    any_failed = False

    # --- max-stress ---
    if "max-stress" in criteria:
        F1 = F1t if s1 >= 0 else F1c
        F2 = F2t if s2 >= 0 else F2c
        fi_vals = [abs(s1) / F1, abs(s2) / F2, abs(s12) / F12]
        fi_ms = max(fi_vals)
        failed_ms = fi_ms >= 1.0
        if failed_ms:
            warnings.warn(
                f"Ply failure: max-stress F.I. = {fi_ms:.4f} >= 1.0",
                stacklevel=2,
            )
        results["max_stress"] = {
            "fi": fi_ms,
            "failed": failed_ms,
            "margin": 1.0 / fi_ms - 1.0 if fi_ms > 0 else float("inf"),
            "component_fi": fi_vals,
        }
        any_failed = any_failed or failed_ms

    # --- max-strain ---
    if "max-strain" in criteria:
        has_strain_allows = all(
            k in strengths for k in ("e1t", "e1c", "e2t", "e2c", "g12_allow")
        )
        if has_strain_allows:
            e1t = float(strengths["e1t"])
            e1c = float(strengths["e1c"])
            e2t = float(strengths["e2t"])
            e2c = float(strengths["e2c"])
            g12a = float(strengths["g12_allow"])
            ea1 = e1t if e1 >= 0 else e1c
            ea2 = e2t if e2 >= 0 else e2c
            fi_vals_s = [abs(e1) / ea1, abs(e2) / ea2, abs(g12) / g12a]
            fi_strain = max(fi_vals_s)
            failed_strain = fi_strain >= 1.0
            if failed_strain:
                warnings.warn(
                    f"Ply failure: max-strain F.I. = {fi_strain:.4f} >= 1.0",
                    stacklevel=2,
                )
            results["max_strain"] = {
                "fi": fi_strain,
                "failed": failed_strain,
                "margin": 1.0 / fi_strain - 1.0 if fi_strain > 0 else float("inf"),
                "component_fi": fi_vals_s,
            }
            any_failed = any_failed or failed_strain
        else:
            results["max_strain"] = {
                "fi": None,
                "failed": False,
                "margin": None,
                "note": "strain allowables not provided; skipped",
            }

    # --- Tsai-Hill ---
    if "tsai-hill" in criteria:
        F1_th = F1t if s1 >= 0 else F1c
        F2_th = F2t if s2 >= 0 else F2c
        # F.I.² = (σ1/F1)² - σ1σ2/F1² + (σ2/F2)² + (τ12/F12)²
        fi2_th = (
            (s1 / F1_th) ** 2
            - (s1 * s2) / F1_th ** 2
            + (s2 / F2_th) ** 2
            + (s12 / F12) ** 2
        )
        fi_th = math.sqrt(abs(fi2_th)) * (1.0 if fi2_th >= 0 else -1.0)
        failed_th = fi2_th >= 1.0
        if failed_th:
            warnings.warn(
                f"Ply failure: Tsai-Hill F.I.² = {fi2_th:.4f} >= 1.0",
                stacklevel=2,
            )
        results["tsai_hill"] = {
            "fi_squared": fi2_th,
            "fi": fi_th,
            "failed": failed_th,
            "margin": 1.0 / math.sqrt(max(fi2_th, 1e-30)) - 1.0 if fi2_th > 0 else float("inf"),
        }
        any_failed = any_failed or failed_th

    # --- Tsai-Wu ---
    if "tsai-wu" in criteria:
        # Strength tensors (Tsai & Wu, 1971)
        H1  =  1.0 / F1t - 1.0 / F1c
        H2  =  1.0 / F2t - 1.0 / F2c
        H11 =  1.0 / (F1t * F1c)
        H22 =  1.0 / (F2t * F2c)
        H66 =  1.0 / (F12 ** 2)
        # Interaction term per Tsai (1968): F12* = -0.5 / sqrt(F1t·F1c·F2t·F2c)
        H12 = -0.5 / math.sqrt(F1t * F1c * F2t * F2c)

        fi_tw = (
            H1 * s1
            + H2 * s2
            + H11 * s1 ** 2
            + H22 * s2 ** 2
            + 2.0 * H12 * s1 * s2
            + H66 * s12 ** 2
        )
        failed_tw = fi_tw >= 1.0
        if failed_tw:
            warnings.warn(
                f"Ply failure: Tsai-Wu F.I. = {fi_tw:.4f} >= 1.0",
                stacklevel=2,
            )
        results["tsai_wu"] = {
            "fi": fi_tw,
            "failed": failed_tw,
            "margin": 1.0 / fi_tw - 1.0 if fi_tw > 0 else float("inf"),
        }
        any_failed = any_failed or failed_tw

    results["failed"] = any_failed
    return results


# ---------------------------------------------------------------------------
# 7. laminate_engineering_moduli
# ---------------------------------------------------------------------------

def laminate_engineering_moduli(
    abd_result: dict,
) -> dict:
    """
    Effective laminate engineering moduli from the A matrix (membrane only).

    These are sometimes called "apparent" or "equivalent" in-plane moduli.
    They assume a uniform stress state through the thickness (membrane).

    For a fully anisotropic laminate the effective moduli are:

        Ex   = 1 / (h · a11)
        Ey   = 1 / (h · a22)
        Gxy  = 1 / (h · a66)
        nu_xy = -a12 / a11

    where [a] = [A]⁻¹ is the compliance matrix and h is total thickness.

    Parameters
    ----------
    abd_result : dict returned by abd_matrix()

    Returns
    -------
    dict
        ok     : True
        Ex     : effective x-direction Young's modulus (Pa)
        Ey     : effective y-direction Young's modulus (Pa)
        Gxy    : effective shear modulus (Pa)
        nu_xy  : effective Poisson ratio
        nu_yx  : minor Poisson ratio (nu_yx = nu_xy · Ex / Ey)
        a      : 3×3 A-compliance matrix (flat list)
    """
    if not isinstance(abd_result, dict) or not abd_result.get("ok"):
        return _err("abd_result must be a successful abd_matrix() dict")

    A = abd_result["A"]  # flat 3×3
    h = abd_result["total_thickness"]

    # Invert 3×3 A matrix (analytic / Gaussian)
    a11, a12, a13 = A[0], A[1], A[2]
    a21, a22, a23 = A[3], A[4], A[5]
    a31, a32, a33 = A[6], A[7], A[8]

    det = (
        a11 * (a22 * a33 - a23 * a32)
        - a12 * (a21 * a33 - a23 * a31)
        + a13 * (a21 * a32 - a22 * a31)
    )

    if abs(det) < 1e-60:
        return _err("A matrix is singular; cannot invert")

    inv_det = 1.0 / det
    # Cofactor matrix (transposed = adjugate)
    c11 =  (a22 * a33 - a23 * a32) * inv_det
    c12 = -(a12 * a33 - a13 * a32) * inv_det
    c13 =  (a12 * a23 - a13 * a22) * inv_det
    c21 = -(a21 * a33 - a23 * a31) * inv_det
    c22 =  (a11 * a33 - a13 * a31) * inv_det
    c23 = -(a11 * a23 - a13 * a21) * inv_det
    c31 =  (a21 * a32 - a22 * a31) * inv_det
    c32 = -(a11 * a32 - a12 * a31) * inv_det
    c33 =  (a11 * a22 - a12 * a21) * inv_det

    a_comp = [c11, c12, c13, c21, c22, c23, c31, c32, c33]

    # Compliance components
    aa11 = c11  # a[0,0]
    aa12 = c12  # a[0,1]
    aa22 = c22  # a[1,1]
    aa66 = c33  # a[2,2]

    if aa11 <= 0 or aa22 <= 0 or aa66 <= 0:
        return _err(
            "A-compliance diagonal non-positive; laminate may be degenerate"
        )

    Ex   = 1.0 / (h * aa11)
    Ey   = 1.0 / (h * aa22)
    Gxy  = 1.0 / (h * aa66)
    nu_xy = -aa12 / aa11
    nu_yx = nu_xy * Ex / Ey if Ey > 0 else 0.0

    return {
        "ok": True,
        "Ex": Ex,
        "Ey": Ey,
        "Gxy": Gxy,
        "nu_xy": nu_xy,
        "nu_yx": nu_yx,
        "a": a_comp,
    }


# ---------------------------------------------------------------------------
# 8. first_ply_failure_load
# ---------------------------------------------------------------------------

def first_ply_failure_load(
    plies: list[dict],
    N_M_unit: list[float],
    strengths_list: list[dict],
    criteria: list[str] | None = None,
) -> dict:
    """
    Compute the first-ply-failure (FPF) load scaling factor λ.

    The applied load vector N_M = λ · N_M_unit.  The function finds the
    smallest λ > 0 such that at least one ply reaches its failure criterion.

    Uses bisection search on λ ∈ [0, λ_max] where λ_max is chosen
    conservatively as 1e6 (adequate for typical composite structures).

    Parameters
    ----------
    plies         : list of ply dicts (same as abd_matrix() input)
    N_M_unit      : unit load vector [Nx, Ny, Nxy, Mx, My, Mxy] at λ=1
    strengths_list: list of strength dicts (one per ply, same order as plies)
                    Each dict must contain F1t, F1c, F2t, F2c, F12.
    criteria      : failure criteria to check (default: all four)

    Returns
    -------
    dict
        ok           : True
        lambda_fpf   : load scaling factor at first-ply failure
        N_M_fpf      : N_M vector at first-ply failure
        ply_index    : 0-based index of the first failing ply
        failure_info : failure_indices dict for the critical ply at λ_fpf
        notes        : list of warning strings
    """
    if criteria is None:
        criteria = ["max-stress", "max-strain", "tsai-wu", "tsai-hill"]

    if not plies:
        return _err("plies list is empty")
    if len(strengths_list) != len(plies):
        return _err(
            f"strengths_list length ({len(strengths_list)}) must match "
            f"plies length ({len(plies)})"
        )
    if not isinstance(N_M_unit, (list, tuple)) or len(N_M_unit) != 6:
        return _err("N_M_unit must be a list of 6 floats")

    # Assemble ABD once
    abd_res = abd_matrix(plies)
    if not abd_res.get("ok"):
        return _err(f"abd_matrix error: {abd_res['reason']}")

    def _check_failure(lam: float) -> tuple[bool, int, dict]:
        """Return (any_fail, first_failing_ply_idx, failure_info)."""
        N_M_scaled = [v * lam for v in N_M_unit]
        resp = laminate_response(abd_res, N_M_scaled)
        if not resp.get("ok"):
            return False, -1, {}

        pss = ply_stresses_strains(abd_res, resp, plies)
        if not pss.get("ok"):
            return False, -1, {}

        for k, ply_data in enumerate(pss["plies"]):
            fi_res = failure_indices(
                ply_data["stress_material"],
                ply_data["strain_material"],
                strengths_list[k],
                criteria,
            )
            if fi_res.get("failed"):
                return True, k, fi_res
        return False, -1, {}

    # Check if λ=1 already fails
    fails_at_1, idx_1, fi_1 = _check_failure(1.0)
    if fails_at_1:
        # Backtrack to find exact λ < 1
        lo, hi = 0.0, 1.0
    else:
        # Search for λ > 1 that fails
        lo = 1.0
        hi = 1.0
        while hi < 1e8:
            hi *= 2.0
            fails_hi, _, _ = _check_failure(hi)
            if fails_hi:
                break
        else:
            return {
                "ok": True,
                "lambda_fpf": float("inf"),
                "N_M_fpf": [float("inf")] * 6,
                "ply_index": -1,
                "failure_info": {},
                "notes": ["No failure found up to lambda=1e8"],
            }
        lo = hi / 2.0

    # Bisection
    for _ in range(60):
        mid = (lo + hi) / 2.0
        fails_mid, _, _ = _check_failure(mid)
        if fails_mid:
            hi = mid
        else:
            lo = mid
        if (hi - lo) / (hi + 1e-30) < 1e-9:
            break

    lam_fpf = hi
    _, ply_idx, fi_res = _check_failure(lam_fpf)
    N_M_fpf = [v * lam_fpf for v in N_M_unit]

    return {
        "ok": True,
        "lambda_fpf": lam_fpf,
        "N_M_fpf": N_M_fpf,
        "ply_index": ply_idx,
        "failure_info": fi_res,
        "notes": [],
    }
