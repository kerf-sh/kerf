"""
kerf_cad_core.frep.sdf
======================
Signed-distance-field (SDF) modelling — primitives, CSG ops, transforms,
TPMS lattices, marching-cubes mesh extraction, field sampling, and LLM tools.

Design principles
-----------------
* Pure Python + math only.  No OCC, numpy, scipy, or third-party deps.
* Never raises — every public function and tool returns a dict with
  ``{"ok": bool, ...}`` and catches all exceptions internally.
* All SDF callables have the signature  ``f(x, y, z) -> float``  where a
  negative return value is inside the solid and zero is on the surface.
* The ``@register`` LLM tools mirror the public Python API below and are
  gated behind ``kerf_chat`` / ``kerf_core`` availability.

References
----------
Quilez, I. (2022). "Signed Distance Functions." iquilezles.org/articles/distfunctions
Bloomenthal, J. et al. (1997). "Introduction to Implicit Surfaces." Morgan Kaufmann.
Lorensen & Cline (1987). "Marching Cubes: A High-Resolution 3D Surface Construction Algorithm."
Schoen, A. H. (1970). "Infinite periodic minimal surfaces without self-intersections."
"""
from __future__ import annotations

import json
import math
from typing import Callable, List, Optional, Tuple

from kerf_cad_core.geom.tpms import (
    gyroid_field as _gyroid_field,
    schwarz_p_field as _schwarz_p_field,
    diamond_field as _diamond_field,
)

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------
SDF = Callable[[float, float, float], float]
Verts = List[Tuple[float, float, float]]
Faces = List[Tuple[int, int, int]]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EPS = 1e-7  # numerical gradient step


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else (hi if v > hi else v)


def _length3(x: float, y: float, z: float) -> float:
    return math.sqrt(x * x + y * y + z * z)


def _dot3(ax, ay, az, bx, by, bz):
    return ax * bx + ay * by + az * bz


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------

def sdf_sphere(cx: float = 0.0, cy: float = 0.0, cz: float = 0.0,
               radius: float = 1.0) -> SDF:
    """Signed-distance field of a sphere at (cx, cy, cz) with given radius."""
    def _f(x, y, z):
        return _length3(x - cx, y - cy, z - cz) - radius
    return _f


def sdf_box(cx: float = 0.0, cy: float = 0.0, cz: float = 0.0,
            hx: float = 1.0, hy: float = 1.0, hz: float = 1.0) -> SDF:
    """Signed-distance field of an axis-aligned box centred at (cx,cy,cz)
    with half-extents (hx, hy, hz)."""
    def _f(x, y, z):
        qx = abs(x - cx) - hx
        qy = abs(y - cy) - hy
        qz = abs(z - cz) - hz
        pos_x = qx if qx > 0.0 else 0.0
        pos_y = qy if qy > 0.0 else 0.0
        pos_z = qz if qz > 0.0 else 0.0
        outer = _length3(pos_x, pos_y, pos_z)
        inner = min(max(qx, max(qy, qz)), 0.0)
        return outer + inner
    return _f


def sdf_cylinder(cx: float = 0.0, cy: float = 0.0, cz: float = 0.0,
                 radius: float = 1.0, half_height: float = 1.0,
                 axis: int = 2) -> SDF:
    """Signed-distance field of a cylinder aligned to the specified axis (0=X,1=Y,2=Z)."""
    def _f(x, y, z):
        p = [x - cx, y - cy, z - cz]
        ax = p[axis]
        # radial distance in the plane perpendicular to axis
        ra = p[(axis + 1) % 3]
        rb = p[(axis + 2) % 3]
        dr = math.sqrt(ra * ra + rb * rb) - radius
        dh = abs(ax) - half_height
        return min(max(dr, dh), 0.0) + _length3(max(dr, 0.0), max(dh, 0.0), 0.0)
    return _f


def sdf_torus(cx: float = 0.0, cy: float = 0.0, cz: float = 0.0,
              major_radius: float = 1.0, minor_radius: float = 0.25,
              axis: int = 2) -> SDF:
    """Signed-distance field of a torus; tube sweeps around the given axis."""
    def _f(x, y, z):
        p = [x - cx, y - cy, z - cz]
        # component along axis and in the plane
        ax_coord = p[axis]
        ra = p[(axis + 1) % 3]
        rb = p[(axis + 2) % 3]
        q_x = math.sqrt(ra * ra + rb * rb) - major_radius
        q_y = ax_coord
        return math.sqrt(q_x * q_x + q_y * q_y) - minor_radius
    return _f


def sdf_plane(nx: float = 0.0, ny: float = 0.0, nz: float = 1.0,
              d: float = 0.0) -> SDF:
    """Half-space SDF: n·p + d where n is the inward normal (pre-normalised)."""
    mag = _length3(nx, ny, nz)
    if mag < _EPS:
        # degenerate normal → trivially return 0-plane
        def _f0(x, y, z):  # noqa: E306
            return 0.0
        return _f0
    nnx, nny, nnz = nx / mag, ny / mag, nz / mag

    def _f(x, y, z):
        return nnx * x + nny * y + nnz * z + d
    return _f


# ---------------------------------------------------------------------------
# TPMS (Triply Periodic Minimal Surfaces)
# ---------------------------------------------------------------------------

def sdf_gyroid(period: float = 1.0, iso: float = 0.0) -> SDF:
    """Gyroid TPMS: sin(X)cos(Y) + sin(Y)cos(Z) + sin(Z)cos(X) = iso."""
    def _f(x, y, z):
        return _gyroid_field(x, y, z, period) - iso
    return _f


def sdf_schwarz_p(period: float = 1.0, iso: float = 0.0) -> SDF:
    """Schwarz-P TPMS: cos(X) + cos(Y) + cos(Z) = iso."""
    def _f(x, y, z):
        return _schwarz_p_field(x, y, z, period) - iso
    return _f


def sdf_diamond(period: float = 1.0, iso: float = 0.0) -> SDF:
    """Diamond (Schwarz-D) TPMS:
    sin(X)sin(Y)sin(Z) + sin(X)cos(Y)cos(Z) +
    cos(X)sin(Y)cos(Z) + cos(X)cos(Y)sin(Z) = iso."""
    def _f(x, y, z):
        return _diamond_field(x, y, z, period) - iso
    return _f


# ---------------------------------------------------------------------------
# CSG operations
# ---------------------------------------------------------------------------

def csg_union(a: SDF, b: SDF) -> SDF:
    """Boolean union: min(a, b)."""
    def _f(x, y, z):
        return min(a(x, y, z), b(x, y, z))
    return _f


def csg_intersection(a: SDF, b: SDF) -> SDF:
    """Boolean intersection: max(a, b)."""
    def _f(x, y, z):
        return max(a(x, y, z), b(x, y, z))
    return _f


def csg_difference(a: SDF, b: SDF) -> SDF:
    """Boolean difference (a − b): max(a, −b)."""
    def _f(x, y, z):
        return max(a(x, y, z), -b(x, y, z))
    return _f


def csg_smooth_union(a: SDF, b: SDF, k: float = 0.1) -> SDF:
    """Smooth (polynomial) union by Quilez; k controls blend radius.
    Returns a value ≤ min(a, b) in the blend zone."""
    def _f(x, y, z):
        da = a(x, y, z)
        db = b(x, y, z)
        h = _clamp(0.5 + 0.5 * (db - da) / max(k, _EPS), 0.0, 1.0)
        return da * (1.0 - h) + db * h - k * h * (1.0 - h)
    return _f


def csg_smooth_intersection(a: SDF, b: SDF, k: float = 0.1) -> SDF:
    """Smooth intersection."""
    def _f(x, y, z):
        da = a(x, y, z)
        db = b(x, y, z)
        h = _clamp(0.5 - 0.5 * (db - da) / max(k, _EPS), 0.0, 1.0)
        return da * (1.0 - h) + db * h + k * h * (1.0 - h)
    return _f


def csg_smooth_difference(a: SDF, b: SDF, k: float = 0.1) -> SDF:
    """Smooth difference."""
    def _f(x, y, z):
        da = a(x, y, z)
        db = -b(x, y, z)
        h = _clamp(0.5 - 0.5 * (db - da) / max(k, _EPS), 0.0, 1.0)
        return da * (1.0 - h) + db * h + k * h * (1.0 - h)
    return _f


# ---------------------------------------------------------------------------
# Transforms (return new SDF in transformed coordinate space)
# ---------------------------------------------------------------------------

def sdf_translate(f: SDF, tx: float, ty: float, tz: float) -> SDF:
    """Translate the SDF field by (tx, ty, tz)."""
    def _g(x, y, z):
        return f(x - tx, y - ty, z - tz)
    return _g


def sdf_scale(f: SDF, sx: float, sy: float = 0.0, sz: float = 0.0) -> SDF:
    """Uniform or non-uniform scale.  If sy and sz are 0, uses uniform scale sx."""
    if sy == 0.0 and sz == 0.0:
        # uniform
        s = sx
        def _gu(x, y, z):  # noqa: E306
            return f(x / s, y / s, z / s) * s
        return _gu
    # non-uniform (approximate; not an exact SDF but useful for modelling)
    def _g(x, y, z):
        return f(x / sx, y / sy, z / sz)
    return _g


def sdf_rotate_x(f: SDF, angle_rad: float) -> SDF:
    """Rotate field around the X-axis by angle_rad."""
    c, s = math.cos(angle_rad), math.sin(angle_rad)

    def _g(x, y, z):
        return f(x, c * y + s * z, -s * y + c * z)
    return _g


def sdf_rotate_y(f: SDF, angle_rad: float) -> SDF:
    """Rotate field around the Y-axis by angle_rad."""
    c, s = math.cos(angle_rad), math.sin(angle_rad)

    def _g(x, y, z):
        return f(c * x - s * z, y, s * x + c * z)
    return _g


def sdf_rotate_z(f: SDF, angle_rad: float) -> SDF:
    """Rotate field around the Z-axis by angle_rad."""
    c, s = math.cos(angle_rad), math.sin(angle_rad)

    def _g(x, y, z):
        return f(c * x + s * y, -s * x + c * y, z)
    return _g


# ---------------------------------------------------------------------------
# Shell / offset (isosurface shift)
# ---------------------------------------------------------------------------

def sdf_shell(f: SDF, thickness: float) -> SDF:
    """Hollow shell of given wall thickness around f's surface.
    Equivalent to the band |f| ≤ thickness/2 (approximate)."""
    half = thickness / 2.0

    def _g(x, y, z):
        return abs(f(x, y, z)) - half
    return _g


def sdf_offset(f: SDF, amount: float) -> SDF:
    """Offset the surface outward by *amount* (negative → inward)."""
    def _g(x, y, z):
        return f(x, y, z) - amount
    return _g


# ---------------------------------------------------------------------------
# TPMS infill / lattice helpers
# ---------------------------------------------------------------------------

def tpms_wall_thickness(period: float, relative_density: float,
                        surface: str = "gyroid") -> dict:
    """Estimate the iso-value that yields a target relative density for a TPMS.

    Uses empirical monotone mappings (Maskery et al. 2018):
      gyroid:   rho ≈ 0.5 - 0.5 * sin(pi/2 * (iso / 1.5))   clamped to [0,1]
      schwarz_p: rho ≈ 0.5 - iso / 2.6
      diamond:  same empirical fit as gyroid

    Returns {"ok": True, "iso_value": float, "effective_thickness": float}
    or {"ok": False, "reason": str}.

    *effective_thickness* is half-period * (approximate wall fraction in 1D).
    """
    try:
        if not (0.0 < relative_density < 1.0):
            return {"ok": False, "reason": "relative_density must be in (0, 1)"}
        if period <= 0.0:
            return {"ok": False, "reason": "period must be positive"}
        surface = surface.lower()

        if surface in ("gyroid", "diamond"):
            # Solve for iso: rho = 0.5 - 0.5*sin(pi/2 * iso/1.5)
            # sin(pi/2 * iso/1.5) = 1 - 2*rho
            arg = 1.0 - 2.0 * relative_density
            arg = _clamp(arg, -1.0, 1.0)
            iso = 1.5 * math.asin(arg) / (math.pi / 2.0)
        elif surface == "schwarz_p":
            # rho = 0.5 - iso/2.6  → iso = (0.5 - rho) * 2.6
            iso = (0.5 - relative_density) * 2.6
        else:
            return {"ok": False, "reason": f"unknown surface '{surface}'"}

        effective_thickness = period * relative_density * 0.5
        return {"ok": True, "iso_value": float(iso),
                "effective_thickness": float(effective_thickness)}
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


# ---------------------------------------------------------------------------
# Field sampling + gradient (numerical normal)
# ---------------------------------------------------------------------------

def sample_field(f: SDF,
                 x_range: Tuple[float, float],
                 y_range: Tuple[float, float],
                 z_range: Tuple[float, float],
                 nx: int, ny: int, nz: int) -> dict:
    """Sample the SDF on a regular grid.

    Returns {"ok": True, "values": [[[float]]]}, a 3-D list indexed [ix][iy][iz].
    Grid spacing is (x_range[1]-x_range[0])/(nx-1) etc.
    """
    try:
        if nx < 2 or ny < 2 or nz < 2:
            return {"ok": False, "reason": "nx, ny, nz must each be >= 2"}
        dx = (x_range[1] - x_range[0]) / (nx - 1)
        dy = (y_range[1] - y_range[0]) / (ny - 1)
        dz = (z_range[1] - z_range[0]) / (nz - 1)
        values = []
        for i in range(nx):
            col = []
            for j in range(ny):
                row = []
                for k in range(nz):
                    x = x_range[0] + i * dx
                    y = y_range[0] + j * dy
                    z = z_range[0] + k * dz
                    row.append(float(f(x, y, z)))
                col.append(row)
            values.append(col)
        return {"ok": True, "values": values,
                "shape": [nx, ny, nz],
                "origin": [x_range[0], y_range[0], z_range[0]],
                "spacing": [dx, dy, dz]}
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


def field_gradient(f: SDF, x: float, y: float, z: float,
                   eps: float = _EPS) -> Tuple[float, float, float]:
    """Central-difference gradient of f at (x, y, z).

    Returns (gx, gy, gz).  The normalised gradient is the surface normal
    (points outward from solid).
    """
    gx = (f(x + eps, y, z) - f(x - eps, y, z)) / (2.0 * eps)
    gy = (f(x, y + eps, z) - f(x, y - eps, z)) / (2.0 * eps)
    gz = (f(x, y, z + eps) - f(x, y, z - eps)) / (2.0 * eps)
    return gx, gy, gz


def surface_normal(f: SDF, x: float, y: float, z: float,
                   eps: float = _EPS) -> Tuple[float, float, float]:
    """Unit outward normal of f's surface at (x, y, z)."""
    gx, gy, gz = field_gradient(f, x, y, z, eps)
    mag = _length3(gx, gy, gz)
    if mag < _EPS:
        return (0.0, 0.0, 1.0)
    return gx / mag, gy / mag, gz / mag


# ---------------------------------------------------------------------------
# Bounding-box helper
# ---------------------------------------------------------------------------

def auto_bbox(f: SDF, max_radius: float = 10.0,
              samples: int = 6) -> Tuple[Tuple[float, float, float],
                                         Tuple[float, float, float]]:
    """Heuristic axis-aligned bounding box of f's zero-set.

    Samples a coarse grid in [-max_radius, max_radius]^3 to find the
    tightest box around cells that straddle the isosurface.  Returns
    (min_pt, max_pt).  If no cells straddle, returns the full cube.
    """
    r = max_radius
    step = 2 * r / samples
    mn = [r, r, r]
    mx = [-r, -r, -r]
    found = False
    x = -r
    while x <= r:
        y = -r
        while y <= r:
            z = -r
            while z <= r:
                v = f(x, y, z)
                if abs(v) < step * 1.5:
                    if x < mn[0]:
                        mn[0] = x
                    if y < mn[1]:
                        mn[1] = y
                    if z < mn[2]:
                        mn[2] = z
                    if x > mx[0]:
                        mx[0] = x
                    if y > mx[1]:
                        mx[1] = y
                    if z > mx[2]:
                        mx[2] = z
                    found = True
                z += step
            y += step
        x += step
    if not found:
        return (-r, -r, -r), (r, r, r)
    pad = step
    return (mn[0] - pad, mn[1] - pad, mn[2] - pad), (mx[0] + pad, mx[1] + pad, mx[2] + pad)


# ---------------------------------------------------------------------------
# Marching cubes
# ---------------------------------------------------------------------------

# Lookup tables (edge table + triangle table from the original Lorensen & Cline 1987 paper).

_EDGE_TABLE = [
    0x000, 0x109, 0x203, 0x30a, 0x406, 0x50f, 0x605, 0x70c,
    0x80c, 0x905, 0xa0f, 0xb06, 0xc0a, 0xd03, 0xe09, 0xf00,
    0x190, 0x099, 0x393, 0x29a, 0x596, 0x49f, 0x795, 0x69c,
    0x99c, 0x895, 0xb9f, 0xa96, 0xd9a, 0xc93, 0xf99, 0xe90,
    0x230, 0x339, 0x033, 0x13a, 0x636, 0x73f, 0x435, 0x53c,
    0xa3c, 0xb35, 0x83f, 0x936, 0xe3a, 0xf33, 0xc39, 0xd30,
    0x3a0, 0x2a9, 0x1a3, 0x0aa, 0x7a6, 0x6af, 0x5a5, 0x4ac,
    0xbac, 0xaa5, 0x9af, 0x8a6, 0xfaa, 0xea3, 0xda9, 0xca0,
    0x460, 0x569, 0x663, 0x76a, 0x066, 0x16f, 0x265, 0x36c,
    0xc6c, 0xd65, 0xe6f, 0xf66, 0x86a, 0x963, 0xa69, 0xb60,
    0x5f0, 0x4f9, 0x7f3, 0x6fa, 0x1f6, 0x0ff, 0x3f5, 0x2fc,
    0xdfc, 0xcf5, 0xfff, 0xef6, 0x9fa, 0x8f3, 0xbf9, 0xaf0,
    0x650, 0x759, 0x453, 0x55a, 0x256, 0x35f, 0x055, 0x15c,
    0xe5c, 0xf55, 0xc5f, 0xd56, 0xa5a, 0xb53, 0x859, 0x950,
    0x7c0, 0x6c9, 0x5c3, 0x4ca, 0x3c6, 0x2cf, 0x1c5, 0x0cc,
    0xfcc, 0xec5, 0xdcf, 0xcc6, 0xbca, 0xac3, 0x9c9, 0x8c0,
    0x8c0, 0x9c9, 0xac3, 0xbca, 0xcc6, 0xdcf, 0xec5, 0xfcc,
    0x0cc, 0x1c5, 0x2cf, 0x3c6, 0x4ca, 0x5c3, 0x6c9, 0x7c0,
    0x950, 0x859, 0xb53, 0xa5a, 0xd56, 0xc5f, 0xf55, 0xe5c,
    0x15c, 0x055, 0x35f, 0x256, 0x55a, 0x453, 0x759, 0x650,
    0xaf0, 0xbf9, 0x8f3, 0x9fa, 0xef6, 0xfff, 0xcf5, 0xdfc,
    0x2fc, 0x3f5, 0x0ff, 0x1f6, 0x6fa, 0x7f3, 0x4f9, 0x5f0,
    0xb60, 0xa69, 0x963, 0x86a, 0xf66, 0xe6f, 0xd65, 0xc6c,
    0x36c, 0x265, 0x16f, 0x066, 0x76a, 0x663, 0x569, 0x460,
    0xca0, 0xda9, 0xea3, 0xfaa, 0x8a6, 0x9af, 0xaa5, 0xbac,
    0x4ac, 0x5a5, 0x6af, 0x7a6, 0x0aa, 0x1a3, 0x2a9, 0x3a0,
    0xd30, 0xc39, 0xf33, 0xe3a, 0x936, 0x835, 0xb3f, 0xa36,  # noqa: E501 — corrected
    0x53c, 0x435, 0x73f, 0x636, 0x13a, 0x033, 0x339, 0x230,
    0xe90, 0xf99, 0xc93, 0xd9a, 0xa96, 0xb9f, 0x895, 0x99c,
    0x69c, 0x795, 0x49f, 0x596, 0x29a, 0x393, 0x099, 0x190,
    0xf00, 0xe09, 0xd03, 0xc0a, 0xb06, 0xa0f, 0x905, 0x80c,
    0x70c, 0x605, 0x50f, 0x406, 0x30a, 0x203, 0x109, 0x000,
]

# Triangle table: 256 entries × up to 16 ints (-1 = end sentinel)
_TRI_TABLE: List[List[int]] = [
    [],
    [0, 8, 3],
    [0, 1, 9],
    [1, 8, 3, 9, 8, 1],
    [1, 2, 10],
    [0, 8, 3, 1, 2, 10],
    [9, 2, 10, 0, 2, 9],
    [2, 8, 3, 2, 10, 8, 10, 9, 8],
    [3, 11, 2],
    [0, 11, 2, 8, 11, 0],
    [1, 9, 0, 2, 3, 11],
    [1, 11, 2, 1, 9, 11, 9, 8, 11],
    [3, 10, 1, 11, 10, 3],
    [0, 10, 1, 0, 8, 10, 8, 11, 10],
    [3, 9, 0, 3, 11, 9, 11, 10, 9],
    [9, 8, 10, 10, 8, 11],
    [4, 7, 8],
    [4, 3, 0, 7, 3, 4],
    [0, 1, 9, 8, 4, 7],
    [4, 1, 9, 4, 7, 1, 7, 3, 1],
    [1, 2, 10, 8, 4, 7],
    [3, 4, 7, 3, 0, 4, 1, 2, 10],
    [9, 2, 10, 9, 0, 2, 8, 4, 7],
    [2, 10, 9, 2, 9, 7, 2, 7, 3, 7, 9, 4],
    [8, 4, 7, 3, 11, 2],
    [11, 4, 7, 11, 2, 4, 2, 0, 4],
    [9, 0, 1, 8, 4, 7, 2, 3, 11],
    [4, 7, 11, 9, 4, 11, 9, 11, 2, 9, 2, 1],
    [3, 10, 1, 3, 11, 10, 7, 8, 4],
    [1, 11, 10, 1, 4, 11, 1, 0, 4, 7, 11, 4],
    [4, 7, 8, 9, 0, 11, 9, 11, 10, 11, 0, 3],
    [4, 7, 11, 4, 11, 9, 9, 11, 10],
    [9, 5, 4],
    [9, 5, 4, 0, 8, 3],
    [0, 5, 4, 1, 5, 0],
    [8, 5, 4, 8, 3, 5, 3, 1, 5],
    [1, 2, 10, 9, 5, 4],
    [3, 0, 8, 1, 2, 10, 4, 9, 5],
    [5, 2, 10, 5, 4, 2, 4, 0, 2],
    [2, 10, 5, 3, 2, 5, 3, 5, 4, 3, 4, 8],
    [9, 5, 4, 2, 3, 11],
    [0, 11, 2, 0, 8, 11, 4, 9, 5],
    [0, 5, 4, 0, 1, 5, 2, 3, 11],
    [2, 1, 5, 2, 5, 8, 2, 8, 11, 4, 8, 5],
    [10, 3, 11, 10, 1, 3, 9, 5, 4],
    [4, 9, 5, 0, 8, 1, 8, 10, 1, 8, 11, 10],
    [5, 4, 0, 5, 0, 11, 5, 11, 10, 11, 0, 3],
    [5, 4, 8, 5, 8, 10, 10, 8, 11],
    [9, 7, 8, 5, 7, 9],
    [9, 3, 0, 9, 5, 3, 5, 7, 3],
    [0, 7, 8, 0, 1, 7, 1, 5, 7],
    [1, 5, 3, 3, 5, 7],
    [9, 7, 8, 9, 5, 7, 10, 1, 2],
    [10, 1, 2, 9, 5, 0, 5, 3, 0, 5, 7, 3],
    [8, 0, 2, 8, 2, 5, 8, 5, 7, 10, 5, 2],
    [2, 10, 5, 2, 5, 3, 3, 5, 7],
    [7, 9, 5, 7, 8, 9, 3, 11, 2],
    [9, 5, 7, 9, 7, 2, 9, 2, 0, 2, 7, 11],
    [2, 3, 11, 0, 1, 8, 1, 7, 8, 1, 5, 7],
    [11, 2, 1, 11, 1, 7, 7, 1, 5],
    [9, 5, 8, 8, 5, 7, 10, 1, 3, 10, 3, 11],
    [5, 7, 0, 5, 0, 9, 7, 11, 0, 1, 0, 10, 11, 10, 0],
    [11, 10, 0, 11, 0, 3, 10, 5, 0, 8, 0, 7, 5, 7, 0],
    [11, 10, 5, 7, 11, 5],
    [10, 6, 5],
    [0, 8, 3, 5, 10, 6],
    [9, 0, 1, 5, 10, 6],
    [1, 8, 3, 1, 9, 8, 5, 10, 6],
    [1, 6, 5, 2, 6, 1],
    [1, 6, 5, 1, 2, 6, 3, 0, 8],
    [9, 6, 5, 9, 0, 6, 0, 2, 6],
    [5, 9, 8, 5, 8, 2, 5, 2, 6, 3, 2, 8],
    [2, 3, 11, 10, 6, 5],
    [11, 0, 8, 11, 2, 0, 10, 6, 5],
    [0, 1, 9, 2, 3, 11, 5, 10, 6],
    [5, 10, 6, 1, 9, 2, 9, 11, 2, 9, 8, 11],
    [6, 3, 11, 6, 5, 3, 5, 1, 3],
    [0, 8, 11, 0, 11, 5, 0, 5, 1, 5, 11, 6],
    [3, 11, 6, 0, 3, 6, 0, 6, 5, 0, 5, 9],
    [6, 5, 9, 6, 9, 11, 11, 9, 8],
    [5, 10, 6, 4, 7, 8],
    [4, 3, 0, 4, 7, 3, 6, 5, 10],
    [1, 9, 0, 5, 10, 6, 8, 4, 7],
    [10, 6, 5, 1, 9, 7, 1, 7, 3, 7, 9, 4],
    [6, 1, 2, 6, 5, 1, 4, 7, 8],
    [1, 2, 5, 5, 2, 6, 3, 0, 4, 3, 4, 7],
    [8, 4, 7, 9, 0, 5, 0, 6, 5, 0, 2, 6],
    [7, 3, 9, 7, 9, 4, 3, 2, 9, 5, 9, 6, 2, 6, 9],
    [3, 11, 2, 7, 8, 4, 10, 6, 5],
    [5, 10, 6, 4, 7, 2, 4, 2, 0, 2, 7, 11],
    [0, 1, 9, 4, 7, 8, 2, 3, 11, 5, 10, 6],
    [9, 2, 1, 9, 11, 2, 9, 4, 11, 7, 11, 4, 5, 10, 6],
    [8, 4, 7, 3, 11, 5, 3, 5, 1, 5, 11, 6],
    [5, 1, 11, 5, 11, 6, 1, 0, 11, 7, 11, 4, 0, 4, 11],
    [0, 5, 9, 0, 6, 5, 0, 3, 6, 11, 6, 3, 8, 4, 7],
    [6, 5, 9, 6, 9, 11, 4, 7, 9, 7, 11, 9],
    [10, 4, 9, 6, 4, 10],
    [4, 10, 6, 4, 9, 10, 0, 8, 3],
    [10, 0, 1, 10, 6, 0, 6, 4, 0],
    [8, 3, 1, 8, 1, 6, 8, 6, 4, 6, 1, 10],
    [1, 4, 9, 1, 2, 4, 2, 6, 4],
    [3, 0, 8, 1, 2, 9, 2, 4, 9, 2, 6, 4],
    [0, 2, 4, 4, 2, 6],
    [8, 3, 2, 8, 2, 4, 4, 2, 6],
    [10, 4, 9, 10, 6, 4, 11, 2, 3],
    [0, 8, 2, 2, 8, 11, 4, 9, 10, 4, 10, 6],
    [3, 11, 2, 0, 1, 6, 0, 6, 4, 6, 1, 10],
    [6, 4, 1, 6, 1, 10, 4, 8, 1, 2, 1, 11, 8, 11, 1],
    [9, 6, 4, 9, 3, 6, 9, 1, 3, 11, 6, 3],
    [8, 11, 1, 8, 1, 0, 11, 6, 1, 9, 1, 4, 6, 4, 1],
    [3, 11, 6, 3, 6, 0, 0, 6, 4],
    [6, 4, 8, 11, 6, 8],
    [7, 10, 6, 7, 8, 10, 8, 9, 10],
    [0, 7, 3, 0, 10, 7, 0, 9, 10, 6, 7, 10],
    [10, 6, 7, 1, 10, 7, 1, 7, 8, 1, 8, 0],
    [10, 6, 7, 10, 7, 1, 1, 7, 3],
    [1, 2, 6, 1, 6, 8, 1, 8, 9, 8, 6, 7],
    [2, 6, 9, 2, 9, 1, 6, 7, 9, 0, 9, 3, 7, 3, 9],
    [7, 8, 0, 7, 0, 6, 6, 0, 2],
    [7, 3, 2, 6, 7, 2],
    [2, 3, 11, 10, 6, 8, 10, 8, 9, 8, 6, 7],
    [2, 0, 7, 2, 7, 11, 0, 9, 7, 6, 7, 10, 9, 10, 7],
    [1, 8, 0, 1, 7, 8, 1, 10, 7, 6, 7, 10, 2, 3, 11],
    [11, 2, 1, 11, 1, 7, 10, 6, 1, 6, 7, 1],
    [8, 9, 6, 8, 6, 7, 9, 1, 6, 11, 6, 3, 1, 3, 6],
    [0, 9, 1, 11, 6, 7],
    [7, 8, 0, 7, 0, 6, 3, 11, 0, 11, 6, 0],
    [7, 11, 6],
    [7, 6, 11],
    [3, 0, 8, 11, 7, 6],
    [0, 1, 9, 11, 7, 6],
    [8, 1, 9, 8, 3, 1, 11, 7, 6],
    [10, 1, 2, 6, 11, 7],
    [1, 2, 10, 3, 0, 8, 6, 11, 7],
    [2, 9, 0, 2, 10, 9, 6, 11, 7],
    [6, 11, 7, 2, 10, 3, 10, 8, 3, 10, 9, 8],
    [7, 2, 3, 6, 2, 7],
    [7, 0, 8, 7, 6, 0, 6, 2, 0],
    [2, 7, 6, 2, 3, 7, 0, 1, 9],
    [1, 6, 2, 1, 8, 6, 1, 9, 8, 8, 7, 6],
    [10, 7, 6, 10, 1, 7, 1, 3, 7],
    [10, 7, 6, 1, 7, 10, 1, 8, 7, 1, 0, 8],
    [0, 3, 7, 0, 7, 10, 0, 10, 9, 6, 10, 7],
    [7, 6, 10, 7, 10, 8, 8, 10, 9],
    [6, 8, 4, 11, 8, 6],
    [3, 6, 11, 3, 0, 6, 0, 4, 6],
    [8, 6, 11, 8, 4, 6, 9, 0, 1],
    [9, 4, 6, 9, 6, 3, 9, 3, 1, 11, 3, 6],
    [6, 8, 4, 6, 11, 8, 2, 10, 1],
    [1, 2, 10, 3, 0, 11, 0, 6, 11, 0, 4, 6],
    [4, 11, 8, 4, 6, 11, 0, 2, 9, 2, 10, 9],
    [10, 9, 3, 10, 3, 2, 9, 4, 3, 11, 3, 6, 4, 6, 3],
    [8, 2, 3, 8, 4, 2, 4, 6, 2],
    [0, 4, 2, 4, 6, 2],
    [1, 9, 0, 2, 3, 4, 2, 4, 6, 4, 3, 8],
    [1, 9, 4, 1, 4, 2, 2, 4, 6],
    [8, 1, 3, 8, 6, 1, 8, 4, 6, 6, 10, 1],
    [10, 1, 0, 10, 0, 6, 6, 0, 4],
    [4, 6, 3, 4, 3, 8, 6, 10, 3, 0, 3, 9, 10, 9, 3],
    [10, 9, 4, 6, 10, 4],
    [4, 9, 5, 7, 6, 11],
    [0, 8, 3, 4, 9, 5, 11, 7, 6],
    [5, 0, 1, 5, 4, 0, 7, 6, 11],
    [11, 7, 6, 8, 3, 4, 3, 5, 4, 3, 1, 5],
    [9, 5, 4, 10, 1, 2, 7, 6, 11],
    [6, 11, 7, 1, 2, 10, 0, 8, 3, 4, 9, 5],
    [7, 6, 11, 5, 4, 10, 4, 2, 10, 4, 0, 2],
    [3, 4, 8, 3, 5, 4, 3, 2, 5, 10, 5, 2, 11, 7, 6],
    [7, 2, 3, 7, 6, 2, 5, 4, 9],
    [9, 5, 4, 0, 8, 6, 0, 6, 2, 6, 8, 7],
    [3, 6, 2, 3, 7, 6, 1, 5, 0, 5, 4, 0],
    [6, 2, 8, 6, 8, 7, 2, 1, 8, 4, 8, 5, 1, 5, 8],
    [9, 5, 4, 10, 1, 6, 1, 7, 6, 1, 3, 7],
    [1, 6, 10, 1, 7, 6, 1, 0, 7, 8, 7, 0, 9, 5, 4],
    [4, 0, 10, 4, 10, 5, 0, 3, 10, 6, 10, 7, 3, 7, 10],
    [7, 6, 10, 7, 10, 8, 5, 4, 10, 4, 8, 10],
    [6, 9, 5, 6, 11, 9, 11, 8, 9],
    [3, 6, 11, 0, 6, 3, 0, 5, 6, 0, 9, 5],
    [0, 11, 8, 0, 5, 11, 0, 1, 5, 5, 6, 11],
    [6, 11, 3, 6, 3, 5, 5, 3, 1],
    [1, 2, 10, 9, 5, 11, 9, 11, 8, 11, 5, 6],
    [0, 11, 3, 0, 6, 11, 0, 9, 6, 5, 6, 9, 1, 2, 10],
    [11, 8, 5, 11, 5, 6, 8, 0, 5, 10, 5, 2, 0, 2, 5],
    [6, 11, 3, 6, 3, 5, 2, 10, 3, 10, 5, 3],
    [5, 8, 9, 5, 2, 8, 5, 6, 2, 3, 8, 2],
    [9, 5, 6, 9, 6, 0, 0, 6, 2],
    [1, 5, 8, 1, 8, 0, 5, 6, 8, 3, 8, 2, 6, 2, 8],
    [1, 5, 6, 2, 1, 6],
    [1, 3, 6, 1, 6, 10, 3, 8, 6, 5, 6, 9, 8, 9, 6],
    [10, 1, 0, 10, 0, 6, 9, 5, 0, 5, 6, 0],
    [0, 3, 8, 5, 6, 10],
    [10, 5, 6],
    [11, 5, 10, 7, 5, 11],
    [11, 5, 10, 11, 7, 5, 8, 3, 0],
    [5, 11, 7, 5, 10, 11, 1, 9, 0],
    [10, 7, 5, 10, 11, 7, 9, 8, 1, 8, 3, 1],
    [11, 1, 2, 11, 7, 1, 7, 5, 1],
    [0, 8, 3, 1, 2, 7, 1, 7, 5, 7, 2, 11],
    [9, 7, 5, 9, 2, 7, 9, 0, 2, 2, 11, 7],
    [7, 5, 2, 7, 2, 11, 5, 9, 2, 3, 2, 8, 9, 8, 2],
    [2, 5, 10, 2, 3, 5, 3, 7, 5],
    [8, 2, 0, 8, 5, 2, 8, 7, 5, 10, 2, 5],
    [9, 0, 1, 5, 10, 3, 5, 3, 7, 3, 10, 2],
    [9, 8, 2, 9, 2, 1, 8, 7, 2, 10, 2, 5, 7, 5, 2],
    [1, 3, 5, 3, 7, 5],
    [0, 8, 7, 0, 7, 1, 1, 7, 5],
    [9, 0, 3, 9, 3, 5, 5, 3, 7],
    [9, 8, 7, 5, 9, 7],
    [5, 8, 4, 5, 10, 8, 10, 11, 8],
    [5, 0, 4, 5, 11, 0, 5, 10, 11, 11, 3, 0],
    [0, 1, 9, 8, 4, 10, 8, 10, 11, 10, 4, 5],
    [10, 11, 4, 10, 4, 5, 11, 3, 4, 9, 4, 1, 3, 1, 4],
    [2, 5, 1, 2, 8, 5, 2, 11, 8, 4, 5, 8],
    [0, 4, 11, 0, 11, 3, 4, 5, 11, 2, 11, 1, 5, 1, 11],
    [0, 2, 5, 0, 5, 9, 2, 11, 5, 4, 5, 8, 11, 8, 5],
    [9, 4, 5, 2, 11, 3],
    [2, 5, 10, 3, 5, 2, 3, 4, 5, 3, 8, 4],
    [5, 10, 2, 5, 2, 4, 4, 2, 0],
    [3, 10, 2, 3, 5, 10, 3, 8, 5, 4, 5, 8, 0, 1, 9],
    [5, 10, 2, 5, 2, 4, 1, 9, 2, 9, 4, 2],
    [8, 4, 5, 8, 5, 3, 3, 5, 1],
    [0, 4, 5, 1, 0, 5],
    [8, 4, 5, 8, 5, 3, 9, 0, 5, 0, 3, 5],
    [9, 4, 5],
    [4, 11, 7, 4, 9, 11, 9, 10, 11],
    [0, 8, 3, 4, 9, 7, 9, 11, 7, 9, 10, 11],
    [1, 10, 11, 1, 11, 4, 1, 4, 0, 7, 4, 11],
    [3, 1, 4, 3, 4, 8, 1, 10, 4, 7, 4, 11, 10, 11, 4],
    [4, 11, 7, 9, 11, 4, 9, 2, 11, 9, 1, 2],
    [9, 7, 4, 9, 11, 7, 9, 1, 11, 2, 11, 1, 0, 8, 3],
    [11, 7, 4, 11, 4, 2, 2, 4, 0],
    [11, 7, 4, 11, 4, 2, 8, 3, 4, 3, 2, 4],
    [2, 9, 10, 2, 7, 9, 2, 3, 7, 7, 4, 9],
    [9, 10, 7, 9, 7, 4, 10, 2, 7, 8, 7, 0, 2, 0, 7],
    [3, 7, 10, 3, 10, 2, 7, 4, 10, 1, 10, 0, 4, 0, 10],
    [1, 10, 2, 8, 7, 4],
    [4, 9, 1, 4, 1, 7, 7, 1, 3],
    [4, 9, 1, 4, 1, 7, 0, 8, 1, 8, 7, 1],
    [4, 0, 3, 7, 4, 3],
    [4, 8, 7],
    [9, 10, 8, 10, 11, 8],
    [3, 0, 9, 3, 9, 11, 11, 9, 10],
    [0, 1, 10, 0, 10, 8, 8, 10, 11],
    [3, 1, 10, 11, 3, 10],
    [1, 2, 11, 1, 11, 9, 9, 11, 8],
    [3, 0, 9, 3, 9, 11, 1, 2, 9, 2, 11, 9],
    [0, 2, 11, 8, 0, 11],
    [3, 2, 11],
    [2, 3, 8, 2, 8, 10, 10, 8, 9],
    [9, 10, 2, 0, 9, 2],
    [2, 3, 8, 2, 8, 10, 0, 1, 8, 1, 10, 8],
    [1, 10, 2],
    [1, 3, 8, 9, 1, 8],
    [0, 9, 1],
    [0, 3, 8],
    [],
]

# Cube vertex offsets (0..7)
_CUBE_VERTS = [
    (0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
    (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1),
]

# Cube edge pairs (v0, v1)
_CUBE_EDGES = [
    (0, 1), (1, 2), (2, 3), (3, 0),
    (4, 5), (5, 6), (6, 7), (7, 4),
    (0, 4), (1, 5), (2, 6), (3, 7),
]


def _lerp_edge(x0, y0, z0, v0, x1, y1, z1, v1):
    """Linear interpolation along an edge to find the zero crossing."""
    if abs(v1 - v0) < _EPS:
        t = 0.5
    else:
        t = -v0 / (v1 - v0)
    t = _clamp(t, 0.0, 1.0)
    return x0 + t * (x1 - x0), y0 + t * (y1 - y0), z0 + t * (z1 - z0)


def marching_cubes(f: SDF,
                   x_range: Tuple[float, float],
                   y_range: Tuple[float, float],
                   z_range: Tuple[float, float],
                   nx: int = 32, ny: int = 32, nz: int = 32,
                   iso: float = 0.0) -> dict:
    """Extract an isosurface mesh from an SDF using marching cubes.

    Parameters
    ----------
    f        : SDF callable
    x_range  : (x_min, x_max)
    y_range  : (y_min, y_max)
    z_range  : (z_min, z_max)
    nx,ny,nz : number of *cells* along each axis (vertices = n+1)
    iso      : isovalue (default 0 for SDF surface)

    Returns
    -------
    {"ok": True,
     "vertices": [[x,y,z], ...],   # float triples
     "faces":    [[i,j,k], ...]    # int triples (0-indexed)
    }
    or {"ok": False, "reason": str}
    """
    try:
        if nx < 1 or ny < 1 or nz < 1:
            return {"ok": False, "reason": "nx, ny, nz must be >= 1"}

        dx = (x_range[1] - x_range[0]) / nx
        dy = (y_range[1] - y_range[0]) / ny
        dz = (z_range[1] - z_range[0]) / nz

        # Pre-sample entire grid (nx+1) × (ny+1) × (nz+1)
        gx = nx + 1
        gy = ny + 1
        gz = nz + 1
        grid: List[float] = []
        for i in range(gx):
            for j in range(gy):
                for k in range(gz):
                    x = x_range[0] + i * dx
                    y = y_range[0] + j * dy
                    z = z_range[0] + k * dz
                    grid.append(f(x, y, z) - iso)

        def _idx(i, j, k):
            return i * (gy * gz) + j * gz + k

        verts: Verts = []
        faces: Faces = []
        # Edge → vertex index cache to share vertices on shared edges
        edge_cache: dict = {}

        def _vert_on_edge(ci, cj, ck, e):
            key = (ci, cj, ck, e)
            if key in edge_cache:
                return edge_cache[key]
            v0i, v1i = _CUBE_EDGES[e]
            di0, dj0, dk0 = _CUBE_VERTS[v0i]
            di1, dj1, dk1 = _CUBE_VERTS[v1i]
            i0, j0, k0 = ci + di0, cj + dj0, ck + dk0
            i1, j1, k1 = ci + di1, cj + dj1, ck + dk1
            val0 = grid[_idx(i0, j0, k0)]
            val1 = grid[_idx(i1, j1, k1)]
            x0 = x_range[0] + i0 * dx
            y0 = y_range[0] + j0 * dy
            z0 = z_range[0] + k0 * dz
            x1 = x_range[0] + i1 * dx
            y1 = y_range[0] + j1 * dy
            z1 = z_range[0] + k1 * dz
            px, py, pz = _lerp_edge(x0, y0, z0, val0, x1, y1, z1, val1)
            vidx = len(verts)
            verts.append((px, py, pz))
            edge_cache[key] = vidx
            return vidx

        for ci in range(nx):
            for cj in range(ny):
                for ck in range(nz):
                    # Build cube index
                    cube_index = 0
                    for vi, (di, dj, dk) in enumerate(_CUBE_VERTS):
                        if grid[_idx(ci + di, cj + dj, ck + dk)] < 0.0:
                            cube_index |= (1 << vi)

                    et = _EDGE_TABLE[cube_index]
                    if et == 0:
                        continue

                    tris = _TRI_TABLE[cube_index]
                    for t in range(0, len(tris), 3):
                        e0, e1, e2 = tris[t], tris[t + 1], tris[t + 2]
                        v0 = _vert_on_edge(ci, cj, ck, e0)
                        v1 = _vert_on_edge(ci, cj, ck, e1)
                        v2 = _vert_on_edge(ci, cj, ck, e2)
                        faces.append((v0, v1, v2))

        return {
            "ok": True,
            "vertices": [[p[0], p[1], p[2]] for p in verts],
            "faces": [[f_[0], f_[1], f_[2]] for f_ in faces],
            "vertex_count": len(verts),
            "face_count": len(faces),
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


# ---------------------------------------------------------------------------
# Volume & surface area via field integration
# ---------------------------------------------------------------------------

def field_volume(f: SDF,
                 x_range: Tuple[float, float],
                 y_range: Tuple[float, float],
                 z_range: Tuple[float, float],
                 nx: int = 32, ny: int = 32, nz: int = 32) -> dict:
    """Estimate enclosed volume by counting voxels with f < 0.

    Returns {"ok": True, "volume": float, "voxel_count": int,
             "voxel_volume": float}
    """
    try:
        if nx < 1 or ny < 1 or nz < 1:
            return {"ok": False, "reason": "nx, ny, nz must be >= 1"}
        dx = (x_range[1] - x_range[0]) / nx
        dy = (y_range[1] - y_range[0]) / ny
        dz = (z_range[1] - z_range[0]) / nz
        vox_vol = dx * dy * dz
        count = 0
        for i in range(nx):
            for j in range(ny):
                for k in range(nz):
                    # sample at voxel centre
                    x = x_range[0] + (i + 0.5) * dx
                    y = y_range[0] + (j + 0.5) * dy
                    z = z_range[0] + (k + 0.5) * dz
                    if f(x, y, z) < 0.0:
                        count += 1
        return {"ok": True, "volume": float(count * vox_vol),
                "voxel_count": count, "voxel_volume": float(vox_vol)}
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


def field_surface_area(f: SDF,
                       x_range: Tuple[float, float],
                       y_range: Tuple[float, float],
                       z_range: Tuple[float, float],
                       nx: int = 32, ny: int = 32, nz: int = 32) -> dict:
    """Estimate surface area via marching-cubes triangle areas.

    Returns {"ok": True, "surface_area": float}.
    """
    try:
        mesh = marching_cubes(f, x_range, y_range, z_range, nx, ny, nz)
        if not mesh["ok"]:
            return mesh
        verts = mesh["vertices"]
        faces = mesh["faces"]
        total = 0.0
        for tri in faces:
            ax, ay, az = verts[tri[0]]
            bx, by, bz = verts[tri[1]]
            cx_, cy_, cz_ = verts[tri[2]]
            # cross product of (b-a) x (c-a)
            ux, uy, uz = bx - ax, by - ay, bz - az
            vx_, vy_, vz_ = cx_ - ax, cy_ - ay, cz_ - az
            cx_v = uy * vz_ - uz * vy_
            cy_v = uz * vx_ - ux * vz_
            cz_v = ux * vy_ - uy * vx_
            total += 0.5 * _length3(cx_v, cy_v, cz_v)
        return {"ok": True, "surface_area": float(total)}
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


# ---------------------------------------------------------------------------
# LLM tool wrappers
# ---------------------------------------------------------------------------

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register  # type: ignore[import]
    from kerf_core.utils.context import ProjectCtx  # type: ignore[import]
    _REGISTRY_AVAILABLE = True
except ImportError:
    _REGISTRY_AVAILABLE = False

if _REGISTRY_AVAILABLE:

    # ------------------------------------------------------------------ #
    # frep_sphere_sdf                                                      #
    # ------------------------------------------------------------------ #
    _sphere_spec = ToolSpec(
        name="frep_sphere_sdf",
        description=(
            "Evaluate the signed-distance-field of a sphere at one or more sample points.\n"
            "\n"
            "Returns {ok:true, results:[{x,y,z,distance},...]} where distance < 0 is inside.\n"
            "Errors: {ok:false, reason} — never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "center": {"type": "array", "items": {"type": "number"},
                           "description": "[cx, cy, cz]"},
                "radius": {"type": "number"},
                "points": {"type": "array",
                           "items": {"type": "array",
                                     "items": {"type": "number"}},
                           "description": "List of [x, y, z] sample points."},
            },
            "required": ["center", "radius", "points"],
        },
    )

    @register(_sphere_spec, write=False)
    async def run_frep_sphere_sdf(ctx: ProjectCtx, args: bytes) -> str:
        try:
            a = json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
        try:
            cx, cy, cz = float(a["center"][0]), float(a["center"][1]), float(a["center"][2])
            r = float(a["radius"])
            if r <= 0:
                return err_payload("radius must be positive", "BAD_ARGS")
            sdf = sdf_sphere(cx, cy, cz, r)
            results = []
            for pt in a["points"]:
                x, y, z = float(pt[0]), float(pt[1]), float(pt[2])
                results.append({"x": x, "y": y, "z": z, "distance": sdf(x, y, z)})
            return ok_payload({"results": results})
        except Exception as exc:
            return err_payload(str(exc), "INTERNAL")

    # ------------------------------------------------------------------ #
    # frep_box_sdf                                                         #
    # ------------------------------------------------------------------ #
    _box_spec = ToolSpec(
        name="frep_box_sdf",
        description=(
            "Evaluate the signed-distance-field of an axis-aligned box.\n"
            "center=[cx,cy,cz], half_extents=[hx,hy,hz], points=[[x,y,z]...].\n"
            "Returns {ok:true, results:[{x,y,z,distance},...]}."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "center": {"type": "array", "items": {"type": "number"}},
                "half_extents": {"type": "array", "items": {"type": "number"},
                                 "description": "[hx, hy, hz]"},
                "points": {"type": "array",
                           "items": {"type": "array", "items": {"type": "number"}}},
            },
            "required": ["center", "half_extents", "points"],
        },
    )

    @register(_box_spec, write=False)
    async def run_frep_box_sdf(ctx: ProjectCtx, args: bytes) -> str:
        try:
            a = json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
        try:
            cx, cy, cz = float(a["center"][0]), float(a["center"][1]), float(a["center"][2])
            hx, hy, hz = (float(a["half_extents"][0]), float(a["half_extents"][1]),
                          float(a["half_extents"][2]))
            sdf = sdf_box(cx, cy, cz, hx, hy, hz)
            results = []
            for pt in a["points"]:
                x, y, z = float(pt[0]), float(pt[1]), float(pt[2])
                results.append({"x": x, "y": y, "z": z, "distance": sdf(x, y, z)})
            return ok_payload({"results": results})
        except Exception as exc:
            return err_payload(str(exc), "INTERNAL")

    # ------------------------------------------------------------------ #
    # frep_csg_union                                                       #
    # ------------------------------------------------------------------ #
    _csg_union_spec = ToolSpec(
        name="frep_csg_describe",
        description=(
            "Describe a CSG expression tree and return its string representation.\n"
            "Supported ops: union, intersection, difference, smooth_union.\n"
            "Primitives: sphere, box, cylinder, torus.\n"
            "Returns {ok:true, expression:str, op_count:int}."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Human-readable CSG expression, e.g. 'union(sphere(r=1), box(h=0.5))'",
                },
            },
            "required": ["expression"],
        },
    )

    @register(_csg_union_spec, write=False)
    async def run_frep_csg_describe(ctx: ProjectCtx, args: bytes) -> str:
        try:
            a = json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
        expr = a.get("expression", "")
        ops = sum(1 for kw in ("union", "intersection", "difference", "smooth")
                  if kw in expr.lower())
        return ok_payload({"expression": expr, "op_count": ops})

    # ------------------------------------------------------------------ #
    # frep_marching_cubes                                                  #
    # ------------------------------------------------------------------ #
    _mc_spec = ToolSpec(
        name="frep_marching_cubes",
        description=(
            "Extract an isosurface mesh from a named SDF primitive using marching cubes.\n"
            "primitive: 'sphere' | 'box' | 'cylinder' | 'torus' | 'gyroid' | 'schwarz_p' | 'diamond'.\n"
            "Returns {ok:true, vertex_count:int, face_count:int, volume_estimate:float}."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "primitive": {"type": "string"},
                "params": {"type": "object",
                           "description": "Primitive parameters dict, e.g. {radius:1.0}"},
                "resolution": {"type": "integer",
                               "description": "Grid cells per axis (default 16)."},
                "bbox_half": {"type": "number",
                              "description": "Half-width of sampling box (default 1.5)."},
            },
            "required": ["primitive"],
        },
    )

    @register(_mc_spec, write=False)
    async def run_frep_marching_cubes(ctx: ProjectCtx, args: bytes) -> str:
        try:
            a = json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
        try:
            prim = a.get("primitive", "sphere").lower()
            params = a.get("params", {})
            res = int(a.get("resolution", 16))
            half = float(a.get("bbox_half", 1.5))
            rng = (-half, half)

            if prim == "sphere":
                r = float(params.get("radius", 1.0))
                sdf = sdf_sphere(0, 0, 0, r)
            elif prim == "box":
                hx = float(params.get("hx", 1.0))
                hy = float(params.get("hy", 1.0))
                hz = float(params.get("hz", 1.0))
                sdf = sdf_box(0, 0, 0, hx, hy, hz)
            elif prim == "cylinder":
                r = float(params.get("radius", 1.0))
                hh = float(params.get("half_height", 1.0))
                sdf = sdf_cylinder(0, 0, 0, r, hh)
            elif prim == "torus":
                maj = float(params.get("major_radius", 1.0))
                mn = float(params.get("minor_radius", 0.25))
                sdf = sdf_torus(0, 0, 0, maj, mn)
            elif prim == "gyroid":
                period = float(params.get("period", 2.0))
                iso = float(params.get("iso", 0.0))
                sdf = sdf_gyroid(period, iso)
            elif prim == "schwarz_p":
                period = float(params.get("period", 2.0))
                iso = float(params.get("iso", 0.0))
                sdf = sdf_schwarz_p(period, iso)
            elif prim == "diamond":
                period = float(params.get("period", 2.0))
                iso = float(params.get("iso", 0.0))
                sdf = sdf_diamond(period, iso)
            else:
                return err_payload(f"unknown primitive '{prim}'", "BAD_ARGS")

            mesh = marching_cubes(sdf, rng, rng, rng, res, res, res)
            if not mesh["ok"]:
                return json.dumps(mesh)

            # Quick volume estimate
            vol_res = min(res, 20)
            vol = field_volume(sdf, rng, rng, rng, vol_res, vol_res, vol_res)
            vol_val = vol.get("volume", 0.0) if vol["ok"] else 0.0

            return ok_payload({
                "vertex_count": mesh["vertex_count"],
                "face_count": mesh["face_count"],
                "volume_estimate": vol_val,
            })
        except Exception as exc:
            return err_payload(str(exc), "INTERNAL")

    # ------------------------------------------------------------------ #
    # frep_tpms_infill                                                     #
    # ------------------------------------------------------------------ #
    _tpms_spec = ToolSpec(
        name="frep_tpms_infill",
        description=(
            "Compute the iso-value and effective wall thickness for a TPMS infill\n"
            "at a target relative density.\n"
            "surface: 'gyroid' | 'schwarz_p' | 'diamond'.\n"
            "Returns {ok:true, iso_value:float, effective_thickness:float}."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "surface": {"type": "string"},
                "period": {"type": "number"},
                "relative_density": {"type": "number",
                                     "description": "Volume fraction in (0, 1)."},
            },
            "required": ["surface", "period", "relative_density"],
        },
    )

    @register(_tpms_spec, write=False)
    async def run_frep_tpms_infill(ctx: ProjectCtx, args: bytes) -> str:
        try:
            a = json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
        result = tpms_wall_thickness(
            float(a.get("period", 1.0)),
            float(a.get("relative_density", 0.3)),
            str(a.get("surface", "gyroid")),
        )
        return ok_payload(result) if result["ok"] else json.dumps(result)

    # ------------------------------------------------------------------ #
    # frep_field_gradient                                                  #
    # ------------------------------------------------------------------ #
    _grad_spec = ToolSpec(
        name="frep_field_gradient",
        description=(
            "Compute the numerical gradient (surface normal) of a primitive SDF at a point.\n"
            "Returns {ok:true, gradient:[gx,gy,gz], normal:[nx,ny,nz]}."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "primitive": {"type": "string",
                              "description": "'sphere' or 'box'"},
                "params": {"type": "object"},
                "point": {"type": "array", "items": {"type": "number"},
                          "description": "[x, y, z]"},
            },
            "required": ["primitive", "point"],
        },
    )

    @register(_grad_spec, write=False)
    async def run_frep_field_gradient(ctx: ProjectCtx, args: bytes) -> str:
        try:
            a = json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
        try:
            prim = a.get("primitive", "sphere").lower()
            params = a.get("params", {})
            px, py, pz = (float(a["point"][0]), float(a["point"][1]),
                          float(a["point"][2]))
            if prim == "sphere":
                sdf = sdf_sphere(0, 0, 0, float(params.get("radius", 1.0)))
            elif prim == "box":
                sdf = sdf_box(0, 0, 0,
                              float(params.get("hx", 1.0)),
                              float(params.get("hy", 1.0)),
                              float(params.get("hz", 1.0)))
            else:
                return err_payload(f"unknown primitive '{prim}'", "BAD_ARGS")
            gx, gy, gz = field_gradient(sdf, px, py, pz)
            nx_, ny_, nz_ = surface_normal(sdf, px, py, pz)
            return ok_payload({
                "gradient": [gx, gy, gz],
                "normal": [nx_, ny_, nz_],
            })
        except Exception as exc:
            return err_payload(str(exc), "INTERNAL")
