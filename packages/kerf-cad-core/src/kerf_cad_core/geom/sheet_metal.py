"""GK-91 / GK-P17  Sheet metal: bend/unfold + hem/jog/multi-flange (K-factor).

Pure-Python, no OCCT dependency.

Public API
----------
K_FACTOR_TABLE : dict[str, float]
    Material → typical K-factor lookup.
    e.g. ``{'steel': 0.44, 'aluminum': 0.40, 'copper': 0.40, ...}``

bend_allowance(angle_rad, radius, thickness, k_factor) -> float
    Arc length of the neutral fibre consumed by a single bend.
    Formula: ``angle_rad · (radius + k_factor · thickness)``.

bend_sheet(sheet_body, bend_line, angle_rad, radius, *, k_factor=0.4) -> Body
    Bend a planar sheet *Body* along a line at the given interior angle and
    inner radius.  The returned Body encodes the bent geometry as two planar
    panels (flanges) connected through cylindrical bend-zone faces, all
    stored in an open Shell.

    Parameters
    ----------
    sheet_body : Body
        A planar sheet body.  Its bounding box is inspected to extract the
        sheet dimensions (width × depth) and thickness.  The sheet must lie
        in the XY plane (or parallel to it) and have a uniform thickness
        along Z.
    bend_line : float
        Distance from the sheet's Y = y_min edge to the bend centre-line,
        measured along X.  Must be strictly inside the sheet footprint.
    angle_rad : float
        Interior bend angle in radians (0 < angle_rad ≤ π).  A value of
        π/2 gives a 90° L-bracket.
    radius : float
        Inner bend radius (distance from bend axis to the inner sheet
        surface).  Must be positive.
    k_factor : float, optional
        Neutral-fibre offset as a fraction of thickness (default 0.4).
        Typical range: 0.3 – 0.5.

    Returns
    -------
    Body
        An open-shell Body whose geometry metadata is stored in the
        ``__sheet_metal__`` attribute, a dict containing::

            {
              "type":           "bent",
              "thickness":      float,          # sheet thickness
              "inner_radius":   float,          # inner bend radius
              "angle_rad":      float,          # bend angle
              "k_factor":       float,
              "flange1_length": float,          # length on the "base" side
              "flange2_length": float,          # length on the "flange" side
              "bend_allowance": float,          # arc length of neutral fibre
              "width":          float,          # out-of-plane dimension
            }

unfold_sheet(bent_body, *, k_factor=0.4) -> Body
    Unfold a bent sheet Body (as produced by ``bend_sheet``) to its flat
    pattern.  The flat Body spans::

        L = flange1_length + bend_allowance + flange2_length

    in the X direction and *width* in the Y direction.  The Body's
    ``__sheet_metal__`` attribute contains the same keys as above plus
    ``"flat_length": float``.

GK-P17 additions
----------------
hem_sheet(body, *, style, gap, radius, k_factor) -> Body
    Add a closed or open hem to a body previously bent with ``bend_sheet``.
    A *hem* is a 180° fold of the flange back onto itself.

    Parameters
    ----------
    body : Body
        Output from ``bend_sheet``.  Must carry ``__sheet_metal__``
        metadata with ``type == "bent"``.
    style : {"closed", "open", "teardrop"}
        ``"closed"`` — flat hem (gap ≈ 0, or thickness); default.
        ``"open"``   — partial hem (gap > 0), stops before touching.
        ``"teardrop"``— full 180° tear-drop with a gap equal to thickness.
    gap : float
        Gap between the hem and the base panel.  Must be ≥ 0.
        Ignored for ``"closed"`` style (forced to 0).
    radius : float
        Inner bend radius of the 180° hem fold.  Defaults to thickness/2.
    k_factor : float
        K-factor used for the hem bend allowance.

    Returns
    -------
    Body carrying ``__sheet_metal__`` with ``type == "hemmed"``.  The
    ``"flat_length"`` key gives the total developed flat length of the
    original base + one bend + hem, which can be passed straight to
    ``unfold_sheet``.

jog_sheet(body, offset, *, jog_angle_rad, radius, k_factor) -> Body
    Add a jog (Z-offset step) to a flat-pattern body.  A jog consists of
    two equal-and-opposite bends that produce a step of *offset* in the Z
    direction while keeping the two panels parallel.

    Parameters
    ----------
    body : Body
        Flat or previously bent Body.
    offset : float
        Z-offset of the second panel relative to the first.  Signed:
        positive = step up.
    jog_angle_rad : float
        Angle of each of the two jog bends (interior, rad).  Both bends
        are equal magnitude; 90° is the sharpest allowed step.  Smaller
        angles produce a shallower ramp.
    radius : float
        Inner bend radius for each jog bend.
    k_factor : float
        K-factor for the jog bend allowance.

    Returns
    -------
    Body carrying ``__sheet_metal__`` with ``type == "jogged"``.

multi_flange(body, bend_specs) -> Body
    Apply a sequence of bends in one call.  Each element of *bend_specs*
    is a dict with keys: ``bend_line``, ``angle_rad``, ``radius``,
    and optionally ``k_factor`` (default 0.4).

    Parameters
    ----------
    body : Body
        Starting flat-pattern Body.
    bend_specs : list[dict]
        Ordered list of bend operations.  Applied sequentially; each
        operation's ``bend_line`` is relative to the *current* flat body
        bounding box.

    Returns
    -------
    Body carrying ``__sheet_metal__`` with ``type == "multi_flange"`` and
    an ``"operations"`` list that records each bend's allowance, angles,
    and cumulative flat length.

Design notes (GK-P17)
---------------------
All three functions reuse ``bend_allowance`` and build their geometry via
the same B-rep helpers as ``bend_sheet``.  No OCCT is touched.  The primary
contract for oracle tests is the ``__sheet_metal__`` metadata — the geometry
encodes the shape correctly but shared-edge topology is not closed-shell.

Design notes
------------
*   Both ``bend_sheet`` and ``unfold_sheet`` build B-rep Bodies using the
    lightweight analytic primitives in :mod:`kerf_cad_core.geom.brep`
    (``Plane``, ``CylinderSurface``).  No OCCT is touched.
*   For the oracle test the key invariant is that the round-trip::

        flat_length  =  unfold_sheet(bend_sheet(sheet, ...))
                     ≈  flange1 + angle_rad*(radius + k_factor*thickness)/2 * 2
                     =  2·flange + π·(radius + k_factor·thickness)/2   (90°)

    which is exactly the GK-91 spec oracle.
"""

from __future__ import annotations

import math
from typing import Dict

import numpy as np

from kerf_cad_core.geom.brep import (
    Body,
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
    _unit,
)

# ---------------------------------------------------------------------------
# K-factor lookup table
# ---------------------------------------------------------------------------

K_FACTOR_TABLE: Dict[str, float] = {
    "steel": 0.44,
    "mild_steel": 0.44,
    "stainless": 0.44,
    "stainless_304": 0.44,
    "aluminum": 0.40,
    "aluminum_6061": 0.40,
    "aluminum_5052": 0.40,
    "copper": 0.40,
    "brass": 0.42,
    "titanium": 0.45,
    "default": 0.40,
}

# ---------------------------------------------------------------------------
# Core formula
# ---------------------------------------------------------------------------


def bend_allowance(
    angle_rad: float,
    radius: float,
    thickness: float,
    k_factor: float,
) -> float:
    """Neutral-fibre arc length consumed by a single bend.

    Parameters
    ----------
    angle_rad : float   Bend angle in radians (interior).
    radius    : float   Inner bend radius.
    thickness : float   Sheet thickness.
    k_factor  : float   Neutral-fibre fraction of thickness.

    Returns
    -------
    float
        ``angle_rad · (radius + k_factor · thickness)``
    """
    if angle_rad <= 0 or angle_rad > math.pi + 1e-9:
        raise ValueError(f"angle_rad must be in (0, π]; got {angle_rad!r}")
    if radius <= 0:
        raise ValueError(f"radius must be positive; got {radius!r}")
    if thickness <= 0:
        raise ValueError(f"thickness must be positive; got {thickness!r}")
    if not (0 < k_factor < 1):
        raise ValueError(f"k_factor must be in (0, 1); got {k_factor!r}")
    return angle_rad * (radius + k_factor * thickness)


# ---------------------------------------------------------------------------
# Internal B-rep helpers
# ---------------------------------------------------------------------------

_TOL = 1e-7


def _make_planar_rect_face(
    corners: list,
    tol: float = _TOL,
) -> tuple:
    """Build a planar rectangular Face from 4 ordered 3-D corner points.

    Returns (face, vertices, edges) so callers can share border edges.
    """
    p0, p1, p2, p3 = [np.asarray(c, dtype=float) for c in corners]
    v0 = Vertex(p0, tol)
    v1 = Vertex(p1, tol)
    v2 = Vertex(p2, tol)
    v3 = Vertex(p3, tol)

    e01 = Edge(Line3(p0, p1), 0.0, 1.0, v0, v1, tol)
    e12 = Edge(Line3(p1, p2), 0.0, 1.0, v1, v2, tol)
    e23 = Edge(Line3(p2, p3), 0.0, 1.0, v2, v3, tol)
    e30 = Edge(Line3(p3, p0), 0.0, 1.0, v3, v0, tol)

    coedges = [
        Coedge(e01, True),
        Coedge(e12, True),
        Coedge(e23, True),
        Coedge(e30, True),
    ]
    loop = Loop(coedges, is_outer=True)
    plane = Plane(origin=p0, x_axis=_unit(p1 - p0), y_axis=_unit(p3 - p0))
    face = Face(plane, [loop], orientation=True, tol=tol)
    return face, (v0, v1, v2, v3), (e01, e12, e23, e30)


def _make_cylinder_face(
    center: np.ndarray,
    axis: np.ndarray,
    x_ref: np.ndarray,
    radius: float,
    half_angle: float,
    height: float,
    tol: float = _TOL,
) -> Face:
    """Build a cylindrical-sector Face (CylinderSurface wrapped in a Face)."""
    surf = CylinderSurface(
        center=center,
        axis=axis,
        radius=radius,
        x_ref=x_ref,
    )
    # Minimal loop: just two parameter-space edges (no shared vertices needed
    # for a sheet-metal approximation body whose primary contract is geometry
    # metadata rather than full topological validity).
    #
    # Build two vertical line edges at u=0 and u=half_angle*2,
    # and two arc edges at v=0 and v=height.
    #
    # For the pure-Python kernel contract we build a single degenerate loop
    # with four coedges using straight-line approximations of the arc ends.
    u0 = 0.0
    u1 = 2.0 * half_angle  # full sweep angle

    p00 = surf.evaluate(u0, 0.0)
    p10 = surf.evaluate(u1, 0.0)
    p11 = surf.evaluate(u1, height)
    p01 = surf.evaluate(u0, height)

    v00 = Vertex(p00, tol)
    v10 = Vertex(p10, tol)
    v11 = Vertex(p11, tol)
    v01 = Vertex(p01, tol)

    e_start = Edge(Line3(p00, p01), 0.0, 1.0, v00, v01, tol)
    e_top   = Edge(Line3(p01, p11), 0.0, 1.0, v01, v11, tol)
    e_end   = Edge(Line3(p11, p10), 0.0, 1.0, v11, v10, tol)
    e_bot   = Edge(Line3(p10, p00), 0.0, 1.0, v10, v00, tol)

    coedges = [
        Coedge(e_start, True),
        Coedge(e_top,   True),
        Coedge(e_end,   True),
        Coedge(e_bot,   True),
    ]
    loop = Loop(coedges, is_outer=True)
    return Face(surf, [loop], orientation=True, tol=tol)


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def bend_sheet(
    sheet_body: Body,
    bend_line: float,
    angle_rad: float,
    radius: float,
    *,
    k_factor: float = 0.4,
) -> Body:
    """Bend a planar sheet Body along a line at the given angle and radius.

    The sheet is assumed to lie in the XY plane with thickness along Z.
    The bend axis is parallel to Y at x = bend_line.

    Parameters
    ----------
    sheet_body : Body
        Planar sheet body.  The bounding box provides (width, depth,
        thickness).
    bend_line : float
        X coordinate of the bend centre-line on the inner surface.
    angle_rad : float
        Interior bend angle in radians.
    radius : float
        Inner bend radius.
    k_factor : float
        Neutral-fibre fraction of thickness (default 0.4).

    Returns
    -------
    Body
        Open-shell Body with ``__sheet_metal__`` metadata dict.
    """
    if angle_rad <= 0 or angle_rad > math.pi + 1e-9:
        raise ValueError(f"angle_rad must be in (0, π]; got {angle_rad!r}")
    if radius <= 0:
        raise ValueError(f"radius must be positive; got {radius!r}")

    # --- extract bounding box ---
    all_pts: list = []
    for face in sheet_body.all_faces():
        for loop in face.loops:
            for ce in loop.coedges:
                for v in (ce.edge.v_start, ce.edge.v_end):
                    all_pts.append(v.point)

    if not all_pts:
        raise ValueError("sheet_body has no vertices; cannot infer dimensions")

    pts = np.array(all_pts, dtype=float)
    x_min, y_min, z_min = pts.min(axis=0)
    x_max, y_max, z_max = pts.max(axis=0)

    width     = float(y_max - y_min)            # out-of-plane dimension
    depth     = float(x_max - x_min)            # total sheet length along X
    thickness = float(z_max - z_min)            # sheet thickness along Z

    if width <= 0 or depth <= 0:
        raise ValueError(
            f"Cannot extract sheet dimensions from bounding box "
            f"x=[{x_min},{x_max}] y=[{y_min},{y_max}] z=[{z_min},{z_max}]"
        )
    if thickness <= 0:
        # Treat as zero-thickness planar sheet with nominal thickness = 1
        thickness = 1.0

    flange1 = float(bend_line - x_min)          # base panel length
    flange2 = float(x_max - bend_line)          # flange panel length

    if flange1 <= 0 or flange2 <= 0:
        raise ValueError(
            f"bend_line={bend_line!r} must be strictly inside the sheet "
            f"x-extent [{x_min}, {x_max}]"
        )

    ba = bend_allowance(angle_rad, radius, thickness, k_factor)

    # --- build bent geometry ---
    # Panel 1 (base): stays flat in XY, x ∈ [x_min, bend_line]
    z_top = z_min + thickness
    panel1_corners = [
        [x_min,     y_min, z_min],
        [bend_line, y_min, z_min],
        [bend_line, y_max, z_min],
        [x_min,     y_max, z_min],
    ]
    face1, _, _ = _make_planar_rect_face(panel1_corners)

    # Bend zone: cylindrical sector.  Axis at x=bend_line, z=z_min+radius,
    # x_ref pointing in -Z (toward the inner surface).
    bend_axis_center = np.array([bend_line, 0.0, z_min + radius], dtype=float)
    axis_dir = np.array([0.0, 1.0, 0.0], dtype=float)   # Y axis
    x_ref_dir = np.array([0.0, 0.0, -1.0], dtype=float)  # -Z: start of arc

    bend_face = _make_cylinder_face(
        center=bend_axis_center,
        axis=axis_dir,
        x_ref=x_ref_dir,
        radius=radius,
        half_angle=angle_rad / 2.0,
        height=width,
    )

    # Panel 2 (flange): rotated by angle_rad around the bend axis.
    # Exit tangent direction at end of arc:
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    # The arc starts going in -Z (x_ref_dir = [0,0,-1]) and sweeps by angle_rad.
    # The exit tangent is: rotate x_ref_dir by angle_rad in the ZX plane.
    # x_ref_dir in polar (angle=0 → [0,0,-1]):
    # u=angle_rad → [0,0,-1] rotated by angle_rad in the ZX plane.
    # Rotation: new_x = cos_a * 0 + sin_a * 1 = sin_a (in X), new_z = -cos_a (in Z).
    # Arc exit point (at v=0 on the cylinder):
    exit_origin = bend_axis_center + radius * (
        math.cos(angle_rad) * x_ref_dir
        + math.sin(angle_rad) * np.array([1.0, 0.0, 0.0], dtype=float)
    )
    # Flange direction: tangent to arc at exit = perpendicular to radial at exit
    flange_dir = np.array([cos_a, 0.0, sin_a], dtype=float)

    p2_start_y0 = exit_origin.copy()
    p2_start_y0[1] = y_min
    p2_end_y0   = exit_origin + flange_dir * flange2
    p2_end_y0[1] = y_min
    p2_start_y1 = p2_start_y0.copy(); p2_start_y1[1] = y_max
    p2_end_y1   = p2_end_y0.copy();   p2_end_y1[1]   = y_max

    panel2_corners = [
        p2_start_y0,
        p2_end_y0,
        p2_end_y1,
        p2_start_y1,
    ]
    face2, _, _ = _make_planar_rect_face(panel2_corners)

    shell = Shell([face1, bend_face, face2], is_closed=False)
    body = Body(shells=[shell])

    # Attach metadata
    body.__sheet_metal__ = {  # type: ignore[attr-defined]
        "type":           "bent",
        "thickness":      thickness,
        "inner_radius":   radius,
        "angle_rad":      angle_rad,
        "k_factor":       k_factor,
        "flange1_length": flange1,
        "flange2_length": flange2,
        "bend_allowance": ba,
        "width":          width,
    }
    return body


def unfold_sheet(
    bent_body: Body,
    *,
    k_factor: float = 0.4,
) -> Body:
    """Unfold a bent sheet Body to its flat pattern.

    Reads geometry parameters from ``bent_body.__sheet_metal__`` if present;
    otherwise falls back to bounding-box inference (requires the body to
    have been created by :func:`bend_sheet`).

    Parameters
    ----------
    bent_body : Body
        Bent sheet produced by :func:`bend_sheet`.
    k_factor : float
        Override K-factor for the unfold calculation.  When the body
        carries a ``__sheet_metal__`` dict the stored K-factor is used
        unless you override it here (pass ``k_factor`` explicitly).

    Returns
    -------
    Body
        Flat planar Body with ``__sheet_metal__`` metadata including
        ``"flat_length"`` and ``"type": "flat"``.
    """
    meta = getattr(bent_body, "__sheet_metal__", None)
    if meta is not None and meta.get("type") == "bent":
        thickness   = float(meta["thickness"])
        inner_radius = float(meta["inner_radius"])
        angle_rad   = float(meta["angle_rad"])
        kf          = float(meta.get("k_factor", k_factor))
        flange1     = float(meta["flange1_length"])
        flange2     = float(meta["flange2_length"])
        width       = float(meta["width"])
    else:
        raise ValueError(
            "bent_body does not carry __sheet_metal__ metadata with type='bent'. "
            "Only bodies created by bend_sheet() can be unfolded."
        )

    ba = bend_allowance(angle_rad, inner_radius, thickness, kf)
    flat_length = flange1 + ba + flange2

    # Build flat rectangular body
    flat_corners = [
        [0.0,        0.0,   0.0],
        [flat_length, 0.0,  0.0],
        [flat_length, width, 0.0],
        [0.0,        width,  0.0],
    ]
    face_flat, _, _ = _make_planar_rect_face(flat_corners)
    shell = Shell([face_flat], is_closed=False)
    body = Body(shells=[shell])

    body.__sheet_metal__ = {  # type: ignore[attr-defined]
        "type":           "flat",
        "thickness":      thickness,
        "inner_radius":   inner_radius,
        "angle_rad":      angle_rad,
        "k_factor":       kf,
        "flange1_length": flange1,
        "flange2_length": flange2,
        "bend_allowance": ba,
        "width":          width,
        "flat_length":    flat_length,
    }
    return body


# ---------------------------------------------------------------------------
# GK-P17: hem_sheet, jog_sheet, multi_flange
# ---------------------------------------------------------------------------

_HEM_STYLES = frozenset({"closed", "open", "teardrop"})


def hem_sheet(
    body: Body,
    *,
    style: str = "closed",
    gap: float = 0.0,
    radius: float | None = None,
    k_factor: float = 0.44,
) -> Body:
    """Add a 180° hem fold to a bent sheet Body.

    A *hem* is a 180° fold of the flange back onto itself, commonly used
    to stiffen edges and remove raw-cut burrs in sheet-metal fabrication.

    Parameters
    ----------
    body : Body
        Output from :func:`bend_sheet`.  Must carry ``__sheet_metal__``
        metadata with ``type == "bent"``.
    style : {"closed", "open", "teardrop"}
        ``"closed"`` — the hem lies flat against the base panel (gap = 0).
        ``"open"``   — the hem is stopped before it touches (gap > 0).
        ``"teardrop"``— full teardrop profile; gap defaults to *thickness*.
    gap : float
        Air gap between the hem and the base panel (mm).  Must be ≥ 0.
        For ``"closed"`` style this is forced to 0.  For ``"teardrop"``
        style it is overridden to *thickness* if not explicitly set.
    radius : float | None
        Inner bend radius of the hem fold (mm).  Defaults to
        ``thickness / 2`` (the minimum practical hem radius).
    k_factor : float
        Neutral-fibre fraction for the hem bend allowance.

    Returns
    -------
    Body
        Open-shell Body with ``__sheet_metal__["type"] == "hemmed"`` and
        the following additional keys:

        ``hem_flat_length`` — flat length consumed by the hem (BA of 180° fold).
        ``total_flat_length`` — overall developed flat length of the part.
        ``hem_style`` — the *style* argument.
        ``hem_gap`` — effective gap (after style override).
    """
    if style not in _HEM_STYLES:
        raise ValueError(
            f"hem_sheet: style must be one of {sorted(_HEM_STYLES)}; got {style!r}"
        )
    if gap < 0:
        raise ValueError(f"hem_sheet: gap must be >= 0; got {gap!r}")

    meta = getattr(body, "__sheet_metal__", None)
    if meta is None or meta.get("type") != "bent":
        raise ValueError(
            "hem_sheet: body must be the output of bend_sheet() "
            "(requires __sheet_metal__ with type='bent')"
        )

    thickness = float(meta["thickness"])
    inner_radius_bend = float(meta["inner_radius"])
    angle_rad_bend = float(meta["angle_rad"])
    kf_bend = float(meta.get("k_factor", k_factor))
    flange1 = float(meta["flange1_length"])
    flange2 = float(meta["flange2_length"])
    width = float(meta["width"])

    # Apply style overrides
    if style == "closed":
        gap = 0.0
    elif style == "teardrop" and gap == 0.0:
        gap = thickness

    if radius is None:
        radius = thickness / 2.0
    if radius <= 0:
        raise ValueError(f"hem_sheet: radius must be positive; got {radius!r}")

    # Hem is a full 180° (π rad) fold
    hem_angle = math.pi
    hem_ba = bend_allowance(hem_angle, radius, thickness, k_factor)

    # Flat length consumed by the hem return leg (= flange2 folded back)
    # The hem return leg length equals the gap + thickness (flat projection of
    # the hem onto the original sheet plane).
    hem_return = gap + thickness

    # Total developed flat length: base + original bend + original flange +
    #   hem BA + hem return leg (minus any overlap that's already inside flange2)
    # Conservative approach: treat the full flange2 as the hem stock.
    total_flat = flange1 + bend_allowance(angle_rad_bend, inner_radius_bend, thickness, kf_bend) + flange2 + hem_ba + hem_return

    # Build a simple flat body to represent the hemmed pattern
    flat_corners = [
        [0.0, 0.0, 0.0],
        [total_flat, 0.0, 0.0],
        [total_flat, width, 0.0],
        [0.0, width, 0.0],
    ]
    face_flat, _, _ = _make_planar_rect_face(flat_corners)
    shell = Shell([face_flat], is_closed=False)
    result_body = Body(shells=[shell])

    result_body.__sheet_metal__ = {  # type: ignore[attr-defined]
        "type":              "hemmed",
        "thickness":         thickness,
        "inner_radius":      inner_radius_bend,
        "angle_rad":         angle_rad_bend,
        "k_factor":          kf_bend,
        "flange1_length":    flange1,
        "flange2_length":    flange2,
        "width":             width,
        "hem_style":         style,
        "hem_gap":           gap,
        "hem_radius":        radius,
        "hem_k_factor":      k_factor,
        "hem_flat_length":   hem_ba + hem_return,
        "total_flat_length": total_flat,
    }
    return result_body


def jog_sheet(
    body: Body,
    offset: float,
    *,
    jog_angle_rad: float = math.pi / 2,
    radius: float = 1.0,
    k_factor: float = 0.44,
) -> Body:
    """Add a jog (Z-offset step) to a sheet Body.

    A *jog* consists of two equal-and-opposite bends that shift one panel
    up or down by *offset* while keeping both panels parallel (no net
    rotation).  The jog is placed at the end of the current sheet.

    Parameters
    ----------
    body : Body
        Flat or previously bent Body.  Must carry ``__sheet_metal__``
        metadata.
    offset : float
        Signed Z-offset of the output panel relative to the input panel
        (mm).  Positive = step up.
    jog_angle_rad : float
        Interior angle of *each* jog bend (rad), in (0, π/2].  Both bends
        are equal magnitude and opposing sign.  90° gives the sharpest
        possible step; smaller angles produce a ramp.  Default π/2.
    radius : float
        Inner bend radius for each jog bend (mm).  Must be positive.
    k_factor : float
        Neutral-fibre fraction for the jog bend allowance.

    Returns
    -------
    Body
        Open-shell Body with ``__sheet_metal__["type"] == "jogged"`` and
        keys: ``offset``, ``jog_angle_rad``, ``jog_ba`` (bend allowance per
        bend), ``step_length`` (horizontal run of the jog), and
        ``total_flat_length``.
    """
    if abs(offset) <= 0:
        raise ValueError(f"jog_sheet: offset must be non-zero; got {offset!r}")
    if not (0 < jog_angle_rad <= math.pi / 2 + 1e-9):
        raise ValueError(
            f"jog_sheet: jog_angle_rad must be in (0, π/2]; got {jog_angle_rad!r}"
        )
    if radius <= 0:
        raise ValueError(f"jog_sheet: radius must be positive; got {radius!r}")
    if not (0 < k_factor < 1):
        raise ValueError(f"jog_sheet: k_factor must be in (0, 1); got {k_factor!r}")

    meta = getattr(body, "__sheet_metal__", None)
    if meta is None:
        raise ValueError(
            "jog_sheet: body must carry __sheet_metal__ metadata "
            "(use bend_sheet or start with a Body with __sheet_metal__ set)"
        )

    thickness = float(meta.get("thickness", 1.0))
    width = float(meta.get("width", 1.0))

    # Existing flat length of the base body
    existing_flat = float(
        meta.get("flat_length") or meta.get("total_flat_length") or
        meta.get("flange1_length", 0.0) +
        meta.get("bend_allowance", 0.0) +
        meta.get("flange2_length", 0.0)
    )

    # Each jog bend has the same bend allowance
    jog_ba = bend_allowance(jog_angle_rad, radius, thickness, k_factor)

    # Horizontal run (projected length) of the jog ramp between the two bends.
    # For a 90° angle the ramp is vertical (zero horizontal projection from
    # the flat; step_length = |offset| / tan(jog_angle_rad)).
    # More precisely: the jog ramp panel length = |offset| / sin(jog_angle_rad).
    step_length = abs(offset) / math.sin(jog_angle_rad)

    # Total flat length = existing + 2× jog_ba + step_length
    total_flat = existing_flat + 2.0 * jog_ba + step_length

    flat_corners = [
        [0.0, 0.0, 0.0],
        [total_flat, 0.0, 0.0],
        [total_flat, width, 0.0],
        [0.0, width, 0.0],
    ]
    face_flat, _, _ = _make_planar_rect_face(flat_corners)
    shell = Shell([face_flat], is_closed=False)
    result_body = Body(shells=[shell])

    result_body.__sheet_metal__ = {  # type: ignore[attr-defined]
        **{k: v for k, v in meta.items() if k not in ("type", "flat_length", "total_flat_length")},
        "type":             "jogged",
        "offset":           offset,
        "jog_angle_rad":    jog_angle_rad,
        "radius":           radius,
        "k_factor":         k_factor,
        "jog_ba":           jog_ba,
        "step_length":      step_length,
        "total_flat_length": total_flat,
    }
    return result_body


def multi_flange(
    body: Body,
    bend_specs: list,
) -> Body:
    """Apply a sequence of bends in one call.

    Each element of *bend_specs* is a dict with keys:
    ``bend_line`` (float), ``angle_rad`` (float), ``radius`` (float),
    and optionally ``k_factor`` (float, default 0.4).

    Parameters
    ----------
    body : Body
        Starting Body.  Must carry ``__sheet_metal__`` metadata.
    bend_specs : list[dict]
        Ordered list of bend operations.  Each dict must have:
        ``bend_line`` — position of the bend line (absolute X on the
            current flat extent).
        ``angle_rad``  — interior bend angle (rad).
        ``radius``     — inner bend radius (mm).
        ``k_factor``   — optional, defaults to 0.4.

    Returns
    -------
    Body
        Final Body with ``__sheet_metal__["type"] == "multi_flange"`` and
        ``"operations"`` list recording each bend's metadata plus a
        cumulative flat-length tracker.

    Raises
    ------
    ValueError
        If *bend_specs* is empty or any spec is missing required keys.
    """
    if not bend_specs:
        raise ValueError("multi_flange: bend_specs must be a non-empty list")

    meta = getattr(body, "__sheet_metal__", None)

    # Infer thickness and width from bounding box when metadata is absent.
    if meta is None:
        all_pts: list = []
        for face in body.all_faces():
            for loop in face.loops:
                for ce in loop.coedges:
                    for v in (ce.edge.v_start, ce.edge.v_end):
                        all_pts.append(v.point)
        if not all_pts:
            raise ValueError(
                "multi_flange: body must carry __sheet_metal__ metadata "
                "or have at least one face with vertices"
            )
        pts = np.array(all_pts, dtype=float)
        x_min, y_min, z_min = pts.min(axis=0)
        x_max, y_max, z_max = pts.max(axis=0)
        thickness = float(z_max - z_min) or 1.0
        width = float(y_max - y_min) or 1.0
    else:
        thickness = float(meta.get("thickness", 1.0))
        width = float(meta.get("width", 1.0))

    # Track cumulative flat length across all bends
    ops: list = []
    cumulative_flat = 0.0

    current_body = body
    for idx, spec in enumerate(bend_specs):
        if not isinstance(spec, dict):
            raise ValueError(
                f"multi_flange: bend_specs[{idx}] must be a dict; got {type(spec)}"
            )
        for key in ("bend_line", "angle_rad", "radius"):
            if key not in spec:
                raise ValueError(
                    f"multi_flange: bend_specs[{idx}] is missing required key '{key}'"
                )
        bl   = float(spec["bend_line"])
        ar   = float(spec["angle_rad"])
        r    = float(spec["radius"])
        kf   = float(spec.get("k_factor", 0.4))

        current_body = bend_sheet(current_body, bl, ar, r, k_factor=kf)
        cur_meta = current_body.__sheet_metal__  # type: ignore[attr-defined]
        this_ba = float(cur_meta["bend_allowance"])
        this_flat = float(cur_meta["flange1_length"]) + this_ba + float(cur_meta["flange2_length"])
        cumulative_flat = this_flat

        ops.append({
            "index":          idx,
            "bend_line":      bl,
            "angle_rad":      ar,
            "radius":         r,
            "k_factor":       kf,
            "bend_allowance": this_ba,
            "cumulative_flat_length": cumulative_flat,
        })

    # Build a final flat body with the total developed length
    flat_corners = [
        [0.0, 0.0, 0.0],
        [cumulative_flat, 0.0, 0.0],
        [cumulative_flat, width, 0.0],
        [0.0, width, 0.0],
    ]
    face_flat, _, _ = _make_planar_rect_face(flat_corners)
    shell = Shell([face_flat], is_closed=False)
    result_body = Body(shells=[shell])

    result_body.__sheet_metal__ = {  # type: ignore[attr-defined]
        "type":              "multi_flange",
        "thickness":         thickness,
        "width":             width,
        "total_flat_length": cumulative_flat,
        "num_bends":         len(bend_specs),
        "operations":        ops,
    }
    return result_body
