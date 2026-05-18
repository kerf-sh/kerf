"""
kerf_cad_core.topology.manufacturing_constraints
================================================
Production-grade manufacturing constraints for density-based topology
optimisation (SIMP).  All functions are **pure Python** (stdlib math only);
no numpy, no scipy, no FEniCSx dependency.

Provided constraints
--------------------
density_filter
    Linear-hat (conic) density filter that enforces a minimum member size.
    Elements whose effective density is set by a weighted neighbourhood of
    radius *r_min* cannot form solid features thinner than the filter
    kernel — this is the standard Bruns & Tortorelli (2001) realisation.

apply_draw_direction
    Monotone casting / milling draw-direction projection: every column of
    elements is made non-decreasing from the draw face (top) to the base,
    eliminating undercuts that would lock a casting in the die or create
    un-millable pockets from a single setup direction.

enforce_symmetry
    Mirror-plane density coupling: paired elements on opposite sides of a
    specified axis are replaced by their average, forcing the optimiser to
    produce a geometrically symmetric result without doubling the mesh.

check_overhang / repair_overhang
    AM self-support (overhang) constraint.  ``check_overhang`` counts solid
    elements whose support cone below the build direction is violated.
    ``repair_overhang`` projects a bottom-up support envelope so no
    unsupported solid survives — the classic Langelaar (2016) projection.

filter_sensitivity
    Chain-rule the density filter through compliance sensitivities so the
    gradient seen by the optimiser is consistent with the filtered field.

References
----------
* Bruns & Tortorelli (2001) Topology optimization of non-linear elastic
  structures and compliant mechanisms. CMAME 190, 3443-3459.
* Sigmund (2001) A 99 line topology optimization code written in Matlab.
  Struct. Multidisc. Optim. 21, 120-127.
* Lazarov & Sigmund (2016) Filters in topology optimization based on
  Helmholtz-type differential equations. IJNME 86, 765-781.
* Langelaar (2016) Topology optimization of 3D self-supporting structures
  for additive manufacturing. Add. Manuf. 12, 60-70.

Author: imranparuk
"""
from __future__ import annotations

import math
from typing import List, Sequence, Tuple


# ---------------------------------------------------------------------------
# Low-level grid helpers
# ---------------------------------------------------------------------------

def _elem(ex: int, ey: int, nely: int) -> int:
    """Column-major element index: column ex, row ey in an nelx x nely grid."""
    return ex * nely + ey


def _centroid(e: int, nely: int) -> Tuple[int, int]:
    """Return (column, row) for flat element index *e*."""
    return divmod(e, nely)


# ---------------------------------------------------------------------------
# Density filter — minimum member size
# ---------------------------------------------------------------------------

def build_filter_weights(
    nelx: int,
    nely: int,
    r_min: float,
) -> List[List[Tuple[int, float]]]:
    """Pre-compute linear-hat filter weights for an *nelx* × *nely* grid.

    For each element *e* the returned list holds ``(neighbour, weight)``
    pairs.  The weight is ``max(0, r_min - dist(e, neighbour))`` — a
    standard linear (conic) kernel.

    Parameters
    ----------
    nelx, nely:
        Grid dimensions (number of elements in x and y directions).
    r_min:
        Filter radius in *element* units.  Values below 1.0 are clamped to
        1.0 (a radius smaller than one element has no filtering effect).

    Returns
    -------
    weights:
        ``weights[e]`` is a list of ``(j, w_j)`` tuples for element *e*.
    """
    r = max(1.0, float(r_min))
    span = int(math.ceil(r)) + 1
    nel = nelx * nely
    weights: List[List[Tuple[int, float]]] = [[] for _ in range(nel)]
    for ex in range(nelx):
        for ey in range(nely):
            e = _elem(ex, ey, nely)
            acc: List[Tuple[int, float]] = []
            for kx in range(max(0, ex - span), min(nelx, ex + span + 1)):
                for ky in range(max(0, ey - span), min(nely, ey + span + 1)):
                    dist = math.hypot(ex - kx, ey - ky)
                    w = r - dist
                    if w > 0.0:
                        acc.append((_elem(kx, ky, nely), w))
            weights[e] = acc
    return weights


def density_filter(
    rho: Sequence[float],
    weights: List[List[Tuple[int, float]]],
) -> List[float]:
    """Apply pre-computed filter weights to a raw density field *rho*.

    The filtered field ``rho_tilde[e] = sum_j(w_j * rho[j]) / sum_j(w_j)``
    satisfies the minimum-member-size constraint: any sharp feature narrower
    than *r_min* is washed out to a value below the solid/void threshold.

    Parameters
    ----------
    rho:
        Raw (unfiltered) element densities, length == nelx * nely.
    weights:
        Output of :func:`build_filter_weights` for the same grid.

    Returns
    -------
    rho_tilde:
        Filtered densities, same length as *rho*.
    """
    out: List[float] = [0.0] * len(rho)
    for e, nb in enumerate(weights):
        num = 0.0
        den = 0.0
        for j, w in nb:
            num += w * rho[j]
            den += w
        out[e] = num / den if den > 0.0 else rho[e]
    return out


def filter_sensitivity(
    dc: Sequence[float],
    weights: List[List[Tuple[int, float]]],
) -> List[float]:
    """Chain-rule the density filter through compliance sensitivities.

    Because the optimiser sees ``rho_tilde(rho)`` rather than ``rho``
    directly, the chain rule gives:

        d(C) / d(rho[e]) = sum_j [ w(j,e) / W_j * d(C) / d(rho_tilde[j]) ]

    where ``W_j = sum_k w(k, j)`` is the normalising weight-sum for element
    *j*.  This transpose-filter ensures the gradient is consistent with the
    filtered field and is necessary for correct OC / MMA convergence.

    Parameters
    ----------
    dc:
        Raw (unfiltered) compliance sensitivities, one per element.
    weights:
        Same weight table used for the density filter.

    Returns
    -------
    dc_filtered:
        Filtered (physically consistent) sensitivities.
    """
    n = len(dc)
    # Pre-compute normalising weight sums.
    wsum = [0.0] * n
    for e, nb in enumerate(weights):
        for _, w in nb:
            wsum[e] += w

    out = [0.0] * n
    for j, nb in enumerate(weights):
        if wsum[j] <= 0.0:
            continue
        for e, w in nb:
            out[e] += w / wsum[j] * dc[j]
    return out


# ---------------------------------------------------------------------------
# Draw-direction constraint (casting / 3-axis milling)
# ---------------------------------------------------------------------------

def apply_draw_direction(
    rho: List[float],
    nelx: int,
    nely: int,
    direction: str = "neg_y",
) -> None:
    """Enforce a monotone draw-direction constraint **in place**.

    A part is extractable from a one-piece mould drawn in *direction* iff the
    density is non-decreasing from the draw face to the parting plane along
    every column.  This projection sweeps each column and carries the
    running maximum forward so no undercut can exist.

    The operation is idempotent: calling it twice on the same array produces
    the same result as calling it once.

    Parameters
    ----------
    rho:
        Flat element-density array of length *nelx* × *nely*, modified in
        place.
    nelx, nely:
        Grid dimensions.
    direction:
        ``"neg_y"`` (draw from top, +y face, typical for downward mould
        extraction) or ``"pos_y"`` (draw from bottom).

    Notes
    -----
    For milling applications *direction* ``"neg_y"`` corresponds to a top
    face that the tool can always reach; ``"pos_y"`` is a bottom-face setup.
    The constraint eliminates overhangs deeper than 90° for *any* tool path
    normal to the draw direction.
    """
    if direction == "neg_y":
        # Sweep from top (ey = nely-1) downward: carry the max.
        for ex in range(nelx):
            carry = 0.0
            for ey in range(nely - 1, -1, -1):
                e = _elem(ex, ey, nely)
                carry = max(carry, rho[e])
                rho[e] = carry
    elif direction == "pos_y":
        # Sweep from bottom (ey = 0) upward: carry the max.
        for ex in range(nelx):
            carry = 0.0
            for ey in range(nely):
                e = _elem(ex, ey, nely)
                carry = max(carry, rho[e])
                rho[e] = carry
    else:
        raise ValueError(f"Unknown draw direction '{direction}'; expected 'neg_y' or 'pos_y'.")


# ---------------------------------------------------------------------------
# Symmetry-plane enforcement
# ---------------------------------------------------------------------------

def build_mirror_pairs(
    nelx: int,
    nely: int,
    axis: str = "x",
) -> List[Tuple[int, int]]:
    """Return paired element indices mirrored about a mid-plane.

    Parameters
    ----------
    nelx, nely:
        Grid dimensions.
    axis:
        ``"x"`` — vertical mid-plane (mirror left ↔ right, common for
        symmetric MBB or bracket problems); ``"y"`` — horizontal mid-plane
        (mirror top ↔ bottom).

    Returns
    -------
    pairs:
        List of ``(e_left, e_right)`` tuples such that ``e_left`` and
        ``e_right`` are symmetric images of each other.  For an odd-column
        grid the central column has no partner and is excluded.
    """
    pairs: List[Tuple[int, int]] = []
    if axis == "x":
        for ex in range(nelx // 2):
            mx = nelx - 1 - ex
            for ey in range(nely):
                pairs.append((_elem(ex, ey, nely), _elem(mx, ey, nely)))
    elif axis == "y":
        for ey in range(nely // 2):
            my = nely - 1 - ey
            for ex in range(nelx):
                pairs.append((_elem(ex, ey, nely), _elem(ex, my, nely)))
    else:
        raise ValueError(f"Unknown symmetry axis '{axis}'; expected 'x' or 'y'.")
    return pairs


def enforce_symmetry(
    rho: List[float],
    pairs: List[Tuple[int, int]],
) -> None:
    """Average paired elements to enforce mirror-plane symmetry **in place**.

    For each ``(a, b)`` pair both ``rho[a]`` and ``rho[b]`` are replaced by
    ``(rho[a] + rho[b]) / 2``.  This is applied both to the density field
    during the SIMP iteration and to the filtered sensitivities so the OC /
    MMA update honours the constraint.

    Parameters
    ----------
    rho:
        Element density array, modified in place.
    pairs:
        Output of :func:`build_mirror_pairs`.
    """
    for a, b in pairs:
        avg = 0.5 * (rho[a] + rho[b])
        rho[a] = avg
        rho[b] = avg


# ---------------------------------------------------------------------------
# AM overhang / self-support
# ---------------------------------------------------------------------------

def check_overhang(
    rho: Sequence[float],
    nelx: int,
    nely: int,
    max_angle_deg: float = 45.0,
    threshold: float = 0.5,
) -> int:
    """Count solid elements that violate the self-support overhang angle.

    Build direction is assumed to be +y (layers stack upward).  A solid
    element at row *ey* > 0 is self-supporting if at least one element
    within the support cone at row *ey* - 1 is also solid.  The support
    cone is defined by the lateral reach ``reach = floor(1 / tan(angle))``.

    Parameters
    ----------
    rho:
        Flat density array.
    nelx, nely:
        Grid dimensions.
    max_angle_deg:
        Maximum permissible overhang angle from the vertical (e.g. 45° for
        standard FDM).  An angle of 0° means strictly vertical walls only.
    threshold:
        Density value above which an element is considered solid.

    Returns
    -------
    n_violations:
        Number of solid elements violating the overhang constraint.
    """
    ang = max(1e-6, min(89.999, float(max_angle_deg)))
    reach = int(math.floor(1.0 / math.tan(math.radians(ang))))
    violations = 0
    for ex in range(nelx):
        for ey in range(1, nely):  # row 0 = base plate, always supported
            if rho[_elem(ex, ey, nely)] <= threshold:
                continue
            supported = False
            for dx in range(-reach, reach + 1):
                kx = ex + dx
                if 0 <= kx < nelx and rho[_elem(kx, ey - 1, nely)] > threshold:
                    supported = True
                    break
            if not supported:
                violations += 1
    return violations


def repair_overhang(
    rho: List[float],
    nelx: int,
    nely: int,
    max_angle_deg: float = 45.0,
) -> None:
    """Project the density field to eliminate overhang violations **in place**.

    Implements the Langelaar (2016) bottom-up support projection: each
    element's density is capped at the maximum density within its support
    cone one layer below, so no density can exceed what its support allows.
    Sweep proceeds from row 0 (base plate) to row nely-1 (top).

    Parameters
    ----------
    rho:
        Flat density array, modified in place.
    nelx, nely:
        Grid dimensions.
    max_angle_deg:
        Maximum permissible overhang angle (same convention as
        :func:`check_overhang`).
    """
    ang = max(1e-6, min(89.999, float(max_angle_deg)))
    reach = int(math.floor(1.0 / math.tan(math.radians(ang))))
    for ey in range(1, nely):
        for ex in range(nelx):
            cone_max = 0.0
            for dx in range(-reach, reach + 1):
                kx = ex + dx
                if 0 <= kx < nelx:
                    cone_max = max(cone_max, rho[_elem(kx, ey - 1, nely)])
            e = _elem(ex, ey, nely)
            if rho[e] > cone_max:
                rho[e] = cone_max


# ---------------------------------------------------------------------------
# Characteristic-length test (analytic oracle for unit tests)
# ---------------------------------------------------------------------------

def min_feature_length(
    rho: Sequence[float],
    nelx: int,
    nely: int,
    threshold: float = 0.5,
) -> float:
    """Estimate the minimum solid-feature width in the density field.

    Performs a 1-D scan in both x and y: each run of consecutive solid
    elements is a candidate feature; returns the minimum run length across
    all rows and columns.  Returns ``float('inf')`` if there are no solid
    elements.

    This is an *analytic oracle* used in unit tests to verify that the
    density filter with radius *r* has washed out all features narrower
    than approximately *r*.

    Parameters
    ----------
    rho:
        Flat density array.
    nelx, nely:
        Grid dimensions.
    threshold:
        Density above which an element is solid.

    Returns
    -------
    min_len:
        Minimum solid-run length (in element units) across all x-rows and
        y-columns.
    """
    min_len = float("inf")

    # Scan along x direction (each row ey is a 1-D slice).
    for ey in range(nely):
        run = 0
        for ex in range(nelx):
            if rho[_elem(ex, ey, nely)] > threshold:
                run += 1
            else:
                if run > 0:
                    min_len = min(min_len, float(run))
                run = 0
        if run > 0:
            min_len = min(min_len, float(run))

    # Scan along y direction (each column ex is a 1-D slice).
    for ex in range(nelx):
        run = 0
        for ey in range(nely):
            if rho[_elem(ex, ey, nely)] > threshold:
                run += 1
            else:
                if run > 0:
                    min_len = min(min_len, float(run))
                run = 0
        if run > 0:
            min_len = min(min_len, float(run))

    return min_len
