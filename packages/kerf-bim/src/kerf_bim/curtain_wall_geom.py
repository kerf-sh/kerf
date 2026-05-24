"""
kerf_bim.curtain_wall_geom — B-rep geometry for curtain walls (GK-P30).

Extends the JSON-only curtain-wall definition to emit swept mullion B-rep
solids and panel solids from the panel grid.

Public API
----------
CurtainWallGeom(doc, start_pt, end_pt) — compute B-rep from a curtain-wall JSON doc.
  .mullion_bodies   — list of B-rep Body (one per mullion segment)
  .panel_bodies     — list of B-rep Body (one per panel cell)

Design
------
Given:
  - A base curve (straight line from start_pt to end_pt in 2D plan view)
  - Wall height (doc["height_mm"])
  - u-divisions (along base curve) and v-divisions (height)
  - Mullion size (square cross-section at ``mullion_type.size_mm``)
  - Panel kind (glass / solid / opening)

The grid produces (n_u × n_v) panels separated by mullions.

Mullion geometry
  Each grid line (u-lines = vertical mullions, v-lines = horizontal rails)
  is extruded as a rectangular box solid:
    - Vertical mullion: height × size × size (along wall, up Z, across wall)
    - Horizontal rail: width × size × size

Panel geometry
  Each panel is a thin flat solid:
    - depth = 10 mm (glass panel depth)
    - positioned flush with the exterior face of the mullions

References
----------
ISO 16739-1:2018 — IfcCurtainWall, IfcMember (mullion).
Revit 2024 Curtain Wall documentation.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


__all__ = [
    "CurtainWallGeom",
    "curtain_wall_geometry",
]

_PANEL_DEPTH_MM = 10.0   # glass panel depth
_MIN_CELL_SIZE  = 1.0    # minimum cell dimension (mm)


# ---------------------------------------------------------------------------
# B-rep import
# ---------------------------------------------------------------------------

def _import_brep():
    from kerf_cad_core.geom.brep import (  # type: ignore
        Body, Solid, Shell, Face, Loop, Coedge, Edge, Vertex, Line3, Plane,
    )
    return Body, Solid, Shell, Face, Loop, Coedge, Edge, Vertex, Line3, Plane


def _box_body(ox, oy, oz, dx, dy, dz) -> "Body":
    """Axis-aligned box solid body."""
    Body, Solid, Shell, Face, Loop, Coedge, Edge, Vertex, Line3, Plane = _import_brep()

    x0, y0, z0 = float(ox), float(oy), float(oz)
    x1, y1, z1 = x0 + float(dx), y0 + float(dy), z0 + float(dz)

    def face(pts):
        n = len(pts)
        coedges = []
        for i in range(n):
            p0, p1 = pts[i], pts[(i + 1) % n]
            v0, v1 = Vertex(p0), Vertex(p1)
            line = Line3(p0=p0, p1=p1)
            edge = Edge(curve=line, t0=0.0, t1=1.0, v_start=v0, v_end=v1)
            coedges.append(Coedge(edge=edge, orientation=True))
        loop = Loop(coedges=coedges, is_outer=True)
        x_ax = pts[1] - pts[0]; n_x = np.linalg.norm(x_ax)
        if n_x > 1e-14: x_ax /= n_x
        y_ax = pts[2] - pts[0]
        surf = Plane(origin=pts[0], x_axis=x_ax, y_axis=y_ax)
        return Face(surface=surf, loops=[loop], orientation=True)

    p000 = np.array([x0, y0, z0])
    p100 = np.array([x1, y0, z0])
    p110 = np.array([x1, y1, z0])
    p010 = np.array([x0, y1, z0])
    p001 = np.array([x0, y0, z1])
    p101 = np.array([x1, y0, z1])
    p111 = np.array([x1, y1, z1])
    p011 = np.array([x0, y1, z1])

    faces = [
        face([p000, p100, p110, p010]),  # bottom
        face([p001, p011, p111, p101]),  # top
        face([p000, p001, p101, p100]),  # front
        face([p110, p111, p011, p010]),  # back
        face([p000, p010, p011, p001]),  # left
        face([p100, p101, p111, p110]),  # right
    ]
    shell = Shell(faces=faces, is_closed=True)
    return Body(solids=[Solid(shells=[shell])])


# ---------------------------------------------------------------------------
# Division helpers
# ---------------------------------------------------------------------------

def _compute_divisions(divisions: List[Dict], total_length: float) -> List[float]:
    """Convert a division spec list into a list of segment lengths (mm).

    Supports ``type=="count"`` and ``type=="spacing"``.
    Returns a list of ``n`` lengths that sum to ``total_length``.
    """
    if not divisions:
        return [total_length]

    spec = divisions[0]  # use first spec
    div_type = spec.get("type", "count")
    value = spec.get("value", 1)

    if div_type == "count":
        n = max(1, int(value))
        seg = total_length / n
        return [seg] * n
    elif div_type == "spacing":
        s = max(_MIN_CELL_SIZE, float(value))
        n = max(1, round(total_length / s))
        seg = total_length / n
        return [seg] * n
    else:
        return [total_length]


# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------

@dataclass
class CurtainWallGeom:
    """Computed B-rep geometry for a curtain wall.

    Attributes
    ----------
    mullion_bodies:
        List of B-rep ``Body`` objects, one per mullion (vertical + horizontal).
    panel_bodies:
        List of B-rep ``Body`` objects, one per panel cell.
    u_count:
        Number of panel columns (along base curve).
    v_count:
        Number of panel rows (height).
    mullion_count:
        Total number of mullion solids emitted.
    panel_count:
        Total number of panel solids emitted (may be < u_count*v_count for
        ``opening`` panels which are skipped).
    """
    mullion_bodies: List[Any] = field(default_factory=list)
    panel_bodies:   List[Any] = field(default_factory=list)
    u_count: int = 0
    v_count: int = 0
    mullion_count: int = 0
    panel_count: int = 0


# ---------------------------------------------------------------------------
# Main geometry function
# ---------------------------------------------------------------------------

def curtain_wall_geometry(
    doc: Dict,
    start_pt: List[float],
    end_pt: List[float],
    base_z: float = 0.0,
) -> CurtainWallGeom:
    """Compute B-rep mullion and panel solids from a curtain-wall JSON doc.

    Parameters
    ----------
    doc:
        Curtain-wall definition dict (``version==1`` schema from
        ``curtain_wall.py``).
    start_pt:
        2-D start point of the base curve ``[x, y]`` in mm.
    end_pt:
        2-D end point of the base curve ``[x, y]`` in mm.
    base_z:
        Z elevation of the wall base (mm).

    Returns
    -------
    :class:`CurtainWallGeom`
        Contains mullion and panel ``Body`` lists.
    """
    height_mm = float(doc.get("height_mm", 3000.0))
    u_divs    = doc.get("u_divisions", [{"type": "count", "value": 4}])
    v_divs    = doc.get("v_divisions", [{"type": "count", "value": 3}])
    mullion   = doc.get("mullion_type", {})
    panel     = doc.get("panel_type",   {})

    mull_size = float(mullion.get("size_mm", 50.0))
    panel_kind = panel.get("kind", "glass")

    # Base curve direction and length
    sx, sy = float(start_pt[0]), float(start_pt[1])
    ex, ey = float(end_pt[0]),   float(end_pt[1])
    dx, dy = ex - sx, ey - sy
    length = math.sqrt(dx * dx + dy * dy)
    if length < 1e-6:
        return CurtainWallGeom()

    # Unit tangent along base curve and perpendicular (into wall depth)
    tx, ty = dx / length, dy / length
    px, py = -ty, tx   # perp (outward normal in plan)

    # Half-mullion size offset for positioning
    h_mull = mull_size / 2.0

    # Segment lengths
    u_segs = _compute_divisions(u_divs, length)
    v_segs = _compute_divisions(v_divs, height_mm)
    n_u = len(u_segs)
    n_v = len(v_segs)

    # Cumulative positions
    u_pos = [0.0]
    for s in u_segs:
        u_pos.append(u_pos[-1] + s)

    v_pos = [0.0]
    for s in v_segs:
        v_pos.append(v_pos[-1] + s)

    mullion_bodies = []
    panel_bodies   = []

    # -- vertical mullions (at each u grid line) --------------------------
    # There are (n_u + 1) vertical mullions
    for ui in range(n_u + 1):
        u = u_pos[ui]
        # 3D position: start + u * tangent
        ox_3d = sx + u * tx - h_mull * px
        oy_3d = sy + u * ty - h_mull * py
        oz_3d = base_z
        # Box dims: mull_size along perp, mull_size along tangent (u-dir), height_mm tall
        # Simplified: place a mull_size × mull_size × height box
        body = _box_body(
            ox_3d,         oy_3d,         oz_3d,
            mull_size * px, mull_size * py, height_mm,
        )
        # The dx/dy passed to _box_body must be unsigned; we use projected coords
        # Build directly with signed convention: store corner + vector
        body = _mullion_box(sx, sy, tx, ty, px, py, u, base_z,
                            height_mm, mull_size)
        mullion_bodies.append(body)

    # -- horizontal rails (at each v grid line) ----------------------------
    # There are (n_v + 1) horizontal rails; each spans the full width
    for vi in range(n_v + 1):
        v = v_pos[vi]
        body = _rail_box(sx, sy, tx, ty, px, py, length, base_z + v,
                         mull_size)
        mullion_bodies.append(body)

    # -- panels (one per cell) --------------------------------------------
    if panel_kind != "opening":
        for ui in range(n_u):
            for vi in range(n_v):
                u0 = u_pos[ui] + mull_size
                u1 = u_pos[ui + 1]
                v0 = v_pos[vi] + mull_size
                v1 = v_pos[vi + 1]
                if u1 - u0 < _MIN_CELL_SIZE or v1 - v0 < _MIN_CELL_SIZE:
                    continue
                body = _panel_box(sx, sy, tx, ty, px, py, u0, u1,
                                  base_z + v0, base_z + v1, _PANEL_DEPTH_MM)
                panel_bodies.append(body)

    return CurtainWallGeom(
        mullion_bodies=mullion_bodies,
        panel_bodies=panel_bodies,
        u_count=n_u,
        v_count=n_v,
        mullion_count=len(mullion_bodies),
        panel_count=len(panel_bodies),
    )


def _mullion_box(sx, sy, tx, ty, px, py, u, base_z, height, size) -> "Body":
    """Vertical mullion box at position u along the base curve."""
    # Corner: (sx + u*tx, sy + u*ty, base_z) — centred on the grid line
    h = size / 2.0
    # The mullion cross-section is size×size in the plan; height in Z
    p0 = np.array([sx + u * tx - h * tx - h * px,
                   sy + u * ty - h * ty - h * py, base_z])
    # We'll place a box: size along tangent, size along perp, height along Z
    return _make_oriented_box(p0,
                               np.array([size * tx, size * ty, 0.0]),
                               np.array([size * px, size * py, 0.0]),
                               np.array([0.0, 0.0, height]))


def _rail_box(sx, sy, tx, ty, px, py, length, z_center, size) -> "Body":
    """Horizontal rail box spanning the full wall width at elevation z_center."""
    h = size / 2.0
    p0 = np.array([sx - h * px, sy - h * py, z_center - h])
    return _make_oriented_box(p0,
                               np.array([length * tx, length * ty, 0.0]),
                               np.array([size * px, size * py, 0.0]),
                               np.array([0.0, 0.0, size]))


def _panel_box(sx, sy, tx, ty, px, py, u0, u1, z0, z1, depth) -> "Body":
    """Panel solid in cell [u0,u1] × [z0,z1]."""
    p0 = np.array([sx + u0 * tx, sy + u0 * ty, z0])
    du = u1 - u0
    return _make_oriented_box(p0,
                               np.array([du * tx, du * ty, 0.0]),
                               np.array([depth * px, depth * py, 0.0]),
                               np.array([0.0, 0.0, z1 - z0]))


def _make_oriented_box(origin, u_vec, v_vec, w_vec) -> "Body":
    """Build an axis-aligned-ish box from three edge vectors.

    For the curtain wall the vectors are in-plane (u_vec along wall,
    v_vec across wall, w_vec vertical).
    """
    Body, Solid, Shell, Face, Loop, Coedge, Edge, Vertex, Line3, Plane = _import_brep()

    o = np.asarray(origin, dtype=float)
    u = np.asarray(u_vec, dtype=float)
    v = np.asarray(v_vec, dtype=float)
    w = np.asarray(w_vec, dtype=float)

    # 8 corners
    c000 = o
    c100 = o + u
    c110 = o + u + v
    c010 = o + v
    c001 = o + w
    c101 = o + u + w
    c111 = o + u + v + w
    c011 = o + v + w

    def face(pts):
        coedges = []
        for i in range(len(pts)):
            p0, p1 = pts[i], pts[(i + 1) % len(pts)]
            v0, v1 = Vertex(p0), Vertex(p1)
            e = Edge(Line3(p0=p0, p1=p1), 0.0, 1.0, v0, v1)
            coedges.append(Coedge(edge=e, orientation=True))
        loop = Loop(coedges=coedges, is_outer=True)
        xa = pts[1] - pts[0]; n = np.linalg.norm(xa)
        if n > 1e-14: xa /= n
        ya = pts[2] - pts[0]
        surf = Plane(origin=pts[0], x_axis=xa, y_axis=ya)
        return Face(surface=surf, loops=[loop], orientation=True)

    faces = [
        face([c000, c100, c110, c010]),
        face([c001, c011, c111, c101]),
        face([c000, c001, c101, c100]),
        face([c110, c111, c011, c010]),
        face([c000, c010, c011, c001]),
        face([c100, c101, c111, c110]),
    ]
    shell = Shell(faces=faces, is_closed=True)
    return Body(solids=[Solid(shells=[shell])])
