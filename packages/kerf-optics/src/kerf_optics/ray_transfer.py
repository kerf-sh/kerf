"""
Paraxial ray-transfer matrix (ABCD matrix) model for multi-element lens systems.

The 2×2 ABCD (ray-transfer) matrix formalism describes paraxial propagation:

    [y2]   [A  B] [y1]
    [u2] = [C  D] [u1]

where (y, u) is the ray state — height y and angle u = n·θ (reduced slope).

For a ray in a medium of refractive index n, we track the paraxial ray vector
(y, nu) — height and reduced angle — so the matrices are compatible across
interfaces with arbitrary refractive indices.

Reference matrices
------------------
Free-space propagation of distance d in medium n:
    M_free(d, n) = [[1, d/n], [0, 1]]   (using (y, nu) convention)

Thin lens of focal length f (refraction, no thickness):
    M_thin_lens(f) = [[1, 0], [-1/f, 1]]

Refraction at a curved interface of radius R, from n1 to n2:
    M_refraction(R, n1, n2) = [[1, 0], [-(n2-n1)/R, 1]]

Mirror of radius R (power P = 2/R):
    M_mirror(R) = [[1, 0], [-2/R, 1]]

Aperture stop: identity matrix (thin aperture does not change the ray).

System matrix = Mn · … · M2 · M1  (right-to-left multiplication).
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np


# ---------------------------------------------------------------------------
# Elementary ABCD matrices (numpy 2×2 float64)
# ---------------------------------------------------------------------------

def M_free(d: float, n: float = 1.0) -> np.ndarray:
    """Free-space propagation of distance *d* in medium of refractive index *n*.

    Using the (y, nu) reduced-angle convention, so n appears only here.
    """
    if d < 0:
        raise ValueError(f"propagation distance d must be >= 0, got {d}")
    if n <= 0:
        raise ValueError(f"refractive index n must be > 0, got {n}")
    return np.array([[1.0, d / n],
                     [0.0, 1.0]], dtype=float)


def M_thin_lens(f: float) -> np.ndarray:
    """Thin-lens refraction matrix for focal length *f*.

    Positive *f* → converging lens; negative *f* → diverging.
    Raises ValueError for f == 0 (infinite power).
    """
    if f == 0:
        raise ValueError("focal length f must not be zero")
    return np.array([[1.0,    0.0],
                     [-1.0 / f, 1.0]], dtype=float)


def M_refraction(R: float, n1: float, n2: float) -> np.ndarray:
    """Refraction at a spherical interface of radius *R*.

    Sign convention: R > 0 → centre of curvature to the right (convex).
    R == 0 (flat interface) → identity matrix.
    """
    if n1 <= 0 or n2 <= 0:
        raise ValueError("refractive indices must be > 0")
    if R == 0:
        # Flat interface — no power
        return np.eye(2, dtype=float)
    power = (n2 - n1) / R
    return np.array([[1.0,   0.0],
                     [-power, 1.0]], dtype=float)


def M_mirror(R: float) -> np.ndarray:
    """Concave mirror of radius of curvature *R*.

    Focal length f = R/2.  R > 0 for concave (converging).
    """
    if R == 0:
        raise ValueError("mirror radius R must not be zero")
    power = 2.0 / R
    return np.array([[1.0,    0.0],
                     [-power, 1.0]], dtype=float)


def M_identity() -> np.ndarray:
    """Identity matrix — thin aperture / detector plane (no optical power)."""
    return np.eye(2, dtype=float)


# ---------------------------------------------------------------------------
# System matrix composition
# ---------------------------------------------------------------------------

def system_matrix(matrices: Sequence[np.ndarray]) -> np.ndarray:
    """Compose a sequence of ABCD matrices (left-to-right element order).

    The *matrices* list is ordered from the first element to the last; the
    product is M_n @ ... @ M_2 @ M_1 (right-to-left multiplication).

    Returns the 2×2 system matrix M = [[A, B], [C, D]].
    """
    if not matrices:
        return M_identity()
    result = matrices[0].copy()
    for m in matrices[1:]:
        result = m @ result
    return result


# ---------------------------------------------------------------------------
# Paraxial system properties derived from the ABCD matrix
# ---------------------------------------------------------------------------

def focal_length(M: np.ndarray) -> float:
    """Effective focal length (EFL) of the system.

    EFL = -1 / C  where C = M[1, 0].

    Raises ValueError if the system has zero power (C == 0).
    """
    C = M[1, 0]
    if C == 0.0:
        raise ValueError("system has no power (C = 0); EFL is undefined (collimating system)")
    return -1.0 / C


def image_distance(M: np.ndarray, object_distance: float) -> float:
    """Paraxial image distance for an object at *object_distance* from the input plane.

    The thin-lens equation in ABCD form:
        di = -(A * do + B) / (C * do + D)

    where do is the object distance (positive in the direction of light travel).

    Raises ValueError if the denominator is zero (object at the front focal point).
    """
    A, B = M[0, 0], M[0, 1]
    C, D = M[1, 0], M[1, 1]
    do = object_distance
    denom = C * do + D
    if abs(denom) < 1e-14:
        raise ValueError(
            f"object at front focal point (denominator = 0 for do={do}); "
            "image is at infinity"
        )
    return -(A * do + B) / denom


def back_focal_distance(M: np.ndarray) -> float:
    """Distance from the rear principal plane to the rear focal point (BFD).

    BFD = -A / C.
    """
    C = M[1, 0]
    if C == 0.0:
        raise ValueError("system has no power (C = 0)")
    return -M[0, 0] / C


def front_focal_distance(M: np.ndarray) -> float:
    """Distance from the front principal plane to the front focal point (FFD).

    FFD = -D / C (negative sign gives distance from rear to front focal point).
    """
    C = M[1, 0]
    if C == 0.0:
        raise ValueError("system has no power (C = 0)")
    return -M[1, 1] / C


def magnification(M: np.ndarray, object_distance: float) -> float:
    """Paraxial transverse magnification for object at *object_distance*.

    m = A + C * di  (derived from the ray-transfer equations).
    """
    di = image_distance(M, object_distance)
    return M[0, 0] + M[1, 0] * di


# ---------------------------------------------------------------------------
# Ray tracing
# ---------------------------------------------------------------------------

def trace_ray(
    y0: float,
    u0: float,
    matrices: Sequence[np.ndarray],
) -> list[tuple[float, float]]:
    """Propagate an initial ray (y0, nu0) through a sequence of ABCD matrices.

    Returns a list of (y, nu) ray states — one entry *before* each element
    and one *after* the last element.

    Parameters
    ----------
    y0  : initial ray height (m or arbitrary length unit)
    u0  : initial reduced angle  n * tan(θ) ≈ n * θ (paraxial)
    matrices : ordered list of ABCD matrices (first = closest to source)
    """
    ray = np.array([y0, u0], dtype=float)
    states: list[tuple[float, float]] = [(float(ray[0]), float(ray[1]))]
    for m in matrices:
        ray = m @ ray
        states.append((float(ray[0]), float(ray[1])))
    return states


def trace_bundle(
    rays: Sequence[tuple[float, float]],
    matrices: Sequence[np.ndarray],
) -> list[list[tuple[float, float]]]:
    """Trace a bundle of rays through the system.

    Parameters
    ----------
    rays     : sequence of (y0, nu0) initial ray states
    matrices : ordered list of ABCD matrices

    Returns
    -------
    list of ray histories; each history is a list of (y, nu) states.
    """
    return [trace_ray(y, u, matrices) for y, u in rays]


# ---------------------------------------------------------------------------
# Spot-size and wavefront utilities
# ---------------------------------------------------------------------------

def spot_radius_at_plane(
    rays: Sequence[tuple[float, float]],
    matrices: Sequence[np.ndarray],
) -> float:
    """RMS spot radius at the plane defined by *matrices*.

    The 'spot' in paraxial optics is the distribution of ray heights at the
    final plane.  Returns the RMS (root-mean-square) radius, which equals
    the standard deviation of the height for a bundle entering at the same
    height but different angles (angular bundle), or vice-versa.
    """
    histories = trace_bundle(rays, matrices)
    final_heights = np.array([h[-1][0] for h in histories])
    return float(np.sqrt(np.mean(final_heights ** 2)))


# ---------------------------------------------------------------------------
# First-order (Seidel) aberration coefficients for a single thin lens
# ---------------------------------------------------------------------------

def seidel_thin_lens(
    f: float,
    n: float,
    object_distance: float,
    y_marginal: float = 1.0,
    shape_factor: float = 0.0,
) -> dict[str, float]:
    """First-order Seidel wavefront aberration coefficients for a thin lens.

    Uses the standard thin-lens Seidel formulae (Born & Wolf §5.5).

    Parameters
    ----------
    f               : focal length (m)
    n               : refractive index of the lens glass
    object_distance : object distance from the lens (positive = real object)
    y_marginal      : marginal ray height at the lens (aperture radius), default 1.0
    shape_factor    : lens shape factor q = (R2+R1)/(R2-R1); 0 = equiconvex

    Returns
    -------
    dict with keys:
        spherical       : W040 spherical aberration coefficient
        coma            : W131 coma coefficient
        astigmatism     : W222 astigmatism coefficient
        field_curvature : W220 Petzval field curvature coefficient
        distortion      : W311 distortion coefficient
    """
    do = float(object_distance)
    h = float(y_marginal)
    q = float(shape_factor)

    # Magnification for this conjugate
    if abs(do) < 1e-14:
        raise ValueError("object_distance must not be zero")

    di = 1.0 / (1.0 / f - 1.0 / do) if abs(1.0 / f - 1.0 / do) > 1e-14 else float("inf")
    m = di / do if abs(do) > 1e-14 else 0.0

    # Conjugate parameter p = (object_distance + image_distance) / (image_distance - object_distance)
    # (sometimes called the 'position factor')
    denom_p = di - do
    p = (di + do) / denom_p if abs(denom_p) > 1e-14 else 0.0

    # Thin-lens Seidel coefficients in terms of (h, f, n, q, p):
    # (from Kingslake, "Lens Design Fundamentals", or Born & Wolf)
    n2 = n * n
    n3 = n2 * n

    # A, B: auxiliary combinations
    A = n / (n - 1.0) if abs(n - 1.0) > 1e-14 else 0.0

    # Spherical aberration W040
    S1 = (h ** 4 / (8.0 * f ** 3)) * (
        n3 / (n2 - 1.0) * (q - (2.0 * (n2 - 1.0) / (n + 2.0)) * p) ** 2
        + (3.0 * (n + 2.0) / (n - 2.0)) * (p - q * (n - 1.0) / n) ** 2
    ) if abs(n - 1.0) > 1e-14 and abs(n - 2.0) > 1e-14 else 0.0

    # Coma W131
    S2 = -(h ** 2 / (2.0 * f ** 2)) * (
        (n + 1.0) / (2.0 * (n - 1.0)) * (q - p * (2.0 * n + 1.0) / (n + 1.0))
    ) * p if abs(n - 1.0) > 1e-14 else 0.0

    # Astigmatism W222
    S3 = p ** 2 / (2.0 * f) if abs(f) > 1e-14 else 0.0

    # Petzval field curvature W220
    S4 = 1.0 / (2.0 * n * f) if abs(f) > 1e-14 else 0.0

    # Distortion W311 (coma-like, vanishes for symmetric systems)
    S5 = 0.0  # zero for a single thin lens in paraxial approximation

    return {
        "spherical": S1,
        "coma": S2,
        "astigmatism": S3,
        "field_curvature": S4,
        "distortion": S5,
    }
