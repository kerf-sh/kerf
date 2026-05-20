"""
subd_authoring.py
=================
Author-time SubD operations on cage meshes.

This module provides creation and editing operations for subdivision surface
control cages (vertices + quad faces + crease weights).  It is purely
additive — it imports the existing evaluator from ``subd.py`` but does not
modify it.

Public API
----------
SubDCage
    Thin wrapper around SubDMesh that explicitly marks a mesh as an
    author-time control cage.  Carries the same data (vertices, faces,
    creases) plus a *sharpness* dict that stores crease sharpness as an
    unbounded float (0 = smooth, math.inf = perfectly sharp / hard edge).

SubDSurface
    Evaluated result returned by ``to_subd_surface``.  Contains the dense
    quad mesh produced by Catmull-Clark subdivision together with the
    originating cage for traceability.

create_subd_primitive(kind, **dims) -> SubDCage
    Build a cage from a standard primitive shape:
      * ``'cube'``     — box; dims: width=2, height=2, depth=2
      * ``'cylinder'`` — dims: radius=1, height=2, segments=8
      * ``'sphere'``   — dims: radius=1, segments_u=8, segments_v=6
      * ``'torus'``    — dims: major_radius=1, minor_radius=0.4,
                               segments_u=8, segments_v=6

subd_extrude(cage, face_ids, distance) -> SubDCage
    Extrude one or more faces along their average normal by ``distance``.

subd_bevel(cage, edge_ids, amount) -> SubDCage
    Bevel one or more edges by splitting each into two parallel edges
    separated by ``amount``.

subd_loop_cut(cage, edge_ring, t=0.5) -> SubDCage
    Insert a loop cut across a ring of quad faces at parameter ``t`` ∈ (0, 1).

subd_loop_slide(cage, edge_loop, t) -> SubDCage
    Slide an edge loop along its adjacent quad faces.  ``t`` in [-1, 1]
    where 0 = identity.  Topology (V/E/F) is unchanged.

subd_set_crease(cage, edge_id, sharpness) -> SubDCage
    Assign a crease sharpness to an edge.  Sharpness 0 = smooth,
    ``math.inf`` = perfectly hard.  Returns a new cage (immutable-style).

to_subd_surface(cage, levels=2) -> SubDSurface
    Round-trip: evaluate the cage through the Catmull-Clark evaluator and
    return a SubDSurface.

All functions never raise — errors produce an unchanged / empty result.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

from kerf_cad_core.geom.subd import (
    SubDMesh,
    catmull_clark_subdivide,
)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

# An "edge id" in the cage API is an integer index into the ordered list of
# unique edges produced by _cage_edge_list().  This is more user-friendly
# than raw (a, b) pairs when scripting.

EdgeId = int
FaceId = int


@dataclass
class SubDCage:
    """Author-time SubD control cage.

    Attributes
    ----------
    vertices : list of [x, y, z]
        Control-point positions.
    faces : list of list[int]
        Quad face vertex-index lists.
    sharpness : dict mapping edge_id -> float
        Unbounded sharpness values.  0 = smooth, math.inf = hard.
        Edge ids correspond to the ordered edge list from ``cage_edges()``.
    _edge_list : list of (int, int)
        Cached ordered unique edge list.  Rebuilt on demand.
    """

    vertices: List[List[float]] = field(default_factory=list)
    faces: List[List[int]] = field(default_factory=list)
    sharpness: Dict[int, float] = field(default_factory=dict)  # edge_id -> sharpness

    # Internal: ordered edge list — lazily built.
    _edge_list: List[Tuple[int, int]] = field(default_factory=list, repr=False)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def num_vertices(self) -> int:
        return len(self.vertices)

    @property
    def num_faces(self) -> int:
        return len(self.faces)

    # ------------------------------------------------------------------
    # Edge indexing helpers
    # ------------------------------------------------------------------

    def _build_edge_list(self) -> List[Tuple[int, int]]:
        """Build (and cache) an ordered list of unique edges."""
        if self._edge_list and len(self._edge_list) > 0:
            return self._edge_list
        seen: Set[Tuple[int, int]] = set()
        result: List[Tuple[int, int]] = []
        for face in self.faces:
            n = len(face)
            for i in range(n):
                a, b = face[i], face[(i + 1) % n]
                key = (min(a, b), max(a, b))
                if key not in seen:
                    seen.add(key)
                    result.append(key)
        self._edge_list = result
        return result

    def cage_edges(self) -> List[Tuple[int, int]]:
        """Return ordered list of (a, b) unique edge pairs.

        The index of each pair is the edge_id used by the sharpness dict
        and the ``edge_ids`` parameter of :func:`subd_bevel`,
        :func:`subd_loop_cut`, and :func:`subd_set_crease`.
        """
        return self._build_edge_list()

    def edge_id(self, a: int, b: int) -> Optional[int]:
        """Return the edge_id for a given vertex pair, or None if not found."""
        edges = self._build_edge_list()
        key = (min(a, b), max(a, b))
        try:
            return edges.index(key)
        except ValueError:
            return None

    def get_sharpness(self, eid: int) -> float:
        """Return sharpness for an edge id (0.0 if not set)."""
        return self.sharpness.get(eid, 0.0)

    # ------------------------------------------------------------------
    # Conversion to SubDMesh (used internally by to_subd_surface)
    # ------------------------------------------------------------------

    def to_subd_mesh(self) -> SubDMesh:
        """Convert cage to a SubDMesh suitable for the evaluator.

        Sharpness values are clamped to [0, 1] for the SubDMesh crease dict
        (math.inf → 1.0).
        """
        edges = self._build_edge_list()
        creases: Dict[Tuple[int, int], float] = {}
        for eid, sharp in self.sharpness.items():
            if 0 <= eid < len(edges):
                clamped = 1.0 if (math.isinf(sharp) or sharp >= 1.0) else float(sharp)
                if clamped > 0.0:
                    creases[edges[eid]] = clamped
        return SubDMesh(
            vertices=[list(v) for v in self.vertices],
            faces=[list(f) for f in self.faces],
            creases=creases,
        )


@dataclass
class SubDSurface:
    """Evaluated SubD surface — result of calling :func:`to_subd_surface`.

    Attributes
    ----------
    mesh : SubDMesh
        Dense quad mesh from Catmull-Clark subdivision.
    cage : SubDCage
        Originating control cage (for round-trip traceability).
    levels : int
        Number of subdivision levels used.
    """

    mesh: SubDMesh = field(default_factory=SubDMesh)
    cage: SubDCage = field(default_factory=SubDCage)
    levels: int = 2


# ---------------------------------------------------------------------------
# Internal geometry helpers
# ---------------------------------------------------------------------------

def _vec3_sub(a: List[float], b: List[float]) -> List[float]:
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def _vec3_add(a: List[float], b: List[float]) -> List[float]:
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]


def _vec3_scale(v: List[float], s: float) -> List[float]:
    return [v[0] * s, v[1] * s, v[2] * s]


def _vec3_cross(a: List[float], b: List[float]) -> List[float]:
    return [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]


def _vec3_length(v: List[float]) -> float:
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def _vec3_normalize(v: List[float]) -> List[float]:
    ln = _vec3_length(v)
    if ln < 1e-15:
        return [0.0, 0.0, 1.0]
    return [v[0] / ln, v[1] / ln, v[2] / ln]


def _face_normal(verts: List[List[float]], face: List[int]) -> List[float]:
    """Compute face normal via Newell's method."""
    n = len(face)
    nx = ny = nz = 0.0
    for i in range(n):
        vi = verts[face[i]]
        vj = verts[face[(i + 1) % n]]
        nx += (vi[1] - vj[1]) * (vi[2] + vj[2])
        ny += (vi[2] - vj[2]) * (vi[0] + vj[0])
        nz += (vi[0] - vj[0]) * (vi[1] + vj[1])
    return _vec3_normalize([nx, ny, nz])


def _face_centroid(verts: List[List[float]], face: List[int]) -> List[float]:
    n = len(face)
    cx = sum(verts[i][0] for i in face) / n
    cy = sum(verts[i][1] for i in face) / n
    cz = sum(verts[i][2] for i in face) / n
    return [cx, cy, cz]


def _copy_cage(cage: SubDCage) -> SubDCage:
    """Deep copy a cage."""
    return SubDCage(
        vertices=[list(v) for v in cage.vertices],
        faces=[list(f) for f in cage.faces],
        sharpness=dict(cage.sharpness),
    )


# ---------------------------------------------------------------------------
# Public: create_subd_primitive
# ---------------------------------------------------------------------------

def create_subd_primitive(kind: str, **dims) -> SubDCage:
    """Create a SubD cage from a standard primitive.

    Parameters
    ----------
    kind : 'cube' | 'cylinder' | 'sphere' | 'torus'
    **dims :
        cube     — width=2, height=2, depth=2
        cylinder — radius=1, height=2, segments=8
        sphere   — radius=1, segments_u=8, segments_v=6
        torus    — major_radius=1, minor_radius=0.4,
                   segments_u=8, segments_v=6

    Returns
    -------
    SubDCage
        Never raises; returns empty cage on unknown kind.
    """
    try:
        kind = kind.lower().strip()
        if kind == "cube":
            return _make_cube(
                w=float(dims.get("width", 2.0)),
                h=float(dims.get("height", 2.0)),
                d=float(dims.get("depth", 2.0)),
            )
        elif kind == "cylinder":
            return _make_cylinder(
                r=float(dims.get("radius", 1.0)),
                h=float(dims.get("height", 2.0)),
                segs=int(dims.get("segments", 8)),
            )
        elif kind == "sphere":
            return _make_sphere(
                r=float(dims.get("radius", 1.0)),
                su=int(dims.get("segments_u", 8)),
                sv=int(dims.get("segments_v", 6)),
            )
        elif kind == "torus":
            return _make_torus(
                R=float(dims.get("major_radius", 1.0)),
                r=float(dims.get("minor_radius", 0.4)),
                su=int(dims.get("segments_u", 8)),
                sv=int(dims.get("segments_v", 6)),
            )
        else:
            return SubDCage()
    except Exception:
        return SubDCage()


def _make_cube(w: float = 2.0, h: float = 2.0, d: float = 2.0) -> SubDCage:
    hw, hh, hd = w / 2.0, h / 2.0, d / 2.0
    verts = [
        [-hw, -hh, -hd],  # 0
        [ hw, -hh, -hd],  # 1
        [ hw,  hh, -hd],  # 2
        [-hw,  hh, -hd],  # 3
        [-hw, -hh,  hd],  # 4
        [ hw, -hh,  hd],  # 5
        [ hw,  hh,  hd],  # 6
        [-hw,  hh,  hd],  # 7
    ]
    faces = [
        [0, 3, 2, 1],  # bottom  z=-hd
        [4, 5, 6, 7],  # top     z=+hd
        [0, 1, 5, 4],  # front   y=-hh
        [2, 3, 7, 6],  # back    y=+hh
        [0, 4, 7, 3],  # left    x=-hw
        [1, 2, 6, 5],  # right   x=+hw
    ]
    return SubDCage(vertices=verts, faces=faces)


def _make_cylinder(r: float = 1.0, h: float = 2.0, segs: int = 8) -> SubDCage:
    segs = max(3, segs)
    hh = h / 2.0
    verts: List[List[float]] = []
    # Bottom ring (z = -hh)
    for i in range(segs):
        angle = 2.0 * math.pi * i / segs
        verts.append([r * math.cos(angle), r * math.sin(angle), -hh])
    # Top ring (z = +hh)
    for i in range(segs):
        angle = 2.0 * math.pi * i / segs
        verts.append([r * math.cos(angle), r * math.sin(angle), hh])

    faces: List[List[int]] = []
    # Side quads
    for i in range(segs):
        b0 = i
        b1 = (i + 1) % segs
        t0 = segs + i
        t1 = segs + (i + 1) % segs
        faces.append([b0, b1, t1, t0])

    # Cap faces — use an N-gon (non-quad) for the top and bottom caps.
    # The caps are n-gons (polygons), which is fine for SubD cage input.
    faces.append(list(range(segs - 1, -1, -1)))        # bottom cap (winding)
    faces.append(list(range(segs, 2 * segs)))           # top cap

    return SubDCage(vertices=verts, faces=faces)


def _make_sphere(r: float = 1.0, su: int = 8, sv: int = 6) -> SubDCage:
    """UV-sphere quad cage (poles capped with n-gons)."""
    su = max(3, su)
    sv = max(2, sv)
    verts: List[List[float]] = []

    # Bottom pole
    verts.append([0.0, 0.0, -r])

    # Middle rings: sv - 1 rings of su vertices each
    for j in range(1, sv):
        phi = math.pi * j / sv  # 0..pi (pole to pole)
        for i in range(su):
            theta = 2.0 * math.pi * i / su
            x = r * math.sin(phi) * math.cos(theta)
            y = r * math.sin(phi) * math.sin(theta)
            z = -r * math.cos(phi)
            verts.append([x, y, z])

    # Top pole
    verts.append([0.0, 0.0, r])

    faces: List[List[int]] = []

    # Ring vertex index: ring j (1-based) starts at 1 + (j-1)*su
    def ring_idx(j: int, i: int) -> int:
        return 1 + (j - 1) * su + (i % su)

    # Bottom cap: pole=0 connects to ring 1
    for i in range(su):
        faces.append([0, ring_idx(1, i + 1), ring_idx(1, i)])

    # Middle quad bands
    for j in range(1, sv - 1):
        for i in range(su):
            a = ring_idx(j, i)
            b = ring_idx(j, i + 1)
            c = ring_idx(j + 1, i + 1)
            d = ring_idx(j + 1, i)
            faces.append([a, b, c, d])

    # Top cap: last ring connects to top pole
    top_pole = 1 + (sv - 1) * su
    last_ring = sv - 1
    for i in range(su):
        faces.append([ring_idx(last_ring, i), ring_idx(last_ring, i + 1), top_pole])

    return SubDCage(vertices=verts, faces=faces)


def _make_torus(
    R: float = 1.0,
    r: float = 0.4,
    su: int = 8,
    sv: int = 6,
) -> SubDCage:
    """Toroidal quad cage."""
    su = max(3, su)
    sv = max(3, sv)
    verts: List[List[float]] = []
    for j in range(sv):
        phi = 2.0 * math.pi * j / sv  # around tube
        for i in range(su):
            theta = 2.0 * math.pi * i / su  # around torus
            x = (R + r * math.cos(phi)) * math.cos(theta)
            y = (R + r * math.cos(phi)) * math.sin(theta)
            z = r * math.sin(phi)
            verts.append([x, y, z])

    faces: List[List[int]] = []
    for j in range(sv):
        for i in range(su):
            a = j * su + i
            b = j * su + (i + 1) % su
            c = ((j + 1) % sv) * su + (i + 1) % su
            d = ((j + 1) % sv) * su + i
            faces.append([a, b, c, d])

    return SubDCage(vertices=verts, faces=faces)


# ---------------------------------------------------------------------------
# Public: subd_extrude
# ---------------------------------------------------------------------------

def subd_extrude(
    cage: SubDCage,
    face_ids: Sequence[int],
    distance: float,
) -> SubDCage:
    """Extrude faces along their normals.

    Each face in ``face_ids`` is duplicated, offset by ``distance`` along
    the face normal, and the original boundary is connected with side quads.
    The original face is replaced by the offset face.

    Parameters
    ----------
    cage : SubDCage
    face_ids : sequence of int
        Face indices to extrude.
    distance : float
        Extrusion distance (negative = inward).

    Returns
    -------
    SubDCage — never raises.
    """
    try:
        result = _copy_cage(cage)
        # Invalidate edge list cache
        result._edge_list = []

        face_ids_set = set(int(fid) for fid in face_ids if 0 <= int(fid) < len(cage.faces))
        if not face_ids_set:
            return result

        verts = result.vertices
        new_faces: List[List[int]] = []

        for fi, face in enumerate(result.faces):
            if fi not in face_ids_set:
                new_faces.append(face)
                continue

            # Compute face normal and centroid
            normal = _face_normal(verts, face)
            offset = _vec3_scale(normal, distance)

            # Duplicate vertices for this face
            new_vert_indices: List[int] = []
            for vi in face:
                new_vi = len(verts)
                verts.append(_vec3_add(verts[vi], offset))
                new_vert_indices.append(new_vi)

            n = len(face)
            # Add side quads connecting original to new
            for i in range(n):
                orig_a = face[i]
                orig_b = face[(i + 1) % n]
                new_a = new_vert_indices[i]
                new_b = new_vert_indices[(i + 1) % n]
                new_faces.append([orig_a, orig_b, new_b, new_a])

            # The extruded (top) face replaces the original
            new_faces.append(new_vert_indices)

        result.faces = new_faces
        return result
    except Exception:
        return _copy_cage(cage)


# ---------------------------------------------------------------------------
# Public: subd_bevel
# ---------------------------------------------------------------------------

def subd_bevel(
    cage: SubDCage,
    edge_ids: Sequence[int],
    amount: float,
) -> SubDCage:
    """Bevel edges by splitting each into two edges separated by ``amount``.

    Each bevelled edge is replaced by a quad strip; adjacent faces are
    updated to reference the new vertices.

    Parameters
    ----------
    cage : SubDCage
    edge_ids : sequence of int
        Edge indices (from ``cage.cage_edges()``) to bevel.
    amount : float
        Bevel offset distance.

    Returns
    -------
    SubDCage — never raises.
    """
    try:
        amount = float(amount)
        if amount <= 0.0:
            return _copy_cage(cage)

        edges = cage.cage_edges()
        bevel_edge_set = set(
            int(eid) for eid in edge_ids
            if 0 <= int(eid) < len(edges)
        )
        if not bevel_edge_set:
            return _copy_cage(cage)

        verts = [list(v) for v in cage.vertices]
        new_faces: List[List[int]] = list(list(f) for f in cage.faces)
        added_quads: List[List[int]] = []

        # For each bevelled edge (a, b), create two new vertices offset
        # perpendicular to the edge in each adjacent face's plane.
        # Then replace the edge references in faces with the new vertices
        # and add a connecting quad.

        for eid in bevel_edge_set:
            a, b = edges[eid]
            va = verts[a]
            vb = verts[b]
            # Edge direction
            edge_dir = _vec3_normalize(_vec3_sub(vb, va))

            # Find faces containing this edge
            adj_face_ids: List[int] = []
            for fi, face in enumerate(new_faces):
                n = len(face)
                for i in range(n):
                    u = face[i]
                    v_ = face[(i + 1) % n]
                    if (min(u, v_), max(u, v_)) == (min(a, b), max(a, b)):
                        adj_face_ids.append(fi)
                        break

            # For each adjacent face, compute an in-plane perpendicular
            # offset direction and create new vertices.
            face_new_verts: Dict[int, Tuple[int, int]] = {}
            # Maps face_id -> (new_v_for_a, new_v_for_b) in that face
            for fi in adj_face_ids:
                face = new_faces[fi]
                normal = _face_normal(verts, face)
                # Perpendicular to edge, in face plane: cross(normal, edge_dir)
                perp = _vec3_normalize(_vec3_cross(normal, edge_dir))
                na_idx = len(verts)
                verts.append(_vec3_add(va, _vec3_scale(perp, amount)))
                nb_idx = len(verts)
                verts.append(_vec3_add(vb, _vec3_scale(perp, amount)))
                face_new_verts[fi] = (na_idx, nb_idx)

            # Update each adjacent face: replace a->na, b->nb
            for fi, (na_idx, nb_idx) in face_new_verts.items():
                face = new_faces[fi]
                updated: List[int] = []
                for vi in face:
                    if vi == a:
                        updated.append(na_idx)
                    elif vi == b:
                        updated.append(nb_idx)
                    else:
                        updated.append(vi)
                new_faces[fi] = updated

            # If there are exactly two adjacent faces, add a bevel quad
            if len(face_new_verts) == 2:
                fids = list(face_new_verts.keys())
                na0, nb0 = face_new_verts[fids[0]]
                na1, nb1 = face_new_verts[fids[1]]
                added_quads.append([na0, nb0, nb1, na1])

        result_faces = new_faces + added_quads
        result = SubDCage(vertices=verts, faces=result_faces)
        # Preserve non-bevelled sharpness entries (edge ids will shift, so
        # we drop sharpness rather than mis-map it — caller can re-apply)
        return result
    except Exception:
        return _copy_cage(cage)


# ---------------------------------------------------------------------------
# Public: subd_loop_cut
# ---------------------------------------------------------------------------

def subd_loop_cut(
    cage: SubDCage,
    edge_ring: Sequence[int],
    t: float = 0.5,
) -> SubDCage:
    """Insert a loop cut across a ring of quad faces.

    Each face in the ring is split into two quads at parameter ``t`` along
    the edge pair defined by the ring.

    Parameters
    ----------
    cage : SubDCage
    edge_ring : sequence of int
        Edge ids forming the loop ring (from ``cage.cage_edges()``).  Each
        edge must belong to a distinct quad face; consecutive edges should
        share a face.
    t : float
        Cut position in [0, 1].  Default 0.5 (midpoint).

    Returns
    -------
    SubDCage — never raises.
    """
    try:
        t = max(0.0001, min(0.9999, float(t)))
        edges = cage.cage_edges()
        ring_eids = [int(eid) for eid in edge_ring if 0 <= int(eid) < len(edges)]
        if not ring_eids:
            return _copy_cage(cage)

        verts = [list(v) for v in cage.vertices]
        old_faces = [list(f) for f in cage.faces]
        new_faces: List[List[int]] = []
        split_faces: Set[int] = set()

        # Build edge -> face adjacency for old faces
        edge_to_faces: Dict[Tuple[int, int], List[int]] = {}
        for fi, face in enumerate(old_faces):
            n = len(face)
            for i in range(n):
                key = (min(face[i], face[(i + 1) % n]), max(face[i], face[(i + 1) % n]))
                edge_to_faces.setdefault(key, []).append(fi)

        # For each edge in the ring, find adjacent quad faces and split them
        for eid in ring_eids:
            a, b = edges[eid]
            key = (min(a, b), max(a, b))
            adj_fids = edge_to_faces.get(key, [])

            for fi in adj_fids:
                if fi in split_faces:
                    continue
                face = old_faces[fi]
                if len(face) != 4:
                    continue

                # Find where (a, b) appears in this face
                n = 4
                edge_pos = -1
                for i in range(n):
                    u, v_ = face[i], face[(i + 1) % n]
                    if (min(u, v_), max(u, v_)) == key:
                        edge_pos = i
                        break
                if edge_pos < 0:
                    continue

                # The quad has edges: 0-1, 1-2, 2-3, 3-0
                # The cut edge is at position edge_pos.
                # The opposite edge is at edge_pos + 2 (mod 4).
                opposite_pos = (edge_pos + 2) % 4
                c_ = face[opposite_pos]
                d_ = face[(opposite_pos + 1) % 4]

                # Midpoint on the cut edge
                va_pos = verts[face[edge_pos]]
                vb_pos = verts[face[(edge_pos + 1) % 4]]
                mid_ab_idx = len(verts)
                verts.append([
                    va_pos[0] + t * (vb_pos[0] - va_pos[0]),
                    va_pos[1] + t * (vb_pos[1] - va_pos[1]),
                    va_pos[2] + t * (vb_pos[2] - va_pos[2]),
                ])

                # Midpoint on the opposite edge
                vc_pos = verts[c_]
                vd_pos = verts[d_]
                mid_cd_idx = len(verts)
                verts.append([
                    vc_pos[0] + t * (vd_pos[0] - vc_pos[0]),
                    vc_pos[1] + t * (vd_pos[1] - vc_pos[1]),
                    vc_pos[2] + t * (vd_pos[2] - vc_pos[2]),
                ])

                # Split the quad into two quads
                # Original: [face[0], face[1], face[2], face[3]]
                # Cut is between face[edge_pos] and face[edge_pos+1]
                # Opposite is between face[opposite_pos] and face[opposite_pos+1]
                p0 = face[edge_pos]
                p1 = face[(edge_pos + 1) % 4]
                p2 = face[(edge_pos + 2) % 4]  # = c_
                p3 = face[(edge_pos + 3) % 4]

                # Quad 1: p0, mid_ab, mid_cd, p3
                # Quad 2: mid_ab, p1, p2, mid_cd
                new_faces.append([p0, mid_ab_idx, mid_cd_idx, p3])
                new_faces.append([mid_ab_idx, p1, p2, mid_cd_idx])
                split_faces.add(fi)

        # Add non-split faces
        for fi, face in enumerate(old_faces):
            if fi not in split_faces:
                new_faces.append(face)

        # Preserve sharpness where edge ids are still valid
        result = SubDCage(vertices=verts, faces=new_faces, sharpness=dict(cage.sharpness))
        return result
    except Exception:
        return _copy_cage(cage)


# ---------------------------------------------------------------------------
# Public: subd_loop_slide
# ---------------------------------------------------------------------------

def subd_loop_slide(
    cage: SubDCage,
    edge_loop: Sequence[int],
    t: float,
) -> SubDCage:
    """Slide an edge loop along its adjacent quad faces.

    Each vertex that belongs to exactly the edges in the loop is moved
    along the face-tangent direction of its adjacent faces.  Topology is
    unchanged (vertex, edge, and face counts stay the same).

    Parameters
    ----------
    cage : SubDCage
        Source cage.  Must have at least some quad faces.
    edge_loop : sequence of int
        Edge ids (from ``cage.cage_edges()``) forming the loop to slide.
        All edges must belong to quad faces.
    t : float
        Slide parameter in [-1, 1].  ``t=0`` → identity (no movement).
        ``t=+1`` → vertex moves to the position of the parallel edge on the
        +normal side.  ``t=-1`` → moves to the parallel edge on the -normal
        side.

    Returns
    -------
    SubDCage
        New cage with updated vertex positions and identical topology.
        Never raises; returns a copy of the input cage on any error.
    """
    try:
        t = float(t)
        if abs(t) < 1e-15:
            return _copy_cage(cage)

        edges = cage.cage_edges()
        loop_eids = set(int(eid) for eid in edge_loop if 0 <= int(eid) < len(edges))
        if not loop_eids:
            return _copy_cage(cage)

        # Collect the raw (a, b) edge pairs in the loop
        loop_edge_pairs: Set[Tuple[int, int]] = set()
        for eid in loop_eids:
            a, b = edges[eid]
            loop_edge_pairs.add((min(a, b), max(a, b)))

        # Build vertex → adjacent faces map
        vert_to_faces: Dict[int, List[int]] = {}
        for fi, face in enumerate(cage.faces):
            for vi in face:
                vert_to_faces.setdefault(vi, []).append(fi)

        # Identify which vertices belong to the loop edges
        loop_verts: Set[int] = set()
        for a, b in loop_edge_pairs:
            loop_verts.add(a)
            loop_verts.add(b)

        # For each loop vertex, compute the slide displacement.
        #
        # Strategy: for each face adjacent to the vertex, if that face
        # contains one of the loop edges, find the "opposite" edge of the
        # quad (the edge parallel to the loop edge on the other side of the
        # quad face).  The displacement is t * (midpoint_of_opposite_edge -
        # vertex_position), averaged over all contributing faces.
        #
        # Sign convention: positive t moves toward the opposite edge in the
        # face-traversal direction; negative t reverses.  For a box edge-loop
        # this means vertices move by t·edge_length in the face-tangent
        # direction.

        result = _copy_cage(cage)
        verts = result.vertices

        # Collect per-vertex slide vectors from each incident loop edge.
        vert_slide: Dict[int, List[List[float]]] = {}

        for a, b in loop_edge_pairs:
            pa = cage.vertices[a]
            pb = cage.vertices[b]
            edge_raw = _vec3_sub(pb, pa)
            edge_len = _vec3_length(edge_raw)
            if edge_len < 1e-15:
                continue

            # Gather "outward" faces: faces containing this edge whose
            # opposite edge is NOT in the loop (i.e. not a cap face).
            outward_face_tangents: List[List[float]] = []

            for face in cage.faces:
                if len(face) != 4:
                    continue
                n = 4
                edge_pos = -1
                for i in range(n):
                    u, v_ = face[i], face[(i + 1) % n]
                    if (min(u, v_), max(u, v_)) == (a, b):
                        edge_pos = i
                        break
                if edge_pos < 0:
                    continue

                # Opposite edge of this quad.
                opp_i = (edge_pos + 2) % n
                oc = face[opp_i]
                od = face[(opp_i + 1) % n]
                opp_key = (min(oc, od), max(oc, od))
                if opp_key in loop_edge_pairs:
                    continue  # cap face — skip

                # Use the face-traversal direction of the edge so that the
                # cross product with the face normal is consistently signed.
                # face[edge_pos] → face[(edge_pos+1)%n] is the traversal dir.
                if face[edge_pos] == a:
                    face_edge = _vec3_normalize(edge_raw)
                else:
                    face_edge = _vec3_normalize(_vec3_scale(edge_raw, -1.0))

                # tangent = normal × face_edge_dir, pointing "into" the face
                # (away from the loop edge, along the face plane).
                fn = _face_normal(cage.vertices, face)
                tang = _vec3_normalize(_vec3_cross(fn, face_edge))
                outward_face_tangents.append(tang)

            if not outward_face_tangents:
                continue

            # Average the tangent directions.
            nt = len(outward_face_tangents)
            avg_tang = [
                sum(tg[j] for tg in outward_face_tangents) / nt
                for j in range(3)
            ]
            avg_tang = _vec3_normalize(avg_tang)

            # Slide displacement = t * edge_len * avg_tang
            disp = _vec3_scale(avg_tang, t * edge_len)

            # Apply to both endpoints of the loop edge.
            for vi in (a, b):
                vert_slide.setdefault(vi, []).append(disp)

        for vi, displacements in vert_slide.items():
            nd = len(displacements)
            dx = sum(d[0] for d in displacements) / nd
            dy = sum(d[1] for d in displacements) / nd
            dz = sum(d[2] for d in displacements) / nd

            cv = cage.vertices[vi]
            verts[vi] = [cv[0] + dx, cv[1] + dy, cv[2] + dz]

        return result
    except Exception:
        return _copy_cage(cage)


# ---------------------------------------------------------------------------
# Public: subd_set_crease
# ---------------------------------------------------------------------------

def subd_set_crease(
    cage: SubDCage,
    edge_id: int,
    sharpness: float,
) -> SubDCage:
    """Set crease sharpness on an edge.

    Parameters
    ----------
    cage : SubDCage
    edge_id : int
        Edge index from ``cage.cage_edges()``.
    sharpness : float
        0.0 = smooth (removes crease), math.inf = hard.

    Returns
    -------
    New SubDCage with updated sharpness.  Never raises.
    """
    try:
        result = _copy_cage(cage)
        result._edge_list = cage._build_edge_list()[:]  # copy cached list
        edge_id = int(edge_id)
        if 0 <= edge_id < len(result.cage_edges()):
            if math.isinf(sharpness) or sharpness > 0.0:
                result.sharpness[edge_id] = float(sharpness)
            else:
                result.sharpness.pop(edge_id, None)
        return result
    except Exception:
        return _copy_cage(cage)


# ---------------------------------------------------------------------------
# Public: to_subd_surface
# ---------------------------------------------------------------------------

def to_subd_surface(
    cage: SubDCage,
    levels: int = 2,
) -> SubDSurface:
    """Evaluate a cage through the Catmull-Clark evaluator.

    Parameters
    ----------
    cage : SubDCage
        Author-time control cage.
    levels : int
        Number of CC subdivision levels (default 2).

    Returns
    -------
    SubDSurface
        Evaluated dense quad mesh.  Never raises.
    """
    try:
        levels = max(0, int(levels))
        mesh = cage.to_subd_mesh()
        result_mesh = catmull_clark_subdivide(mesh, levels=levels)
        return SubDSurface(mesh=result_mesh, cage=cage, levels=levels)
    except Exception:
        return SubDSurface(cage=cage, levels=levels)
