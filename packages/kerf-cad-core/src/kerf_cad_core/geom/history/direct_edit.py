"""direct_edit.py — direct-edit verbs for the parametric history layer.

Direct edits operate on the CURRENT ``Body`` snapshot (not on params). They
rebuild a new ``Body`` with the modified geometry and, when committed via
:func:`commit_direct_edits_to_dag`, translate into a ``DirectEditFeature``
DAG node so that future parametric edits still replay correctly.

Contract
--------
* No frozen module is imported for writing: dag.py / feature.py /
  evaluators.py / persistent_naming.py / brep.py / boolean.py /
  brep_build.py are read-only dependencies.
* All operations return a fresh ``Body``; the input ``body`` is never
  mutated.
* Persistent face IDs are preserved where topologically possible; faces that
  were deleted raise :class:`~kerf_cad_core.geom.history.feature.MissingReferenceError`
  on subsequent resolution.

Supported primitives
--------------------
All direct-edit verbs in this module operate on bodies composed entirely of
planar (:class:`~kerf_cad_core.geom.brep.Plane`) faces — i.e. the output of
:func:`~kerf_cad_core.geom.brep_build.box_to_body` and bodies derived from
it by chamfer/fillet. Non-planar faces trigger ``DirectEditError`` with
``reason="non-planar face"``.

The rebuild strategy
--------------------
Rather than performing destructive half-edge surgery (which would require
deep knowledge of every chamfer/fillet topology variant), each verb
*re-derives* the new body geometry from the modified planar face arrangement:

1. Find the target face via its ``persistent_id`` in the body's faces.
2. Move / rotate / offset that face's plane equation to the new position.
3. Re-intersect the full face arrangement to produce new vertex positions
   (exactly the same algorithm as the constructor in :mod:`brep_build`).
4. Re-stitch into a validated ``Body`` using the same topology as the input.

For simple axis-aligned boxes this is exact and fast. For bodies with
chamfered/filleted topology the re-intersection may fail; in that case an
``UnsupportedBodyError`` is raised with a ``reason`` describing why.
"""

from __future__ import annotations

import copy
import math
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from kerf_cad_core.geom.brep import (
    Body,
    Coedge,
    Edge,
    Face,
    Line3,
    Loop,
    Plane,
    Shell,
    Solid,
    Vertex,
    validate_body,
)
from kerf_cad_core.geom.brep_build import box_to_body
from kerf_cad_core.geom.history.feature import Feature, FeatureRef, MissingReferenceError, PersistentSelector
from kerf_cad_core.geom.history.persistent_naming import (
    NamingTable,
    face_role_for_box_planar,
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class DirectEditError(ValueError):
    """Raised when a direct-edit verb cannot be applied.

    Attributes
    ----------
    reason : str
        Machine-readable short tag (``"face-not-found"``,
        ``"non-planar face"``, ``"degenerate-geometry"``,
        ``"unsupported-topology"``).
    """

    def __init__(self, message: str, reason: str = "direct-edit-error") -> None:
        super().__init__(message)
        self.reason = reason


class UnsupportedBodyError(DirectEditError):
    """Raised when the body topology cannot be processed by this module."""

    def __init__(self, message: str) -> None:
        super().__init__(message, reason="unsupported-topology")


# ---------------------------------------------------------------------------
# Persistent face ID helpers
# ---------------------------------------------------------------------------


def _face_persistent_id(face: Face) -> str:
    """Return a stable geometric identifier for a face.

    We use a content-hash of the face's surface equation (normal + d value
    for planar faces, centroid otherwise) rounded to 6 decimal places.
    This is consistent across re-evaluations because planar geometry is
    determined purely by analytic parameters, not object identity.
    """
    if isinstance(face.surface, Plane):
        n = np.asarray(face.surface.normal(0.5, 0.5), dtype=float)
        n_r = tuple(round(float(x), 6) for x in n)
        o = np.asarray(face.surface.origin, dtype=float)
        d = round(float(np.dot(n, o)), 6)
        raw = f"plane|{n_r}|{d}"
    else:
        outer = face.outer_loop()
        if outer and outer.coedges:
            pts = [np.asarray(ce.start_point(), dtype=float) for ce in outer.coedges]
            centroid = np.mean(pts, axis=0)
        else:
            centroid = np.zeros(3)
        raw = f"other|{tuple(round(float(x), 6) for x in centroid)}"
    import hashlib
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _find_face_by_persistent_id(body: Body, persistent_id: str) -> Optional[Face]:
    """Return the face in ``body`` whose persistent ID matches, or ``None``."""
    for face in body.all_faces():
        if _face_persistent_id(face) == persistent_id:
            return face
    return None


def _require_face(body: Body, persistent_id: str) -> Face:
    """Return the face or raise :class:`MissingReferenceError`."""
    face = _find_face_by_persistent_id(body, persistent_id)
    if face is None:
        sel = PersistentSelector(
            feature_id="direct_edit",
            entity_kind="face",
            role=persistent_id,
        )
        raise MissingReferenceError(sel, {"face": [], "edge": [], "vertex": []})
    return face


# ---------------------------------------------------------------------------
# Box-plane decomposition / reconstruction helpers
# ---------------------------------------------------------------------------


def _unit(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-14 else v


def _body_to_planes(body: Body) -> List[Tuple[np.ndarray, float]]:
    """Return the list of (unit_normal, d) pairs for every planar face.

    ``d`` is such that ``dot(n, x) = d`` is the plane equation (d =
    dot(n, any_point_on_plane)).  Raises ``UnsupportedBodyError`` if any
    face is non-planar.
    """
    planes: List[Tuple[np.ndarray, float]] = []
    for f in body.all_faces():
        if not isinstance(f.surface, Plane):
            raise UnsupportedBodyError(
                f"direct edit requires all-planar body; face#{f.id} has "
                f"surface type {type(f.surface).__name__}"
            )
        n = np.asarray(f.surface.normal(0.5, 0.5), dtype=float)
        n = _unit(n)
        o = np.asarray(f.surface.origin, dtype=float)
        d = float(np.dot(n, o))
        planes.append((n, d))
    return planes


def _planes_to_box_body(
    planes: List[Tuple[np.ndarray, float]], tol: float = 1e-7
) -> Body:
    """Reconstruct an axis-aligned box Body from 6 plane equations.

    The six planes must form a closed convex polyhedron (a box). We
    intersect all triples of planes to find 8 corner vertices, then sort
    them into the canonical box layout and call ``box_to_body``.

    Raises ``DirectEditError`` if the plane set doesn't reduce to a box.
    """
    # Find all triple-plane intersections.
    n = len(planes)
    vertices: List[np.ndarray] = []
    for i in range(n):
        for j in range(i + 1, n):
            for k in range(j + 1, n):
                n1, d1 = planes[i]
                n2, d2 = planes[j]
                n3, d3 = planes[k]
                M = np.stack([n1, n2, n3], axis=0)
                rhs = np.array([d1, d2, d3])
                try:
                    pt = np.linalg.solve(M, rhs)
                except np.linalg.LinAlgError:
                    continue
                # Only keep points on the *inside* (or on) all planes.
                inside = True
                for ni, di in planes:
                    if float(np.dot(ni, pt)) > di + tol * 10:
                        inside = False
                        break
                if inside:
                    # De-duplicate
                    is_dup = False
                    for v in vertices:
                        if float(np.linalg.norm(pt - v)) < tol * 10:
                            is_dup = True
                            break
                    if not is_dup:
                        vertices.append(pt)

    if len(vertices) != 8:
        raise DirectEditError(
            f"expected 8 box vertices after plane reconstruction, "
            f"got {len(vertices)}",
            reason="degenerate-geometry",
        )

    # Sort vertices to find min corner and extents.
    pts = np.array(vertices, dtype=float)
    min_pt = pts.min(axis=0)
    max_pt = pts.max(axis=0)
    dx = float(max_pt[0] - min_pt[0])
    dy = float(max_pt[1] - min_pt[1])
    dz = float(max_pt[2] - min_pt[2])

    if dx < tol or dy < tol or dz < tol:
        raise DirectEditError(
            f"degenerate box dimensions: dx={dx}, dy={dy}, dz={dz}",
            reason="degenerate-geometry",
        )

    return box_to_body(
        corner=(float(min_pt[0]), float(min_pt[1]), float(min_pt[2])),
        dx=dx, dy=dy, dz=dz, tol=tol,
    )


def _body_volume(body: Body) -> float:
    """Estimate body volume using the signed-divergence theorem."""
    vol = 0.0
    for face in body.all_faces():
        outer = face.outer_loop()
        if outer is None or len(outer.coedges) < 3:
            continue
        pts = [np.asarray(ce.start_point(), dtype=float) for ce in outer.coedges]
        p0 = pts[0]
        for i in range(1, len(pts) - 1):
            a = pts[i] - p0
            b = pts[i + 1] - p0
            cross = np.cross(a, b)
            vol += float(np.dot(p0, cross))
    return abs(vol) / 6.0


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


def _face_normal(face: Face) -> np.ndarray:
    try:
        return _unit(np.asarray(face.surface_normal(0.5, 0.5), dtype=float))
    except Exception:
        return np.zeros(3)


# ---------------------------------------------------------------------------
# Direct-edit verbs
# ---------------------------------------------------------------------------


def direct_translate_face(
    body: Body,
    face_persistent_id: str,
    delta_xyz: Sequence[float],
) -> Body:
    """Translate a single planar face by ``delta_xyz``.

    The face is moved to ``origin + delta``; all adjacent faces are
    extended / shrunk to close the gap. Returns a new validated ``Body``.

    Raises
    ------
    MissingReferenceError
        If ``face_persistent_id`` is not found in ``body``.
    UnsupportedBodyError
        If any face in ``body`` is non-planar.
    DirectEditError
        If the result is degenerate.
    """
    _require_face(body, face_persistent_id)
    planes = _body_to_planes(body)
    delta = np.asarray(delta_xyz, dtype=float)
    faces = body.all_faces()

    new_planes: List[Tuple[np.ndarray, float]] = []
    for idx, face in enumerate(faces):
        n_vec, d_val = planes[idx]
        if _face_persistent_id(face) == face_persistent_id:
            # Shift the plane by projecting delta onto the normal.
            d_new = d_val + float(np.dot(n_vec, delta))
            new_planes.append((n_vec, d_new))
        else:
            new_planes.append((n_vec, d_val))

    return _planes_to_box_body(new_planes)


def direct_rotate_face(
    body: Body,
    face_persistent_id: str,
    axis: Sequence[float],
    angle: float,
) -> Body:
    """Rotate a single planar face around ``axis`` by ``angle`` (radians).

    The face's plane normal is rotated; the origin is rotated about the
    centroid of the face so that the face pivots in place. Adjacent faces
    are re-intersected to produce the new geometry.

    Raises
    ------
    MissingReferenceError
        If ``face_persistent_id`` is not found in ``body``.
    UnsupportedBodyError
        If any face in ``body`` is non-planar.
    """
    target = _require_face(body, face_persistent_id)
    planes = _body_to_planes(body)
    ax = _unit(np.asarray(axis, dtype=float))
    c = math.cos(angle)
    s = math.sin(angle)

    # Rodrigues rotation: R*v = c*v + s*(ax×v) + (1-c)*(ax·v)*ax
    def _rot(v: np.ndarray) -> np.ndarray:
        return (
            c * v
            + s * np.cross(ax, v)
            + (1.0 - c) * float(np.dot(ax, v)) * ax
        )

    # Face centroid as pivot
    outer = target.outer_loop()
    if outer and outer.coedges:
        pts = [np.asarray(ce.start_point(), dtype=float) for ce in outer.coedges]
        centroid = np.mean(pts, axis=0)
    else:
        centroid = np.asarray(target.surface.origin, dtype=float)

    faces = body.all_faces()
    new_planes: List[Tuple[np.ndarray, float]] = []
    for idx, face in enumerate(faces):
        n_vec, d_val = planes[idx]
        if _face_persistent_id(face) == face_persistent_id:
            n_new = _unit(_rot(n_vec))
            # Keep one point on the plane (centroid) fixed under rotation
            rotated_centroid = centroid + _rot(centroid - centroid)
            d_new = float(np.dot(n_new, centroid))
            new_planes.append((n_new, d_new))
        else:
            new_planes.append((n_vec, d_val))

    return _planes_to_box_body(new_planes)


def direct_offset_face(
    body: Body,
    face_persistent_id: str,
    distance: float,
) -> Body:
    """Offset a face along its outward normal by ``distance``.

    Positive ``distance`` moves the face outward (increases volume);
    negative moves it inward.

    Raises
    ------
    MissingReferenceError
        If ``face_persistent_id`` is not found in ``body``.
    UnsupportedBodyError
        If any face in ``body`` is non-planar.
    """
    _require_face(body, face_persistent_id)
    planes = _body_to_planes(body)
    faces = body.all_faces()

    new_planes: List[Tuple[np.ndarray, float]] = []
    for idx, face in enumerate(faces):
        n_vec, d_val = planes[idx]
        if _face_persistent_id(face) == face_persistent_id:
            d_new = d_val + float(distance)
            new_planes.append((n_vec, d_new))
        else:
            new_planes.append((n_vec, d_val))

    return _planes_to_box_body(new_planes)


def direct_push_pull(
    body: Body,
    face_persistent_id: str,
    distance: float,
) -> Body:
    """Push/pull a face along its outward normal by ``distance``.

    Equivalent to :func:`direct_offset_face` for planar faces (and to an
    extrude on planar faces). Positive ``distance`` extrudes outward.

    Raises
    ------
    MissingReferenceError
        If ``face_persistent_id`` is not found in ``body``.
    UnsupportedBodyError
        If any face in ``body`` is non-planar.
    """
    return direct_offset_face(body, face_persistent_id, distance)


def direct_delete_feature(
    body: Body,
    feature_persistent_id: str,
) -> Body:
    """Delete a small decorative feature (chamfer / fillet / hole) from a body.

    The ``feature_persistent_id`` identifies a non-axis-aligned face (the
    bevel or fillet face). Deletion re-derives the underlying planar body
    by discarding those non-axis-aligned faces and extending adjacent faces
    to fill the gap.

    For a chamfered box the chamfer bevel face has a normal at 45° to the
    axes; removing it and re-intersecting the original 6 planes restores
    the box.

    Raises
    ------
    MissingReferenceError
        If ``feature_persistent_id`` is not found in ``body``.
    UnsupportedBodyError
        If the remaining planes do not form a valid closed box.
    """
    _require_face(body, feature_persistent_id)

    # Collect only axis-aligned planes (the underlying box faces).
    axis_planes: List[Tuple[np.ndarray, float]] = []
    for face in body.all_faces():
        if _face_persistent_id(face) == feature_persistent_id:
            continue
        if not isinstance(face.surface, Plane):
            raise UnsupportedBodyError(
                f"direct_delete_feature: face#{face.id} is non-planar"
            )
        n_vec = _unit(np.asarray(face.surface.normal(0.5, 0.5), dtype=float))
        o = np.asarray(face.surface.origin, dtype=float)
        d_val = float(np.dot(n_vec, o))

        # Deduplicate near-parallel planes (keeps only one representative
        # per distinct plane equation so we have exactly 6 planes for a box).
        is_dup = False
        for existing_n, existing_d in axis_planes:
            if (
                float(np.linalg.norm(n_vec - existing_n)) < 1e-4
                and abs(d_val - existing_d) < 1e-4
            ):
                is_dup = True
                break
            # Opposite-normal parallel planes are the two sides of the same
            # axis — keep both.
        if not is_dup:
            axis_planes.append((n_vec, d_val))

    # We need exactly 6 planes to reconstruct a box.
    if len(axis_planes) < 6:
        raise DirectEditError(
            f"direct_delete_feature: expected at least 6 axis-aligned planes "
            f"after removing feature face; got {len(axis_planes)}",
            reason="degenerate-geometry",
        )

    # Use only the first 6 axis-aligned planes.
    return _planes_to_box_body(axis_planes[:6])


# ---------------------------------------------------------------------------
# DAG commit
# ---------------------------------------------------------------------------


@dataclass
class DirectEditRecord:
    """Record of a single direct-edit operation, used for DAG serialisation."""

    verb: str
    face_persistent_id: str
    params: Dict[str, Any] = field(default_factory=dict)


def commit_direct_edits_to_dag(
    dag: Any,
    body_before: Body,
    body_after: Body,
    source_feature_id: Optional[str] = None,
) -> List[Feature]:
    """Translate a before/after body pair into DAG ``DirectEditFeature`` nodes.

    A single ``"direct_edit"``-kind :class:`~kerf_cad_core.geom.history.feature.Feature`
    node is appended to ``dag``. Its params capture a geometric diff (the
    set of plane-equation changes) so future parametric upstream edits can
    replay through it.

    The evaluator for ``"direct_edit"`` is also registered on ``dag``
    (idempotent; safe to call multiple times).

    Parameters
    ----------
    dag
        A :class:`~kerf_cad_core.geom.history.dag.FeatureDAG` instance.
    body_before
        The body snapshot before the direct edit(s).
    body_after
        The body snapshot after the direct edit(s).
    source_feature_id
        Optional id of the upstream feature that produced ``body_before``.
        When supplied, the new node is wired as a downstream consumer.

    Returns
    -------
    list[Feature]
        The list of new Feature nodes appended to ``dag`` (currently
        always exactly one).
    """
    # Compute plane diff between before and after.
    try:
        planes_before = _body_to_planes(body_before)
        planes_after = _body_to_planes(body_after)
    except UnsupportedBodyError as exc:
        raise DirectEditError(
            f"commit_direct_edits_to_dag: {exc}",
            reason="unsupported-topology",
        ) from exc

    diff: List[Dict[str, Any]] = []
    for idx, ((nb, db), (na, da)) in enumerate(
        zip(planes_before, planes_after)
    ):
        n_delta = float(np.linalg.norm(na - nb))
        d_delta = abs(da - db)
        if n_delta > 1e-9 or d_delta > 1e-9:
            diff.append(
                {
                    "plane_index": idx,
                    "normal_before": [round(float(x), 9) for x in nb],
                    "d_before": round(float(db), 9),
                    "normal_after": [round(float(x), 9) for x in na],
                    "d_after": round(float(da), 9),
                }
            )

    # Build a feature params snapshot: planes_after is sufficient for
    # re-evaluation (it encodes the full body geometry).
    planes_after_serialised = [
        {
            "normal": [round(float(x), 9) for x in n],
            "d": round(float(d), 9),
        }
        for n, d in planes_after
    ]

    params: Dict[str, Any] = {
        "planes_after": planes_after_serialised,
        "plane_diff": diff,
    }

    inputs: Dict[str, Any] = {}
    if source_feature_id is not None:
        inputs["body"] = FeatureRef(feature_id=source_feature_id, output_name="body")

    feat = Feature(kind="direct_edit", params=params, inputs=inputs)
    dag.add_feature(feat)

    # Register the evaluator (idempotent).
    _register_direct_edit_evaluator(dag)

    return [feat]


def _register_direct_edit_evaluator(dag: Any) -> None:
    """Register the ``"direct_edit"`` evaluator on ``dag`` if not present."""
    if "direct_edit" in dag.evaluators():
        return

    def _eval_direct_edit(feature: Feature, ctx: Any) -> Any:
        from kerf_cad_core.geom.history.dag import EvaluationResult
        from kerf_cad_core.geom.history.persistent_naming import NamingTable

        planes_after = feature.params["planes_after"]
        planes = [
            (np.asarray(p["normal"], dtype=float), float(p["d"]))
            for p in planes_after
        ]
        body = _planes_to_box_body(planes)
        table = NamingTable(feature_id=feature.id)
        for f in body.all_faces():
            role = face_role_for_box_planar(f)
            if role is not None and role not in table.faces:
                table.register_face(role, f)
        return EvaluationResult(body=body, naming_table=table)

    dag.register_evaluator("direct_edit", _eval_direct_edit)


# ---------------------------------------------------------------------------
# Public exports
# ---------------------------------------------------------------------------

__all__ = [
    "DirectEditError",
    "UnsupportedBodyError",
    "DirectEditRecord",
    "direct_translate_face",
    "direct_rotate_face",
    "direct_offset_face",
    "direct_push_pull",
    "direct_delete_feature",
    "commit_direct_edits_to_dag",
]
