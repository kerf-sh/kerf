"""
kerf_cad_core.jewelry.profile_lib
===================================

MatrixGold / RhinoGold parity: parametric 2D cross-section profile library for
ring shanks, bangles, and wire jewellery.

Each profile is a named, parametric closed 2D polyline suitable as a sweep
profile.  The module returns geometry and section properties (area, centroid,
second moments of area, perimeter, inner/outer radii) in a plain dict — no
OCCT required.

Coordinate convention
---------------------
The profile sits in the XY plane.  The ring bore axis is Z.

  X-axis:  across the band width  (finger-to-finger, labial direction)
  Y-axis:  radial (thumb-nail to palm, thickness direction)
    +Y = outside (skin of ring, away from finger)
    -Y = inside  (bore, touching finger)

Origin is at the centroid of the outer bounding rectangle.

Named profiles
--------------
  comfort_fit         -- rounded inside, sharp/flat outside (standard comfort)
  court               -- rounded outside, flat inside (UK "court" shape)
  flat                -- rectangular cross-section, sharp corners throughout
  half_round          -- semicircle outside, flat inside
  d_shape             -- D-profile: flat inside, full round outside
  knife_edge          -- V-wedge, apex at +Y (sharp outside edge)
  square              -- square cross-section (w == t)
  rectangle           -- alias for flat
  stamped_edge        -- flat with two symmetric edge-radius fillets on the
                         outside corners (rolled/pressed look)
  bombe               -- domed outside + flat inside
  bevelled            -- flat with four straight chamfers at corners
  double_bombe        -- bombe profile mirrored: convex both sides (lens)
  flat_with_comfort_edge -- flat with comfort-fit rounding only at inside corners
  channel_ready       -- flat band with a central groove on the outside face for
                         stone channel setting
  knife_bombe         -- knife-edge outside + bombe (dome) inside

LLM tools registered
---------------------
  jewelry_list_profiles      -- read: list catalogue + metadata
  jewelry_get_profile        -- read: compute one profile by name + params
  jewelry_compare_comfort    -- read: qualitative ergonomic comparison of two profiles

All tools are read-only (write=False) and gated.

Pure Python -- never raises.  Missing profiles / bad params return an error dict.
"""

from __future__ import annotations

import json
import math
from typing import Any, Optional

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register

_PI = math.pi

# ---------------------------------------------------------------------------
# Internal profile registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, dict] = {}


def _reg(name: str, description: str, params: list):
    """Register a profile entry in the catalogue."""
    _REGISTRY[name] = {"name": name, "description": description, "params": params}


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _arc_points(cx: float, cy: float, r: float, a0: float, a1: float, n: int) -> list:
    """Return n+1 points along an arc from angle a0 to a1 (radians, CCW)."""
    pts = []
    for i in range(n + 1):
        t = a0 + (a1 - a0) * i / n
        pts.append((cx + r * math.cos(t), cy + r * math.sin(t)))
    return pts


def _poly_area(pts: list) -> float:
    """Signed area via shoelace formula (positive = CCW)."""
    n = len(pts)
    a = 0.0
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        a += x0 * y1 - x1 * y0
    return a / 2.0


def _poly_centroid(pts: list) -> tuple:
    """Centroid of a closed polygon (Shoelace)."""
    n = len(pts)
    a = _poly_area(pts)
    if abs(a) < 1e-12:
        return (0.0, 0.0)
    cx = cy = 0.0
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        cross = x0 * y1 - x1 * y0
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    f = 1.0 / (6.0 * a)
    return (round(cx * f, 8), round(cy * f, 8))


def _poly_second_moments(pts: list, cx: float, cy: float) -> tuple:
    """Second moments of area Ixx, Iyy about centroidal axes."""
    n = len(pts)
    ixx = iyy = 0.0
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        cross = x0 * y1 - x1 * y0
        ixx += (y0 ** 2 + y0 * y1 + y1 ** 2) * cross
        iyy += (x0 ** 2 + x0 * x1 + x1 ** 2) * cross
    a = _poly_area(pts)
    ixx_o = abs(ixx) / 12.0
    iyy_o = abs(iyy) / 12.0
    ixx_c = ixx_o - abs(a) * cy ** 2
    iyy_c = iyy_o - abs(a) * cx ** 2
    return (round(max(ixx_c, 0.0), 6), round(max(iyy_c, 0.0), 6))


def _poly_perimeter(pts: list) -> float:
    """Perimeter of a closed polygon."""
    n = len(pts)
    p = 0.0
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        p += math.hypot(x1 - x0, y1 - y0)
    return p


def _build_result(name: str, pts: list, inner_r: float, outer_r: float,
                  extra=None) -> dict:
    """Build the standard profile result dict."""
    area = abs(_poly_area(pts))
    cx, cy = _poly_centroid(pts)
    ixx, iyy = _poly_second_moments(pts, cx, cy)
    perim = _poly_perimeter(pts)
    result = {
        "name": name,
        "polyline": [(round(x, 6), round(y, 6)) for x, y in pts],
        "area": round(area, 6),
        "centroid": (round(cx, 6), round(cy, 6)),
        "Ixx": round(ixx, 6),
        "Iyy": round(iyy, 6),
        "perimeter": round(perim, 6),
        "inner_radius": round(inner_r, 6),
        "outer_radius": round(outer_r, 6),
    }
    if extra:
        result.update(extra)
    return result


# ---------------------------------------------------------------------------
# Catalogue metadata
# ---------------------------------------------------------------------------

_reg("comfort_fit",
     "Rounded inside surface for finger comfort; flat/sharp outside. "
     "Industry standard for everyday rings.",
     [
         {"name": "width", "type": "number", "description": "Band width in mm", "required": True},
         {"name": "thickness", "type": "number", "description": "Band thickness (radial) in mm", "required": True},
         {"name": "inner_radius", "type": "number", "description": "Inside dome radius (mm). Defaults to thickness/2.", "required": False},
     ])

_reg("court",
     "Rounded outside, flat inside. UK-style comfort profile.",
     [
         {"name": "width", "type": "number", "description": "Band width in mm", "required": True},
         {"name": "thickness", "type": "number", "description": "Band thickness in mm", "required": True},
         {"name": "outer_radius", "type": "number", "description": "Outside dome radius (mm). Defaults to thickness/2.", "required": False},
     ])

_reg("flat",
     "Rectangular cross-section, sharp corners throughout.",
     [
         {"name": "width", "type": "number", "description": "Band width in mm", "required": True},
         {"name": "thickness", "type": "number", "description": "Band thickness in mm", "required": True},
     ])

_reg("half_round",
     "Semicircular outside, flat inside. Classic wire profile.",
     [
         {"name": "width", "type": "number", "description": "Band width in mm", "required": True},
         {"name": "thickness", "type": "number", "description": "Band thickness in mm (<=width/2)", "required": True},
     ])

_reg("d_shape",
     "D-shape: full round outside, flat inside. Heavy-weight look.",
     [
         {"name": "width", "type": "number", "description": "Band width in mm", "required": True},
         {"name": "thickness", "type": "number", "description": "Band thickness in mm", "required": True},
     ])

_reg("knife_edge",
     "V-wedge profile with apex at outside (+Y). Dramatic look.",
     [
         {"name": "width", "type": "number", "description": "Band width in mm", "required": True},
         {"name": "thickness", "type": "number", "description": "Band thickness in mm", "required": True},
     ])

_reg("square",
     "Square cross-section (width == thickness). Geometric/modern look.",
     [
         {"name": "width", "type": "number", "description": "Side length in mm", "required": True},
     ])

_reg("rectangle",
     "Alias for flat. Explicit rectangular cross-section.",
     [
         {"name": "width", "type": "number", "description": "Band width in mm", "required": True},
         {"name": "thickness", "type": "number", "description": "Band thickness in mm", "required": True},
     ])

_reg("stamped_edge",
     "Flat band with edge-radius fillets on outside corners (rolled/pressed appearance).",
     [
         {"name": "width", "type": "number", "description": "Band width in mm", "required": True},
         {"name": "thickness", "type": "number", "description": "Band thickness in mm", "required": True},
         {"name": "edge_radius", "type": "number", "description": "Corner fillet radius in mm. Defaults to thickness*0.15.", "required": False},
     ])

_reg("bombe",
     "Domed outside + flat inside. Substantial, rounded feel.",
     [
         {"name": "width", "type": "number", "description": "Band width in mm", "required": True},
         {"name": "thickness", "type": "number", "description": "Band thickness in mm", "required": True},
         {"name": "dome_radius", "type": "number", "description": "Outside dome radius in mm. Defaults to width.", "required": False},
     ])

_reg("bevelled",
     "Flat with four straight chamfers at corners.",
     [
         {"name": "width", "type": "number", "description": "Band width in mm", "required": True},
         {"name": "thickness", "type": "number", "description": "Band thickness in mm", "required": True},
         {"name": "chamfer", "type": "number", "description": "Chamfer size in mm. Defaults to min(width,thickness)*0.15.", "required": False},
     ])

_reg("double_bombe",
     "Convex outside and convex inside -- lenticular / lens cross-section.",
     [
         {"name": "width", "type": "number", "description": "Band width in mm", "required": True},
         {"name": "thickness", "type": "number", "description": "Band thickness in mm", "required": True},
         {"name": "dome_radius", "type": "number", "description": "Dome radius for both sides (mm). Defaults to width.", "required": False},
     ])

_reg("flat_with_comfort_edge",
     "Flat outside, comfort-fit rounded inside corners only.",
     [
         {"name": "width", "type": "number", "description": "Band width in mm", "required": True},
         {"name": "thickness", "type": "number", "description": "Band thickness in mm", "required": True},
         {"name": "inner_radius", "type": "number", "description": "Inside corner fillet radius (mm). Defaults to thickness*0.3.", "required": False},
     ])

_reg("channel_ready",
     "Flat band with a central groove on the outside face for stone channel setting.",
     [
         {"name": "width", "type": "number", "description": "Band width in mm", "required": True},
         {"name": "thickness", "type": "number", "description": "Band thickness in mm", "required": True},
         {"name": "groove_width", "type": "number", "description": "Groove width in mm. Defaults to width*0.4.", "required": False},
         {"name": "groove_depth", "type": "number", "description": "Groove depth in mm. Defaults to thickness*0.25.", "required": False},
     ])

_reg("knife_bombe",
     "Knife-edge outside (V-apex at +Y) combined with a domed inside surface.",
     [
         {"name": "width", "type": "number", "description": "Band width in mm", "required": True},
         {"name": "thickness", "type": "number", "description": "Band thickness in mm", "required": True},
         {"name": "inner_radius", "type": "number", "description": "Inside dome radius (mm). Defaults to width.", "required": False},
     ])


# ---------------------------------------------------------------------------
# Profile builders
# ---------------------------------------------------------------------------

_ARC_N = 24  # points per quarter-circle arc


def _build_comfort_fit(width: float, thickness: float, inner_radius=None) -> dict:
    w, t = width, thickness
    r = inner_radius if inner_radius is not None else t / 2.0
    r = min(r, t / 2.0, w / 2.0)

    hw = w / 2.0
    cy_inner = -t / 2.0 + r
    pts = []
    pts.append((-hw, t / 2.0))
    pts.append((hw, t / 2.0))
    pts.append((hw, cy_inner))
    pts += _arc_points(0.0, cy_inner, hw if r >= hw else r, 0.0, _PI, _ARC_N)
    pts.append((-hw, cy_inner))

    return _build_result("comfort_fit", pts, r, 0.0,
                         {"comfort_inner_radius": round(r, 6)})


def _build_court(width: float, thickness: float, outer_radius=None) -> dict:
    w, t = width, thickness
    r = outer_radius if outer_radius is not None else t / 2.0
    r = min(r, t / 2.0, w / 2.0)

    hw = w / 2.0
    cy_outer = t / 2.0 - r
    pts = []
    pts.append((-hw, -t / 2.0))
    pts.append((hw, -t / 2.0))
    pts.append((hw, cy_outer))
    pts += _arc_points(0.0, cy_outer, hw if r >= hw else r, 0.0, _PI, _ARC_N)
    pts.append((-hw, cy_outer))

    return _build_result("court", pts, 0.0, r,
                         {"comfort_outer_radius": round(r, 6)})


def _build_flat(width: float, thickness: float) -> dict:
    hw = width / 2.0
    ht = thickness / 2.0
    pts = [(-hw, -ht), (hw, -ht), (hw, ht), (-hw, ht)]
    return _build_result("flat", pts, 0.0, 0.0)


def _build_half_round(width: float, thickness: float) -> dict:
    hw = width / 2.0
    pts = []
    pts.append((-hw, 0.0))
    pts.append((hw, 0.0))
    pts += _arc_points(0.0, 0.0, hw, 0.0, _PI, _ARC_N * 2)

    return _build_result("half_round", pts, 0.0, hw,
                         {"arc_radius": round(hw, 6)})


def _build_d_shape(width: float, thickness: float) -> dict:
    hw = width / 2.0
    ht = thickness / 2.0
    yc = -hw ** 2 / (4.0 * ht) if ht > 0 else 0.0
    arc_r = math.hypot(hw, -ht - yc)

    a_start = math.atan2(-ht - yc, -hw)
    a_end = math.atan2(-ht - yc, hw)
    if a_end <= a_start:
        a_end += 2 * _PI

    pts = []
    pts.append((hw, -ht))
    pts.append((-hw, -ht))
    pts += _arc_points(0.0, yc, arc_r, a_start, a_end, _ARC_N * 2)

    return _build_result("d_shape", pts, 0.0, arc_r - abs(yc + ht),
                         {"arc_radius": round(arc_r, 6), "arc_centre_y": round(yc, 6)})


def _build_knife_edge(width: float, thickness: float) -> dict:
    hw = width / 2.0
    ht = thickness / 2.0
    pts = [
        (-hw, -ht),
        (hw, -ht),
        (0.0, ht),
    ]
    return _build_result("knife_edge", pts, 0.0, 0.0,
                         {"apex_y": round(ht, 6)})


def _build_square(width: float) -> dict:
    return _build_flat(width, width)


def _build_rectangle(width: float, thickness: float) -> dict:
    return _build_flat(width, thickness)


def _build_stamped_edge(width: float, thickness: float, edge_radius=None) -> dict:
    w, t = width, thickness
    r = edge_radius if edge_radius is not None else t * 0.15
    r = min(r, w / 2.0, t / 2.0)
    hw = w / 2.0
    ht = t / 2.0
    n = max(4, _ARC_N // 4)
    pts = []
    pts.append((-hw, -ht))
    pts.append((hw, -ht))
    pts += _arc_points(hw - r, ht - r, r, 0.0, _PI / 2.0, n)
    pts += _arc_points(-(hw - r), ht - r, r, _PI / 2.0, _PI, n)

    return _build_result("stamped_edge", pts, 0.0, r,
                         {"edge_radius": round(r, 6)})


def _build_bombe(width: float, thickness: float, dome_radius=None) -> dict:
    w, t = width, thickness
    hw = w / 2.0
    ht = t / 2.0
    r = dome_radius if dome_radius is not None else w
    r = max(r, hw)

    yc = ht - r
    y_right = yc + math.sqrt(r ** 2 - hw ** 2) if hw < r else yc

    pts = []
    pts.append((-hw, -ht))
    pts.append((hw, -ht))
    pts.append((hw, y_right))
    a_start = math.atan2(y_right - yc, hw)
    a_end = math.atan2(y_right - yc, -hw)
    if a_end < a_start:
        a_end += 2 * _PI
    pts += _arc_points(0.0, yc, r, a_start, a_end, _ARC_N * 2)
    pts.append((-hw, -ht))
    if pts[-1] == pts[0]:
        pts.pop()

    return _build_result("bombe", pts, 0.0, r,
                         {"dome_radius": round(r, 6), "dome_centre_y": round(yc, 6)})


def _build_bevelled(width: float, thickness: float, chamfer=None) -> dict:
    w, t = width, thickness
    c = chamfer if chamfer is not None else min(w, t) * 0.15
    c = min(c, w / 2.0, t / 2.0)
    hw = w / 2.0
    ht = t / 2.0
    pts = [
        (-hw + c, -ht),
        (hw - c, -ht),
        (hw, -ht + c),
        (hw, ht - c),
        (hw - c, ht),
        (-hw + c, ht),
        (-hw, ht - c),
        (-hw, -ht + c),
    ]
    return _build_result("bevelled", pts, 0.0, 0.0,
                         {"chamfer": round(c, 6)})


def _build_double_bombe(width: float, thickness: float, dome_radius=None) -> dict:
    w, t = width, thickness
    hw = w / 2.0
    ht = t / 2.0
    r = dome_radius if dome_radius is not None else w
    r = max(r, hw)

    yc_out = ht - r
    yc_in = -ht + r

    y_side_out = yc_out + math.sqrt(r ** 2 - hw ** 2) if hw < r else yc_out
    y_side_in = yc_in - math.sqrt(r ** 2 - hw ** 2) if hw < r else yc_in

    pts = []
    pts.append((hw, y_side_in))
    a_start_in = math.atan2(y_side_in - yc_in, hw)
    a_end_in = math.atan2(y_side_in - yc_in, -hw)
    if a_end_in > a_start_in:
        a_end_in -= 2 * _PI
    pts += _arc_points(0.0, yc_in, r, a_start_in, a_end_in, _ARC_N * 2)
    pts.append((-hw, y_side_out))
    a_start_out = math.atan2(y_side_out - yc_out, -hw)
    a_end_out = math.atan2(y_side_out - yc_out, hw)
    if a_end_out <= a_start_out:
        a_end_out += 2 * _PI
    pts += _arc_points(0.0, yc_out, r, a_start_out, a_end_out, _ARC_N * 2)

    return _build_result("double_bombe", pts, r, r,
                         {"dome_radius": round(r, 6)})


def _build_flat_with_comfort_edge(width: float, thickness: float, inner_radius=None) -> dict:
    w, t = width, thickness
    r = inner_radius if inner_radius is not None else t * 0.3
    r = min(r, w / 2.0, t / 2.0)
    hw = w / 2.0
    ht = t / 2.0
    n = max(4, _ARC_N // 4)
    pts = []
    pts.append((-hw, ht))
    pts.append((hw, ht))
    pts.append((hw, -ht + r))
    pts += _arc_points(hw - r, -ht + r, r, 0.0, -_PI / 2.0, n)
    pts.append((-hw + r, -ht))
    pts += _arc_points(-hw + r, -ht + r, r, -_PI / 2.0, -_PI, n)
    pts.append((-hw, -ht + r))

    return _build_result("flat_with_comfort_edge", pts, r, 0.0,
                         {"comfort_inner_radius": round(r, 6)})


def _build_channel_ready(width: float, thickness: float,
                          groove_width=None, groove_depth=None) -> dict:
    w, t = width, thickness
    gw = groove_width if groove_width is not None else w * 0.4
    gd = groove_depth if groove_depth is not None else t * 0.25
    gw = min(gw, w * 0.8)
    gd = min(gd, t * 0.6)
    hw = w / 2.0
    ht = t / 2.0
    ghw = gw / 2.0
    pts = []
    pts.append((-hw, -ht))
    pts.append((hw, -ht))
    pts.append((hw, ht))
    pts.append((ghw, ht))
    pts.append((ghw, ht - gd))
    pts.append((-ghw, ht - gd))
    pts.append((-ghw, ht))
    pts.append((-hw, ht))

    return _build_result("channel_ready", pts, 0.0, 0.0,
                         {"groove_width": round(gw, 6), "groove_depth": round(gd, 6)})


def _build_knife_bombe(width: float, thickness: float, inner_radius=None) -> dict:
    w, t = width, thickness
    hw = w / 2.0
    ht = t / 2.0
    r = inner_radius if inner_radius is not None else w
    r = max(r, hw)

    yc_in = -ht + r
    y_side_in = yc_in - math.sqrt(r ** 2 - hw ** 2) if hw < r else yc_in

    pts = []
    pts.append((0.0, ht))
    pts.append((hw, y_side_in))
    a_start = math.atan2(y_side_in - yc_in, hw)
    a_end = math.atan2(y_side_in - yc_in, -hw)
    if a_end > a_start:
        a_end -= 2 * _PI
    pts += _arc_points(0.0, yc_in, r, a_start, a_end, _ARC_N * 2)
    pts.append((-hw, y_side_in))

    return _build_result("knife_bombe", pts, r, 0.0,
                         {"inner_dome_radius": round(r, 6)})


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_BUILDERS = {
    "comfort_fit":             _build_comfort_fit,
    "court":                   _build_court,
    "flat":                    _build_flat,
    "half_round":              _build_half_round,
    "d_shape":                 _build_d_shape,
    "knife_edge":              _build_knife_edge,
    "square":                  _build_square,
    "rectangle":               _build_rectangle,
    "stamped_edge":            _build_stamped_edge,
    "bombe":                   _build_bombe,
    "bevelled":                _build_bevelled,
    "double_bombe":            _build_double_bombe,
    "flat_with_comfort_edge":  _build_flat_with_comfort_edge,
    "channel_ready":           _build_channel_ready,
    "knife_bombe":             _build_knife_bombe,
}


def get_profile(name: str, **params) -> dict:
    """Compute and return a named profile.

    Parameters
    ----------
    name : str
        Profile name (see list_profiles() for valid names).
    **params
        Profile-specific parameters (width, thickness, etc.).

    Returns
    -------
    dict
        Profile result with keys: name, polyline, area, centroid, Ixx, Iyy,
        perimeter, inner_radius, outer_radius, plus profile-specific extra keys.
        On error returns {"error": "...", "code": "..."} -- never raises.
    """
    try:
        name = str(name).strip().lower().replace("-", "_").replace(" ", "_")
        if name not in _BUILDERS:
            return {"error": f"Unknown profile {name!r}. Valid: {sorted(_BUILDERS)}", "code": "NOT_FOUND"}
        fn = _BUILDERS[name]
        result = fn(**params)
        return result
    except TypeError as e:
        return {"error": f"Parameter error for profile {name!r}: {e}", "code": "BAD_ARGS"}
    except Exception as e:
        return {"error": f"Internal error computing profile {name!r}: {e}", "code": "ERROR"}


def list_profiles() -> list:
    """Return the full profile catalogue.

    Returns
    -------
    list[dict]
        Each entry: {name, description, params}.
    """
    return [_REGISTRY[k] for k in sorted(_REGISTRY)]


def compare_comfort(profile_a: dict, profile_b: dict) -> dict:
    """Qualitative ergonomic comparison of two computed profiles.

    Parameters
    ----------
    profile_a, profile_b : dict
        Profile result dicts returned by get_profile().

    Returns
    -------
    dict
        Keys: winner, scores, delta, explanation.  Never raises.
    """
    try:
        def _score(p: dict) -> float:
            ir = float(p.get("inner_radius", 0.0) or 0.0)
            cir = float(p.get("comfort_inner_radius", 0.0) or 0.0)
            r = max(ir, cir)
            # Ergonomic heuristic: a rounded inner surface (dome/comfort) is the
            # primary comfort driver -- it distributes pressure over the finger.
            # Outer radius: profiles with rounded outer surface score slightly better
            # (less sharp on palm side when worn).
            outer_r = float(p.get("outer_radius", 0.0) or
                            p.get("comfort_outer_radius", 0.0) or 0.0)
            # inner_radius dominates at 85%; outer_radius secondary at 15%
            return round(r * 0.85 + outer_r * 0.15, 4)

        sa = _score(profile_a)
        sb = _score(profile_b)
        na = profile_a.get("name", "A")
        nb = profile_b.get("name", "B")

        if sa > sb:
            winner = na
            delta = sa - sb
        elif sb > sa:
            winner = nb
            delta = sb - sa
        else:
            winner = "tie"
            delta = 0.0

        return {
            "winner": winner,
            "scores": {na: round(sa, 4), nb: round(sb, 4)},
            "delta": round(delta, 4),
            "explanation": (
                f"{winner} is more ergonomic: larger inner continuity radius reduces "
                "finger pressure at band edges."
                if winner != "tie"
                else "Both profiles have equivalent ergonomic scores."
            ),
        }
    except Exception as e:
        return {"error": str(e), "code": "ERROR"}


# ---------------------------------------------------------------------------
# LLM tool: jewelry_list_profiles
# ---------------------------------------------------------------------------

_jewelry_list_profiles_spec = ToolSpec(
    name="jewelry_list_profiles",
    description=(
        "Read-only: list all named 2D cross-section profiles in the ring/band profile library.\n\n"
        "Returns a catalogue of profile names, descriptions, and accepted parameters.\n"
        "Use jewelry_get_profile to compute a specific profile's geometry and section properties."
    ),
    input_schema={
        "type": "object",
        "properties": {},
        "required": [],
    },
)


@register(_jewelry_list_profiles_spec, write=False)
async def run_jewelry_list_profiles(ctx: Any, args: bytes) -> str:
    try:
        return ok_payload(list_profiles())
    except Exception as e:
        return err_payload(f"internal error: {e}", "ERROR")


# ---------------------------------------------------------------------------
# LLM tool: jewelry_get_profile
# ---------------------------------------------------------------------------

_ALL_PROFILE_NAMES = sorted(_BUILDERS.keys())

_jewelry_get_profile_spec = ToolSpec(
    name="jewelry_get_profile",
    description=(
        "Compute a named 2D cross-section profile for ring shanks, bangles, or wire jewellery.\n\n"
        "Returns: polyline (closed 2D point list), area (mm2), centroid (mm),\n"
        "Ixx/Iyy (second moments of area, mm4), perimeter (mm),\n"
        "inner_radius/outer_radius (mm).\n\n"
        "Coordinate system: X = band width direction, Y = radial (+Y = outside).\n"
        "All dims in mm.  Use jewelry_list_profiles to browse the catalogue."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "enum": _ALL_PROFILE_NAMES,
                "description": "Profile name. Use jewelry_list_profiles to browse.",
            },
            "width": {
                "type": "number",
                "description": "Band width in mm (finger-to-finger direction).",
            },
            "thickness": {
                "type": "number",
                "description": "Band thickness in mm (radial direction). Not required for 'square'.",
            },
            "inner_radius": {
                "type": "number",
                "description": "comfort_fit / flat_with_comfort_edge / knife_bombe: inside dome radius (mm).",
            },
            "outer_radius": {
                "type": "number",
                "description": "court: outside dome radius (mm).",
            },
            "dome_radius": {
                "type": "number",
                "description": "bombe / double_bombe: dome radius (mm).",
            },
            "edge_radius": {
                "type": "number",
                "description": "stamped_edge: corner fillet radius (mm).",
            },
            "chamfer": {
                "type": "number",
                "description": "bevelled: chamfer size (mm).",
            },
            "groove_width": {
                "type": "number",
                "description": "channel_ready: groove width (mm).",
            },
            "groove_depth": {
                "type": "number",
                "description": "channel_ready: groove depth (mm).",
            },
        },
        "required": ["name", "width"],
    },
)


@register(_jewelry_get_profile_spec, write=False)
async def run_jewelry_get_profile(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args) if args.strip() else {}
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    name = str(a.pop("name", "")).strip()
    if not name:
        return err_payload("name is required", "BAD_ARGS")

    opt_floats = ["width", "thickness", "inner_radius", "outer_radius",
                  "dome_radius", "edge_radius", "chamfer", "groove_width", "groove_depth"]
    params = {}
    for key in opt_floats:
        if key in a:
            try:
                params[key] = float(a[key])
            except (TypeError, ValueError):
                return err_payload(f"{key} must be a number", "BAD_ARGS")

    result = get_profile(name, **params)
    if "error" in result:
        return err_payload(result["error"], result.get("code", "ERROR"))
    return ok_payload(result)


# ---------------------------------------------------------------------------
# LLM tool: jewelry_compare_comfort
# ---------------------------------------------------------------------------

_jewelry_compare_comfort_spec = ToolSpec(
    name="jewelry_compare_comfort",
    description=(
        "Qualitative ergonomic comparison of two ring/band cross-section profiles.\n\n"
        "Scores each profile by inner-radius continuity and outer smoothness.\n"
        "Returns winner, scores dict, delta, and an explanation string.\n\n"
        "Pass two computed profiles (as returned by jewelry_get_profile) in "
        "profile_a and profile_b."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "profile_a": {
                "type": "object",
                "description": "First profile dict (output of jewelry_get_profile).",
            },
            "profile_b": {
                "type": "object",
                "description": "Second profile dict (output of jewelry_get_profile).",
            },
        },
        "required": ["profile_a", "profile_b"],
    },
)


@register(_jewelry_compare_comfort_spec, write=False)
async def run_jewelry_compare_comfort(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args) if args.strip() else {}
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    pa = a.get("profile_a")
    pb = a.get("profile_b")
    if not isinstance(pa, dict) or not isinstance(pb, dict):
        return err_payload("profile_a and profile_b must be profile dicts", "BAD_ARGS")

    result = compare_comfort(pa, pb)
    if "error" in result:
        return err_payload(result["error"], result.get("code", "ERROR"))
    return ok_payload(result)
