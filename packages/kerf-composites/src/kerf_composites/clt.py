"""
kerf_composites.clt — Classical Laminate Theory (CLT) solver.

Computes the full [A | B | D] stiffness matrix for a general laminate using
the standard CLT formulation (Jones 1975; Reddy 2004).

Key functions
-------------
ply_Q_matrix(ply)       → 3×3 reduced stiffness matrix in ply principal axes
ply_Qbar_matrix(ply)    → 3×3 transformed stiffness in laminate axes
abd_matrices(layup)     → (A, B, D) each 3×3 numpy arrays [N/mm, N, N·mm]
effective_moduli(layup) → dict of Ex, Ey, Gxy, nu_xy, nu_yx

Sign convention
---------------
The three stress/strain components are ordered (σ₁₁, σ₂₂, σ₁₂) / (ε₁₁, ε₂₂, γ₁₂).
Units: moduli in GPa → Q in GPa; thickness in mm → A in GPa·mm = kN/mm,
       B in GPa·mm² = kN, D in GPa·mm³ = kN·mm.

For the public API the A matrix is returned in **N/mm** (SI-consistent kN/mm
multiplied by 1000 → N/mm), B in N, D in N·mm by converting:
    A [N/mm]   = Q [GPa] * t [mm] * 1e3
    B [N]      = Q [GPa] * z_mid * t [mm] * 1e3
    D [N·mm]   = (1/12) * Q [GPa] * t³ [mm³] * 1e3  (for each ply contribution)
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from kerf_composites.layup import LaminateLayup, Ply, PlyMaterial


# ---------------------------------------------------------------------------
# Reduced stiffness matrix (principal material axes)
# ---------------------------------------------------------------------------

def ply_Q_matrix(ply: "Ply") -> np.ndarray:
    """
    3×3 reduced stiffness matrix **Q** for a ply in its principal axes.

    Returns Q in GPa (consistent with moduli stored in GPa).

    Q = [[Q11, Q12,   0 ],
         [Q12, Q22,   0 ],
         [  0,   0, Q66 ]]

    where:
      Q11 = E1 / (1 - ν12·ν21)
      Q22 = E2 / (1 - ν12·ν21)
      Q12 = ν12·E2 / (1 - ν12·ν21)
      Q66 = G12
    """
    m = ply.material
    denom = 1.0 - m.nu12 * m.nu21
    Q11 = m.E1 / denom
    Q22 = m.E2 / denom
    Q12 = m.nu12 * m.E2 / denom
    Q66 = m.G12

    return np.array([
        [Q11, Q12, 0.0],
        [Q12, Q22, 0.0],
        [0.0, 0.0, Q66],
    ], dtype=float)


# ---------------------------------------------------------------------------
# Transformed reduced stiffness (laminate reference axes)
# ---------------------------------------------------------------------------

def ply_Qbar_matrix(ply: "Ply") -> np.ndarray:
    """
    3×3 transformed reduced stiffness **Q̄** in the laminate axes.

    The transformation rotates the principal-axis Q by the ply fibre angle θ.

    Q̄ = T⁻¹ · Q · Tε      (where Tε is the strain-transformation matrix)

    Returns Q̄ in GPa.
    """
    theta = math.radians(ply.angle)
    c = math.cos(theta)
    s = math.sin(theta)
    c2 = c * c
    s2 = s * s
    cs = c * s
    c4 = c2 * c2
    s4 = s2 * s2
    c2s2 = c2 * s2

    Q = ply_Q_matrix(ply)
    Q11, Q12, Q22, Q66 = Q[0, 0], Q[0, 1], Q[1, 1], Q[2, 2]

    Qbar11 = Q11 * c4 + 2.0 * (Q12 + 2.0 * Q66) * c2s2 + Q22 * s4
    Qbar12 = (Q11 + Q22 - 4.0 * Q66) * c2s2 + Q12 * (c4 + s4)
    Qbar22 = Q11 * s4 + 2.0 * (Q12 + 2.0 * Q66) * c2s2 + Q22 * c4
    Qbar16 = (Q11 - Q12 - 2.0 * Q66) * c2 * cs - (Q22 - Q12 - 2.0 * Q66) * s2 * cs
    Qbar26 = (Q11 - Q12 - 2.0 * Q66) * s2 * cs - (Q22 - Q12 - 2.0 * Q66) * c2 * cs
    Qbar66 = (Q11 + Q22 - 2.0 * Q12 - 2.0 * Q66) * c2s2 + Q66 * (c4 + s4)

    return np.array([
        [Qbar11, Qbar12, Qbar16],
        [Qbar12, Qbar22, Qbar26],
        [Qbar16, Qbar26, Qbar66],
    ], dtype=float)


# ---------------------------------------------------------------------------
# ABD stiffness matrices
# ---------------------------------------------------------------------------

def abd_matrices(layup: "LaminateLayup") -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Compute the full CLT stiffness partition (A, B, D).

    Parameters
    ----------
    layup : LaminateLayup
        Ordered ply stack.

    Returns
    -------
    A : np.ndarray, shape (3, 3)
        In-plane stiffness matrix [N/mm].
    B : np.ndarray, shape (3, 3)
        Bending-extension coupling matrix [N].
    D : np.ndarray, shape (3, 3)
        Bending stiffness matrix [N·mm].

    Notes
    -----
    The standard CLT summation (Jones, 1975) is:

        Aij = Σ Q̄ij_k * (z_k − z_{k−1})
        Bij = ½ Σ Q̄ij_k * (z_k² − z_{k−1}²)
        Dij = ⅓ Σ Q̄ij_k * (z_k³ − z_{k−1}³)

    where z_k are the ply interface coordinates measured from the mid-plane.
    Q̄ is in GPa; z is in mm → result in GPa·mm.  Multiply by 1 000 to get
    N/mm (A), N (B), N·mm (D).
    """
    if layup.num_plies == 0:
        raise ValueError("LaminateLayup has no plies.")

    A = np.zeros((3, 3), dtype=float)
    B = np.zeros((3, 3), dtype=float)
    D = np.zeros((3, 3), dtype=float)

    z = layup.z_coords  # length num_plies + 1, in mm

    for k, ply in enumerate(layup.plies):
        Qbar = ply_Qbar_matrix(ply)
        z_k = z[k + 1]
        z_km1 = z[k]

        dz = z_k - z_km1
        dz2 = z_k ** 2 - z_km1 ** 2
        dz3 = z_k ** 3 - z_km1 ** 3

        A += Qbar * dz
        B += Qbar * (0.5 * dz2)
        D += Qbar * (dz3 / 3.0)

    # Convert from GPa·mm (=kN/mm) → N/mm  (×1000)
    A = A * 1.0e3
    B = B * 1.0e3
    D = D * 1.0e3

    return A, B, D


# ---------------------------------------------------------------------------
# Effective engineering moduli (membrane only)
# ---------------------------------------------------------------------------

def effective_moduli(layup: "LaminateLayup") -> dict[str, float]:
    """
    Compute effective in-plane engineering moduli from the A matrix.

    Uses the inverse compliance approach (following Jones, 1975, §4.5):

        a = A⁻¹   (compliance matrix)
        Ex   = 1 / (h · a11)
        Ey   = 1 / (h · a22)
        Gxy  = 1 / (h · a66)
        nu_xy = −a12 / a11
        nu_yx = −a12 / a22

    Parameters
    ----------
    layup : LaminateLayup

    Returns
    -------
    dict with keys: Ex, Ey, Gxy, nu_xy, nu_yx  (moduli in GPa)
    """
    A, _, _ = abd_matrices(layup)
    h = layup.total_thickness  # mm
    if h <= 0.0:
        raise ValueError("Laminate has zero total thickness.")

    a = np.linalg.inv(A)  # compliance, mm/N

    # Convert: a [mm/N] * h [mm] → dimensionless / (N/mm²) → GPa
    # Ex = 1/(a11 * h) [N/mm / mm] = [N/mm²] = MPa → /1000 → GPa
    Ex = 1.0 / (a[0, 0] * h) / 1.0e3
    Ey = 1.0 / (a[1, 1] * h) / 1.0e3
    Gxy = 1.0 / (a[2, 2] * h) / 1.0e3
    nu_xy = -a[0, 1] / a[0, 0]
    nu_yx = -a[0, 1] / a[1, 1]

    return {
        "Ex": Ex,
        "Ey": Ey,
        "Gxy": Gxy,
        "nu_xy": nu_xy,
        "nu_yx": nu_yx,
    }
