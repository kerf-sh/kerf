"""
kerf_composites.failure — Ply failure criteria.

Implements:
  - Tsai-Wu quadratic failure criterion (Tsai & Wu, 1971)
  - Tsai-Hill maximum strain-energy criterion (Hill, 1950; Tsai, 1968)

Both criteria operate on the ply-level principal-axis stresses
(σ₁, σ₂, τ₁₂) in MPa and return a failure index (FI).

  FI < 1  →  safe
  FI = 1  →  onset of failure
  FI > 1  →  failed

The reserve factor (RF) = 1 / FI.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kerf_composites.layup import PlyMaterial


# ---------------------------------------------------------------------------
# Stress state dataclass
# ---------------------------------------------------------------------------

@dataclass
class PlyStress:
    """
    In-plane stress state in the ply principal material axes.

    Parameters
    ----------
    sigma1 : float
        Longitudinal (fibre-direction) stress [MPa].  + = tension.
    sigma2 : float
        Transverse stress [MPa].  + = tension.
    tau12 : float
        In-plane shear stress [MPa].
    """
    sigma1: float  # MPa
    sigma2: float  # MPa
    tau12: float   # MPa


# ---------------------------------------------------------------------------
# Tsai-Wu failure index
# ---------------------------------------------------------------------------

def tsai_wu_index(stress: PlyStress, material: "PlyMaterial", F12_star: float = -0.5) -> float:
    """
    Tsai-Wu quadratic failure index.

    FI = F₁σ₁ + F₂σ₂ + F₁₁σ₁² + F₂₂σ₂² + F₆₆τ₁₂² + 2F₁₂σ₁σ₂

    where:
      F₁  = 1/Xt − 1/Xc
      F₂  = 1/Yt − 1/Yc
      F₁₁ = 1/(Xt·Xc)
      F₂₂ = 1/(Yt·Yc)
      F₆₆ = 1/S₁₂²
      F₁₂ = F12_star * √(F₁₁·F₂₂)     (interaction term, default −0.5)

    Parameters
    ----------
    stress : PlyStress
        Ply stress state in principal axes [MPa].
    material : PlyMaterial
        Ply material with strength data [MPa].
    F12_star : float
        Normalised interaction coefficient (−1 < F12_star* < 0.5).
        Default −0.5 is conservative (Tsai-Wu recommendation).

    Returns
    -------
    float
        Failure index.  FI ≥ 1 → failure predicted.
    """
    m = material
    s1, s2, t12 = stress.sigma1, stress.sigma2, stress.tau12

    F1 = 1.0 / m.Xt - 1.0 / m.Xc
    F2 = 1.0 / m.Yt - 1.0 / m.Yc
    F11 = 1.0 / (m.Xt * m.Xc)
    F22 = 1.0 / (m.Yt * m.Yc)
    F66 = 1.0 / (m.S12 ** 2)
    F12 = F12_star * math.sqrt(F11 * F22)

    fi = (
        F1 * s1
        + F2 * s2
        + F11 * s1 ** 2
        + F22 * s2 ** 2
        + F66 * t12 ** 2
        + 2.0 * F12 * s1 * s2
    )
    return fi


# ---------------------------------------------------------------------------
# Tsai-Hill failure index
# ---------------------------------------------------------------------------

def tsai_hill_index(stress: PlyStress, material: "PlyMaterial") -> float:
    """
    Tsai-Hill failure index.

    FI = (σ₁/X)² − (σ₁σ₂/X²) + (σ₂/Y)² + (τ₁₂/S₁₂)²

    where X = Xt if σ₁ ≥ 0 else Xc, Y = Yt if σ₂ ≥ 0 else Yc.

    Parameters
    ----------
    stress : PlyStress
        Ply stress state in principal axes [MPa].
    material : PlyMaterial
        Ply material.

    Returns
    -------
    float
        Failure index.  FI ≥ 1 → failure predicted.
    """
    m = material
    s1, s2, t12 = stress.sigma1, stress.sigma2, stress.tau12

    X = m.Xt if s1 >= 0.0 else m.Xc
    Y = m.Yt if s2 >= 0.0 else m.Yc

    fi = (
        (s1 / X) ** 2
        - (s1 * s2 / X ** 2)
        + (s2 / Y) ** 2
        + (t12 / m.S12) ** 2
    )
    return fi


# ---------------------------------------------------------------------------
# Reserve factor helpers
# ---------------------------------------------------------------------------

def reserve_factor_tsai_wu(
    stress: PlyStress,
    material: "PlyMaterial",
    F12_star: float = -0.5,
) -> float:
    """Reserve factor = 1 / Tsai-Wu FI.  RF > 1 → safe."""
    fi = tsai_wu_index(stress, material, F12_star=F12_star)
    if fi <= 0.0:
        return float("inf")
    return 1.0 / fi


def reserve_factor_tsai_hill(stress: PlyStress, material: "PlyMaterial") -> float:
    """Reserve factor = 1 / Tsai-Hill FI.  RF > 1 → safe."""
    fi = tsai_hill_index(stress, material)
    if fi <= 0.0:
        return float("inf")
    return 1.0 / fi


# ---------------------------------------------------------------------------
# Laminate failure analysis (first-ply failure)
# ---------------------------------------------------------------------------

@dataclass
class PlyFailureResult:
    """Failure analysis result for a single ply."""
    ply_index: int
    angle: float
    tsai_wu_fi: float
    tsai_hill_fi: float
    failed_tsai_wu: bool
    failed_tsai_hill: bool


def laminate_failure_analysis(
    stresses: list[PlyStress],
    materials: list["PlyMaterial"],
    angles: list[float],
    F12_star: float = -0.5,
) -> list[PlyFailureResult]:
    """
    Evaluate failure indices for every ply in the laminate.

    Parameters
    ----------
    stresses : list[PlyStress]
        Per-ply stress states in principal axes [MPa].
    materials : list[PlyMaterial]
        Per-ply materials (same length as stresses).
    angles : list[float]
        Per-ply fibre angles in degrees.
    F12_star : float
        Tsai-Wu interaction coefficient.

    Returns
    -------
    list[PlyFailureResult]
        One entry per ply.
    """
    if not (len(stresses) == len(materials) == len(angles)):
        raise ValueError("stresses, materials, and angles must have equal length.")

    results = []
    for i, (stress, mat, angle) in enumerate(zip(stresses, materials, angles)):
        fi_tw = tsai_wu_index(stress, mat, F12_star=F12_star)
        fi_th = tsai_hill_index(stress, mat)
        results.append(PlyFailureResult(
            ply_index=i,
            angle=angle,
            tsai_wu_fi=fi_tw,
            tsai_hill_fi=fi_th,
            failed_tsai_wu=(fi_tw >= 1.0),
            failed_tsai_hill=(fi_th >= 1.0),
        ))
    return results
