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

from kerf_cad_core.geom.tpms import gyroid_field, schwarz_p_field

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------
Point3 = Tuple[float, float, float]
Strut = Tuple[Point3, Point3]


# ---------------------------------------------------------------------------
# TPMS helpers — thin closures over the shared field functions
# ---------------------------------------------------------------------------

def _make_gyroid_f(cell_size: float) -> Callable[[float, float, float], float]:
    """Return the gyroid implicit function scaled to *cell_size*."""
    def f(x: float, y: float, z: float) -> float:
        return gyroid_field(x, y, z, cell_size)

    return f


def _make_schwarz_p_f(cell_size: float) -> Callable[[float, float, float], float]:
    """Return the Schwarz-P implicit function scaled to *cell_size*."""
    def f(x: float, y: float, z: float) -> float:
        return schwarz_p_field(x, y, z, cell_size)

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


# ---------------------------------------------------------------------------
# GK-116 - Lattice fill of a Body to a target relative density
# ---------------------------------------------------------------------------


def lattice_fill(
    body,
    cell_type="gyroid",
    relative_density=0.3,
    cell_size=None,
):
    """Fill body with a periodic lattice trimmed to the body walls (GK-116).

    Parameters
    ----------
    body : kerf_cad_core.geom.brep.Body
    cell_type : str
        One of "gyroid", "schwarz_p", "octet_truss", "kelvin_cell".
    relative_density : float
        Target volume fraction in (0, 1).
    cell_size : float or None
        Unit cell edge length; auto-chosen as min(extents)/3 if None.

    Returns
    -------
    dict
        mesh             - {"verts": ndarray (V,3), "faces": ndarray (F,3)}
        body             - None (reserved for B-rep output)
        achieved_density - float
    """
    import math as _math

    import numpy as _np

    from kerf_cad_core.geom.sdf import body_sdf as _body_sdf
    from kerf_cad_core.geom.sdf import marching_cubes as _marching_cubes

    _VALID = {"gyroid", "schwarz_p", "octet_truss", "kelvin_cell"}
    if cell_type not in _VALID:
        raise ValueError(
            "cell_type must be one of %s, got %r" % (sorted(_VALID), cell_type)
        )
    if not (0.0 < relative_density < 1.0):
        raise ValueError(
            "relative_density must be in (0, 1), got %s" % relative_density
        )

    sdf_data = _body_sdf(body, resolution=48, padding=0.05)
    grid_body = sdf_data["grid"]
    origin = sdf_data["origin"]
    spacing = sdf_data["spacing"]
    nx, ny, nz = grid_body.shape

    extents = spacing * _np.array([nx - 1, ny - 1, nz - 1], dtype=float)
    if cell_size is None:
        cs = float(min(extents)) / 3.0
        if cs < 1e-12:
            cs = 1.0
    else:
        cs = float(cell_size)

    gx = origin[0] + _np.arange(nx, dtype=_np.float64) * spacing[0]
    gy = origin[1] + _np.arange(ny, dtype=_np.float64) * spacing[1]
    gz = origin[2] + _np.arange(nz, dtype=_np.float64) * spacing[2]
    GX, GY, GZ = _np.meshgrid(gx, gy, gz, indexing="ij")

    if cell_type in ("gyroid", "schwarz_p"):
        # Empirically calibrated: iso_t s.t. voxel fraction == relative_density.
        # Gyroid: fraction(iso_t) ~ iso_t/1.55; Schwarz-P: fraction(iso_t) ~ iso_t/1.75.
        _ISO_SCALE = {"gyroid": 1.55, "schwarz_p": 1.75}
        iso_t = relative_density * _ISO_SCALE[cell_type]
        k = 2.0 * _math.pi / cs
        if cell_type == "gyroid":
            F = (
                _np.sin(k * GX) * _np.cos(k * GY)
                + _np.sin(k * GY) * _np.cos(k * GZ)
                + _np.sin(k * GZ) * _np.cos(k * GX)
            )
        else:
            F = _np.cos(k * GX) + _np.cos(k * GY) + _np.cos(k * GZ)
        phi_lattice = _np.abs(F) - iso_t
    else:
        n_struts = 36
        _STRUT_LEN_FRAC = {
            "octet_truss": 1.0 / _math.sqrt(2),
            "kelvin_cell": _math.sqrt(2) / 4.0,
        }
        slf = _STRUT_LEN_FRAC[cell_type]
        strut_r = _math.sqrt(relative_density * cs * cs / (n_struts * _math.pi * slf))

        if cell_type == "octet_truss":
            cell_desc = octet_truss(cs, strut_r)
        else:
            cell_desc = kelvin_cell(cs, strut_r)

        struts_unit = cell_desc["struts"]

        Xf = GX.ravel()
        Yf = GY.ravel()
        Zf = GZ.ravel()
        N_pts = len(Xf)
        Xc = _np.mod(Xf - origin[0], cs)
        Yc = _np.mod(Yf - origin[1], cs)
        Zc = _np.mod(Zf - origin[2], cs)
        pts_cell = _np.stack([Xc, Yc, Zc], axis=1)

        min_dist_sq = _np.full(N_pts, 1e30, dtype=_np.float64)
        for (ax, ay, az), (bx, by, bz) in struts_unit:
            ab = _np.array([bx - ax, by - ay, bz - az], dtype=_np.float64)
            ab_len_sq = float(ab @ ab)
            if ab_len_sq < 1e-24:
                continue
            ap = pts_cell - _np.array([ax, ay, az])
            t = _np.clip((ap @ ab) / ab_len_sq, 0.0, 1.0)
            closest = _np.array([ax, ay, az]) + t[:, None] * ab
            d_sq = _np.sum((pts_cell - closest) ** 2, axis=1)
            _np.minimum(min_dist_sq, d_sq, out=min_dist_sq)

        phi_lattice = (_np.sqrt(min_dist_sq) - strut_r).reshape(nx, ny, nz)

    phi_combined = _np.maximum(phi_lattice, grid_body)

    mc_input = {"grid": phi_combined, "origin": origin, "spacing": spacing}
    mesh = _marching_cubes(mc_input, iso=0.0)

    n_body_interior = int(_np.sum(grid_body < 0))
    n_lattice_fill = int(_np.sum(phi_combined < 0))
    if n_body_interior > 0:
        achieved_density = float(n_lattice_fill) / float(n_body_interior)
    else:
        achieved_density = 0.0

    return {"mesh": mesh, "body": None, "achieved_density": achieved_density}


# ---------------------------------------------------------------------------
# GK-117 - TPMS implicit sheet (meshed band | |f(p)| <= t/2)
# ---------------------------------------------------------------------------

def tpms_sheet(
    cell_type: str = "schwarz_p",
    cell_size: float = 10.0,
    thickness: float = 1.0,
    bounds=None,
) -> dict:
    """GK-117 — Triply-periodic minimal surface meshed as a closed sheet.

    Evaluates the chosen TPMS implicit function *f* on a voxel grid, builds
    the scalar field ``phi = |f(p)| - iso_t`` (negative inside the band
    |f| <= iso_t) and extracts the zero-level-set via marching cubes.
    The result is a closed-manifold triangle mesh of the solid sheet.

    The iso threshold ``iso_t`` is derived from the requested physical
    *thickness* using the analytic gradient magnitude of the TPMS at the
    mid-surface:

    - Schwarz-P: |∇f| ≈ k·√3 at the mid-surface ⇒ iso_t = (k·√3)·(t/2)
    - Gyroid/Diamond: |∇f| ≈ k·√2 at the mid-surface ⇒ iso_t = (k·√2)·(t/2)

    where k = 2π / cell_size.

    Parameters
    ----------
    cell_type : str
        One of ``"schwarz_p"``, ``"gyroid"``, or ``"diamond"``.
    cell_size : float
        Edge length of the cubic repeating unit cell (same units as design
        coordinates, e.g. mm).
    thickness : float
        Desired physical sheet thickness (same units).  The function
        selects the appropriate iso-threshold to match this.
    bounds : tuple or None
        ``((xmin,xmax), (ymin,ymax), (zmin,zmax))`` — world-space extent of
        the voxel grid.  Defaults to two unit cells in each direction:
        ``((0, 2·cell_size), …)``.

    Returns
    -------
    dict
        ``{"verts": np.ndarray (V, 3), "faces": np.ndarray (F, 3)}``

        - ``verts``: float64 world-space vertex positions.
        - ``faces``: int32 vertex indices (triangles).  The mesh is a
          closed manifold (no boundary edges) when *thickness* is small
          enough that the band does not reach the grid boundary.

    Raises
    ------
    ValueError
        For invalid ``cell_type``, non-positive ``cell_size``/``thickness``.

    Notes
    -----
    Pure-Python / NumPy only.  Reuses :func:`~kerf_cad_core.geom.lattice.gyroid`,
    :func:`~kerf_cad_core.geom.lattice.schwarz_p` and
    :func:`~kerf_cad_core.geom.sdf.marching_cubes` (GK-113).

    References
    ----------
    - Lord, E.A. & Mackay, A.L. (2003) Periodic minimal surfaces of cubic
      symmetry. Current Science 85(3).
    """
    import math as _math

    import numpy as _np

    from kerf_cad_core.geom.sdf import marching_cubes as _marching_cubes

    _VALID = {"schwarz_p", "gyroid", "diamond"}
    if cell_type not in _VALID:
        raise ValueError(
            "cell_type must be one of %s, got %r" % (sorted(_VALID), cell_type)
        )
    if cell_size <= 0:
        raise ValueError(f"cell_size must be positive, got {cell_size}")
    if thickness <= 0:
        raise ValueError(f"thickness must be positive, got {thickness}")

    L = float(cell_size)
    t = float(thickness)
    k = 2.0 * _math.pi / L

    # ---- iso threshold from analytic |∇f| at mid-surface -------------------
    # Schwarz-P: f = cos(kx)+cos(ky)+cos(kz), |∇f|² = k²(sin²(kx)+sin²(ky)+sin²(kz))
    #   At the mid-surface (f=0) the typical value is |∇f| ≈ k√2..k√3; use k√3.
    # Gyroid / diamond: |∇f| ≈ k√2 at the mid-surface.
    if cell_type == "schwarz_p":
        grad_mag = k * _math.sqrt(3.0)
    else:
        grad_mag = k * _math.sqrt(2.0)

    iso_t = grad_mag * (t / 2.0)

    # ---- build voxel grid ---------------------------------------------------
    if bounds is None:
        bounds = (
            (0.0, 2.0 * L),
            (0.0, 2.0 * L),
            (0.0, 2.0 * L),
        )

    (xmin, xmax), (ymin, ymax), (zmin, zmax) = bounds
    # Target ~8 voxels per cell_size minimum; use at least 32 nodes per axis.
    voxels_per_cell = 12
    nx = max(32, int(_math.ceil((xmax - xmin) / L * voxels_per_cell)) + 1)
    ny = max(32, int(_math.ceil((ymax - ymin) / L * voxels_per_cell)) + 1)
    nz = max(32, int(_math.ceil((zmax - zmin) / L * voxels_per_cell)) + 1)

    gx = _np.linspace(xmin, xmax, nx, dtype=_np.float64)
    gy = _np.linspace(ymin, ymax, ny, dtype=_np.float64)
    gz = _np.linspace(zmin, zmax, nz, dtype=_np.float64)
    GX, GY, GZ = _np.meshgrid(gx, gy, gz, indexing="ij")

    # ---- evaluate TPMS implicit function ------------------------------------
    if cell_type == "schwarz_p":
        F = _np.cos(k * GX) + _np.cos(k * GY) + _np.cos(k * GZ)
    elif cell_type == "gyroid":
        F = (
            _np.sin(k * GX) * _np.cos(k * GY)
            + _np.sin(k * GY) * _np.cos(k * GZ)
            + _np.sin(k * GZ) * _np.cos(k * GX)
        )
    else:  # diamond
        # Schwarz Diamond: sin(kx)sin(ky)sin(kz) + sin(kx)cos(ky)cos(kz)
        #                + cos(kx)sin(ky)cos(kz) + cos(kx)cos(ky)sin(kz) = 0
        F = (
            _np.sin(k * GX) * _np.sin(k * GY) * _np.sin(k * GZ)
            + _np.sin(k * GX) * _np.cos(k * GY) * _np.cos(k * GZ)
            + _np.cos(k * GX) * _np.sin(k * GY) * _np.cos(k * GZ)
            + _np.cos(k * GX) * _np.cos(k * GY) * _np.sin(k * GZ)
        )

    # phi < 0 inside the band |F| <= iso_t; phi = 0 is the sheet boundary.
    phi = _np.abs(F) - iso_t

    # Seal the grid boundary: force the outermost voxel layer to phi > 0 so
    # that marching cubes sees a closed domain and produces no boundary edges.
    # This effectively caps any band that would exit the grid, yielding a
    # closed-manifold mesh.
    wall = float(iso_t + 1.0)
    phi[0, :, :] = wall
    phi[-1, :, :] = wall
    phi[:, 0, :] = wall
    phi[:, -1, :] = wall
    phi[:, :, 0] = wall
    phi[:, :, -1] = wall

    spacing_x = (xmax - xmin) / (nx - 1)
    spacing_y = (ymax - ymin) / (ny - 1)
    spacing_z = (zmax - zmin) / (nz - 1)

    grid_input = {
        "grid": phi,
        "origin": _np.array([xmin, ymin, zmin], dtype=_np.float64),
        "spacing": _np.array([spacing_x, spacing_y, spacing_z], dtype=_np.float64),
    }

    return _marching_cubes(grid_input, iso=0.0)
