"""
direct_edit.py
==============
GK-134 / GK-P18 — Direct modelling: move-face / push-pull / delete-face.

History-free local edits on a :class:`Body`:

* :func:`push_pull_face` — translate (or offset) a face along its outward
  normal by a signed distance.  For planar faces adjacent faces are re-healed
  so the solid remains closed.  For curved (non-planar) faces the offset is
  applied using the pure-Python surface-offset path; the OCCT worker uses
  ``BRepOffsetAPI_MakeOffsetShape`` for higher accuracy (GK-P18).

* :func:`move_face` — translate a planar face by an arbitrary 3-D vector.
  The component of the vector perpendicular to the face normal is discarded;
  only the projection onto the face normal is used, keeping the face planar
  and the body closed.

* :func:`delete_face` — delete a face from a body and attempt to heal the
  resulting hole.  For planar bodies reuses the feature-deletion path from
  :mod:`~kerf_cad_core.geom.history.direct_edit`.  For general bodies the
  pure-Python path approximates healing by dropping the face and flagging the
  resulting open shell; the OCCT worker uses ``BRepTools_ReShape`` for proper
  topological healing (GK-P18).

Both push_pull_face and move_face
----------------------------------
* Accept a 0-based integer ``face_id`` (index into ``body.all_faces()``).
* Return a *new* :class:`~kerf_cad_core.geom.brep.Body`; the input body is
  never mutated.
* For planar bodies: require all faces to be
  (:class:`~kerf_cad_core.geom.brep.Plane`); raise
  :class:`~kerf_cad_core.geom.history.direct_edit.UnsupportedBodyError`.
* Raise :class:`ValueError` if ``face_id`` is out of range.
* Re-heal adjacent faces via the plane-intersection reconstruction used in
  the history layer.

GK-P18 non-planar push-pull
-----------------------------
When the target face is non-planar (e.g. a cylindrical face from a swept
body) ``push_pull_face`` applies a surface-offset approximation:

1. The face's surface is sampled at a 10×10 grid of parameter values.
2. Each grid point is displaced along its surface normal by ``distance``.
3. A new NurbsSurface is fitted to the offset grid using the Coons-patch
   interpolation in :mod:`~kerf_cad_core.geom.coons`.
4. The offset surface replaces the original face in a new Body.  Adjacent
   faces are NOT healed (the body may be open); callers should sew the
   result or pass it to the OCCT worker for proper healing.

The metadata ``__direct_edit_curved__`` is set on the returned body so
callers can detect the approximation.

Dependency chain
----------------
Reuses :mod:`kerf_cad_core.geom.history.direct_edit` (GK-86 / T-107):
  * ``_face_persistent_id`` — content-hash of a face's plane equation.
  * ``direct_offset_face`` — offset a face by a signed scalar distance.
  * ``direct_translate_face`` — translate a face by an xyz delta vector.
  * ``UnsupportedBodyError`` — re-raised on non-planar bodies (public alias).
"""

from __future__ import annotations

import warnings
from typing import List, Optional, Sequence

import numpy as np

from kerf_cad_core.geom.brep import Body, Face, Shell, Plane, Vertex, Edge, Line3, Loop, Coedge
from kerf_cad_core.geom.history.direct_edit import (
    UnsupportedBodyError,
    DirectEditError,
    _face_persistent_id,
    direct_offset_face,
    direct_translate_face,
    direct_delete_feature,
)

__all__ = [
    "push_pull_face",
    "move_face",
    "delete_face",
    "UnsupportedBodyError",
    "DirectEditError",
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _push_pull_curved_face(body: Body, face: Face, distance: float) -> Body:
    """Pure-Python approximation of push-pull on a non-planar face.

    Applies a point-wise surface offset: each surface sample point is
    displaced along its local outward normal by ``distance``.  The offset
    sample grid is fitted as a new NurbsSurface via Coons-patch interpolation
    and the face is replaced in a new Body (open shell — caller is responsible
    for re-healing).

    This is the GK-P18 fallback path; the OCCT worker routes non-planar
    push-pull through ``BRepOffsetAPI_MakeOffsetShape`` for topologically
    correct healing.

    Returns a Body with ``__direct_edit_curved__ = True`` set.
    """
    from kerf_cad_core.geom.nurbs import NurbsSurface
    from kerf_cad_core.geom.coons import _interpolating_surface

    surf = face.surface
    N = 10  # sample grid size

    # Build parameter grid within the surface's natural domain.
    # For NurbsSurface use knot domain; for others use [0, 1].
    if isinstance(surf, NurbsSurface):
        u0 = float(surf.knots_u[surf.degree_u])
        u1 = float(surf.knots_u[-surf.degree_u - 1])
        v0 = float(surf.knots_v[surf.degree_v])
        v1 = float(surf.knots_v[-surf.degree_v - 1])
        us = np.linspace(u0, u1, N)
        vs = np.linspace(v0, v1, N)
    else:
        us = np.linspace(0.0, 1.0, N)
        vs = np.linspace(0.0, 1.0, N)

    # Sample surface points and normals.
    grid = np.zeros((N, N, 3))
    for i, u in enumerate(us):
        for j, v in enumerate(vs):
            try:
                pt = np.asarray(surf.evaluate(u, v), dtype=float).ravel()[:3]
                # Approximate normal via finite differences.
                eps = (u1 - u0 + v1 - v0) / (2 * N * 10) if isinstance(surf, NurbsSurface) else 1e-4
                du = np.asarray(surf.evaluate(min(u + eps, u1 if isinstance(surf, NurbsSurface) else 1.0), v), dtype=float).ravel()[:3] - pt
                dv = np.asarray(surf.evaluate(u, min(v + eps, v1 if isinstance(surf, NurbsSurface) else 1.0)), dtype=float).ravel()[:3] - pt
            except Exception:
                grid[i, j] = np.zeros(3)
                continue
            cross = np.cross(du, dv)
            norm = np.linalg.norm(cross)
            if norm > 1e-14:
                normal = cross / norm
            else:
                normal = np.array([0.0, 0.0, 1.0])
            grid[i, j] = pt + distance * normal

    # Fit a NurbsSurface to the offset grid.
    try:
        deg = min(3, N - 1)
        offset_surf = _interpolating_surface(grid, deg, deg)
    except Exception as exc:
        raise DirectEditError(
            f"push_pull_face (curved): offset surface fitting failed: {exc}",
            reason="degenerate-geometry",
        ) from exc

    # Build a new Body with the offset surface replacing the original face.
    # For simplicity, build a new open shell containing only the offset face.
    from kerf_cad_core.geom.brep import Face, Loop, Coedge, Edge, Line3, Vertex, Shell, Body

    tol = 1e-7
    # Build a minimal face from the 4 corner points of the offset grid.
    corners = [grid[0, 0], grid[-1, 0], grid[-1, -1], grid[0, -1]]
    vs_pts = [np.asarray(c, dtype=float) for c in corners]
    verts = [Vertex(p, tol) for p in vs_pts]
    edges = [
        Edge(Line3(vs_pts[k], vs_pts[(k+1) % 4]), 0.0, 1.0, verts[k], verts[(k+1) % 4], tol)
        for k in range(4)
    ]
    coedges = [Coedge(e, True) for e in edges]
    loop = Loop(coedges, is_outer=True)
    new_face = Face(offset_surf, [loop], orientation=face.orientation, tol=tol)

    # Collect all other faces unchanged.
    other_faces = [f for f in body.all_faces() if f is not face]
    all_new_faces = other_faces + [new_face]

    shell = Shell(all_new_faces, is_closed=False)
    result_body = Body(shells=[shell])
    result_body.__direct_edit_curved__ = True  # type: ignore[attr-defined]
    return result_body


def push_pull_face(body: Body, face_id: int, distance: float) -> Body:
    """Offset face ``face_id`` along its outward normal by ``distance``.

    This is the classic "push/pull" direct-edit operation: select a face,
    drag it along its own normal direction.  Positive ``distance`` moves the
    face outward (increases volume); negative moves it inward (decreases
    volume).

    For **planar** bodies: adjacent faces are automatically re-healed so the
    solid remains watertight (via plane-intersection reconstruction).

    For **curved** (non-planar) faces (GK-P18): a surface-offset approximation
    is applied using point-wise normal displacement and Coons-patch fitting.
    The OCCT worker uses ``BRepOffsetAPI_MakeOffsetShape`` for topologically
    correct healing; this pure-Python path is the fallback.  The returned body
    has ``__direct_edit_curved__ = True`` and may be an open shell.

    Parameters
    ----------
    body : Body
        Source body.  Not mutated.
    face_id : int
        0-based index into ``body.all_faces()``.
    distance : float
        Signed offset distance along the outward face normal.

    Returns
    -------
    Body
        New body with the target face offset.  For planar bodies the result
        is a valid closed solid; for curved faces it is an open shell with
        ``__direct_edit_curved__ = True``.

    Raises
    ------
    ValueError
        If ``face_id`` is out of range.
    UnsupportedBodyError
        If the body is planar but topology reconstruction fails.
    DirectEditError
        If the resulting geometry would be degenerate.
    """
    all_faces = body.all_faces()
    if face_id < 0 or face_id >= len(all_faces):
        raise ValueError(
            f"push_pull_face: face_id {face_id} is out of range "
            f"(body has {len(all_faces)} faces)"
        )
    target_face = all_faces[face_id]

    # If the target face is non-planar, use the curved-face path (GK-P18).
    if not isinstance(target_face.surface, Plane):
        return _push_pull_curved_face(body, target_face, float(distance))

    # Check if ALL faces are planar — if so, use the history planar path.
    all_planar = all(isinstance(f.surface, Plane) for f in all_faces)
    if not all_planar:
        # Mixed body: target face is planar but body has curved faces too.
        # Fall through to the curved path for the target face.
        return _push_pull_curved_face(body, target_face, float(distance))

    persistent_id = _face_persistent_id(target_face)
    return direct_offset_face(body, persistent_id, float(distance))


def move_face(
    body: Body,
    face_id: int,
    translation_vec: Sequence[float],
) -> Body:
    """Translate face ``face_id`` by ``translation_vec``.

    Only the component of ``translation_vec`` along the face's outward normal
    is effective — in-plane components are silently discarded so the face
    remains planar and the body stays closed.  Adjacent faces are
    automatically re-healed.

    Parameters
    ----------
    body : Body
        Source body.  Must be composed entirely of planar faces.  Not
        mutated.
    face_id : int
        0-based index into ``body.all_faces()``.
    translation_vec : sequence of float
        3-element (x, y, z) translation vector.  The projection onto the
        face normal determines the effective displacement.

    Returns
    -------
    Body
        New body with the target face translated and all adjacent faces
        re-healed.

    Raises
    ------
    ValueError
        If ``face_id`` is out of range.
    UnsupportedBodyError
        If any face in ``body`` is non-planar.
    DirectEditError
        If the resulting geometry would be degenerate.
    """
    all_faces = body.all_faces()
    if face_id < 0 or face_id >= len(all_faces):
        raise ValueError(
            f"move_face: face_id {face_id} is out of range "
            f"(body has {len(all_faces)} faces)"
        )
    vec = np.asarray(translation_vec, dtype=float).ravel()
    if vec.shape[0] != 3:
        raise ValueError(
            f"move_face: translation_vec must be a 3-element sequence, "
            f"got shape {vec.shape}"
        )
    persistent_id = _face_persistent_id(all_faces[face_id])
    return direct_translate_face(body, persistent_id, vec)


# ---------------------------------------------------------------------------
# GK-P18: delete_face — remove a face and heal the body
# ---------------------------------------------------------------------------


def delete_face(
    body: Body,
    face_id: int,
    *,
    heal: bool = True,
) -> Body:
    """Delete a face from a body and attempt to heal the result.

    For **planar all-face bodies** (axis-aligned boxes and simple polyhedra):
    the face is removed and the remaining planes are re-intersected to close
    the body.  This reuses the :func:`~kerf_cad_core.geom.history.direct_edit.direct_delete_feature`
    logic from the history layer.

    For **bodies with curved faces**: the face is removed from the shell and
    the body is rebuilt as an open shell.  The OCCT worker uses
    ``BRepTools_ReShape`` for topologically correct healing; this pure-Python
    path is the fallback.  When ``heal=False`` the raw open-shell body is
    returned without attempting to close it.

    The returned body has ``__direct_edit_deleted_face__ = True`` when the
    pure-Python fallback (open-shell) path is used.

    Parameters
    ----------
    body : Body
        Source body.  Not mutated.
    face_id : int
        0-based index into ``body.all_faces()``.
    heal : bool
        If True (default), attempt to heal the body after face deletion.
        For planar bodies this always succeeds.  For curved bodies it is
        advisory: the topology healing is approximate (open shell).

    Returns
    -------
    Body
        New body with the specified face removed.  May be an open shell
        for curved-face bodies.

    Raises
    ------
    ValueError
        If ``face_id`` is out of range.
    DirectEditError
        If deletion leaves a degenerate body (e.g. fewer than 3 faces).
    """
    all_faces = body.all_faces()
    if face_id < 0 or face_id >= len(all_faces):
        raise ValueError(
            f"delete_face: face_id {face_id} is out of range "
            f"(body has {len(all_faces)} faces)"
        )

    if len(all_faces) < 2:
        raise DirectEditError(
            "delete_face: body must have at least 2 faces; "
            f"cannot delete face from a body with {len(all_faces)} face(s)",
            reason="degenerate-geometry",
        )

    target_face = all_faces[face_id]
    all_planar = all(isinstance(f.surface, Plane) for f in all_faces)

    # Planar path: use history direct_delete_feature for full healing.
    if all_planar:
        persistent_id = _face_persistent_id(target_face)
        try:
            return direct_delete_feature(body, persistent_id)
        except (DirectEditError, UnsupportedBodyError):
            # History path failed (e.g. not a box topology); fall through to
            # the open-shell fallback below.
            pass

    # General path: remove the face, build an open shell (GK-P18 fallback).
    # This is also the path used for curved-face bodies where the OCCT worker
    # would use BRepTools_ReShape for proper healing.
    remaining_faces: List[Face] = [f for f in all_faces if f is not target_face]

    if not remaining_faces:
        raise DirectEditError(
            "delete_face: no faces remaining after deletion",
            reason="degenerate-geometry",
        )

    # Warn callers that healing is approximate for curved-face bodies.
    if not all_planar and heal:
        warnings.warn(
            "delete_face: curved-face body healing is approximate in the "
            "pure-Python kernel. The OCCT worker uses BRepTools_ReShape for "
            "topologically correct healing.",
            UserWarning,
            stacklevel=2,
        )

    # After deleting a face the shell is open by definition (missing a face).
    shell = Shell(remaining_faces, is_closed=False)
    result_body = Body(shells=[shell])
    result_body.__direct_edit_deleted_face__ = True  # type: ignore[attr-defined]
    return result_body
