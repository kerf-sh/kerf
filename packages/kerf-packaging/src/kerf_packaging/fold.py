"""
kerf_packaging.fold — 3-D fold preview for dieline flat patterns.

``fold_dieline`` sweeps panels along their fold lines, producing a 3-D
carton shape as a dict of panel-name → list of 3-D vertices.

Algorithm
---------
1. Identify the *base panel* (first panel in fold_edges that has no inbound
   fold, or the panel named "front" / "base" / "bottom" as a heuristic).
2. Place the base panel in the XY plane at z = 0.
3. Walk the fold-edge graph (BFS) from the base panel: for each fold edge
   rotate the connected panel by its fold angle around the shared fold axis.
4. Return a ``FoldResult`` with:
       - ``panels``   — dict of panel_name → list of (x, y, z) tuples (4 corners).
       - ``is_closed`` — True if all expected faces are present and the shape
                        appears topologically closed (all bounding-box faces covered).
       - ``warnings`` — list of diagnostic strings.

Pure Python + math only (no numpy / scipy dependency).

Public API
----------
``fold_dieline(dieline, fold_angle_override=None) -> FoldResult``

``FoldResult``
    Dataclass with ``panels``, ``is_closed``, ``warnings``.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from kerf_packaging.dieline import Dieline, DiPanel, FoldEdge


# ---------------------------------------------------------------------------
# 3-D vector helpers (pure Python)
# ---------------------------------------------------------------------------

Vec3 = tuple[float, float, float]


def _v3(x: float, y: float, z: float) -> Vec3:
    return (x, y, z)


def _add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _scale(a: Vec3, s: float) -> Vec3:
    return (a[0] * s, a[1] * s, a[2] * s)


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _norm(a: Vec3) -> float:
    return math.sqrt(a[0] ** 2 + a[1] ** 2 + a[2] ** 2)


def _normalise(a: Vec3) -> Vec3:
    n = _norm(a)
    if n < 1e-12:
        return (0.0, 0.0, 0.0)
    return (a[0] / n, a[1] / n, a[2] / n)


def _rotate_around_axis(point: Vec3, axis_pt: Vec3, axis_dir: Vec3, angle_deg: float) -> Vec3:
    """
    Rotate *point* around the line through *axis_pt* in direction *axis_dir*
    by *angle_deg* degrees (right-hand rule).
    """
    u = _normalise(axis_dir)
    theta = math.radians(angle_deg)
    c = math.cos(theta)
    s = math.sin(theta)

    # Translate so axis passes through origin
    p = _sub(point, axis_pt)

    # Rodrigues' rotation formula
    rotated = _add(
        _add(
            _scale(p, c),
            _scale(_cross(u, p), s),
        ),
        _scale(u, _dot(u, p) * (1.0 - c)),
    )

    # Translate back
    return _add(rotated, axis_pt)


# ---------------------------------------------------------------------------
# Panel corners in 2-D → 3-D (initial placement in XY plane)
# ---------------------------------------------------------------------------

def _panel_corners_2d(panel: DiPanel) -> list[Vec3]:
    """Return the four corners of a rectangular panel in 2-D (z = 0)."""
    if panel.polygon and len(panel.polygon) >= 3:
        return [(v.x, v.y, 0.0) for v in panel.polygon]
    x0, y0 = panel.x, panel.y
    x1, y1 = panel.x + panel.width, panel.y + panel.height
    return [
        (x0, y0, 0.0),
        (x1, y0, 0.0),
        (x1, y1, 0.0),
        (x0, y1, 0.0),
    ]


# ---------------------------------------------------------------------------
# FoldResult
# ---------------------------------------------------------------------------

@dataclass
class FoldResult:
    """
    Result of folding a dieline into a 3-D shape.

    Attributes
    ----------
    panels : dict[str, list[Vec3]]
        Panel name → list of 3-D corner vertices after folding.
    is_closed : bool
        Heuristic: True if the shape appears topologically closed (all six
        faces of the expected bounding box are accounted for).
    bounding_box : tuple[Vec3, Vec3]
        (min_corner, max_corner) of the folded 3-D shape.
    warnings : list[str]
        Diagnostic messages.
    """
    panels: dict[str, list[Vec3]] = field(default_factory=dict)
    is_closed: bool = False
    bounding_box: tuple[Vec3, Vec3] = field(
        default_factory=lambda: ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    )
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def fold_dieline(
    dieline: Dieline,
    fold_angle_override: Optional[float] = None,
) -> FoldResult:
    """
    Fold a 2-D dieline into a 3-D carton shape.

    Parameters
    ----------
    dieline : Dieline
        A fully-populated dieline (from an ECMA generator or custom).
    fold_angle_override : float or None
        If given, override all fold angles to this value (degrees).
        Useful for partial-fold animation frames (0 = flat, 90 = closed).

    Returns
    -------
    FoldResult
        Panel corners in 3-D, closed flag, bounding box, and warnings.

    Notes
    -----
    The algorithm places panels in the XY plane first (their original flat
    coordinates), then walks the fold-edge graph BFS from a root panel,
    rotating each newly-encountered panel around the shared fold axis by
    the specified fold angle.

    For the RSC: the "front" panel is used as the root; all other body panels
    fold around their shared vertical fold lines.  The flap panels fold around
    the horizontal fold lines.

    Limitation: this implementation handles orthogonal (horizontal/vertical)
    fold axes correctly.  Diagonal fold axes (e.g., tuck corners) are
    approximated.
    """
    warnings_out: list[str] = []

    # ----- Build panel lookup --------------------------------------------
    panel_by_name: dict[str, DiPanel] = {p.name: p for p in dieline.panels}
    if not panel_by_name:
        return FoldResult(warnings=["no panels in dieline"])

    # Initial 3-D positions = flat 2-D coordinates (z=0)
    panel_verts: dict[str, list[Vec3]] = {
        name: _panel_corners_2d(p)
        for name, p in panel_by_name.items()
    }

    # ----- Choose root panel ---------------------------------------------
    root = _choose_root(dieline, panel_by_name)
    if root not in panel_verts:
        root = next(iter(panel_verts))

    # ----- BFS fold walk -------------------------------------------------
    # Graph: fold_edges define adjacency
    adjacency: dict[str, list[FoldEdge]] = {name: [] for name in panel_by_name}
    for fe in dieline.fold_edges:
        if fe.panel_a in adjacency:
            adjacency[fe.panel_a].append(fe)
        if fe.panel_b in adjacency:
            adjacency[fe.panel_b].append(fe)

    visited: set[str] = {root}
    queue: deque[str] = deque([root])

    # Track the cumulative 3-D transform for each panel as a list of
    # (axis_pt, axis_dir, angle) operations applied so far.
    # We keep it simple: store the accumulated 3-D corners in panel_verts.
    # When we fold panel B around the shared edge with already-folded panel A,
    # the fold axis is defined by the CURRENT (already-rotated) positions of
    # the shared edge endpoints.

    while queue:
        current_name = queue.popleft()
        for fe in adjacency[current_name]:
            # Determine which panel is the neighbour
            if fe.panel_a == current_name:
                neighbour_name = fe.panel_b
            else:
                neighbour_name = fe.panel_a

            if neighbour_name in visited:
                continue
            if neighbour_name not in panel_verts:
                warnings_out.append(
                    f"fold edge references unknown panel '{neighbour_name}'"
                )
                continue

            visited.add(neighbour_name)
            queue.append(neighbour_name)

            angle = fold_angle_override if fold_angle_override is not None else fe.angle_deg

            if abs(angle) < 1e-6:
                # No rotation needed
                continue

            # The fold axis is the shared edge.  We need the 3-D positions of
            # the axis endpoints.  The fold line is defined in 2-D (flat layout)
            # coords; the current panel's vertices are already in 3-D (after
            # prior rotations).  We find the axis endpoints by locating the
            # fold line's 2-D endpoints in the CURRENT panel's vertex set.
            axis_pt1, axis_pt2 = _find_axis_in_3d(
                fe.line.x1, fe.line.y1, fe.line.x2, fe.line.y2,
                panel_by_name[current_name],
                panel_verts[current_name],
            )

            if axis_pt1 is None or axis_pt2 is None:
                # Fallback: use the 2-D fold line endpoints directly (z=0)
                axis_pt1 = (fe.line.x1, fe.line.y1, 0.0)
                axis_pt2 = (fe.line.x2, fe.line.y2, 0.0)

            axis_dir = _sub(axis_pt2, axis_pt1)
            if _norm(axis_dir) < 1e-9:
                warnings_out.append(
                    f"degenerate fold axis for edge {fe.panel_a}↔{fe.panel_b}"
                )
                continue

            # Rotate the NEIGHBOUR panel's vertices around the fold axis
            new_verts = [
                _rotate_around_axis(v, axis_pt1, axis_dir, -angle)
                for v in panel_verts[neighbour_name]
            ]
            panel_verts[neighbour_name] = new_verts

    # Any unvisited panels are disconnected from the fold graph
    unvisited = set(panel_by_name) - visited
    if unvisited:
        warnings_out.append(
            f"panels not reachable from fold graph root '{root}': "
            + ", ".join(sorted(unvisited))
        )

    # ----- Bounding box --------------------------------------------------
    all_verts = [v for vlist in panel_verts.values() for v in vlist]
    if all_verts:
        xs = [v[0] for v in all_verts]
        ys = [v[1] for v in all_verts]
        zs = [v[2] for v in all_verts]
        bb_min = (min(xs), min(ys), min(zs))
        bb_max = (max(xs), max(ys), max(zs))
    else:
        bb_min = bb_max = (0.0, 0.0, 0.0)

    # ----- Closed check --------------------------------------------------
    is_closed = _check_closed(dieline, visited)

    return FoldResult(
        panels=panel_verts,
        is_closed=is_closed,
        bounding_box=(bb_min, bb_max),
        warnings=warnings_out,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _choose_root(dieline: Dieline, panel_by_name: dict) -> str:
    """Pick the root panel for BFS fold walk."""
    # Prefer "front" or "base" or "bottom" in that order
    for preferred in ("front", "base", "bottom", "left"):
        if preferred in panel_by_name:
            return preferred
    # Fall back to the first panel
    return next(iter(panel_by_name))


def _find_axis_in_3d(
    x1_2d: float, y1_2d: float,
    x2_2d: float, y2_2d: float,
    panel: DiPanel,
    verts_3d: list[Vec3],
    tol: float = 0.5,
) -> tuple[Optional[Vec3], Optional[Vec3]]:
    """
    Find the 3-D positions of the fold axis endpoints by matching their
    original 2-D coordinates to the panel's vertex list.

    Returns (pt1_3d, pt2_3d) or (None, None) if not found.
    """
    corners_2d = _panel_corners_2d(panel)

    def _closest_3d(x: float, y: float):
        best_d = float("inf")
        best_v = None
        for i, (cx, cy, _) in enumerate(corners_2d):
            d = math.hypot(x - cx, y - cy)
            if d < best_d:
                best_d = d
                best_v = verts_3d[i] if i < len(verts_3d) else None
        if best_d <= tol and best_v is not None:
            return best_v
        # Interpolate along edges for mid-edge fold points
        n = len(corners_2d)
        for i in range(n):
            j = (i + 1) % n
            ax, ay, _ = corners_2d[i]
            bx, by, _ = corners_2d[j]
            # Parametric closest point on segment
            dx, dy = bx - ax, by - ay
            seg_len_sq = dx * dx + dy * dy
            if seg_len_sq < 1e-12:
                continue
            t = ((x - ax) * dx + (y - ay) * dy) / seg_len_sq
            t = max(0.0, min(1.0, t))
            px, py = ax + t * dx, ay + t * dy
            d = math.hypot(x - px, y - py)
            if d < best_d and d <= tol:
                best_d = d
                # Interpolate between 3-D corners
                if i < len(verts_3d) and j < len(verts_3d):
                    va = verts_3d[i]
                    vb = verts_3d[j]
                    best_v = _add(_scale(va, 1.0 - t), _scale(vb, t))
        return best_v

    pt1 = _closest_3d(x1_2d, y1_2d)
    pt2 = _closest_3d(x2_2d, y2_2d)
    return pt1, pt2


def _check_closed(dieline: Dieline, visited: set[str]) -> bool:
    """
    Heuristic: the shape is "closed" if the expected face panels are all
    visited and the dieline has enough panels for a complete box.

    For an RSC (C02): we need front, back, left, right, and at least the
    bottom-flap or top-flap panels.
    """
    expected_body = {"front", "back", "left", "right"}
    if not expected_body.issubset(set(dieline.panels[i].name for i in range(len(dieline.panels)))):
        # Tray or display style: check base + sides
        expected_tray = {"base", "front_panel", "back_panel", "left_panel", "right_panel"}
        if expected_tray.issubset(visited):
            return True
        # If most panels are visited it's plausibly closed
        total = len(dieline.panels)
        return total > 0 and len(visited) >= total * 0.8

    # RSC: body panels + at least two flap sets
    body_ok = expected_body.issubset(visited)
    flap_panels = [
        name for name in visited
        if "flap" in name or "tuck" in name or "dust" in name
    ]
    return body_ok and len(flap_panels) >= 4
