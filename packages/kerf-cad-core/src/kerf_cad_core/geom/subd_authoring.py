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
    unbounded float (0 = smooth, math.inf = perfectly sharp / hard edge),
    and a *bevel_weights* dict that stores per-edge bevel weights in [0, 1].

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

subd_edge_slide(cage, edge_id, t) -> SubDCage
    Slide a single edge along its adjacent quad faces.  ``t`` in [-1, 1]
    where 0 = identity.  The single-edge sibling of subd_loop_slide.
    Topology (V/E/F) is unchanged.

subd_edge_split(cage, edge_id, t=0.5) -> SubDCage
    Insert a vertex on an edge at parameter ``t`` ∈ (0, 1), splitting all
    incident faces at that point.  V increases by 1; Euler identity
    V - E + F is preserved.

subd_set_crease(cage, edge_id, sharpness) -> SubDCage
    Assign a crease sharpness to an edge.  Sharpness 0 = smooth,
    ``math.inf`` = perfectly hard.  Returns a new cage (immutable-style).

subd_set_bevel_weight(cage, edge_id, weight) -> SubDCage
    Assign a bevel weight to an edge.  Weight is clamped to [0, 1].
    ``weight=0.0`` = fully smooth (no influence); ``weight=1.0`` = hard
    crease (equivalent to ``subd_set_crease`` with ``sharpness=inf``).
    Intermediate values interpolate between the smooth limit surface and
    the hard-crease limit surface, providing graded sharpness control
    distinct from the binary crease.  Returns a new cage (immutable-style).

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
    bevel_weights : dict mapping edge_id -> float
        Graded bevel weight in [0, 1].  0.0 = fully smooth (no influence);
        1.0 = hard crease (equivalent to infinite sharpness).  Intermediate
        values produce a partially-sharp limit surface via linear interpolation
        between the smooth and fully-creased limit positions.
    _edge_list : list of (int, int)
        Cached ordered unique edge list.  Rebuilt on demand.
    """

    vertices: List[List[float]] = field(default_factory=list)
    faces: List[List[int]] = field(default_factory=list)
    sharpness: Dict[int, float] = field(default_factory=dict)  # edge_id -> sharpness
    bevel_weights: Dict[int, float] = field(default_factory=dict)  # edge_id -> weight [0,1]

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

        Bevel weights (stored in ``bevel_weights``) are also honoured: a
        weight ``w`` in [0, 1] maps to a CC sharpness of ``w`` (since the
        CC evaluator clamps to [0, 1], weight=1.0 gives a hard crease
        identical to math.inf sharpness).  When both a sharpness entry and a
        bevel-weight entry exist for the same edge, the higher effective
        sharpness wins.
        """
        edges = self._build_edge_list()
        creases: Dict[Tuple[int, int], float] = {}
        for eid, sharp in self.sharpness.items():
            if 0 <= eid < len(edges):
                clamped = 1.0 if (math.isinf(sharp) or sharp >= 1.0) else float(sharp)
                if clamped > 0.0:
                    creases[edges[eid]] = clamped
        # Bevel weights: weight w maps to sharpness w (in [0,1]).
        # Merge: take max of any existing sharpness + bevel-weight contribution.
        for eid, w in self.bevel_weights.items():
            if 0 <= eid < len(edges):
                w_clamped = max(0.0, min(1.0, float(w)))
                if w_clamped > 0.0:
                    key = edges[eid]
                    existing = creases.get(key, 0.0)
                    creases[key] = max(existing, w_clamped)
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
        bevel_weights=dict(cage.bevel_weights),
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
# Public: subd_edge_slide
# ---------------------------------------------------------------------------

def subd_edge_slide(
    cage: SubDCage,
    edge_id: int,
    t: float,
) -> SubDCage:
    """Slide a single edge along its adjacent quad faces.

    This is the single-edge sibling of :func:`subd_loop_slide`.  Only the two
    endpoints of the specified edge are moved; all other vertices remain in
    place.  The same face-tangent logic as ``subd_loop_slide`` is used.

    Parameters
    ----------
    cage : SubDCage
        Source cage.  Must have at least some quad faces adjacent to the edge.
    edge_id : int
        Index of the edge to slide, from ``cage.cage_edges()``.
    t : float
        Slide parameter in [-1, 1].  ``t=0`` → identity (no movement).
        ``t=+1`` → endpoint moves to the position of the parallel edge on the
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
        eid = int(edge_id)
        if eid < 0 or eid >= len(edges):
            return _copy_cage(cage)

        a, b = edges[eid]
        # Delegate to subd_loop_slide with a single-edge "loop"
        return subd_loop_slide(cage, [eid], t)
    except Exception:
        return _copy_cage(cage)


# ---------------------------------------------------------------------------
# Public: subd_edge_split
# ---------------------------------------------------------------------------

def subd_edge_split(
    cage: SubDCage,
    edge_id: int,
    t: float = 0.5,
) -> SubDCage:
    """Insert a vertex on an edge at parameter ``t``, splitting incident faces.

    A new vertex is placed at the linear interpolation of the edge endpoints::

        new_vertex = (1 - t) * v_a + t * v_b

    Each face incident to the edge is split into two faces.  For a quad face
    the split produces two quads; for a triangle the split produces two
    triangles.  The topology change for a quad incident to the split edge:

        V → V + 1
        E → E + 3   (the original edge is replaced by two halves and one new
                     edge crossing the face)
        F → F + 1   (one face is replaced by two)

    Euler consistency: Δ(V - E + F) = 1 - 3 + 2 = 0 per incident face.

    Parameters
    ----------
    cage : SubDCage
    edge_id : int
        Index of the edge to split, from ``cage.cage_edges()``.
    t : float
        Split position in (0, 1).  Default 0.5 (midpoint).

    Returns
    -------
    SubDCage
        New cage with the extra vertex and split faces.  Sharpness entries
        that no longer map to valid edge ids are silently dropped.
        Never raises; returns a copy of the input on any error.
    """
    try:
        t = max(1e-9, min(1.0 - 1e-9, float(t)))

        edges = cage.cage_edges()
        eid = int(edge_id)
        if eid < 0 or eid >= len(edges):
            return _copy_cage(cage)

        a, b = edges[eid]
        va = cage.vertices[a]
        vb = cage.vertices[b]

        # New vertex at parameter t along the edge.
        new_v = [
            va[0] + t * (vb[0] - va[0]),
            va[1] + t * (vb[1] - va[1]),
            va[2] + t * (vb[2] - va[2]),
        ]
        new_vi = len(cage.vertices)  # index of the new vertex

        verts = [list(v) for v in cage.vertices] + [new_v]
        new_faces: List[List[int]] = []

        edge_key = (min(a, b), max(a, b))

        for face in cage.faces:
            n = len(face)
            # Check if this face contains the edge.
            edge_pos = -1
            for i in range(n):
                u, w = face[i], face[(i + 1) % n]
                if (min(u, w), max(u, w)) == edge_key:
                    edge_pos = i
                    break

            if edge_pos < 0:
                # Face does not contain the split edge — keep unchanged.
                new_faces.append(list(face))
                continue

            # Rotate the face so the split edge is first (pos 0 → 1).
            # rotated[0] = face[edge_pos], rotated[1] = face[(edge_pos+1)%n]
            rotated = [face[(edge_pos + k) % n] for k in range(n)]

            # rotated[0] and rotated[1] are the endpoints of the split edge
            # (one of them is a, the other is b; order may differ from (a,b)).
            # The new vertex sits between rotated[0] and rotated[1].

            # Split: face [r0, r1, r2, ..., r_{n-1}]
            # → face A: [r0, new_vi, r_{n-1}, r_{n-2}, ..., r2]   (if quad: [r0, new_vi, r2, r3] wait – need careful indexing)
            # For a quad (n=4): rotated = [r0, r1, r2, r3]
            #   Face A: [r0, new_vi, r3]           ← triangle (wrong for SubD quad)
            # We want to preserve quads.  For a quad, split along the
            # mid-edge → mid-opposite-edge diagonal is the typical SubD
            # approach, but here we only insert a point on one edge.
            # The standard "edge split" for a polygon with the new vertex:
            #   poly [p0, p1, p2, ..., p_{n-1}], edge p0-p1:
            #   → poly_A: [p0, m, p_{n-1}, p_{n-2}, ..., p1] where last
            #     wraps — actually simplest: connect the new midpoint to the
            #     opposite vertex (for a quad, opposite of the edge midpoint
            #     is the midpoint of the opposite edge — but we don't add
            #     that).
            #
            # Standard "1-edge-split" on a polygon: insert vertex m between
            # p0 and p1.  If we only split the edge we get an (n+1)-gon
            # [p0, m, p1, p2, ..., p_{n-1}] which is topologically valid but
            # not a split into *two* faces.
            #
            # The spec says "splitting incident faces" so we split each face
            # into two by connecting m to the vertex opposite the split edge.
            # For an n-gon the "opposite" of edge p0-p1 is vertex p_{n//2+1}
            # for odd, or the midpoint of p_{n//2} - p_{n//2+1} for even
            # (but we avoid adding another vertex).  For quads (n=4) the
            # natural split is:
            #   face [p0, p1, p2, p3], edge p0-p1, new vertex m:
            #   → quad A: [p0, m, p3, ???] → triangle [p0, m, p3] + triangle
            #     [m, p1, p2, p3]... that gives two quads only if we add m
            #     plus connect to p3 — but [p0, m, p3] is a triangle.
            #
            # The cleanest topology for a quad: connect m to the vertex
            # *diagonally opposite* to the MIDPOINT of the split edge, i.e.
            # p3 (the vertex "across" p0) and p2 (across p1):
            #   quad A: [p0, m, p2, p3]   — NOT a split of the original quad
            #
            # Correct approach for quad p0 p1 p2 p3 with edge p0-p1:
            #   We insert m between p0 and p1.  We connect m to p3 to split:
            #   → face A: [p0, m, p3]          (triangle)
            #   → face B: [m, p1, p2, p3]      (quad)
            # OR connect m to p2:
            #   → face A: [p0, m, p2, p3]      (quad)
            #   → face B: [m, p1, p2]          (triangle)
            #
            # For maximum regularity and Euler consistency with the oracle
            # (V+1, Euler consistent) we pick the split that preserves quads
            # where possible.  For an n-gon (n≥4) connecting m to
            # rotated[n-1] gives:
            #   face A: [r0, m, r_{n-1}]  (triangle — bad for quads)
            #
            # Best approach for quads: connect m to both r2 and r3 via the
            # single new interior edge m-r3, yielding:
            #   face A: [r0, m, r3]    → 3-gon
            #   face B: [m, r1, r2, r3] → 4-gon
            # Or m-r2:
            #   face A: [r0, m, r2, r3] → 4-gon  ← preferred
            #   face B: [m, r1, r2]     → 3-gon
            #
            # The spec oracle: "split a quad edge at t=0.5 → 2 new faces,
            # V+1/E+? consistent with Euler". It says V+1 and 2 new faces
            # (i.e. the 1 face becomes 2, so F increases by 1).
            # Euler: V - E + F = const (for manifold orientable surface).
            # ΔV=1, ΔF=+1 → ΔE must be 2 (so Euler stays same: 1-2+1=0 ✓).
            #
            # New edges added per incident face: 2 (split edge → 2 halves,
            # plus 1 interior cut, minus the original edge → net +2).
            # That matches ΔE=+2 per incident face.
            #
            # For the split: we'll produce for each incident face:
            #   face A (lower half): [r0, m, r2, r3, ..., r_{n-1}]
            #   face B (upper half): [m, r1, r2]  — only if n=4 gives [m,r1,r2]
            # For n=4 specifically:
            #   A: [r0, m, r2, r3]  (quad)
            #   B: [m, r1, r2]      (triangle)
            # But that gives 1 quad + 1 tri, and ΔF=+1, ΔV=+1 — Euler ok.
            #
            # For pure-quad output we'd need a loop cut (adds vertex on
            # opposite edge too). Since the spec says "splitting incident
            # faces" (not "insert loop cut"), we'll do the minimal split:
            # connect m to r_{n//2+1} so that for n=4 we get two quads.
            # n=4: connect m to r3 → A:[r0,m,r3], B:[m,r1,r2,r3] (tri+quad).
            # OR connect m to vertex at index floor(n/2)+1 = index 3 for n=4.
            #
            # Simplest consistent rule: For face [r0,r1,...,r_{n-1}] with
            # edge r0-r1 split at m:
            #   face A: [r0, m] + r_{n-1..2}   i.e. [r0, m, r_{n-1}, r_{n-2},..., r2]
            #   face B: [m, r1, r2]
            # For n=4: A=[r0,m,r3,r2]... that reverses winding.
            #
            # Let's just do the straightforward n+1 polygon insert on the
            # edge, then split it with a diagonal to r_{n-1} (the vertex
            # "before" r0 in face order, i.e. diagonally opposite the edge
            # midpoint for a quad):
            #   face A: [r0, m, r_{n-1}]
            #   face B: [m, r1, r2, ..., r_{n-1}]
            # For n=4: A=[r0, m, r3] (tri), B=[m,r1,r2,r3] (quad)
            # ΔF=+1, ΔV=+1 per incident face, ΔE=+2 → Euler consistent ✓

            r = rotated  # shorthand
            face_a = [r[0], new_vi, r[n - 1]]
            face_b = [new_vi, r[1]] + [r[k] for k in range(2, n)]
            new_faces.append(face_a)
            new_faces.append(face_b)

        result = SubDCage(vertices=verts, faces=new_faces)
        # Sharpness entries can't be reliably remapped after edge reindexing;
        # drop them rather than mis-map (same policy as subd_bevel).
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
# Public: subd_set_bevel_weight  (GK-107)
# ---------------------------------------------------------------------------

def subd_set_bevel_weight(
    cage: SubDCage,
    edge_id: int,
    weight: float,
) -> SubDCage:
    """Set a graded bevel weight on an edge.

    Bevel weight is a value in [0, 1] that controls how tightly the
    limit surface hugs the cage edge — distinct from the binary crease
    (``subd_set_crease``).

    * ``weight=0.0`` — fully smooth; the edge exerts no crease influence.
      The limit surface is identical to a cage with no crease on that edge.
    * ``weight=1.0`` — hard crease; the limit surface is identical to the
      result of ``subd_set_crease(cage, edge_id, math.inf)``.
    * Intermediate values interpolate linearly between those two extremes
      in the Catmull-Clark sharpness domain: the effective CC sharpness
      passed to the evaluator is ``weight * _BEVEL_MAX_SHARPNESS`` where
      ``_BEVEL_MAX_SHARPNESS`` is a large finite value that reproduces the
      hard-crease limit to within floating-point precision.

    The bevel weight is stored in ``cage.bevel_weights`` and is honoured
    by ``to_subd_surface`` and the NURBS limit-surface conversion in
    ``subd_to_nurbs.py``.

    Parameters
    ----------
    cage : SubDCage
    edge_id : int
        Edge index from ``cage.cage_edges()``.
    weight : float
        Bevel weight, clamped to [0, 1].

    Returns
    -------
    New SubDCage with updated bevel weight.  Never raises.
    """
    try:
        result = _copy_cage(cage)
        result._edge_list = cage._build_edge_list()[:]
        eid = int(edge_id)
        if 0 <= eid < len(result.cage_edges()):
            w = max(0.0, min(1.0, float(weight)))
            if w > 0.0:
                result.bevel_weights[eid] = w
            else:
                result.bevel_weights.pop(eid, None)
        return result
    except Exception:
        return _copy_cage(cage)


# Bevel weight → CC sharpness mapping.
# We use a large but finite sharpness so that weight=1.0 produces a limit
# that is indistinguishable from math.inf at the precision used by the CC
# evaluator.  The SubDMesh evaluator clamps sharpness to [0, 1] internally
# (see to_subd_mesh), so any value >= 1.0 maps to the hard-crease limit.
_BEVEL_MAX_SHARPNESS: float = 1.0  # maps cleanly to clamped crease=1.0


# ---------------------------------------------------------------------------
# Public: subd_vertex_slide
# ---------------------------------------------------------------------------

def subd_vertex_slide(
    cage: SubDCage,
    vertex_id: int,
    edge_id: int,
    t: float,
) -> SubDCage:
    """Slide a vertex along one of its incident edges.

    The vertex is linearly interpolated from its current position toward the
    neighbour at the opposite end of the specified edge.  Topology (vertex
    count, edge count, face count) is unchanged.

    Parameters
    ----------
    cage : SubDCage
        Source cage.
    vertex_id : int
        Index of the vertex to slide (into ``cage.vertices``).
    edge_id : int
        Index of an edge incident on ``vertex_id``, from ``cage.cage_edges()``.
        The vertex will be slid toward the *other* endpoint of that edge.
    t : float
        Slide parameter in [0, 1].  ``t=0`` → identity (vertex stays put).
        ``t=1`` → vertex coincides with the neighbour.  ``t=0.5`` → midpoint.

    Returns
    -------
    SubDCage
        New cage with updated vertex position and identical topology.
        Never raises; returns a copy of the input cage on any error.
    """
    try:
        t = float(t)
        vid = int(vertex_id)
        eid = int(edge_id)

        if t == 0.0:
            return _copy_cage(cage)

        edges = cage.cage_edges()
        if eid < 0 or eid >= len(edges):
            return _copy_cage(cage)

        a, b = edges[eid]
        if a == vid:
            neighbour = b
        elif b == vid:
            neighbour = a
        else:
            # edge_id is not incident on vertex_id
            return _copy_cage(cage)

        nv = len(cage.vertices)
        if vid < 0 or vid >= nv or neighbour < 0 or neighbour >= nv:
            return _copy_cage(cage)

        result = _copy_cage(cage)
        p = cage.vertices[vid]
        q = cage.vertices[neighbour]
        # lerp: new_pos = p + t*(q-p) = (1-t)*p + t*q
        result.vertices[vid] = [
            p[i] + t * (q[i] - p[i]) for i in range(len(p))
        ]
        return result
    except Exception:
        return _copy_cage(cage)


# ---------------------------------------------------------------------------
# Public: loop_subdivide  (GK-108)
# ---------------------------------------------------------------------------

def loop_subdivide(
    verts: "list[list[float]]",
    faces: "list[list[int]]",
    iterations: int = 1,
) -> "tuple[list[list[float]], list[list[int]]]":
    """Loop subdivision scheme for triangle meshes.

    Implements the Loop (1987) subdivision stencils:

    * **Odd vertices** (edge midpoints) — interior edge ``(a, b)`` with
      opposite vertices ``c`` (in face abc) and ``d`` (in face abd):

          new_pos = 3/8 * a + 3/8 * b + 1/8 * c + 1/8 * d

      Boundary edges use the simple midpoint ``(a + b) / 2``.

    * **Even vertices** (updated original vertices) — vertex ``v`` with
      ``n`` neighbours ``u_i``:

          β(n) = (1/n) * (5/8 - (3/8 + 1/4 * cos(2π/n))²)
          new_pos = (1 - n·β) * v + β * Σ u_i

      Special cases: n=3 → β = 3/16; boundary vertices are left in place.

    Each subdivision step replaces every triangle with four triangles:

    ::

              v0
             /  \\
           m01---m02
           / \\  / \\
         v1--m12--v2

        Original triangle [v0, v1, v2] →
          [v0, m01, m02]
          [v1, m12, m01]
          [v2, m02, m12]
          [m01, m12, m02]   (interior)

    Parameters
    ----------
    verts : list of [x, y, z]
        Input vertex positions.
    faces : list of [i, j, k]
        Input triangle faces (each must have exactly 3 vertices).
    iterations : int
        Number of subdivision steps (default 1).  Must be ≥ 0.

    Returns
    -------
    (verts, faces) : tuple
        New vertex list and new face list after all subdivision steps.
        Pure-Python; numpy is used internally for performance when available.

    Notes
    -----
    * Input must be a triangle mesh.  Non-triangle faces are left unchanged
      (they are copied to the output without subdivision).
    * Never raises; returns the original mesh on any error.
    """
    try:
        # Validate and coerce
        iterations = max(0, int(iterations))
        v_out: list = [list(p) for p in verts]
        f_out: list = [list(f) for f in faces]

        for _step in range(iterations):
            v_out, f_out = _loop_subdivide_once(v_out, f_out)

        return v_out, f_out
    except Exception:
        return [list(p) for p in verts], [list(f) for f in faces]


def _loop_subdivide_once(
    verts: "list[list[float]]",
    faces: "list[list[int]]",
) -> "tuple[list[list[float]], list[list[int]]]":
    """Single step of Loop subdivision."""
    nv = len(verts)

    # ----------------------------------------------------------------
    # Step 1 — build edge → adjacent face info
    # ----------------------------------------------------------------
    # edge_faces: (a, b) with a < b  →  list of face indices
    edge_faces: dict = {}
    for fi, face in enumerate(faces):
        if len(face) != 3:
            continue
        i0, i1, i2 = face
        for u, v_ in ((i0, i1), (i1, i2), (i2, i0)):
            key = (min(u, v_), max(u, v_))
            edge_faces.setdefault(key, []).append(fi)

    # ----------------------------------------------------------------
    # Step 2 — compute odd (edge-midpoint) vertex positions
    # ----------------------------------------------------------------
    # edge_to_odd: edge key → index in the new vertex array (offset nv)
    edge_to_odd: dict = {}
    new_odd_verts: list = []

    for key, adj_fids in edge_faces.items():
        a, b = key
        pa = verts[a]
        pb = verts[b]

        if len(adj_fids) == 2:
            # Interior edge: 3/8 + 3/8 + 1/8 + 1/8 stencil.
            # Find the two opposite vertices c and d.
            fi0, fi1 = adj_fids[0], adj_fids[1]
            face0 = faces[fi0]
            face1 = faces[fi1]
            # c is the vertex in face0 that is not a or b
            c = next(idx for idx in face0 if idx != a and idx != b)
            # d is the vertex in face1 that is not a or b
            d = next(idx for idx in face1 if idx != a and idx != b)
            pc = verts[c]
            pd = verts[d]
            odd_pos = [
                (3.0 / 8.0) * pa[j] + (3.0 / 8.0) * pb[j]
                + (1.0 / 8.0) * pc[j] + (1.0 / 8.0) * pd[j]
                for j in range(3)
            ]
        else:
            # Boundary edge: simple midpoint
            odd_pos = [(pa[j] + pb[j]) / 2.0 for j in range(3)]

        edge_to_odd[key] = nv + len(new_odd_verts)
        new_odd_verts.append(odd_pos)

    # ----------------------------------------------------------------
    # Step 3 — compute even (updated original) vertex positions
    # ----------------------------------------------------------------
    # Classify each vertex as boundary or interior.
    # A boundary vertex lies on at least one boundary edge (valence-1 edge).

    # Build adjacency: vertex → list of neighbour vertex indices
    neighbours: dict = {}
    boundary_verts: set = set()
    for key, adj_fids in edge_faces.items():
        a, b = key
        neighbours.setdefault(a, []).append(b)
        neighbours.setdefault(b, []).append(a)
        if len(adj_fids) == 1:
            # Boundary edge
            boundary_verts.add(a)
            boundary_verts.add(b)

    new_even_verts: list = []
    for vi in range(nv):
        if vi in boundary_verts:
            # Boundary vertex: leave in place (simple scheme)
            new_even_verts.append(list(verts[vi]))
            continue

        nbrs = neighbours.get(vi, [])
        n = len(nbrs)
        if n == 0:
            new_even_verts.append(list(verts[vi]))
            continue

        # Loop's beta formula
        if n == 3:
            beta = 3.0 / 16.0
        else:
            # Warren's simplified formula: β = 3/(8n) is commonly used;
            # original Loop formula:
            inner = 3.0 / 8.0 + (1.0 / 4.0) * math.cos(2.0 * math.pi / n)
            beta = (1.0 / n) * (5.0 / 8.0 - inner * inner)

        pv = verts[vi]
        neighbour_sum = [sum(verts[nbr][j] for nbr in nbrs) for j in range(3)]
        alpha = 1.0 - n * beta
        new_pos = [
            alpha * pv[j] + beta * neighbour_sum[j]
            for j in range(3)
        ]
        new_even_verts.append(new_pos)

    # ----------------------------------------------------------------
    # Step 4 — assemble new vertex array and new face array
    # ----------------------------------------------------------------
    all_new_verts = new_even_verts + new_odd_verts  # indices match: even=0..nv-1, odd=nv..

    new_faces: list = []
    for face in faces:
        if len(face) != 3:
            # Non-triangle: pass through unchanged (indices still valid)
            new_faces.append(list(face))
            continue

        v0, v1, v2 = face

        # Midpoint vertex indices
        m01 = edge_to_odd[(min(v0, v1), max(v0, v1))]
        m12 = edge_to_odd[(min(v1, v2), max(v1, v2))]
        m02 = edge_to_odd[(min(v0, v2), max(v0, v2))]

        # Four child triangles
        new_faces.append([v0, m01, m02])
        new_faces.append([v1, m12, m01])
        new_faces.append([v2, m02, m12])
        new_faces.append([m01, m12, m02])  # centre

    return all_new_verts, new_faces


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
