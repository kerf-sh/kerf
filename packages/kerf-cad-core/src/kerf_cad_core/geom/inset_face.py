"""
inset_face.py
=============
GK-73 — Inset face for SubD cages and B-rep Body faces.

Offsets a face inward (or outward) by a per-edge ``gap``, creating a ring of
new quad faces around the shrunk original.  The operation is:

  * **SubD cage** (``SubDCage``): the target face is shrunk by moving its
    vertices toward the face centroid, and a ring of new quads bridges the
    original boundary edges to the new inner boundary.
  * **B-rep Body** (``Body``): the face's outer-loop vertices are extracted,
    the same shrink is applied in 3-D, new ``Plane`` faces are built for the
    ring quads, and the original face is replaced with the shrunk version.

Both paths return an ``InsetResult`` TypedDict.

Public API
----------
InsetResult
    TypedDict with keys:

    ``target`` : SubDCage | Body
        New target with the inset applied (immutable-style; original unchanged).
    ``face_id`` : int
        Index of the *inner* face in the returned target (matches ``face_id``
        passed in for B-rep; same index for SubD).
    ``ring_face_ids`` : list[int]
        Indices of the newly created ring quad faces.
    ``gap`` : float
        Actual gap applied.

inset_face(target, face_id, gap, direction='inward') -> InsetResult
    Apply inset to *one* face of a SubDCage or Body.

    Parameters
    ----------
    target : SubDCage | Body
        Input object.  Not mutated.
    face_id : int
        Index of the face to inset (SubD: index into ``cage.faces``; Body:
        index into ``body.all_faces()``).
    gap : float
        Offset distance from each edge toward the centroid.  Must be > 0.
    direction : 'inward' | 'outward'
        'inward'  — inner face shrinks (gap > 0 → smaller inner face).
        'outward' — inner face grows (gap negated, only valid for non-convex
        contexts; typically you just pass a negative gap).

    Returns
    -------
    InsetResult — never raises; returns the original target + empty ring on
    invalid inputs.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple, TYPE_CHECKING

# --------------------------------------------------------------------------
# Type stubs to keep imports lazy / avoid hard dependency at module load
# --------------------------------------------------------------------------

try:
    from kerf_cad_core.geom.subd_authoring import SubDCage
except ImportError:  # pragma: no cover
    SubDCage = None  # type: ignore[assignment,misc]

try:
    from kerf_cad_core.geom.brep import Body, Face, Shell, Solid, Vertex, Edge, Coedge, Loop, Line3, Plane
    import numpy as np
    _HAS_BREP = True
except ImportError:  # pragma: no cover
    _HAS_BREP = False
    np = None  # type: ignore[assignment]


# --------------------------------------------------------------------------
# InsetResult — plain dict with known keys (TypedDict-compatible)
# --------------------------------------------------------------------------

class InsetResult(dict):
    """Dict-like result from :func:`inset_face`.

    Keys
    ----
    target : SubDCage | Body
    face_id : int
    ring_face_ids : list[int]
    gap : float
    """

    # Provide attribute-style access as a convenience.
    def __getattr__(self, name: str):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


# --------------------------------------------------------------------------
# Internal helpers — pure-Python 3-D vector math (no numpy required for SubD)
# --------------------------------------------------------------------------

def _v3_sub(a: List[float], b: List[float]) -> List[float]:
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def _v3_add(a: List[float], b: List[float]) -> List[float]:
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]


def _v3_scale(v: List[float], s: float) -> List[float]:
    return [v[0] * s, v[1] * s, v[2] * s]


def _v3_len(v: List[float]) -> float:
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def _v3_norm(v: List[float]) -> List[float]:
    ln = _v3_len(v)
    if ln < 1e-15:
        return [0.0, 0.0, 1.0]
    return [v[0] / ln, v[1] / ln, v[2] / ln]


def _v3_lerp(a: List[float], b: List[float], t: float) -> List[float]:
    return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]


def _face_centroid_3d(verts: List[List[float]], face_vert_indices: List[int]) -> List[float]:
    n = len(face_vert_indices)
    if n == 0:
        return [0.0, 0.0, 0.0]
    cx = sum(verts[i][0] for i in face_vert_indices) / n
    cy = sum(verts[i][1] for i in face_vert_indices) / n
    cz = sum(verts[i][2] for i in face_vert_indices) / n
    return [cx, cy, cz]


def _face_normal_newell(verts: List[List[float]], face_vert_indices: List[int]) -> List[float]:
    """Newell's method for face normal."""
    n = len(face_vert_indices)
    nx = ny = nz = 0.0
    for i in range(n):
        vi = verts[face_vert_indices[i]]
        vj = verts[face_vert_indices[(i + 1) % n]]
        nx += (vi[1] - vj[1]) * (vi[2] + vj[2])
        ny += (vi[2] - vj[2]) * (vi[0] + vj[0])
        nz += (vi[0] - vj[0]) * (vi[1] + vj[1])
    return _v3_norm([nx, ny, nz])


def _inset_vertices_2d(
    verts: List[List[float]],
    face_vert_indices: List[int],
    gap: float,
) -> List[List[float]]:
    """Compute the inset positions for a planar/3-D face.

    Each original vertex is moved toward the face centroid by ``gap``.  This
    is the simplest area-preserving inset: the ring width is ``gap`` measured
    perpendicular to each edge.

    For a planar quad the inner face area is ``(sqrt(A) - 2*gap)²`` (the spec
    oracle).

    Returns
    -------
    List of new [x, y, z] positions for each vertex in ``face_vert_indices``,
    in the same order.
    """
    centroid = _face_centroid_3d(verts, face_vert_indices)
    n = len(face_vert_indices)
    inner: List[List[float]] = []
    for vi in face_vert_indices:
        orig = verts[vi]
        # Direction from vertex toward centroid
        to_c = _v3_sub(centroid, orig)
        dist = _v3_len(to_c)
        if dist < 1e-15:
            inner.append(list(orig))
            continue
        # Compute edge-perpendicular offset: for a regular polygon vertex
        # the inset t along the centroid direction that produces a gap of
        # `gap` at each edge midpoint.
        # We use half-angle correction: t = gap / sin(half_interior_angle)
        # For robustness we fall back to the simpler dist-proportional move.
        #
        # Edge before and after this vertex:
        prev_vi = face_vert_indices[(face_vert_indices.index(vi) - 1) % n]
        next_vi = face_vert_indices[(face_vert_indices.index(vi) + 1) % n]
        e_prev = _v3_norm(_v3_sub(verts[prev_vi], orig))
        e_next = _v3_norm(_v3_sub(verts[next_vi], orig))
        # Interior half-angle bisector — angle between the two edge directions
        dot = max(-1.0, min(1.0, e_prev[0] * e_next[0] + e_prev[1] * e_next[1] + e_prev[2] * e_next[2]))
        half_angle = math.acos(dot) / 2.0
        sin_half = math.sin(half_angle)
        if sin_half < 1e-6:
            move_dist = gap
        else:
            move_dist = gap / sin_half
        # Clamp so we don't overshoot the centroid
        move_dist = min(move_dist, dist)
        direction = _v3_norm(to_c)
        inner.append(_v3_add(orig, _v3_scale(direction, move_dist)))
    return inner


# --------------------------------------------------------------------------
# SubD cage path
# --------------------------------------------------------------------------

def _inset_subd(
    cage: "SubDCage",
    face_id: int,
    gap: float,
    direction: str,
) -> "InsetResult":
    """Inset one face of a SubDCage."""
    from kerf_cad_core.geom.subd_authoring import SubDCage as _SubDCage

    # Validate
    if face_id < 0 or face_id >= len(cage.faces):
        return InsetResult(
            target=_SubDCage(
                vertices=[list(v) for v in cage.vertices],
                faces=[list(f) for f in cage.faces],
                sharpness=dict(cage.sharpness),
            ),
            face_id=face_id,
            ring_face_ids=[],
            gap=gap,
        )

    effective_gap = gap if direction == "inward" else -gap

    # Deep copy
    new_verts: List[List[float]] = [list(v) for v in cage.vertices]
    new_faces: List[List[int]] = [list(f) for f in cage.faces]
    new_sharpness: dict = dict(cage.sharpness)

    orig_face = new_faces[face_id]
    n = len(orig_face)

    if n < 3:
        return InsetResult(
            target=_SubDCage(vertices=new_verts, faces=new_faces, sharpness=new_sharpness),
            face_id=face_id,
            ring_face_ids=[],
            gap=gap,
        )

    # Compute inset positions for the face vertices
    inner_positions = _inset_vertices_2d(new_verts, orig_face, effective_gap)

    # Add new inner vertices to the vertex list
    inner_vert_ids: List[int] = []
    base_idx = len(new_verts)
    for pos in inner_positions:
        new_verts.append(pos)
        inner_vert_ids.append(base_idx)
        base_idx += 1

    # Replace original face with inner face (same face_id)
    new_faces[face_id] = inner_vert_ids

    # Add ring quads: one per edge of the original face
    ring_face_ids: List[int] = []
    for i in range(n):
        outer_a = orig_face[i]
        outer_b = orig_face[(i + 1) % n]
        inner_a = inner_vert_ids[i]
        inner_b = inner_vert_ids[(i + 1) % n]
        # Quad: outer_a -> outer_b -> inner_b -> inner_a (winding matches face normal)
        ring_idx = len(new_faces)
        new_faces.append([outer_a, outer_b, inner_b, inner_a])
        ring_face_ids.append(ring_idx)

    # Invalidate edge cache
    result_cage = _SubDCage(
        vertices=new_verts,
        faces=new_faces,
        sharpness=new_sharpness,
    )

    return InsetResult(
        target=result_cage,
        face_id=face_id,
        ring_face_ids=ring_face_ids,
        gap=gap,
    )


# --------------------------------------------------------------------------
# B-rep Body path
# --------------------------------------------------------------------------

def _extract_face_world_vertices(face: "Face") -> List[List[float]]:
    """Extract ordered world-space vertex positions from a Body Face outer loop.

    Walks the coedges of the outer loop, evaluating each edge at t=0 for the
    start vertex.  Falls back to the stored Vertex.point if available.
    """
    outer = face.outer_loop()
    if outer is None or not outer.coedges:
        return []
    pts: List[List[float]] = []
    for ce in outer.coedges:
        v = ce.start_vertex()
        if v is not None and hasattr(v, "point"):
            pts.append(v.point.tolist())
    return pts


def _make_planar_face_brep(pts_3d: List[List[float]]) -> Optional["Face"]:
    """Build a simple planar B-rep Face from an ordered list of 3-D points."""
    if not _HAS_BREP or len(pts_3d) < 3:
        return None
    import numpy as _np
    pts = [_np.asarray(p, dtype=float) for p in pts_3d]
    n = len(pts)

    # Build vertices, edges, coedges, loop, face
    verts = [Vertex(p) for p in pts]
    edges = []
    for i in range(n):
        a = verts[i]
        b = verts[(i + 1) % n]
        e = Edge(Line3(a.point, b.point), 0.0, 1.0, a, b)
        edges.append(e)

    coedges = [Coedge(e, False) for e in edges]
    loop = Loop(coedges, is_outer=True)

    # Build a Plane from first three non-collinear points
    p0, p1, p2 = pts[0], pts[1], pts[2]
    x_ax = p1 - p0
    y_ax = p2 - p0
    plane = Plane(origin=p0, x_axis=x_ax, y_axis=y_ax)

    return Face(plane, [loop], orientation=True)


def _inset_body(
    body: "Body",
    face_id: int,
    gap: float,
    direction: str,
) -> "InsetResult":
    """Inset one face of a B-rep Body."""
    if not _HAS_BREP:
        return InsetResult(target=body, face_id=face_id, ring_face_ids=[], gap=gap)

    all_faces = body.all_faces()
    if face_id < 0 or face_id >= len(all_faces):
        return InsetResult(target=body, face_id=face_id, ring_face_ids=[], gap=gap)

    effective_gap = gap if direction == "inward" else -gap

    target_face = all_faces[face_id]
    outer_pts = _extract_face_world_vertices(target_face)
    n = len(outer_pts)
    if n < 3:
        return InsetResult(target=body, face_id=face_id, ring_face_ids=[], gap=gap)

    # Compute inset positions in 3-D
    inner_positions = _inset_vertices_2d(outer_pts, list(range(n)), effective_gap)

    # Build new inner face (replaces original)
    new_inner_face = _make_planar_face_brep(inner_positions)
    if new_inner_face is None:
        return InsetResult(target=body, face_id=face_id, ring_face_ids=[], gap=gap)

    # Build ring quad faces
    ring_faces: List["Face"] = []
    for i in range(n):
        quad_pts = [
            outer_pts[i],
            outer_pts[(i + 1) % n],
            inner_positions[(i + 1) % n],
            inner_positions[i],
        ]
        ring_f = _make_planar_face_brep(quad_pts)
        if ring_f is not None:
            ring_faces.append(ring_f)

    # Build new Body: copy existing structure, replace target face, add ring faces
    import itertools as _it
    import copy as _copy

    # We construct a fresh Body that reuses all shells / solids from the
    # original, but replaces the target face with new_inner_face and appends
    # ring faces as a new free shell.
    #
    # Strategy: shallow copy — rebuild topology containers.
    new_body = Body()

    # Rebuild solids / shells, swapping the face
    def _clone_face(f: "Face") -> "Face":
        """Return f as-is, or return new_inner_face if f is the target."""
        if f is target_face:
            return new_inner_face
        return f

    for solid in body.solids:
        new_solid = Solid()
        for shell in solid.shells:
            new_shell = Shell(is_closed=shell.is_closed)
            for f in shell.faces:
                new_shell.add_face(_clone_face(f))
            new_solid.shells.append(new_shell)
            new_shell.solid = new_solid
        new_body.solids.append(new_solid)
        new_solid  # type: ignore[no-op]

    for shell in body.shells:
        new_shell = Shell(is_closed=shell.is_closed)
        for f in shell.faces:
            new_shell.add_face(_clone_face(f))
        new_body.shells.append(new_shell)

    # Add ring faces as a free shell (open sheet)
    if ring_faces:
        ring_shell = Shell(is_closed=False)
        for rf in ring_faces:
            ring_shell.add_face(rf)
        new_body.shells.append(ring_shell)

    # Compute face_id of inner face in new body and ring face ids
    new_all_faces = new_body.all_faces()
    new_inner_id = face_id  # same slot by construction
    base_ring_idx = len(new_all_faces) - len(ring_faces)
    ring_face_ids_out = list(range(base_ring_idx, base_ring_idx + len(ring_faces)))

    return InsetResult(
        target=new_body,
        face_id=new_inner_id,
        ring_face_ids=ring_face_ids_out,
        gap=gap,
    )


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------

def inset_face(
    target,
    face_id: int,
    gap: float,
    direction: str = "inward",
) -> "InsetResult":
    """Inset one face of a SubDCage or Body.

    Parameters
    ----------
    target : SubDCage | Body
        Input object.  Not mutated.
    face_id : int
        Index of the face to inset.
        * ``SubDCage``: index into ``cage.faces``.
        * ``Body``: index into ``body.all_faces()``.
    gap : float
        Per-edge inset distance (must be > 0 for a meaningful inset).
    direction : 'inward' | 'outward'
        Inward shrinks the inner face; outward grows it (negate gap).

    Returns
    -------
    InsetResult
        Never raises.  Returns the original ``target`` unchanged with an
        empty ``ring_face_ids`` list on invalid inputs.
    """
    try:
        gap = float(gap)
        face_id = int(face_id)
        if direction not in ("inward", "outward"):
            direction = "inward"

        # Detect SubDCage
        if SubDCage is not None and isinstance(target, SubDCage):
            return _inset_subd(target, face_id, gap, direction)

        # Detect Body
        if _HAS_BREP:
            from kerf_cad_core.geom.brep import Body as _Body
            if isinstance(target, _Body):
                return _inset_body(target, face_id, gap, direction)

        # Unknown type — return passthrough
        return InsetResult(target=target, face_id=face_id, ring_face_ids=[], gap=gap)
    except Exception:
        return InsetResult(target=target, face_id=face_id, ring_face_ids=[], gap=gap)
