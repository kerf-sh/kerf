"""GK-115 — Lattice unit-cell library (implicit TPMS + strut generators).

Pure-Python, no OCCT dependency.

Public API
----------
gyroid(cell_size, thickness) -> dict
    Gyroid TPMS implicit surface.
    Returns:
        f           : callable (x, y, z) -> float   — implicit function
                      zero-level = mid-surface; positive = inside shell
        cell_size   : float
        thickness   : float
        kind        : "tpms"

schwarz_p(cell_size, thickness) -> dict
    Schwarz-P TPMS implicit surface.
    Returns:
        f           : callable (x, y, z) -> float
        cell_size   : float
        thickness   : float
        kind        : "tpms"

octet_truss(cell_size, strut_radius) -> dict
    Octet truss (FCC + octahedron) strut lattice.
    Produces exactly 36 strut segments per unit cell.
    Returns:
        struts      : list[((x0,y0,z0),(x1,y1,z1))]  — 36 strut segments
        nodes       : list[(x, y, z)]                  — unique node positions
        cell_size   : float
        strut_radius: float
        kind        : "strut"

kelvin_cell(cell_size, strut_radius) -> dict
    Kelvin (bitruncated cubic) strut lattice.
    Returns:
        struts      : list[((x0,y0,z0),(x1,y1,z1))]
        nodes       : list[(x, y, z)]
        cell_size   : float
        strut_radius: float
        kind        : "strut"

References
----------
- Lord, E.A. & Mackay, A.L. (2003) Periodic minimal surfaces of cubic
  symmetry. Current Science 85(3).
- Deshpande, V.S., Fleck, N.A. & Ashby, M.F. (2001) Effective properties
  of the octet-truss lattice material. J. Mech. Phys. Solids 49, 1747-1769.
- Kelvin, Lord (1887) On the division of space with minimum partitional area.
  Phil. Mag. 24(151), 503-514.
"""

from __future__ import annotations

import math
from typing import Callable, List, Tuple

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------
Point3 = Tuple[float, float, float]
Strut = Tuple[Point3, Point3]


# ---------------------------------------------------------------------------
# TPMS helpers
# ---------------------------------------------------------------------------

def _make_gyroid_f(cell_size: float) -> Callable[[float, float, float], float]:
    """Return the gyroid implicit function scaled to *cell_size*."""
    k = 2.0 * math.pi / cell_size

    def f(x: float, y: float, z: float) -> float:
        # Gyroid: sin(kx)cos(ky) + sin(ky)cos(kz) + sin(kz)cos(kx) = 0
        return (
            math.sin(k * x) * math.cos(k * y)
            + math.sin(k * y) * math.cos(k * z)
            + math.sin(k * z) * math.cos(k * x)
        )

    return f


def _make_schwarz_p_f(cell_size: float) -> Callable[[float, float, float], float]:
    """Return the Schwarz-P implicit function scaled to *cell_size*."""
    k = 2.0 * math.pi / cell_size

    def f(x: float, y: float, z: float) -> float:
        # Schwarz-P: cos(kx) + cos(ky) + cos(kz) = 0
        return math.cos(k * x) + math.cos(k * y) + math.cos(k * z)

    return f


# ---------------------------------------------------------------------------
# Public TPMS API
# ---------------------------------------------------------------------------

def gyroid(cell_size: float, thickness: float) -> dict:
    """Gyroid TPMS unit-cell descriptor.

    Parameters
    ----------
    cell_size:
        Edge length of the cubic repeating unit cell (same units as design
        coordinates, e.g. mm).
    thickness:
        Shell half-thickness — a point p is inside the solid sheet when
        |f(p)| <= iso_offset, where iso_offset = thickness * approximate_gradient.
        For practical use, callers may band-select |f(p)| <= 1.5 * (thickness /
        cell_size) * 2*pi.

    Returns
    -------
    dict with keys:
        ``f``          - callable (x, y, z) -> float (implicit, zero = mid-surface)
        ``cell_size``  - float
        ``thickness``  - float
        ``kind``       - "tpms"
    """
    if cell_size <= 0:
        raise ValueError(f"cell_size must be positive, got {cell_size}")
    if thickness <= 0:
        raise ValueError(f"thickness must be positive, got {thickness}")

    return {
        "f": _make_gyroid_f(cell_size),
        "cell_size": float(cell_size),
        "thickness": float(thickness),
        "kind": "tpms",
    }


def schwarz_p(cell_size: float, thickness: float) -> dict:
    """Schwarz-P TPMS unit-cell descriptor.

    Parameters
    ----------
    cell_size:
        Edge length of the cubic repeating unit cell.
    thickness:
        Shell half-thickness (same convention as gyroid).

    Returns
    -------
    dict with keys:
        ``f``          - callable (x, y, z) -> float
        ``cell_size``  - float
        ``thickness``  - float
        ``kind``       - "tpms"
    """
    if cell_size <= 0:
        raise ValueError(f"cell_size must be positive, got {cell_size}")
    if thickness <= 0:
        raise ValueError(f"thickness must be positive, got {thickness}")

    return {
        "f": _make_schwarz_p_f(cell_size),
        "cell_size": float(cell_size),
        "thickness": float(thickness),
        "kind": "tpms",
    }


# ---------------------------------------------------------------------------
# Strut lattice helpers
# ---------------------------------------------------------------------------

def _dedup_nodes(raw: List[Point3], tol: float = 1e-9) -> List[Point3]:
    """Return a de-duplicated node list (order-preserving)."""
    unique: List[Point3] = []
    for p in raw:
        for q in unique:
            if abs(p[0] - q[0]) < tol and abs(p[1] - q[1]) < tol and abs(p[2] - q[2]) < tol:
                break
        else:
            unique.append(p)
    return unique


def _make_strut(a: Point3, b: Point3) -> Strut:
    """Return a canonical (sorted) strut so duplicates are easy to detect."""
    return (a, b) if a <= b else (b, a)


# ---------------------------------------------------------------------------
# Octet truss — FCC nearest-neighbour connectivity, 36 struts per unit cell
# ---------------------------------------------------------------------------
#
# Node set: 8 cube corners + 6 face-centres = 14 FCC positions.
# Two nodes are connected iff their separation == L/sqrt(2) (FCC nn distance).
# This gives exactly 36 struts per Deshpande, Fleck & Ashby (2001).

def octet_truss(cell_size: float, strut_radius: float) -> dict:
    """Octet truss unit-cell descriptor.

    Generates the canonical octet truss (face-centred cubic + octahedron)
    with exactly **36** strut segments per unit cell.

    The node set is the FCC unit cell: 8 cube corners + 6 face-centres = 14
    unique nodes.  Two nodes are connected by a strut when their Euclidean
    separation equals the FCC nearest-neighbour distance L/sqrt(2).  This
    yields exactly 36 struts per cell (Deshpande, Fleck & Ashby, 2001).

    Parameters
    ----------
    cell_size:
        Edge length of the cubic repeating unit cell.
    strut_radius:
        Radius of each cylindrical strut member.

    Returns
    -------
    dict with keys:
        ``struts``       - list of 36 ((x0,y0,z0),(x1,y1,z1)) tuples
        ``nodes``        - list of 14 unique node positions
        ``cell_size``    - float
        ``strut_radius`` - float
        ``kind``         - "strut"
    """
    if cell_size <= 0:
        raise ValueError(f"cell_size must be positive, got {cell_size}")
    if strut_radius <= 0:
        raise ValueError(f"strut_radius must be positive, got {strut_radius}")

    L = float(cell_size)
    h = L / 2.0

    # FCC nodes: 8 cube corners + 6 face-centres (14 nodes)
    nodes: List[Point3] = [
        # Corners
        (0.0, 0.0, 0.0), (L,   0.0, 0.0), (0.0, L,   0.0), (L,   L,   0.0),
        (0.0, 0.0, L),   (L,   0.0, L),   (0.0, L,   L),   (L,   L,   L),
        # Face centres
        (h,   h,   0.0),  # -Z face
        (h,   h,   L),    # +Z face
        (h,   0.0, h),    # -Y face
        (h,   L,   h),    # +Y face
        (0.0, h,   h),    # -X face
        (L,   h,   h),    # +X face
    ]

    # Connect nodes at FCC nearest-neighbour distance L/sqrt(2)
    target_sq = (L * L) / 2.0
    tol = 1e-9 * L * L
    strut_set: set = set()
    for i, a in enumerate(nodes):
        for b in nodes[i + 1:]:
            dx = a[0] - b[0]
            dy = a[1] - b[1]
            dz = a[2] - b[2]
            if abs(dx * dx + dy * dy + dz * dz - target_sq) < tol:
                strut_set.add(_make_strut(a, b))

    struts = list(strut_set)
    assert len(struts) == 36, (
        f"octet_truss: expected 36 struts, got {len(struts)}"
    )

    return {
        "struts": struts,
        "nodes": nodes,
        "cell_size": L,
        "strut_radius": float(strut_radius),
        "kind": "strut",
    }


# ---------------------------------------------------------------------------
# Kelvin cell (bitruncated cubic honeycomb / truncated octahedron)
# ---------------------------------------------------------------------------
#
# The Kelvin cell tiles space with truncated octahedra.  Canonical vertex
# coordinates: all permutations of (0, +/-1, +/-2), giving 24 vertices.
# Two vertices are adjacent iff their squared distance == 2 (edge length
# sqrt(2) in integer coords).  This gives 36 edges.
#
# We scale so the bounding box == cell_size: scale factor s = L / 4.

def kelvin_cell(cell_size: float, strut_radius: float) -> dict:
    """Kelvin (bitruncated cubic / truncated octahedron) strut cell descriptor.

    Parameters
    ----------
    cell_size:
        Edge length of the bounding cubic cell (the truncated octahedron fits
        inside a cube of this size).
    strut_radius:
        Radius of each strut member.

    Returns
    -------
    dict with keys:
        ``struts``       - list of strut segments
        ``nodes``        - list of 24 unique node positions
        ``cell_size``    - float
        ``strut_radius`` - float
        ``kind``         - "strut"
    """
    if cell_size <= 0:
        raise ValueError(f"cell_size must be positive, got {cell_size}")
    if strut_radius <= 0:
        raise ValueError(f"strut_radius must be positive, got {strut_radius}")

    L = float(cell_size)
    # Truncated octahedron integer coords span [-2,2] -> width 4; scale to L.
    s = L / 4.0
    cx = cy = cz = L / 2.0  # centre inside the cell

    # 24 vertices: all permutations of (0, +/-1, +/-2)
    raw_vertices: set = _permutations_signed_012()
    sorted_verts = sorted(raw_vertices)

    nodes: List[Point3] = [
        (cx + s * v[0], cy + s * v[1], cz + s * v[2])
        for v in sorted_verts
    ]

    # Build adjacency: vertices connected iff squared integer distance == 2
    edge_len_sq = 2.0
    tol = 1e-6
    strut_set: set = set()
    for i, a in enumerate(sorted_verts):
        for j, b in enumerate(sorted_verts):
            if j <= i:
                continue
            dx = a[0] - b[0]
            dy = a[1] - b[1]
            dz = a[2] - b[2]
            if abs(dx * dx + dy * dy + dz * dz - edge_len_sq) < tol:
                na = (cx + s * a[0], cy + s * a[1], cz + s * a[2])
                nb = (cx + s * b[0], cy + s * b[1], cz + s * b[2])
                strut_set.add(_make_strut(na, nb))

    struts = list(strut_set)

    return {
        "struts": struts,
        "nodes": nodes,
        "cell_size": L,
        "strut_radius": float(strut_radius),
        "kind": "strut",
    }


def _permutations_signed_012() -> set:
    """Yield all 24 vertices of the form permutations(0, +/-1, +/-2)."""
    from itertools import permutations as _perms
    seen: set = set()
    base = [0, 1, 2]
    for perm in _perms(base):
        for sx in (1, -1):
            for sy in (1, -1):
                for sz in (1, -1):
                    v = (sx * perm[0], sy * perm[1], sz * perm[2])
                    seen.add(v)
    return seen
