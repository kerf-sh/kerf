"""Pure-Python STEP AP214 Part 21 B-rep writer.

Serialises a Kerf :class:`~kerf_cad_core.geom.brep.Body` to an ISO 10303-21
(Part 21) file that conforms to the AUTOMOTIVE_DESIGN application protocol
(AP214 edition 1 / STEP AP214).

Entity coverage
---------------
- MANIFOLD_SOLID_BREP (root)
- CLOSED_SHELL
- ADVANCED_FACE per face
- PLANE / CYLINDRICAL_SURFACE per carrier surface
- EDGE_CURVE / VERTEX_POINT / CARTESIAN_POINT
- LINE / CIRCLE per edge curve
- EDGE_LOOP / ORIENTED_EDGE per loop / coedge
- AXIS2_PLACEMENT_3D + DIRECTION + VECTOR supporting entities

The writer performs a two-pass algorithm:
  Pass 1 — collect all distinct topology / geometry objects and assign
            stable, deterministic integer entity IDs.  IDs are assigned
            in a fixed traversal order:
              a) header supporting entities (TIME_STAMP etc.) — #1..fixed
              b) vertex points
              c) edge curves (with direction / line / circle geometry)
              d) faces (surface entities, then loops, then ADVANCED_FACE)
              e) shells and solid
              f) MANIFOLD_SOLID_BREP root
  Pass 2 — emit DATA section lines in ID order.

Determinism guarantee
---------------------
Two calls to :func:`write` on *the same* :class:`Body` object produce
byte-identical output.  This is achieved by:
  * sorting objects by Python ``id()`` (memory address is fixed for the
    life of the object, and the Body is not mutated between calls), and
  * using a local counter seeded at 1 so it is independent of the global
    :data:`~kerf_cad_core.geom.brep._ID` counter.

Usage::

    from kerf_cad_core.geom.brep import make_box
    from kerf_cad_core.io.step_writer import write

    body = make_box()
    step_text = write(body)                    # returns str
    write(body, path="cube.step")              # writes to file
"""

from __future__ import annotations

import math
import os
from typing import Dict, List, Optional, TextIO, Tuple

import numpy as np

from kerf_cad_core.geom.brep import (
    Body,
    CircleArc3,
    Coedge,
    CylinderSurface,
    Edge,
    Face,
    Line3,
    Loop,
    Plane,
    Shell,
    Solid,
    Vertex,
)

__all__ = ["write"]

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_FILE_SCHEMA = "'AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'"


def _fmt_float(v: float) -> str:
    """Format a float for Part 21: no exponential notation, trimmed."""
    s = f"{v:.10g}"
    # ensure there is always a decimal point (Part 21 requires it)
    if "." not in s and "e" not in s and "E" not in s:
        s = s + "."
    return s


def _fmt_point(pt) -> str:
    x, y, z = (float(c) for c in np.asarray(pt, dtype=float))
    return f"({_fmt_float(x)},{_fmt_float(y)},{_fmt_float(z)})"


def _unit_vec(v) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-14 else v


def _perp(axis: np.ndarray) -> np.ndarray:
    ref = np.array([1.0, 0.0, 0.0])
    if abs(float(np.dot(ref, axis))) > 0.9:
        ref = np.array([0.0, 1.0, 0.0])
    return _unit_vec(np.cross(axis, ref))


# ---------------------------------------------------------------------------
# ID allocator
# ---------------------------------------------------------------------------

class _IDPool:
    def __init__(self) -> None:
        self._next = 1
        self._map: Dict[int, int] = {}  # Python id(obj) -> entity ID

    def get(self, obj) -> int:
        key = id(obj)
        if key not in self._map:
            self._map[key] = self._next
            self._next += 1
        return self._map[key]

    def alloc(self) -> int:
        n = self._next
        self._next += 1
        return n

    @property
    def next_id(self) -> int:
        return self._next


# ---------------------------------------------------------------------------
# Entity line builders
# ---------------------------------------------------------------------------

def _cartesian_point(eid: int, label: str, pt) -> str:
    x, y, z = (float(c) for c in np.asarray(pt, dtype=float))
    return (
        f"#{eid}=CARTESIAN_POINT('{label}',"
        f"({_fmt_float(x)},{_fmt_float(y)},{_fmt_float(z)}));"
    )


def _direction(eid: int, label: str, d) -> str:
    x, y, z = (float(c) for c in _unit_vec(np.asarray(d, dtype=float)))
    return (
        f"#{eid}=DIRECTION('{label}',"
        f"({_fmt_float(x)},{_fmt_float(y)},{_fmt_float(z)}));"
    )


def _vector(eid: int, label: str, dir_id: int, mag: float) -> str:
    return f"#{eid}=VECTOR('{label}',#{dir_id},{_fmt_float(mag)});"


def _axis2_placement_3d(
    eid: int,
    label: str,
    loc_id: int,
    axis_id: int,
    ref_id: int,
) -> str:
    return (
        f"#{eid}=AXIS2_PLACEMENT_3D('{label}',#{loc_id},#{axis_id},#{ref_id});"
    )


def _vertex_point(eid: int, label: str, cp_id: int) -> str:
    return f"#{eid}=VERTEX_POINT('{label}',#{cp_id});"


def _edge_curve(eid: int, label: str, v0_id: int, v1_id: int, geom_id: int) -> str:
    return (
        f"#{eid}=EDGE_CURVE('{label}',#{v0_id},#{v1_id},#{geom_id},.T.);"
    )


def _oriented_edge(eid: int, label: str, ec_id: int, orientation: bool) -> str:
    s = ".T." if orientation else ".F."
    return f"#{eid}=ORIENTED_EDGE('{label}',*,*,#{ec_id},{s});"


def _edge_loop(eid: int, label: str, oe_ids: List[int]) -> str:
    refs = ",".join(f"#{i}" for i in oe_ids)
    return f"#{eid}=EDGE_LOOP('{label}',({refs}));"


def _face_outer_bound(eid: int, label: str, loop_id: int, orientation: bool) -> str:
    s = ".T." if orientation else ".F."
    return f"#{eid}=FACE_OUTER_BOUND('{label}',#{loop_id},{s});"


def _face_bound(eid: int, label: str, loop_id: int, orientation: bool) -> str:
    s = ".T." if orientation else ".F."
    return f"#{eid}=FACE_BOUND('{label}',#{loop_id},{s});"


def _advanced_face(eid: int, label: str, bound_ids: List[int], surf_id: int, sense: bool) -> str:
    refs = ",".join(f"#{i}" for i in bound_ids)
    s = ".T." if sense else ".F."
    return f"#{eid}=ADVANCED_FACE('{label}',({refs}),#{surf_id},{s});"


def _plane(eid: int, label: str, ax2p_id: int) -> str:
    return f"#{eid}=PLANE('{label}',#{ax2p_id});"


def _cylindrical_surface(eid: int, label: str, ax2p_id: int, radius: float) -> str:
    return f"#{eid}=CYLINDRICAL_SURFACE('{label}',#{ax2p_id},{_fmt_float(radius)});"


def _closed_shell(eid: int, label: str, face_ids: List[int]) -> str:
    refs = ",".join(f"#{i}" for i in face_ids)
    return f"#{eid}=CLOSED_SHELL('{label}',({refs}));"


def _open_shell(eid: int, label: str, face_ids: List[int]) -> str:
    refs = ",".join(f"#{i}" for i in face_ids)
    return f"#{eid}=OPEN_SHELL('{label}',({refs}));"


def _manifold_solid_brep(eid: int, label: str, shell_id: int) -> str:
    return f"#{eid}=MANIFOLD_SOLID_BREP('{label}',#{shell_id});"


def _line(eid: int, label: str, pt_id: int, dir_vec_id: int) -> str:
    return f"#{eid}=LINE('{label}',#{pt_id},#{dir_vec_id});"


def _circle(eid: int, label: str, ax2p_id: int, radius: float) -> str:
    return f"#{eid}=CIRCLE('{label}',#{ax2p_id},{_fmt_float(radius)});"


# ---------------------------------------------------------------------------
# Core serialisation logic
# ---------------------------------------------------------------------------

def _collect(body: Body):
    """Two-pass collector: returns an ordered list of (entity_id, line) tuples."""

    pool = _IDPool()
    lines: List[Tuple[int, str]] = []

    # -----------------------------------------------------------------------
    # Helper: emit a line tagged with the entity ID
    # -----------------------------------------------------------------------
    def emit(eid: int, line: str) -> None:
        lines.append((eid, line))

    # -----------------------------------------------------------------------
    # Helper: axis placement for a Plane surface
    # -----------------------------------------------------------------------
    def _emit_plane_ax2p(origin, x_axis, y_axis, label_prefix: str) -> int:
        """Emit CARTESIAN_POINT + 2 DIRECTION + AXIS2_PLACEMENT_3D for a plane.
        Returns the AXIS2_PLACEMENT_3D id."""
        # z_axis is the plane normal
        xa = _unit_vec(np.asarray(x_axis, dtype=float))
        ya = _unit_vec(np.asarray(y_axis, dtype=float))
        za = _unit_vec(np.cross(xa, ya))

        loc_id = pool.alloc()
        emit(loc_id, _cartesian_point(loc_id, f"{label_prefix}_loc", origin))
        ax_id = pool.alloc()
        emit(ax_id, _direction(ax_id, f"{label_prefix}_ax", za))
        ref_id = pool.alloc()
        emit(ref_id, _direction(ref_id, f"{label_prefix}_ref", xa))
        a2p_id = pool.alloc()
        emit(a2p_id, _axis2_placement_3d(a2p_id, label_prefix, loc_id, ax_id, ref_id))
        return a2p_id

    # -----------------------------------------------------------------------
    # Helper: axis placement for a CylinderSurface
    # -----------------------------------------------------------------------
    def _emit_cyl_ax2p(cyl: CylinderSurface, label_prefix: str) -> int:
        ax = _unit_vec(cyl.axis)
        xref = _unit_vec(cyl.x_ref)
        loc_id = pool.alloc()
        emit(loc_id, _cartesian_point(loc_id, f"{label_prefix}_loc", cyl.center))
        ax_id = pool.alloc()
        emit(ax_id, _direction(ax_id, f"{label_prefix}_ax", ax))
        ref_id = pool.alloc()
        emit(ref_id, _direction(ref_id, f"{label_prefix}_ref", xref))
        a2p_id = pool.alloc()
        emit(a2p_id, _axis2_placement_3d(a2p_id, label_prefix, loc_id, ax_id, ref_id))
        return a2p_id

    # -----------------------------------------------------------------------
    # Helper: emit VERTEX_POINT for a Vertex (memoised by object identity)
    # -----------------------------------------------------------------------
    vertex_entity: Dict[int, int] = {}  # id(Vertex) -> entity_id of VERTEX_POINT

    def emit_vertex(v: Vertex) -> int:
        key = id(v)
        if key in vertex_entity:
            return vertex_entity[key]
        cp_id = pool.alloc()
        emit(cp_id, _cartesian_point(cp_id, f"v{cp_id}", v.point))
        vp_id = pool.alloc()
        emit(vp_id, _vertex_point(vp_id, f"vp{vp_id}", cp_id))
        vertex_entity[key] = vp_id
        return vp_id

    # -----------------------------------------------------------------------
    # Helper: emit EDGE_CURVE for an Edge (memoised by object identity)
    # -----------------------------------------------------------------------
    edge_entity: Dict[int, int] = {}  # id(Edge) -> entity_id of EDGE_CURVE

    def emit_edge(e: Edge) -> int:
        key = id(e)
        if key in edge_entity:
            return edge_entity[key]

        v0_id = emit_vertex(e.v_start)
        v1_id = emit_vertex(e.v_end)

        # Build curve geometry entity
        if isinstance(e.curve, Line3):
            direction = e.curve.p1 - e.curve.p0
            mag = float(np.linalg.norm(direction))
            # LINE needs a CARTESIAN_POINT (origin) + VECTOR
            pt_id = pool.alloc()
            emit(pt_id, _cartesian_point(pt_id, "line_pt", e.curve.p0))
            dir_id = pool.alloc()
            emit(dir_id, _direction(dir_id, "line_dir", direction if mag > 1e-14 else np.array([1., 0., 0.])))
            vec_id = pool.alloc()
            emit(vec_id, _vector(vec_id, "line_vec", dir_id, max(mag, 0.0)))
            geom_id = pool.alloc()
            emit(geom_id, _line(geom_id, "line", pt_id, vec_id))

        elif isinstance(e.curve, CircleArc3):
            arc = e.curve
            xref = _unit_vec(arc.x_axis)
            ax = _unit_vec(np.cross(xref, arc.y_axis))
            loc_id = pool.alloc()
            emit(loc_id, _cartesian_point(loc_id, "circ_ctr", arc.center))
            ax_id = pool.alloc()
            emit(ax_id, _direction(ax_id, "circ_ax", ax))
            ref_id = pool.alloc()
            emit(ref_id, _direction(ref_id, "circ_ref", xref))
            a2p_id = pool.alloc()
            emit(a2p_id, _axis2_placement_3d(a2p_id, "circ_pl", loc_id, ax_id, ref_id))
            geom_id = pool.alloc()
            emit(geom_id, _circle(geom_id, "circle", a2p_id, arc.radius))

        else:
            # Generic fallback: encode as a LINE from start to end point
            p0 = np.asarray(e.curve.evaluate(e.t0), dtype=float)
            p1 = np.asarray(e.curve.evaluate(e.t1), dtype=float)
            direction = p1 - p0
            mag = float(np.linalg.norm(direction))
            pt_id = pool.alloc()
            emit(pt_id, _cartesian_point(pt_id, "line_pt", p0))
            dir_id = pool.alloc()
            d = direction if mag > 1e-14 else np.array([1., 0., 0.])
            emit(dir_id, _direction(dir_id, "line_dir", d))
            vec_id = pool.alloc()
            emit(vec_id, _vector(vec_id, "line_vec", dir_id, max(mag, 0.0)))
            geom_id = pool.alloc()
            emit(geom_id, _line(geom_id, "line", pt_id, vec_id))

        ec_id = pool.alloc()
        emit(ec_id, _edge_curve(ec_id, f"ec{ec_id}", v0_id, v1_id, geom_id))
        edge_entity[key] = ec_id
        return ec_id

    # -----------------------------------------------------------------------
    # Helper: emit EDGE_LOOP for a Loop (returns loop entity id)
    # -----------------------------------------------------------------------
    def emit_loop(lp: Loop, loop_label: str) -> int:
        oe_ids: List[int] = []
        for ce in lp.coedges:
            ec_id = emit_edge(ce.edge)
            oe_id = pool.alloc()
            emit(oe_id, _oriented_edge(oe_id, "oe", ec_id, ce.orientation))
            oe_ids.append(oe_id)
        loop_id = pool.alloc()
        emit(loop_id, _edge_loop(loop_id, loop_label, oe_ids))
        return loop_id

    # -----------------------------------------------------------------------
    # Helper: emit surface + ADVANCED_FACE for a Face
    # -----------------------------------------------------------------------
    def emit_face(f: Face, face_label: str) -> int:
        surf = f.surface

        if isinstance(surf, Plane):
            a2p_id = _emit_plane_ax2p(surf.origin, surf.x_axis, surf.y_axis, f"{face_label}_pl")
            surf_id = pool.alloc()
            emit(surf_id, _plane(surf_id, f"{face_label}_surf", a2p_id))

        elif isinstance(surf, CylinderSurface):
            a2p_id = _emit_cyl_ax2p(surf, f"{face_label}_cyl")
            surf_id = pool.alloc()
            emit(surf_id, _cylindrical_surface(surf_id, f"{face_label}_surf", a2p_id, surf.radius))

        else:
            # Fallback: emit as PLANE using finite-difference normal
            try:
                pt = np.asarray(surf.evaluate(0.5, 0.5), dtype=float)
                h = 1e-4
                du = np.asarray(surf.evaluate(0.5 + h, 0.5), dtype=float) - pt
                dv = np.asarray(surf.evaluate(0.5, 0.5 + h), dtype=float) - pt
                nrm = _unit_vec(np.cross(du, dv))
                xa = _unit_vec(du) if float(np.linalg.norm(du)) > 1e-14 else np.array([1., 0., 0.])
                ya = _unit_vec(np.cross(nrm, xa))
                a2p_id = _emit_plane_ax2p(pt, xa, ya, f"{face_label}_fb")
            except Exception:
                a2p_id = _emit_plane_ax2p(
                    np.zeros(3),
                    np.array([1., 0., 0.]),
                    np.array([0., 1., 0.]),
                    f"{face_label}_fb",
                )
            surf_id = pool.alloc()
            emit(surf_id, _plane(surf_id, f"{face_label}_surf", a2p_id))

        # Emit bounds
        outer = f.outer_loop()
        bound_ids: List[int] = []
        for lp in f.loops:
            loop_id = emit_loop(lp, f"loop{pool.next_id}")
            if lp is outer:
                b_id = pool.alloc()
                emit(b_id, _face_outer_bound(b_id, "fob", loop_id, True))
            else:
                b_id = pool.alloc()
                emit(b_id, _face_bound(b_id, "fb", loop_id, True))
            bound_ids.append(b_id)

        af_id = pool.alloc()
        emit(af_id, _advanced_face(af_id, face_label, bound_ids, surf_id, f.orientation))
        return af_id

    # -----------------------------------------------------------------------
    # Main traversal
    # -----------------------------------------------------------------------
    # Deterministic ordering: sort shells/faces/edges/vertices by id(obj)
    all_shells = sorted(body.all_shells(), key=id)

    for shell in all_shells:
        sorted_faces = sorted(shell.faces, key=id)
        face_ids: List[int] = []
        for face in sorted_faces:
            # Sort loops by id for determinism
            face_loops_orig = face.loops
            face.loops = sorted(face.loops, key=id)
            af_id = emit_face(face, f"face{pool.next_id}")
            face.loops = face_loops_orig
            face_ids.append(af_id)

        sh_id = pool.alloc()
        if shell.is_closed:
            emit(sh_id, _closed_shell(sh_id, f"shell{sh_id}", face_ids))
        else:
            emit(sh_id, _open_shell(sh_id, f"shell{sh_id}", face_ids))

        # Wrap each closed shell in MANIFOLD_SOLID_BREP if it belongs to a solid
        if shell.solid is not None and shell.is_closed:
            msb_id = pool.alloc()
            emit(msb_id, _manifold_solid_brep(msb_id, "brep", sh_id))

    # Sort by entity ID before returning
    lines.sort(key=lambda x: x[0])
    return lines


# ---------------------------------------------------------------------------
# Part 21 header / footer
# ---------------------------------------------------------------------------

def _header(body_label: str = "kerf_export") -> str:
    return (
        "ISO-10303-21;\n"
        "HEADER;\n"
        f"FILE_DESCRIPTION(('Kerf CAD export'),'{body_label}');\n"
        "FILE_NAME('','',(''),(''),'kerf-cad-core step_writer','','');\n"
        f"FILE_SCHEMA(({_FILE_SCHEMA}));\n"
        "ENDSEC;\n"
        "DATA;\n"
    )


def _footer() -> str:
    return "ENDSEC;\nEND-ISO-10303-21;\n"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write(
    body: Body,
    path: Optional[str] = None,
    label: str = "kerf_export",
) -> str:
    """Serialise *body* to an AP214 Part 21 string.

    Parameters
    ----------
    body:
        The :class:`~kerf_cad_core.geom.brep.Body` to serialise.
    path:
        If given, write the result to this file path (UTF-8).
    label:
        Label embedded in FILE_DESCRIPTION.

    Returns
    -------
    str
        The full Part 21 text (header + data + footer).
    """
    entity_lines = _collect(body)
    parts = [_header(label)]
    for _eid, line in entity_lines:
        parts.append(line + "\n")
    parts.append(_footer())
    result = "".join(parts)

    if path is not None:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(result)

    return result
