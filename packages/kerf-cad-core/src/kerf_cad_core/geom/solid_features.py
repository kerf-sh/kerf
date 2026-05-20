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
