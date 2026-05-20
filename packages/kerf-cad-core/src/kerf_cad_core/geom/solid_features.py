"""
solid_features.py
=================
Solid-feature parity with Rhino/SolidTools — pure-Python specs + analytic /
parametric geometry.  OCC B-rep ops are gated behind ``_OCC_AVAILABLE`` and
are clearly documented when a required OCC symbol is absent.

All public functions return a structured result dict that is **never** raised
as an exception:
    {"ok": True,  ...computed fields...}
    {"ok": False, "reason": "<human-readable>", ...zero-value fields...}

Public API
----------
pipe_along_curve(path_points, radius, *, variable_radii=None, cap_style="round",
                 min_bend_radius=None) -> dict
    Sweep a circular profile of radius *r* along a 3-D polyline.
    • Constant-radius or variable-radius (keyed to path parameter t∈[0,1]).
    • Returns: ok, volume, length, centroid, bend_check (list of violations),
      cap_style, radius_at_t callable description, geometry_params.

shell_solid(outer_dims, wall_thickness, *, open_faces=None, density=1.0) -> dict
    Hollow a rectangular solid with given wall thickness and selectable faces
    to remove.  Returns: ok, volume_outer, volume_inner, shell_mass,
    thickness_feasible, open_faces, geometry_params.

variable_radius_fillet(edge_length, radius_start, radius_end, *,
                       min_allowed_radius=None) -> dict
    Edge fillet with radius varying linearly along the edge.
    Returns: ok, radius_at_start, radius_at_end, min_radius_violation,
    tangency_ok, geometry_params.

draft_faces(face_height, draft_angle_deg, *, neutral_plane_offset=0.0) -> dict
    Apply a draft angle to a planar face about a pull direction.
    Returns: ok, taper_offset_at_top, draft_angle_deg, neutral_plane_offset,
    geometry_params.

rib_web(profile_length, rib_thickness, rib_height, *,
        draft_angle_deg=0.0, attachment_width=None) -> dict
    Thickened rib between a profile and a solid.
    Returns: ok, volume, cross_section_area, draft_taper, geometry_params.

wirecut(solid_bbox, cut_profile_points, *, direction=(0.0, 0.0, 1.0)) -> dict
    Cut a solid with a swept 2D curve through-all.
    Returns: ok, cut_area, path_length, direction, geometry_params.

OCC-gated note
--------------
None of the six functions in this module can perform actual B-rep operations
without pythonOCC (BRepPrimAPI, BRepAlgoAPI, BRepFilletAPI, etc.).  The
pure-Python layer supplies:
  • Parametric geometry parameters (volumes, lengths, areas via analytic /
    Pappus formulas).
  • Feasibility diagnostics (min-bend-radius violations, thickness checks,
    min-fillet-radius checks).
  • Full feature specs ready for OCC worker consumption.

When ``_OCC_AVAILABLE`` is True the ``_occ_*`` helpers at the bottom of this
file may be extended by a worker; they are stubs here because the OCC symbols
required (BRepPrimAPI_MakePrism, BRepAlgoAPI_Cut, BRepFilletAPI_MakeFillet,
BRepOffsetAPI_MakeThickSolid, BRepFeat_MakeDPrism) are not confirmed present
in the CI environment.  The functions return ``ok=True`` with the analytic
geometry even when OCC is unavailable — callers that need a real B-rep should
check ``geometry_params["occ_available"]``.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from kerf_cad_core.occ_helpers import _OCC_AVAILABLE  # noqa: F401 (re-exported below)
from kerf_cad_core.geom.brep_build import BuildError, extrude_to_body as _brep_extrude_to_body
_BuildError = BuildError  # local alias for use in GK-46 body-producing functions
from kerf_cad_core.geom.brep import (
    Body as _Body,
    Coedge as _Coedge,
    Edge as _Edge,
    Face as _Face,
    Line3 as _Line3,
    Loop as _Loop,
    Plane as _Plane,
    Shell as _Shell,
    Solid as _Solid,
    Vertex as _Vertex,
    validate_body as _validate_body,
)
from kerf_cad_core.geom.sew import sew_faces as _sew_faces, sew_into_solid as _sew_into_solid

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_TWO_PI = 2.0 * math.pi


def _vec3(p) -> np.ndarray:
    """Convert any 3-element sequence to a float64 ndarray."""
    return np.asarray(p, dtype=float).reshape(3)


def _polyline_length(points: List[np.ndarray]) -> float:
    """Arc-length of a 3-D polyline."""
    if len(points) < 2:
        return 0.0
    return float(sum(
        np.linalg.norm(points[i + 1] - points[i])
        for i in range(len(points) - 1)
    ))


def _polyline_centroid(points: List[np.ndarray]) -> np.ndarray:
    """Centroid weighted by segment length (midpoint rule)."""
    if len(points) == 1:
        return points[0].copy()
    total = 0.0
    acc = np.zeros(3)
    for i in range(len(points) - 1):
        seg = np.linalg.norm(points[i + 1] - points[i])
        mid = (points[i] + points[i + 1]) * 0.5
        acc += seg * mid
        total += seg
    if total < 1e-15:
        return points[0].copy()
    return acc / total


def _arc_length_params(points: List[np.ndarray]) -> List[float]:
    """Return cumulative arc-length parameters t∈[0,1] for each point."""
    if len(points) < 2:
        return [0.0] * len(points)
    segs = [float(np.linalg.norm(points[i + 1] - points[i])) for i in range(len(points) - 1)]
    total = sum(segs)
    if total < 1e-15:
        return list(np.linspace(0.0, 1.0, len(points)))
    cumulative = [0.0]
    for s in segs:
        cumulative.append(cumulative[-1] + s / total)
    return cumulative


def _segment_bend_radii(points: List[np.ndarray]) -> List[float]:
    """Estimate minimum bend radius at each interior point via osculating circle."""
    radii = []
    for i in range(1, len(points) - 1):
        a = points[i - 1]
        b = points[i]
        c = points[i + 1]
        ab = b - a
        bc = c - b
        len_ab = float(np.linalg.norm(ab))
        len_bc = float(np.linalg.norm(bc))
        if len_ab < 1e-12 or len_bc < 1e-12:
            continue
        cos_theta = float(np.dot(ab, bc) / (len_ab * len_bc))
        cos_theta = max(-1.0, min(1.0, cos_theta))
        theta = math.acos(cos_theta)
        if theta < 1e-8:
            # Nearly straight — infinite bend radius (safe)
            continue
        # Chord = average of the two half-segments
        chord = (len_ab + len_bc) * 0.5
        # R = chord / (2 * sin(theta/2))
        r_bend = chord / (2.0 * math.sin(theta / 2.0))
        radii.append(r_bend)
    return radii


# ---------------------------------------------------------------------------
# 1. pipe_along_curve
# ---------------------------------------------------------------------------

def pipe_along_curve(
    path_points: Sequence,
    radius: float,
    *,
    variable_radii: Optional[Dict[float, float]] = None,
    cap_style: str = "round",
    min_bend_radius: Optional[float] = None,
) -> dict:
    """Sweep a circular profile along a 3-D polyline (pipe/tube).

    Parameters
    ----------
    path_points : sequence of [x, y, z]
        Spine polyline (at least 2 points).
    radius : float
        Circular profile radius (constant, unless variable_radii is provided).
    variable_radii : dict {t: r}, optional
        Radius overrides keyed to path parameter t∈[0,1].  Values between
        keys are linearly interpolated.
    cap_style : str
        "round" (hemispherical end caps) or "mitered" (flat cross-section cuts).
    min_bend_radius : float, optional
        If provided, any bend radius smaller than this value is flagged in
        bend_check.  A common rule of thumb is ``min_bend_radius = 2 * radius``.

    Returns
    -------
    dict
        ok, volume, length, centroid ([x,y,z]), bend_check (list of dicts),
        cap_style, geometry_params (detailed intermediates).
    """
    _ZERO = {
        "ok": False,
        "reason": "",
        "volume": 0.0,
        "length": 0.0,
        "centroid": [0.0, 0.0, 0.0],
        "bend_check": [],
        "cap_style": cap_style,
        "geometry_params": {},
    }

    try:
        pts = [_vec3(p) for p in path_points]
    except Exception as exc:
        return {**_ZERO, "ok": False, "reason": f"invalid path_points: {exc}"}

    if len(pts) < 2:
        return {**_ZERO, "ok": False, "reason": "path_points must have at least 2 points"}

    if not isinstance(radius, (int, float)) or radius <= 0:
        return {**_ZERO, "ok": False, "reason": f"radius must be a positive number; got {radius!r}"}

    if cap_style not in ("round", "mitered"):
        return {**_ZERO, "ok": False, "reason": f"cap_style must be 'round' or 'mitered'; got {cap_style!r}"}

    # ── Geometry ──────────────────────────────────────────────────────────
    length = _polyline_length(pts)
    if length < 1e-12:
        return {**_ZERO, "ok": False, "reason": "path_points are all coincident (zero length)"}

    t_params = _arc_length_params(pts)
    centroid = _polyline_centroid(pts)

    # Build radius-at-t function
    def _radius_at(t: float) -> float:
        if not variable_radii:
            return float(radius)
        keys = sorted(variable_radii.keys())
        if t <= keys[0]:
            return float(variable_radii[keys[0]])
        if t >= keys[-1]:
            return float(variable_radii[keys[-1]])
        for i in range(len(keys) - 1):
            if keys[i] <= t <= keys[i + 1]:
                alpha = (t - keys[i]) / (keys[i + 1] - keys[i] + 1e-15)
                return float(
                    variable_radii[keys[i]] * (1 - alpha) +
                    variable_radii[keys[i + 1]] * alpha
                )
        return float(radius)

    # ── Volume (Pappus / numerical integration along the spine) ───────────
    # For a circular cross-section swept along a path:
    #   dV = π * r(t)² * ds
    # Integrate numerically over the polyline segments.
    volume = 0.0
    seg_data = []
    for i in range(len(pts) - 1):
        ds = float(np.linalg.norm(pts[i + 1] - pts[i]))
        t_mid = (t_params[i] + t_params[i + 1]) * 0.5
        r_mid = _radius_at(t_mid)
        dv = math.pi * r_mid ** 2 * ds
        volume += dv
        seg_data.append({"t_mid": t_mid, "radius": r_mid, "ds": ds, "dV": dv})

    # Add hemispherical caps if round
    if cap_style == "round":
        r_start = _radius_at(0.0)
        r_end = _radius_at(1.0)
        volume += (2.0 / 3.0) * math.pi * r_start ** 3
        volume += (2.0 / 3.0) * math.pi * r_end ** 3

    # ── Bend check ────────────────────────────────────────────────────────
    bend_radii = _segment_bend_radii(pts)
    bend_check = []
    if min_bend_radius is not None and min_bend_radius > 0:
        for i, rb in enumerate(bend_radii):
            # t at interior point i+1
            t_pt = t_params[i + 1]
            r_pipe = _radius_at(t_pt)
            effective_min = max(float(min_bend_radius), r_pipe)
            if rb < effective_min:
                bend_check.append({
                    "point_index": i + 1,
                    "t": t_pt,
                    "bend_radius": rb,
                    "min_allowed": effective_min,
                    "violation": True,
                })

    return {
        "ok": True,
        "reason": "",
        "volume": volume,
        "length": length,
        "centroid": centroid.tolist(),
        "bend_check": bend_check,
        "cap_style": cap_style,
        "geometry_params": {
            "num_path_points": len(pts),
            "radius_constant": radius,
            "variable_radii": variable_radii,
            "segment_data": seg_data,
            "bend_radii_at_joints": bend_radii,
            "occ_available": _OCC_AVAILABLE,
            "occ_note": (
                "BRepOffsetAPI_MakePipe requires pythonOCC; use geometry_params "
                "to pass analytic spec to the OCCT worker."
            ),
        },
    }


# ---------------------------------------------------------------------------
# 2. shell_solid
# ---------------------------------------------------------------------------

_VALID_FACES = frozenset({"top", "bottom", "front", "back", "left", "right"})


def shell_solid(
    outer_dims: Sequence,
    wall_thickness: float,
    *,
    open_faces: Optional[List[str]] = None,
    density: float = 1.0,
) -> dict:
    """Hollow a rectangular solid, computing shell mass.

    Parameters
    ----------
    outer_dims : [width, depth, height]
        Outer bounding box dimensions (all positive).
    wall_thickness : float
        Uniform wall thickness (> 0).
    open_faces : list of str, optional
        Faces to remove: any subset of {"top","bottom","front","back","left","right"}.
    density : float
        Material density in kg/m³ (or any consistent unit); used for mass.

    Returns
    -------
    dict
        ok, volume_outer, volume_inner, shell_mass, thickness_feasible,
        open_faces, geometry_params.
    """
    _ZERO = {
        "ok": False,
        "reason": "",
        "volume_outer": 0.0,
        "volume_inner": 0.0,
        "shell_mass": 0.0,
        "thickness_feasible": False,
        "open_faces": open_faces or [],
        "geometry_params": {},
    }

    try:
        dims = [float(d) for d in outer_dims]
    except Exception as exc:
        return {**_ZERO, "ok": False, "reason": f"invalid outer_dims: {exc}"}

    if len(dims) != 3:
        return {**_ZERO, "ok": False, "reason": "outer_dims must have exactly 3 elements [w, d, h]"}

    if any(d <= 0 for d in dims):
        return {**_ZERO, "ok": False, "reason": f"all outer_dims must be > 0; got {dims}"}

    if not isinstance(wall_thickness, (int, float)) or wall_thickness <= 0:
        return {**_ZERO, "ok": False,
                "reason": f"wall_thickness must be > 0; got {wall_thickness!r}"}

    if not isinstance(density, (int, float)) or density <= 0:
        return {**_ZERO, "ok": False, "reason": f"density must be > 0; got {density!r}"}

    open_faces = [f.lower() for f in (open_faces or [])]
    invalid_faces = [f for f in open_faces if f not in _VALID_FACES]
    if invalid_faces:
        return {**_ZERO, "ok": False,
                "reason": f"invalid face names: {invalid_faces}; allowed={sorted(_VALID_FACES)}"}

    w, d, h = dims
    t = float(wall_thickness)

    # Feasibility: inner dims must all be positive
    inner_w = w - 2 * t
    inner_d = d - 2 * t
    inner_h = h - 2 * t
    feasible = inner_w > 0 and inner_d > 0 and inner_h > 0

    volume_outer = w * d * h
    volume_inner = max(0.0, inner_w) * max(0.0, inner_d) * max(0.0, inner_h)

    shell_volume = volume_outer - volume_inner
    shell_mass = shell_volume * float(density)

    return {
        "ok": True,
        "reason": "",
        "volume_outer": volume_outer,
        "volume_inner": volume_inner,
        "shell_mass": shell_mass,
        "thickness_feasible": feasible,
        "open_faces": open_faces,
        "geometry_params": {
            "outer_dims": dims,
            "inner_dims": [inner_w, inner_d, inner_h],
            "wall_thickness": t,
            "density": density,
            "shell_volume": shell_volume,
            "occ_available": _OCC_AVAILABLE,
            "occ_note": (
                "BRepOffsetAPI_MakeThickSolid / BRepPrimAPI_MakeBox require pythonOCC; "
                "analytic spec is ready for the OCCT worker."
            ),
            "feasibility": {
                "min_inner_dim": min(inner_w, inner_d, inner_h),
                "feasible": feasible,
            },
        },
    }


# ---------------------------------------------------------------------------
# 2b. shell_body  (GK-45)
# ---------------------------------------------------------------------------

def _unit3(v: np.ndarray) -> np.ndarray:
    """Return the unit vector of *v* (raises ValueError on zero vector)."""
    n = float(np.linalg.norm(v))
    if n < 1e-14:
        raise ValueError("zero-length vector cannot be normalised")
    return v / n


def _face_outward_normal(face: "_Face") -> np.ndarray:
    """Return the outward unit normal of a face at its parametric origin.

    Works for any surface that implements ``normal(u, v)``, falling back
    to a finite-difference cross-product for surfaces without that method.
    The sign is checked against the face's ``.orientation`` flag and the
    rough centroid of the face's loop to determine whether the normal
    points outward from the solid.
    """
    surf = face.surface
    if hasattr(surf, "normal"):
        nrm = np.asarray(surf.normal(0.0, 0.0), dtype=float)
    else:
        h = 1e-5
        p = np.asarray(surf.evaluate(0.0, 0.0), dtype=float)
        du = np.asarray(surf.evaluate(h, 0.0), dtype=float) - p
        dv = np.asarray(surf.evaluate(0.0, h), dtype=float) - p
        nrm = np.cross(du, dv)
    nrm = _unit3(nrm)
    if not face.orientation:
        nrm = -nrm
    return nrm


def _face_sample_point(face: "_Face") -> np.ndarray:
    """Return a representative point on the face (centroid of outer loop vertices)."""
    pts = []
    outer = face.outer_loop()
    if outer is not None:
        for ce in outer.coedges:
            pts.append(ce.start_vertex().point)
    if not pts:
        return np.asarray(face.surface.evaluate(0.0, 0.0), dtype=float)
    return np.mean(pts, axis=0)


def _offset_plane(plane: "_Plane", d: float) -> "_Plane":
    """Return a new :class:`Plane` shifted by *d* along its normal.

    Parameters
    ----------
    plane : Plane
        Source analytic plane.
    d : float
        Signed offset (positive = along normal, negative = opposite).
    """
    nrm = _unit3(np.cross(plane.x_axis, plane.y_axis))
    new_origin = plane.origin + d * nrm
    return _Plane(origin=new_origin, x_axis=plane.x_axis.copy(), y_axis=plane.y_axis.copy())


def _intersect_three_planes(
    p1: "_Plane", p2: "_Plane", p3: "_Plane"
) -> np.ndarray:
    """Compute the intersection point of three analytic planes.

    Raises ``ValueError`` when the planes do not meet at a unique point.
    """
    n1 = _unit3(np.cross(p1.x_axis, p1.y_axis))
    n2 = _unit3(np.cross(p2.x_axis, p2.y_axis))
    n3 = _unit3(np.cross(p3.x_axis, p3.y_axis))
    d1 = float(np.dot(n1, p1.origin))
    d2 = float(np.dot(n2, p2.origin))
    d3 = float(np.dot(n3, p3.origin))
    A = np.array([n1, n2, n3])
    b = np.array([d1, d2, d3])
    det = float(np.linalg.det(A))
    if abs(det) < 1e-12:
        raise ValueError("Three planes do not have a unique intersection point (parallel or coincident)")
    return np.linalg.solve(A, b)


def _build_planar_quad_face(
    pts: List[np.ndarray],
    tol: float = 1e-7,
    flip_normal: bool = False,
) -> "_Face":
    """Build a quad planar :class:`Face` from 4 corner points (CCW order).

    The face normal is ``cross(pts[1]-pts[0], pts[3]-pts[0])``.
    If *flip_normal* is True the winding is reversed so the normal flips.
    """
    if flip_normal:
        pts = [pts[0], pts[3], pts[2], pts[1]]

    V = [_Vertex(p.copy(), tol) for p in pts]

    edges = [
        _Edge(_Line3(V[i].point, V[(i + 1) % 4].point), 0.0, 1.0,
              V[i], V[(i + 1) % 4], tol)
        for i in range(4)
    ]
    coedges = [_Coedge(e, True) for e in edges]
    loop = _Loop(coedges, is_outer=True)
    p0, p1, p3 = pts[0], pts[1], pts[3]
    plane = _Plane(origin=p0, x_axis=_unit3(p1 - p0), y_axis=_unit3(p3 - p0))
    return _Face(plane, [loop], orientation=True, tol=tol)


def shell_body(
    body: "_Body",
    wall_thickness: float,
    *,
    open_face_index: Optional[int] = None,
    tol: float = 1e-7,
) -> dict:
    """Shell/hollow a closed planar-faced :class:`Body` by offsetting each face inward.

    Topology operation: for each outer face, an inner face is built offset
    inward by *wall_thickness*.  Rim (wall) quad faces stitch the outer
    boundary edges to the inner boundary edges.  An optional face (by
    index into the body's outer-shell face list) may be removed to leave
    an open shell.

    Limitations
    -----------
    * Supports bodies whose outer shell is **planar-faced** (all faces
      have a :class:`~kerf_cad_core.geom.brep.Plane` surface).  This
      covers ``make_box`` and ``extrude_to_body`` outputs.
    * Non-planar faces (cylinders, spheres, NURBS) raise a descriptive
      ``ValueError`` rather than silently producing incorrect geometry.
    * *open_face_index* removes one outer face (and its corresponding
      inner face), leaving the six rim faces connecting the aperture
      boundary as open boundary edges — resulting in an open (non-closed)
      shell body.

    Parameters
    ----------
    body : Body
        Input body.  Must have exactly one solid with one closed outer shell.
    wall_thickness : float
        Inward offset distance ``t > 0``.
    open_face_index : int, optional
        Zero-based index into the outer shell's face list of the face to
        remove.  When given, the body becomes an open shell (a box with
        one side missing, like a tray).
    tol : float
        Topological tolerance forwarded to sewing and B-rep construction.

    Returns
    -------
    dict
        ``ok``, ``body`` (:class:`Body`), ``volume_outer``, ``volume_inner``,
        ``wall_thickness``, ``open_face_index``, ``n_faces``, ``n_edges``,
        ``n_vertices``, ``geometry_params``.
        On error: ``ok=False``, ``reason``, ``body=None``.
    """
    _ZERO: dict = {
        "ok": False,
        "reason": "",
        "body": None,
        "volume_outer": 0.0,
        "volume_inner": 0.0,
        "wall_thickness": 0.0,
        "open_face_index": open_face_index,
        "n_faces": 0,
        "n_edges": 0,
        "n_vertices": 0,
        "geometry_params": {},
    }

    # ── Input validation ────────────────────────────────────────────────
    if not isinstance(body, _Body):
        return {**_ZERO, "reason": f"body must be a Body instance, got {type(body).__name__}"}

    if not isinstance(wall_thickness, (int, float)) or wall_thickness <= 0:
        return {**_ZERO, "reason": f"wall_thickness must be > 0; got {wall_thickness!r}"}

    t = float(wall_thickness)

    if not body.solids:
        return {**_ZERO, "reason": "body has no solids"}
    if len(body.solids) > 1:
        return {**_ZERO, "reason": f"body has {len(body.solids)} solids; shell_body supports exactly 1"}
    solid = body.solids[0]
    if not solid.shells:
        return {**_ZERO, "reason": "body solid has no shells"}
    outer_shell = solid.shells[0]
    if not outer_shell.is_closed:
        return {**_ZERO, "reason": "outer shell is not closed; cannot shell an open body"}

    outer_faces = outer_shell.faces
    n_outer = len(outer_faces)

    if open_face_index is not None:
        if not isinstance(open_face_index, int) or not (0 <= open_face_index < n_outer):
            return {**_ZERO,
                    "reason": f"open_face_index {open_face_index!r} out of range [0, {n_outer - 1}]"}

    # ── Verify all faces have Plane surfaces ────────────────────────────
    for i, f in enumerate(outer_faces):
        if not isinstance(f.surface, _Plane):
            return {**_ZERO,
                    "reason": (
                        f"face {i} has non-planar surface {type(f.surface).__name__}; "
                        "shell_body currently supports planar-faced bodies only"
                    )}

    # ── Compute offset planes (inward by t) ─────────────────────────────
    # Outward normal of each face — the Plane's normal is cross(x_axis, y_axis).
    # For a properly oriented outer face this should point outward; we
    # correct for face.orientation flag.
    offset_planes: List[_Plane] = []
    face_normals: List[np.ndarray] = []
    for f in outer_faces:
        plane = f.surface
        raw_nrm = _unit3(np.cross(plane.x_axis, plane.y_axis))
        nrm = raw_nrm if f.orientation else -raw_nrm
        face_normals.append(nrm)
        # Inward offset = move origin along -nrm by t
        inner_origin = plane.origin - t * nrm
        offset_planes.append(_Plane(origin=inner_origin,
                                    x_axis=plane.x_axis.copy(),
                                    y_axis=plane.y_axis.copy()))

    # ── Extract ordered corner vertices per outer face ───────────────────
    # For each face, extract the coedge ring to get corner vertices in order.
    outer_face_vertices: List[List[np.ndarray]] = []
    for f in outer_faces:
        outer_loop = f.outer_loop()
        if outer_loop is None:
            return {**_ZERO, "reason": f"face has no outer loop: {f!r}"}
        verts = [ce.start_vertex().point for ce in outer_loop.coedges]
        outer_face_vertices.append(verts)

    # ── Build inner corner points by intersecting 3 offset planes ────────
    # For each vertex of the outer shell, find which 3 faces are incident to it.
    # The inner vertex is the intersection of those 3 offset planes.

    # Map: vertex id -> list of (face_index, plane_index)
    vertex_to_faces: dict = {}
    for fi, f in enumerate(outer_faces):
        outer_loop = f.outer_loop()
        if outer_loop is None:
            continue
        for ce in outer_loop.coedges:
            vid = id(ce.start_vertex())
            vertex_to_faces.setdefault(vid, []).append(fi)

    # All unique outer vertices (in order of first encounter)
    all_outer_verts: List[np.ndarray] = []
    outer_vert_id_to_idx: dict = {}
    for fi, f in enumerate(outer_faces):
        outer_loop = f.outer_loop()
        if outer_loop is None:
            continue
        for ce in outer_loop.coedges:
            vid = id(ce.start_vertex())
            if vid not in outer_vert_id_to_idx:
                outer_vert_id_to_idx[vid] = len(all_outer_verts)
                all_outer_verts.append(ce.start_vertex().point.copy())

    # Compute inner vertices by 3-plane intersection
    inner_verts: List[np.ndarray] = []
    for vid, vert_pt in zip(outer_vert_id_to_idx.keys(), all_outer_verts):
        face_indices = vertex_to_faces.get(vid, [])
        if len(face_indices) < 3:
            return {**_ZERO,
                    "reason": (
                        f"vertex at {vert_pt} is incident to {len(face_indices)} faces "
                        "(need ≥ 3 for inner vertex computation)"
                    )}
        # Use the first 3 incident planes for the intersection
        planes_3 = [offset_planes[fi] for fi in face_indices[:3]]
        try:
            inner_pt = _intersect_three_planes(*planes_3)
        except ValueError as exc:
            return {**_ZERO, "reason": f"inner vertex computation failed: {exc}"}

        # Verify wall thickness: distance from inner_pt to outer_pt ≈ t
        # (only exact for a box; allow small geometric tolerance)
        inner_verts.append(inner_pt)

    # Map each face's outer vertices to their inner counterparts
    # inner_face_vertices[fi] = inner corners corresponding to outer_face_vertices[fi]
    inner_face_vertices: List[List[np.ndarray]] = []
    for fi, f in enumerate(outer_faces):
        outer_loop = f.outer_loop()
        if outer_loop is None:
            inner_face_vertices.append([])
            continue
        inner_corners = []
        for ce in outer_loop.coedges:
            vid = id(ce.start_vertex())
            idx = outer_vert_id_to_idx[vid]
            inner_corners.append(inner_verts[idx])
        inner_face_vertices.append(inner_corners)

    # ── Feasibility: inner dims must all be positive ──────────────────────
    # The inner body is degenerate when the offset planes "cross over" —
    # i.e. when the inner vertex is on the wrong side of any outer face plane.
    # Check: for each inner vertex, its distance to the corresponding outer
    # face planes must be >= t (not collapsed past zero).
    if inner_verts and all_outer_verts:
        all_outer = np.array(all_outer_verts)
        all_inner = np.array(inner_verts)
        outer_extents = all_outer.max(axis=0) - all_outer.min(axis=0)
        inner_extents = all_inner.max(axis=0) - all_inner.min(axis=0)
        # For a box, each inner extent should be outer_extent - 2*t
        for axis_i in range(3):
            expected_inner = outer_extents[axis_i] - 2 * t
            if expected_inner <= -tol:
                return {**_ZERO,
                        "reason": (
                            f"wall_thickness {t} is too large; inner body is degenerate "
                            f"(axis {axis_i}: outer extent {outer_extents[axis_i]:.4g} - 2t = {expected_inner:.4g} ≤ 0)"
                        )}

    # ── Determine which face(s) to remove ────────────────────────────────
    faces_to_remove: set = set()
    if open_face_index is not None:
        faces_to_remove.add(open_face_index)

    # ── Assemble faces: outer + inner + rim quads ─────────────────────────
    all_new_faces: List[_Face] = []

    # OUTER faces (keep as-is by rebuilding them fresh for sewing)
    for fi, f in enumerate(outer_faces):
        if fi in faces_to_remove:
            continue
        pts = outer_face_vertices[fi]
        new_face = _build_planar_quad_face(pts, tol=tol, flip_normal=False)
        all_new_faces.append(new_face)

    # INNER faces (reversed winding so normal points inward = toward outer)
    for fi, f in enumerate(outer_faces):
        if fi in faces_to_remove:
            continue
        pts = inner_face_vertices[fi]
        # Flip so the inner face normal points toward the interior (inward = outward
        # from the inner shell perspective means toward the void).
        # The inner shell must have normals pointing INWARD (toward the shell material).
        # In a hollow body, the inner surface normals point toward the outer surface.
        # flip_normal=True reverses the winding, flipping the normal.
        new_face = _build_planar_quad_face(pts, tol=tol, flip_normal=True)
        all_new_faces.append(new_face)

    # RIM (wall) faces: for each outer edge that is on the boundary of a removed face,
    # or for each edge of the outer faces that connects to a removed face's edges.
    # For a fully closed shell: connect each edge of each outer face to the
    # corresponding edge of the inner face (wall faces).
    # For an open shell (one face removed): all 4 edges of the removed outer face
    # become rim aperture — we need to build rim quads for those boundary edges too.
    #
    # Strategy: for each outer face, for each of its edges, if the adjacent face
    # is the removed face, build a rim quad from the outer edge to the inner edge.

    # Build face adjacency: for each edge (as frozenset of vertex ids), which faces share it
    outer_edge_to_faces: dict = {}
    for fi, f in enumerate(outer_faces):
        outer_loop = f.outer_loop()
        if outer_loop is None:
            continue
        ces = outer_loop.coedges
        for i, ce in enumerate(ces):
            v0 = id(ce.start_vertex())
            v1 = id(ces[(i + 1) % len(ces)].start_vertex())
            key = frozenset([v0, v1])
            outer_edge_to_faces.setdefault(key, []).append(fi)

    # For a closed shell: build rim quads for ALL outer edges (connecting outer
    # boundary to inner boundary). But we only need rim quads on edges that
    # border the removed face (for open shell) or for all edges where inner
    # and outer surfaces need to be stitched with wall material.
    #
    # Correct approach for hollow body:
    # - A rim quad sits between each pair of adjacent outer+inner faces.
    # - We need a rim quad for every edge of the outer shell.
    # - The 4 corners of a rim quad for edge (va, vb) are:
    #     outer_va, outer_vb, inner_vb, inner_va  (forms a quad)
    #
    # For a CLOSED shell: all outer face edges are shared between two outer faces.
    # The rim quads form a "tubular" connection — but wait, for a truly hollow solid
    # (like a hollow box), the inner shell is a separate closed body nested inside
    # the outer shell. The Solid object has outer_shell=outer and void_shell=inner.
    #
    # Re-thinking: A hollow body IS a body with two nested closed shells, not
    # a single re-sewn body. The outer shell faces outward, the inner shell
    # faces inward (normals pointing INTO the material = outward from the void).
    # This is the canonical B-rep representation of a hollow solid.
    #
    # The "rim" faces are only needed for OPEN shells (where one face is removed)
    # to connect the outer boundary loop to the inner boundary loop at the aperture.

    rim_faces: List[_Face] = []

    if open_face_index is not None:
        # Build rim quads around the aperture (the edges of the removed outer face)
        removed_fi = open_face_index
        removed_outer_loop = outer_faces[removed_fi].outer_loop()
        if removed_outer_loop is not None:
            ces = removed_outer_loop.coedges
            n_rim = len(ces)
            for i in range(n_rim):
                ce = ces[i]
                va_outer = ce.start_vertex().point
                vb_outer = ces[(i + 1) % n_rim].start_vertex().point
                # Corresponding inner vertices
                va_inner = inner_verts[outer_vert_id_to_idx[id(ce.start_vertex())]]
                vb_inner = inner_verts[outer_vert_id_to_idx[id(ces[(i + 1) % n_rim].start_vertex())]]
                # Rim quad: outer_va -> outer_vb -> inner_vb -> inner_va
                # Normal should point outward from the rim face.
                rim_pts = [va_outer, vb_outer, vb_inner, va_inner]
                rim_face = _build_planar_quad_face(rim_pts, tol=tol, flip_normal=False)
                rim_faces.append(rim_face)

    all_new_faces.extend(rim_faces)

    # ── Sew faces into shell(s) / Body ────────────────────────────────────
    try:
        if open_face_index is None:
            # Two closed shells: outer + inner. We sew them separately and
            # build a Body with a Solid containing both shells.
            n_half = n_outer  # all outer faces kept

            outer_new_faces = all_new_faces[:n_outer]
            inner_new_faces = all_new_faces[n_outer:]

            outer_sewn = _sew_faces(outer_new_faces, tol=tol)
            inner_sewn = _sew_faces(inner_new_faces, tol=tol)

            if not outer_sewn.is_closed:
                return {**_ZERO, "reason": "sewn outer shell is not closed"}
            if not inner_sewn.is_closed:
                return {**_ZERO, "reason": "sewn inner shell is not closed"}

            solid = _Solid([outer_sewn, inner_sewn])
            new_body = _Body(solids=[solid])

            res = _validate_body(new_body)
            if not res["ok"]:
                return {**_ZERO,
                        "reason": f"shell_body produced invalid Body: {res['errors']}",
                        "geometry_params": {"validate_errors": res["errors"]}}
        else:
            # Single open shell from sewn outer + inner + rim faces
            sewn_shell = _sew_faces(all_new_faces, tol=tol)
            solid = _Solid([sewn_shell])
            new_body = _Body(solids=[solid])

            # For open shells validate_body may complain about non-closed manifold;
            # we run it but don't hard-fail — report the result.
            res = _validate_body(new_body)
            if not res["ok"]:
                return {**_ZERO,
                        "reason": f"shell_body (open) produced invalid Body: {res['errors']}",
                        "geometry_params": {"validate_errors": res["errors"]}}

    except BuildError as exc:
        return {**_ZERO, "reason": f"sew failed: {exc}"}
    except Exception as exc:
        return {**_ZERO, "reason": f"shell_body failed: {exc}"}

    # ── Volume accounting ─────────────────────────────────────────────────
    # Compute outer volume from bounding box of outer vertices
    all_outer_pts = np.array(all_outer_verts)
    mins_out = all_outer_pts.min(axis=0)
    maxs_out = all_outer_pts.max(axis=0)
    volume_outer = float(np.prod(maxs_out - mins_out))

    all_inner_pts = np.array(inner_verts)
    mins_in = all_inner_pts.min(axis=0)
    maxs_in = all_inner_pts.max(axis=0)
    volume_inner = float(np.prod(maxs_in - mins_in))

    counts = new_body.euler_counts()
    return {
        "ok": True,
        "reason": "",
        "body": new_body,
        "volume_outer": volume_outer,
        "volume_inner": volume_inner,
        "wall_thickness": t,
        "open_face_index": open_face_index,
        "n_faces": counts["F"],
        "n_edges": counts["E"],
        "n_vertices": counts["V"],
        "geometry_params": {
            "n_outer_faces": n_outer,
            "n_inner_faces": n_outer - len(faces_to_remove),
            "n_rim_faces": len(rim_faces),
            "open_face_index": open_face_index,
            "tol": tol,
            "occ_available": _OCC_AVAILABLE,
        },
    }


# ---------------------------------------------------------------------------
# 3. variable_radius_fillet
# ---------------------------------------------------------------------------

def variable_radius_fillet(
    edge_length: float,
    radius_start: float,
    radius_end: float,
    *,
    min_allowed_radius: Optional[float] = None,
) -> dict:
    """Edge fillet with radius varying linearly along the edge.

    Parameters
    ----------
    edge_length : float
        Length of the edge to be filleted (> 0).
    radius_start : float
        Fillet radius at the start of the edge (> 0).
    radius_end : float
        Fillet radius at the end of the edge (> 0).
    min_allowed_radius : float, optional
        Manufacturing minimum radius.  Both endpoint radii and the minimum
        along the edge are checked.

    Returns
    -------
    dict
        ok, radius_at_start, radius_at_end, min_radius_on_edge,
        min_radius_violation, tangency_ok, geometry_params.
    """
    _ZERO = {
        "ok": False,
        "reason": "",
        "radius_at_start": 0.0,
        "radius_at_end": 0.0,
        "min_radius_on_edge": 0.0,
        "min_radius_violation": False,
        "tangency_ok": False,
        "geometry_params": {},
    }

    if not isinstance(edge_length, (int, float)) or edge_length <= 0:
        return {**_ZERO, "ok": False, "reason": f"edge_length must be > 0; got {edge_length!r}"}
    if not isinstance(radius_start, (int, float)) or radius_start <= 0:
        return {**_ZERO, "ok": False,
                "reason": f"radius_start must be > 0; got {radius_start!r}"}
    if not isinstance(radius_end, (int, float)) or radius_end <= 0:
        return {**_ZERO, "ok": False, "reason": f"radius_end must be > 0; got {radius_end!r}"}

    edge_length = float(edge_length)
    radius_start = float(radius_start)
    radius_end = float(radius_end)

    # Minimum radius is at one endpoint (linear interpolation → monotone)
    min_radius = min(radius_start, radius_end)

    # Violation check
    violation = False
    if min_allowed_radius is not None and min_allowed_radius > 0:
        violation = min_radius < float(min_allowed_radius)

    # Tangency: for a smooth fillet the radius change rate must be smooth.
    # A common check: |dr/ds| = |r_end - r_start| / L must be < 1 for G1 tangency.
    dr_ds = abs(radius_end - radius_start) / edge_length
    tangency_ok = dr_ds < 1.0

    # Sample radius at 10 evenly spaced t values for geometry_params
    samples = [
        {"t": t, "radius": radius_start + (radius_end - radius_start) * t}
        for t in [i / 9.0 for i in range(10)]
    ]

    return {
        "ok": True,
        "reason": "",
        "radius_at_start": radius_start,
        "radius_at_end": radius_end,
        "min_radius_on_edge": min_radius,
        "min_radius_violation": violation,
        "tangency_ok": tangency_ok,
        "geometry_params": {
            "edge_length": edge_length,
            "dr_ds": dr_ds,
            "radius_samples": samples,
            "min_allowed_radius": min_allowed_radius,
            "occ_available": _OCC_AVAILABLE,
            "occ_note": (
                "BRepFilletAPI_MakeFillet with ChFi3d_FilletShape variable-radius "
                "requires pythonOCC; analytic spec ready for OCCT worker."
            ),
        },
    }


# ---------------------------------------------------------------------------
# 4. draft_faces
# ---------------------------------------------------------------------------

def draft_faces(
    face_height: float,
    draft_angle_deg: float,
    *,
    neutral_plane_offset: float = 0.0,
) -> dict:
    """Apply a draft angle to a planar face about a pull direction.

    The neutral plane is at ``neutral_plane_offset`` (fraction of face_height
    from the bottom).  Above and below the neutral plane the face tapers
    inward/outward by ``draft_angle_deg``.

    Parameters
    ----------
    face_height : float
        Height of the drafted face (> 0).
    draft_angle_deg : float
        Draft angle in degrees (0 < angle < 90).
    neutral_plane_offset : float
        Height of the neutral plane as a fraction [0,1] of face_height.
        0.0 = bottom, 1.0 = top.

    Returns
    -------
    dict
        ok, taper_offset_at_top, taper_offset_at_bottom, draft_angle_deg,
        neutral_plane_offset, geometry_params.
    """
    _ZERO = {
        "ok": False,
        "reason": "",
        "taper_offset_at_top": 0.0,
        "taper_offset_at_bottom": 0.0,
        "draft_angle_deg": draft_angle_deg,
        "neutral_plane_offset": neutral_plane_offset,
        "geometry_params": {},
    }

    if not isinstance(face_height, (int, float)) or face_height <= 0:
        return {**_ZERO, "ok": False, "reason": f"face_height must be > 0; got {face_height!r}"}

    if not isinstance(draft_angle_deg, (int, float)):
        return {**_ZERO, "ok": False,
                "reason": f"draft_angle_deg must be a number; got {draft_angle_deg!r}"}
    if not (0 < draft_angle_deg < 90):
        return {**_ZERO, "ok": False,
                "reason": f"draft_angle_deg must be in (0, 90); got {draft_angle_deg}"}

    if not isinstance(neutral_plane_offset, (int, float)):
        return {**_ZERO, "ok": False,
                "reason": f"neutral_plane_offset must be a number; got {neutral_plane_offset!r}"}
    if not (0.0 <= neutral_plane_offset <= 1.0):
        return {**_ZERO, "ok": False,
                "reason": f"neutral_plane_offset must be in [0,1]; got {neutral_plane_offset}"}

    face_height = float(face_height)
    angle_rad = math.radians(float(draft_angle_deg))
    h_neutral = face_height * float(neutral_plane_offset)
    h_above = face_height - h_neutral
    h_below = h_neutral

    # Taper offset = h * tan(angle)
    taper_top = h_above * math.tan(angle_rad)
    taper_bottom = h_below * math.tan(angle_rad)

    # Sample offset at 10 heights
    samples = []
    for i in range(11):
        h = face_height * i / 10.0
        dist_from_neutral = abs(h - h_neutral)
        offset = dist_from_neutral * math.tan(angle_rad)
        samples.append({"height": h, "taper_offset": offset})

    return {
        "ok": True,
        "reason": "",
        "taper_offset_at_top": taper_top,
        "taper_offset_at_bottom": taper_bottom,
        "draft_angle_deg": float(draft_angle_deg),
        "neutral_plane_offset": float(neutral_plane_offset),
        "geometry_params": {
            "face_height": face_height,
            "angle_rad": angle_rad,
            "h_neutral": h_neutral,
            "h_above_neutral": h_above,
            "h_below_neutral": h_below,
            "height_samples": samples,
            "occ_available": _OCC_AVAILABLE,
            "occ_note": (
                "BRepFeat_MakeDPrism (draft prism) requires pythonOCC; "
                "analytic spec ready for OCCT worker."
            ),
        },
    }


# ---------------------------------------------------------------------------
# 5. rib_web
# ---------------------------------------------------------------------------

def rib_web(
    profile_length: float,
    rib_thickness: float,
    rib_height: float,
    *,
    draft_angle_deg: float = 0.0,
    attachment_width: Optional[float] = None,
) -> dict:
    """Thickened rib between a profile and a solid.

    Parameters
    ----------
    profile_length : float
        Length of the rib profile along the solid surface (> 0).
    rib_thickness : float
        Thickness of the rib at the neutral plane (> 0).
    rib_height : float
        Height of the rib above the attachment surface (> 0).
    draft_angle_deg : float
        Optional draft angle (0 ≤ angle < 90) applied to rib faces.
    attachment_width : float, optional
        Width of the rib foot at the base; if omitted, computed as
        rib_thickness + 2 * rib_height * tan(draft_angle_deg).

    Returns
    -------
    dict
        ok, volume, cross_section_area, draft_taper, attachment_width,
        geometry_params.
    """
    _ZERO = {
        "ok": False,
        "reason": "",
        "volume": 0.0,
        "cross_section_area": 0.0,
        "draft_taper": 0.0,
        "attachment_width": 0.0,
        "geometry_params": {},
    }

    if not isinstance(profile_length, (int, float)) or profile_length <= 0:
        return {**_ZERO, "ok": False,
                "reason": f"profile_length must be > 0; got {profile_length!r}"}
    if not isinstance(rib_thickness, (int, float)) or rib_thickness <= 0:
        return {**_ZERO, "ok": False,
                "reason": f"rib_thickness must be > 0; got {rib_thickness!r}"}
    if not isinstance(rib_height, (int, float)) or rib_height <= 0:
        return {**_ZERO, "ok": False,
                "reason": f"rib_height must be > 0; got {rib_height!r}"}
    if not isinstance(draft_angle_deg, (int, float)):
        return {**_ZERO, "ok": False,
                "reason": f"draft_angle_deg must be a number; got {draft_angle_deg!r}"}
    if not (0.0 <= draft_angle_deg < 90.0):
        return {**_ZERO, "ok": False,
                "reason": f"draft_angle_deg must be in [0, 90); got {draft_angle_deg}"}

    profile_length = float(profile_length)
    rib_thickness = float(rib_thickness)
    rib_height = float(rib_height)
    draft_rad = math.radians(float(draft_angle_deg))
    draft_taper = rib_height * math.tan(draft_rad)

    # Trapezoidal cross-section (symmetric draft)
    # Top width = rib_thickness; bottom width = rib_thickness + 2 * taper
    w_top = rib_thickness
    w_bottom = rib_thickness + 2.0 * draft_taper
    cross_section_area = 0.5 * (w_top + w_bottom) * rib_height

    volume = cross_section_area * profile_length

    att_width = float(attachment_width) if attachment_width is not None else w_bottom

    return {
        "ok": True,
        "reason": "",
        "volume": volume,
        "cross_section_area": cross_section_area,
        "draft_taper": draft_taper,
        "attachment_width": att_width,
        "geometry_params": {
            "profile_length": profile_length,
            "rib_thickness": rib_thickness,
            "rib_height": rib_height,
            "draft_angle_deg": float(draft_angle_deg),
            "draft_rad": draft_rad,
            "w_top": w_top,
            "w_bottom": w_bottom,
            "occ_available": _OCC_AVAILABLE,
            "occ_note": (
                "BRepFeat_MakeLinearForm (rib/web) requires pythonOCC; "
                "analytic spec ready for OCCT worker."
            ),
        },
    }


# ---------------------------------------------------------------------------
# 6. wirecut
# ---------------------------------------------------------------------------

def wirecut(
    solid_bbox: Sequence,
    cut_profile_points: Sequence,
    *,
    direction: Tuple[float, float, float] = (0.0, 0.0, 1.0),
) -> dict:
    """Cut a solid with a swept 2D profile through-all.

    The cut profile (a 2D polyline in the XY plane) is extruded through the
    solid along ``direction``.

    Parameters
    ----------
    solid_bbox : [width, depth, height]
        Bounding box of the solid being cut (all > 0).
    cut_profile_points : sequence of [x, y]
        2D profile points in the cutting plane (at least 2).
    direction : (dx, dy, dz)
        Sweep direction (unit vector); the profile is extruded this way
        through the entire solid bounding box.

    Returns
    -------
    dict
        ok, cut_area, path_length, cut_depth, direction, geometry_params.
    """
    _ZERO = {
        "ok": False,
        "reason": "",
        "cut_area": 0.0,
        "path_length": 0.0,
        "cut_depth": 0.0,
        "direction": list(direction),
        "geometry_params": {},
    }

    try:
        bbox = [float(d) for d in solid_bbox]
    except Exception as exc:
        return {**_ZERO, "ok": False, "reason": f"invalid solid_bbox: {exc}"}

    if len(bbox) != 3:
        return {**_ZERO, "ok": False, "reason": "solid_bbox must have exactly 3 elements [w, d, h]"}
    if any(d <= 0 for d in bbox):
        return {**_ZERO, "ok": False, "reason": f"all solid_bbox dims must be > 0; got {bbox}"}

    try:
        profile_pts = [np.asarray(p, dtype=float).reshape(-1)[:2] for p in cut_profile_points]
    except Exception as exc:
        return {**_ZERO, "ok": False, "reason": f"invalid cut_profile_points: {exc}"}

    if len(profile_pts) < 2:
        return {**_ZERO, "ok": False, "reason": "cut_profile_points must have at least 2 points"}

    try:
        dir_vec = _vec3(direction)
    except Exception as exc:
        return {**_ZERO, "ok": False, "reason": f"invalid direction: {exc}"}

    dir_norm = float(np.linalg.norm(dir_vec))
    if dir_norm < 1e-10:
        return {**_ZERO, "ok": False, "reason": "direction must be a non-zero vector"}

    dir_unit = dir_vec / dir_norm

    # ── Profile arc length (2-D) ──────────────────────────────────────────
    path_length_2d = sum(
        float(np.linalg.norm(profile_pts[i + 1] - profile_pts[i]))
        for i in range(len(profile_pts) - 1)
    )

    # ── Cut depth: project bbox diagonal onto the direction vector ─────────
    # Worst-case depth = max extent of bbox along direction
    bbox_corners = np.array([
        [s_x * bbox[0], s_y * bbox[1], s_z * bbox[2]]
        for s_x in (0, 1) for s_y in (0, 1) for s_z in (0, 1)
    ])
    projections = bbox_corners @ dir_unit
    cut_depth = float(projections.max() - projections.min())

    # ── Approximate cut area (swept face area = path_length * cut_depth) ──
    cut_area = path_length_2d * cut_depth

    return {
        "ok": True,
        "reason": "",
        "cut_area": cut_area,
        "path_length": path_length_2d,
        "cut_depth": cut_depth,
        "direction": dir_unit.tolist(),
        "geometry_params": {
            "solid_bbox": bbox,
            "num_profile_points": len(profile_pts),
            "profile_pts": [p.tolist() for p in profile_pts],
            "dir_unit": dir_unit.tolist(),
            "occ_available": _OCC_AVAILABLE,
            "occ_note": (
                "BRepPrimAPI_MakePrism + BRepAlgoAPI_Cut require pythonOCC; "
                "analytic spec ready for OCCT worker."
            ),
        },
    }


# ---------------------------------------------------------------------------
# 7. extrude_to_body
# ---------------------------------------------------------------------------

def extrude_to_body(
    profile_vertices: Sequence,
    direction: Sequence,
    *,
    tol: float = 1e-7,
) -> dict:
    """Extrude a closed planar polygon into a capped solid ``Body``.

    Parameters
    ----------
    profile_vertices : sequence of [x, y, z]
        Ordered N-point closed planar polygon (N ≥ 3).  The last point need
        not repeat the first.
    direction : [dx, dy, dz]
        Extrusion vector; its magnitude is the extrusion height.
    tol : float
        Topological tolerance forwarded to the B-rep builder.

    Returns
    -------
    dict
        ok, body (:class:`kerf_cad_core.geom.brep.Body`), volume, n_faces,
        n_edges, n_vertices, geometry_params.
        On error: ok=False, reason, zero-value fields, body=None.

    Notes
    -----
    The returned ``body`` satisfies ``validate_body(body)["ok"] is True``.
    For a 4-sided profile the topology is V=8, E=12, F=6 (identical to a
    box); the Euler–Poincaré residual is 0.
    Volume is computed analytically as ``|profile_area| * |direction|``.
    """
    _ZERO: dict = {
        "ok": False,
        "reason": "",
        "body": None,
        "volume": 0.0,
        "n_faces": 0,
        "n_edges": 0,
        "n_vertices": 0,
        "geometry_params": {},
    }

    # Validate inputs
    try:
        verts = [_vec3(p) for p in profile_vertices]
    except Exception as exc:
        return {**_ZERO, "reason": f"invalid profile_vertices: {exc}"}

    if len(verts) < 3:
        return {**_ZERO, "reason": "profile_vertices must have at least 3 points"}

    try:
        d = _vec3(direction)
    except Exception as exc:
        return {**_ZERO, "reason": f"invalid direction: {exc}"}

    d_len = float(np.linalg.norm(d))
    if d_len < 1e-14:
        return {**_ZERO, "reason": "direction must be a non-zero vector"}

    # Analytic volume = |profile_area| * height
    centroid = np.mean(verts, axis=0)
    area_vec = np.zeros(3)
    for i in range(len(verts)):
        a = verts[i] - centroid
        b = verts[(i + 1) % len(verts)] - centroid
        area_vec += np.cross(a, b)
    profile_area = float(np.linalg.norm(area_vec)) * 0.5
    volume = profile_area * d_len

    try:
        body = _brep_extrude_to_body(verts, d, tol=tol)
    except BuildError as exc:
        return {**_ZERO, "reason": str(exc)}
    except Exception as exc:
        return {**_ZERO, "reason": f"extrude_to_body failed: {exc}"}

    counts = body.euler_counts()
    return {
        "ok": True,
        "reason": "",
        "body": body,
        "volume": volume,
        "n_faces": counts["F"],
        "n_edges": counts["E"],
        "n_vertices": counts["V"],
        "geometry_params": {
            "n_profile_verts": len(verts),
            "profile_area": profile_area,
            "direction": d.tolist(),
            "height": d_len,
            "tol": tol,
            "occ_available": _OCC_AVAILABLE,
        },
    }


# ---------------------------------------------------------------------------
# GK-46  Body-producing ops: draft_body, rib_body, wirecut_body, pipe_body
# ---------------------------------------------------------------------------


def draft_body(
    base_width: float,
    base_depth: float,
    face_height: float,
    draft_angle_deg: float,
    *,
    neutral_plane_offset: float = 0.0,
    tol: float = 1e-7,
) -> dict:
    """Extrude a rectangular face with a draft angle into a validated ``Body``.

    The rectangular base (``base_width`` × ``base_depth``) is tapered by
    ``draft_angle_deg`` degrees about a horizontal neutral plane at
    ``neutral_plane_offset`` (fraction [0,1] of ``face_height``).  Above and
    below the neutral plane each face shrinks inward by
    ``t = h × tan(draft_angle_deg)``.

    The resulting solid is a frustum-like prism whose bottom face is a
    rectangle widened by the taper below the neutral plane and whose top face
    is narrowed by the taper above the neutral plane.  All four lateral faces
    are planar quadrilaterals; the body passes ``validate_body``.

    Parameters
    ----------
    base_width, base_depth : float
        Dimensions of the rectangle at the neutral plane (both > 0).
    face_height : float
        Total height of the solid (> 0).
    draft_angle_deg : float
        Draft angle in degrees; must be in (0, 90).  The taper offset at
        each end is ``h_end × tan(draft_angle_deg)``.
    neutral_plane_offset : float
        Fraction [0, 1] of ``face_height`` for the neutral plane.  0 = bottom,
        1 = top.  Default 0 means the draft opens upward from the base.
    tol : float
        Topological tolerance forwarded to the B-rep builder.

    Returns
    -------
    dict
        ok, body (:class:`~kerf_cad_core.geom.brep.Body`), volume,
        taper_at_top, taper_at_bottom, n_faces, n_edges, n_vertices,
        geometry_params.  On error: ok=False, reason, body=None.
    """
    _ZERO: dict = {
        "ok": False,
        "reason": "",
        "body": None,
        "volume": 0.0,
        "taper_at_top": 0.0,
        "taper_at_bottom": 0.0,
        "n_faces": 0,
        "n_edges": 0,
        "n_vertices": 0,
        "geometry_params": {},
    }

    for name, val in [("base_width", base_width), ("base_depth", base_depth),
                      ("face_height", face_height)]:
        if not isinstance(val, (int, float)) or val <= 0:
            return {**_ZERO, "reason": f"{name} must be > 0; got {val!r}"}

    if not isinstance(draft_angle_deg, (int, float)) or not (0 < draft_angle_deg < 90):
        return {**_ZERO, "reason": f"draft_angle_deg must be in (0, 90); got {draft_angle_deg!r}"}

    if not isinstance(neutral_plane_offset, (int, float)) or not (0.0 <= neutral_plane_offset <= 1.0):
        return {**_ZERO, "reason": (
            f"neutral_plane_offset must be in [0, 1]; got {neutral_plane_offset!r}"
        )}

    base_width = float(base_width)
    base_depth = float(base_depth)
    face_height = float(face_height)
    angle_rad = math.radians(float(draft_angle_deg))
    h_neutral = face_height * float(neutral_plane_offset)
    h_above = face_height - h_neutral
    h_below = h_neutral

    taper_top = h_above * math.tan(angle_rad)
    taper_bottom = h_below * math.tan(angle_rad)

    # ── Compute corner widths / depths at bottom and top ──────────────────
    # At the neutral plane the cross-section is base_width × base_depth.
    # Below: each side expands by taper_bottom (symmetric).
    # Above: each side contracts by taper_top (symmetric).
    w_bottom = base_width + 2.0 * taper_bottom   # wider at base
    d_bottom = base_depth + 2.0 * taper_bottom
    w_top = base_width - 2.0 * taper_top         # narrower at top
    d_top = base_depth - 2.0 * taper_top

    if w_top <= 0 or d_top <= 0:
        return {**_ZERO, "reason": (
            f"draft_angle_deg {draft_angle_deg} is too large; "
            f"top face collapses (w_top={w_top:.4g}, d_top={d_top:.4g})"
        )}

    # Analytic volume: trapezoidal prism  =  Σ (area_at_z * dz) but since
    # width and depth both vary linearly we integrate exactly:
    # V = h * (A_bottom + A_top + A_neutral) / 3  (Simpson for linear taper)
    # Actually it's a prismatoid: V = h/6*(A_bottom + 4*A_mid + A_top)
    # For linear taper: A(z) = w(z)*d(z), linear in z, so the product is
    # quadratic.  Prismatoid formula is exact.
    A_bot = w_bottom * d_bottom
    A_top = w_top * d_top
    w_mid = (w_bottom + w_top) / 2.0
    d_mid = (d_bottom + d_top) / 2.0
    A_mid = w_mid * d_mid
    volume = face_height / 6.0 * (A_bot + 4.0 * A_mid + A_top)

    # ── Build geometry: the solid is an extrusion of the bottom quadrilateral
    # with corresponding top quadrilateral (trapezoidal prism).
    # We express it as 8 corners of a frustum and build a box-like body via
    # brep_build.extrude_to_body, using a tapered polygon.  However
    # extrude_to_body only does straight prisms.  Instead we build directly
    # using box_to_body won't work either.
    #
    # Strategy: build via box_to_body with custom corners — use the low-level
    # brep API directly (8 vertices, 12 edges, 6 planar quad faces).
    # This mirrors box_to_body in brep_build.py but with arbitrary corners.
    from kerf_cad_core.geom.brep_build import box_to_body as _box_to_body

    # Corner layout (z grows upward):
    # Bottom quad (z=0): (-w_b/2, -d_b/2), (w_b/2, -d_b/2),
    #                    (w_b/2, d_b/2), (-w_b/2, d_b/2)
    # Top quad (z=H):    (-w_t/2, -d_t/2), (w_t/2, -d_t/2),
    #                    (w_t/2, d_t/2), (-w_t/2, d_t/2)

    hw_b, hd_b = w_bottom / 2.0, d_bottom / 2.0
    hw_t, hd_t = w_top / 2.0, d_top / 2.0
    H = face_height

    P = [
        np.array([-hw_b, -hd_b, 0.0]),  # 0: bot front-left
        np.array([ hw_b, -hd_b, 0.0]),  # 1: bot front-right
        np.array([ hw_b,  hd_b, 0.0]),  # 2: bot back-right
        np.array([-hw_b,  hd_b, 0.0]),  # 3: bot back-left
        np.array([-hw_t, -hd_t,   H]),  # 4: top front-left
        np.array([ hw_t, -hd_t,   H]),  # 5: top front-right
        np.array([ hw_t,  hd_t,   H]),  # 6: top back-right
        np.array([-hw_t,  hd_t,   H]),  # 7: top back-left
    ]

    try:
        body = _build_frustum_body(P, tol=tol)
    except Exception as exc:
        return {**_ZERO, "reason": f"draft_body build failed: {exc}"}

    counts = body.euler_counts()
    return {
        "ok": True,
        "reason": "",
        "body": body,
        "volume": volume,
        "taper_at_top": taper_top,
        "taper_at_bottom": taper_bottom,
        "n_faces": counts["F"],
        "n_edges": counts["E"],
        "n_vertices": counts["V"],
        "geometry_params": {
            "base_width": base_width,
            "base_depth": base_depth,
            "face_height": face_height,
            "draft_angle_deg": float(draft_angle_deg),
            "neutral_plane_offset": float(neutral_plane_offset),
            "w_bottom": w_bottom,
            "d_bottom": d_bottom,
            "w_top": w_top,
            "d_top": d_top,
            "tol": tol,
            "occ_available": _OCC_AVAILABLE,
        },
    }


def _build_frustum_body(P: List[np.ndarray], tol: float = 1e-7) -> "_Body":
    """Build a closed 6-faced frustum Body from 8 corners P[0..7].

    Corner layout:
        P[0..3] = bottom quad (CCW when viewed from -z)
        P[4..7] = top quad    (matching indices: P[4] above P[0], etc.)

    All six faces are planar quadrilaterals.  The body satisfies
    ``validate_body``.  This is the raw topology builder reused by both
    ``draft_body`` and ``rib_body``.
    """
    # 8 vertices
    V = [_Vertex(p.copy(), tol) for p in P]

    # 12 edges: 4 bottom + 4 top + 4 vertical
    # Bottom ring: 0→1, 1→2, 2→3, 3→0
    # Top ring:    4→5, 5→6, 6→7, 7→4
    # Verticals:   0→4, 1→5, 2→6, 3→7
    edef_bot = [(0,1),(1,2),(2,3),(3,0)]
    edef_top = [(4,5),(5,6),(6,7),(7,4)]
    edef_vert = [(0,4),(1,5),(2,6),(3,7)]

    def _mk_edge(a: int, b: int) -> "_Edge":
        return _Edge(_Line3(P[a], P[b]), 0.0, 1.0, V[a], V[b], tol)

    bot_E = [_mk_edge(a, b) for (a, b) in edef_bot]   # indices 0-3
    top_E = [_mk_edge(a, b) for (a, b) in edef_top]   # indices 0-3
    vert_E = [_mk_edge(a, b) for (a, b) in edef_vert] # indices 0-3

    def _edge_of(a: int, b: int):
        """Return (edge, orientation) for directed edge a→b."""
        for e, (ia, ib) in zip(bot_E, edef_bot):
            if ia == a and ib == b:
                return e, True
            if ia == b and ib == a:
                return e, False
        for e, (ia, ib) in zip(top_E, edef_top):
            if ia == a and ib == b:
                return e, True
            if ia == b and ib == a:
                return e, False
        for e, (ia, ib) in zip(vert_E, edef_vert):
            if ia == a and ib == b:
                return e, True
            if ia == b and ib == a:
                return e, False
        raise ValueError(f"No edge found for {a}→{b}")

    def _build_face(ring: List[int]) -> "_Face":
        """Build a planar Face from a CCW ring of vertex indices (outward normal)."""
        coedges = []
        n = len(ring)
        for i in range(n):
            a, b = ring[i], ring[(i + 1) % n]
            e, o = _edge_of(a, b)
            coedges.append(_Coedge(e, o))
        loop = _Loop(coedges, is_outer=True)
        # Plane from first 3 points
        p0 = P[ring[0]]
        p1 = P[ring[1]]
        p2 = P[ring[-1]]
        x_ax = _unit3(p1 - p0)
        # Compute outward normal via cross product of consecutive edges
        area_vec = np.zeros(3)
        centroid = np.mean([P[i] for i in ring], axis=0)
        for i in range(n):
            a_pt = P[ring[i]] - centroid
            b_pt = P[ring[(i+1) % n]] - centroid
            area_vec += np.cross(a_pt, b_pt)
        nrm = area_vec / (np.linalg.norm(area_vec) + 1e-30)
        y_ax = _unit3(np.cross(nrm, x_ax))
        plane = _Plane(origin=p0.copy(), x_axis=x_ax, y_axis=y_ax)
        return _Face(plane, [loop], orientation=True, tol=tol)

    # Six faces:
    # Bottom (viewed from -z: CCW): 0,3,2,1 (reversed so normal points -z)
    # Top (viewed from +z: CCW):    4,5,6,7
    # Front (y- face):  0,1,5,4
    # Right (x+ face):  1,2,6,5
    # Back  (y+ face):  2,3,7,6
    # Left  (x- face):  3,0,4,7
    face_rings = [
        [0, 3, 2, 1],   # bottom — normal points -z
        [4, 5, 6, 7],   # top    — normal points +z
        [0, 1, 5, 4],   # front
        [1, 2, 6, 5],   # right
        [2, 3, 7, 6],   # back
        [3, 0, 4, 7],   # left
    ]
    faces = [_build_face(ring) for ring in face_rings]
    shell = _Shell(faces, is_closed=True)
    body = _Body(solids=[_Solid([shell])])
    res = _validate_body(body)
    if not res["ok"]:
        raise ValueError(f"_build_frustum_body produced invalid Body: {res['errors']}")
    return body


def rib_body(
    profile_length: float,
    rib_thickness: float,
    rib_height: float,
    *,
    draft_angle_deg: float = 0.0,
    tol: float = 1e-7,
) -> dict:
    """Extrude a rib's trapezoidal cross-section into a validated ``Body``.

    The rib has a trapezoidal cross-section (width varying from ``w_bottom``
    at the base to ``w_top = rib_thickness`` at the top) extruded along the
    rib's profile length.  The resulting solid passes ``validate_body``.

    Parameters
    ----------
    profile_length : float
        Length of the rib along the attachment surface (> 0).
    rib_thickness : float
        Rib width at the top (neutral plane, > 0).
    rib_height : float
        Rib height from attachment surface (> 0).
    draft_angle_deg : float
        Draft angle applied symmetrically to both sides of the rib (0 ≤ < 90).
    tol : float
        Topological tolerance.

    Returns
    -------
    dict
        ok, body, volume, cross_section_area, w_top, w_bottom, n_faces,
        n_edges, n_vertices, geometry_params.  On error: ok=False, reason.
    """
    _ZERO: dict = {
        "ok": False,
        "reason": "",
        "body": None,
        "volume": 0.0,
        "cross_section_area": 0.0,
        "w_top": 0.0,
        "w_bottom": 0.0,
        "n_faces": 0,
        "n_edges": 0,
        "n_vertices": 0,
        "geometry_params": {},
    }

    for name, val in [("profile_length", profile_length), ("rib_thickness", rib_thickness),
                      ("rib_height", rib_height)]:
        if not isinstance(val, (int, float)) or val <= 0:
            return {**_ZERO, "reason": f"{name} must be > 0; got {val!r}"}

    if not isinstance(draft_angle_deg, (int, float)) or not (0.0 <= draft_angle_deg < 90.0):
        return {**_ZERO, "reason": f"draft_angle_deg must be in [0, 90); got {draft_angle_deg!r}"}

    profile_length = float(profile_length)
    rib_thickness = float(rib_thickness)
    rib_height = float(rib_height)
    draft_rad = math.radians(float(draft_angle_deg))
    draft_taper = rib_height * math.tan(draft_rad)

    w_top = rib_thickness
    w_bottom = rib_thickness + 2.0 * draft_taper
    cross_section_area = 0.5 * (w_top + w_bottom) * rib_height
    volume = cross_section_area * profile_length

    # Build the trapezoidal cross-section as a polygon in the YZ plane,
    # then extrude along X (profile_length).
    # Cross-section corners (in XZ plane for readability, extruded along Y):
    #   z=0: x = -w_bottom/2 to +w_bottom/2
    #   z=H: x = -w_top/2 to +w_top/2
    # We place this in the XZ plane and extrude along Y.
    hw_b = w_bottom / 2.0
    hw_t = w_top / 2.0
    H = rib_height
    L = profile_length

    # 8 corner points:
    # Bottom face (y=0): corners of trapezoidal cross-section at y=0
    # Top face    (y=L): same cross-section at y=L
    P = [
        np.array([-hw_b,  0.0, 0.0]),  # 0: bot-left-base
        np.array([ hw_b,  0.0, 0.0]),  # 1: bot-right-base
        np.array([ hw_t,  0.0,   H]),  # 2: bot-right-top
        np.array([-hw_t,  0.0,   H]),  # 3: bot-left-top
        np.array([-hw_b,    L, 0.0]),  # 4: top-left-base
        np.array([ hw_b,    L, 0.0]),  # 5: top-right-base
        np.array([ hw_t,    L,   H]),  # 6: top-right-top
        np.array([-hw_t,    L,   H]),  # 7: top-left-top
    ]

    try:
        body = _build_frustum_body(P, tol=tol)
    except Exception as exc:
        return {**_ZERO, "reason": f"rib_body build failed: {exc}"}

    counts = body.euler_counts()
    return {
        "ok": True,
        "reason": "",
        "body": body,
        "volume": volume,
        "cross_section_area": cross_section_area,
        "w_top": w_top,
        "w_bottom": w_bottom,
        "n_faces": counts["F"],
        "n_edges": counts["E"],
        "n_vertices": counts["V"],
        "geometry_params": {
            "profile_length": profile_length,
            "rib_thickness": rib_thickness,
            "rib_height": rib_height,
            "draft_angle_deg": float(draft_angle_deg),
            "draft_taper": draft_taper,
            "tol": tol,
            "occ_available": _OCC_AVAILABLE,
        },
    }


def wirecut_body(
    solid_bbox: Sequence,
    cut_profile_points: Sequence,
    *,
    direction: Tuple[float, float, float] = (0.0, 0.0, 1.0),
    tol: float = 1e-7,
) -> dict:
    """Build a validated cutter ``Body`` for a wirecut operation.

    The cutter is an extruded prism whose profile is the 2-D cut profile
    (expressed in the plane perpendicular to *direction*) extruded through-all
    along *direction* by the full depth of the solid bounding box.  The
    returned ``body`` is the cutter solid, not the result of the boolean cut.

    Parameters
    ----------
    solid_bbox : [width, depth, height]
        Bounding box of the solid being cut (all > 0).
    cut_profile_points : sequence of [x, y]
        2-D profile points in the XY plane (at least 3).  The polygon must
        be convex or simply connected (no self-intersections).
    direction : (dx, dy, dz)
        Through-cut direction (default: (0, 0, 1) = cut along Z).
    tol : float
        Topological tolerance.

    Returns
    -------
    dict
        ok, body, cut_depth, cut_area, path_length, n_faces, n_edges,
        n_vertices, geometry_params.  On error: ok=False, reason.
    """
    _ZERO: dict = {
        "ok": False,
        "reason": "",
        "body": None,
        "cut_depth": 0.0,
        "cut_area": 0.0,
        "path_length": 0.0,
        "n_faces": 0,
        "n_edges": 0,
        "n_vertices": 0,
        "geometry_params": {},
    }

    try:
        bbox = [float(d) for d in solid_bbox]
    except Exception as exc:
        return {**_ZERO, "reason": f"invalid solid_bbox: {exc}"}
    if len(bbox) != 3 or any(d <= 0 for d in bbox):
        return {**_ZERO, "reason": f"solid_bbox must be 3 positive dims; got {bbox}"}

    try:
        profile_pts_2d = [np.asarray(p, dtype=float).reshape(-1)[:2]
                          for p in cut_profile_points]
    except Exception as exc:
        return {**_ZERO, "reason": f"invalid cut_profile_points: {exc}"}

    if len(profile_pts_2d) < 3:
        return {**_ZERO, "reason": "cut_profile_points needs at least 3 points for a closed polygon"}

    try:
        dir_vec = _vec3(direction)
    except Exception as exc:
        return {**_ZERO, "reason": f"invalid direction: {exc}"}
    dir_norm = float(np.linalg.norm(dir_vec))
    if dir_norm < 1e-10:
        return {**_ZERO, "reason": "direction must be a non-zero vector"}
    dir_unit = dir_vec / dir_norm

    # Cut depth: max extent of bbox along direction
    bbox_corners = np.array([
        [sx * bbox[0], sy * bbox[1], sz * bbox[2]]
        for sx in (0, 1) for sy in (0, 1) for sz in (0, 1)
    ])
    projections = bbox_corners @ dir_unit
    cut_depth = float(projections.max() - projections.min())

    # Path length (2-D perimeter of profile)
    path_length_2d = sum(
        float(np.linalg.norm(profile_pts_2d[i + 1] - profile_pts_2d[i]))
        for i in range(len(profile_pts_2d) - 1)
    )
    # Close the loop for area computation
    cut_area = path_length_2d * cut_depth

    # ── Build cutter solid ──────────────────────────────────────────────
    # Lift 2-D profile into 3-D (embed in the plane perpendicular to direction).
    # We build a local coordinate frame (u, v) perpendicular to dir_unit.
    # For direction=(0,0,1): u=(1,0,0), v=(0,1,0) → 2D XY maps directly.
    # For general direction: u = perp to dir_unit, v = dir_unit × u.
    ref = np.array([1.0, 0.0, 0.0])
    if abs(float(np.dot(ref, dir_unit))) > 0.9:
        ref = np.array([0.0, 1.0, 0.0])
    u_ax = _unit3(np.cross(dir_unit, ref))
    v_ax = _unit3(np.cross(dir_unit, u_ax))

    profile_3d = [
        pt[0] * u_ax + pt[1] * v_ax
        for pt in profile_pts_2d
    ]

    # Extrusion vector: dir_unit * cut_depth
    extrude_dir = dir_unit * cut_depth

    try:
        body = _brep_extrude_to_body(profile_3d, extrude_dir, tol=tol)
    except _BuildError as exc:
        return {**_ZERO, "reason": f"wirecut_body build failed: {exc}"}
    except Exception as exc:
        return {**_ZERO, "reason": f"wirecut_body failed: {exc}"}

    # Validate explicitly
    res = _validate_body(body)
    if not res["ok"]:
        return {**_ZERO, "reason": f"wirecut_body: invalid Body: {res['errors']}"}

    counts = body.euler_counts()
    return {
        "ok": True,
        "reason": "",
        "body": body,
        "cut_depth": cut_depth,
        "cut_area": cut_area,
        "path_length": path_length_2d,
        "n_faces": counts["F"],
        "n_edges": counts["E"],
        "n_vertices": counts["V"],
        "geometry_params": {
            "solid_bbox": bbox,
            "num_profile_points": len(profile_pts_2d),
            "direction": dir_unit.tolist(),
            "cut_depth": cut_depth,
            "tol": tol,
            "occ_available": _OCC_AVAILABLE,
        },
    }


def pipe_body(
    path_points: Sequence,
    outer_radius: float,
    inner_radius: float,
    *,
    tol: float = 1e-7,
) -> dict:
    """Sweep an annular (washer) cross-section along a straight line → ``Body``.

    For a straight-line path, the result is an exact annular cylinder with
    volume ``π(R_out² − R_in²) × L``.  The body passes ``validate_body`` with
    genus 1 (one through-hole).

    Parameters
    ----------
    path_points : sequence of [x, y, z]
        Spine polyline (at least 2 points).  Currently only the first and
        last points are used; intermediate points are ignored (straight-line
        approximation).  For a single-segment straight path the result is
        analytic.
    outer_radius : float
        Outer radius of the annular cross-section (> 0).
    inner_radius : float
        Inner radius (> 0, < outer_radius).
    tol : float
        Topological tolerance.

    Returns
    -------
    dict
        ok, body, volume, length, outer_radius, inner_radius, n_faces,
        n_edges, n_vertices, geometry_params.  On error: ok=False, reason.

    Notes
    -----
    Oracle: ``volume = π(R_out² − R_in²) × L`` exact to ≤ 1e-6 relative
    tolerance.  ``validate_body`` passes with genus 1.
    """
    _ZERO: dict = {
        "ok": False,
        "reason": "",
        "body": None,
        "volume": 0.0,
        "length": 0.0,
        "outer_radius": 0.0,
        "inner_radius": 0.0,
        "n_faces": 0,
        "n_edges": 0,
        "n_vertices": 0,
        "geometry_params": {},
    }

    try:
        pts = [_vec3(p) for p in path_points]
    except Exception as exc:
        return {**_ZERO, "reason": f"invalid path_points: {exc}"}

    if len(pts) < 2:
        return {**_ZERO, "reason": "path_points must have at least 2 points"}

    if not isinstance(outer_radius, (int, float)) or outer_radius <= 0:
        return {**_ZERO, "reason": f"outer_radius must be > 0; got {outer_radius!r}"}
    if not isinstance(inner_radius, (int, float)) or inner_radius <= 0:
        return {**_ZERO, "reason": f"inner_radius must be > 0; got {inner_radius!r}"}
    if inner_radius >= outer_radius:
        return {**_ZERO, "reason": (
            f"inner_radius ({inner_radius}) must be < outer_radius ({outer_radius})"
        )}

    outer_radius = float(outer_radius)
    inner_radius = float(inner_radius)

    # Use start and end points (straight-line path)
    p_start = pts[0]
    p_end = pts[-1]
    d_vec = p_end - p_start
    length = float(np.linalg.norm(d_vec))

    if length < 1e-12:
        return {**_ZERO, "reason": "path_points are coincident (zero length)"}

    # Analytic volume: annular cylinder
    volume = math.pi * (outer_radius ** 2 - inner_radius ** 2) * length

    # ── Build washer face using region_difference ─────────────────────────
    # The outer loop is a circle of radius R_out; the inner loop is a circle
    # of radius R_in.  region_difference(outer_loop, inner_loop) returns a
    # Face with one outer CCW loop and one inner CW hole loop.
    from kerf_cad_core.geom.region2d import make_circle_loop, region_difference
    from kerf_cad_core.geom.brep_build import extrude_face_to_body as _extrude_face

    outer_loop = make_circle_loop(0.0, 0.0, outer_radius)
    inner_loop = make_circle_loop(0.0, 0.0, inner_radius)
    washer_face = region_difference(outer_loop, inner_loop)
    if washer_face is None:
        return {**_ZERO, "reason": "region_difference returned None; inner circle may be outside outer"}

    # The washer face is in the Z=0 plane; extrude along the path direction.
    # We need to transform the washer face so its plane normal aligns with
    # the path direction.
    #
    # The path direction is d_vec; the washer face's plane normal is (0,0,1).
    # We need to rotate the washer face so (0,0,1) maps to d_unit.
    # However, extrude_face_to_body takes a face + direction, so we can
    # simply pass d_vec as the direction and let the function handle it.
    # The face is already in the Z=0 plane; the extrusion will go along d_vec.
    #
    # The extrude_face_to_body function uses the face's plane normal and the
    # direction vector, then builds a washer-like solid. We use the default
    # Z-up washer and extrude in the path direction. If the path isn't along Z
    # we need to transform the face first.
    #
    # Simplest approach: always build the washer in the plane perpendicular to
    # d_vec by transforming the face vertices.

    d_unit = d_vec / length

    # Check if d_unit is already (0,0,1)
    z_ax = np.array([0.0, 0.0, 1.0])
    dot_z = float(np.dot(d_unit, z_ax))
    if abs(dot_z - 1.0) > 1e-9:
        # Need to rotate the washer face to be perpendicular to d_unit.
        # We build the face anew using make_circle_loop but in 3D.
        # The washer face from region_difference is in the Z=0 plane.
        # extrude_face_to_body will extrude along d_vec regardless of face orientation.
        # The key check: face_normal · d must not be zero (the two must not be parallel).
        # Our face_normal = (0,0,1) and d = d_unit; if they are anti-parallel or parallel
        # extrude_face_to_body still works (it uses the dot product sign to decide winding).
        # For completely arbitrary directions we need to transform the face.
        #
        # Since we're always using a circle centered at origin in Z=0 plane,
        # we'll use cylinder_to_body and subtract — but that requires boolean ops.
        #
        # Better: build the face directly in the correct plane using CircleArc3
        # with the correct x/y axes.
        from kerf_cad_core.geom.brep import CircleArc3, Vertex, Edge, Loop, Coedge, Face, Plane

        # Build orthogonal frame for the cross-section plane
        ref_ax = np.array([1.0, 0.0, 0.0])
        if abs(float(np.dot(ref_ax, d_unit))) > 0.9:
            ref_ax = np.array([0.0, 1.0, 0.0])
        x_ax = _unit3(np.cross(d_unit, ref_ax))
        y_ax = _unit3(np.cross(d_unit, x_ax))

        def _make_circle_face_3d(cx, cy, cz, r, x_axis, y_axis):
            center = np.array([cx, cy, cz], dtype=float)
            arc = CircleArc3(
                center=center, radius=r,
                x_axis=x_axis.copy(), y_axis=y_axis.copy(),
                t0=0.0, t1=2.0 * math.pi,
            )
            p0 = np.asarray(arc.evaluate(0.0), dtype=float)
            v = Vertex(p0, tol)
            edge = Edge(arc, 0.0, 2.0 * math.pi, v, v, tol)
            return Loop(coedges=[Coedge(edge, True)], is_outer=True)

        origin_3d = p_start
        outer_loop_3d = _make_circle_face_3d(
            origin_3d[0], origin_3d[1], origin_3d[2],
            outer_radius, x_ax, y_ax
        )
        inner_loop_3d = _make_circle_face_3d(
            origin_3d[0], origin_3d[1], origin_3d[2],
            inner_radius, x_ax, y_ax
        )

        # Build a washer face directly
        from kerf_cad_core.geom.brep import Shell, Solid, Body as _BrepBody
        from kerf_cad_core.geom.brep_build import extrude_face_to_body as _eftb

        # Create the washer plane
        washer_plane = Plane(origin=origin_3d.copy(), x_axis=x_ax.copy(), y_axis=y_ax.copy())
        outer_outer = outer_loop_3d
        outer_inner = inner_loop_3d
        # inner loop must be CW in the face
        inner_loop_3d_cw = Loop(
            coedges=[Coedge(outer_inner.coedges[0].edge, False)],
            is_outer=False,
        )
        washer_face_3d = Face(
            washer_plane, [outer_outer, inner_loop_3d_cw],
            orientation=True, tol=tol
        )
        try:
            body = _eftb(washer_face_3d, d_vec, tol=tol)
        except Exception as exc:
            return {**_ZERO, "reason": f"pipe_body (3D) build failed: {exc}"}
    else:
        # Path is along Z: washer is already in correct plane, just extrude
        try:
            body = _extrude_face(washer_face, d_vec, tol=tol)
        except Exception as exc:
            return {**_ZERO, "reason": f"pipe_body build failed: {exc}"}

    # Validate
    res = _validate_body(body)
    if not res["ok"]:
        return {**_ZERO, "reason": f"pipe_body: invalid Body: {res['errors']}"}

    counts = body.euler_counts()
    return {
        "ok": True,
        "reason": "",
        "body": body,
        "volume": volume,
        "length": length,
        "outer_radius": outer_radius,
        "inner_radius": inner_radius,
        "n_faces": counts["F"],
        "n_edges": counts["E"],
        "n_vertices": counts["V"],
        "geometry_params": {
            "p_start": p_start.tolist(),
            "p_end": p_end.tolist(),
            "length": length,
            "outer_radius": outer_radius,
            "inner_radius": inner_radius,
            "volume_analytic": volume,
            "tol": tol,
            "occ_available": _OCC_AVAILABLE,
        },
    }


# ---------------------------------------------------------------------------
# LLM tool registration (gated — mirrors trim_curve.py pattern)
# ---------------------------------------------------------------------------

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register  # type: ignore[import]
    from kerf_core.utils.context import ProjectCtx  # type: ignore[import]
    import json as _json
    _REGISTRY_AVAILABLE = True
except ImportError:
    _REGISTRY_AVAILABLE = False


if _REGISTRY_AVAILABLE:

    # ── pipe_along_curve ───────────────────────────────────────────────────

    _pipe_spec = ToolSpec(
        name="solid_pipe_along_curve",
        description=(
            "Sweep a circular cross-section along a 3-D polyline to produce a pipe or "
            "tube.  Supports constant or variable radius keyed to path parameter t∈[0,1], "
            "round or mitered end caps, and min-bend-radius violation checking.\n"
            "\n"
            "Returns: ok, volume (π r² L for straight path / Pappus for curved), "
            "length, centroid, bend_check (list of violations), geometry_params.\n"
            "Errors: {ok:false, reason}.  Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "path_points": {
                    "type": "array",
                    "description": "Spine polyline as [[x,y,z], ...] with ≥2 points.",
                    "items": {"type": "array", "items": {"type": "number"}},
                },
                "radius": {
                    "type": "number",
                    "description": "Constant pipe radius (> 0).",
                },
                "variable_radii": {
                    "type": "object",
                    "description": (
                        "Optional radius overrides as {t: r} where t∈[0,1] "
                        "and r is the radius at that path parameter. "
                        "Values between keys are linearly interpolated."
                    ),
                    "additionalProperties": {"type": "number"},
                },
                "cap_style": {
                    "type": "string",
                    "enum": ["round", "mitered"],
                    "description": "End-cap style (default 'round').",
                },
                "min_bend_radius": {
                    "type": "number",
                    "description": (
                        "Minimum allowed bend radius.  Any bend tighter than this "
                        "is reported in bend_check."
                    ),
                },
            },
            "required": ["path_points", "radius"],
        },
    )

    @register(_pipe_spec)
    async def run_solid_pipe_along_curve(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        path_points = a.get("path_points")
        radius = a.get("radius")
        if path_points is None or radius is None:
            return err_payload("path_points and radius are required", "BAD_ARGS")

        result = pipe_along_curve(
            path_points,
            radius,
            variable_radii=a.get("variable_radii"),
            cap_style=a.get("cap_style", "round"),
            min_bend_radius=a.get("min_bend_radius"),
        )
        if not result["ok"]:
            return err_payload(result["reason"], "OP_FAILED")
        return ok_payload({
            "volume": result["volume"],
            "length": result["length"],
            "centroid": result["centroid"],
            "bend_check": result["bend_check"],
            "cap_style": result["cap_style"],
            "geometry_params": result["geometry_params"],
        })

    # ── shell_solid ────────────────────────────────────────────────────────

    _shell_spec = ToolSpec(
        name="solid_shell_solid",
        description=(
            "Hollow a rectangular solid with a uniform wall thickness.  "
            "Specify which faces to remove (open_faces).  "
            "Returns shell mass = (V_outer − V_inner) × density, feasibility check.\n"
            "Errors: {ok:false, reason}.  Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "outer_dims": {
                    "type": "array",
                    "description": "Outer [width, depth, height] (all > 0).",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                },
                "wall_thickness": {
                    "type": "number",
                    "description": "Uniform wall thickness (> 0).",
                },
                "open_faces": {
                    "type": "array",
                    "description": "Faces to remove: subset of [top,bottom,front,back,left,right].",
                    "items": {"type": "string"},
                },
                "density": {
                    "type": "number",
                    "description": "Material density for mass calc (default 1.0).",
                },
            },
            "required": ["outer_dims", "wall_thickness"],
        },
    )

    @register(_shell_spec)
    async def run_solid_shell_solid(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        outer_dims = a.get("outer_dims")
        wall_thickness = a.get("wall_thickness")
        if outer_dims is None or wall_thickness is None:
            return err_payload("outer_dims and wall_thickness are required", "BAD_ARGS")

        result = shell_solid(
            outer_dims, wall_thickness,
            open_faces=a.get("open_faces"),
            density=a.get("density", 1.0),
        )
        if not result["ok"]:
            return err_payload(result["reason"], "OP_FAILED")
        return ok_payload({k: v for k, v in result.items() if k not in ("ok", "reason")})

    # ── variable_radius_fillet ─────────────────────────────────────────────

    _vfillet_spec = ToolSpec(
        name="solid_variable_radius_fillet",
        description=(
            "Specify an edge fillet with radius varying linearly along the edge. "
            "Validates tangency condition and min-radius manufacturing constraint.\n"
            "Errors: {ok:false, reason}.  Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "edge_length": {"type": "number", "description": "Edge length (> 0)."},
                "radius_start": {"type": "number", "description": "Fillet radius at edge start (> 0)."},
                "radius_end": {"type": "number", "description": "Fillet radius at edge end (> 0)."},
                "min_allowed_radius": {
                    "type": "number",
                    "description": "Manufacturing minimum radius (optional).",
                },
            },
            "required": ["edge_length", "radius_start", "radius_end"],
        },
    )

    @register(_vfillet_spec)
    async def run_solid_variable_radius_fillet(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        for field in ("edge_length", "radius_start", "radius_end"):
            if a.get(field) is None:
                return err_payload(f"{field} is required", "BAD_ARGS")

        result = variable_radius_fillet(
            a["edge_length"], a["radius_start"], a["radius_end"],
            min_allowed_radius=a.get("min_allowed_radius"),
        )
        if not result["ok"]:
            return err_payload(result["reason"], "OP_FAILED")
        return ok_payload({k: v for k, v in result.items() if k not in ("ok", "reason")})

    # ── draft_faces ────────────────────────────────────────────────────────

    _draft_spec = ToolSpec(
        name="solid_draft_faces",
        description=(
            "Apply a draft angle to a planar face about a pull direction. "
            "Returns taper_offset = h * tan(angle) at top and bottom of face. "
            "Useful for mold/die design and injection-molded parts.\n"
            "Errors: {ok:false, reason}.  Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "face_height": {"type": "number", "description": "Height of drafted face (> 0)."},
                "draft_angle_deg": {
                    "type": "number",
                    "description": "Draft angle in degrees (0 < angle < 90).",
                },
                "neutral_plane_offset": {
                    "type": "number",
                    "description": "Fraction [0,1] of face_height for the neutral plane (default 0.0).",
                },
            },
            "required": ["face_height", "draft_angle_deg"],
        },
    )

    @register(_draft_spec)
    async def run_solid_draft_faces(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        for field in ("face_height", "draft_angle_deg"):
            if a.get(field) is None:
                return err_payload(f"{field} is required", "BAD_ARGS")

        result = draft_faces(
            a["face_height"], a["draft_angle_deg"],
            neutral_plane_offset=a.get("neutral_plane_offset", 0.0),
        )
        if not result["ok"]:
            return err_payload(result["reason"], "OP_FAILED")
        return ok_payload({k: v for k, v in result.items() if k not in ("ok", "reason")})

    # ── rib_web ────────────────────────────────────────────────────────────

    _rib_spec = ToolSpec(
        name="solid_rib_web",
        description=(
            "Create a thickened structural rib between a profile and a solid. "
            "Computes trapezoidal cross-section with optional draft, volume, "
            "and attachment foot width.\n"
            "Errors: {ok:false, reason}.  Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "profile_length": {"type": "number", "description": "Length of rib along the solid (> 0)."},
                "rib_thickness": {"type": "number", "description": "Rib thickness at neutral plane (> 0)."},
                "rib_height": {"type": "number", "description": "Rib height above attachment surface (> 0)."},
                "draft_angle_deg": {
                    "type": "number",
                    "description": "Draft angle in degrees (default 0.0).",
                },
                "attachment_width": {
                    "type": "number",
                    "description": "Optional explicit attachment foot width; computed from draft if omitted.",
                },
            },
            "required": ["profile_length", "rib_thickness", "rib_height"],
        },
    )

    @register(_rib_spec)
    async def run_solid_rib_web(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        for field in ("profile_length", "rib_thickness", "rib_height"):
            if a.get(field) is None:
                return err_payload(f"{field} is required", "BAD_ARGS")

        result = rib_web(
            a["profile_length"], a["rib_thickness"], a["rib_height"],
            draft_angle_deg=a.get("draft_angle_deg", 0.0),
            attachment_width=a.get("attachment_width"),
        )
        if not result["ok"]:
            return err_payload(result["reason"], "OP_FAILED")
        return ok_payload({k: v for k, v in result.items() if k not in ("ok", "reason")})

    # ── wirecut ────────────────────────────────────────────────────────────

    _wirecut_spec = ToolSpec(
        name="solid_wirecut",
        description=(
            "Cut a solid with a 2-D profile swept through-all along a direction. "
            "Returns cut_area (swept face area), path_length (2-D profile arc length), "
            "cut_depth (extent of solid along direction).\n"
            "Errors: {ok:false, reason}.  Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "solid_bbox": {
                    "type": "array",
                    "description": "Solid bounding box [width, depth, height] (all > 0).",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                },
                "cut_profile_points": {
                    "type": "array",
                    "description": "2-D profile as [[x,y], ...] with ≥2 points.",
                    "items": {"type": "array", "items": {"type": "number"}},
                },
                "direction": {
                    "type": "array",
                    "description": "Sweep direction vector [dx,dy,dz] (default [0,0,1]).",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                },
            },
            "required": ["solid_bbox", "cut_profile_points"],
        },
    )

    @register(_wirecut_spec)
    async def run_solid_wirecut(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        for field in ("solid_bbox", "cut_profile_points"):
            if a.get(field) is None:
                return err_payload(f"{field} is required", "BAD_ARGS")

        result = wirecut(
            a["solid_bbox"],
            a["cut_profile_points"],
            direction=tuple(a.get("direction", [0.0, 0.0, 1.0])),
        )
        if not result["ok"]:
            return err_payload(result["reason"], "OP_FAILED")
        return ok_payload({k: v for k, v in result.items() if k not in ("ok", "reason")})
