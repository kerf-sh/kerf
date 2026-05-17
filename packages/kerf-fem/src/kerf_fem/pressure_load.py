"""
Distributed-pressure load utilities for shell/plate/cylinder problems
with citation-grade closed-form oracles.

Public entry-points
-------------------
    thin_cylinder_hoop_stress(p, r, t)   -> dict
        σ_hoop = p r / t        (thin-wall pressure vessel; Roark Table 13.1)
        σ_axial = p r / (2 t)   (closed ends)

    thin_sphere_stress(p, r, t)          -> dict
        σ = p r / (2 t)         (thin spherical shell; Roark Table 13.1)

    pressure_to_nodal_forces(face_nodes, p, *, varying=None) -> dict
        Convert a uniform or linearly-varying pressure on a triangular
        surface patch into consistent nodal forces  f = ∫ N p dA.

    plate_centre_deflection_simply_supported(p, a, b, E, nu, h) -> dict
        Centre deflection of a thin rectangular plate with uniform
        pressure p on a simply-supported boundary (Timoshenko & Woinowsky-
        Krieger, "Theory of Plates and Shells", 2nd ed., Table 8 case 1;
        Roark Table 11.4 case 1a).
            w_centre = α p a⁴ / (E h³ / (1 − ν²))
        α is a tabulated function of the aspect ratio b/a; for b/a = 1
        (square plate), α = 0.00406.

References
----------
* Roark's Formulas for Stress and Strain, 9th ed., Tables 13.1 (pressure vessels)
  and 11.4 (rectangular plate uniform load).
* Timoshenko & Woinowsky-Krieger, Theory of Plates and Shells, 2nd ed.,
  Table 8 (uniformly loaded simply-supported rectangular plate).

All routines never raise; errors return {"ok": False, "reason": "..."}.
"""

from __future__ import annotations

import math
from typing import Any


# ---------------------------------------------------------------------------
# Pressure-vessel closed-form
# ---------------------------------------------------------------------------

def thin_cylinder_hoop_stress(p: float, r: float, t: float) -> dict[str, Any]:
    """
    Thin-wall pressure-vessel stresses (Roark Table 13.1, case 1a; Timoshenko
    & Goodier §16).  Valid for r/t > 10.

        σ_hoop  = p r / t        (circumferential)
        σ_axial = p r / (2 t)    (longitudinal, closed ends)

    Returns
    -------
    { ok, sigma_hoop, sigma_axial, ratio }      where ratio = r/t
    """
    if p < 0:
        return {"ok": False, "reason": "p must be non-negative"}
    if r <= 0:
        return {"ok": False, "reason": "r must be positive"}
    if t <= 0:
        return {"ok": False, "reason": "t must be positive"}
    if r / t < 5.0:
        # Still compute it, but flag in a warning
        warnings = ["r/t < 5: thin-wall assumption is questionable"]
    else:
        warnings = []
    sigma_hoop = p * r / t
    sigma_axial = p * r / (2.0 * t)
    return {
        "ok": True,
        "sigma_hoop": sigma_hoop,
        "sigma_axial": sigma_axial,
        "ratio": r / t,
        "warnings": warnings,
    }


def thin_sphere_stress(p: float, r: float, t: float) -> dict[str, Any]:
    """
    Thin-wall spherical pressure-vessel stress (Roark Table 13.1, case 2a):

        σ = p r / (2 t)        (membrane stress, isotropic in the shell)
    """
    if p < 0:
        return {"ok": False, "reason": "p must be non-negative"}
    if r <= 0:
        return {"ok": False, "reason": "r must be positive"}
    if t <= 0:
        return {"ok": False, "reason": "t must be positive"}
    sigma = p * r / (2.0 * t)
    return {"ok": True, "sigma": sigma, "ratio": r / t}


# ---------------------------------------------------------------------------
# Consistent nodal forces from pressure on a triangular face
# ---------------------------------------------------------------------------

def pressure_to_nodal_forces(
    face_nodes: list[list[float]],
    p: float,
    *,
    normal: list[float] | None = None,
    varying: list[float] | None = None,
) -> dict[str, Any]:
    """
    Convert a pressure load on a triangular surface patch into consistent
    nodal forces (statically equivalent and energy-conjugate).

    For a linear (P1) triangle with shape functions N₁,N₂,N₃ and area A:

        Uniform pressure p:    f_i = (p A / 3) · n̂      for each i
        Linearly varying p_i:  f_i = (A / 12) Σ_j p_j (1 + δ_ij)  ·  n̂
        i.e. f_i = (A/12) [(2 p_i + p_j + p_k)] · n̂
        Reference: Cook, Malkus, Plesha, Witt, "Concepts and Applications of
        Finite Element Analysis", 4th ed., eq. (7.3-12).

    Parameters
    ----------
    face_nodes : [[x0,y0,z0], [x1,y1,z1], [x2,y2,z2]]
    p          : scalar pressure (Pa) — used when varying is None
    normal     : outward unit normal (default: computed from CCW triangle)
    varying    : optional per-vertex pressure [p0, p1, p2]

    Returns
    -------
    { ok, area, normal, forces: [[fx,fy,fz], ...] }
    """
    if len(face_nodes) != 3:
        return {"ok": False, "reason": "face_nodes must have exactly 3 vertices"}
    P = [list(map(float, v)) for v in face_nodes]
    e1 = [P[1][i] - P[0][i] for i in range(3)]
    e2 = [P[2][i] - P[0][i] for i in range(3)]
    cross = [
        e1[1] * e2[2] - e1[2] * e2[1],
        e1[2] * e2[0] - e1[0] * e2[2],
        e1[0] * e2[1] - e1[1] * e2[0],
    ]
    cn = math.sqrt(cross[0] ** 2 + cross[1] ** 2 + cross[2] ** 2)
    if cn < 1e-30:
        return {"ok": False, "reason": "degenerate triangle"}
    area = 0.5 * cn
    if normal is None:
        n = [cross[i] / cn for i in range(3)]
    else:
        nm = math.sqrt(sum(v * v for v in normal))
        if nm < 1e-30:
            return {"ok": False, "reason": "normal must be non-zero"}
        n = [normal[i] / nm for i in range(3)]

    if varying is None:
        # Uniform pressure: each vertex gets p * A / 3 along normal
        per_node = p * area / 3.0
        forces = [[per_node * n[0], per_node * n[1], per_node * n[2]] for _ in range(3)]
    else:
        if len(varying) != 3:
            return {"ok": False, "reason": "varying must have 3 entries"}
        pv = [float(v) for v in varying]
        # f_i = (A/12)(2 p_i + p_j + p_k) along normal
        coeff = area / 12.0
        forces = []
        for i in range(3):
            j, k = (i + 1) % 3, (i + 2) % 3
            magnitude = coeff * (2.0 * pv[i] + pv[j] + pv[k])
            forces.append([magnitude * n[0], magnitude * n[1], magnitude * n[2]])

    return {"ok": True, "area": area, "normal": n, "forces": forces}


# ---------------------------------------------------------------------------
# Thin plate uniform-pressure analytic centre deflection
# ---------------------------------------------------------------------------

# Timoshenko & Woinowsky-Krieger Table 8: α coefficient for simply-supported
# rectangular plate, uniform load.  Indexed by aspect ratio b/a (b >= a).
# Selected entries from the textbook table (chosen so linear interpolation
# yields textbook-accurate values).
_TW_TABLE_8 = [
    # (b/a, alpha)   from Timoshenko & Woinowsky-Krieger, Table 8 (1959)
    (1.0,  0.00406),
    (1.1,  0.00485),
    (1.2,  0.00564),
    (1.4,  0.00705),
    (1.6,  0.00830),
    (1.8,  0.00931),
    (2.0,  0.01013),
    (3.0,  0.01223),
    (4.0,  0.01282),
    (5.0,  0.01297),
    (1e6,  0.01302),  # b/a → ∞
]


def _interp(table: list[tuple[float, float]], x: float) -> float:
    if x <= table[0][0]:
        return table[0][1]
    if x >= table[-1][0]:
        return table[-1][1]
    for i in range(len(table) - 1):
        x0, y0 = table[i]
        x1, y1 = table[i + 1]
        if x0 <= x <= x1:
            t = (x - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)
    return table[-1][1]


def plate_centre_deflection_simply_supported(
    p: float,
    a: float,
    b: float,
    E: float,
    nu: float,
    h: float,
) -> dict[str, Any]:
    """
    Centre deflection of a thin rectangular plate of sides a×b, simply
    supported on all four edges, with uniform pressure p (Timoshenko &
    Woinowsky-Krieger, Theory of Plates and Shells, 2nd ed., Table 8):

        w_centre = α p a⁴ / D         where D = E h³ / (12 (1 − ν²))

    a is taken as the *shorter* side (the convention used in the table).

    Returns
    -------
    { ok, w_centre, alpha, D }
    """
    if p < 0:
        return {"ok": False, "reason": "p must be non-negative"}
    if a <= 0 or b <= 0:
        return {"ok": False, "reason": "a, b must be positive"}
    if E <= 0:
        return {"ok": False, "reason": "E must be positive"}
    if h <= 0:
        return {"ok": False, "reason": "h must be positive"}
    if not (-1.0 < nu < 0.5):
        return {"ok": False, "reason": "nu must be in (-1, 0.5)"}

    a_short = min(a, b)
    b_long = max(a, b)
    ratio = b_long / a_short
    alpha = _interp(_TW_TABLE_8, ratio)

    D = E * (h ** 3) / (12.0 * (1.0 - nu * nu))
    w_centre = alpha * p * (a_short ** 4) / D

    return {"ok": True, "w_centre": w_centre, "alpha": alpha, "D": D}
