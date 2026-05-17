"""persistent_naming.py — face/edge persistent IDs that survive regeneration.

This module is the *crux* of "parametric vs scripted" CAD. When a user fillets
the top-front edge of a box and then changes the box's ``dx`` from 2 to 4, the
fillet must re-apply to the SAME topological edge of the now-larger box — not
a different edge, and not crash. Rhino, SolidWorks, Fusion, Onshape, CATIA all
have a layer like this; ours is one of the things they actively patent around.

------------------------------------------------------------------
ALGORITHM (as implemented)
------------------------------------------------------------------
A persistent id has three parts, packed into the string form
``feature_id::role::fingerprint``:

  1. **feature_id** — the UUID4 of the FEATURE that produced this entity.
     This pins identity to a *node in the feature DAG*, not to a Python
     object that will be regenerated.

  2. **role** — a stable, kind-specific label assigned by that feature's
     evaluator at construction time. Examples:

       * Box:        ``face:+X``, ``face:-Y``, ``edge:+Y/+Z``,
                     ``vertex:+X/+Y/+Z``
       * Cylinder:   ``face:lateral``, ``face:cap_bottom``,
                     ``face:cap_top``, ``edge:rim_bottom``,
                     ``edge:rim_top``, ``edge:seam``
       * Sphere:     ``face:surface``, ``edge:seam``
       * Boolean:    ``face:A:+X`` / ``face:B:lateral`` for surviving
                     input faces, ``face:boundary:<idx>`` for newly created
                     interface faces (idx assigned in deterministic
                     centroid-sorted order)
       * Chamfer:    ``face:bevel`` for the new bevel face; trimmed support
                     faces inherit ``face:A`` / ``face:B`` of the chamfered
                     edge
       * Fillet:     ``face:fillet`` for the new rolling-ball face; trimmed
                     supports inherit ``face:A`` / ``face:B``

     Roles are PURELY structural. They never reference numeric parameter
     values — that is the property that lets selectors survive parameter
     edits.

  3. **fingerprint** — a 12-char content-hash of the analytic geometry
     produced from (centroid, normal/axis, area-or-length), rounded to a
     fixed decimal precision. The fingerprint is NOT part of identity for
     normal resolution — it is a *tie-breaker* used to detect kind-change
     (e.g. the same feature_id/role now points at a face with a wildly
     different normal because the user replaced ``Box`` with ``Cylinder``).

------------------------------------------------------------------
RESOLUTION RULES
------------------------------------------------------------------
A ``PersistentSelector(feature_id, role)`` resolves against a live Body by:

  1. Looking up the producing feature's last ``NamingTable``.
  2. Returning the live Face/Edge/Vertex registered under ``role``.
  3. If ``role`` is absent from the table — the topological role no longer
     exists (e.g. the edge was eliminated by a too-large fillet, or the
     feature kind changed) — raising :class:`MissingReferenceError` with
     the persistent id and the list of available roles for debugging.

------------------------------------------------------------------
INTEROP WITH face_name_registry.py
------------------------------------------------------------------
The existing ``FaceNameRegistry`` (centroid/normal/area signatures) is used
internally by the BooleanFeature evaluator: pre-boolean role tags from the A
and B operands are *carried through* by signature match, leveraging the
existing ``remap_face_ids_across_boolean`` infrastructure. New boundary faces
get fresh role tags via ``assign_new_boundary_names`` semantics, but with the
boolean's ``feature_id::role`` schema rather than the legacy
``boolean-1.boundary.fuse.0`` string convention.

This module is additive: it does NOT modify ``face_name_registry.py``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

import numpy as np

from kerf_cad_core.geom.brep import (
    Body,
    CylinderSurface,
    Edge,
    Face,
    Plane,
    SphereSurface,
    Vertex,
)

# ---------------------------------------------------------------------------
# Fingerprint precision
# ---------------------------------------------------------------------------

# Coordinates rounded to this many decimals before hashing. Loose enough to
# absorb numerical noise from arithmetic in the evaluators, tight enough to
# distinguish geometrically different entities at "model unit" (mm) scale.
_FP_COORD_DECIMALS = 6
_FP_SCALAR_DECIMALS = 8

# Default tolerance used by face_role_for_box and similar role-inference
# helpers (matches the default tol of brep_build constructors).
_ROLE_TOL = 1e-7


# ---------------------------------------------------------------------------
# PersistentId — the string form of a stable identifier
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PersistentId:
    """Stable identifier for a face/edge/vertex of a Body produced by a
    feature.

    See module docstring for the algorithm. Construct via
    :func:`make_persistent_id`; use ``str(pid)`` to get the canonical
    ``feature_id::role::fingerprint`` form, or ``pid.short`` for the
    ``feature_id[:8]::role`` short form used in error messages.
    """

    feature_id: str
    role: str
    fingerprint: str

    def __str__(self) -> str:
        return f"{self.feature_id}::{self.role}::{self.fingerprint}"

    @property
    def short(self) -> str:
        """Human-readable short form (omits fingerprint)."""
        return f"{self.feature_id[:8]}::{self.role}"

    @classmethod
    def parse(cls, s: str) -> "PersistentId":
        """Parse the canonical ``feature_id::role::fingerprint`` form."""
        parts = s.split("::")
        if len(parts) != 3:
            raise ValueError(
                f"PersistentId.parse: expected 3 '::' parts, got {len(parts)}: {s!r}"
            )
        return cls(feature_id=parts[0], role=parts[1], fingerprint=parts[2])


def make_persistent_id(
    feature_id: str,
    role: str,
    entity: Any,
) -> PersistentId:
    """Build a :class:`PersistentId` from the producing feature, the structural
    role, and the live topology entity (Face/Edge/Vertex)."""
    fp = entity_fingerprint(entity)
    return PersistentId(feature_id=feature_id, role=role, fingerprint=fp)


# ---------------------------------------------------------------------------
# Fingerprint computation
# ---------------------------------------------------------------------------


def _round_tuple(values, decimals: int) -> Tuple[float, ...]:
    return tuple(round(float(v), decimals) for v in values)


def _face_centroid_and_normal(face: Face) -> Tuple[np.ndarray, np.ndarray]:
    """Return (centroid, normal) for a face using its vertex ring.

    For planar faces, this is exact; for analytic curved faces (cylinder,
    sphere), this gives an approximation that is still stable across
    regenerations because the surface object's analytic params are stable.
    """
    surf = face.surface
    # Centroid: average of all unique vertex points in the outer loop.
    outer = face.outer_loop()
    if outer is not None and outer.coedges:
        pts = []
        for ce in outer.coedges:
            pts.append(np.asarray(ce.start_point(), dtype=float))
        # de-dup by rounded coordinates
        seen = set()
        uniq = []
        for p in pts:
            key = tuple(round(float(x), 9) for x in p)
            if key not in seen:
                seen.add(key)
                uniq.append(p)
        centroid = np.mean(np.array(uniq), axis=0) if uniq else np.zeros(3)
    else:
        centroid = np.zeros(3)
    # Normal: prefer the surface's analytic mid-uv normal
    try:
        normal = face.surface_normal(0.5, 0.5)
    except Exception:
        normal = np.zeros(3)
    # For curved surfaces, fallback to a robust analytic centroid where
    # available, so that two regenerations of the same box face produce the
    # same fingerprint even if their loops were re-built in a different order.
    if isinstance(surf, Plane):
        # already correct
        pass
    elif isinstance(surf, CylinderSurface):
        # Use the surface origin (cylinder axis start) projected to the face's
        # mean-vertex height for stability.
        try:
            axis = np.asarray(surf.axis, dtype=float)
            origin = np.asarray(surf.origin, dtype=float)
            mid_h = float(np.dot(centroid - origin, axis))
            centroid = origin + mid_h * axis
            normal = axis  # cylindrical surface's "characteristic" direction
        except Exception:
            pass
    elif isinstance(surf, SphereSurface):
        try:
            centroid = np.asarray(surf.center, dtype=float)
            normal = np.array([0.0, 0.0, 1.0])
        except Exception:
            pass
    return centroid, normal


def _face_area(face: Face) -> float:
    """Polygonal area of a face's outer loop (triangle fan)."""
    outer = face.outer_loop()
    if outer is None or len(outer.coedges) < 3:
        return 0.0
    pts = [np.asarray(ce.start_point(), dtype=float) for ce in outer.coedges]
    p0 = pts[0]
    total = 0.0
    for i in range(1, len(pts) - 1):
        a = pts[i] - p0
        b = pts[i + 1] - p0
        total += 0.5 * float(np.linalg.norm(np.cross(a, b)))
    return total


def _edge_fingerprint_inputs(edge: Edge) -> Tuple[Tuple[float, ...], float]:
    """(midpoint, length) for an edge."""
    try:
        a = np.asarray(edge.start_point(), dtype=float)
        b = np.asarray(edge.end_point(), dtype=float)
        mid = 0.5 * (a + b)
        length = float(np.linalg.norm(b - a))
    except Exception:
        mid = np.zeros(3)
        length = 0.0
    return _round_tuple(mid, _FP_COORD_DECIMALS), round(
        length, _FP_SCALAR_DECIMALS
    )


def entity_fingerprint(entity: Any) -> str:
    """Compute a 12-char hex content-hash of an entity's analytic geometry.

    The fingerprint is *intentionally not used as identity*. It is the
    tie-breaker that detects kind-change: when the same ``feature_id::role``
    points at an entity whose fingerprint is wildly different from the last
    one stored, downstream consumers can flag it as a structural mutation
    rather than a parametric refresh.
    """
    if isinstance(entity, Face):
        c, n = _face_centroid_and_normal(entity)
        a = _face_area(entity)
        raw = (
            f"face|{_round_tuple(c, _FP_COORD_DECIMALS)}|"
            f"{_round_tuple(n, _FP_COORD_DECIMALS)}|"
            f"{round(a, _FP_SCALAR_DECIMALS)}"
        )
    elif isinstance(entity, Edge):
        mid, length = _edge_fingerprint_inputs(entity)
        raw = f"edge|{mid}|{length}"
    elif isinstance(entity, Vertex):
        p = np.asarray(entity.point, dtype=float)
        raw = f"vertex|{_round_tuple(p, _FP_COORD_DECIMALS)}"
    else:
        raw = f"other|{type(entity).__name__}|{repr(entity)}"
    digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
    return digest


# ---------------------------------------------------------------------------
# NamingTable — per-feature role -> live-entity map
# ---------------------------------------------------------------------------


@dataclass
class NamingTable:
    """Maps a feature's structural role tags to live entities in the Body it
    just produced. Owned per-feature, rebuilt on every evaluation.

    The dict is keyed by ``role`` string (e.g. ``face:+X``) and stores both
    the live entity reference (Face/Edge/Vertex) and the persistent id for
    fingerprint-based change detection.
    """

    feature_id: str
    faces: Dict[str, Face] = field(default_factory=dict)
    edges: Dict[str, Edge] = field(default_factory=dict)
    vertices: Dict[str, Vertex] = field(default_factory=dict)

    # Cached PersistentIds — recomputed on register so callers can compare
    # across regenerations.
    face_ids: Dict[str, PersistentId] = field(default_factory=dict)
    edge_ids: Dict[str, PersistentId] = field(default_factory=dict)
    vertex_ids: Dict[str, PersistentId] = field(default_factory=dict)

    def register_face(self, role: str, face: Face) -> PersistentId:
        self.faces[role] = face
        pid = make_persistent_id(self.feature_id, f"face:{role}", face)
        self.face_ids[role] = pid
        return pid

    def register_edge(self, role: str, edge: Edge) -> PersistentId:
        self.edges[role] = edge
        pid = make_persistent_id(self.feature_id, f"edge:{role}", edge)
        self.edge_ids[role] = pid
        return pid

    def register_vertex(self, role: str, vertex: Vertex) -> PersistentId:
        self.vertices[role] = vertex
        pid = make_persistent_id(self.feature_id, f"vertex:{role}", vertex)
        self.vertex_ids[role] = pid
        return pid

    # ── lookup ────────────────────────────────────────────────────────────

    def face_roles(self) -> List[str]:
        return sorted(self.faces.keys())

    def edge_roles(self) -> List[str]:
        return sorted(self.edges.keys())

    def vertex_roles(self) -> List[str]:
        return sorted(self.vertices.keys())

    def all_roles(self) -> Dict[str, List[str]]:
        return {
            "face": self.face_roles(),
            "edge": self.edge_roles(),
            "vertex": self.vertex_roles(),
        }


# ---------------------------------------------------------------------------
# Role-inference helpers for the evaluators
# ---------------------------------------------------------------------------


_AXIS_LABELS = ((0, "+X", "-X"), (1, "+Y", "-Y"), (2, "+Z", "-Z"))


def face_role_for_box_planar(face: Face, tol: float = _ROLE_TOL) -> Optional[str]:
    """For an axis-aligned planar face, return the role tag (``+X``, ``-Y``,
    etc.) iff the face normal is parallel to a world axis within ``tol``.

    Returns None if the face is not planar or is not axis-aligned (in which
    case the caller should fall back to a generic naming scheme).
    """
    if not isinstance(face.surface, Plane):
        return None
    try:
        n = face.surface_normal(0.5, 0.5)
    except Exception:
        return None
    n = np.asarray(n, dtype=float)
    for axis_idx, pos_lbl, neg_lbl in _AXIS_LABELS:
        target = np.zeros(3)
        target[axis_idx] = 1.0
        dot = float(np.dot(n, target))
        if abs(dot - 1.0) <= tol:
            return pos_lbl
        if abs(dot + 1.0) <= tol:
            return neg_lbl
    return None


def edge_role_for_box(
    edge: Edge,
    incident_face_roles: Mapping[Face, str],
    tol: float = _ROLE_TOL,
) -> Optional[str]:
    """Combine the two incident face roles of a box edge into a stable edge
    role tag like ``+Y/+Z``.

    The two role strings are concatenated in sorted order so the result is
    invariant to traversal direction.
    """
    incident = [r for r in incident_face_roles.values() if r is not None]
    if len(incident) < 2:
        return None
    a, b = sorted(incident[:2])
    return f"{a}/{b}"


def vertex_role_for_box(point: np.ndarray, box_centroid: np.ndarray) -> str:
    """Octant label for a box vertex, e.g. ``+X/+Y/-Z``."""
    labels = []
    for axis_idx, pos_lbl, neg_lbl in _AXIS_LABELS:
        if float(point[axis_idx]) > float(box_centroid[axis_idx]):
            labels.append(pos_lbl)
        else:
            labels.append(neg_lbl)
    return "/".join(labels)


# ---------------------------------------------------------------------------
# MissingReferenceError lives in feature.py to avoid circular imports;
# re-exported here for convenience.
# ---------------------------------------------------------------------------

from kerf_cad_core.geom.history.feature import MissingReferenceError  # noqa: E402,F401


__all__ = [
    "PersistentId",
    "NamingTable",
    "make_persistent_id",
    "entity_fingerprint",
    "face_role_for_box_planar",
    "edge_role_for_box",
    "vertex_role_for_box",
    "MissingReferenceError",
]
