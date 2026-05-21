"""
direct_edit.py
==============
GK-134 — Direct modelling: move-face / push-pull.

History-free local edits on a planar :class:`Body`:

* :func:`push_pull_face` — translate (or offset) a planar face along its
  outward normal by a signed distance.  Adjacent faces are re-healed so the
  solid remains closed.  Equivalent to a Push/Pull operation in most
  direct-modelling CAD tools.

* :func:`move_face` — translate a planar face by an arbitrary 3-D vector.
  The component of the vector perpendicular to the face normal is discarded;
  only the projection onto the face normal is used, keeping the face planar
  and the body closed.

Both operations are *history-free*: they take a Body snapshot and return a
new Body without modifying the parametric feature DAG.  For DAG-integrated
direct edits see :mod:`kerf_cad_core.geom.history.direct_edit`.

Public API
----------
push_pull_face(body, face_id, distance) -> Body
    Offset the face at index ``face_id`` in ``body.all_faces()`` along its
    outward normal by ``distance`` (positive = outward, negative = inward).

move_face(body, face_id, translation_vec) -> Body
    Translate the face at index ``face_id`` by ``translation_vec``.  Only
    the component along the face normal is effective; in-plane components are
    silently ignored so that the face remains planar and the body stays
    closed.

Both functions
--------------
* Accept a 0-based integer ``face_id`` (index into ``body.all_faces()``).
* Return a *new* :class:`~kerf_cad_core.geom.brep.Body`; the input body is
  never mutated.
* Require all faces in ``body`` to be planar
  (:class:`~kerf_cad_core.geom.brep.Plane`).  Non-planar bodies raise
  :class:`~kerf_cad_core.geom.history.direct_edit.UnsupportedBodyError`.
* Raise :class:`ValueError` if ``face_id`` is out of range.
* Re-heal adjacent faces via the plane-intersection reconstruction used in
  the history layer.

Dependency chain
----------------
Reuses :mod:`kerf_cad_core.geom.history.direct_edit` (GK-86 / T-107):
  * ``_face_persistent_id`` — content-hash of a face's plane equation.
  * ``direct_offset_face`` — offset a face by a signed scalar distance.
  * ``direct_translate_face`` — translate a face by an xyz delta vector.
  * ``UnsupportedBodyError`` — re-raised on non-planar bodies (public alias).
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

from kerf_cad_core.geom.brep import Body
from kerf_cad_core.geom.history.direct_edit import (
    UnsupportedBodyError,
    _face_persistent_id,
    direct_offset_face,
    direct_translate_face,
)

__all__ = ["push_pull_face", "move_face", "UnsupportedBodyError"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def push_pull_face(body: Body, face_id: int, distance: float) -> Body:
    """Offset face ``face_id`` along its outward normal by ``distance``.

    This is the classic "push/pull" direct-edit operation: select a planar
    face, drag it along its own normal direction.  Positive ``distance``
    moves the face outward (increases volume); negative moves it inward
    (decreases volume).  Adjacent faces are automatically re-healed so the
    solid remains watertight.

    Parameters
    ----------
    body : Body
        Source body.  Must be composed entirely of planar faces.  Not
        mutated.
    face_id : int
        0-based index into ``body.all_faces()``.
    distance : float
        Signed offset distance along the outward face normal.

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
        If the resulting geometry would be degenerate (e.g. face moved past
        an opposing face).
    """
    all_faces = body.all_faces()
    if face_id < 0 or face_id >= len(all_faces):
        raise ValueError(
            f"push_pull_face: face_id {face_id} is out of range "
            f"(body has {len(all_faces)} faces)"
        )
    persistent_id = _face_persistent_id(all_faces[face_id])
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
